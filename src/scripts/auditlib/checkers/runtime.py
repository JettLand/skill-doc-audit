# checkers/runtime.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）

def check_runtime(ctx):
    import py_compile
    findings = []
    skill_dir = ctx["skill_dir"]
    doc = ctx["doc"]
    code = ctx["code"]
    tmpdir = tempfile.mkdtemp(prefix="audit_pyc_")
    try:
        for rel in code:
            if not rel.endswith(".py"):
                continue
            p = os.path.join(skill_dir, rel)
            if not os.path.isfile(p):
                continue
            cf = os.path.join(tmpdir, os.path.basename(rel) + ".pyc")
            try:
                py_compile.compile(p, cfile=cf, doraise=True)
            except py_compile.PyCompileError as e:
                msg = str(e).strip().splitlines()[-1]
                findings.append(finding("runtime", SEVERITY_ERROR, "py_syntax",
                                        "Python 语法错误: %s — %s" % (rel, msg), file=rel,
                                        suggestion="修正语法"))
            except Exception as e:  # noqa: BLE001
                findings.append(finding("runtime", SEVERITY_WARN, "py_check_fail",
                                        "无法校验 %s: %s" % (rel, e), file=rel))

        # 文档引用的脚本是否存在
        for m in re.finditer(r"(scripts/[A-Za-z0-9_\-]+\.(?:py|js|jsx|ts|tsx|vue|go|rs|java|c|cpp|h|rb|php|swift|kt|lua|sh|ps1))", doc):
            ref = m.group(1)
            if not os.path.exists(os.path.join(skill_dir, ref)):
                findings.append(finding("runtime", SEVERITY_ERROR, "script_ref_missing",
                                        "文档引用的脚本不存在: %s" % ref, file="SKILL.md", ref=ref))

        # 能力预检清单（静态列举，不执行）
        caps = set()
        for rel, content in code.items():
            for line in content.splitlines():
                if any(tok in line for tok in SCAN_SKIP_TOKENS):
                    continue
                if "open(" in line:
                    caps.add(rel + ":文件IO")
                if re.search(r"requests\.|urllib|http[s]?://", line):
                    caps.add(rel + ":网络")
                if re.search(r"subprocess|os\.system|Popen|shell=True", line):
                    caps.add(rel + ":子进程")
                if "eval(" in line or "exec(" in line:
                    caps.add(rel + ":动态执行")
        if caps:
            findings.append(finding("runtime", SEVERITY_INFO, "capability",
                                    "脚本能力预检（静态列举，不执行）: " + " | ".join(sorted(caps))))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return findings


# --------------------------------------------------------------------------- #
# 检查器：deps（依赖与平台声明）
# --------------------------------------------------------------------------- #
# 自注册
CHECKERS["runtime"] = check_runtime

