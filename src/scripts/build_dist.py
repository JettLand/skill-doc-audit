#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可复现地构建 src/dist/skill-doc-audit.zip（SkillHub 发布制品）。

dev-only（不进部署副本）。部署副本用的是 sync_deploy 同步的*实时*文件，
但 `skillhub publish` 发的是这个 zip，所以发布面前文件一变就必须重打包。

本脚本让重打包可复现，并给发布门禁一个可提示的单条命令。
**自 v1.25.8 起，zip 不再入库**（视为生成产物，见 .gitignore），由
`sync_deploy.py` 在每次提交后自动调用 `ensure_fresh()` 重建，agent 无需手动重打包；
`release_check.py::check_dist_staleness` 仅作为「同步钩子未跑」时的兜底守卫。

发布面（须与 sync_deploy.SYNC_FILES + SYNC_DIRS 一致）：
  SKILL.md
  scripts/audit_docs.py
  scripts/auditlib/**   （仅 .py）
  references/checkers.md
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))   # <root>/src/scripts
SRC = os.path.dirname(HERE)                           # <root>/src
ZIP_PATH = os.path.join(SRC, "dist", "skill-doc-audit.zip")

FILES = [
    ("SKILL.md", "SKILL.md"),
    ("scripts/audit_docs.py", "scripts/audit_docs.py"),
    ("references/checkers.md", "references/checkers.md"),
]

# 发布面根（用于「是否过期」判定：任一文件/目录比 zip 新则需重建）
SURFACE_ROOTS = [
    os.path.join(SRC, "SKILL.md"),
    os.path.join(SRC, "scripts", "audit_docs.py"),
    os.path.join(SRC, "references", "checkers.md"),
    os.path.join(SRC, "scripts", "auditlib"),
]


def collect():
    out = list(FILES)
    adir = os.path.join(SRC, "scripts", "auditlib")
    for root, dirs, files in os.walk(adir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".pyc"):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, SRC).replace(os.sep, "/")
            out.append((rel, rel))
    return out


def build():
    """强制重建 zip（覆盖写）。返回 (zip_path, entry_count)。"""
    os.makedirs(os.path.dirname(ZIP_PATH), exist_ok=True)
    items = collect()
    tmp = ZIP_PATH + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for src_rel, arc_rel in items:
            z.write(os.path.join(SRC, src_rel), arc_rel)
    os.replace(tmp, ZIP_PATH)
    return ZIP_PATH, len(items)


def _surface_newest_mtime():
    newest = 0.0
    for r in SURFACE_ROOTS:
        if os.path.isfile(r):
            newest = max(newest, os.path.getmtime(r))
        elif os.path.isdir(r):
            for root, dirs, files in os.walk(r):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    if f.endswith(".pyc"):
                        continue
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
    return newest


def ensure_fresh():
    """若 zip 缺失或早于发布面源码，则重建；否则跳过。

    返回 True 表示本次发生了重建，False 表示本来就是最新的（无需动）。
    供 sync_deploy 在同步前调用，保证部署副本 / SkillHub 发布永远基于最新 src。
    """
    need = False
    if not os.path.exists(ZIP_PATH):
        need = True
    else:
        zmt = os.path.getmtime(ZIP_PATH)
        if _surface_newest_mtime() > zmt + 1.0:  # 1s 容差
            need = True
    if not need:
        return False
    path, n = build()
    print("[build_dist] rebuilt %s (%d entries)" % (path, n))
    return True


def main():
    path, n = build()
    print("[build_dist] wrote %s (%d entries)" % (path, n))
    for s, _ in collect():
        print("  + %s" % s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
