# doc-llm 自动降级的隐性问题 · 详细分析与修复

> 配套提交：`src/scripts/auditlib/core.py`、`report.py`、`checkers/doc_llm.py`、`SKILL.md`、`references/checkers.md`
> 版本：skill-doc-audit 1.34.2 → 1.34.3（补丁级，检查器行为修正）
> 复现证据：`audit_all_log.txt`（修复前，全量体检默认 ask 模式）、`repro_noninteractive.txt`（修复后非交互复现）

---

## 一、问题现象（来自全量体检实测）

在 `skill-doc-audit --all --all-checks` 默认（ask）模式的批量审计里，`audit_all_log.txt` 暴露了 doc-llm 的异常表现：

```
[doc-llm] 语义漂移检测（Vector 2）如何运行？
[doc-llm] 超时/无输入，已自动采用默认模式（不调用 LLM）。
[doc-llm] 已采用 off 模式：关闭（跳过 doc-llm 语义漂移检测）
  [#08] [doc-llm] ✓ 已执行   ERROR 0 / WARN 0 / INFO 0
  检查器执行回执: ✓doc ✓structure … ✓doc-llm ✓examples  [9/9 已执行 OK]
```

**表面看一切正常**：doc-llm 标记 `✓ 已执行`、回执 `9/9 已执行 OK`、零发现。但语义漂移检测（Vector 2）**根本没跑**——这正是 `checkers.md:20` 立下的"杜绝 doc-llm 类「静默落空却显示通过」"红线被突破。

---

## 二、根因（代码级，四个叠加的隐性问题）

### 隐性问题 1：伪交互判定（核心根因）
`core.py:429` 的 `is_interactive()` 只查 `sys.stdin.isatty()`：

```python
def is_interactive():
    return sys.stdin.isatty()
```

Agent 后台任务 / CI 把 **stdout/stderr 重定向到日志文件**，但 **stdin 仍可能是 TTY**。`is_interactive()` 因此误判为"可交互" → 进入 `_prompt_doc_llm_mode` 弹菜单。菜单写到 stderr（不可见流），无人键入。

### 隐性问题 2：30 秒静默阻塞
`prompt_choice`（`core.py:434`）用后台线程 `th.join(timeout)` 等 30s。每个技能卡 30s；批量审计 N 个技能 = **30s × N 白白等待**（全量体检实测整批耗时大部分耗在此）。

### 隐性问题 3：超时降级被伪装成"用户决策"
`doc_llm.py:52-56` 的超时分支：

```python
choice = _prompt_doc_llm_mode(timeout=30)
if choice == "agent":
    return "agent", False, None
return "off", False, None   # ← degraded=False！视为"用户明确放弃"
```

超时返回 `("off", False, None)`，`degraded=False`。于是 `check_doc_llm`（`doc_llm.py:182`）走到 `if mode == "off":` 且 `degraded` 为假 → **直接 `return findings`（空）**，无任何 finding，连 INFO 都不记。即：无人决策，却被当成"用户主动放弃"。

### 隐性问题 4：回执误导
`report.py:25` 的回执按"检查器函数是否执行"判 `✓/✗`：

```python
mark = "✓" if c["status"] == "OK" else "✗"
```

跳过的 doc-llm 函数**确实执行了**（只是决定跳过），`status="OK"` → 显示 `✓doc-llm`。这与真正 agent 接手（也标 `✓`、0 发现）**视觉上无法区分**，形成"静默落空却显示通过"。

### 附带：文档漂移
`SKILL.md:33`、`references/checkers.md:50` 写着"非交互环境记 INFO `doc_llm_skipped`"，但代码实际走 `ask_undecided`（ERROR，见 `doc_llm.py:188`），且因上述根因该路径此前**根本不可达**。文档与代码双重失准。

---

## 三、为何此前的观察报告误判了这一点

我在此前的 `audit_all_observation_report.md` 中称 doc-llm"连 `doc_llm_skipped` INFO 都不记、空转"——这表述不准确：

1. 代码**从未**发 `doc_llm_skipped`，真正该触发的是 `ask_undecided`（ERROR）；
2. 因**隐性问题 1（伪交互）**，那条本应触发的 `ask_undecided` 硬失败路径不可达，实际落点是**隐性问题 3 的超时伪装 silent-off**。

两层叠加，使非交互批量审计"表面全绿、实为空转"。本分析以 `audit_all_log.txt`（修复前）与 `repro_noninteractive.txt`（修复后）为据，更正此前报告的误判。

---

## 四、修复

### Fix A — 鲁棒的可交互判定（根因）
`core.py:429` 改为要求 **stdin 与 stderr 均为 TTY**：

```python
def is_interactive():
    return sys.stdin.isatty() and sys.stderr.isatty()
```

菜单可见（stderr 是 TTY）才算可交互；否则按非交互处理，直接走 ask 非交互降级 / 硬失败路径，**不再 30s 静默超时**。deadcode / examples 共用此函数，一并受益。

### Fix B — 回执诚实化（杜绝"静默落空却显示通过"）
`report.py` 对 `mode == "off"`（跳过）的检查器：
- 回执标记由 `✓` 改为 `⚠`，并追加 `⚠ 跳过(未实际运行): <name>`；
- 逐检查器块追加注解：`该检查器本次未实际运行（mode=off（非交互降级））：…`；
- `doc_llm.py:167` 把 `degraded` 写入 `ctx["_meta"]`，使报告能区分"非交互降级"与"显式 off"。

### Fix C — 分类收敛 + 文档收口
- doc-llm 非交互降级统一走 `ask_undecided`（ERROR，与 deadcode/examples 层级3 一致）；
- `core.py` 为 `ask_undecided` 补中文标签（三者共用，显示一致）；
- 删除已死的 `doc_llm_skipped` 描述（`core.py:187`），修正 `SKILL.md:33`、`:345`、`references/checkers.md:50`、`:271` 的文档漂移。

---

## 五、验证

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 非交互 `--all-checks`（默认 ask） | 30s×N 静默超时 → `✓doc-llm` 空转 | **731ms** 返回、`EXIT=1`、`⚠doc-llm … ⚠ 跳过(未实际运行): doc-llm` + "需用户决策"块 |
| 显式 `--doc-llm-mode off` | `✓doc-llm` 空转 | `⚠doc-llm` 跳过、**无 doc-llm ERROR**（诚实标注未运行） |
| 显式 `--doc-llm-mode agent` | `✓doc-llm` + handoff | `✓doc-llm` + `AGENT_TAKEOVER`（不变） |
| 交互终端（真人） | 弹菜单选 | 弹菜单选（不变，体验保留） |

回归门禁：
- `self_validate.py`：全 PASS（黄金快照未受影响，确定性检查器不含 doc-llm/deadcode）。
- `dev_self_audit.py --strict`：**EXIT 0，ERROR 0 / WARN 0 / INFO 39**（doc-llm 走 agent 模式，回执 `✓doc-llm`）。

副作用（预期且良性）：examples / deadcode 同样不再 30s 静默超时，非交互统一 `ask_undecided` 硬失败。故推荐 CI 命令须显式 `--examples-mode static --examples-consent`（本项目 `dev_market_bench.py` 与 `--strict` 重跑均已采用）。

---

## 六、注意事项 / 后续建议

- **examples / deadcode 的 SKILL.md 段仍写"非交互回退 static/ast 并发 INFO"**，与代码硬失败（`ask_undecided`）不一致——同源根因，未在本变更中改其文档以免范围扩散。已加 `ask_undecided` 中文标签使三者回执显示一致。建议后续同源收口其文档表述。
- 本变更为 skill-doc-audit **自身**的检查器行为修正；上架 SkillHub 仍须经你显式授权（agent-todo 第 4 条 `[必须]` 阻断）。
