#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布就绪检查：让同步钩子/本地CI 对 agent 发出「待办提示」，减少对记忆文件的依赖。

为什么需要（长期项目痛点）：
  版本迭代后有一批「必须由 agent 执行」的收尾操作——把 sources.py 的 User-Agent
  同步为 SKILL.md 版本号、把 CHANGELOG「未发布改动」收口为版本节、清理 temp/ 测试残留。
  这些步骤若只靠 agent 记忆，极易漏做并造成隐蔽漂移（例如工具带着陈旧版本号自报给远端
  服务器）。本模块把这类步骤固化为可重复检查，由 dev_self_audit.py（本地 pre-push 钩子
  与远程 dev-qa CI 都调用它）统一输出 `[agent-todo]` 提示块，agent 无需回忆即可照做。

  注：**不存在 dist 重打包步骤**——市场上架时自行重打包（`skillhub publish <技能目录>`），
  本仓库不再产出 `src/dist/*.zip`；本地 zip 若残留在被发布目录内反而会被市场拒收
  （400「不允许的文件类型」）。原 `check_dist_staleness` 兜底守卫随之移除。

  阻断项（版本不一致 / CHANGELOG 未收口 / 版本变动须做的文档自审计与上架授权）以
  ERROR/WARN/必须 返回，使 dev_self_audit 在 --strict 下失败、拦下 push；非阻断项
  （temp 残留 / 过时备份 / 市场基准实测建议）仅作 INFO/建议 提示，不阻塞常规提交与推送。
"""
import os
import re
import sys
import glob
import subprocess

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


def check_temp_residue():
    """temp/ 存放临时测试产物；另须清理开发期产生的过时备份(.bak)。

    过时产物：审计工具改动 SKILL.md 时会生成 SKILL.md.bak.<n> 备份（默认保留最近 3 个，
    见项目约定），更早的应清理；这些文件已被 .gitignore 忽略、不应入库。
    """
    found = []
    # 1) temp/ 测试残留
    temp_dir = os.path.join(ROOT, "temp")
    if os.path.isdir(temp_dir):
        for pat in ("*_test*.py", "*.mhtml", "_eval*.txt", "stress*", "_rezip*"):
            for p in glob.glob(os.path.join(temp_dir, pat)):
                found.append(os.path.relpath(p, ROOT))
        for p in glob.glob(os.path.join(temp_dir, "*.py")):
            r = os.path.relpath(p, ROOT)
            if r not in found:
                found.append(r)
    # 2) 过时备份(.bak / .bak.*)：开发期工具生成的 SKILL.md.bak.<n> 等
    for base in (ROOT, SRC, os.path.join(SRC, "scripts")):
        for p in glob.glob(os.path.join(base, "*.bak")):
            found.append(os.path.relpath(p, ROOT))
        for p in glob.glob(os.path.join(base, "*.bak.*")):
            found.append(os.path.relpath(p, ROOT))
    if not found:
        return None
    return {
        "blocking": False,
        "severity": "INFO",
        "title": "temp/ 残留测试产物与过时备份(.bak)",
        "detail": "发现 %d 个可能过期的临时/备份文件：%s" % (len(found), ", ".join(found[:8])),
        "todo": "及时清理 temp/ 测试残留与 *.bak 备份（*.bak 默认保留最近 3 个、更早的删除）；"
                "⚠ 清理前先确认这些文件非你手动放入，再删除（遵循 temp/ 管理约定）",
    }




def check_dev_workbench_usage():
    """常驻 [建议] 开发工作流提醒：开发面改动优先用 dev_workbench.py。

    仅在检测到未提交改动触及「开发面文件」（SKILL.md / src/scripts / src/references /
    CHANGELOG.md / DEVELOPMENT.md / README.md）时提示，避免干净树发布时的噪音。
    返回 finding dict 或 None。非阻断、不升退出码。
    """
    dev_paths = ("src/SKILL.md", "src/scripts", "src/references",
                 "CHANGELOG.md", "DEVELOPMENT.md", "README.md")
    touched = set()

    def _match(p):
        return any(p.startswith(d) for d in dev_paths)

    try:
        out = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                              capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                p = line[3:].strip()
                if _match(p):
                    touched.add(p)
    except Exception:
        pass
    if not touched:
        return None
    return {
        "blocking": False,
        "severity": "建议",
        "title": "开发期改动请按边界使用 dev_workbench.py（提交除外）",
        "detail": "检测到未提交改动涉及开发面文件：%s" % "、".join(sorted(touched)[:6]),
        "todo": "开发面改动按以下边界使用 dev_workbench.py（提交不属其职责，勿混用）：\n"
                "• 版本 bump / 改 SKILL.md·CHANGELOG·脚本：用 `python src/scripts/dev_workbench.py "
                "bump --version X --section-file <tpl>` / `patch --old-file/--new-file` / `verify`；"
                "多字节与转义内容一律走 --*-file（规避 Edit 工具 phantom success 与参数传输层丢参），"
                "纯 ASCII 简单串可用内联 --old/--new。\n"
                "• 只读核验（版本锚点一致性 / 部署副本同步 / git 状态 / 仓库内 grep）：用 "
                "`dev_workbench.py doctor` / `status` / `grep`，勿用裸 Bash `git status` 或 Read/Grep。\n"
                "• 提交：仍走 `dev_commit.py`（它会触发 post-commit 同步钩子）；也可经薄封装入口 "
                "`python src/scripts/dev_workbench.py commit -m \"...\"`，但 commit 本身不属于 "
                "dev_workbench，严禁裸 `git commit`。",
    }


CHECKS = [check_version_consistency,
          check_changelog_promotion,
          check_temp_residue]


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
                         "detail": str(e), "todo": "忽略，或手动核对版本号/CHANGELOG/temp"})
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
