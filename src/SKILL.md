---
name: skill-doc-audit
slug: skill-doc-audit
displayName: 技能文档审计
description: 技能文档审计：审计技能文档与代码的一致性及静态质量，找出版本迭代造成的文档漂移与结构/安全/可运行性/依赖隐患——死链接、失效的命令行参数、退出码表不符、状态或配置项漏写、描述脱节，以及 frontmatter 不规范、硬编码密钥、脚本语法错误、外部依赖与运行平台未声明、跨平台可移植性等。当你刚改完某个技能的脚本或配置、担心文档没跟上，或某个技能经历多次版本迭代后想做一次体检/质量检查/一致性校验时使用。可审计任意本地技能目录、批量审计全部已安装技能，也可经 --source 审计 GitHub 仓库、SkillHub 集市或任意 URL 上的技能；portability 检查器可按 SKILL.md 的 target_platform 字段豁免对应平台项。支持 `--ref` 逗号分隔批量审计多仓库/整组织技能，并以 `--report health` 输出供应链安全自检汇总。
version: "1.27.2"
license: MIT
author: Jett
agent_created: true
allowed-tools: Bash, Read, Edit
tags: [文档审计, 技能体检, 安全审计, 质量检查, 静态分析]
---

# 技能文档审计

## 为什么需要

技能文档会随着版本迭代漂移：代码改了、文档没跟上。典型症状是**死引用**（文档写着某个文件/参数，代码里早已删除）和**描述过时**（文档声称某个行为，实测已不成立）。这类偏差不会让脚本报错，却会误导后续维护者与调用方。

## 能力边界（务必先读）

这个技能是「机器扫描 + AI 语义复核」的组合，两者分工不同：

**脚本能可靠判定的（低误报，通常就是偏差）** —— 由以下检查器产出，可按需启用（模式机制 / 判定口径 / 误报抑制详见 `references/checkers.md`）：

- `doc`（常驻默认开）：文档一致性——死引用 `DEAD_PATH`、失效命令行参数 `DEAD_FLAG`、退出码不符、枚举/数量/能力声明与代码事实不符、正向能力覆盖 `DOC_CAPABILITY_MISSING`（代码注册的能力/参数、文档未写）；自由散文语义漂移由 `doc-llm` 补足。
- `structure`：结构体检 + 元信息（frontmatter / 标题 / 引用）。
- `security`：安全红线静态子集（硬编码密钥、路径穿越、危险通配删除等）。
- `runtime`：脚本可运行性（语法 / 引用缺失）。
- `deps`：依赖与平台声明（未声明外部 CLI / 运行平台）。
- `deadcode`（运行前按 `--deadcode-mode` 选精度）：未使用定义 / 导入、不可达代码、孤立资源文件（Agent 调用须显式传 `--deadcode-mode`，见下方「Agent 执行约定」）。
- `portability`（零依赖纯静态）：跨平台可移植性——硬编码绝对路径、`os.getcwd` 依赖、平台专属 shell、解释器锁、编码假设、`agent_coupling`；按 `target_platform` / `target_agent` 豁免。
- `doc-llm`：自由散文语义漂移检测（由 agent 直接接手、无需外部 LLM）——由 agent 用自身能力比对 SKILL.md 与代码事实；全量检测显式问询，非交互环境记 INFO `doc_llm_skipped`。
- `examples`（**检查器 #9**）：文档示例静态校验——校验任意技能文档里写出的命令示例是否站得住脚（脚本引用是否存在 / 传给脚本的参数是否声明 / 示例调用的外部 CLI 是否声明 / 是否含危险或不可逆命令）。默认 `static`（纯静态、零执行 / 零网络 / 零 token）；`--examples-mode run` 方在受限沙箱试运行带 `expected` 标注的示例（仅白名单解释器 + 技能内脚本 + 超时保护，绝不执行任意 shell）。

各检查器的完整项、判定口径与误报抑制细节见 `references/checkers.md`。

脚本只能枚举差异、不能判定对错的，以及完全查不出、必须 AI 读代码判断的语义项（如描述是否仍成立、提示是否误导、跨文件一致性），详见 `references/checkers.md`。**不要只用脚本结论就下判断**——扫描报告是线索，不是裁决。

### 能力边界速查（一句话）

为减少「多处查阅 checkers.md 才看清边界」，这里把关键边界浓缩成一张表，细节仍以 `references/checkers.md` 为准：

| 你能指望脚本可靠判定的 | 脚本只能给线索、必须你/AI 复核的 | 脚本根本查不出的 |
|---|---|---|
| 死引用（`DEAD_PATH`/`DEAD_FLAG`/失效退出码）、frontmatter 缺字段、语法错误、未声明外部 CLI、硬编码密钥/路径穿越、`portability` 各项 OS 级破损、死代码、示例引用的脚本/参数/外部 CLI 是否声明与是否含危险命令（EXAMPLE_*） | 描述是否仍成立、提示是否误导、跨文件语义一致性、文档示例是否过时、某 `WARN` 是否为有意为之 | 业务正确性、用户体验、是否「应该」有这个功能、安全设计的合理性（如：审计策略该用静态规则还是 LLM、密钥是否明文落盘） |
| 报告给出 `category`（机器码）+ `category_cn`（中文标签）+ `suggestion`（修复建议），每条发现自解释 | `WARN`/`INFO` 通常需结合上下文，勿直接当错误处置 | — |

> 铁律：**报告是线索，不是裁决。**（新手误区、避坑要点与常见问答见「常见问题与避坑」）

## 设计原则（核心约束）

> **默认模式零依赖，但绝不替用户决定。**

这是本技能的顶层设计原则，所有「可选 / 增强 / 外部依赖」能力（doc-llm 语义检测、deadcode 精度选择）都必须受此约束：

- **默认即零依赖**：任何可选能力的默认路径必须是纯脚本、无外部依赖、不联网、零额外成本（token）。开箱即用不应要求用户安装任何东西或配置任何密钥。
- **绝不替用户决定**：凡涉及「是否启用增强 / 外部依赖能力」的取舍，必须显式交还用户决策——交互终端呈现可选项（含代价）并等待选择，超时 / 非交互则安全回退默认模式，而**绝不**为省事自动替用户开启联网或消耗资源。
- **透明兜底**：无法询问（自动化 / Agent / 非 TTY）时，宁可在报告中显著标注「已跳过 / 已降级」（INFO / WARN），也不静默代决。

该原则已在 doc-llm（`--doc-llm-mode` 默认问询、菜单含代价、超时回退默认）与 deadcode（`--deadcode-mode ask` 交互询问精度、非 TTY 显著告警）中落地。

> **跨平台、跨 Agent 适配，不写死宿主假设。**

本技能不假设自己只跑在 WorkBuddy 上、只装在某个固定用户名 / 盘符的目录。该原则统领路径解析与跨 Agent 分发：

- **路径零宿主硬编码**：一律经 `os.path.expanduser("~")` / 环境变量解析，禁止写死随账号或盘符变化的用户主目录绝对路径（例如 Windows 用户目录下「用户名」起手的写法）；换机器 / 换用户名 / 自定义数据目录都不应破。
- **用户侧审计本就 agent 无关**：`--skill <目录>` 收任意路径、`--all` 扫宿主 skills 根、`--source` 支持 github / skillhub / url；跨 Agent 分发以 `target_agent` 字段声明，portability 据此豁免耦合项（`agent_coupling`）。

## 快速开始

三条命令覆盖 90% 场景：

```sh
# 1) 体检一个技能（doc 一致性常驻默认开，审计前自动备份 SKILL.md）
python scripts/audit_docs.py --skill ~/.workbuddy/skills/<技能名> --backup

# 2) 全套体检（结构/安全/可运行/依赖/死代码；deadcode 已装 vulture 则自动高精度，否则运行前询问精度）
python scripts/audit_docs.py --skill <目录> --all-checks

# 3) 先预览再审计（看清楚会扫哪些检查器、哪些文件，退出码 0）
python scripts/audit_docs.py --skill <目录> --all-checks --preview
```

想做某件事，直接用对应命令要点：

| 我的诉求 | 命令要点 |
|---|---|
| 只查文档与代码对不对得上 | `--backup`（doc 常驻默认开） |
| 一次性全身体检 | `--all-checks` |
| CI 门禁，连 WARN 也阻断合并 | `--all-checks --strict` |
| 批量体检所有已装技能 | `--all --all-checks` |
| 先看看会扫什么再决定 | `--preview` |
| 只查某一类（如安全红线） | `--check security` |
| 审计 GitHub 仓库里的技能 | `--source github --ref owner/repo`（可 `@分支`） |
| 审计 SkillHub 集市里的技能 | `--source skillhub --ref <slug>` |
| 审计任意 URL 上的技能 | `--source url --ref <https 地址>`（指向 SKILL.md 文件或所在目录；支持 github.com blob 链接自动转 raw） |
| 只查跨平台可移植性 | `--check portability` |
| 声明目标平台以豁免对应项 | SKILL.md 写 `target_platform: windows`（或 linux/macos/列表） |
| 标注目标 Agent 分发范围 | SKILL.md 写 `target_agent: workbuddy`（或 claude-code/cross-agent/自由列表）；耦合提示不再抑制，跨 Agent 声明未含 workbuddy 升 WARN |
| 生成跨格式可移植性矩阵（X→Y 字段损失） | `--report portability-matrix`（仅做报告，不改写；输出源格式到各目标格式的 P/D/L 矩阵） |
| 生成跨格式**转译报告**（只读预览·不落盘） | `--report translate --target <fmt>`（仅出报告不生成文件；输出 frontmatter 字段映射表 + 目标 SKILL.md 脚手架预览；支持 `--verify` 做内存往返保真；目标格式 `workbuddy`/`agentskills`/`claude-code`/`cursor-plugin`/`generic`，与源格式双向；其中 `agentskills`/`cursor-plugin` 即 Agent Skills 开放标准，一次转译全生态通用） |
| 生成生态级健康度汇总（批量审计时） | `--report health`（仅做报告，不改写；汇总各技能 ERROR/WARN/INFO 与供应链安全风险技能数；`--json` 多技能时自动附带 `health_summary`） |

其余参数（`--json` / `--timeout` / `--max-file-size` / `--deadcode-mode` / `--backup-limit` / `--source` / `--ref` / `--keep-temp`）与完整检查项口径见下方「用法」与 `references/checkers.md`。

## 5 分钟上手（极简路径）

只想最快跑起来，只需记住一条命令：

```sh
python scripts/audit_docs.py --skill <技能目录> --all-checks
```

它会自动备份 `SKILL.md`、跑完全部检查器、输出带中文标签的报告。`deadcode` 若环境已装 `vulture` 会自动用高精度模式，没装则自动降级为零依赖 `ast`（**不需要额外安装任何东西就能跑**，见下）。其余 90% 场景用「快速开始」那张表查对应命令要点即可，无需通读全文。**注意**：上一段的「自动降级」仅在人类交互终端成立；**Agent 经管道执行时不会真正询问用户，须按上方『Agent 执行约定』显式传 `--deadcode-mode`**，勿依赖静默降级。

> 三个最常见疑问（要装 vulture 吗 / 远程审计要装 git 吗 / WARN 要不要全改）见「常见问题与避坑」·速答三问。

## 多平台来源（--source github / skillhub / url）

默认 `--source local`：用 `--skill <目录>` 或 `--all`（扫 `~/.workbuddy/skills`）审计本机技能。
新增 `--source` 可把**远程仓库 / 集市技能**拉到临时目录后照常审计，`analyze_skill` 核心逻辑零改动。

> **本地审计完全离线、零外部依赖**：`--source local`（默认）与 `--all` 只读写本机目录，**不联网、不需要任何外部 CLI 或令牌**。仅 `--source github`（需 `git`）、`--source skillhub`（需 `skillhub` CLI）才要求对应命令在 PATH 中；而 `--source url` 用标准库 `urllib` 直抓，**同样零外部 CLI**（仅需 HTTPS 网络可达、对目标 OS 透明）。切勿因「远程审计」条目误以为本工具整体依赖联网——本地体检是纯离线脚本。

> **审计远端技能优先用 `--source url`**（零外部 CLI、绕开 `git clone` 不通的网络限制；常见误区见「常见问题与避坑」·新手误区）。

| 来源 | 说明 | --ref 取值 |
|---|---|---|
| `local`（默认） | 本机目录 / 已装技能 | 无需（用 `--skill` / `--all`） |
| `github` | `git clone --depth 1` 到临时目录后审计；支持仓库内含嵌套子目录（如 `src/` 下放 SKILL.md）/多技能 | `owner/repo` 或 https 地址，可加 `@分支` |
| `skillhub` | 经 `skillhub install <slug> --dir` 拉取集市技能 | 技能 slug |
| `url` | 用标准库 `urllib` 直接抓取 SKILL.md 文本到临时目录后审计；零外部依赖、对 OS 透明；`github.com` blob 链接自动转 `raw.githubusercontent.com` | SKILL.md 的 https 地址（可指向文件或所在目录） |

审计结束后临时目录默认自动清理；加 `--keep-temp` 可保留并打印路径，便于排查。

## Agent 执行约定（deadcode 精度模式 / doc-llm 语义检测必须显式决策）

本技能的 `deadcode` 默认精度模式为 `ask`，其「询问」是基于**人类交互终端（TTY）**的 `input()` 现场提示。但当你（Agent）替用户执行 `--all-checks` 时，脚本是通过管道运行的（`stdin` 非 TTY），`input()` 既无法显示也无法接收用户输入，于是脚本只能**静默降级为零依赖 `ast` 模式**——用户的精度选择权被悄悄吞掉，与设计初衷（精度应由用户决定）相悖。实测表现即「Agent 跑全量检测时 deadcode 只跑 AST、跳过询问」。

因此，**Agent 在运行任何包含 deadcode 的全量审计前，必须显式决策并把结果以 `--deadcode-mode` 传入，绝不依赖 `ask` 默认**。标准动作如下：

1. **探测 vulture 是否已安装**（零副作用）：
   ```sh
   python -c "import vulture" 2>/dev/null && echo HAVE || echo NONE
   ```
2. **已装** → 直接以高精度运行：
   ```sh
   python scripts/audit_docs.py --skill <目录> --all-checks --deadcode-mode vulture
   ```
3. **未装** → **主动用 AskUserQuestion 询问用户三选一**（不要替用户默认 ast），再把选择显式传入：
   - 「安装 vulture 后走高精度」：先 `pip install vulture`，再 `--deadcode-mode vulture`；
   - 「直接零依赖 AST 跑（精度略低）」：`--deadcode-mode ast`；
   - 「本次跳过 deadcode」：`--deadcode-mode skip`。

### doc-llm 语义检测同理（由 agent 直接接手，无需外部 LLM）

`--all-checks` 已包含 `doc-llm`，默认按 `ask` 处理。但**「ask」的载体因调用方式而异，且 Agent 场景必须用原生交互**：

- **真实交互终端（tty 且有用户在场）**：CLI 直接弹 stdin 菜单询问，30 秒超时默认不启用。
- **Agent 调用（本技能的主场景）**：Agent 沙箱没有用户能键入的终端，CLI 的 stdin 菜单虽会打印却**收不到输入**（实测：打印后空等约 30s 超时回退默认）。因此 **Agent 必须改用其原生的 `AskUserQuestion` 工具把 doc-llm 选择权抛给用户**，再按选择显式传参——这是「通过 agent 调用也要弹出菜单让用户选择」的正确实现，也契合「绝不替用户决定」红线。
- **管道/CI（stdin 非 tty）**：弹不出菜单，记 INFO `doc_llm_skipped`（不联网、不消耗 token，INFO 非 WARN，不影响「全量检测 WARN 0」）。

> 语义漂移检测由 agent 直接接手、不再依赖外部 LLM（会占用 agent 自身推理 token，但不向外部服务付费）；「预览」选项已移除。脚本职责收窄为：准备材料 → 落盘 dossier → 打印 `[doc-llm] AGENT_TAKEOVER: <path>` 哨兵 → 由 agent 读取判定。完整机制见 `references/checkers.md`。

**Agent 调用时的标准动作（必须执行，不得省略询问）：**
1. 运行 `--all-checks`（或 `--check doc-llm`）**前**，先调用 `AskUserQuestion` 向用户呈现 doc 检查器的语义检测模式。**使用以下统一措辞模板**（经用户改进，问题与选项文本必须原样使用，便于理解）：
   - **question**：`运行doc检查器（默认常驻）时，你希望采用哪种模式？`
   - **header**：`doc 检查`（≤12 字符）
   - **选项 1** label `默认模式（静态脚本检查，零依赖）` / desc `推荐 · 不调用 LLM · 0 token · 离线`
   - **选项 2** label `启用语义漂移检查（agent介入，消耗额外token）` / desc `agent 读取 SKILL.md 与代码事实清单，用自身能力比对；会占用 agent 推理 token（输入侧为主），但不依赖外部 LLM、无需付费`
2. 按用户选择显式传参后再运行：默认→`--doc-llm-mode off`；agent 接手→`--doc-llm-mode agent`。**此举既不触发 CLI 的 30s 空等，又把决定权交还用户。**
3. **红线**：Agent 不得跳过询问直接默认/跳过（那才是「替用户决定」）；也不得在用户未选「agent 接手」时擅自宣布已做语义检测。用户在指令中已明确指定模式时，可免问直接照办。
4. **仅当明确处于无人值守的 CI / 自动化链路**时，才允许不经询问直接 `--deadcode-mode ast`（此时静默降级即预期行为）。

一句话：**Agent 场景下的 deadcode 精度，永远由「Agent 显式传参」决定，而不是脚本的 `ask` 默认。** 这样精度选择权始终在用户手里，符合设计初衷。

## 流程

1. **备份并扫描**
   ```sh
   python scripts/audit_docs.py --skill ~/.workbuddy/skills/<技能名> --backup
   ```
   脚本会在审计前把 `SKILL.md` 备份为 `SKILL.md.bak.<时间戳>`。为防频繁迭代产生过多备份，同一 `SKILL.md` 的 `.bak.*` 文件**最多保留 3 个**——生成新备份前会先删除最旧者。可用 `--backup-limit N` 调整上限（如 `--backup-limit 5`）。

2. **AI 复核**：阅读报告后，针对每一条核对源码。重点甄别三类：
   - A 类里是否有「有意为之」的条目（例如文档标注「已弃用」的退出码，属正常）
   - B 类里哪些其实是用户可感知行为、应当补写
   - 脚本查不出的语义项：把文档逐段与代码行为对照，确认描述仍然成立

3. **直接修改**：本技能按「全自动改 + 备份」模式运行——判断清楚后直接编辑 `SKILL.md`，无需停下来等待确认。

4. **汇总**：列出改了什么、依据是什么，并告知备份位置与回滚方法。

## 修改原则

- 修改文档时的五条避坑原则（只改文档不改代码、保留「已弃用」标注、存疑标注、先读源码复核、语义化递增版本号）已归集到「常见问题与避坑」·避坑要点。

## 用法

```sh
# doc 一致性（常驻默认）
python scripts/audit_docs.py --skill ~/.workbuddy/skills/workbuddy-checkin --backup

# 启用插件式检查器（doc 常驻 + 指定项，可重复 --check）
python scripts/audit_docs.py --skill <目录> --check structure --check security

# 全部检查器（doc + structure + security + runtime + deps + deadcode；deadcode 已装 vulture 则自动高精度，否则运行前询问精度模式）
python scripts/audit_docs.py --skill <目录> --all-checks

# 仅依赖/平台声明检查
python scripts/audit_docs.py --skill <目录> --check deps

# 备份上限可调；批量审计；JSON 机读（同时仍打印可读报告）
python scripts/audit_docs.py --skill <目录> --backup --backup-limit 5
python scripts/audit_docs.py --all --all-checks
python scripts/audit_docs.py --skill <目录> --all-checks --json
# CI 门禁：WARN 也计入退出码（默认仅 ERROR 计入）
python scripts/audit_docs.py --skill <目录> --all-checks --strict
# 整体超时保护（秒）；超时优雅终止，不再卡死
python scripts/audit_docs.py --skill <目录> --all-checks --timeout 60
# 超大文件跳过阈值（字节）；超过则跳过并报告，避免拖慢
python scripts/audit_docs.py --skill <目录> --all-checks --max-file-size 2000000
# deadcode 精度模式：ask(已装 vulture 则自动高精度,不询问) / 显式 vulture 高精度 / ast 零依赖 / skip 跳过；Agent/CI 用 --deadcode-mode 跳过交互询问
python scripts/audit_docs.py --skill <目录> --all-checks --deadcode-mode vulture
# 先预览将运行哪些检查器、将扫描哪些文件（不产出发现，退出码 0）
python scripts/audit_docs.py --skill <目录> --all-checks --preview

# 多平台来源：克隆 GitHub 仓库并审计（可 @分支；仓库内 SKILL.md 在 src/ 也能自动定位）
python scripts/audit_docs.py --source github --ref owner/repo --all-checks
python scripts/audit_docs.py --source github --ref https://github.com/owner/repo @dev --check structure
# 多平台来源：经 skillhub CLI 拉取集市技能并审计
python scripts/audit_docs.py --source skillhub --ref <slug> --all-checks
# 保留克隆/安装的临时目录供排查
python scripts/audit_docs.py --source github --ref owner/repo --keep-temp
# 泛化源：直接审计任意 URL 上的 SKILL.md（零外部依赖，github blob 链接自动转 raw）
python scripts/audit_docs.py --source url --ref https://raw.githubusercontent.com/owner/repo/main/SKILL.md --all-checks
python scripts/audit_docs.py --source url --ref https://github.com/owner/repo/blob/main/SKILL.md
```

退出码：`0` 未发现 ERROR 级问题（--strict 下还需无 WARN）；`1` 发现 ERROR 级问题（或 --strict 下存在 WARN）；`2` 参数或路径错误；`130` 审计被中断（超时或 Ctrl+C），优雅退出、不抛堆栈。报告同时提供人类可读分组与 `--json` 机读（每条含 `checker/severity/category/category_cn/message/file/line/suggestion`）；`category` 为稳定机器标识符（用于机读与跨版本比对），`category_cn` 为中文可读标签（用于人类报告，使每条发现自解释）。

## 回滚

```sh
cp SKILL.md.bak.<时间戳> SKILL.md
```

## 触发与实测

本技能在以下真实对话口吻下应被准确触发（正例），以及在相似但不同诉求下不应触发（near-miss 反例）。

**正例（应触发）**
- 「帮我体检一下这个技能的文档，看看版本迭代后有没有漂移」→ 触发 `doc` 一致性检查。
- 「审计一下这个技能的安全红线，有没有硬编码密钥或路径穿越」→ 触发 `security` 检查器（含上下文感知的 `path_traversal`，自动排除 `https://.../v2` 这类文档 URL 与合法资源上溯，不再误报）。
- 「我想批量检查一下所有已安装技能的依赖和平台声明」→ 触发 `--all --all-checks`（含 `deps`）。

**Near-miss 反例（不应触发）**
- 「帮我优化这段代码的性能」→ 属通用编码任务，非文档/静态体检，本技能不介入。
- 「把这个技能打包成 Docker 镜像」→ 属部署范畴，超出静态体检边界，不触发。

> 触发判据：用户意图围绕「文档与代码一致性 / 结构 / 安全红线 / 可运行性 / 依赖平台」的静态审计时使用；纯运行期、动态行为或部署类诉求不在范围内。

**误报自纠错能力**：`security` 检查器对所有正则统一采用上下文感知过滤，自动排除注释、文档 URL、自引用资源上溯，避免上下文盲误报；**该能力同样覆盖 `structure`/`portability`**——`hardcoded_path` 已跳过表格/引用块/示例性描述行，`encoding_sep` 已排除 `urlopen`/`io.open` 等非文件 `open`（如 `--source url` 的 `urllib.request.urlopen` 不再误报），`hardcoded_endpoint` 已对 `raw.githubusercontent.com` 等 url 源规范主机白名单放行。完整机制见 `references/checkers.md`。

## examples 检查器：文档示例静态校验（检查器 #9）

校验**任意技能**文档里写出的命令示例是否站得住脚——避免「文档教用户的命令一跑就挂」这类漂移。默认**纯静态**（零执行 / 零网络 / 零 token），执行为需显式授权的可选能力。

- **三档模式（`--examples-mode`）**：`static`（默认，纯静态解析）/ `ask`（交互询问是否允许沙箱试运行，30 秒超时或本地非交互一律回退 static 并 INFO 标注降级）/ `run`（受限沙箱试运行）/ `off`（跳过）。
- **默认静态档查什么**：① 示例命令引用的脚本文件是否存在（`EXAMPLE_TARGET_MISSING`，仅核验 `.py/.js/.mjs/.ts/.sh/.ps1` 这类脚本扩展名，仓库引用 / 安装路径 / 输出文件一律跳过，避免误报）；② 传给脚本的参数是否在脚本中声明（`EXAMPLE_FLAG_UNKNOWN` WARN，仅 SKILL.md）；③ 示例调用的外部 CLI 是否在文档声明依赖（`EXAMPLE_EXT_CMD` INFO）；④ 是否含危险 / 不可逆命令（`EXAMPLE_DANGEROUS` ERROR/WARN）。纯文档快照（未取到代码）时退为 INFO，绝不把「没下载到」误判成「文件不存在」。
- **安全红线（不可放宽）**：即便 `run` 模式也**绝不执行文档里的任意 shell**。只执行同时满足全部条件的命令：白名单解释器（python/python3/node）+ 无 shell 元字符（`; | & < > $ \` ( )` 等）+ 目标脚本在技能目录内 + 扩展名白名单 + 该示例块由作者显式标注了期望 + 受超时与条数上限约束。不满足即跳过并 INFO 说明，绝不「尽力执行」。
- **示例标注语法（作者可选，供 run 模式比对）**：

```bash {example expected-exit=0 expected-stdout="OK"}
python scripts/audit_docs.py --check doc
```

支持 `expected-exit` / `expected-stdout` / `expected-stderr`。未标注的示例任何模式都只做静态检查、不执行。

> 与 `self_validate.py` 的区别：本检查器是审计**目标技能**的插件式检查器（进 `CHECKERS` 与 `--all-checks`）；`self_validate.py` 是维护者自校工具，只校验本技能自身。两者不同类。

## 常见问题与避坑

### 本节导航（速查锚点）
- [速答三问](#速答三问30-秒)：要装 vulture 吗 / 远程审计要装 git 吗 / WARN 要不要全改
- [新手误区](#新手误区)：把线索当裁决 · 远程必用 github · 报漏洞就是真漏洞 · 已弃用即错 · 没装 vulture 用不了
- [避坑要点](#避坑要点)：DEAD_PATH 是运行产物 · WARN/INFO 非错误 · 改文档五原则 · 缩小审计范围 · 默认零依赖 · doc-llm 语义检测

> **铁律：报告是线索，不是裁决。** 任何改动前先读源码核对，尤其 `WARN`/`INFO` 与语义项。脚本只枚举差异、不判定对错；语义项（描述是否仍成立、提示是否误导、跨文件一致性）必须 AI 读代码判断。

### 速答三问（30 秒）

- **要装 vulture 吗？** 不用手动装。显式 `--deadcode-mode vulture` 但环境缺库时，脚本会先自动 `pip install vulture`（装好即用高精度）；装不上才降级 `ast` 并标注精度降级。其它情形（ast/skip 或 ask 的自动回退）不触发安装，缺库即零依赖 `ast`，其它检查器完全不受影响。
- **审计远程技能要装 git / skillhub 吗？** 不用。用 `--source url --ref <SKILL.md 的 https 地址>` 即可，标准库直抓、零外部 CLI。
- **报告里一堆 WARN/INFO 要不要全改？** 不要。只有 `ERROR` 默认计入退出码；`WARN`/`INFO` 是线索，需你/AI 读源码复核后再决定。

### 新手误区

- **误区一：把线索当裁决。** 只有 `ERROR` 默认计入退出码；`WARN`/`INFO` 是「这里可能有问题，请你/AI 读源码确认」的提示。例如 `agent_coupling` 的 INFO 是跨 Agent 咨询、非缺陷；`hardcoded_path` 的 WARN 若出现在表格/引用块里多半是示例误报（已做上下文感知过滤）。**先读源码，再决定改不改。**
- **误区二：以为远程审计必须 `--source github`。** 其实优先用 `--source url --ref <SKILL.md 的 https 地址>` 即可——标准库直抓、零外部 CLI、绕开 `git clone`，绝大多数远端技能都能审计。仅在需要完整克隆仓库（含嵌套子目录/多技能）时才用 `--source github` / `--source skillhub`。
- **误区三：报了路径穿越 / 硬编码密钥就是真漏洞。** 多半是上下文盲误报。`security` 检查器对所有正则统一做上下文感知过滤，自动排除注释行、含 `://` 的文档 URL、含 `__file__`/`dirname`/`.asar` 的合法资源上溯；真实漏洞（外部可控字符串拼入落盘路径、文档里真写死密钥）才会保留。
- **误区四：文档列了退出码但代码从不返回，就是文档错了。** 未必。若标注「已弃用」，那是刻意的向后兼容说明，保留不要删。
- **误区五：没装 vulture 就跑不了死代码检测 / 整工具用不了。** 不是。没装时 `deadcode` 仍可用：显式 `--deadcode-mode vulture` 会先尝试自动安装；装不上或选 `ast`/`skip` 才以零依赖 `ast` 运行（仅死代码精度略低），其余检查器完全不受影响。

### 避坑要点

- **`DEAD_PATH` 但路径确实在用？** 很可能指向「运行期生成的产物」（如技能在目标项目创建 `.learnings/`、脚本在临时目录生成 state），本技能目录下不存在却非漂移。判定前留意引用处是否含「生成 / 创建 / 写入」含义。详见 `references/checkers.md` 的「判定提示」。
- **`WARN`/`INFO` 不是错误**：`structure` 的 `name_mismatch` 是提示性项，`portability` 的 `agent_coupling` INFO 是跨 *Agent* 咨询、**非** OS 级破损，均属正常产物，勿直接当错误处置。
- **修改文档的五条原则**：① 只改文档，不改代码（代码问题整理出来交用户决策）；② 保留「已弃用」标注（不因「代码从不返回」就删）；③ 存疑时标注「待确认」而非臆断；④ 先读源码复核再决定；⑤ 版本号按语义化递增（修正文档表述属补丁级，修复功能缺陷属小版本级）。
- **缩小审计范围**：用 `--check` 按需启用（如 `--check security`），或 `--all-checks` 全开；`--strict` 让 `WARN` 也计入退出码，适合 CI 门禁。
- **设计原则：默认零依赖，绝不替用户决定**：本技能所有可选 / 增强能力默认纯脚本、不联网、零 token；涉及是否启用外部依赖能力的取舍必须显式交还用户（菜单含代价、超时回退默认），自动化环境宁可显著标注跳过也不静默代决。这条原则统领 doc-llm 与 deadcode。
- **`doc-llm` 已纳入全量集，语义检测由 agent 直接接手（会占用 agent 推理 token，但不向外部 LLM 付费）**：`--all-checks` 会跑 `doc-llm` 并**显式问询**是否启用语义检测（全量检测理应包含语义漂移问询）。默认按 `ask`：交互终端弹菜单、30 秒超时默认不启用；非交互环境无法询问则跳过并记 INFO `doc_llm_skipped`。**不依赖任何外部 LLM 端点**——选「agent 接手」时脚本把 SKILL.md 全文 + 代码事实清单写成 dossier 并打印 `[doc-llm] AGENT_TAKEOVER: <path>` 哨兵，由 agent 读取后用自身能力完成语义比对；此过程会占用 agent 自身推理 token（输入侧为主、输出极少），但不向任何外部 LLM 服务付费。完全不想参加可显式 `--doc-llm-mode off`。调用流程刻意对齐 `deadcode` 检查器（`--doc-llm-mode` 与 `--deadcode-mode` 同构）。

## 完整运行示例（真实输出 + 解读）

对某个技能目录运行全套体检时（下方输出取自对本技能自身的审计；当审计目标目录名与技能名不一致时，会额外出现 1 个 `name_mismatch` WARN，审计正常部署的技能则无此项）：

```sh
python scripts/audit_docs.py --skill src --all-checks
```

真实输出（节选，每条发现均带中文标签与机器码，自解释）：

```
  [doc]       ERROR 0 / WARN 0 / INFO 1
  [structure] ERROR 0 / WARN 1 / INFO 0
  [security] ERROR 0 / WARN 0 / INFO 0
  [runtime]   ERROR 0 / WARN 0 / INFO 1
  [deps]      ERROR 0 / WARN 0 / INFO 0
  [deadcode]  ERROR 0 / WARN 0 / INFO 0
  [portability] ERROR 0 / WARN 0 / INFO 18

  本技能汇总：ERROR 0 / WARN 1 / INFO 20    通过
```

**如何解读（关键）**
- **`通过` = 未发现 ERROR 级问题**，退出码 `0`。只有 `ERROR` 默认计入退出码；`--strict` 才把 `WARN` 也算失败。
- `WARN`/`INFO` 是否要处理、`portability` 的 `agent_coupling` INFO 为何可忽略，见「常见问题与避坑」·避坑要点。
- 每条发现的机器码（`category`）稳定、可用于跨版本比对；`--json` 输出供 CI 消费（每条含 `checker/severity/category/category_cn/message/file/line/suggestion`）。

> 练习：把上面这条命令对你的一个技能跑一遍，对照「能力边界速查」表判断每条 WARN/INFO 是否真要处理。绝大多数技能首跑都会有几个 INFO，属正常。

## 错误码对照表

每条发现都带一个机器标识符 `category`（稳定、用于机读与跨版本比对）与一个中文标签 `category_cn`（用于人类报告）。下表为全部 `category` 的权威对照；各检查项完整判定口径与误报抑制机制见 `references/checkers.md`。

### doc（文档一致性，常驻默认开）

| category | 中文含义 | 默认级别 |
|---|---|---|
| `DEAD_PATH` | 死路径（文档引用文件已不存在） | ERROR |
| `EXTERNAL_REF` | 外部裸文件名引用（需人工确认） | INFO |
| `DEAD_FLAG` | 失效命令行参数（代码无实现） | ERROR |
| `EXIT_DOC_ONLY` | 文档独有退出码（代码未返回） | ERROR |
| `EXIT_CODE_ONLY` | 代码独有退出码（文档未列） | ERROR |
| `UNKNOWN_IDENT` | 未知标识符（代码找不到） | WARN |
| `VERSION_MISSING` | 缺少版本声明 | ERROR |
| `B_STATUS` | 运行状态枚举（供 AI 复核） | INFO |
| `B_CONFIG` | 配置项枚举（供 AI 复核） | INFO |
| `DOC_ENUM_DRIFT` | 文档枚举/集合与代码不一致（如 deadcode 模式列表） | WARN |
| `DOC_COUNT_DRIFT` | 文档数量声明与代码不一致（如「N 个检查器」） | WARN |
| `DOC_CAPABILITY_DRIFT` | 文档声称的能力在代码中无对应实现 | WARN |
| `DOC_CAPABILITY_MISSING` | 代码声明的能力文档未提及（正向覆盖缺口） | WARN |
| `DOC_LLM_DRIFT` | 文档/代码语义漂移（agent 判定，doc-llm） | WARN |
| `doc_llm_agent_handoff` | 语义漂移检测已转交 agent 接手（dossier 已写入，agent 将自行比对） | INFO |
| `doc_llm_skipped` | 全量检测中语义漂移检测跳过（非交互环境，未调用任何 LLM） | INFO |

> 结构化声明 ↔ 代码事实交叉校验（`DOC_ENUM_DRIFT` / `DOC_COUNT_DRIFT` / `DOC_CAPABILITY_DRIFT` / `DOC_CAPABILITY_MISSING`，均 `WARN` 仅作线索）；自由散文语义漂移由独立的 `doc-llm` 检查器覆盖（由 agent 直接接手、不再调外部 LLM）。完整机制见 `references/checkers.md`。

### structure（结构体检 + 元信息）

| category | 中文含义 | 默认级别 |
|---|---|---|
| `name_mismatch` | 名称不一致（frontmatter name ≠ 目录名） | WARN |
| `version_missing` | 版本缺失 | ERROR |
| `name_missing` | 名称缺失 | ERROR |
| `license_missing` | 许可证缺失 | WARN |
| `desc_length` | 描述长度异常（应 20–1024 字符） | WARN |
| `desc_four` | 描述四要素不全 | INFO |
| `desc_missing` | 描述缺失 | ERROR |
| `h1_name_mismatch` | 标题与名称不一致 | WARN |
| `no_frontmatter` | 缺少 frontmatter | WARN |
| `too_long` | 文档过长（超 500 行） | WARN |
| `broken_ref` | 加载式引用失效（references/、scripts/ 目标不存在） | ERROR |
| `hardcoded_path` | 硬编码绝对路径 | WARN |
| `todo_marker` | 待办标记（TODO/FIXME） | WARN |
| `placeholder` | 占位/历史文本 | INFO |
| `oversize_doc` | 文档过大（超过扫描阈值） | WARN |
| `oversize_file` | 文件过大已跳过扫描 | WARN |

### security（安全红线静态子集）

| category | 中文含义 | 默认级别 |
|---|---|---|
| `hardcoded_secret` | 疑似硬编码密钥/凭据 | ERROR |
| `obfuscation` | 疑似混淆编码 | WARN |
| `dynamic_exec` | 动态执行（eval/exec 外部内容） | WARN |
| `hardcoded_endpoint` | 硬编码远端端点（供应链风险，需代码上下文才报告，避免文档链接误报） | WARN |
| `dynamic_import` | 动态导入（importlib/__import__ 等反射式模块加载） | WARN |
| `path_traversal` | 路径穿越（`../`，上下文感知过滤） | ERROR |
| `destructive_wildcard` | 危险通配删除（`rm -rf *`） | ERROR |
| `injection_phrasing` | 疑似提示词注入句式 | INFO |
| `secret_in_doc` | 文档含疑似密钥（需确认） | WARN |

### runtime（脚本可运行性）

| category | 中文含义 | 默认级别 |
|---|---|---|
| `py_syntax` | Python 语法错误 | ERROR |
| `py_check_fail` | 语法校验失败 | WARN |
| `script_ref_missing` | 脚本引用缺失 | ERROR |
| `capability` | 能力预检（静态列举，不执行） | INFO |

### deps（依赖与平台声明）

| category | 中文含义 | 默认级别 |
|---|---|---|
| `undeclared_cli` | 未声明外部 CLI 调用 | WARN |
| `platform_undeclared` | 未声明运行平台（含 Windows 专属 API） | INFO |

> **何时显式声明 `target_platform`（deps 指引）**：`deps` 仅发 `platform_undeclared` INFO（非阻断），但正确声明可消除误报、提升 `portability` 审计精度。判定：① 技能**只**能在某一 OS 上运行（依赖 `winreg`/`ctypes.windll` 等 Windows 专属 API）→ 显式 `target_platform: windows`（`linux`/`macos` 同理）；② 调用平台专属 shell/命令是设计内行为 → 同样声明豁免该项；③ 跨平台通用（目标 = 全平台）→ **不写** `target_platform`（默认即跨平台全检），切勿为消 WARN 而谎报平台。声明后 `portability` 仅抑制与 `breaks_on` **无交集**的 OS 项（详见下方「豁免规则」），不会掩盖真实跨平台破损。

### deadcode（死代码检测，运行前按 --deadcode-mode 选精度）

| category | 中文含义 | 默认级别 |
|---|---|---|
| `unused_def` | 未使用的定义（全技能范围都未被引用才报，含跨文件引用感知） | WARN |
| `unused_import` | 未使用的导入 | INFO |
| `unreachable` | 不可达代码（return/raise 之后紧跟的无条件语句） | WARN |
| `orphan_asset` | 孤立资源文件（scripts/ 或 references/ 中从未被引用/加载） | WARN |
| `vulture` | 高精度死代码（可选，仅 `--deadcode-mode vulture` 且已装 vulture 时产出） | WARN |

> 死代码误报抑制（详见 `references/checkers.md`）：字符串键/装饰器/入口启发、跨文件引用感知、`# keep` 白名单；`orphan_asset` 仅当文件名或相对路径未出现在任何文档/代码、也未被其他 `.py` 以模块名 import 时才报（只可能漏报、不会误标孤儿）。

### portability（跨平台可移植性，按 target_platform 豁免）

> `portability` 先由 `detect_format()` 推断技能格式并构建统一 `SkillModel`，再按 `target_platform` / `target_agent` 豁免；跨格式矩阵 / 转译机制见 `references/checkers.md`。

| category | 中文含义 | 默认级别 |
|---|---|---|
| `hardcoded_abs_path` | 硬编码绝对路径（`C:\Users\...` / `/Users/` / `/home/`） | WARN |
| `cwd_dependence` | 启动目录依赖（`os.getcwd` / `Path.cwd` / `process.cwd`），从别的目录启动找不到资源 | WARN |
| `platform_shell` | 平台专属 shell/命令（`cmd.exe`/`powershell`/`rm -rf`/`ls` 等，仅看子进程/系统调用语义的行） | WARN |
| `interpreter_lock` | 解释器/运行时锁（裸 `python` 非 `python3`、Windows `py` 启动器） | WARN |
| `encoding_sep` | 编码/路径分隔符假设（`open()` 未指定 `encoding`，Windows 文本模式默认编码非 UTF-8 易解码失败） | WARN |
| `agent_coupling` | Agent 平台耦合（硬编码 `.workbuddy` / `allowed-tools` 约定，跨 Agent 分发需抽象） | INFO/WARN |
| `lossy_port` | 跨格式可移植性损失（声明跨 Agent 目标却含目标端无对应/需转译的字段；`lost` 升 WARN，`degraded` 仅 INFO） | INFO/WARN |

> `--report portability-matrix` 生成「源格式 → 各目标格式」的 P/D/L 矩阵；跨格式转译（`--report translate`）与 `agentskills` 枢纽机制见 `references/checkers.md`。

> `--report translate`（只读预览·不落盘）做跨格式转译方案；`agentskills` 为全生态通用枢纽（一次转译即被 40+ 工具消费）。完整机制见 `references/checkers.md`。

> 豁免规则（核心）：每条发现的 `breaks_on` 是「它会在哪些 OS 上崩」。声明平台与 `breaks_on` **有交集才报**，无交集才抑制。例：`target_platform: windows` 会抑制 `powershell`/`C:\` 这类 Windows 专属项的误报，但**保留** `rm -rf`/`/Users/` 这种在 Windows 目标上真会崩的项。`target_platform` 不写 = 跨平台（全平台）→ 始终全检。`agent_coupling`（Agent 平台耦合）为 INFO/WARN 咨询项，受 `target_agent` 字段门控：声明跨 Agent 目标（不含 `workbuddy`，如 `claude-code`/`cross-agent`）但仍含 WorkBuddy 耦合时升为 WARN（跨 Agent 会失效）；其余（未声明 / 声明含 `workbuddy` / 推断 `workbuddy`）均按 INFO 提示——不再因 `workbuddy` 而抑制，因本 skill 自身亦开发跨 Agent 能力，耦合提示对所有技能均有价值。开放标准技能的 `compatibility` 字段视作 `target_agent`。

## 跨平台可移植性证明（本技能自身）

本技能自身满足跨平台可部署要求，以下为**实测证据**（非声明、可复现）：

- **纯 Python 标准库实现，零第三方依赖**：`scripts/audit_docs.py` 仅依赖 `argparse` / `re` / `os` / `json` / `zipfile` / `subprocess` / `threading` 等标准库，无需 `pip install`；`deadcode` 高精度模式的可选依赖 `vulture` 缺省时自动降级为零依赖 `ast`，非运行必需。
- **无平台专属 API 的实际调用**：代码中出现的 `win32api` / `ctypes.windll` / `winreg` / `HKEY_` / `ShellExecute` / `os.startfile` / `powershell` / `cmd.exe` / `os.getcwd` / `shell=True` 等字样，**仅作为检查器自身的检测规则**（用于发现*其他*技能的这些反模式），本技能自身从未调用；所有外部 CLI（`git` / `npm` / `skillhub` 等）均以**列表传参**方式调用，未使用 `shell=True`。
- **portability 自检零 OS 级发现**：在本技能源码（SKILL.md 未声明 `target_platform`，即「跨平台 = 全平台全检」）上运行 `--check portability`，结果为 `ERROR 0 / WARN 0`；所有 `INFO` 均为 `agent_coupling`（跨 *Agent* 咨询，提示 `.workbuddy` / `allowed-tools` 耦合，**非** OS 级破损）——无硬编码绝对路径、无启动目录依赖、无平台专属 shell、无解释器锁、无编码假设。
- **结论**：可在 Windows / Linux / macOS 上无修改运行。仅当接入 `--source github`（git clone）或 `--source skillhub`（skillhub CLI）时才需对应外部 CLI 存在于 `PATH`；`--source url` 使用标准库 `urllib`，无需任何外部 CLI，且 HTTPS 依赖对目标 OS 透明。

## 进阶用法示例

基础用法之外，以下场景覆盖更复杂的实际诉求：

**1. CI 质量门禁（任何小瑕疵都阻断合并）**

```sh
# --strict 让 WARN 也计入退出码；--json 便于接入看板
python scripts/audit_docs.py --skill . --all-checks --strict --json > audit.json
echo "exit=$?"   # 0=体检通过，1=发现问题（含 WARN）
```

解读：`--strict` 适合发布前的强约束；把 `audit.json` 喂给后续步骤可做「文档质量趋势」看板，每次提交对比 ERROR/WARN 数量。

**2. 超大单体仓库扫描调优（避免卡死/拖慢）**

```sh
# 调高超大文件跳过阈值、设总超时上限
python scripts/audit_docs.py --skill ./huge-monorepo --all-checks --max-file-size 5000000 --timeout 120
# 只查安全红线 + 依赖声明，省时
python scripts/audit_docs.py --skill ./huge-monorepo --check security --check deps
```

解读：单仓库文件极多时，优先用 `--check` 指定检查器，配合 `--max-file-size`/`--timeout` 把审计控制在可接受时长内，超大文件会自动跳过并报告、不拖慢整体。

**3. 一次体检多个已安装技能**

```sh
python scripts/audit_docs.py --all --all-checks
```

解读：`--all` 遍历 `~/.workbuddy/skills/` 下全部技能，批量产出各自报告，适合周期性「存量技能大扫除」。
