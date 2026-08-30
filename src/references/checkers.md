# 检查器清单与口径（skill-doc-audit 细则）

本文件是 `SKILL.md` 的加载式补充，列明各检查器的完整项、判定口径与误报抑制机制。SKILL.md 仅保留能力边界概述，执行审计时以本文件为明细基准。

## 检查器总览

脚本能可靠判定的偏差由以下检查器产出，可按需启用。代码/配置文件覆盖多语言：`.py/.js/.jsx/.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua/.sh/.ps1/.json`（含 Python 语法校验与多语言硬编码密钥检测）。

- `doc`（常驻默认开）：文档一致性
- `structure`：结构体检 + 元信息
- `security`：安全红线静态子集
- `runtime`：脚本可运行性
- `deps`：依赖与平台声明
- `deadcode`（运行前按 `--deadcode-mode` 选精度，已装 vulture 则自动高精度、不询问）：死代码检测（未使用定义/导入、不可达代码、孤立资源文件）
- `portability`（零依赖纯静态分析，全部 WARN/INFO 不报 ERROR）：跨平台可移植性——硬编码绝对路径 / 启动目录依赖 / 平台专属 shell / 解释器锁 / 编码分隔符假设 / Agent 平台耦合 / 跨格式可移植性损失（`lossy_port`，Phase 6）。按 SKILL.md 的 `target_platform` 字段豁免对应平台项；`--report portability-matrix` 可打印「源格式 → 各目标格式」的 P/D/L 损失矩阵

## 检查项明细（权威错误码对照表）

下表为全部检查项的权威对照。`category` 是**稳定机器标识符**，用于 `--json` 机读输出与跨版本比对，不应随意改名；`中文标签` 由 `audit_docs.py` 的 `CATEGORY_LABELS` 自动映射，用于人类可读报告（`category_cn` 字段），使每条发现自解释。新增检查项须在 `audit_docs.py` 的 `CATEGORY_LABELS` 与本文档同步登记。

| 检查器 | 项（category） | 中文标签 | 说明 | 默认级别 |
|---|---|---|---|---|
| doc | `DEAD_PATH` | 死路径 | 文档引用的文件路径已不存在 | ERROR |
| doc | `DEAD_FLAG` | 失效命令行参数 | 文档提到的命令行参数在代码中无实现 | ERROR |
| doc | `EXIT_DOC_ONLY` | 文档独有退出码 | 文档列了退出码，但代码从不返回 | ERROR |
| doc | `EXIT_CODE_ONLY` | 代码独有退出码 | 代码会返回某退出码，但文档未列 | ERROR |
| doc | `UNKNOWN_IDENT` | 未知标识符 | 文档提到的 snake_case 标识符在代码/声明中不存在（已自动跳过 frontmatter 与文档中声明的外部 MCP/插件工具名，避免对 Agent 类技能误报） | WARN |
| doc | `VERSION_MISSING` | 缺少版本声明 | SKILL.md 缺少 version 声明 | ERROR |
| doc | `EXTERNAL_REF` | 外部裸文件名引用 | 裸文件名引用，可能指向技能外文件，需人工确认 | INFO |
| doc | `B_STATUS` | 运行状态枚举 | 运行状态全集（供 AI 复核） | INFO |
| doc | `B_CONFIG` | 配置项枚举 | 配置项全集（供 AI 复核） | INFO |
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

孤儿资源（`orphan_asset`）判定保守：只要文件名或相对路径（`scripts/x.py`、`references/x.md`）出现在任意文档或代码文本中，**或被技能内其他 `.py` 以模块名 import**，即视为已引用，故只可能漏报、不会把被引用文件误标为孤儿。可选增强 `vulture` 仅当选择 `--deadcode-mode vulture` 且环境已安装时运行；选 `ast` 或默认回退时不运行，`vulture` 缺失也自动回退零依赖，不影响默认行为。

**两种精度模式的分工（避免重复报告）**：`ast` 模式由 AST 负责未使用导入 / 未使用定义 / 不可达代码 + 孤儿资源；`vulture` 模式由 vulture 负责导入 / 定义 / 类 / 方法 / 变量检测（高精度、低噪声），并叠加 AST 独有的不可达代码与孤儿资源检测，**不再重复报告 AST 的导入/定义项**。两种模式均支持 `# keep` 内联白名单（vulture 分支同样按定义行/上一行判定 `# keep` 并跳过）。vulture 分析若异常（如版本 API 不兼容），会在 stderr 打印告警并跳过该步、不影响其余检查器。

## 命令行参数速查

| 参数 | 作用 |
|---|---|
| `--skill <目录>` | 审计单个技能目录（含 SKILL.md） |
| `--all` | 批量审计 `~/.workbuddy/skills/` 下全部已安装技能 |
| `--check <名称>` | 仅启用指定检查器（可重复），`doc` 常驻默认开 |
| `--all-checks` | 启用全部检查器（含 deadcode） |
| `--deadcode-mode {ask,vulture,ast,skip}` | deadcode 精度模式；`ask` 默认已装 vulture 则自动高精度(不询问)，否则交互询问、30s 超时回退 `ast`；Agent/CI 用 `vulture`/`ast`/`skip` 跳过交互 |
| `--preview` | 只预览将运行的检查器与将扫描的文件，不产出发现，退出码 0（适合首次审计前心里有数） |
| `--strict` | WARN 也计入退出码（CI 门禁用） |
| `--json` | 额外输出 JSON 机读结果（每条含 checker/severity/category/category_cn/message/file/line/suggestion） |
| `--timeout <秒>` | 整体超时保护，超时优雅终止（退出码 130）而非卡死 |
| `--max-file-size <字节>` | 超大文件跳过阈值，避免拖慢 |
| `--backup` / `--backup-limit N` | 审计前备份 SKILL.md（默认最多保留 3 个备份） |

