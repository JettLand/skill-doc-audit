# checkers/doc.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）

def check_doc(ctx):
    findings = []
    extra_roots = ctx.get("extra_roots") or []
    docs = ctx.get("docs") or [{"name": "SKILL.md", "content": ctx.get("doc", "")}]
    scripts_dir = ctx["scripts_dir"]
    code = ctx["code"]
    blob = ctx["blob"]
    declared = ctx.get("declared_tools", set())

    for d in docs:
        doc = d["content"]
        doc_name = d["name"]

        # A1 死路径 / 技能外裸文件名
        # 仅 SKILL.md 报 DEAD_PATH(ERROR)：SKILL.md 是规范能力目录，其中每个带 / 的路径都应真实存在；
        # references/*.md 与开发文档为叙述性内容，常出现「references/x.md」「scripts/x.py」类示例路径，
        # 套用 ERROR 会大量误报，故非 SKILL.md 文档只对裸文件名报 EXTERNAL_REF(INFO)（低噪音、非阻断），
        # 真实断链改由 doc-llm 语义 dossier 覆盖。
        for m in FILE_REF_RE.finditer(doc):
            ref = m.group(1)
            # 扩展名枚举（如「.py/.js/.sh/.ps1/.json」）不是文件路径，跳过避免误报死路径
            if ref.startswith(".") and "/" in ref:
                continue
            if resolve_exists(ctx["skill_dir"], ref, scripts_dir, extra_roots=extra_roots):
                continue
            if ref.startswith(("http://", "https://")):
                continue
            if doc_name == "SKILL.md":
                if "/" in ref or "\\" in ref:
                    findings.append(finding("doc", SEVERITY_ERROR, "DEAD_PATH",
                                            "文档里写的路径 %s 在当前技能目录中找不到" % ref, file=doc_name,
                                            suggestion="修正路径或补充文件", ref=ref))
                else:
                    findings.append(finding("doc", SEVERITY_INFO, "EXTERNAL_REF",
                                            "裸文件名引用，可能指向技能外文件，需人工确认: %s" % ref,
                                            file=doc_name, ref=ref))
            else:
                # 非 SKILL.md（references/开发文档）：叙述性内容，仅对裸文件名做 INFO 级提示，不报 ERROR
                if "/" not in ref and "\\" not in ref:
                    findings.append(finding("doc", SEVERITY_INFO, "EXTERNAL_REF",
                                            "裸文件名引用，可能指向技能外文件，需人工确认: %s" % ref,
                                            file=doc_name, ref=ref))

        # A2 失效参数（CLI 契约，仅 SKILL.md：开发文档命令示例常引用开发期工具如
        # make_fixtures.py --baseline，其参数不在发布面代码 blob 中，按能力目录口径跳过避免误报）
        if doc_name == "SKILL.md":
            for m in FLAG_RE.finditer(doc):
                flag = m.group(1)
                ls = doc.rfind("\n", 0, m.start()) + 1
                le = doc.find("\n", m.end())
                line = doc[ls:le if le != -1 else len(doc)]
                if "python" not in line.lower():
                    continue
                if flag not in blob:
                    findings.append(finding("doc", SEVERITY_ERROR, "DEAD_FLAG",
                                            "文档命令行参数在代码中无实现: %s" % flag, file=doc_name,
                                            suggestion="实现该参数或更正文档示例"))

        # A3 退出码口径（仅 SKILL.md：退出码是技能本体的契约，开发文档不列退出码，避免误报）
        if doc_name == "SKILL.md":
            # 文档退出码：表格行 + 「退出码：」行内反引号（两种写法都收）
            doc_exits = set(DOC_EXIT_RE.findall(doc))
            for _line in doc.splitlines():
                if "退出码" in _line:
                    doc_exits |= set(DOC_EXIT_INLINE_RE.findall(_line))
            # 代码退出码：从 sys.exit(<arg>) 实参中提取数字（覆盖条件表达式两种分支）
            code_exits = set()
            for _arg in CODE_EXIT_RE.findall(blob):
                code_exits |= set(re.findall(r"\d+", _arg))
            deprecated = set()
            for line in doc.splitlines():
                m2 = re.match(r"^\|\s*`(\d+)`\s*\|", line)
                if m2 and re.search(r"已弃用|已停用|已废弃|已移除|deprecated", line, re.I):
                    deprecated.add(m2.group(1))
            for ex in sorted(doc_exits - code_exits, key=int):
                if ex in deprecated:
                    continue
                findings.append(finding("doc", SEVERITY_ERROR, "EXIT_DOC_ONLY",
                                        "文档列了退出码但代码从不返回: %s" % ex, file=doc_name))
            for c in sorted(code_exits - doc_exits, key=int):
                findings.append(finding("doc", SEVERITY_ERROR, "EXIT_CODE_ONLY",
                                        "代码会返回该退出码但文档未列: %s" % c, file=doc_name,
                                        suggestion="在文档补全退出码说明"))

        # A4 标识符（能力目录漂移）：SKILL.md 是技能能力的规范性目录，只有它才做符号级
        # 能力漂移（DOC_CAPABILITY_DRIFT / UNKNOWN_IDENT）。开发文档（README/CHANGELOG）是
        # 叙述性变更日志，常提及「已移除的符号」（如历史版本删掉的 _call_llm），属历史叙事、
        # 非真实漂移，跳过避免噪音；其语义漂移改由 doc-llm dossier 扫描覆盖。
        if doc_name == "SKILL.md":
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
                                                file=doc_name, suggestion="核实该能力是否仍存在，或更正文档"))
                    else:
                        findings.append(finding("doc", SEVERITY_ERROR, "UNKNOWN_IDENT",
                                                "文档里提到的名称 %s 在代码里找不到（可能拼写有误或已被删除；若为外部 MCP/插件工具请在 frontmatter 的 allowed-tools 声明）" % ident, file=doc_name))

        # A5 版本号（仅 WorkBuddy 平台强制；开放标准 agentskills/generic 不强制 version，避免审计外部技能误报）
        # 仅对技能本体 SKILL.md 检查；开发文档（README/CHANGELOG）无 frontmatter，不强制。
        if doc_name == "SKILL.md" and ctx.get("platform", "workbuddy") == "workbuddy" \
                and not VERSION_RE.search(doc):
            findings.append(finding("doc", SEVERITY_ERROR, "VERSION_MISSING",
                                    "SKILL.md 缺少 version 声明", file=doc_name,
                                    suggestion="添加 version: x.y.z"))

        # C 类：内容漂移——结构化声明 ↔ 代码事实 交叉校验（仅 SKILL.md：开发文档为叙述性变更日志，
        # 其中的「第 7 个检查器」「共 6 个检查器」「删 skip」等历史表述会被数量/枚举正则误判为漂移，非真实漂移）
        if doc_name == "SKILL.md":
            # C1 检查器数量声明漂移
            for m in DOC_CHECKER_COUNT_RE.finditer(doc):
                n = int(m.group(1))
                if n != len(ALL_CHECKERS):
                    findings.append(finding("doc", SEVERITY_WARN, "DOC_COUNT_DRIFT",
                                            "文档声称 %d 个检查器，代码实际定义 %d 个（ALL_CHECKERS）" % (n, len(ALL_CHECKERS)),
                                            file=doc_name, suggestion="同步文档中的检查器数量"))
            # C2 deadcode 模式集合漂移（大括号 / 斜杠两种枚举写法）
            for m in DOC_MODE_BRACE_RE.finditer(doc):
                toks = [t for t in m.group(1).split(",") if t]
                if toks and set(toks) <= set(DEADCODE_MODES) and set(toks) != set(DEADCODE_MODES):
                    findings.append(finding("doc", SEVERITY_WARN, "DOC_ENUM_DRIFT",
                                            "文档枚举的 deadcode 模式 %s 与代码实际 %s 不一致（多出或缺失模式）" % (
                                                "、".join(sorted(toks)), "、".join(sorted(DEADCODE_MODES))),
                                            file=doc_name, suggestion="同步文档中的 deadcode 模式集合"))
            for m in DOC_MODE_SLASH_RE.finditer(doc):
                toks = m.group(1).split("/")
                if set(toks) <= set(DEADCODE_MODES) and set(toks) != set(DEADCODE_MODES):
                    findings.append(finding("doc", SEVERITY_WARN, "DOC_ENUM_DRIFT",
                                            "文档枚举的 deadcode 模式 %s 与代码实际 %s 不一致" % (
                                                "、".join(sorted(toks)), "、".join(sorted(DEADCODE_MODES))),
                                            file=doc_name, suggestion="同步文档中的 deadcode 模式集合"))

        # B 类：仅枚举，供 AI 判断（基于代码事实，挂在技能本体 SKILL.md 上）
        if doc_name == "SKILL.md":
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

        # C3 正向能力覆盖（代码有、文档没写）——与 DOC_CAPABILITY_DRIFT 正反向对称（v1.27.0）
        # 仅当目标技能使用本框架（blob 含 ALL_CHECKERS 标记，即审计自家技能）才做强校验，
        # 避免对第三方技能误报；第三方技能不跑本段（其能力契约我们无从知晓，误报比漏报更糟）。
        # 文档比对用全部被扫文档并集（SKILL.md + references 等），避免「写在 checkers.md 却被判缺失」。
        if doc_name == "SKILL.md" and "ALL_CHECKERS" in blob:
            all_doc_text = "\n".join(d["content"] for d in docs)
            checker_gaps, flag_gaps = compute_capability_gaps(code, all_doc_text)
            for name in checker_gaps:
                findings.append(finding("doc", SEVERITY_WARN, "DOC_CAPABILITY_MISSING",
                                        "代码注册了检查器 %s，但 SKILL.md 未提及（能力目录漏列）" % name,
                                        file=doc_name,
                                        suggestion="在「能力边界」或检查器章节补 %s 的说明" % name))
            for fl in flag_gaps:
                findings.append(finding("doc", SEVERITY_WARN, "DOC_CAPABILITY_MISSING",
                                        "代码声明了命令行参数 %s 但文档未提及（用户面向参数应写入文档）" % fl,
                                        file=doc_name,
                                        suggestion="在 SKILL.md / checkers.md 的 CLI 速查补 %s 说明" % fl))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：structure（结构体检 + 元信息）
# --------------------------------------------------------------------------- #
# 自注册
CHECKERS["doc"] = check_doc
