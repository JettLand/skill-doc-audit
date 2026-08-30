---
name: skill-doc-audit
slug: skill-doc-audit
displayName: 技能文档审计
description: 技能文档审计：审计技能文档与代码的一致性及静态质量，找出版本迭代造成的文档漂移与结构/安全/可运行性/依赖隐患——死链接、失效的命令行参数、退出码表不符、状态或配置项漏写、描述脱节，以及 frontmatter 不规范、硬编码密钥、脚本语法错误、外部依赖与运行平台未声明、跨平台可移植性等。当你刚改完某个技能的脚本或配置、担心文档没跟上，或某个技能经历多次版本迭代后想做一次体检/质量检查/一致性校验时使用。可审计任意本地技能目录、批量审计全部已安装技能，也可经 --source 审计 GitHub 仓库或 SkillHub 集市里的技能；portability 检查器可按 SKILL.md 的 target_platform 字段豁免对应平台项。支持 `--ref` 逗号分隔批量审计多仓库/整组织技能，并以 `--report health` 输出供应链安全自检汇总。
version: "1.16.0"
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

**脚本能可靠判定的（低误报，通常就是偏差）** —— 由以下检查器产出，可按需启用：

- `doc`（常驻默认开）：文档一致性
- `structure`：结构体检 + 元信息
- `security`：安全红线静态子集
- `runtime`：脚本可运行性
- `deps`：依赖与平台声明
- `deadcode`（运行前会询问精度模式）：死代码检测——未使用的函数/类定义、未使用的导入、不可达代码，以及 `scripts/` 与 `references/` 下从未被引用的孤立资源文件。运行前按 `--deadcode-mode` 选 `vulture`（高精度，需装 vulture，推荐）/`ast`（零依赖，易误报）/`skip`（本次跳过）；默认 `ask`：环境已装 vulture 则自动采用高精度（不询问），未装则交互询问，30 秒超时或无输入回退零依赖 `ast`。两种模式下函数/导入定义所在行或上一行写 `# keep` 均可作为白名单、跳过告警；vulture 模式由 vulture 负责导入/定义/类/方法检测（不重复报 AST 结果），并叠加 AST 独有的不可达代码与孤儿资源检测
- `portability`（零依赖纯静态分析）：跨平台可移植性——硬编码绝对路径、启动目录依赖（`os.getcwd`）、平台专属 shell/命令、解释器/运行时锁、编码/路径分隔符假设、Agent 平台耦合。按 SKILL.md 的 `target_platform` 字段豁免对应平台项（`target_platform: windows` 仅抑制 Windows 专属项的误报，仍保留在 Windows 上真会崩的项；不写=跨平台，全检）；`agent_coupling`（Agent 平台耦合）另受同级 `target_agent` 字段门控：声明含 `workbuddy` 则抑制，声明 `claude-code`/`cross-agent` 等跨 Agent 目标且仍含 WorkBuddy 耦合时升为 WARN；全部 WARN/INFO，绝不 ERROR

各检查器的完整项、判定口径与误报抑制细节见 `references/checkers.md`。

脚本只能枚举差异、不能判定对错的，以及完全查不出、必须 AI 读代码判断的语义项（如描述是否仍成立、提示是否误导、跨文件一致性），详见 `references/checkers.md`。**不要只用脚本结论就下判断**——扫描报告是线索，不是裁决。

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
| 只查跨平台可移植性 | `--check portability` |
| 声明目标平台以豁免对应项 | SKILL.md 写 `target_platform: windows`（或 linux/macos/列表） |
| 标注目标 Agent 分发范围 | SKILL.md 写 `target_agent: workbuddy`（或 claude-code/cross-agent/自由列表）；耦合提示不再抑制，跨 Agent 声明未含 workbuddy 升 WARN |
| 生成跨格式可移植性矩阵（X→Y 字段损失） | `--report portability-matrix`（仅做报告，不改写；输出源格式到各目标格式的 P/D/L 矩阵） |
| 生成跨格式**转译报告**（只读预览·不落盘） | `--report translate --target <fmt>`（仅出报告不生成文件；输出 frontmatter 字段映射表 + 目标 SKILL.md 脚手架预览；支持 `--verify` 做内存往返保真；目标格式 `workbuddy`/`agentskills`/`claude-code`/`cursor-plugin`/`generic`，与源格式双向；其中 `agentskills`/`cursor-plugin` 即 Agent Skills 开放标准，一次转译全生态通用） |
| 生成生态级健康度汇总（批量审计时） | `--report health`（仅做报告，不改写；汇总各技能 ERROR/WARN/INFO 与供应链安全风险技能数；`--json` 多技能时自动附带 `health_summary`） |

其余参数（`--json` / `--timeout` / `--max-file-size` / `--deadcode-mode` / `--backup-limit` / `--source` / `--ref` / `--keep-temp`）与完整检查项口径见下方「用法」与 `references/checkers.md`。

## 多平台来源（--source github / skillhub）

默认 `--source local`：用 `--skill <目录>` 或 `--all`（扫 `~/.workbuddy/skills`）审计本机技能。
新增 `--source` 可把**远程仓库 / 集市技能**拉到临时目录后照常审计，`analyze_skill` 核心逻辑零改动。

| 来源 | 说明 | --ref 取值 |
|---|---|---|
| `local`（默认） | 本机目录 / 已装技能 | 无需（用 `--skill` / `--all`） |
| `github` | `git clone --depth 1` 到临时目录后审计；支持仓库内含嵌套子目录（如 `src/` 下放 SKILL.md）/多技能 | `owner/repo` 或 https 地址，可加 `@分支` |
| `skillhub` | 经 `skillhub install <slug> --dir` 拉取集市技能 | 技能 slug |

审计结束后临时目录默认自动清理；加 `--keep-temp` 可保留并打印路径，便于排查。

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

- **只改文档，不改代码**。若审计中发现是代码有问题，整理出来交由用户决策，不要顺手改代码。
- **保留「已弃用」标注**。例如某退出码已在文档标注弃用，那是刻意的向后兼容说明，不要因为它「代码从不返回」就删掉。
- **存疑时标注而非臆断**。语义判断没有把握时，在文档中写明「待确认」，好过写下一个错误的断言。
- 版本号按语义化规则递增：修正文档表述属补丁级，修复功能缺陷属小版本级。

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

**误报自纠错能力**：`security` 检查器对所有正则统一采用上下文感知过滤，自动排除注释、文档 URL、自引用资源上溯，避免上下文盲误报。完整机制见 `references/checkers.md`。

## 常见问题（FAQ）与避坑

**Q1：报告里出现 `DEAD_PATH`，但那个路径确实在用，是误报吗？**
很可能是。文档引用的路径若指向「运行期生成的产物」（如某技能会在目标项目创建 `.learnings/` 目录、或脚本在临时目录生成 state），本技能目录下确实不存在，却并非漂移。判定前留意引用处是否含「生成 / 创建 / 写入」等含义。详见 `references/checkers.md` 的「判定提示」。

**Q2：安全扫描报了 `path_traversal`（`../`），但我只是写文档 URL，怎么办？**
这是上下文盲误报。`security` 检查器已对全部正则做上下文感知过滤，自动排除注释行、含 `://` 的文档 URL、以及含 `__file__`/`dirname`/`.asar` 的合法资源上溯。若仍报出，请贴出原行复核；真实漏洞（外部可控字符串拼入落盘路径并含相对上溯）会被正确保留。

**Q3：扫描报告能直接当裁决改文档吗？**
不能。脚本只枚举差异、不判定对错；语义项（描述是否仍成立、提示是否误导、跨文件一致性）必须 AI 读代码判断。报告是线索，不是裁决。

**Q4：退出码在文档列了但代码从不返回，是文档错了？**
未必。若文档已标注「已弃用」，那是刻意的向后兼容说明，保留不要删。

**Q5：只想查某一类问题，怎么缩小范围？**
用 `--check` 按需启用（如 `--check security`），或 `--all-checks` 全开；`--strict` 让 WARN 也计入退出码，适合 CI 门禁。

## 示例输出

对 `~/.workbuddy/skills/workbuddy-checkin` 运行：

```sh
python scripts/audit_docs.py --skill ~/.workbuddy/skills/workbuddy-checkin --all-checks
```

典型可读报告（节选，每条发现均带中文标签与机器码，自解释）：

```
[doc]      ERROR  失效命令行参数【DEAD_FLAG】 文档提到的 `--retry` 在代码中无实现 (SKILL.md:42)
          → 建议：补实现或删除文档描述
[doc]      WARN   缺少版本声明【VERSION_MISSING】 未声明 version (SKILL.md)
[security] ERROR  疑似硬编码密钥【hardcoded_secret】 疑似硬编码 Token (scripts/audit_docs.py)
          → 建议：改为环境变量读取
[security] INFO   路径穿越【path_traversal】 被上下文过滤忽略（文档 URL，非真实穿越）
[structure] OK    名称不一致【name_mismatch】 frontmatter name 与目录名一致
...
Summary: 2 ERROR, 1 WARN, 0 INFO  | exit code 1
```

说明：`ERROR` 默认计入退出码（`1`）；`WARN`/`INFO` 不计入，需结合上下文判断，勿直接当错误处置。`--json` 可输出机读明细（每条含 `checker/severity/category/category_cn/message/file/line/suggestion`）。`category` 为稳定机器码，`category_cn` 为同一含义的中文标签。

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

> **跨 Agent 格式归一化内核（Phase 5）**：审计引擎在执行检查前先用 `detect_format()` 按 frontmatter 特征推断技能格式——`workbuddy` / `agentskills` / `claude-code` / `cursor-mdc` / `generic`——并构建统一 `SkillModel`（name/description/fmt/platform/target_platform/target_agent/tools/license/version/extra），供各检查器与后续矩阵/转译消费。格式判定「按特征推断」而非硬锁枚举，以适配生态演进（同 v1.11.0 自由列表原则）。`analyze_skill` 的返回结果现含 `format` 与 `skill_model` 字段。

| category | 中文含义 | 默认级别 |
|---|---|---|
| `hardcoded_abs_path` | 硬编码绝对路径（`C:\Users\...` / `/Users/` / `/home/`） | WARN |
| `cwd_dependence` | 启动目录依赖（`os.getcwd` / `Path.cwd` / `process.cwd`），从别的目录启动找不到资源 | WARN |
| `platform_shell` | 平台专属 shell/命令（`cmd.exe`/`powershell`/`rm -rf`/`ls` 等，仅看子进程/系统调用语义的行） | WARN |
| `interpreter_lock` | 解释器/运行时锁（裸 `python` 非 `python3`、Windows `py` 启动器） | WARN |
| `encoding_sep` | 编码/路径分隔符假设（`open()` 未指定 `encoding`，Windows 文本模式默认编码非 UTF-8 易解码失败） | WARN |
| `agent_coupling` | Agent 平台耦合（硬编码 `.workbuddy` / `allowed-tools` 约定，跨 Agent 分发需抽象） | INFO/WARN |
| `lossy_port` | 跨格式可移植性损失（Phase 6：声明跨 Agent 目标却含目标端无对应/需转译的字段；`lost` 升 WARN，`degraded` 仅 INFO） | INFO/WARN |

> **跨格式可移植性矩阵（Phase 6，核心价值）**：在 Phase 5 统一 `SkillModel` 之上，引擎以开放标准 `agentskills` 为枢纽构建字段级能力映射（`FMT_CAPS` / `EQUIV`），对任意技能生成「源格式 → 各目标格式」的 P（保留）/ D（降级需转译）/ L（丢失）矩阵，并可通过 `--report portability-matrix` 直接打印。`lossy_port` 发现即来自该矩阵：仅当技能**显式声明跨 Agent 目标**（如 `compatibility: [claude-code, cursor]`、`target_agent` 含非 workbuddy 项）时，对声明目标端会 `lost`/`degraded` 的字段发出 WARN/INFO；纯 workbuddy 或未声明目标的不发（其跨 Agent 咨询已由 `agent_coupling` 覆盖）。降级示例：`target_agent` ↔ `compatibility`、`slug`/`displayName` → `name`；丢失示例：workbuddy 的 `version`/`slug` 在 claude-code 无对应字段。

> **跨格式转译报告（Phase 7，只读预览）**：在 Phase 5/6 底座之上新增 `--report translate`，把「检测/矩阵」升级为「可预览的转译方案」——但**只出报告、不落盘**，守住本技能「只读扫描、绝不自动改写」的立身之本。它复用 `SkillModel` + `FMT_CAPS`/`EQUIV` + `build_portability_matrix`：对给定源技能与目标格式（`--target`，支持 `workbuddy`↔`agentskills`/`claude-code`/`cursor-plugin`/`generic` 双向），输出 **frontmatter 字段映射表**（保留/降级/丢失逐项标注）+ **目标 SKILL.md 脚手架预览**（仅 frontmatter + 标题骨架，正文散文不翻译、留人工）。`--verify` 在此之上做**内存往返保真**：emit→re-parse→比对，依 `build_portability_matrix` 给出每个字段的可逆性（保留/降级可往返、丢失不可逆）与整体保真结论（`RECOVERABLE` / `LOSSY` / `IRREVERSIBLE`），全程不写任何文件。JSON 模式下附 `translate` 字段供 CI 消费。`generic` 为**降级兜底**目标：仅保留 `name`/`description`，其余字段（version/license/allowed-tools/target_agent 等）全部丢失，仅作最简归档/人读兜底。决策约束：①仅报告不生成文件；②仅 frontmatter + 脚手架；③先支持 workbuddy↔agentskills/claude-code/cursor-plugin，v1.16.0 起追加 `generic` 降级兜底；④`--verify` 往返保真一并纳入。
> **agentskills = 全生态通用枢纽（Phase 7 关键认知）**：`--target agentskills` 与 `--target cursor-plugin` 产出的 frontmatter 即 **Agent Skills 开放标准（agentskills.io，Anthropic 2025-12 开源）** 形态（`name`/`description`/`license`/`allowed-tools`/`compatibility`/`metadata` 能力集合）。该标准截至 2026 年已被 **40+ AI 工具**采纳为技能格式——Claude Code、Cursor、Gemini CLI、OpenAI Codex、GitHub Copilot、Windsurf、Kiro、OpenCode、Cline、Roo Code 等。即**一次转译到 `agentskills`，技能即可被上述 40+ 工具直接消费**；`claude-code` 仅在其上叠加 `model`/`context`/`agent`/`hooks`/`argument-hint` 等可选扩展键。因此「更多目标格式」的核心诉求已被现有目标以最小成本覆盖，`generic` 仅作压扁兜底。

> 豁免规则（核心）：每条发现的 `breaks_on` 是「它会在哪些 OS 上崩」。声明平台与 `breaks_on` **有交集才报**，无交集才抑制。例：`target_platform: windows` 会抑制 `powershell`/`C:\` 这类 Windows 专属项的误报，但**保留** `rm -rf`/`/Users/` 这种在 Windows 目标上真会崩的项。`target_platform` 不写 = 跨平台（全平台）→ 始终全检。`agent_coupling`（Agent 平台耦合）为 INFO/WARN 咨询项，受 `target_agent` 字段门控：声明跨 Agent 目标（不含 `workbuddy`，如 `claude-code`/`cross-agent`）但仍含 WorkBuddy 耦合时升为 WARN（跨 Agent 会失效）；其余（未声明 / 声明含 `workbuddy` / 推断 `workbuddy`）均按 INFO 提示——不再因 `workbuddy` 而抑制，因本 skill 自身亦开发跨 Agent 能力，耦合提示对所有技能均有价值。开放标准技能的 `compatibility` 字段视作 `target_agent`。

## 跨平台可移植性证明（本技能自身）

本技能自身满足跨平台可部署要求，以下为**实测证据**（非声明、可复现）：

- **纯 Python 标准库实现，零第三方依赖**：`scripts/audit_docs.py` 仅依赖 `argparse` / `re` / `os` / `json` / `zipfile` / `subprocess` / `threading` 等标准库，无需 `pip install`；`deadcode` 高精度模式的可选依赖 `vulture` 缺省时自动降级为零依赖 `ast`，非运行必需。
- **无平台专属 API 的实际调用**：代码中出现的 `win32api` / `ctypes.windll` / `winreg` / `HKEY_` / `ShellExecute` / `os.startfile` / `powershell` / `cmd.exe` / `os.getcwd` / `shell=True` 等字样，**仅作为检查器自身的检测规则**（用于发现*其他*技能的这些反模式），本技能自身从未调用；所有外部 CLI（`git` / `npm` / `skillhub` 等）均以**列表传参**方式调用，未使用 `shell=True`。
- **portability 自检零 OS 级发现**：在本技能源码（SKILL.md 未声明 `target_platform`，即「跨平台 = 全平台全检」）上运行 `--check portability`，结果为 `ERROR 0 / WARN 0`；17 条 `INFO` 全部为 `agent_coupling`（跨 *Agent* 咨询，提示 `.workbuddy` / `allowed-tools` 耦合，**非** OS 级破损）——无硬编码绝对路径、无启动目录依赖、无平台专属 shell、无解释器锁、无编码假设。
- **结论**：可在 Windows / Linux / macOS 上无修改运行。仅当接入 `--source github`（git clone）或 `--source skillhub`（skillhub CLI）时才需对应外部 CLI 存在于 `PATH`，且该依赖对目标 OS 透明。

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
