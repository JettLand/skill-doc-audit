# checkers/structure.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）

def check_structure(ctx):
    findings = []
    doc = ctx["doc"]
    skill_dir = ctx["skill_dir"]

    fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", doc, re.S)
    dir_name = os.path.basename(skill_dir.rstrip(os.sep))
    platform = ctx.get("platform", "workbuddy")  # workbuddy 强制 version/license；agentskills/generic 为开放标准，不强制

    if fm:
        fm_text = fm.group(1)
        name_m = re.search(r"^name:\s*(.+)$", fm_text, re.M)
        ver_m = re.search(r"^version:\s*[\"']?([0-9][0-9A-Za-z.\-]*)[\"']?", fm_text, re.M)
        desc_m = re.search(r"^description:\s*(.+)$", fm_text, re.M)
        # 开发模式自审计审计的是 src/（目录名是 src 而非技能名），名称不一致是目录布局使然、非真实漂移；
        # dev_audit 时跳过，避免污染 ERROR/WARN 门禁信号（真实部署目录名与技能名一致，常规审计仍照常检查）。
        if name_m and name_m.group(1).strip().strip("\"'") != dir_name and not ctx.get("dev_audit"):
            findings.append(finding("structure", SEVERITY_WARN, "name_mismatch",
                                    "frontmatter name 与目录名不一致",
                                    suggestion="改为 '%s'" % dir_name))
        if not ver_m:
            if platform == "workbuddy":
                findings.append(finding("structure", SEVERITY_ERROR, "version_missing",
                                        "frontmatter 缺少合规 version",
                                        suggestion="添加 version: x.y.z"))
            # 非 WorkBuddy 平台（开放标准 agentskills/generic）不强制 version，跳过避免误报
        if not name_m:
            findings.append(finding("structure", SEVERITY_ERROR, "name_missing",
                                    "frontmatter 缺少 name 声明",
                                    suggestion="添加 name: <技能目录名>"))
        if not re.search(r"^license:", fm_text, re.M):
            if platform == "workbuddy":
                findings.append(finding("structure", SEVERITY_WARN, "license_missing",
                                        "frontmatter 缺少 license 声明",
                                        suggestion="添加 license: MIT 等"))
            else:
                findings.append(finding("structure", SEVERITY_INFO, "license_missing",
                                        "frontmatter 缺少 license 声明（非 WorkBuddy 平台，建议补充）",
                                        suggestion="添加 license: MIT 等"))
        if desc_m:
            desc = desc_m.group(1).strip().strip("\"'")
            if not (20 <= len(desc) <= 1024):
                findings.append(finding("structure", SEVERITY_WARN, "desc_length",
                                        "description 长度应 20-1024 字符（当前 %d）" % len(desc)))
            has_when = bool(re.search(r"当|如果|用户|遇到|在.*时", desc))
            has_what = bool(re.search(r"检查|审计|生成|创建|扫描|验证|导出|处理|管理", desc))
            if not (has_when and has_what):
                findings.append(finding("structure", SEVERITY_INFO, "desc_four",
                                        "description 建议含四要素（做什么/何时用/关键能力/触发短语）"))
        else:
            findings.append(finding("structure", SEVERITY_ERROR, "desc_missing",
                                    "frontmatter 缺少 description"))
        # H1 标题与 frontmatter 身份一致性（与 name 或 displayName 比对，兼容中英文）
        disp_m = re.search(r"^displayName:\s*(.+)$", fm_text, re.M)
        h1_m = re.search(r"^#\s+(.+)$", doc, re.M)
        if h1_m and name_m:
            nm = name_m.group(1).strip().strip("\"'")
            disp = disp_m.group(1).strip().strip("\"'") if disp_m else ""
            h1n = h1_m.group(1).strip()
            _norm = lambda s: re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s.lower()).strip()
            cand = [_norm(disp), _norm(nm)] if disp else [_norm(nm)]
            h1n_n = _norm(h1n)
            if not any(c and (c in h1n_n or h1n_n in c) for c in cand):
                findings.append(finding("structure", SEVERITY_WARN, "h1_name_mismatch",
                                        "正文 H1 标题与 frontmatter 身份不一致（H1='%s', name='%s'%s）"
                                        % (h1n, nm, (" / displayName='%s'" % disp) if disp else ""),
                                        suggestion="统一 H1 与 name/displayName"))
    else:
        # 无 frontmatter：退化为检查 inline version / description，避免对已验证技能误报
        if not VERSION_RE.search(doc):
            findings.append(finding("structure", SEVERITY_ERROR, "version_missing",
                                    "SKILL.md 缺少 version 声明（frontmatter 或 inline）",
                                    suggestion="添加 version: x.y.z"))
        else:
            findings.append(finding("structure", SEVERITY_WARN, "no_frontmatter",
                                    "建议使用 YAML frontmatter 声明 name/version/description"))
        if not re.search(r"description", doc, re.I):
            findings.append(finding("structure", SEVERITY_WARN, "desc_missing",
                                    "未检测到 description 字段"))

    # 正文行数
    lines = doc.splitlines()
    if len(lines) > 500:
        findings.append(finding("structure", SEVERITY_WARN, "too_long",
                                "正文 %d 行，超过 500 行建议拆分" % len(lines)))

    # 加载式引用完整性（references/ 与 scripts/）
    for m in re.finditer(r"(?:references|scripts)/[A-Za-z0-9_.\-/]+\.(?:md|py|js|jsx|ts|tsx|vue|go|rs|java|c|cpp|h|rb|php|swift|kt|lua|json|sh|ps1)", doc):
        ref = m.group(0)
        if not os.path.exists(os.path.join(skill_dir, ref)):
            findings.append(finding("structure", SEVERITY_ERROR, "broken_ref",
                                    "文档里引用加载的脚本或文件 %s 不存在（请检查引用路径是否写错）" % ref, file="SKILL.md",
                                    suggestion="修正路径或补充文件"))

    # 硬编码用户绝对路径（上下文感知，降低文档示例误报）
    # 仅对「真实指令行」报：跳过代码围栏、表格行、引用块、以及含豁免/示例性语言的描述行，
    # 这些上下文里的路径多为规则说明 / 命令行示例，并非要求用户照做的真实绝对路径。
    _in_fence = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            _in_fence = not _in_fence
            continue
        if _in_fence:
            continue
        if "|" in line or line.lstrip().startswith(">"):
            continue
        if re.search(r"豁免|示例|example|如[：:]|比如|例如|说明|文档|描述", line, re.I):
            continue
        for m in re.finditer(r"[A-Za-z]:\\Users\\[^\s`]+|/home/[^\s`]+|/Users/[^\s`]+", line):
            findings.append(finding("structure", SEVERITY_WARN, "hardcoded_path",
                                    "文档含硬编码用户绝对路径: %s" % m.group(0), file="SKILL.md", line=i,
                                    suggestion="改用相对路径或 <用户目录> 占位"))

    # TODO / 占位 / 历史记录（跳过表格行，避免把"描述检查器本身"的单元格误判为真实标记）
    for i, line in enumerate(lines, 1):
        if "|" in line:
            continue
        if re.search(r"\b(TODO|FIXME|XXX)\b", line):
            findings.append(finding("structure", SEVERITY_WARN, "todo_marker",
                                    "含 TODO/FIXME 标记", file="SKILL.md", line=i))
        if re.search(r"占位|伪代码|待补充|示例待填|修改于|更新于\s*\d{4}", line):
            findings.append(finding("structure", SEVERITY_INFO, "placeholder",
                                    "疑似占位/历史记录文本", file="SKILL.md", line=i))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：security（安全红线静态子集）
# --------------------------------------------------------------------------- #
# 自注册
CHECKERS["structure"] = check_structure

