#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dev_workbench.py —— dev-workbench 开发编排层全子命令回归测试。

不进部署副本、不触碰真实仓库：版本类操作（bump / run-plan 含 bump）在临时沙箱仓库内执行——
沙箱结构 tmp/{src/SKILL.md, src/scripts/dev_workbench.py, src/scripts/auditlib/sources.py,
CHANGELOG.md}，脚本 _repo_root() 会解析到 tmp（无 audit_docs.py 时回退 .git 上溯失败→取 cand）。

运行：python tests/test_dev_workbench.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC_SCRIPT = os.path.join(REPO, "src", "scripts", "dev_workbench.py")
PY = sys.executable

fails = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL") + "  " + name + (("  | " + detail) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def run(script, *args, **kw):
    """以子进程方式调用（贴近真实 shell 用法），返回 (rc, stdout, stderr)。"""
    r = subprocess.run([PY, script] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=kw.get("cwd"))
    return r.returncode, r.stdout or "", r.stderr or ""


def mk_sandbox(root):
    """构造最小仓库沙箱，返回沙箱内 dev_workbench.py 路径。"""
    os.makedirs(os.path.join(root, "src", "scripts", "auditlib"))
    shutil.copy(SRC_SCRIPT, os.path.join(root, "src", "scripts", "dev_workbench.py"))
    with open(os.path.join(root, "src", "SKILL.md"), "w", encoding="utf-8", newline="") as f:
        f.write('---\nname: sandbox\nversion: "9.9.8"\n---\n\n# sandbox\n')
    with open(os.path.join(root, "src", "scripts", "auditlib", "sources.py"), "w",
              encoding="utf-8", newline="") as f:
        f.write('UA = "skill-doc-audit/9.9.8"\n')
    with open(os.path.join(root, "CHANGELOG.md"), "w", encoding="utf-8", newline="") as f:
        f.write("# 变更明细（CHANGELOG）\n\n> 排序：版本号降序（最新在前）。\n")
    return os.path.join(root, "src", "scripts", "dev_workbench.py")


tmp = tempfile.mkdtemp(prefix="dev_orch_test_")
try:
    script = mk_sandbox(tmp)
    work = os.path.join(tmp, "work")
    os.makedirs(work)
    target = os.path.join(work, "t.txt")
    oldf = os.path.join(work, "old.txt")
    newf = os.path.join(work, "new.txt")

    # ---- patch：多字节走文件 ----
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write("alpha\n旧的中文行：含“引号”与\\转义\nbeta\n")
    with open(oldf, "w", encoding="utf-8", newline="") as f:
        f.write("旧的中文行：含“引号”与\\转义")
    with open(newf, "w", encoding="utf-8", newline="") as f:
        f.write("新的中文行：含「引号」与\\转义")

    rc, out, err = run(script, "patch", "--file", target, "--old-file", oldf,
                       "--new-file", newf, "--once")
    txt = open(target, encoding="utf-8").read()
    check("T1 patch 多字节走文件（--once 命中 1 处）", rc == 0 and "新的中文行" in txt
          and "旧的中文行" not in txt, "rc=%d stderr=%s" % (rc, err))

    rc, out, err = run(script, "patch", "--file", target, "--old-file", oldf,
                       "--new-file", newf, "--once")
    check("T2 patch 旧串未命中（0 处）→ rc 2", rc == 2, "rc=%d" % rc)

    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write("dup\ndup\n")
    rc, out, err = run(script, "patch", "--file", target, "--old", "dup", "--new", "DUP", "--once")
    check("T3 patch 命中 2 处 + --once → rc 2", rc == 2, "rc=%d" % rc)

    rc, out, err = run(script, "patch", "--file", target, "--old", "dup", "--new", "DUP",
                       "--count", "1")
    txt = open(target, encoding="utf-8").read()
    check("T4 patch --count 1 只替换首处", rc == 0 and txt == "DUP\ndup\n", repr(txt))

    # ---- verify ----
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write("新的中文行：含「引号」与\\转义\n")
    rc, out, err = run(script, "verify", "--file", target, "--contains-file", newf,
                       "--not-contains-file", oldf)
    check("T5 verify 含新串且不含旧串 → rc 0", rc == 0, "rc=%d" % rc)
    rc, out, err = run(script, "verify", "--file", target, "--contains", "不存在的串")
    check("T6 verify 断言失败 → rc 2", rc == 2, "rc=%d" % rc)

    # ---- compile ----
    okdir = os.path.join(work, "ok")
    os.makedirs(okdir)
    with open(os.path.join(okdir, "good.py"), "w", encoding="utf-8", newline="") as f:
        f.write("x = 1\n")
    rc, out, err = run(script, "compile", "--root", okdir)
    check("T7 compile 干净目录 → rc 0", rc == 0 and "1 文件通过" in err, err)

    with open(os.path.join(okdir, "bad.py"), "w", encoding="utf-8", newline="") as f:
        f.write("def broken(:\n")
    rc, out, err = run(script, "compile", "--root", okdir)
    check("T8 compile 含语法错文件 → rc 1 且点名", rc == 1 and "bad.py" in err, err)
    os.remove(os.path.join(okdir, "bad.py"))

    # ---- grep ----
    rc, out, err = run(script, "grep", "--pattern", "新的中文行", "--path", work, "--max", "1")
    check("T9 grep 命中并按 --max 截断", rc == 0 and "新的中文行" in out, "rc=%d out=%r" % (rc, out))

    # ---- status / doctor ----
    rc, out, err = run(SRC_SCRIPT, "status")
    check("T10 status 返回 git 状态（rc 0）", rc == 0, "rc=%d err=%s" % (rc, err))
    rc, out, err = run(script, "status")
    check("T10b status 在非 git 目录透传 git 非零退出码", rc != 0, "rc=%d" % rc)
    rc, out, err = run(script, "doctor")
    check("T11 doctor 环境探针（rc 0，含三锚点与部署副本）",
          rc == 0 and "version-anchors" in err and "deploy-copy" in err, err)

    # ---- run ----
    rc, out, err = run(script, "run", "--script", "src/scripts/dev_workbench.py", "doctor")
    check("T12 run 执行仓库内 .py → rc 0 且带 rc=0 回执", rc == 0 and "rc=0" in err, err)
    rc, out, err = run(script, "run", "--script", "src/scripts/not_exists.py")
    check("T13 run 拒绝不存在的脚本 → rc 2", rc == 2, "rc=%d" % rc)
    rc, out, err = run(script, "run", "--script", "src/SKILL.md")
    check("T14 run 拒绝非 .py → rc 2", rc == 2, "rc=%d" % rc)

    # ---- bump（沙箱内，不碰真实仓库）----
    sec = os.path.join(work, "section.md")
    with open(sec, "w", encoding="utf-8", newline="") as f:
        f.write("## {version} 打磨明细（中文副标题：含“引号”）\n"
                "\n- **改动**：沙箱验证 {version}。\n- **验证**：全绿。\n")
    rc, out, err = run(script, "bump", "--version", "9.9.9", "--section-file", sec)
    skill = open(os.path.join(tmp, "src", "SKILL.md"), encoding="utf-8").read()
    ua = open(os.path.join(tmp, "src", "scripts", "auditlib", "sources.py"), encoding="utf-8").read()
    cl = open(os.path.join(tmp, "CHANGELOG.md"), encoding="utf-8").read()
    check("T15 bump 三锚点同步", rc == 0 and 'version: "9.9.9"' in skill
          and "skill-doc-audit/9.9.9" in ua, err)
    check("T16 bump CHANGELOG 走文件模板（{version} 占位符替换 + 中文副标题）",
          "## 9.9.9 打磨明细（中文副标题：含“引号”）" in cl and "沙箱验证 9.9.9" in cl, cl[:200])
    rc, out, err = run(script, "bump", "--version", "9.9.9", "--section-file", sec)
    check("T17 bump 版本已相同 → 跳过（rc 0，未重复插入）", rc == 0 and "跳过" in err
          and cl.count("## 9.9.9") == 1, err)
    rc, out, err = run(script, "bump", "--version", "9.9.10")
    cl2 = open(os.path.join(tmp, "CHANGELOG.md"), encoding="utf-8").read()
    check("T18 bump 无 --section-file → 简化模板 + WARN", rc == 0 and "WARN" in err
          and "## 9.9.10 打磨明细" in cl2, err)

    # ---- run-plan ----
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write("dup\ndup\n")
    plan = {"steps": [
        {"op": "patch", "args": {"file": target, "old": "dup", "new": "PLAN"}},
        {"op": "verify", "args": {"file": target, "contains": ["PLAN"], "not_contains": ["dup"]}},
        {"op": "compile", "args": {"root": okdir}},
        {"op": "run", "args": {"script": "src/scripts/dev_workbench.py", "argv": ["doctor"]}},
    ]}
    planf = os.path.join(work, "plan.json")
    with open(planf, "w", encoding="utf-8", newline="") as f:
        json.dump(plan, f, ensure_ascii=False)
    rc, out, err = run(script, "run-plan", "--plan", planf)
    txt = open(target, encoding="utf-8").read()
    check("T19 run-plan 四步串联（patch→verify→compile→run）",
          rc == 0 and txt == "PLAN\nPLAN\n" and "plan: 完成" in err,
          "rc=%d txt=%r" % (rc, txt))

    bad_plan = {"steps": [
        {"op": "patch", "args": {"file": target, "old": "不存在的锚点", "new": "X", "once": True}},
        {"op": "compile", "args": {"root": okdir}},
    ]}
    badf = os.path.join(work, "bad_plan.json")
    with open(badf, "w", encoding="utf-8", newline="") as f:
        json.dump(bad_plan, f, ensure_ascii=False)
    rc, out, err = run(script, "run-plan", "--plan", badf)
    check("T20 run-plan 任一步失败即中止（后续 compile 未执行）",
          rc != 0 and "中止" in err and "step 1: compile" not in err, err)

finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n%d/%d passed" % (21 - len(fails), 21))
if fails:
    print("FAILED: " + ", ".join(fails))
    sys.exit(1)
print("ALL PASS")
