# checkers/doc.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）

def check_doc(ctx):
    doc = ctx["doc"]
    code = ctx["code"]
    blob = ctx["blob"]
    scripts_dir = ctx["scripts_dir"]
    findings = []

    # A1 死路径 / 技能外裸文件名
    for m in FILE_REF_RE.finditer(doc):
        ref = m.group(1)
        if resolve_exists(ctx["skill_dir"], ref, scripts_dir):
            continue
        if ref.startswith(("http://", "https://")):
            continue
        if "/" in ref or "\\" in ref:
            findings.append(finding("doc", SEVERITY_ERROR, "DEAD_PATH",
                                    "文档里写的路径 %s 在当前技能目录中找不到" % ref, file="SKILL.md",
                                    suggestion="修正路径或补充文件"))
        else:
            findings.append(finding("doc", SEVERITY_INFO, "EXTERNAL_REF",
                                    "裸文件名引用，可能指向技能外文件，需人工确认: %s" % ref,
                                    file="SKILL.md"))

    # A2 失效参数（仅本技能 python 命令行示例中的参数）
    for m in FLAG_RE.finditer(doc):
        flag = m.group(1)
        ls = doc.rfind("\n", 0, m.start()) + 1
        le = doc.find("\n", m.end())
        line = doc[ls:le if le != -1 else len(doc)]
        if "python" not in line.lower():
            continue
        if flag not in blob:
            findings.append(finding("doc", SEVERITY_ERROR, "DEAD_FLAG",
                                    "文档命令行参数在代码中无实现: %s" % flag, file="SKILL.md",
                                    suggestion="实现该参数或更正文档示例"))

    # A3 退出码口径
    doc_exits = set(DOC_EXIT_RE.findall(doc))
    code_exits = set(CODE_EXIT_RE.findall(blob))
    deprecated = set()
    for line in doc.splitlines():
        m2 = re.match(r"^\|\s*`(\d+)`\s*\|", line)
        if m2 and re.search(r"已弃用|已停用|已废弃|已移除|deprecated", line, re.I):
            deprecated.add(m2.group(1))
    for d in sorted(doc_exits - code_exits, key=int):
        if d in deprecated:
            continue
        findings.append(finding("doc", SEVERITY_ERROR, "EXIT_DOC_ONLY",
                                "文档列了退出码但代码从不返回: %s" % d, file="SKILL.md"))
    for c in sorted(code_exits - doc_exits, key=int):
        findings.append(finding("doc", SEVERITY_ERROR, "EXIT_CODE_ONLY",
                                "代码会返回该退出码但文档未列: %s" % c, file="SKILL.md",
                                suggestion="在文档补全退出码说明"))

    # A4 标识符
    declared = ctx.get("declared_tools", set())
    seen_idents = set()
    for m in IDENT_RE.finditer(doc):
        ident = m.group(1)
        if ident not in blob:
            if ident in declared:
                # 外部 MCP / 插件工具名（frontmatter 或文档中声明），非本地代码符号，跳过避免误报
                continue
            if ident in seen_idents:
                # 同一标识符在文档多处提及只报一次，避免重复刷屏
                continue
            seen_idents.add(ident)
            # 能力声明语境下出现未知标识符 → 升级为「能力漂移」提示（更精准，免与通用 UNKNOWN_IDENT 混淆）
            ls = doc.rfind("\n", 0, m.start()) + 1
            le = doc.find("\n", m.end())
            line = doc[ls:le if le != -1 else len(doc)]
            if CAP_VERB_RE.search(line):
                findings.append(finding("doc", SEVERITY_WARN, "DOC_CAPABILITY_DRIFT",
                                        "文档声称提供/支持的能力 %s 在代码中找不到对应实现（可能已移除或拼写有误）" % ident,
                                        file="SKILL.md", suggestion="核实该能力是否仍存在，或更正文档"))
            else:
                findings.append(finding("doc", SEVERITY_WARN, "UNKNOWN_IDENT",
                                        "文档里提到的名称 %s 在代码里找不到（可能拼写有误或已被删除；若为外部 MCP/插件工具请在 frontmatter 的 allowed-tools 声明）" % ident, file="SKILL.md"))

    # A5 版本号（仅 WorkBuddy 平台强制；开放标准 agentskills/generic 不强制 version，避免审计外部技能误报）
    if ctx.get("platform", "workbuddy") == "workbuddy" and not VERSION_RE.search(doc):
        findings.append(finding("doc", SEVERITY_ERROR, "VERSION_MISSING",
                                "SKILL.md 缺少 version 声明", file="SKILL.md",
                                suggestion="添加 version: x.y.z"))

    # C 类：Vector 1 (v1.21.0) 内容漂移——结构化声明 ↔ 代码事实 交叉校验
    # C1 检查器数量声明漂移
    for m in DOC_CHECKER_COUNT_RE.finditer(doc):
        n = int(m.group(1))
        if n != len(ALL_CHECKERS):
            findings.append(finding("doc", SEVERITY_WARN, "DOC_COUNT_DRIFT",
                                    "文档声称 %d 个检查器，代码实际定义 %d 个（ALL_CHECKERS）" % (n, len(ALL_CHECKERS)),
                                    file="SKILL.md", suggestion="同步文档中的检查器数量"))
    # C2 deadcode 模式集合漂移（大括号 / 斜杠两种枚举写法）
    for m in DOC_MODE_BRACE_RE.finditer(doc):
        toks = [t for t in m.group(1).split(",") if t]
        if toks and set(toks) <= set(DEADCODE_MODES) and set(toks) != set(DEADCODE_MODES):
            findings.append(finding("doc", SEVERITY_WARN, "DOC_ENUM_DRIFT",
                                    "文档枚举的 deadcode 模式 %s 与代码实际 %s 不一致（多出或缺失模式）" % (
                                        "、".join(sorted(toks)), "、".join(sorted(DEADCODE_MODES))),
                                    file="SKILL.md", suggestion="同步文档中的 deadcode 模式集合"))
    for m in DOC_MODE_SLASH_RE.finditer(doc):
        toks = m.group(1).split("/")
        if set(toks) <= set(DEADCODE_MODES) and set(toks) != set(DEADCODE_MODES):
            findings.append(finding("doc", SEVERITY_WARN, "DOC_ENUM_DRIFT",
                                    "文档枚举的 deadcode 模式 %s 与代码实际 %s 不一致" % (
                                        "、".join(sorted(toks)), "、".join(sorted(DEADCODE_MODES))),
                                    file="SKILL.md", suggestion="同步文档中的 deadcode 模式集合"))

    # B 类：仅枚举，供 AI 判断
    statuses = sorted(set(STATUS_RE.findall(blob)))
    status_missing = [s for s in statuses if s not in doc]
    if statuses:
        findings.append(finding("doc", SEVERITY_INFO, "B_STATUS",
                                "运行状态全集(%d): %s；文档未出现: %s" % (
                                    len(statuses), ", ".join(statuses),
                                    ", ".join(status_missing) or "无")))
    cfg_keys = []
    cfg_path = os.path.join(scripts_dir, "config.json")
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                cfg_keys = sorted(json.load(fh).keys())
        except Exception:
            pass
    cfg_missing = [k for k in cfg_keys if k not in doc]
    if cfg_keys:
        findings.append(finding("doc", SEVERITY_INFO, "B_CONFIG",
                                "配置项全集(%d): %s；文档未出现: %s" % (
                                    len(cfg_keys), ", ".join(cfg_keys),
                                    ", ".join(cfg_missing) or "无")))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：structure（结构体检 + 元信息）
# --------------------------------------------------------------------------- #
# 自注册
CHECKERS["doc"] = check_doc

