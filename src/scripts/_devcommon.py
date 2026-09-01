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


def fail(msg, code=2, tag="dev"):
    sys.stderr.write("[%s] ERROR: %s\n" % (tag, msg))
    sys.exit(code)
