# checkers/examples.py (v1.26.0 新增：泛用版「文档示例」检查器)
"""泛用版 examples 检查器——校验**任意技能**文档里写出的命令示例是否站得住脚。

路线图定位：本检查器即 DEVELOPMENT / 设计文档中长期挂名的「泛用版 examples 检查器」
（与只服务本技能自身的 `self_validate.py` 不同类——后者是维护者自校工具，
本检查器是审计**目标技能**的插件式检查器，进 `CHECKERS` 与 `--all-checks`）。

## 三档能力（默认 ask：交互询问是否沙箱试运行，非交互/超时回退 static）
- **ask（默认）**：交互询问是否沙箱试运行；30 秒超时或本地非交互一律回退 static 并 INFO 标注降级（零执行 / 零网络 / 零 token 不变）。
  检查示例命令引用的文件是否存在、参数是否在脚本中有声明、外部 CLI 是否在文档声明、
  是否含危险/不可逆命令。
- **ask**：交互终端弹菜单询问是否允许沙箱试运行；30 秒超时 / 非交互环境一律回退 static，
  并发出 INFO 显式标注「已降级」（绝不静默替用户决定）。
- **run**：允许执行，但**仍受沙箱白名单约束**——只跑白名单解释器 + 技能内脚本，
  且只对**作者显式标注了期望**的示例块执行（见下方标注语法）。
- **off**：本次不运行。

## 安全红线（不可协商）
**绝不执行文档里的任意 shell**。即使 `run` 模式也只执行同时满足以下全部条件的命令：
① 首 token 为白名单解释器（python/python3/py/node）；② 参数无 shell 元字符
（; | & > < $ ` ( ) 等，含重定向与管道）；③ 目标脚本位于被审计技能目录内；
④ 脚本扩展名在白名单内；⑤ 该示例块由作者显式标注了期望；⑥ 受超时与条数上限约束。
不满足即跳过并 INFO 说明原因，绝不"尽力执行"。

## 示例标注语法（作者可选，供 run 模式比对）
    ```bash {example expected-exit=0 expected-stdout="OK"}
    python scripts/foo.py --dry-run
    ```
支持键：`expected-exit`（退出码）、`expected-stdout`（标准输出需包含的片段）、
`expected-stderr`。未标注的示例在任何模式下都**只做静态检查、不执行**。
"""
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）
import os, re, ast, threading, subprocess, sys  # 显式标准库（不依赖核心包 * 导入，避免任何环境差异）
import shlex

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
# 命令型围栏语言标注（白名单：只从这些块提取命令，避免把 JSON/输出块当命令）
CMD_LANGS = {"bash", "sh", "shell", "shell-session", "zsh", "console", "terminal",
             "powershell", "pwsh", "ps1", "bat", "cmd", "python", "py",
             "node", "javascript", "js", ""}
# 明确是输出/数据而非命令的标注（即便语言未列入 CMD_LANGS 也据此排除）
NON_CMD_LANGS = {"json", "yaml", "yml", "toml", "ini", "xml", "csv", "tsv",
                 "text", "txt", "output", "diff", "http", "markdown", "md",
                 "html", "css", "sql", "log", "tree", "properties"}

# 外部 CLI（与 deps 检查器同口径）：示例中出现但文档未声明 → INFO 提示
EXAMPLES_EXTERNAL_CLI = {"npm", "npx", "pnpm", "yarn", "pip", "pip3", "git", "curl",
                         "wget", "docker", "kubectl", "aws", "az", "gcloud", "ffmpeg",
                         "ffprobe", "sqlite3", "jq", "go", "cargo", "java", "mvn",
                         "gradle", "terraform", "ssh", "scp", "rsync", "make", "cmake"}

# 危险/不可逆命令模式：(正则, 严重级, 说明)
DANGEROUS_PATTERNS = [
    (r"\brm\s+-rf\s+(/|~|\*|/\*|/root|/home)\b", SEVERITY_ERROR, "递归删除根目录/家目录/通配（不可逆且范围失控）"),
    (r":\s*\(\s*\)\s*\{.*\|.*&\s*\}", SEVERITY_ERROR, "fork 炸弹（瞬间耗尽系统资源）"),
    (r"\bmkfs(\.[a-z0-9]+)?\b", SEVERITY_ERROR, "格式化文件系统（数据全毁）"),
    (r"\bdd\s+if=[^\s]+\s+of=/dev/", SEVERITY_ERROR, "dd 直接写入块设备（覆盖磁盘）"),
    (r">\s*/dev/(sd|nvme|hd)", SEVERITY_ERROR, "输出重定向到块设备（覆盖磁盘）"),
    (r"curl[^\n]*\|\s*(sudo\s+)?(ba|z|k)?sh\b", SEVERITY_ERROR, "远端内容直喂 shell（等同执行任意代码）"),
    (r"wget[^\n]*\|\s*(sudo\s+)?(ba|z|k)?sh\b", SEVERITY_ERROR, "远端内容直喂 shell（等同执行任意代码）"),
    (r"\bsudo\s+rm\b", SEVERITY_ERROR, "提权删除（误伤系统文件且不可恢复）"),
    (r"\brm\s+-rf\s+\S+", SEVERITY_WARN, "递归删除（照抄易误删，建议加确认或限定路径）"),
    (r"\bgit\s+push\s+(-f|--force)\b", SEVERITY_WARN, "强制推送（覆盖远端历史，协作场景高危）"),
    (r"\bgit\s+clean\s+-[a-z]*f", SEVERITY_WARN, "强制清理未跟踪文件（丢失未提交内容）"),
    (r"\bchmod\s+(-R\s+)?777\b", SEVERITY_WARN, "开放全员可写权限（安全面扩大）"),
    (r"\bsudo\b", SEVERITY_WARN, "提权执行（示例被照抄时风险不可控）"),
]

# 沙箱：允许执行的解释器与其可执行的脚本扩展名
SANDBOX_INTERPRETERS = {"python", "python3", "python.exe", "python3.exe", "py", "node", "node.exe"}
SANDBOX_SCRIPT_EXT = (".py", ".js", ".mjs")
# 参数中出现的任一字符即判定为「含 shell 元字符」→ 拒绝执行（防注入/重定向/管道）
SHELL_METACHARS = set(";|&<>$()`\n\r")

# --------------------------------------------------------------------------- #
# 围栏与命令解析
# --------------------------------------------------------------------------- #
_FENCE_RE = re.compile(
    r"(?m)^[ \t]{0,3}```([^\n`]*)[ \t]*\r?\n(.*?)(?:^[ \t]{0,3}```[ \t]*$|\Z)",
    re.S)


def _iter_fences(text):
    """产出 (lang, info, body, line)：line 为围栏起始行号（1 基）。"""
    for m in _FENCE_RE.finditer(text):
        info = (m.group(1) or "").strip()
        lang = info.split()[0].lower() if info.split() else ""
        line = text.count("\n", 0, m.start()) + 1
        yield lang, info, m.group(2), line


def _looks_like_command(s):
    """启发式判定一行是否为「命令行」而非输出/数据。宁放过、不误判。"""
    if not s or len(s) > 400:
        return False
    if s.startswith(("#", "//", "<!--", "...", "->", "→")):
        return False
    parts = s.split()
    if not parts:
        return False
    first = parts[0]
    if not re.match(r"^[\w./\\~$@:+-]+$", first):
        return False
    if first.endswith(("{", "[", "(", ",")):
        return False
    # 纯赋值（环境变量）不是命令
    if len(parts) == 1 and "=" in first and not first.startswith(("./", "/", "~")):
        return False
    return True


def _commands_from_block(body, base_line):
    """从围栏正文提取命令行。返回 [(cmd, line)]，已处理续行与 console 提示符。"""
    out = []
    lines = body.splitlines()
    cur, cur_line = None, 0
    for i, raw in enumerate(lines):
        s = raw.strip()
        if cur is None:
            if not s or s.startswith("#"):
                continue
            s = re.sub(r"^(?:\$|>|PS>|>>>)\s+", "", s)
            if not _looks_like_command(s):
                continue
            cur, cur_line = s, i
        else:
            # 续行：仅当上一行以 \ 结束时才拼接
            cur = cur.rstrip()
            if not cur.endswith("\\"):
                if s:
                    out.append((cur, base_line + cur_line))
                cur, cur_line = s, i
            else:
                cur = cur[:-1] + " " + s
                continue
        if cur.rstrip().endswith("\\"):
            continue
        if cur and cur.strip():
            out.append((cur.strip(), base_line + cur_line))
            cur = None
    if cur and cur.strip():
        out.append((cur.strip(), base_line + cur_line))
    return out


def _tokenize(cmd):
    """命令行 → token 列表。兼容反斜杠路径（Windows）导致的 shlex 失败。"""
    try:
        return shlex.split(cmd, posix=True)
    except Exception:
        try:
            return shlex.split(cmd, posix=False)
        except Exception:
            return cmd.split()


def _parse_annotation(info):
    """解析围栏标注 `{example expected-exit=0 expected-stdout="OK"}`。

    返回 (is_annotated, {key: value})。非示例标注返回 (False, {})。
    """
    m = re.search(r"\{([^{}]*)\}", info or "")
    if not m:
        return False, {}
    inner = m.group(1).strip()
    if not re.match(r"^(example|expected)\b", inner):
        return False, {}
    inner = re.sub(r"^example\b", "", inner).strip()
    spec = {}
    try:
        for tok in shlex.split(inner):
            if "=" in tok:
                k, v = tok.split("=", 1)
                spec[k.strip()] = v.strip()
    except Exception:
        pass
    return True, spec


# --------------------------------------------------------------------------- #
# 脚本参数表静态解析（argparse AST + 单层跟随导入 + 字面量兜底）
# --------------------------------------------------------------------------- #
def _add_argument_flags(src):
    """AST 解析源码中所有 `*.add_argument("--x", ...)` 的显式声明参数。"""
    flags = set()
    try:
        tree = ast.parse(src)
    except Exception:
        return flags
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "add_argument"):
            continue
        for a in node.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                    and a.value.startswith("--"):
                flags.add(a.value)
    return flags


def _imported_modules(src):
    """源码中 import 的模块名（用于单层跟随解析参数表）。"""
    mods = []
    try:
        tree = ast.parse(src)
    except Exception:
        return mods
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                mods.append(a.name)
    return mods


def _module_path_for_import(skill_dir, script_dir, module):
    """模块名 → 技能内的文件路径；找不到返回 None（不跨出技能目录，防越界读）。"""
    if not module:
        return None
    cand = module.replace(".", os.sep)
    bases = [script_dir, os.path.join(skill_dir, "scripts"), skill_dir,
             os.path.dirname(script_dir)]
    for base in bases:
        for rel in (cand + ".py", os.path.join(cand, "__init__.py")):
            p = os.path.join(base, rel)
            if os.path.isfile(p):
                return p
    return None


def _declared_flags(script_path, skill_dir):
    """返回 (declared, strict)。

    declared：脚本（或其单层导入模块）中可静态确定的参数集合；空集表示
    「无法静态确定参数表」——此时调用方应跳过参数校验（不猜、不误报）。
    strict：True 表示来自显式 add_argument（可严格比对）；False 表示来自
    字面量兜底（宽松，仅作证据存在性判定）。
    """
    try:
        with open(script_path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except Exception:
        return set(), False
    script_dir = os.path.dirname(script_path)
    declared = _add_argument_flags(src)
    strict = bool(declared)
    # 薄入口（如 audit_docs.py 委托给 auditlib.cli）：参数表在被导入模块里 → 单层跟随
    if not strict:
        for mod in _imported_modules(src)[:8]:
            p = _module_path_for_import(skill_dir, script_dir, mod)
            if not p or os.path.abspath(p) == os.path.abspath(script_path):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    sub = fh.read()
            except Exception:
                continue
            declared |= _add_argument_flags(sub)
            if declared:
                strict = True
                break
    if not declared:
        # 字面量兜底：手写参数解析（如 `"--verbose" in sys.argv`）也算证据
        declared = set(m.group(0) for m in re.finditer(r"--[a-z][a-z0-9-]{2,}", src))
    return declared, strict


# --------------------------------------------------------------------------- #
# 模式解析（static / ask / run / off）
# --------------------------------------------------------------------------- #
def _resolve_examples_mode(args):
    """决定 examples 模式与是否「非交互降级 / 授权缺失阻断」。

    返回 (mode, degraded, reason)，与 _resolve_doc_llm_mode 同构：
    - mode: "static" | "run" | "off"
    - degraded: bool，本次是否因「非交互环境未经用户确认」而停留在静态档（未沙箱试运行）
    - reason: str|None，降级/阻断原因（供 check_examples 发结构化 finding，让 agent 可读到并转交用户）

    设计原则（v1.27.13）：把「是否执行技能内脚本」这一安全决策强制交还用户，
    不依赖 SKILL.md 散文约定（agent 可能读漏），改由代码 consent 闸门自执行：
    - ask 默认：非交互环境直接降级 static 并发出 user_prompts（结构化、机读），由 agent 转交用户；
    - 显式 run/static/off：交互终端（真人即用户）可直接生效；非交互（agent）环境必须携带
      --examples-consent 授权令牌，否则判定为 agent 静默替用户决定档位，返回 reason="consent_missing"
      交由 check_examples 发阻断级 finding（examples_consent_missing），拒绝执行。
    """
    mode = getattr(args, "examples_mode", "ask") if args else "ask"
    if mode not in EXAMPLES_MODES:
        mode = "ask"
    if mode == "ask":
        if not is_interactive():
            sys.stderr.write(
                "[examples] 非交互（自动化）环境，未获授权执行示例命令，"
                "采用纯静态检查（如需试运行请由 agent 转交用户决策后显式重跑）。\n")
            return "static", True, "ask 模式处于非交互（自动化）环境，无法向用户询问，已回退默认（纯静态）模式"
        return _prompt_examples_mode()
    # 显式 run/static/off：交互终端（真人即用户）或已携 --examples-consent 授权令牌方可行
    consent = getattr(args, "examples_consent", False)
    if is_interactive() or consent:
        return mode, False, None
    # agent 在非交互环境显式指定档位却无用户授权令牌 → 阻断（视为静默替用户决定）
    return mode, False, "consent_missing"


def _prompt_examples_mode():
    """交互询问是否允许沙箱试运行；30 秒超时默认 static（最保守）。"""
    sys.stderr.write(
        "\n[examples] 是否允许在受限沙箱（白名单软隔离）内试运行带 expected 标注的示例命令？\n"
        "  1) 仅静态检查（默认，零执行 / 零网络 / 零 token）\n"
        "  2) 受限沙箱试运行（仅白名单解释器 + 技能内脚本 + 超时保护，绝不执行任意 shell / 外部命令）\n"
        "  ⚠ 风险提示：沙箱非操作系统级容器，脚本仍以当前用户权限运行，可能读写本地文件或发起网络访问；请仅对您信任的技能选择此档。\n"
        "请输入 1/2（30 秒内未选则默认 1 静态）：")
    sys.stderr.flush()
    buf = {}

    def _read():
        try:
            buf["v"] = sys.stdin.readline().strip()
        except Exception:
            buf["v"] = ""
    th = threading.Thread(target=_read, daemon=True)
    th.start()
    th.join(30)
    choice = buf.get("v", "")
    if choice == "2":
        sys.stderr.write("\n[examples] 已授权受限沙箱试运行。\n")
        return "run", False, None
    if not choice:
        sys.stderr.write("\n[examples] 超时/无输入，采用纯静态检查。\n")
        return "static", True, "超时/无输入，采用纯静态检查"
    return "static", False, None


# --------------------------------------------------------------------------- #
# 沙箱执行（仅 run 模式，仅带标注且过白名单的命令）
# --------------------------------------------------------------------------- #
def _sandbox_reject_reason(argv, skill_dir):
    """命令是否可执行。返回 None 表示允许，否则返回拒绝原因（供 INFO 提示）。"""
    if not argv:
        return "空命令"
    prog = os.path.basename(argv[0]).lower()
    if prog not in SANDBOX_INTERPRETERS:
        return "解释器 %s 不在沙箱白名单（仅 %s）" % (
            argv[0], "/".join(sorted(SANDBOX_INTERPRETERS)))
    for a in argv[1:]:
        if any(ch in SHELL_METACHARS for ch in a):
            return "参数含 shell 元字符（重定向/管道/命令替换一律拒绝）：%s" % a
    script = None
    for a in argv[1:]:
        if a.lower().endswith(SANDBOX_SCRIPT_EXT):
            script = a
            break
    if not script:
        return "未指向白名单脚本（.py/.js/.mjs）"
    sp = os.path.normpath(os.path.join(skill_dir, script))
    try:
        inside = os.path.realpath(sp).startswith(os.path.realpath(skill_dir) + os.sep)
    except Exception:
        inside = False
    if not inside:
        return "脚本路径越出技能目录（拒绝，防读写技能外文件）"
    if not os.path.isfile(sp):
        return "脚本不存在：%s" % script
    return None


def _run_command(argv, skill_dir, timeout):
    """在受限环境执行命令。返回 (rc, out, err, err_kind)。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # 尽力削弱联网能力（不替代真沙箱，仅降低意外外联概率）
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
              "http_proxy", "https_proxy", "all_proxy"):
        env.pop(k, None)
    try:
        p = subprocess.run(argv, cwd=skill_dir, env=env, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.TimeoutExpired:
        return None, "", "", "timeout"
    except Exception as e:  # noqa: BLE001
        return None, "", "", repr(e)
    dec = lambda b: b.decode("utf-8", errors="replace")[:8000]
    return p.returncode, dec(p.stdout), dec(p.stderr), None


def _compare_expectation(spec, rc, out, err):
    """比对执行结果与标注期望。返回差异说明列表（空=符合）。"""
    diffs = []
    if "expected-exit" in spec:
        try:
            want = int(spec["expected-exit"])
        except ValueError:
            want = None
        if want is not None and rc != want:
            diffs.append("退出码期望 %d，实际 %s" % (want, rc))
    if "expected-stdout" in spec and spec["expected-stdout"]:
        needle = spec["expected-stdout"]
        if needle not in out:
            diffs.append("标准输出未包含期望片段：%r" % needle)
    if "expected-stderr" in spec and spec["expected-stderr"]:
        needle = spec["expected-stderr"]
        if needle not in err:
            diffs.append("标准错误未包含期望片段：%r" % needle)
    return diffs


# --------------------------------------------------------------------------- #
# 检查器主体
# --------------------------------------------------------------------------- #
def check_examples(ctx):
    findings = []
    args = ctx.get("args")
    mode, degraded, reason = _resolve_examples_mode(args)
    # 反参告知：无论采用哪种模式（static / run / off），都显式回参，供 human（stderr 行）与
    # agent（checker_runs["examples"].mode）确定性读取，杜绝静默代决（与 deadcode/doc-llm 一致）。
    _MODE_DESC = {
        "static": "纯静态检查（零执行 / 零网络 / 零 token）",
        "run": "受限沙箱试运行（白名单软隔离，绝不执行任意 shell / 外部命令）",
        "off": "关闭（跳过 examples 检查）",
    }
    _mode_desc = _MODE_DESC.get(mode, mode)
    sys.stderr.write("[examples] 已采用 %s 模式：%s\n" % (mode, _mode_desc))
    ctx["_meta"] = {"mode": mode, "mode_desc": _mode_desc}
    if mode == "off":
        return findings
    if reason == "consent_missing":
        # agent 非交互环境显式指定档位却无用户授权令牌 → 阻断（不执行任何示例命令）
        findings.append(finding(
            "examples", SEVERITY_ERROR, "examples_consent_missing",
            "示例执行验证遭拒（examples_consent_missing）：agent 在非交互（自动化）环境下显式指定了 "
            "--examples-mode %s，但未携带用户授权令牌 --examples-consent，判定为 agent 静默替用户决定档位，"
            "已阻断执行、未运行任何示例命令。正确做法二选一：① 不传 --examples-mode（默认 ask → 非交互降级"
            "为纯静态并发出 user_prompts，由 agent 转交用户决策）；② 仅当用户在本次指令中已明确指定某档时，"
            "才以 --examples-mode %s --examples-consent 显式重跑。" % (mode, mode),
            user_decision=user_decision(
                "examples",
                "示例执行验证是否允许受限沙箱试运行？（agent 显式指定 %s 但无用户授权，已阻断）" % mode,
                [("1", "仅静态检查（默认，零执行 / 零网络 / 零 token）"),
                 ("2", "受限沙箱试运行（白名单软隔离，绝不执行任意 shell / 外部命令）")],
                default="1",
                rerun_hint="python audit_docs.py --skill <技能目录> --examples-mode %s --examples-consent" % mode,
            )))
        return findings
    if degraded:
        findings.append(finding(
            "examples", SEVERITY_INFO, "examples_degraded",
            "示例执行验证已降级（examples_degraded）：当前为非交互（agent/自动化）环境、ask 模式"
            "无法向用户弹窗确认，已仅做纯静态检查。是否允许受限沙箱试运行属安全确认，须由用户决定——"
            "请 agent 用提问工具向用户确认（选项：允许沙箱试运行 / 仅静态检查），再按用户选择以显式"
            " --examples-mode run --examples-consent（允许）或 --examples-mode static --examples-consent（拒绝）"
            "重新调用本检查器；切勿静默代用户默认。",
            suggestion="run 模式为白名单软沙箱（非 OS 级隔离），执行的技能内脚本仍以当前用户权限运行，"
                       "可能读写本地文件或发起网络访问；仅对信任的技能选 run。与 doc-llm 的 agent 接手约定一致："
                       "非交互环境的决策须交由用户确认，而非脚本静默替决。",
            user_decision=user_decision(
                "examples",
                "示例执行验证是否允许受限沙箱试运行？（ask 模式、非交互环境无法询问，已降级为纯静态检查）",
                [("1", "仅静态检查（默认，零执行 / 零网络 / 零 token）"),
                 ("2", "受限沙箱试运行（白名单软隔离，绝不执行任意 shell / 外部命令）")],
                default="1",
                rerun_hint="python audit_docs.py --skill <技能目录> --examples-mode run --examples-consent   # 或 static --examples-consent",
            )))

    skill_dir = ctx["skill_dir"]
    scripts_dir = ctx["scripts_dir"]
    extra_roots = ctx.get("extra_roots") or []
    doc_text = ctx.get("doc", "")
    docs = ctx.get("docs") or [{"name": "SKILL.md", "content": doc_text}]
    # 纯文档快照（--source url 只取到 SKILL.md / 无代码文件）时，
    # 无法校验示例目标是否存在——降为 INFO，绝不把"没下载到"误判成"文件不存在"。
    doc_only = not ctx.get("code")
    max_cmd = int(getattr(args, "examples_max_cmd", 12) or 12) if args else 12
    timeout = float(getattr(args, "examples_timeout", 20) or 20) if args else 20

    executed = 0
    annotated_seen = 0
    for d in docs:
        doc = d["content"]
        doc_name = d["name"]
        # 参数校验仅对技能本体 SKILL.md 生效：references / 开发文档常引用开发期工具
        # （如 make_fixtures.py --baseline），其参数表不在发布面代码内，套用会误报。
        # 与 doc 检查器 A2 的「能力目录口径」保持一致。
        core_doc = (doc_name == "SKILL.md")
        seen_targets = set()
        seen_flags = set()
        for lang, info, body, line in _iter_fences(doc):
            if lang in NON_CMD_LANGS:
                continue
            if lang not in CMD_LANGS:
                continue
            annotated, spec = _parse_annotation(info)
            cmds = _commands_from_block(body, line)
            if not cmds:
                continue
            if annotated:
                annotated_seen += 1
                if mode != "run":
                    findings.append(finding(
                        "examples", SEVERITY_INFO, "EXAMPLE_UNVERIFIED",
                        "示例（%s 第 %d 行）标注了期望值，但当前为纯静态模式，未做执行验证"
                        % (doc_name, line),
                        file=doc_name, line=line,
                        suggestion="如需执行验证请显式指定 --examples-mode run（仅白名单解释器 + 技能内脚本 + 超时保护）"))

            for cmd, cline in cmds:
                argv = _tokenize(cmd)
                if not argv:
                    continue
                prog = os.path.basename(argv[0]).lower()

                # --- 1) 危险/不可逆命令（真实照抄风险，所有文档均检） ---
                for pat, sev, why in DANGEROUS_PATTERNS:
                    if re.search(pat, cmd, re.I):
                        findings.append(finding(
                            "examples", sev, "EXAMPLE_DANGEROUS",
                            "文档示例含危险命令（%s）：%s" % (why, cmd[:120]),
                            file=doc_name, line=cline,
                            suggestion="示例会被照抄，建议改为更安全的等价写法并加显式提示"))
                        break

                # --- 2) 示例引用的技能内脚本文件是否存在 ---
                # 仅核验「以脚本扩展名结尾」的引用（.py/.js/.mjs/.ts/.sh/.ps1）：
                # 这才是「照抄命令会直接失败」的真实风险面。仓库引用(owner/repo)、
                # 用户安装路径(~/.workbuddy/...)、输出文件(audit.json)、占位目录(./huge-monorepo)
                # 等无脚本扩展名的 token 一律跳过——避免把示例/说明性路径误判为缺失文件。
                # 通用文件引用（含非脚本扩展名）由 doc 检查器 DEAD_PATH 覆盖，二者互补不重叠。
                for tok in argv:
                    if tok.startswith("-") or "://" in tok:
                        continue
                    m = re.match(r"^[\w.\-~]+(?:[/\\][\w.\-~]+)*"
                                 r"\.(py|js|mjs|ts|sh|ps1)$", tok)
                    if not m:
                        continue
                    ref = tok
                    if ref in seen_targets:
                        continue
                    if resolve_exists(skill_dir, ref, scripts_dir, extra_roots=extra_roots):
                        continue
                    # 形如 foo.bar 的域名/包名（requests.get 之类）不是路径
                    if re.match(r"^[\w.\-]+\.(com|org|net|io|cn|dev|ai)$", ref):
                        continue
                    seen_targets.add(ref)
                    if doc_only:
                        findings.append(finding(
                            "examples", SEVERITY_INFO, "EXAMPLE_TARGET_UNVERIFIABLE",
                            "示例引用的 ` %s ` 无法核验：本次审计为纯文档快照（未取到技能代码）"
                            % ref, file=doc_name, line=cline,
                            suggestion="如需校验示例目标，请审计完整技能目录而非单个 SKILL.md"))
                    else:
                        findings.append(finding(
                            "examples",
                            SEVERITY_ERROR if core_doc else SEVERITY_WARN,
                            "EXAMPLE_TARGET_MISSING",
                            "示例命令引用的文件 `%s` 在技能目录中不存在（照抄将直接失败）" % ref,
                            file=doc_name, line=cline,
                            suggestion="修正示例中的路径，或补齐该文件", ref=ref))

                # --- 3) 参数是否在目标脚本中有声明（仅 SKILL.md） ---
                if core_doc:
                    script_tok = None
                    for a in argv[1:]:
                        if a.lower().endswith((".py", ".js", ".mjs", ".ts")):
                            script_tok = a
                            break
                    used_flags = [a for a in argv if a.startswith("--")]
                    if script_tok and used_flags:
                        spath = os.path.join(skill_dir, script_tok)
                        if not os.path.isfile(spath):
                            spath = os.path.join(scripts_dir, os.path.basename(script_tok))
                        if os.path.isfile(spath):
                            declared, _strict = _declared_flags(spath, skill_dir)
                            if declared:  # 无参数表可确定 → 跳过（不猜、不误报）
                                for fl in used_flags:
                                    key = (script_tok, fl)
                                    if fl in declared or key in seen_flags:
                                        continue
                                    seen_flags.add(key)
                                    findings.append(finding(
                                        "examples", SEVERITY_WARN, "EXAMPLE_FLAG_UNKNOWN",
                                        "示例给 `%s` 传了参数 `%s`，该脚本中未找到对应声明" % (
                                            script_tok, fl),
                                        file=doc_name, line=cline,
                                        suggestion="核实参数名拼写；若脚本确已移除该参数，请同步更新示例"))

                # --- 4) 外部 CLI 是否已声明依赖 ---
                # 仅凭「文档是否含该 token」判断会失效——示例本身就写出该命令，token 必然出现。
                # 故改为：该 CLI 未在本技能**代码**中出现、也未在 frontmatter 声明时才提示，
                # 即「仅出现在文档示例、却非真实依赖」的情形，避免把示例里的命令误判为已声明。
                _blob = ctx.get("blob") or ""
                _declared = ctx.get("declared_tools") or set()
                if prog in EXAMPLES_EXTERNAL_CLI and prog not in _blob and prog not in _declared:
                    findings.append(finding(
                        "examples", SEVERITY_INFO, "EXAMPLE_EXT_CMD",
                        "示例调用了外部命令 `%s`，但该 CLI 未在本技能代码中出现、也未在 frontmatter 声明，可能缺少依赖说明" % prog,
                        file=doc_name, line=cline,
                        suggestion="在文档补充该外部依赖声明与缺失时的降级方式"))

                # --- 5) 沙箱试运行（run 模式 + 带标注 + 过白名单） ---
                if mode == "run" and annotated:
                    if executed >= max_cmd:
                        findings.append(finding(
                            "examples", SEVERITY_INFO, "EXAMPLE_RUN_LIMIT",
                            "已达单技能示例执行上限（%d 条），其余标注示例未执行" % max_cmd,
                            file=doc_name, line=cline,
                            suggestion="如需提高上限请用 --examples-max-cmd"))
                        continue
                    reason = _sandbox_reject_reason(argv, skill_dir)
                    if reason:
                        findings.append(finding(
                            "examples", SEVERITY_INFO, "EXAMPLE_SANDBOX_SKIP",
                            "示例未执行（沙箱拒绝）：%s —— %s" % (reason, cmd[:100]),
                            file=doc_name, line=cline,
                            suggestion="沙箱只执行白名单解释器 + 技能内脚本；这是安全红线，不可放宽"))
                        continue
                    executed += 1
                    rc, out, err, kind = _run_command(argv, skill_dir, timeout)
                    if kind == "timeout":
                        findings.append(finding(
                            "examples", SEVERITY_WARN, "EXAMPLE_RUN_FAIL",
                            "示例执行超时（>%.0fs）：%s" % (timeout, cmd[:100]),
                            file=doc_name, line=cline,
                            suggestion="示例应在数秒内完成；检查是否需要网络或交互输入"))
                        continue
                    if kind is not None:
                        findings.append(finding(
                            "examples", SEVERITY_WARN, "EXAMPLE_RUN_FAIL",
                            "示例执行失败（%s）：%s" % (kind, cmd[:100]),
                            file=doc_name, line=cline,
                            suggestion="在本机复现该示例以定位问题"))
                        continue
                    diffs = _compare_expectation(spec, rc, out, err)
                    if diffs:
                        findings.append(finding(
                            "examples", SEVERITY_WARN, "EXAMPLE_OUTPUT_DRIFT",
                            "示例执行结果与文档标注的期望不符（%s）：%s" % (
                                "；".join(diffs), cmd[:100]),
                            file=doc_name, line=cline,
                            suggestion="更新示例的期望标注或修正脚本行为"))

    if mode == "run" and annotated_seen == 0:
        findings.append(finding(
            "examples", SEVERITY_INFO, "examples_run_noop",
            "已启用沙箱试运行，但文档中没有任何带 `{example ...}` 标注的示例块，本次未执行任何命令。",
            suggestion="标注语法：```bash {example expected-exit=0} —— 未标注的示例只做静态检查"))
    return findings


# 自注册（注册键必须与 ALL_CHECKERS 逐字一致：连字符/下划线拼写漂移曾致 doc-llm 长期静默休眠）
CHECKERS["examples"] = check_examples
