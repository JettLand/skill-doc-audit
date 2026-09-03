# 检查器清单与口径（skill-doc-audit 细则）

本文件是 `SKILL.md` 的加载式补充，列明各检查器的完整项、判定口径与误报抑制机制。SKILL.md 仅保留能力边界概述，执行审计时以本文件为明细基准。

## 检查器总览

脚本能可靠判定的偏差由以下检查器产出，可按需启用。代码/配置文件覆盖多语言：`.py/.js/.jsx/.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua/.sh/.ps1/.json`（含 Python 语法校验与多语言硬编码密钥检测）。

- `doc`（常驻默认开）：文档一致性。**扫描范围**：默认 `SKILL.md` + `references/*.md`（技能自带参考文档，断链是真实漂移）；开发者模式 `--dev-docs` 递归扫描技能文件夹内全部 `.md` 描述性文档（`README`/`CHANGELOG`/`examples` 等）。`A1` 死路径（`DEAD_PATH`，ERROR）仅对 `SKILL.md` 生效（`references`/开发文档为叙述性内容、常含示例路径，套 ERROR 会误报，故仅对裸文件名报 `EXTERNAL_REF` INFO）；`A2`-`A5`/`C`/`B` 类检查仅 `SKILL.md`（能力目录口径，避免把变更日志叙事误判为漂移）。所有被扫文档均进入 `doc-llm` 语义 dossier。**跨检查器去重**：同一缺失引用文件会被 `doc`(`DEAD_PATH`)/`structure`(`broken_ref`)/`runtime`(`script_ref_missing`) 各报一次，且 `doc` 内同裸文件名会逐次报 `EXTERNAL_REF`；v1.25.5 起这些按引用路径自动归并为单条（保留最高严重级，message 标注命中检查器集合，finding 附 `ref`/`dedup` 溯源字段），ERROR/WARN 聚合计数不再虚高、且不掩盖不同根因的真实缺陷。
- `structure`：结构体检 + 元信息
- `security`：安全红线静态子集
- `runtime`：脚本可运行性
- `deps`：依赖与平台声明
- `deadcode`（运行前按 `--deadcode-mode` 选精度，已装 vulture 则自动高精度、不询问）：死代码检测（未使用定义/导入、不可达代码、孤立资源文件）
- `portability`（零依赖纯静态分析，全部 WARN/INFO 不报 ERROR）：跨平台可移植性——硬编码绝对路径 / 启动目录依赖 / 平台专属 shell / 解释器锁 / 编码分隔符假设 / Agent 平台耦合 / 跨格式可移植性损失（`lossy_port`，Phase 6）。按 SKILL.md 的 `target_platform` 字段豁免对应平台项；`--report portability-matrix` 可打印「源格式 → 各目标格式」的 P/D/L 损失矩阵
- `doc-llm`（**独立检查器**，v1.23.0 起纳入 `--all-checks` 全量集，v1.24.0 起由 agent 直接接手）：语义漂移增强检测——覆盖 `doc` 触及不到的自由散文语义漂移，由 agent 用自身能力判定（不再调用外部 LLM）；dossier 含「正向覆盖缺口」预分析段（v1.27.0 起，与 `doc` 检查器的 `DOC_CAPABILITY_MISSING` 共用 `compute_capability_gaps()`——确定性列出代码已注册但文档未写的检查器 / CLI 参数，列为 agent 比对要点优先核对，即「doc 出确定性 WARN 兜底 + doc-llm 供语义复核」）与「代码事实清单」（顶层定义 / CLI 参数 / 退出码 / 常量）；默认 `ask` 问询、非交互记 INFO `doc_llm_skipped`。错误码见下方明细 `DOC_LLM_DRIFT` / `doc_llm_agent_handoff` / `doc_llm_skipped`
- `examples`（**新增检查器 #9**，v1.26.0 起纳入 `--all-checks` 全量集）：文档示例静态校验——校验任意技能文档里写出的命令示例是否站得住脚（脚本引用是否存在 / 参数是否声明 / 外部 CLI 是否声明 / 是否含危险命令）。默认 `ask`（交互询问是否沙箱试运行；非交互 / 超时回退 `static` 零执行 / 零网络 / 零 token）；`--examples-mode run` 方在受限沙箱试运行带 `expected` 标注的示例（仅白名单解释器 + 技能内脚本 + 超时保护，绝不执行任意 shell）。错误码见下方明细 `EXAMPLE_TARGET_MISSING` / `EXAMPLE_DANGEROUS` / `EXAMPLE_FLAG_UNKNOWN` / `EXAMPLE_EXT_CMD` / `EXAMPLE_UNVERIFIED` 等

### 检查器执行回执（身份代号 + 调用结果）
任一检查器被调用时，引擎（`auditlib/model.py` 的 dispatch 循环）都会为它生成一条**执行回执**，明确告知 agent / 使用者「这个检查器到底有没有真跑过」——杜绝 doc-llm 类「静默落空却显示通过」的隐患。

- **身份代号（数字，单一真相源 `CHECKER_CODES`）**：doc=#01、structure=#02、security=#03、runtime=#04、deps=#05、deadcode=#06、portability=#07、doc-llm=#08、examples=#09。选用数字而非缩写名作权威身份：注册键拼写漂移（连字符/下划线不一致）是 doc-llm 静默休眠的根因，数字代号集中登记、绝不会与注册键拼写漂移。回执同时打印 `#编号 名称` 兼顾机读与人读。
- **三态状态**：每条回执携带 `status`：
  - `OK`——检查器成功执行（返回其 `#身份代号`，即成功回执）；
  - `FAILED`——检查器执行中抛异常（已被捕获、未中断其余检查器，异常转成 `CHECKER_ERROR` ERROR 发现，退出码真实反映）；
  - `UNKNOWN`——`CHECKERS` 中无此键（未注册 / 名称拼写不一致），**绝不静默跳过**，转成 `CHECKER_UNKNOWN` ERROR 发现。
- **消费层**：`print_human` 每检查器头部标 `[#NN 名称]` + `✓ 已执行 / ✗ 执行失败 / ✗ 未注册(UNKNOWN)`，每个技能尾部打印一行回执（`检查器执行回执: ✓doc … ✓doc-llm ✓examples  [9/9 已执行 OK]`）；`--json` 在记录中给出 `checker_runs`；`dev_self_audit` 与 `cli.py --preview` 同样展示 `#代号`。

## 检查项明细（权威错误码对照表）

下表为全部检查项的权威对照。`category` 是**稳定机器标识符**，用于 `--json` 机读输出与跨版本比对，不应随意改名；`中文标签` 由 `auditlib/core.py` 的 `CATEGORY_LABELS` 自动映射，用于人类可读报告（`category_cn` 字段），使每条发现自解释。新增检查项须在 `auditlib/core.py` 的 `CATEGORY_LABELS` 与本文档同步登记。

| 检查器 | 项（category） | 中文标签 | 说明 | 默认级别 |
|---|---|---|---|---|
| doc | `DEAD_PATH` | 死路径 | `SKILL.md` 引用的带 `/` 文件路径已不存在（**仅 SKILL.md 报 ERROR**；`references`/开发文档为叙述性内容，示例路径不报 ERROR，仅裸文件名报 `EXTERNAL_REF` INFO） | ERROR |
| doc | `DEAD_FLAG` | 失效命令行参数 | 文档提到的命令行参数在代码中无实现 | ERROR |
| doc | `EXIT_DOC_ONLY` | 文档独有退出码 | 文档列了退出码，但代码从不返回 | ERROR |
| doc | `EXIT_CODE_ONLY` | 代码独有退出码 | 代码会返回某退出码，但文档未列 | ERROR |
| doc | `UNKNOWN_IDENT` | 未知标识符 | 文档提到的 snake_case 标识符在代码/声明中不存在（已自动跳过 frontmatter 与文档中声明的外部 MCP/插件工具名，避免对 Agent 类技能误报） | WARN |
| doc | `VERSION_MISSING` | 缺少版本声明 | SKILL.md 缺少 version 声明 | ERROR |
| doc | `EXTERNAL_REF` | 外部裸文件名引用 | 裸文件名引用，可能指向技能外文件，需人工确认 | INFO |
| doc | `B_STATUS` | 运行状态枚举 | 运行状态全集（供 AI 复核） | INFO |
| doc | `B_CONFIG` | 配置项枚举 | 配置项全集（供 AI 复核） | INFO |
| doc | `DOC_ENUM_DRIFT` | 文档枚举/集合与代码不一致 | 文档枚举的集合（如 deadcode 模式 `{ask,vulture,ast,off}` 或 `ask/vulture/ast/off`）与代码权威集合 `DEADCODE_MODES` 不符 | WARN |
| doc | `DOC_COUNT_DRIFT` | 文档数量声明与代码不一致 | 文档「N 个检查器」等数量声明与 `len(ALL_CHECKERS)` 实际计数不符 | WARN |
| doc | `DOC_CAPABILITY_DRIFT` | 文档声称的能力在代码中无对应实现 | 能力声明动词（提供/支持/默认/自动/…）行内的反引号标识符在代码与声明中均不存在（能力可能已移除或拼写有误） | WARN |
| doc | `DOC_CAPABILITY_MISSING` | 代码声明的能力文档未提及（正向覆盖缺口） | 仅审计本框架技能（代码含 `ALL_CHECKERS`）：注册的每个检查器名 / 用户面向 CLI 参数须出现在 SKILL.md 或 references 文档中，否则提示文档漏更新（与 `DOC_CAPABILITY_DRIFT` 正反向对称） | WARN |
| doc-llm | `DOC_LLM_DRIFT` | 文档/代码语义漂移（agent 判定） | `doc-llm` 检查器（v1.23.0 起纳入 `--all-checks`，v1.24.0 起由 agent 直接接手）经 agent 用自身能力判定的语义漂移条目，仅作线索（v1.22.1 引入 / 接手机制 v1.24.0） | WARN |
| doc-llm | `doc_llm_agent_handoff` | 语义漂移检测已转交 agent 接手 | 用户选「agent 接手」或显式 `--doc-llm-mode agent`：脚本写 dossier（SKILL.md 全文 + 代码事实清单 + 正向覆盖缺口预分析 + 比对要点）+ 打印 `AGENT_TAKEOVER` 哨兵，由 agent 读取后自行比对 | INFO |
| doc-llm | `ask_undecided` | 决策未决（非交互硬失败） | `--all-checks` 全量自带 `doc-llm`、非交互环境（stdout/stderr 任一非 TTY）无法向用户询问 → 硬失败挂起（ERROR，退出码 1），强制以显式 `--doc-llm-mode agent/off` 重跑；与 deadcode/examples 层级3 一致。不再静默软跳过（旧 `doc_llm_skipped` INFO 已弃用） | ERROR |
| structure | `name_mismatch` | 名称不一致 | frontmatter name 与目录名不一致 | WARN |
| structure | `version_missing` | 版本缺失 | 缺少合规 version | ERROR |
| structure | `name_missing` | 名称缺失 | 缺少 name 声明 | ERROR |
| structure | `license_missing` | 许可证缺失 | 缺少 license 声明 | WARN |
| structure | `h1_name_mismatch` | 标题与名称不一致 | 正文 H1 与 name/displayName 不一致 | WARN |
| structure | `oversize_doc` | 文档过大 | SKILL.md 超过大小上限 | WARN |
| structure | `oversize_file` | 文件过大已跳过 | 代码文件超过大小上限被跳过 | WARN |
| structure | `desc_missing` | 描述缺失 | 缺少 description | ERROR |
| structure | `desc_length` | 描述长度异常 | description 长度应 20-1024 字符 | WARN |
| structure | `desc_four` | 描述四要素不全 | description 建议含四要素 | INFO |
| structure | `no_frontmatter` | 缺少 frontmatter | 建议使用 YAML frontmatter | WARN |
| structure | `too_long` | 文档过长 | 正文超过 500 行建议拆分 | WARN |
| structure | `broken_ref` | 加载式引用失效 | 加载式引用（references/、scripts/）目标不存在 | ERROR |
| structure | `hardcoded_path` | 硬编码绝对路径 | 文档含硬编码用户绝对路径 | WARN |
| structure | `todo_marker` | 待办标记 | 含 TODO/FIXME 标记 | WARN |
| structure | `placeholder` | 占位/历史文本 | 疑似占位/历史记录文本 | INFO |
| security | `hardcoded_secret` | 疑似硬编码密钥 | 疑似硬编码密钥/凭据 | ERROR |
| security | `path_traversal` | 路径穿越 | 路径穿越('../')（上下文感知：排除注释/文档URL/自引用上溯，避免误报）| ERROR |
| security | `destructive_wildcard` | 危险通配删除 | 用户目录通配删除 'rm -rf *' | ERROR |
| security | `obfuscation` | 疑似混淆编码 | 疑似混淆/编码隐藏执行 | WARN |
| security | `dynamic_exec` | 动态执行 | 动态执行外部内容 eval/exec | WARN |
| security | `hardcoded_endpoint` | 硬编码远端端点 | 脚本硬编码远端地址（供应链风险，仅当行内含代码上下文 `=`/`(`/`[`/`return`/`yield` 才报，避免文档/注释里的示例 URL 误报） | WARN |
| security | `dynamic_import` | 动态导入 | 反射式模块加载（`importlib.import_module` / `__import__` / `getattr(sys.modules)`） | WARN |
| security | `secret_in_doc` | 文档含疑似密钥 | 文档出现疑似密钥（可能为示例） | WARN |
| security | `injection_phrasing` | 疑似注入句式 | 文档含疑似提示词注入句式，需 AI 复核 | INFO |
| runtime | `py_syntax` | Python 语法错误 | Python 脚本语法错误 | ERROR |
| runtime | `script_ref_missing` | 脚本引用缺失 | 文档引用的脚本不存在 | ERROR |
| runtime | `py_check_fail` | 语法校验失败 | 无法校验语法 | WARN |
| runtime | `capability` | 能力预检 | 脚本能力预检（静态列举，不执行） | INFO |
| deps | `undeclared_cli` | 未声明外部 CLI | 代码调用外部 CLI 但文档未声明依赖 | WARN |
| deps | `platform_undeclared` | 未声明运行平台 | 代码含 Windows 专属 API 但未声明运行平台 | INFO |
| deadcode | `unused_def` | 未使用的定义 | 模块内定义的函数/类但从未被引用（动态派发/钩子可能误报） | WARN |
| deadcode | `unused_import` | 未使用的导入 | 导入但未使用 | INFO |
| deadcode | `unreachable` | 不可达代码 | return/raise 之后紧跟的无条件语句 | WARN |
| deadcode | `orphan_asset` | 孤立资源文件 | `scripts/` 或 `references/` 中从未被引用/加载的文件 | WARN |
| deadcode | `vulture` | 高精度死代码（可选） | 仅当 `--deadcode-mode vulture` 且环境已安装 vulture 时产出（高精度检测） | WARN |
| portability | `hardcoded_abs_path` | 硬编码绝对路径 | 硬编码用户/家目录绝对路径（Windows `C:\...` 或 Unix `/Users/`/`/home/`），非对应平台将失效 | WARN |
| portability | `cwd_dependence` | 启动目录依赖 | 依赖 `os.getcwd()`/`process.cwd()` 定位资源，从其他目录启动时失败 | WARN |
| portability | `platform_shell` | 平台专属 shell/命令 | 调用平台专属命令（`cmd.exe`/`powershell` 或 `rm -rf`/`ls`/`mkdir -p` 等），无跨平台分支兜底 | WARN |
| portability | `interpreter_lock` | 解释器/运行时锁 | 裸 `python`（非 python3）或 Windows `py` 启动器，跨平台不可用 | WARN |
| portability | `encoding_sep` | 编码/路径分隔符假设 | `open()` 未指定 `encoding`，Windows 文本模式默认非 UTF-8 易致解码错误 | WARN |
| portability | `agent_coupling` | Agent 平台耦合 | 耦合 WorkBuddy 平台约定（`.workbuddy`/`allowed-tools`），受 `target_agent` 字段门控：声明跨 Agent 目标（不含 workbuddy，如 claude-code/cross-agent）且仍含 WorkBuddy 耦合升 WARN，其余（未声明/声明含 workbuddy/推断 workbuddy）均 INFO 提示（不再抑制）；开放标准 `compatibility` 视作 `target_agent` | INFO/WARN |
| portability | `lossy_port` | 跨格式可移植性损失 | Phase 6 矩阵发现：技能显式声明跨 Agent 目标（如 `compatibility: [claude-code, cursor]`）却含目标端无对应字段（`lost`，升 WARN）或需转译（`degraded`，仅 INFO）的字段；纯 workbuddy/未声明目标不触发 | INFO/WARN |
| examples | `EXAMPLE_TARGET_MISSING` | 示例引用文件不存在（照抄将失败） | 示例命令引用的脚本文件（`.py/.js/.mjs/.ts/.sh/.ps1`）在技能目录中不存在（仅核验脚本扩展名，仓库引用 / 安装路径 / 输出文件跳过，避免误报）；SKILL.md 报 ERROR、其余文档 WARN | ERROR/WARN |
| examples | `EXAMPLE_TARGET_UNVERIFIABLE` | 示例引用无法核验（纯文档快照） | 纯文档快照（未取到技能代码）时示例引用无法核验，退为 INFO 提示，绝不把「没下载到」误判成「文件不存在」 | INFO |
| examples | `EXAMPLE_FLAG_UNKNOWN` | 示例参数在脚本中无声明 | 示例给脚本传了参数，但该脚本中未找到对应 `add_argument` 声明（AST 解析 + 单层跟随导入 + 字面量兜底；仅 SKILL.md） | WARN |
| examples | `EXAMPLE_EXT_CMD` | 示例调用外部命令但未声明依赖 | 示例调用外部 CLI（curl/pip/git/docker…），但文档未出现该依赖说明 | INFO |
| examples | `EXAMPLE_DANGEROUS` | 示例含危险/不可逆命令 | 示例含 `rm -rf /`、fork 炸弹、`mkfs`、`dd` 写块设备、远端内容直喂 shell、`sudo rm` 等危险/不可逆命令（照抄风险） | ERROR/WARN |
| examples | `EXAMPLE_UNVERIFIED` | 示例标注了期望但未执行验证 | 示例块标注了 `expected-*`，但当前为纯静态模式，未做执行验证（如需执行请 `--examples-mode run`） | INFO |
| examples | `EXAMPLE_SANDBOX_SKIP` | 示例未执行（沙箱拒绝） | run 模式下示例因不满足沙箱白名单（解释器 / 脚本路径 / 元字符）被跳过，INFO 说明原因（安全红线，不可放宽） | INFO |
| examples | `EXAMPLE_OUTPUT_DRIFT` | 示例执行结果与标注期望不符 | run 模式执行示例后，退出码 / 标准输出 / 标准错误与 `expected-*` 标注不一致 | WARN |
| examples | `EXAMPLE_RUN_FAIL` | 示例执行失败/超时 | run 模式执行示例抛异常或超时（> `--examples-timeout`，默认 20s） | WARN |
| examples | `EXAMPLE_RUN_LIMIT` | 示例执行已达上限 | 单技能执行示例数已达 `--examples-max-cmd`（默认 12），其余标注示例未执行 | INFO |
| examples | `examples_degraded` | 示例执行验证已降级为纯静态 | 非交互环境且未显式授权执行，回退纯静态并显式标注（绝不静默代决） | INFO |
| examples | `examples_run_noop` | 沙箱已启用但无标注示例 | 已启用 run 模式，但文档中没有任何带 `expected` 标注的示例块，本次未执行任何命令 | INFO |

## 平台豁免字段 `target_platform`

`portability` 检查器读取 SKILL.md frontmatter 的 `target_platform` 字段来抑制「有意绑定某平台」的误报。规则：某条发现**仅当声明平台与该发现会崩的平台有交集时才报**（`fire iff 声明平台 ∩ breaks_on ≠ ∅`）；未声明 / `cross-platform` / `all` / `*` → 视为全平台 → 始终报。

| 声明值 | 语义 | 典型抑制效果 |
|---|---|---|
| 省略 / `cross-platform` / `all` / `*` | 全平台 | 无豁免，6 类全报 |
| `windows` | 仅 Windows | 抑制 `C:\` 路径 / `powershell` / 裸 `python` 告警；但 `/Users/` 路径、`rm -rf`、`cwd` 依赖、`open()` 无 encoding（这些在 Windows 上才真坏）仍报 |
| `linux` / `macos` | 单一 Unix | 抑制 `rm -rf`/`ls` 等 Unix 命令告警；`C:\` 路径 / `powershell` 仍报 |
| `[windows, linux]` | 多平台列表 | 仅抑制两平台均覆盖的项 |

> `#6 agent_coupling` 的门控维度是 **Agent** 而非 OS，不走 `target_platform` 的 OS 门控，而由下方 `target_agent` 字段单独门控（v1.11.0 起；v1.11.1 起不再因 `workbuddy` 而抑制）。

## 跨 Agent 字段 `target_agent`

> **Phase 5 归一化内核**：审计引擎以 `detect_format()` 按 frontmatter 特征推断技能格式（`workbuddy` / `agentskills` / `claude-code` / `cursor-mdc` / `generic`），并构建统一 `SkillModel` 承载 name/description/fmt/platform/target_platform/target_agent/tools/license/version/extra，供各检查器与后续矩阵/转译消费。格式判定「按特征推断」而非硬锁枚举，以适配生态演进。

`agent_coupling`（Agent 平台耦合）按 SKILL.md frontmatter 的 `target_agent` 字段门控，维度是「目标 Agent 平台」而非 OS。规则：声明跨 Agent 目标（不含 `workbuddy`，如 `claude-code`/`cross-agent`）但仍含 WorkBuddy 耦合 → 升为 WARN（跨 Agent 会失效）；其余（未声明 / 声明含 `workbuddy` / 推断 `workbuddy`）→ 均 INFO 提示（v1.11.1 起不再因声明 `workbuddy` 而抑制，耦合提示对所有技能均有价值，供作者评估跨 Agent 可移植性）。

`target_agent` 取值为**自由列表**（如 `workbuddy` / `claude-code` / `[workbuddy, claude-code]` / `cross-agent`）；开放标准技能的 `compatibility` 字段（如 `[claude-code, cursor]`）视作 `target_agent`。未写字段时按信号推断：技能内容含 `mcp__`/`.workbuddy` 等 WorkBuddy 特征 → 视为 `workbuddy`。`workbuddy` 仅作为「是否升 WARN」的边界判定（声明跨 Agent 但不含 `workbuddy` 才升 WARN），不再作为抑制信号。

| 声明值 | 语义 | agent_coupling 效果 |
|---|---|---|
| 省略 / 无 WorkBuddy 信号 | 未知 | INFO 提示（跨 Agent 分发需抽象） |
| `workbuddy` | 仅 WorkBuddy | INFO 提示（不再抑制，供评估跨 Agent 可移植性） |
| `claude-code` / `[claude-code, cursor]` | 跨 Agent，未含 workbuddy | WARN（仍耦合 WorkBuddy 会失效） |
| `[workbuddy, claude-code]` | 多 Agent 含 workbuddy | INFO（含 workbuddy 不升 WARN，但仍提示） |

## 跨格式可移植性矩阵（Phase 6）

在 Phase 5 统一 `SkillModel` 之上，引擎以开放标准 `agentskills` 为枢纽，构建字段级能力映射（`FMT_CAPS` 各格式原生支持的字段集合、`EQUIV` 跨格式等价字段），对任意技能生成「源格式 → 各目标格式」的 **P（保留）/ D（降级需转译）/ L（丢失）** 矩阵。`--report portability-matrix` 直接打印该矩阵（不改写任何文件）。

- **触发**：`lossy_port` 仅在技能**显式声明跨 Agent 目标**（`target_agent`/`compatibility` 含非 `workbuddy` 项，如 `claude-code`/`cursor`/`cross-agent`）时产出发现；纯 workbuddy 或未声明目标的不发（其跨 Agent 咨询已由 `agent_coupling` 覆盖），避免对未声明目标刷噪音。
- **分级**：字段在声明目标端 `lost`（无对应字段，如 workbuddy 的 `version`/`slug` 在 claude-code）→ **WARN**；`degraded`（有等价字段需转译，如 `target_agent`→`compatibility`、`slug`/`displayName`→`name`）→ **INFO**。
- **等价映射（固化 v1.11.0 约定）**：`target_agent` ↔ `compatibility`；`slug`/`displayName` → `name`。
- **Cursor 两种形态**：Cursor Plugin 的 `SKILL.md` 等同 `agentskills`（支持 `allowed-tools`/`compatibility`）；若以 `.mdc` 规则文件分发（`cursor-mdc`），则无 `name`/`allowed-tools`，损失更大——矩阵报告中对 `cursor-mdc` 单列呈现以提示差异。

## 跨格式转译报告（Phase 7，只读预览·不落盘）

在 Phase 5/6 底座之上新增 `--report translate`，把「检测/矩阵」升级为「可预览的转译方案」。核心约束：**只出报告、不落盘**，守住本技能「只读扫描、绝不自动改写」的立身之本。

- **复用底座**：直接消费 `SkillModel`（P5）+ `FMT_CAPS`/`EQUIV`/`build_portability_matrix`（P6），无新增扫描逻辑，避免与 P5/6 漂移。
- **用法**：`--report translate --target <fmt>`。`--target` 取值 `workbuddy`/`agentskills`/`claude-code`/`cursor-plugin`/`generic`，与源格式**双向**（源可为任一已识别格式）。`--verify` 在此之上做内存往返保真（emit→re-parse→比对，不写文件）。
- **agentskills = 全生态通用枢纽**：`--target agentskills` 与 `--target cursor-plugin` 产出的 frontmatter 即 **Agent Skills 开放标准（agentskills.io，Anthropic 2025-12 开源）** 形态（`name`/`description`/`license`/`allowed-tools`/`compatibility`/`metadata`）。该标准截至 2026 年已被 **40+ AI 工具**采纳——Claude Code、Cursor、Gemini CLI、OpenAI Codex、GitHub Copilot、Windsurf、Kiro、OpenCode、Cline、Roo Code 等。即**一次转译到 `agentskills`，即可被上述 40+ 工具直接消费**；`claude-code` 仅叠加 `model`/`context`/`agent`/`hooks`/`argument-hint` 等可选扩展键。故「更多目标格式」诉求已被现有目标覆盖，`generic` 仅作兜底。
- **报告内容**（决策①+②）：① 仅出报告不生成文件；② 仅 **frontmatter 字段映射表**（保留/降级/丢失逐项标注）+ **目标 SKILL.md 脚手架预览**（仅 frontmatter + 标题骨架，正文散文不翻译、留人工）。脚手架输出明确标注「仅展示，不落盘」。
- **字段映射内核**：`emit_frontmatter(model, target_fmt)` 依 `FMT_CAPS` 逐字段映射；命中 `EQUIV`（如 `target_agent`→`compatibility`、`slug`/`displayName`→`name`）记降级；目标格式无对应记丢失。多个源字段映射到同一目标字段（如 `slug`/`displayName` 与 `name`）时，保留 canon `name`、其余价值并入并记降级、不重复写入。
- **往返保真（`--verify`，决策④）**：复用 `build_portability_matrix` 中该目标行的 `status`——`preserved` 完整往返、`degraded` 可往返（重命名）、`lost` 不可逆。整体结论 `RECOVERABLE`（无丢失）/ `LOSSY`（仅重命名类字段丢失，可人工补回）/ `IRREVERSIBLE`（含不可恢复字段如 `version`/`slug`/`displayname`）。全程内存计算，不落盘。
- **JSON**：`--json` 时每个技能结果附 `translate` 字段（`source_format`/`target_format`/`frontmatter`/`lost_fields`/`degraded_fields`；`--verify` 追加 `round_trip`）。
- **范围（决策③ + v1.16.0 追加 `generic`）**：先支持 `workbuddy`↔`agentskills`/`claude-code`/`cursor-plugin`；v1.16.0 起追加 `generic` 作为**降级兜底**目标——仅保留 `name`/`description`，其余字段（version/license/allowed-tools/target_agent/slug/displayname/metadata 等）全部丢失，报告前置「⚠ 高损失」警告并提示「如需完整跨 Agent 分发，优先用 agentskills/cursor-plugin（一次转译全生态通用）」。`.mdc` 规则文件（`cursor-mdc`）损失更大，本期仍不纳入 emit 目标（仅矩阵单列呈现）。

## 生态级批量审计与供应链安全（Phase 8）

面向「作者/组织自检整库或整组织技能健康度」场景（对标 Snyk ToxicSkills，但服务于作者而非攻击者）：

- **批量来源**：`--source github --ref owner/repo1,owner/repo2`（逗号分隔多仓库）一次性审计多个远程仓库；`--source local --all` 审计本机全部已装技能。每个仓库/技能独立落地、独立审计、独立聚合，任一失败不影响其余。
- **供应链安全启发式**（喂给 `security`）：在既有 `hardcoded_secret`/`obfuscation`/`dynamic_exec`/`path_traversal`/`destructive_wildcard` 之上新增两项——`hardcoded_endpoint`（脚本硬编码远端地址，仅当行内含代码上下文 `=`/`(`/`[`/`return`/`yield` 才报，排除文档/注释示例 URL 与检查器自身源码误报）、`dynamic_import`（反射式模块加载 `importlib.import_module`/`__import__`/`getattr(sys.modules)`）。两者均标 **WARN**，提示「远端地址/动态加载目标应提取为配置并核验来源可信」。
- **健康度汇总报告**：`--report health` 输出逐技能 ERROR/WARN/INFO 计数与「含供应链安全风险技能数」汇总；`--json` 在审计 ≥2 个技能时自动附带 `health_summary` 顶层键，便于 CI / 批量巡检消费。

## 判定提示

> `structure`/`security`/`runtime` 中的 `WARN`/`INFO` 项（如 description 长度、混淆、动态执行、能力预检清单）为提示性质，需结合上下文判断，勿直接当错误处置。

> 即便 `doc` 类的 `DEAD_PATH` 也需看一眼上下文：它可能是文档在引用**运行期生成的产物**（例如某技能会在目标项目里创建 `.learnings/` 目录，或脚本在临时目录生成 state）。这类引用在本技能目录下确实找不到，却并非漂移。判定前留意引用处是否含「生成 / 创建 / 写入」等含义。

## 需 AI 语义复核的部分

**脚本只能枚举差异、需 AI 判断的（默认多为误报）**

运行状态全集、配置项全集。内部实现细节本就不必写进面向用户的文档，故「未提及」通常是正常的——**只有当该状态或配置属于用户可感知行为**（如退出码含义、可手动调整的开关）时才需要补写。脚本只呈现事实，不判定对错。

**脚本完全查不出、必须由 AI 读代码判断的**

- 描述是否准确反映实际行为（例如文档写某功能是「兜底」，实测它早已失效）
- 提示文案是否误导用户
- 代码注释与实现是否一致
- 跨文件一致性（项目记忆、报告与 SKILL.md 之间）

> 因此**不要只用脚本结论就下判断**。扫描报告是线索，不是裁决。

## 误报自纠错能力

`security` 检查器对所有正则（硬编码密钥 / 混淆 / 动态执行 / 路径穿越 / 通配删除）统一采用上下文感知过滤，自动排除以下情形，避免上下文盲误报：

1. **注释行**：以 `#`、`//`、`/*`、`*`、`<!--` 开头的整行；
2. **文档 URL**：含 `://` 的行（例如文档里出现的 API 基地址中 `.../` 段，曾被误判为路径穿越）；
3. **自引用资源上溯**：含 `__file__`/`dirname`/`.asar`/`install_dir` 等标记的行（合法定位安装目录，非真实穿越）。

真实漏洞（如将外部可控字符串拼入用于 `open`/`os.remove`/`shutil` 的落盘路径并含相对上溯）仍正常报出。该机制无需人工逐条标注，统一作用于全部 security 正则，只减误报、绝不增 ERROR。

## 死代码检查误报抑制（deadcode）

死代码本质是「静态不可达 / 未引用」的启发式判定，天然有漏报/误报，故本检查器全部输出 **WARN/INFO，绝不 ERROR**，结论需人判。已内置四重抑制降低误报：

1. **字符串字面量引用视为已用**：扫描所有字符串常量中的标识符，覆盖「按字符串键注册到 dispatch 字典」「反射 / 动态调用」等场景，避免把被字符串键注册的函数误判为死代码（宁可漏报、绝不误报）。
2. **入口/特殊名启发**：`main`/`run`/`handler`/`setup`/`callback` 等常见入口名，以及 `__` 开头结尾的魔术方法，视为已用。
3. **`# keep` 内联白名单**：在定义行或上一行加 `# keep` 注释，即可保留该定义/导入、不再告警（适用于公开 API、钩子、测试辅助等确属有意的「未直接引用」符号）。
4. **跨文件引用感知**：`unused_def` 先汇总全技能所有 `.py` 的引用集合，仅当某定义在**全技能范围都未被引用**时才报，避免把「本文件定义、他文件调用」的符号误判为死代码（多文件技能常见场景）。

孤儿资源（`orphan_asset`）判定保守：只要文件名或相对路径（`scripts/x.py`、`references/x.md`）出现在任意文档或代码文本中，**或被技能内其他 `.py` 以模块名 import**，即视为已引用，故只可能漏报、不会把被引用文件误标为孤儿。可选增强 `vulture` 仅在选择 `--deadcode-mode vulture` 时运行：环境已装即直接高精度；未装则先尝试自动 `pip install vulture`（**仅此显式路径会联网安装**——ask 模式的非交互自动回退路径绝不触发安装，避免自动化场景意外联网），装不上再回退零依赖 `ast`；选 `ast`/`off` 或 ask 自动回退时不运行也不安装，不影响默认行为。

**两种精度模式的分工（避免重复报告）**：`ast` 模式由 AST 负责未使用导入 / 未使用定义 / 不可达代码 + 孤儿资源；`vulture` 模式由 vulture 负责导入 / 定义 / 类 / 方法 / 变量检测（高精度、低噪声），并叠加 AST 独有的不可达代码与孤儿资源检测，**不再重复报告 AST 的导入/定义项**。两种模式均支持 `# keep` 内联白名单（vulture 分支同样按定义行/上一行判定 `# keep` 并跳过）。vulture 分析若异常（如版本 API 不兼容），会在 stderr 打印告警并跳过该步、不影响其余检查器。

## examples 检查器：功能与风险详解

examples 检查器（检查器 #9，v1.26.0 起纳入 `--all-checks` 全量集）校验**任意技能**文档里写出的命令示例是否站得住脚——既拦「照抄会失败」的示例，也拦「照抄会闯祸」的危险命令。它**不是**「跑一遍文档里的命令看对不对」，而是静态 + 可选沙箱两层：默认零执行、零网络、零 token，只在显式授权时才受限试运行。

### 一、检查覆盖（五类）

1. **危险 / 不可逆命令（所有文档均检，真实照抄风险最高）**：`rm -rf /`、`mkfs`、`dd` 写块设备、远端内容直喂 shell（`curl ... | sh`）、fork 炸弹、`sudo rm`、强制 `git push -f` 等。根目录 / 家目录递归删除与提权删除报 **ERROR**（照抄即不可逆），其余 `rm -rf <路径>` / `git push -f` / `chmod 777` / `sudo` 等报 **WARN**（照抄易误伤）。这是本检查器价值最高的一类——文档示例最常被用户原样复制执行。
2. **示例引用的脚本文件是否存在（照抄将直接失败）**：仅核验以 `.py/.js/.mjs/.ts/.sh/.ps1` 结尾的引用；仓库引用（`owner/repo`）、安装路径（`~/.workbuddy/...`）、输出文件（`audit.json`）、占位目录（`./huge-monorepo`）等一律跳过（这些不是「照抄会失败」的脚本，套 ERROR 会误报）。`SKILL.md` 报 **ERROR**、其余文档报 **WARN**；纯文档快照（`--source url` 未取到代码）退为 `EXAMPLE_TARGET_UNVERIFIABLE` INFO，绝不把「没下载到」误判成「文件不存在」。
3. **示例参数是否在脚本中声明（仅 `SKILL.md`）**：示例给脚本传了 `--xxx` 但该脚本（含单层导入模块）未声明该参数 → `EXAMPLE_FLAG_UNKNOWN`（WARN）。无参数表可静态确定时**跳过**（不猜、不误报）。`references` / 开发文档常引用开发期工具（参数表不在发布面代码内），故只对能力目录口径的 `SKILL.md` 校验，与 `doc` 检查器 A2 一致。
4. **外部 CLI 依赖声明（INFO 提示）**：示例调用了 `curl` / `pip` / `git` / `docker` 等外部 CLI，但该 CLI 未在本技能**代码**中出现、也未在 frontmatter 声明 → 提示可能缺依赖说明。判定用「代码 + frontmatter」而非「文档是否含该 token」——因为示例本身就写出该命令，token 必然出现，否则必误报。
5. **沙箱试运行（仅 `run` 模式 + 作者显式标注）**：对带 `{example expected-exit=0 expected-stdout="..."}` 标注的示例，在受限沙箱内执行并比对期望（退出码 / 标准输出 / 标准错误）；超出条数上限（`--examples-max-cmd`，默认 12）或超时（`--examples-timeout`，默认 20s）即停。未标注的示例在任何模式下**只做静态检查、不执行**。

### 二、多档模式与默认姿态

| 模式 | 行为 | 适用场景 |
|---|---|---|
| `ask`（**默认**） | 交互终端弹菜单询问是否授权沙箱试运行；30s 超时 / 非交互环境一律回退 `static` 并发 INFO 标注「已降级」 | 交互终端想试运行又想确认（日常 / CI / Agent 自动化默认落到 `static` 静态档） |
| `static` | 纯静态解析，零执行 / 零网络 / 零 token / 零第三方依赖 | 日常审计、CI、Agent 自动化（即 `ask` 的回退落点） |
| `run` | 受限沙箱试运行带 `expected` 标注的示例 | 显式要验证示例真实输出 |
| `off` | 完全跳过本检查器 | 不需要示例校验时 |

默认 `ask` 仍坚守**最保守姿态**：本检查器绝不替用户决定执行——仅交互环境弹问询，非交互（管道 / Agent 自动化）直接回退 `static` 并显著标注降级，超时无输入也回退 `static`，杜绝「静默执行」。

### 三、安全红线（不可协商）

即便 `run` 模式也**绝不执行文档里的任意 shell**。只执行同时满足以下全部条件的命令：① 首 token 为白名单解释器（`python` / `python3` / `py` / `node`）；② 参数无 shell 元字符（`; | & > < $ \` ( )` 等，含重定向与管道）；③ 目标脚本位于被审计技能目录内（路径越界即拒绝，防读写技能外文件）；④ 脚本扩展名在白名单内（`.py/.js/.mjs`）；⑤ 该示例由作者显式标注了期望；⑥ 受超时与条数上限约束。任一不满足即跳过并 INFO 说明原因，**绝不「尽力执行」**。执行时还尽力剥离网络代理环境变量（仅降低意外外联概率，不替代真沙箱）。

### 四、风险与局限（使用者须知）

- **默认不执行 → 不捕获运行期失败与输出漂移**：`static` 模式只验证示例「结构性站得住脚」（文件在、参数有声明、命令不危险），**不验证脚本真的能跑通、输出真的匹配文档**。要验证运行期行为必须显式 `--examples-mode run` 且为示例加 `expected` 标注——而目前多数技能文档的示例未标注 `expected`，故 `run` 模式对其只做静态检查。
- **只验证「站得住脚」，不验证「逻辑正确」**：示例引用的文件存在、参数有声明、命令不危险，不代表示例演示的功能真的符合文档描述。语义正确性仍属 `doc-llm` 的 AI 复核范畴。
- **参数校验仅限 `SKILL.md`**：`references` / 开发文档里的示例参数不校验，可能漏掉开发文档中的失效参数（但开发文档非发布面，影响小）。
- **保守设计带来的漏报面**：多重误报抑制（见下）刻意「宁漏不误」——域名式 `foo.bar`、包名式引用、占位路径都被跳过，意味着真正缺失的脚本若恰好以非脚本扩展名或特殊形式出现，可能漏报。examples 与 `doc` 检查器的 `DEAD_PATH` 互补但不重叠。
- **`run` 模式的沙箱是轻量隔离，不是安全沙箱**：它限制解释器 / 路径 / 元字符 / 超时，但不限制文件系统读写范围（脚本本身可能在技能目录内写文件）、不提供完整容器隔离。执行不可信技能的示例前仍须人工评估。

### 五、误报抑制机制（保守设计）

文档示例本质是「给人看的例子」，天然含占位 / 说明性路径，故本检查器做了多重保守设计，只报高置信缺陷、绝不把说明性内容当缺失文件：

1. **仅核验脚本扩展名**：示例命令里只有以 `.py/.js/.mjs/.ts/.sh/.ps1` 结尾的引用才核验存在性；仓库引用（`owner/repo`）、用户安装路径（`~/.workbuddy/...`）、输出文件（`audit.json`）、占位目录（`./huge-monorepo`）等一律跳过——这些不是「照抄会失败」的脚本，套 ERROR 会误报。通用文件引用由 `doc` 的 `DEAD_PATH` 覆盖。
2. **参数校验仅 SKILL.md**：示例给脚本传的参数是否在脚本中声明，只对技能本体 `SKILL.md` 生效（`references`/开发文档常引用开发期工具如 `make_fixtures.py --baseline`，其参数表不在发布面代码内，套用会误报）。且无参数表可静态确定时跳过（不猜、不误报）。
3. **纯文档快照退 INFO**：`--source url` 只取到 SKILL.md、无代码文件时，无法核验示例目标是否存在，一律退为 `EXAMPLE_TARGET_UNVERIFIABLE` INFO，绝不把「没下载到」误判成「文件不存在」。
4. **执行红线不可放宽**：`run` 模式也绝不执行任意 shell——只跑白名单解释器 + 技能内脚本 + 无 shell 元字符 + 带 `expected` 标注 + 超时保护的命令，不满足即跳过并 INFO 说明。

## 命令行参数速查

| 参数 | 作用 |
|---|---|
| `--skill <目录>` | 审计单个技能目录（含 SKILL.md） |
| `--all` | 批量审计 `~/.workbuddy/skills/` 下全部已安装技能 |
| `--check <名称>` | 仅启用指定检查器（可重复），`doc` 常驻默认开 |
| `--all-checks` | 启用全部检查器（含 deadcode） |
| `--deadcode-mode {ask,vulture,ast,off}` | deadcode 精度模式；`ask` 默认已装 vulture 则自动高精度(不询问)，未装则交互询问、30s 超时或非交互回退 `ast`（**不安装**）；显式 `vulture` 或交互选 vulture 缺库时先自动安装、失败回退 `ast` 并 WARN 告警；`ast`/`off` 绝不联网安装 |
| `--preview` | 只预览将运行的检查器与将扫描的文件，不产出发现，退出码 0（适合首次审计前心里有数） |
| `--strict` | WARN 也计入退出码（CI 门禁用） |
| `--json` | 额外输出 JSON 机读结果（每条含 checker/severity/category/category_cn/message/file/line/suggestion） |
| `--timeout <秒>` | 整体超时保护，超时优雅终止（退出码 130）而非卡死 |
| `--max-file-size <字节>` | 超大文件跳过阈值，避免拖慢 |
| `--backup` / `--backup-limit N` | 审计前备份 SKILL.md（默认最多保留 3 个备份） |
| `--examples-mode {static,ask,run,off}` | examples 检查器模式；`ask` 默认(交互询问是否沙箱试运行，30s 超时/非交互回退 static 并 INFO 标注)，`static` 纯静态(零执行/零网络/零 token)，`run` 受限沙箱试运行带 expected 标注的示例，`off` 跳过 |
| `--examples-timeout <秒>` | examples run 模式下单条示例命令执行超时（默认 20） |
| `--examples-max-cmd <条>` | examples run 模式下单技能最多执行示例命令条数（默认 12，防突刺） |
| `--doc-llm-mode {ask,agent,off}` | doc-llm 语义检测模式；`ask` 默认（交互终端问询是否 agent 接手，30s 超时回退 off；非交互环境无法征询 → 硬失败挂起 `ask_undecided`（ERROR），须显式 `--doc-llm-mode agent/off` 重跑），`agent` 写 dossier 由 agent 接手比对，`off` 跳过 |
| `--examples-consent` | examples 授权令牌：agent 非交互环境显式指定 `--examples-mode run/static/off` 时须附此令牌，否则脚本阻断并报 `examples_consent_missing`（ERROR），杜绝静默替用户决定 |
| `--source {local,github,skillhub,url}` | 技能来源（默认 local 本机）；`github` 需 git、`skillhub` 需 skillhub CLI、`url` 标准库直抓零外部 CLI |
| `--ref <值>` | 来源引用：`owner/repo`（可 `@分支`，逗号分隔批量）/ 集市 slug / https 地址 |
| `--keep-temp` | 保留克隆/安装/抓取的临时目录并打印路径，便于排查 |
| `--report {portability-matrix,translate,health}` | 生成对应报告（只读，不改写文件） |
| `--target <格式>` | 仅 `--report translate` 时用：目标格式 `workbuddy`/`agentskills`/`claude-code`/`cursor-plugin`/`generic` |
| `--verify` | 仅 `--report translate` 时用：内存往返保真校验，不落盘 |
| `--dev-docs` | 开发者模式：doc/doc-llm 递归扫描技能目录内全部 `.md`（含 README/CHANGELOG），仅维护者自检用 |

