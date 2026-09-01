# checkers/security.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）
from auditlib.core import _security_irrelevant

def check_security(ctx):
    findings = []
    doc = ctx["doc"]
    code = ctx["code"]

    for rel, content in code.items():
        for i, line in enumerate(content.splitlines(), 1):
            if any(tok in line for tok in SCAN_SKIP_TOKENS):
                # 含检查器自身检测常量/调用的行（re.compile / subprocess|os.system 等）
                # 整体跳过，避免把检查器源码误判为漏洞；此 continue 也保障下方
                # hardcoded_endpoint 不会对检查器自身源码触发，故无需再判一次 SCAN_SKIP_TOKENS。
                continue
            # 硬编码远端端点（供应链风险）：仅排除注释行、并要求行内含代码上下文
            # （赋值/调用/返回），避免把文档叙述/注释中的示例 URL 误报（如检查器自身 docstring）。
            # 文档/示例/SDK 主机已在下方排除，避免把正常链接误报为硬编码端点。
            _ep = ENDPOINT_RE.search(line)
            _ep_comment = line.strip().startswith(("#", "//", "/*", "*", "<!--"))
            _ep_context = re.search(r"[=(\[]|return |yield ", line) is not None
            if _ep and not _ep_comment and _ep_context \
                    and _ep.group(1) not in EXCLUDE_ENDPOINT_HOSTS \
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
# 自注册
CHECKERS["security"] = check_security

