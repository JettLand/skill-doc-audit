# 研究：抽取 trace-selfcheck 静态文档检查能力为 skill-doc-audit 的 doc-llm 升级项

> 研究阶段产出（task #69）。**先不实施**，仅做能力映射、差距分析与抽取可行性结论。
> 证据来源：`~/.workbuddy/skills/trace-selfcheck/scripts/trace_eval.py`、`references/trace_criteria.md`；
> 对照：`skill-doc-audit` 的 `auditlib/checkers/doc.py`、`doc_llm.py`、`security.py`、`deps.py`、`portability.py`、`structure.py`（代码事实，非推断）。

---

## 一、trace-selfcheck 静态能力清单 ↔ TRACE 子项映射

trace_eval.py 的 `analyze()` 一次性统计以下机器判定指标，`derive_static_scores()` 按 rubric 阈值派生 15 子项的"静态代理分"（非 AI 语义分）。能力清单如下：

| TRACE 子项 | 维度 | trace_eval.py 静态能力（函数/正则/常量） | 判定性质 |
|---|---|---|---|
| T1 国内适配性 | T | `chinese_ratio()`（CJK 占比）、`DOMESTIC_RE`（国内关键词命中）、`INFO_PATTERNS→foreign_endpoint`（境外端点扫描） | 统计 + INFO 级扫描 |
| T2 安全性扫描（红线） | T | `scan_redline()`：`RED_PATTERNS`（`hardcoded_secret`/`path_traversal`/`destructive_wildcard`，P0/P1，仅代码上下文判） | 确定性 + 红线 |
| R1 异常处理 | R | `ERROR_HANDLE_RE` 关键词命中计数 | 关键词计数（弱代理） |
| R2 功能完整性 | R | `count_headings()`、`count_code_blocks()` | 结构计数 |
| R3 运行稳定性 | R | `STABILITY_RE` 关键词命中计数 | 关键词计数（弱代理） |
| A1 能力边界定义 | A | `BOUNDARY_RE`（✅擅长/⚠️需补充/❌超范围 三类标记计数） | 标记计数 |
| A2 触发方式 | A | `OPENING_RE`（正例/反例/用户说/触发示例等）命中计数 | 关键词计数 |
| C1 反模式与 FAQ | C | `FAQ_HEAD_RE`+`QUESTION_RE`（FAQ 节+问题数）、`ANTI_HEAD_RE`（反模式节+条目数） | 结构探测 + 计数 |
| C2 文档质量 | C | `count_code_blocks()` | 结构计数 |
| C3 渐进式披露 | C | `PROGRESSIVE_RE`（快速开始/功能详情/深度参考 三层）命中计数 | 关键词计数 |
| C4 结构清晰 | C | `c_structure`（ref_files/script_files/headings 枚举） | 文件枚举 |
| E1 输出准确性 | E | `t_security_redline`（红线干净）、`REPORT_LABEL_RE`（中文标签/修复建议/扣分项等命中计数） | 红线 + 关键词 |
| E2 内容完整度 | E | `check_completeness()`：`_third_party_imports()`（第三方 import）+ 声明核对（requirements/pyproject/SKILL.md）；`SHELL_INVOKE_RE`/`OS_SHELL_CMD_RE`/`HARDSEP_RE`（OS 专属 shell、硬编码分隔符）；`runtime_declared` | 确定性依赖/可移植扫描 |
| E3 创造力与增值 | E | 无静态信号（`derive_static_scores` 返回 `None`，AI 语义判定） | N/A |
| E4 开箱即用度 | E | `QUICKSTART_RE`/`SINGLE_CMD_RE` 命中计数 | 关键词计数 |
| 基础项 | — | `parse_frontmatter()`（has_frontmatter/has_version）、`count_tables()`、`PRIVACY_KW`（隐私说明）、`doc_lines` | 元信息 |

**核心结论**：trace 的静态能力分三类——①**确定性扫描**（红线、第三方依赖、跨平台 shell/分隔符、frontmatter、FAQ/反模式节探测）；②**结构计数**（标题/代码块/表格数、文件枚举）；③**关键词计数质量代理**（R1/R2/R3/A1/A2/C2/C3/E1/E4，靠正则命中数近似"质量门槛"）。②③ 本质是 TRACE 评测体系的"质量门槛"代理，非文档↔代码一致性。

---

## 二、与 skill-doc-audit 现有检查器的重叠 / 互补分析

### 2.1 已被 skill-doc-audit 覆盖（重复造轮子，不应再抽）

| trace 能力 | 对应 skill-doc-audit 检查器 | 说明 |
|---|---|---|
| T2 红线 `hardcoded_secret`/`path_traversal`/`destructive_wildcard` | **security** 检查器 | 同属安全红线检测；skill-doc-audit 的 security 已实现同类扫描（含注释/围栏上下文豁免口径）。`E1.redline_clean` 亦同源。 |
| E2 `deps_third_party`/`deps_undeclared` | **deps** 检查器 | 第三方依赖 vs 声明完整性，deps 检查器已覆盖。 |
| E2 `os_specific_shell`/`hardcoded_separators`/`runtime_declared` | **portability** 检查器 | 跨平台可移植性，portability 检查器已覆盖（且更细到 Plan B 的 OS/Agent 正交维度）。 |
| C4 `ref_files`/`script_files`/`headings` | **structure** 检查器 | 文件组织/结构，structure 检查器已覆盖。 |
| `has_version` | **doc** 检查器 `VERSION_MISSING`（A5） | 版本声明缺失报错，doc 已覆盖。 |
| `has_frontmatter` | 隐含（doc/structure 解析 frontmatter） | 无独立 ERROR，但解析已依赖。 |

> ⚠️ **关键提醒**：trace 与 skill-doc-audit 在 security / deps / portability / structure / version 五处**高度重叠**。若再从 trace 抽这些，会产生双份维护 + 口径漂移风险。正确做法是**以 skill-doc-audit 现有检查器为单一真相源**，trace 侧保持独立（它是 SkillHub 外部评测体系）。

### 2.2 与 doc-llm dossier 的关系（互补，非重叠）

doc-llm 当前 dossier（`doc_llm.py::_write_doc_llm_dossier`）只做一件事：**文档↔代码一致性语义比对**——给 agent 代码事实清单（顶层定义/CLI 参数/退出码/常量）+ 正向覆盖缺口（代码有文档缺），让 agent 判"文档声称的能力/默认值/行为/数量/集合是否与代码事实冲突"。

trace 的静态能力侧重的"内容完整性/质量门槛"（R/A/C/E 的大部分）是 doc-llm **目前完全没有**的维度：
- doc-llm 不知道"FAQ 是否齐全""能力边界是否用 ✅/⚠️/❌ 显式界定""是否有渐进式分层""示例是否丰富""异常处理是否写明位置+修法"。
- 这些是"文档写得好不好"而非"文档与代码是否一致"，与 doc-llm 的 Vector 2 语义漂移互补。

**互补定位**：doc-llm 负责"一致"，trace 静态能力负责"完整/质量"。抽取目标是把 trace 中**确定性可机判的"完整性"信号**补进 doc 检查器，把**需语义阅读的"质量"信号**作为 doc-llm dossier 的新比对要点。

---

## 三、抽取候选分类

### 3.1 确定性规则 → 落 `doc` 检查器（零依赖、可静态判定）

| 候选能力 | 来自 trace | 落点建议 | 严重度 | 备注 |
|---|---|---|---|---|
| FAQ 章节探测 + 问题数门槛 | C1 | `doc` 新增 `DOC_FAQ_COVERAGE`：检测 SKILL.md 是否含 FAQ 节（头正则）+ 问题数；缺失或 `<4` 条 → WARN | WARN/INFO | 纯结构探测，确定性强 |
| 反模式/误区章节探测 + 条目数 | C1 | `doc` 新增 `DOC_ANTIPATTERN_COVERAGE`：含反模式节 + 条目数；缺失 → INFO | INFO | 新手易错提示，属质量门槛 |
| 能力边界标记显式界定 | A1 | `doc` 新增 `DOC_BOUNDARY_MARKERS`：扫描 ✅擅长/⚠️需补充/❌超范围 三类标记是否齐全（0 类 → INFO 提示"未界定能力边界"） | INFO | 与 doc 现有 DOC_CAPABILITY_DRIFT（声称能力是否存在代码）**正交互补**：drift 查"存在性"，boundary 查"是否显式分类" |
| 隐私/合规说明 | `PRIVACY_KW` | `doc` 新增 `DOC_PRIVACY_NOTE`：涉及敏感数据/上传的技能缺少隐私说明 → INFO | INFO | 良好实践信号，非阻断 |
| 表格/代码块丰富度（作为完整性提示） | `count_tables`/`count_code_blocks` | 可选：doc 把 `tables`/`code_blocks` 计数作为 INFO 输出（供 doc-llm dossier 使用），不直接报错 | INFO | 弱代理，仅喂 dossier |

> 以上均可**纯脚本、零 token、零网络**实现，契合 skill-doc-audit "默认零依赖"铁律。但注意：FAQ/反模式/边界标记属于"文档写作质量门槛"，对**第三方技能**可能不适用（不同作者的文档风格），应参考 doc 检查器既有的 `ALL_CHECKERS in blob` 自框架判定——仅对**审计自家技能**（blob 含 ALL_CHECKERS）做强校验，第三方技能降 INFO 或不报，避免误报。

### 3.2 需 agent 语义判读 → 落 `doc-llm` dossier（新增比对要点）

| 候选能力 | 来自 trace | doc-llm 处置 |
|---|---|---|
| R1 异常处理质量 | R1 | dossier 新增比对要点："异常处理是否写明 文件:行:问题:修法"，由 agent 语义判 |
| R2/R3 功能完整/运行稳定 | R2/R3 | dossier 要点："主要场景是否全覆盖、有无输出格式说明/兜底/备份说明"，agent 语义判 |
| A2 触发方式正/反例 | A2 | dossier 要点："是否有正例+反例对照说明何时用" |
| C2 文档质量 | C2 | dossier 要点："命令/错误说明是否清楚、有无完整输出示例" |
| C3 渐进式披露 | C3 | dossier 要点："是否有快速开始→进阶的分层" |
| E1 输出准确性 | E1 | dossier 要点："每条问题是否有中文标签+修复建议、误报是否过多" |
| E4 开箱即用度 | E4 | dossier 要点："常用场景是否一条命令/一键完成" |
| T1 国内适配性 | T1 | dossier 要点："是否贴合国内用户、是否依赖境外网络"，agent 语义判（属外部评测视角，可选） |

> doc-llm 的抽取**不改检查器代码逻辑**，只是**扩展 dossier 的比对要点模板**（目前的"比对要点"只有 2 条，集中在一致性；新增"完整性/质量"要点即完成）。这是最低成本、零风险、纯增量改动。

### 3.3 不抽取（保持独立，原因已述）

security 红线、deps 第三方依赖、portability 跨平台、structure 文件结构、version 声明——**已全部在 skill-doc-audit 现有检查器中**，重复抽取会双份维护 + 口径漂移。TRACE 是 SkillHub 外部上架评测体系，其 15 子项总分应由 trace-selfcheck 独立承担（它是 `agent_created` 的专属自评 skill）。

---

## 四、可行性结论与推荐抽取范围

### 4.1 结论

1. **trace 的"确定性扫描 + 结构计数"中，约 5 项与 skill-doc-audit 现有检查器高度重叠**（security/deps/portability/structure/version）——**不抽取**，以现有检查器为单一真相源。
2. **trace 的"质量门槛代理"（R/A/C/E 关键词计数 + FAQ/反模式/边界标记）是 skill-doc-audit 当前空白**，与 doc-llm 的"一致性"语义互补，是值得抽取的核心价值。
3. **抽取成本极低、风险可控**：确定性项（FAQ/反模式/边界/隐私标记）纯脚本落 `doc`；语义项只需扩展 doc-llm dossier 模板，不改执行逻辑。
4. **架构边界必须守住**：skill-doc-audit 定位"文档↔代码一致性 + 静态健康"，不应变成"上架质量评分器"。TRACE 的 15 子项**总分/评级**仍归 trace-selfcheck；skill-doc-audit 只吸收"确定性完整性信号"+"dossier 比对要点"，不引入 5.0 分制评分。

### 4.2 推荐抽取范围（优先级）

| 优先级 | 抽取项 | 落点 | 严重度 | 实施成本 |
|---|---|---|---|---|
| P0 | doc-llm dossier 比对要点扩展（R1/R2/R3/A2/C2/C3/E1/E4 + 可选 T1） | `doc_llm.py::_write_doc_llm_dossier` | INFO（agent 语义） | 低（纯模板增量） |
| P1 | FAQ 章节 + 问题数门槛 | `doc.py` `DOC_FAQ_COVERAGE` | WARN/INFO（自框架强校验，第三方降 INFO） | 低（纯静态） |
| P1 | 能力边界标记显式界定 | `doc.py` `DOC_BOUNDARY_MARKERS` | INFO | 低 |
| P2 | 反模式/误区章节探测 | `doc.py` `DOC_ANTIPATTERN_COVERAGE` | INFO | 低 |
| P2 | 隐私/合规说明提示 | `doc.py` `DOC_PRIVACY_NOTE` | INFO | 低 |
| 不抽 | security/deps/portability/structure/version 红线类 | — | — | 重复，跳过 |

### 4.3 实施前置建议（若后续落地）

- 所有 doc 检查器新增项遵循既有 `ALL_CHECKERS in blob` 自框架判定，避免对第三方技能误报（与 C3 正向覆盖缺口同口径）。
- 抽取后须跑 `dev_self_audit --strict`（次/主版本口径）+ `self_validate` 确认不引入 WARN/ERROR 漂移；版本号按约定升版 + CHANGELOG 收口（README 不记版本表，见 v1.33.1 约定）。
- 建议先落地 P0（dossier 模板扩展，零风险），再视 P1/P2 反馈决定是否进 `doc` 检查器。

---

## 附：交叉印证要点（供实施时复用，避免重造）

- trace 的 `scan_redline` 与 skill-doc-audit `security` 的"硬编码密钥仅代码上下文、注释/围栏跳过"口径一致，可作为 security 检查器口径参考。
- trace 的 `_third_party_imports`（stdlib 白名单 + 同目录内部模块豁免）与 deps 检查的"第三方依赖识别"口径一致。
- trace 的 `SHELL_INVOKE_RE`/`OS_SHELL_CMD_RE`/`HARDSEP_RE` 与 portability 的 OS/Agent 正交维度一致。
- doc-llm 既有 `compute_capability_gaps` 与 doc 的 `DOC_CAPABILITY_MISSING` 已共用，新增抽取项应同样复用 core.py 单一真相源（如 FAQ 头正则、边界标记正则），避免散落多份。

---

## 五、P1/P2 谨慎评估（2026-09-03，落地 P0 后复盘）

> 用户要求「谨慎评估 P1/P2 扩展」——本节为评估结论，**未实施**。

### 5.1 可行性复核（基于真实代码）

- **自框架门控确实存在**：`doc.py:185` 有 `if doc_name == "SKILL.md" and "ALL_CHECKERS" in blob:` 判定，仅对「自家技能」（blob 含框架标记）做强校验，第三方技能整段不跑——可彻底杜绝第三方误报。但当前该门控**只包裹 `DOC_CAPABILITY_MISSING`（C3 正向覆盖）一处**。
- **P1/P2 落点可行**：FAQ/边界/反模式/隐私 四项确定性检查，只要写在 `ALL_CHECKERS in blob` 门控内（或并列同条件门控），即可复用语界机制、零第三方误报。

### 5.2 风险点（暂缓主因）

1. **严重度策略冲突**：研究初稿给 `DOC_FAQ_COVERAGE` 定 WARN（缺失或 `<4` 条）。但门控只对「自家技能」生效——若用户自有技能并非都有 FAQ≥4，WARN 会直接打破用户「WARN 0」干净基线，引发噪音式告警。正确做法应降为 **INFO（质量信号，非缺陷）**，但这与研究初稿口径不一致，需先与用户对齐严重度策略。
2. **边界标记正则脆弱**：✅/⚠️/❌ 存在多形态（✔ 与 ✅、⚠ 与 ⚠️、全角/半角、表格行 vs 行内），若只配单一正则会漏判/误判，产出不可信的 INFO 噪音。需先做健壮性多形态匹配器。
3. **FAQ 探测启发式偏差**：`FAQ_HEAD_RE`+`QUESTION_RE` 对「常见问题 / Q&A / 疑问解答」等头变体、以及问题行（以 `?`/`？`/编号 Q 开头）的识别是启发式，漏检会把「有 FAQ 实无名」误报为缺失。
4. **职责边界扩张**：doc 检查器法定职责是「文档↔代码一致性 + 静态健康」；FAQ/反模式/边界/隐私属「写作质量门槛」，与一致性正交。批量加入会把 doc 检查器推向「质量评分器」，触碰研究结论明令守住的架构边界（不引入 5.0 分制 / 不变成上架质量评分器）。须明确标注为 INFO 级「质量信号」而非缺陷。

### 5.3 结论与建议

- **P0 已交付互补价值**：doc-llm dossier 现覆盖「完整性/质量门槛」10 要点（语义判读、零误报风险），已实质吸收 TRACE 互补维度。
- **P1/P2 暂缓落地**，理由：边际收益低于实现/维护风险——确定性项只能给自家技能发 INFO（第三方被门控跳过），而 INFO 噪音 + 正则健壮性是实打实成本；且需先与用户对齐「自家技能质量信号」的严重度策略与预期基线。
- **若后续仍要落地**，前置条件：① 写在 `ALL_CHECKERS in blob` 门控内（第三方静默）；② 严重度一律 INFO；③ 先做 ✅/⚠️/❌ 与 FAQ 头/问题行的多形态健壮匹配器；④ 在用户自有技能上跑回归，确认无意外 INFO 洪泛后再升版收口。
---

## 六、P1/P2 落地价值与必要性结论（2026-09-03 复盘）

> 用户要求「研究总结 P1/P2 是否有落地的价值和必要」。本节为价值判断，**未实施**，与第五章风险评估衔接。

### 6.1 价值（value）

- P1/P2 四类确定性检查（FAQ 章节/能力边界标记/反模式节/隐私说明）= 给「自家技能」的纯静态**写作质量自检**，零 token、零网络、确定性可复现。
- 但对**第三方技能**被 `doc.py:185` 的 `ALL_CHECKERS in blob` 门控**完全跳过** → 对 skill-doc-audit 的核心使命（审计第三方技能文档↔代码一致性）**不增加任何新检测能力**。
- **P0 已吸收互补价值**：doc-llm dossier 现 12 要点（含 R1/R2/R3/A2/C2/C3/E1/E4/T1 语义判读），覆盖**全部技能（含第三方）**的「完整性/质量门槛」维度。P1/P2 只是把 dossier 让 agent 看的要点机械化为静态检查，且只作用于自家技能——属 dossier 的**弱静态替代**。

### 6.2 必要性（necessity）

- **低**。P0 已实质交付「一致性 + 完整性/质量门槛」双维度；P1/P2 不引入新能力，仅把"自家技能写作自检"从 agent 语义判读降为脚本 INFO 提示。
- **边际收益 << 实现/维护成本**：自家技能写作自检的便利性（边际收益），相比正则健壮性投入 + INFO 噪音治理 + 严重度策略对齐（成本），不成比例。

### 6.3 风险（已确认，见 §5.2）

1. 严重度冲突：FAQ<4 若定 WARN 直接打破用户「WARN 0」自家基线 → 须降 INFO，口径与研究初稿不一致。
2. 边界标记正则脆弱：✅/⚠️/❌ 多形态（✔/⚠/全半角/表格行 vs 行内）易漏判误判。
3. FAQ 头/问题行启发式偏差 → 误报"缺失"。
4. 职责边界扩张：把 doc 检查器推向「质量评分器」，触碰「不引入 5.0 分制」架构边界。

### 6.4 结论

- **暂缓落地**（与 §5.3 一致）：非必要、价值有限。P0 已交付互补维度，P1/P2 对发布产品无新检测能力、仅自家技能 INFO 便利。
- **若后续仍要落地**，定位为 INFO 级「自家技能写作质量自检」，前置条件：① 写在 `ALL_CHECKERS in blob` 门控内（第三方静默）；② 严重度一律 INFO；③ 先做 ✅/⚠️/❌ 与 FAQ 头/问题行多形态健壮匹配器；④ 自家技能回归确认无 INFO 洪泛后再升版收口。
