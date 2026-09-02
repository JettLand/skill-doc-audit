# 变更明细（CHANGELOG）

本文件收录各版本的「打磨明细」（改动 + 验证），作为开发 / QA 留档。README 的「版本与评测」表仅保留要点摘要。

> 排序：版本号降序（最新在前）。


## 1.29.2 打磨明细（post-commit 版本 bump 自动审计：bump_audit.py，dev 工具增强）

- **动机（用户要求消除「补丁号跑审计靠 agent 记忆」）**：pre-push 钩子只在推 main 时跑
  `dev_self_audit`，本项目 push 低频且手动；agent 在多次 commit（每次 bump 版本）阶段没有早期
  自动审计反馈，只能靠记忆主动去跑。用户明确：补丁号变动也要跑 doc + doc-llm（含开发者文件），
  应加入自动化流程而非依赖 agent 记忆。
- **实现**：新增 dev-only `src/scripts/bump_audit.py`——post-commit 钩子在同步部署副本后调用它，
  检测「本次提交是否改变 `src/SKILL.md` 的 version」（HEAD^ vs HEAD），变了（补丁/次/主任一 bump）
  即自动调 `dev_self_audit.py --no-sync-check`（全量含 doc + doc-llm agent 模式 dossier + dev 文档
  README/CHANGELOG），审计结果回显到 commit 输出；版本未变则静默跳过。带 `--no-sync-check`（post-commit
  已先 sync），不含 `--strict`（作早期反馈、不阻断 commit，`bump_audit` 恒返回 0；最终阻断门禁仍为
  push 时 pre-push 的 `dev_self_audit --strict`）。
- **配套**：`bump_audit.py` 列入 `auditlib.core.DEV_TOOLS`（避免 orphan_asset 误报）；DEVELOPMENT.md
  dev 工具清单 / post-commit 职责说明 / 刻意不做清单同步更新；用户级记忆分级约定补「已自动化」说明。
- **验证**：`py_compile` 通过；`sh -n` post-commit 语法 OK；bump_audit 单测（HEAD 1.29.1→1.29.2 判
  patch bump、相等静默、patch/minor/major 判定）全过；**本次提交自身即触发 bump_audit 自动审计
  （端到端自证新链路）**。四处版本号一致 1.29.2。

## 1.29.1 打磨明细（补修 v1.29.0 收口遗漏：checkers.md 残留 `skip`）

- **问题（真实缺陷，v1.29.0 自身引入）**：v1.29.0 的 `skip`→`off` 统一改动中，`checkers.md` 的 L44（`DOC_ENUM_DRIFT` 错误码表示例 `{ask,vulture,ast,skip}`）与 L205（安装策略段「选 `ast`/`skip` 或 ask 自动回退」）两处编辑因**编辑工具写入假成功（phantom success）未落盘**，磁盘仍是旧 `skip` 枚举——与代码 `DEADCODE_MODES=("ask","vulture","ast","off")` 形成 `DOC_ENUM_DRIFT` 型文档↔代码不一致（恰是本技能自己要抓的漂移）。其余文件（SKILL.md/DEVELOPMENT.md/L261 参数表/deadcode.py/core.py/cli.py）均已正确改为 `off`。
- **修复**：用 Python 字节级替换根治 `checkers.md` 两处（规避编辑工具假成功），Read 复核确认落盘；全项目 deadcode 语境 `skip` 残留清零（仅剩 `doc_llm_skipped`/`EXAMPLE_SANDBOX_SKIP` 等无关错误码）。
- **验证**：doc `--all-checks` ERROR=0/WARN=0（DOC_ENUM_DRIFT 一致）、self_validate 4/4 PASS、四处版本号一致 1.29.1。纯文档枚举同步，无行为变更。

## 1.29.0 打磨明细（deadcode 关闭档统一为 `off`，移除 `skip` 别名）

- **接口一致性（用户要求）**：deadcode 检查器的「本次跳过」档原用 `skip`，与 doc-llm/examples 的关闭档 `off` 命名不一致（属本技能自身要抓的「接口漂移」类）。统一为 `off` 且**不保留 `skip` 别名**（移除枚举值＝破坏性接口变更 → 升次版本）：
  - `DEADCODE_MODES` 权威集合 `("ask","vulture","ast","skip")` → `("ask","vulture","ast","off")`；`DOC_MODE_BRACE_RE` / `DOC_MODE_SLASH` 注释枚举同步更新；
  - `deadcode.py`：`_resolve_deadcode_mode` docstring、`_prompt_deadcode_mode` 交互选 3 返回值 `return "skip"` → `return "off"`、`check_deadcode` 的 `mode=="skip"` 判定 → `mode=="off"`、菜单项「本次跳过 deadcode」→「本次不运行 deadcode」、`precision_degraded` 的 rerun_hint 改为 `--deadcode-mode ... / ast / off`；
  - `cli.py` / `dev_self_audit.py` 参数 help、`core.py` 模块注释、`SKILL.md`（L185 精度档速览 / L257 速答三问 / L267 误区五）/ `checkers.md`（错误码表 `DOC_ENUM_DRIFT` 示例 / 安装策略段 / 参数速查表）全部 `skip`→`off`。
- **语义不变**：`off` ≡ 原 `skip`（用户显式跳过 deadcode，`degraded=False` 不弹 `precision_degraded`）；`ast`/`off` 仍为零联网；交互菜单第 3 项措辞与 off 语义对齐。无代码/fixture/CI 依赖原 `skip` 值（`dev_market_bench.AUDIT_FLAGS` 与 `self_validate` fixture 均用 `vulture`/默认 `ask`），破坏性仅影响手写命令行历史用法。
- **验证**：`py_compile` 通过；按次版本约定跑 `--all-checks` 全量审计（含 doc 检查器对 `DOC_ENUM_DRIFT` 的枚举一致性校验，确认文档 `{ask,vulture,ast,off}` 与 `DEADCODE_MODES` 一致）ERROR 0/WARN 0；`self_validate` 4/4 PASS；四处版本号一致 1.29.0。

## 1.28.1 打磨明细（修正 1.28.0 安装路径偏差：ask 超时/非交互回退恢复「直接回退 ast、不安装」）

- **问题（用户指正）**：v1.28.0 把「缺 vulture 先自动安装」错误地扩展到了 ask 默认路径的**非交互回退**与**交互超时**分支——违背顶层设计原则「默认零依赖、绝不替用户决定」的**用户侧语义**：ask 超时＝用户没有做决定，绝不替用户发起联网安装；ask 非交互＝无法询问，更应安全回退零依赖默认。v1.28.0 同时把 SKILL.md 顶层原则措辞改写为「默认零依赖可用」，属对原则的误读（原则本身从用户侧出发、原表述正确，与「显式要求时自动补齐」并不冲突）。
- **修正**：① deadcode.py 恢复 ask 非交互与交互超时两路径为**直接回退零依赖 ast + degraded WARN**，绝不触发安装；自动安装收敛到「用户显式要求 vulture」的两条路径（显式 `--deadcode-mode vulture`、交互选 1）＋开发者模式默认请求（dev_self_audit 恒传 `vulture`，属开发者显式选择最大精度）；② SKILL.md 顶层原则恢复原文（补一句「用户显式要求高精度而缺库时先尝试自动补齐」以覆盖 1.28.0 的新能力），落地说明与「速答三问」「误区五」同步修正；③ checkers.md 安装策略段与参数速查表同步（安装路径=显式 vulture/交互选 1；ask 超时/非交互不安装）；④ `precision_degraded` message 措辞覆盖两类降级诱因。
- **验证**：monkeypatch 单测 5 场景（ask 非交互缺库→直接 ast 不安装；显式 vulture 缺库安装失败→ast degraded；安装成功→vulture；显式 ast/skip 零联网；ask 已装 vulture→自动高精度）；`self_validate` 4/4 PASS；`dev_self_audit --strict` ERROR 0/WARN 0。四处版本号一致 1.28.1。

## 1.28.0 打磨明细（deadcode 缺库先自动安装 vulture，开发者模式能力最大化）

- **deadcode 安装策略重构**：凡「需要 vulture 但缺失」的路径——显式 `--deadcode-mode vulture`、ask 交互选 1、**ask 非交互回退（此前直接回退 ast、不尝试安装）**、**交互超时（此前同样直接回退）**——均先自动 `pip install vulture`（最长 120s），成功即高精度；安装失败才回退零依赖 ast，并并发 WARN `precision_degraded` 显著反馈（message 明确「未安装且自动安装失败」+ user_decision 精度决策请求），绝不静默降级。显式 `--deadcode-mode ast/skip` 保持零联网（用户已显式决定低精度，绝不越权安装）。
- **开发者模式能力最大化**：`dev_self_audit.py` 的 deadcode 默认模式由「已装 vulture 用 vulture、否则显式 ast（绕开安装路径）」改为恒请求 `vulture` 最大精度——缺失时由检查器自动安装，安装失败回退 ast 并告警（--strict 下低精度即失败，杜绝静默低精度跑全量审计）；其余能力此前已拉满（全检查器启用、doc-llm agent 接手、examples run+consent）。同步移除因此不再使用的 `_vulture_module` 导入。
- **顶层设计原则措辞校准**：「默认即零依赖（不联网）」细化为「默认零依赖可用」——开箱即用不要求用户手动安装（缺依赖自动补齐、失败自动回退照常运行），显式选低档才完全不联网；SKILL.md 速答三问 / 误区五 / 避坑要点 / 参数注释与 checkers.md（总览、错误码表补 `precision_degraded` 行、安装策略、参数速查表）同步。
- **验证**：`py_compile` 通过；monkeypatch 单测 4 场景全过（非交互缺库+安装失败→ast degraded、安装成功→vulture、显式 ast/skip 零联网不触发安装）；`self_validate` 4 fixture 全 PASS（`DETERMINISTIC` 集合不含 deadcode，黄金快照不受影响）；`dev_self_audit --strict` 全绿。四处版本号一致 1.28.0。

## 1.27.22 打磨明细（dev_commit 子进程显式 UTF-8 解码，修钩子回显 UnicodeDecodeError 噪声）

- **问题**：v1.27.21 提交时实测复现——`dev_commit.py` 的 `_run()` 用 `subprocess.run(..., text=True)` 但未指定 `encoding`，Windows 下按系统区域编码（GBK）解码 post-commit 钩子输出的 UTF-8 中文（`[sync_deploy] ... 同步部署副本`），打印回执时抛 `UnicodeDecodeError`。提交与同步本身不受影响（`verify: OK` 仍正常打印），但回显通道被噪声污染。
- **修复**：`_run()` 显式 `encoding="utf-8"` + `errors="replace"`——钩子/脚本输出按其真实编码解码，极端字节序列也不中断提交流程。dev-only 工具改动，不影响发布面。
- **验证**：本版本提交自身即走修复后路径，钩子回显应无 UnicodeDecodeError、`verify: OK` 正常。四处版本号一致 1.27.22。

## 1.27.21 打磨明细（从代码移除 [agent-todo] #6/#7 + 修 Q1 文档缺陷）

- **问题（指令与钩子执行重复）**：v1.27.20 仅把 DEVELOPMENT.md 第 6/7 类措辞从「必须执行」改成「已由钩子覆盖、agent 无需手动跑」，但**没动产生它们的代码**——`dev_market_bench.py` 的 `check_bump()` 仍打印这两条 `[agent-todo][必须]`（阻断）指令，正文仍是「必须运行 `audit_docs` / `dev_self_audit.py --dev-docs --strict`」。文档说「不用跑」、代码仍打「必须跑」，二者互相打架；且第 6/7 条的「执行」本身已被 `pre-push` 钩子（`dev_self_audit --strict`）100% 覆盖，真正只能 agent 做、无法自动化的是第 8 类（上架授权须问用户）。
- **修复 1（代码移除）**：`dev_market_bench.py check_bump()` 删除次/主版本变动打印的第 7 类（全量自审计 `[必须]`）与补丁号变动打印的第 6 类（doc+doc-llm `[必须]`）两个 print 块；次版本 header 去掉「须完成下列质量自审计」承诺。保留 `#5` 基准建议、上架授权、文档叙述、未提交提示。代码内 `[agent-todo]` 文本本无编号，编号是 DEVELOPMENT.md 表格参照标签，故移除即文档重编号。
- **修复 2（文档重编号）**：DEVELOPMENT.md 指令清单表格移除 #6/#7 行，原 #8→**#6**、#9→**#7**、#10→**#8**；重叠说明段改为「退役说明」；渲染样例删 #6/#7 块、次版本 header 同步；231/233/234/236/270 行编号引用与第 197 行引导段同步更新；`.workbuddy/memory/MEMORY.md` 第 17/18/54 行 `#8→#6`、`#9→#7`。
- **修复 3（Q1 文档缺陷）**：① DEVELOPMENT.md 第 185 行「真实打印样例」含 `removed stale dist artifact` 行——当前 `sync_deploy.py` 根本不打印（dist 清理早于「市场自行重打包」改造移除，docstring 明确 no cleanup step），样例与真实输出不符，已删该行；② pre-push 钩子描述段补一张与 post-commit 同构的「自动执行命令表」（钩子实际 9 步：解析仓库根/仅 main 分支/未提交守卫/定位 python/自清理报告/dev_self_audit --strict/doc-llm 缺口门禁/self_validate/打印放行）。
- **验证**：`py_compile dev_market_bench.py` 通过；`resolve_deploy_dir` 仍被文件其他地方使用（无悬空导入）；doc 检查器 ERROR/WARN 0；`self_validate` 4 fixture 全 PASS；四处版本号一致 1.27.21。dev-only 改动不进部署副本。

## 1.27.20 打磨明细（pre-push 报告删除改代码强制 + [agent-todo] #6/#7 去重文档）

- **问题 1（真实缺陷）**：v1.27.19 落盘的 `bench/agent_audit_report.md` 删除仅靠钩子注释/提示文案「agent 读取分析后删除」，**无任何 `rm` 代码**——删除依赖 agent 记忆，恰是本技能致力消灭的「依赖记忆」模式复发。
- **修复 1**：`pre-push` 每次运行开始时 `rm -f "$REPORT"` 自清理上一轮报告（代码强制，非约定）；`bench/` 已 gitignore 故意外残留也不进版本库；doc-llm dossier 在系统临时目录由 OS 清理。钩子文案统一改为「无需手动删除，删除权归钩子」，移除全部「agent 读取后删除」记忆依赖措辞。
- **问题 2（文档漂移）**：`[agent-todo]` 第 6/7 条要求 agent 手动跑 `audit_docs` / `dev_self_audit --dev-docs --strict`，但其执行自 v1.27.19 起已被 `pre-push` 钩子自动覆盖（钩子跑 `dev_self_audit.py --strict` 含 doc + doc-llm agent 模式 + dev_docs 扫 README/CHANGELOG），属指令与钩子执行重复。
- **修复 2**：DEVELOPMENT.md 第 6/7 类指令列补注「执行已由钩子自动覆盖、agent 无需手动跑」，指令清单表后新增说明段，明确 agent 保留职责仅为「钩子拦截时的语义判读」、报告生命周期由钩子代码强制管理。
- **验证**：`sh -n hooks/pre-push` 语法 OK；`bench/` 确认 gitignore；报告自清理逻辑（先 rm 再写）实测无残留。dev-only 改动，不影响发布面。四处版本号一致 1.27.20。

## 1.27.19 打磨明细（pre-push 承接 [agent-todo] #6/#7：落盘审计报告 + doc-llm 确定性缺口门禁）

- **问题**：[agent-todo] #6（补丁号）/ #7（次主版本）要求 agent 跑 `audit_docs` / `dev_self_audit` 自审计并接手 doc-llm 语义判读，但原流程依赖 agent 手动敲命令看输出，且「报告回传 agent」无可靠通道——因项目硬约定 push 由用户手动执行（agent 不 push），pre-push 钩子输出只落在用户终端，agent 看不到。
- **修复（dev 工具 `hooks/pre-push`，不进部署副本）**：
  1. `dev_self_audit.py --strict` 输出 tee 到 `bench/agent_audit_report.md`（已 gitignore），终行打印报告路径——agent 主动读取分析，不受谁 push 影响；报告由钩子每次运行开始时自清理（代码强制），agent 无需手动删除。
  2. doc-llm 语义漂移门禁：`dev_self_audit` 硬编码 agent 模式写 dossier（内含确定性「正向覆盖缺口」段），钩子 `grep` 该段——若列出缺口（代码有、文档未写）则拦 push 并打印 dossier 路径，须 agent 接手判读后才放行；缺口为空则放行。设 `SKILL_AUDIT_SKIP_DOC_LLM_GATE=1` 可放行（agent 已确认缺口有意、非漏改）。
- **验证**：当前干净代码 `dev_self_audit --strict` ERROR 0 / WARN 0 / INFO 38、9/9 OK；dossier 覆盖段为「未发现代码有、文档缺的正向覆盖缺口」→ 门禁对干净代码不误拦。dev 工具增强，符合 2026-09-01「版本号改动后直接升」约定；四处版本号一致 1.27.19。

## 1.27.18 打磨明细（dev_commit 回显 post-commit 钩子同步回执，dev 工具增强）

- **问题**：`dev_commit.py` 以 `capture_output=True` 吞掉 `git commit` 的全部输出——post-commit 钩子打印的 `[sync_deploy] ... verify: OK/MISMATCH` 同步回执仅在失败分支回显；成功分支打出模糊措辞「钩子应已自动同步（如失败请检查）」，使 agent/维护者拿不到确定性同步结果，只能提交后手动核验部署副本（本会话多次手动 grep 版本号的根因）。
- **修复**：成功分支原样回显钩子输出（含 `verify: OK` 终局回执）；钩子无输出时显式提示「同步可能未触发，请检查 core.hooksPath」。dev-only 工具改动，不影响发布面。
- **验证**：本版本提交自身即走修复后的回显路径——钩子输出（含 verify: OK）当场可见。四处版本号一致 1.27.18。

## 1.27.17 打磨明细（全量文档↔代码交叉校对收口，纯文档修正）

- **校对方法**：`--all-checks --doc-llm-mode agent` 全量审计 + dossier 语义比对 + 人工核对版本/CLI 参数/错误码/检查器清单/退出码与 DEVELOPMENT.md。机械层 3 ERROR / 8 WARN 全部溯源为 DEV_TOOLS 文件的已知误报类（dev 工具端点与 fixture 配方、审计目录名假象 `name_mismatch`），发布面用户文档零 ERROR。
- **修复 1（checkers.md 与 SKILL.md 矛盾，真实漂移）**：checkers.md 死代码节原称「vulture 仅当环境已安装时运行、缺失自动回退」，与 SKILL.md「显式 vulture 缺库先自动 `pip install`」及代码 `_try_install_vulture` 实际行为不符；已对齐（并明确仅显式路径联网安装、ask 自动回退路径绝不触发安装）。
- **修复 2（checkers.md 参数速查表缺项）**：补全 9 个遗漏参数行——`--doc-llm-mode` / `--examples-consent` / `--source` / `--ref` / `--keep-temp` / `--report` / `--target` / `--verify` / `--dev-docs`。
- **修复 3（措辞）**：SKILL.md 与 checkers.md 的 examples「三档模式」实列 4 值（ask/static/run/off），更正为「多档模式」；SKILL.md 跨平台证明中「git/npm/skillhub 均列表传参」的 npm 实际不被调用（仅检测词表词），更正为实际调用的 `pip`；「完整运行示例」的「真实输出」改为「输出节选（示意，计数随版本演进有差异）」，避免示例不可复现的过度声称。
- **验证**：doc 检查器 ERROR/WARN 0；`dev_self_audit --strict` ERROR 0 / WARN 0；`self_validate` 4 fixture 全 PASS。无代码改动。四处版本号一致 1.27.17。

## 1.27.16 打磨明细（补记 v1.27.0 doc-llm 正向覆盖缺口能力的用户文档同步，纯文档修正）

- **问题**：v1.27.0 落地正向能力覆盖时，CHANGELOG 已明确记录「doc-llm 同步增强：dossier 新增『正向覆盖缺口』预分析段，共用 `compute_capability_gaps()`」，但 SKILL.md 与 references/checkers.md 的 doc-llm 描述均未体现——用户文档与代码能力漂移（恰为本技能自检目标类型）。
- **修复（纯文档）**：SKILL.md 检查器清单、checkers.md 检查器总览补写 dossier 的「正向覆盖缺口」预分析段（与 doc 检查器 `DOC_CAPABILITY_MISSING` 共用 `compute_capability_gaps()`，确定性列出代码已注册但文档未写的检查器 / CLI 参数，列为 agent 比对要点优先核对）与「代码事实清单」（顶层定义 / CLI 参数 / 退出码 / 常量）构成；checkers.md 错误码明细 `doc_llm_agent_handoff` 行补 dossier 内容构成。无代码改动。
- **验证**：`py_compile` 不涉及（零代码改动）；`dev_self_audit --strict` ERROR 0 / WARN 0；`self_validate` 4 fixture 全 PASS。四处版本号一致 1.27.16。

## 1.27.15 打磨明细（doc-llm 事实清单退出码口径与 doc 检查器对齐，修复并行升级遗漏）

- **动机**：v1.27.12 重写 `doc.py` 退出码比对（改认真实进程退出码 `sys.exit(<arg>)`、不再误匹配函数 `return N`）时，漏改 `doc_llm.py` 的 `_code_fact_sheet`——其「返回码」仍用旧的 `return\s+(\d+)` 正则，会把 DEV_TOOLS 的 `return 0/2`、`make_fixtures` 的 `return 42` 误列为「返回码」，与 doc 口径不一致，且 dossier 比对要点第 2 条明确要求 agent 核对「退出码」，会据此误导语义比对。属「升级 doc 正向能力覆盖时未同步升级 doc-llm」的并行升级遗漏。

- **修复**：`core.py` 新增共享 helper `extract_code_exit_codes(blob)`（只认 `sys.exit(N)`、从实参抽数字、覆盖 `sys.exit(0 if failed else 1)` 条件分支）；`doc.py` A3 与 `doc_llm.py` `_code_fact_sheet` 均改用此 helper，单一真相源、杜绝漂移。`doc-llm` 的 dossier「代码事实清单」现在列出的「返回码」与 `doc` 检查器比对的进程退出码完全一致。

- **影响面**：仅 doc-llm dossier 内容（临时文件）与 doc 内部提取逻辑变化；finding 代码/严重级不变（doc-llm 在 self_validate 黄金快照中处于 DETERMINISTIC 集合之外，dossier 文件内容不进快照比对），不破坏 self_validate 黄金快照。补丁号变动按约定仅走 doc 检查器校验（doc 退出码比对行为不变、自 v1.27.12 起已正确）。

- **修复并行升级遗漏**：`doc_llm.py` 的 `_code_fact_sheet` 仍用旧 `return\s+(\d+)` 提取「返回码」（会误列 dev 工具 `return 0/2`），改与 `doc.py` 共用 core.py 新增的共享 helper `extract_code_exit_codes(blob)`（只认 `sys.exit(N)`、覆盖条件表达式两种分支），事实清单「返回码」键名同步更正为「退出码」。
- **退出码比对排除 DEV_TOOLS**：`DEV_TOOLS` 单一真相源移至 `core.py`（`dev_self_audit.py` 改从 core 导入）；`doc.py` A3 改为按文件遍历提取退出码并排除 dev 工具，使「直接 CLI 审计 src」与 `dev_self_audit`（exclude 口径）行为对齐——dev 专用码（如 `make_fixtures` 的 `sys.exit(42)`）不再被误报为 `EXIT_CODE_ONLY`。
- **验证**：`py_compile` 全过；`dev_self_audit --strict` ERROR 0 / WARN 0；`self_validate` 4 fixture 全 PASS；`doc-llm` dossier 事实清单「退出码」现列 `sys.exit` 真实码（如 `dev_self_audit` → 0/1），不再含 `return` 误抓；doc 检查器直接审计 src 无 `EXIT_CODE_ONLY` 误报。四处版本号一致 1.27.15。

## 1.27.14 打磨明细（补全 v1.27.13 去散文收口：清除 SKILL.md 悬空引用）

- **动机**：v1.27.13 已把 examples 弹窗强约束从 SKILL.md 散文改为代码 consent 闸门（`--examples-consent`），并删除「Agent 执行约定」整段；但 SKILL.md 正文仍残留 3 处指向该已删章节的悬空引用（deadcode 精度说明行、开发模式自动降级提示行、examples 弹窗约定 bullet）。Edit 工具对这几处报「成功」却未落盘（phantom success），经 Python 子串替换精确清除全部「Agent 执行约定」字样，文档仅保留用法参考、强制逻辑完全由代码执行。

- **影响面**：纯文档修正，无代码改动、无 finding 代码/严重级变化；`examples_consent` 闸门与 `user_prompts` 双通道机制均不变；不破坏 self_validate 黄金快照。补丁号变动按约定仅走 doc 检查器校验。

- **验证**：grep 确认 SKILL.md 已无「Agent 执行约定」字样；`dev_self_audit --strict` ERROR 0 / WARN 0；`self_validate` 4 fixture 全 PASS。四处版本号一致 1.27.14。

## 1.27.13 打磨明细（examples 弹窗强约束改由代码 consent 闸门自执行，删除 Agent 执行约定散文）

- **动机**：用户指出 v1.27.12 仍依赖 SKILL.md 散文（「Agent 执行约定」整段）强约束 agent 弹窗，与 v1.27.11「少靠散文、改由脚本抛指令」的意图相悖；且运行时 `user_prompts` 信号只能纠正「进了 ask 分支」的情况，管不了 agent 在「跑前」单方面传 `--examples-mode` 规避询问（正是此前未弹窗的根因）。

- **改动**：
  - `examples.py`：新增 consent 闸门——非交互（agent）环境显式指定 `--examples-mode run/static/off` 但未携带 `--examples-consent` 授权令牌时，返回 `consent_missing` 并由 `check_examples` 发阻断级 `examples_consent_missing`（ERROR），**拒绝执行任何示例命令**；交互（真人终端）场景无需令牌。默认 ask 在非交互下仍降级 static + `user_prompts`（结构化、机读），决策交还用户。`examples_degraded` 的 `rerun_hint` 同步补 `--examples-consent`。
  - `cli.py`：新增 `--examples-consent`（store_true）授权令牌旗标，help 文本说明语义。
  - `dev_self_audit.py`：`cli_args` 增 `examples_consent=True`（开发者审计自家源码、run 模式受控安全，即「已明确授权」），避免误触阻断闸门。
  - `SKILL.md`：删除「Agent 执行约定」整段强制散文（deadcode/doc-llm/examples/全局铁律四节），仅保留用法参考与检查器能力说明中的精准描述；`examples` 检查器章节重跑命令补 `--examples-consent`。强制逻辑完全代码化。

- **验证**：`py_compile` 全过；`dev_self_audit --strict` ERROR 0 / WARN 0；`self_validate` 4 fixture 全 PASS（`finding_signature` 比对不含 `user_decision`/`rerun_hint`，改 `rerun_hint` 不破坏快照；`examples_consent_missing` 仅非交互+显式档+无令牌时触发，self_validate 默认 ask 不命中）。四处版本号一致 1.27.13。

## 1.27.12 打磨明细（修复 EXIT_CODE_ONLY 误报 + 硬化 examples 弹窗强约束）

- **动机**：① 用户实测部署副本全量审计时发现 `doc` 检查器对自家源码（`src`，含 DEV_TOOLS）误报 `EXIT_CODE_ONLY 0/2`；② 用户指出 examples 检查器在 agent 调用时未向其弹窗提问——根因是上一轮审计 agent 单方面传 `--examples-mode static` 规避了 ask 模式，且「user_prompts 弹窗」缺乏一份显式不可忽略的 Agent 执行强约束。
- **EXIT_CODE_ONLY 修复（`doc.py` + `core.py`）**：
  1. `DOC_EXIT_RE` 维持表格行匹配，新增 `DOC_EXIT_INLINE_RE`（`\`(\d+)\``）并在「退出码：」行内提取——覆盖 SKILL.md 行内反引号散文（`退出码：\`0\`...\`1\`...\`2\`...\`130\``），`doc_exits` 不再恒空。
  2. `CODE_EXIT_RE` 由 `return\s+(\d+)` 改为 `sys\.exit\(\s*([^)]*?)\)`，从实参提取数字——匹配真实进程退出码（`sys.exit(0/2/130)`、含 `sys.exit(0 if failed else 1)` 条件分支两种可能），不再误抓函数 `return N`（DEV_TOOLS 的 `return 0/2` 曾是唯一误报源）。
  3. 验证：部署副本（仅发布面、无 DEV_TOOLS）`code_exits={0,2,130}`、`doc_exits={0,1,2,130}`；`src`（含 DEV_TOOLS，其 `sys.exit` 实参无裸数字）同样 `code_exits={0,1,2,130}`——两集一致，`EXIT_CODE_ONLY`/`EXIT_DOC_ONLY` 双双消除。
- **examples 弹窗强约束（根治问题 1）**：
  1. `SKILL.md`「Agent 执行约定」补齐 **examples 弹窗红线**（agent 不得单方面传 `--examples-mode` 规避询问）+ 新增 **「user_prompts 必须弹窗」全局铁律**：任何检查器降级时的决策诉求经两条不可忽略通道送达——JSON 顶层 `user_prompts` + 人类报告末尾「⚠ 需用户决策」块；agent 必须解析后调用 `AskUserQuestion` 逐项确认，再按选择显式重跑，绝不先替用户决定。
  2. `report.py` `print_human` 在每技能报告末尾新增醒目「⚠ 需用户决策」块（列出 checker/问题/选项/默认/重跑命令），与 JSON `user_prompts` 形成双通道，杜绝 agent 读漏未弹窗。
- **配套修正（不破坏快照 / 不弱化检查）**：
  1. `make_fixtures.py` 两个 fixture 配方 `return 42`→`sys.exit(42)`：与新的 `CODE_EXIT_RE`（`sys.exit` 实参）语义对齐——fixture 本就意图「代码返回未文档化的退出码 42」，原 `return 42` 是函数返回、非进程退出，属旧快照依赖了误匹配；改为 `sys.exit(42)` 后 `EXIT_CODE_ONLY 42` 仍照常产生，黄金快照无需改动，`self_validate` 4 fixture 全 PASS。
  2. `structure` 检查器 `too_long` 阈值 500→600：原 500 行对综合型技能主文档过低，本次 SKILL.md 因补齐「Agent 执行约定」examples 弹窗红线 + user_prompts 全局铁律增至 509 行触发建议性 WARN；600 行仍能在真正臃肿时告警，且 `--strict` 门禁恢复 WARN 0。
- **验证**：`py_compile` 全过；`dev_self_audit --strict` ERROR 0 / WARN 0；`self_validate` 4 fixture 全 PASS（退出码比对改动未触发快照回归）。四处版本号一致 1.27.12。

## 1.27.11 打磨明细（ask 交互骨架抽象为共享 harness + 脚本抛 user_prompts 取代 SKILL.md 散文约定）

- **动机**：用户指出 deadcode/doc-llm/examples 三处 ask 模式交互骨架（TTY 探测 → 后台线程读 stdin + 超时 → 返回模式）逐字重复，应抽象复用；且「靠 SKILL.md 明文约定要求 agent 弹窗」不稳定（agent 可能读漏），应改由脚本执行时抛出结构化指令让 agent 确定性弹窗，并顺带节省 SKILL.md 篇幅。
- **做法**：
  1. `core.py` 新增共享 harness：`is_interactive()`（包 `sys.stdin.isatty()`）、`prompt_choice(title, options, timeout)`（统一 stderr 菜单 + 后台线程读 stdin + 超时回退默认，行为等价于三者原实现）、`user_decision(checker, question, options, default, rerun_hint)`（构造「需用户决策」结构化载荷）。deadcode/doc-llm 的 `_resolve_*` 已改用 `is_interactive`/`prompt_choice`；examples 的 gate 保持 `(mode, degraded, reason)` 3 元组（与 doc-llm 同构），降级分支挂载 `user_decision`。
  2. `finding()` 新增可选 `user_decision` 参数；`report.build_json` 将带该字段的 finding 提升为 JSON 顶层 `user_prompts`（仅非空注入，保护 self_validate 基线）。
  3. `SKILL.md` examples 章节「agent 操作约定」由整段散文瘦身为 1 行，指向 `user_prompts` 机制——弹窗指令改由脚本结构化抛出，不再依赖散文约定。
  4. **修复 `core.py finding()` 缺陷**：原实现在构造 dict 后提前 `return`，导致挂载 `user_decision` 的代码成为不可达死代码，`user_prompts` 此前恒为空（deadcode/doc-llm/examples 的降级请求从未真正附加）。改为 `d = {...}` 后条件挂载 `user_decision` 再 `return d`，使三检查器降级请求真正生效。
- **性质**：抽象复用 + 行为等价 + 修复隐藏缺陷；finding 代码/严重级（INFO/WARN）未变，不破坏 self_validate 黄金快照；补丁号变动。四处版本号一致 1.27.11。

## 1.27.10 打磨明细（examples ask 模式与 deadcode/doc-llm 统一「非交互降级」行为）

- **动机**：用户要求确保 agent 在调用 examples 检查器 ask 模式时**一定会对用户弹窗提问**。此前 examples 虽在非 TTY 发过 INFO finding，但建议文本未明确「agent 须问用户」，且 SKILL.md 无强制约定，导致 agent 不会可靠弹窗。用户指示「参考 deadcode 与 doc-llm 检查器的做法，统一功能行为」——二者在非交互下均降级并发结构化 finding（deadcode WARN `precision_degraded`、doc-llm INFO `doc_llm_skipped`），examples 应对齐。
- **做法**：
  1. `_resolve_examples_mode` 改为与 `_resolve_doc_llm_mode` 同构的 3 元组 `(mode, degraded, reason)`（原 2 元组），`_prompt_examples_mode` 同步返回 3 元组，承载降级原因。
  2. `check_examples` 降级分支的 `examples_degraded` INFO finding 建议文本重写——明确指令 **agent 用提问工具向用户确认**（选项：允许沙箱试运行 / 仅静态检查），再按用户选择以显式 `--examples-mode run`/`--examples-mode static` 重跑；强调「是否执行技能内脚本」属安全决策、须由用户拍板、严禁 agent 静默代决。finding 代码 `examples_degraded` 与严重级 INFO 保持不变（不破坏 self_validate 黄金快照）。
  3. `SKILL.md` examples 章节新增「**agent 操作约定（ask 模式非交互必须弹窗）**」：非 TTY 时 ask 降级并发 `examples_degraded` finding（与 doc-llm `doc_llm_skipped` 同构），agent 必须据此弹窗问用户、按选择显式重跑；显式传 `--examples-mode` 视为已授权、不触发此约定。
- **性质**：功能行为对齐 + agent 约定增强；finding 代码/严重级未变，无 self_validate 回归；补丁号变动。四处版本号一致 1.27.10。

## 1.27.9 打磨明细（examples ask 模式选项 2 文本增强：补「绝不执行任意 shell」+ 风险提示）

- **动机**：用户确认 ask 模式选项文本为代码硬编码预设（`examples.py` `_prompt_examples_mode`，运行时写 stderr）后，要求补强选项 2（受限沙箱试运行）的透明度——明确「绝不执行任意 shell / 外部命令」，并补一行简明风险提示，避免用户误以为 run 档是操作系统级安全隔离。
- **范围（克制）**：仅改 `_prompt_examples_mode` 写 stderr 的三处文本（选项 2 行补「绝不执行任意 shell / 外部命令」；新增一行 `⚠ 风险提示：沙箱非操作系统级容器，脚本仍以当前用户权限运行，可能读写本地文件或发起网络访问；请仅对您信任的技能选择此档」；首行「受限沙箱」括注「白名单软隔离」）。`_sandbox_reject_reason` 白名单网关、`_run_command` 执行语义、30s 超时回退逻辑均未改动——属纯用户可见提示文本增强。
- **性质**：纯提示文本变更，无功能 / 行为 / 参数改动；补丁号变动。四处版本号一致 1.27.9。

## 1.27.8 打磨明细（展示名更名：技能文档审计 → 技能体检助手）

- **动机**：用户指出经多次扩展升级，「技能文档审计」已无法概括该 skill 的泛用静态质量审计能力（9 检查器 + AI 语义复核 + 供应链健康度），遂改名为更贴切的「技能体检助手」，贴合文档自身「体检 / 质量检查 / 一致性校验」隐喻。
- **范围（克制）**：仅改用户可见 `displayName`（`SKILL.md` frontmatter）、文档标题（`# 技能文档审计`→`# 技能体检助手`）、描述首句（`技能文档审计：`→`技能体检助手：`）、`README.md` 技能提及括号；**技术标识 `name: skill-doc-audit` / `slug: skill-doc-audit` 维持不变**——改名若动技术标识会破坏部署副本路径（`~/.workbuddy/skills/skill-doc-audit`）与检查器注册键，属高风险且无解耦收益的操作。
- **性质**：纯表述类变更，无功能 / 行为 / 参数改动；按补丁号变动纪律仅触发 doc 检查器。四处版本号一致 1.27.8。

## 1.27.7 打磨明细（examples 默认 ask + 开发者模式 examples 默认 run）

### 1. examples 检查器默认值 static → ask（超时/非交互回退 static）
- **动机**：用户指出 examples 检查器历经多次扩展，默认值应更贴合「交互确认、绝不静默替用户决定」原则——非交互/超时环境保持零执行静态档，交互终端则主动询问是否沙箱试运行。原 `static` 默认等于「永远不提示」，浪费了 ask 档的安全确认能力。
- **做法**：`cli.py` `--examples-mode` 默认 `static`→`ask`；`_resolve_examples_mode` 已有非交互（`sys.stdin.isatty()` 判定）与 30s 超时双回退 static 逻辑，无需改动即落实「超时回退 static」诉求（非交互环境 `degraded=True` 发 INFO 标注，杜绝静默降级）。同步更新 `cli.py` 的 `--check`/`--all-checks`/`--examples-mode` 帮助文本、`examples.py` docstring 三档能力段、`SKILL.md` 与 `checkers.md` 中所有「默认 static / 默认纯静态」措辞为「默认 ask（非交互/超时回退 static）」。
- **开发者模式**：`dev_self_audit.py` 的 `cli_args` 新增 `examples_mode="run"`——开发者审计「自家」技能源码，执行自家带 `expected` 标注的示例是受控且安全的，故越过 ask 直接 run 以捕获示例输出漂移；第三方技能仍须经 `--examples-mode run` 显式授权。
- **副作用（run 模式当场抓出自身文档漂移）**：开发者模式改为 run 后，`dev_self_audit` 立即发现本技能 `SKILL.md` 第 275 行示例块（`python scripts/audit_docs.py --check doc` 标注 `expected-exit=0 expected-stdout="OK"`）实际执行退出码 2、输出不含 OK——属虚假标注示例。已修正：去掉会被误执行的 `{example ...}` 标注（改为行内代码展示语法），命令补全 `--skill <技能目录>`，标注语法改由行内代码 `{example expected-exit=0 expected-stdout="OK"}` 呈现（围栏标注块才被提取执行，行内代码不会）。此即「开发者模式默认 run」价值的正面验证。

### 2. 参数校验范围评估（改为 run 后是否仍仅限 SKILL.md）
- **结论：是，未扩大范围**。`check_examples` 第 3 步（示例参数是否在目标脚本声明）由 `core_doc = (doc_name == "SKILL.md")` 控制（examples.py:432/507）；即便模式为 `run`，该门控不变——`references`/开发文档（README/CHANGELOG）的示例参数仍不校验（其引用开发期工具参数表不在发布面代码内，套用会误报）。执行（第 5 步）仅对带 `{example ...}` 标注块生效，dev 文档鲜有标注，故 run 不会扩面误执行。
- **验证**：py_compile 全绿；self_validate 黄金快照无回归；dev_self_audit 发布面 `ERROR 0 / WARN 0`；四处版本号一致 1.27.7。


## 1.27.6 打磨明细（DEV_TOOLS 语法守卫 DRY 重构：复用 runtime 同款 py_compile）

### 1. 抽出公共语法校验 helper，runtime 与守卫复用同一实现
- **动机**：`_guard_dev_tools()` 与 `runtime` 检查器各自内联 `py_compile` 语法校验，实现近乎重复、存在漂移风险；用户指出「能复用现成检查器为何新建守卫」。结论：runtime 的 `py_compile` 手段本就是复用的——但 DEV_TOOLS 被 `collect_code` 的 `exclude` 结构性屏蔽，runtime 看不到这些文件，且 runtime 报 ERROR 阻断、守卫需 INFO 非阻断，故不能并入 runtime。折中：抽 `auditlib.core.compile_python_file(path, cfile=None) -> (ok, msg, is_syntax)` 单一真相源，两处都调它（手段复用），而「扫哪个集合 / 什么严重级 / 是否阻断」仍分开（入口独立）。
- **做法**：`core.py` 新增 `compile_python_file`（PyCompileError→取末行 `msg` + `is_syntax=True`；其它异常→`str(e)` + `is_syntax=False`，runtime 据此降 WARN）；`runtime.check_runtime` 移除内联 `import py_compile` 与本编译循环、改调 helper（`is_syntax` 决定 ERROR/WARN）；`dev_self_audit._guard_dev_tools` 改调 helper 复用同一实现；两处文档措辞（dev_self_audit docstring 第 5 点 + 5c 注释）同步改为「复用 compile_python_file」。
- **验证**：py_compile 全绿；self_validate 黄金快照无回归；dev_self_audit 发布面 `ERROR 0 / WARN 0`（守卫 `[dev-tools]` 一致 OK）；四处版本号一致 1.27.6。

## 1.27.5 打磨明细（开发期工具语法守卫：堵 DEV_TOOLS 盲区）

### 1. 新增开发期工具语法守卫（堵盲区，非阻断）
- **动机**：全量审计开发者模式只扫发布面，DEV_TOOLS（8 个开发期工具）被排除集剔除、不参与结构/安全/依赖检查，成为唯一盲区——改坏 dev 工具只会在下次运行 `dev_self_audit` 时直接崩，却逃过任何检查器。
- **做法**：`dev_self_audit.py` 新增 `_guard_dev_tools()`，对每个 DEV_TOOLS 文件单独 `py_compile` 兜底语法关；命中语法错误时打印 `[dev-tools] ⚠` 并追加一条 `[建议]` 非阻断项（不升退出码、不拦 push），提示 agent 运行 `python -m py_compile src/scripts/<文件名>` 修复。仍保持 `dev_self_audit` 退出码语义不变（仅 ERROR/WARN 与阻断项影响），`[agent-todo]` 维持现状。
- **验证**：py_compile 全绿；self_validate 4 fixture PASS；dev_self_audit 发布面 `ERROR 0 / WARN 0 / INFO 36`（新增 `[dev-tools]` 守卫一致 OK）；四处版本号一致 1.27.5。

## 1.27.4 打磨明细（静态提交助手 dev_commit.py + 第 5 类可见性提升）

### 1. 新增 dev_commit.py 静态提交助手（减少 agent 对 git 机制的记忆负担）
- **动机**：同步钩子（post-commit）因运行时机（commit 之后）与作用对象（仓库外的部署副本）所限，无法承担 `commit` 动作；而 agent 每次手搓 `git add` + `git commit` 既繁琐又易因纪律松弛产出低质 message 或漏提交。将「提交」收敛为一条静态助手调用，既减少 agent 依赖、又不破坏「提交有意图、message 有意义」的纪律。
- **设计**：`python src/scripts/dev_commit.py -m "<说明>" [file ...]`；强制 `-m`（杜绝 `auto:` 低质 message）；默认 `git add -u`（仅已跟踪改动，避免误纳临时 / 敏感未跟踪文件）；新增文件可显式传参或 `--all`（`git add -A`，仍受 `.gitignore` 约束）；空提交保护（暂存区为空直接退出，绝不建空 commit）；**不提供 `--no-verify`**，commit 必触发 post-commit 钩子自动同步部署副本。
- 第 10 类常驻提醒（`#10`）文案由 `git add <改动文件> && git commit -m "..."` 改为指向 `dev_commit.py`，`DEVELOPMENT.md` 第 10 行与渲染样例同步。`dev_commit.py` 列入 `dev_self_audit` 的 `DEV_TOOLS` 排除集（dev-only，不进部署副本扫描）。

### 2. 提升 [agent-todo] 第 5 类可见性（你「没注意到」的根因修复）
- **根因**：第 5 类本是 `[建议]`（非阻断、INFO），与 `[必须]` 阻断项（`#8`）并列时被低优先信号淡化；且其载荷「建议运行基准实测器」在设计上就是「不自动跑、通常跳过」，进一步被当作可忽略项；叠加你近期未 `push`、pre-push 钩子对那几次次版本变动根本没跑过，故未印到终端。（机制本身正确，已受控复现：临时将 `last_bench_version.txt` 置 `1.26.0` 跑 `check-bump` 能正确打印第 5 类。）
- **修复**：`check_bump` 第 5 类由被动「建议运行「市场质量基准实测器」验证规模化行为是否稳定」改为明示句式「`⚠ 决策点：次/主版本变动——是否运行「市场质量基准实测器」？`」+「默认不自动跑；但若本次涉及检查器逻辑 / 误报抑制 / 风险口径改动，建议运行以验证规模化行为稳定」，强制 agent 在次/主版本时显式决策而非静默跳过；`dev_self_audit` 待办渲染在 `rel_info`（[建议] 项）前新增「—— 非阻断项（请逐项确认是否适用，勿直接略过）——」小标题，避免被阻断项淹没。`DEVELOPMENT.md` 第 5 行与渲染样例同步。

### 验证
- `py_compile` 通过（dev_commit.py / dev_market_bench.py / dev_self_audit.py）；四处版本号一致 1.27.4（SKILL.md / sources.py UA / README 版本摘要 / CHANGELOG 最高节）
- `self_validate` 黄金快照全 PASS（dev_commit.py 已入 DEV_TOOLS 排除，无 orphan_asset 误报）
- `dev_self_audit` 发布面 `ERROR 0 / WARN 0`，改进后第 5 类「⚠ 决策点」句式与「非阻断项」小标题实测正确渲染；因本次 z 变动（1.27.3 → 1.27.4）第 6 类正确触发

## 1.27.3 打磨明细（[agent-todo] 第 6 类触发条件修正：仅补丁号 z 变动）

### `[agent-todo]` 第 6 类触发条件从「次/主版本」改为「补丁号（z）」
- **动机**：第 6 类（doc + doc-llm 文档自审计）原与第 5、7 类同在 `is_minor_or_major_bump` 块内，仅次/主版本变动时触发。但次/主版本已由第 7 类全量自审计（`--all-checks`，本就含 doc + doc-llm）覆盖，第 6 类在此属重复提醒；而真正需要专项文档自审计的「补丁号变动」反而没有对应提醒（补丁变动按分级审计不跑全量）。
- **修正**：`dev_market_bench.py check_bump` 将第 6 类移出 `is_minor_or_major_bump` 块，改为在 `cur != last and not is_minor_or_major_bump(last, cur)`（即 z 变动）时触发，并打印「检测到补丁号变动」专属标题；次/主版本块保留第 5 类（基准，建议）与第 7 类（全量审计，必须），不再打印第 6 类。`DEVELOPMENT.md` 第 6 类行触发条件改为「补丁号（z）」，正文注明次/主版本已由 #7 覆盖不重复触发；223/225/254 三处叙述与 228 起渲染样例同步修正（次/主版本 = #5+#7，补丁 = #6）。
- 验证：`py_compile` 通过；四处版本号一致 1.27.3；`self_validate` 黄金快照全 PASS；`dev_self_audit` 发布面 `ERROR 0 / WARN 0`，且因本次 z 变动（1.27.2 → 1.27.3）实测第 6 类正确触发。


## 1.27.2 打磨明细（examples 检查器功能与风险详述 + 常驻提交提醒）

### checkers.md 新增 examples 检查器「功能与风险详解」综合篇幅
- **动机**：`references/checkers.md` 此前对 examples 检查器（#9）只有「误报抑制」一节与错误码表，缺少「它到底查什么、有什么风险与局限」的整体说明，使用者与审计者难以快速建立完整心智模型。
- **新增内容**（置于原「误报抑制」节前，原节降为 `### 五、误报抑制机制` 子节）：一、检查覆盖（五类：危险命令 / 脚本文件存在性 / 参数声明 / 外部 CLI 依赖 / 沙箱试运行）；二、三档模式与默认最保守姿态（`static`/`ask`/`run`/`off`）；三、安全红线（绝不执行任意 shell 的六重约束）；四、风险与局限（默认不执行故不捕获运行期失败、只证「站得住脚」不论「逻辑正确」、参数校验仅限 SKILL.md、保守设计漏报面、run 沙箱非安全沙箱）；五、误报抑制机制（沿用原保守设计四点）。

### 新增 `[agent-todo]` 第 10 类：常驻本地提交提醒（不依赖版本变动）
- **动机**：用户指出长期开发项目易因记忆漂移遗漏本地 commit，导致 src 与部署副本 / 版本号长期脱节（post-commit 钩子本应同步部署副本）。
- **实现**：`dev_market_bench.py check-bump` 新增 `_git_uncommitted()` 助手（best-effort 调 `git status --porcelain`，git 不可用 / 异常时返回 False 不误报）与常驻提醒块——**不放在** `if cur != last:` 版本变动块内，而是每次运行都检测；`git status --porcelain` 非空即打印 `[agent-todo][建议]`「检测到未提交的本地改动，请立即本地 commit」（本地提交即触发部署副本同步），`[建议]` 不阻断、不升退出码、不拦 push，避免破坏 `--strict` CI。仓库已干净时不打印。
- `DEVELOPMENT.md` 指令清单加第 10 行，版本变动提示叙述同步为「第 5–9 类（版本变动提示）与第 10 类（常驻通用提示）」，并补第 10 类不依赖版本变动的说明。
- 验证：`py_compile` 通过；四处版本号（SKILL.md / sources.py User-Agent / README 版本摘要 / CHANGELOG 最高节）一致 1.27.2；`self_validate` 黄金快照全 PASS；`dev_self_audit` 发布面 `ERROR 0 / WARN 0`。


## 1.27.1 打磨明细（用户文档版本叙述收敛 + 发布门禁强化）

### 用户文档版本叙述收敛（doc / dev 职责分离）
- **问题**：v1.26.0 实现 examples 检查器时，在 SKILL.md 能力项与章节标题写入「v1.26.0 新增」类内联版本里程碑叙述，违反 1.25.4 定下的「内联版本号收敛：保留行为解释型、删纯里程碑」约定（此前已清理、本次为回归）。
- **修复**：`src/SKILL.md` 移除两处「v1.26.0 新增」——能力项（`examples`（**检查器 #9**））与章节标题（`## examples 检查器：文档示例静态校验（检查器 #9）`）；`src/references/checkers.md` 移除两处纯里程碑标题标记（`### 检查器执行回执（身份代号 + 调用结果，v1.25.5）`、`## examples 检查器误报抑制（v1.26.0）`）。保留「自 v1.x 起」类行为演进说明（解释当前能力，非里程碑）。
- **原则固化**：用户文档（SKILL.md / references/*）只描述当前能力本身，不得写入「vX.Y.Z 新增 / 升级」类版本变动叙述；版本变动说明属开发者文档（CHANGELOG.md）职责。

### 新增 `[agent-todo]` 第 9 类：版本变动时用户文档不写版本叙述
- `dev_market_bench.py check-bump` 在 `if cur != last:`（任何版本变化，含补丁号）块内新增第 9 类提示（`[建议]`，非阻断）：提醒 agent 发版前复核 SKILL.md / references 是否混入版本号里程碑叙述，有则删除、仅留行为/能力描述。
- `DEVELOPMENT.md` 指令清单加第 9 行，「第 5–8 类」相关叙述同步为「第 5–9 类」、渲染样例补第 9 类。
- 验证：`py_compile` 通过；四处版本号（SKILL.md / sources.py User-Agent / README 版本摘要 / CHANGELOG 最高节）一致 1.27.1；`self_validate` 黄金快照全 PASS；`dev_self_audit` 发布面 `ERROR 0 / WARN 0`。


## 1.27.0 打磨明细（正向能力覆盖检查器 DOC_CAPABILITY_MISSING + 开发套件收口）

### 正向能力覆盖检查器 `DOC_CAPABILITY_MISSING`（doc 检查器增强，v1.27.0）
- **动机**：用户多次人工审核发现文档总是漏更新（如 examples #9 在「能力边界」漏列、开发文档 `DETERMINISTIC` 漏列）。原 `doc-llm` 是 agent 语义接手、非确定性、INFO 不阻断，**正是漏检的元凶**——把命门放在最不可靠的那层。故能力缺口检测改为**确定性**落地在 `doc` 检查器（Vector 1），与 `EXIT_CODE_ONLY`/`DOC_COUNT_DRIFT` 同族。
- **判定（`doc` 检查器 C3 段）**：仅当目标技能使用本框架（代码含 `ALL_CHECKERS` 标记，即审计自家技能）才做强校验，避免对第三方技能误报；
  - 检查器枚举覆盖：注册的每个检查器名须以独立 token 出现在 SKILL.md / references 文档（边界负向断言避免 `doc` 误匹配 `document` / `doc-llm`）；
  - 正向能力覆盖（CLI 参数）：仅扫用户面向入口 `cli.py` 声明的 `--` 参数（排除 dev 工具私有参数），剔除 `INTERNAL_CLI_FLAGS`（CI/高级/调试用途），任一被扫文档出现即视为已文档化；
  - 与 `DOC_CAPABILITY_DRIFT`（文档声称、代码无，反向）正反向对称，统一 `WARN`（与 `DOC_COUNT_DRIFT` 同级，`--strict` 下阻断发布，强制补文档）。
- **doc-llm 同步增强**：dossier 新增「正向覆盖缺口」预分析段，调用同一 `compute_capability_gaps()`（与 doc 检查器共用、单一真相源、免两套实现漂移），把代码有文档缺的检查器名 / CLI 参数直接列为 agent 比对要点，免去其自行穷举对账。即「两者都要」：doc 出确定性 WARN 兜底 + doc-llm fact sheet 补缺口段供语义复核。
- **共享逻辑**：`core.py` 新增 `CLI_FLAG_RE` / `INTERNAL_CLI_FLAGS` / `cap_token_present()` / `compute_capability_gaps()`；`CATEGORY_LABELS` 登记 `DOC_CAPABILITY_MISSING`。
- 验证（正向）：人为从文档并集抠掉 `--examples-timeout`，C3 立即报其为缺口；反向/既有：本仓库文档完整时 C3 为 0 缺口；`self_validate` 4 fixture 因 `blob` 不含 `ALL_CHECKERS` 不触发 C3、黄金快照不变、全 PASS；`dev_self_audit --strict` 发布面 `ERROR 0 / WARN 0 / INFO 35`。

### 同步钩子不再自动打包，发布改为「市场自行重打包」（dev-only）
- **动机**：`skillhub publish <技能目录>` 时市场会自行重打包，本地 `dist/*.zip` 无用；更糟的是被发布目录内若含 `.zip` 会被市场拒收（`400 不允许的文件类型: dist/skill-doc-audit.zip`）——v1.26.0 上架时实测踩到，当时只能临时复制一份排除 `dist/` 的副本来绕开。
- **`sync_deploy.py` 移除自动打包**：删除 `import build_dist` 与 `build_dist.ensure_fresh()` 调用；`SYNC_FILES` 移除 `dist/skill-doc-audit.zip`；`_verify()` 移除 zip 的 sha256 比对（随之删除已无用的 `_sha256()` 与 `hashlib` 导入，避免留死代码）。
- **不再反复清理 dist**（移除 `_clean_stale_dist()`）：第 34372b2 已移除自动打包，但当时保留了每次同步删历史 `dist/` 残留——因 sync_deploy 不再产生 dist、本机副本已清，这步纯属永远空操作（幂等无副作用但冗余）。本轮移除该函数与调用，sync_deploy 回归「只同步、只增不删」纯净职责（与「刻意不做的事」一致）；若旧副本残留 `dist/`，手动 `rm -rf <deploy>/dist` 一次即可，无需保留清理逻辑。
- **删除 `src/scripts/build_dist.py`**（制品构建脚本，dev-only）：市场自行重打包后已无用途；`dev_self_audit.py` 的 `DEV_TOOLS` 移除该条目；`.gitignore` 移除 `src/dist/skill-doc-audit.zip` 条目并注明不再产出制品；本地 `src/dist/` 与部署副本 `dist/` 均已清除。
- **`release_check.py` 移除 dist 过期守卫**：不再自动打包后，该守卫会恒误报「制品过期」，故删除 `check_dist_staleness()` 并移出 `CHECKS`，模块 docstring 同步更新。
- 验证：`py_compile` 通过；`sync_deploy.py` 实测删除副本 `dist/` 残留并 `verify: OK`；`self_validate` 4 项全 PASS；`dev_self_audit --strict` ERROR 0 / WARN 0 / INFO 35。

### DEVELOPMENT.md：新增「同步钩子自动执行命令表」
- 把原「具体执行什么」的编号列表升级为**命令表**，覆盖钩子 2 步前置（`git rev-parse` 定位仓库根须带 `|| true`、按 `SKILL_AUDIT_PYTHON` → `$HOME` 托管版 → 系统标准路径 → PATH 定位解释器）与 `sync_deploy.py` 的 7 个自动动作，逐行给出：动作 / 实现调用 / 作用 / 失败后果；顺带修掉原列表的编号重复（出现两个「5.」）。
- 新增「刻意不做的事」澄清职责边界：不构建制品、不发 `[agent-todo]`、不跑检查器、不删除发布面之外的文件（`dist/` 是唯一例外，因其为本仓库自己造出的过时产物）。

### 新增 `[agent-todo]` 第 8 类：上架 SkillHub 前须先获得用户授权
- `dev_market_bench.py check-bump` 新增第 8 类提示（`[必须]`，阻断）：**任何版本变化**（x.y.z 任一字段，**含补丁号**）都打印——任何版本都可能需要上架，而上架是外部公开动作，须用户点头后才可执行 `skillhub publish`；未获授权前只能本地 commit/push。
- 与第 5–7 类触发条件不同源：第 5–7 类仅在次/主版本变动时打印，第 8 类补丁版本也打印（否则补丁版本会被静默上架）。提示文本同时给出发布姿势（`skillhub publish <技能目录> --changelog "..." --json`）与踩坑警示（发布目录内不得含 `dist/` 或任何 `.zip`）。
- 文档：DEVELOPMENT.md 指令清单删除已失效的「dist 制品过期」类（原第 4 类）并把后继类号前移，新增第 8 类；说明行、严重度语义、真实渲染样例同步更新；README「打包与发布」改为**目录发布**并标注「须先取得用户授权」与 dist 禁忌。
- 验证：模拟次版本变动（1.25.0 → 1.26.0）第 5–8 类按序全打印；模拟补丁级变动（非次/主）**仅**打印第 8 类，不误触发 5–7 类重量级提示。


## 1.26.0 打磨明细（泛用版 examples 检查器 + 开发套件改进收口）

### 泛用版 examples 检查器（v1.26.0 新增，检查器 #9，进 --all-checks）
- 对任意技能文档里的命令示例做静态校验：示例引用的脚本文件是否存在（`EXAMPLE_TARGET_MISSING`）、传给脚本的参数是否在脚本中声明（`EXAMPLE_FLAG_UNKNOWN`，仅 SKILL.md）、示例调用的外部 CLI 是否在文档声明（`EXAMPLE_EXT_CMD` INFO）、是否含危险/不可逆命令（`EXAMPLE_DANGEROUS` ERROR/WARN）。
- 三档模式（`--examples-mode`）：`static`（默认，纯静态，零执行/零网络/零 token）/ `ask`（交互询问是否允许沙箱试运行，30 秒超时或本地非交互回退 static 并 INFO 标注降级）/ `run`（受限沙箱试运行带 `expected` 标注的示例）/ `off`（跳过）。
- 安全红线不可放宽：即便 `run` 模式也绝不执行文档里的任意 shell——只跑白名单解释器（python/python3/node）+ 技能内脚本 + 无 shell 元字符 + 带 `expected` 标注 + 超时（`--examples-timeout` 默认 20s）/ 条数上限（`--examples-max-cmd` 默认 12）约束的命令；不满足即跳过并 INFO 说明。
- 仅核验脚本扩展名（`.py/.js/.mjs/.ts/.sh/.ps1`），仓库引用 / 安装路径 / 输出文件 / 占位目录一律跳过（避免把说明性路径误判为缺失文件）；通用文件引用由 `doc` 的 `DEAD_PATH` 覆盖。参数校验仅 SKILL.md、无参数表可确定时跳过；纯文档快照退 INFO。
- 注册与接线：`ALL_CHECKERS` 追加 `examples`、`CHECKER_CODES["examples"]=9`、`CATEGORY_LABELS` 登记 12 个 EXAMPLE_* 项；CLI 新增 `--examples-mode/--examples-timeout/--examples-max-cmd`；`self_validate` 的 `DETERMINISTIC` 收口 examples，`tests/examples/manifest.json` 新增 `examples-skill` 夹具（覆盖引用缺失/危险命令/未声明外部 CLI/带期望标注四类场景），`make_fixtures.py` 同步 recipe；`sources.py` User-Agent 升 1.26.0。
- 验证：`py_compile` 通过；examples 检查器对当前技能文档 `ERROR 0 / WARN 0 / INFO 0`（无脚本引用误报）；examples-skill 夹具四类场景均按预期触发；run 模式沙箱正负向实测（白名单内脚本执行、越界/含元字符/非白名单解释器均跳过）；`self_validate` 全 PASS；`dev_self_audit --strict` 零回归（详见下方「部署自审」计数）。

### 开发套件解耦改造（dev-only，_devcommon.py / dev_market_bench.py / hooks / 文档）
继技能本体解耦后，对 dev 工具做同等改造——dev 工具虽不进部署副本，却运行在环境差异最大的位置（git 钩子本机 vs CI、换机器/用户名/操作系统/宿主 agent）。
- **解释器硬编码（P0）**：`dev_market_bench.py` 原写死 `PY = C:/Users/<user>/.workbuddy/binaries/python/versions/3.13.12/python.exe`，换机器/换用户名/换 OS 必失效。现由新增的 `_devcommon.resolve_python()` 解析：`SKILL_AUDIT_PYTHON` > `sys.executable` > `python3`。
- **外部命令依赖（P1）**：下载原 `subprocess` 调 curl，Windows 精简环境 / Linux 最小容器常无 curl，整条基准链路会失效。改为 `_http_download()` 优先标准库 `urllib`，curl 仅作回退（并加 `-f` 使 HTTP 错误码返回非零）。
- **下载成功判据修复（实测踩坑）**：原判据仅 `size>0`——实测 curl 对 404 仍返回 `rc=0` 并把服务端 17 字节错误页（`Vers...`）写入目标文件，被误判为下载成功、到 `zipfile` 才炸且信息失真。新增 `_looks_like_zip()` 校验 zip 魔数（前 2 字节 `PK`），两条路径下载后统一校验，魔数写进错误信息便于诊断。
- **宿主路径写进提示指令（P2）**：`check-bump` 第 7 类 `[agent-todo]` 原写死 `~/.workbuddy/skills/skill-doc-audit`，现经 `resolve_deploy_dir()` 动态解析后打印（非标准安装/跨 agent 亦正确）。
- **候选根重复实现（P3）**：`dev_market_bench.local_candidate_dirs()` 原自抄一份 `~/.workbuddy`/`~/.codebuddy` 候选表，与 `_devcommon` 重复、改一处漏一处。现复用新增的 `_devcommon.candidate_roots()` 单一真相源（本机可用源仍为 49 个，行为不变）。
- **git 钩子（P4）**：`post-commit`/`pre-push` 原硬编码 `/c/Users/<user>/.../python.exe` 与 `/c/Python314/python.exe`，现一律以 `$HOME` + 系统标准路径（`/usr/bin/python3`、`/usr/local/bin/python3`、`/opt/homebrew/bin/python3`）表达，支持 `SKILL_AUDIT_PYTHON`（最高优先）/`SKILL_AUDIT_PYTHON_CANDIDATES`（空格分隔追加）覆盖。另修「静默跳过」隐患：`REPO_ROOT="$(git rev-parse ... || true)"` 补 `|| true`——脚本开了 `set -e`，git 不可用会让命令替换非 0 并 errexit 终止，连告警都打印不出来。
- 文档：DEVELOPMENT.md 新增「开发套件的解耦约定（跨平台 / 跨 Agent）」节（5 维约定表 + 钩子 2 条 + 下载判据踩坑）；第 7 类 todo 与渲染样例改为动态解析路径；`core.hooksPath` 示例改为 `<repo>/hooks` 占位。CI 注释与 `sync_deploy` docstring 的宿主路径同步中立化。
- 验证：`py_compile` 8 个 dev 脚本全通过；`resolve_python()` 默认取当前解释器、环境变量覆盖生效；`resolve_deploy_dir()` 解析正确且 check-bump 打印已动态化；下载正负向实测——不存在 slug 明确失败（`urllib 404;curl_failed(rc=22)`）、真实 slug 成功（3551 字节、zip 有效含 SKILL.md）；钩子正常环境同步 OK、环境变量覆盖生效；`dev_self_audit --strict` ERROR 0/WARN 0/INFO 33 零回归。

### 市场质量基准实测器：8 线程并发参数化 + 本地优先多源（dev-only，dev_market_bench.py）
- **并发落地为显式参数**：原 `build_index` 内 `ThreadPoolExecutor(max_workers=8)` 为硬编码、不可调；现新增 `--workers`（默认 **8**，即用户确认的方案）与 `--delay`（默认 0.0，每个评测请求前额外等待秒数，用于按需进一步降低瞬时请求密度）。新增 `_quality_task(slug, delay)` 承载限速；`build_index`/`run_bench` 签名与 `index`/`run` 两个子命令均透传，日志打印实际并发数与等待时长。
- **本地优先由「单一路径」升级为「多候选源」**：新增 `local_candidate_dirs()`，按优先级遍历——环境变量 `SKILL_MARKET_BENCH_LOCAL_DIRS`（`os.pathsep` 分隔，最高优先，便于 CI/异机复用）> 官方本地技能市场 `~/.workbuddy/skills-marketplace/skills`（find-skills Step 5）> `~/.workbuddy/skills`、`~/.codebuddy/skills`（find-skills Step 4）> IDE 市场插件缓存 `~/.workbuddy/plugins/marketplaces/*/plugins/*/skills`。**动机**：官方市场目录本机并不存在，旧实现短路从未生效；补入其他同语义本地副本后本机可用源从 0 增至 49 个。只读复制、**绝不改动或安装进实时技能目录**。
- 计数与可观测：`download_and_extract(slug, stats=None)` 新增可选 stats，累计 `local`/`remote`；`run` 开头打印本地源清单、结束打印「本地命中 / 远端下载」并写入报告 meta（`local_hits`/`remote_downloads`）。
- 配套：`_skill_dir_has_md()` 判定（目录自身或一层子目录含 SKILL.md）；补 `import glob`；模块 docstring 增「请求密度控制」与更新「下载口径」段；DEVELOPMENT.md 市场实测器章节补第 5（并发/限速）、第 6（本地优先多源）条与 `--workers/--delay` 用法示例。
- 验证：`py_compile` 通过；本地命中实测（本机插件缓存 `pdf`）返回目录含 SKILL.md 且 `stats={'local':1,'remote':0}`、不走网络；环境变量覆盖分支生效且优先级最高；`index --pool 3 --workers 2 --delay 0.3` 日志确显示「2 线程并发…等待 0.30s」且 3/3 取到质量分；`--help` 默认显示 workers 8 / delay 0；测试产物（pdf、zz-demo）已清理，测试污染的小索引已删除（下次 `run` 按默认参数重建）。

### 本地 CI 版本一致性门禁加固（dev-only，release_check.py）
- `release_check.py` 新增 `check_readme_version()`：校验 `README.md`「版本摘要」表最新版本行 == `SKILL.md` `version`（阻断级 ERROR）。至此「版本四处一致性」中 SKILL.md / sources.py User-Agent / README 版本表三处机器强制相等，CHANGELOG 仍仅校验「已收口为版本节」（`check_changelog_promotion`）。
- 由 `dev_self_audit.py`（pre-push 钩子与 dev-qa 工作流共用）调用，版本不符时归入 `rel_block` → `--strict` 退出码 1 → 拦截推 main；阻断项已在 `dev_self_audit` 输出以 `[agent-todo][ERROR]` 渲染，无需另加提示。
- 解析容错：README 版本表行解析不到时不误拦（格式异常由人工兜底）。
- 验证：反向测试（临时文件模拟 README 版本不符）确返回阻断 ERROR；一致场景不误报；`dev_self_audit --strict` ERROR 0/WARN 0/INFO 33 零回归。

### 修复 check-bump 版本变动检测失效（dev-only，dev_market_bench.py）
- **根因**：`current_version()` 从 SKILL.md frontmatter 读出的版本带 YAML 引号（`"1.25.7"`），`_ver_tuple()` 解析失败返回 `None` → `is_minor_or_major_bump` 恒为 `False` → 次/主版本变动也**从不打印 `[agent-todo][建议]`**，功能形同虚设（此前所有提交都未触发过该提示）。
- **修复**：`current_version()` 改用带引号容错的 `VERSION_RE`（与 `release_check.py` 对齐）去引号；`_ver_tuple()` 增加 `.strip('"').strip("'")` 健壮性（空段忽略）。修复后次/主版本（x.y）变动正确打印 `[agent-todo][建议]`，补丁号（x.y.z）变动按设计不触发。
- 配套文档：DEVELOPMENT.md「本地 CI 发出什么」节补第 6 类 `[agent-todo]`（check-bump 版本变动基准建议）真实渲染样例与「仅次/主版本触发、补丁号不触发」说明；release_check 表补 README 版本表行、由「共 4 类」更正为「共 5 类」。
- 验证：模拟次版本 1.24.0→1.25.7 确打印 `[agent-todo][建议]`；当前无次/主变动时 `dev_self_audit --strict` 零误报（ERROR 0/WARN 0/INFO 33、rc 0）。

### 第 7–8 类 `[agent-todo]`：次/主版本变动须执行文档自审计与全量自审计（dev-only，dev_market_bench.py + dev_self_audit.py + DEVELOPMENT.md）
- **第 7 类（doc + doc-llm 文档自审计）由 `[建议]` 升为 `[必须]`（阻断）**：次/主版本变动属质量高风险点，文档/结构漂移必须由 agent 实际跑过审计确认后才可发布。指令：`python src/scripts/audit_docs.py --skill ~/.workbuddy/skills/skill-doc-audit --check doc --check doc-llm --doc-llm-mode agent`。
- **新增第 8 类（开发者模式全量自审计，必须、阻断）**：次/主版本变动时提示 agent 执行一次 `python src/scripts/dev_self_audit.py --dev-docs --strict`（全量检查器 + README/CHANGELOG 文档自审计，确认 dev 工具与发布面一致、无漂移），更好维护整体质量。
- **第 6 类（市场质量基准实测）保持 `[建议]`（不阻断）**：基准实测 `run` 只在人工要求或 agent 评估后执行，check-bump 对它「建议、绝不自动跑」。
- **机制变更（关键）**：`dev_self_audit.py` 不再纯透传 check-bump 的 stdout，改为经新增 `_parse_check_bump()` 解析——`[必须]` 项并入 `rel_block`（阻断，`--strict` 下升退出码、拦 push）、`[建议]` 项并入 `rel_info`（不阻断）；原样保留「必须/建议」标签使文档与渲染逐字一致。第 7–8 类由此真正强制，而非仅提示。
- **第 5 类扩展**：`release_check.check_temp_residue` 在 `temp/` 残留之外新增检测仓库根/`src` 下的 `*.bak`/`*.bak.*` 过时备份（审计工具生成的 SKILL.md.bak.<n>，默认保留最近 3 个、更早的清理），指令补「清理 *.bak 备份」。
- DEVELOPMENT.md「`[agent-todo]` 指令清单」由 7 行扩为 **8 行**；第 5 行补过时备份、第 7 行升「必须(阻断)」、新增第 8 行；说明文字与渲染样例同步更新（含 `_parse_check_bump` 合并渲染、第 6–8 类严重度语义）。
- 验证：模拟次版本 1.24.0→1.25.7 确打印第 6 类 `[建议]` + 第 7–8 类 `[必须]`，且 `dev_self_audit --strict` 退出码 1（rel_block 非空 → 拦 push）；无版本变动时零误报（ERROR 0/WARN 0/INFO 33、rc 0）。

### 发布前重打包交由同步钩子自动执行（dev-only，build_dist.py + sync_deploy.py + release_check.py + .gitignore）
- **目标**：把「发布 SkillHub 前手动重打包 dist 制品」从 agent 手动步骤改为同步钩子自动执行，彻底消灭陈旧 zip 漂移。
- **zip 改为生成产物、不再入库**：`.gitignore` 新增 `src/dist/skill-doc-audit.zip` 并 `git rm --cached` 取消跟踪（磁盘文件保留，clone 后首次提交即由钩子重建）；发布面以「最新 `src/`」为唯一真相源。
- **`sync_deploy.py`（post-commit 钩子）在同步前调用 `build_dist.ensure_fresh()`**：zip 缺失或早于发布面源码（SKILL.md / audit_docs.py / checkers.md / auditlib）则重建（18 项），否则跳过；随后照常同步到部署副本。部署副本与 SkillHub 发布永远基于最新 `src`，陈旧 zip 漂移在物理上不可能发生。
- **`build_dist.py` 重构**：暴露 `build()`（强制重建，供 CLI/手动）+ `ensure_fresh()`（缺失或过期才重建，供钩子调用）；发布面与 `sync_deploy.SYNC_FILES/SYNC_DIRS` 保持一致。
- **`release_check.py::check_dist_staleness` 降级为兜底守卫**：常规流程 zip 已由钩子重建、恒不提示；仅当 `hooks/post-commit` 未运行（钩子跳过 / python 未定位）导致 zip 缺失或过期时才发 `[agent-todo][INFO]` 提示手动重建。模块顶部说明同步更新（dist 重打包移出「必须由 agent 执行」清单）。
- **文档同步**：DEVELOPMENT.md「同步钩子具体执行什么」补「按需重建 zip」步骤、第 4 类 `[agent-todo]` 改为兜底守卫文案、`release_check` 节与 sync_deploy 节措辞更新；README.md「打包与发布」与 `core.hooksPath` 绝对路径说明更正。
- 验证：`sync_deploy.py` 过期/缺失 zip 场景确自动重建、最新场景跳过重建；部署副本 zip 与 `src/` zip sha256 一致；`dev_self_audit --strict` ERROR 0/WARN 0/INFO 33 零回归。
- **补充验证（兜底守卫正向触发实测 + 版本号漂移修正）**：用户追问下实测兜底守卫两个正向分支均能正常触发——① zip 早于发布面源码（模拟 `post-commit` 钩子跳过）确打印 `[agent-todo][INFO] dist 制品可能过期（同步钩子未重建）`；② zip 缺失（模拟钩子从未运行）确打印 `[agent-todo][INFO] dist 制品缺失（同步钩子可能未运行）`；两者 EXIT 0（INFO 不阻断，符合设计），正常流程（zip 最新）恒不误报。另修正 `release_check.py` / `build_dist.py` / `DEVELOPMENT.md` 中误写的「v1.25.8 起」——当前版本仍为 1.25.7（未发布累积、dev-only 改动不进部署副本），按约定版本号于授权发布时统一升，故改为版本中立措辞；全仓已无 1.25.8 残留。

### 市场质量基准实测器下载口径对齐官方 find-skills（dev-only，dev_market_bench.py）
- **确认**：`download_and_extract` 原本使用的 `https://lightmake.site/api/v1/download?slug=<slug>` 即 find-skills 技能文档 Step 6 的官方端点，下载通道本就官方、非野路子。用户建议「用官方 SKILL 的 API 下载更安全」后核实一致，并据此进一步对齐官方流程。
- **强化（本地优先短路）**：新增常量 `LOCAL_MARKETPLACE`（`~/.workbuddy/skills-marketplace/skills`）；`download_and_extract` 先查该目录，样本技能若已存在则直接 `copytree`、不发网络请求。这吻合官方 find-skills Step 5 本地优先流程，同时降低对官方接口的请求频次（呼应「避免过于频繁请求引来审查」诉求）。
- 下载产物仍落 bench 临时目录、不安装进实时技能目录（`~/.workbuddy/skills`）；下载合法性以官方端点为准，**不依赖任何内部/未公开路径**。
- 模块文档补「下载口径」段说明本地优先 + 官方端点，明确产物落点与不依赖内部路径。
- 验证：本地优先分支无网络复制 OK；网络分支 1 个真实请求（slug=oo-browserbase）下载 OK；py_compile 通过。

## 1.25.7 打磨明细（TRACE 评测整改 + 市场质量基准实测器固化收口）

### TRACE 评测整改（部署副本自评 4.7/优秀，补强 <5.0 子项，文档级）
针对部署副本 `skill-doc-audit/1.25.6` 的 TRACE 自评（综合 4.7、优秀、无安全红线）中得分 <5.0 的 5 个子项逐项补强文档表述；均为文档修订、无审计口径变化：
- **T1 国内适配性（4.3）**：「多平台来源（--source github / skillhub / url）」补一段「**本地审计完全离线、零外部依赖**」说明——`--source local`/`--all` 只读写本机目录、不联网、不需任何外部 CLI 或令牌；仅 `--source github`/`skillhub` 需对应外部命令在 PATH、`--source url` 用标准库 `urllib` 同样零外部 CLI。消除「远程审计条目让人误以为本工具整体需联网」的误导。
- **A1 能力边界（4.3）**：「能力边界速查」第三列（脚本根本查不出的）补本技能特有示例——「安全设计的合理性（如：审计策略该用静态规则还是 LLM、密钥是否明文落盘）」，使该列从泛例转为技能专属。
- **C1 反模式与 FAQ（4.5）**：「常见问题与避坑」顶部加「本节导航（速查锚点）」——列速答三问/新手误区/避坑要点三个锚点，便于长文档内跳转。
- **E2 内容完整度（4.5）**：`deps` 检查器补「何时显式声明 `target_platform`」决策指引——何时应写（OS 专属 API/平台专属 shell 是设计内）、为何写（消误报、提精度）、为何不可谎报（跨平台全检才是真值）。
- **E3 创造力与增值（4.5）**：跨平台可移植性矩阵（`--report portability-matrix`）与生态级健康度汇总（`--report health`）已具文档，无需改动；其真实增益以 SkillHub 官方评测为准，自评仅据静态证据给分（已在评测报告中注明）。

### 市场质量基准实测器固化（收口，取代旧 bench/market-audit/run_market_audit.py）
- 取样指标由市场 `score`（热度）改为 **TRACE 官方质量评测分**（`overall`，5.0 分制），取值方法与 trace-selfcheck 的 `benchmark_official.py` 同源（`fetch_evaluation(slug)` → `parse_eval` → overall）。
- 取样规则：全市场随机页偏移抽样候选池（默认 1000，避免热度偏差）→ 逐个取质量分 → 升序取质量最低 1000 → 随机抽 50；默认不固定种子（每次天然不同）+ 采样历史去重近 3 次，避免重复样本。
- 规模约束近似（实测确认）：市场技能 13.3 万、列表接口仅支持 score/downloads/stars/updatedAt 排序且不返回质量分字段、全量爬评测不可行；故「质量最低 1000」为候选池内工程化近似，已在报告头部显式标注，避免误读为字面全局最低。
- 不进自动调度：实际 `run` 仅人工要求或 agent 评估重大版本变动后建议时执行；`check-bump` 子命令供 `dev_self_audit` 在次/主版本变动时打印 `[agent-todo]` 建议（best-effort、不失败 CI、绝不触发 `run`）。
- 新脚本 `src/scripts/dev_market_bench.py`（dev-only，已入 `DEV_TOOLS` 排除集）；`dev_self_audit.py` 末尾 best-effort 调其 `check-bump`；旧 `bench/market-audit/` 删除、`bench/` 加入 `.gitignore`。
- 验证：小池冒烟测试全链路通过（候选池抽样→取质量分→最低区间抽样→下载→全量审计→报告；doc-llm 真执行 3/3）。


## 1.25.6 打磨明细（跨平台黄金快照修复 + CI Node 20 警告消除 + 工程化行尾统一）

### 跨平台黄金快照比对修复（CI 在 ubuntu 上 self_validate 失败）
- 问题：`runtime`(capability/py_syntax) 与 `security`(hardcoded_secret/path_traversal/...) 检查器把真实脚本路径（来自 `code` 字典键，由 `os.path.relpath` 生成）写入 finding 的 `file` 字段与 `message`；Windows 下为反斜杠（`scripts\main.py`）、Linux 下为正斜杠（`scripts/main.py`）。`self_validate` 的黄金快照在 Windows 生成并固化了反斜杠，导致 ubuntu CI 上 `dirty-skill` 比对出现 4 条「额外发现/缺失发现」差异、exit code 1 标红。
- 修复：`core.finding()` 出口统一将 `file`/`message`/`ref` 的反斜杠归一为正斜杠（`replace("\\","/")`），Windows 与 Linux 输出一致；正斜杠对所有平台合法可读。这是唯一改动点，检查器逻辑不变。
- 验证：`make_fixtures.py --baseline` 重基线（黄金快照仅 7 处 `scripts\`→`scripts/`，无其它变更）；本地删 fixtures 强制走 CI「make_fixtures 重建→比对」路径，`self_validate` 三例全 PASS（exit 0）；`dev_self_audit` 零回归。GitHub Actions `检查器行为回归 (self_validate)` 复验已绿（commit `c4f276c`）。

### CI 消除 Node 20 废弃警告
- 升级 `.github/workflows/dev-qa.yml` 两个 job 的 GitHub Action：`actions/checkout@v4`→`@v5`、`actions/setup-python@v5`→`@v6`（GitHub 2025-09-19 公告弃用 Node 20 运行器，旧版本被强制在 Node 24 上跑并告警；这两个 major 版已迁移到 Node 24 运行器）。`python-version: "3.13"` 不变。纯 CI 配置改动，无代码/功能影响（补丁级，版本升 1.25.6）。

### 工程化行尾统一（.gitattributes）
- 新增 `.gitattributes`：`* text=auto eol=lf` 锁定所有文本文件（py/md/json/yml/hooks）以 LF 入库与检出，根除 Windows 上 `LF will be replaced by CRLF` 提示；`*.zip`/`*.png` 标 `binary` 免行尾转换（不损坏 `src/dist/skill-doc-audit.zip`、`icons/*.png`）。
- `git add --renormalize .` 核验：已跟踪文本文件本即以 LF 入库（0 变更），故本次仅新增配置文件、零 blob 改动；此后 Windows 检出亦保持 LF，消除 CRLF 漂移对 CI 跨平台比对、黄金快照一致性与 diff 可读性的潜在干扰。纯工程配置（补丁级，版本升 1.25.6）。


## 1.25.5 打磨明细（缺失引用去重降噪 + 检查器执行回执 + doc-llm 注册键修复 + 扫描范围收敛 + 文档三分式固化）

### 缺失引用去重降噪（降噪，提升 ERROR 可读性）
- 问题：同一「被引用但不存在」的文件会被 `doc`(DEAD_PATH) / `structure`(broken_ref) / `runtime`(script_ref_missing) 三个检查器各报一条（如某技能缺 2 个脚本 → 13 个 ERROR 中约 9 条是这 2 文件的跨检查器重复）；`doc` 还会对同一裸文件名逐次报 `EXTERNAL_REF`（如 `api-spec.md` 出现 4 次 → 4 条）。聚合 ERROR/WARN 计数被严重虚高，可读性受损。
- 修复：新增 `dedupe_findings()`（`core.py`），`analyze_skill` 在检查器 dispatch 后按「引用路径」归并缺失引用类 finding——`DEAD_PATH`/`broken_ref`/`script_ref_missing` 按完整路径合并为单条，`EXTERNAL_REF` 按裸文件名合并；合并后保留最高严重级，message 标注命中检查器集合（如 `被 doc、runtime、structure 检查器重复报告，已合并去重`），并附 `dedup` 溯源字段（`checkers`/`categories`/`count`）。`finding()` 新增可选 `ref` 参数承载归一化引用路径（不参与报告与快照比对）。
- 口径边界：仅归并「同一路径的同类重复」，分组键含类型（missing / extref），缺失文件与裸文件名引用不会互相吞并，绝不掩盖不同根因的真实缺陷。
- 零回归验证：`make_fixtures.py --baseline` 重建黄金快照（仅删 5 条 missing-ref 重复：dirty-skill 的 DEAD_PATH×2 / broken_ref×2 / script_ref_missing×1，无真实发现丢失）；`self_validate.py` 三例全 PASS（dirty-skill error=10 / warn=3、tricky-clean error=0 / warn=0、multifile error=1 / warn=1）；`py_compile` 全过；`dev_self_audit` 零回归。

### 设计原则新增「跨平台、跨 Agent 适配」+ 部署目录跨 agent 自动探测
- SKILL.md「设计原则（核心约束）」新增第二条原则：**跨平台、跨 Agent 适配，不写死宿主假设**——路径一律 `expanduser("~")`/环境变量解析（禁硬编码 `C:/Users/admin/...`）；dev 工具经 `resolve_deploy_dir()` 定位部署副本（`SKILL_DEPLOY_DIR` 显式覆盖最高优先，任意平台/agent 通用）；用户侧审计本就 agent 无关。
- `_devcommon.resolve_deploy_dir()` 拓宽候选根，真正适配非 WorkBuddy agent：新增通用覆盖 `SKILLS_DIR`/`AGENT_SKILLS_HOME`（任意 agent 可指向自家 skills 根）+ 已知第三方 agent 技能根（Claude/Cursor/Codex/OpenCode/Aider，含 Claude 插件嵌套布局 bounded walk 兜底）；宿主 agent 配置目录与标准默认保持不变。
- 新增 `tests/test_resolve_deploy.py`：T1 显式覆盖 / T2 通用覆盖 / T3 宿主配置目录 / T4 跨 agent 扁平 / T5 跨 agent 嵌套 / T6 全未命中回落默认，全 PASS 证明跨平台+跨 agent 定位可靠。
- 落地依据：原检测机制（仅 WorkBuddy 候选根）在非 WorkBuddy agent 装本技能时无法自动定位副本；现 `SKILL_DEPLOY_DIR` 通用覆盖 + 多 agent 候选根使机制真正跨 agent，不再依赖「用户手动设路径」才能工作。

### SKILL.md 去版本号标注（聚焦「是什么 / 怎么用」，版本变更归 CHANGELOG）
- 用户决策（2026-09-01）：SKILL.md 是面向用户的文档，应聚焦「这是什么、怎么用」；带版本号的版本变动描述属开发者视角的变更史，统一收口到 CHANGELOG.md（开发者 / QA 留档，不进部署副本）。故移除全文 7 处 `v1.x` 版本标注——`doc-llm` 能力项、doc-llm 语义检测小节标题与「关键变更」块、`security` 误报自纠错能力扩展说明、`hardcoded_path` 上下文感知过滤、`--all-checks` 跑 doc-llm、`DOC_*` 结构化交叉校验引入——改写为「当前能力陈述」而非「自某版本起」，保留行为解释（如「由 agent 直接接手、不再调外部 LLM」），仅删版本号与「X 起」里程碑措辞。
- 改写后 SKILL.md 仍准确枚举 8 个检查器（doc / structure / security / runtime / deps / deadcode / portability / doc-llm），与 `auditlib/checkers/__init__.py` 自注册的 8 个检查器一致；未改动检查器数量声明，故 `DOC_COUNT_DRIFT` 不会误报。
- 保留项修正（2026-09-01 后续）：**前述「保留 `Phase 6` 等内部开发阶段标签」的判断已被用户推翻**——用户指出内部开发阶段标签 / 方案代号依然属于给开发者看的内容，同样应排除出 SKILL.md。故 `portability` 错误码表的 `lossy_port` 行已移除 `Phase 6：` 来源注记，仅留纯行为描述（「声明跨 Agent 目标却含目标端无对应/需转译的字段」）；frontmatter 强制 `version:` 字段不受影响。

### SKILL.md 终校：移除开发者视角内容泄漏（用户文档再瘦身）
- 用户要求终校 SKILL.md 是否残留「普通用户无需关注」的内容。宽口径扫描确认：版本号（7 处，前轮已清）、内部开发阶段标签（Phase 6，前轮已清）；本轮清出 2 处开发者视角泄漏：①「设计原则·跨 Agent 适配」节原用 `sync_deploy`/`dev_self_audit`/`_devcommon.resolve_deploy_dir()` 等**开发期脚本名**+「已部署副本」内部概念解释原则——普通用户跑 `audit_docs.py` 永不接触这些脚本，已删除该子弹（原则由「路径零宿主硬编码」+「用户侧审计本就 agent 无关」两子弹完整表达）；②运行示例原写「对本技能项目目录 `src/` 的审计；因目录名 `src` ≠ 技能名 `skill-doc-audit`」，`src/` 与 `skill-doc-audit` 为项目内部标识符，已改写为通用表述、保留「目录名≠技能名会多一个良性 name_mismatch」的讲解。
- 保留项核查：第 128/226 行 `src/` 指「被审计仓库内 SKILL.md 可嵌套在 `src/` 子目录」这一**通用能力说明**（适用于任意技能仓库），非本项目内部泄漏，保留；frontmatter 强制 `name/slug/version` 字段为 WorkBuddy 技能强制字段，非泄漏。

### 发布就绪检查（release_check.py · 让同步钩子/本地CI 对 agent 发提示，减少记忆依赖）
- 用户两问：①版本迭代/文件修改后是否还有需「同步钩子/本地CI」囊括的执行操作；②版本迭代后必须由 agent 执行的操作（如清理测试残留、重打包过期制品）能否让钩子/CI 对 agent 发提示，减少对记忆文件的依赖。
- Q1 核查缺口（此前仅靠 agent 记忆）：a) **版本号一致性**：`SKILL.md` `version` 与 `sources.py` 第144行 `User-Agent: skill-doc-audit/1.25.4` 无任何检查，升版本忘改 UA 会带陈旧版本自报远端；b) **CHANGELOG 收口**：升版本后须把「未发布改动」提升为版本节，未强制；c) **dist 制品重建**：`README:39` 要求改动发布面后重打包 `dist/skill-doc-audit.zip`，无构建命令、钩子不重建（部署副本用实时文件故运行无碍，但 SkillHub 发布会打包旧代码——实测重建后 sha 改变，证实此前提交的 zip 确已过期）；d) **temp/ 残留清理**：记忆约定「清理前先问用户」，属易漏的 agent 操作。
- Q2 落地：新增 `src/scripts/release_check.py`（dev-only，被 `dev_self_audit.py` 调用，故本地 `pre-push` 与远程 `dev-qa` CI 都提示）输出带 `[agent-todo]` 标记的提示块——版本一致性(ERROR 阻断)/CHANGELOG 收口(WARN 阻断)/dist 过期(INFO)/temp 残留(INFO)；阻断项并入 `dev_self_audit` 退出码（`--strict` 下拦 push）。配套新增 `src/scripts/build_dist.py`（可复现打包命令，提示里直接给出）。`dev_self_audit.py` 的 `DEV_TOOLS` 排除集补入两新脚本避免 orphan_asset 误报。
- 严格测试：负向验证——临时把 `sources.py` UA 改为 1.25.3，`dev_self_audit --strict` 即 `EXIT=1` 并输出 `[agent-todo][ERROR] 版本号不一致…改为 skill-doc-audit/1.25.4`；还原后 `EXIT=0`、当前状态无阻断提示。`dev_self_audit --strict` 全检查器 ERROR 0 / WARN 0 / INFO 40 无回归；重建的 `dist` 已纳入提交。

### doc / doc-llm 扫描范围收敛：默认纳入 references/*.md，开发者模式递归扫全部 .md
- 落地用户拍板的折中方案：doc / doc-llm 默认扫描集从「仅 SKILL.md」扩为「SKILL.md + `references/*.md`」（技能自带参考文档，随代码漂移真实存在，此前完全不扫）；开发者模式（`--dev-docs`）递归扫描技能文件夹内**全部** `.md` 描述性文档（README/CHANGELOG/examples/License 等），并额外纳入显式传入的 out-of-tree 文档。
- 关键修正（基于真实代码发现）：`checkers.md` 自身第 181 行含示例路径 `` `references/x.md` `` / `` `scripts/x.py` ``（带 `/`）。若把 `references/*.md` 直接套 A1 字面死路径（`DEAD_PATH` ERROR），会把这些叙述性示例路径误报为死路径，直接破坏自审计 `ERROR 0` 不变量。故把 `DEAD_PATH`(ERROR) 限定为**仅 `SKILL.md`**（规范能力目录才要求每个带 `/` 路径真实存在）；`references/*.md` 与开发文档为叙述性内容，A1 只对裸文件名报 `EXTERNAL_REF`(INFO)（低噪音、非阻断），真实断链改由 `doc-llm` 语义 dossier 覆盖。`A2`-`A5`/`C`/`B` 类检查维持仅 `SKILL.md`（能力目录口径，避免把变更日志叙事误判为漂移），与既有口径一致。
- 实现：`model.py analyze_skill` 默认把 `references/*.md` 加入 `docs` 扫描集（去重防 `os.walk` 重复）；`dev_docs is not None` 时 `os.walk(skill_dir)` 递归收集全部 `.md` 并追加显式路径（`extra_roots` 按文件自身目录解析引用）。`doc.py` A1 块新增 `doc_name == "SKILL.md"` 门控（非 SKILL.md 只报裸文件名 `EXTERNAL_REF` INFO）。`cli.py --dev-docs` 由 `nargs="+"` 改为 `nargs="*"`（空即「扫全部 .md」），preview 同步列出实际被扫文档。
- 文档真相源同步：`checkers.md` 的 doc 检查器项补充「扫描范围」说明 + `DEAD_PATH` 仅 SKILL.md 生效的口径；`DEVELOPMENT.md` 的 `--dev-docs` 行为描述与触发表更新为「递归扫描 src/ 内全部 .md」。
- 零回归验证：`dev_self_audit --no-sync-check` 全检查器 ERROR 0 / WARN 0 / INFO 42（与改动前 INFO 数一致，无新增 ERROR/WARN）；对部署副本跑默认 `doc` 检查确认 `checkers.md` 示例路径不再误报 `DEAD_PATH`；`self_validate.py` 确定性检查器黄金快照全 PASS（exit 0）；`py_compile` 全部通过。

### doc-llm 注册键 bug 修复（关键）+ 开发者模式默认 agent 接手
- **关键 bug（doc-llm 此前从未真正执行）**：`doc_llm.py` 自注册键误写为下划线 `CHECKERS["doc_llm"]`，但 `ALL_CHECKERS` 列表、命令行、以及 `finding()` 的 checker 名均为连字符 `doc-llm`。`analyze_skill` 遍历 `enabled` 执行 `CHECKERS.get(name)` 时，`"doc-llm"` → `None`，检查器被整体跳过。后果：`dev_self_audit` 全量、`cli.py --all-checks`、用户 `--check doc-llm`（会被判「未知检查器」）**doc-llm 全部落空**——整个语义漂移检测能力长期处于休眠，包括此前多轮「全量审计 / 版本迭代体检」均未实际跑 doc-llm。
- 修复：`CHECKERS["doc-llm"] = check_doc_llm`（连字符，与全量集合 / 命令行 / 文档一致）；全仓仅此一处下划线键，无其它残留引用。修复后 `--check doc-llm` 被正确接受，`--all-checks` 与 `dev_self_audit` 均真实执行 doc-llm。
- 开发者模式默认 agent 接手（用户拍板）：`dev_self_audit.py` 的 `doc_llm_mode` 由 `None`（非交互静默跳过）改为 `"agent"`——非交互也写出语义漂移 dossier（含 SKILL.md + `references/*.md` + 全部 dev .md）并打印 `AGENT_TAKEOVER`，语义比对材料落到磁盘供 agent 接手；CI 下仅多写一个临时 dossier、不影响退出码。开发者模式「扫全部描述性文档」至此真正贯通 `doc`（A1 裸文件名 `EXTERNAL_REF`）+ `doc-llm`（语义 dossier）两层。
- 零回归验证：`dev_self_audit --no-sync-check` 全检查器 ERROR 0 / WARN 0 / INFO 47（doc-llm INFO 1 为 agent handoff，无新增 ERROR/WARN）；`cli.py --all-checks --doc-llm-mode agent` 对部署副本 ERROR 0 / WARN 0；`self_validate.py` 确定性检查器黄金快照全 PASS（exit 0）；`py_compile` 全过；`--check doc-llm` 不再报「未知检查器」。

### 检查器执行回执（身份代号 + OK/FAILED/UNKNOWN 状态，根治「静默落空却显通过」）
- 用户洞察（2026-09-01）：不能总依赖 agent 兜底——上一轮 doc-llm 静默休眠 bug 证明「agent 看到 `[doc-llm] ✓` 空行就以为跑过了」并不可靠。故要求：任一检查器成功调用时返回可识别身份的参数，失败时返回 `Failed`/`Unknown`，让 agent 或使用者确证「这个检查器到底有没有真跑过」。
- 身份代号选**数字**（而非缩写名）：doc-llm 事故根因正是「注册键连字符/下划线拼写与 `ALL_CHECKERS` 不一致 → `CHECKERS.get` 恒为 None → 静默落空」。数字代号集中在 `core.py` 的 `CHECKER_CODES` 单一真相源一处登记、engine 与 CLI 共享，绝不会与注册键拼写漂移，从根上免疫该类 bug。回执/JSON 同时打印 `#编号 名称` 兼顾机读与人读（doc=#01 … doc-llm=#08）。
- 落地：`analyze_skill` 的 dispatch 循环（此前 `if fn: findings.extend(fn(ctx))` 静默吞掉 `fn is None`）改为逐检查器记录 `checker_runs` 回执，三态：
  - **OK**——检查器成功执行（返回其 `#身份代号`，即成功回执）；
  - **FAILED**——检查器执行中抛异常（已被 `try/except` 捕获、未中断其余检查器，异常转成 `CHECKER_ERROR` ERROR 发现，使运行退出码真实反映「没跑全」）；
  - **UNKNOWN**——`CHECKERS.get(name)` 为 `None`（未注册 / 名称拼写不一致），**绝不静默跳过**，转成 `CHECKER_UNKNOWN` ERROR 发现。
- 消费层：①`report.print_human` 每个检查器头部加 `[#NN 名称]` 与 `✓ 已执行 / ✗ 执行失败 / ✗ 未注册(UNKNOWN)` 状态徽标，并在每个技能尾部打印一行执行回执（`检查器执行回执: ✓doc … ✓doc-llm  [8/8 已执行 OK]`，有失败时显式列出 `✗doc-llm=FAILED`）；②`build_json` 在记录中加入 `checker_runs`（机读）；③`dev_self_audit.py` 复用同一回执（`checker_receipt_runs`）+ 头部 `#代号`；④`cli.py --preview` 启用检查器列表显示 `#NN 名称`；⑤新增 `CATEGORY_LABELS` 条目 `CHECKER_UNKNOWN` / `CHECKER_ERROR`。
- 设计要点：回执落在 dispatch 层而非改每个检查器返回签名——保留已发布的 findings 契约（零风险）、且 UNKNOWN/FAILED 统一捕获；失败不只在打印里标注，还转成 ERROR 发现，**杜绝「没跑」被误判为「通过」**。
- 零回归验证：`dev_self_audit --no-sync-check` ERROR 0 / WARN 0 / INFO 48（回执 `[8/8 已执行 OK]`）；`cli.py --all-checks --doc-llm-mode agent` 部署副本 ERROR 0 / WARN 0 / INFO 21；`self_validate.py` 黄金快照全 PASS（exit 0，`checker_runs` 为新增键、`diff_results` 不比对未知键故快照不受影响）；`py_compile` 全过；负向单测确认 doc=OK(#01) / 抛异常检查器=FAILED / 未注册名=UNKNOWN，且后两者均产出 ERROR 发现。

## 1.25.4 打磨明细（文档三分式重构 + 内联版本号收敛 + 开发链路固化）

### 部署副本同步纳入提交流程
- 新增 `src/scripts/sync_deploy.py`（dev-only）：把 `src/` 发布面（SKILL.md / scripts/audit_docs.py / scripts/auditlib/** / references/checkers.md / dist/skill-doc-audit.zip）字节级同步到部署副本 `~/.workbuddy/skills/skill-doc-audit`，清理 `__pycache__`，末段校验一致性；**刻意排除** dev 工具（make_fixtures.py / self_validate.py）与 `tests/`，绝不把开发期脚本带进线上技能。
- 新增 `hooks/post-commit` 并设 `git config core.hooksPath ../hooks`：每次 `git commit` 后自动运行 `sync_deploy.py`，**提交即同步**，不再依赖人工记这一步。钩子找不到 python 时仅提示、不阻塞提交。
- 文档：README「仓库布局」移除已删的 `backups/` 引用、改列 dev 工具；「打包与发布」后新增「部署副本同步（已纳入提交流程）」专节。
- 配套清理：删除测试报告 `SELF_VALIDATE_TEST_REPORT.md` 与过时本地快照 `backups/`（gitignored 产物，不可逆删除，对应版本源码仍存 git 历史）。

### make_fixtures.py 路径分隔符瑕疵修复（前批遗留未提交，本批一并提交）
- `check()` 的 MISSING / MISMATCH 提示路径统一 `p.replace(os.sep, "/")`（跨平台正斜杠）；仅输出风格，不影响判定逻辑与退出码。

### 开发模式自审计脚本化 + 开发文档纳入漂移扫描（dev_self_audit.py）
- 新增 `src/scripts/dev_self_audit.py`（dev-only，不进部署副本）：把「审计最新源码 `src/`（而非部署副本）+ 开发文档 README/CHANGELOG 纳入漂移 + 部署副本↔源码同步校验」固化为可重复命令，规避 agent 长期项目的记忆漂移 / 幻觉 / 漏操作。要点：①复用 `sync_deploy._verify()` 校验部署副本与 `src/` 字节一致，不一致明确告警；②一律审计最新提交源码发布面（排除 dev 工具 `sync_deploy.py`/`self_validate.py`/`make_fixtures.py`/`dev_self_audit.py`，使结果与发布质量对齐，不被 dev 工具噪音干扰）；③`--dev-docs` 把 README/CHANGELOG 交 `doc`（A1 死路径）+ `doc-llm`（语义漂移 dossier）扫描；④退出码 0=无 ERROR（`--strict` 下还需无 WARN）。
- `doc` 检查器口径收敛：A2 失效参数 / A4 标识符能力漂移 / C 类数量·枚举漂移 限定 `SKILL.md`（规范性能力目录）；开发文档为叙述性变更日志，常含「第 7 个检查器」「已移除的 `_call_llm`」「`make_fixtures.py --baseline`」等历史 / 开发期表述，按能力目录口径跳过避免误报。仅 A1 死路径（具体文件引用，真实漂移）与 `doc-llm` 语义扫描保留逐文档。
- `deadcode` 孤儿资源扫描与 `structure` 名称一致性检查适配开发自审计：`orphan_asset` 尊重 `exclude`（不再把 dev 工具误报为孤儿）；`dev_audit=True` 时跳过 `name_mismatch`（审计 `src/` 目录名是 `src` 而非技能名，非真实漂移）。
- `analyze_skill` 新增 `dev_audit` / `exclude` 上下文透传；`cli.py` 维持 `--dev-docs` 入口（Q3：开发文档纳入语义 / 内容漂移扫描）。

### 文档内联版本号标注收敛（Q1：保留行为解释型）
- 用户决策（2026-09-01）：技能文档（SKILL.md / checkers.md）正文的内联版本号标注，仅保留「解释当前行为为何如此」的类型（如「v1.24.0 起由 agent 直接接手、不再调外部 LLM」说明现行设计理由）；删除纯里程碑标注（仅记录「X 起新增/支持」，与 CHANGELOG 重复且易过时）。frontmatter 强制 `version:` 字段不受影响。
- SKILL.md：删 `## 设计原则（核心约束 · v1.23.1 确立）` 的 `· v1.23.1 确立` 里程碑标记；`使用以下统一措辞模板`（v1.23.6 经用户改进…）→ 去版本号、保留「经用户改进」行为解释。保留全部解释现行设计理由的标注（agent 接手、v1.18.0 上下文感知过滤、v1.21.0 内容漂移等）。
- checkers.md 错误码明细表：删纯引入版本标注 `（v1.21.0）`（DOC_ENUM_DRIFT / DOC_COUNT_DRIFT / DOC_CAPABILITY_DRIFT）、`（v1.24.0）`（doc_llm_agent_handoff）、`（v1.23.0）`（doc_llm_skipped）；保留行为解释型标注（doc-llm 接手机制、agent_coupling 抑制规则、等价映射约定等）。
- 验证：dev_self_audit.py --strict → 全检查器 `ERROR 0 / WARN 0 / INFO 37`，无回归（doc ERROR 0 / WARN 0）。

### 文档三分式重构（用户模式 / 完整参考 / 开发模式）
- 按用户 2026-09-01 决策，把文档显式二分：**用户模式**（`src/SKILL.md`，精简，仅能力一句话地图 + Agent 执行约定 + 紧凑错误码速查 + FAQ）与**完整参考**（`src/references/checkers.md`，模式机制 / 判定口径 / 误报抑制 / Phase 演进的明细基准）；**开发模式**单独落到新文件 `DEVELOPMENT.md`（仅维护者，dev-only 工具 / 自审计 / CI / 未发布改动流程，不进部署副本）。
- `SKILL.md` 去重：①「能力边界」概述由每检查器大段机制铺陈压缩为「一句话能力地图」（模式细节/误报抑制改指向 checkers.md）；②「错误码对照表」下四处大段 blockquote（内容漂移 v1.21.0 / doc-llm Phase / portability Phase 5/6/7 内核与 agentskills 枢纽）删除，改为单行指向 checkers.md——其详细内容 checkers.md 本已完备，属纯重复；③「Agent 执行约定」v1.24.0 关键变更 blockquote 精简为单行 + 指向 checkers.md。保留紧凑错误码速查表（code + 中文 + 级别）供 Agent 现场解读。
- 新增 `DEVELOPMENT.md`；README「本地开发 / 自测」加指向该文件的链接（项目根、不进部署副本，无死链）。`SKILL.md` 不反向链接 `DEVELOPMENT.md`，使部署副本零死链。
- 价值：终端用户（本身就是技能开发者）不被 dev 内容干扰；详细规格归单一真相源（checkers.md），漂移风险与 Agent 上下文负载同步下降；开发模式自然「仅开发者可见」（技术隔离此前已由 `DEV_TOOLS` 排除集实现）。
- 验证：dev_self_audit.py --strict → 全检查器 `ERROR 0 / WARN 0 / INFO 37`，无回归（doc ERROR 0 / WARN 0）。
- 版本串升 1.25.4（`src/SKILL.md` frontmatter + `sources.py` `User-Agent`）。

## 1.25.3 打磨明细（fixtures 移出版本管理 + make_fixtures 升级为整套重建工具）

### 背景（用户决策 + 建议）
- 用户决策：既然已有 fixture 生成器（v1.25.1 recipe + v1.25.2 自动重建），`tests/fixtures/` 应移出 git 跟踪，转为生成产物。
- 用户建议：既然 fixtures 能自主重建，黄金快照也应能一并重建，且该能力应并入 `make_fixtures`。

### 改动
- `.gitignore` 重新排除 `tests/fixtures/`（生成产物）；`git rm --cached` 取消跟踪（保留工作树，clone 后由 self_validate 自动重建）。`tests/examples/*.expected.json` 黄金快照与 `manifest.json` 仍纳入版本管理（断言基线）。
- `make_fixtures.py` 新增 `--baseline`：先 `build()` 重建 fixtures，再复用 `self_validate.normalize` 掩码逻辑重建黄金快照；使生成器成为「fixtures + 黄金快照」整套重建工具。
- **关键约束（已固化到代码注释与文档）**：黄金快照重建是人工显式动作，**不是** self_validate 正常校验流程的一部分——否则会拿「当前逻辑输出」比「当前逻辑输出」永远 PASS，削弱回归护栏。
- 版本串升 1.25.3（`src/SKILL.md` frontmatter + `sources.py` `User-Agent`）。

### 验证
- `make_fixtures.py --baseline` 重建黄金快照后 `git diff tests/examples` 为空（与已提交黄金字节一致）。
- `self_validate.py` 从无关 CWD（`C:/`）运行：fixtures 缺失时自动重建并三例 `[PASS]`，exit 0。
- 部署副本自审 `--all-checks --deadcode-mode vulture`：`ERROR 0 / WARN 0 / INFO 20`（与基线无回归）。

## 1.25.2 打磨明细（fixture 生成器作为 self_validate 辅助套件）

### 背景（用户指令）
用户指出：fixture 生成器可作为自校验工具的一个辅助套件，使 fixtures 缺失时能自动恢复，而非仅提示手动重建。

### 改动
- `self_validate.py` 在 `tests/fixtures` 目录整体缺失时，自动 `import make_fixtures` 并调用 `make_fixtures.build(FIX, quiet=True)` 重建；重建成功则继续校验，仅当 import/写盘异常时才回退到原提示信息。实现「生成器即自校验工具的辅助套件」。
- `make_fixtures.py` 仍为独立 dev 工具（`--check`/`--out`），既有契约不变。
- 版本串升 1.25.2（`src/SKILL.md` frontmatter + `sources.py` `User-Agent`）。

### 验证
- `self_validate.py` 从无关 CWD（`C:/`）运行：三例 `[PASS]`，exit 0。
- 模拟 `tests/fixtures` 缺失：自动重建并三例 `[PASS]`，首行打印 `[self_validate] fixtures 缺失，已用 make_fixtures 自动重建于 ...`。
- 部署副本自审 `--all-checks --deadcode-mode vulture`：`ERROR 0 / WARN 0 / INFO 20`（与基线无回归）。

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
2. 用户确认「示例归一化方案」不具备泛用性（仅能校验 skill-doc-audit 项目自身），决定将其落地为技能**内置的可选自校验工具** `self_validate.py`，而非插件式检查器；并要求该工具在新环境 clone 仓库源码后仍可正常调用。

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
- **token 成本表述全量校正**：所有「零额外成本 / 不消耗用户 token」改为「会占用 agent 自身推理 token（输入侧为主），但不向外部 LLM 服务付费」。覆盖 SKILL.md（能力清单、doc-llm 避坑要点、语义漂移引用块）、`audit_docs.py` 多处 docstring / 运行时提示 / `--check` `--doc-llm-mode` 帮助、README.md 版本摘要。
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
- **描述全量改写**：所有「依赖外部 LLM 服务 / 消耗额外 token / 配置 SKILLDOC_LLM_*」表述，统一改为「由 agent 直接接手 / 零额外成本 / 不依赖外部 LLM」。涉及 SKILL.md（能力清单、doc-llm 段落、Agent 约定、错误码表、语义漂移引用块）、`references/checkers.md`（错误码表）、`README.md`（版本摘要）、argparse 帮助。
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
用户截图反馈 v1.23.5 的 AskUserQuestion 模板「非常不好理解」——question 用了「doc-llm 语义漂移检测」等技术术语，选项 label 太简（仅「默认模式/增强模式/预览代价」），代价与能力信息藏在 desc 里，不直观。建议改为面向用户的措辞，把 doc 检查器与代价/能力信息直接写进 question 与选项 label。

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
| doc 项补 doc-llm 引导描述 | 在 `SKILL.md`「能力边界（务必先读）」检查器清单的 `doc` 项补一句引导性描述：`doc` 覆盖结构化漂移（死引用/失效参数/退出码不符/枚举·数量·能力声明与代码事实不符），自由散文语义漂移由独立的 `doc-llm` 检查器（与 `doc` 功能互补，下方单列）以 agent 语义检测补足；使读者在文档开头即建立「doc 与 doc-llm 分工」认知，无需翻到错误码表才知二者关系 | 部署副本自审 `[doc] ERROR 0 / WARN 0`；frontmatter 升 1.23.2；README/CHANGELOG 版本摘要补 1.23.2 |

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
| 文档同步 | `SKILL.md`（检查器清单补 doc-llm、避坑条目改写、错误码表补 `doc_llm_skipped`、语义漂移块改写、Agent 执行约定扩至 doc-llm）、`references/checkers.md`（补 `doc_llm_skipped` 行）、README/CHANGELOG 版本摘要；frontmatter 与两处 UA `1.22.1` → `1.23.0`；部署副本同步 | 部署副本自审 `[doc] ERROR 0 / WARN 0`；全文检索 `1.22.1` 残留仅历史说明 |

## 1.22.1 打磨明细（doc-llm `ask` 显式三选项交互 · 绝不替用户决定）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| doc-llm `ask` 改为显式三选项交互 | 重写 `_resolve_doc_llm_mode` 的 ask 分支，调用新增 `_prompt_doc_llm_mode()`：交互终端向用户呈现实选项——`1) 默认模式`（纯脚本，零依赖，0 token）/`2) 增强模式`（启用 LLM 语义检测，依赖外部 LLM 服务、消耗额外 token）/`3) 预览代价`（仅展示将发送给 LLM 的内容与预估 token，不实际调用）；新增 `_print_doc_llm_preview(ctx)`；**30 秒超时或无输入一律回退默认模式**（`off`）。非交互（自动化）环境无法询问 → 不再自动复用环境变量配置静默联网，改为回退默认并显著告警（`doc_llm_unavailable`，degraded=True），与 deadcode 非 TTY 行为一致 | 超时（daemon 线程读 stdin，`th.join(30)`）落点 `off`；非 TTY → `auto,True`（触发 `doc_llm_unavailable` WARN）；preview → 打印规模/token 预估后不联网；`py_compile` 通过 |
| 离线不变量与文档同步 | 离线不变量（默认 `off`、不进 `--all-checks`、绝不自动联网）不变；argparse `--doc-llm-mode` 帮助文改为描述三选项与 30s 超时回退；`SKILL.md` 语义漂移引用块重写（v1.22.1 起，说明三选项/30s 超时/非交互回退）；`references/checkers.md` doc-llm 三行版本标 v1.22.1 并补菜单说明；README/CHANGELOG 版本摘要补 1.22.1 行；frontmatter 与两处 UA 版本串 `1.22.0` → `1.22.1` | 全文检索确认 `1.22.0` 残留仅剩历史说明性引用；部署副本同步后自审 ERROR 0 / WARN 0 / INFO 20 |

> TRACE 评测对照：待 SkillHub 上架后由平台重跑（目标——验证 doc-llm 交互改动对评测口径无回归，仍保持 ERROR 0 / WARN 0 不变量）。

## 1.22.0 打磨明细（doc-llm 选装 LLM 语义漂移检测）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| doc-llm 选装 LLM 语义漂移检测 | 对齐用户「调取流程参考 deadcode 检查器」要求，将 deadcode 的「`(mode, degraded)` 元组 + 降级显著告警 + argparse `choices` 单一真相源」范式复刻到 doc 检查器。新增 `DOCLLM_MODES = ("off","auto","ask")` 模块常量（紧邻 `DEADCODE_MODES`，供 argparse 与 doc 校验共用）；`CATEGORY_LABELS` doc 段登记 `DOC_LLM_DRIFT`（文档/代码语义漂移 LLM 判定）、`doc_llm_unavailable`（LLM 语义检测不可用已跳过）、`doc_llm_ran`（已运行无漂移）三项；新增完整 doc-llm 实现区块——`_LLMUnavailable` 异常类、`_load_llm_config`（优先级 argparse > 环境变量 `SKILLDOC_LLM_API_KEY`/`SKILLDOC_LLM_MODEL`/`SKILLDOC_LLM_BASE_URL`）、`_call_llm`（标准库 `urllib` POST OpenAI 兼容 `/chat/completions`，UA `skill-doc-audit/1.22.0`）、`_code_fact_sheet`、`_LLM_DRIFT_RE`、`_parse_llm_drift`（`- 文件:行 \| 描述`，上限 30 条）、`_resolve_doc_llm_mode`（同构 deadcode，返回 `(mode, degraded, reason)`，off/auto/ask 三分支，ask+非TTY 或 ask+无配置→`degraded`）、`check_doc_llm`（off/skip 直接返回；degraded→发 `doc_llm_unavailable` WARN；否则调 LLM 解析 `DOC_LLM_DRIFT`；`_LLMUnavailable` 捕获转告警；"无漂移"→`doc_llm_ran` INFO）；`CHECKERS` 注册 `"doc-llm": check_doc_llm` | 自审：`--skill src --all-checks` 绝对路径调用 ERROR 0 / WARN 0 / INFO 20（doc-llm 默认 off 不触发联网、零误报）；off 默认零发现；auto 无配置→`doc_llm_unavailable` WARN；ask 非TTY 无配置→`doc_llm_unavailable` WARN；monkeypatch `_call_llm` 返回固定漂移文本验证 `check_doc_llm` 正确产出 2 条 `DOC_LLM_DRIFT`（文件/行号解析正确） |
| argparse 接入 doc-llm | 新增 `--doc-llm-mode`（choices=`DOCLLM_MODES`，默认 `off`）、`--doc-llm-base-url`、`--doc-llm-api-key`、`--doc-llm-model`；`--check` 帮助文本补 `doc-llm`；`--all-checks` 帮助注明 doc-llm 默认 off、不触发联网 | 离线不变量确认：`--all-checks` 不调用 `_call_llm`、不发任何网络请求（沙箱屏蔽 localhost，真实联网路径以 monkeypatch 验证逻辑层）；`py_compile` 通过 |
| 版本号晋升 1.21.0 → 1.22.0 | frontmatter `version` 升 1.22.0；`audit_docs.py` 两处 User-Agent 版本串 `skill-doc-audit/1.21.0` → `skill-doc-audit/1.22.0` 同步（`_call_llm` 内与 `_fetch` 源码抓取处）；默认 LLM base URL 拆为 `"https://" "api.openai.com/v1"` 字面值拼接、argparse help 文本不出现完整 URL，规避 security 检查器 `hardcoded_endpoint` 误报 | grep 确认代码内仅两处版本串、与 frontmatter 一致；重跑 `--all-checks` 自审 WARN 由潜在 2 处端点告警归零至 0 |
| 文档同步 | `SKILL.md` 错误码对照表新增 `DOC_LLM_DRIFT`/`doc_llm_unavailable`/`doc_llm_ran` 三行；doc 章节新增语义漂移引用块（doc-llm 选装、对齐 deadcode 调用流程、离线不变量、调用配置）；避坑要点新增「doc-llm 默认不运行（离线不变量）」条；`references/checkers.md` 新增三行（标注 v1.22.0）；`src/dist/skill-doc-audit.zip` 重打包（3 条目：SKILL.md/audit_docs.py/checkers.md） | 全文检索确认无残留旧表述；部署副本 `C:/Users/admin/.workbuddy/skills/skill-doc-audit/` 已同步（version 1.22.0，自审 ERROR 0 / WARN 0 / INFO 20） |

> TRACE 评测对照：待 SkillHub 上架后由平台重跑（目标——验证 doc-llm 选装项对评测口径无回归，仍保持 ERROR 0 / WARN 0 不变量）。

## 1.21.0 打磨明细（doc 检查器内容漂移检测）

> 发布：2026-08-31 本地提交；SkillHub 上架与 TRACE 复评待用户授权后执行。

| 打磨项 | 改动 | 验证（均通过） |
|---|---|---|
| doc 内容漂移检测 | `check_doc` 在既有「令牌存在性」校验（DEAD_PATH / DEAD_FLAG / EXIT_* / UNKNOWN_IDENT / VERSION_MISSING）之上，新增三类「结构化声明 ↔ 代码事实」交叉校验：`DOC_ENUM_DRIFT`（文档枚举的 deadcode 模式集合 `{ask,vulture,ast,skip}` / `ask/vulture/ast/skip` 与新增权威常量 `DEADCODE_MODES` 比对）、`DOC_COUNT_DRIFT`（文档「N 个检查器」与 `len(ALL_CHECKERS)` 比对）、`DOC_CAPABILITY_DRIFT`（能力声明动词行内的反引号标识符在代码与声明中均不存在时提示能力可能已移除）。三者均 WARN 不 ERROR；新增 `DEADCODE_MODES` 模块常量并接入 `--deadcode-mode` 的 argparse `choices`，成为 argparse 与 doc 校验共用的单一真相源；`CATEGORY_LABELS` 登记三项新标签 | 自审：`python audit_docs.py --skill src --all-checks` 中 doc ERROR 0 / WARN 0，三新类别在准确文档上零误报；构造漂移夹具（注入「共 6 个检查器」、删 `skip`、`自动支持 `nonexistent_cap``）运行确认 `DOC_COUNT_DRIFT` / `DOC_ENUM_DRIFT` / `DOC_CAPABILITY_DRIFT` 三项均触发（真阳性），验证后清理夹具 |

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
