#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bump_audit.py —— post-commit 自动审计：提交若 bump 版本号即触发 dev_self_audit。

为什么需要（消除「补丁号/版本迭代跑审计靠 agent 记忆」的脆弱模式）：
  pre-push 钩子只在推 main 时跑 dev_self_audit，而本项目 push 低频且手动；agent 在多次
  commit（每次 bump 版本）阶段没有早期自动审计反馈，只能靠记忆主动去跑 dev_self_audit。
  本脚本由 post-commit 钩子调用：检测「本次提交是否改变了 src/SKILL.md 的 version」，
  若变了（补丁/次/主版本任一 bump）就自动调用 dev_self_audit.py（全量检查器，含 doc +
  doc-llm agent 模式 + 覆盖 dev 文档 README/CHANGELOG），把审计结果回显给 agent。
  非版本提交（如 dev 工具改动、不 bump 的普通提交）跳过，省性能。

  职责边界：
  - 只做「版本 diff 判定 + 触发审计 + 回显」，不阻断 commit（post-commit 语义：提交已成功，
    审计仅作早期反馈；真正阻断门禁仍是 pre-push 的 --strict）。
  - 带 --no-sync-check：post-commit 已先跑 sync_deploy.py 同步副本，此处只审计、不重复校验同步。
  - dev-only（不进部署副本）；列入 auditlib.core 的 DEV_TOOLS 排除集，避免 orphan_asset 误报。

退出码：0 = 未 bump（静默）或审计完成（审计自身失败不改变本脚本退出码，交由 agent 看回显）；
        2 = git 不可用 / 无法读取版本（优雅跳过，不阻断）。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # <root>/src/scripts
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from _devcommon import ROOT, resolve_python                # noqa: E402

VERSION_RE = re.compile(r'^version:\s*["\']?([0-9][0-9A-Za-z.\-]*)["\']?\s*$', re.M)
SKILL_MD = "src/SKILL.md"


def _git_show_version(ref):
    """读取指定 git ref 的 src/SKILL.md version；ref 不存在 / 文件不存在返回 None。"""
    if not ref:
        return None
    try:
        out = subprocess.run(
            ["git", "show", "%s:%s" % (ref, SKILL_MD)],
            cwd=ROOT, capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return None
    if out.returncode != 0:
        return None
    m = VERSION_RE.search(out.stdout)
    return m.group(1) if m else None


def _ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split(".") if x.isdigit())
    except Exception:  # noqa: BLE001
        return None


def _bump_kind(old, new):
    """返回 bump 级别：'patch' / 'minor' / 'major' / None（未 bump）。"""
    a, b = _ver_tuple(old), _ver_tuple(new)
    if not a or not b or len(a) < 2 or len(b) < 2:
        return None
    if b[0] != a[0]:
        return "major"
    if b[1] != a[1]:
        return "minor"
    if b[2] != a[2]:
        return "patch"
    return None


def main():
    py = resolve_python()
    # 本次提交 = HEAD；上一版 = HEAD^（首次提交无 HEAD^，跳过）
    cur = _git_show_version("HEAD")
    prev = _git_show_version("HEAD^")
    if cur is None:
        print("[bump-audit] 无法读取 src/SKILL.md 版本（HEAD），跳过自动审计。")
        return 0
    if prev is None:
        # 首次提交 / 上一版读不到：无基线可比，静默跳过（避免每次提交都误触发）
        return 0
    if cur == prev:
        return 0  # 版本未变，非版本收口提交 → 静默（省性能）

    kind = _bump_kind(prev, cur)
    kind_cn = {"major": "主版本", "minor": "次版本", "patch": "补丁号"}.get(kind, "版本")
    print("")
    print("=" * 72)
    print("[bump-audit] 检测到%s变动 v%s → v%s —— 自动审计（doc + doc-llm agent 模式 + dev 文档）"
          % (kind_cn, prev, cur))
    print("=" * 72)
    # 调 dev_self_audit（不带 --strict 作早期反馈；带 --no-sync-check 因 post-commit 已 sync）。
    # 输出直接透传给调用方（post-commit 终端 / agent 可见），不阻断 commit。
    try:
        r = subprocess.run(
            [py, os.path.join(HERE, "dev_self_audit.py"), "--no-sync-check"],
            cwd=ROOT)
    except Exception as e:  # noqa: BLE001
        print("[bump-audit] 自动审计调用失败：%s" % e)
        return 0
    print("")
    print("[bump-audit] 自动审计结束（exit=%s）。注：post-commit 审计为早期反馈、不阻断本次提交；"
          "最终门禁为 push 时 pre-push 的 dev_self_audit --strict。" % r.returncode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
