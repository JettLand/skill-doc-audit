# 可行性研究：示例输出归一化方案（Vector 3 核心子问题）

> 研究目标：在立项「示例输出回归检查器（--check examples）」之前，先评估其中最棘手的**示例归一化**子问题是否可行——即如何让文档示例的真实输出变得可比对、可 diff。
> 结论：**可行，且成本低于预期**（实证依据见第二节）。

## 一、结论（先行）
**判定：GO（高可行性）。**
- 工具输出**确定性已实证**：对同一 fixture 连续两次 `--json`，输出**逐字节一致**（3 个 fixture 全部通过）。
- 归一化所需掩盖的易变字段**仅 1 个**：顶层 `skill`（绝对工作区路径）。finding 内部的 `file` 已是**相对路径**，无需处理；`message`/`category_cn` 为稳定字符串，`line` 确定（可为 null）。
- 已有**固定 fixture 底座**（`tests/fixtures/` 下 4 个技能）天然作示例锚点，规避「对易变生产代码跑示例」的难题。
- 全部示例命令均为 `audit_docs.py` 只读扫描，**无联网、无副作用**，沙箱风险低。

## 二、实证证据（基于真实代码，非推测）
1. **示例命令性质**：SKILL.md 共 12 个围栏代码块，全部为 `python scripts/audit_docs.py ...` 只读调用（另含 `python -c "import vulture"` 探测、以及恢复备份的 `cp` 示例，均非写入式审计）。
2. **结构化输出已具备**：`audit_docs.py` 有 `--json`（`build_json()`），输出顶层 dict 含 `skill / version / summary{error,warn,info,pass} / findings / checkers / ...`，findings 含 `checker/category/severity/category_cn/file/line/message/suggestion`。这正是机读比对的载体。
3. **确定性已验证**（实跑，连跑两次 diff）：
   - `tests/fixtures/multifile` → 完全一致（1 发现；summary error1/warn1/info1）
   - `tests/fixtures/tricky-clean` → 完全一致（info1）
   - `tests/fixtures/dirty-skill` → 完全一致（29 发现；summary error12/warn15/info2）
   → 输出**无时间戳/随机/进程相关污染**（datetime 仅用于 `--backup` 文件名，默认不触发）。
4. **易变字段实测仅 1 处**：`skill` 为绝对路径（如 `D:/Agent Work/skill-doc-audit技能项目管理/tests/fixtures/dirty-skill`）。findings 的 `file` 字段为相对路径（实测 `SKILL.md`），`line` 确定，`message`/`category_cn` 稳定。

## 三、归一化方案（核心子问题）
对 `--json` 结果施加**极轻量**归一化后即可比对，无需 NLP：

| 规则 | 做法 | 必要性 |
|---|---|---|
| N1 路径掩码 | 正则将顶层 `skill` 绝对路径替换为 `<ROOT>` 令牌 | **必须**（唯一实测易变项）|
| N2 行号可选掩码 | 固定 fixture 下行号本确定，可保留做精确断言；为抗 trivial 编辑亦可掩码 | 可选 |
| N3 INFO 计数 | 锚定 fixture 后 INFO 计数稳定，无需掩码 | 视锚点而定 |
| N4 语义化按键 | 以 (checker, category, severity, message 子串) 为键比对，而非整段文本 | 推荐（抗文案微调）|

**比对策略（可并存）**：
- **A. 黄金快照**：在 `tests/examples/` 提交 `<name>.expected.json`（已归一化），实跑后 diff。稳健精确。
- **B. 文档内联断言**：示例围栏标注 ` ```sh {example expected=ERROR0 WARN1 INFO1} `，仅校验 summary 计数。文档与示例自验证、零额外文件。

## 四、安全与沙箱
- **白名单执行**：示例运行器**仅**执行 `python .../audit_docs.py` 针对 `tests/fixtures/*`（或白名单只读目标），**绝不**执行文档任意 shell，杜绝注入。
- **离线不变量**：`audit_docs.py` 默认不联网（仅 `--source url` 走网，示例不用）；CI 可禁网运行。
- **只读**：工具本身是只读扫描器；示例不触发 `--backup` 写操作。
- **默认关闭**：`--check examples` 默认 off、显式开启，契合「绝不替用户决定 / 离线优先」原则。

## 五、风险与缓解
| 风险 | 说明 | 缓解 |
|---|---|---|
| R1 vulture 版本差异 | deadcode 计数可能随 vulture 版本浮动 | CI 固定 vulture 版本；或为含死代码 fixture 掩码 deadcode INFO；升级 vulture 时重基线黄金 |
| R2 黄金维护成本 | 工具合法改输出时需更新黄金 | 本就是回归信号本意，刻意更新即可，按「快照测试」管理 |
| R3 范围蔓延 | 泛化到任意 shell 示例 | 限定 Vector 3 仅覆盖 `audit_docs.py` 对 fixture 的调用 |
| R4 doc-llm 不可确定回归 | agent 语义比对非确定 | doc-llm 示例排除出示例回归（由 Vector 2 覆盖）|

## 六、建议与下一步
- **建议 GO**，落地为 `examples` 检查器（与 doc/structure 同构），纳入 `--all-checks` 但默认 off。
- 最小实现：① `tests/examples/manifest.json`（cmd + fixture + expected）；② `--check examples` 运行器（白名单执行 → 归一化 → diff）；③ 以现有 3 个 fixture 产出 2–3 条黄金示例；④ SKILL.md/CHANGELOG 记录为规划版本（如 v1.25.0 路线图）。
- **不阻塞当前发布**；作为独立后续版本迭代。
