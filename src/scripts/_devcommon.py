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
    """Cross-platform & cross-agent 搜索根（按可靠性降序、去重保序）。

    覆盖：
      - 通用覆盖环境变量 SKILLS_DIR / AGENT_SKILLS_HOME（任意 agent 可指向，跨 agent 最高）
      - 宿主 agent 运行时必导出的配置目录（WorkBuddy/CodeBuddy，非标准安装也可靠）
      - 数据文件夹名 + 用户主目录（WORKBUDDY_DATA_FOLDER_NAME，默认 .workbuddy）
      - 经典 ~/.workbuddy（标准跨平台默认）
      - 已知第三方 agent 技能根（Claude / Cursor / Codex / OpenCode / Aider）
      - 平台专属常见根（裸终端运行、未继承宿主 agent 变量时的兜底）
    """
    roots = []
    # 0) 通用覆盖：任意 agent 可设此指向自家 skills 根（跨 agent 自动探测次高优先级）
    for var in ("SKILLS_DIR", "AGENT_SKILLS_HOME", "AGENT_SKILLS_DIR"):
        v = os.environ.get(var, "").strip()
        if v:
            roots.append(v)
    # 1) 宿主 agent 运行时必导出的配置目录（非标准安装 / 换机器 / 自定义数据目录均可靠）
    for var in ("WORKBUDDY_CONFIG_DIR", "CODEBUDDY_CONFIG_DIR"):
        v = os.environ.get(var, "").strip()
        if v:
            roots.append(os.path.join(v, "skills"))
    # 2) 数据文件夹名 + 用户主目录
    folder = os.environ.get("WORKBUDDY_DATA_FOLDER_NAME", ".workbuddy").strip() or ".workbuddy"
    home = os.path.expanduser("~")
    roots.append(os.path.join(home, folder, "skills"))
    # 3) 经典标准跨平台默认
    roots.append(os.path.join(home, ".workbuddy", "skills"))
    # 4) 已知第三方 agent 技能根（跨 agent 自动探测；嵌套布局由 resolve_deploy_dir bounded walk 兜底）
    for r in (
        os.path.join(home, ".claude", "skills"),
        os.path.join(home, ".claude", "plugins"),       # Claude 插件：plugins/<mkt>/skills/<name>
        os.path.join(home, ".config", "claude", "skills"),
        os.path.join(home, ".cursor", "skills"),
        os.path.join(home, ".codex", "skills"),
        os.path.join(home, ".opencode", "skills"),
        os.path.join(home, ".aider", "skills"),
    ):
        roots.append(r)
    # 5) 平台专属常见根（裸终端运行、未继承宿主 agent 变量时的兜底）
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
    roots.append(os.path.join(home, "Library", "Application Support", "WorkBuddy", "skills"))  # macOS
    # 去重保序
    seen, out = set(), []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _find_skill_dir(root, name, maxdepth=3):
    """在 root 下找 <name>/SKILL.md，返回该技能目录或 None。maxdepth 限深，避免大根拖慢。"""
    direct = os.path.join(root, name)
    if os.path.isfile(os.path.join(direct, "SKILL.md")):
        return direct
    # 嵌套布局（如 agent 插件 plugins/<mkt>/skills/<name>）bounded walk 兜底
    for cur, dirs, _files in os.walk(root):
        cand = os.path.join(cur, name)
        if os.path.isfile(os.path.join(cand, "SKILL.md")):
            return cand
        depth = cur[len(root):].count(os.sep)
        if depth >= maxdepth:
            dirs[:] = []   # 不再下潜，限深
    return None


def resolve_deploy_dir(explicit=None):
    """解析「已部署副本」目录，力求在任意安装位置（含非标准 / 换机器 / 非 WorkBuddy agent）都能定位。

    返回 (path, how)：path 为候选目录，how 为解析方式（便于日志 / 调试）。

    优先级（从高到低）：
      1. SKILL_DEPLOY_DIR  —— 显式按机覆盖（最高，绕过一切自动探测，任意平台/agent 通用）
      2. SKILLS_DIR / AGENT_SKILLS_HOME —— 通用覆盖（任意 agent 可指向自家 skills 根）
      3. WORKBUDDY_CONFIG_DIR / CODEBUDDY_CONFIG_DIR + /skills
         —— 宿主 agent 运行时必导出，非标准安装 / 自定义数据目录 / 换用户名均可靠
      4. ~/<WORKBUDDY_DATA_FOLDER_NAME>/skills/<name> —— 数据文件夹名 + 主目录
      5. ~/.workbuddy/skills/<name> —— 标准跨平台默认
      6. 探测：在候选根（含 Claude/Cursor/Codex/OpenCode/Aider 等第三方 agent + 平台根）中
         找首个含 <name>/SKILL.md 的目录（嵌套布局 bounded walk 兜底）
      若全部未命中：退回标准默认（上层 sync/_verify 会判「not found」并优雅跳过）
    """
    env = (explicit or os.environ.get("SKILL_DEPLOY_DIR", "")).strip()
    if env:
        return os.path.expanduser(env), "SKILL_DEPLOY_DIR"
    for root in _candidate_roots():
        p = _find_skill_dir(root, SKILL_NAME)
        if p:
            return p, "candidate_root:%s" % root
    # 全部未命中：退回标准默认（上层报 not found + 优雅处理）
    p = os.path.join(os.path.expanduser("~"), ".workbuddy", "skills", SKILL_NAME)
    return p, "default(fallback)"


def fail(msg, code=2, tag="dev"):
    sys.stderr.write("[%s] ERROR: %s\n" % (tag, msg))
    sys.exit(code)
