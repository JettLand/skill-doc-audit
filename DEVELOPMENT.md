# 开发模式文档（DEVELOPMENT.md · 仅维护者）

> 本文件**仅供 skill-doc-audit 的维护者使用**，不属于发布给终端用户的技能内容（不进 `dist/`、不进部署副本 `~/.workbuddy/skills/skill-doc-audit`）。终端用户的使用文档是 `src/SKILL.md`（用户模式）+ `src/references/checkers.md`（完整参考）。

## 用户模式 vs 开发模式

| 维度 | 用户模式 | 开发模式 |
|---|---|---|
| 文档 | `src/SKILL.md` + `src/references/checkers.md` | 本文件 |
| 受众 | 任何安装并使用本技能审计自己技能的人 | 本技能的开发者 / 贡献者 |
| 工具 | `scripts/audit_docs.py`（随技能发布） | `dev_self_audit.py` / `self_validate.py` / `make_fixtures.py` / `sync_deploy.py` / `_devcommon.py`（dev-only 共享样板；均已被 `sync_deploy.py` 排除在部署副本外，`_devcommon.py` 亦在 `dev_self_audit.py` 的 `DEV_TOOLS` 排除集内避免 orphan_asset 误报） |
| 关键动作 | 跑 `--all-checks` 审计目标技能 | 审计最新源码 `src/`、自校验 fixtures、把 `src/` 同步到部署副本、走「未发布改动」累积发布 |

**设计边界**：技术隔离已存在——dev 工具根本不进部署副本，终端用户拿不到。本文件是把「哪些是给用户、哪些是给维护者」的叙事显式二分，避免读者混淆；并明确 dev-only CLI 旗标仅在本仓库内有效。

## 开发模式自审计（dev_self_audit.py）

`src/scripts/dev_self_audit.py` 把以下约定固化为可重复命令，规避长期项目的记忆漂移 / 幻觉 / 漏操作：

1. **同步校验**：复用 `sync_deploy._verify()` 确认「部署副本 ↔ 最新源码 `src/`」字节一致；不一致说明有未提交改动或钩子未触发，明确告警。
2. **审计最新源码**：一律对 `src/`（最新提交）跑全量检查器，而非部署副本——避免审计过时产物。
3. **开发文档纳入漂移**：`--dev-docs` 把 `README.md` / `CHANGELOG.md` 交 `doc`（A1 死路径）+ `doc-llm`（语义漂移）扫描。
4. **只扫发布面**：排除 `sync_deploy.py` / `self_validate.py` / `make_fixtures.py` / `dev_self_audit.py`，使结果与发布质量对齐，不被 dev 工具噪音干扰。

退出码：`0` = 无 ERROR（`--strict` 下还需无 WARN）；`1` = 发现 ERROR（或 `--strict` 下 WARN）；`2` = 参数/路径错误。

```bash
python src/scripts/dev_self_audit.py            # 同步校验 + 审计最新源码发布面 + dev 文档
python src/scripts/dev_self_audit.py --strict   # CI 门禁：WARN 也计入失败
python src/scripts/dev_self_audit.py --no-sync-check  # 跳过同步校验（仅审计）
```

dev 专用 CLI 旗标（`--dev-docs` / `dev_audit=True` / `exclude`）仅在运行本仓库的 `dev_self_audit.py` 时有效；对终端用户审计任意技能无意义，若被误用会在非本仓库上下文打印提示并忽略。

### 约定：哪些 dev 旗标进主 CLI、哪些不进（避免回退三分式）

**`--dev-docs` 进主 CLI（`cli.py:44`）——合理，且性质不同于另两项。** 它是通用能力：任意技能的维护者都能把自己的 `README.md` / `CHANGELOG.md` 纳入漂移扫描，不是「关掉正确性检查」。所以它在用户模式 CLI 中可见是对的。

**`dev_audit=True` 与 `exclude=DEV_TOOLS` 不进主 CLI——属本仓库专属 hack，禁止提成开关。** 理由：

- `dev_audit=True`：`structure.py:21` 用 `not ctx.get("dev_audit")` 跳过 `name_mismatch`，唯一目的是本仓库源码根目录叫 `src/` 而非技能名（`dev_self_audit.py:115` 硬编码）。而用户用本技能审计**自己**的技能时，目录即技能目录，`name_mismatch` 是正确告警；把它暴露给用户等于教用户「可关掉名称一致性检查」。
- `exclude=DEV_TOOLS`：`dev_self_audit.py:40/:114` 排除 `sync_deploy.py` / `self_validate.py` / `make_fixtures.py` / `dev_self_audit.py` 这 4 个本仓库 dev 工具；其他技能根本没有这些文件，暴露出去是死参数。

**硬性边界**：`dev_audit` / `exclude` 的打开点只存在于 `dev_self_audit.py`（`src/scripts/` 内，已被 `sync_deploy.py` 排除在部署副本外）。若日后有人想把 `--dev-audit` 加到 `cli.py`（它是部署副本一部分），**等于把维护者专属逻辑塞回用户技能、直接回退三分式隔离**，应拒绝。引擎默认 `dev_audit=False`（`model.py:152`）即用户模式，符合「默认零依赖、绝不替用户决定」。

### 判定逻辑：进入开发者模式由「调用入口」决定，非运行时自判

- **没有自动检测**：引擎 `analyze_skill`（`model.py:151`）默认 `dev_audit=False` / `exclude=None` / `dev_docs=None`，即用户模式；脚本**不**探测 cwd / 环境变量 / git 远端 / 调用者身份来「判断」当前处于哪种模式。
- **由调用入口决定**：跑 `audit_docs.py`（随技能发布的用户 CLI）→ 永远用户模式（`cli.py:114-116` 只传 `dev_docs=args.dev_docs`，`dev_audit` / `exclude` 不传 → 取引擎默认）；跑 `dev_self_audit.py`（dev-only）→ 开发者自审计（`dev_self_audit.py:109-116` 硬编码 `dev_audit=True` + `dev_docs=[README.md, CHANGELOG.md]` + `exclude=DEV_TOOLS`）。
- **流程完全可控、确定性**：无隐式切换、无运行时自判、无 agent 决断。终端用户装到的部署副本不含 `dev_self_audit.py`，只能跑用户 CLI，用户模式由**结构**保证，不可能「误入」开发模式。
- **唯一的运行时探测与模式无关**：`dev_self_audit.py:95` `_detect_vulture()` 仅决定 deadcode 精度（vulture / ast），非模式判断；`dev_self_audit.py:98` `doc_llm_mode=None` 非交互下跳过 doc-llm、语义比较留给交互 agent 接手，是**能力选择**（符合「默认零依赖、绝不替用户决定」），非模式开关。
- **dev 自审计内部三参不可 flag 调**：`dev_audit` / `dev_docs` / `exclude` 为硬编码常量，`dev_self_audit.py` 无 `--dev-audit` 之类开关；脚本可调 flag 仅 `--strict` / `--no-sync-check` / `--deadcode-mode`（调严度，不切换模式）。
- **禁止反向加自动检测**：不要为「是否进入开发模式」引入运行时 if 判定（如 `if os.path.basename(cwd) == "src": dev_audit=True`），那会破坏上述结构保证、引入隐式切换与回归风险；判定一律由入口显式决定。

## 触发条件（何时运行各 dev 工具）

消除「不知何时跑某 dev 工具」的困惑——下面是精确触发表。核心原则：**`dev_self_audit` 守发布质量、`self_validate` 守检查器行为，两条流水线刻意不串**（前者全量含 vulture/doc-llm、随环境可变；后者只用 `DETERMINISTIC=[doc,structure,security,runtime,deps]` 确定性子集、保证可复现）。

| 你改动了什么 | 该跑 | 不该跑 | 说明 |
|---|---|---|---|
| `src/` 任意发布面文件（SKILL.md / scripts/audit_docs.py / scripts/auditlib/ / references/checkers.md / dist） | `dev_self_audit.py`（建议 `--strict`） | — | 发布质量门禁：审计最新源码 + 验证「部署副本 ↔ src」一致 + 开发文档漂移 |
| `README.md` / `CHANGELOG.md` | `dev_self_audit.py --dev-docs`（或 `--strict --dev-docs`） | — | 把开发文档纳入漂移扫描 |
| `src/scripts/auditlib/checkers/{doc,structure,security,runtime,deps}.py` 或公共层 `model` / `report` / `core` | `self_validate.py` | — | 检查器行为回归护栏：对 fixtures 跑确定性检查器、比对 `tests/examples/*.expected.json` 黄金快照 |
| `src/scripts/auditlib/checkers/{deadcode,doc_llm,portability}.py` 或 fixtures / 文档自身 | `dev_self_audit.py`（视情况） | `self_validate.py` | deadcode/doc_llm/portability 不在 `DETERMINISTIC` 子集，跑 `self_validate` 无回归捕捉价值、反引入噪音 |
| dev 工具自身（sync_deploy / self_validate / make_fixtures / dev_self_audit / `_devcommon`） | 仅 `dev_self_audit.py` 复查 | `self_validate.py` | dev 工具不进发布面，`self_validate` 审计的是用户技能行为、与 dev 工具改动无关 |
| 发布前（统一动作） | `dev_self_audit.py --strict` **+** `self_validate.py` | — | 一键全量：先质量门禁、再检查器回归（也可靠 CI 钩子自动覆盖） |
| 版本迭代 / 发布前收尾 | （`dev_self_audit.py` 内置 `release_check` 自动提示） | 手动记忆 | 版本号一致性(SKILL.md↔sources.py) / CHANGELOG 收口 / dist 重打包 / temp 清理——改为门禁输出 `[agent-todo]`，不再依赖记忆 |
| 准备 `git commit` | （`post-commit` 钩子自动 `sync_deploy`） | 手动 | 提交即同步部署副本 |
| `git push origin main` | （`pre-push` 钩子自动跑 `dev_self_audit --strict` + `self_validate`） | 手动 | 本地发布门禁，失败拦截 push |
| 推到 GitHub / 开 PR 到 `main` | （GitHub Actions `dev-qa.yml` 自动跑 `dev_self_audit --strict --no-sync-check` + `self_validate`） | 手动 | 远程兜底，防绕过 |

> 记忆锚点：`self_validate` 只在「动了检查器代码」时有意义；`dev_self_audit` 在「动了发布面 / 文档」或「发布前」跑。两者均不进部署副本，终端用户拿不到。

### 三道自动化机制分工对比

上表按「改动类型」给触发建议；下表按「自动化机制」横向对比三者各自做什么、差异在哪，避免混淆「哪个钩子负责什么」：

| 机制 | 触发时机 | 执行的命令 | 同步校验（副本 ↔ src） | 发 `[agent-todo]` | 门禁拦截 | 失败后果 |
|---|---|---|---|---|---|---|
| 同步钩子 `post-commit` | 每次 `git commit` | `sync_deploy.py`（仅同步副本） | 自身即同步动作 | **否** | 否 | 仅告警（commit 已成功），不阻塞 |
| 本地 CI `pre-push` | `git push origin main` | `dev_self_audit.py --strict` + `self_validate.py` | **是**（本机有副本） | **是** | 是（任一失败拦 push） | 拦截本次 push，须先修复 |
| 远程 CI `dev-qa.yml` | push/PR 到 `main`（GitHub Actions） | `dev_self_audit.py --strict --no-sync-check` + `self_validate.py` | **否**（`--no-sync-check`，CI 无副本） | **是** | 是（job 失败标红 PR） | PR 标红，拦下合并/发布 |

要点：
- **`post-commit` 只同步、不发提示、不门禁**——职责单一（提交即把 `src/` 发布面同步到部署副本）；`[agent-todo]` 由 `dev_self_audit` 输出，故只来自 `pre-push` 与 `dev-qa`。
- **同步校验开关是本地与远程的唯一实质差异**：本机有部署副本故 `pre-push` 保留校验；GitHub 机器无副本，`dev-qa` 加 `--no-sync-check`。两套门禁的检查内容（`dev_self_audit --strict` + `self_validate`）完全一致。
- **`[agent-todo]` 在远程 CI 仅日志噪音、但门禁（退出码）仍生效**：GitHub 上无 agent 消费提示文本，而 `release_check` 阻断项会升 `dev_self_audit` 退出码 → `dev-qa` 的 `publish-gate` job 失败 → PR 标红，是本地钩子未拦住时的远程兜底。

### `[agent-todo]` 提示具体长什么样（由 `release_check.py` 产出、`dev_self_audit.py:153-165` 渲染）

执行 `dev_self_audit.py --strict` 时，若命中下列任一检查项，会打印一个提示块，**每项都给出发指令级的可照做动作**。共 4 类检查：

| 检查项 | 严重度 | 是否阻断 | 触发条件 | 发出的 `todo` 指令（原文） |
|---|---|---|---|---|
| 版本号一致性 | `ERROR` | **是** | `SKILL.md version` ≠ `sources.py` 第144行 `User-Agent` | `将 src/scripts/auditlib/sources.py 第144行的 User-Agent 改为 skill-doc-audit/<SKILL版本>` |
| CHANGELOG 收口 | `WARN` | **是** | `SKILL.md version` 高于 `CHANGELOG.md` 最高版本节 | `将 CHANGELOG.md 的「未发布改动」节提升为 '<SKILL版本> 打磨明细' 节后再提交` |
| dist 制品过期 | `INFO` | 否 | `dist/skill-doc-audit.zip` 早于发布面源码 mtime | `发布 SkillHub 前重打包：python src/scripts/build_dist.py` |
| temp 残留 | `INFO` | 否 | `temp/` 下有 `*_test*.py`/`*.mhtml`/`_eval*.txt`/`stress*`/`_rezip*`/`*.py` | `及时清理 temp/ 测试残留；⚠ 清理前先确认这些文件非你手动放入，再删除（遵循 temp/ 管理约定）` |

**提示块的实际打印格式**（来自 `dev_self_audit.py:153-165`，以「版本不一致」为例的真实渲染）：

```
========================================================================
发布前待办（Agent 提示 · 由 pre-push 钩子与 dev-qa 工作流发出）
========================================================================
  [agent-todo][ERROR] 版本号不一致：SKILL.md 与 sources.py User-Agent 不同步
      SKILL.md version=1.25.4，但 sources.py 的 HTTP User-Agent=skill-doc-audit/1.25.3
      → 将 src/scripts/auditlib/sources.py 第144行的 User-Agent 改为 skill-doc-audit/1.25.4

⚠ 存在阻断项，发布前须先解决（--strict 下将失败）。
```

> 注：`release_check` 自身异常或被 import 失败时，只发一条 `INFO` 提示「发布就绪检查不可用 / 手动核对版本号·CHANGELOG·dist·temp」，绝不因此阻断门禁。

## 自校验（self_validate.py）与 fixture 生成器（make_fixtures.py）

- `self_validate.py`：基于 `auditlib` 对 `tests/fixtures/` 跑确定性检查器，掩去绝对路径后比对 `tests/examples/*.expected.json` 黄金快照。新环境 clone 后任意 CWD 可跑（`tests/fixtures/` 已由 `.gitignore` 排除，缺失时自动调 `make_fixtures.build()` 重建）。
- `make_fixtures.py`：声明式 recipe 字节级复刻 `tests/fixtures/`；`--check` 校验与 recipe 一致，`--baseline` 重建 fixtures 后一并重建黄金快照（**人工显式动作**，正常校验流程不自动重建，否则削弱回归护栏）。

```bash
python src/scripts/self_validate.py
python src/scripts/make_fixtures.py --check
python src/scripts/make_fixtures.py --baseline   # 仅人工显式触发
```

## 发布就绪检查（release_check.py · 让钩子/CI 对 agent 发提示）

版本迭代后有一批「必须由 agent 执行」的收尾操作，此前依赖 agent 记忆、易漏做并造成隐蔽漂移（例如 `sources.py` 的 `User-Agent` 版本号带陈旧值自报给远端）。现固化为 `src/scripts/release_check.py`，由 `dev_self_audit.py` 调用——本地 `pre-push` 与远程 `dev-qa` CI 都跑 `dev_self_audit`，故**两道门禁都会输出带 `[agent-todo]` 标记的提示块**，agent 无需回忆即可照做：

- **版本号一致性（阻断）**：`SKILL.md` `version` 必须等于 `sources.py` 第144行的 `User-Agent: skill-doc-audit/<ver>`；不一致 → ERROR 并打印精确修复指令，`--strict` 下拦下 push。
- **CHANGELOG 收口（阻断）**：`SKILL.md` 版本高于 CHANGELOG 最高版本节时，提示把「未发布改动」提升为 `<ver> 打磨明细`；WARN，`--strict` 下拦截。
- **dist 制品过期（提示）**：`src/dist/skill-doc-audit.zip` 早于发布面源码时，提示重打包（发布 SkillHub 前必做）；INFO，不阻塞。配套 `src/scripts/build_dist.py`（可复现打包命令，提示里直接给出）。
- **temp/ 残留（提示）**：`temp/` 发现 `*_test*.py` / `*.mhtml` / `_eval*.txt` / `stress*` 等临时产物时提示清理；INFO，且提示重申「清理前先确认非用户手动放入的文件」（遵循 temp/ 管理约定）。

阻断项与 `--strict` 的 WARN 同样计入 `dev_self_audit` 退出码，故会拦下 `pre-push`；非阻断项仅作 INFO 提示，不阻塞常规提交/推送。效果：把「发布前该做什么」从记忆下沉为门禁输出。

## 部署副本同步（sync_deploy.py + 提交即同步钩子）

- `sync_deploy.py`（dev-only）：把 `src/` 发布面（SKILL.md / scripts/audit_docs.py / scripts/auditlib/** / references/checkers.md / dist/skill-doc-audit.zip）字节级同步到部署副本 `~/.workbuddy/skills/skill-doc-audit`，清理 `__pycache__`，末段校验一致性；**刻意排除** dev 工具与 `tests/`。
- `hooks/post-commit`（`git config core.hooksPath` 须为绝对路径 `D:/Agent Work/skill-doc-audit技能项目管理/hooks`）：每次 `git commit` 后自动运行 `sync_deploy.py`，**提交即同步**。⚠ 钩子必须在能找到 `python` 的环境运行，且 `core.hooksPath` 必须为绝对路径——相对 `../hooks` 会被 git 解析到仓库外导致钩子永不触发；提交后务必 `diff` 核验副本一致，不能只看 commit 成功。

部署目录解析（与用户名/平台/设备/宿主 agent 解耦，**非标准安装、非 WorkBuddy agent 下真正定位、不降级**）：`sync_deploy.py` 与 `dev_self_audit.py` 均通过 `_devcommon.resolve_deploy_dir()` 解析，返回 `(path, how)`（how 打印在同步日志，便于排查）。优先级：
1. `SKILL_DEPLOY_DIR`（显式按机覆盖，最高，绕过一切自动探测——任意平台 / 任意 agent 通用）
2. `SKILLS_DIR` / `AGENT_SKILLS_HOME`（通用覆盖：任意 agent 可指向自家 skills 根，跨 agent 自动探测次高）
3. **`WORKBUDDY_CONFIG_DIR` / `CODEBUDDY_CONFIG_DIR` + `/skills/<name>`** —— WorkBuddy 运行时**必导出**的配置目录（见进程环境 `WORKBUDDY_CONFIG_DIR=C:\Users\admin\.workbuddy`），非标准安装 / 自定义数据目录 / 换用户名均可靠定位
4. `~/<WORKBUDDY_DATA_FOLDER_NAME>/skills/<name>`（数据文件夹名 + 主目录，默认 `.workbuddy`）
5. `~/.workbuddy/skills/<name>`（标准跨平台默认，`~` 按当前用户展开，不写死盘符/用户名）
6. **跨 agent 候选根探测兜底**：`~/.claude/skills`、`~/.claude/plugins`（含嵌套布局，bounded walk）、`~/.config/claude/skills`、`~/.cursor/skills`、`~/.codex/skills`、`~/.opencode/skills`、`~/.aider/skills`，以及平台根 `LOCALAPPDATA/CodeBuddyExtension/skills`、`APPDATA/WorkBuddy/skills`、`XDG_DATA_HOME/workbuddy/skills`、`~/Library/Application Support/WorkBuddy/skills`——覆盖「裸终端运行、未继承 `WORKBUDDY_*` 变量、或非 WorkBuddy agent 托管」的场景

> 严格测试已证明跨平台 + 跨 agent 定位均可靠（见 `tests/test_resolve_deploy.py` 的 T1–T6）：`SKILL_DEPLOY_DIR` 显式覆盖、`SKILLS_DIR` 通用覆盖、`WORKBUDDY_CONFIG_DIR` 非标准安装、Claude 扁平 / 插件嵌套布局均实际命中并 `verify: OK`，**不再 skip/降级**。只有「所有候选根都找不到该技能」的极端情况才退回默认并优雅跳过——那已不是降级，而是确实未安装（如该 agent 从未装过本技能，此时用 `SKILL_DEPLOY_DIR` 显式指向即可）。

手动触发：`python src/scripts/sync_deploy.py`（可用 `SKILL_DEPLOY_DIR` 覆盖目标路径）。

## 未发布改动工作流（累积发布）

真实能力改动（如 dev 工具、doc 口径收敛）先记入 `CHANGELOG.md` 的「未发布改动」节、**不 bump 版本号**；版本号在用户授权发布时统一升。本地改动照常 `git commit`（触发同步钩子），push 由维护者手动执行（`git push origin main`）。SkillHub 上架按发布节奏约定——多个连续版本只上架最新一版，不每次微改都发。

## 文档分层约定（用户模式文档如何写）

- `src/SKILL.md`：用户模式，精简——能力一句话地图 + Agent 执行约定（动作）+ 紧凑错误码速查 + FAQ；详细规格不在此展开。
- `src/references/checkers.md`：完整参考（模式机制 / 判定口径 / 误报抑制 / Phase 演进），是用户模式文档的明细基准。
- 本文件（DEVELOPMENT.md）：开发模式，仅维护者。
- 任何文档改动后须复跑 `dev_self_audit.py --strict` 确认 `ERROR 0 / WARN 0`，并提交触发同步钩子。
