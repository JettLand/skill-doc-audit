# 开发模式文档（DEVELOPMENT.md · 仅维护者）

> 本文件**仅供 skill-doc-audit 的维护者使用**，不属于发布给终端用户的技能内容（不进 `dist/`、不进部署副本 `~/.workbuddy/skills/skill-doc-audit`）。终端用户的使用文档是 `src/SKILL.md`（用户模式）+ `src/references/checkers.md`（完整参考）。

## 用户模式 vs 开发模式

| 维度 | 用户模式 | 开发模式 |
|---|---|---|
| 文档 | `src/SKILL.md` + `src/references/checkers.md` | 本文件 |
| 受众 | 任何安装并使用本技能审计自己技能的人 | 本技能的开发者 / 贡献者 |
| 工具 | `scripts/audit_docs.py`（随技能发布） | `dev_self_audit.py` / `dev_market_bench.py`（三套辅助开发工具）/ `self_validate.py` / `make_fixtures.py` / `sync_deploy.py` / `release_check.py` / `_devcommon.py` / `bump_audit.py` / `dev_commit.py` / `dev_workbench.py`（dev-only 共享样板；均已被 `sync_deploy.py` 排除在部署副本外，且列入 `dev_self_audit.py` 的 `DEV_TOOLS` 排除集避免 orphan_asset 误报） |
| 关键动作 | 跑 `--all-checks` 审计目标技能 | 审计最新源码 `src/`、自校验 fixtures、把 `src/` 同步到部署副本、走「未发布改动」累积发布 |

**设计边界**：技术隔离已存在——dev 工具根本不进部署副本，终端用户拿不到。本文件是把「哪些是给用户、哪些是给维护者」的叙事显式二分，避免读者混淆；并明确 dev-only CLI 旗标仅在本仓库内有效。

## 辅助开发套件（三套 dev 工具）

本仓库的辅助开发工具共**三套**，均 dev-only（不进部署副本、终端用户拿不到），定位互补：

| 正式名称 | 脚本 | 职责 | 触发方式 |
|---|---|---|---|
| 源码自审计器 | `src/scripts/dev_self_audit.py` | 守**发布质量**：同步校验（副本↔src）+ 审计最新源码发布面 + dev 文档漂移 + 发布就绪检查（`[agent-todo]`） | 每次 `git commit`（post-commit 同步 + 版本 bump 提交经 `bump_audit` 自动跑它作早期反馈）/ `git push`（pre-push 门禁）/ 推 PR（dev-qa CI）；也手动跑 |
| 市场质量基准实测器 | `src/scripts/dev_market_bench.py` | 守**「规模化真实世界」**：按官方市场列表 API 随机抽 sample 个技能、批量跑全量检查，验证检查器在长尾技能上的稳定性与 doc-llm 真实执行 | **不进自动调度**：仅人工要求时启用（`run`）；`check-bump` 子命令供 `dev_self_audit` 在版本变动 / 未提交时打印 `[agent-todo]` 提示（含次/主版本变动时的基准实测决策点），绝不直接触发 `run` |
| 开发工作台 | `src/scripts/dev_workbench.py` | 守**改动落盘的可靠性**：字节级 patch / 断言复核 / 递归 py_compile / 版本 bump / 覆盖全部文本文件的纯 Python grep / git 状态 / git commit 薄封装（commit）/ JSON 计划单进程批量执行（多字节与转义内容走 `--*-file`，规避 Edit 工具 phantom success 与工具调用参数传输层丢参） | 纯按需手动调用（不进任何钩子 / CI）；`[agent-todo]` #8 在检测到开发面未提交改动时提醒优先用它 |

> 其余 `self_validate.py` / `make_fixtures.py` / `sync_deploy.py` / `release_check.py` / `_devcommon.py` / `bump_audit.py` 为检查器回归护栏、fixture 生成、副本同步、发布就绪检查、共享样板等基础设施，不属于「三套辅助开发工具」本身，但支撑前述三套工具运转。

### 源码自审计器（dev_self_audit.py）

…（职责与判定逻辑见下方「开发模式自审计」节，此处不重复；本表仅定位三套工具）

### 市场质量基准实测器（dev_market_bench.py）

把「批量实测 skill-doc-audit 在规模化真实世界的稳定性」固化成可重复命令。关键设计（用户 2026-09-01 要求，取代旧 `bench/market-audit/run_market_audit.py`）：

1. **取样规则（2026-09-03 推翻原「质量分近似」）**：不再构建质量索引、不再依赖评测接口；直接用官方市场列表 API（`LIST_ENDPOINTS`，免鉴权）随机页偏移抽候选（`collect_pool`：`total` 取自接口 `data.total` 定随机页范围，每页 `page_size` 个、随机打乱），候选池大小 `max(sample*2, 120)` 留出去重余量；再排除近 `dedup`（默认 3）次已采 slug（`sampled_history.json`），随机抽 `sample`（默认 50）个做实测。默认不固定种子（每次天然不同，`--seed` 可复现）。
2. **规模约束与接口压力（已在代码中实测确认）**：市场技能 13 万+；列表接口仅支持 `score/downloads/stars/updatedAt` 排序、不返回质量分字段，全量爬评测不可行——故改为「随机页偏移抽候选」而非「质量最低优先」。单次 `run` 仅约 2-4 次列表请求 + `sample` 次下载，对官方接口压力远低于原质量索引路径（约 1000 次评测请求）；如需进一步降密度可减小 `--page-size` 或减少 `--sample`。
3. **全量审计**：每个样本技能经本地优先源（`SKILL_MARKET_BENCH_LOCAL_DIRS` 覆盖 / 官方本地技能市场 / `~/.workbuddy/skills` 等）命中即复制、完全不发网络请求；未命中走官方下载端点。落盘 `bench/market_bench/skills/` 后逐个跑 `auditlib/cli.py`，旗标 `--all-checks --deadcode-mode vulture --doc-llm-mode agent --examples-mode static --examples-consent --json`（与发布面门禁同源）；`results.json` 支持 resume（已审计 slug 跳过）。只读本地副本、绝不改动实时技能目录。
4. **下载口径（与官方 find-skills 一致）**：下载前先遍历本地候选源（`local_candidate_dirs()`）——环境变量 `SKILL_MARKET_BENCH_LOCAL_DIRS`（`os.pathsep` 分隔，最高优先）> 官方本地技能市场 `~/.workbuddy/skills-marketplace/skills` > `~/.workbuddy/skills`、`~/.codebuddy/skills` > IDE 市场插件缓存 `~/.workbuddy/plugins/marketplaces/*/plugins/*/skills`——命中即复制、**完全不发网络请求**；未命中才走官方端点 `https://lightmake.site/api/v1/download?slug=<slug>`。产物落 bench 临时目录、**只读本地副本、绝不改动或安装进实时技能目录**；`run` 结束会打印「本地命中 / 远端下载」计数并写入报告 meta。
5. **不进自动调度**：实际跑基准（`run`）只在人工要求时执行；`check-bump` 子命令供 `dev_self_audit` 在版本变动 / 未提交改动时打印 `[agent-todo]` 提示（含次/主版本变动时的「是否运行完整基准实测」决策点），best-effort、不失败 CI、绝不触发 `run`。

子命令：

```bash
python src/scripts/dev_market_bench.py run                       # 随机抽 50 个市场技能 → 下载 → 全量审计 → 报告
python src/scripts/dev_market_bench.py run --sample 50 --seed 7  # 可复现抽样（50 个）
python src/scripts/dev_market_bench.py run --dedup 0             # 不去重（允许重复历史样本）
python src/scripts/dev_market_bench.py run --page-size 60        # 减小列表分页（进一步降接口密度）
python src/scripts/dev_market_bench.py check-bump                # 版本监测（由 dev_self_audit 自动调用）
```

缓存（均 `bench/`，已 gitignore，不进版本库）：`sampled_history.json`（采样历史）/ `last_bench_version.txt`（版本监测基线）/ `skills/`（下载的技能源码）/ `results.json` / `report.md`（逐次结果）。

退出码：`0` 正常；`2` 参数/路径错误；`run` 下被审技能出现 ERROR 属被测现象、不升退出码（与旧 `run_market_audit` 一致）。

**运行时产出的 `[agent-todo]` 提示**（本工具是两个 `[agent-todo]` 发射方之一，另一个是 `dev_self_audit` 经 `release_check`）：文档只描述、不重述全文，代码（`print_selfcheck_hint()` 与 `check_bump()`）是单一真相源，改提示须同步代码。

1. **`run` 结束时**（`print_selfcheck_hint()`，best-effort、非阻断）：首行 `[agent-todo][建议] 用实测结果反查 skill-doc-audit 自身（基准实测的初衷）——逐项校验：`，后附 5 条——① 回执健康（`UNKNOWN`/`FAILED` 非 0 ⇒ 检查器静默休眠或执行异常，须立即排查）；② 检查器点火率（命中技能数 / 已审 N）+ 标注 ⚠ 零点火（跑了却零 finding，疑似静默休眠/判定过窄）与 ⚠ 全量命中（每个都报，疑似口径过宽/噪音）；③ 全量命中类别（N/N 技能皆中）多属噪音口径须逐条判真伪；④ 与上一版 `report.md` 对比，新增/消失类别须先抽样复现再定性；⑤ 抽样优先级 = 单技能 finding 数最高者 + 全量命中类别 + 零源码技能（历史误报集中区）。判据：误报 ⇒ 加抑制规则 + `self_validate` fixture 固化 + bump 版本；真缺陷 ⇒ 修检查器并回归 `self_validate` 与 `dev_self_audit --strict`。
2. **`check-bump` 时**（`dev_self_audit` 汇总后 best-effort 调用，绝不触发 `run`）：① `[agent-todo][必须] 上架 SkillHub 前须先取得用户明确授权（不得自动发布）`；② `[agent-todo][建议] 版本变动时用户文档（SKILL.md / references/*）无需写入版本变动叙述`（留 CHANGELOG.md）；③ `[agent-todo][建议] ⚠ 决策点：次/主版本变动——是否运行「市场质量基准实测器」做完整实测？`（仅 `is_minor_or_major_bump` 命中时）；④ `[agent-todo][建议] 检测到未提交的本地改动，请立即本地 commit`（仅存在未提交改动时）。

### 开发工作台（dev_workbench.py）

`src/scripts/dev_workbench.py` 是开发工作台（v1.35.0 由 `dev_orchestrate.py` 更名而来；该名 v1.34.7 由 `devkit.py` 重命名得到）——更名理由：本工具不编排任何外部流程，实为单进程内的开发期文件操作与校验工作台，原名 orchestrate（编排）词不达意：**不替代 bash**，而是把开发期对 shell 的脆弱依赖压缩到最小——凡能在一个 Python 进程内完成的字节级 patch / 断言复核 / 编译 / 版本 bump / git 状态 / git commit 薄封装 / 计划批量，都不经 bash 命令行传递多字节或转义内容，降低对 shell 调用层的暴露面。动机：本会话反复踩的 Edit 工具 phantom success（报成功但磁盘未变）与工具调用参数传输层间歇丢参（`command` / `file_path` 随机变 undefined）——多字节/转义内容移出命令行即可规避。

设计要点（dev-only，不进部署副本、列入 `DEV_TOOLS` 排除集）：

- **多字节/转义内容走文件**：`patch` / `verify` 的旧值、新值、待匹配串一律从 `--*-file` 读（纯 ASCII 简单串可用内联 `--old` / `--new`），shell 启动命令只剩 ASCII 路径与旗标。
- **单进程批量（`run-plan`）**：读 JSON 计划，在一个 Python 进程内依次执行 patch / verify / compile / run，把 N 次 shell 往返压缩为 1 次，任一步失败即中止并给非零退出码；`run` op 以白名单执行仓库内 `.py`（不执行任意命令 / shell 字符串）。
- **幂等可重跑**：每个子命令只读/写明确路径，无副作用累积；计划中断后重跑安全。
- **纯标准库、零外部依赖**：不联网、不装包；`doctor` 纯 Python 环境探针（python 版本 / git 在 PATH / 部署副本在位 / 三锚点版本一致性），零 shell 依赖。
- **跨 shell 冗余**：启动行 `python src/scripts/dev_workbench.py <sub>` 纯 ASCII、跨 shell 通用（bash / powershell / cmd 皆认）；Bash 工具丢参时改用 PowerShell 工具（或反之）用同一行重试。

子命令：

```bash
python src/scripts/dev_workbench.py patch --file <路径> --old-file <旧值文件> --new-file <新值> \
  [--once] [--count N]          # 字节级替换（断言命中次数 + 保 LF）；--once 要求恰好 1 处
python src/scripts/dev_workbench.py verify --file <路径> \
  --contains-file <期望含> --not-contains-file <期望不含> [--contains <串>]   # 断言含/不含，打 repr 行
python src/scripts/dev_workbench.py compile [--root <目录>]   # 递归 py_compile，逐文件报告
python src/scripts/dev_workbench.py bump --version X.Y.Z --section-file <CHANGELOG小节模板> \
  # 版本号三锚点同步（SKILL.md frontmatter / 源码内 User-Agent / CHANGELOG 小节）+ 中文内容走文件（{version} 占位符）
python src/scripts/dev_workbench.py grep --pattern <正则> [--path <目录>] [--max N]   # 纯 Python 递归 grep（跳过已知二进制，覆盖仓库全部文本文件）
python src/scripts/dev_workbench.py status   # git status --short（一次 subprocess 封装）
python src/scripts/dev_workbench.py doctor   # 环境探针（零 shell 依赖）
python src/scripts/dev_workbench.py run --script <PY路径> [-- <argv...>]   # 白名单执行仓库内 .py（不执行任意命令 / shell 字符串）
python src/scripts/dev_workbench.py run-plan --plan <JSON计划文件>   # 单进程批量执行
python src/scripts/dev_workbench.py selftest # 内置自测
python src/scripts/dev_workbench.py commit -m "<说明>"   # git commit 薄封装（转发 -m、跑完自动 doctor 确认同步；禁止 --no-verify）
python src/scripts/dev_workbench.py trash --path <路径> [--force] [--dry-run]   # 移入系统回收站（绝不硬删；先以 canary 探针验证回收站可用，不可用则拒绝真实文件）；--force 才硬删且二次告警
python src/scripts/dev_workbench.py clean [--path <目录>] [--force] [--dry-run]   # 清理仓库内 temp/ 等生成物（移入回收站；默认 temp/）；同样经 canary 护栏，回收站退化时拒绝而非静默硬删
python src/scripts/dev_workbench.py audit [透传参数...]   # 薄封装 dev_self_audit.py（质量门禁；如 --strict 直接跟在子命令后）
python src/scripts/dev_workbench.py validate [透传参数...]   # 薄封装 self_validate.py（检查器回归护栏）
python src/scripts/dev_workbench.py diff [<git diff 参数>]   # git diff --stat（默认；只读，替代裸 git diff）
python src/scripts/dev_workbench.py log [<git log 参数>]   # git log --oneline -10（默认；只读，替代裸 git log）
python src/scripts/dev_workbench.py sync   # 手动强制重同步部署副本（调用 sync_deploy.py）
```

> **bump 的中文小节走文件（非内联）**：模板文件内 `{version}` 占位符替换为新版本号（用 `replace` 而非 `format`，避免正文花括号被误解析）；未提供 `--section-file` 时回退简化模板并告警——房屋风格要求「## X.Y.Z 打磨明细（副标题）」，须人工补齐。
> **与 [agent-todo] #8 联动**：开发期改动（未提交且触及 SKILL.md / src/scripts / src/references / CHANGELOG.md / DEVELOPMENT.md / README.md）时，`dev_self_audit.py --strict` 会发 `[agent-todo][建议]` 提醒优先用本工具，详见下方指令清单。
> **安全删除纪律**：`trash` / `clean` 永远移入系统回收站（可恢复），**绝不硬删**；先以 sacrificial canary 探针验证回收站真正可用（源消失且确实进入 `$Recycle.Bin`），不可用则**拒绝操作真实文件**而非静默硬删；仅当显式 `--force` 时才硬删并二次告警，契合全局「Trash Not Delete」约定，替代了此前 `rm -f temp/*.py` 的硬删除习惯。只读核验（doctor/status/grep）与变更操作（patch/bump/commit/trash/clean/audit/validate/diff/log/sync）均为 dev 工作流统一入口。

覆盖测试：`tests/test_dev_workbench.py` 24/24 全绿（沙箱隔离、不碰真实仓库），覆盖 patch / verify / compile / bump 文件版与内联版、run-plan 四步串联、grep 截断、status 在真实 git 仓库 vs 非 git 目录的退出码差异、doctor 版本比对、selftest 正反路径。

## 开发套件的解耦约定（跨平台 / 跨 Agent）

技能本体的解耦原则（SKILL.md「设计原则（核心约束）」）**同样适用于 dev 工具**。dev 工具虽不进部署副本，却恰恰运行在环境差异最大的位置——git 钩子（本机 vs CI）、换机器、换用户名、换操作系统、换宿主 agent。因此以下为硬约定：

| 维度 | 约定 | 落地方式 |
| --- | --- | --- |
| 仓库路径 | 一律经 `__file__` 推导，绝不依赖 CWD / 绝对仓库路径 | `_devcommon.ROOT/SRC/HERE`；各 dev 脚本 `sys.path.insert(0, HERE)` 后复用 |
| 部署副本路径 | 绝不写死 `~/.workbuddy/skills/<name>` | `_devcommon.resolve_deploy_dir()`（含 `SKILL_DEPLOY_DIR` 显式覆盖 + 多 agent 候选探测） |
| 解释器 | 绝不写死 `C:/Users/<user>/.../python.exe` | `_devcommon.resolve_python()`：`SKILL_AUDIT_PYTHON` > `sys.executable` > `python3` |
| 外部命令 | 不依赖单一外部命令（curl 等） | 优先标准库（`urllib`），外部命令仅作回退 |
| 候选根列表 | 不在各工具里各抄一份 `~/.workbuddy` / `~/.claude` 等候选 | `_devcommon.candidate_roots()` 单一真相源，新增 agent 支持只改一处 |

**git 钩子（`hooks/post-commit`、`hooks/pre-push`）额外遵守**：
- python 候选一律以 `$HOME` 或系统标准路径表达（`/usr/bin/python3`、`/usr/local/bin/python3`、`/opt/homebrew/bin/python3`），**不出现任何具体用户名**；可用 `SKILL_AUDIT_PYTHON`（最高优先）或 `SKILL_AUDIT_PYTHON_CANDIDATES`（空格分隔追加）覆盖。
- `REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"` 的 `|| true` **不可省**：脚本开了 `set -e`，git 不可用会让命令替换返回非 0 并 errexit 终止，**连告警都打印不出来**——静默跳过正是要避免的失效模式。

**下载判据（实测踩过的坑）**：`dev_market_bench` 下载技能 zip 时，成功判据必须是 **zip 魔数校验**（`_looks_like_zip()` 校验前 2 字节为 `PK`）而非「文件非空」。实测 curl 默认对 404/5xx 仍返回 `rc=0`，会把服务端 17 字节错误页写进目标文件；若仅以 `size>0` 判成功，错误页会被当成下载成功、到 `zipfile` 阶段才炸且信息失真。两条路径（urllib / curl）下载后统一魔数校验，curl 另加 `-f` 使 HTTP 错误码返回非零。

## 开发模式自审计（dev_self_audit.py）

`src/scripts/dev_self_audit.py` 把以下约定固化为可重复命令，规避长期项目的记忆漂移 / 幻觉 / 漏操作：

1. **同步校验**：复用 `sync_deploy._verify()` 确认「部署副本 ↔ 最新源码 `src/`」字节一致；不一致说明有未提交改动或钩子未触发，明确告警。
2. **审计最新源码**：一律对 `src/`（最新提交）跑全量检查器，而非部署副本——避免审计过时产物。
3. **开发文档纳入漂移**：`--dev-docs` 递归扫描 `src/` 内全部 `.md` 描述性文档（含 `README.md` / `CHANGELOG.md` / `references/*.md` / `examples` 等）交 `doc`（A1 裸文件名 `EXTERNAL_REF` 提示）+ `doc-llm`（语义漂移 dossier）扫描；默认（不带此旗标）仅扫 `SKILL.md` + `references/*.md`。另 `dev_self_audit.py` 额外写死纳入仓库根三份 out-of-tree 开发文档：`README.md` / `DEVELOPMENT.md` 全文、`CHANGELOG.md` 仅**最新 3 节**（`model.py` 通用机制：`dev_docs` 条目可传 `(path, head_sections)`，前缀截断至第 4 个 `^## ` 标题前，finding 行号与原文件一致）——历史节描述的是当时的退出码/枚举/路径，拿当前代码审计只会产出假阳性漂移；最新节才是漂移风险最高的新写内容。
4. **只扫发布面**：排除 `DEV_TOOLS`（`sync_deploy.py` / `self_validate.py` / `make_fixtures.py` / `dev_self_audit.py` / `dev_market_bench.py` / `_devcommon.py` / `release_check.py` / `dev_commit.py` / `bump_audit.py` / `dev_workbench.py`），使结果与发布质量对齐，不被 dev 工具噪音干扰。
5. **开发期工具语法守卫**：`DEV_TOOLS` 不进发布面扫描，故 `_guard_dev_tools()` 对每个 dev 工具单独 `py_compile` 兜底语法关（改坏 dev 工具会立刻崩、却逃过检查器）；命中即打印 `[dev-tools] ⚠` 并追加一条 `[建议]` 非阻断项，不升退出码、不拦 push。

退出码：`0` = 无 ERROR（`--strict` 下还需无 WARN）；`1` = 发现 ERROR（或 `--strict` 下 WARN）；`2` = 参数/路径错误。

```bash
python src/scripts/dev_self_audit.py            # 同步校验 + 审计最新源码发布面 + dev 文档
python src/scripts/dev_self_audit.py --strict   # CI 门禁：WARN 也计入失败
python src/scripts/dev_self_audit.py --no-sync-check  # 跳过同步校验（仅审计）
```

dev 专用 CLI 旗标（`--dev-docs` / `dev_audit=True` / `exclude`）仅在运行本仓库的 `dev_self_audit.py` 时有效；对终端用户审计任意技能无意义，若被误用会在非本仓库上下文打印提示并忽略。

### 约定：哪些 dev 旗标进主 CLI、哪些不进（避免回退三分式）

**`--dev-docs` 进主 CLI（`cli.py:43`）——合理，且性质不同于另两项。** 它是通用能力：任意技能的维护者都能用 `--dev-docs` 把技能文件夹内全部 `.md`（`README`/`CHANGELOG`/`examples` 等）纳入漂移扫描，不是「关掉正确性检查」。所以它在用户模式 CLI 中可见是对的。默认（不带此旗标）仅扫 `SKILL.md` + `references/*.md`，开发者模式扩面到全部描述性文档。

**`dev_audit=True` 与 `exclude=DEV_TOOLS` 不进主 CLI——属本仓库专属 hack，禁止提成开关。** 理由：

- `dev_audit=True`：`structure.py:21` 用 `not ctx.get("dev_audit")` 跳过 `name_mismatch`，唯一目的是本仓库源码根目录叫 `src/` 而非技能名（`dev_self_audit.py:115` 硬编码）。而用户用本技能审计**自己**的技能时，目录即技能目录，`name_mismatch` 是正确告警；把它暴露给用户等于教用户「可关掉名称一致性检查」。
- `exclude=DEV_TOOLS`：`dev_self_audit.py:44` 排除 `sync_deploy.py` / `self_validate.py` / `make_fixtures.py` / `dev_self_audit.py` / `dev_market_bench.py` / `_devcommon.py` / `release_check.py` 本仓库 dev 工具；其他技能根本没有这些文件，暴露出去是死参数。

**硬性边界**：`dev_audit` / `exclude` 的打开点只存在于 `dev_self_audit.py`（`src/scripts/` 内，已被 `sync_deploy.py` 排除在部署副本外）。若日后有人想把 `--dev-audit` 加到 `cli.py`（它是部署副本一部分），**等于把维护者专属逻辑塞回用户技能、直接回退三分式隔离**，应拒绝。引擎默认 `dev_audit=False`（`model.py:152`）即用户模式，符合「默认零依赖、绝不替用户决定」。

### 判定逻辑：进入开发者模式由「调用入口」决定，非运行时自判

- **没有自动检测**：引擎 `analyze_skill`（`model.py:151`）默认 `dev_audit=False` / `exclude=None` / `dev_docs=None`，即用户模式；脚本**不**探测 cwd / 环境变量 / git 远端 / 调用者身份来「判断」当前处于哪种模式。
- **由调用入口决定**：跑 `audit_docs.py`（随技能发布的用户 CLI）→ 永远用户模式（`cli.py:114-116` 只传 `dev_docs=args.dev_docs`，`dev_audit` / `exclude` 不传 → 取引擎默认）；跑 `dev_self_audit.py`（dev-only）→ 开发者自审计（`dev_self_audit.py:109-116` 硬编码 `dev_audit=True` + `dev_docs=[README.md, CHANGELOG.md]` + `exclude=DEV_TOOLS`）。
- **流程完全可控、确定性**：无隐式切换、无运行时自判、无 agent 决断。终端用户装到的部署副本不含 `dev_self_audit.py`，只能跑用户 CLI，用户模式由**结构**保证，不可能「误入」开发模式。
- **唯一的运行时探测与模式无关**：`dev_self_audit.py:95` `_detect_vulture()` 仅决定 deadcode 精度（vulture / ast），非模式判断；`dev_self_audit.py:98` `doc_llm_mode=None` 非交互下跳过 doc-llm、语义比较留给交互 agent 接手，是**能力选择**（符合「默认零依赖、绝不替用户决定」），非模式开关。
- **dev 自审计内部三参不可 flag 调**：`dev_audit` / `dev_docs` / `exclude` 为硬编码常量，`dev_self_audit.py` 无 `--dev-audit` 之类开关；脚本可调 flag 仅 `--strict` / `--no-sync-check` / `--deadcode-mode`（调严度，不切换模式）。
- **禁止反向加自动检测**：不要为「是否进入开发模式」引入运行时 if 判定（如 `if os.path.basename(cwd) == "src": dev_audit=True`），那会破坏上述结构保证、引入隐式切换与回归风险；判定一律由入口显式决定。

## 触发条件（何时运行各 dev 工具）

消除「不知何时跑某 dev 工具」的困惑——下面是精确触发表。核心原则：**`dev_self_audit` 守发布质量、`self_validate` 守检查器行为，两条流水线刻意不串**（前者全量含 vulture/doc-llm、随环境可变；后者只用 `DETERMINISTIC=[doc,structure,security,runtime,deps,examples]` 确定性子集、保证可复现）。

| 你改动了什么 | 该跑 | 不该跑 | 说明 |
|---|---|---|---|
| `src/` 任意发布面文件（SKILL.md / scripts/audit_docs.py / scripts/auditlib/ / references/checkers.md / dist） | `dev_self_audit.py`（建议 `--strict`） | — | 发布质量门禁：审计最新源码 + 验证「部署副本 ↔ src」一致 + 开发文档漂移 |
| `README.md` / `CHANGELOG.md` / `references/*.md` / 任意 `.md` | `dev_self_audit.py`（默认即 `--dev-docs`，递归扫描 `src/` 内全部 `.md`） | — | 把开发文档纳入漂移扫描 |
| `src/scripts/auditlib/checkers/{doc,structure,security,runtime,deps,examples}.py` 或公共层 `model` / `report` / `core` | `self_validate.py` | — | 检查器行为回归护栏：对 fixtures 跑确定性检查器（含 examples）、比对 `tests/examples/*.expected.json` 黄金快照 |
| `src/scripts/auditlib/checkers/{deadcode,doc_llm,portability}.py` 或 fixtures / 文档自身 | `dev_self_audit.py`（视情况） | `self_validate.py` | deadcode/doc_llm/portability 不在 `DETERMINISTIC` 子集，跑 `self_validate` 无回归捕捉价值、反引入噪音 |
| dev 工具自身（DEV_TOOLS 全 10 个：`sync_deploy` / `self_validate` / `make_fixtures` / `dev_self_audit` / `dev_market_bench` / `_devcommon` / `release_check` / `dev_commit` / `bump_audit` / `dev_workbench`） | `dev_self_audit.py` 内置 `_guard_dev_tools()` 逐个 `py_compile` 兜底语法关（非阻断 `[建议]`） | `self_validate.py` | dev 工具不进发布面，`self_validate` 审计的是用户技能行为、与 dev 工具改动无关；语法盲区由 `dev_self_audit` 守卫补上 |
| 发布前（统一动作） | `dev_self_audit.py --strict` **+** `self_validate.py` | — | 一键全量：先质量门禁、再检查器回归（也可靠 CI 钩子自动覆盖） |
| 版本迭代 / 发布前收尾 | （`dev_self_audit.py` 内置 `release_check` 自动提示） | 手动记忆 | 版本号一致性(SKILL.md↔sources.py) / CHANGELOG 收口 / temp 清理 / **上架前取得用户授权**——改为门禁输出 `[agent-todo]`，不再依赖记忆 |
| 想验证检查器在规模化真实世界的稳定性 / 长尾技能质量分布 | `dev_market_bench.py run` | 人工要求 | 仅在人工要求时运行（`run`）；基准实测不进自动调度、也不由 `check-bump` 自动触发 |
| 准备 `git commit` | （`post-commit` 钩子自动 `sync_deploy`） | 手动 | 提交即同步部署副本 |
| `git push origin main` | （`pre-push` 钩子自动跑 `dev_self_audit --strict` + `self_validate`） | 手动 | 本地发布门禁，失败拦截 push |
| 推到 GitHub / 开 PR 到 `main` | （GitHub Actions `dev-qa.yml` 自动跑 `dev_self_audit --strict --no-sync-check` + `self_validate`） | 手动 | 远程兜底，防绕过 |

> 记忆锚点：`self_validate` 只在「动了检查器代码」时有意义；`dev_self_audit` 在「动了发布面 / 文档」或「发布前」跑。两者均不进部署副本，终端用户拿不到。

### 三道自动化机制分工对比

上表按「改动类型」给触发建议；下表按「自动化机制」横向对比三者各自做什么、差异在哪，避免混淆「哪个钩子负责什么」：

| 机制 | 触发时机 | 执行的命令 | 同步校验（副本 ↔ src） | 发 `[agent-todo]` | 门禁拦截 | 失败后果 |
|---|---|---|---|---|---|---|
| 同步钩子 `post-commit` | 每次 `git commit`（版本 bump 提交额外自动审计） | `sync_deploy.py`（同步副本）→ 版本变了再 `bump_audit.py`（自动跑 `dev_self_audit` 全量作**早期反馈**） | 自身即同步动作 | **否** | 否（bump_audit 恒返 0，不拦 commit） | 仅告警（commit 已成功），不阻塞 |
| 本地 CI `pre-push` | `git push origin main` | `dev_self_audit.py --strict` + `self_validate.py` | **是**（本机有副本） | **是** | 是（任一失败拦 push） | 拦截本次 push，须先修复 |
| 远程 CI `dev-qa.yml` | push/PR 到 `main`（GitHub Actions） | `dev_self_audit.py --strict --no-sync-check` + `self_validate.py` | **否**（`--no-sync-check`，CI 无副本） | **是** | 是（job 失败标红 PR） | PR 标红，拦下合并/发布 |

要点：
- **`post-commit` 职责 = 同步 + 版本 bump 自动早期审计**：提交即把 `src/` 发布面同步到部署副本（并清副本里过时的 `dist/` 残留）；**若本次提交 bump 了版本号，再由 `bump_audit.py` 自动跑一次 `dev_self_audit` 全量（含 doc + doc-llm agent + dev 文档）作早期反馈回显给 agent，不依赖 agent 记忆手动跑**。它**不发 `[agent-todo]`、不门禁**（bump_audit 恒返 0）——`[agent-todo]` 仍只来自 `pre-push` 与 `dev-qa`。（旧版曾在此按需重建发布制品 zip，现已移除——市场上架时自行重打包，本地 zip 无用且会被拒收，详见下方命令表。）
- **同步校验开关是本地与远程的唯一实质差异**：本机有部署副本故 `pre-push` 保留校验；GitHub 机器无副本，`dev-qa` 加 `--no-sync-check`。两套门禁的检查内容（`dev_self_audit --strict` + `self_validate`）完全一致。
- **`[agent-todo]` 在远程 CI 仅日志噪音、但门禁（退出码）仍生效**：GitHub 上无 agent 消费提示文本，而 `release_check` 阻断项会升 `dev_self_audit` 退出码 → `dev-qa` 的 `publish-gate` job 失败 → PR 标红，是本地钩子未拦住时的远程兜底。

### 同步钩子（`post-commit` → `sync_deploy.py`）自动执行命令表

`post-commit` 钩子（`hooks/post-commit`）同步 `src/` 发布面到部署副本后，**再调 `bump_audit.py`**：若本次提交 bump 了版本号，自动跑 `dev_self_audit.py`（全量含 doc + doc-llm agent 模式 + dev 文档）作早期反馈。**它不发 `[agent-todo]`、不做质量门禁、不构建任何制品**，只同步 + 打印同步状态行；版本未变则静默跳过。

**钩子自身的两步前置**（`hooks/post-commit`，shell）：

1. `git rev-parse --show-toplevel` 定位仓库根（**必须带 `|| true`**：脚本开了 `set -e`，git 不可用会 errexit 终止、连告警都打印不出来）。
2. 按 `SKILL_AUDIT_PYTHON` → `$HOME` 托管版本 → 系统标准路径 → `PATH` 的顺序定位解释器（git 钩子子进程**不继承**交互 shell 的 PATH，裸 `python` 可能静默失败）。

**随后 `sync_deploy.py` 自动执行的操作**（命令表）：

| # | 自动执行的动作 | 实现 / 调用 | 作用 | 失败后果 |
|---|---|---|---|---|
| 1 | 解析部署目录 | `_devcommon.resolve_deploy_dir()` → `(path, how)` | 定位要同步的目标副本（跨平台 / 跨 Agent 探测，见本文「部署目录跨平台 / 跨 Agent 解析」节） | 未找到 → 打印 `deploy dir not found ... skip` 并 `exit 0`，**不阻塞 commit** |
| 2 | 复制发布面文件 | `_sync_file()`（**仅当目标缺失或字节不一致**才复制） | `SKILL.md`、`scripts/audit_docs.py`、`references/checkers.md` | 源缺失 → 打印 `WARN src missing` |
| 3 | 递归复制发布面目录 | `_sync_tree()`（跳过 `__pycache__` / `*.pyc`） | `scripts/auditlib/**` | 源目录缺失 → 打印 `WARN src dir missing` |
| 4 | 清理副本内 `__pycache__` | `_clean_pycache(<deploy>/scripts)` | 避免旧字节码污染已安装技能 | 无 |
| 5 | 字节一致性校验 | `_verify()`（`filecmp` 逐文件比对） | 核对发布面 ↔ 副本是否一致 | `MISMATCH` → `exit 1`（仅告警，**commit 已成功**） |
| 6 | 打印结果行 | — | `synced N file(s); verify: OK` / `already up-to-date; verify: OK` | — |

> **刻意不做的事**（职责边界，避免膨胀）：
> - **不构建 `dist/` 制品**——SkillHub 上架时自行重打包，本地 zip 无用且有害（见上表）；
> - 不发 `[agent-todo]`（由 `pre-push` / `dev-qa` 的 `dev_self_audit` 负责）；
> - 不跑检查器、不做质量门禁（版本 bump 提交会由 `bump_audit.py` 自动跑一次 `dev_self_audit` 作**早期反馈**，但 `bump_audit` 恒返回 0、**不阻断 commit**；最终阻断门禁仍为 `pre-push` 的 `dev_self_audit --strict`）；
> - **绝不删除副本内发布面之外的任何文件（只增不删）**：陈旧 dev 文件需人工复核，不自动删；`dist/` 也从不产生，故无需任何清理例外（若旧副本残留 `dist/`，手动 `rm -rf <deploy>/dist` 一次即可）。

**刻意排除、不进副本的内容**（dev-only，避免污染用户技能）：

- dev 工具：`make_fixtures.py` / `self_validate.py` / `dev_self_audit.py` / `dev_market_bench.py` / `_devcommon.py` / `sync_deploy.py` / `release_check.py` / `bump_audit.py` / `dev_commit.py` / `dev_workbench.py`（原 `build_dist.py` 制品构建脚本已随「市场自行重打包」移除）
- `src/tests/`（fixtures + 黄金快照）、`__pycache__` / `*.pyc`

**真实打印样例**（本机一次提交后）：

```text
[sync_deploy] deploy dir: C:\Users\admin\.workbuddy\skills\skill-doc-audit (resolved via candidate_root:C:\Users\admin\.workbuddy\skills)
[sync_deploy] already up-to-date; verify: OK
```

> 若部署目录不存在（非标准安装且未设 `SKILL_DEPLOY_DIR`）：打印 `deploy dir not found ... skip (set SKILL_DEPLOY_DIR to override)` 并 `exit 0`（**不阻塞 commit**）——这是「优雅回落」而非「降级报错」，因为确实未安装该技能。

### 本地 CI（`pre-push` 钩子）发出的 `[agent-todo]` 指令清单

`pre-push` 钩子（`hooks/pre-push`）在 `git push origin main` 前调用 `dev_self_audit.py --strict` + `self_validate.py`，并把审计报告落盘 `bench/agent_audit_report.md`（钩子每次运行自清理、gitignored）。其中 `dev_self_audit` 在汇总后调用 `release_check.run_release_checks()` 产出提示块，并在末尾 best-effort 调用 `dev_market_bench.py check-bump` 产出版本变动提示——**本地 CI 是这些 `[agent-todo]` 仅有的两个发出方之一（另一个是远程 `dev-qa`；`post-commit` 同步钩子不发提示）**。

> **v1.27.19 起 pre-push 增强「回传 agent 分析」通道**：`dev_self_audit --strict` 输出 tee 落盘 `bench/agent_audit_report.md`（gitignore），钩子终行打印报告路径，agent 主动读取分析（不受谁 push 影响）；agent 只需读取、无需手动删除（钩子每次运行开始 `rm -f` 自清理，删除权归钩子）。另加 doc-llm 确定性门禁——`dev_self_audit` 硬编码 agent 模式写 dossier（含「正向覆盖缺口」段），钩子 `grep` 该段，列出缺口则拦 push 并打印 dossier 路径（须 agent 接手判读后才放行，挡住「doc-llm 静默通过」）；设 `SKILL_AUDIT_SKIP_DOC_LLM_GATE=1` 可放行 agent 已确认的有意缺口。详见 `hooks/pre-push`。

**钩子自身自动执行的操作**（命令表，与 post-commit 同构）：

| # | 自动执行的动作 | 实现 / 调用 | 作用 | 失败后果 |
|---|---|---|---|---|
| 1 | 解析仓库根 | `git rev-parse --show-toplevel` | 定位钩子工作目录（须 `\|\| true`，避免 git 不可用时 errexit 吞掉告警） | 解析失败 → 跳门禁 `exit 0` |
| 2 | 仅对推 `main` 执行 | 读 `stdin` 的 `rref`，非 `refs/heads/main` 直接 `exit 0` | 其他分支推送不拦截 | — |
| 3 | 未提交守卫 | `git diff --quiet HEAD -- src/ README.md CHANGELOG.md DEVELOPMENT.md` | 防止推送不完整、间接保证副本同步 | 有改动 → 打印 `git status` 并 `exit 1` |
| 4 | 定位 python 解释器 | `SKILL_AUDIT_PYTHON` → 候选链 → `PATH` | git 子进程不继承交互 PATH，须绝对路径优先 | 找不到 → 跳过门禁 `exit 0` |
| 5 | 自清理上一轮报告 | `rm -f bench/agent_audit_report.md` | 杜绝跨 push 残留（代码强制，非约定） | 无 |
| 6 | 开发模式自审计 | `dev_self_audit.py --strict`（`tee` 到报告） | 发布质量 + 部署副本同步门禁（含 doc/doc-llm agent 模式 + dev_docs） | 失败 → 打印报告路径并 `exit 1` |
| 7 | doc-llm 确定性缺口门禁 | `grep` dossier「正向覆盖缺口」段 | 代码有、文档未写则拦 push，须 agent 接手判读 | 列缺口 → 打印 dossier 路径并 `exit 1`（设 `SKILL_AUDIT_SKIP_DOC_LLM_GATE=1` 放行） |
| 8 | 示例回归自校验 | `self_validate.py` | 检查器行为回归（黄金快照比对） | 失败 → `exit 1`（有意变更先 `--baseline`） |
| 9 | 打印报告路径 / 放行 | `echo` 报告路径 | agent 读取判读；报告下次 push 自动清理 | — |

> 注：第 6/7 类（`[agent-todo]`）的**审计执行**自 v1.27.19 起已由上表第 6 步 `dev_self_audit --strict` 自动覆盖，v1.27.21 起不再作为「agent 必须手动跑命令」的指令打印（见下方指令清单表后说明），避免与钩子重复、且误导为手动门禁。

> 下列「指令清单」汇总本地 CI **所有可能发出的 `[agent-todo]`**，逐项给出：触发条件、发出的指令（可照做动作）、严重度与是否阻断。其中第 1–3 类来自 `release_check.py`（版本一致性 / CHANGELOG 收口 / temp 清理），第 4–7 类来自 `dev_market_bench.py check-bump`（第 4 类上架授权为 `[必须]` 阻断、任何版本变化都打印；第 5 类文档无版本叙述、第 6 类基准实测建议[次/主版本]、第 7 类未提交提示为 `[建议]` 不阻断；第 7 类常驻、不依赖版本变动）；第 8 类（开发工作流提醒，[建议] 不阻断）来自 `release_check.check_dev_workbench_usage`，**可靠触发点已下移至 `dev_commit.py` 提交前**（开发面改动仍可见时必触发），`dev_self_audit` 保留为冗余安全网（提交后树已干净、通常不再触发）；非发布门禁。

| # | 标识 / 严重度 | 触发条件 | 发出的 `[agent-todo]` 指令（原文要点） | 阻断 |
|---|---|---|---|---|
| 1 | `[agent-todo][ERROR]` | `SKILL.md version` ≠ `sources.py` 第144行 `User-Agent` | `将 src/scripts/auditlib/sources.py 第144行的 User-Agent 改为 skill-doc-audit/<SKILL版本>` | **是** |
| 2 | `[agent-todo][WARN]` | `SKILL.md version` 高于 `CHANGELOG.md` 最高版本节 | `将 CHANGELOG.md 的「未发布改动」节提升为 '<SKILL版本> 打磨明细' 节后再提交` | **是** |
| 3 | `[agent-todo][INFO]` | `temp/` 下有 `*_test*.py`/`*.mhtml`/`_eval*.txt`/`stress*`/`_rezip*`/`*.py`；或仓库根/`src` 下存在 `*.bak`/`*.bak.*` 过时备份 | `及时清理 temp/ 测试残留与 `*.bak` 备份（默认保留最近 3 个、更早的删除）；⚠ 清理前先确认这些文件非你手动放入，再删除（遵循 temp/ 管理约定）` | 否 |
| 4 | `[agent-todo][必须]`（阻断） | **任何版本变化**（x.y.z 任一字段变动，**含补丁号**） | `上架 SkillHub 前须先获得用户明确授权同意（不得自动发布）`：SkillHub 上架属对外公开动作，须用户点头；未获授权前只能本地 commit/push，不得 publish。→ 先询问用户取得授权；获准后 `skillhub publish <技能目录> --changelog "..." --json`（发布目录内**不得含 `dist/` 或任何 `.zip`**：市场自行重打包，目录内含 zip 会返回 400「不允许的文件类型」） | **是** |
| 5 | `[agent-todo][建议]` | **任何版本变化**（x.y.z 任一字段变动，**含补丁号**） | `版本变动时用户文档（SKILL.md / references/*）无需写入版本变动叙述`：如「vX.Y.Z 新增 / 升级」类里程碑叙述应留在开发者文档（CHANGELOG.md）；用户文档只描述当前能力本身。→ 发版前复核 SKILL.md 与 references/*.md 是否混入版本号里程碑叙述，有则删除 | 否 |
| 6 | `[agent-todo][建议]` | **次版本 / 主版本变动**（x.y / X.y，x 或 y 中任一变动） | `⚠ 决策点：是否运行「市场质量基准实测器」做完整实测？`：次/主版本属质量高风险点（检查器逻辑 / 误报抑制 / 风险口径可能变动），建议评估是否运行一次规模化基准验证稳定性 → `python src/scripts/dev_market_bench.py run`（默认随机抽 50 个市场技能全量审计；可 `--sample` / `--seed` / `--dedup`）；仅在人工要求或本建议触发时启用，不进自动调度、绝不由 `check-bump` 自动触发 `run` | 否 |
| 7 | `[agent-todo][建议]` | 仓库存在未提交改动（`git status --porcelain` 非空） | `检测到未提交的本地改动，请立即本地 commit`：本地提交即触发 post-commit 钩子同步部署副本，避免 src 与部署副本 / 版本号长期脱节；提交与发布解耦，未上架也可随时提交。→ `python src/scripts/dev_commit.py -m "<有意义说明>"`（静态提交助手：自动 git add -u + commit，commit 触发 post-commit 同步部署副本；新增文件加 --all 或显式传路径） | 否 |
| 8 | `[agent-todo][建议]` | 未提交改动触及「开发面文件」（SKILL.md / src/scripts / src/references / CHANGELOG.md / DEVELOPMENT.md / README.md） | `开发面改动按边界使用 dev_workbench.py（提交不属其职责）`：• 版本 bump / 改 SKILL.md·CHANGELOG·脚本：用 `dev_workbench.py bump --version X --section-file <tpl>` / `patch --old-file/--new-file` / `verify`，多字节与转义走 `--*-file`；• 只读核验（版本锚点/部署同步/git 状态/grep）：用 `dev_workbench.py doctor` / `status` / `grep`，勿用裸 Bash `git status` 或 Read/Grep；• 提交：走 `dev_commit.py`（触发 post-commit 同步），或经薄封装 `dev_workbench.py commit -m "..."`，但 commit 本身不属 dev_workbench、严禁裸 `git commit`。仅 [建议]、不阻断、不升退出码 | 否 |

> **旧第 6 / 7 类已于 v1.27.21 退役（与 `pre-push` 钩子的执行重叠）**：`pre-push` 在每次推 `main` 前已自动跑 `dev_self_audit.py --strict`（其内硬编码 doc-llm agent 模式、dev_docs 写死含 README/CHANGELOG）+ `self_validate.py`，并对 doc-llm 确定性「正向覆盖缺口」做门禁、落盘报告 `bench/agent_audit_report.md`。因此旧第 6 类（补丁号 doc+doc-llm 文档自审计）与旧第 7 类（次/主版本全量自审计）的**执行已被钩子 100% 覆盖**——继续把它们作为 `[agent-todo][必须]`（阻断）的「agent 必须手动跑命令」指令，既与钩子重复、又误导为手动门禁，故 v1.27.21 从 `dev_market_bench.py check-bump` 移除这两条打印：
> - 审计的**门禁**由钩子跑审计后的检查器结果决定（如确有 doc 漂移，doc 检查器报错即拦 push），不依赖 agent 手动跑命令；
> - agent 的**保留职责是语义判读**：仅当钩子拦截（打印 dossier / 报告路径）时读取并决定「补文档 or 确认缺口有意（`SKILL_AUDIT_SKIP_DOC_LLM_GATE=1` 放行）」；
> - 真正只能 agent 做、无法自动化的是第 4 类（上架授权，须问用户）——它保留为 `[必须]`（阻断），见上表。
>
> **报告文件生命周期（代码强制，不依赖 agent 记忆）**：`bench/agent_audit_report.md` 由钩子每次运行开始时 `rm -f` 自清理上一轮，且 `bench/` 已 gitignore——即便意外残留也不进版本库；doc-llm dossier 写在系统临时目录、由 OS 清理。**agent 只需读取、不应手动删除**（删除权归钩子）。这避免了「靠记忆删除」的脆弱模式。

**提示块的实际打印格式**（来自 `dev_self_audit.py:153-165`，以「版本不一致」为例的真实渲染）：

```text
========================================================================
发布前待办（Agent 提示 · 由 pre-push 钩子与 dev-qa 工作流发出）
========================================================================
  [agent-todo][ERROR] 版本号不一致：SKILL.md 与 sources.py User-Agent 不同步
      SKILL.md version=1.25.4，但 sources.py 的 HTTP User-Agent=skill-doc-audit/1.25.3
      → 将 src/scripts/auditlib/sources.py 第144行的 User-Agent 改为 skill-doc-audit/1.25.4

⚠ 存在阻断项，发布前须先解决（--strict 下将失败）。
```

> 第 4–7 类 `[agent-todo]` 均来自 `dev_market_bench.py check-bump`（第 4 类上架授权 / 第 5 类文档无版本叙述 / 第 6 类基准实测建议[次/主版本] / 第 7 类常驻未提交提示）；第 8 类来自 `release_check.check_dev_workbench_usage`（开发工作流提醒，[建议] 非门禁），由 `dev_self_audit.py` 经 `_parse_check_bump` 解析后并入同一「发布前待办」块（[必须] 进 rel_block 阻断、[建议] 进 rel_info 不阻断），**不再纯透传 stdout**；rel_info 项现以「非阻断项（请逐项确认是否适用）」小标题分组呈现，避免被阻断项淹没；与上面的 release_check 提示合并显示。
> - **第 4 类（上架授权）为任何版本变化（含补丁号）都打印**，且为 `[必须]` 阻断：任何版本都可能需要上架、而上架属对外公开动作须先经用户授权（不能只在次/主版本提醒，否则补丁版本会被静默上架）；第 5 类（文档无版本叙述）同样任何版本变化都打印（版本变动叙述在任何级别迭代中都可能误写入用户文档）；第 6 类（基准实测建议）仅次/主版本变动打印（评估是否运行完整实测，非阻断）；第 7 类（未提交改动）常驻（见下）。
> - 严重度标签语义：第 4 类打 `[必须]`（阻断，**`--strict` 下升退出码、拦 push**）——仅上架授权（覆盖任意版本，上架属对外公开动作、须用户授权）；第 5 类（文档无版本叙述）、第 6 类（基准实测建议）、第 7 类（未提交改动）为 `[建议]` 不阻断。审计门禁已由 pre-push 钩子跑 `dev_self_audit --strict` 的检查器结果承担，不再由 `[agent-todo]` 提醒 agent 手动跑命令。
> - **第 7 类为常驻通用提示（不依赖版本变动）**：只要 `git status --porcelain` 非空（有未提交改动）就打印，旨在防止长期开发中因记忆漂移遗漏本地 commit、使 src 与部署副本 / 版本号脱节；属 `[建议]` 不阻断、不升退出码。仓库已干净时不打印（与其余版本变动提示正交，任何版本 / 任何状态都可能触发）。
> - 检测基线存于 `bench/market_bench/last_bench_version.txt`（gitignore，不进版本库）；每次运行都刷新为当前版本，故同一版本变动只提示一次。
> - 真实渲染样例（次版本 1.24.0 → 1.25.7 触发；第 4 类上架授权进 `rel_block` 阻断、第 5/6/7 类进 `rel_info` 不阻断；补丁号样例附后）：

```text

  [agent-todo][必须] 上架 SkillHub 前须先获得用户明确授权同意（不得自动发布）
    SkillHub 上架属对外公开动作，须用户点头；未获授权前只能本地 commit/push，不得 publish
    → 先询问用户取得授权；获准后：skillhub publish <技能目录> --changelog "..." --json
    （发布目录内不得含 dist/ 或任何 .zip：市场自行重打包，目录内含 zip 会返回 400「不允许的文件类型」）

  [agent-todo][建议] 版本变动时，用户文档（SKILL.md / references/*）无需写入版本变动叙述
    如「vX.Y.Z 新增 / 升级」类里程碑叙述应留在开发者文档（CHANGELOG.md）；用户文档只描述当前能力本身
    → 发版前复核：SKILL.md 与 references/*.md 是否混入版本号里程碑叙述，有则删除、仅留行为/能力描述
  [agent-todo][建议] ⚠ 决策点：次/主版本变动——是否运行「市场质量基准实测器」做完整实测？
    次/主版本属质量高风险点（检查器逻辑 / 误报抑制 / 风险口径可能变动）；建议评估是否运行一次规模化基准以验证稳定性
    → python src/scripts/dev_market_bench.py run （默认随机抽 50 个市场技能全量审计；可 --sample / --seed / --dedup）
    （仅在人工要求或本建议触发时启用，不进自动调度、绝不由 check-bump 自动触发 run）

（补丁号样例：1.27.2 → 1.27.3，仅上架授权（第 4 类）+ 文档无版本叙述（第 5 类）触发）

  [agent-todo][必须] 上架 SkillHub 前须先获得用户明确授权同意（不得自动发布）
    …（同上，任意版本均触发）
  [agent-todo][建议] 版本变动时，用户文档（SKILL.md / references/*）无需写入版本变动叙述
    …（同上，任意版本均触发）

  [agent-todo][必须] 上架 SkillHub 前须先获得用户明确授权同意（不得自动发布）
    …（同上，任意版本均触发）
  [agent-todo][建议] 版本变动时，用户文档（SKILL.md / references/*）无需写入版本变动叙述
    …（同上，任意版本均触发）
```

> ⚠ 历史坑位：`check-bump` 曾因 `current_version()` 读出的版本带 YAML 引号（`"1.25.7"`）导致 `_ver_tuple` 解析失败、`is_minor_or_major_bump` 恒为 `False`、次/主版本变动也**从不提示**（形同虚设）。已修复（`current_version()` 去引号 + `_ver_tuple` 健壮性增强），修复后次/主版本变动能正确打印第 5、7 类（旧 #7 为全量自审计 `[必须]` 阻断、#5 为基准 `[建议] 不阻断）；补丁号变动则打印第 6 类（doc+doc-llm，`[必须]` 阻断）。三者（旧 #6/#7 审计提醒）已于 v1.27.21 退役，执行改由 pre-push 钩子自动覆盖；彼时清单第 6 类为「上架授权」、第 7 类为「文档无版本叙述」、第 8 类为「未提交改动」；v1.34.1 曾精简为 6 类（上架授权=第4类、文档无版本叙述=第5类、未提交改动=第6类），v1.34.2 应需求恢复次/主版本基准实测建议为第 6 类、未提交提示顺移第 7 类（当前 8 类：上架授权=第4类、文档无版本叙述=第5类、基准实测建议=第6类、未提交改动=第7类、开发工作流提醒[优先用 dev_workbench]=第8类）。

> 注：`release_check` 自身异常或被 import 失败时，只发一条 `INFO` 提示「发布就绪检查不可用 / 手动核对版本号·CHANGELOG·temp」，绝不因此阻断门禁。

> 此外，`dev_self_audit` / `cli.py` 的汇总区会打印**检查器执行回执**（v1.25.5）：逐检查器标 `#身份代号 名称` 与 `✓ 已执行 / ✗ 执行失败 / ✗ 未注册(UNKNOWN)`，尾部一行 `检查器执行回执: ✓doc … ✓doc-llm ✓examples  [9/9 已执行 OK]`。这是给 agent / 使用者的显式信号——确证每个检查器「真的跑过」，而非像 doc-llm 旧 bug 那样静默落空却显通过；`UNKNOWN`（注册键拼写不一致）/ `FAILED`（执行抛异常）会额外转成 ERROR 发现并升退出码。

### 远程 CI（`dev-qa.yml`）发出什么

`dev-qa.yml` 有两个 job，调用命令与本地 `pre-push` **完全相同**（仅 `dev_self_audit` 多一个 `--no-sync-check`）。因此它发出的提示 **与本地 CI 同源、内容一致**：

- **`[agent-todo]` 块**：来自 `publish-gate` job → `dev_self_audit.py --strict --no-sync-check`，7 类提示（release_check 产 #1-3 + check-bump 产 #4-7）的文案、渲染格式同上「本地 CI（`pre-push` 钩子）发出什么」节，**逐字一致**。唯一差别是少了「`[sync] ⚠ 不一致`」那行（CI 机器无部署副本，`_verify` 被跳过）。
- **`[PASS]` / `[FAIL]` / `[SKIP]` 行**：来自 `checker-regression` job → `self_validate.py`，**逐 fixture** 比对黄金快照，真实打印形如：

```text
[PASS] dirty-skill  (summary: error=13 warn=3 info=0 pass=0)
[FAIL] tricky-clean
       - summary.error: expected=0 got=1
       - 额外发现(+1): ('security', 'HARDCODED_SECRET', 'ERROR', 'scripts/main.py', '...')
[SKIP] ts-skill: 黄金快照缺失（先跑 --baseline）
```

  - 全部 fixture 通过则 `exit 0`；任一 `[FAIL]` 或 `[SKIP]` → `exit 1` → 该 job 标红。
  - fixtures 缺失时先自动调 `make_fixtures.build()` 重建并打印 `[self_validate] fixtures 缺失，已用 make_fixtures 自动重建于 <path>`；`--baseline` 时打印 `[BASELINE] <name> -> <golden>`（正常流程不触发）。

> GitHub Actions 上没有 agent 消费 `[agent-todo]` 文本——那几行只是 CI 日志噪音；但 `release_check` 的**阻断项会让 `dev_self_audit` 退出码升为 1** → `publish-gate` job 失败 → **PR 标红**，是本地 `pre-push` 没拦住（或换机器直推）时的远程兜底。**所以远程 CI 的价值在「门禁退出码」而非「提示文本」。**

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

- **版本号一致性（阻断，两处机器校验）**：① `SKILL.md` `version` 必须等于 `sources.py` 第144行的 `User-Agent: skill-doc-audit/<ver>`；② `SKILL.md` `version` 必须等于 `README.md`「版本摘要」表最新版本行。任一处不一致 → ERROR 并打印精确修复指令，`--strict` 下拦下 push。（`CHANGELOG` 最高版本节仍仅校验「已收口」，不逐字比对。）
- **CHANGELOG 收口（阻断）**：`SKILL.md` 版本高于 CHANGELOG 最高版本节时，提示把「未发布改动」提升为 `<ver> 打磨明细`；WARN，`--strict` 下拦截。
- **temp/ 残留（提示）**：`temp/` 发现 `*_test*.py` / `*.mhtml` / `_eval*.txt` / `stress*` 等临时产物时提示清理；INFO，且提示重申「清理前先确认非用户手动放入的文件」（遵循 temp/ 管理约定）。

阻断项与 `--strict` 的 WARN 同样计入 `dev_self_audit` 退出码，故会拦下 `pre-push`；非阻断项仅作 INFO 提示，不阻塞常规提交/推送。效果：把「发布前该做什么」从记忆下沉为门禁输出。

## 部署副本同步（sync_deploy.py + 提交即同步钩子）

- `sync_deploy.py`（dev-only）：把 `src/` 发布面（SKILL.md / scripts/audit_docs.py / scripts/auditlib/** / references/checkers.md）字节级同步到部署副本 `~/.workbuddy/skills/skill-doc-audit`，清理 `__pycache__` 与历史 `dist/` 残留，末段校验一致性；**刻意排除** dev 工具与 `tests/`。**不再产出或同步任何制品 zip**——市场在上架时自行重打包，本地 zip 无用且会导致上传被拒（详见「同步钩子（`post-commit` → `sync_deploy.py`）自动执行命令表」）。
- `hooks/post-commit`（`git config core.hooksPath` 须为**本仓库的绝对路径** `<repo>/hooks`，勿照抄他人路径）：每次 `git commit` 后自动运行 `sync_deploy.py`，**提交即同步**。⚠ 钩子必须在能找到 `python` 的环境运行，且 `core.hooksPath` 必须为绝对路径——相对 `../hooks` 会被 git 解析到仓库外导致钩子永不触发；提交后务必 `diff` 核验副本一致，不能只看 commit 成功。

部署目录解析（与用户名/平台/设备/宿主 agent 解耦，**非标准安装、非 WorkBuddy agent 下真正定位、不降级**）：`sync_deploy.py` 与 `dev_self_audit.py` 均通过 `_devcommon.resolve_deploy_dir()` 解析，返回 `(path, how)`（how 打印在同步日志，便于排查）。优先级：
1. `SKILL_DEPLOY_DIR`（显式按机覆盖，最高，绕过一切自动探测——任意平台 / 任意 agent 通用）
2. `SKILLS_DIR` / `AGENT_SKILLS_HOME`（通用覆盖：任意 agent 可指向自家 skills 根，跨 agent 自动探测次高）
3. **`WORKBUDDY_CONFIG_DIR` / `CODEBUDDY_CONFIG_DIR` + `/skills/<name>`** —— WorkBuddy 运行时**必导出**的配置目录（见进程环境 `WORKBUDDY_CONFIG_DIR=C:\Users\admin\.workbuddy`），非标准安装 / 自定义数据目录 / 换用户名均可靠定位
4. `~/<WORKBUDDY_DATA_FOLDER_NAME>/skills/<name>`（数据文件夹名 + 主目录，默认 `.workbuddy`）
5. `~/.workbuddy/skills/<name>`（标准跨平台默认，`~` 按当前用户展开，不写死盘符/用户名）
6. **跨 agent 候选根探测兜底**：`~/.claude/skills`、`~/.claude/plugins`（含嵌套布局，bounded walk）、`~/.config/claude/skills`、`~/.cursor/skills`、`~/.codex/skills`、`~/.opencode/skills`、`~/.aider/skills`，以及平台根 `LOCALAPPDATA/CodeBuddyExtension/skills`、`APPDATA/WorkBuddy/skills`、`XDG_DATA_HOME/workbuddy/skills`、`~/Library/Application Support/WorkBuddy/skills`——覆盖「裸终端运行、未继承 `WORKBUDDY_*` 变量、或非 WorkBuddy agent 托管」的场景

> 严格测试已证明跨平台 + 跨 agent 定位均可靠（见 `tests/test_resolve_deploy.py` 的 T1–T6）：`SKILL_DEPLOY_DIR` 显式覆盖、`SKILLS_DIR` 通用覆盖、`WORKBUDDY_CONFIG_DIR` 非标准安装、Claude 扁平 / 插件嵌套布局均实际命中并 `verify: OK`，**不再 skip/降级**。只有「所有候选根都找不到该技能」的极端情况才退回默认并优雅跳过——那已不是降级，而是确实未安装（如该 agent 从未装过本技能，此时用 `SKILL_DEPLOY_DIR` 显式指向即可）。

手动触发：`python src/scripts/sync_deploy.py`（可用 `SKILL_DEPLOY_DIR` 覆盖目标路径）。

## 版本发布工作流（版本直接升，不累积）

**版本号与上架授权是解耦的两件事**（用户 2026-09-01 明确、2026-09-04 重申）：

- **版本号直接升**：凡有版本相关改动，**立即 bump 版本号并写进 `CHANGELOG.md` 对应版本节**，不等上架授权、不攒「未发布改动」累积节。曾因把「未拿到上架授权」误当作「也不升版本号」的理由而违规攒过一次（v1.34.8），已纠正（v1.34.9 起一律直接升）。
- **push / 上架归用户手动**：本地改动照常 `git commit`（触发同步钩子），`git push origin main` 由维护者手动执行；SkillHub 上架须用户显式授权，agent 绝不自动 publish。发布节奏：多个连续版本只上架最新一版，不每次微改都发。


## 文档分层约定（用户模式文档如何写）

- `src/SKILL.md`：用户模式，精简——能力一句话地图 + Agent 执行约定（动作）+ 紧凑错误码速查 + FAQ；详细规格不在此展开。
- `src/references/checkers.md`：完整参考（模式机制 / 判定口径 / 误报抑制 / Phase 演进），是用户模式文档的明细基准。
- 本文件（DEVELOPMENT.md）：开发模式，仅维护者。
- 任何文档改动后须复跑 `dev_self_audit.py --strict` 确认 `ERROR 0 / WARN 0`，并提交触发同步钩子。
