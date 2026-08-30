# skill-doc-audit 技能工程仓库

本仓库是 SkillHub 技能 **skill-doc-audit（技能文档审计）** 的源管理与发布工程仓库，并非技能本身。正式上架版本发布于 SkillHub（slug：`skill-doc-audit`），平台综合评测 **4.8/5（优秀）**。

## 仓库布局
- `src/`：技能根目录（即发布包内容）
  - `src/SKILL.md`：技能定义与用法（SkillHub 据此生成技能主页）
  - `src/scripts/audit_docs.py`：核心静态体检脚本
  - `src/references/checkers.md`：检查器明细基准
  - `src/dist/skill-doc-audit.zip`：可发布制品
- `icons/`：已选定技能图标
- `backups/`：本地编辑期快照，不进版本库，仅留本机

## 本地开发 / 自测
```bash
# 对技能源做全检查器自审计（应 0 ERROR，退出码 0）
python src/scripts/audit_docs.py --skill src --all-checks
# 多平台来源自测：克隆 GitHub 仓库并审计（应正常克隆+定位 SKILL.md+审计+清理临时目录）
python src/scripts/audit_docs.py --source github --ref JettLand/skill-doc-audit --check structure
# 多平台来源自测：经 skillhub CLI 拉取集市技能并审计
python src/scripts/audit_docs.py --source skillhub --ref skill-doc-audit --check structure
```

## 打包与发布
1. 修改 `src/` 内源文件，自测通过；
2. 重新打包制品为 `src/dist/skill-doc-audit.zip`（含 SKILL.md / audit_docs.py / checkers.md）；
3. 经 SkillHub CLI 发布：`skillhub publish src/dist/skill-doc-audit.zip --version x.y.z --changelog "..."`；
4. 提交并推送本仓库：`git add ... && git commit && git push origin main`。

## 版本与评测
| 版本 | 综合评分 | 说明 |
|---|---|---|
| 1.5.2 | 4.7/5 优秀 | 进阶用法示例 + 报错提示通俗化 |
| 1.5.3 | 4.8/5 优秀 | 检查项中文标签（category_cn）+ 错误码对照表，报告自解释；异常处理 4.3→4.8 |
| 1.6.0 | 4.8/5 优秀 | 新增 deadcode 死代码检查器（--check deadcode 启用，默认不随 --all-checks） |
| 1.7.0 | 待复评 | deadcode 并入 --all-checks 默认集；运行前按 --deadcode-mode 询问精度（vulture/ast/skip），超时回退 ast |
| 1.8.0 | 已发布（平台审核中） | deadcode 投产打磨：
| 1.8.1 | 已发布 | 交互体验改进：deadcode 询问超时 10s→30s（给用户更充裕思考时间）；`ask` 模式检测到 vulture 已安装时直接采用高精度模式、不再交互询问 |修复 vulture API 调用；vulture 模式去重（不重复报 AST 项）；`# keep` 白名单统一作用于 vulture 分支；vulture 异常改 stderr 告警不静默；ast/vulture 分工明确。`doc` 检查器 `UNKNOWN_IDENT` 误报修复：自动识别 frontmatter `allowed-tools`/`tools` 与文档中的 `mcp__*__<name>` 外部工具名并跳过，不再对 MCP/Agent 类技能刷海量误报；该检查由 ERROR 降级为 WARN（本就是「可能拼写有误」的猜测），并按标识符去重。**同窗口内追加三项打磨**：① 死代码 `unused_def` 增加跨文件引用感知（多文件技能「本文件定义、他文件调用」不再误报），`orphan_asset` 增加 import 模块名豁免；② 代码/配置文件扫描扩展至多语言（.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua 等），含多语言硬编码密钥检测；③ 新增 `--preview` 检查预览（只列出将运行的检查器与将扫描的文件，不产出发现，退出码 0），缓解「参数偏多/文档偏长」的首次使用门槛 |
| 1.8.2 | 已发布（平台审核中） | 文档补全：SKILL.md 错误码对照表补全额 deadcode 检查器 5 个 category（`unused_def`/`unused_import`/`unreachable`/`orphan_asset`/`vulture`），与 `references/checkers.md` 权威表对齐（原速查表漏列 deadcode）；dist 同步重打包 |
| 1.9.0 | 已发布（平台审核中） | **多平台来源抽象（--source）**：新增 `github` / `skillhub` 来源，经 `git clone --depth 1` / `skillhub install` 把远程/集市技能落到临时目录后照常审计；`analyze_skill` 核心逻辑零改动；新增 `--ref` / `--keep-temp` 参数；支持仓库内嵌套/多技能自动定位 SKILL.md |
| 1.10.0 | 已发布（平台审核中） | **portability 检查器组（跨平台可移植性）**：新增第 7 个检查器 `portability`，已纳入 `--all-checks` 默认集；6 类全做（硬编码绝对路径 / 启动目录依赖 / 平台专属 shell / 解释器锁 / 编码分隔符假设 / Agent 平台耦合）；按 SKILL.md 的 `target_platform` 字段豁免对应平台项（fire iff 声明平台∩breaks_on 非空），全 WARN/INFO 不报 ERROR；#6 Agent 耦合为 INFO 咨询（暂不加 `target_agent` 字段，列入 Phase 4 跨 Agent 分发待办） |
| 1.11.0 | 已实现待发布（等用户命令） | **Phase 4 跨 Agent 分发 + Schema Normalizer**：新增 `target_agent` 字段轴（自由列表，`compatibility` 映射，按 mcp__/`.workbuddy` 信号推断 workbuddy），#6 `agent_coupling` 可按字段抑制（声明 workbuddy）/升级（声明跨 Agent 目标仍含 WorkBuddy 耦合→WARN）；`deps.platform_undeclared` 由散文扫描升级为读取结构化 `target_platform`；Schema Normalizer 支持 Claude Code/Cursor 等开放标准技能——YAML 列表式 `allowed-tools` 解析、`version`/`license` 检查平台感知（外部平台不强制 version）。经 `--source github --ref anthropics/skills` 真实外部仓库验证无 version/license 误报洪泛 |
| 1.11.1 | 已实现待发布（等用户命令） | **portability #6 行为修正**：移除 `agent_coupling` 对 `workbuddy` 的抑制——本 skill 自身亦开发跨平台/跨 Agent 能力，故 WorkBuddy 目标的耦合提示同样有价值，不再免报。新口径：声明跨 Agent 目标（不含 `workbuddy`，如 `claude-code`/`cross-agent`）但仍含 WorkBuddy 耦合→WARN；其余（未声明/声明含 `workbuddy`/推断 `workbuddy`）→均 INFO 提示。文档同步（SKILL.md/checkers.md/README） |
| 1.12.0 | 已实现待发布（等用户命令） | **Phase 5 跨 Agent 格式归一化内核**：新增 `detect_format()` 按 frontmatter 特征推断技能格式（workbuddy/agentskills/claude-code/cursor-mdc/generic），并构建统一 `SkillModel`（name/description/fmt/platform/target_platform/target_agent/tools/license/version/extra）；`analyze_skill` 返回结果新增 `format` 与 `skill_model` 字段，供各检查器与后续 Phase 6 矩阵 / Phase 7 转译消费。格式判定「按特征推断」而非硬锁枚举，延续 v1.11.0 自由列表原则以防生态演进漏判。自审 0 ERROR、WARN 无回归 |
| 1.13.0 | 已实现待发布（等用户命令） | **Phase 6 跨格式可移植性矩阵（核心价值）**：在 Phase 5 `SkillModel` 之上以开放标准 `agentskills` 为枢纽构建字段级能力映射（`FMT_CAPS`/`EQUIV`），对任意技能生成「源格式 → 各目标格式」P/D/L 损失矩阵；新增 `lossy_port` 发现（仅当技能显式声明跨 Agent 目标时触发，`lost`→WARN、`degraded`→INFO）；新增 `--report portability-matrix` 专项报告；并修复 `_parse_frontmatter_list` 内联列表 `[a, b]` 括号未剥离导致 `target_agent` 归一化失效的缺陷。自审 0 ERROR、WARN 维持基线 2 无回归 |
| 1.14.0 | 已实现待发布（等用户命令） | **Phase 8 生态级批量审计 + 供应链安全**：`--ref` 支持逗号分隔多仓库批量审计（`--source github --ref a/b,c/d`）；`security` 新增 `hardcoded_endpoint`（硬编码远端地址，仅代码上下文才报，排除文档/注释示例 URL 与检查器自身源码误报）与 `dynamic_import`（反射式模块加载）两项供应链启发式；新增 `--report health` 生态健康度汇总（`--json` 多技能时自动附带 `health_summary`）。契合 13.4% 技能严重安全问题的行业痛点。自审 0 ERROR、WARN 维持基线 2 无回归 |

> 评测由 SkillHub 平台在每次发布后自动重跑（TRACE 五维）。

## 1.8.0 打磨明细（发布窗口内就地修正）

| 打磨项 | 改动 | 验证（均通过，0 回归） |
|---|---|---|
| 死代码跨文件感知 | `check_deadcode` 预扫描全技能 `.py` 构建全局 `global_used` + `imported_modules`，`unused_def` 仅当全技能范围都未引用才报；`orphan_asset` 增加 import 模块名豁免 | `tests/fixtures/multifile`（a.py 定义 `shared_helper`、b.py 调用）不再误报 `unused_def`；真阳性 `EXIT_CODE_ONLY` 保留 |
| 多语言扫描覆盖 | `CODE_EXT` 由 `.py/.js/.sh/.ps1/.json` 扩展至含 `.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua` 等；`FILE_REF_RE`/`structure`/`runtime` 引用正则同步扩展 | `tests/fixtures/ts-skill` 的 `runGame` 不再误报 `UNKNOWN_IDENT`；`.ts` 内硬编码密钥被 `security` 抓到 |
| 检查预览 `--preview` | `main()` 新增 `--preview`：只打印将运行检查器 / deadcode 精度模式 / 文档存在性 / 将扫描文件清单 / 跳过的大文件，退出码 0 | `tests/fixtures/multifile --all-checks --preview` 退出码 0、列出 2 个文件、无发现 |
| `UNKNOWN_IDENT` 误报修复 | 提取 frontmatter `allowed-tools`/`tools` 与全仓库 `mcp__*__<name>` 标记为 `declared_tools` 并跳过；级别 ERROR→WARN；按标识符去重 | `weixin-minigame-helper` 原 57 ERROR → 0 ERROR；`godot-core`（MCP 技能）26 个外部工具名由 ERROR 降为 WARN（仍保留，提示作者在 frontmatter 声明）；真阳性 `tune_model` 仍报出 |
| 文档渐进式披露 | `SKILL.md` 新增「快速开始」小节（3 条核心命令 + 意图→命令速查表）；`--preview` 进入用法示例；`checkers.md` 新增「命令行参数速查」 | 文档偏长/参数偏多感知缓解 |

复测总览：`py_compile` 通过；自审 5 检查器 + `--all-checks` 均 0 ERROR；`dirty-skill` 14 类缺陷全命中 0 漏报；`tricky-clean` 0 误报；`--all` 扫已装技能 1.7s 无崩溃；市场随机抽检 6 技能无崩溃、`UNKNOWN_IDENT` 稳定为 WARN。

## 1.8.1 打磨明细（交互体验改进）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| deadcode 询问超时延长 | `_prompt_deadcode_mode` 超时 `th.join(10)`→`th.join(30)`，提示文案「10 秒内未选」→「30 秒内未选」，docstring 同步 | 单元验证 `th.join(30)` 生效、`th.join(10)` 已移除 |
| vulture 已装免询问 | `_resolve_deadcode_mode` 的 `ask` 分支先探测 `_vulture_module()`，已装则直接返回 `vulture` 高精度模式（打印「自动采用高精度模式（跳过询问）」），不再进入交互询问；未装仍走原逻辑（非 TTY→ast / TTY→询问 30s） | 单测：ask+vulture→`vulture`、ask+无 vulture(非 TTY)→`ast`、显式 vulture+无 vulture→`ast`(回退)；端到端 `--all-checks` 默认 ask + vulture 已装 → 自动高精度、不询问、跑完无崩 |

文档同步：SKILL.md / checkers.md 的能力描述与 `--deadcode-mode` 参数说明同步（「默认 ask：已装 vulture 则自动高精度」）；dist 已重打包（含最新源码）。

## 1.8.2 打磨明细（文档补全）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| SKILL.md 错误码对照表补全 | 「错误码对照表」新增 `### deadcode` 段，列出 deadcode 检查器全部 5 个 category（`unused_def`=WARN / `unused_import`=INFO / `unreachable`=WARN / `orphan_asset`=WARN / `vulture`=WARN），级别与 `checkers.md` 权威表一致，并附一行误报抑制说明 | 脚本比对 `CATEGORY_LABELS`（42 个）与 SKILL.md 速查表，缺口由 5（`unused_def`/`unused_import`/`unreachable`/`orphan_asset`/`vulture`）降为 0；`checkers.md` 权威表本就全覆盖 |

复测总览：`py_compile` 通过；自审 `--all-checks` 0 ERROR；错误码对照表与代码 `CATEGORY_LABELS` 完全一致（42/42）。

## 1.9.0 打磨明细（多平台来源抽象）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 来源抽象层 | 新增 `SkillSource` 基类 + `LocalSource` / `GithubSource` / `SkillhubSource` 三实现；`analyze_skill(skill_dir)` 签名与逻辑零改动。来源层只负责把远程/集市技能落地为本地临时目录，再交还路径 | 单元外：`--skill` / `--all` 行为与 1.8.2 完全一致（回归 0 变化） |
| `--source` / `--ref` / `--keep-temp` | `main()` 目标构建改为 `get_source(args.source).resolve(args.ref, args)`；`github` 经 `git clone --depth 1 [--branch]` 到 `tempfile.mkdtemp`；`skillhub` 经 `skillhub install <slug> --dir` 到临时目录；新增 `find_skill_dirs` 遍历定位含 `SKILL.md` 的目录（支持嵌套 `src/SKILL.md` 与一仓库多技能）；审计后默认 `shutil.rmtree` 清理，`--keep-temp` 保留并打印路径 | 端到端：`--source github --ref JettLand/skill-doc-audit --check structure` 克隆→定位 `src/SKILL.md`→审计→自动清理（退出码 0）；`--source skillhub --ref skill-doc-audit --check structure` 拉取→审计（退出码 0）；`--keep-temp` 临时目录留存可验证 |
| 健壮性 | `git` / `skillhub` 调用走 `subprocess` 列表参数（无 shell 注入）；克隆/安装失败捕获 `CalledProcessError` / `TimeoutExpired` / `FileNotFoundError` 并打印末行错误后退出码 2；`skillhub` 二进制经 `shutil.which` 解析全路径（Windows 上为 `skillhub.CMD`，规避裸名扩展名解析失败）；空结果（无 SKILL.md）也安全退出 | 缺参/克隆失败路径均优雅退出码 2，无堆栈泄漏 |
| 文档同步 | SKILL.md 新增「多平台来源」小节 + 快速开始速查表 2 行 + 用法示例；README 增加自测示例与 1.9.0 明细；模块 docstring 用法段补充 `--source` 示例 | — |

> 注：Phase 3（portability 检查器组）已于 v1.10.0 交付；Phase 4（跨 Agent 分发 + Schema Normalizer）已于 v1.11.0 交付。

## 1.10.0 打磨明细（portability 跨平台可移植性检查器）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| portability 检查器 | 新增 `check_portability(ctx)`：6 类全做（hardcoded_abs_path / cwd_dependence / platform_shell / interpreter_lock / encoding_sep / agent_coupling）；纯静态正则扫描 `ctx["code"]`，复用现有基建；注册进 `CHECKERS` + `ALL_CHECKERS`，零依赖可进默认集 | 自审本项目 `--all-checks` 仅剩 6 条 INFO `agent_coupling`（本项目确耦合 `.workbuddy`/allowed-tools，属真实提示非误报） |
| `target_platform` 豁免 | `analyze_skill` 从 frontmatter 提取 `target_platform` 注入 `ctx`；`_normalize_target_platform` 归一（空/未知/cross-platform/all/* → 全平台）；`_port_fire` 实现 `fire iff 声明平台∩breaks_on 非空`；`code` 扫描跳过注释行与自检令牌（SELF_REF_TOKENS/SCAN_SKIP_TOKENS），避免扫描器自身字符串误报 | 构造破损测试技能：Case A（无声明）7 WARN + 1 INFO 全命中；Case B（声明 `windows`）正确抑制 `C:\`/powershell/裸python，但 `/Users/`/rm -rf/cwd/open()无encoding 仍报（符合「Windows 目标上才真坏」设计） |
| 级别与口径 | 全部 WARN/INFO、绝不 ERROR（可移植性是程度问题，结论需人判）；#6 `agent_coupling` 为 INFO 咨询；`target_platform` 任意取值均不抑制 #6（本期无 `target_agent` 字段），列入 Phase 4 跨 Agent 分发待办 | — |
| 文档同步 | SKILL.md 升 1.10.0 + 检查器列表 + 快速开始速查表 + 新增「portability 跨平台可移植性」小节；`references/checkers.md` 权威表新增 6 行 + `target_platform` 豁免字段说明；README 版本表 + 本明细 | — |

> Phase 4 已交付（v1.11.0）：① `deps.platform_undeclared` 由散文关键词扫描升级为读取结构化 `target_platform` 字段（与 portability 共用同一提取逻辑，已显式声明平台则抑制散文扫描）；② 跨 Agent 分发——新增 `target_agent` 字段轴（自由列表，仅特判 workbuddy 抑制；开放标准 `compatibility` 视作 target_agent），#6 `agent_coupling` 可按字段抑制/升级；③ Schema Normalizer——YAML 列表式 `allowed-tools` 解析（修外部技能 UNKNOWN_IDENT 误报）、`version`/`license` 检查平台感知（开放标准 agentskills/generic 不强制 version、license 降级 INFO），经 `--source github` 审计 `anthropics/skills` 真实外部仓库验证无 version/license 误报洪泛。

## 1.11.0 打磨明细（Phase 4 跨 Agent 分发 + Schema Normalizer）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| `target_agent` 字段轴 | `analyze_skill` 新增 `target_agent` 提取（自由列表；开放标准 `compatibility` 字段映射；无字段时按 mcp__/`.workbuddy` 信号推断 workbuddy）；`agent_coupling` 改为：声明含 workbuddy 抑制、声明跨 Agent 目标（claude-code/cross-agent）且仍含 WorkBuddy 耦合升 WARN、未声明 INFO | 构造测试技能：Case A（无声明+`.workbuddy`）INFO；Case B（`target_agent: claude-code`+`.workbuddy`）WARN；本项目自审 0 ERROR 且 agent_coupling 被推断 workbuddy 抑制 |
| deps 平台声明结构化（4a） | `platform_undeclared` 优先读 `ctx["target_platform"]`；已显式声明（非跨平台默认）则抑制散文扫描，否则保留作次级信号 | Case D（`target_platform: windows` + winreg）`platform_undeclared` 被抑制 |
| Schema Normalizer（4b-2） | YAML 列表式 `allowed-tools` 解析（修外部技能 UNKNOWN_IDENT 误报）；`check_structure`/`check_doc` 的 `version`/`license` 检查平台感知（workbuddy 强制，开放标准 agentskills/generic 不强制 version、license 降级 INFO） | 构造 agentskills 格式夹具（YAML 列表 allowed-tools + compatibility + 无 version/license）→ 无 version ERROR、license INFO、无 UNKNOWN_IDENT；`--source github --ref anthropics/skills` 真实外部仓库（约 20 技能）审计无 version/license 误报洪泛、`agent_coupling` 正确触发 |
| 文档同步 | SKILL.md 升 1.11.0 + 检查器列表/速查表/portability 小节补充 `target_agent`；`references/checkers.md` 权威表 `agent_coupling` 行 + 新增 `target_agent` 字段说明；README 版本表 + 本明细 | — |

复测总览：`py_compile` 通过；自审 `--all-checks` 0 ERROR；4 类测试技能（抑制/升级/声明/外部）行为符合设计；真实外部仓库 `anthropics/skills` 审计无工具崩溃（无 Traceback）。

复测总览：`py_compile` 通过；自审 `--all-checks` 0 ERROR（仅 INFO 咨询项）；`target_platform` 豁免两用例行为与设计完全一致；`--source github/skillhub` 多源能力回归无变化。

## 1.11.1 打磨明细（portability #6 行为修正）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 移除 workbuddy 抑制 | `check_portability` #6 删除「声明/推断含 `workbuddy` 则抑制 `agent_coupling`」分支；新口径：声明跨 Agent 目标（不含 `workbuddy`，如 `claude-code`/`cross-agent`）仍含 WorkBuddy 耦合→WARN，其余（未声明/声明含 `workbuddy`/推断 `workbuddy`）→均 INFO 提示 | 自审本项目 `--all-checks`：portability 现报 INFO `agent_coupling`（不再 0 发现）；构造 claude-code 目标夹具→WARN 升级仍正确 |
| 文档同步 | SKILL.md 升 1.11.1 + 速查表/portability 豁免说明改写；`references/checkers.md` 权威表 + `target_agent` 小节改写（workbuddy 不再作为抑制信号）；README 版本表 + 本明细 | — |

> 修正动机：本 skill 自身亦在开发跨平台/跨 Agent 分发能力，故 WorkBuddy 目标的耦合提示对所有技能（含 workbuddy 目标）均有参考价值，不应抑制。

## 1.12.0 打磨明细（Phase 5 跨 Agent 格式归一化内核）

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| 格式检测 `detect_format()` | 新增函数：按特征推断 5 类格式——`.mdc` + description/globs/alwaysApply → `cursor-mdc`；含 WorkBuddy 专有键（slug/displayName/target_platform/target_agent/agent_created）→ `workbuddy`；含 Claude Code 专有扩展键（argument-hint/model/context/agent/...）→ `claude-code`；含 `compatibility` 或仅开放标准键 → `agentskills`；其余 → `generic`。判定「按特征推断」而非硬锁枚举（延续 v1.11.0 自由列表原则，防生态演进漏判） | 5/5 夹具分类正确（workbuddy/agentskills/claude-code/cursor-mdc/generic） |
| 统一模型 `SkillModel` | 新增普通类承载 name/description/fmt/platform/target_platform/target_agent/tools/license/version/extra；`analyze_skill` 计算 `fmt` 并构建 `SkillModel`，注入 `ctx` 与返回结果（`format` / `skill_model` 字段），供检查器与后续 Phase 6 矩阵 / Phase 7 转译消费 | 本技能自检：`fmt=workbuddy`、`platform=workbuddy`、`version=1.11.1`、`target_agent=['workbuddy']`；字段经 ctx 与返回值双向可见 |
| 避免误报 | 未引入未使用常量（`FORMAT_ALL` 不落地）；`SkillModel` 用普通类而非 `@dataclass`，规避 vulture 对 dataclass 字段的死代码误报 | 自审 `--all-checks`：ERROR 0 / WARN 2（name_mismatch + hardcoded_path，均预期）/ INFO 11，WARN 较改动前无新增（无回归） |
| 文档同步 | SKILL.md 升 1.12.0 + portability 节补充「跨 Agent 格式归一化内核」说明；`references/checkers.md` 跨 Agent 字段节补充 Phase 5 内核说明；README 版本表 + 本明细 | — |

> 设计要点：Phase 5 是「地基」，不直接改变任何检查器的发现口径（现有 findings 与改动前完全一致），仅为跨格式审计建立统一表示层。下一步 Phase 6 将在此之上构建跨格式可移植性矩阵（字段映射 / 工具名 crosswalk / lossy-port 分级警告）。

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
