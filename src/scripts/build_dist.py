#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可复现地构建 src/dist/skill-doc-audit.zip（SkillHub 发布制品）。

dev-only（不进部署副本）。部署副本用的是 sync_deploy 同步的*实时*文件，
但 `skillhub publish` 发的是这个 zip，所以发布面前文件一变就必须重打包。
本脚本让重打包可复现，并给发布门禁一个可提示的单条命令。

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


def main():
    os.makedirs(os.path.dirname(ZIP_PATH), exist_ok=True)
    items = collect()
    tmp = ZIP_PATH + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for src_rel, arc_rel in items:
            z.write(os.path.join(SRC, src_rel), arc_rel)
    os.replace(tmp, ZIP_PATH)
    print("[build_dist] wrote %s (%d entries)" % (ZIP_PATH, len(items)))
    for s, _ in items:
        print("  + %s" % s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
