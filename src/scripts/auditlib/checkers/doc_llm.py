# checkers/doc_llm.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）

def _code_fact_sheet(code):
    """从代码 blob 抽取轻量「事实清单」交给 agent 接手比对：定义/CLI 参数/返回码/常量。

    不直接倾倒整份源码（避免超长上下文），仅给 agent 可交叉比对的符号事实。
    """
    rows = []
    for rel, content in code.items():
        defs = re.findall(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.M)
        flags = re.findall(r'add_argument\(\s*["\'](--[A-Za-z0-9_-]+)', content)
        returns = sorted(set(re.findall(r"return\s+(\d+)", content)))
        consts = re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=", content, re.M)
        rows.append("文件 %s: 顶层定义=%s; CLI参数=%s; 返回码=%s; 常量=%s"
                    % (rel, defs[:40], flags, returns, consts[:40]))
    return "\n".join(rows)


# （v1.24.0）原 _parse_llm_drift 用于解析外部 LLM 返回，已随外部 LLM 调用移除；agent 接手后
# 由 agent 直接判定语义漂移，不再需要结构化解析。


def _resolve_doc_llm_mode(args):
    """决定 doc-llm 模式与是否「非交互跳过」。

    返回 (mode, degraded, reason)，与 _resolve_deadcode_mode 同构：
    - mode: "off" | "agent"
    - degraded/reason：仅当「--all-checks 全量自带、非交互环境无法询问」时标记，
      供 check_doc_llm 发 INFO doc_llm_skipped（不污染「全量检测 WARN 0」不变量）。

    v1.24.0 起：语义漂移检测由 agent 直接接手，本函数不再处理任何外部 LLM 配置；
    v1.24.1 起：移除 preview 模式（会重复占用 agent 推理 token，徒增成本）。
      - 未显式传入（--all-checks 全量路径即此）→ 按 ask：交互弹菜单，超时 30s 回退默认；
      - 显式 off：完全不运行；
      - 显式 ask：交互弹菜单，超时 30s 回退默认；非交互 → 无法询问，回退默认并记 INFO 跳过；
      - 显式 agent：直接由 agent 接手（脚本写 dossier + 打印哨兵）。
    """
    raw = getattr(args, "doc_llm_mode", None) if args else None
    mode = raw or "ask"
    if mode == "off":
        return "off", False, None
    if mode == "agent":
        return "agent", False, None
    # ask 模式：交互征询，绝不替用户决定
    if not sys.stdin.isatty():
        # 自动化环境无法询问 → 回退默认（纯脚本），并显著告知被跳过（INFO，不告警）
        return "off", True, "ask 模式处于非交互（自动化）环境，无法向用户询问，已回退默认（纯脚本）模式"
    choice = _prompt_doc_llm_mode(timeout=30)
    if choice == "agent":
        return "agent", False, None
    # off（含超时/无输入/选 1）：用户明确放弃，非降级
    return "off", False, None


def _prompt_doc_llm_mode(timeout=30):
    """交互式询问 doc-llm 运行方式；超时/无输入默认「默认模式」（不调用 LLM）。

    返回 "off" | "agent"：
      - off：纯脚本检查，零依赖，不调用 LLM（0 token）——超时/无输入/选 1 的落点；
      - agent：由 agent 介入完成语义漂移检测（使用 agent 自身能力，会占用 agent 推理 token，但不依赖外部 LLM、无需付费）。
    代价透明 + 兜底：菜单标注「agent 介入、消耗额外 token」；超时一律回退 off，绝不联网。
    """
    sys.stderr.write(
        "\n[doc-llm] 语义漂移检测（Vector 2）如何运行？\n"
        "  1) 默认模式：纯脚本检查，零依赖，不调用 LLM（0 token）【推荐 · %d 秒超时默认】\n"
        "  2) 启用语义漂移检查（agent 介入，消耗额外 token）\n"
        "请选择 [1/2]：" % timeout
    )
    sys.stderr.flush()
    buf = {}

    def _read():
        try:
            buf["v"] = sys.stdin.readline().strip()
        except Exception:
            buf["v"] = ""

    th = threading.Thread(target=_read, daemon=True)
    th.start()
    th.join(timeout)
    choice = buf.get("v", "")
    if not choice:
        sys.stderr.write("\n[doc-llm] 超时/无输入，已自动采用默认模式（不调用 LLM）。\n")
        return "off"
    if choice == "2":
        return "agent"
    return "off"


# (v1.24.1) 预览模式已移除：预览会把材料重复灌入上下文、徒增 agent 推理 token，无实质收益。
# 语义比对统一走 agent 接手流程（--doc-llm-mode agent）：脚本写 dossier + 打印 AGENT_TAKEOVER 哨兵。


def _write_doc_llm_dossier(ctx):
    """把被扫文档（SKILL.md + 开发模式下的 README/CHANGELOG 等）全文 + 代码事实清单写入 dossier，
    供 agent 直接接手语义比对。

    返回 dossier 的绝对路径。agent 读取后使用自身能力判定文档声称的能力/默认值/行为/数量/集合
    与代码事实是否一致，回报潜在语义漂移。**不依赖任何外部 LLM 端点（agent 读取后会占用其自身推理 token，输入侧为主）**。
    """
    import tempfile
    docs = ctx.get("docs") or [{"name": "SKILL.md", "content": ctx.get("doc", "")}]
    code = ctx.get("code", {}) or {}
    try:
        sheet = _code_fact_sheet(code)
    except Exception as e:  # noqa: BLE001
        sheet = "（无法生成事实清单：%s）" % e
    doc_sections = "\n\n".join(
        "## 文档 %s 全文\n\n%s" % (d["name"], d["content"]) for d in docs
    )
    content = (
        "# doc-llm 语义漂移检测 Dossier（agent 接手）\n\n"
        "本文件由 skill-doc-audit 生成，供 **agent 直接接手** 完成语义漂移检测。\n"
        "请勿依赖任何外部 LLM；agent 应使用自身能力比对下方材料。\n\n"
        "%s\n\n"
        "## 代码事实清单（由源码抽取：顶层定义 / CLI 参数 / 返回码 / 常量）\n\n%s\n\n"
        "## 比对要点\n"
        "逐条核对上述各文档声称的：能力范围、默认值、行为、数量、集合、CLI 参数、退出码、配置项 —— "
        "是否与代码事实清单一致。\n"
        "仅报告确有依据的语义漂移（文档说法与代码事实冲突），不报告风格/措辞问题。\n"
    ) % (doc_sections, sheet)
    path = os.path.join(tempfile.gettempdir(), "skill_doc_audit_doc_llm_dossier.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def check_doc_llm(ctx):
    """语义漂移检测（Vector 2）——由 agent 直接接手。

    v1.24.0 起：本检查器不再调用任何外部 LLM 端点。语义漂移检测改由 **agent 直接接手**：脚本负责
    准备材料（SKILL.md 全文 + 代码事实清单）并落盘，agent 读取后使用自身能力完成语义比对
    （会占用 agent 自身推理 token，输入侧为主，但不向外部 LLM 服务付费）。流程与 deadcode 检查器
    对齐（同构的 (mode, degraded) 元组）。

      - 显式 off / 非交互 ask 回退 → 跳过（off：静默；非交互全量 → INFO doc_llm_skipped）；
      - agent → 写 dossier + 打印 `[doc-llm] AGENT_TAKEOVER: <path>` 哨兵，由 agent 接手。
    """
    args = ctx.get("args")
    raw_mode = getattr(args, "doc_llm_mode", None) if args else None
    explicit = raw_mode is not None  # 用户是否显式传入 --doc-llm-mode
    mode, degraded, _ = _resolve_doc_llm_mode(args)
    findings = []
    if mode == "agent":
        dossier = _write_doc_llm_dossier(ctx)
        sys.stderr.write("\n[doc-llm] AGENT_TAKEOVER: %s\n" % dossier)
        sys.stderr.write(
            "[doc-llm] 语义漂移检测已由 agent 直接接手（使用 agent 自身能力，不依赖外部 LLM、但会占用 agent 自身推理 token（输入侧为主））。"
            "请 agent 读取上方 dossier 并完成语义比对。\n"
        )
        findings.append(finding(
            "doc-llm", SEVERITY_INFO, "doc_llm_agent_handoff",
            "doc-llm 语义检测转交 agent 接手：dossier 已写入 %s。agent 将使用自身能力比对 SKILL.md 与代码事实清单，会占用 agent 推理 token（输入侧为主），但不向外部 LLM 服务付费。" % dossier,
            suggestion="agent 读取 dossier，比对文档声称的能力/默认值/行为/数量/集合与代码事实清单，回报潜在语义漂移。",
        ))
        return findings
    if mode == "off":
        if degraded and not explicit:
            # --all-checks 全量自带、非交互环境无法询问 → INFO 提示，不升 WARN
            findings.append(finding(
                "doc-llm", SEVERITY_INFO, "doc_llm_skipped",
                "doc-llm（语义漂移检测）已纳入本次全量检测，但当前为非交互环境、无法向用户询问，已跳过（未调用任何 LLM、零成本）。Vector 1 确定性检查仍生效。",
                suggestion="如需语义级检测：由 agent 调用本技能并以 --doc-llm-mode agent 接手；或在交互终端运行 --all-checks 并在菜单中选「agent 接手」。不想被询问可显式 --doc-llm-mode off。",
            ))
        return findings
    # 不应到达
    return findings
# 自注册
# 注意：注册键必须与 ALL_CHECKERS / 命令行 / finding() 的 checker 名一致，均为连字符 "doc-llm"。
# 此前误写为下划线 "doc_llm"，导致 analyze_skill 里 CHECKERS.get("doc-llm") 始终返回 None、
# doc-llm 检查器从未被真正执行（--all-checks / --check doc-llm / dev_self_audit 全量均落空）。
CHECKERS["doc-llm"] = check_doc_llm

