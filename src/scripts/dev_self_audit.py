#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dev_self_audit.py —— skill-doc-audit 开发模式自审计（脚本化，不依赖 agent 记忆）

为什么需要它（长期项目痛点）：
  开发期 agent 容易出现「记忆漂移 / 幻觉 / 漏操作」——例如审计了过时的部署副本而非最新
  源码、忘了把 README/CHANGELOG 的漂移一并检查、忘记提交即同步部署副本。本脚本把以下约定
  固化成可重复执行的命令，任何人都跑得出来、结果一致：

  1) 同步校验：脚本化确认「已部署副本」与「最新源码 src/」字节一致（复用 sync_deploy._verify）。
     若不一致，说明有未提交改动或钩子未触发，明确告警。
  2) 审计最新源码：一律对 src/（最新提交）跑全量检查器，而非部署副本——避免审计过时产物。
  3) 开发文档纳入漂移：--dev-docs 递归扫描 src/ 内全部 .md 描述性文档（含 README.md /
     CHANGELOG.md / references/*.md / examples 等）交 doc（A1 裸文件名 EXTERNAL_REF 提示）与
     doc-llm（语义漂移 dossier）扫描，捕捉发布文档之外的漂移。
  4) 只扫发布面：排除 sync_deploy.py / self_validate.py / make_fixtures.py / dev_self_audit.py
     等开发期工具，使结果与「实际发布质量」对齐，不被 dev 工具噪音干扰。
  5) 开发期工具语法守卫：DEV_TOOLS 不进发布面扫描，此处复用 auditlib.core.compile_python_file
     对每个 dev 工具兜底语法关（开发期改坏 dev 工具会立刻崩、却逃过发布面检查器），非阻断、命中即提示 agent 复核。

  退出码：0 = 无 ERROR（--strict 下还需无 WARN）；1 = 发现 ERROR（或 --strict 下 WARN）；2 = 参数/路径错误。

用法：
  python src/scripts/dev_self_audit.py                 # 校验同步 + 审计最新源码发布面 + dev 文档
  python src/scripts/dev_self_audit.py --strict        # CI 门禁：WARN 也计为失败
  python src/scripts/dev_self_audit.py --no-sync-check  # 跳过同步校验（仅审计）
"""
import os
import sys
import argparse
import subprocess
import re
from types import SimpleNamespace

# 仓库根经 __file__ 解析（不依赖 CWD）；dev 脚本共享样板见 _devcommon
HERE = os.path.dirname(os.path.abspath(__file__))          # <root>/src/scripts
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from _devcommon import ROOT, SRC, fail as _fail, resolve_deploy_dir

DEP, _DEP_HOW = resolve_deploy_dir()   # 自动探测：优先 WORKBUDDY_CONFIG_DIR，失败回退多候选根探测


def _parse_check_bump(text):
    """把 dev_market_bench.check-bump 输出解析为 (rel_block, rel_info, ctx_lines)。

    - `[agent-todo][必须]` → 阻断项（blocking=True，原样保留「必须」标签）→ --strict 下失败、拦 push
    - `[agent-todo][建议]` → 非阻断提示（blocking=False，原样保留「建议」标签）
    - 其它行（如版本变动标题）作为 ctx_lines 原样返回，由调用方打印为上下文

    原样保留「必须 / 建议」标签，使本地 CI 指令清单（DEVELOPMENT.md）与真实渲染逐字一致。
    """
    block, info, ctx = [], [], []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = re.match(r'^\[agent-todo\]\[(必须|建议)\]\s*(.*)$', s)
        if m:
            sev = m.group(1)
            title = m.group(2)
            detail_parts, todo = [], None
            j = i + 1
            while j < len(lines):
                ns = lines[j].strip()
                if not ns:
                    j += 1
                    continue
                if ns.startswith("[agent-todo]"):
                    break
                if ns.startswith("→"):
                    todo = ns[1:].strip()
                else:
                    detail_parts.append(ns)
                j += 1
            entry = {
                "blocking": sev == "必须",
                "severity": sev,   # 原样保留「必须」/「建议」标签
                "title": title,
                "detail": " ".join(detail_parts) if detail_parts else "",
                "todo": todo or "",
            }
            (block if sev == "必须" else info).append(entry)
            i = j
        else:
            ctx.append(lines[i])
            i += 1
    return block, info, ctx

# DEV_TOOLS 单一真相源移至 auditlib.core（doc 检查器 A3 退出码比对需按文件排除 dev 工具，
# 避免直接 CLI 审计 src 时把 make_fixtures 的 sys.exit(42) 等 dev 专用码误报为 EXIT_CODE_ONLY）。
from auditlib.core import DEV_TOOLS


def _guard_dev_tools():
    """开发期工具盲区守卫：DEV_TOOLS 不在发布面扫描内，复用 compile_python_file 兜底语法关。

    返回 (ok, errors)：ok=True 表示全部通过；errors 为「文件名: 末行错误」列表。
    仅兜底语法，不替代发布面检查器（结构/安全/依赖）；非阻断，命中即提示 agent 复核。
    best-effort：文件缺失 / 无编译能力均静默跳过（视为通过，不误报）。
    """
    from auditlib.core import compile_python_file
    errors = []
    for name in sorted(DEV_TOOLS):
        p = os.path.join(HERE, name)
        if not os.path.isfile(p):
            continue
        ok, msg, _is_syntax = compile_python_file(p)
        if not ok:
            errors.append("%s: %s" % (name, msg))
    return (len(errors) == 0), errors


def fail(msg, code=2):
    _fail(msg, code, tag="dev_self_audit")


def main():
    ap = argparse.ArgumentParser(description="skill-doc-audit 开发模式自审计（最新源码 + dev 文档）")
    ap.add_argument("--strict", action="store_true",
                    help="WARN 也计入退出码（CI 门禁用）")
    ap.add_argument("--no-sync-check", action="store_true",
                    help="跳过「部署副本 ↔ 源码」同步校验")
    ap.add_argument("--deadcode-mode", default=None,
                    help="deadcode 精度模式（默认：已装 vulture 用 vulture，否则 ast）")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        fail("未找到源码根：%s" % SRC)

    # ---- 1) 同步校验 ----
    sync_ok = True
    if not args.no_sync_check:
        try:
            import sync_deploy
            if not os.path.isdir(DEP):
                print("[sync] 部署副本不存在：%s（跳过同步校验）" % DEP)
            else:
                sync_ok = sync_deploy._verify()
                print("[sync] 部署副本 ↔ 源码 src/：%s" % ("一致 OK" if sync_ok else "不一致 MISMATCH"))
                if not sync_ok:
                    print("[sync] ⚠ 不一致：可能存在未提交改动，或 post-commit 钩子未触发同步。"
                          " 请先 `git status` 确认，或手动 `python src/scripts/sync_deploy.py`。")
        except Exception as e:
            print("[sync] 同步校验跳过（无法导入 sync_deploy：%s）" % e)

    # ---- 2) 导入审计器（触发检查器自注册）----
    try:
        from auditlib.model import analyze_skill
        from auditlib.core import ALL_CHECKERS, CHECKER_CODES
        from auditlib.report import summarize, checker_receipt_runs
        from auditlib.checkers.deadcode import _vulture_module
    except Exception as e:
        fail("无法导入 auditlib 包：%s" % e)

    # ---- 3) 审计最新源码发布面 + dev 文档 ----
    # 复用引擎 deadcode 检查器已有的 _vulture_module()（避免与 dev_self_audit 重复实现）
    deadcode_mode = args.deadcode_mode or ("vulture" if _vulture_module() is not None else "ast")
    cli_args = SimpleNamespace(
        deadcode_mode=deadcode_mode,
        # doc-llm：开发者模式默认 agent 接手——写出语义漂移 dossier（含 SKILL.md + references/*.md +
        # 全部 dev .md）并打印 AGENT_TAKEOVER，供交互 agent 直接接手比对；非交互（钩子/CI）下无害
        # （仅多写一个临时 dossier 文件，无 agent 读取时不影响退出码）。语义比对不再静默跳过。
        doc_llm_mode="agent",
        # examples：开发者模式审计「自家」技能源码，执行自家带 expected 标注的示例是受控且安全的，
        # 故默认 run（受限沙箱试运行）以捕获示例输出漂移；第三方技能仍须经 --examples-mode run 显式授权。
        examples_mode="run",
        # 开发者自审计即「开发者已明确授权 run」，携带 consent 令牌避免触发 consent_missing 阻断闸门
        examples_consent=True,
        max_file_size=2_000_000,
    )
    dev_docs = [os.path.join(ROOT, "README.md"), os.path.join(ROOT, "CHANGELOG.md")]

    print("[audit] 审计目标：%s（最新源码）" % SRC)
    print("[audit] deadcode 精度模式：%s%s" % (
        deadcode_mode, "（已装 vulture）" if deadcode_mode == "vulture" else "（零依赖 ast，易误报）"))
    print("[audit] 开发者模式：递归扫描 %s 内全部 .md + 显式开发文档：%s"
          % (SRC, ", ".join(os.path.basename(d) for d in dev_docs)))
    print("[audit] 排除开发期工具：%s" % ", ".join(sorted(DEV_TOOLS)))

    result = analyze_skill(
        SRC,
        enabled=list(ALL_CHECKERS),
        args=cli_args,
        dev_docs=dev_docs,
        exclude=DEV_TOOLS,
        dev_audit=True,    # src/ 目录名是 src 而非技能名，抑制 structure name_mismatch 误报
    )

    # ---- 4) 汇总 ----
    findings = result.get("findings", [])
    s = summarize(findings)
    print("\n" + "=" * 72)
    print("开发模式自审计结果")
    print("=" * 72)
    by = {}
    for f in findings:
        by.setdefault(f["checker"], []).append(f)
    runs = {c["name"]: c for c in result.get("checker_runs", [])}
    for chk in ALL_CHECKERS:
        fs = by.get(chk, [])
        cs = summarize(fs)
        run = runs.get(chk)
        code = run["code"] if run else CHECKER_CODES.get(chk)
        status = run["status"] if run else "OK"
        flag = "✓" if cs["error"] == 0 and (args.strict or cs["warn"] == 0) else "✗"
        run_badge = "" if status == "OK" else "  [%s]" % status
        print("  %s[%s] %s ERROR %d / WARN %d / INFO %d%s"
              % (("[#%02d] " % code) if code is not None else "", chk, flag,
                 cs["error"], cs["warn"], cs["info"], run_badge))
        for f in fs:
            if f["severity"] in ("ERROR", "WARN"):
                loc = f.get("file") or ""
                if f.get("line"):
                    loc += ":%d" % f["line"]
                print("      - [%s] %s%s%s" % (
                    f["severity"], f.get("category_cn", f["category"]),
                    ("（%s）" % loc) if loc else "",
                    "：%s" % f["message"] if f["severity"] == "WARN" else ""))

    rec = checker_receipt_runs(result)
    if rec:
        print("  " + rec)
    print("\n汇总：ERROR %d / WARN %d / INFO %d" % (s["error"], s["warn"], s["info"]))
    if not sync_ok:
        print("⚠ 同步校验未通过（部署副本与源码不一致），发布前请先解决。")

    # ---- 5) 发布就绪检查：对 agent 发出待办提示（减少记忆依赖）----
    # 由 pre-push 钩子与 dev-qa CI 共同调用，故本地与远程门禁都会提示。
    try:
        from release_check import run_release_checks
        rel_block, rel_info = run_release_checks()
    except Exception as e:
        rel_block, rel_info = [], [{"severity": "INFO",
                                     "title": "发布就绪检查不可用",
                                     "detail": str(e),
                                     "todo": "手动核对版本号/CHANGELOG/dist/temp"}]
    # ---- 5b) 版本变动提示（次/主版本）：解析 dev_market_bench.check-bump 输出 ----
    # 必须项([必须])并入 rel_block（阻断，--strict 下失败 → 拦 push）；
    # 建议项([建议])并入 rel_info（不阻断）。其它上下文行（版本变动标题）原样打印。
    # best-effort：脚本缺失 / 无网络 / 缓存目录不可写均静默跳过，不影响门禁退出码。
    try:
        mb = os.path.join(HERE, "dev_market_bench.py")
        if os.path.isfile(mb):
            out = subprocess.run([sys.executable, mb, "check-bump"],
                                 capture_output=True, text=True, timeout=30)
            mb_block, mb_info, mb_ctx = _parse_check_bump(out.stdout + out.stderr)
            rel_block.extend(mb_block)
            rel_info.extend(mb_info)
            for c in mb_ctx:
                if c.strip():
                    print(c)
    except Exception:  # noqa: BLE001
        pass
    # ---- 5c) 开发期工具语法守卫（堵盲区）----
    # DEV_TOOLS 被发布面排除集剔除（不参与结构/安全/依赖检查），此处复用 compile_python_file 兜底
    # 语法关，避免「改了 dev 工具却漏编译」导致下次运行直接崩溃。非阻断（INFO/[建议]）。
    dev_ok, dev_errs = _guard_dev_tools()
    print("[dev-tools] 开发期工具语法守卫（DEV_TOOLS）：%s"
          % ("一致 OK" if dev_ok else "不一致 %d 处" % len(dev_errs)))
    if not dev_ok:
        print("[dev-tools] ⚠ 下列开发期工具存在语法错误，发布前请修复：")
        for e in dev_errs:
            print("      - %s" % e)
        rel_info.append({
            "severity": "建议",
            "title": "开发期工具存在语法错误（py_compile 守卫）",
            "detail": "；".join(dev_errs),
            "todo": "对报错的 dev 工具运行 `python -m py_compile src/scripts/<文件名>` 修复语法后再提交",
        })
    if rel_block or rel_info:
        print("\n" + "=" * 72)
        print("发布前待办（Agent 提示 · 由 pre-push 钩子与 dev-qa 工作流发出）")
        print("=" * 72)
        for r in rel_block:
            print("  [agent-todo][%s] %s" % (r["severity"], r["title"]))
            print("      %s" % r["detail"])
            print("      → %s" % r["todo"])
        if rel_info:
            print("\n  —— 非阻断项（请逐项确认是否适用，勿直接略过）——")
            for r in rel_info:
                print("  [agent-todo][%s] %s" % (r["severity"], r["title"]))
                print("      %s" % r["detail"])
                print("      → %s" % r["todo"])
        if rel_block:
            print("\n⚠ 存在阻断项，发布前须先解决（--strict 下将失败）。")

    # 阻断项并入失败判定（版本不一致 / CHANGELOG 未收口）
    failed = (s["error"] > 0) or (args.strict and s["warn"] > 0) or bool(rel_block)
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
