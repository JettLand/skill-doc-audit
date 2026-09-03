# model.py (拆分自 audit_docs.py)
from auditlib.core import *
from auditlib.core import _parse_frontmatter_list, _normalize_target_agent

# ---- 跨 Agent 格式检测与统一模型（Phase 5 归一化内核）----

# 各格式的特征 frontmatter 键（按特征推断，不硬锁枚举——遵循 v1.11.0 自由列表原则，防格式漂移）
_FMT_WB_ONLY = {"slug", "displayname", "target_platform", "target_agent", "agent_created"}
_FMT_CC_ONLY = {"argument-hint", "model", "context", "agent", "user-invocable",
                "disable-model-invocation", "hooks", "paths"}
_FMT_STD = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def _fm_keys(fm_text):
    """从 frontmatter 文本提取小写键名集合（兼容 `key:` 与块列表首行）。"""
    if not fm_text:
        return set()
    return {m.group(1).lower() for m in re.finditer(r"^([A-Za-z0-9_\-]+):", fm_text, re.M)}


def _fm_scalar(fm_text, key):
    """取 frontmatter 标量值（去引号）。找不到返回空串。"""
    if not fm_text:
        return ""
    m = re.search(r"^%s:\s*(.+)$" % re.escape(key), fm_text, re.M)
    if not m:
        return ""
    return m.group(1).strip().strip('"').strip("'")


def detect_format(fm_text, filename=""):
    """推断技能格式（归一化枚举）。
    - .mdc 且含 description/alwaysApply/globs → cursor-mdc（Cursor 规则文件）
    - SKILL.md 含 WorkBuddy 专有键 → workbuddy
    - SKILL.md 含 Claude Code 专有扩展键 → claude-code
    - 含 compatibility 或仅开放标准键 → agentskills（Cursor Plugin 的 SKILL.md 同此处理）
    - 其它 → generic
    判定「按特征推断」而非按枚举硬锁，避免生态演进导致漏判（同 v1.11.0 自由列表原则）。
    """
    keys = _fm_keys(fm_text)
    if filename.endswith(".mdc"):
        return "cursor-mdc" if (keys & {"description", "alwaysapply", "globs"}) else "generic"
    if keys & _FMT_WB_ONLY:
        return "workbuddy"
    if keys & _FMT_CC_ONLY:
        return "claude-code"
    if "compatibility" in keys:
        return "agentskills"
    if keys and keys <= (_FMT_STD | {"version", "author", "tags"}):
        return "agentskills"
    return "generic"


class SkillModel:
    """跨格式统一技能模型（Phase 5 归一化内核），供检查器与 Phase 6 矩阵 / Phase 7 转译消费。"""
    def __init__(self, name="", description="", fmt="generic", platform="generic",
                 target_platform="cross-platform", target_agent=None, tools=None,
                 license="", version="", extra=None):
        self.name = name
        self.description = description
        self.fmt = fmt
        self.platform = platform
        self.target_platform = target_platform
        self.target_agent = target_agent or set()
        self.tools = tools or set()
        self.license = license
        self.version = version
        self.extra = extra or {}


# ---- Phase 6：跨格式可移植性矩阵（字段级能力映射）----
# 以开放标准 agentskills 为枢纽：Claude Code / Cursor Plugin 共用 SKILL.md 格式。
# 各格式原生支持的字段集合（决定某 feature 在目标端是保留/降级/丢失）。
FMT_CAPS = {
    "workbuddy":     {"name", "description", "license", "version", "allowed-tools",
                      "target_agent", "slug", "displayname", "metadata"},
    "agentskills":   {"name", "description", "license", "allowed-tools",
                      "compatibility", "metadata"},
    "claude-code":   {"name", "description", "license", "allowed-tools",
                      "model", "context", "agent", "hooks", "argument-hint", "metadata"},
    "cursor-plugin": {"name", "description", "license", "allowed-tools",
                      "compatibility", "metadata"},   # = agentskills 兼容
    "cursor-mdc":    {"description", "globs", "alwaysApply"},   # Cursor 规则文件：无 name/allowed-tools
    "generic":       {"name", "description"},
}
# 跨格式字段等价映射（降级而非丢失）：feature -> 目标端对应字段名
EQUIV = {
    "target_agent": "compatibility",
    "slug": "name",
    "displayname": "name",
}
# 候选目标格式（用于 --report 全矩阵展示）
FORMAT_TARGETS = ["workbuddy", "agentskills", "claude-code", "cursor-plugin", "cursor-mdc", "generic"]
# Agent 名 -> 规范格式（target_agent 自由列表元素映射为矩阵目标）
AGENT_TO_FMT = {
    "workbuddy": "workbuddy",
    "claude-code": "claude-code",
    "cursor": "cursor-plugin",     # Cursor Plugin 的 SKILL.md 形式（agentskills 兼容）
    "codex": "agentskills",
    "copilot": "agentskills",
    "cline": "agentskills",
    "generic": "generic",
}


def _model_features(model):
    """从 SkillModel 提取该技能实际填充的字段集合（供矩阵消费）。"""
    f = set()
    if model.name:
        f.add("name")
    if model.description:
        f.add("description")
    if model.license:
        f.add("license")
    if model.version:
        f.add("version")
    if model.tools:
        f.add("allowed-tools")
    if model.target_agent:
        f.add("target_agent")
    for k in ("slug", "displayname", "metadata", "globs", "alwaysapply",
              "model", "context", "agent", "hooks", "argument-hint"):
        if k in model.extra:
            f.add(k)
    return f


def build_portability_matrix(model):
    """返回跨格式可移植性矩阵行列表：{feature, target, status, note}。
    status: preserved(保留) / degraded(降级，需转译) / lost(丢失)。
    """
    feats = _model_features(model)
    rows = []
    for tgt in FORMAT_TARGETS:
        if tgt == model.fmt:
            continue
        caps = FMT_CAPS.get(tgt, FMT_CAPS["generic"])
        for feat in sorted(feats):
            if feat in caps:
                status, note = "preserved", ""
            elif feat in EQUIV and EQUIV[feat] in caps:
                status, note = "degraded", "%s 在 %s 中以 %s 表达（需转译）" % (feat, tgt, EQUIV[feat])
            else:
                status, note = "lost", "%s 在 %s 无对应字段，将丢失" % (feat, tgt)
            rows.append({"feature": feat, "target": tgt, "status": status, "note": note})
    return rows


def analyze_skill(skill_dir, enabled, args=None, do_backup=False, backup_limit=BACKUP_LIMIT,
                  dev_docs=None, exclude=None, dev_audit=False):
    doc_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(doc_path):
        return {"skill": skill_dir, "error": "no SKILL.md", "findings": []}

    with open(doc_path, encoding="utf-8") as fh:
        doc = fh.read()
    scripts_dir = os.path.join(skill_dir, "scripts")
    code, skipped_code = collect_code(skill_dir, exclude=exclude)
    blob = "\n".join(code.values())

    # 文档扫描集（doc / doc-llm 消费）：
    #  - 默认即纳入 references/*.md：它们是技能契约的一部分，断链是真实问题，且应进入
    #    doc-llm 语义 dossier 供 agent 比对；A2-A5/C/B 仅 SKILL.md（能力目录口径）自动跳过，
    #    避免 README/CHANGELOG 类叙述噪音。A1 死路径(DEAD_PATH, ERROR)仅 SKILL.md 生效，
    #    因 references 为叙述性内容、常含示例路径，套 ERROR 会误报，故只报 EXTERNAL_REF(INFO)。
    #  - 开发者模式（dev_docs 非 None）：在默认基础上**递归扫描技能文件夹内全部 .md 描述性文档**
    #    （README/CHANGELOG/examples/License 等），并额外纳入显式传入的 out-of-tree 文档
    #    （如项目根 README/CHANGELOG）；其仓库相对引用按文件自身目录解析，降低 DEAD_PATH 误报。
    docs = [{"name": "SKILL.md", "content": doc}]
    extra_roots = []
    _seen_doc = {os.path.abspath(doc_path)}   # 已加入文档的绝对路径，去重（防 walk 重复加 SKILL.md/references）

    def _add_doc(abs_path, name=None, extra_root=None):
        ap = os.path.abspath(abs_path)
        if ap in _seen_doc or not os.path.isfile(ap):
            return
        try:
            with open(ap, encoding="utf-8", errors="replace") as _fh:
                _c = _fh.read()
        except Exception:
            return
        _seen_doc.add(ap)
        docs.append({"name": name or os.path.basename(ap), "content": _c})
        if extra_root:
            extra_roots.append(extra_root)

    # 默认扩面：references/*.md（技能自带参考文档，随代码漂移真实存在）
    _refs_dir = os.path.join(skill_dir, "references")
    if os.path.isdir(_refs_dir):
        for _fn in sorted(os.listdir(_refs_dir)):
            if _fn.endswith(".md"):
                _add_doc(os.path.join(_refs_dir, _fn), name="references/%s" % _fn)

    # 开发者模式：递归扫描技能文件夹内全部 .md + 显式 out-of-tree 文档
    if dev_docs is not None:
        for _root, _dirs, _names in os.walk(skill_dir):
            _dirs[:] = [d for d in _dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for _n in _names:
                if not _n.endswith(".md"):
                    continue
                _fp = os.path.join(_root, _n)
                _rel = os.path.relpath(_fp, skill_dir).replace(os.sep, "/")
                _add_doc(_fp, name=_rel)
        for dd in (dev_docs or []):
            _add_doc(dd, extra_root=os.path.dirname(os.path.abspath(dd)))

    # 声明式外部工具名（MCP / 插件工具）：frontmatter 的 allowed-tools / tools 字段，
    # 以及全仓库 .md 中出现的 mcp__*__<name> 标记。这些名称只出现在文档/声明里、不在本地
    # 代码内，UNKNOWN_IDENT 检查应跳过，避免对 Agent / MCP 类技能刷出海量误报。
    declared_tools = set()
    target_agent = set()
    platform = "workbuddy"
    _fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", doc, re.S)
    _fm_text = _fm.group(1) if _fm else ""
    if _fm:
        for _key in ("allowed-tools", "tools"):
            for _tok in _parse_frontmatter_list(_fm_text, _key):
                if not _tok:
                    continue
                declared_tools.add(_tok)
                if "__" in _tok:
                    declared_tools.add(_tok.rsplit("__", 1)[-1])
        # 跨 Agent 目标（target_agent 自由列表；兼容开放标准 compatibility 字段）
        _ta_vals = _parse_frontmatter_list(_fm_text, "target_agent")
        _compat_vals = _parse_frontmatter_list(_fm_text, "compatibility")
        target_agent = _normalize_target_agent(_ta_vals + _compat_vals)
        if not target_agent:
            # 推断：仅当含 WorkBuddy 强特征(mcp__*__ / .workbuddy) 才视为 WorkBuddy（allowed-tools 为跨平台共享键，不可据此推断）
            if "mcp__" in doc or ".workbuddy" in doc or re.search(r"~/.workbuddy", doc):
                target_agent = {"workbuddy"}
        # 平台推断：开放标准(agentskills, 含 compatibility) / workbuddy / generic（开放标准兼容）
        if re.search(r"^compatibility:", _fm_text, re.M):
            platform = "agentskills"
        elif "mcp__" in doc or ".workbuddy" in doc or re.search(r"~/.workbuddy", _fm_text, re.M):
            platform = "workbuddy"
        else:
            platform = "generic"
    for _root, _dirs, _names in os.walk(skill_dir):
        _dirs[:] = [d for d in _dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for _n in _names:
            if not _n.endswith(".md"):
                continue
            _fp = os.path.join(_root, _n)
            try:
                with open(_fp, encoding="utf-8", errors="replace") as _fh:
                    _t = _fh.read()
            except Exception:
                continue
            for _m in re.finditer(r"mcp__[A-Za-z0-9_]+__([A-Za-z0-9_]+)", _t):
                declared_tools.add(_m.group(1))

    # 目标运行平台（portability 检查器用）：frontmatter 的 target_platform 字段。
    # 取值：cross-platform(默认/省略) / windows / linux / macos / 列表如 [windows, linux]。
    target_platform = "cross-platform"
    if _fm:
        _tp = re.search(r"^target_platform:\s*(.+)$", _fm.group(1), re.M)
        if _tp:
            _raw = _tp.group(1).strip()
            if _raw.startswith("[") and _raw.endswith("]"):
                target_platform = [v.strip() for v in _raw[1:-1].split(",") if v.strip()]
            else:
                target_platform = _raw

    # 跨 Agent 格式检测（Phase 5 归一化内核）
    fmt = detect_format(_fm_text, os.path.basename(doc_path))
    _sm_extra = {}
    if _fm:
        for _k in _fm_keys(_fm_text):
            _sm_extra[_k] = _fm_scalar(_fm_text, _k)
    sm = SkillModel(
        name=_fm_scalar(_fm_text, "name") if _fm else "",
        description=_fm_scalar(_fm_text, "description") if _fm else "",
        fmt=fmt,
        platform=platform,
        target_platform=target_platform,
        target_agent=target_agent,
        tools=declared_tools,
        license=_fm_scalar(_fm_text, "license") if _fm else "",
        version=_fm_scalar(_fm_text, "version") if _fm else "",
        extra=_sm_extra,
    )

    backup_path = None
    if do_backup:
        prune_backups(doc_path, backup_limit)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = doc_path + ".bak." + stamp
        shutil.copy2(doc_path, backup_path)

    ctx = {
        "skill_dir": skill_dir,
        "doc": doc,
        "doc_path": doc_path,
        "docs": docs,
        "extra_roots": extra_roots,
        "code": code,
        "blob": blob,
        "scripts_dir": scripts_dir,
        "args": args,
        "declared_tools": declared_tools,
        "target_platform": target_platform,
        "target_agent": target_agent,
        "platform": platform,
        "format": fmt,
        "skill_model": sm,
        # 开发模式自审计（dev_self_audit.py / --dev-docs）专用上下文：
        # exclude=发布面之外的开发期工具（避免死代码孤儿/噪音）；dev_audit=审计 src/ 而非技能目录（抑制 name_mismatch 误报）
        "exclude": set(exclude or set()),
        "dev_audit": dev_audit,
    }
    findings = []
    # 检查器执行回执（v1.25.5：执行回执 + 缺失引用去重）：每个检查器调用结果显式记录身份(#代号) + 状态(OK/FAILED/UNKNOWN)，
    # 直接回答「这个检查器到底有没有真跑过」——杜绝 doc-llm 类「静默落空却显示通过」的隐患。
    #   OK      检查器成功执行（返回其身份代号，作为成功回执）
    #   FAILED  检查器执行中抛异常（已被捕获，未中断其余检查器；异常转成 ERROR 发现，使退出码真实反映）
    #   UNKNOWN 检查器未注册（CHECKERS 中无此键，名称拼写/连字符不一致）——从不静默跳过，转成 ERROR 发现
    checker_runs = []
    for name in enabled:
        ccode = CHECKER_CODES.get(name)
        fn = CHECKERS.get(name)
        if fn is None:
            # 检查器未注册：显式记为 UNKNOWN，绝不静默跳过（这正是 doc-llm 误注册键 bug 的表征）
            checker_runs.append({
                "name": name, "code": ccode, "status": "UNKNOWN",
                "findings": 0,
                "error": "检查器未注册：CHECKERS 中无此键（可能名称/连字符不一致），其检查从未执行",
            })
            findings.append(finding(
                name, SEVERITY_ERROR, "CHECKER_UNKNOWN",
                "检查器 %s 未注册（CHECKERS 中无对应键），其检查从未执行，不能视为通过" % name,
                suggestion="检查 auditlib/checkers/__init__.py 的自注册键与 ALL_CHECKERS 是否一致（连字符/下划线拼写）"))
            continue
        try:
            res = fn(ctx) or []
            findings.extend(res)
            run = {
                "name": name, "code": ccode, "status": "OK",
                "findings": len(res), "error": None,
            }
            # 检查器自报元信息（如 deadcode 精度模式），合并进执行回执，供 JSON 确定性可读
            meta = ctx.pop("_meta", None)
            if meta:
                run.update(meta)
            checker_runs.append(run)
        except Exception as e:  # noqa: BLE001
            # 检查器执行抛异常：显式记为 FAILED，且把异常转成 ERROR 发现，确保运行退出码反映「没跑全」
            checker_runs.append({
                "name": name, "code": ccode, "status": "FAILED",
                "findings": 0, "error": repr(e),
            })
            findings.append(finding(
                name, SEVERITY_ERROR, "CHECKER_ERROR",
                "检查器 %s 执行异常（已被捕获，未中断其余检查器）：%s" % (name, e),
                suggestion="查看完整追踪栈定位异常；该检查器的发现可能不完整"))

    # 缺失引用类 finding 跨检查器 / 同检查器去重（降噪）：同一被引用但不存在的文件，
    # 会被 doc(DEAD_PATH) / structure(broken_ref) / runtime(script_ref_missing) 各报一条，
    # doc 还会对同一裸文件名逐次报 EXTERNAL_REF；按引用路径归并为单条，避免 ERROR 计数虚高。
    findings = dedupe_findings(findings)

    # 稳定性：超大文件防护（避免卡死/拖慢）
    doc_size = os.path.getsize(doc_path)
    if doc_size > MAX_FILE_SIZE:
        findings.append(finding("structure", SEVERITY_WARN, "oversize_doc",
                               "SKILL.md 超过 %d 字节（实际 %d），建议拆分或精简" % (MAX_FILE_SIZE, doc_size),
                               file="SKILL.md",
                               suggestion="文档过大可能影响审计性能"))
    if skipped_code and set(enabled) & {"structure", "security", "runtime", "deps"}:
        findings.append(finding("structure", SEVERITY_WARN, "oversize_file",
                               "以下文件超过 %d 字节已跳过扫描（可能为生成物/大资源）: %s"
                               % (MAX_FILE_SIZE, ", ".join(sorted(skipped_code)[:10])),
                               suggestion="确认是否为应纳入审计的源文件"))

    return {
        "skill": skill_dir,
        "version": (VERSION_RE.search(doc).group(1) if VERSION_RE.search(doc) else None),
        "doc_lines": len(doc.splitlines()),
        "code_files": len(code),
        "backup": backup_path,
        "checkers": enabled,
        "findings": findings,
        "checker_runs": checker_runs,
        "format": fmt,
        "skill_model": sm,
    }


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
