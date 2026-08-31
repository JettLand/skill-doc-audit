# checkers/deps.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）
from auditlib.core import _normalize_target_platform, PLAT_ALL, ENTRY_HINTS

def check_deps(ctx):
    findings = []
    doc = ctx["doc"]
    code = ctx["code"]

    # 1) 探测代码中对外部二进制 / CLI 的显式调用（仅看子进程/系统调用语义的行）
    EXTERNAL_CLI = {"git", "npm", "npx", "pip", "pip3", "ffmpeg", "ffprobe", "curl", "wget", "docker", "kubectl", "aws", "az", "gcloud", "powershell", "pwsh", "node", "node.exe", "bun", "deno", "go", "cargo", "rustc", "java", "javac", "sqlite3", "tmux", "ssh", "scp", "rsync", "gsutil", "terraform"}
    invoked = set()
    for rel, content in code.items():
        for line in content.splitlines():
            if any(tok in line for tok in SCAN_SKIP_TOKENS):
                continue
            if "EXTERNAL_CLI" in line:  # 跳过本检查器自身的检测常量定义/迭代行
                continue
            if not re.search(r"subprocess|os\.system|Popen|shell=True|os\.popen", line):
                continue
            for cli in EXTERNAL_CLI:
                if re.search(r"(?<![A-Za-z0-9_\-])" + re.escape(cli) + r"(?![A-Za-z0-9_\-])", line):
                    invoked.add(cli)

    for cli in sorted(invoked):
        if cli.lower() not in doc.lower():
            findings.append(finding("deps", SEVERITY_WARN, "undeclared_cli",
                                    "代码调用外部 CLI 但文档未声明依赖: %s" % cli,
                                    suggestion="在 SKILL.md 补充依赖声明与安装/降级方式"))

    # 2) 平台相关性：含 Windows 专属 API 但未声明运行平台
    WIN_MARKERS = ("win32api", "ctypes.windll", "winreg", "HKEY_", "ShellExecute", "os.startfile", "windll", ".exe", "GetShortcut")
    win_hits = set()
    for rel, content in code.items():
        for line in content.splitlines():
            if any(tok in line for tok in SCAN_SKIP_TOKENS):
                continue
            if "WIN_MARKERS" in line or "EXTERNAL_CLI" in line:  # 跳过检测常量定义/迭代行
                continue
            for mk in WIN_MARKERS:
                if mk in line:
                    win_hits.add(mk)
    if win_hits:
        _declared_plat = _normalize_target_platform(ctx.get("target_platform", "cross-platform"))
        if _declared_plat != set(PLAT_ALL):
            pass  # 已显式声明运行平台（非跨平台默认）→ 结构化字段即是声明，抑制散文扫描
        elif not re.search(r"windows|仅.*windows|平台.*windows|platform", doc, re.I):
            findings.append(finding("deps", SEVERITY_INFO, "platform_undeclared",
                                    "代码含 Windows 专属 API（%s 等），建议声明运行平台" %
                                    ", ".join(sorted(win_hits)[:5]),
                                    suggestion="在文档注明「仅支持 Windows」或补充平台元信息（SKILL.md 的 target_platform 字段）"))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：deadcode（死代码检测；运行前按 --deadcode-mode 询问精度模式）
#   零依赖：基于 ast 静态分析 .py 的未使用定义/导入、不可达代码；
#   孤儿资源：scripts/ 与 references/ 下从未被引用的文件；
#   可选增强：环境装了 vulture 则额外跑高精度死代码（未装静默跳过）。
#   全部 WARN/INFO，绝不 ERROR——死代码结论需人判（同 structure/security 提示项）。
# --------------------------------------------------------------------------- #
# 常见入口名启发：这些名字即使没被显式调用（如作为回调/钩子/公开 API 注册）也视为已用，避免误报。




# 自注册
CHECKERS["deps"] = check_deps

