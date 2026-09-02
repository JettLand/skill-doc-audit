# cli.py (拆分自 audit_docs.py)
from auditlib.core import *
from auditlib.model import *
from auditlib.report import *
from auditlib.sources import *

def main():
    global MAX_FILE_SIZE
    ap = argparse.ArgumentParser(description="技能静态体检（文档一致性/结构/安全/可运行性）")
    ap.add_argument("--skill", help="技能目录")
    ap.add_argument("--all", action="store_true", help="审计 ~/.workbuddy/skills 下全部技能")
    ap.add_argument("--check", action="append", metavar="NAME",
                    help="启用插件式检查器(doc/structure/security/runtime/deps/deadcode/portability/doc-llm/examples)，可重复；doc 常驻默认开；doc-llm 默认按 ask 处理（弹菜单询问是否启用语义检测，由 agent 接手），显式 --doc-llm-mode agent 即由 agent 直接接手（不依赖外部 LLM、但会占用 agent 推理 token，输入侧为主）；examples 默认 ask(交互询问是否沙箱试运行，超时/非交互回退 static 零执行/零网络/零 token)，--examples-mode run 方在受限沙箱试运行带 expected 标注的示例")
    ap.add_argument("--all-checks", action="store_true", help="启用全部检查器（含 doc-llm：交互终端弹菜单询问是否启用 LLM 语义检测，30 秒超时默认不启用，绝不自动联网；非交互环境跳过并以 INFO 提示；含 examples：默认 ask(交互询问是否沙箱试运行，超时/非交互回退 static 零执行/零网络/零 token)，--examples-mode run 方在受限沙箱试运行带 expected 标注的示例）")
    ap.add_argument("--backup", action="store_true", help="审计前备份 SKILL.md")
    ap.add_argument("--backup-limit", type=int, default=BACKUP_LIMIT,
                    help="SKILL.md 最多保留的备份数（默认 %d）" % BACKUP_LIMIT)
    ap.add_argument("--json", action="store_true", help="额外输出 JSON 机读结果")
    ap.add_argument("--strict", action="store_true", help="WARN 也计入退出码（CI 门禁用）")
    ap.add_argument("--timeout", type=float, default=0,
                    help="整体超时秒数（0=不限制）；超时后优雅终止而非卡死")
    ap.add_argument("--max-file-size", type=int, default=MAX_FILE_SIZE,
                    help="单文件超过此字节数跳过扫描（默认 %d）" % MAX_FILE_SIZE)
    ap.add_argument("--deadcode-mode", default="ask", choices=list(DEADCODE_MODES),
                    help="deadcode 精度模式：ask(默认,已装vulture则自动高精度否则交互询问,超时30s→ast) / vulture(高精度,需装 vulture) / ast(零依赖,易误报) / skip(本次跳过)")
    ap.add_argument("--doc-llm-mode", default=None, choices=list(DOCLLM_MODES),
                    help="doc-llm 语义漂移检测模式（v1.24.0 起由 agent 直接接手，不再依赖外部 LLM；v1.24.1 起移除 preview 选项）：ask(默认,交互终端呈现实选项：1)默认模式 2)agent接手(会占用 agent 推理 token，但不向外部 LLM 付费)，30 秒超时自动回退默认模式) / off(不运行) / agent(直接由 agent 接手：脚本写 dossier + 打印 AGENT_TAKEOVER 哨兵，agent 读取后自行比对)。Agent 经 AskUserQuestion 收到用户选择后显式传入")
    ap.add_argument("--examples-mode", default="ask", choices=list(EXAMPLES_MODES),
                    help="examples 检查器模式（v1.26.0 新增，泛用版文档示例校验）：ask(默认,交互终端询问是否允许沙箱试运行,30秒超时或本地非交互一律回退 static 并 INFO 标注降级) / static(纯静态解析,零执行/零网络/零 token,检查示例引用的文件是否存在/参数是否声明/外部CLI是否声明/是否含危险命令) / run(受限沙箱试运行带 expected 标注的示例:仅白名单解释器+技能内脚本+超时保护) / off(本次不运行)")
    ap.add_argument("--examples-timeout", type=float, default=20,
                    help="examples run 模式下单条示例命令执行超时秒数（默认 20）")
    ap.add_argument("--examples-max-cmd", type=int, default=12,
                    help="examples run 模式下单技能最多执行的示例命令条数（默认 12，防突刺）")
    ap.add_argument("--preview", action="store_true",
                    help="只预览将运行哪些检查器、将扫描哪些文件，不产出发现，退出码 0（适合首次审计前心里有数）")
    ap.add_argument("--source", default="local", choices=list(SOURCES),
                    help="技能来源：local(默认,--skill/--all) / github(--ref 仓库) / skillhub(--ref slug,经 skillhub CLI 拉取) / url(--ref https 地址,标准库直接抓取任意 SKILL.md)")
    ap.add_argument("--ref", help="来源引用：github 为 owner/repo 或 https 地址(可 @分支)；skillhub 为技能 slug；url 为 SKILL.md 的 https 地址（可指向文件或所在目录，支持 github.com blob 链接自动转 raw）")
    ap.add_argument("--keep-temp", action="store_true",
                    help="保留 github/skillhub 产生的临时目录（用于排查，默认审计后自动清理）")
    ap.add_argument("--report", default=None,
                    choices=["portability-matrix", "health", "translate"],
                    help="生成专项报告：portability-matrix 跨格式可移植性矩阵；health 生态级健康度汇总；translate 跨格式转译报告（需配 --target）")
    ap.add_argument("--target", default=None,
                    choices=["workbuddy", "agentskills", "claude-code", "cursor-plugin", "generic"],
                    help="--report translate 的目标格式（与源格式双向）：workbuddy / agentskills / claude-code / cursor-plugin / generic。其中 agentskills 与 cursor-plugin 即 Agent Skills 开放标准(agentskills.io)，一次转译可被 40+ 工具(Claude Code、Cursor、Gemini CLI、Codex、Copilot、Windsurf、Kiro、OpenCode 等)直接消费；generic 为仅保留 name/description 的降级兜底")
    ap.add_argument("--verify", action="store_true",
                    help="跨格式转译时做内存往返保真校验（emit→re-parse→比对，不落盘）")
    ap.add_argument("--dev-docs", nargs="*", metavar="PATH",
                    help="开发模式：递归扫描技能文件夹内全部 .md 描述性文档（README/CHANGELOG/examples/License 等）"
                         "一并交给 doc（A1 裸文件名 EXTERNAL_REF 提示）+ doc-llm（语义漂移 dossier）漂移扫描；"
                         "可选追加显式路径（相对仓库根或绝对，空格分隔）纳入 out-of-tree 文档（如项目根 README/CHANGELOG），"
                         "其仓库相对引用按文件自身目录解析，降低 DEAD_PATH 误报。"
                         "默认（不带此旗标）仅扫描 SKILL.md + references/*.md。")
    args = ap.parse_args()

    MAX_FILE_SIZE = args.max_file_size

    watchdog = None
    if args.timeout and args.timeout > 0:
        def _on_timeout():
            sys.stderr.write("\n[超时] 审计超过 %.0f 秒，强制终止\n" % args.timeout)
            _thread.interrupt_main()
        watchdog = threading.Timer(args.timeout, _on_timeout)
        watchdog.daemon = True
        watchdog.start()
    # 解析技能来源：本地/远程仓库/集市，统一落地为本地目录列表
    # Phase 8：--ref 支持逗号分隔多仓库（org/多仓库批量审计）；local 忽略 ref
    src = get_source(args.source)
    refs = [r.strip() for r in (args.ref or "").split(",") if r.strip()]
    if args.source == "local" or not refs:
        targets, cleanup_dirs = src.resolve(args.ref, args)
    else:
        targets, cleanup_dirs = [], []
        for ref in refs:
            d, c = src.resolve(ref, args)
            targets += d
            cleanup_dirs += c
    for t in targets:
        if not os.path.isdir(t):
            print("目录不存在: %s" % t, file=sys.stderr)
            sys.exit(2)

    # 解析启用的检查器：doc 常驻，--check 追加，--all-checks 全开
    enabled = list(DEFAULT_CHECKERS)
    if args.all_checks:
        enabled = list(ALL_CHECKERS)
    elif args.check:
        for c in args.check:
            if c not in CHECKERS:
                print("未知检查器: %s（可选: %s）" % (c, ", ".join(CHECKERS)), file=sys.stderr)
                sys.exit(2)
            if c not in enabled:
                enabled.append(c)
    # 转译报告：仅解析模型、不跑检查器（报告本身取代常规体检输出）
    if args.report == "translate":
        if not args.target:
            print("--report translate 需要 --target <agentskills|claude-code|cursor-plugin|generic>", file=sys.stderr)
            sys.exit(2)
        enabled = []

    # 检查预览：只展示将运行哪些检查器、将扫描哪些文件，不产出发现
    if args.preview:
        for t in targets:
            d = os.path.join(t, "SKILL.md")
            code, _skipped = collect_code(t)
            print("预览：%s" % t)
            print("  启用检查器: %s" % ", ".join("#%02d %s" % (CHECKER_CODES.get(c, 0), c) for c in enabled))
            if "deadcode" in enabled:
                print("  deadcode 精度模式: %s（ask=已装vulture则自动高精度,否则交互询问30s→ast/非TTY回退ast并提示精度降级）" % args.deadcode_mode)
            if "examples" in enabled:
                print("  examples 模式: %s（static=纯静态零执行/零网络/零 token；run=受限沙箱试运行带 expected 标注的示例）" % args.examples_mode)
            print("  文档: %s" % ("SKILL.md" if os.path.isfile(d) else "（无）"))
            # 列出实际被扫文档：默认 SKILL.md + references/*.md；--dev-docs 再加技能内全部 .md
            _docs_preview = ["SKILL.md"]
            _rd = os.path.join(t, "references")
            if os.path.isdir(_rd):
                _docs_preview += ["references/%s" % f for f in sorted(os.listdir(_rd)) if f.endswith(".md")]
            if args.dev_docs is not None:
                _docs_preview.append("（递归扫描 %s 内全部 .md）" % t)
                if args.dev_docs:
                    _docs_preview += list(args.dev_docs)
            print("  纳入漂移扫描的文档: %s" % ", ".join(_docs_preview))
            print("  将扫描代码/配置文件 %d 个:" % len(code))
            for rel in sorted(code.keys()):
                print("    - %s" % rel)
            if _skipped:
                print("  跳过（超大文件）: %s" % ", ".join(sorted(_skipped)[:10]))
        sys.exit(0)

    results = [analyze_skill(t, enabled, args=args, do_backup=args.backup,
                             backup_limit=args.backup_limit,
                             dev_docs=args.dev_docs) for t in targets]
    if args.report != "translate":
        print_human(results)
    if args.report == "portability-matrix":
        for r in results:
            if r.get("skill_model"):
                print_portability_matrix(r["skill_model"])
    if args.report == "health" or (args.json and len(results) > 1):
        summary = build_health_summary(results)
        if args.report == "health":
            print_health_summary(summary)
    if args.report == "translate":
        for r in results:
            sm = r.get("skill_model")
            if not sm:
                print("跳过（无 SKILL.md / 模型）: %s" % r.get("skill"))
                continue
            build_translate_report(sm, args.target, verify=args.verify)
        if args.json:
            for r in results:
                if r.get("skill_model"):
                    r["translate"] = build_translate_json(r["skill_model"], args.target, verify=args.verify)
    if args.json:
        print("\n" + "=" * 72)
        print("JSON 结果：")
        out = build_json(results)
        # 多技能审计时附带健康度汇总，便于 CI / 批量巡检消费
        if len(results) > 1:
            out = {"health_summary": build_health_summary(results), "skills": out}
        print(json.dumps(out, ensure_ascii=False, indent=2))

    # 清理来源产生的临时目录（--keep-temp 时保留并打印路径供排查）
    for d in cleanup_dirs:
        if args.keep_temp:
            print("[保留临时目录] %s" % d)
        else:
            shutil.rmtree(d, ignore_errors=True)

    total_err = sum(summarize(r.get("findings", [])).get("error", 0)
                    for r in results if "findings" in r)
    total_warn = sum(summarize(r.get("findings", [])).get("warn", 0)
                     for r in results if "findings" in r)
    failed = (total_err > 0) or (args.strict and total_warn > 0)
    if watchdog is not None:
        watchdog.cancel()
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\n审计被中断（Ctrl+C 或超时），已安全退出，未产生部分结果。\n")
        sys.exit(130)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("\n审计异常终止：%s\n" % e)
        sys.exit(2)

