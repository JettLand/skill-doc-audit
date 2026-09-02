# skill-doc-audit 技能工程仓库

本仓库是 SkillHub 技能 **skill-doc-audit（技能文档审计）** 的源管理与发布工程仓库，并非技能本身。正式上架版本发布于 SkillHub（slug：`skill-doc-audit`）。

## 仓库布局
- `src/`：技能根目录（即发布包内容）
  - `src/SKILL.md`：技能定义与用法（SkillHub 据此生成技能主页）
  - `src/scripts/audit_docs.py`：核心静态体检脚本
  - `src/references/checkers.md`：检查器明细基准
  - （发布**不再产出** `src/dist/*.zip`：SkillHub 上架时自行重打包；本地制品无用，且残留在被发布目录内会被市场拒收）
- `icons/`：已选定技能图标
- `src/scripts/make_fixtures.py`、`src/scripts/self_validate.py`、`src/scripts/sync_deploy.py`、`src/scripts/dev_self_audit.py`：开发期维护工具（**dev-only，不进部署副本**）；`sync_deploy.py` 负责把 `src/` 的发布面同步到已安装的部署副本 `~/.workbuddy/skills/skill-doc-audit`；`dev_self_audit.py` 是开发模式自审计脚本（审计最新源码 + 开发文档漂移 + 部署副本同步校验）

## 本地开发 / 自测

> 开发模式完整文档见 [DEVELOPMENT.md](./DEVELOPMENT.md)（仅维护者；dev-only 工具、自审计 / CI / 未发布改动流程；不进部署副本）。

```bash
# 对技能源做全检查器自审计（应 0 ERROR，退出码 0）
python src/scripts/audit_docs.py --skill src --all-checks
# 多平台来源自测：克隆 GitHub 仓库并审计（应正常克隆+定位 SKILL.md+审计+清理临时目录）
python src/scripts/audit_docs.py --source github --ref JettLand/skill-doc-audit --check structure
# 多平台来源自测：经 skillhub CLI 拉取集市技能并审计
python src/scripts/audit_docs.py --source skillhub --ref skill-doc-audit --check structure
# 自校验（基于 tests/fixtures 跑确定性检查器，比对黄金快照；新环境 clone 后任意 CWD 可跑）
# 注：tests/fixtures 已由 .gitignore 排除（生成产物），git checkout 后由 self_validate 自动重建
python src/scripts/self_validate.py
# fixture 生成器（声明式 recipe，self_validate 的辅助套件；--baseline 还可重建黄金快照）
python src/scripts/make_fixtures.py              # 重建 tests/fixtures/
python src/scripts/make_fixtures.py --check      # 校验现有 fixtures 与 recipe 一致
python src/scripts/make_fixtures.py --baseline   # 重建 fixtures 后一并重建黄金快照 tests/examples/*.expected.json（人工显式动作）
# 开发模式自审计：审计最新源码发布面 + 开发文档(README/CHANGELOG)漂移 + 部署副本↔源码同步校验（应 0 ERROR，退出码 0）
python src/scripts/dev_self_audit.py
python src/scripts/dev_self_audit.py --strict   # CI 门禁：WARN 也计入失败
```

## 打包与发布
1. 修改 `src/` 内源文件，自测通过；
2. 提交并推送本仓库：`git add ... && git commit && git push origin main`（`commit` 会自动同步部署副本）；
3. **以目录发布**（市场自行重打包，**无需本地制品**）：

```bash
skillhub publish <技能目录> --changelog "..." --json
```

- 典型目录为已同步的部署副本（本机 `~/.workbuddy/skills/skill-doc-audit`；由 `sync_deploy` 经 `resolve_deploy_dir()` 解析，勿写死路径）。
- ⚠ 被发布目录内**不得含 `dist/` 或任何 `.zip`**，否则市场返回 `400 不允许的文件类型`；若部署副本残留旧 `dist/`，手动 `rm -rf <deploy>/dist` 一次（新 `sync_deploy.py` 不再生成，无需清理逻辑）。
- ⚠ 上架属对外公开动作，**须先取得用户明确授权**，不得自动 `publish`（版本变动时本地 CI 会就此发出 `[agent-todo]` 提示）。

## 部署副本同步（已纳入提交流程）

已安装的部署副本 `~/.workbuddy/skills/skill-doc-audit/` 必须与 `src/` 的提交态保持一致，否则会出现「源码改了、线上技能没更新」的漂移。本项目已把同步**自动化进 git 提交流程**：

- `src/scripts/sync_deploy.py`（dev-only）：把 `src/` 的发布面（SKILL.md / scripts/audit_docs.py / scripts/auditlib/** / references/checkers.md）字节级同步到部署副本，清理部署副本内的 `__pycache__`，最后校验一致性（**绝不删除发布面之外的文件**）。刻意**排除** dev 工具（make_fixtures.py / self_validate.py）与 `tests/`。
- `hooks/post-commit` + `git config core.hooksPath "D:/Agent Work/skill-doc-audit技能项目管理/hooks"`（**务必绝对路径**：相对 `../hooks` 会被 git 解析到仓库外的 `D:/Agent Work/hooks`，钩子永不触发）：每次 `git commit` 后自动运行 `sync_deploy.py`，提交即同步，无需手动记这一步。
- 手动触发（如换机器或 hook 未装）：`python src/scripts/sync_deploy.py`；可用环境变量 `SKILL_DEPLOY_DIR` 覆盖目标路径。

> 注：钩子仅在能找到 `python`/`python3` 时生效；找不到则仅打印提示、不阻塞提交。
> 发布到 SkillHub 仍走「打包与发布」第 3 步的 `skillhub publish`，与本地部署副本是两回事。

## 版本摘要
| 版本 | 说明 |
| --- | --- |
| 1.27.6 | **DEV_TOOLS 语法守卫 DRY 重构（复用 runtime 同款 py_compile）**：抽出 `auditlib.core.compile_python_file` 公共 helper，`runtime` 检查器与 `_guard_dev_tools` 守卫复用同一 `py_compile` 语法校验实现——手段复用、入口独立（runtime 报 `py_syntax` ERROR 阻断发布面；守卫仅 INFO 非阻断，命中即提示 agent 复核）。`runtime.py` 移除内联 `py_compile`、改调 helper，`_guard_dev_tools` 同步复用；三处源码改动，行为不变、输出格式与错误摘要一致。四处版本号一致 1.27.6 |
| 1.27.5 | **堵开发期工具盲区：新增 `dev_self_audit.py` 内置「DEV_TOOLS 语法守卫」**：全量审计只扫发布面、8 个 dev 工具被排除集剔除，成为唯一无自动化扫描的盲区；新增 `_guard_dev_tools()` 对每个 dev 工具单独 `py_compile` 兜底语法关，命中即打印 `[dev-tools] ⚠` 并追加 `[建议]` 非阻断项（不升退出码、不拦 push），把改坏 dev 工具的崩溃风险提前暴露。`[agent-todo]` 维持现状。部署自审 `ERROR 0 / WARN 0` |
| 1.27.3 | **`[agent-todo]` 第 6 类触发条件修正（仅补丁号 z 变动）**：原第 6 类（doc + doc-llm 文档自审计）与第 5、7 类同在「次/主版本变动」触发块，存在重复——次/主版本已由第 7 类全量自审计（`--all-checks`，含 doc + doc-llm）覆盖。修正后第 6 类改为仅「补丁号（x.y.z 中 z）变动」触发，次/主版本不再重复提醒；`dev_market_bench.py check_bump` 与 `DEVELOPMENT.md` 指令清单、渲染样例同步。部署自审 `ERROR 0 / WARN 0` |
| 1.27.2 | **checkers.md 新增 examples 检查器「功能与风险详解」综合篇幅 + 新增 `[agent-todo]` 第 10 类常驻提交提醒**：examples 检查器补充五类检查覆盖 / 三档模式与默认姿态 / 安全红线 / 风险与局限 / 误报抑制机制的完整说明；check-bump 新增不依赖版本变动的常驻提醒——检测到未提交改动即提示立即本地 commit（防长期开发记忆漂移使 src 与部署副本 / 版本号脱节），`[建议]` 不阻断、不升退出码。部署自审 `ERROR 0 / WARN 0` |
| 1.27.1 | **用户文档版本叙述收敛 + 发布门禁强化**：删除 SKILL.md / references 内联版本里程碑叙述（如「v1.26.0 新增」），用户文档只描述当前能力本身；新增 `[agent-todo]` 第 9 类（版本变动时用户文档不写版本变动叙述，属开发者文档 CHANGELOG 职责）。部署自审 `ERROR 0 / WARN 0 / INFO 35` |
| 1.27.0 | **正向能力覆盖检查器 `DOC_CAPABILITY_MISSING`（doc 检查器增强）**：确定性捕捉「代码有、文档没写」的能力缺口——仅审计本框架技能（代码含 `ALL_CHECKERS`）时，注册的每个检查器名 / 用户面向 CLI 参数须出现在 SKILL.md 或 references 文档中，否则 `WARN` 阻断发布（与 `DOC_CAPABILITY_DRIFT` 正反向对称）；doc-llm dossier 同步新增「正向覆盖缺口」预分析段，把代码有文档缺的项直接列为比对要点，免去 agent 自行穷举对账（正是漏检的元凶）。另含前序 dev-only 收口（同步钩子移除自动打包、上架授权 `[agent-todo]` 第 8 类）。部署自审 `ERROR 0 / WARN 0 / INFO 35` |
| 1.26.0 | **泛用版 examples 检查器（检查器 #9）**：对任意技能文档里的命令示例做静态校验——示例引用的脚本文件是否存在（`EXAMPLE_TARGET_MISSING`）、传给脚本的参数是否声明（`EXAMPLE_FLAG_UNKNOWN`）、示例调用的外部 CLI 是否声明（`EXAMPLE_EXT_CMD`）、是否含危险/不可逆命令（`EXAMPLE_DANGEROUS`）；默认纯静态（零执行/零网络/零 token），`--examples-mode run` 方在受限沙箱试运行带 `expected` 标注的示例（白名单解释器+技能内脚本+超时保护，绝不执行任意 shell）。新增 `examples-skill` fixture 与黄金快照，`self_validate` 的 `DETERMINISTIC` 收口 examples。部署自审 `ERROR 0 / WARN 0 / INFO 34` |
| 1.25.7 | **TRACE 评测整改（文档表述补强，补丁级）+ 市场质量基准实测器固化收口**：针对部署副本 TRACE 自评（4.7/优秀）中 <5.0 的 5 子项做文档补强——①「多平台来源」补「本地审计完全离线、零外部依赖，仅 github/skillhub 需外部 CLI、url 零 CLI」（T1）；②「能力边界速查」第三列补本技能特有示例「安全设计的合理性（静态规则 vs LLM、密钥是否明文落盘）」（A1）；③「常见问题与避坑」顶部加题号锚点导航（C1）；④「deps」补 `target_platform` 显式声明决策指引（E2）；⑤ 跨平台矩阵/生态级健康度汇总（E3 增值）已具文档无需改动。同时收口 `未发布改动`：市场质量基准实测器（质量分取样）固化落地。部署自审 `ERROR 0 / WARN 0 / INFO 33` |
| 1.25.6 | **跨平台黄金快照比对修复 + CI Node 20 警告消除 + 工程化行尾统一**：`core.finding()` 出口把 `file`/`message`/`ref` 反斜杠归一为正斜杠，根治 ubuntu CI 上 `self_validate` 黄金快照比对失败（commit `c4f276c`）；`.github/workflows/dev-qa.yml` 两 job `actions/checkout@v4`→`@v5`、`actions/setup-python@v5`→`@v6` 消除 Node 20 废弃警告（commit `23986cc`）；新增 `.gitattributes`（`* text=auto eol=lf` + `*.zip`/`*.png` binary）统一文本行尾、根除 Windows 上 `LF will be replaced by CRLF` 提示（commit `0f78eb5`）。三项均纯工程/维护类，部署自审 `ERROR 0 / WARN 0 / INFO 32` |
| 1.25.5 | **缺失引用去重降噪 + 检查器执行回执 + doc-llm 注册键修复 + 扫描范围收敛 + 文档三分式固化**：`dedupe_findings()` 按引用路径归并 `doc`(DEAD_PATH)/`structure`(broken_ref)/`runtime`(script_ref_missing) 与 `doc` 内重复 `EXTERNAL_REF` 为单条（保留最高严重级 + `dedup` 溯源字段），ERROR/WARN 计数不再虚高；检查器执行回执根治「静默落空却显通过」；doc-llm 注册键 bug 修复（此前从未真跑）；doc/doc-llm 默认扫 `references/*.md`、开发者模式递归扫全部 `.md`。`self_validate` 黄金快照重基线全 PASS，部署自审 `ERROR 0 / WARN 0 / INFO 48` |
| 1.25.4 | **文档三分式重构 + 内联版本号收敛 + 开发链路固化**：`SKILL.md` 精简为用户模式（能力地图 + 去重大段 blockquote 改指向 `checkers.md`）、`checkers.md` 收为完整参考单一真相源、新增 `DEVELOPMENT.md` 收纳开发模式（dev-only，不进部署副本）；Q1 收敛文档内联版本号标注（保留行为解释型、删纯里程碑）；部署副本同步自动化进 git 提交流程（`sync_deploy.py` + `post-commit` 钩子）、新增 `dev_self_audit.py` 自审计脚本。文档级改动，部署自审 `ERROR 0 / WARN 0 / INFO 37` |
| 1.25.3 | **fixtures 移出版本管理 + make_fixtures 升级为整套重建工具**：`tests/fixtures/` 改由 `.gitignore` 排除（生成产物，clone 后由 self_validate 自动重建）；`make_fixtures.py` 新增 `--baseline`，可重建 fixtures 后一并重建黄金快照 `tests/examples/*.expected.json`（人工显式动作，正常校验流程不自动重建以免削弱回归护栏）。dev-only。部署自审 `ERROR 0 / WARN 0 / INFO 20` |
| 1.25.2 | **fixture 生成器作为 self_validate 辅助套件**：`tests/fixtures` 整体缺失时，`self_validate.py` 自动 `import make_fixtures` 并调用 `build()` 重建后继续校验，仅当 import/写盘失败时回退到手动提示；二者构成 coherent 自校验套件。dev-only（不进 dist/部署副本）。部署自审 `ERROR 0 / WARN 0 / INFO 20` |
| 1.25.1 | **fixtures 声明式 recipe 生成器（self_validate 技术兜底）**：新增 dev 工具 `make_fixtures.py`，将每个 fixture 的「手工创建过程」编码为 recipe（frontmatter + 文件内容），可字节级精确复刻 `tests/fixtures/`，支持 `--check` 校验与 `--out` 指定目录；`self_validate.py` 缺失 fixtures 时提示改用本生成器重建。与「从 golden 反推」的弱方案不同——recipe 复刻原始 fixture 本身（无损），golden 仍只作断言基准，不削弱回归严格性。dev-only（不进 dist/部署副本）。部署自审 `ERROR 0 / WARN 0 / INFO 20` |
| 1.25.0 | **audit_docs.py 模块化拆分 + 内置自校验工具 self_validate.py**：将 2491 行单体 `audit_docs.py` 拆为薄入口 + `auditlib/` 包（core/model/report/sources/cli + checkers/ 八检查器自注册）；新增开发期自校验工具 `self_validate.py`——基于 `auditlib` 对 `tests/fixtures` 跑确定性检查器、掩去绝对路径后比对 `tests/examples/*.expected.json` 黄金快照，`--baseline` 可重建快照，纯 `__file__` 解析仓库根、新环境 clone 后任意 CWD 可跑。部署自审 `ERROR 0 / WARN 0 / INFO 20` |
| 1.24.1 | **doc-llm 移除预览选项 + 全量校正 token 成本表述**：用户指出「agent 接手也会消耗 token（输入输出都消耗，输入为主），并非零额外成本」。据此删除 `preview` 模式（`DOCLLM_MODES` 由 `(off,agent,ask,preview)` 改为 `(off,agent,ask)`），删除 `_print_doc_llm_preview` 与 `--doc-llm-mode preview` 处理分支、AskUserQuestion 选项 3 及「前置步骤」流程；交互菜单精简为「1) 默认模式 / 2) 启用语义漂移检查（agent 介入，消耗额外 token）」；全量校正所有「零额外成本 / 不消耗用户 token」表述为「会占用 agent 自身推理 token（输入侧为主），但不向外部 LLM 服务付费」。部署自审 `ERROR 0 / WARN 0 / INFO 20` |
| 1.24.0 | **doc-llm 语义检测改由 agent 直接接手，彻底移除外部 LLM 依赖**：用户指出「凡用到外部 LLM 的地方都应改由 agent 接手，否则只会提高用户使用成本」。据此删除 `_call_llm`/`_load_llm_config`/`_LLMUnavailable`/`_parse_llm_drift` 及 `--doc-llm-api-key`/`--doc-llm-model`/`--doc-llm-base-url` 三个外部 LLM 参数，`DOCLLM_MODES` 由 `(off,auto,ask,preview)` 改为 `(off,agent,ask,preview)`；新增 `--doc-llm-mode agent`：脚本把 SKILL.md 全文 + 代码事实清单写成 dossier 并打印 `[doc-llm] AGENT_TAKEOVER: <path>` 哨兵，由 agent 用自身能力完成语义比对（会占用 agent 自身推理 token，输入侧为主，但不向外部 LLM 服务付费）。同步修正 **Agent 调用流程**：选项 3（预览）改为「前置步骤」——先展示 agent 将比对的材料与规模，再二次 `AskUserQuestion` 只给 1（默认）/2（agent 接手）让用户做最终选择（超时默认 1）。全量改写所有「依赖外部 LLM / 消耗额外 token」描述为「agent 直接接手 / 零额外成本」。部署自审 `ERROR 0 / WARN 0 / INFO 21` |
| 1.23.7 | **修复 `--doc-llm-mode preview` 不被 argparse 接受的 bug**：v1.23.5 起 Agent 约定 step 2 把预览映射为 `--doc-llm-mode preview`，但 choices 元组 `DOCLLM_MODES = ("off","auto","ask")` 不含 preview，CLI 直接报 `invalid choice`。预览此前只能经 `--doc-llm-mode ask` 的交互菜单选 3 进入——意味着 Agent 经 AskUserQuestion 收到用户选 3 后无法直接 CLI 调用，违背 step 2 承诺。代码修复：`DOCLLM_MODES` 增加 `"preview"`；`_resolve_doc_llm_mode` 加直返分支（不依赖 LLM 配置、零 token、不调用 LLM）；`--doc-llm-mode` 帮助补 preview 说明。同步校正 SKILL.md。实跑验证：preview 模式正确打印 SKILL.md 长度（26297 字符）+ 代码事实清单长度（1743 字符、预估 ~435 token），未调 LLM，零联网 |
| 1.23.2 | **doc 检查器补 doc-llm 引导描述**：在「能力边界」检查器清单的 `doc` 项补一句引导性描述——`doc` 覆盖结构化漂移（死引用/失效参数/退出码不符/枚举·数量·能力声明与代码不符），自由散文语义漂移由**独立的** `doc-llm` 检查器（与 `doc` 功能互补）以 agent 语义检测补足，便于读者在开头即建立「doc 与 doc-llm 的分工」认知。纯文档增补，版本号补丁级，部署自审 `[doc] ERROR 0 / WARN 0` |
| 1.23.1 | **确立核心设计原则**：新增头条「设计原则（核心约束）」——`默认模式零依赖，但绝不替用户决定`：默认即零依赖（纯脚本/不联网/零 token）、绝不替用户决定（涉及外部依赖能力的取舍必须显式交还用户、超时回退默认）、透明兜底（无法询问宁可显著标注跳过也不静默代决）；统领 doc-llm 与 deadcode 的交互式取舍。纯文档确立，部署自审 `[doc] ERROR 0 / WARN 0` |
| 1.23.0 | **doc-llm 默认问询 + 纳入全量检测**：①`--doc-llm-mode` 默认改 `ask`，`--check doc-llm` 不传 mode 即弹三选项菜单（默认/增强/预览，30s 超时回退）；②doc-llm 列入 `ALL_CHECKERS`，`--all-checks` 含 LLM 语义漂移问询——交互弹菜单、非交互记 INFO `doc_llm_skipped`（保全量 WARN 0 不变量）、显式传入未运行则 WARN `doc_llm_unavailable`；离线不变量（绝不自动联网）不变 |
| 1.22.1 | **doc-llm `ask` 模式改为显式三选项交互（绝不替用户决定）**：按用户要求，`--doc-llm-mode ask` 在交互终端呈现实选项——`1) 默认模式`（纯脚本，零依赖，0 token）/`2) 增强模式`（启用 LLM 语义检测，依赖外部 LLM 服务、消耗额外 token）/`3) 预览代价`（仅展示将发送给 LLM 的内容与预估 token，不实际调用）；**30 秒超时或无输入一律回退默认模式**。非交互（自动化）环境无法询问 → 回退默认并显著告警（`doc_llm_unavailable`），不再自动复用环境变量配置静默联网；离线不变量（默认 off、不进 `--all-checks`、绝不自动联网）不变。自身 `--all-checks` 自审 ERROR 0 / WARN 0 |
| 1.22.0 | **doc-llm 选装 LLM 语义漂移检测（离线不变量）**：对齐用户「调取流程参考 deadcode 检查器」要求，将 deadcode 的「`(mode, degraded)` 元组 + 降级显著告警 + argparse `choices` 单一真相源」范式复刻到 doc 检查器，新增选装 `doc-llm` 检查器——`_resolve_doc_llm_mode` 同构返回 `(mode, degraded, reason)`（`off`/`auto`/`ask` 三分支，ask+非TTY 或 ask+无配置→`degraded`），降级发 `doc_llm_unavailable` WARN（对应 `precision_degraded` 显著告警）；`_call_llm` 用纯标准库 `urllib` 调 OpenAI 兼容 `/chat/completions`，`_code_fact_sheet` 抽轻量代码事实清单、`_parse_llm_drift` 按 `- 文件:行 | 描述` 解析（上限 30 条）并登记 `DOC_LLM_DRIFT`；默认 `off`、`--all-checks` 不纳入、绝不自动联网（离线不变量）；凭据经 argparse > 环境变量 `SKILLDOC_LLM_API_KEY`/`SKILLDOC_LLM_MODEL`/`SKILLDOC_LLM_BASE_URL`，默认 URL 拆字面值避免 `hardcoded_endpoint` 误报。自身 `--all-checks` 自审 ERROR 0 / WARN 0 |
| 1.21.0 | **doc 检查器「内容漂移」检测（确定性·零依赖）**：针对用户指出的 doc 检查器只能做「令牌存在性」匹配、漏检内容漂移的盲区，新增三类「结构化声明 ↔ 代码事实」交叉校验——`DOC_ENUM_DRIFT`（文档枚举集合如 deadcode 模式与 `DEADCODE_MODES` 不符）、`DOC_COUNT_DRIFT`（「N 个检查器」与 `len(ALL_CHECKERS)` 不符）、`DOC_CAPABILITY_DRIFT`（能力声明行内反引号标识符在代码不存在）；三者均 WARN 不 ERROR。新增模块常量 `DEADCODE_MODES` 成为 argparse 与 doc 校验共用的单一真相源。自审零误报、构造漂移夹具验证三检均触发真阳性 |
| 1.20.0 | **FAQ / 新手误区 / 避坑聚合为单一「常见问题与避坑」专章（C 规范性收口）**：将原先散落在「能力边界速查」铁律、「5 分钟上手」速答三问、「多平台来源」远程审计避坑、「修改原则」、「完整运行示例」解读与线性 Q1–Q8 问答中的经验性内容，统一归集到 `## 常见问题与避坑`（铁律 + 速答三问 + 新手误区 5 条 + 避坑要点 4 条），原位改为指向专章的简短语，消除重复与分散，回应评测「FAQ/避坑分散、无集中章节」的扣分；frontmatter 与代码 UA 版本串同步升 1.20.0；自身 `--all-checks` 自审 ERROR 0 / WARN 0 |
| 1.19.0 | **deadcode 非 TTY 精度降级可见化 + 显式 vulture 自动安装（代码层修复 R 可靠性退步）**：根因——v1.18.1 的 SKILL.md 约定修复对评测器自动化调用「不可见」，评测仍点名「deadcode 自动化精度下降无提示」。本版在代码层修复：`_resolve_deadcode_mode` 返回 `(mode, degraded)` 元组，非 TTY 且未装 vulture、或显式 vulture 但缺失、或交互超时无输入时均标记 `degraded=True`，并在报告中发出 `precision_degraded` WARN（明确标注精度降级与解决建议），使降级对自动化评测/调用方可见、不再无提示蒙混；**新增 `_try_install_vulture()`：当用户显式 `--deadcode-mode vulture` 或交互选了 vulture 但环境缺库时，先尝试 `pip install vulture`，装好即用高精度、装不上才降级告警，尊重用户显式意图；`ast`/`skip` 与 ask 非 TTY 自动回退不触发安装**，避免自动化场景发起意外网络请求。vulture 已装仍静默走高精度（不提示）。自身 `--all-checks` 自审 ERROR 0 / WARN 0，降级路径经模拟样本验证确实产出 `precision_degraded` 警告 |
| 1.18.1 | **Agent 执行 deadcode 精度模式修复（非能力变更，补丁级）**：根因——`deadcode` 默认 `ask` 的「询问」依赖人类 TTY 的 `input()`，Agent 经管道调用（stdin 非 TTY）时脚本静默降级为 `ast`，用户精度选择权被吞掉，与设计初衷相悖。新增「Agent 执行约定（deadcode 精度模式必须显式决策）」专节：Agent 跑 `--all-checks` 前须先探测 vulture，未装则主动用 AskUserQuestion 询问用户三选一（装 vulture/直接 ast/跳过），并以 `--deadcode-mode` 显式传入，绝不依赖 `ask` 默认；同步在「能力边界」deadcode 项与「5 分钟上手」补充 Agent 上下文提示。仅改文档与一处版本常量，无审计口径变化；自身 `--check doc` 自审 ERROR 0 / WARN 0 |
| 1.18.0 | **回应评测误报与文档短板**：①检查器误报修复——`hardcoded_path` 上下文感知（跳过表格/引用块/示例性描述行）、`encoding_sep` 排除 `urlopen`/`io.open`/`os.open` 等非文件 `open`（如 `--source url` 的 `urllib.request.urlopen` 不再误报）、`hardcoded_endpoint` 对 `raw.githubusercontent.com` 等 url 源规范主机白名单放行；自审 WARN 由 4 降至 1（仅剩审计 `src/` 目录名≠技能名的 harness 假象，部署副本不触发）；②文档增强——新增「5 分钟上手（极简路径）」「能力边界速查」「完整运行示例（真实输出+解读）」「新手常见误区 FAQ（Q6–Q8）」，并引导远端审计优先用 `--source url`（零外部 CLI、绕开 git clone 网络限制，回应国内适配性扣分）与明确 vulture 可选自动降级 ast。回归自审 ERROR 0 / WARN 1 / EXIT 0 |
| 1.17.0 | **泛化来源 `--source url`（零依赖直抓任意 SKILL.md）**：新增 `url` 来源，用标准库 `urllib` 直接抓取 SKILL.md 文本到临时目录后照常审计，无需 `git`/`skillhub` 等外部 CLI、对 OS 透明；`github.com` blob 链接自动转 `raw.githubusercontent.com`；抓取 SKILL.md 后自动补全其显式引用的 `scripts/` 与 `references/` 文件，使远程单文件技能与本地克隆等价，避免「引用缺失」刷屏（单次补全长上限 50）。审计能力格式无关，故加来源只加「抓取适配器」、不增加审计口径。`SOURCES` 注册 `url`，`--source`/`--ref` 帮助文本同步。自审 0 ERROR、WARN 维持 4 无回归；url 源实测（抓取本仓库已发布 SKILL.md + 引用补全）ERROR 0 / WARN 2 / EXIT 0 |
| 1.16.0 | **Phase 7 ⑤落地·agentskills 全生态枢纽标注 + generic 兜底目标 + 跨平台证明**：①文档标注 `--target agentskills`/`cursor-plugin` 即 Agent Skills 开放标准（agentskills.io），一次转译可被 40+ 工具（Claude Code、Cursor、Gemini CLI、Codex、Copilot、Windsurf、Kiro、OpenCode、Cline、Roo Code 等）直接消费；③新增 `generic` 降级兜底目标（`--target` 枚举扩展），仅保留 name/description，报告前置「⚠ 高损失」警告并提示优先用 agentskills/cursor-plugin；补全「跨平台可移植性证明」专节（纯标准库/零第三方依赖、无平台专属 API 实际调用、portability 自检 0 OS 级发现）。自审 0 ERROR、WARN 维持基线 2 无回归 |
| 1.15.0 | **Phase 7 跨格式转译报告（只读预览·不落盘）**：在 Phase 5/6 底座（`SkillModel`+`FMT_CAPS`/`EQUIV`+`build_portability_matrix`）之上新增 `--report translate --target <fmt>`，把「检测/矩阵」升级为「可预览转译方案」——但**仅出报告、不落盘**，守住本技能「只读扫描」立身之本。输出 frontmatter 字段映射表（保留/降级/丢失逐项标注）+ 目标 SKILL.md 脚手架预览（仅 frontmatter+标题骨架，正文散文不翻译留人工）；`--target` 支持 `workbuddy`↔`agentskills`/`claude-code`/`cursor-plugin` 双向；`--verify` 做内存往返保真（emit→re-parse→比对），依矩阵给出 `RECOVERABLE`/`LOSSY`/`IRREVERSIBLE` 结论；`--json` 附 `translate` 字段。决策：①仅报告不生成文件 ②仅 frontmatter+脚手架 ③先支持 workbuddy↔agentskills/claude-code/cursor-plugin ④`--verify` 一并纳入。自审 0 ERROR、WARN 维持基线 2 无回归 |
| 1.14.0 | **Phase 8 生态级批量审计 + 供应链安全**：`--ref` 支持逗号分隔多仓库批量审计（`--source github --ref a/b,c/d`）；`security` 新增 `hardcoded_endpoint`（硬编码远端地址，仅代码上下文才报，排除文档/注释示例 URL 与检查器自身源码误报）与 `dynamic_import`（反射式模块加载）两项供应链启发式；新增 `--report health` 生态健康度汇总（`--json` 多技能时自动附带 `health_summary`）。契合 13.4% 技能严重安全问题的行业痛点。自审 0 ERROR、WARN 维持基线 2 无回归 |
| 1.13.0 | **Phase 6 跨格式可移植性矩阵（核心价值）**：在 Phase 5 `SkillModel` 之上以开放标准 `agentskills` 为枢纽构建字段级能力映射（`FMT_CAPS`/`EQUIV`），对任意技能生成「源格式 → 各目标格式」P/D/L 损失矩阵；新增 `lossy_port` 发现（仅当技能显式声明跨 Agent 目标时触发，`lost`→WARN、`degraded`→INFO）；新增 `--report portability-matrix` 专项报告；并修复 `_parse_frontmatter_list` 内联列表 `[a, b]` 括号未剥离导致 `target_agent` 归一化失效的缺陷。自审 0 ERROR、WARN 维持基线 2 无回归 |
| 1.12.0 | **Phase 5 跨 Agent 格式归一化内核**：新增 `detect_format()` 按 frontmatter 特征推断技能格式（workbuddy/agentskills/claude-code/cursor-mdc/generic），并构建统一 `SkillModel`（name/description/fmt/platform/target_platform/target_agent/tools/license/version/extra）；`analyze_skill` 返回结果新增 `format` 与 `skill_model` 字段，供各检查器与后续 Phase 6 矩阵 / Phase 7 转译消费。格式判定「按特征推断」而非硬锁枚举，延续 v1.11.0 自由列表原则以防生态演进漏判。自审 0 ERROR、WARN 无回归 |
| 1.11.1 | **portability #6 行为修正**：移除 `agent_coupling` 对 `workbuddy` 的抑制——本 skill 自身亦开发跨平台/跨 Agent 能力，故 WorkBuddy 目标的耦合提示同样有价值，不再免报。新口径：声明跨 Agent 目标（不含 `workbuddy`，如 `claude-code`/`cross-agent`）但仍含 WorkBuddy 耦合→WARN；其余（未声明/声明含 `workbuddy`/推断 `workbuddy`）→均 INFO 提示。文档同步（SKILL.md/checkers.md/README） |
| 1.11.0 | **Phase 4 跨 Agent 分发 + Schema Normalizer**：新增 `target_agent` 字段轴（自由列表，`compatibility` 映射，按 mcp__/`.workbuddy` 信号推断 workbuddy），#6 `agent_coupling` 可按字段抑制（声明 workbuddy）/升级（声明跨 Agent 目标仍含 WorkBuddy 耦合→WARN）；`deps.platform_undeclared` 由散文扫描升级为读取结构化 `target_platform`；Schema Normalizer 支持 Claude Code/Cursor 等开放标准技能——YAML 列表式 `allowed-tools` 解析、`version`/`license` 检查平台感知（外部平台不强制 version）。经 `--source github --ref anthropics/skills` 真实外部仓库验证无 version/license 误报洪泛 |
| 1.10.0 | **portability 检查器组（跨平台可移植性）**：新增第 7 个检查器 `portability`，已纳入 `--all-checks` 默认集；6 类全做（硬编码绝对路径 / 启动目录依赖 / 平台专属 shell / 解释器锁 / 编码分隔符假设 / Agent 平台耦合）；按 SKILL.md 的 `target_platform` 字段豁免对应平台项（fire iff 声明平台∩breaks_on 非空），全 WARN/INFO 不报 ERROR；#6 Agent 耦合为 INFO 咨询（暂不加 `target_agent` 字段，列入 Phase 4 跨 Agent 分发待办） |
| 1.9.0 | **多平台来源抽象（--source）**：新增 `github` / `skillhub` 来源，经 `git clone --depth 1` / `skillhub install` 把远程/集市技能落到临时目录后照常审计；`analyze_skill` 核心逻辑零改动；新增 `--ref` / `--keep-temp` 参数；支持仓库内嵌套/多技能自动定位 SKILL.md |
| 1.8.2 | 文档补全：SKILL.md 错误码对照表补全额 deadcode 检查器 5 个 category（`unused_def`/`unused_import`/`unreachable`/`orphan_asset`/`vulture`），与 `references/checkers.md` 权威表对齐（原速查表漏列 deadcode）；dist 同步重打包 |
| 1.8.1 | 交互体验改进：deadcode 询问超时 10s→30s（给用户更充裕思考时间）；`ask` 模式检测到 vulture 已安装时直接采用高精度模式、不再交互询问；修复 vulture API 调用；vulture 模式去重（不重复报 AST 项）；`# keep` 白名单统一作用于 vulture 分支；vulture 异常改 stderr 告警不静默；ast/vulture 分工明确。`doc` 检查器 `UNKNOWN_IDENT` 误报修复：自动识别 frontmatter `allowed-tools`/`tools` 与文档中的 `mcp__*__<name>` 外部工具名并跳过，不再对 MCP/Agent 类技能刷海量误报；该检查由 ERROR 降级为 WARN（本就是「可能拼写有误」的猜测），并按标识符去重。**同窗口内追加三项打磨**：① 死代码 `unused_def` 增加跨文件引用感知（多文件技能「本文件定义、他文件调用」不再误报），`orphan_asset` 增加 import 模块名豁免；② 代码/配置文件扫描扩展至多语言（.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua 等），含多语言硬编码密钥检测；③ 新增 `--preview` 检查预览（只列出将运行的检查器与将扫描的文件，不产出发现，退出码 0），缓解「参数偏多/文档偏长」的首次使用门槛 |
| 1.8.0 | **deadcode 投产打磨**：跨文件引用感知 + 多语言扫描覆盖（.ts/.go/.rs 等）；新增 `--preview` 检查预览；`UNKNOWN_IDENT` 误报修复（ERROR→WARN，按标识符去重）；文档渐进式披露（快速开始/速查表） |
| 1.7.0 | deadcode 并入 --all-checks 默认集；运行前按 --deadcode-mode 询问精度（vulture/ast/skip），超时回退 ast |
| 1.6.0 | 新增 deadcode 死代码检查器（--check deadcode 启用，默认不随 --all-checks） |
| 1.5.3 | 检查项中文标签（category_cn）+ 错误码对照表，报告自解释；异常处理 4.3→4.8 |
| 1.5.2 | 进阶用法示例 + 报错提示通俗化 |

> 各版本的「改动 + 验证」明细见 [CHANGELOG.md](./CHANGELOG.md)。
