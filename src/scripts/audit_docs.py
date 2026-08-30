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
      deadcode   死代码检测（未使用定义/导入、不可达代码、孤儿资源文件；已纳入 --all-checks，运行前询问精度模式）
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
    # runtime：脚本可运行性
    "py_syntax": "Python 语法错误",
    "py_check_fail": "语法校验失败",
    "script_ref_missing": "脚本引用缺失",
    "capability": "能力预检（静态列举）",
    # deps：依赖与平台声明
    "undeclared_cli": "未声明外部 CLI",
    "platform_undeclared": "未声明运行平台",
    # deadcode：死代码检测（已纳入 --all-checks，运行前按 --deadcode-mode 询问精度）
    "unused_def": "未使用的定义",
    "unused_import": "未使用的导入",
    "unreachable": "不可达代码",
    "orphan_asset": "孤立资源文件",
    "vulture": "高精度死代码（可选）",
}


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
            findings.append(finding("doc", SEVERITY_WARN, "UNKNOWN_IDENT",
                                    "文档里提到的名称 %s 在代码里找不到（可能拼写有误或已被删除；若为外部 MCP/插件工具请在 frontmatter 的 allowed-tools 声明）" % ident, file="SKILL.md"))

    # A5 版本号
    if not VERSION_RE.search(doc):
        findings.append(finding("doc", SEVERITY_ERROR, "VERSION_MISSING",
                                "SKILL.md 缺少 version 声明", file="SKILL.md",
                                suggestion="添加 version: x.y.z"))

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
            findings.append(finding("structure", SEVERITY_ERROR, "version_missing",
                                    "frontmatter 缺少合规 version",
                                    suggestion="添加 version: x.y.z"))
        if not name_m:
            findings.append(finding("structure", SEVERITY_ERROR, "name_missing",
                                    "frontmatter 缺少 name 声明",
                                    suggestion="添加 name: <技能目录名>"))
        if not re.search(r"^license:", fm_text, re.M):
            findings.append(finding("structure", SEVERITY_WARN, "license_missing",
                                    "frontmatter 缺少 license 声明",
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

    # 硬编码用户绝对路径
    for m in re.finditer(r"[A-Za-z]:\\Users\\[^\s`]+|/home/[^\s`]+|/Users/[^\s`]+", doc):
        findings.append(finding("structure", SEVERITY_WARN, "hardcoded_path",
                                "文档含硬编码用户绝对路径: %s" % m.group(0), file="SKILL.md",
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
        if not re.search(r"windows|仅.*windows|平台.*windows|platform", doc, re.I):
            findings.append(finding("deps", SEVERITY_INFO, "platform_undeclared",
                                    "代码含 Windows 专属 API（%s 等），建议声明运行平台" %
                                    ", ".join(sorted(win_hits)[:5]),
                                    suggestion="在文档注明「仅支持 Windows」或补充平台元信息"))
    return findings


# --------------------------------------------------------------------------- #
# 检查器：deadcode（死代码检测，已纳入 --all-checks；运行前按 --deadcode-mode 询问精度模式）
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


def _resolve_deadcode_mode(args):
    """决定 deadcode 运行模式：ask/vulture/ast/skip。

    - 显式 --deadcode-mode vulture|ast|skip：直接用（供 Agent/CI 跳过交互）。
    - 默认 ask：环境已装 vulture 则直接采用高精度 vulture 模式（不重复询问）；
      未装 vulture 时：TTY 交互询问（超时 30s / 无输入 → ast 零依赖）；
      非 TTY（被管道或 Agent 调用）→ 直接 ast。
    """
    mode = getattr(args, "deadcode_mode", "ask") if args else "ask"
    if mode != "ask":
        if mode == "vulture" and _vulture_module() is None:
            sys.stderr.write("[deadcode] 未检测到 vulture 库，回退零依赖 AST 模式\n")
            return "ast"
        return mode
    # ask 模式：已装 vulture 直接走高精度，避免重复询问
    if _vulture_module() is not None:
        sys.stderr.write("[deadcode] 检测到 vulture 库，自动采用高精度模式（跳过询问）\n")
        return "vulture"
    if not sys.stdin.isatty():
        sys.stderr.write("[deadcode] 非交互环境，默认零依赖 AST 模式（若要 vulture/skip 请传 --deadcode-mode）\n")
        return "ast"
    return _prompt_deadcode_mode()


def _prompt_deadcode_mode():
    """交互询问 deadcode 模式；30 秒超时默认 ast（零依赖，易误报）。"""
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
        sys.stderr.write("\n[deadcode] 超时/无输入，默认零依赖 AST 模式\n")
        return "ast"
    if choice == "1":
        if _vulture_module() is None:
            sys.stderr.write("[deadcode] 未检测到 vulture 库，回退零依赖 AST 模式\n")
            return "ast"
        return "vulture"
    if choice == "3":
        return "skip"
    return "ast"


def check_deadcode(ctx):
    mode = _resolve_deadcode_mode(ctx.get("args"))
    if mode == "skip":
        return []
    findings = []
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
# 调度
# --------------------------------------------------------------------------- #
CHECKERS = {
    "doc": check_doc,
    "structure": check_structure,
    "security": check_security,
    "runtime": check_runtime,
    "deps": check_deps,
    "deadcode": check_deadcode,
}
DEFAULT_CHECKERS = ["doc"]
# deadcode 已纳入 --all-checks；ask 模式下已装 vulture 自动高精度，否则运行前询问精度（默认 ask，超时 30s→ast 零依赖）。
ALL_CHECKERS = ["doc", "structure", "security", "runtime", "deps", "deadcode"]


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
    _fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", doc, re.S)
    if _fm:
        for _key in ("allowed-tools", "tools"):
            _kv = re.search(r"^%s:\s*(.+)$" % re.escape(_key), _fm.group(1), re.M)
            if _kv:
                for _tok in re.split(r"[,;\s]+", _kv.group(1).strip()):
                    _tok = _tok.strip()
                    if not _tok:
                        continue
                    declared_tools.add(_tok)
                    if "__" in _tok:
                        declared_tools.add(_tok.rsplit("__", 1)[-1])
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
        out.append({
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
        })
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


SOURCES = {"local": LocalSource, "github": GithubSource, "skillhub": SkillhubSource}


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
                    help="启用插件式检查器(doc/structure/security/runtime/deps/deadcode)，可重复；doc 常驻默认开")
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
    ap.add_argument("--deadcode-mode", default="ask", choices=["ask", "vulture", "ast", "skip"],
                    help="deadcode 精度模式：ask(默认,已装vulture则自动高精度否则交互询问,超时30s→ast) / vulture(高精度,需装 vulture) / ast(零依赖,易误报) / skip(本次跳过)")
    ap.add_argument("--preview", action="store_true",
                    help="只预览将运行哪些检查器、将扫描哪些文件，不产出发现，退出码 0（适合首次审计前心里有数）")
    ap.add_argument("--source", default="local", choices=list(SOURCES),
                    help="技能来源：local(默认,--skill/--all) / github(--ref 仓库) / skillhub(--ref slug,经 skillhub CLI 拉取)")
    ap.add_argument("--ref", help="来源引用：github 为 owner/repo 或 https 地址(可 @分支)；skillhub 为技能 slug")
    ap.add_argument("--keep-temp", action="store_true",
                    help="保留 github/skillhub 产生的临时目录（用于排查，默认审计后自动清理）")
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
    src = get_source(args.source)
    targets, cleanup_dirs = src.resolve(args.ref, args)
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

    # 检查预览：只展示将运行哪些检查器、将扫描哪些文件，不产出发现
    if args.preview:
        for t in targets:
            d = os.path.join(t, "SKILL.md")
            code, _skipped = collect_code(t)
            print("预览：%s" % t)
            print("  启用检查器: %s" % ", ".join(enabled))
            if "deadcode" in enabled:
                print("  deadcode 精度模式: %s（ask=已装vulture则自动高精度,否则交互询问30s→ast/非TTY回退ast）" % args.deadcode_mode)
            print("  文档: %s" % ("SKILL.md" if os.path.isfile(d) else "（无）"))
            print("  将扫描代码/配置文件 %d 个:" % len(code))
            for rel in sorted(code.keys()):
                print("    - %s" % rel)
            if _skipped:
                print("  跳过（超大文件）: %s" % ", ".join(sorted(_skipped)[:10]))
        sys.exit(0)

    results = [analyze_skill(t, enabled, args=args, do_backup=args.backup,
                             backup_limit=args.backup_limit) for t in targets]
    print_human(results)
    if args.json:
        print("\n" + "=" * 72)
        print("JSON 结果：")
        print(json.dumps(build_json(results), ensure_ascii=False, indent=2))

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
