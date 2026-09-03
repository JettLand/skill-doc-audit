# 测试：屏蔽 vulture 条件下验证 deadcode ask 模式流程（位置无关，从仓库任意子目录均可跑）
import sys, os, io, json, contextlib, subprocess

# ---- 屏蔽 vulture 导入（模拟库不可用/被卸载）----
sys.modules["vulture"] = None  # 任何 `import vulture` 将触发 ImportError

import importlib.util
_HERE = os.path.dirname(os.path.abspath(__file__))
# 仓库根：scripts 位于 <root>/src/scripts
_ROOT = _HERE
while not os.path.isfile(os.path.join(_ROOT, "src", "scripts", "audit_docs.py")):
    _parent = os.path.dirname(_ROOT)
    if _parent == _ROOT:
        break
    _ROOT = _parent
SPEC = os.path.join(_ROOT, "src", "scripts", "audit_docs.py")
spec = importlib.util.spec_from_file_location("audit_docs", SPEC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
import auditlib.checkers.deadcode as dc_mod

SKILL = "C:/Users/admin/.workbuddy/skills/skill-doc-audit"

def _run(argv):
    old_argv = sys.argv
    sys.argv = ["audit_docs.py"] + argv
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            mod.cli.main()
    except SystemExit as e:
        code = e.code
    finally:
        sys.argv = old_argv
    return code, out.getvalue(), err.getvalue()

def _parse_decision(err_text):
    for line in err_text.splitlines():
        if line.startswith("PRE_RUN_DECISION_JSON:"):
            return json.loads(line.split(":", 1)[1])
    return None

print("=" * 72)
print("TEST A: 屏蔽 vulture + 非交互 --deadcode-mode ask -> 执行前决策门(exit 130)，deadcode 选项仅 ast/off")
ca, oa, ea = _run(["--skill", SKILL, "--check", "deadcode", "--deadcode-mode", "ask", "--json"])
dec = _parse_decision(ea)
dc_opts = None
if dec:
    for p in dec["prompts"]:
        if p["checker"] == "deadcode":
            dc_opts = [o["value"] for o in p["options"]]
print("  exit_code=%s  decision_deadcode_options=%s  json_present=%s" % (ca, dc_opts, dec is not None))
assert ca == 130, "A: 期望 exit 130"
assert dec is not None, "A: 期望 PRE_RUN_DECISION_JSON"
assert dc_opts == ["ast", "off"], "A: 屏蔽 vulture 时 deadcode 仅应提供 ast/off，实际=%s" % dc_opts
print("  PASS")

print("=" * 72)
print("TEST B: 屏蔽 vulture + 显式 --deadcode-mode ast -> 直接跑 ast，exit 0")
cb, ob, eb = _run(["--skill", SKILL, "--check", "deadcode", "--deadcode-mode", "ast", "--json"])
print("  exit_code=%s  stderr含'已采用 ast 精度模式'=%s" % (cb, "已采用 ast 精度模式" in eb))
assert cb == 0, "B: 期望 exit 0"
assert "已采用 ast 精度模式" in eb, "B: 应回参 ast 模式"
print("  PASS")

print("=" * 72)
print("TEST C: 屏蔽 vulture + 显式 --deadcode-mode vulture -> 安装失败回退 ast + precision_degraded WARN，exit 0")
_real_run = subprocess.run
def _fake_run(*a, **k):
    raise subprocess.CalledProcessError(1, list(a[0]))
dc_mod.subprocess.run = _fake_run
cc, oc, ec = _run(["--skill", SKILL, "--check", "deadcode", "--deadcode-mode", "vulture", "--json"])
dc_mod.subprocess.run = _real_run
print("  exit_code=%s  stderr含'回退零依赖 AST'=%s  含'精度降级'=%s" % (cc, "回退零依赖 AST" in ec, "精度降级" in ec))
assert cc == 0, "C: 期望 exit 0（WARN 不阻断）"
assert "回退零依赖 AST" in ec, "C: 显式 vulture 缺失应回退 ast"
print("  PASS")

print("=" * 72)
print("TEST D: 屏蔽 vulture + 直接单元调用 _prompt_deadcode_mode（交互提示逻辑）-> 选1(vulture失败回退ast,degraded) / 选2=ast / 超时=ast(degraded)")
for feed, exp in [("1\n", ("ast", True, None)), ("2\n", ("ast", False, None)), ("", ("ast", True, None))]:
    sys.stdin = io.StringIO(feed)
    got = dc_mod._prompt_deadcode_mode()
    print("  输入=%r -> %s  (期望 %s)" % (feed, got, exp))
    assert got == exp, "D: 输入%r 期望%s 实际%s" % (feed, exp, got)
print("  PASS")

print("=" * 72)
print("TEST E: 决策门 _vulture_available() 在屏蔽条件下应为 False（影响 deadcode 选项生成）")
from auditlib.cli import _vulture_available
print("  cli._vulture_available()=%s (屏蔽 vulture 应为 False)" % _vulture_available())
assert _vulture_available() is False, "E: 屏蔽 vulture 时 _vulture_available 应为 False"
print("  PASS")

print("=" * 72)
print("ALL TESTS PASSED: 屏蔽 vulture 条件下 deadcode ask 模式流程全部正常（决策门仅给 ast/off / 交互提示取值正确 / 显式 ast 正常 / 显式 vulture 优雅回退）。")
