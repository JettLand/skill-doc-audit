#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dev-workbench —— skill-doc-audit 开发工作台（dev workbench）。

定位（v1.34.7 重定位；v1.35.0 由 dev_orchestrate.py 更名为 dev_workbench.py）
========================
更名理由：本工具并不编排任何外部流程，它是「单进程内的开发期文件操作与校验工作台」
（patch / verify / compile / bump / grep / status / run-plan / doctor / selftest），
原名 orchestrate（编排）词不达意、易被误读成流程调度器。

========================
本工具不是「替代 bash」，而是把开发期对 shell 的脆弱依赖**压缩到最小**：凡是能在一个
Python 进程内完成的事（字节级 patch / 断言复核 / 编译 / 版本 bump / git 状态 / 计划批量），
都不经 bash 命令行传递多字节或转义内容，从而降低对 shell 调用层的暴露面。仍须至少一次
`python dev_workbench.py <sub>` 的 shell 启动——这是物理事实，绕不开。

设计动机：本会话反复踩的坑
============================
1. **Edit 工具 phantom success**：Edit 报「Successfully edited」但磁盘未变，多发于含
   反斜杠转义 / 多字节 / 枚举串 / 中文嵌套引号的字符串。
2. **工具调用参数传输层间歇丢参**：harness 级故障——`Bash.command` / `PowerShell.command` /
   `Read.file_path` 等任意字符串参数会随机变成 `undefined`（报错
   "command expected string, but received undefined"），**与命令内容无关**
   （连 `echo ok` 也失败）。Bash / PowerShell / Read 工具均可能中招，证明脆弱点在
   工具调用的参数传输层，而非某个具体 shell 或 Python。

本工具如何应对（务实口径）
==========================
- **多字节/转义内容移出命令行**：`patch`/`verify` 的旧值、新值、待匹配串一律从*文件*
   读取（`--old-file`/`--new-file`/`--contains-file`），shell 启动命令只剩 ASCII 路径与
   标志，规避参数传输层对中文/引号的丢参。
- **单进程批量执行**：`run-plan` 接受一个 JSON 计划，在**一个 Python 进程**内依次执行
   patch/verify/compile/status，把原本 N 次 shell 往返压缩为 1 次，显著降低因单次
   传输丢参而整批失败的概率；任一步失败即中止并给非零退出码。
- **幂等可重跑**：每个子命令只读/写明确路径，无副作用累积；计划中断后重跑安全。
- **跨 shell 工具冗余**：启动行 `python src/scripts/dev_workbench.py <sub>` 是纯 ASCII、
   跨 shell 通用（bash / powershell / cmd 皆认）。当 Bash 工具丢参时，改用 PowerShell
   工具（或反之）用**同一行**重试——这是针对「传输层丢参」的冗余容错，dev-workbench
   自身不根绝该 bug，只减少其暴露面并提供幂等可重跑路径。
- **验证不依赖 bash echo/cat**：`verify` 直接读字节、对匹配行打印 `repr()`，等价于用
   Read 工具复核磁盘，但可在同一次进程内完成。
- **纯标准库、零外部依赖**：不联网、不装包，开箱即用。

子命令
======
  patch    字节级替换（断言出现次数 + 保 LF），旧/新值来自文件
  verify   断言文件含/不含某子串（多字节串来自文件），打印匹配行 repr
  compile  递归 py_compile 指定目录下全部 .py，逐文件报告
  bump     版本号三锚点同步 + 插入 CHANGELOG 小节
  grep     纯 Python 递归 grep（覆盖全部文本文件，跳过已知二进制）
  status   git status --short（一次 subprocess 封装）
  run      白名单执行仓库内 .py（不执行任意命令 / shell 字符串）
  run-plan 读 JSON 计划，单进程批量执行上述操作
  doctor   纯 Python 环境探针（python 版本 / git 在 PATH / 部署副本 / 三锚点一致），零 shell 依赖
  selftest 内置自测
  commit   git commit 薄封装（转发 -m、跑完自动 doctor 确认同步；禁止 --no-verify）
  trash    移入系统回收站（绝不硬删；--force 才硬删且二次告警；--dry-run 只打印）
  clean    清理仓库内 temp/ 等生成物（移入回收站；--dry-run 只打印）
  audit    薄封装 dev_self_audit.py（质量门禁；argv 透传如 --strict）
  validate 薄封装 self_validate.py（检查器回归护栏）
  diff     git diff --stat（只读，替代裸 git diff）
  log      git log（默认 --oneline -10，只读，替代裸 git log）
  sync     手动强制重同步部署副本（调用 sync_deploy.py）
"""
import argparse
import io
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import base64
import time

# ── 路径解析：从本文件向上定位仓库根（与 tests/ 下测试脚本同源手法）──────────────
def _repo_root():
    d = os.path.dirname(os.path.abspath(__file__))
    # src/scripts/dev_workbench.py -> 仓库根 = 上两级
    cand = os.path.dirname(os.path.dirname(d))
    if os.path.isfile(os.path.join(cand, "src", "scripts", "audit_docs.py")):
        return cand
    # 兜底：向上找含 .git 的目录
    cur = d
    while cur and cur != os.path.dirname(cur):
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        cur = os.path.dirname(cur)
    return cand


def _read_bytes(p):
    with open(p, "rb") as f:
        return f.read()


def _read_text(p):
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write_text(p, text):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


# ── patch ────────────────────────────────────────────────────────────────────
def cmd_patch(args):
    old_file = getattr(args, "old_file", None)
    new_file = getattr(args, "new_file", None)
    old_inline = getattr(args, "old", None)
    new_inline = getattr(args, "new", None)
    if old_file:
        old = _read_bytes(old_file)
    elif old_inline is not None:
        old = old_inline if isinstance(old_inline, bytes) else old_inline.encode("utf-8")
    else:
        sys.stderr.write("patch FAIL: 需提供 --old-file 或 --old\n")
        return 2
    if new_file:
        new = _read_bytes(new_file)
    elif new_inline is not None:
        new = new_inline if isinstance(new_inline, bytes) else new_inline.encode("utf-8")
    else:
        sys.stderr.write("patch FAIL: 需提供 --new-file 或 --new\n")
        return 2
    data = _read_bytes(args.file)
    cnt = data.count(old)
    if args.once and cnt != 1:
        sys.stderr.write("patch FAIL: 期望恰好 1 处匹配，实际 %d 处\n" % cnt)
        return 2
    if cnt == 0:
        sys.stderr.write("patch FAIL: 旧串未命中（0 处）\n")
        return 2
    data = data.replace(old, new, args.count if args.count else -1)
    _write_text(args.file, data.decode("utf-8"))
    sys.stderr.write("patch OK: 文件 %s，替换 %d 处\n" % (args.file, cnt))
    return 0


# ── verify ─────────────────────────────────────────────────────────────────────
def cmd_verify(args):
    text = _read_text(args.file)
    ok = True
    for cf in args.contains_file or []:
        sub = _read_text(cf)
        n = text.count(sub)
        sys.stderr.write("verify contains-file %s : 命中 %d 处\n" % (cf, n))
        if n == 0:
            ok = False
    for c in args.contains or []:
        n = text.count(c)
        sys.stderr.write("verify contains %r : 命中 %d 处\n" % (c, n))
        if n == 0:
            ok = False
    for nf in args.not_contains_file or []:
        sub = _read_text(nf)
        n = text.count(sub)
        sys.stderr.write("verify NOT contains-file %s : 命中 %d 处\n" % (nf, n))
        if n != 0:
            ok = False
    for nc in args.not_contains or []:
        n = text.count(nc)
        sys.stderr.write("verify NOT contains %r : 命中 %d 处\n" % (nc, n))
        if n != 0:
            ok = False
    # 打印匹配行上下文（等价 Read 复核，但无需 bash）
    for c in args.contains or []:
        for m in re.finditer(re.escape(c), text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.start())
            if line_end == -1:
                line_end = len(text)
            sys.stderr.write("  ↳ %s\n" % repr(text[line_start:line_end]))
    return 0 if ok else 2


# ── compile ────────────────────────────────────────────────────────────────────
def cmd_compile(args):
    root = args.root or os.path.join(_repo_root(), "src", "scripts")
    bad = []
    good = 0
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.endswith(".py"):
                fp = os.path.join(dirpath, fn)
                try:
                    py_compile.compile(fp, doraise=True)
                    good += 1
                except py_compile.PyCompileError as exc:
                    bad.append((fp, str(exc)))
    sys.stderr.write("compile: %d 文件通过，%d 失败\n" % (good, len(bad)))
    for fp, exc in bad:
        sys.stderr.write("  FAIL %s\n%s\n" % (fp, exc))
    return 1 if bad else 0


# ── bump ───────────────────────────────────────────────────────────────────────
_VERSION_RE = re.compile(r'^version:\s*["\']?([0-9][0-9A-Za-z.\-]*)["\']?\s*$', re.M)
_UA_RE = re.compile(r'skill-doc-audit/([0-9][0-9A-Za-z.\-]*)')


def cmd_bump(args):
    root = _repo_root()
    skill_md = os.path.join(root, "src", "SKILL.md")
    sources_py = os.path.join(root, "src", "scripts", "auditlib", "sources.py")
    changelog = os.path.join(root, "CHANGELOG.md")
    new = args.version
    skill_text = _read_text(skill_md)
    m = _VERSION_RE.search(skill_text)
    if not m:
        sys.stderr.write("bump FAIL: SKILL.md 未找到 version:\n")
        return 2
    old = m.group(1)
    if old == new:
        sys.stderr.write("bump: 版本已是 %s，跳过\n" % new)
        return 0
    # 1) SKILL.md
    skill_text = _VERSION_RE.sub('version: "%s"' % new, skill_text, count=1)
    _write_text(skill_md, skill_text)
    # 2) sources.py User-Agent
    src_text = _read_text(sources_py)
    cnt = len(_UA_RE.findall(src_text))
    src_text = _UA_RE.sub("skill-doc-audit/%s" % new, src_text, count=1)
    _write_text(sources_py, src_text)
    sys.stderr.write("bump: SKILL.md %s->%s, sources.py UA 替换 %d 处\n" % (old, new, cnt))
    # 3) CHANGELOG 小节（插在排序说明之后）
    # 中文/转义内容一律走文件（--section-file），符合本工具「多字节移出命令行」原则；
    # 文件内 {version} 占位符替换为新版本号（用 replace 而非 format，避免正文花括号被误解析）。
    # 未提供文件时回退简化模板并告警——房屋风格要求「## X.Y.Z 打磨明细（副标题）」，须人工补齐。
    cl = _read_text(changelog)
    sf = getattr(args, "section_file", None)
    if sf:
        body = _read_text(sf).replace("{version}", new)
        if not body.endswith("\n"):
            body += "\n"
        section = "\n" + body + "\n"
    else:
        sys.stderr.write("bump WARN: 未提供 --section-file，已写简化模板；"
                         "须人工补齐「## X.Y.Z 打磨明细（副标题）」与验证行\n")
        section = ("\n## %s 打磨明细\n\n- **改动**：%s\n- **验证**：dev_self_audit --strict 全绿。\n"
                   % (new, args.section or "(待补)"))
    anchor = "> 排序：版本号降序（最新在前）。"
    if anchor in cl:
        cl = cl.replace(anchor, anchor + section, 1)
    else:
        cl = section + cl
    _write_text(changelog, cl)
    sys.stderr.write("bump OK: 三锚点已同步为 %s\n" % new)
    return 0


# ── grep ────────────────────────────────────────────────────────────────────────
def cmd_grep(args):
    root = args.path or _repo_root()
    pat = re.compile(args.pattern)
    hits = 0
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            # 跳过已知二进制；其余按文本尝试（解码失败由下方 try/except 兜底），
            # 从而覆盖仓库全部文本文件（含 .sh/.yaml/.ts 等），实现"只读核验作用于所有文件"。
            if fn.endswith((".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
                            ".ico", ".zip", ".gz", ".tar", ".tgz", ".pdf", ".exe",
                            ".dll", ".so", ".dylib", ".bin", ".dat", ".woff", ".woff2")):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                text = _read_text(fp)
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pat.search(line):
                    sys.stdout.write("%s:%d: %s\n" % (fp, i, line))
                    hits += 1
                    if args.max and hits >= args.max:
                        return 0
    sys.stderr.write("grep: %d 命中\n" % hits)
    return 0


# ── status ──────────────────────────────────────────────────────────────────────
def cmd_status(args):
    r = subprocess.run(["git", "-C", _repo_root(), "status", "--short"],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r.returncode


# ── doctor（纯 Python 环境探针，零 shell 依赖）────────────────────────────────────
def cmd_doctor(args):
    root = _repo_root()
    rows = []
    rows.append(("python", "%d.%d.%d" % sys.version_info[:3]))
    rows.append(("git", "in PATH" if shutil.which("git") else "MISSING"))
    try:
        v1 = _VERSION_RE.search(_read_text(os.path.join(root, "src", "SKILL.md"))).group(1)
        v2 = _UA_RE.search(_read_text(os.path.join(root, "src", "scripts", "auditlib", "sources.py"))).group(1)
        rows.append(("version-anchors", "consistent(%s)" % v1 if v1 == v2 else "MISMATCH %s/%s" % (v1, v2)))
    except Exception as e:
        v1 = None
        rows.append(("version-anchors", "ERROR %s" % e))
    # 部署副本：存在性 + 与源码版本比对（等价 dev_self_audit 的同步校验，但零 shell）
    deploy = os.path.expanduser("~/.workbuddy/skills/skill-doc-audit/SKILL.md")
    if not os.path.isfile(deploy):
        rows.append(("deploy-copy", "MISSING"))
    elif v1:
        try:
            dv = _VERSION_RE.search(_read_text(deploy)).group(1)
            rows.append(("deploy-copy", "synced(%s)" % dv if dv == v1 else "STALE %s(src %s)" % (dv, v1)))
        except Exception as e:
            rows.append(("deploy-copy", "ERROR %s" % e))
    else:
        rows.append(("deploy-copy", "exists"))
    for k, v in rows:
        sys.stderr.write("doctor: %s = %s\n" % (k, v))
    bad = [k for k, v in rows if ("MISSING" in v) or ("MISMATCH" in v) or v.startswith("ERROR")]
    return 1 if bad else 0


# ── run（单进程内执行仓库内脚本，供 run-plan 编排）─────────────────────────────────
def cmd_run(args):
    script = args.script
    if not os.path.isabs(script):
        script = os.path.join(_repo_root(), script)
    # 白名单：仅仓库内已存在的 .py（相对路径按仓库根解析），不执行任意命令 / shell 字符串
    if not script.endswith(".py") or not os.path.isfile(script):
        sys.stderr.write("run FAIL: 仅执行仓库内 .py 脚本，未找到 %s\n" % script)
        return 2
    argv = [sys.executable, script] + list(getattr(args, "argv", None) or [])
    r = subprocess.run(argv, cwd=_repo_root(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    sys.stderr.write("run: %s rc=%d\n" % (os.path.basename(script), r.returncode))
    return r.returncode


# ── commit（薄封装 dev_commit.py，确保提交必走 post-commit 同步钩子）─────────────────
def cmd_commit(args):
    script = os.path.join(_repo_root(), "src", "scripts", "dev_commit.py")
    if not os.path.isfile(script):
        sys.stderr.write("commit FAIL: 未找到 %s\n" % script)
        return 2
    msg = getattr(args, "message", None)
    if not msg:
        sys.stderr.write("commit FAIL: 需 -m 提交说明\n")
        return 2
    # 透传 -m；不提供 --no-verify，提交须触发 post-commit 同步钩子
    argv = [sys.executable, script, "-m", msg]
    r = subprocess.run(argv, cwd=_repo_root(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    if r.returncode != 0:
        sys.stderr.write("commit: dev_commit.py 失败 rc=%d\n" % r.returncode)
        return r.returncode
    # 提交后确认部署副本已同步（零额外 shell）
    sys.stderr.write("commit: 提交完成，校验部署副本同步状态...\n")
    return cmd_doctor(argparse.Namespace())


# ── run-plan（单进程批量，压缩 bash 往返）─────────────────────────────────────────
def cmd_run_plan(args):
    plan = json.loads(_read_text(args.plan))
    rc = 0
    for i, step in enumerate(plan.get("steps", [])):
        op = step.get("op")
        sys.stderr.write("=== plan step %d: %s ===\n" % (i, op))
        a = argparse.Namespace(**step.get("args", {}))
        # 注入子命令可能缺省的属性，避免 AttributeError
        for k, dv in (("old_file", None), ("new_file", None), ("old", None),
                      ("new", None), ("count", 0), ("once", False),
                      ("contains", []), ("not_contains", []),
                      ("contains_file", []), ("not_contains_file", []),
                      ("root", None), ("section", ""), ("path", None), ("max", 0),
                      ("script", None), ("argv", []), ("section_file", None),
                      ("message", ""), ("path", None), ("force", False), ("dry_run", False)):
            if not hasattr(a, k):
                setattr(a, k, dv)
        # 把文件路径相对仓库根解析
        for k in ("file", "old_file", "new_file", "contains_file", "not_contains_file"):
            v = getattr(a, k, None)
            if isinstance(v, str) and not os.path.isabs(v):
                setattr(a, k, os.path.join(_repo_root(), v))
        if op == "patch":
            rc = cmd_patch(a) or rc
        elif op == "verify":
            rc = cmd_verify(a) or rc
        elif op == "compile":
            rc = cmd_compile(a) or rc
        elif op == "bump":
            rc = cmd_bump(a) or rc
        elif op == "run":
            rc = cmd_run(a) or rc
        elif op == "commit":
            rc = cmd_commit(a) or rc
        elif op == "trash":
            rc = cmd_trash(a) or rc
        elif op == "clean":
            rc = cmd_clean(a) or rc
        elif op == "audit":
            rc = cmd_audit(a) or rc
        elif op == "validate":
            rc = cmd_validate(a) or rc
        elif op == "diff":
            rc = cmd_diff(a) or rc
        elif op == "log":
            rc = cmd_log(a) or rc
        elif op == "sync":
            rc = cmd_sync(a) or rc
        else:
            sys.stderr.write("plan: 未知 op %s，跳过\n" % op)
            rc = rc or 2
        if rc and not step.get("continue_on_error", False):
            sys.stderr.write("plan: step %d 失败，中止\n" % i)
            return rc
    sys.stderr.write("plan: 完成\n")
    return rc


# ── selftest ──────────────────────────────────────────────────────────────────
def cmd_selftest(args):
    import tempfile
    d = tempfile.mkdtemp()
    f = os.path.join(d, "t.txt")
    _write_text(f, "alpha\nbeta\n gamma \n")
    # patch
    assert cmd_patch(argparse.Namespace(file=f, old=b"beta", new=b"Beta",
                                        old_file=None, new_file=None,
                                        count=0, once=True)) == 0
    assert "Beta" in _read_text(f)
    # verify
    assert cmd_verify(argparse.Namespace(file=f, contains=["Beta"], not_contains=["beta"],
                                         contains_file=None, not_contains_file=None)) == 0
    # verify fail path
    assert cmd_verify(argparse.Namespace(file=f, contains=["zzz"], not_contains=[],
                                         contains_file=None, not_contains_file=None)) == 2
    sys.stderr.write("selftest OK\n")
    return 0



# ── trash / clean（安全删除：进系统回收站，绝不硬删）────────────────────────────
class _TrashUnavailable(Exception):
    pass


def _in_recycle_bin(name):
    """粗略判断名为 name 的文件是否已在系统回收站（仅作安全校验，非精确匹配）。"""
    try:
        bin_root = os.path.join(os.environ.get("SystemDrive", "C:"), "$Recycle.Bin")
        for sid in os.listdir(bin_root):
            d = os.path.join(bin_root, sid)
            for root, _, files in os.walk(d):
                for f in files:
                    if f == name or name in f:
                        return True
    except OSError:
        pass
    return False


def _recycle_via_com(path):
    """经 Shell.Application COM 将文件送回收站（与资源管理器同源，正确处理含中文目录名）。
    返回 subprocess.CompletedProcess；调用方自行判定成功/超时。路径走环境变量透传（Unicode 无损）。"""
    env = dict(os.environ)
    env["DEVWB_TRASH_PATH"] = os.path.abspath(path)
    com = ('$p=$env:DEVWB_TRASH_PATH; '
          '$sh=New-Object -ComObject Shell.Application; '
          '$folder=$sh.Namespace((Split-Path $p)); '
          '$item=$folder.ParseName((Split-Path $p -Leaf)); '
          'if($item){$item.InvokeVerb("delete")}else{throw "ParseName-null:$p"}')
    return subprocess.run(["powershell", "-NoProfile", "-Command", com],
                          capture_output=True, env=env, timeout=15)


def _trash_windows(path):
    # 安全护栏：本环境（或无交互外壳的沙箱）下，回收站 API（VB / COM / SHFileOperation）实测会退化为「硬删除」。
    # 故先用一个 sacrificial canary 验证回收站是否真可用；若 canary 被硬删（不在回收站），
    # 则拒绝操作真实文件，绝不让静默数据丢失。真实 Windows 上 canary 会进回收站，可安全继续。
    canary = path + ".canary-%d" % os.getpid()
    try:
        open(canary, "w", encoding="utf-8").close()
        r = _recycle_via_com(canary)
        if r.returncode != 0 or os.path.exists(canary) or not _in_recycle_bin(os.path.basename(canary)):
            raise _TrashUnavailable("回收站不可用（canary 未安全进入回收站，疑似硬删），拒绝操作真实文件")
    except subprocess.TimeoutExpired:
        raise _TrashUnavailable("powershell(COM) 超时（疑似无交互外壳），拒绝操作真实文件")
    finally:
        if os.path.exists(canary):
            try:
                os.remove(canary)
            except OSError:
                pass
    # canary 已进入回收站 → 真实文件回收可用
    try:
        r = _recycle_via_com(path)
        if r.returncode != 0:
            out = (r.stdout or b"").decode("utf-8", "replace")
            err = (r.stderr or b"").decode("utf-8", "replace")
            raise _TrashUnavailable("powershell rc=%d %s" % (r.returncode, (err or out).strip()))
    except subprocess.TimeoutExpired:
        raise _TrashUnavailable("powershell(COM) 超时（疑似无交互外壳），已中止，文件未删")
    if os.path.exists(path):
        raise _TrashUnavailable("回收站未移走真实文件（仍存在于 %s）；拒绝谎报成功" % path)
    if not _in_recycle_bin(os.path.basename(path)):
        raise _TrashUnavailable("检测到真实文件被硬删除（不在回收站）——环境回收站退化，已发生数据丢失，请改用 --force 显式确认或手动处理")


def _trash_darwin(path):
    # 纯标准库：移入用户回收站 ~/Trash（Finder 可见、可恢复）
    trash_dir = os.path.expanduser("~/.Trash")
    os.makedirs(trash_dir, exist_ok=True)
    dest = os.path.join(trash_dir, os.path.basename(path))
    if os.path.exists(dest):
        dest += ".%d" % int(time.time())
    shutil.move(path, dest)


def _trash_linux(path):
    r = None
    if shutil.which("gio"):
        r = subprocess.run(["gio", "trash", path], capture_output=True)
    elif shutil.which("trash-put"):
        r = subprocess.run(["trash-put", path], capture_output=True)
    else:
        trash_dir = os.path.join(os.environ.get("XDG_DATA_HOME",
                                                 os.path.expanduser("~/.local/share")),
                                 "Trash", "files")
        try:
            os.makedirs(trash_dir, exist_ok=True)
            dest = os.path.join(trash_dir, os.path.basename(path))
            if os.path.exists(dest):
                dest += ".%d" % int(time.time())
            shutil.move(path, dest)
            return
        except Exception as e:
            raise _TrashUnavailable("manual trash failed: %s" % e)
    if r is not None and r.returncode != 0:
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        raise _TrashUnavailable("trash util rc=%d %s" % (r.returncode, (err or out).strip()))


def _trash_file(path, force=False, dry_run=False):
    """移入系统回收站（可恢复）；回收站不可用且未 --force 时拒绝硬删。"""
    if not os.path.exists(path):
        return 2, "trash: 路径不存在 %s" % path
    if dry_run:
        return 0, "trash DRY-RUN: 将移入回收站 %s" % path
    try:
        if sys.platform == "win32":
            _trash_windows(path)
        elif sys.platform == "darwin":
            _trash_darwin(path)
        else:
            _trash_linux(path)
        return 0, "trash: 已移入回收站 %s" % path
    except _TrashUnavailable as e:
        if force:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return 0, "trash: 回收站不可用，--force 已硬删 %s" % path
        return 2, "trash: 回收站不可用（%s）；拒绝硬删，请用 --force 显式确认" % e


def cmd_trash(args):
    rc, msg = _trash_file(args.path, force=args.force, dry_run=args.dry_run)
    sys.stderr.write(msg + "\n")
    return rc


def cmd_clean(args):
    root = _repo_root()
    targets = [args.path] if getattr(args, "path", None) else [os.path.join(root, "temp")]
    rc = 0
    for t in targets:
        if not os.path.exists(t):
            sys.stderr.write("clean: 跳过（不存在）%s\n" % t)
            continue
        entries = [os.path.join(t, e) for e in os.listdir(t)] if os.path.isdir(t) else [t]
        if not entries:
            sys.stderr.write("clean: 空目录 %s\n" % t)
            continue
        for e in entries:
            r, msg = _trash_file(e, force=args.force, dry_run=args.dry_run)
            sys.stderr.write(msg + "\n")
            if r != 0:
                rc = r
    return rc


# ── audit / validate（薄封装 dev 工具，消除裸 Bash 跑门禁/护栏）────────────────
def cmd_audit(args):
    script = os.path.join(_repo_root(), "src", "scripts", "dev_self_audit.py")
    if not os.path.isfile(script):
        sys.stderr.write("audit FAIL: 未找到 %s\n" % script)
        return 2
    argv = [sys.executable, script] + list(getattr(args, "argv", None) or [])
    r = subprocess.run(argv, cwd=_repo_root(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    sys.stderr.write("audit: %s rc=%d\n" % (os.path.basename(script), r.returncode))
    return r.returncode


def cmd_validate(args):
    script = os.path.join(_repo_root(), "src", "scripts", "self_validate.py")
    if not os.path.isfile(script):
        sys.stderr.write("validate FAIL: 未找到 %s\n" % script)
        return 2
    argv = [sys.executable, script] + list(getattr(args, "argv", None) or [])
    r = subprocess.run(argv, cwd=_repo_root(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    sys.stderr.write("validate: %s rc=%d\n" % (os.path.basename(script), r.returncode))
    return r.returncode


# ── diff / log（只读 git 检视，替代裸 git 调用）────────────────────────────────
def cmd_diff(args):
    extra = list(getattr(args, "argv", None) or [])
    if not extra:
        extra = ["--stat"]
    argv = ["git", "-C", _repo_root(), "diff"] + extra
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r.returncode


def cmd_log(args):
    extra = list(getattr(args, "argv", None) or []) or ["--oneline", "-10"]
    r = subprocess.run(["git", "-C", _repo_root(), "log"] + extra, capture_output=True, text=True)
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r.returncode


# ── sync（手动强制重同步部署副本）────────────────────────────────────────────
def cmd_sync(args):
    script = os.path.join(_repo_root(), "src", "scripts", "sync_deploy.py")
    if not os.path.isfile(script):
        sys.stderr.write("sync FAIL: 未找到 %s\n" % script)
        return 2
    r = subprocess.run([sys.executable, script], cwd=_repo_root(), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r.returncode


def build_parser():
    p = argparse.ArgumentParser(description="dev-workbench")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("patch", help="字节级替换（旧/新值来自文件）")
    pp.add_argument("--file", required=True)
    pp.add_argument("--old-file", help="旧值文件（字节）")
    pp.add_argument("--new-file", help="新值文件（字节）")
    pp.add_argument("--old", help="旧值内联（简单 ASCII 用）")
    pp.add_argument("--new", help="新值内联")
    pp.add_argument("--count", type=int, default=0, help="最多替换次数（0=全部）")
    pp.add_argument("--once", action="store_true", help="要求恰好 1 处匹配")
    pp.set_defaults(func=cmd_patch)

    vp = sub.add_parser("verify", help="断言含/不含子串")
    vp.add_argument("--file", required=True)
    vp.add_argument("--contains", action="append", default=[])
    vp.add_argument("--not-contains", action="append", default=[])
    vp.add_argument("--contains-file", action="append", default=[])
    vp.add_argument("--not-contains-file", action="append", default=[])
    vp.set_defaults(func=cmd_verify)

    cp = sub.add_parser("compile", help="递归 py_compile")
    cp.add_argument("--root", default=None)
    cp.set_defaults(func=cmd_compile)

    bp = sub.add_parser("bump", help="版本号三锚点 + CHANGELOG")
    bp.add_argument("--version", required=True)
    bp.add_argument("--section-file", default=None,
                    help="CHANGELOG 小节模板文件（中文/转义内容走文件，规避参数传输层丢参；"
                         "可含 {version} 占位符）")
    bp.add_argument("--section", default="", help="小节内容内联（仅简单 ASCII 用）")
    bp.set_defaults(func=cmd_bump)

    gp = sub.add_parser("grep", help="纯 Python grep")
    gp.add_argument("--pattern", required=True)
    gp.add_argument("--path", default=None)
    gp.add_argument("--max", type=int, default=0)
    gp.set_defaults(func=cmd_grep)

    sp = sub.add_parser("status", help="git status --short")
    sp.set_defaults(func=cmd_status)

    dp = sub.add_parser("doctor", help="纯 Python 环境探针")
    dp.set_defaults(func=cmd_doctor)

    rnp = sub.add_parser("run", help="执行仓库内 .py 脚本（单进程编排用）")
    rnp.add_argument("--script", required=True, help="仓库相对路径或绝对路径，须为 .py")
    rnp.add_argument("argv", nargs=argparse.REMAINDER, help="原样透传给脚本的参数（含其内部子命令与 - 开头旗标）")
    rnp.set_defaults(func=cmd_run)

    cmp = sub.add_parser("commit", help="薄封装 dev_commit.py（提交并触发同步钩子）")
    cmp.add_argument("-m", "--message", required=True, help="提交说明（必填）")
    cmp.set_defaults(func=cmd_commit)

    tp = sub.add_parser("trash", help="移入系统回收站（绝不硬删；--force 才硬删且二次告警）")
    tp.add_argument("--path", required=True, help="要移入回收站的路径（文件或目录；支持中文）")
    tp.add_argument("--force", action="store_true", help="回收站不可用时硬删（须显式确认）")
    tp.add_argument("--dry-run", action="store_true", help="只打印将执行的操作，不真正移动")
    tp.set_defaults(func=cmd_trash)

    clp = sub.add_parser("clean", help="清理仓库内 temp/ 等生成物（移入回收站）")
    clp.add_argument("--path", default=None, help="覆盖默认清理目标（默认仓库 temp/）")
    clp.add_argument("--force", action="store_true", help="回收站不可用时硬删（须显式确认）")
    clp.add_argument("--dry-run", action="store_true", help="只打印，不真正移动")
    clp.set_defaults(func=cmd_clean)

    ap = sub.add_parser("audit", help="薄封装 dev_self_audit.py（质量门禁）")
    ap.add_argument("argv", nargs="*", help="透传给 dev_self_audit.py 的参数（如 --strict）")
    ap.set_defaults(func=cmd_audit)

    vp = sub.add_parser("validate", help="薄封装 self_validate.py（检查器回归护栏）")
    vp.add_argument("argv", nargs="*", help="透传给 self_validate.py 的参数")
    vp.set_defaults(func=cmd_validate)

    dp = sub.add_parser("diff", help="git diff --stat（只读）")
    dp.add_argument("argv", nargs="*", help="透传给 git diff 的额外参数（默认 --stat；可覆盖）")
    dp.set_defaults(func=cmd_diff)

    lp = sub.add_parser("log", help="git log（默认 --oneline -10，只读）")
    lp.add_argument("argv", nargs="*", help="透传给 git log 的额外参数（默认 --oneline -10；可覆盖）")
    lp.set_defaults(func=cmd_log)

    syp = sub.add_parser("sync", help="手动强制重同步部署副本（调用 sync_deploy.py）")
    syp.set_defaults(func=cmd_sync)

    rp = sub.add_parser("run-plan", help="单进程批量执行 JSON 计划")
    rp.add_argument("--plan", required=True)
    rp.set_defaults(func=cmd_run_plan)

    st = sub.add_parser("selftest", help="内置自测")
    st.set_defaults(func=cmd_selftest)
    return p


def main(argv=None):
    args, extra = build_parser().parse_known_args(argv)
    # 透传型子命令（audit/validate/diff/log 的 argv 可能以 -- 开头）：
    # parse_known_args 把 -- 开头的参数留在 extra，这里并回 argv。
    if hasattr(args, "argv") and isinstance(args.argv, list):
        args.argv = list(args.argv) + list(extra)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
