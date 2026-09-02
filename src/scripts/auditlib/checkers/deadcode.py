# checkers/deadcode.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）

def _deadcode_name_of(node):
    """从装饰器/调用节点取出被引用的名字（用于识别注册式调用）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _deadcode_name_of(node.func)
    return ""

def _has_keep(content, lineno):
    """该函数/导入所在行或上一行含 `# keep` 则视为有意保留，跳过告警。"""
    if not lineno:
        return False
    lines = content.splitlines()
    for off in (0, -1):
        idx = lineno - 1 + off
        if 0 <= idx < len(lines) and "keep" in lines[idx].lower():
            return True
    return False

def _vulture_module():
    """尝试导入 vulture；不可用返回 None（不抛异常、不自动安装）。"""
    try:
        import vulture as _v  # noqa: F401
        return _v
    except Exception:
        return None

def _try_install_vulture():
    """vulture 缺失时尝试 pip 安装以满足高精度意图（最长 120s，绝不抛异常）。

    返回安装后的 vulture 模块；任何失败（无网络 / 无权限 / 超时）均返回 None，
    由调用方按「降级」逻辑处理（回退零依赖 ast 并触发 precision_degraded 显著提示）。
    覆盖所有「需要 vulture 但缺失」的路径：显式 --deadcode-mode vulture、交互选 1、
    以及 ask 默认路径的非交互回退与交互超时——唯一不触发安装的是用户显式选择
    ast / skip（用户已显式决定低精度，绝不联网）。
    """
    import subprocess
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "vulture"],
            check=True, timeout=120,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    return _vulture_module()

def _resolve_deadcode_mode(args):
    """决定 deadcode 运行模式与是否「降级」。

    返回 (mode, degraded)：
    - mode: "vulture" | "ast" | "skip"
    - degraded: bool，表示本次是否「未经显式确认」地降低了精度。仅在以下情况为真：
      未装 vulture 且自动安装失败、最终回退 ast——无论来源是显式 --deadcode-mode
      vulture、ask 默认的非交互回退、还是交互超时。调用方（check_deadcode）在
      degraded=True 时发出显著提示（precision_degraded WARN + user_decision），
      使精度下降对自动化评测/调用方可见。

    - 显式 --deadcode-mode vulture：缺失时先尝试自动安装，成功即高精度，失败回退
      ast（degraded=True）；显式 ast / skip 直接用、绝不安装（用户已显式决定，零联网）。
    - 默认 ask：环境已装 vulture 则直接采用高精度 vulture 模式（不重复询问）；
      未装 vulture 时：TTY 交互询问（选 1 会先尝试自动安装；超时 30s / 无输入 →
      也先尝试自动安装）；非 TTY（被管道或 Agent 调用）→ 先尝试自动安装，
      安装失败才回退零依赖 ast 并标记 degraded=True。
    """
    mode = getattr(args, "deadcode_mode", "ask") if args else "ask"
    if mode != "ask":
        if mode == "vulture" and _vulture_module() is None:
            sys.stderr.write("[deadcode] 未检测到 vulture 库，尝试自动安装 vulture……\n")
            if _try_install_vulture() is not None:
                sys.stderr.write("[deadcode] vulture 安装成功，采用高精度模式\n")
                return "vulture", False
            sys.stderr.write("[deadcode] ⚠ 未检测到 vulture 库且自动安装失败，回退零依赖 AST 模式（精度降级）\n")
            return "ast", True
        return mode, False
    # ask 模式：已装 vulture 直接走高精度，避免重复询问
    if _vulture_module() is not None:
        sys.stderr.write("[deadcode] 检测到 vulture 库，自动采用高精度模式（跳过询问）\n")
        return "vulture", False
    if not is_interactive():
        # 非交互（管道/Agent/CI）且未装 vulture：先尝试自动安装（成功即高精度），
        # 安装失败才回退零依赖 ast 并标记 degraded——绝不静默降级（precision_degraded
        # WARN + user_decision 显著反馈）。完全不联网请显式 --deadcode-mode ast。
        sys.stderr.write("[deadcode] 非交互环境未检测到 vulture 库，尝试自动安装 vulture……\n")
        if _try_install_vulture() is not None:
            sys.stderr.write("[deadcode] vulture 安装成功，采用高精度模式\n")
            return "vulture", False
        sys.stderr.write(
            "[deadcode] ⚠ 未检测到 vulture 库且自动安装失败，回退零依赖 AST 模式"
            "（精度较低、易误报）。如需完全不联网，请显式 --deadcode-mode ast。\n"
        )
        return "ast", True
    return _prompt_deadcode_mode()

def _prompt_deadcode_mode():
    """交互询问 deadcode 精度模式；30 秒超时/无输入先尝试自动安装 vulture，失败才默认 ast。

    返回 (mode, degraded)：超时/无输入且安装失败、或交互选 1 但「选了 vulture 且安装失败」
    视为降级（degraded=True），因为并非用户清醒选择的精度；显式选 2（ast）/3（skip）则
    degraded=False 且绝不触发安装。
    """
    key = prompt_choice(
        "[deadcode] 选择死代码检测精度模式：",
        [("1", "vulture 高精度（推荐，需已安装 vulture）"),
         ("2", "零依赖 AST（易误报，无需安装）"),
         ("3", "本次跳过 deadcode")],
        timeout=30)
    if not key:
        # 交互超时/无输入：同样先尝试自动安装（与其它「未显式决定」路径一致），
        # 失败才回退 ast 并标记降级；成功即高精度。
        sys.stderr.write("\n[deadcode] 超时/无输入，尝试自动安装 vulture……\n")
        if _try_install_vulture() is not None:
            sys.stderr.write("[deadcode] vulture 安装成功，采用高精度模式\n")
            return "vulture", False
        sys.stderr.write("[deadcode] ⚠ vulture 自动安装失败，默认零依赖 AST 模式（精度降级）\n")
        return "ast", True
    if key == "1":
        if _vulture_module() is None:
            sys.stderr.write("[deadcode] 未检测到 vulture 库，尝试自动安装 vulture……\n")
            if _try_install_vulture() is not None:
                sys.stderr.write("[deadcode] vulture 安装成功，采用高精度模式\n")
                return "vulture", False
            sys.stderr.write("[deadcode] ⚠ 未检测到 vulture 库且自动安装失败，回退零依赖 AST 模式（精度降级）\n")
            return "ast", True
        return "vulture", False
    if key == "3":
        return "skip", False
    return "ast", False

def check_deadcode(ctx):
    mode, degraded = _resolve_deadcode_mode(ctx.get("args"))
    findings = []
    if degraded:
        # 降级（未装 vulture 且自动安装失败，回退零依赖 ast）→ 显著提示精度下降，
        # 让自动化评测/调用方能够「看见」降级与诱因，而非无提示地以低精度结果蒙混过关。
        # 结构化 user_decision 同步注入，供 build_json 提升为顶层 user_prompts ->
        # agent 据此确定性弹窗，不再依赖 SKILL.md 散文约定（见 report.build_json）。
        findings.append(finding(
            "deadcode", SEVERITY_WARN, "precision_degraded",
            "deadcode 精度降级：vulture 库不可用（未安装且自动安装失败），已回退至零依赖 AST 模式（精度较低、易误报）。",
            suggestion="修复网络/权限后重跑，或确认接受 ast 精度；JSON 输出 user_prompts 已含精度模式决策请求，请 agent 向用户确认后显式重跑。",
            user_decision=user_decision(
                "deadcode",
                "deadcode 精度模式选择（ask 模式、非交互环境无法询问，已降级为 AST）：希望以哪种精度运行？",
                [("1", "安装 vulture 后以 --deadcode-mode vulture 高精度运行（推荐）"),
                 ("2", "零依赖 AST（易误报，无需安装）"),
                 ("3", "跳过 deadcode 检查")],
                default="2",
                rerun_hint="python audit_docs.py --skill <技能目录> --deadcode-mode vulture   # 或 ast / skip",
            ),
        ))
    if mode == "skip":
        return findings
    skill_dir = ctx["skill_dir"]
    doc = ctx["doc"]
    code = ctx["code"]

    # ---- 预扫描：跨文件引用集合 ----
    # 多文件技能里，一个函数常在本文件定义、在他文件被调用。若只按单文件 AST 判定，
    # 会把「跨文件被引用」的符号误报为 unused_def。故先汇总全技能范围被引用的标识符
    # (global_used) 与被 import 的模块名 (imported_modules)，供下方跨文件判定使用。
    global_used = set()
    imported_modules = set()

    def _collect_refs(tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                global_used.add(node.id)
            elif isinstance(node, ast.Attribute):
                global_used.add(node.attr)
            elif isinstance(node, ast.Import):
                for n in node.names:
                    imported_modules.add(n.name.split(".")[0])
                    if n.asname:
                        imported_modules.add(n.asname)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split(".")[0])
                for n in node.names:
                    imported_modules.add(n.name.split(".")[0])
                    if n.asname:
                        imported_modules.add(n.asname)
            elif isinstance(node, ast.Call):
                n = _deadcode_name_of(node.func)
                if n:
                    global_used.add(n)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # 字符串字面量中的标识符也视为潜在引用：覆盖 dispatch 字典按字符串键注册、反射等动态调用
                for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", node.value):
                    global_used.add(tok)

    per_file = []
    for rel, content in code.items():
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue  # 语法错误由 runtime 检查器负责
        _collect_refs(tree)
        used_local = set()
        defined = []
        import_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_local.add(node.id)
            elif isinstance(node, ast.Attribute):
                used_local.add(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.append((node.name, node.lineno))
                for dec in node.decorator_list:  # 装饰器即注册式调用，视为已用
                    n = _deadcode_name_of(dec)
                    if n:
                        used_local.add(n)
            elif isinstance(node, ast.ClassDef):
                defined.append((node.name, node.lineno))
            elif isinstance(node, ast.Import):
                for n in node.names:
                    import_names.append((n.asname or n.name.split(".")[0], node.lineno))
            elif isinstance(node, ast.ImportFrom):
                for n in node.names:
                    import_names.append((n.asname or n.name.split(".")[0], node.lineno))
            elif isinstance(node, ast.Call):
                n = _deadcode_name_of(node.func)
                if n:
                    used_local.add(n)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # 字符串字面量中的标识符也视为潜在引用：覆盖 dispatch 字典按字符串键注册、反射等动态调用
                for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", node.value):
                    used_local.add(tok)
        per_file.append((rel, content, tree, used_local, defined, import_names))

    # ---- A. 代码级：AST 分析 .py（unused_def 跨文件判定） ----
    for rel, content, tree, used_local, defined, import_names in per_file:
        # 未使用导入（INFO）—— 仅按本文件判定；vulture 模式下交由 vulture 检测，避免重复报告
        if mode != "vulture":
            for name, lineno in import_names:
                if name == "*":
                    continue
                if name in used_local or _has_keep(content, lineno):
                    continue
                findings.append(finding("deadcode", SEVERITY_INFO, "unused_import",
                                        "导入但未使用: %s" % name, file=rel, line=lineno,
                                        suggestion="删除未使用的导入，或加 `# keep` 保留"))

        # 未使用定义（WARN）—— 跨文件判定：仅在全技能范围都未引用时才报（消除多文件技能的误报）
        if mode != "vulture":
            for name, lineno in defined:
                if name in global_used or name in ENTRY_HINTS:
                    continue
                if name.startswith("__") and name.endswith("__"):
                    continue  # 魔术方法/特殊名不视为死代码
                if _has_keep(content, lineno):
                    continue
                findings.append(finding("deadcode", SEVERITY_WARN, "unused_def",
                                        "定义了但从未被引用: %s" % name, file=rel, line=lineno,
                                        suggestion="删除死代码，或加 `# keep` 保留（如公开 API/钩子）"))

        # 不可达代码（WARN）：同一代码块中 return/raise 之后紧跟无条件的语句
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or len(body) < 2:
                continue
            for idx in range(len(body) - 1):
                cur = body[idx]
                nxt = body[idx + 1]
                if not isinstance(cur, (ast.Return, ast.Raise)):
                    continue
                if isinstance(nxt, (ast.If, ast.For, ast.AsyncFor, ast.While,
                                    ast.With, ast.AsyncWith, ast.Try,
                                    ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef, ast.Import, ast.ImportFrom)):
                    continue
                ln = getattr(nxt, "lineno", 0)
                if _has_keep(content, ln):
                    continue
                findings.append(finding("deadcode", SEVERITY_WARN, "unreachable",
                                        "不可达代码（return/raise 之后的语句）", file=rel, line=ln,
                                        suggestion="删除不可达分支"))

    # ---- B. 孤儿资源文件（scripts/ 与 references/ 下从未被引用的文件） ----
    all_text = doc + "\n" + "\n".join(code.values())
    for sub in ("scripts", "references"):
        d = os.path.join(skill_dir, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            fp = os.path.join(d, fn)
            if not os.path.isfile(fp):
                continue
            if fn in ("__init__.py",):
                continue
            if fn in ctx.get("exclude", set()):
                # 开发期工具（如 sync_deploy.py / dev_self_audit.py）不属于发布面，排除避免误报孤儿资源
                continue
            base = fn
            relref = "%s/%s" % (sub, fn)
            mod_name = os.path.splitext(fn)[0]
            # 被文档/代码按文件名或相对路径引用，或被其他 .py 以模块名 import（保守：避免把被导入模块误标为孤儿）
            if base in all_text or relref in all_text or mod_name in imported_modules:
                continue
            findings.append(finding("deadcode", SEVERITY_WARN, "orphan_asset",
                                    "资源文件从未被引用/加载: %s" % relref, file=relref,
                                    suggestion="删除无用文件，或在 SKILL.md/代码中引用"))

    # ---- 可选：vulture 高精度死代码（仅 vulture 模式运行） ----
    if mode == "vulture":
        _v = _vulture_module()
        if _v is not None:
            try:
                py_files = [os.path.join(skill_dir, r) for r in code if r.endswith(".py")]
                if py_files:
                    v = _v.Vulture()
                    v.scavenge(py_files)
                    # 兼容 vulture 2.x（get_unused_code / typ / first_lineno）
                    # 与旧版（get_unused_code_items / typename / lineno）
                    if hasattr(v, "get_unused_code"):
                        items = v.get_unused_code()
                    elif hasattr(v, "get_unused_code_items"):
                        items = v.get_unused_code_items()
                    else:
                        items = []
                    for item in items:
                        typ = getattr(item, "typ", None) or getattr(item, "typename", None) or ""
                        line = getattr(item, "first_lineno", None) or getattr(item, "lineno", None)
                        # 与 AST 分支一致：定义所在行或上一行含 `# keep` 视为有意保留，跳过
                        if item.filename:
                            try:
                                with open(item.filename, encoding="utf-8", errors="ignore") as _fh:
                                    _src = _fh.read()
                                if _has_keep(_src, line):
                                    continue
                            except Exception:
                                pass
                        msg = ("vulture 检出死代码: %s (%s)" % (item.name, typ)) if typ else ("vulture 检出死代码: %s" % item.name)
                        findings.append(finding("deadcode", SEVERITY_WARN, "vulture",
                                                msg,
                                                file=os.path.relpath(item.filename, skill_dir) if item.filename else None,
                                                line=line,
                                                suggestion="确认后删除或加白名单"))
            except Exception as exc:
                sys.stderr.write("[deadcode] vulture 分析异常，已跳过：%s\n" % exc)

    return findings

# --------------------------------------------------------------------------- #
# 检查器：portability（跨平台可移植性，零依赖纯静态分析）
#   按 frontmatter 的 target_platform 字段豁免：声明平台「覆盖」该发现会崩的平台才抑制。
#   规则：fire iff (声明平台 ∩ breaks_on) 非空；cross-platform(默认/省略) = 全平台 → 始终 fire。
#   全部 WARN/INFO，绝不 ERROR（可移植性是程度问题，结论需人判；同 deadcode 提示项）。
# --------------------------------------------------------------------------- #

# 自注册
CHECKERS["deadcode"] = check_deadcode

