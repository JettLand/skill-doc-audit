#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync release artifacts from repo `src/` to the installed deployment copy.

This is a **dev-only maintainer tool** (NOT part of the distributed skill; it is
excluded from `src/dist/skill-doc-audit.zip` and from the deployment copy itself).

Purpose
-------
Keep the live installed skill at
    C:/Users/admin/.workbuddy/skills/skill-doc-audit
byte-identical to the committed source in `src/`, so that every local commit
automatically refreshes the deployed skill. It is wired as a git `post-commit`
hook (see `hooks/post-commit` + `git config core.hooksPath ../hooks`).

What gets synced (the release surface)
--------------------------------------
- src/SKILL.md                     -> <deploy>/SKILL.md
- src/scripts/audit_docs.py        -> <deploy>/scripts/audit_docs.py
- src/scripts/auditlib/**          -> <deploy>/scripts/auditlib/**
- src/references/checkers.md       -> <deploy>/references/checkers.md
- src/dist/skill-doc-audit.zip     -> <deploy>/dist/skill-doc-audit.zip

What is deliberately EXCLUDED (dev-only / not for deployment)
------------------------------------------------------------
- src/scripts/make_fixtures.py, src/scripts/self_validate.py  (dev tools)
- src/tests/                                                 (fixtures + golden)
- __pycache__ / *.pyc                                       (regenerated at runtime)

Safety
------
- Only copies the explicit release surface above; never deletes files in the
  deploy dir that are not part of the surface (so a stale dev file would be
  left behind rather than removed — manual review if you ever add dev files).
- Cleans `__pycache__` inside the deploy copy after sync.
- Verifies byte-consistency at the end and prints OK / MISMATCH.

Usage
-----
    python src/scripts/sync_deploy.py            # sync + verify
    SKILL_DEPLOY_DIR=/path/to/deploy python ...  # override target
"""
import os
import sys
import shutil
import hashlib
import filecmp

HERE = os.path.dirname(os.path.abspath(__file__))   # .../src/scripts
SRC = os.path.dirname(HERE)                          # .../src  (skill root)
ROOT = os.path.dirname(SRC)                           # repo root (unused)

DEP = os.environ.get(
    "SKILL_DEPLOY_DIR",
    r"C:/Users/admin/.workbuddy/skills/skill-doc-audit",
)

# (relative-in-src, relative-in-deploy) — file-level release surface
SYNC_FILES = [
    ("SKILL.md", "SKILL.md"),
    ("scripts/audit_docs.py", "scripts/audit_docs.py"),
    ("references/checkers.md", "references/checkers.md"),
    ("dist/skill-doc-audit.zip", "dist/skill-doc-audit.zip"),
]
# (relative-in-src, relative-in-deploy) — directory-level release surface
SYNC_DIRS = [
    ("scripts/auditlib", "scripts/auditlib"),
]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def _sync_file(src, dst):
    """Copy if missing or differing. Return True if a copy happened."""
    if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _sync_tree(src_dir, dst_dir):
    n = 0
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(root, src_dir)
        tdir = os.path.join(dst_dir, rel)
        os.makedirs(tdir, exist_ok=True)
        for f in files:
            if f.endswith(".pyc"):
                continue
            sp = os.path.join(root, f)
            dp = os.path.join(tdir, f)
            if _sync_file(sp, dp):
                n += 1
    return n


def _clean_pycache(base):
    for root, dirs, _ in os.walk(base):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(root, "__pycache__"))


def _verify():
    # dist zip byte-identical
    a = os.path.join(SRC, "dist/skill-doc-audit.zip")
    b = os.path.join(DEP, "dist/skill-doc-audit.zip")
    if os.path.exists(a) and os.path.exists(b) and _sha256(a) != _sha256(b):
        return False
    for s, d in SYNC_FILES + SYNC_DIRS:
        sp, dp = os.path.join(SRC, s), os.path.join(DEP, d)
        if os.path.isdir(sp):
            for root, _, files in os.walk(sp):
                if "__pycache__" in root:
                    continue
                for f in files:
                    if f.endswith(".pyc"):
                        continue
                    rel = os.path.relpath(os.path.join(root, f), sp)
                    tp = os.path.join(dp, rel)
                    if not os.path.exists(tp):
                        return False
                    if not filecmp.cmp(os.path.join(root, f), tp, shallow=False):
                        return False
        else:
            if not (os.path.exists(dp) and filecmp.cmp(sp, dp, shallow=False)):
                return False
    return True


def main():
    if not os.path.isdir(DEP):
        print("[sync_deploy] deploy dir not found: %s" % DEP)
        print("[sync_deploy] skip (set SKILL_DEPLOY_DIR to override)")
        return 0
    copied = 0
    for s, d in SYNC_FILES:
        sp, dp = os.path.join(SRC, s), os.path.join(DEP, d)
        if not os.path.exists(sp):
            print("[sync_deploy] WARN src missing: %s" % s)
            continue
        if _sync_file(sp, dp):
            copied += 1
    for s, d in SYNC_DIRS:
        sdir, ddir = os.path.join(SRC, s), os.path.join(DEP, d)
        if not os.path.isdir(sdir):
            print("[sync_deploy] WARN src dir missing: %s" % s)
            continue
        copied += _sync_tree(sdir, ddir)
    _clean_pycache(os.path.join(DEP, "scripts"))
    ok = _verify()
    verb = ("synced %d file(s)" % copied) if copied else "already up-to-date"
    print("[sync_deploy] %s; verify: %s" % (verb, "OK" if ok else "MISMATCH"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
