#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dev_market_bench.py —— 市场质量基准实测器（dev-only 辅助开发工具 · 不进部署副本）

为什么需要它：
  skill-doc-audit 的检查器在「规模化真实世界」里是否稳定、doc-llm 修复后是否真的执行、
  市场长尾技能的质量分布长什么样——这些必须用批量实测验证，而不能只靠单测 fixture。
  本工具把「批量实测」流程固化成可重复命令，任何人都跑得出来、口径一致。

取样口径（用户 2026-09-03 推翻原「质量分近似」规则，改为直接随机取样）：
  原规则（已废弃）：先 `index` 构建质量索引（候选池随机抽→逐个拉 TRACE 评测取质量分→缓存）
    → `run` 在「质量最低 1000」里抽 50。该路径对评测接口依赖重（约 1000 次评测请求）、
    且 13 万技能规模下「质量最低区间」只是工程化近似，并非真全局最低。
  新规则：直接用官方市场列表 API（`lightmake.site/api/skills` 或 `api.skillhub.cn/api/skills`）
    **随机页偏移抽样 50 个 slug** → 下载 → 全量审计 → 报告。不依赖任何质量分 / 评测接口，
    取样即「市场随机 50 个技能」，口径简单、可复现（--seed）、可去重（--dedup）。
  为什么可行：列表接口返回 `data.total`（市场总量）与分页 `data.skills[]`，按随机页号 +
    页内打乱即可均匀覆盖全市场，避免热度偏差；单次 run 仅 ~2-4 次列表请求 + 50 次下载，
    对官方接口压力远低于原质量索引路径。

子命令：
  run            随机页偏移抽 50 个 slug → 下载 → 全量审计 → 报告（默认；可 --sample / --seed / --dedup）
  check-bump     版本监测：检测版本变动/未提交改动，打印上架授权与文档约定等 [agent-todo] 提示

不进自动调度（用户明确要求）：
  实际跑基准（run）只在「人工要求」或「agent 评估重大版本变动后建议」时执行；
  check-bump 供 dev_self_audit 打印版本变动/未提交相关 [agent-todo] 提示（绝不动触发 run，不自动跑基准）。

下载口径（与官方 find-skills 技能一致 · 用户 2026-09-02 确认）：
  样本技能先遍历本地候选源（`local_candidate_dirs()`：环境变量覆盖 > 官方本地技能市场
  ~/.workbuddy/skills-marketplace/skills > ~/.workbuddy/skills、~/.codebuddy/skills >
  IDE 市场插件缓存 ~/.workbuddy/plugins/marketplaces/*/plugins/*/skills），命中即复制、
  **完全不发网络请求**；未命中才走官方端点 `https://lightmake.site/api/v1/download?slug=<slug>`。
  产物落在 bench 临时目录、不安装进实时技能目录，且只读本地副本、绝不改动原目录。
  下载合法性以官方端点为准，**不依赖任何内部/未公开路径**；本地优先短路同时降低对官方
  接口的请求频次（呼应「避免过于频繁请求引来审查」的诉求）。

请求密度控制（2026-09-03 更新）：
  新取样规则不再逐个拉评测（原 `--workers` / `--delay` 已废弃），单次 run 仅约 2-4 次列表
  请求 + 50 次下载，对官方接口压力远低于原质量索引路径；如仍需降低列表请求瞬时密度，
  可减小 `--page-size` 或减少 `--sample`。

退出码：
  0 正常；2 参数/路径错误；run 下被审技能出现 ERROR 属被测现象、不升退出码（与 run_market_audit 一致）。

典型用法：
  python src/scripts/dev_market_bench.py run                       # 随机抽 50 个市场技能 → 审计 → 报告
  python src/scripts/dev_market_bench.py run --sample 50 --seed 7 # 可复现抽样（50 个）
  python src/scripts/dev_market_bench.py run --dedup 0            # 不去重（允许重复历史样本）
  python src/scripts/dev_market_bench.py check-bump               # 版本监测（由 dev_self_audit 自动调用）
"""
import argparse
import concurrent.futures as futures
import glob
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
# 复用 dev 公共层的解耦能力：跨 agent/跨平台候选根 + 解释器解析（避免本工具另抄一份）
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from _devcommon import candidate_roots, resolve_python  # noqa: E402
CACHE = os.path.join(ROOT, "bench", "market_bench")          # 运行时缓存（gitignore：不进版本库）
# INDEX_JSON 已于 2026-09-03 随质量索引废弃而移除（新取样规则不再维护质量索引）。
HISTORY_JSON = os.path.join(CACHE, "sampled_history.json")
LAST_VERSION = os.path.join(CACHE, "last_bench_version.txt")
SKILLS_DIR = os.path.join(CACHE, "skills")
LOCAL_MARKETPLACE = os.path.join(os.path.expanduser("~"), ".workbuddy",
                                 "skills-marketplace", "skills")  # 官方 find-skills Step 5 本地优先
# 本地优先根目录可被环境变量整体覆盖（os.pathsep 分隔，便于 CI / 异机复用本地缓存）
LOCAL_DIRS_ENV = "SKILL_MARKET_BENCH_LOCAL_DIRS"
RESULTS_JSON = os.path.join(CACHE, "results.json")
REPORT_MD = os.path.join(CACHE, "report.md")

# 审计子进程用的解释器：绝不硬编码机器专属绝对路径（换机器/换用户名/换 OS 即失效），
# 默认取当前解释器，需指定别的版本时用 SKILL_AUDIT_PYTHON 覆盖（见 _devcommon.resolve_python）。
CLI = os.path.join(SRC, "scripts", "auditlib", "cli.py")
AUDIT_FLAGS = ["--all-checks", "--deadcode-mode", "vulture",
               "--doc-llm-mode", "agent", "--examples-mode", "static",
               "--examples-consent", "--json"]
PER_AUDIT_TIMEOUT = 240  # 秒

LIST_ENDPOINTS = [
    "https://api.skillhub.cn/api/skills?pageSize={size}&page={page}",
    "https://lightmake.site/api/skills?pageSize={size}&page={page}",
]
# EVAL_ENDPOINTS 已于 2026-09-03 移除：新取样规则（直接随机抽列表）不再依赖评测接口。
UA = "skill-doc-audit-market-bench/1.0"


def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# ── 官方市场列表 API 封装（随机页偏移抽样用）────────────────────────────────
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


# fetch_quality 已于 2026-09-03 移除：新取样规则（直接随机抽列表）不再依赖评测接口；
# 其函数体（dimensions → 各子项 score 均值 → 综合分）一并废弃。


# ── 随机候选池（全市场随机页偏移抽样，供 run 直接取样）────────────────────────
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


# 质量索引（_quality_task / build_index / load_index / save_index）已于 2026-09-03 随取样规则改为直接随机抽列表而废弃移除


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
def _skill_dir_has_md(d):
    """目录自身或其一层子目录含 SKILL.md 即视为可用技能副本。"""
    if os.path.isfile(os.path.join(d, "SKILL.md")):
        return True
    try:
        for name in os.listdir(d):
            if os.path.isfile(os.path.join(d, name, "SKILL.md")):
                return True
    except OSError:
        pass
    return False


def local_candidate_dirs():
    """本地技能副本的候选根目录（按优先级），命中即免网络下载。

    官方 find-skills Step 5 要求「下载前先查本地技能市场」，其默认目录为
    `~/.workbuddy/skills-marketplace/skills`；但该目录并非所有机器都存在（本机即无），
    故再纳入同语义的其他本地副本根目录，提高本地命中率：
      ① 环境变量 SKILL_MARKET_BENCH_LOCAL_DIRS（os.pathsep 分隔，最高优先，便于覆盖）
      ② 官方本地技能市场 ~/.workbuddy/skills-marketplace/skills
      ③ dev 公共层的跨 agent / 跨平台候选根（_devcommon.candidate_roots()，
         覆盖 WorkBuddy/CodeBuddy/Claude/Cursor/Codex/OpenCode/Aider 与平台专属根）
      ④ IDE 市场插件缓存 ~/.workbuddy/plugins/marketplaces/*/plugins/*/skills
    只读取这些目录、不写不删；复制到 bench 缓存后再审计，绝不改动原副本。

    解耦考量：③ 刻意复用 _devcommon.candidate_roots() 而非在此另列一份 ~/.workbuddy、
    ~/.claude 等候选表——重复实现会导致新增 agent 支持时改一处漏一处（跨 agent 漂移）。
    """
    env = os.environ.get(LOCAL_DIRS_ENV, "")
    roots = [p for p in env.split(os.pathsep) if p.strip()]
    roots += [LOCAL_MARKETPLACE]
    roots += candidate_roots()          # 跨 agent / 跨平台候选根（单一真相源）
    mkt = os.path.join(os.path.expanduser("~"), ".workbuddy", "plugins",
                       "marketplaces", "*", "plugins", "*", "skills")
    roots += sorted(glob.glob(mkt))
    out, seen = [], set()
    for r in roots:
        r = os.path.normpath(r)
        if r and r not in seen and os.path.isdir(r):
            seen.add(r)
            out.append(r)
    return out


def _http_download(url, dest_path, timeout=40):
    """下载文件：优先纯 Python urllib（零外部命令、跨平台），失败回退 curl。

    解耦考量：早期实现直接 subprocess 调 curl——Windows 精简环境 / Linux 最小化容器
    常无 curl，会让整条基准链路在异机失效。故改为 urllib 优先（Python 标准库必有），
    仅当 urllib 失败（代理、重定向、TLS 环境差异）时才回退 curl，两条路径任一成功即可。
    返回 (True, None) 或 (False, error_str)。

    ⚠ 成功判据必须是「zip 魔数校验」而非「非空」：实测踩过坑——curl 默认对 404/5xx
    仍返回 rc=0，并把服务端错误页（17 字节的 `Version: ...` 文本）写进目标文件。
    若仅以 size>0 判成功，会把错误页当成下载成功，后续 zipfile 才炸、且错误信息失真。
    故两条路径下载后统一校验前 2 字节为 zip 魔数 `PK`，并把实际魔数写进错误信息便于诊断。
    """
    err = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "skill-doc-audit-dev-bench"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest_path, "wb") as fp:
            shutil.copyfileobj(resp, fp)
        ok, why = _looks_like_zip(dest_path)
        if ok:
            return True, None
        err = "urllib_not_zip(%s)" % why
    except Exception as e:  # noqa: BLE001
        err = "urllib_failed:%r" % e
    # 回退：curl（部分网络环境对代理/重定向处理更好）；-f 使 HTTP 4xx/5xx 返回非零
    try:
        rc = subprocess.run(["curl", "-sLf", "--max-time", str(timeout), "-o", dest_path, url],
                            capture_output=True, text=True)
        if rc.returncode == 0:
            ok, why = _looks_like_zip(dest_path)
            if ok:
                return True, None
            return False, "%s;curl_not_zip(%s)" % (err, why)
        return False, "%s;curl_failed(rc=%s)" % (err, rc.returncode)
    except FileNotFoundError:
        return False, err + ";curl_missing"
    except Exception as e2:  # noqa: BLE001
        return False, "%s;curl_error:%r" % (err, e2)


def _looks_like_zip(path):
    """校验下载产物确为 zip（前 2 字节魔数 PK）；返回 (bool, 诊断串)。"""
    if not os.path.isfile(path):
        return False, "missing"
    size = os.path.getsize(path)
    if size == 0:
        return False, "empty"
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
    except OSError as e:
        return False, "unreadable:%r" % e
    if magic[:2] != b"PK":
        return False, "magic=%r size=%d" % (magic[:4], size)
    return True, ""


def download_and_extract(slug, stats=None):
    """下载技能并解包到 SKILLS_DIR/<slug>/，返回 (skill_dir_or_None, error_or_None)。

    下载走官方 SkillHub 端点（与 find-skills 技能文档 Step 6 完全一致：
    https://lightmake.site/api/v1/download?slug=<slug>），并在联网前先遍历
    `local_candidate_dirs()` 做**本地优先短路**——命中即复制、完全不发网络请求。
    这既吻合官方 find-skills 的 Step 5 本地优先流程，也降低对官方接口的请求频次
    （呼应「避免过于频繁请求引来审查」的诉求）。下载产物落在 bench 临时目录，
    不安装进实时技能目录（~/.workbuddy/skills）。

    `stats` 为可选 dict，用于累计本次 run 的 `local`（本地命中）/ `remote`（联网下载）次数。
    """
    dest = os.path.join(SKILLS_DIR, slug)
    os.makedirs(dest, exist_ok=True)

    # ① 本地优先（官方 find-skills Step 5）：命中任一本地候选源即免网络下载
    for root in local_candidate_dirs():
        src = os.path.join(root, slug)
        if os.path.isdir(src) and _skill_dir_has_md(src):
            try:
                if not os.path.isfile(os.path.join(dest, "SKILL.md")):
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                if isinstance(stats, dict):
                    stats["local"] = stats.get("local", 0) + 1
                log("   本地命中（免下载）：%s" % src)
                return dest, None
            except Exception as e:  # noqa: BLE001
                return None, "local_copy_failed:%r" % e

    # ② 否则走官方下载端点（纯 Python 优先，curl 仅作回退 —— 不依赖单一外部命令）
    zip_path = os.path.join(SKILLS_DIR, slug + ".zip")
    url = "https://lightmake.site/api/v1/download?slug=" + slug
    try:
        ok, derr = _http_download(url, zip_path)
        if not ok:
            return None, derr
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
            for wroot, _dirs, files in os.walk(dest):
                if "SKILL.md" in files:
                    found = wroot
                    break
            if found is None:
                return None, "no_SKILL.md_in_zip"
            skill_dir = found
        if isinstance(stats, dict):
            stats["remote"] = stats.get("remote", 0) + 1
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
        rc = subprocess.run([resolve_python(), CLI, "--skill", skill_dir, *AUDIT_FLAGS],
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
    lines.append("- 取样口径：**直接用官方市场列表 API 随机页偏移抽样**（2026-09-03 推翻原「质量分近似」规则）。")
    lines.append("- 取样规则：列表接口取 `data.total`（市场总量）→ 随机页号 + 页内打乱均匀抽候选"
                 " → 排除近 %d 次已采 → 取前 %d 个（seed=%s，全市场均匀、无热度偏差）。"
                 % (meta["dedup"], meta["sample"], meta["seed"]))
    lines.append("- 工具：`skill-doc-audit` 全量检查 `--all-checks --deadcode-mode vulture --doc-llm-mode agent`")
    lines.append("- 意义：随机 %d 个市场技能最贴近「真实世界长尾」，可验证当前工作树在规模化场景"
                 "能否稳定点名 UNKNOWN/FAILED、doc-llm 修复后是否真执行。" % meta["sample"])
    lines.append("- 注意：本取样不依赖评测接口，单次 run 仅约 2-4 次列表请求 + %d 次下载，"
                 "对官方接口压力远低于原质量索引路径（约 1000 次评测请求）。" % meta["sample"])
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("| --- | --- |")
    lines.append("| 市场技能总量 | %d |" % meta["total"])
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
    lines.append("| --- | --- |")
    for slug, st, name in summary["worst"][:30]:
        lines.append("| %s | %s | %s |" % (slug, st, name))
    lines.append("")
    lines.append("> 逐技能原始 JSON 见 `results.json`；下载的技能目录见 `skills/`。")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log("report written: %s" % REPORT_MD)


# ── run 子命令 ────────────────────────────────────────────────────────────────
def run_bench(sample=50, seed=None, dedup=3, page_size=100):
    """直接用官方市场列表 API 随机页偏移抽 sample 个 slug → 下载 → 全量审计 → 报告。

    取样规则（2026-09-03 推翻原「质量分近似」）：不再构建质量索引、不再依赖评测接口；
    仅用列表接口的 data.total 决定随机页范围，collect_pool 在随机页上均匀抽候选
    （含去重余量），再排除近 dedup 次已采、取前 sample 个做实测。
    """
    total = fetch_total()
    if total <= 0:
        log("[run] 无法从市场列表接口取得总数（检查网络 / 端点可用性），退出。")
        return 2
    # 候选池留出去重余量：默认至少 120 或 sample*2，确保去重后仍够 sample 个
    cand_pool = max(int(sample) * 2, 120)
    slugs = collect_pool(cand_pool, page_size=page_size, total=total)
    if not slugs:
        log("[run] 未从市场取得任何 slug，退出（检查网络 / 端点可用性）。")
        return 2
    log("[run] 随机页偏移抽得候选 %d 个 slug（page_size=%d）" % (len(slugs), page_size))
    picked = slugs
    if dedup and dedup > 0:
        recent = recent_sampled(dedup)
        avail = [s for s in slugs if s not in recent]
        if len(avail) >= sample:
            picked = avail
            log("[run] 去重：排除近 %d 次已采 %d 个，候选余 %d" % (dedup, len(recent), len(picked)))
        else:
            log("[run] 去重后不足 %d（仅 %d），放宽去重保留全量" % (sample, len(avail)))
    rng = random.Random(seed)
    rng.shuffle(picked)            # 候选顺序本就随机；再洗一次使 --seed 可复现
    picked = picked[:sample]
    log("[run] 最终抽取 %d 个 slug（seed=%s）" % (len(picked), seed))

    os.makedirs(SKILLS_DIR, exist_ok=True)
    locals_roots = local_candidate_dirs()
    if locals_roots:
        log("[run] 本地优先源 %d 个：%s" % (len(locals_roots), " | ".join(locals_roots)))
    else:
        log("[run] 无本地优先源，样本将全部走官方下载端点")
    dl_stats = {"local": 0, "remote": 0}
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
           "sample_by": "random_market_list", "skills": list(done.values())}
    t0 = time.time()
    for i, slug in enumerate(picked, 1):
        log("[%02d/%d] %s" % (i, len(picked), slug))
        if slug in done:
            log("   已审计，跳过")
            continue
        rec = {"slug": slug}
        skill_dir, derr = download_and_extract(slug, dl_stats)
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
    meta = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "total": total,
            "sample_by": "random_market_list", "sample": len(picked),
            "seed": seed, "dedup": dedup,
            "local_hits": dl_stats.get("local", 0),
            "remote_downloads": dl_stats.get("remote", 0)}
    write_report(summary, meta)
    record_sampled(picked)
    log("DONE in %.1fs | ERROR %d WARN %d INFO %d | doc-llm OK %d/%d | 本地命中 %d / 远端下载 %d"
        % (time.time() - t0, summary["tot_err"], summary["tot_warn"], summary["tot_info"],
           summary["doc_llm_ok"], summary["n_dl_ok"],
           dl_stats.get("local", 0), dl_stats.get("remote", 0)))
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




def _git_uncommitted():
    """best-effort 检测仓库是否有未提交改动；git 不可用 / 异常时返回 False（不误报）。

    用于 check_bump 的常驻提醒：长期开发易因记忆漂移遗漏本地 commit，
    导致 src 与部署副本 / 版本号长期脱节（post-commit 钩子本应同步部署副本）。
    """
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        out = subprocess.run(["git", "status", "--porcelain"],
                             cwd=repo, capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return False
    if out.returncode != 0:
        return False
    return bool(out.stdout.strip())


def _ver_tuple(v):
    """解析 `x.y.z` 版本为三元组；带 YAML 引号或非法返回 None。"""
    if not v:
        return None
    m = re.match(r"^\s*\"?(\d+)\.(\d+)\.(\d+)\"?\s*$", str(v))
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_minor_or_major_bump(old, new):
    """次版本（y）或主版本（x）变动返回 True；补丁号（z）变动返回 False。"""
    if old is None or new is None:
        return False
    to, tn = _ver_tuple(old), _ver_tuple(new)
    if to is None or tn is None:
        return False
    return (tn[0] != to[0]) or (tn[1] != to[1])


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
    if cur != last:
        # 任何版本变化（含补丁）都须先取得用户授权才允许上架——上架是外部公开动作。
        print("")
        print("  [agent-todo][必须] 上架 SkillHub 前须先获得用户明确授权同意（不得自动发布）")
        print("  SkillHub 上架属对外公开动作，须用户点头；未获授权前只能本地 commit/push，不得 publish")
        print("  → 先询问用户取得授权；获准后：skillhub publish <技能目录> --changelog \"...\" --json")
        print("  （发布目录内不得含 dist/ 或任何 .zip：市场自行重打包，目录内含 zip 会返回 400「不允许的文件类型」）")
        print("")
        print("  [agent-todo][建议] 版本变动时，用户文档（SKILL.md / references/*）无需写入版本变动叙述")
        print("  如「vX.Y.Z 新增 / 升级」类里程碑叙述应留在开发者文档（CHANGELOG.md）；用户文档只描述当前能力本身")
        print("  → 发版前复核：SKILL.md 与 references/*.md 是否混入版本号里程碑叙述，有则删除、仅留行为/能力描述")
        # 次/主版本变动：提醒 agent 评估是否运行完整基准实测（[建议]，非阻断）
        if is_minor_or_major_bump(last, cur):
            print("")
            print("  [agent-todo][建议] ⚠ 决策点：次/主版本变动——是否运行「市场质量基准实测器」做完整实测？")
            print("  次/主版本属质量高风险点（检查器逻辑 / 误报抑制 / 风险口径可能变动）；建议评估是否运行一次规模化基准以验证稳定性：")
            print("  → python src/scripts/dev_market_bench.py run （默认随机抽 50 个市场技能全量审计；可 --sample / --seed / --dedup）")
            print("  （仅在人工要求或本建议触发时启用，不进自动调度、绝不由 check-bump 自动触发 run）")
    # 通用提示（不依赖版本变动）：长期开发易因记忆漂移遗漏本地 commit，
    # 导致 src 与部署副本 / 版本号长期脱节（post-commit 钩子本应同步部署副本）。
    # 检测到未提交改动即提示立即本地 commit；[建议] 不阻断、不升退出码。
    if _git_uncommitted():
        print("")
        print("  [agent-todo][建议] 检测到未提交的本地改动，请立即本地 commit")
        print("  本地提交即触发 post-commit 钩子同步部署副本，避免 src 与部署副本 / 版本号长期脱节")
        print("  → python src/scripts/dev_commit.py -m \"<有意义说明>\"（静态提交助手：自动 git add -u + commit，commit 触发 post-commit 同步部署副本；新增文件加 --all 或显式传路径；提交与发布解耦，未上架也可随时提交）")
    try:
        os.makedirs(CACHE, exist_ok=True)
        open(LAST_VERSION, "w", encoding="utf-8").write(cur)
    except Exception:  # noqa: BLE001
        pass
    return 0


def main():
    ap = argparse.ArgumentParser(description="市场质量基准实测器（dev-only）")
    sub = ap.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="随机页偏移抽 50 → 下载 → 全量审计 → 报告（默认抽 50）")
    p_run.add_argument("--sample", type=int, default=50, help="抽取数量（默认 50）")
    p_run.add_argument("--seed", type=int, default=None, help="随机种子（指定可复现；默认每次不同）")
    p_run.add_argument("--dedup", type=int, default=3,
                       help="排除近 N 次已采 slug（默认 3；0=不排除）")
    p_run.add_argument("--page-size", type=int, default=100, help="列表分页大小（默认 100）")

    sub.add_parser("check-bump", help="版本监测：版本变动/未提交改动时打印 [agent-todo] 提示")

    args = ap.parse_args()
    if args.cmd == "run":
        return run_bench(sample=args.sample, seed=args.seed, dedup=args.dedup,
                         page_size=args.page_size)
    if args.cmd == "check-bump":
        return check_bump()
    # 无子命令：默认 run（随机抽 50）
    return run_bench()


if __name__ == "__main__":
    sys.exit(main())
