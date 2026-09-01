
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
  - --all-checks  启用全部检查器（含 deadcode 与 doc-llm：deadcode 已装 vulture 则自动高精度，否则询问
                  vulture/ast/skip；doc-llm 弹菜单询问是否启用 LLM 语义检测，30 秒超时默认不启用，绝不自动联网）
  检查器只扫描不改写；description 四要素、制作质量评分等需语义判断的项仅给提示(INFO)。

退出码：0=未发现 ERROR（--strict 下还需无 WARN）；1=发现 ERROR 或（--strict 下）WARN；2=参数或路径错误

用法：
  python audit_docs.py --skill <技能目录>                  # 仅运行常驻 doc 检查器
  python audit_docs.py --skill <技能目录> --check structure # doc + structure
  python audit_docs.py --skill <技能目录> --all-checks     # 全部检查器（含 deadcode 与 doc-llm，均运行前询问）
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
  python audit_docs.py --skill <技能目录> --dev-docs README.md CHANGELOG.md --all-checks   # 开发模式：把 README/CHANGELOG 一并纳入 doc 内容漂移与 doc-llm 语义漂移扫描（在仓库根目录运行）
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
    # doc-llm：语义漂移检测（Vector 2，v1.22.0 引入、v1.23.0 纳入全量，v1.24.0 起由 agent 直接接手，不再依赖外部 LLM）
    "DOC_LLM_DRIFT": "文档/代码语义漂移（agent 判定）",
    "doc_llm_agent_handoff": "语义漂移检测已转交 agent 接手",
    "doc_llm_skipped": "全量检测中语义漂移检测跳过（非交互环境，未调用任何 LLM）",
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
    # 检查器执行回执（v1.25.5）：身份 / 执行状态自检
    "CHECKER_UNKNOWN": "检查器未注册（从未被真正执行）",
    "CHECKER_ERROR": "检查器执行异常（已被捕获，未中断其余检查器）",
}


# --------------------------------------------------------------------------- #
# Vector 1 (v1.21.0)：doc 检查器「内容漂移」结构化声明交叉校验用常量
# --------------------------------------------------------------------------- #
# deadcode 精度模式权威集合：同时供 argparse choices 与 doc 漂移校验使用（单一真相源）
DEADCODE_MODES = ("ask", "vulture", "ast", "skip")
# doc-llm 语义漂移检测模式权威集合（Vector 2）：
# off=不运行；ask=交互终端弹菜单征得同意后由 agent 接手；agent=直接由 agent 用自身能力接手检测。
# v1.24.0 起：语义漂移检测一律由 agent 直接接手（使用 agent 自身能力），不再依赖外部 LLM 端点；
# v1.24.1 起：明确 agent 接手会占用 agent 自身推理 token（输入侧为主，输出极少），仅不向外部 LLM 服务
# 付费，故移除「零额外成本」误导表述；preview 模式（选项3）因会重复占用上下文 token 已移除。
DOCLLM_MODES = ("off", "agent", "ask")
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
def finding(checker, severity, category, message, file=None, line=None, suggestion=None, ref=None):
    return {
        "checker": checker,
        "severity": severity,
        "category": category,
        "category_cn": category_cn(category),
        "message": message,
        "file": file,
        "line": line,
        "suggestion": suggestion,
        # ref：被引用（若不存在即缺失）文件的归一化路径，仅供跨检查器去重归并使用；
        # 不参与任何比对/报告（人类报告按 checker/category 分组，机读快照按签名比对忽略此键）。
        "ref": ref,
    }


# --------------------------------------------------------------------------- #
# 通用辅助
# --------------------------------------------------------------------------- #
def collect_code(skill_dir, exclude=None):
    """收集技能目录下所有可作为基准的代码/配置文件内容（不含 SKILL.md）。

    返回 (files, skipped)：files 为 路径->内容；skipped 为因超过 MAX_FILE_SIZE
    而被跳过的文件相对路径列表（避免超大生成物/资源文件拖慢或卡死扫描）。
    exclude：额外排除的文件名集合（如开发期工具 sync_deploy.py / self_validate.py /
    make_fixtures.py，它们不属于发布面，纳入扫描会产生与技能质量无关的噪音）。
    """
    exc = set(exclude or set())
    files = {}
    skipped = []
    for root, dirs, names in os.walk(skill_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for n in names:
            if n in exc:
                continue
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


def resolve_exists(skill_dir, ref, scripts_dir, extra_roots=None):
    cand = ref.replace("/", os.sep).replace("\\", os.sep)
    paths = [
        os.path.join(skill_dir, cand),
        os.path.join(scripts_dir, os.path.basename(cand)),
        os.path.join(skill_dir, "scripts", cand),
    ]
    # 开发文档（如 README.md / CHANGELOG.md）里的引用常以仓库根为基准，额外按 extra_roots 解析，
    # 避免把「src/scripts/...」「hooks/...」这类仓库相对路径误判为死路径。
    for root in (extra_roots or []):
        paths.append(os.path.join(root, cand))
    # 绝对路径（如部署副本的 Windows 绝对路径）直接判存在，避免误报死路径
    if os.path.isabs(ref):
        paths.append(ref)
    return any(os.path.exists(p) for p in paths)


# --------------------------------------------------------------------------- #
# 缺失引用类 finding 去重（降噪）
# --------------------------------------------------------------------------- #
# 同一「被引用但不存在」的文件，会被 doc / structure / runtime 多个检查器各报一条
# （DEAD_PATH / broken_ref / script_ref_missing）；doc 检查器还会对同一裸文件名逐次报
# EXTERNAL_REF。这导致 ERROR/WARN 计数虚高、读数失真。此处按「引用路径」归并，合并为单条，
# 保留最高严重级，并在 message 标注命中检查器集合、附 dedup 溯源字段，便于 agent / 使用者复核。
# 设计要点：①仅归并「同一路径的同类重复」，绝不跨不同根因合并，不会掩盖真实缺陷；
# ②分组键含类型（missing / extref），缺失文件与裸文件名引用不会互相吞并。
_MISSING_REF_CATS = {"DEAD_PATH", "broken_ref", "script_ref_missing"}
_EXTREF_CATS = {"EXTERNAL_REF"}
_SEV_RANK = {SEVERITY_INFO: 0, SEVERITY_WARN: 1, SEVERITY_ERROR: 2}
_SEV_NAME = {0: SEVERITY_INFO, 1: SEVERITY_WARN, 2: SEVERITY_ERROR}
_REP_CHK_ORDER = {"doc": 0, "structure": 1, "runtime": 2}


def dedupe_findings(findings):
    """按引用路径归并跨检查器 / 同检查器重复的缺失引用类 finding。

    返回去重后的 finding 列表（原列表不变）。不参与去重的 finding 原样保留。
    """
    groups = {}          # key -> [finding]
    order = []           # 保持首次出现顺序
    kept = []            # 不参与去重的 finding（原样保留）
    for f in findings:
        cat = f.get("category")
        ref = f.get("ref")
        if ref and cat in _MISSING_REF_CATS:
            key = ("missing", ref)
        elif ref and cat in _EXTREF_CATS:
            key = ("extref", ref)
        else:
            kept.append(f)
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)
    if not groups:
        return findings
    out = list(kept)
    for key in order:
        grp = groups[key]
        if len(grp) == 1:
            out.append(grp[0])
            continue
        sev = max(_SEV_RANK[f["severity"]] for f in grp)
        sev_name = _SEV_NAME[sev]
        checkers = sorted({f["checker"] for f in grp},
                          key=lambda c: _REP_CHK_ORDER.get(c, 9))
        cats = sorted({f["category"] for f in grp})
        ref = key[1]
        # 代表 category：缺失类优先 DEAD_PATH，其次 broken_ref / script_ref_missing；extref 用 EXTERNAL_REF
        if "DEAD_PATH" in cats:
            rep_cat = "DEAD_PATH"
        elif "broken_ref" in cats:
            rep_cat = "broken_ref"
        elif "script_ref_missing" in cats:
            rep_cat = "script_ref_missing"
        else:
            rep_cat = cats[0]
        # 代表 checker：取拥有 rep_cat 的检查器（缺失类恒含 doc 的 DEAD_PATH；extref 恒为 doc）
        rep_chk = next((f["checker"] for f in grp if f["category"] == rep_cat), checkers[0])
        sugg = next((f["suggestion"] for f in grp if f.get("suggestion")), None)
        if key[0] == "missing":
            msg = "文档引用的文件 `%s` 不存在（被 %s 检查器重复报告，已合并去重）" % (
                ref, "、".join(checkers))
        else:
            msg = "裸文件名引用 `%s`，可能指向技能外文件（文档中多次出现，已合并去重）" % ref
        out.append({
            "checker": rep_chk,
            "severity": sev_name,
            "category": rep_cat,
            "category_cn": category_cn(rep_cat),
            "message": msg,
            "file": "SKILL.md",
            "line": None,
            "suggestion": sugg,
            "ref": ref,
            "dedup": {"checkers": checkers, "categories": cats, "count": len(grp)},
        })
    return out


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

# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# 跨模块共享 helper / 常量（v1.25.0 拆分后集中于此，避免检查器间循环导入）
# --------------------------------------------------------------------------- #
# [relocated from checkers/portability.py]
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

# [relocated from checkers/portability.py]
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

# [relocated from checkers/portability.py]
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

# [relocated from checkers/deadcode.py]
AGENT_ALL = {"workbuddy", "claude-code", "cursor", "codex", "copilot", "cline", "generic"}

# [relocated from checkers/deadcode.py]
PLAT_WIN = {"windows"}

# [relocated from checkers/deadcode.py]
PLAT_UNIX = {"linux", "macos"}

# [relocated from checkers/deadcode.py]
PLAT_ALL = {"windows", "linux", "macos"}

# [relocated from checkers/deps.py]
ENTRY_HINTS = {"main", "run", "start", "handler", "setup", "init", "register",
               "callback", "on_load", "entrypoint", "cli", "execute", "invoke"}

# 检查器注册表（v1.25.0 拆分后：由各检查器模块自注册，不再在此硬编码函数引用）
# --------------------------------------------------------------------------- #
CHECKERS = {}
DEFAULT_CHECKERS = ["doc"]
ALL_CHECKERS = ["doc", "structure", "security", "runtime", "deps",
                "deadcode", "portability", "doc-llm"]

# 检查器身份代号（单一真相源，v1.25.5 新增）：供执行回执 / --json / 机读稳定标识。
# 选用「数字代号」而非缩写名作权威身份：doc-llm 事故根因正是「注册键连字符/下划线拼写
# 与 ALL_CHECKERS 不一致 → CHECKERS.get 恒为 None → 检查器从未执行且静默通过」。数字代号
# 集中在此一处登记、engine 与 CLI 共享，绝不会与注册键拼写漂移，从根上免疫该类 bug。
# 收据/JSON 同时打印 #编号 与名称，兼顾机读与人读。
CHECKER_CODES = {
    "doc": 1,
    "structure": 2,
    "security": 3,
    "runtime": 4,
    "deps": 5,
    "deadcode": 6,
    "portability": 7,
    "doc-llm": 8,
}

