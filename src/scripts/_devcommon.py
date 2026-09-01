#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_devcommon.py —— dev-only 脚本共享的小工具（不进部署副本）。

所有维护者脚本（dev_self_audit / self_validate / make_fixtures / sync_deploy）都位于
src/scripts/，本模块集中放它们重复的「仓库根解析」与「fail 退出」样板，消除四处复制。

部署隔离：本文件刻意不被 sync_deploy 的发布面包含（发布面只含 audit_docs.py +
auditlib/，不含裸 src/scripts/ 文件），且已加入 dev_self_audit 的 DEV_TOOLS 排除集，
避免被 orphan_asset 检查误报为未引用资源。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))        # <root>/src/scripts
ROOT = os.path.dirname(os.path.dirname(HERE))            # <root>
SRC = os.path.join(ROOT, "src")                          # 技能源码根 src/

SKILL_NAME = "skill-doc-audit"                           # 部署副本的技能目录名


def _candidate_roots():
    """WorkBuddy 各已知技能根（跨平台 / 跨安装位置），按可靠性降序、去重保序。

    覆盖：
      - WorkBuddy 运行时必导出的配置目录（最可靠，非标准安装也能定位）
      - 数据文件夹名 + 用户主目录
      - 经典 ~/.workbuddy（标准默认）
      - 平台专属常见根（兜底裸终端运行、未继承 WORKBUDDY_* 变量时）
    """
    roots = []
    # 1) WorkBuddy 运行时必导出的配置目录（非标准安装 / 换机器 / 自定义数据目录均可靠）
    for var in ("WORKBUDDY_CONFIG_DIR", "CODEBUDDY_CONFIG_DIR"):
        v = os.environ.get(var, "").strip()
        if v:
            roots.append(os.path.join(v, "skills"))
    # 2) 数据文件夹名（默认 .workbuddy）+ 用户主目录
    folder = os.environ.get("WORKBUDDY_DATA_FOLDER_NAME", ".workbuddy").strip() or ".workbuddy"
    roots.append(os.path.join(os.path.expanduser("~"), folder, "skills"))
    # 3) 经典标准默认
    roots.append(os.path.join(os.path.expanduser("~"), ".workbuddy", "skills"))
    # 4) 平台专属常见根（裸终端运行、未继承 WORKBUDDY_* 时的兜底）
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(os.path.join(local, "CodeBuddyExtension", "skills"))
        roots.append(os.path.join(local, "WorkBuddy", "skills"))
    appd = os.environ.get("APPDATA")
    if appd:
        roots.append(os.path.join(appd, "WorkBuddy", "skills"))
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        roots.append(os.path.join(xdg, "workbuddy", "skills"))
    roots.append(os.path.expanduser("~/Library/Application Support/WorkBuddy/skills"))  # macOS
    # 去重保序
    seen, out = set(), []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def resolve_deploy_dir(explicit=None):
    """解析「已部署副本」目录，力求在任意安装位置（含非标准 / 换机器）都能定位。

    返回 (path, how)：path 为候选目录，how 为解析方式（便于日志 / 调试）。

    优先级（从高到低）：
      1. SKILL_DEPLOY_DIR  —— 显式按机覆盖（最高，绕过一切自动探测）
      2. WORKBUDDY_CONFIG_DIR / CODEBUDDY_CONFIG_DIR + /skills/<name>
         —— WorkBuddy 运行时必导出，非标准安装 / 自定义数据目录 / 换用户名均可靠
      3. ~/<WORKBUDDY_DATA_FOLDER_NAME>/skills/<name> —— 数据文件夹名 + 主目录
      4. ~/.workbuddy/skills/<name> —— 标准跨平台默认
      5. 探测：在候选根中找首个含 <name>/SKILL.md 的目录（兜底裸终端运行）
      若全部未命中：退回标准默认（上层 sync/_verify 会判「not found」并优雅跳过）
    """
    env = (explicit or os.environ.get("SKILL_DEPLOY_DIR", "")).strip()
    if env:
        return os.path.expanduser(env), "SKILL_DEPLOY_DIR"
    for root in _candidate_roots():
        p = os.path.join(root, SKILL_NAME)
        if os.path.isfile(os.path.join(p, "SKILL.md")):
            return p, "candidate_root:%s" % root
    # 全部未命中：退回标准默认（上层报 not found + 优雅处理）
    p = os.path.join(os.path.expanduser("~"), ".workbuddy", "skills", SKILL_NAME)
    return p, "default(fallback)"


def fail(msg, code=2, tag="dev"):
    sys.stderr.write("[%s] ERROR: %s\n" % (tag, msg))
    sys.exit(code)
