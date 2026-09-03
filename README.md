# skill-doc-audit 技能工程仓库

本仓库是 SkillHub 技能 **skill-doc-audit（技能体检助手）** 的源管理与发布工程仓库，并非技能本身。正式上架版本发布于 SkillHub（slug：`skill-doc-audit`）。

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

版本变动的「改动 + 验证」明细统一记录于 [CHANGELOG.md](./CHANGELOG.md)。
