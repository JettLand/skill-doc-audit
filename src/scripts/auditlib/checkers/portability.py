# checkers/portability.py (拆分自 audit_docs.py)
from auditlib.core import *   # 常量 + 公共 helper（finding/collect_code/正则等）
from auditlib.model import *  # SkillModel / detect_format 等（如需）
from auditlib.core import (_normalize_target_platform, _normalize_target_agent, _parse_frontmatter_list)

















def _port_fire(declared, breaks_on):
    """声明平台与「该发现会崩的平台」有交集才 fire；否则该缺陷只存在于未声明的平台上 → 抑制。"""
    return bool(declared & breaks_on)
























































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
# Vector 2 (v1.22.0)：doc-llm 选装 LLM 语义漂移检测（调用流程参考 deadcode 检查器）
# --------------------------------------------------------------------------- #
# 设计（v1.24.0 起重构）：语义漂移检测由 **agent 直接接手**，本脚本不再调用任何外部 LLM 端点。
# 原因：外部 LLM 需用户自备 API Key、额外付费，提高使用成本；而 agent 本身即具备语义理解能力，
# 由 agent 读 SKILL.md + 代码事实清单自行比对即可（仅占用 agent 自身推理 token，输入侧为主，不另付费）。
#   - 模式：off（不运行）/ ask（交互菜单，由用户选 1=默认 2=agent接手）/ agent（直接由 agent 接手）。
#   - agent 模式：脚本把「SKILL.md 全文 + 代码事实清单」写成 dossier 文件并打印
#     `[doc-llm] AGENT_TAKEOVER: <path>` 哨兵，由 agent 读取后自行完成语义比对，回报漂移。
#   - 绝不依赖外部服务：本模块已移除 urllib/HTTP 调用与 API Key 配置项。
#   - v1.24.1：移除选项 3（预览）——预览会重复把材料灌入上下文、徒增 token 消耗，无实质收益。


# 自注册
CHECKERS["portability"] = check_portability

