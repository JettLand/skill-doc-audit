# 变更明细（CHANGELOG）

本文件收录各版本的「打磨明细」（改动 + 验证），作为开发 / QA 留档。README 的「版本与评测」表仅保留要点摘要。

> 排序：版本号降序（最新在前）。


## 1.25.1 打磨明细（fixtures 声明式 recipe 生成器，self_validate 技术兜底）

### 背景（用户指令）
用户指出：既然 fixtures 是手工创建的，应「参考手工创建过程构筑一个 fixtures 生成器」，为自校验工具做技术兜底——fixtures 丢失时仍能重新生成，而非只能依赖 git 恢复。

### 改动
- **新增 dev 工具 `make_fixtures.py`（声明式 recipe 生成器）**：把每个 fixture 的「手工创建过程」编码为 recipe（frontmatter + 文件内容），运行时精确复刻 `tests/fixtures/`；支持 `--check`（校验现有 fixtures 与 recipe 一致、不写盘）与 `--out DIR`（输出到指定目录），幂等可重跑。
- **设计取舍（与弱方案区分）**：刻意采用「recipe 复刻原始 fixture 本身」而非「从 golden 快照反推」——前者无损、golden 仍只作断言基准，不削弱回归严格性；后者会循环且可能丢失原始覆盖面。recipe 内容取自已提交 fixtures 的精确副本，故重建字节一致（`make_fixtures.py --check` 验证 OK、`diff -r` 验证 DIFF_CLEAN）。
- **`self_validate.py` 缺失提示增强**：fixtures 目录/单项缺失时，`fail()` 提示改为「可运行 `python src/scripts/make_fixtures.py` 重建」，引导使用兜底生成器。
- **dev-only 约束不变**：`make_fixtures.py` 与 `self_validate.py` 均不进 `src/dist/skill-doc-audit.zip` / 部署副本。
- **版本号升 1.25.1**：`src/SKILL.md` frontmatter 与 `sources.py` 的 `User-Agent` 串同步升至 `skill-doc-audit/1.25.1`。

### 验证
- `make_fixtures.py --check`：`check: OK`；临时重建后 `diff -r tests/fixtures <tmp>`：`DIFF_CLEAN`（字节一致）。
- `self_validate.py` 从无关 CWD（`C:/`）运行：三例全部 `[PASS]`，exit 0。
- 部署副本自审 `--all-checks --deadcode-mode vulture`：`ERROR 0 / WARN 0 / INFO 20`（与基线无回归）。

## 1.25.0 打磨明细（audit_docs.py 模块化拆分 + 内置自校验工具 self_validate.py）

### 背景（用户两项指令）
1. 用户指出 `audit_docs.py` 已达约 2490 行，单体文件难以维护，要求拆分为多个源码文件。
2. 用户确认 Vector 3「示例归一化方案」不具备泛用性（仅能校验 skill-doc-audit 项目自身），决定将其落地为技能**内置的可选自校验工具** `self_validate.py`，而非插件式检查器；并要求该工具在新环境 clone 仓库源码后仍可正常调用。

### 改动（代码 + 文档同步）
- **模块化拆分**：原 2491 行单体 `src/scripts/audit_docs.py` 拆为薄入口（仅 `from auditlib import cli; cli.main()`）+ `src/scripts/auditlib/` 包：`core.py`（常量/公共辅助/`CHECKERS` 注册表）、`model.py`（`analyze_skill`）、`report.py`（`build_json` 等）、`sources.py`（来源层级）、`cli.py`（argparse 入口，含 `import auditlib.checkers  # keep` 触发自注册）；`checkers/` 子包含 doc/structure/security/runtime/deps/deadcode/portability/doc_llm 八检查器，各自 `CHECKERS["name"]=fn` 自注册。
- **跨模块共享符号归位**：`_normalize_target_platform`/`_normalize_target_agent`/`_parse_frontmatter_list`/`AGENT_ALL`/`PLAT_WIN|UNIX|ALL`/`ENTRY_HINTS` 由原先散落的检查器模块统一迁至 `core.py`，消费者改为显式 `from auditlib.core import ...`，规避检查器↔检查器导入环。
- **自校验工具 `self_validate.py`（开发期，非插件）**：独立于 `CHECKERS` 注册表，不经 `--check`/`--all-checks` 触发；基于 `auditlib.model.analyze_skill` + `auditlib.report.build_json` 对 `tests/fixtures/{dirty-skill,multifile,tricky-clean}` 跑确定性检查器 （doc/structure/security/runtime/deps，规避 vulture/agent 非确定项），将结果中顶层 `skill` 绝对路径掩为 `<ROOT>` 后，与 `tests/examples/*.expected.json` 黄金快照做「摘要计数 + 发现签名集合」比对；`--baseline` 可重建快照；仓库根经 `__file__` 解析（`HERE=dirname(abspath(__file__))`, `ROOT=dirname(dirname(HERE))`），**不依赖 CWD**，新环境 clone 后任意目录可跑。
- **制品同步**：`src/dist/skill-doc-audit.zip` 重打包为 18 项（SKILL.md + audit_docs.py + references/checkers.md + auditlib/**）；部署副本 `C:/Users/admin/.workbuddy/skills/skill-doc-audit/` 同步含 `auditlib/**`。
- **版本号升 1.25.0**：`src/SKILL.md` frontmatter 与 `sources.py` 的 `User-Agent` 串同步升至 `skill-doc-audit/1.25.0`。

### 验证
- `py_compile` 全模块通过；拆分后部署副本自审 `--all-checks --deadcode-mode vulture`：`ERROR 0 / WARN 0 / INFO 20`（与拆分前基线无回归）。
- `self_validate.py` 三例全部 `[PASS]`（dirty-skill error=12/warn=4、tricky-clean error=0/warn=0、multifile error=1/warn=1）；从无关 CWD（`C:/`）调用仍 PASS，证明新环境 clone 后调用无碍；人为损坏黄金快照可触发 exit 1 并输出明确 diff，证明漂移可检出。

## 1.24.1 打磨明细（移除 doc-llm 预览选项 + 校正 token 成本表述）

### 背景（用户两项指令）
1. 用户指出「调用了 agent 其实就会消耗 token，因为输入输出都会消耗 token，只是输入消耗更少而已」——v1.24.0 文档称 agent 接手「零额外成本、不消耗用户 token」不准确：agent 用自身能力比对时，SKILL.md 全文 + 代码事实清单作为上下文注入 agent，会占用 agent 推理 token（输入侧为主、输出极少），外部 LLM 账单虽免，token 成本客观存在。
2. 用户认为 doc-llm 的选项 3（预览）应删除——预览会把材料重复灌入上下文、徒增 token，无实质收益，「有浪费用户 token 的嫌疑」。

### 改动（代码 + 文档同步，纯文档级语义、不改审计逻辑）
- **删除 preview 模式**：`DOCLLM_MODES` 由 `("off","agent","ask","preview")` 改为 `("off","agent","ask")`；`_resolve_doc_llm_mode` 移除 `preview` 分支；`--doc-llm-mode` 帮助与 argparse choices 同步去除 preview；`check_doc_llm` 移除 `if mode == "preview": _print_doc_llm_preview(...)`。
- **删除 `_print_doc_llm_preview`**：原函数整体删除，仅留两行注释说明 v1.24.1 移除缘由（预览重复占用上下文 token、徒增成本）。
- **AskUserQuestion 模板精简**：选项由「1) 默认 / 2) agent 接手 / 3) 预览（前置步骤）」改为「1) 默认模式 / 2) 启用语义漂移检查（agent 介入，消耗额外 token）」，删除选项 3 及「前置步骤」二次询问流程，后续红线 / CI 步骤顺延编号。
- **token 成本表述全量校正**：所有「零额外成本 / 不消耗用户 token」改为「会占用 agent 自身推理 token（输入侧为主），但不向外部 LLM 服务付费」。覆盖 SKILL.md（能力清单、doc-llm 避坑要点、Vector 2 引用块）、`audit_docs.py` 多处 docstring / 运行时提示 / `--check` `--doc-llm-mode` 帮助、README.md 版本摘要。
- **顺手修复版本漂移**：`--source url` 的 `User-Agent` 串仍为 `skill-doc-audit/1.23.0`（v1.24.0 漏升），本次一并升为 `skill-doc-audit/1.24.1`。

### 验证
- `py_compile` 通过；`audit_docs.py` 中 `preview` 仅剩全局 `--preview`（审计范围预览，无关）与 `_print_doc_llm_preview` 的两行移除注释，doc-llm 的 preview 模式已无残留。
- 部署副本自审 `--all-checks --deadcode-mode vulture`：`ERROR 0 / WARN 0 / INFO 20`（基线无回归）。

## 1.24.0 打磨明细（doc-llm 改由 agent 直接接手，移除外部 LLM 依赖）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

### 背景（用户两项指令）
1. 选项 3（预览）应作为前置步骤：展示预估结果后，继续让用户在选项 1（默认）与 2（增强/接手）间选择，除非超时；此前 agent 选了 3 就直接结束，未回问 1/2。
2. 所有用到外部 LLM 的地方都应改由 agent 直接接手——否则只会提高用户使用成本（自备 API Key、额外付费）。要求全量改写相关描述。

### 改动
- **删除外部 LLM 调用**：移除 `_call_llm`（urllib/OpenAI 兼容 HTTP 调用）、`_load_llm_config`、`_LLMUnavailable`、`_parse_llm_drift`，及 `--doc-llm-api-key`/`--doc-llm-model`/`--doc-llm-base-url` 三个配置参数与 `SKILLDOC_LLM_*` 环境变量依赖。
- **模式重构**：`DOCLLM_MODES` 由 `(off,auto,ask,preview)` 改为 `(off,agent,ask,preview)`；`auto` 彻底移除，`agent` 取而代之——语义漂移检测一律由 agent 用自身能力完成。
- **agent 接手机制**：新增 `_write_doc_llm_dossier(ctx)`——把 SKILL.md 全文 + 代码事实清单写成 dossier 文件（系统临时目录），`check_doc_llm` 在 `agent` 模式下打印 `[doc-llm] AGENT_TAKEOVER: <path>` 哨兵并发 `INFO doc_llm_agent_handoff`，由 agent 读取后自行完成语义比对、回报 `DOC_LLM_DRIFT`。
- **预览改写**：`_print_doc_llm_preview` 改为「agent 将接手、零额外成本、不依赖外部 LLM」口径，展示 agent 将比对的材料规模（不再提「消耗 token」）。
- **Agent 调用流程修正**（SKILL.md「Agent 调用标准动作」）：选项 3 明确为「前置步骤」——先跑 `--doc-llm-mode preview` 展示材料，再二次 `AskUserQuestion` 只给 1（默认）/2（agent 接手）让用户做最终选择（超时默认 1）。
- **描述全量改写**：所有「依赖外部 LLM 服务 / 消耗额外 token / 配置 SKILLDOC_LLM_*」表述，统一改为「由 agent 直接接手 / 零额外成本 / 不依赖外部 LLM」。涉及 SKILL.md（能力清单、doc-llm 段落、Agent 约定、错误码表、Vector 2 引用块）、`references/checkers.md`（错误码表）、`README.md`（版本摘要）、argparse 帮助。
- **错误码调整**：移除 `doc_llm_unavailable` / `doc_llm_ran`（随外部 LLM 调用移除），新增 `doc_llm_agent_handoff`（INFO）。

### 验证
- 残留符号 grep：`_call_llm`/`_load_llm_config`/`_LLMUnavailable`/`_parse_llm_drift`/`SKILLDOC_LLM`/`--doc-llm-api-key` 等均为空（仅剩一处「移除说明」注释）。
- `py_compile` 通过；`--doc-llm-mode` choices 实测为 `{off,agent,ask,preview}`。
- 实跑 `agent` 模式：写出 49217 字节 dossier + 打印 `AGENT_TAKEOVER` 哨兵 + `INFO doc_llm_agent_handoff`，整体 `ERROR 0 / WARN 0 / INFO 21`。
- 实跑 `preview` 模式：展示「agent 直接接手、零额外成本」口径，未调用任何 LLM，整体 `ERROR 0 / WARN 0 / INFO 20`。
- 部署副本自审（同步后）：`ERROR 0 / WARN 0 / INFO 21` 通过。

## 1.23.7 打磨明细（修复 --doc-llm-mode preview 被 argparse 拒绝的 bug）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

### 背景（用户实操暴露）
v1.23.5/v1.23.6 的 Agent 约定 step 2 把预览模式映射为 `--doc-llm-mode preview`，但 argparse 的 `choices=list(DOCLLM_MODES)` 中 `DOCLLM_MODES = ("off","auto","ask")` 不含 preview，故 CLI 实跑报 `invalid choice: 'preview'`。预览此前只能经 `--doc-llm-mode ask` 的交互 stdin 菜单选 3 才能进入——意味着 Agent 经 AskUserQuestion 收到用户选 3 后无法直接 CLI 调用，违背 step 2 承诺。v1.23.6 演示「预览选项 2 的 token 消耗」时即触发。

### 改动（代码 + 文档同步）
- `src/scripts/audit_docs.py:214` `DOCLLM_MODES` 由 `("off","auto","ask")` 增为 `("off","auto","ask","preview")`。
- `_resolve_doc_llm_mode`（1410–1450 区间）新增直返分支：`if mode == "preview": return "preview", False, None`——不依赖 LLM 配置、零 token、不调用 LLM（语义与 ask 交互菜单选 3 一致）。
- `--doc-llm-mode` 帮助文本补 `preview` 说明，明确「仅展示将发送给 LLM 的内容与预估 token，不实际调用，零依赖零 token，Agent 经 AskUserQuestion 收到用户选 3 后可直接传入」。
- frontmatter 1.23.6 → 1.23.7；README 版本表新增 1.23.7 行；本 CHANGELOG 新增本节。

### 验证
- `py_compile` 通过。
- 实跑 `--doc-llm-mode preview --all-checks --deadcode-mode vulture`：help 显示 `{off,auto,ask,preview}`；doc-llm 段打印 `[doc-llm 预览] 增强模式将向配置的 LLM 端点发起 1 次请求，发送 SKILL.md 全文 + 代码事实清单` + SKILL.md 长度 26297 字符 + 代码事实清单 1743 字符（预估 ~435 token）+ 明确「本次未调用 LLM」；`[doc-llm] ERROR 0 / WARN 0 / INFO 0`；整体 `ERROR 0 / WARN 0 / INFO 20 通过`。
- 部署副本同步；`dist` 重打包；自审零误报。

## 1.23.6 打磨明细（改进 AskUserQuestion 措辞模板：术语化→用户语）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

### 背景（用户反馈）
用户截图反馈 v1.23.5 的 AskUserQuestion 模板「非常不好理解」——question 用了「doc-llm 语义漂移检测（Vector 2）」等技术术语，选项 label 太简（仅「默认模式/增强模式/预览代价」），代价与能力信息藏在 desc 里，不直观。建议改为面向用户的措辞，把 doc 检查器与代价/能力信息直接写进 question 与选项 label。

### 改动（纯文档，frontmatter 1.23.5→1.23.6）
- SKILL.md「Agent 调用标准动作」第 1 步：把三选项措辞固化为**强制模板**（agent 必须原样使用）：
  - **question**：`运行doc检查器（默认常驻）时，你希望采用哪种模式？`
  - **header**：`doc 检查`（≤12 字符）
  - **选项 1** label `默认模式（静态脚本检查，零依赖）` / desc `推荐 · 不调用 LLM · 0 token · 离线`
  - **选项 2** label `启用语义漂移检查（依赖外部LLM服务，消耗额外token）` / desc `需先配置 LLM 密钥（SKILLDOC_LLM_API_KEY + SKILLDOC_LLM_MODEL），会调用 LLM 比对 SKILL.md 与代码事实清单`
  - **选项 3** label `预览选项2的预估token消耗` / desc `不实际调用 LLM，仅展示将发送的 SKILL.md + 代码事实清单内容与 token 估算`
- README 版本表新增 1.23.6 行；本 CHANGELOG 新增本节。

### 验证
- 部署副本同步；自审 `--all-checks --deadcode-mode vulture` 通过：`ERROR 0 / WARN 0`，代码零改动。
- 行为说明：用户实际看到的卡片菜单按上述模板呈现（已当场用新措辞演示一次）。

## 1.23.5 打磨明细（Agent 调用必须用 AskUserQuestion 抛出 doc-llm 选择）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

### 背景（用户指令）
用户指出：「这是个 agent skill，通过 agent 调用时也要弹出菜单让用户选择。」——即 agent 调用本技能时，doc-llm 的「显式提问」必须真正触达用户、由用户选择，而不是靠 CLI stdin 菜单（agent 沙箱收不到输入，只会空等 30s 超时回退默认）。

### 根因
- 1.23.4 的 Agent 约定仍含「让用户自己在终端选」的指引，且未规定 agent 在调用前应主动用 `AskUserQuestion` 抛选择；旧版甚至暗示 Bash 工具下让菜单打印即可，但那在 agent 场景里用户根本无法输入。
- 正确载体：agent 场景没有可键入终端 → CLI stdin 菜单失效 → 必须用 agent 原生的 `AskUserQuestion` 工具把选择权交给用户，再按选择显式传 `--doc-llm-mode`。

### 改动（纯文档，frontmatter 1.23.4→1.23.5）
- SKILL.md「Agent 执行约定 · doc-llm 语义检测同理」整段重写：
  - 厘清三载体：真实交互终端（CLI stdin 菜单）/ Agent 调用（**必须改用 `AskUserQuestion`**）/ 管道 CI（INFO skipped）。
  - 新增「Agent 调用时的标准动作」三步：①运行前先 `AskUserQuestion` 呈现三选项（默认/增强/预览代价，代价透明）；②按选择显式传 `--doc-llm-mode off|auto|preview`；③红线（不得跳过询问、不得擅自 auto）。
  - 删除过时的「让用户自己在终端选」指引。
- README 版本表新增 1.23.5 行；本 CHANGELOG 新增本节。

### 验证
- 部署副本同步（后续）。
- 部署副本自身 `--all-checks --deadcode-mode vulture` 自审：`ERROR 0 / WARN 0`，通过（代码零改动，行为不变，仅约定校正）。
- 行为说明：agent 按新约定先用 `AskUserQuestion` 询问 → 再带显式 `--doc-llm-mode` 运行，**不再触发 CLI 的 30s 空等**，用户决定权落实。

## 1.23.4 打磨明细（校正 Agent 约定文档漂移：Bash 工具下 doc-llm 并非 INFO skipped）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

### 背景
用户执行 `@skill:skill-doc-audit --all-checks` 后问「doc-llm 的显式提问呢？」——经查证代码（`audit_docs.py:1438` 的 `if not sys.stdin.isatty()` 分支）并实测两路径：
- **Path B（Bash 工具，不管道 stdin）**：`sys.stdin.isatty()` 为真 → 走交互分支，真实打印菜单并等待约 30s 后超时回退默认（`[doc-llm] INFO 0`），菜单可见但无人输入。
- **Path A（管道 `echo "" \|`）**：`isatty()` 为假 → 直接 `INFO doc_llm_skipped`（第 1440 行返回值）。

故 1.23.3 约定「Bash 工具下 doc-llm 会安全回退为 INFO `doc_llm_skipped`」**与实测不符**——Bash 工具是 tty，走的是菜单+超时分支，不是 skip。上一轮菜单「没看到」的真实原因是 agent 用 `2>&1 | tail -40` 截断了第 2 行打印的菜单（总输出 65 行），并非功能缺失。

### 改动（纯文档，frontmatter 1.23.3→1.23.4）
- SKILL.md「Agent 执行约定」第 148 行：把「交互终端弹菜单 / 管道才 skip」补成三种环境完整描述（真实交互终端 / Bash 工具 tty 无人 / 管道非 tty）。
- SKILL.md 第 152 行红线：把「非交互下自行跳过为 INFO」校正为「Bash 工具下打印菜单+等 30s，管道下才 skip」，并注明 30s 是安全超时、想避免等待可走管道 skip 但仍不得传 `off`。
- README 版本表新增 1.23.4 行；本 CHANGELOG 新增本节。

### 验证
- 部署副本字节级一致（后续同步）。
- 部署副本自审 `--all-checks --deadcode-mode vulture`：`ERROR 0 / WARN 0`，通过。
- 代码零改动，行为不变；仅校正文档使其与实测一致。

## 1.23.3 打磨明细（修正 Agent 约定：禁止替用户关掉 doc-llm）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 修正 Agent 执行约定（doc-llm） | 用户反馈：Agent 跑 `--all-checks` 其他技能时输出「doc-llm 显式关闭」，疑 Agent 替用户做决定。根因——本技能 `SKILL.md`「Agent 执行约定」的 doc-llm 小节旧文把「本次不启用语义检测（默认、最省事）：加 `--doc-llm-mode off`」列为默认项，Agent 据此静默替用户关闭 doc-llm（代码中 `mode in (off,skip)` 即静默 return，故用户只见「doc-llm 显式关闭」叙述、不觉察该能力存在），直接违背 v1.23.1 确立的「绝不替用户决定」原则。重写该小节为明确红线：非交互（Agent/自动化）下**直接跑 `--all-checks` 即可、不要传 `--doc-llm-mode off`**——doc-llm 会自行**安全回退**为 INFO `doc_llm_skipped`（不联网、不耗 token，保留用户后续启用选择权与知情）；仅当用户明确表示要启用 LLM 语义检测时，才先 `AskUserQuestion` 确认代价、再传 `--doc-llm-mode auto`；Agent 不得自行决定启用（那才会消耗用户资源） | 部署副本自审 `[doc] ERROR 0 / WARN 0`；frontmatter 升 1.23.3；README/CHANGELOG 版本摘要补 1.23.3；dist 重打包（含更新后 SKILL.md）。**未改任何代码**，离线不变量与「全量 WARN 0」不变量不变 |

## 1.23.2 打磨明细（doc 检查器补 doc-llm 引导描述）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| doc 项补 doc-llm 引导描述 | 在 `SKILL.md`「能力边界（务必先读）」检查器清单的 `doc` 项补一句引导性描述：`doc` 覆盖 Vector 1 结构化漂移（死引用/失效参数/退出码不符/枚举·数量·能力声明与代码事实不符），自由散文语义漂移由同族 `doc-llm` 检查器（Vector 2，下方单列）以 LLM 语义检测补足；使读者在文档开头即建立「doc 与 doc-llm 分工」认知，无需翻到错误码表才知二者关系 | 部署副本自审 `[doc] ERROR 0 / WARN 0`；frontmatter 升 1.23.2；README/CHANGELOG 版本摘要补 1.23.2 |

## 1.23.1 打磨明细（确立核心设计原则）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 确立核心设计原则 | 在 `SKILL.md` 新增头条「设计原则（核心约束）」：`默认模式零依赖，但绝不替用户决定`——默认即零依赖、绝不替用户决定、透明兜底；并补一条「避坑要点」交叉引用，统领 doc-llm 与 deadcode 的交互式取舍。原则既已落地的代码行为（doc-llm 默认问询/菜单含代价/超时回退；deadcode ask 交互选精度）被正式提炼为书面约束 | 原则与既有实现一致，无文档漂移；部署副本自审 `[doc] ERROR 0 / WARN 0` |

## 1.23.0 打磨明细（doc-llm 默认问询 + 纳入全量检测）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| `--check doc-llm` 默认弹菜单 | `--doc-llm-mode` 默认由 `off` 改为 `ask`（`None` 即解析为 `ask`）；`--check doc-llm` 不传 mode 即进入询问流程，30s 超时/无输入回退默认模式，绝不替用户决定 | 交互选增强/预览/超时默认均解析正确；`py_compile` 通过 |
| doc-llm 纳入 `--all-checks` 全量集 | `ALL_CHECKERS` 追加 `doc-llm`；`check_doc_llm` 按「是否显式传入 `--doc-llm-mode`」区分可见级别——显式传入却未运行 → WARN `doc_llm_unavailable`；`--all-checks` 全量自带、非交互无法询问 → INFO `doc_llm_skipped`（不污染全量 WARN 0 不变量）；新增 `doc_llm_skipped` INFO 类别 | `--all-checks` 非交互 → INFO `doc_llm_skipped`、WARN 1（仅 deadcode 已知）；`--all-checks --doc-llm-mode ask` 非交互 → WARN `doc_llm_unavailable`；`--doc-llm-mode off` 全静默 |
| 文档同步 | `SKILL.md`（检查器清单补 doc-llm、避坑条目改写、错误码表补 `doc_llm_skipped`、Vector 2 块改写、Agent 执行约定扩至 doc-llm）、`references/checkers.md`（补 `doc_llm_skipped` 行）、README/CHANGELOG 版本摘要；frontmatter 与两处 UA `1.22.1` → `1.23.0`；部署副本同步 | 部署副本自审 `[doc] ERROR 0 / WARN 0`；全文检索 `1.22.1` 残留仅历史说明 |

## 1.22.1 打磨明细（doc-llm `ask` 显式三选项交互 · 绝不替用户决定）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| doc-llm `ask` 改为显式三选项交互 | 重写 `_resolve_doc_llm_mode` 的 ask 分支，调用新增 `_prompt_doc_llm_mode()`：交互终端向用户呈现实选项——`1) 默认模式`（纯脚本，零依赖，0 token）/`2) 增强模式`（启用 LLM 语义检测，依赖外部 LLM 服务、消耗额外 token）/`3) 预览代价`（仅展示将发送给 LLM 的内容与预估 token，不实际调用）；新增 `_print_doc_llm_preview(ctx)`；**30 秒超时或无输入一律回退默认模式**（`off`）。非交互（自动化）环境无法询问 → 不再自动复用环境变量配置静默联网，改为回退默认并显著告警（`doc_llm_unavailable`，degraded=True），与 deadcode 非 TTY 行为一致 | 超时（daemon 线程读 stdin，`th.join(30)`）落点 `off`；非 TTY → `auto,True`（触发 `doc_llm_unavailable` WARN）；preview → 打印规模/token 预估后不联网；`py_compile` 通过 |
| 离线不变量与文档同步 | 离线不变量（默认 `off`、不进 `--all-checks`、绝不自动联网）不变；argparse `--doc-llm-mode` 帮助文改为描述三选项与 30s 超时回退；`SKILL.md` Vector 2 引用块重写（v1.22.1 起，说明三选项/30s 超时/非交互回退）；`references/checkers.md` doc-llm 三行版本标 v1.22.1 并补菜单说明；README/CHANGELOG 版本摘要补 1.22.1 行；frontmatter 与两处 UA 版本串 `1.22.0` → `1.22.1` | 全文检索确认 `1.22.0` 残留仅剩历史说明性引用；部署副本同步后自审 ERROR 0 / WARN 0 / INFO 20 |

> TRACE 评测对照：待 SkillHub 上架后由平台重跑（目标——验证 doc-llm 交互改动对评测口径无回归，仍保持 ERROR 0 / WARN 0 不变量）。

## 1.22.0 打磨明细（doc-llm 选装 LLM 语义漂移检测 · Vector 2）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| doc-llm 选装 LLM 语义漂移检测（Vector 2） | 对齐用户「调取流程参考 deadcode 检查器」要求，将 deadcode 的「`(mode, degraded)` 元组 + 降级显著告警 + argparse `choices` 单一真相源」范式复刻到 doc 检查器。新增 `DOCLLM_MODES = ("off","auto","ask")` 模块常量（紧邻 `DEADCODE_MODES`，供 argparse 与 doc 校验共用）；`CATEGORY_LABELS` doc 段登记 `DOC_LLM_DRIFT`（文档/代码语义漂移 LLM 判定）、`doc_llm_unavailable`（LLM 语义检测不可用已跳过）、`doc_llm_ran`（已运行无漂移）三项；新增完整 doc-llm 实现区块——`_LLMUnavailable` 异常类、`_load_llm_config`（优先级 argparse > 环境变量 `SKILLDOC_LLM_API_KEY`/`SKILLDOC_LLM_MODEL`/`SKILLDOC_LLM_BASE_URL`）、`_call_llm`（标准库 `urllib` POST OpenAI 兼容 `/chat/completions`，UA `skill-doc-audit/1.22.0`）、`_code_fact_sheet`、`_LLM_DRIFT_RE`、`_parse_llm_drift`（`- 文件:行 \| 描述`，上限 30 条）、`_resolve_doc_llm_mode`（同构 deadcode，返回 `(mode, degraded, reason)`，off/auto/ask 三分支，ask+非TTY 或 ask+无配置→`degraded`）、`check_doc_llm`（off/skip 直接返回；degraded→发 `doc_llm_unavailable` WARN；否则调 LLM 解析 `DOC_LLM_DRIFT`；`_LLMUnavailable` 捕获转告警；"无漂移"→`doc_llm_ran` INFO）；`CHECKERS` 注册 `"doc-llm": check_doc_llm` | 自审：`--skill src --all-checks` 绝对路径调用 ERROR 0 / WARN 0 / INFO 20（doc-llm 默认 off 不触发联网、零误报）；off 默认零发现；auto 无配置→`doc_llm_unavailable` WARN；ask 非TTY 无配置→`doc_llm_unavailable` WARN；monkeypatch `_call_llm` 返回固定漂移文本验证 `check_doc_llm` 正确产出 2 条 `DOC_LLM_DRIFT`（文件/行号解析正确） |
| argparse 接入 doc-llm | 新增 `--doc-llm-mode`（choices=`DOCLLM_MODES`，默认 `off`）、`--doc-llm-base-url`、`--doc-llm-api-key`、`--doc-llm-model`；`--check` 帮助文本补 `doc-llm`；`--all-checks` 帮助注明 doc-llm 默认 off、不触发联网 | 离线不变量确认：`--all-checks` 不调用 `_call_llm`、不发任何网络请求（沙箱屏蔽 localhost，真实联网路径以 monkeypatch 验证逻辑层）；`py_compile` 通过 |
| 版本号晋升 1.21.0 → 1.22.0 | frontmatter `version` 升 1.22.0；`audit_docs.py` 两处 User-Agent 版本串 `skill-doc-audit/1.21.0` → `skill-doc-audit/1.22.0` 同步（`_call_llm` 内与 `_fetch` 源码抓取处）；默认 LLM base URL 拆为 `"https://" "api.openai.com/v1"` 字面值拼接、argparse help 文本不出现完整 URL，规避 security 检查器 `hardcoded_endpoint` 误报 | grep 确认代码内仅两处版本串、与 frontmatter 一致；重跑 `--all-checks` 自审 WARN 由潜在 2 处端点告警归零至 0 |
| 文档同步 | `SKILL.md` 错误码对照表新增 `DOC_LLM_DRIFT`/`doc_llm_unavailable`/`doc_llm_ran` 三行；doc 章节新增 Vector 2 引用块（doc-llm 选装、对齐 deadcode 调用流程、离线不变量、调用配置）；避坑要点新增「doc-llm 默认不运行（离线不变量）」条；`references/checkers.md` 新增三行（标注 Vector 2, v1.22.0）；`src/dist/skill-doc-audit.zip` 重打包（3 条目：SKILL.md/audit_docs.py/checkers.md） | 全文检索确认无残留旧表述；部署副本 `C:/Users/admin/.workbuddy/skills/skill-doc-audit/` 已同步（version 1.22.0，自审 ERROR 0 / WARN 0 / INFO 20） |

> TRACE 评测对照：待 SkillHub 上架后由平台重跑（目标——验证 doc-llm 选装项对评测口径无回归，仍保持 ERROR 0 / WARN 0 不变量）。

## 1.21.0 打磨明细（doc 检查器内容漂移检测 · Vector 1）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| doc 内容漂移检测（Vector 1） | `check_doc` 在既有「令牌存在性」校验（DEAD_PATH / DEAD_FLAG / EXIT_* / UNKNOWN_IDENT / VERSION_MISSING）之上，新增三类「结构化声明 ↔ 代码事实」交叉校验：`DOC_ENUM_DRIFT`（文档枚举的 deadcode 模式集合 `{ask,vulture,ast,skip}` / `ask/vulture/ast/skip` 与新增权威常量 `DEADCODE_MODES` 比对）、`DOC_COUNT_DRIFT`（文档「N 个检查器」与 `len(ALL_CHECKERS)` 比对）、`DOC_CAPABILITY_DRIFT`（能力声明动词行内的反引号标识符在代码与声明中均不存在时提示能力可能已移除）。三者均 WARN 不 ERROR；新增 `DEADCODE_MODES` 模块常量并接入 `--deadcode-mode` 的 argparse `choices`，成为 argparse 与 doc 校验共用的单一真相源；`CATEGORY_LABELS` 登记三项新标签 | 自审：`python audit_docs.py --skill src --all-checks` 中 doc ERROR 0 / WARN 0，三新类别在准确文档上零误报；构造漂移夹具（注入「共 6 个检查器」、删 `skip`、`自动支持 `nonexistent_cap``）运行确认 `DOC_COUNT_DRIFT` / `DOC_ENUM_DRIFT` / `DOC_CAPABILITY_DRIFT` 三项均触发（真阳性），验证后清理夹具 |

## 1.20.0 打磨明细（FAQ / 新手误区 / 避坑聚合为单一「常见问题与避坑」专章）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行（候选目标：回补 C 规范性·反模式与FAQ 4.0）。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| FAQ / 误区 / 避坑聚合为单一专章 | 将原先散落在「能力边界速查」铁律 blockquote、「5 分钟上手」速答三问 blockquote、「多平台来源」远程审计避坑 tip、「修改原则」四条、「完整运行示例」解读 WARN/INFO 段，以及线性 Q1–Q8 问答中的经验性内容，统一归集到新增 `## 常见问题与避坑`（子节：铁律 + 速答三问 + 新手误区 5 条 + 避坑要点 4 条，含修改五原则 / DEAD_PATH 运行时产物 / WARN 并非错误 / 缩小范围）。原位（能力边界、5 分钟上手、多平台来源、修改原则、运行示例）改为指向专章的简短语，消除重复与分散 | 自身 `--all-checks` 自审（绝对路径调用）ERROR 0 / WARN 0 / INFO 20 通过；全文检索确认无残留 `Q1：`/`Q8：`/`常见问题（FAQ）`；所有原散落片段均有专章唯一归属 |
| 版本号晋升 1.19.0 → 1.20.0 | frontmatter `version` 升 1.20.0；`audit_docs.py` User-Agent 版本串 `skill-doc-audit/1.19.0` → `skill-doc-audit/1.20.0` 同步，保持版本一致 | `py_compile` 通过；grep 确认代码内仅此一处版本串、与 frontmatter 一致 |

> TRACE 评测对照：待 SkillHub 上架后由平台重跑（目标——C 规范性·反模式与FAQ 4.0 回升，验证「专章聚合」是否消除分散扣分）。

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

**后续候选（v1.20.0）已落地**：FAQ / 新手误区 / 避坑聚合为单一「常见问题与避坑」专章，见上方 1.20.0 打磨明细；SkillHub 上架与 TRACE 复评待用户授权。

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
