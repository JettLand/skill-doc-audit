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
  - --all-checks  启用全部检查器
  检查器只扫描不改写；description 四要素、制作质量评分等需语义判断的项仅给提示(INFO)。

退出码：0=未发现 ERROR（--strict 下还需无 WARN）；1=发现 ERROR 或（--strict 下）WARN；2=参数或路径错误

用法：
  python audit_docs.py --skill <技能目录>                  # 仅运行常驻 doc 检查器
  python audit_docs.py --skill <技能目录> --check structure # doc + structure
  python audit_docs.py --skill <技能目录> --all-checks     # 全部检查器
  python audit_docs.py --all --all-checks                  # 审计全部技能（全检查器）
  python audit_docs.py --skill <目录> --backup             # 审计前先备份 SKILL.md
  python audit_docs.py --skill <目录> --json               # JSON 机读输出（同时仍打印可读报告）
  python audit_docs.py --skill <目录> --timeout 60         # 整体超时 60 秒，超时优雅终止（非卡死）
  python audit_docs.py --skill <目录> --max-file-size 2000000  # 超过此字节的文件跳过扫描
"""

import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import _thread

SKILLS_ROOT = os.path.expanduser("~/.workbuddy/skills")
BACKUP_LIMIT = 3  # 同一技能 SKILL.md 最多保留的备份数，防止频繁迭代产生过多 .bak 文件
SKIP_DIRS = {"__pycache__", "dist", "state", "logs", "node_modules",
             ".git", "evals", ".workbuddy", "archive", "vendor"}
CODE_EXT = (".py", ".js", ".sh", ".ps1", ".json")
MAX_FILE_SIZE = 2_000_000  # 单文件超过此字节数跳过扫描，避免超大文件拖慢/卡死

# ---- doc 检查器正则 ----
FILE_REF_RE = re.compile(r"`([\w./\\-]+\.(?:py|json|log|md|lnk|sh|ps1|asar|txt))`")
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


# --------------------------------------------------------------------------- #
# Finding 模型
# --------------------------------------------------------------------------- #
def finding(checker, severity, category, message, file=None, line=None, suggestion=None):
    return {
        "checker": checker,
        "severity": severity,
        "category": category,
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
                                    "文档引用的相对路径不存在: %s" % ref, file="SKILL.md",
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
    for m in IDENT_RE.finditer(doc):
        ident = m.group(1)
        if ident not in blob:
            findings.append(finding("doc", SEVERITY_ERROR, "UNKNOWN_IDENT",
                                    "文档提到的标识符在代码中不存在: %s" % ident, file="SKILL.md"))

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
    for m in re.finditer(r"(?:references|scripts)/[A-Za-z0-9_.\-/]+\.(?:md|py|json|sh|ps1)", doc):
        ref = m.group(0)
        if not os.path.exists(os.path.join(skill_dir, ref)):
            findings.append(finding("structure", SEVERITY_ERROR, "broken_ref",
                                    "加载式引用目标不存在: %s" % ref, file="SKILL.md",
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
        for m in re.finditer(r"(scripts/[A-Za-z0-9_\-]+\.(?:py|sh|ps1))", doc):
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
# 调度
# --------------------------------------------------------------------------- #
CHECKERS = {
    "doc": check_doc,
    "structure": check_structure,
    "security": check_security,
    "runtime": check_runtime,
    "deps": check_deps,
}
DEFAULT_CHECKERS = ["doc"]
ALL_CHECKERS = ["doc", "structure", "security", "runtime", "deps"]


def analyze_skill(skill_dir, enabled, do_backup=False, backup_limit=BACKUP_LIMIT):
    doc_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(doc_path):
        return {"skill": skill_dir, "error": "no SKILL.md", "findings": []}

    with open(doc_path, encoding="utf-8") as fh:
        doc = fh.read()
    scripts_dir = os.path.join(skill_dir, "scripts")
    code, skipped_code = collect_code(skill_dir)
    blob = "\n".join(code.values())

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
                print("    [%s] %s%s" % (f["severity"], f["message"], loc))
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
            "findings": r["findings"],
        })
    return out


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def main():
    global MAX_FILE_SIZE
    ap = argparse.ArgumentParser(description="技能静态体检（文档一致性/结构/安全/可运行性）")
    ap.add_argument("--skill", help="技能目录")
    ap.add_argument("--all", action="store_true", help="审计 ~/.workbuddy/skills 下全部技能")
    ap.add_argument("--check", action="append", metavar="NAME",
                    help="启用插件式检查器(doc/structure/security/runtime/deps)，可重复；doc 常驻默认开")
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
    if args.all:
        if not os.path.isdir(SKILLS_ROOT):
            print("技能根目录不存在: %s" % SKILLS_ROOT, file=sys.stderr)
            sys.exit(2)
        targets = [os.path.join(SKILLS_ROOT, d) for d in sorted(os.listdir(SKILLS_ROOT))
                   if os.path.isfile(os.path.join(SKILLS_ROOT, d, "SKILL.md"))]
    elif args.skill:
        targets = [args.skill]
    else:
        print("需指定 --skill <目录> 或 --all", file=sys.stderr)
        sys.exit(2)

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

    results = [analyze_skill(t, enabled, do_backup=args.backup,
                             backup_limit=args.backup_limit) for t in targets]
    print_human(results)
    if args.json:
        print("\n" + "=" * 72)
        print("JSON 结果：")
        print(json.dumps(build_json(results), ensure_ascii=False, indent=2))

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
