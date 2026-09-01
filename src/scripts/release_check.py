#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布就绪检查：让同步钩子/本地CI 对 agent 发出「待办提示」，减少对记忆文件的依赖。

为什么需要（长期项目痛点）：
  版本迭代后有一批「必须由 agent 执行」的收尾操作——把 sources.py 的 User-Agent
  同步为 SKILL.md 版本号、把 CHANGELOG「未发布改动」收口为版本节、重打包 dist 制品、
  清理 temp/ 测试残留。这些步骤若只靠 agent 记忆，极易漏做并造成隐蔽漂移
  （例如工具带着陈旧版本号自报给远端服务器）。本模块把这类步骤固化为可重复检查，
  由 dev_self_audit.py（本地 pre-push 钩子与远程 dev-qa CI 都调用它）统一输出
  `[agent-todo]` 提示块，agent 无需回忆即可照做。

  阻断项（版本不一致 / CHANGELOG 未收口）以 ERROR/WARN 返回，使 dev_self_audit
  在 --strict 下失败、拦下 push；非阻断项（dist 过期 / temp 残留）仅作 INFO 提示，
  不阻塞常规提交与推送。
"""
import os
import re
import sys
import glob

HERE = os.path.dirname(os.path.abspath(__file__))   # <root>/src/scripts
SRC = os.path.dirname(HERE)                           # <root>/src
ROOT = os.path.dirname(SRC)                           # 仓库根

VERSION_RE = re.compile(r'^version:\s*["\']?([0-9][0-9A-Za-z.\-]*)["\']?\s*$', re.M)
UA_RE = re.compile(r'skill-doc-audit/(\d+\.\d+\.\d+)')


def _ver_tuple(v):
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def check_version_consistency():
    """SKILL.md frontmatter version 必须等于 sources.py 的 HTTP User-Agent。"""
    skill_md = os.path.join(SRC, "SKILL.md")
    sources_py = os.path.join(SRC, "scripts", "auditlib", "sources.py")
    skill_ver = ua_ver = None
    try:
        with open(skill_md, encoding="utf-8") as f:
            m = VERSION_RE.search(f.read())
            if m:
                skill_ver = m.group(1)
    except OSError:
        pass
    try:
        with open(sources_py, encoding="utf-8") as f:
            m = UA_RE.search(f.read())
            if m:
                ua_ver = m.group(1)
    except OSError:
        pass
    if skill_ver and ua_ver and skill_ver != ua_ver:
        return {
            "blocking": True,
            "severity": "ERROR",
            "title": "版本号不一致：SKILL.md 与 sources.py User-Agent 不同步",
            "detail": "SKILL.md version=%s，但 sources.py 的 HTTP User-Agent=skill-doc-audit/%s"
                      % (skill_ver, ua_ver),
            "todo": "将 src/scripts/auditlib/sources.py 第144行的 User-Agent 改为 skill-doc-audit/%s" % skill_ver,
        }
    return None


def check_readme_version():
    """README.md「版本摘要」表的最新版本行必须等于 SKILL.md 版本号。

    与 check_version_consistency 同属「版本四处一致性」家族：SKILL.md / sources.py
    User-Agent / README 版本摘要表 / CHANGELOG 最高版本节。前三者机器强制相等，
    CHANGELOG 仅校验「已收口为版本节」（见 check_changelog_promotion）。本检查把
    README 纳入机器强制，避免某次改了 SKILL.md 却漏更新 README 版本表、带旧版本号上架。
    """
    skill_md = os.path.join(SRC, "SKILL.md")
    readme = os.path.join(ROOT, "README.md")
    try:
        with open(skill_md, encoding="utf-8") as f:
            m = VERSION_RE.search(f.read())
            skill_ver = m.group(1) if m else None
    except OSError:
        return None
    if not skill_ver:
        return None
    try:
        with open(readme, encoding="utf-8") as f:
            rows = re.findall(r"^\|\s*(\d+\.\d+\.\d+)\s*\|", f.read(), re.M)
    except OSError:
        return None
    if not rows:
        return None  # 解析不到版本表行时不误拦（格式异常由人工兜底）
    max_ver = max(rows, key=_ver_tuple)
    if max_ver != skill_ver:
        return {
            "blocking": True,
            "severity": "ERROR",
            "title": "版本号不一致：README.md 版本摘要表与 SKILL.md 不同步",
            "detail": "SKILL.md version=%s，但 README.md「版本摘要」表最新版本行为 %s" % (skill_ver, max_ver),
            "todo": "在 README.md「版本摘要」表顶部补一行 '| %s | （本次改动说明） |'，或修正已有行版本号" % skill_ver,
        }
    return None


def check_changelog_promotion():
    """SKILL.md 版本高于 CHANGELOG 最高版本节时，须先把「未发布改动」收口为版本节。"""
    skill_md = os.path.join(SRC, "SKILL.md")
    changelog = os.path.join(ROOT, "CHANGELOG.md")
    try:
        with open(skill_md, encoding="utf-8") as f:
            m = VERSION_RE.search(f.read())
            skill_ver = m.group(1) if m else None
    except OSError:
        return None
    if not skill_ver:
        return None
    max_ver = None
    try:
        with open(changelog, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^##\s+(\d+\.\d+\.\d+)\s", line)
                if m:
                    t = _ver_tuple(m.group(1))
                    if max_ver is None or t > max_ver:
                        max_ver = t
    except OSError:
        return None
    if max_ver is None:
        return None
    if _ver_tuple(skill_ver) > max_ver:
        max_str = ".".join(str(x) for x in max_ver)
        return {
            "blocking": True,
            "severity": "WARN",
            "title": "CHANGELOG 未发布改动未收口为版本节",
            "detail": "SKILL.md version=%s，但 CHANGELOG 最高版本节为 %s（「未发布改动」尚未收口）" % (skill_ver, max_str),
            "todo": "将 CHANGELOG.md 的「未发布改动」节提升为 '%s 打磨明细' 节后再提交" % skill_ver,
        }
    return None


def check_dist_staleness():
    """dist zip 必须不早于发布面源码，否则 SkillHub 发布会打包旧代码。"""
    zip_path = os.path.join(SRC, "dist", "skill-doc-audit.zip")
    if not os.path.exists(zip_path):
        return None
    zip_mtime = os.path.getmtime(zip_path)
    roots = [
        os.path.join(SRC, "SKILL.md"),
        os.path.join(SRC, "scripts", "audit_docs.py"),
        os.path.join(SRC, "references", "checkers.md"),
        os.path.join(SRC, "scripts", "auditlib"),
    ]
    newest = zip_mtime
    for r in roots:
        if os.path.isfile(r):
            newest = max(newest, os.path.getmtime(r))
        elif os.path.isdir(r):
            for root, dirs, files in os.walk(r):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    if f.endswith(".pyc"):
                        continue
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
    if zip_mtime < newest - 1.0:  # 1s 容差
        return {
            "blocking": False,
            "severity": "INFO",
            "title": "dist 制品可能过期",
            "detail": "src/dist/skill-doc-audit.zip 早于发布面源码，SkillHub 发布将打包旧代码",
            "todo": "发布 SkillHub 前重打包：python src/scripts/build_dist.py",
        }
    return None


def check_temp_residue():
    """temp/ 存放临时测试产物；及时清理（但清理前先确认非用户手动放入的文件）。"""
    temp_dir = os.path.join(ROOT, "temp")
    if not os.path.isdir(temp_dir):
        return None
    found = []
    for pat in ("*_test*.py", "*.mhtml", "_eval*.txt", "stress*", "_rezip*"):
        for p in glob.glob(os.path.join(temp_dir, pat)):
            found.append(os.path.relpath(p, ROOT))
    for p in glob.glob(os.path.join(temp_dir, "*.py")):
        r = os.path.relpath(p, ROOT)
        if r not in found:
            found.append(r)
    if not found:
        return None
    return {
        "blocking": False,
        "severity": "INFO",
        "title": "temp/ 残留测试产物",
        "detail": "发现 %d 个可能过期的临时文件：%s" % (len(found), ", ".join(found[:8])),
        "todo": "及时清理 temp/ 测试残留；⚠ 清理前先确认这些文件非你手动放入，再删除（遵循 temp/ 管理约定）",
    }


CHECKS = [check_version_consistency, check_readme_version,
          check_changelog_promotion,
          check_dist_staleness, check_temp_residue]


def run_release_checks():
    """返回 (blocking_findings, info_prompts)。"""
    blocking = []
    info = []
    for fn in CHECKS:
        try:
            r = fn()
        except Exception as e:  # 检查自身异常不应阻断门禁，仅提示
            info.append({"blocking": False, "severity": "INFO",
                         "title": "release_check 内部异常",
                         "detail": str(e), "todo": "忽略，或手动核对版本号/CHANGELOG/dist/temp"})
            continue
        if r is None:
            continue
        (blocking if r.get("blocking") else info).append(r)
    return blocking, info


if __name__ == "__main__":
    b, i = run_release_checks()
    for r in b + i:
        print("[%s] %s" % (r["severity"], r["title"]))
        print("  %s" % r["detail"])
        print("  → %s" % r["todo"])
    sys.exit(1 if b else 0)
