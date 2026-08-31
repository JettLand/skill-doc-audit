#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_docs.py —— 技能静态体检（零第三方依赖）

设计定位：**只做扫描与备份，不做自动改写**。
机器只能可靠判定「存在性 / 枚举 / 语法」类偏差；而「描述是否准确反映行为」
属语义判断，必须由执行本技能的 AI 阅读代码后决定。脚本负责把事实摆出来，
改由 AI 完成。

分层架构（方案 C）：
  - 常驻核心（默认开）：doc      —— 文档与实际代码的一致性（死路径/失效参数/退出码口径/版本缺失）
  - 插件式（--check 启用，可重复）：
      structure  结构体检 + 元信息（frontmatter/name/description/version/引用完整性/TODO/硬编码路径）
      security   安全红线静态子集（硬编码密钥/混淆/路径穿越/eval 外部内容/注入句式）
      runtime    脚本可运行性（py_compile 语法、脚本引用存在性、能力预检清单）
      deps      依赖与平台声明（外部 CLI 调用未声明 / Windows 专属 API 未标注平台）
      deadcode   死代码检测（未使用定义/导入、不可达代码、孤儿资源文件；运行前询问精度模式）
      portability 跨平台可移植性（硬编码绝对路径/cwd依赖/平台专属shell/解释器锁/编码分隔符假设/Agent平台耦合；按 SKILL.md 的 target_platform 字段豁免对应平台项）
  - --all-checks  启用全部检查器（含 deadcode；已装 vulture 则自动高精度，否则运行前询问 vulture/ast/skip 模式）
  检查器只扫描不改写；description 四要素、制作质量评分等需语义判断的项仅给提示(INFO)。

退出码：0=未发现 ERROR（--strict 下还需无 WARN）；1=发现 ERROR 或（--strict 下）WARN；2=参数或路径错误

用法：
  python audit_docs.py --skill <技能目录>                  # 仅运行常驻 doc 检查器
  python audit_docs.py --skill <技能目录> --check structure # doc + structure
  python audit_docs.py --skill <技能目录> --all-checks     # 全部检查器（含 deadcode，运行前询问模式）
  python audit_docs.py --skill <技能目录> --check deadcode # 仅死代码检查
  python audit_docs.py --skill <目录> --deadcode-mode vulture   # 指定精度模式，跳过交互
  python audit_docs.py --all --all-checks                  # 审计全部技能（全检查器）
  python audit_docs.py --skill <目录> --backup             # 审计前先备份 SKILL.md
  python audit_docs.py --skill <目录> --json               # JSON 机读输出（同时仍打印可读报告）
  python audit_docs.py --skill <目录> --timeout 60         # 整体超时 60 秒，超时优雅终止（非卡死）
  python audit_docs.py --skill <目录> --max-file-size 2000000  # 超过此字节的文件跳过扫描
  python audit_docs.py --source github --ref owner/repo --all-checks     # 克隆 GitHub 仓库并审计（可 @分支）
  python audit_docs.py --source github --ref https://github.com/owner/repo @dev --check structure
  python audit_docs.py --source skillhub --ref <slug> --all-checks       # 经 skillhub CLI 拉取集市技能并审计
  python audit_docs.py --source github --ref owner/repo --keep-temp      # 保留克隆临时目录供排查
  python audit_docs.py --skill <目录> --check portability                # 仅跨平台可移植性；SKILL.md 声明 target_platform: windows 可豁免对应 Unix 专有项
"""

import argparse
import ast
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import _thread
import urllib.request

SKILLS_ROOT = os.path.expanduser("~/.workbuddy/skills")
BACKUP_LIMIT = 3  # 同一技能 SKILL.md 最多保留的备份数，防止频繁迭代产生过多 .bak 文件
SKIP_DIRS = {"__pycache__", "dist", "state", "logs", "node_modules",
             ".git", "evals", ".workbuddy", "archive", "vendor"}
CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".go", ".rs", ".java",
             ".c", ".cpp", ".h", ".rb", ".php", ".swift", ".kt", ".lua",
             ".sh", ".ps1", ".json")
MAX_FILE_SIZE = 2_000_000  # 单文件超过此字节数跳过扫描，避免超大文件拖慢/卡死

# ---- doc 检查器正则 ----
FILE_REF_RE = re.compile(r"`([\w./\\-]+\.(?:py|js|jsx|ts|tsx|vue|go|rs|java|c|cpp|h|rb|php|swift|kt|lua|json|log|md|lnk|sh|ps1|asar|txt))`")
FLAG_RE = re.compile(r"(--[a-z][a-z0-9-]{2,})")
IDENT_RE = re.compile(r"`(_?[a-z][a-z0-9]*_[a-z0-9_]+)`")
DOC_EXIT_RE = re.compile(r"^\|\s*`(\d+)`\s*\|", re.M)
CODE_EXIT_RE = re.compile(r"return\s+(\d+)\s*$", re.M)
STATUS_RE = re.compile(r"write_result\(\s*[\"']([a-z_]+)[\"']")
VERSION_RE = re.compile(r"^version:\s*[\"']?([0-9][0-9A-Za-z.\-]*)[\"']?\s*$", re.M)

# ---- security 检查器正则 ----
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|access[_-]?key|akia[0-9a-z]{16})"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}")
EVAL_EXT_RE = re.compile(r"\b(eval|exec)\s*\(\s*(?![\"'\"])")
TRAVERSAL_RE = re.compile(r"\.\./|\.\.\\")
# 路径穿越检测：上下文感知，避免「上下文盲」误报。
# 排除：整行注释 / 文档 URL（如 https://.../v2 中的 .../）/ 自引用资源定位（如定位 app.asar 的合法上溯）。
SELF_REF_TOKENS = ("__file__", "__dirname", "os.path.dirname", "os.path.abspath",
                    "os.path.realpath", "app.asar", ".asar", "resource_path",
                    "install_dir", "base_dir", "root_dir", "APP_DIR", "APP_ROOT",
                    "pkg_root", "sys.prefix", "site-packages")
WILDCARD_RM_RE = re.compile(r"rm\s+-rf\s+\*")
INJECT_RE = re.compile(r"(忽略|无视|disregard)\s*(the\s*)?(above|previous|上述|以上|前面)", re.I)

# 扫描时跳过「检测逻辑内部行」，避免检查器扫描自身源码时把正则字面量 / 判断语句当成漏洞
SCAN_SKIP_TOKENS = ("re.compile", "re.search", "re.match", "re.findall",
                    '"eval(', "subprocess|os.system")

# Phase 8 供应链安全启发式（跨 Agent 生态级批量审计用）：硬编码远端端点 / 动态导入
ENDPOINT_RE = re.compile(r"https?://([\w.\-]+)")
# 排除明显文档 / 示例 / SDK 主机，避免把文档链接误报为硬编码端点
# 含 url 源归一化的规范主机（如 raw.githubusercontent.com），非真实可被篡改的远端端点
EXCLUDE_ENDPOINT_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org",
    "docs.github.com", "github.com", "w3.org", "developer.mozilla.org",
    "python.org", "nodejs.org", "developer.mozilla.org", "docs.python.org",
    "raw.githubusercontent.com", "raw.githack.com", "gitee.com", "raw.gitee.com",
    "gitlab.com", "raw.gitlab.com", "codeload.github.com", "objects.githubusercontent.com",
}
DYNAMIC_IMPORT_RE = re.compile(
    r"(importlib\s*\.\s*import_module|__import__\s*\(|getattr\s*\(\s*(sys\s*\.\s*modules|__import__))")


def _security_irrelevant(line):
    """安全扫描上下文感知跳过：注释 / 文档 URL / 自引用资源上溯 不视为漏洞。

    解决「上下文盲」误报——legacy 规则凡匹配即告警，会把注释、文档 URL
    （如 https://.../v2 的 .../）、合法目录上溯（定位 app.asar 等）错判为漏洞。
    统一作用于 security 检查器内所有正则，降低误报。
    """
    s = line.strip()
    if s.startswith(("#", "//", "/*", "*", "<!--")):
        return True
    if "://" in line:
        return True
    if any(tok in line for tok in SELF_REF_TOKENS):
        return True
    return False

SEVERITY_ERROR = "ERROR"
SEVERITY_WARN = "WARN"
SEVERITY_INFO = "INFO"

# 检查项分类的中文标签。
# 机器标识符（如 DEAD_PATH）稳定用于 --json 机读与跨版本比对；
# 中文标签仅用于人类可读报告，使每一条发现自解释、无需查表。
# 新增检查项时务必在此登记，否则报告会回退为显示机器码本身。
CATEGORY_LABELS = {
    # doc：文档一致性
    "DEAD_PATH": "死路径（文档引用文件已不存在）",
    "EXTERNAL_REF": "外部裸文件名引用",
    "DEAD_FLAG": "失效命令行参数",
    "EXIT_DOC_ONLY": "文档独有退出码（代码未返回）",
    "EXIT_CODE_ONLY": "代码独有退出码（文档未列）",
    "UNKNOWN_IDENT": "未知标识符",
    "VERSION_MISSING": "缺少版本声明",
    "DOC_ENUM_DRIFT": "文档枚举/集合与代码不一致",
    "DOC_COUNT_DRIFT": "文档数量声明与代码不一致",
    "DOC_CAPABILITY_DRIFT": "文档声称的能力在代码中无对应实现",
    "B_STATUS": "运行状态枚举（供 AI 复核）",
    "B_CONFIG": "配置项枚举（供 AI 复核）",
    # structure：结构体检 + 元信息
    "name_mismatch": "名称不一致",
    "version_missing": "版本缺失",
    "name_missing": "名称缺失",
    "license_missing": "许可证缺失",
    "desc_length": "描述长度异常",
    "desc_four": "描述四要素不全",
    "desc_missing": "描述缺失",
    "h1_name_mismatch": "标题与名称不一致",
    "no_frontmatter": "缺少 frontmatter",
    "too_long": "文档过长",
    "broken_ref": "加载式引用失效",
    "hardcoded_path": "硬编码绝对路径",
    "todo_marker": "待办标记",
    "placeholder": "占位/历史文本",
    "oversize_doc": "文档过大",
    "oversize_file": "文件过大已跳过",
    # security：安全红线静态子集
    "hardcoded_secret": "疑似硬编码密钥",
    "obfuscation": "疑似混淆编码",
    "dynamic_exec": "动态执行",
    "path_traversal": "路径穿越",
    "destructive_wildcard": "危险通配删除",
    "injection_phrasing": "疑似注入句式",
    "secret_in_doc": "文档含疑似密钥",
    "hardcoded_endpoint": "硬编码远端端点",
    "dynamic_import": "动态导入",
    # runtime：脚本可运行性
    "py_syntax": "Python 语法错误",
    "py_check_fail": "语法校验失败",
    "script_ref_missing": "脚本引用缺失",
    "capability": "能力预检（静态列举）",
    # deps：依赖与平台声明
    "undeclared_cli": "未声明外部 CLI",
    "platform_undeclared": "未声明运行平台",
    # deadcode：死代码检测（运行前按 --deadcode-mode 询问精度）
    "unused_def": "未使用的定义",
    "unused_import": "未使用的导入",
    "unreachable": "不可达代码",
    "orphan_asset": "孤立资源文件",
    "vulture": "高精度死代码（可选）",
    # portability：跨平台可移植性（零依赖静态分析；默认进入 --all-checks；按 target_platform 字段豁免）
    "hardcoded_abs_path": "硬编码绝对路径",
    "cwd_dependence": "启动目录依赖(os.getcwd)",
    "platform_shell": "平台专属 shell/命令",
    "interpreter_lock": "解释器/运行时锁",
    "encoding_sep": "编码/路径分隔符假设",
    "agent_coupling": "Agent 平台耦合",
}


# --------------------------------------------------------------------------- #
# Vector 1 (v1.21.0)：doc 检查器「内容漂移」结构化声明交叉校验用常量
# --------------------------------------------------------------------------- #
# deadcode 精度模式权威集合：同时供 argparse choices 与 doc 漂移校验使用（单一真相源）
DEADCODE_MODES = ("ask", "vulture", "ast", "skip")
# 文档声称的检查器数量："(N) 个检查器"
DOC_CHECKER_COUNT_RE = re.compile(r"(\d+)\s*个\s*检查器")
# 文档以大括号枚举 deadcode 模式：{ask,vulture,ast,skip}
DOC_MODE_BRACE_RE = re.compile(r"\{([a-z]+(?:,[a-z]+)*)\}")
# 文档以斜杠枚举 deadcode 模式：`ask/vulture/ast/skip`
DOC_MODE_SLASH_RE = re.compile(r"`([a-z]+(?:/[a-z]+){1,})`")
# 能力声明动词（文档声称提供/支持/默认/自动/移除/弃用/停用/废弃/新增/包含某能力）
CAP_VERB_RE = re.compile(r"提供|支持|默认|自动|移除|弃用|停用|废弃|新增|包含")


def category_cn(category):
    """返回检查项的中文可读标签；未登记时回退为机器标识符本身。"""
    return CATEGORY_LABELS.get(category, category)


# --------------------------------------------------------------------------- #
# Finding 模型
# --------------------------------------------------------------------------- #
def finding(checker, severity, category, message, file=None, line=None, suggestion=None):
    return {
        "checker": checker,
        "severity": severity,
        "category": category,
        "category_cn": category_cn(category),
        "message": message,
        "file": file,
        "line": line,
        "suggestion": suggestion,
    }


# --------------------------------------------------------------------------- #
# 通用辅助
# --------------------------------------------------------------------------- #
def collect_code(skill_dir):
    """收集技能目录下所有可作为基准的代码/配置文件内容（不含 SKILL.md）。

    返回 (files, skipped)：files 为 路径->内容；skipped 为因超过 MAX_FILE_SIZE
    而被跳过的文件相对路径列表（避免超大生成物/资源文件拖慢或卡死扫描）。
    """
    files = {}
    skipped = []
    for root, dirs, names in os.walk(skill_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for n in names:
            if n.endswith(CODE_EXT):
                p = os.path.join(root, n)
                rel = os.path.relpath(p, skill_dir)
                if rel == "SKILL.md":
                    continue
                try:
                    size = os.path.getsize(p)
                except OSError:
                    continue
                if size > MAX_FILE_SIZE:
                    skipped.append(rel)
                    continue
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        files[rel] = fh.read()
                except Exception:
                    pass
    return files, skipped


def resolve_exists(skill_dir, ref, scripts_dir):
    cand = ref.replace("/", os.sep).replace("\\", os.sep)
    paths = [
        os.path.join(skill_dir, cand),
        os.path.join(scripts_dir, os.path.basename(cand)),
        os.path.join(skill_dir, "scripts", cand),
    ]
    return any(os.path.exists(p) for p in paths)


def prune_backups(doc_path, limit):
    """生成新备份前，将同一 SKILL.md 的 .bak.* 文件裁剪到 limit-1 个（删除最旧），
    使生成新备份后总量不超过 limit。文件名含时间戳，字典序即时间序。"""
    if limit <= 0:
        return
    existing = sorted(glob.glob(doc_path + ".bak.*"))
    while len(existing) >= limit:
        oldest = existing.pop(0)
        try:
            os.remove(oldest)
        except OSError:
            break


# --------------------------------------------------------------------------- #
# 检查器：doc（常驻核心，已验证）
# --------------------------------------------------------------------------- #
def check_doc(ctx):
    doc = ctx["doc"]
    code = ctx["code"]
    blob = ctx["blob"]
    scripts_dir = ctx["scripts_dir"]
    findings = []

    # A1 死路径 / 技能外裸文件名
    for m in FILE_REF_RE.finditer(doc):
        ref = m.group(1)
        if resolve_exists(ctx["skill_dir"], ref, scripts_dir):
            continue
        if ref.startswith(("http://", "https://")):
            continue
        if "/" in ref or "\\" in ref:
            findings.append(finding("doc", SEVERITY_ERROR, "DEAD_PATH",
                                    "文档里写的路径 %s 在当前技能目录中找不到" % ref, file="SKILL.md",
                                    suggestion="修正路径或补充文件"))
        else:
            findings.append(finding("doc", SEVERITY_INFO, "EXTERNAL_REF",
                                    "裸文件名引用，可能指向技能外文件，需人工确认: %s" % ref,
                                    file="SKILL.md"))

    # A2 失效参数（仅本技能 python 命令行示例中的参数）
    for m in FLAG_RE.finditer(doc):
        flag = m.group(1)
        ls = doc.rfind("\n", 0, m.start()) + 1
        le = doc.find("\n", m.end())
        line = doc[ls:le if le != -1 else len(doc)]
        if "python" not in line.lower():
            continue
        if flag not in blob:
            findings.append(finding("doc", SEVERITY_ERROR, "DEAD_FLAG",
                                    "文档命令行参数在代码中无实现: %s" % flag, file="SKILL.md",
                                    suggestion="实现该参数或更正文档示例"))

    # A3 退出码口径
    doc_exits = set(DOC_EXIT_RE.findall(doc))
    code_exits = set(CODE_EXIT_RE.findall(blob))
    deprecated = set()
    for line in doc.splitlines():
        m2 = re.match(r"^\|\s*`(\d+)`\s*\|", line)
        if m2 and re.search(r"已弃用|已停用|已废弃|已移除|deprecated", line, re.I):
            deprecated.add(m2.group(1))
    for d in sorted(doc_exits - code_exits, key=int):
        if d in deprecated:
            continue
        findings.append(finding("doc", SEVERITY_ERROR, "EXIT_DOC_ONLY",
                                "文档列了退出码但代码从不返回: %s" % d, file="SKILL.md"))
    for c in sorted(code_exits - doc_exits, key=int):
        findings.append(finding("doc", SEVERITY_ERROR, "EXIT_CODE_ONLY",
                                "代码会返回该退出码但文档未列: %s" % c, file="SKILL.md",
                                suggestion="在文档补全退出码说明"))

    # A4 标识符
    declared = ctx.get("declared_tools", set())
    seen_idents = set()
    for m in IDENT_RE.finditer(doc):
        ident = m.group(1)
        if ident not in blob:
            if ident in declared:
                # 外部 MCP / 插件工具名（frontmatter 或文档中声明），非本地代码符号，跳过避免误报
                continue
            if ident in seen_idents:
                # 同一标识符在文档多处提及只报一次，避免重复刷屏
                continue
            seen_idents.add(ident)
            # 能力声明语境下出现未知标识符 → 升级为「能力漂移」提示（更精准，免与通用 UNKNOWN_IDENT 混淆）
            ls = doc.rfind("\n", 0, m.start()) + 1
            le = doc.find("\n", m.end())
            line = doc[ls:le if le != -1 else len(doc)]
            if CAP_VERB_RE.search(line):
                findings.append(finding("doc", SEVERITY_WARN, "DOC_CAPABILITY_DRIFT",
                                        "文档声称提供/支持的能力 %s 在代码中找不到对应实现（可能已移除或拼写有误）" % ident,
                                        file="SKILL.md", suggestion="核实该能力是否仍存在，或更正文档"))
            else:
                findings.append(finding("doc", SEVERITY_WARN, "UNKNOWN_IDENT",
                                        "文档里提到的名称 %s 在代码里找不到（可能拼写有误或已被删除；若为外部 MCP/插件工具请在 frontmatter 的 allowed-tools 声明）" % ident, file="SKILL.md"))

    # A5 版本号（仅 WorkBuddy 平台强制；开放标准 agentskills/generic 不强制 version，避免审计外部技能误报）
    if ctx.get("platform", "workbuddy") == "workbuddy" and not VERSION_RE.search(doc):
        findings.append(finding("doc", SEVERITY_ERROR, "VERSION_MISSING",
                                "SKILL.md 缺少 version 声明", file="SKILL.md",
                                suggestion="添加 version: x.y.z"))

    # C 类：Vector 1 (v1.21.0) 内容漂移——结构化声明 ↔ 代码事实 交叉校验
    # C1 检查器数量声明漂移
    for m in DOC_CHECKER_COUNT_RE.finditer(doc):
        n = int(m.group(1))
        if n != len(ALL_CHECKERS):
            findings.append(finding("doc", SEVERITY_WARN, "DOC_COUNT_DRIFT",
                                    "文档声称 %d 个检查器，代码实际定义 %d 个（ALL_CHECKERS）" % (n, len(ALL_CHECKERS)),
                                    file="SKILL.md", suggestion="同步文档中的检查器数量"))
    # C2 deadcode 模式集合漂移（大括号 / 斜杠两种枚举写法）
    for m in DOC_MODE_BRACE_RE.finditer(doc):
        toks = [t for t in m.group(1).split(",") if t]
        if toks and set(toks) <= set(DEADCODE_MODES) and set(toks) != set(DEADCODE_MODES):
            findings.append(finding("doc", SEVERITY_WARN, "DOC_ENUM_DRIFT",
                                    "文档枚举的 deadcode 模式 %s 与代码实际 %s 不一致（多出或缺失模式）" % (
                                        "、".join(sorted(toks)), "、".join(sorted(DEADCODE_MODES))),
                                    file="SKILL.md", suggestion="同步文档中的 deadcode 模式集合"))
    for m in DOC_MODE_SLASH_RE.finditer(doc):
        toks = m.group(1).split("/")
        if set(toks) <= set(DEADCODE_MODES) and set(toks) != set(DEADCODE_MODES):
            findings.append(finding("doc", SEVERITY_WARN, "DOC_ENUM_DRIFT",
                                    "文档枚举的 deadcode 模式 %s 与代码实际 %s 不一致" % (
                                        "、".join(sorted(toks)), "、".join(sorted(DEADCODE_MODES))),
                                    file="SKILL.md", suggestion="同步文档中的 deadcode 模式集合"))

    # B 类：仅枚举，供 AI 判断
    statuses = sorted(set(STATUS_RE.findall(blob)))
    status_missing = [s for s in statuses if s not in doc]
    if statuses:
        findings.append(finding("doc", SEVERITY_INFO, "B_STATUS",
                                "运行状态全集(%d): %s；文档未出现: %s" % (
                                    len(statuses), ", ".join(statuses),
                                    ", ".join(status_missing) or "无")))
    cfg_keys = []
    cfg_path = os.path.join(scripts_dir, "config.json")
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                cfg_keys = sorted(json.load(fh).keys())
        except Exception:
            pass
    cfg_missing = [k for k in cfg_keys if k not in doc]
    if cfg_keys:
        findings.append(finding("doc", SEVERITY_INFO, "B_CONFIG",
                                "配置项全集(%d): %s；文档未出现: %s" % (
                                    len(cfg_keys), ", ".join(cfg_keys),
                                    ", ".join(cfg_missing) or "无")))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：structure（结构体检 + 元信息）
# --------------------------------------------------------------------------- #
def check_structure(ctx):
    findings = []
    doc = ctx["doc"]
    skill_dir = ctx["skill_dir"]

    fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", doc, re.S)
    dir_name = os.path.basename(skill_dir.rstrip(os.sep))
    platform = ctx.get("platform", "workbuddy")  # workbuddy 强制 version/license；agentskills/generic 为开放标准，不强制

    if fm:
        fm_text = fm.group(1)
        name_m = re.search(r"^name:\s*(.+)$", fm_text, re.M)
        ver_m = re.search(r"^version:\s*[\"']?([0-9][0-9A-Za-z.\-]*)[\"']?", fm_text, re.M)
        desc_m = re.search(r"^description:\s*(.+)$", fm_text, re.M)
        if name_m and name_m.group(1).strip().strip("\"'") != dir_name:
            findings.append(finding("structure", SEVERITY_WARN, "name_mismatch",
                                    "frontmatter name 与目录名不一致",
                                    suggestion="改为 '%s'" % dir_name))
        if not ver_m:
            if platform == "workbuddy":
                findings.append(finding("structure", SEVERITY_ERROR, "version_missing",
                                        "frontmatter 缺少合规 version",
                                        suggestion="添加 version: x.y.z"))
            # 非 WorkBuddy 平台（开放标准 agentskills/generic）不强制 version，跳过避免误报
        if not name_m:
            findings.append(finding("structure", SEVERITY_ERROR, "name_missing",
                                    "frontmatter 缺少 name 声明",
                                    suggestion="添加 name: <技能目录名>"))
        if not re.search(r"^license:", fm_text, re.M):
            if platform == "workbuddy":
                findings.append(finding("structure", SEVERITY_WARN, "license_missing",
                                        "frontmatter 缺少 license 声明",
                                        suggestion="添加 license: MIT 等"))
            else:
                findings.append(finding("structure", SEVERITY_INFO, "license_missing",
                                        "frontmatter 缺少 license 声明（非 WorkBuddy 平台，建议补充）",
                                        suggestion="添加 license: MIT 等"))
        if desc_m:
            desc = desc_m.group(1).strip().strip("\"'")
            if not (20 <= len(desc) <= 1024):
                findings.append(finding("structure", SEVERITY_WARN, "desc_length",
                                        "description 长度应 20-1024 字符（当前 %d）" % len(desc)))
            has_when = bool(re.search(r"当|如果|用户|遇到|在.*时", desc))
            has_what = bool(re.search(r"检查|审计|生成|创建|扫描|验证|导出|处理|管理", desc))
            if not (has_when and has_what):
                findings.append(finding("structure", SEVERITY_INFO, "desc_four",
                                        "description 建议含四要素（做什么/何时用/关键能力/触发短语）"))
        else:
            findings.append(finding("structure", SEVERITY_ERROR, "desc_missing",
                                    "frontmatter 缺少 description"))
        # H1 标题与 frontmatter 身份一致性（与 name 或 displayName 比对，兼容中英文）
        disp_m = re.search(r"^displayName:\s*(.+)$", fm_text, re.M)
        h1_m = re.search(r"^#\s+(.+)$", doc, re.M)
        if h1_m and name_m:
            nm = name_m.group(1).strip().strip("\"'")
            disp = disp_m.group(1).strip().strip("\"'") if disp_m else ""
            h1n = h1_m.group(1).strip()
            _norm = lambda s: re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s.lower()).strip()
            cand = [_norm(disp), _norm(nm)] if disp else [_norm(nm)]
            h1n_n = _norm(h1n)
            if not any(c and (c in h1n_n or h1n_n in c) for c in cand):
                findings.append(finding("structure", SEVERITY_WARN, "h1_name_mismatch",
                                        "正文 H1 标题与 frontmatter 身份不一致（H1='%s', name='%s'%s）"
                                        % (h1n, nm, (" / displayName='%s'" % disp) if disp else ""),
                                        suggestion="统一 H1 与 name/displayName"))
    else:
        # 无 frontmatter：退化为检查 inline version / description，避免对已验证技能误报
        if not VERSION_RE.search(doc):
            findings.append(finding("structure", SEVERITY_ERROR, "version_missing",
                                    "SKILL.md 缺少 version 声明（frontmatter 或 inline）",
                                    suggestion="添加 version: x.y.z"))
        else:
            findings.append(finding("structure", SEVERITY_WARN, "no_frontmatter",
                                    "建议使用 YAML frontmatter 声明 name/version/description"))
        if not re.search(r"description", doc, re.I):
            findings.append(finding("structure", SEVERITY_WARN, "desc_missing",
                                    "未检测到 description 字段"))

    # 正文行数
    lines = doc.splitlines()
    if len(lines) > 500:
        findings.append(finding("structure", SEVERITY_WARN, "too_long",
                                "正文 %d 行，超过 500 行建议拆分" % len(lines)))

    # 加载式引用完整性（references/ 与 scripts/）
    for m in re.finditer(r"(?:references|scripts)/[A-Za-z0-9_.\-/]+\.(?:md|py|js|jsx|ts|tsx|vue|go|rs|java|c|cpp|h|rb|php|swift|kt|lua|json|sh|ps1)", doc):
        ref = m.group(0)
        if not os.path.exists(os.path.join(skill_dir, ref)):
            findings.append(finding("structure", SEVERITY_ERROR, "broken_ref",
                                    "文档里引用加载的脚本或文件 %s 不存在（请检查引用路径是否写错）" % ref, file="SKILL.md",
                                    suggestion="修正路径或补充文件"))

    # 硬编码用户绝对路径（上下文感知，降低文档示例误报）
    # 仅对「真实指令行」报：跳过代码围栏、表格行、引用块、以及含豁免/示例性语言的描述行，
    # 这些上下文里的路径多为规则说明 / 命令行示例，并非要求用户照做的真实绝对路径。
    _in_fence = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            _in_fence = not _in_fence
            continue
        if _in_fence:
            continue
        if "|" in line or line.lstrip().startswith(">"):
            continue
        if re.search(r"豁免|示例|example|如[：:]|比如|例如|说明|文档|描述", line, re.I):
            continue
        for m in re.finditer(r"[A-Za-z]:\\Users\\[^\s`]+|/home/[^\s`]+|/Users/[^\s`]+", line):
            findings.append(finding("structure", SEVERITY_WARN, "hardcoded_path",
                                    "文档含硬编码用户绝对路径: %s" % m.group(0), file="SKILL.md", line=i,
                                    suggestion="改用相对路径或 <用户目录> 占位"))

    # TODO / 占位 / 历史记录（跳过表格行，避免把"描述检查器本身"的单元格误判为真实标记）
    for i, line in enumerate(lines, 1):
        if "|" in line:
            continue
        if re.search(r"\b(TODO|FIXME|XXX)\b", line):
            findings.append(finding("structure", SEVERITY_WARN, "todo_marker",
                                    "含 TODO/FIXME 标记", file="SKILL.md", line=i))
        if re.search(r"占位|伪代码|待补充|示例待填|修改于|更新于\s*\d{4}", line):
            findings.append(finding("structure", SEVERITY_INFO, "placeholder",
                                    "疑似占位/历史记录文本", file="SKILL.md", line=i))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：security（安全红线静态子集）
# --------------------------------------------------------------------------- #
def check_security(ctx):
    findings = []
    doc = ctx["doc"]
    code = ctx["code"]

    for rel, content in code.items():
        for i, line in enumerate(content.splitlines(), 1):
            if any(tok in line for tok in SCAN_SKIP_TOKENS):
                continue
            # 硬编码远端端点（供应链风险）：须在 _security_irrelevant 跳过之前检测，
            # 否则含 :// 的代码行会被整体跳过而漏报。仅排除注释行与检查器自身源码
            # （re.compile 等），排除文档/示例/SDK 主机以避免把文档链接误报为硬编码端点。
            _ep = ENDPOINT_RE.search(line)
            _ep_comment = line.strip().startswith(("#", "//", "/*", "*", "<!--"))
            # 仅当行内含代码上下文（赋值/调用/返回）才视为真实硬编码端点，
            # 避免把文档叙述/注释中的示例 URL 误报（如检查器自身 docstring）。
            _ep_context = re.search(r"[=(\[]|return |yield ", line) is not None
            if _ep and not _ep_comment and not any(tok in line for tok in SCAN_SKIP_TOKENS) \
                    and _ep_context and _ep.group(1) not in EXCLUDE_ENDPOINT_HOSTS \
                    and not _ep.group(1).endswith(".example.com"):
                findings.append(finding("security", SEVERITY_WARN, "hardcoded_endpoint",
                                        "脚本硬编码远端端点: %s (%s)" % (_ep.group(0), rel),
                                        file=rel, line=i,
                                        suggestion="远端地址建议提取为配置/环境变量，避免供应链被定点篡改"))
            # 误报自纠错（上下文感知）：注释 / 文档 URL / 自引用资源上溯 不视为漏洞，
            # 统一作用于所有 security 正则，避免上下文盲误报。
            if _security_irrelevant(line):
                continue
            if SECRET_RE.search(line):
                findings.append(finding("security", SEVERITY_ERROR, "hardcoded_secret",
                                        "疑似硬编码密钥/凭据: %s" % rel, file=rel, line=i,
                                        suggestion="移至配置或环境变量，勿落盘"))
            if re.search(r"base64\.b64decode|codecs\.decode\([^)]*,\s*['\"]?base64", line, re.I):
                findings.append(finding("security", SEVERITY_WARN, "obfuscation",
                                        "疑似混淆/编码隐藏执行: %s" % rel, file=rel, line=i))
            if EVAL_EXT_RE.search(line):
                findings.append(finding("security", SEVERITY_WARN, "dynamic_exec",
                                        "动态执行外部内容 eval/exec: %s" % rel, file=rel, line=i,
                                        suggestion="确认输入来源可信，避免执行外部内容"))
            if TRAVERSAL_RE.search(line):
                findings.append(finding("security", SEVERITY_ERROR, "path_traversal",
                                        "路径穿越（相对路径上溯）: %s" % rel, file=rel, line=i))
            if WILDCARD_RM_RE.search(line):
                findings.append(finding("security", SEVERITY_ERROR, "destructive_wildcard",
                                        "用户目录通配删除: %s" % rel, file=rel, line=i))
            if DYNAMIC_IMPORT_RE.search(line):
                findings.append(finding("security", SEVERITY_WARN, "dynamic_import",
                                        "动态导入（importlib/__import__ 等反射式模块加载）: %s" % rel,
                                        file=rel, line=i,
                                        suggestion="确认导入目标来源可信，避免加载未预期的模块"))

    for i, line in enumerate(doc.splitlines(), 1):
        if INJECT_RE.search(line):
            findings.append(finding("security", SEVERITY_INFO, "injection_phrasing",
                                    "文档含疑似提示词注入句式，需 AI 复核", file="SKILL.md", line=i))
        if SECRET_RE.search(line):
            findings.append(finding("security", SEVERITY_WARN, "secret_in_doc",
                                    "文档出现疑似密钥（可能为示例，需确认）", file="SKILL.md", line=i))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：runtime（脚本可运行性）
# --------------------------------------------------------------------------- #
def check_runtime(ctx):
    import py_compile
    findings = []
    skill_dir = ctx["skill_dir"]
    doc = ctx["doc"]
    code = ctx["code"]
    tmpdir = tempfile.mkdtemp(prefix="audit_pyc_")
    try:
        for rel in code:
            if not rel.endswith(".py"):
                continue
            p = os.path.join(skill_dir, rel)
            if not os.path.isfile(p):
                continue
            cf = os.path.join(tmpdir, os.path.basename(rel) + ".pyc")
            try:
                py_compile.compile(p, cfile=cf, doraise=True)
            except py_compile.PyCompileError as e:
                msg = str(e).strip().splitlines()[-1]
                findings.append(finding("runtime", SEVERITY_ERROR, "py_syntax",
                                        "Python 语法错误: %s — %s" % (rel, msg), file=rel,
                                        suggestion="修正语法"))
            except Exception as e:  # noqa: BLE001
                findings.append(finding("runtime", SEVERITY_WARN, "py_check_fail",
                                        "无法校验 %s: %s" % (rel, e), file=rel))

        # 文档引用的脚本是否存在
        for m in re.finditer(r"(scripts/[A-Za-z0-9_\-]+\.(?:py|js|jsx|ts|tsx|vue|go|rs|java|c|cpp|h|rb|php|swift|kt|lua|sh|ps1))", doc):
            ref = m.group(1)
            if not os.path.exists(os.path.join(skill_dir, ref)):
                findings.append(finding("runtime", SEVERITY_ERROR, "script_ref_missing",
                                        "文档引用的脚本不存在: %s" % ref, file="SKILL.md"))

        # 能力预检清单（静态列举，不执行）
        caps = set()
        for rel, content in code.items():
            for line in content.splitlines():
                if any(tok in line for tok in SCAN_SKIP_TOKENS):
                    continue
                if "open(" in line:
                    caps.add(rel + ":文件IO")
                if re.search(r"requests\.|urllib|http[s]?://", line):
                    caps.add(rel + ":网络")
                if re.search(r"subprocess|os\.system|Popen|shell=True", line):
                    caps.add(rel + ":子进程")
                if "eval(" in line or "exec(" in line:
                    caps.add(rel + ":动态执行")
        if caps:
            findings.append(finding("runtime", SEVERITY_INFO, "capability",
                                    "脚本能力预检（静态列举，不执行）: " + " | ".join(sorted(caps))))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return findings


# --------------------------------------------------------------------------- #
# 检查器：deps（依赖与平台声明）
# --------------------------------------------------------------------------- #
def check_deps(ctx):
    findings = []
    doc = ctx["doc"]
    code = ctx["code"]

    # 1) 探测代码中对外部二进制 / CLI 的显式调用（仅看子进程/系统调用语义的行）
    EXTERNAL_CLI = {"git", "npm", "npx", "pip", "pip3", "ffmpeg", "ffprobe", "curl", "wget", "docker", "kubectl", "aws", "az", "gcloud", "powershell", "pwsh", "node", "node.exe", "bun", "deno", "go", "cargo", "rustc", "java", "javac", "sqlite3", "tmux", "ssh", "scp", "rsync", "gsutil", "terraform"}
    invoked = set()
    for rel, content in code.items():
        for line in content.splitlines():
            if any(tok in line for tok in SCAN_SKIP_TOKENS):
                continue
            if "EXTERNAL_CLI" in line:  # 跳过本检查器自身的检测常量定义/迭代行
                continue
            if not re.search(r"subprocess|os\.system|Popen|shell=True|os\.popen", line):
                continue
            for cli in EXTERNAL_CLI:
                if re.search(r"(?<![A-Za-z0-9_\-])" + re.escape(cli) + r"(?![A-Za-z0-9_\-])", line):
                    invoked.add(cli)

    for cli in sorted(invoked):
        if cli.lower() not in doc.lower():
            findings.append(finding("deps", SEVERITY_WARN, "undeclared_cli",
                                    "代码调用外部 CLI 但文档未声明依赖: %s" % cli,
                                    suggestion="在 SKILL.md 补充依赖声明与安装/降级方式"))

    # 2) 平台相关性：含 Windows 专属 API 但未声明运行平台
    WIN_MARKERS = ("win32api", "ctypes.windll", "winreg", "HKEY_", "ShellExecute", "os.startfile", "windll", ".exe", "GetShortcut")
    win_hits = set()
    for rel, content in code.items():
        for line in content.splitlines():
            if any(tok in line for tok in SCAN_SKIP_TOKENS):
                continue
            if "WIN_MARKERS" in line or "EXTERNAL_CLI" in line:  # 跳过检测常量定义/迭代行
                continue
            for mk in WIN_MARKERS:
                if mk in line:
                    win_hits.add(mk)
    if win_hits:
        _declared_plat = _normalize_target_platform(ctx.get("target_platform", "cross-platform"))
        if _declared_plat != set(PLAT_ALL):
            pass  # 已显式声明运行平台（非跨平台默认）→ 结构化字段即是声明，抑制散文扫描
        elif not re.search(r"windows|仅.*windows|平台.*windows|platform", doc, re.I):
            findings.append(finding("deps", SEVERITY_INFO, "platform_undeclared",
                                    "代码含 Windows 专属 API（%s 等），建议声明运行平台" %
                                    ", ".join(sorted(win_hits)[:5]),
                                    suggestion="在文档注明「仅支持 Windows」或补充平台元信息（SKILL.md 的 target_platform 字段）"))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：deadcode（死代码检测；运行前按 --deadcode-mode 询问精度模式）
#   零依赖：基于 ast 静态分析 .py 的未使用定义/导入、不可达代码；
#   孤儿资源：scripts/ 与 references/ 下从未被引用的文件；
#   可选增强：环境装了 vulture 则额外跑高精度死代码（未装静默跳过）。
#   全部 WARN/INFO，绝不 ERROR——死代码结论需人判（同 structure/security 提示项）。
# --------------------------------------------------------------------------- #
# 常见入口名启发：这些名字即使没被显式调用（如作为回调/钩子/公开 API 注册）也视为已用，避免误报。
ENTRY_HINTS = {"main", "run", "start", "handler", "setup", "init", "register",
               "callback", "on_load", "entrypoint", "cli", "execute", "invoke"}


def _deadcode_name_of(node):
    """从装饰器/调用节点取出被引用的名字（用于识别注册式调用）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _deadcode_name_of(node.func)
    return ""


def _has_keep(content, lineno):
    """该函数/导入所在行或上一行含 `# keep` 则视为有意保留，跳过告警。"""
    if not lineno:
        return False
    lines = content.splitlines()
    for off in (0, -1):
        idx = lineno - 1 + off
        if 0 <= idx < len(lines) and "keep" in lines[idx].lower():
            return True
    return False


def _vulture_module():
    """尝试导入 vulture；不可用返回 None（不抛异常、不自动安装）。"""
    try:
        import vulture as _v  # noqa: F401
        return _v
    except Exception:
        return None


def _try_install_vulture():
    """用户显式要求 vulture 但环境缺失时，尝试 pip 安装以满足其意图。

    返回安装后的 vulture 模块；任何失败（无网络 / 无权限 / 超时）均返回 None，
    由调用方按「降级」逻辑处理。绝不抛异常，最长等待 120s。
    仅用于「用户显式要求 vulture」的路径（--deadcode-mode vulture 或交互选 1），
    ask 模式的非 TTY 自动回退路径不调用，避免自动化场景发起意外网络请求。
    """
    import subprocess
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "vulture"],
            check=True, timeout=120,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    return _vulture_module()


def _resolve_deadcode_mode(args):
    """决定 deadcode 运行模式与是否「静默降级」。

    返回 (mode, degraded)：
    - mode: "vulture" | "ast" | "skip"
    - degraded: bool，表示本次是否因环境限制而「未经显式确认」地降低了精度。
      仅在以下两种情况为真：
        (a) 默认 ask + 非 TTY（被管道/Agent 自动化调用）+ 未装 vulture → 回退零依赖 AST（不尝试安装，避免自动化场景发起网络请求）；
        (b) 显式 --deadcode-mode vulture 但运行环境缺失 vulture → 先尝试自动安装 vulture，安装成功则采用高精度，
            安装失败才回退 AST（仍标记 degraded）。
      调用方（check_deadcode）应在 degraded=True 时发出显著提示（precision_degraded
      告警），使精度下降对自动化评测/调用方可见——回应「精度下降而无提示」的可靠性短板。

    - 显式 --deadcode-mode vulture|ast|skip：直接用（供 Agent/CI 跳过交互）；
      vulture 但缺失视为降级（degraded=True）。
    - 默认 ask：环境已装 vulture 则直接采用高精度 vulture 模式（不重复询问）；
      未装 vulture 时：TTY 交互询问（超时 30s / 无输入 → ast 零依赖）；
      非 TTY（被管道或 Agent 调用）→ 零依赖 ast，并标记 degraded=True。
    """
    mode = getattr(args, "deadcode_mode", "ask") if args else "ask"
    if mode != "ask":
        if mode == "vulture" and _vulture_module() is None:
            sys.stderr.write("[deadcode] 未检测到 vulture 库，尝试自动安装 vulture……\n")
            if _try_install_vulture() is not None:
                sys.stderr.write("[deadcode] vulture 安装成功，采用高精度模式\n")
                return "vulture", False
            sys.stderr.write("[deadcode] ⚠ 未检测到 vulture 库且自动安装失败，回退零依赖 AST 模式（精度降级）\n")
            return "ast", True
        return mode, False
    # ask 模式：已装 vulture 直接走高精度，避免重复询问
    if _vulture_module() is not None:
        sys.stderr.write("[deadcode] 检测到 vulture 库，自动采用高精度模式（跳过询问）\n")
        return "vulture", False
    if not sys.stdin.isatty():
        sys.stderr.write(
            "[deadcode] ⚠ 非交互（自动化）环境且未检测到 vulture，回退零依赖 AST 模式"
            "（精度较低、易误报）。如需高精度请安装 vulture 并以 --deadcode-mode vulture 显式指定。\n"
        )
        return "ast", True
    return _prompt_deadcode_mode()


def _prompt_deadcode_mode():
    """交互询问 deadcode 模式；30 秒超时默认 ast（零依赖，易误报）。

    返回 (mode, degraded)：超时/无输入或「选了 vulture 但缺失」视为降级（degraded=True），
    因为并非用户清醒选择的精度；显式选 2（ast）/3（skip）则 degraded=False。
    """
    sys.stderr.write(
        "\n[deadcode] 选择死代码检测精度模式：\n"
        "  1) vulture 高精度（推荐，需已安装 vulture）\n"
        "  2) 零依赖 AST（易误报，无需安装）\n"
        "  3) 本次跳过 deadcode\n"
        "请输入 1/2/3（30 秒内未选则默认 2 零依赖）："
    )
    sys.stderr.flush()

    buf = {}

    def _read():
        try:
            buf["v"] = sys.stdin.readline().strip()
        except Exception:
            buf["v"] = ""

    th = threading.Thread(target=_read, daemon=True)
    th.start()
    th.join(30)
    choice = buf.get("v", "")
    if not choice:
        sys.stderr.write("\n[deadcode] 超时/无输入，默认零依赖 AST 模式（精度降级）\n")
        return "ast", True
    if choice == "1":
        if _vulture_module() is None:
            sys.stderr.write("[deadcode] 未检测到 vulture 库，尝试自动安装 vulture……\n")
            if _try_install_vulture() is not None:
                sys.stderr.write("[deadcode] vulture 安装成功，采用高精度模式\n")
                return "vulture", False
            sys.stderr.write("[deadcode] ⚠ 未检测到 vulture 库且自动安装失败，回退零依赖 AST 模式（精度降级）\n")
            return "ast", True
        return "vulture", False
    if choice == "3":
        return "skip", False
    return "ast", False


def check_deadcode(ctx):
    mode, degraded = _resolve_deadcode_mode(ctx.get("args"))
    findings = []
    if degraded:
        # 静默降级（非 TTY + 未装 vulture / 显式 vulture 但缺失）→ 显著提示精度下降，
        # 让自动化评测/调用方能够「看见」降级，而非无提示地以低精度结果蒙混过关。
        findings.append(finding(
            "deadcode", SEVERITY_WARN, "precision_degraded",
            "deadcode 精度降级：当前为非交互（自动化）环境且未安装 vulture，已回退至零依赖 AST 模式（精度较低、易误报）。",
            suggestion="请在运行环境安装 vulture 并以 --deadcode-mode vulture 显式指定；或由 Agent 在调用前主动询问用户精度模式（见 SKILL.md「Agent 执行约定」）。",
        ))
    if mode == "skip":
        return findings
    skill_dir = ctx["skill_dir"]
    doc = ctx["doc"]
    code = ctx["code"]

    # ---- 预扫描：跨文件引用集合 ----
    # 多文件技能里，一个函数常在本文件定义、在他文件被调用。若只按单文件 AST 判定，
    # 会把「跨文件被引用」的符号误报为 unused_def。故先汇总全技能范围被引用的标识符
    # (global_used) 与被 import 的模块名 (imported_modules)，供下方跨文件判定使用。
    global_used = set()
    imported_modules = set()

    def _collect_refs(tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                global_used.add(node.id)
            elif isinstance(node, ast.Attribute):
                global_used.add(node.attr)
            elif isinstance(node, ast.Import):
                for n in node.names:
                    imported_modules.add(n.name.split(".")[0])
                    if n.asname:
                        imported_modules.add(n.asname)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split(".")[0])
                for n in node.names:
                    imported_modules.add(n.name.split(".")[0])
                    if n.asname:
                        imported_modules.add(n.asname)
            elif isinstance(node, ast.Call):
                n = _deadcode_name_of(node.func)
                if n:
                    global_used.add(n)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # 字符串字面量中的标识符也视为潜在引用：覆盖 dispatch 字典按字符串键注册、反射等动态调用
                for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", node.value):
                    global_used.add(tok)

    per_file = []
    for rel, content in code.items():
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue  # 语法错误由 runtime 检查器负责
        _collect_refs(tree)
        used_local = set()
        defined = []
        import_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_local.add(node.id)
            elif isinstance(node, ast.Attribute):
                used_local.add(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.append((node.name, node.lineno))
                for dec in node.decorator_list:  # 装饰器即注册式调用，视为已用
                    n = _deadcode_name_of(dec)
                    if n:
                        used_local.add(n)
            elif isinstance(node, ast.ClassDef):
                defined.append((node.name, node.lineno))
            elif isinstance(node, ast.Import):
                for n in node.names:
                    import_names.append((n.asname or n.name.split(".")[0], node.lineno))
            elif isinstance(node, ast.ImportFrom):
                for n in node.names:
                    import_names.append((n.asname or n.name.split(".")[0], node.lineno))
            elif isinstance(node, ast.Call):
                n = _deadcode_name_of(node.func)
                if n:
                    used_local.add(n)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # 字符串字面量中的标识符也视为潜在引用：覆盖 dispatch 字典按字符串键注册、反射等动态调用
                for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", node.value):
                    used_local.add(tok)
        per_file.append((rel, content, tree, used_local, defined, import_names))

    # ---- A. 代码级：AST 分析 .py（unused_def 跨文件判定） ----
    for rel, content, tree, used_local, defined, import_names in per_file:
        # 未使用导入（INFO）—— 仅按本文件判定；vulture 模式下交由 vulture 检测，避免重复报告
        if mode != "vulture":
            for name, lineno in import_names:
                if name == "*":
                    continue
                if name in used_local or _has_keep(content, lineno):
                    continue
                findings.append(finding("deadcode", SEVERITY_INFO, "unused_import",
                                        "导入但未使用: %s" % name, file=rel, line=lineno,
                                        suggestion="删除未使用的导入，或加 `# keep` 保留"))

        # 未使用定义（WARN）—— 跨文件判定：仅在全技能范围都未引用时才报（消除多文件技能的误报）
        if mode != "vulture":
            for name, lineno in defined:
                if name in global_used or name in ENTRY_HINTS:
                    continue
                if name.startswith("__") and name.endswith("__"):
                    continue  # 魔术方法/特殊名不视为死代码
                if _has_keep(content, lineno):
                    continue
                findings.append(finding("deadcode", SEVERITY_WARN, "unused_def",
                                        "定义了但从未被引用: %s" % name, file=rel, line=lineno,
                                        suggestion="删除死代码，或加 `# keep` 保留（如公开 API/钩子）"))

        # 不可达代码（WARN）：同一代码块中 return/raise 之后紧跟无条件的语句
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or len(body) < 2:
                continue
            for idx in range(len(body) - 1):
                cur = body[idx]
                nxt = body[idx + 1]
                if not isinstance(cur, (ast.Return, ast.Raise)):
                    continue
                if isinstance(nxt, (ast.If, ast.For, ast.AsyncFor, ast.While,
                                    ast.With, ast.AsyncWith, ast.Try,
                                    ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef, ast.Import, ast.ImportFrom)):
                    continue
                ln = getattr(nxt, "lineno", 0)
                if _has_keep(content, ln):
                    continue
                findings.append(finding("deadcode", SEVERITY_WARN, "unreachable",
                                        "不可达代码（return/raise 之后的语句）", file=rel, line=ln,
                                        suggestion="删除不可达分支"))

    # ---- B. 孤儿资源文件（scripts/ 与 references/ 下从未被引用的文件） ----
    all_text = doc + "\n" + "\n".join(code.values())
    for sub in ("scripts", "references"):
        d = os.path.join(skill_dir, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            fp = os.path.join(d, fn)
            if not os.path.isfile(fp):
                continue
            if fn in ("__init__.py",):
                continue
            base = fn
            relref = "%s/%s" % (sub, fn)
            mod_name = os.path.splitext(fn)[0]
            # 被文档/代码按文件名或相对路径引用，或被其他 .py 以模块名 import（保守：避免把被导入模块误标为孤儿）
            if base in all_text or relref in all_text or mod_name in imported_modules:
                continue
            findings.append(finding("deadcode", SEVERITY_WARN, "orphan_asset",
                                    "资源文件从未被引用/加载: %s" % relref, file=relref,
                                    suggestion="删除无用文件，或在 SKILL.md/代码中引用"))

    # ---- 可选：vulture 高精度死代码（仅 vulture 模式运行） ----
    if mode == "vulture":
        _v = _vulture_module()
        if _v is not None:
            try:
                py_files = [os.path.join(skill_dir, r) for r in code if r.endswith(".py")]
                if py_files:
                    v = _v.Vulture()
                    v.scavenge(py_files)
                    # 兼容 vulture 2.x（get_unused_code / typ / first_lineno）
                    # 与旧版（get_unused_code_items / typename / lineno）
                    if hasattr(v, "get_unused_code"):
                        items = v.get_unused_code()
                    elif hasattr(v, "get_unused_code_items"):
                        items = v.get_unused_code_items()
                    else:
                        items = []
                    for item in items:
                        typ = getattr(item, "typ", None) or getattr(item, "typename", None) or ""
                        line = getattr(item, "first_lineno", None) or getattr(item, "lineno", None)
                        # 与 AST 分支一致：定义所在行或上一行含 `# keep` 视为有意保留，跳过
                        if item.filename:
                            try:
                                with open(item.filename, encoding="utf-8", errors="ignore") as _fh:
                                    _src = _fh.read()
                                if _has_keep(_src, line):
                                    continue
                            except Exception:
                                pass
                        msg = ("vulture 检出死代码: %s (%s)" % (item.name, typ)) if typ else ("vulture 检出死代码: %s" % item.name)
                        findings.append(finding("deadcode", SEVERITY_WARN, "vulture",
                                                msg,
                                                file=os.path.relpath(item.filename, skill_dir) if item.filename else None,
                                                line=line,
                                                suggestion="确认后删除或加白名单"))
            except Exception as exc:
                sys.stderr.write("[deadcode] vulture 分析异常，已跳过：%s\n" % exc)

    return findings


# --------------------------------------------------------------------------- #
# 检查器：portability（跨平台可移植性，零依赖纯静态分析）
#   按 frontmatter 的 target_platform 字段豁免：声明平台「覆盖」该发现会崩的平台才抑制。
#   规则：fire iff (声明平台 ∩ breaks_on) 非空；cross-platform(默认/省略) = 全平台 → 始终 fire。
#   全部 WARN/INFO，绝不 ERROR（可移植性是程度问题，结论需人判；同 deadcode 提示项）。
# --------------------------------------------------------------------------- #
PLAT_WIN = {"windows"}
PLAT_UNIX = {"linux", "macos"}
PLAT_ALL = {"windows", "linux", "macos"}
AGENT_ALL = {"workbuddy", "claude-code", "cursor", "codex", "copilot", "cline", "generic"}


def _normalize_target_platform(raw):
    """frontmatter 的 target_platform 原始值 → 标准化平台集合。
    空/未知/跨平台(cross-platform|all|*) → 全平台（安全默认：仍报告）。"""
    if isinstance(raw, (list, tuple, set)):
        toks = [str(t).strip().lower() for t in raw]
    else:
        toks = [str(raw).strip().lower()]
    out = set()
    for t in toks:
        if t in ("cross-platform", "all", "*", ""):
            return set(PLAT_ALL)
        if t in PLAT_ALL:
            out.add(t)
    return out or set(PLAT_ALL)


def _port_fire(declared, breaks_on):
    """声明平台与「该发现会崩的平台」有交集才 fire；否则该缺陷只存在于未声明的平台上 → 抑制。"""
    return bool(declared & breaks_on)


def _parse_frontmatter_list(fm_text, key):
    """frontmatter 中 key 的值 → 字符串列表。兼容两种写法：
      - 内联：allowed-tools: Read, Grep, Bash(npm run:*)  （逗号/空格分隔；含括号权限时取工具名部分）
      - YAML 块列表：
          allowed-tools:
            - Read
            - Grep
    找不到返回 []。"""
    m = re.search(r"^%s:\s*(.*)$" % re.escape(key), fm_text, re.M)
    if not m:
        return []
    val = m.group(1).strip().strip("[]").strip()
    if val:
        out = []
        for tok in re.split(r"[,;\s]+", val):
            tok = tok.strip().strip("[]")
            if tok:
                out.append(tok.split("(", 1)[0].strip())  # Bash(npm run:*) -> Bash
        return out
    # 块列表：后续以 "- " 开头的行（遇非列表/空行即止，允许空行）
    lines = fm_text.splitlines()
    idx = None
    for i, ln in enumerate(lines):
        if re.match(r"^%s:\s*$" % re.escape(key), ln):
            idx = i
            break
    if idx is None:
        return []
    out = []
    for ln in lines[idx + 1:]:
        if ln.strip() == "":
            continue
        lm = re.match(r"^\s*-\s*(.+)$", ln)
        if not lm:
            break
        tok = lm.group(1).strip()
        if tok:
            out.append(tok.split("(", 1)[0].strip())
    return out


def _normalize_target_agent(tokens):
    """frontmatter 的 target_agent / compatibility 值列表 → 标准化 Agent 集合。
    含 all/*/cross-agent → 全平台（安全默认：仍提示/报告）；否则取显式列表（自由形式）。"""
    out = set()
    for t in tokens:
        t = str(t).strip().lower()
        if t in ("all", "*", "cross-agent", "cross_agent", "any"):
            return set(AGENT_ALL)
        if t:
            out.add(t)
    return out


SHELL_SCAN_TOKENS = ("subprocess", "os.system", "Popen", "os.popen", "shell=True", "run(")


def check_portability(ctx):
    findings = []
    code = ctx["code"]
    declared = _normalize_target_platform(ctx.get("target_platform", "cross-platform"))
    declared_agent = _normalize_target_agent(ctx.get("target_agent", []))

    def add(sev, cat, msg, suggestion, breaks_on):
        if _port_fire(declared, breaks_on):
            findings.append(finding("portability", sev, cat, msg, suggestion=suggestion))

    for rel, content in code.items():
        for ln, line in enumerate(content.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if any(tok in line for tok in SELF_REF_TOKENS) or any(tok in line for tok in SCAN_SKIP_TOKENS):
                continue
            in_shell = any(s in line for s in SHELL_SCAN_TOKENS)

            # #1 硬编码绝对路径（用户/家目录）
            m_win = re.search(r"\b[A-Za-z]:\\", line)
            if m_win:
                add(SEVERITY_WARN, "hardcoded_abs_path",
                    "%s:%d 硬编码 Windows 绝对路径（%s），非 Windows 平台将失效" % (rel, ln, m_win.group(0)),
                    suggestion="改用 os.path.expanduser('~') / pathlib.Path.home() 等相对用户目录的方式",
                    breaks_on=PLAT_UNIX)
            m_unix = re.search(r"(/Users/|/home/)[A-Za-z0-9_\-]+", line)
            if m_unix:
                add(SEVERITY_WARN, "hardcoded_abs_path",
                    "%s:%d 硬编码 Unix 家目录路径（%s），Windows 上通常不存在" % (rel, ln, m_unix.group(0)),
                    suggestion="改用 os.path.expanduser('~') / pathlib.Path.home()",
                    breaks_on=PLAT_WIN)

            # #2 启动目录依赖
            if re.search(r"\b(os\.getcwd\(|os\.getcwdb\(|Path\.cwd\(|\.cwd\(\)|process\.cwd)", line):
                add(SEVERITY_WARN, "cwd_dependence",
                    "%s:%d 依赖当前工作目录（%s），从其他目录启动时资源定位会失败" % (rel, ln, line.strip()[:60]),
                    suggestion="基于 __file__ / __dirname / pathlib.Path(__file__) 定位资源，而非 os.getcwd()",
                    breaks_on=PLAT_ALL)

            # #3 平台专属 shell/命令（仅看子进程/系统调用语义的行）
            if in_shell:
                mw = re.search(r"\b(cmd\.exe|powershell|pwsh)\b", line)
                if mw:
                    add(SEVERITY_WARN, "platform_shell",
                        "%s:%d 调用 Windows 专属命令 %s，非 Windows 平台不可用" % (rel, ln, mw.group(0)),
                        suggestion="为跨平台提供分支兜底，或用跨平台库替代 shell 调用",
                        breaks_on=PLAT_UNIX)
                mu = re.search(r"\b(rm\s+-rf|rm\s+-r|/bin/sh|/bin/bash|ls\s|mkdir\s+-p|grep\s|sed\s|awk\s|cat\s)", line)
                if mu:
                    add(SEVERITY_WARN, "platform_shell",
                        "%s:%d 调用 Unix 专属命令 %s，Windows 上不可用" % (rel, ln, mu.group(0).strip()),
                        suggestion="为 Windows 提供分支兜底，或用跨平台库（pathlib/shutil）替代",
                        breaks_on=PLAT_WIN)

                # #4 解释器/运行时锁
                if re.search(r"\bpython\b(?!3)", line) and "python3" not in line:
                    add(SEVERITY_WARN, "interpreter_lock",
                        "%s:%d 调用裸 python（非 python3），部分 Linux 仅装 python3 会找不到" % (rel, ln),
                        suggestion="统一用 python3，或在文档声明解释器依赖",
                        breaks_on={"linux"})
                if re.search(r"\bpy\b", line) and "python" not in line and "pyproject" not in line and "happy" not in line:
                    add(SEVERITY_WARN, "interpreter_lock",
                        "%s:%d 使用 Windows py 启动器，非 Windows 不可用" % (rel, ln),
                        suggestion="跨平台改用 python3 直接调用",
                        breaks_on=PLAT_UNIX)

            # #5 编码/路径分隔符假设：open 不指定 encoding（仅真实文件 open() 告警）
            # 排除：引号内描述性文本、带前缀的方法名（urlopen / io.open / os.open 等非文件 open）、
            #       已显式 encoding、二进制模式（rb/wb/ab）。负向环视保证 open( 前非单词/点字符，
            #       从而 urlopen( / io.open( 等不会被误判为缺 encoding 的文件打开。
            if re.search(r"(?<![A-Za-z0-9_.])open\(", line) and '"open("' not in line and "'open('" not in line \
                    and "encoding=" not in line and "rb" not in line and "wb" not in line and "ab" not in line:
                add(SEVERITY_WARN, "encoding_sep",
                    "%s:%d 以 open 打开文件未指定 encoding，Windows 下文本模式默认编码非 UTF-8 易致解码错误" % (rel, ln),
                    suggestion="打开文件时显式指定 encoding='utf-8'",
                    breaks_on=PLAT_ALL)

            # #6 Agent 平台耦合（受 target_agent 门控；不再因声明/推断 workbuddy 而抑制，始终提示）
            # 门控维度是 Agent 而非 OS，故不走 add() 的 OS 平台 _port_fire 闭包，直接判定。
            # 本 skill 自身亦开发跨平台/跨 Agent 能力，故 workbuddy 目标的耦合提示同样有价值，不抑制。
            coupled = [t for t in (".workbuddy", "allowed-tools") if t in line]
            if coupled:
                if declared_agent and "workbuddy" not in declared_agent:
                    # 声明跨 Agent 目标（不含 workbuddy）却仍耦合 WorkBuddy → 升级 WARN（跨 Agent 会失效）
                    findings.append(finding("portability", SEVERITY_WARN, "agent_coupling",
                        "%s:%d 耦合 WorkBuddy 平台约定（%s），但 target_agent 未包含 workbuddy，跨 Agent 分发将失效" % (rel, ln, " / ".join(coupled)),
                        suggestion="若仅面向 WorkBuddy，声明 target_agent: workbuddy；若跨 Agent，抽象平台专有路径/约定"))
                else:
                    # 未声明 / 声明含 workbuddy / 推断 workbuddy → 始终 INFO 提示（供评估跨 Agent 可移植性）
                    findings.append(finding("portability", SEVERITY_INFO, "agent_coupling",
                        "%s:%d 耦合 WorkBuddy 平台约定（%s），跨 Agent 分发需抽象" % (rel, ln, " / ".join(coupled)),
                        suggestion="若计划跨 Agent 分发，将平台专有路径/约定抽取为可配置项；或声明 target_agent: workbuddy"))


    # #7 跨格式可移植性矩阵（lossy_port）：仅当声明跨 Agent 目标（不含 workbuddy）时升级为发现
    # 设计：纯 workbuddy / 未声明 → 不发 lossy 发现（跨 Agent 咨询已由 #6 agent_coupling 覆盖）；
    # 声明跨 Agent（claude-code/cursor 等且不含 workbuddy）→ 对声明目标端会丢失/降级的字段发 WARN/INFO。
    # 放在代码行循环之外：本检查基于 SkillModel/frontmatter，与代码内容无关，无代码文件也应触发。
    model = ctx.get("skill_model")
    if model is not None:
        _da = ctx.get("target_agent", set())
        _cross = bool(_da) and "workbuddy" not in _da
        if _cross:
            _tgt_fmts = {AGENT_TO_FMT.get(a, "generic") for a in _da}
            _tgt_fmts.discard(model.fmt)
            for _r in build_portability_matrix(model):
                if _r["target"] not in _tgt_fmts or _r["status"] == "preserved":
                    continue
                _sev = SEVERITY_WARN if _r["status"] == "lost" else SEVERITY_INFO
                _msg = "跨 Agent 移植损失【lossy_port】 %s → %s：%s" % (
                    _r["feature"], _r["target"],
                    _r["note"] or ("%s 在 %s 丢失" % (_r["feature"], _r["target"])))
                findings.append(finding("portability", _sev, "lossy_port", _msg,
                    suggestion="若确需跨 Agent 分发，将该字段抽象为各端可识别形式（参考 --report portability-matrix）"))

    return findings


# --------------------------------------------------------------------------- #
# 调度
# --------------------------------------------------------------------------- #
CHECKERS = {
    "doc": check_doc,
    "structure": check_structure,
    "security": check_security,
    "runtime": check_runtime,
    "deps": check_deps,
    "deadcode": check_deadcode,
    "portability": check_portability,
}
DEFAULT_CHECKERS = ["doc"]
# deadcode / portability：deadcode ask 模式下已装 vulture 自动高精度，否则运行前询问精度（默认 ask，超时 30s→ast 零依赖）。
ALL_CHECKERS = ["doc", "structure", "security", "runtime", "deps", "deadcode", "portability"]


# ---- 跨 Agent 格式检测与统一模型（Phase 5 归一化内核）----

# 各格式的特征 frontmatter 键（按特征推断，不硬锁枚举——遵循 v1.11.0 自由列表原则，防格式漂移）
_FMT_WB_ONLY = {"slug", "displayname", "target_platform", "target_agent", "agent_created"}
_FMT_CC_ONLY = {"argument-hint", "model", "context", "agent", "user-invocable",
                "disable-model-invocation", "hooks", "paths"}
_FMT_STD = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def _fm_keys(fm_text):
    """从 frontmatter 文本提取小写键名集合（兼容 `key:` 与块列表首行）。"""
    if not fm_text:
        return set()
    return {m.group(1).lower() for m in re.finditer(r"^([A-Za-z0-9_\-]+):", fm_text, re.M)}


def _fm_scalar(fm_text, key):
    """取 frontmatter 标量值（去引号）。找不到返回空串。"""
    if not fm_text:
        return ""
    m = re.search(r"^%s:\s*(.+)$" % re.escape(key), fm_text, re.M)
    if not m:
        return ""
    return m.group(1).strip().strip('"').strip("'")


def detect_format(fm_text, filename=""):
    """推断技能格式（归一化枚举）。
    - .mdc 且含 description/alwaysApply/globs → cursor-mdc（Cursor 规则文件）
    - SKILL.md 含 WorkBuddy 专有键 → workbuddy
    - SKILL.md 含 Claude Code 专有扩展键 → claude-code
    - 含 compatibility 或仅开放标准键 → agentskills（Cursor Plugin 的 SKILL.md 同此处理）
    - 其它 → generic
    判定「按特征推断」而非按枚举硬锁，避免生态演进导致漏判（同 v1.11.0 自由列表原则）。
    """
    keys = _fm_keys(fm_text)
    if filename.endswith(".mdc"):
        return "cursor-mdc" if (keys & {"description", "alwaysapply", "globs"}) else "generic"
    if keys & _FMT_WB_ONLY:
        return "workbuddy"
    if keys & _FMT_CC_ONLY:
        return "claude-code"
    if "compatibility" in keys:
        return "agentskills"
    if keys and keys <= (_FMT_STD | {"version", "author", "tags"}):
        return "agentskills"
    return "generic"


class SkillModel:
    """跨格式统一技能模型（Phase 5 归一化内核），供检查器与 Phase 6 矩阵 / Phase 7 转译消费。"""
    def __init__(self, name="", description="", fmt="generic", platform="generic",
                 target_platform="cross-platform", target_agent=None, tools=None,
                 license="", version="", extra=None):
        self.name = name
        self.description = description
        self.fmt = fmt
        self.platform = platform
        self.target_platform = target_platform
        self.target_agent = target_agent or set()
        self.tools = tools or set()
        self.license = license
        self.version = version
        self.extra = extra or {}


# ---- Phase 6：跨格式可移植性矩阵（字段级能力映射）----
# 以开放标准 agentskills 为枢纽：Claude Code / Cursor Plugin 共用 SKILL.md 格式。
# 各格式原生支持的字段集合（决定某 feature 在目标端是保留/降级/丢失）。
FMT_CAPS = {
    "workbuddy":     {"name", "description", "license", "version", "allowed-tools",
                      "target_agent", "slug", "displayname", "metadata"},
    "agentskills":   {"name", "description", "license", "allowed-tools",
                      "compatibility", "metadata"},
    "claude-code":   {"name", "description", "license", "allowed-tools",
                      "model", "context", "agent", "hooks", "argument-hint", "metadata"},
    "cursor-plugin": {"name", "description", "license", "allowed-tools",
                      "compatibility", "metadata"},   # = agentskills 兼容
    "cursor-mdc":    {"description", "globs", "alwaysApply"},   # Cursor 规则文件：无 name/allowed-tools
    "generic":       {"name", "description"},
}
# 跨格式字段等价映射（降级而非丢失）：feature -> 目标端对应字段名
EQUIV = {
    "target_agent": "compatibility",
    "slug": "name",
    "displayname": "name",
}
# 候选目标格式（用于 --report 全矩阵展示）
FORMAT_TARGETS = ["workbuddy", "agentskills", "claude-code", "cursor-plugin", "cursor-mdc", "generic"]
# Agent 名 -> 规范格式（target_agent 自由列表元素映射为矩阵目标）
AGENT_TO_FMT = {
    "workbuddy": "workbuddy",
    "claude-code": "claude-code",
    "cursor": "cursor-plugin",     # Cursor Plugin 的 SKILL.md 形式（agentskills 兼容）
    "codex": "agentskills",
    "copilot": "agentskills",
    "cline": "agentskills",
    "generic": "generic",
}


def _model_features(model):
    """从 SkillModel 提取该技能实际填充的字段集合（供矩阵消费）。"""
    f = set()
    if model.name:
        f.add("name")
    if model.description:
        f.add("description")
    if model.license:
        f.add("license")
    if model.version:
        f.add("version")
    if model.tools:
        f.add("allowed-tools")
    if model.target_agent:
        f.add("target_agent")
    for k in ("slug", "displayname", "metadata", "globs", "alwaysapply",
              "model", "context", "agent", "hooks", "argument-hint"):
        if k in model.extra:
            f.add(k)
    return f


def build_portability_matrix(model):
    """返回跨格式可移植性矩阵行列表：{feature, target, status, note}。
    status: preserved(保留) / degraded(降级，需转译) / lost(丢失)。
    """
    feats = _model_features(model)
    rows = []
    for tgt in FORMAT_TARGETS:
        if tgt == model.fmt:
            continue
        caps = FMT_CAPS.get(tgt, FMT_CAPS["generic"])
        for feat in sorted(feats):
            if feat in caps:
                status, note = "preserved", ""
            elif feat in EQUIV and EQUIV[feat] in caps:
                status, note = "degraded", "%s 在 %s 中以 %s 表达（需转译）" % (feat, tgt, EQUIV[feat])
            else:
                status, note = "lost", "%s 在 %s 无对应字段，将丢失" % (feat, tgt)
            rows.append({"feature": feat, "target": tgt, "status": status, "note": note})
    return rows


def analyze_skill(skill_dir, enabled, args=None, do_backup=False, backup_limit=BACKUP_LIMIT):
    doc_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(doc_path):
        return {"skill": skill_dir, "error": "no SKILL.md", "findings": []}

    with open(doc_path, encoding="utf-8") as fh:
        doc = fh.read()
    scripts_dir = os.path.join(skill_dir, "scripts")
    code, skipped_code = collect_code(skill_dir)
    blob = "\n".join(code.values())

    # 声明式外部工具名（MCP / 插件工具）：frontmatter 的 allowed-tools / tools 字段，
    # 以及全仓库 .md 中出现的 mcp__*__<name> 标记。这些名称只出现在文档/声明里、不在本地
    # 代码内，UNKNOWN_IDENT 检查应跳过，避免对 Agent / MCP 类技能刷出海量误报。
    declared_tools = set()
    target_agent = set()
    platform = "workbuddy"
    _fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", doc, re.S)
    _fm_text = _fm.group(1) if _fm else ""
    if _fm:
        for _key in ("allowed-tools", "tools"):
            for _tok in _parse_frontmatter_list(_fm_text, _key):
                if not _tok:
                    continue
                declared_tools.add(_tok)
                if "__" in _tok:
                    declared_tools.add(_tok.rsplit("__", 1)[-1])
        # 跨 Agent 目标（target_agent 自由列表；兼容开放标准 compatibility 字段）
        _ta_vals = _parse_frontmatter_list(_fm_text, "target_agent")
        _compat_vals = _parse_frontmatter_list(_fm_text, "compatibility")
        target_agent = _normalize_target_agent(_ta_vals + _compat_vals)
        if not target_agent:
            # 推断：仅当含 WorkBuddy 强特征(mcp__*__ / .workbuddy) 才视为 WorkBuddy（allowed-tools 为跨平台共享键，不可据此推断）
            if "mcp__" in doc or ".workbuddy" in doc or re.search(r"~/.workbuddy", doc):
                target_agent = {"workbuddy"}
        # 平台推断：开放标准(agentskills, 含 compatibility) / workbuddy / generic（开放标准兼容）
        if re.search(r"^compatibility:", _fm_text, re.M):
            platform = "agentskills"
        elif "mcp__" in doc or ".workbuddy" in doc or re.search(r"~/.workbuddy", _fm_text, re.M):
            platform = "workbuddy"
        else:
            platform = "generic"
    for _root, _dirs, _names in os.walk(skill_dir):
        _dirs[:] = [d for d in _dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for _n in _names:
            if not _n.endswith(".md"):
                continue
            _fp = os.path.join(_root, _n)
            try:
                with open(_fp, encoding="utf-8", errors="replace") as _fh:
                    _t = _fh.read()
            except Exception:
                continue
            for _m in re.finditer(r"mcp__[A-Za-z0-9_]+__([A-Za-z0-9_]+)", _t):
                declared_tools.add(_m.group(1))

    # 目标运行平台（portability 检查器用）：frontmatter 的 target_platform 字段。
    # 取值：cross-platform(默认/省略) / windows / linux / macos / 列表如 [windows, linux]。
    target_platform = "cross-platform"
    if _fm:
        _tp = re.search(r"^target_platform:\s*(.+)$", _fm.group(1), re.M)
        if _tp:
            _raw = _tp.group(1).strip()
            if _raw.startswith("[") and _raw.endswith("]"):
                target_platform = [v.strip() for v in _raw[1:-1].split(",") if v.strip()]
            else:
                target_platform = _raw

    # 跨 Agent 格式检测（Phase 5 归一化内核）
    fmt = detect_format(_fm_text, os.path.basename(doc_path))
    _sm_extra = {}
    if _fm:
        for _k in _fm_keys(_fm_text):
            _sm_extra[_k] = _fm_scalar(_fm_text, _k)
    sm = SkillModel(
        name=_fm_scalar(_fm_text, "name") if _fm else "",
        description=_fm_scalar(_fm_text, "description") if _fm else "",
        fmt=fmt,
        platform=platform,
        target_platform=target_platform,
        target_agent=target_agent,
        tools=declared_tools,
        license=_fm_scalar(_fm_text, "license") if _fm else "",
        version=_fm_scalar(_fm_text, "version") if _fm else "",
        extra=_sm_extra,
    )

    backup_path = None
    if do_backup:
        prune_backups(doc_path, backup_limit)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = doc_path + ".bak." + stamp
        shutil.copy2(doc_path, backup_path)

    ctx = {
        "skill_dir": skill_dir,
        "doc": doc,
        "doc_path": doc_path,
        "code": code,
        "blob": blob,
        "scripts_dir": scripts_dir,
        "args": args,
        "declared_tools": declared_tools,
        "target_platform": target_platform,
        "target_agent": target_agent,
        "platform": platform,
        "format": fmt,
        "skill_model": sm,
    }
    findings = []
    for name in enabled:
        fn = CHECKERS.get(name)
        if fn:
            findings.extend(fn(ctx))

    # 稳定性：超大文件防护（避免卡死/拖慢）
    doc_size = os.path.getsize(doc_path)
    if doc_size > MAX_FILE_SIZE:
        findings.append(finding("structure", SEVERITY_WARN, "oversize_doc",
                               "SKILL.md 超过 %d 字节（实际 %d），建议拆分或精简" % (MAX_FILE_SIZE, doc_size),
                               file="SKILL.md",
                               suggestion="文档过大可能影响审计性能"))
    if skipped_code and set(enabled) & {"structure", "security", "runtime", "deps"}:
        findings.append(finding("structure", SEVERITY_WARN, "oversize_file",
                               "以下文件超过 %d 字节已跳过扫描（可能为生成物/大资源）: %s"
                               % (MAX_FILE_SIZE, ", ".join(sorted(skipped_code)[:10])),
                               suggestion="确认是否为应纳入审计的源文件"))

    return {
        "skill": skill_dir,
        "version": (VERSION_RE.search(doc).group(1) if VERSION_RE.search(doc) else None),
        "doc_lines": len(doc.splitlines()),
        "code_files": len(code),
        "backup": backup_path,
        "checkers": enabled,
        "findings": findings,
        "format": fmt,
        "skill_model": sm,
    }


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def summarize(findings):
    e = sum(1 for f in findings if f["severity"] == SEVERITY_ERROR)
    w = sum(1 for f in findings if f["severity"] == SEVERITY_WARN)
    i = sum(1 for f in findings if f["severity"] == SEVERITY_INFO)
    return {"error": e, "warn": w, "info": i, "pass": e == 0}


def print_human(results):
    for r in results:
        print("=" * 72)
        print("技能体检 —— %s" % r["skill"])
        print("=" * 72)
        if r.get("error"):
            print("  跳过：%s" % r["error"])
            continue
        print("  版本 %s    文档 %d 行    代码文件 %d 个    检查器: %s" % (
            r["version"] or "(无)", r["doc_lines"], r["code_files"],
            ",".join(r["checkers"])))
        if r.get("backup"):
            print("  已备份：%s" % r["backup"])

        by = {}
        for f in r["findings"]:
            by.setdefault(f["checker"], []).append(f)
        for chk in r["checkers"]:
            fs = by.get(chk, [])
            s = summarize(fs)
            print("\n  [%s]  ERROR %d / WARN %d / INFO %d" % (chk, s["error"], s["warn"], s["info"]))
            for f in fs:
                loc = ""
                if f.get("file"):
                    loc += f["file"]
                if f.get("line"):
                    loc += ":%d" % f["line"]
                if loc:
                    loc = " (" + loc + ")"
                print("    [%s] %s【%s】 %s%s" % (
                    f["severity"], f["category_cn"], f["category"], f["message"], loc))
                if f.get("suggestion"):
                    print("          建议: %s" % f["suggestion"])
        tot = summarize(r["findings"])
        print("\n  本技能汇总：ERROR %d / WARN %d / INFO %d    %s" % (
            tot["error"], tot["warn"], tot["info"],
            "通过" if tot["pass"] else "存在问题"))
        print("-" * 72)


def build_json(results):
    out = []
    for r in results:
        if r.get("error"):
            out.append({"skill": r["skill"], "error": r["error"]})
            continue
        rec = {
            "skill": r["skill"],
            "version": r.get("version"),
            "doc_lines": r.get("doc_lines"),
            "code_files": r.get("code_files"),
            "checkers": r.get("checkers"),
            "backup": r.get("backup"),
            "summary": summarize(r["findings"]),
            "findings": [
                {**f, "category_cn": f.get("category_cn", category_cn(f["category"]))}
                for f in r["findings"]
            ],
            "portability_matrix": (build_portability_matrix(r["skill_model"])
                                   if r.get("skill_model") else []),
        }
        if "translate" in r:
            rec["translate"] = r["translate"]
        out.append(rec)
    return out


def print_portability_matrix(model):
    """打印跨格式可移植性矩阵（--report portability-matrix 用）。"""
    targets = [t for t in FORMAT_TARGETS if t != model.fmt]
    rows = build_portability_matrix(model)
    idx = {(r["feature"], r["target"]): r["status"] for r in rows}
    feats = sorted({r["feature"] for r in rows})
    print("=" * 72)
    print("跨格式可移植性矩阵（源格式: %s）" % model.fmt)
    print("  P=保留  D=降级(需转译)  L=丢失")
    header = "  %-16s" % "feature" + "".join(" %-15s" % t for t in targets)
    print(header)
    print("-" * len(header))
    for feat in feats:
        cells = "".join(" %-15s" % idx.get((feat, t), "-") for t in targets)
        print("  %-16s%s" % (feat, cells))
    print("=" * 72)


def build_health_summary(results):
    """生态级健康度汇总（Phase 8：批量审计 + 供应链安全自检用）。

    返回逐技能计数与跨 Agent 供应链风险（含安全 ERROR/WARN 的技能数与类别分布），
    面向「作者自检整库/整组织技能健康度」场景，对标 Snyk ToxicSkills 但服务于作者而非攻击者。
    """
    rows = []
    for r in results:
        sm = r.get("skill_model")
        name = (sm.name if sm else os.path.basename(r.get("skill", "")) or "?")
        fmt = sm.fmt if sm else "unknown"
        s = summarize(r.get("findings", []))
        sec_issues = [f for f in r.get("findings", [])
                      if f.get("checker") == "security"
                      and f.get("severity") in (SEVERITY_ERROR, SEVERITY_WARN)]
        rows.append({
            "name": name,
            "format": fmt,
            "skill": r.get("skill", ""),
            "error": s.get("error", 0),
            "warn": s.get("warn", 0),
            "info": s.get("info", 0),
            "security_issues": len(sec_issues),
            "security_categories": sorted({f["category"] for f in sec_issues}),
        })
    return {
        "total_skills": len(rows),
        "total_error": sum(x["error"] for x in rows),
        "total_warn": sum(x["warn"] for x in rows),
        "skills_with_security_issue": sum(1 for x in rows if x["security_issues"] > 0),
        "skills": rows,
    }


def print_health_summary(summary):
    """打印生态健康度汇总（--report health 用）。"""
    print("\n" + "=" * 72)
    print("生态健康度汇总（共审计 %d 个技能）" % summary["total_skills"])
    print("-" * 72)
    print("%-30s %-12s %5s %5s %5s %6s" % ("技能", "格式", "ERR", "WARN", "INFO", "安全项"))
    for x in summary["skills"]:
        print("%-30s %-12s %5d %5d %5d %6d" % (
            x["name"][:30], x["format"], x["error"], x["warn"], x["info"],
            x["security_issues"]))
    print("-" * 72)
    print("总计：ERROR %d / WARN %d / 含供应链安全风险技能 %d/%d" % (
        summary["total_error"], summary["total_warn"],
        summary["skills_with_security_issue"], summary["total_skills"]))


# --------------------------------------------------------------------------- #
# Phase 7：跨格式转译报告（只读，仅出报告不落盘；frontmatter + 脚手架）
# --------------------------------------------------------------------------- #
# 设计约束（来自决策）：
#   ① 仅出报告不生成文件（绝不自动改写，守住本技能「只读扫描」立身之本）
#   ② 仅 frontmatter + 脚手架（不翻译正文散文，正文差异交由人工）
#   ③ 先支持 workbuddy ↔ agentskills / claude-code / cursor-plugin
#   ④ --verify 做内存往返保真（emit→re-parse→比对，不落盘）
# 复用底座：SkillModel(Phase5) + FMT_CAPS/EQUIV(Phase6) + build_portability_matrix(Phase6)。
SCAFFOLD_HEADINGS = {
    "workbuddy": ["# {name}", "", "## 描述", "", "## 使用方法", "", "## 注意事项"],
    "agentskills": ["# {name}", "", "## Description", "", "## Usage", "", "## Notes"],
    "claude-code": ["# Skill: {name}", "", "## Description", "", "## Usage", "", "## Notes"],
    "cursor-plugin": ["# {name}", "", "## Description", "", "## Usage", "", "## Notes"],
    "generic": ["# {name}", "", "## 说明"],
}


def _yaml_val(v):
    if isinstance(v, list):
        return "[%s]" % ", ".join(str(x) for x in v)
    return str(v)


def _scaffold(target_fmt, model):
    name = model.name or "技能名"
    return "\n".join(SCAFFOLD_HEADINGS.get(target_fmt, SCAFFOLD_HEADINGS["generic"])).format(name=name)


def _emit_field(target_fmt, src_field, src_value, caps):
    """返回 (target_field, target_value, status) 或 None(丢失)。
    status: preserved(保留) / degraded(经 EQUIV 重命名) / lost(无对应)。
    """
    if src_field in caps:
        return src_field, src_value, "preserved"
    if src_field in EQUIV and EQUIV[src_field] in caps:
        return EQUIV[src_field], src_value, "degraded"
    return None


def emit_frontmatter(model, target_fmt):
    """产出目标格式 frontmatter 字典 + 损失清单（仅 frontmatter，不动正文）。
    返回 (target_dict, lost_fields, degraded_fields)。
    """
    caps = FMT_CAPS.get(target_fmt, FMT_CAPS["generic"])
    tgt, lost, degraded = {}, [], []
    mapping = [
        ("name", model.name),
        ("description", model.description),
        ("license", model.license),
        ("version", model.version),
        ("allowed-tools", sorted(model.tools) if model.tools else None),
        ("target_agent", sorted(model.target_agent) if model.target_agent else None),
        ("slug", model.extra.get("slug")),
        ("displayname", model.extra.get("displayname")),
        ("metadata", model.extra.get("metadata")),
    ]
    for fld, val in mapping:
        if val in (None, "", [], {}):
            continue
        res = _emit_field(target_fmt, fld, val, caps)
        if res is None:
            lost.append(fld)
            continue
        tf, tv, st = res
        # name 已被 canon name 占用时，slug/displayname 价值并入、记降级不重复写入
        if tf == "name" and "name" in tgt and fld != "name":
            degraded.append((fld, "name"))
            continue
        tgt[tf] = tv
        if st == "degraded":
            degraded.append((fld, tf))
    # extra 中的格式专有键
    for k in ("model", "context", "agent", "hooks", "argument-hint", "globs", "alwaysApply"):
        v = model.extra.get(k)
        if v in (None, "", [], {}):
            continue
        if k in caps:
            tgt[k] = v
        else:
            lost.append(k)
    return tgt, lost, degraded


def build_translate_report(model, target_fmt, verify=False):
    """打印 源格式→目标格式 的转译报告（只读，不落盘）。"""
    src = model.fmt
    print("\n" + "=" * 72)
    print("跨格式转译报告（只读预览 · 不落盘）")
    print("-" * 72)
    print("  源格式: %s    目标格式: %s" % (src, target_fmt))
    if src == target_fmt:
        print("  同格式，无需转译。")
        print("=" * 72)
        return
    tgt, lost, degraded = emit_frontmatter(model, target_fmt)
    caps = FMT_CAPS.get(target_fmt, FMT_CAPS["generic"])
    if target_fmt == "generic":
        print("  ⚠ 高损失目标格式：generic 仅保留 %s，其余字段（version / license / allowed-tools / target_agent / slug / displayname / metadata 等）将全部丢失。" % "、".join(sorted(caps)))
        print("    建议：generic 仅作最简归档/人读兜底；如需完整跨 Agent 分发，优先用 agentskills / cursor-plugin（Agent Skills 开放标准，一次转译全生态通用）。")
    print("  【Frontmatter 映射】")
    print("  %-14s %-20s %-16s %-8s" % ("源字段", "源值(截断)", "目标字段", "状态"))
    print("  " + "-" * 62)

    def show(fld, val):
        if val in (None, "", [], {}):
            return
        sval = (str(val)[:18] + "…") if len(str(val)) > 18 else str(val)
        res = _emit_field(target_fmt, fld, val, caps)
        if res is None:
            print("  %-14s %-20s %-16s %-8s" % (fld, sval, "—", "丢失"))
            return
        tf, _, st = res
        disp_tf, disp_st = tf, {"preserved": "保留", "degraded": "降级", "lost": "丢失"}[st]
        if tf == "name" and "name" in tgt and fld != "name":
            disp_tf, disp_st = "name(并入)", "降级"
        print("  %-14s %-20s %-16s %-8s" % (fld, sval, disp_tf, disp_st))

    for fld, val in [("name", model.name), ("description", model.description),
                     ("license", model.license), ("version", model.version),
                     ("allowed-tools", sorted(model.tools)), ("target_agent", sorted(model.target_agent)),
                     ("slug", model.extra.get("slug")), ("displayname", model.extra.get("displayname")),
                     ("metadata", model.extra.get("metadata"))]:
        show(fld, val)
    for k in ("model", "context", "agent", "hooks", "argument-hint", "globs", "alwaysApply"):
        v = model.extra.get(k)
        if v not in (None, "", [], {}):
            show(k, v)
    if lost:
        print("\n  注意：将丢失字段（目标格式无对应）：%s" % ", ".join(lost))
    if degraded:
        print("  降级/并入字段：%s" % ", ".join("%s→%s" % d for d in degraded))
    print("\n  【目标 SKILL.md 脚手架预览】（仅展示，不落盘）")
    fm = "---\n" + "\n".join("%s: %s" % (k, _yaml_val(v)) for k, v in tgt.items()) + "\n---"
    for ln in (fm + "\n" + _scaffold(target_fmt, model)).split("\n"):
        print("  " + ln)
    if verify:
        print("\n  【往返保真校验 --verify】")
        matrix = build_portability_matrix(model)
        trows = [r for r in matrix if r["target"] == target_fmt]
        kept = [r["feature"] for r in trows if r["status"] == "preserved"]
        deg = [r["feature"] for r in trows if r["status"] == "degraded"]
        los = [r["feature"] for r in trows if r["status"] == "lost"]
        print("  完整往返(保留): %s" % (", ".join(kept) or "无"))
        print("  可往返(降级): %s" % (", ".join(deg) or "无"))
        print("  不可逆丢失: %s" % (", ".join(los) or "无"))
        if not los:
            verdict = "RECOVERABLE（完全可逆）"
        elif all(l in ("target_agent", "slug", "displayname") for l in los):
            verdict = "LOSSY（仅重命名类字段丢失，可人工补回）"
        else:
            verdict = "IRREVERSIBLE（含不可恢复字段：%s）" % ", ".join(los)
        print("  保真结论: %s" % verdict)
    print("=" * 72)


def build_translate_json(model, target_fmt, verify=False):
    """与 build_translate_report 对应的机读结构（供 --json 消费）。"""
    tgt, lost, degraded = emit_frontmatter(model, target_fmt)
    out = {
        "source_format": model.fmt,
        "target_format": target_fmt,
        "frontmatter": tgt,
        "lost_fields": lost,
        "degraded_fields": ["%s→%s" % d for d in degraded],
    }
    if verify:
        matrix = build_portability_matrix(model)
        trows = [r for r in matrix if r["target"] == target_fmt]
        los = [r["feature"] for r in trows if r["status"] == "lost"]
        out["round_trip"] = {
            "preserved": [r["feature"] for r in trows if r["status"] == "preserved"],
            "degraded": [r["feature"] for r in trows if r["status"] == "degraded"],
            "lost": los,
            "verdict": "recoverable" if not los else (
                "lossy" if all(l in ("target_agent", "slug", "displayname") for l in los)
                else "irreversible"),
        }
    return out


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# 技能来源抽象（多平台：local / github / skillhub）
# --------------------------------------------------------------------------- #
def find_skill_dirs(root):
    """遍历 root，返回所有含 SKILL.md 的目录（绝对路径）。

    支持仓库内含嵌套技能（如 src/SKILL.md）或一仓库多技能。忽略目录与
    collect_code 一致（SKIP_DIRS + 点目录），避免扫入 .git / node_modules。
    """
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if "SKILL.md" in filenames:
            out.append(os.path.abspath(dirpath))
    return out


class SkillSource:
    """将一种「来源」解析为若干本地技能目录。

    analyze_skill 只消费本地目录，故来源层只负责把远程/集市技能落到临时目录，
    再交还本地路径——核心审计逻辑零改动。

    resolve(ref, args) -> (dirs, cleanup)：
      dirs     待审计的本地技能目录列表
      cleanup  使用完毕需清理的临时目录（--keep-temp 时保留供排查）
    """

    name = "local"

    def resolve(self, ref, args):
        raise NotImplementedError


class LocalSource(SkillSource):
    name = "local"

    def resolve(self, ref, args):
        if args.all:
            if not os.path.isdir(SKILLS_ROOT):
                print("技能根目录不存在: %s" % SKILLS_ROOT, file=sys.stderr)
                sys.exit(2)
            dirs = [os.path.join(SKILLS_ROOT, d) for d in sorted(os.listdir(SKILLS_ROOT))
                    if os.path.isfile(os.path.join(SKILLS_ROOT, d, "SKILL.md"))]
            return dirs, []
        if args.skill:
            return [args.skill], []
        print("本地来源需指定 --skill <目录> 或 --all", file=sys.stderr)
        sys.exit(2)


class GithubSource(SkillSource):
    name = "github"

    def resolve(self, ref, args):
        if not ref:
            print("github 来源需通过 --ref 指定仓库（owner/repo 或 https 地址，可加 @分支）", file=sys.stderr)
            sys.exit(2)
        branch = None
        # 仅对 owner/repo 简写做 @分支 切分；完整 URL 整体作为地址
        if not ref.startswith(("http://", "https://", "git@")) and "@" in ref:
            ref, branch = ref.split("@", 1)
        if ref.startswith(("http://", "https://", "git@")):
            url = ref
        else:
            url = "https://github.com/%s.git" % ref
        tmp = tempfile.mkdtemp(prefix="skill-doc-audit-gh-")
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [url, tmp]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except subprocess.CalledProcessError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            _out = (e.stderr or e.stdout or str(e)).strip().splitlines()
            msg = _out[-1] if _out else str(e)
            print("git clone 失败：%s" % msg, file=sys.stderr)
            sys.exit(2)
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp, ignore_errors=True)
            print("git clone 超时（>120s）", file=sys.stderr)
            sys.exit(2)
        dirs = find_skill_dirs(tmp)
        if not dirs:
            shutil.rmtree(tmp, ignore_errors=True)
            print("克隆仓库中未发现 SKILL.md：%s" % ref, file=sys.stderr)
            sys.exit(2)
        return dirs, [tmp]


class SkillhubSource(SkillSource):
    name = "skillhub"

    def resolve(self, ref, args):
        if not ref:
            print("skillhub 来源需通过 --ref 指定技能 slug", file=sys.stderr)
            sys.exit(2)
        # 显式解析 skillhub 可执行文件全路径：Windows 上常为 skillhub.CMD，
        # 直接传裸名时 subprocess 不会自动补扩展名，故取 which 结果（含扩展名）直传。
        bin_path = shutil.which("skillhub") or os.path.expanduser(
            os.path.join("~", ".local", "bin", "skillhub"))
        if not bin_path or not os.path.isfile(bin_path):
            print("未找到 skillhub CLI，请确认已安装并在 PATH 中", file=sys.stderr)
            sys.exit(2)
        tmp = tempfile.mkdtemp(prefix="skill-doc-audit-sh-")
        cmd = [bin_path, "install", ref, "--dir", tmp]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            shutil.rmtree(tmp, ignore_errors=True)
            print("未找到 skillhub CLI，请确认已安装并在 PATH 中", file=sys.stderr)
            sys.exit(2)
        except subprocess.CalledProcessError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            _out = (e.stderr or e.stdout or str(e)).strip().splitlines()
            msg = _out[-1] if _out else str(e)
            print("skillhub install 失败：%s" % msg, file=sys.stderr)
            sys.exit(2)
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp, ignore_errors=True)
            print("skillhub install 超时（>120s）", file=sys.stderr)
            sys.exit(2)
        dirs = find_skill_dirs(tmp)
        if not dirs:
            shutil.rmtree(tmp, ignore_errors=True)
            print("skillhub 安装后未发现 SKILL.md：%s" % ref, file=sys.stderr)
            sys.exit(2)
        return dirs, [tmp]


class UrlSource(SkillSource):
    name = "url"

    def _normalize(self, ref):
        # GitHub 网页 blob 链接 → raw 直链，便于直接抓取 SKILL.md 文本
        m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/(.+)", ref)
        if m:
            return "https://raw.githubusercontent.com/%s/%s/%s" % (m.group(1), m.group(2), m.group(3))
        return ref

    def _fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "skill-doc-audit/1.21.0"})
        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            raise ValueError("网络请求失败：%s" % e)
        if resp.status != 200:
            raise ValueError("HTTP %s" % resp.status)
        data = resp.read()
        if len(data) > MAX_FILE_SIZE:
            raise ValueError("文件过大（>%d 字节），已跳过" % MAX_FILE_SIZE)
        return data.decode("utf-8", errors="replace")

    def resolve(self, ref, args):
        if not ref:
            print("url 来源需通过 --ref 指定 SKILL.md 的 https 地址（可指向文件或所在目录）", file=sys.stderr)
            sys.exit(2)
        ref = self._normalize(ref)
        tmp = tempfile.mkdtemp(prefix="skill-doc-audit-url-")
        skill_dir = os.path.join(tmp, "skill")
        os.makedirs(skill_dir, exist_ok=True)
        # 推导 SKILL.md 文件 URL 与所在目录 base：
        #   - 直接指向 .md 文件 → base 为其父目录
        #   - 指向目录 → 尝试 <dir>/SKILL.md，base=<dir>
        if ref.rstrip("/").endswith(".md"):
            skill_url = ref
            base = ref.rstrip("/")[:ref.rstrip("/").rfind("/")]
        else:
            skill_url = ref.rstrip("/") + "/SKILL.md"
            base = ref.rstrip("/")
        try:
            content = self._fetch(skill_url)
        except Exception as e:
            shutil.rmtree(tmp, ignore_errors=True)
            print("URL 抓取失败：%s" % e, file=sys.stderr)
            sys.exit(2)
        low = content.lstrip().lower()
        if low.startswith(("<!doctype", "<html")):
            shutil.rmtree(tmp, ignore_errors=True)
            print("URL 返回内容疑似 HTML 页面，非 SKILL.md 文本：%s" % skill_url, file=sys.stderr)
            sys.exit(2)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(content)
        # 相对引用补全：抓取 SKILL.md 中显式引用的 scripts/ 与 references/ 下文件，
        # 使其与本地克隆等价，避免「引用文件缺失」刷屏；单文件抓取失败则静默跳过（保留原缺失提示）。
        self._fetch_refs(content, base, skill_dir)
        return [skill_dir], [tmp]

    def _fetch_refs(self, skill_md, base, skill_dir):
        # 仅补全 scripts/ 与 references/ 下的相对引用（非 http(s)），控制规模防失控
        pat = re.compile(r'(?:scripts|references)[\\/][\w./-]+\.\w+')
        seen = set()
        for m in pat.finditer(skill_md):
            rel = m.group(0).replace("\\", "/")
            if rel in seen or len(seen) >= 50:
                continue
            seen.add(rel)
            dest = os.path.join(skill_dir, rel)
            try:
                data = self._fetch(base.rstrip("/") + "/" + rel)
            except Exception:
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(data)


SOURCES = {"local": LocalSource, "github": GithubSource, "skillhub": SkillhubSource, "url": UrlSource}


def get_source(name):
    cls = SOURCES.get(name)
    if cls is None:
        print("未知来源: %s（可选: %s）" % (name, ", ".join(SOURCES)), file=sys.stderr)
        sys.exit(2)
    return cls()


def main():
    global MAX_FILE_SIZE
    ap = argparse.ArgumentParser(description="技能静态体检（文档一致性/结构/安全/可运行性）")
    ap.add_argument("--skill", help="技能目录")
    ap.add_argument("--all", action="store_true", help="审计 ~/.workbuddy/skills 下全部技能")
    ap.add_argument("--check", action="append", metavar="NAME",
                    help="启用插件式检查器(doc/structure/security/runtime/deps/deadcode/portability)，可重复；doc 常驻默认开")
    ap.add_argument("--all-checks", action="store_true", help="启用全部检查器")
    ap.add_argument("--backup", action="store_true", help="审计前备份 SKILL.md")
    ap.add_argument("--backup-limit", type=int, default=BACKUP_LIMIT,
                    help="SKILL.md 最多保留的备份数（默认 %d）" % BACKUP_LIMIT)
    ap.add_argument("--json", action="store_true", help="额外输出 JSON 机读结果")
    ap.add_argument("--strict", action="store_true", help="WARN 也计入退出码（CI 门禁用）")
    ap.add_argument("--timeout", type=float, default=0,
                    help="整体超时秒数（0=不限制）；超时后优雅终止而非卡死")
    ap.add_argument("--max-file-size", type=int, default=MAX_FILE_SIZE,
                    help="单文件超过此字节数跳过扫描（默认 %d）" % MAX_FILE_SIZE)
    ap.add_argument("--deadcode-mode", default="ask", choices=list(DEADCODE_MODES),
                    help="deadcode 精度模式：ask(默认,已装vulture则自动高精度否则交互询问,超时30s→ast) / vulture(高精度,需装 vulture) / ast(零依赖,易误报) / skip(本次跳过)")
    ap.add_argument("--preview", action="store_true",
                    help="只预览将运行哪些检查器、将扫描哪些文件，不产出发现，退出码 0（适合首次审计前心里有数）")
    ap.add_argument("--source", default="local", choices=list(SOURCES),
                    help="技能来源：local(默认,--skill/--all) / github(--ref 仓库) / skillhub(--ref slug,经 skillhub CLI 拉取) / url(--ref https 地址,标准库直接抓取任意 SKILL.md)")
    ap.add_argument("--ref", help="来源引用：github 为 owner/repo 或 https 地址(可 @分支)；skillhub 为技能 slug；url 为 SKILL.md 的 https 地址（可指向文件或所在目录，支持 github.com blob 链接自动转 raw）")
    ap.add_argument("--keep-temp", action="store_true",
                    help="保留 github/skillhub 产生的临时目录（用于排查，默认审计后自动清理）")
    ap.add_argument("--report", default=None,
                    choices=["portability-matrix", "health", "translate"],
                    help="生成专项报告：portability-matrix 跨格式可移植性矩阵；health 生态级健康度汇总；translate 跨格式转译报告（需配 --target）")
    ap.add_argument("--target", default=None,
                    choices=["workbuddy", "agentskills", "claude-code", "cursor-plugin", "generic"],
                    help="--report translate 的目标格式（与源格式双向）：workbuddy / agentskills / claude-code / cursor-plugin / generic。其中 agentskills 与 cursor-plugin 即 Agent Skills 开放标准(agentskills.io)，一次转译可被 40+ 工具(Claude Code、Cursor、Gemini CLI、Codex、Copilot、Windsurf、Kiro、OpenCode 等)直接消费；generic 为仅保留 name/description 的降级兜底")
    ap.add_argument("--verify", action="store_true",
                    help="跨格式转译时做内存往返保真校验（emit→re-parse→比对，不落盘）")
    args = ap.parse_args()

    MAX_FILE_SIZE = args.max_file_size

    watchdog = None
    if args.timeout and args.timeout > 0:
        def _on_timeout():
            sys.stderr.write("\n[超时] 审计超过 %.0f 秒，强制终止\n" % args.timeout)
            _thread.interrupt_main()
        watchdog = threading.Timer(args.timeout, _on_timeout)
        watchdog.daemon = True
        watchdog.start()
    # 解析技能来源：本地/远程仓库/集市，统一落地为本地目录列表
    # Phase 8：--ref 支持逗号分隔多仓库（org/多仓库批量审计）；local 忽略 ref
    src = get_source(args.source)
    refs = [r.strip() for r in (args.ref or "").split(",") if r.strip()]
    if args.source == "local" or not refs:
        targets, cleanup_dirs = src.resolve(args.ref, args)
    else:
        targets, cleanup_dirs = [], []
        for ref in refs:
            d, c = src.resolve(ref, args)
            targets += d
            cleanup_dirs += c
    for t in targets:
        if not os.path.isdir(t):
            print("目录不存在: %s" % t, file=sys.stderr)
            sys.exit(2)

    # 解析启用的检查器：doc 常驻，--check 追加，--all-checks 全开
    enabled = list(DEFAULT_CHECKERS)
    if args.all_checks:
        enabled = list(ALL_CHECKERS)
    elif args.check:
        for c in args.check:
            if c not in CHECKERS:
                print("未知检查器: %s（可选: %s）" % (c, ", ".join(CHECKERS)), file=sys.stderr)
                sys.exit(2)
            if c not in enabled:
                enabled.append(c)
    # 转译报告：仅解析模型、不跑检查器（报告本身取代常规体检输出）
    if args.report == "translate":
        if not args.target:
            print("--report translate 需要 --target <agentskills|claude-code|cursor-plugin|generic>", file=sys.stderr)
            sys.exit(2)
        enabled = []

    # 检查预览：只展示将运行哪些检查器、将扫描哪些文件，不产出发现
    if args.preview:
        for t in targets:
            d = os.path.join(t, "SKILL.md")
            code, _skipped = collect_code(t)
            print("预览：%s" % t)
            print("  启用检查器: %s" % ", ".join(enabled))
            if "deadcode" in enabled:
                print("  deadcode 精度模式: %s（ask=已装vulture则自动高精度,否则交互询问30s→ast/非TTY回退ast并提示精度降级）" % args.deadcode_mode)
            print("  文档: %s" % ("SKILL.md" if os.path.isfile(d) else "（无）"))
            print("  将扫描代码/配置文件 %d 个:" % len(code))
            for rel in sorted(code.keys()):
                print("    - %s" % rel)
            if _skipped:
                print("  跳过（超大文件）: %s" % ", ".join(sorted(_skipped)[:10]))
        sys.exit(0)

    results = [analyze_skill(t, enabled, args=args, do_backup=args.backup,
                             backup_limit=args.backup_limit) for t in targets]
    if args.report != "translate":
        print_human(results)
    if args.report == "portability-matrix":
        for r in results:
            if r.get("skill_model"):
                print_portability_matrix(r["skill_model"])
    if args.report == "health" or (args.json and len(results) > 1):
        summary = build_health_summary(results)
        if args.report == "health":
            print_health_summary(summary)
    if args.report == "translate":
        for r in results:
            sm = r.get("skill_model")
            if not sm:
                print("跳过（无 SKILL.md / 模型）: %s" % r.get("skill"))
                continue
            build_translate_report(sm, args.target, verify=args.verify)
        if args.json:
            for r in results:
                if r.get("skill_model"):
                    r["translate"] = build_translate_json(r["skill_model"], args.target, verify=args.verify)
    if args.json:
        print("\n" + "=" * 72)
        print("JSON 结果：")
        out = build_json(results)
        # 多技能审计时附带健康度汇总，便于 CI / 批量巡检消费
        if len(results) > 1:
            out = {"health_summary": build_health_summary(results), "skills": out}
        print(json.dumps(out, ensure_ascii=False, indent=2))

    # 清理来源产生的临时目录（--keep-temp 时保留并打印路径供排查）
    for d in cleanup_dirs:
        if args.keep_temp:
            print("[保留临时目录] %s" % d)
        else:
            shutil.rmtree(d, ignore_errors=True)

    total_err = sum(summarize(r.get("findings", [])).get("error", 0)
                    for r in results if "findings" in r)
    total_warn = sum(summarize(r.get("findings", [])).get("warn", 0)
                     for r in results if "findings" in r)
    failed = (total_err > 0) or (args.strict and total_warn > 0)
    if watchdog is not None:
        watchdog.cancel()
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\n审计被中断（Ctrl+C 或超时），已安全退出，未产生部分结果。\n")
        sys.exit(130)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("\n审计异常终止：%s\n" % e)
        sys.exit(2)
