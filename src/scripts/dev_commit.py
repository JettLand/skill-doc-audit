#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dev_commit.py — 静态本地提交助手（减少 agent 对 git 机制的记忆负担）

用法：
  python src/scripts/dev_commit.py -m "有意义的提交说明" [file ...]
  python src/scripts/dev_commit.py -m "..." --all

设计原则（贴合本项目发布纪律）：
  - 强制显式 message（杜绝 auto: 低质 message，保留「提交有意图」的纪律）
  - 默认只暂存已跟踪文件的改动（git add -u），避免误纳临时 / 敏感未跟踪文件
  - 新增文件需显式传参或 --all（--all 仍受 .gitignore 约束，不会纳忽略项）
  - 不提供 --no-verify：commit 必然触发 post-commit 钩子自动同步部署副本
  - 空提交保护：暂存区无任何改动时直接报错退出，绝不创建空 commit

注意：本脚本属 dev-only 工具，已列入 dev_self_audit 的 DEV_TOOLS 排除集，不进部署副本扫描。
"""
import argparse
import os
import subprocess
import sys

# 仓库根 = src/scripts/ 上溯两级
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run(cmd):
    # 显式 UTF-8 解码：钩子/脚本输出为 UTF-8，Windows 默认按区域编码（GBK）读
    # 会触发 UnicodeDecodeError（v1.27.21 提交回显钩子 stderr 中文时实测复现）；
    # errors="replace" 保证极端字节序列也不中断提交流程。
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser(description="静态本地提交助手（dev-only）")
    ap.add_argument("-m", "--message", required=True, help="提交说明（必填，须有意义）")
    ap.add_argument("files", nargs="*",
                    help="显式要暂存的文件 / 路径（默认 git add -u 仅已跟踪改动）")
    ap.add_argument("--all", action="store_true",
                    help="暂存所有改动（git add -A，仍受 .gitignore 约束；用于新增文件也一并提交时）")
    args = ap.parse_args()

    if not args.message.strip():
        print("[dev_commit] 错误：message 不能为空", file=sys.stderr)
        return 2

    # 1) 暂存
    if args.files:
        res = _run(["git", "add", "--"] + args.files)
    elif args.all:
        res = _run(["git", "add", "-A"])
    else:
        res = _run(["git", "add", "-u"])
    if res.returncode != 0:
        print("[dev_commit] git add 失败：\n" + (res.stderr or res.stdout).strip(),
              file=sys.stderr)
        return 2

    # 2) 空提交保护：git diff --cached --quiet 在「无暂存改动」时返回 0
    diff = _run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("[dev_commit] 没有可提交的改动（暂存区为空），已跳过，未创建空 commit。")
        return 0

    # 3) 提交（触发 post-commit 钩子同步部署副本）
    cm = _run(["git", "commit", "-m", args.message])
    if cm.returncode != 0:
        print("[dev_commit] git commit 失败：\n" + (cm.stderr or cm.stdout).strip(),
              file=sys.stderr)
        return 2

    # 4) 回显结果。post-commit 钩子的同步回执（[sync_deploy] ... verify: OK/MISMATCH）
    #    随 git commit 输出被 capture 吞掉，必须在此原样回显——否则 agent/维护者看不到
    #    同步校验结果，只能退化成手动核验部署副本（本修复的动机）。
    sha = _run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    print("[dev_commit] 已提交 %s" % sha)
    print("  message: %s" % args.message)
    hook_out = ((cm.stdout or "") + (cm.stderr or "")).strip()
    if hook_out:
        print("  post-commit 钩子输出：")
        for line in hook_out.splitlines():
            print("    " + line)
    else:
        print("  post-commit 钩子无输出（同步可能未触发；请检查 git config core.hooksPath）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
