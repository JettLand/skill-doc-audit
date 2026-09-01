# 开发模式文档（DEVELOPMENT.md · 仅维护者）

> 本文件**仅供 skill-doc-audit 的维护者使用**，不属于发布给终端用户的技能内容（不进 `dist/`、不进部署副本 `~/.workbuddy/skills/skill-doc-audit`）。终端用户的使用文档是 `src/SKILL.md`（用户模式）+ `src/references/checkers.md`（完整参考）。

## 用户模式 vs 开发模式

| 维度 | 用户模式 | 开发模式 |
|---|---|---|
| 文档 | `src/SKILL.md` + `src/references/checkers.md` | 本文件 |
| 受众 | 任何安装并使用本技能审计自己技能的人 | 本技能的开发者 / 贡献者 |
| 工具 | `scripts/audit_docs.py`（随技能发布） | `dev_self_audit.py` / `self_validate.py` / `make_fixtures.py` / `sync_deploy.py`（dev-only，已被 `sync_deploy.py` 排除在部署副本外） |
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

## 自校验（self_validate.py）与 fixture 生成器（make_fixtures.py）

- `self_validate.py`：基于 `auditlib` 对 `tests/fixtures/` 跑确定性检查器，掩去绝对路径后比对 `tests/examples/*.expected.json` 黄金快照。新环境 clone 后任意 CWD 可跑（`tests/fixtures/` 已由 `.gitignore` 排除，缺失时自动调 `make_fixtures.build()` 重建）。
- `make_fixtures.py`：声明式 recipe 字节级复刻 `tests/fixtures/`；`--check` 校验与 recipe 一致，`--baseline` 重建 fixtures 后一并重建黄金快照（**人工显式动作**，正常校验流程不自动重建，否则削弱回归护栏）。

```bash
python src/scripts/self_validate.py
python src/scripts/make_fixtures.py --check
python src/scripts/make_fixtures.py --baseline   # 仅人工显式触发
```

## 部署副本同步（sync_deploy.py + 提交即同步钩子）

- `sync_deploy.py`（dev-only）：把 `src/` 发布面（SKILL.md / scripts/audit_docs.py / scripts/auditlib/** / references/checkers.md / dist/skill-doc-audit.zip）字节级同步到部署副本 `~/.workbuddy/skills/skill-doc-audit`，清理 `__pycache__`，末段校验一致性；**刻意排除** dev 工具与 `tests/`。
- `hooks/post-commit`（`git config core.hooksPath` 须为绝对路径 `D:/Agent Work/skill-doc-audit技能项目管理/hooks`）：每次 `git commit` 后自动运行 `sync_deploy.py`，**提交即同步**。⚠ 钩子必须在能找到 `python` 的环境运行，且 `core.hooksPath` 必须为绝对路径——相对 `../hooks` 会被 git 解析到仓库外导致钩子永不触发；提交后务必 `diff` 核验副本一致，不能只看 commit 成功。

手动触发：`python src/scripts/sync_deploy.py`（可用 `SKILL_DEPLOY_DIR` 覆盖目标路径）。

## 未发布改动工作流（累积发布）

真实能力改动（如 dev 工具、doc 口径收敛）先记入 `CHANGELOG.md` 的「未发布改动」节、**不 bump 版本号**；版本号在用户授权发布时统一升。本地改动照常 `git commit`（触发同步钩子），push 由维护者手动执行（`git push origin main`）。SkillHub 上架按发布节奏约定——多个连续版本只上架最新一版，不每次微改都发。

## 文档分层约定（用户模式文档如何写）

- `src/SKILL.md`：用户模式，精简——能力一句话地图 + Agent 执行约定（动作）+ 紧凑错误码速查 + FAQ；详细规格不在此展开。
- `src/references/checkers.md`：完整参考（模式机制 / 判定口径 / 误报抑制 / Phase 演进），是用户模式文档的明细基准。
- 本文件（DEVELOPMENT.md）：开发模式，仅维护者。
- 任何文档改动后须复跑 `dev_self_audit.py --strict` 确认 `ERROR 0 / WARN 0`，并提交触发同步钩子。
