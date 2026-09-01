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


def resolve_deploy_dir():
    """解析「已部署副本」目录，尽量与用户名 / 平台 / 设备解耦。

    优先级（从高到低）：
      1. SKILL_DEPLOY_DIR  —— 显式按机覆盖（CI、非标准安装、换机器迁移）
      2. WORKBUDDY_HOME    —— 若 WorkBuddy 根与 ~/.workbuddy 不同
      3. ~/.workbuddy/skills/<SKILL_NAME>  —— 标准跨平台默认
         （~ 按当前用户展开，不写死盘符 / 用户名，Windows/Linux/macOS 通用）
    """
    env = os.environ.get("SKILL_DEPLOY_DIR", "").strip()
    if env:
        return env
    wb_home = os.environ.get("WORKBUDDY_HOME", "").strip()
    if wb_home:
        return os.path.join(wb_home, "skills", SKILL_NAME)
    return os.path.join(os.path.expanduser("~"), ".workbuddy", "skills", SKILL_NAME)


def fail(msg, code=2, tag="dev"):
    sys.stderr.write("[%s] ERROR: %s\n" % (tag, msg))
    sys.exit(code)
