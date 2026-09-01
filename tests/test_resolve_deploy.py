#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_resolve_deploy.py —— 验证 resolve_deploy_dir 跨平台/跨 agent 解析。

不进部署副本；仅 dev 自测用。运行：python tests/test_resolve_deploy.py
"""
import os
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "src", "scripts")
sys.path.insert(0, SCRIPTS)
import _devcommon as dc

NAME = dc.SKILL_NAME
fails = []


def _mk_skill(root, name=NAME):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: %s\n---\n" % name)
    return d


def check(name, cond):
    print(("PASS" if cond else "FAIL") + "  " + name)
    if not cond:
        fails.append(name)


def _clean_env():
    for k in ("SKILL_DEPLOY_DIR", "SKILLS_DIR", "AGENT_SKILLS_HOME", "AGENT_SKILLS_DIR",
              "WORKBUDDY_CONFIG_DIR", "CODEBUDDY_CONFIG_DIR", "WORKBUDDY_DATA_FOLDER_NAME",
              "LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME"):
        os.environ.pop(k, None)


tmp = tempfile.mkdtemp(prefix="resolve_test_")
try:
    # T1: 显式覆盖最高优先（任意平台/agent 通用）
    _clean_env()
    explicit = os.path.join(tmp, "explicit", NAME)
    _mk_skill(explicit)
    p, how = dc.resolve_deploy_dir(explicit=explicit)
    check("T1 SKILL_DEPLOY_DIR 显式覆盖（任意平台/agent 通用）",
          p == explicit and how == "SKILL_DEPLOY_DIR")

    # T2: 通用覆盖 SKILLS_DIR（任意 agent 可指向自家 skills 根）
    _clean_env()
    skills = os.path.join(tmp, "skills_generic")
    _mk_skill(skills)
    os.environ["SKILLS_DIR"] = skills
    p, how = dc.resolve_deploy_dir()
    check("T2 SKILLS_DIR 通用覆盖定位",
          p == os.path.join(skills, NAME) and how.startswith("candidate_root"))

    # T3: 宿主 agent WORKBUDDY_CONFIG_DIR（非标准安装也能定位）
    _clean_env()
    cfg = os.path.join(tmp, "wb_cfg")
    _mk_skill(os.path.join(cfg, "skills"))
    os.environ["WORKBUDDY_CONFIG_DIR"] = cfg
    p, how = dc.resolve_deploy_dir()
    check("T3 WORKBUDDY_CONFIG_DIR 定位",
          p == os.path.join(cfg, "skills", NAME) and how.startswith("candidate_root"))

    # T4: 第三方 agent（Claude 扁平布局），HOME 指向 tmp、清掉宿主变量
    _clean_env()
    home = os.path.join(tmp, "home_claude")
    os.environ["HOME"] = home
    os.environ["USERPROFILE"] = home  # Windows expanduser 亦看 USERPROFILE
    claude_skills = os.path.join(home, ".claude", "skills")
    _mk_skill(claude_skills)
    p, how = dc.resolve_deploy_dir()
    check("T4 跨 agent（Claude 扁平）自动定位",
          p == os.path.join(claude_skills, NAME) and how.startswith("candidate_root"))

    # T5: 第三方 agent 嵌套布局（Claude 插件），bounded walk 兜底
    _clean_env()
    home = os.path.join(tmp, "home_claude2")
    os.environ["HOME"] = home
    os.environ["USERPROFILE"] = home
    plugin = os.path.join(home, ".claude", "plugins", "mkt", "skills")
    _mk_skill(plugin)
    p, how = dc.resolve_deploy_dir()
    check("T5 跨 agent 嵌套（Claude 插件）bounded walk",
          p == os.path.join(plugin, NAME) and how.startswith("candidate_root"))

    # T6: 全部未命中 → 回落默认（优雅跳过，非降级）
    _clean_env()
    home = os.path.join(tmp, "home_empty")
    os.environ["HOME"] = home
    os.environ["USERPROFILE"] = home
    p, how = dc.resolve_deploy_dir()
    check("T6 全未命中回落默认（优雅跳过，非降级）",
          how == "default(fallback)" and p.endswith(os.path.join("skills", NAME)))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

passed = 6 - len(fails)
print("\n%d/%d passed" % (passed, 6))
if fails:
    print("FAILED: " + ", ".join(fails))
    sys.exit(1)
print("ALL PASS")
