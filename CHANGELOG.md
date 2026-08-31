# 变更明细（CHANGELOG）

本文件收录各版本的「打磨明细」（改动 + 验证），作为开发 / QA 留档。README 的「版本与评测」表仅保留要点摘要。

> 排序：版本号降序（最新在前）。


## 1.19.0 打磨明细（deadcode 非 TTY 精度降级可见化——代码层修复 R 可靠性退步）

> 发布：2026-08-31 经 SkillHub CLI 发布 v1.19.0（versionId 277420，审核通过，已评测 **4.7/5 优秀**，测评时间 2026-08-31 15:36）。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| R 可靠性退步的代码层根因修复 | v1.18.1 仅改 SKILL.md「Agent 执行约定」，但评测器直接调 `audit_docs.py --all-checks`（非 TTY 回退 ast），不遵循 SKILL.md 约定，故评测仍点名「deadcode 自动化精度下降无提示」。本版在代码层根治：`_resolve_deadcode_mode` 返回值由单值改为 `(mode, degraded)` 元组；在三类「未显式确认即降低精度」的情形——①非 TTY（管道/Agent 调用）且未装 vulture、②显式 `--deadcode-mode vulture` 但运行环境缺失 vulture、③交互询问超时/无输入——均标记 `degraded=True`；`check_deadcode` 在 `degraded` 时向报告追加 `precision_degraded`（WARN）发现，明确写出精度降级事实与「装 vulture + `--deadcode-mode vulture` / 由 Agent 主动询问」的解决建议 | 自身 `--all-checks` 自审 ERROR 0 / WARN 0（vulture 已装走高精度、无降级提示）；模拟样本以 `-S`（vulture 缺失）+ 非 TTY 实测：报告确实产出 `[WARN] precision_degraded` 行；显式 `--deadcode-mode vulture` 缺库亦触发；vulture 已装路径仍静默高精度、零降级提示；`py_compile` 通过；确认无遗留旧单值返回调用点 |
| 显式 vulture 缺库时自动安装（尊重用户意图） | 当用户**显式** `--deadcode-mode vulture` 或交互选了「1) vulture」但环境缺库时，原逻辑直接回退 AST（即便用户已明确要求高精度）。本版新增 `_try_install_vulture()`：先尝试 `pip install vulture`（超时 120s、异常兜底），安装成功即采用高精度（`degraded=False`），安装失败才回退 AST 并标注 `precision_degraded`；`ast`/`skip` 与 ask 模式的非 TTY 自动回退**不**触发安装，避免自动化/无人值守场景发起意外网络请求。`_vulture_module()` 保持「不自动安装」语义，安装职责独立 | 路径1（-S + 显式 vulture）实测打印「尝试自动安装」并因 `-S` 隔离在装后仍不可导入而优雅降级告警；路径2 monkeypatch 验证：装成功→`('vulture', False)`、装失败→`('ast', True)`、显式 ast→`('ast', False)` 且全程不安装；路径3（ask + 非 TTY 缺库）确认无「尝试自动安装」字样、纯回退 |

## v1.19.0 TRACE 评测对照（2026-08-31 15:36 测评）

> 综合 **4.7/5（优秀）**，较 v1.18.1（4.8）降 0.1，但**R 可靠性根因修复得到验证**。

| 维度 | v1.18.1 | v1.19.0 | Δ | 关联优化 |
|---|---|---|---|---|
| 综合 | 4.8 | 4.7 | −0.1 | 评测器存在维度级波动（见下） |
| T 可信任度 | 5.0 | 4.8 | −0.2 | 国内适配性 5.0→**4.5**（报告提「网络抓取偶尔有问题」；`--source url` 仍受网络环境影响，属评测器对网络场景的波动） |
| R 可靠性 | 4.5 | **4.8** | **+0.3** | 运行稳定性 4.3→**4.5**；报告明确「死代码检测会自动选择最合适的方式跑，不会在环境不同时崩溃」——**v1.19.0 的 `precision_degraded` 可见化 + 自动安装修复生效，R 扣分消除** ✅ |
| A 适用性 | 4.7 | 4.8 | +0.1 | 触发方式 4.7→4.9 |
| C 规范性 | 4.8 | 4.4 | −0.4 | 反模式与FAQ 4.8→**4.0**、文档质量 4.8→4.5（报告指「FAQ/避坑分散各处、无集中章节」——v1.18.0 新增的 Q6–Q8 仍散落，未聚合成专章，属可优化项） |
| E 有效性 | 4.8 | 4.6 | −0.2 | 输出准确性 4.8→4.5（报告指「部分内容被截断」） |

**核心结论**：v1.19.0 针对性修复的 R 可靠性**已验证回补（4.5→4.8）**，deadcode「精度下降无提示」扣分消除。综合分回落至 4.7 并非本次改动所致，而是评测器在「国内适配性（4.3→5.0→4.5 反复）」「规范性/FAQ（4.8→4.4）」两维度存在运行间波动——同技能跨次评测分数抖动明显，4.8↔4.7 落在噪声区间。

**后续候选（v1.20.0，待用户决策）**：将 FAQ / 新手误区 / 避坑指南聚合为单一「常见问题与避坑」专章（回应 C 反模式与FAQ 4.0），预计可回补 C 规范性。

> 发布：2026-08-31 经 SkillHub CLI 发布 v1.18.1（versionId 277173，审核通过，已评测 4.8/5 优秀，2026-08-31 00:37）。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| Agent 跳过 deadcode 询问的根因修复 | 根因：`deadcode` 默认 `ask` 模式的「询问」依赖人类 TTY 的 `input()` 提示；Agent 经管道调用（stdin 非 TTY）时脚本静默降级为 `ast`，用户的精度选择权被吞掉。新增「Agent 执行约定（deadcode 精度模式必须显式决策）」专节，明确 Agent 在跑 `--all-checks` 前必须先探测 vulture、再主动用 AskUserQuestion 询问用户三选一、并以 `--deadcode-mode` 显式传入，绝不依赖 `ask` 默认；同步在「能力边界」deadcode 项与「5 分钟上手」补充 Agent 上下文提示 | 自身 `--check doc` 自审 ERROR 0 / WARN 0（仅 1 条预存 `audit.json` 裸文件名 INFO，非本次引入）；`audit_docs.py` py_compile 通过 |

## v1.18.1 TRACE 评测对照（2026-08-31 00:37 测评）

> 综合 **4.8/5（优秀）**，较 v1.17.0（4.7）升 0.1。印证 v1.18.0（误报修复 / 文档增强 / `--source url`）与 v1.18.1（deadcode Agent 约定）优化方向正确。

| 维度 | v1.17.0 | v1.18.1 | Δ | 关联优化 |
|---|---|---|---|---|
| 综合 | 4.7 | 4.8 | +0.1 | |
| T 可信任度 | 4.7 | 5.0 | +0.3 | 国内适配性 4.3→5.0（+0.7）：`--source url` 绕过 git clone 生效 |
| R 可靠性 | 4.8 | 4.5 | -0.3 | 运行稳定性 4.5→4.3：仍点名 deadcode 自动化精度下降 |
| A 适用性 | 4.7 | 4.7 | 0 | |
| C 规范性 | 4.6 | 4.8 | +0.2 | 文档质量/渐进式披露 4.5→4.8（+0.3）：文档增强生效 |
| E 有效性 | 4.8 | 4.8 | 0 | 内容完整度 4.8→4.9；输出准确性获「能区分真实/误报」肯定 |

- **提升点**：T（国内适配性）、C（文档质量/渐进式披露）直接印证 v1.18.0 优化；E 输出准确性评测肯定「能区分真实问题还是误报」，对应误报修复。
- **退步点**：R 可靠性降 0.3，评测点名「死代码检测在某些自动化环境下可能精度下降而无提示」——恰为 v1.18.1 修复目标，但评测器直接调脚本（非 TTY 回退 ast）未走 SKILL.md 的 Agent 询问约定，故负面评价仍在 → 候选 v1.19.0 **代码层**修复（非 TTY 不再静默降级 ast）。

## 1.18.0 打磨明细（回应 SkillHub TRACE 评测反馈）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 检查器误报修复（评测不足②/③） | `structure/hardcoded_path` 上下文感知：逐行扫描，跳过代码围栏、表格行、引用块、含豁免/示例性语言的行，仅对真实指令行报硬编码绝对路径；`portability/encoding_sep` 改用负向环视 `(?<![A-Za-z0-9_.])open\(`，排除 `urlopen`/`io.open`/`os.open` 等非文件 `open`（如 `--source url` 的 `urllib.request.urlopen`）；`security/hardcoded_endpoint` 的 `EXCLUDE_ENDPOINT_HOSTS` 新增 `raw.githubusercontent.com`/`raw.githack.com`/`gitee.com`/`gitlab.com` 等 url 源规范主机白名单 | 自身 `--all-checks` 自审：WARN 由 4 降至 1（仅剩审计 `src/` 目录名≠技能名的 harness 假象，真实部署副本不触发）；原本 3 个误报（hardcoded_path/encoding_sep/hardcoded_endpoint）全部消除，ERROR 维持 0 |
| 文档增强（评测 C 4.6 / A 边界分散） | 新增「5 分钟上手（极简路径）」「能力边界速查（一句话）」「完整运行示例（真实输出+解读）」「新手常见误区 FAQ（Q6–Q8：误用 github 源/把误报当 bug/vulture 未装以为跑不了）」；并引导远端审计优先用 `--source url`、明确 vulture 可选自动降级 `ast` | 文档体量适度增加但结构更清晰，新手可凭极简路径与误区清单快速上手 |
| 国内适配性回应（评测 4.3 扣分） | `多平台来源` 节新增「审计远端技能优先用 `--source url`」引导（零外部 CLI、绕开 `git clone` 网络限制） | 与 v1.17.0 url 源能力一致，正面回应评测的网络受限扣分 |

## 1.17.0 打磨明细（泛化来源 --source url）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 泛化来源 `url` | 新增 `UrlSource(SkillSource)`：`resolve(ref, args)` 用标准库 `urllib.request` 直接抓取 SKILL.md 文本到临时目录，复用 `analyze_skill` 核心逻辑零改动；`github.com` blob 链接经 `_normalize` 转 `raw.githubusercontent.com` 直链；支持「文件 URL」与「目录 URL（自动补 /SKILL.md）」两种形态 | 抓取本仓库已发布 SKILL.md 链路通畅（沙箱 HTTP 可达） |
| 引用补全 `_fetch_refs` | 抓取 SKILL.md 后，正则提取其显式引用的 `scripts/`、`references/` 相对文件，相对 base 逐一抓取落盘（上限 50、单文件超 `MAX_FILE_SIZE` 跳过），使远程单文件技能与本地克隆等价 | 实测：原单文件抓取刷出 134 个 `script_ref_missing` ERROR，补全后降至 ERROR 0 / WARN 2；`--source url` 与 `--source local` 审计同一技能结论一致 |
| 零外部依赖 / 跨平台 | `url` 来源仅用标准库（`urllib`），不依赖 `git`/`skillhub` CLI；HTTPS 依赖对目标 OS 透明 | `portability` 仅报 `agent_coupling`（WorkBuddy 约定），无 OS 级破损；自审 `--all-checks` 0 ERROR |
| 文档与 CLI 同步 | `SKILL.md` 版本 1.16.0→1.17.0；来源表、用法示例、跨平台证明补 `url`；`audit_docs.py` 的 `--source`/`--ref` 帮助文本补 url 形态 | — |

## 1.16.0 打磨明细（Phase 7 ⑤落地·agentskills 枢纽标注 + generic 兜底 + 跨平台证明）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 建议1·文档标注 agentskills 全生态枢纽（零成本） | SKILL.md / checkers.md / README 标注：`--target agentskills` 与 `--target cursor-plugin` 即 Agent Skills 开放标准（agentskills.io）形态，一次转译可被 40+ 工具（Claude Code、Cursor、Gemini CLI、Codex、Copilot、Windsurf、Kiro、OpenCode 等）直接消费；`claude-code` 仅叠加可选扩展键 | 文档与代码（`FMT_CAPS` agentskills/cursor-plugin 同构）一致；本技能自扫 `--target agentskills` 产出字段符合开放标准能力集合 |
| 建议3·generic 降级兜底目标（极低本） | `--target` 枚举扩展加入 `generic`；`build_translate_report` 对 `generic` 前置「⚠ 高损失」警告并提示优先用 agentskills/cursor-plugin；`emit_frontmatter`/`SCAFFOLD_HEADINGS`/`FORMAT_TARGETS` 已原生支持 generic，无需改映射内核 | workbuddy→generic 正确输出高损失警告 + 仅保 name/description；generic→workbuddy 正确判 `RECOVERABLE`；`--json` 附 `translate` 字段正常 |
| 跨平台可移植性证明（按用户要求校对补全） | SKILL.md 新增「跨平台可移植性证明（本技能自身）」专节：纯 Python 标准库/零第三方依赖、无平台专属 API 实际调用（相关字样仅作检查器检测规则）、portability 自检 0 OS 级发现（17 条 INFO 全为 agent_coupling 跨 Agent 咨询）；并附可复现命令 | 在本技能源码运行 `--check portability`（未声明 target_platform=全平台全检）得 `ERROR 0 / WARN 0`，全部 INFO 为 agent_coupling；Grep 确认无 `win32api`/`os.getcwd`/`shell=True` 实际调用 |
| 文档同步 | SKILL.md 升 1.16.0 + 速查表补 `generic` 目标 + portability 节补 Phase 7 agentskills 枢纽认知；checkers.md 补 agentskills 枢纽专述与 generic 范围；README 版本表 + 本明细 | — |

> 设计要点：本次为 Phase 7 ⑤评估结论的落地——①（文档标注，零代码）与③（generic 兜底，极低本）均按评估采纳；②（cursor-mdc emit）与④（OpenAI plugins/MCP，非 SKILL.md 范式）维持「不纳」；同时按用户要求补「跨平台可移植性证明」节，把本技能自身的跨平台能力从「隐含」变为「可复现证据」。

## 1.15.0 打磨明细（Phase 7 跨格式转译报告·只读预览）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 转译内核 | 新增 `emit_frontmatter(model, target_fmt)`：复用 `FMT_CAPS`/`EQUIV` 逐字段映射，命中等价映射记降级、目标无对应记丢失；多源字段映射同一目标字段（如 `slug`/`displayName`→`name`）时保留 canon `name`、其余并入并记降级。新增 `_emit_field`/`_yaml_val`/`_scaffold` 辅助 | 4 个目标格式逐项映射符合 `FMT_CAPS` 预期 |
| 报告 | 新增 `build_translate_report`：frontmatter 字段映射表（保留/降级/丢失标注）+ 目标 SKILL.md 脚手架预览（仅 frontmatter+标题骨架，明确标注「仅展示，不落盘」） | workbuddy→agentskills/claude-code/cursor-plugin 与 agentskills→workbuddy 双向输出正确 |
| 往返保真 `--verify` | 复用 `build_portability_matrix` 该目标行的 `status`：preserved 完整往返、degraded 可往返（重命名）、lost 不可逆；整体结论 `RECOVERABLE`/`LOSSY`/`IRREVERSIBLE` | workbuddy→agentskills 正确判 `IRREVERSIBLE(含 version)`；agentskills→workbuddy 正确判 `RECOVERABLE` |
| CLI | `--report` 增 `translate`；新增 `--target`（workbuddy/agentskills/claude-code/cursor-plugin）、`--verify`；translate 模式跳过检查器、不打印常规体检、仅出转译报告；`--json` 附 `translate` 字段 | 各方向 + JSON 实跑通过 |
| 文档同步 | SKILL.md 升 1.15.0 + 速查表补 `--report translate` 行 + portability 节补 Phase 7 专述；`references/checkers.md` 补 Phase 7 专节；README 版本表 + 本明细 | — |

> 设计要点：Phase 7 是「只读预览」而非「写能力」——只把 Phase 5/6 已有的归一化与矩阵下沉为可预览的转译方案，全程不落盘，守住本技能「只读扫描、绝不自动改写」的立身之本（原计划中的「自动生成目标 SKILL.md」因与本原则冲突、且正文散文机械转译不可靠，已按用户决策改为仅出报告）。决策①②③④ 全部落地。下一步（⑤）：评估是否纳入更多高性价比目标格式（generic-markdown / aidevice / openai-plugins / mcp-server 等）。

## 1.14.0 打磨明细（Phase 8 生态级批量审计 + 供应链安全）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 批量来源 | `--ref` 由单仓库扩展为**逗号分隔多仓库**（`--source github --ref owner/repo1,owner/repo2`）；local/organization 单仓库语义不变（`refs` 为空时回落原路径）。每个仓库独立克隆、独立审计、独立聚合，单仓失败不影响其余 | 多 ref 拆分逻辑单测通过；单 ref 向后兼容 |
| 供应链启发式 `hardcoded_endpoint` | `security` 新增：扫描 `http(s)://` 远端地址，标 WARN；**仅当行内含代码上下文**（`=`/`(`/`[`/`return`/`yield`）才报，排除文档/注释示例 URL；排除 localhost/example/SDK 文档主机；排除检查器自身源码（`re.compile` 等） | 夹具 `URL = "https://api.malicious-cdn.example.net/..."` 正确命中；自审 docstring 示例 URL 不误报（WARN 维持基线 2） |
| 供应链启发式 `dynamic_import` | `security` 新增：反射式模块加载 `importlib.import_module` / `__import__` / `getattr(sys.modules)` 标 WARN | 夹具 `importlib.import_module("os")`、`__import__("sys")` 正确命中；自审 0 误报（提示文案已避免含正则字面量自匹配） |
| 健康度汇总 | 新增 `build_health_summary()` / `print_health_summary()`；`--report health` 打印逐技能计数 + 含供应链风险技能数；`--json` 审计 ≥2 技能时自动包裹 `health_summary` 顶层键 | 单技能表格渲染正常；双结果单元验证 `total_skills=2`、风险类别分布正确、JSON 含 `health_summary` |
| 文档同步 | SKILL.md 升 1.14.0 + 快速开始新增 `--report health` 行 + `security` 表补两项；`references/checkers.md` 补 `hardcoded_endpoint`/`dynamic_import` 行 + Phase 8 专节；README 版本表 + 本明细 | — |

> 设计要点：Phase 8 是「轻量」生态级能力——供应链安全启发式复用并扩展既有 `security` 检查器（不新增独立检查器，避免口径漂移），批量审计复用既有 `--source` 抽象（仅放开 `--ref` 多值），健康度汇总作为只读报告叠加（不改写文件）。Phase 7 双向转译仍暂缓，待 Phase 5/6/8 经真实外部仓库（anthropics/skills、Cursor 官方样例、多组织批量）验证稳定后再议。

## 1.13.0 打磨明细（Phase 6 跨格式可移植性矩阵）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 字段级能力映射 | 新增 `FMT_CAPS`（各格式原生支持字段集合）、`EQUIV`（跨格式等价字段：target_agent↔compatibility、slug/displayName→name）、`AGENT_TO_FMT`（Agent 名→规范格式）、`FORMAT_TARGETS`；新增 `_model_features()` 与 `build_portability_matrix()` 生成「源格式 → 各目标格式」P/D/L 矩阵 | 本技能自检矩阵正确呈现 8 个特征跨 5 目标格式的 P/D/L 分布 |
| `lossy_port` 发现（#7） | `check_portability` 新增 #7：仅当 `target_agent`/`compatibility` 显式声明跨 Agent 目标（不含 `workbuddy`）时触发；对声明目标端 `lost`→WARN、`degraded`→INFO；纯 workbuddy/未声明目标不触发（避免噪音）。修复初版误置于代码行循环内导致无代码文件技能不触发的问题 | 跨 Agent 夹具 `compatibility:[claude-code,cursor]`：正确产 WARN（version/target_agent 丢失）+ INFO（slug/displayName 降级），准确区分级别 |
| 专项报告 `--report portability-matrix` | 新增 CLI 选项，打印 P/D/L 矩阵（不改写任何文件），并并入 `--json` 的 `portability_matrix` 字段 | 自身 `--report` 输出 8 特征 × 5 目标矩阵；`--json` 含矩阵 |
| 缺陷修复 `_parse_frontmatter_list` | 内联列表 `[claude-code, cursor]` 此前被解析为 `['[claude-code', 'cursor]']`（括号未剥离）→ `target_agent` 归一化失效；现解析前后均 `strip("[]")` | 夹具 `compatibility:[claude-code, cursor]` 现正确归一为 `{claude-code, cursor}`，`lossy_port` 正常触发 |
| 文档同步 | SKILL.md 升 1.13.0 + 快速开始新增 `--report` 行 + portability 节补 Phase 6 矩阵说明与 `lossy_port` 行；`references/checkers.md` 损失行 + 矩阵专节；README 版本表 + 本明细 | — |

> 设计要点：Phase 6 放大既有 `portability` 能力，将单点 `agent_coupling` 升级为可执行的「X→Y 会损失什么」迁移指南（核心价值）。Phase 7 双向转译暂缓，待 5/6 经真实外部仓库稳定验证后再议；Phase 8 生态级批量审计 + 供应链安全按计划排期在 Phase 6 之后。

## 1.12.0 打磨明细（Phase 5 跨 Agent 格式归一化内核）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 格式检测 `detect_format()` | 新增函数：按特征推断 5 类格式——`.mdc` + description/globs/alwaysApply → `cursor-mdc`；含 WorkBuddy 专有键（slug/displayName/target_platform/target_agent/agent_created）→ `workbuddy`；含 Claude Code 专有扩展键（argument-hint/model/context/agent/...）→ `claude-code`；含 `compatibility` 或仅开放标准键 → `agentskills`；其余 → `generic`。判定「按特征推断」而非硬锁枚举（延续 v1.11.0 自由列表原则，防生态演进漏判） | 5/5 夹具分类正确（workbuddy/agentskills/claude-code/cursor-mdc/generic） |
| 统一模型 `SkillModel` | 新增普通类承载 name/description/fmt/platform/target_platform/target_agent/tools/license/version/extra；`analyze_skill` 计算 `fmt` 并构建 `SkillModel`，注入 `ctx` 与返回结果（`format` / `skill_model` 字段），供检查器与后续 Phase 6 矩阵 / Phase 7 转译消费 | 本技能自检：`fmt=workbuddy`、`platform=workbuddy`、`version=1.11.1`、`target_agent=['workbuddy']`；字段经 ctx 与返回值双向可见 |
| 避免误报 | 未引入未使用常量（`FORMAT_ALL` 不落地）；`SkillModel` 用普通类而非 `@dataclass`，规避 vulture 对 dataclass 字段的死代码误报 | 自审 `--all-checks`：ERROR 0 / WARN 2（name_mismatch + hardcoded_path，均预期）/ INFO 11，WARN 较改动前无新增（无回归） |
| 文档同步 | SKILL.md 升 1.12.0 + portability 节补充「跨 Agent 格式归一化内核」说明；`references/checkers.md` 跨 Agent 字段节补充 Phase 5 内核说明；README 版本表 + 本明细 | — |

> 设计要点：Phase 5 是「地基」，不直接改变任何检查器的发现口径（现有 findings 与改动前完全一致），仅为跨格式审计建立统一表示层。下一步 Phase 6 将在此之上构建跨格式可移植性矩阵（字段映射 / 工具名 crosswalk / lossy-port 分级警告）。

## 1.11.1 打磨明细（portability #6 行为修正）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 移除 workbuddy 抑制 | `check_portability` #6 删除「声明/推断含 `workbuddy` 则抑制 `agent_coupling`」分支；新口径：声明跨 Agent 目标（不含 `workbuddy`，如 `claude-code`/`cross-agent`）仍含 WorkBuddy 耦合→WARN，其余（未声明/声明含 `workbuddy`/推断 `workbuddy`）→均 INFO 提示 | 自审本项目 `--all-checks`：portability 现报 INFO `agent_coupling`（不再 0 发现）；构造 claude-code 目标夹具→WARN 升级仍正确 |
| 文档同步 | SKILL.md 升 1.11.1 + 速查表/portability 豁免说明改写；`references/checkers.md` 权威表 + `target_agent` 小节改写（workbuddy 不再作为抑制信号）；README 版本表 + 本明细 | — |

> 修正动机：本 skill 自身亦在开发跨平台/跨 Agent 分发能力，故 WorkBuddy 目标的耦合提示对所有技能（含 workbuddy 目标）均有参考价值，不应抑制。

## 1.11.0 打磨明细（Phase 4 跨 Agent 分发 + Schema Normalizer）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| `target_agent` 字段轴 | `analyze_skill` 新增 `target_agent` 提取（自由列表；开放标准 `compatibility` 字段映射；无字段时按 mcp__/`.workbuddy` 信号推断 workbuddy）；`agent_coupling` 改为：声明含 workbuddy 抑制、声明跨 Agent 目标（claude-code/cross-agent）且仍含 WorkBuddy 耦合升 WARN、未声明 INFO | 构造测试技能：Case A（无声明+`.workbuddy`）INFO；Case B（`target_agent: claude-code`+`.workbuddy`）WARN；本项目自审 0 ERROR 且 agent_coupling 被推断 workbuddy 抑制 |
| deps 平台声明结构化（4a） | `platform_undeclared` 优先读 `ctx["target_platform"]`；已显式声明（非跨平台默认）则抑制散文扫描，否则保留作次级信号 | Case D（`target_platform: windows` + winreg）`platform_undeclared` 被抑制 |
| Schema Normalizer（4b-2） | YAML 列表式 `allowed-tools` 解析（修外部技能 UNKNOWN_IDENT 误报）；`check_structure`/`check_doc` 的 `version`/`license` 检查平台感知（workbuddy 强制，开放标准 agentskills/generic 不强制 version、license 降级 INFO） | 构造 agentskills 格式夹具（YAML 列表 allowed-tools + compatibility + 无 version/license）→ 无 version ERROR、license INFO、无 UNKNOWN_IDENT；`--source github --ref anthropics/skills` 真实外部仓库（约 20 技能）审计无 version/license 误报洪泛、`agent_coupling` 正确触发 |
| 文档同步 | SKILL.md 升 1.11.0 + 检查器列表/速查表/portability 小节补充 `target_agent`；`references/checkers.md` 权威表 `agent_coupling` 行 + 新增 `target_agent` 字段说明；README 版本表 + 本明细 | — |

复测总览：`py_compile` 通过；自审 `--all-checks` 0 ERROR；4 类测试技能（抑制/升级/声明/外部）行为符合设计；真实外部仓库 `anthropics/skills` 审计无工具崩溃（无 Traceback）。

复测总览：`py_compile` 通过；自审 `--all-checks` 0 ERROR（仅 INFO 咨询项）；`target_platform` 豁免两用例行为与设计完全一致；`--source github/skillhub` 多源能力回归无变化。

## 1.10.0 打磨明细（portability 跨平台可移植性检查器）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| portability 检查器 | 新增 `check_portability(ctx)`：6 类全做（hardcoded_abs_path / cwd_dependence / platform_shell / interpreter_lock / encoding_sep / agent_coupling）；纯静态正则扫描 `ctx["code"]`，复用现有基建；注册进 `CHECKERS` + `ALL_CHECKERS`，零依赖可进默认集 | 自审本项目 `--all-checks` 仅剩 6 条 INFO `agent_coupling`（本项目确耦合 `.workbuddy`/allowed-tools，属真实提示非误报） |
| `target_platform` 豁免 | `analyze_skill` 从 frontmatter 提取 `target_platform` 注入 `ctx`；`_normalize_target_platform` 归一（空/未知/cross-platform/all/* → 全平台）；`_port_fire` 实现 `fire iff 声明平台∩breaks_on 非空`；`code` 扫描跳过注释行与自检令牌（SELF_REF_TOKENS/SCAN_SKIP_TOKENS），避免扫描器自身字符串误报 | 构造破损测试技能：Case A（无声明）7 WARN + 1 INFO 全命中；Case B（声明 `windows`）正确抑制 `C:\`/powershell/裸python，但 `/Users/`/rm -rf/cwd/open()无encoding 仍报（符合「Windows 目标上才真坏」设计） |
| 级别与口径 | 全部 WARN/INFO、绝不 ERROR（可移植性是程度问题，结论需人判）；#6 `agent_coupling` 为 INFO 咨询；`target_platform` 任意取值均不抑制 #6（本期无 `target_agent` 字段），列入 Phase 4 跨 Agent 分发待办 | — |
| 文档同步 | SKILL.md 升 1.10.0 + 检查器列表 + 快速开始速查表 + 新增「portability 跨平台可移植性」小节；`references/checkers.md` 权威表新增 6 行 + `target_platform` 豁免字段说明；README 版本表 + 本明细 | — |

> Phase 4 已交付（v1.11.0）：① `deps.platform_undeclared` 由散文关键词扫描升级为读取结构化 `target_platform` 字段（与 portability 共用同一提取逻辑，已显式声明平台则抑制散文扫描）；② 跨 Agent 分发——新增 `target_agent` 字段轴（自由列表，仅特判 workbuddy 抑制；开放标准 `compatibility` 视作 target_agent），#6 `agent_coupling` 可按字段抑制/升级；③ Schema Normalizer——YAML 列表式 `allowed-tools` 解析（修外部技能 UNKNOWN_IDENT 误报）、`version`/`license` 检查平台感知（开放标准 agentskills/generic 不强制 version、license 降级 INFO），经 `--source github` 审计 `anthropics/skills` 真实外部仓库验证无 version/license 误报洪泛。

## 1.9.0 打磨明细（多平台来源抽象）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 来源抽象层 | 新增 `SkillSource` 基类 + `LocalSource` / `GithubSource` / `SkillhubSource` 三实现；`analyze_skill(skill_dir)` 签名与逻辑零改动。来源层只负责把远程/集市技能落地为本地临时目录，再交还路径 | 单元外：`--skill` / `--all` 行为与 1.8.2 完全一致（回归 0 变化） |
| `--source` / `--ref` / `--keep-temp` | `main()` 目标构建改为 `get_source(args.source).resolve(args.ref, args)`；`github` 经 `git clone --depth 1 [--branch]` 到 `tempfile.mkdtemp`；`skillhub` 经 `skillhub install <slug> --dir` 到临时目录；新增 `find_skill_dirs` 遍历定位含 `SKILL.md` 的目录（支持嵌套 `src/SKILL.md` 与一仓库多技能）；审计后默认 `shutil.rmtree` 清理，`--keep-temp` 保留并打印路径 | 端到端：`--source github --ref JettLand/skill-doc-audit --check structure` 克隆→定位 `src/SKILL.md`→审计→自动清理（退出码 0）；`--source skillhub --ref skill-doc-audit --check structure` 拉取→审计（退出码 0）；`--keep-temp` 临时目录留存可验证 |
| 健壮性 | `git` / `skillhub` 调用走 `subprocess` 列表参数（无 shell 注入）；克隆/安装失败捕获 `CalledProcessError` / `TimeoutExpired` / `FileNotFoundError` 并打印末行错误后退出码 2；`skillhub` 二进制经 `shutil.which` 解析全路径（Windows 上为 `skillhub.CMD`，规避裸名扩展名解析失败）；空结果（无 SKILL.md）也安全退出 | 缺参/克隆失败路径均优雅退出码 2，无堆栈泄漏 |
| 文档同步 | SKILL.md 新增「多平台来源」小节 + 快速开始速查表 2 行 + 用法示例；README 增加自测示例与 1.9.0 明细；模块 docstring 用法段补充 `--source` 示例 | — |

> 注：Phase 3（portability 检查器组）已于 v1.10.0 交付；Phase 4（跨 Agent 分发 + Schema Normalizer）已于 v1.11.0 交付。

## 1.8.2 打磨明细（文档补全）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| SKILL.md 错误码对照表补全 | 「错误码对照表」新增 `### deadcode` 段，列出 deadcode 检查器全部 5 个 category（`unused_def`=WARN / `unused_import`=INFO / `unreachable`=WARN / `orphan_asset`=WARN / `vulture`=WARN），级别与 `checkers.md` 权威表一致，并附一行误报抑制说明 | 脚本比对 `CATEGORY_LABELS`（42 个）与 SKILL.md 速查表，缺口由 5（`unused_def`/`unused_import`/`unreachable`/`orphan_asset`/`vulture`）降为 0；`checkers.md` 权威表本就全覆盖 |

复测总览：`py_compile` 通过；自审 `--all-checks` 0 ERROR；错误码对照表与代码 `CATEGORY_LABELS` 完全一致（42/42）。

## 1.8.1 打磨明细（交互体验改进）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| deadcode 询问超时延长 | `_prompt_deadcode_mode` 超时 `th.join(10)`→`th.join(30)`，提示文案「10 秒内未选」→「30 秒内未选」，docstring 同步 | 单元验证 `th.join(30)` 生效、`th.join(10)` 已移除 |
| vulture 已装免询问 | `_resolve_deadcode_mode` 的 `ask` 分支先探测 `_vulture_module()`，已装则直接返回 `vulture` 高精度模式（打印「自动采用高精度模式（跳过询问）」），不再进入交互询问；未装仍走原逻辑（非 TTY→ast / TTY→询问 30s） | 单测：ask+vulture→`vulture`、ask+无 vulture(非 TTY)→`ast`、显式 vulture+无 vulture→`ast`(回退)；端到端 `--all-checks` 默认 ask + vulture 已装 → 自动高精度、不询问、跑完无崩 |

文档同步：SKILL.md / checkers.md 的能力描述与 `--deadcode-mode` 参数说明同步（「默认 ask：已装 vulture 则自动高精度」）；dist 已重打包（含最新源码）。

## 1.8.0 打磨明细（发布窗口内就地修正）

| 打磨项 | 改动 | 验证（均通过，0 回归） |
|---|---|---|
| 死代码跨文件感知 | `check_deadcode` 预扫描全技能 `.py` 构建全局 `global_used` + `imported_modules`，`unused_def` 仅当全技能范围都未引用才报；`orphan_asset` 增加 import 模块名豁免 | `tests/fixtures/multifile`（a.py 定义 `shared_helper`、b.py 调用）不再误报 `unused_def`；真阳性 `EXIT_CODE_ONLY` 保留 |
| 多语言扫描覆盖 | `CODE_EXT` 由 `.py/.js/.sh/.ps1/.json` 扩展至含 `.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua` 等；`FILE_REF_RE`/`structure`/`runtime` 引用正则同步扩展 | `tests/fixtures/ts-skill` 的 `runGame` 不再误报 `UNKNOWN_IDENT`；`.ts` 内硬编码密钥被 `security` 抓到 |
| 检查预览 `--preview` | `main()` 新增 `--preview`：只打印将运行检查器 / deadcode 精度模式 / 文档存在性 / 将扫描文件清单 / 跳过的大文件，退出码 0 | `tests/fixtures/multifile --all-checks --preview` 退出码 0、列出 2 个文件、无发现 |
| `UNKNOWN_IDENT` 误报修复 | 提取 frontmatter `allowed-tools`/`tools` 与全仓库 `mcp__*__<name>` 标记为 `declared_tools` 并跳过；级别 ERROR→WARN；按标识符去重 | `weixin-minigame-helper` 原 57 ERROR → 0 ERROR；`godot-core`（MCP 技能）26 个外部工具名由 ERROR 降为 WARN（仍保留，提示作者在 frontmatter 声明）；真阳性 `tune_model` 仍报出 |
| 文档渐进式披露 | `SKILL.md` 新增「快速开始」小节（3 条核心命令 + 意图→命令速查表）；`--preview` 进入用法示例；`checkers.md` 新增「命令行参数速查」 | 文档偏长/参数偏多感知缓解 |

复测总览：`py_compile` 通过；自审 5 检查器 + `--all-checks` 均 0 ERROR；`dirty-skill` 14 类缺陷全命中 0 漏报；`tricky-clean` 0 误报；`--all` 扫已装技能 1.7s 无崩溃；市场随机抽检 6 技能无崩溃、`UNKNOWN_IDENT` 稳定为 WARN。
