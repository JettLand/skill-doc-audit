#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dev_market_bench.py —— 市场质量基准实测器（dev-only 辅助开发工具 · 不进部署副本）

为什么需要它：
  skill-doc-audit 的检查器在「规模化真实世界」里是否稳定、doc-llm 修复后是否真的执行、
  市场长尾技能的质量分布长什么样——这些必须用批量实测验证，而不能只靠单测 fixture。
  本工具把「批量实测」流程固化成可重复命令，任何人都跑得出来、口径一致。

取样口径（与旧 run_market_audit 的关键区别 · 用户 2026-09-01 要求）：
  旧：按市场 `score`（热度）升序取最低 50（实测全 score=0 长尾）。
  新：按 **TRACE 官方质量评测分**（overall，5.0 分制）取样——取值方法与 trace-selfcheck
      的 `benchmark_official.py` 同源：`fetch_evaluation(slug)` → `parse_eval` → overall。
  规则：从「质量分最低的 1000 个候选」里随机抽取 50 做审计，避免每次采到重复样本。

为什么是近似（受 13.3 万技能规模约束，已在代码中实测确认）：
  市场列表接口只支持 score/downloads/stars/updatedAt 排序、**不返回质量分字段**；且全量
  逐个拉评测（13 万次请求）不可行。故采用「随机均匀抽样候选池 + 逐个取质量分 + 池内取
  最低 1000」的近似：候选池为全市场随机页偏移抽样的 pool 个 slug（默认 3000，散布随机页
  避免热度偏差），在其质量分内取最低 1000、再随机抽 50。这是「质量最低区间」的工程化近似，
  非字面全局最低 1000（全局最低需爬全量评测，不现实）。

子命令：
  index          构建/刷新质量索引：随机抽候选池 → 逐个 fetch_evaluation 取质量分 → 缓存
  run            采样（最低质量 1000 中抽 50）→ 下载 → 全量审计 → 报告（默认缺索引时自动 index）
  check-bump     版本监测：当前版本较记录版本出现次/主版本变动时，打印 [agent-todo] 建议

不进自动调度（用户明确要求）：
  实际跑基准（run）只在「人工要求」或「agent 评估重大版本变动后建议」时执行；
  check-bump 供 dev_self_audit 在次版本/大版本变动时打印建议（绝不动触发 run，不自动跑基准）。

退出码：
  0 正常；2 参数/路径错误；run 下被审技能出现 ERROR 属被测现象、不升退出码（与 run_market_audit 一致）。

典型用法：
  python src/scripts/dev_market_bench.py index            # 刷新质量索引（重随机候选池，约 3000 次评测请求）
  python src/scripts/dev_market_bench.py run              # 采样最低质量 1000 中 50 个 → 审计 → 报告
  python src/scripts/dev_market_bench.py run --sample 50 --seed 7   # 可复现抽样
  python src/scripts/dev_market_bench.py check-bump       # 版本监测（由 dev_self_audit 自动调用）
"""
import argparse
import concurrent.futures as futures
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone

# ── 路径（经 __file__ 解析，不依赖 CWD）──────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))            # <root>/src/scripts
ROOT = os.path.dirname(os.path.dirname(HERE))                # <root>
SRC = os.path.join(ROOT, "src")
CACHE = os.path.join(ROOT, "bench", "market_bench")          # 运行时缓存（gitignore：不进版本库）
INDEX_JSON = os.path.join(CACHE, "quality_index.json")
HISTORY_JSON = os.path.join(CACHE, "sampled_history.json")
LAST_VERSION = os.path.join(CACHE, "last_bench_version.txt")
SKILLS_DIR = os.path.join(CACHE, "skills")
RESULTS_JSON = os.path.join(CACHE, "results.json")
REPORT_MD = os.path.join(CACHE, "report.md")

PY = r"C:/Users/admin/.workbuddy/binaries/python/versions/3.13.12/python.exe"
CLI = os.path.join(SRC, "scripts", "auditlib", "cli.py")
AUDIT_FLAGS = ["--all-checks", "--deadcode-mode", "vulture",
               "--doc-llm-mode", "agent", "--json"]
PER_AUDIT_TIMEOUT = 240  # 秒

# 真实代码检查的 8 个检查器（与 CHECKER_CODES 对齐，用于回执完整性统计）
EXPECTED_CHECKERS = ["doc", "structure", "security", "runtime", "deps",
                     "deadcode", "portability", "doc-llm"]

LIST_ENDPOINTS = [
    "https://api.skillhub.cn/api/skills?pageSize={size}&page={page}",
    "https://lightmake.site/api/skills?pageSize={size}&page={page}",
]
EVAL_ENDPOINTS = [
    "https://api.skillhub.cn/api/v1/skills/{slug}/evaluation",
    "https://lightmake.site/api/v1/skills/{slug}/evaluation",
]
UA = "skill-doc-audit-market-bench/1.0"


def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# ── TRACE 质量分取值（与 trace-selfcheck/benchmark_official.py 同源）──────────
def _get_json(url, timeout=25, retries=2):
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4)
    raise last


def fetch_total():
    """市场技能总数（用于随机页偏移范围）。"""
    for tpl in LIST_ENDPOINTS:
        try:
            d = _get_json(tpl.format(size=1, page=1))
            return int((d.get("data") or {}).get("total", 0))
        except Exception:  # noqa: BLE001
            continue
    return 0


def fetch_list_page(page, size=100):
    for tpl in LIST_ENDPOINTS:
        try:
            d = _get_json(tpl.format(size=size, page=page))
            return (d.get("data") or {}).get("skills") or []
        except Exception:  # noqa: BLE001
            continue
    return []


def fetch_quality(slug):
    """返回 slug 的 TRACE 质量分（overall，0–5.0）；无评测/失败返回 None。

    取值逻辑与 trace-selfcheck 的 fetch_official_trace.fetch_evaluation + parse_eval 一致：
      dimensions -> 各子项 score 均值 -> 维度均值 -> 综合 = 各维度均值之均值。
    """
    for tpl in EVAL_ENDPOINTS:
        try:
            d = _get_json(tpl.format(slug=slug), timeout=20)
        except Exception:  # noqa: BLE001
            continue
        dims = (d or {}).get("dimensions", {})
        if not isinstance(dims, dict) or not dims:
            return None
        dim_avgs = []
        for dv in dims.values():
            items = dv.get("items", {}) if isinstance(dv, dict) else {}
            sc = [iv.get("score") for iv in items.values()
                  if isinstance(iv, dict) and isinstance(iv.get("score"), (int, float))]
            if sc:
                dim_avgs.append(sum(sc) / len(sc))
        if not dim_avgs:
            return None
        return round(sum(dim_avgs) / len(dim_avgs), 3)
    return None


# ── 质量索引（候选池 + 质量分缓存）────────────────────────────────────────────
def collect_pool(pool, page_size=100, total=None):
    """从全市场随机页偏移抽 pool 个不重复 slug（散布随机页，避免热度偏差）。"""
    if total is None:
        total = fetch_total()
    if total <= 0:
        return []
    n_pages = max(1, -(-total // page_size))
    slugs, seen = [], set()
    attempts = 0
    max_attempts = max(pool * 2, 50)
    while len(slugs) < pool and attempts < max_attempts:
        page = random.randint(1, n_pages)
        arr = fetch_list_page(page, page_size)
        if not arr:
            attempts += 1
            continue
        random.shuffle(arr)
        for it in arr:
            s = it.get("slug")
            if s and s not in seen:
                seen.add(s)
                slugs.append(s)
                if len(slugs) >= pool:
                    break
        attempts += 1
    return slugs


def build_index(pool, page_size=100):
    os.makedirs(CACHE, exist_ok=True)
    total = fetch_total()
    log("[index] 市场技能总数 ≈ %d；随机抽候选池 %d（page_size=%d）" % (total, pool, page_size))
    slugs = collect_pool(pool, page_size, total)
    if not slugs:
        log("[index] 候选池为空：无法访问市场列表接口。")
        return {}
    log("[index] 候选池实采 %d 个 slug；并发拉取 TRACE 质量分…" % len(slugs))
    results = {}
    done = 0
    with futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_quality, s): s for s in slugs}
        for fu in futures.as_completed(futs):
            s = futs[fu]
            try:
                q = fu.result()
            except Exception:  # noqa: BLE001
                q = None
            results[s] = q
            done += 1
            if done % 200 == 0 or done == len(slugs):
                nq = sum(1 for v in results.values() if v is not None)
                log("[index] 已取 %d/%d（有质量分 %d）" % (done, len(slugs), nq))
    save_index(results)
    nq = sum(1 for v in results.values() if v is not None)
    log("[index] 完成：候选 %d，有质量分 %d，无评测 %d → %s"
        % (len(results), nq, len(results) - nq, INDEX_JSON))
    return results


def load_index():
    if not os.path.isfile(INDEX_JSON):
        return None
    try:
        with open(INDEX_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def save_index(idx):
    os.makedirs(CACHE, exist_ok=True)
    with open(INDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


# ── 采样历史（避免每次采到重复样本）────────────────────────────────────────────
def recent_sampled(runs):
    if runs <= 0 or not os.path.isfile(HISTORY_JSON):
        return set()
    try:
        hist = json.load(open(HISTORY_JSON, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return set()
    out = set()
    for rec in hist[-runs:]:
        out.update(rec.get("slugs", []))
    return out


def record_sampled(slugs):
    os.makedirs(CACHE, exist_ok=True)
    hist = []
    if os.path.isfile(HISTORY_JSON):
        try:
            hist = json.load(open(HISTORY_JSON, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            hist = []
    hist.append({"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "slugs": slugs})
    hist = hist[-20:]
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)


# ── 下载 + 审计（复用旧 run_market_audit 的稳健实现）──────────────────────────
def download_and_extract(slug):
    """下载技能 zip 并解包到 skills/<slug>/，返回 (skill_dir_or_None, error_or_None)。"""
    zip_path = os.path.join(SKILLS_DIR, slug + ".zip")
    url = "https://lightmake.site/api/v1/download?slug=" + slug
    os.makedirs(SKILLS_DIR, exist_ok=True)
    try:
        rc = subprocess.run(["curl", "-sL", "--max-time", "40", "-o", zip_path, url],
                            capture_output=True, text=True)
        if rc.returncode != 0 or not os.path.isfile(zip_path) or os.path.getsize(zip_path) == 0:
            return None, "download_failed(rc=%s)" % rc.returncode
        dest = os.path.join(SKILLS_DIR, slug)
        os.makedirs(dest, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(dest)
        except zipfile.BadZipFile as e:
            return None, "bad_zip:%s" % e
        try:
            zips_dir = os.path.join(SKILLS_DIR, "zips")
            os.makedirs(zips_dir, exist_ok=True)
            shutil.move(zip_path, os.path.join(zips_dir, slug + ".zip"))
        except (OSError, Exception):  # noqa: BLE001
            pass
        skill_dir = dest
        if not os.path.isfile(os.path.join(dest, "SKILL.md")):
            found = None
            for root, _dirs, files in os.walk(dest):
                if "SKILL.md" in files:
                    found = root
                    break
            if found is None:
                return None, "no_SKILL.md_in_zip"
            skill_dir = found
        return skill_dir, None
    except Exception as e:  # noqa: BLE001
        return None, "download_exception:%r" % e


def extract_json(text):
    cand = [i for i, ch in enumerate(text) if ch in "[{"]
    cand.reverse()
    for i in cand:
        try:
            return json.loads(text[i:])
        except json.JSONDecodeError:
            continue
    raise ValueError("no_json_in_stdout(len=%d)" % len(text))


def run_audit(skill_dir):
    """返回 (parsed_json_or_None, raw_stdout, error_or_None)。发现 ERROR 时退出码非 0 是预期。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(SRC, "scripts")
    try:
        rc = subprocess.run([PY, CLI, "--skill", skill_dir, *AUDIT_FLAGS],
                            capture_output=True, text=True, cwd=ROOT, env=env,
                            timeout=PER_AUDIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, "", "audit_timeout"
    except Exception as e:  # noqa: BLE001
        return None, "", "audit_exception:%r" % e
    raw = rc.stdout
    try:
        return extract_json(raw), raw, None
    except ValueError:
        return None, raw, "json_parse_failed(stdout_len=%d)" % len(raw)


# ── 汇总 + 报告 ──────────────────────────────────────────────────────────────
def _sev(status):
    m = re.match(r"ERROR=(\d+)", status)
    return int(m.group(1)) if m else 10 ** 9


def summarize_results(rows):
    n_total = len(rows)
    n_dl_ok = sum(1 for r in rows if r.get("audit") and r["audit"].get("ok"))
    n_dl_fail = sum(1 for r in rows if r.get("download_error"))
    n_audit_fail = sum(1 for r in rows if r.get("audit_error"))
    tot_err = tot_warn = tot_info = 0
    cat_counter = {}
    receipt_all_ok = receipt_with_unknown = receipt_with_failed = doc_llm_ok = 0
    worst = []
    for r in rows:
        a = r.get("audit")
        if not a or not a.get("ok"):
            if r.get("download_error"):
                worst.append((r["slug"], "下载失败:%s" % r["download_error"], r.get("name", "")))
            elif r.get("audit_error"):
                worst.append((r["slug"], "审计失败:%s" % r["audit_error"], r.get("name", "")))
            continue
        res = a["result"]
        if isinstance(res, list):
            res = res[0] if res else {}
        s = res.get("summary", {})
        tot_err += s.get("error", 0)
        tot_warn += s.get("warn", 0)
        tot_info += s.get("info", 0)
        for f in res.get("findings", []):
            cat_counter[f.get("category", "?")] = cat_counter.get(f.get("category", "?"), 0) + 1
        runs = res.get("checker_runs") or []
        names = {c["name"] for c in runs}
        statuses = {c["status"] for c in runs}
        if {"doc-llm"} & names and "OK" in {c["status"] for c in runs if c["name"] == "doc-llm"}:
            doc_llm_ok += 1
        if statuses == {"OK"} and len(runs) >= 8:
            receipt_all_ok += 1
        if "UNKNOWN" in statuses:
            receipt_with_unknown += 1
        if "FAILED" in statuses:
            receipt_with_failed += 1
        if s.get("error", 0) > 0:
            worst.append((r["slug"], "ERROR=%d/WARN=%d" % (s.get("error", 0), s.get("warn", 0)),
                          r.get("name", "")))
    return {
        "n_total": n_total, "n_dl_ok": n_dl_ok, "n_dl_fail": n_dl_fail,
        "n_audit_fail": n_audit_fail, "tot_err": tot_err, "tot_warn": tot_warn,
        "tot_info": tot_info, "cat_counter": cat_counter,
        "receipt_all_ok": receipt_all_ok, "receipt_with_unknown": receipt_with_unknown,
        "receipt_with_failed": receipt_with_failed, "doc_llm_ok": doc_llm_ok,
        "worst": sorted(worst, key=lambda x: -_sev(x[1])),
    }


def write_report(summary, meta):
    lines = []
    lines.append("# 市场质量基准实测报告")
    lines.append("")
    lines.append("- 生成时间：%s" % meta["ts"])
    lines.append("- 取样口径：**TRACE 官方质量评测分（overall，5.0 分制）**——与 trace-selfcheck 同源"
                 "（`fetch_evaluation(slug)` → `parse_eval` → overall）。")
    lines.append("- 取样规则：候选池 %d 个 slug（全市场随机页偏移抽样、避免热度偏差）→ 有质量分 %d 个"
                 " → 升序取**质量最低 %d** → 随机抽 %d（seed=%s，去重近 %d 次运行）。"
                 % (meta["pool"], meta["scored"], meta["lowest_n"], meta["sample"],
                    meta["seed"], meta["dedup"]))
    lines.append("- 工具：`skill-doc-audit` 全量检查 `--all-checks --deadcode-mode vulture --doc-llm-mode agent`")
    lines.append("- 意义：质量最低区间最可能存在文档/代码漂移、frontmatter 不规范；同时验证当前工作树"
                 "在规模化场景能否稳定点名 UNKNOWN/FAILED、doc-llm 修复后是否真执行。")
    lines.append("- 注意：受 13.3 万技能规模约束，列表接口无质量排序、全量爬评测不可行；本采样是"
                 "「候选池内质量最低 1000」的工程化近似，非字面全局最低 1000。")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("| --- | --- |")
    lines.append("| 候选池 slug 数 | %d |" % meta["pool"])
    lines.append("| 有质量分（进入排序）| %d |" % meta["scored"])
    lines.append("| 质量最低区间取数 | %d |" % meta["lowest_n"])
    lines.append("| 实际抽取测试 | %d |" % meta["sample"])
    lines.append("| 下载成功并审计 | %d |" % summary["n_dl_ok"])
    lines.append("| 下载失败 | %d |" % summary["n_dl_fail"])
    lines.append("| 审计异常 | %d |" % summary["n_audit_fail"])
    lines.append("| 累计 ERROR / WARN / INFO | %d / %d / %d |" % (
        summary["tot_err"], summary["tot_warn"], summary["tot_info"]))
    lines.append("| 回执全 OK（8/8 已执行）| %d |" % summary["receipt_all_ok"])
    lines.append("| 回执含 UNKNOWN（未注册）| %d |" % summary["receipt_with_unknown"])
    lines.append("| 回执含 FAILED（执行异常）| %d |" % summary["receipt_with_failed"])
    lines.append("| doc-llm 真实执行(OK) | %d / %d |" % (summary["doc_llm_ok"], summary["n_dl_ok"]))
    lines.append("")
    lines.append("## 漂移类别分布（Top 15）")
    lines.append("")
    lines.append("| 类别 | 次数 |")
    lines.append("| --- | --- |")
    for cat, n in sorted(summary["cat_counter"].items(), key=lambda x: -x[1])[:15]:
        lines.append("| %s | %d |" % (cat, n))
    lines.append("")
    lines.append("## 问题最突出 / 未跑成的技能")
    lines.append("")
    lines.append("| slug | 状态 | 名称 |")
    lines.append("| --- | --- | --- |")
    for slug, st, name in summary["worst"][:30]:
        lines.append("| %s | %s | %s |" % (slug, st, name))
    lines.append("")
    lines.append("> 逐技能原始 JSON 见 `results.json`；下载的技能目录见 `skills/`。")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log("report written: %s" % REPORT_MD)


# ── run 子命令 ────────────────────────────────────────────────────────────────
def run_bench(sample=50, seed=None, dedup=3, pool=3000, refresh=False, no_index=False):
    if refresh or (not no_index and not os.path.isfile(INDEX_JSON)):
        if no_index and not os.path.isfile(INDEX_JSON):
            log("[run] 质量索引缺失且 --no-index，退出。请先 `index`。")
            return 2
        build_index(pool)
    idx = load_index() or {}
    scored = {s: q for s, q in idx.items() if isinstance(q, (int, float))}
    if not scored:
        log("[run] 索引中无有效质量分，无法取样。请先 `index`。")
        return 2
    ranked = sorted(scored.items(), key=lambda x: x[1])
    lowest_n = min(1000, len(ranked))
    cand = [s for s, _ in ranked[:lowest_n]]
    if dedup and dedup > 0:
        recent = recent_sampled(dedup)
        avail = [s for s in cand if s not in recent]
        if len(avail) >= sample:
            cand = avail
            log("[run] 去重：排除近 %d 次已采 %d 个，候选余 %d" % (dedup, len(recent), len(cand)))
    rng = random.Random(seed)
    picked = rng.sample(cand, min(sample, len(cand)))
    log("[run] 质量最低区间 %d 个 → 抽 %d（seed=%s）" % (lowest_n, len(picked), seed))

    os.makedirs(SKILLS_DIR, exist_ok=True)
    done = {}
    if os.path.isfile(RESULTS_JSON):
        try:
            prev = json.load(open(RESULTS_JSON, encoding="utf-8"))
            for r in prev.get("skills", []):
                if r.get("audit", {}).get("ok"):
                    done[r["slug"]] = r
            log("[run] resume: 已有 %d 个已完成技能，将跳过" % len(done))
        except Exception:  # noqa: BLE001
            pass
    out = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "sample_by": "trace_quality", "skills": list(done.values())}
    t0 = time.time()
    for i, slug in enumerate(picked, 1):
        log("[%02d/%d] %s" % (i, len(picked), slug))
        if slug in done:
            log("   已审计，跳过")
            continue
        rec = {"slug": slug, "quality": scored.get(slug)}
        skill_dir, derr = download_and_extract(slug)
        if derr:
            rec["download_error"] = derr
            log("   下载失败: %s" % derr)
            out["skills"].append(rec)
            _flush(out)
            continue
        parsed, raw, aerr = run_audit(skill_dir)
        if aerr or parsed is None:
            rec["audit_error"] = aerr or "no_result"
            rec["raw_stdout_len"] = len(raw)
            log("   审计失败: %s" % (aerr or "no_result"))
            out["skills"].append(rec)
            _flush(out)
            continue
        rec["audit"] = {"ok": True, "result": parsed}
        sm = parsed[0].get("summary", {}) if isinstance(parsed, list) and parsed else {}
        rec["audit"]["summary"] = sm
        log("   审计完成: ERROR %d / WARN %d / INFO %d" % (
            sm.get("error", 0), sm.get("warn", 0), sm.get("info", 0)))
        out["skills"].append(rec)
        _flush(out)

    summary = summarize_results(out["skills"])
    meta = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "pool": len(idx),
            "scored": len(scored), "lowest_n": lowest_n, "sample": len(picked),
            "seed": seed, "dedup": dedup}
    write_report(summary, meta)
    record_sampled(picked)
    log("DONE in %.1fs | ERROR %d WARN %d INFO %d | doc-llm OK %d/%d"
        % (time.time() - t0, summary["tot_err"], summary["tot_warn"], summary["tot_info"],
           summary["doc_llm_ok"], summary["n_dl_ok"]))
    return 0


def _flush(out):
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


# ── check-bump 子命令（版本监测，供 dev_self_audit 调用）──────────────────────
def current_version():
    p = os.path.join(SRC, "SKILL.md")
    if not os.path.isfile(p):
        return None
    txt = open(p, encoding="utf-8").read()
    # 去 YAML 引号：frontmatter 形如 version: "1.25.7"
    m = re.search(r'^version:\s*["\']?([0-9][0-9A-Za-z.\-]*)["\']?\s*$', txt, re.MULTILINE)
    return m.group(1) if m else None


def _ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().strip('"').strip("'").split(".")
                     if x.strip() != "")
    except Exception:  # noqa: BLE001
        return None


def is_minor_or_major_bump(old, new):
    a, b = _ver_tuple(old), _ver_tuple(new)
    if not a or not b or len(a) < 2 or len(b) < 2:
        return False
    return b[0] != a[0] or b[1] != a[1]


def check_bump():
    cur = current_version()
    if not cur:
        log("[check-bump] 无法读取 src/SKILL.md 版本，跳过。")
        return 0
    last = None
    try:
        if os.path.isfile(LAST_VERSION):
            last = open(LAST_VERSION, encoding="utf-8").read().strip()
    except Exception:  # noqa: BLE001
        last = None
    if last is None:
        # 首次运行：仅记录基线，不提示（避免无历史时误报）
        try:
            os.makedirs(CACHE, exist_ok=True)
            open(LAST_VERSION, "w", encoding="utf-8").write(cur)
        except Exception:  # noqa: BLE001
            pass
        return 0
    if is_minor_or_major_bump(last, cur):
        kind = "主" if _ver_tuple(cur)[0] != _ver_tuple(last)[0] else "次"
        print("检测到%s版本变动 v%s → v%s（次/主版本变更须完成下列文档自审计后才可发布）" % (kind, last, cur))
        print("[agent-todo][建议] 建议运行「市场质量基准实测器」验证规模化行为是否稳定")
        print("  → python src/scripts/dev_market_bench.py run")
        print("  （基准实测不自动执行，由 Agent 评估后决定是否运行；仅人工要求或本建议触发时启用）")
        print("")
        print("  [agent-todo][必须] 次/主版本变更须执行 doc + doc-llm 文档自审计（开发者模式）")
        print("  doc 检查死链接/文档漂移，doc-llm 产出语义漂移 dossier 需 agent 接手判读")
        print("  → python src/scripts/audit_docs.py --skill ~/.workbuddy/skills/skill-doc-audit --check doc --check doc-llm --doc-llm-mode agent")
        print("")
        print("  [agent-todo][必须] 次/主版本变更须执行开发者模式全量自审计（维护整体质量）")
        print("  全量检查器 + README/CHANGELOG 文档自审计；确认 dev 工具与发布面一致、无漂移")
        print("  → python src/scripts/dev_self_audit.py --dev-docs --strict")
    try:
        os.makedirs(CACHE, exist_ok=True)
        open(LAST_VERSION, "w", encoding="utf-8").write(cur)
    except Exception:  # noqa: BLE001
        pass
    return 0


def main():
    ap = argparse.ArgumentParser(description="市场质量基准实测器（dev-only）")
    sub = ap.add_subparsers(dest="cmd")

    p_idx = sub.add_parser("index", help="构建/刷新质量索引（随机候选池 + 逐个取质量分）")
    p_idx.add_argument("--pool", type=int, default=3000, help="候选池大小（默认 3000）")
    p_idx.add_argument("--page-size", type=int, default=100, help="列表分页大小（默认 100）")

    p_run = sub.add_parser("run", help="采样最低质量 1000 中 50 → 审计 → 报告")
    p_run.add_argument("--sample", type=int, default=50, help="抽取数量（默认 50）")
    p_run.add_argument("--seed", type=int, default=None, help="随机种子（指定可复现；默认每次不同）")
    p_run.add_argument("--dedup", type=int, default=3,
                       help="排除近 N 次已采 slug（默认 3；0=不排除）")
    p_run.add_argument("--pool", type=int, default=3000, help="index 候选池大小（默认 3000）")
    p_run.add_argument("--refresh-index", action="store_true", help="强制重建质量索引")
    p_run.add_argument("--no-index", action="store_true", help="索引缺失时直接报错（不自动 index）")

    sub.add_parser("check-bump", help="版本监测：次/主版本变动时打印 [agent-todo] 建议")

    args = ap.parse_args()
    if args.cmd == "index":
        build_index(args.pool, args.page_size)
        return 0
    if args.cmd == "run":
        return run_bench(sample=args.sample, seed=args.seed, dedup=args.dedup,
                         pool=args.pool, refresh=args.refresh_index, no_index=args.no_index)
    if args.cmd == "check-bump":
        return check_bump()
    # 无子命令：默认 run
    return run_bench()


if __name__ == "__main__":
    sys.exit(main())
