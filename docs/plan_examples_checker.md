# Vector 3 落地方案（修订版：内置可选校验工具形态）

> 状态：架构已定稿（2026-09-01）。本方案取代初版「插件式检查器」写法。
> 现状：v1.24.1 已发布（ERROR 0 / WARN 0）。本方案是下一步规划，不改动当前发布。

## 一、决策摘要（架构定稿）

**Vector 3 = skill-doc-audit 的「内置可选校验工具」，落地为独立脚本 `scripts/self_validate.py`，不是 `CHECKERS` 插件式检查器。**

- 它**只校验 skill-doc-audit 自身**：跑审计器自己的 `tests/fixtures/`、比对审计器自己的黄金快照、守护审计器自己 SKILL.md 里写的示例输出仍为真。
- 它**不审计任意用户技能**、**不具备泛用性** → 因此**不混入**「审计目标技能」的 `CHECKERS` 框架。
- 它是**源码仓库内的维护者工具（dev-only）**：只在开发本技能时跑，不进 3-条目 dist、不进部署副本。
- 候选版本：**v1.25.0**（新能力，次版本号，跑全量审计）。

## 二、与「插件式检查器」的本质区别

| | 插件式检查器（现有 8 个） | **Vector 3（本方案）** |
|---|---|---|
| 接收什么 | 一个**目标技能**目录 | 审计器**自己的 fixtures** |
| 产出什么 | 该目标的 findings（ERROR/WARN/INFO） | 审计器自身文档是否过期的 pass/fail + diff |
| 是否在 `CHECKERS` | 是（被 `enabled` 循环统一分派） | **否**，独立脚本，完全不碰 `CHECKERS` |
| 是否能被 `--check` / `--all-checks` 触发 | 是 | **否** |
| 对终端用户技能生效？ | 是 | **否（仅维护者自校）** |

> 强行塞进 `CHECKERS` 是类别错误：现有检查器语义是「审计目标」，Vector 3 语义是「自校审计器」。二者不同类。

## 三、它做什么 / 不做什么

**做**：在开发环境跑 `python scripts/self_validate.py`，对 `tests/fixtures/` 跑 `audit_docs.py`，把实时输出（归一化后）与黄金快照比对，报告差异。守护「我们自己的文档示例没过期」。

**不做**：
- ❌ 不审计用户拿去检查的技能；
- ❌ 不产生 `DOC_EXAMPLE_DRIFT` 这类「目标技能 findings」；
- ❌ 不进 `--all-checks` 全量集（因此无需「fixture 缺失就 INFO 跳过」那套兜底——因为只在 fixtures 必然存在的开发仓库跑）。

## 四、工作原理（三步走）

```
scripts/self_validate.py
        │
        ▼
① 跑（白名单内）   对 tests/fixtures/ 各样本跑 audit_docs.py（只读、离线、幂等）
        │           取 --json 结构化结果
        ▼
② 归一化          只把顶层 skill 绝对路径 掩码成 <ROOT>（已实证是唯一易变项）
        │
        ▼
③ 比对            和 tests/examples/*.expected.json 黄金快照做结构化 diff
        │
        ├─ 一致 → PASS（退出 0）
        └─ 不一致 → 打印差异（退出非 0，便于 CI 门禁）
```

**已实证前提**（来自可行性研究，仍成立）：
- 同 fixture 连跑两次 `--json` 输出**逐字节一致** → 比对稳定；
- 唯一需归一化项 = 顶层 `skill` 绝对路径（findings 内部 `file` 已是相对路径）。

## 五、文件改动清单（修订）

| 类型 | 路径 | 说明 |
|---|---|---|
| **新增** | `scripts/self_validate.py` | 校验工具主体：读 manifest、跑 fixture、归一化、比对、报 diff。**不碰 `CHECKERS`/CLI 分派**。 |
| **新增** | `tests/examples/manifest.json` | 示例清单：哪些 fixture、用哪些检查器、对应哪个黄金快照。 |
| **新增** | `tests/examples/*.expected.json` | 黄金快照（首次由 `--baseline` 自动生成，人工评审提交）。 |
| 复用 | `tests/fixtures/` | 现有 4 个样本（dirty-skill / multifile / tricky-clean / ts-skill），**无需新建**。 |
| **改动** | `SKILL.md` / `README.md` | 在「开发 / 自测」章节说明本工具；**不再**列入 `--check` 检查器表。 |
| 不改动 | `audit_docs.py` 的 `CHECKERS` / `main()` | Vector 3 完全外置于插件框架，零侵入。 |

> **dist / 部署影响**：`self_validate.py` 与 `tests/` 均**不进** `src/dist/skill-doc-audit.zip`（3 条目维持 SKILL.md / audit_docs.py / checkers.md），也**不进**部署副本 `~/.workbuddy/skills/skill-doc-audit/`。仅源码仓库持有。

## 六、数据格式

**manifest.json**（手写好一次）：
```json
{
  "examples": [
    {"name": "dirty-skill-baseline", "fixture": "tests/fixtures/dirty-skill",
     "checkers": ["doc","structure","security","runtime","deps"],
     "golden": "tests/examples/dirty-skill-baseline.expected.json"},
    {"name": "tricky-clean-pass", "fixture": "tests/fixtures/tricky-clean",
     "checkers": ["doc","structure"],
     "golden": "tests/examples/tricky-clean-pass.expected.json"}
  ]
}
```

**黄金快照**（首次 `--baseline` 生成，评审后提交）：
```json
{"skill":"<ROOT>","summary":{"error":3,"warn":1,"info":0,"pass":4},
 "findings":[{"checker":"doc","severity":"error","category":"dead_link",
              "file":"SKILL.md","line":12,"message":"..."}]}
```

## 七、比对规则（归一化，已实证只需 1 条）

| 规则 | 做法 | 必要性 |
|---|---|---|
| **N1 路径掩码** | 顶层 `skill` 绝对路径 → `<ROOT>` | **必须**（唯一实测易变项） |
| N2 行号可选掩码 | 固定 fixture 下行号本确定，可保留精确断言 | 可选 |
| N3 INFO 计数 | 锚定 fixture 后稳定，无需掩码 | 视锚点 |
| **N4 语义化按键** | 以 `(checker,category,severity,message 子串)` 比对，非整段文本 | **推荐**（抗文案微调） |

## 八、CLI / 触发（维护者用）

```bash
# 跑自校验（开发本技能时）
python scripts/self_validate.py

# 首次建立 / 刷新黄金基线（生成 *.expected.json，人工评审后提交）
python scripts/self_validate.py --baseline
```

> 注意：这是对**本技能自身**的校验，与 `python audit_docs.py --skill <别的技能>` 是两条独立命令。

## 九、报告与退出码

| 情况 | 行为 |
|---|---|
| 全部一致 | 打印 `PASS`，退出 0 |
| 有差异 | 打印每个差异（checker/category/字段/预期 vs 实际），退出非 0（CI 门禁可拦） |
| manifest / golden 缺失 | 打印明确提示（开发者环境，直接报错退出非 0 即可，无需 INFO 跳过） |

## 十、安全

- **白名单执行**：只跑 `audit_docs.py` 对 fixture，**绝不执行文档任意 shell**，杜绝注入。
- **离线 / 只读 / 幂等**：示例命令全是对 fixture 的只读扫描。
- **dev-only**：不进 dist / 部署副本，终端用户无触点，无越权面。

## 十一、与「拆分 audit_docs.py」的关系

- 模块化拆分（把 2491 行 `audit_docs.py` 拆成 `auditlib/` 包）**仍可独立决策、独立进行**，与 Vector 3 解耦。
- 无论是否拆分，`self_validate.py` 都是 `scripts/` 下的**独立文件**，调用 `audit_docs.py`（或拆分后的 `auditlib`）即可，不依赖插件框架。
- 推荐：v1.25.0 同时做「模块化 + Vector 3 自校验工具」，一次全量审计（`--all-checks --deadcode-mode vulture`）同时验证「拆分无回归 + 自校验工具有效」。

## 十二、工作量估算

| 模块 | 估计 |
|---|---|
| `self_validate.py` 主体 + 归一化 | 约 80–120 行 |
| manifest 加载 + `--baseline` | 约 40 行 |
| 黄金快照建立（2–3 示例） | 跑一次 + 人工评审 |
| 文档（SKILL/README 自测章） | 约 0.5 天 |
| **合计** | **约 0.5–1 天** |

## 十三、风险与缓解

| 风险 | 缓解 |
|---|---|
| vulture 版本差异导致 golden 抖动 | CI 固定 vulture 版本；或 golden 只锚定非 deadcode 检查器 |
| 黄金快照维护成本 | 本就是「文档示例过期」的回归信号，改动时同步更新 |
| 误当插件检查器用 | 文档明确「内置自校验工具」定位；不进 `CHECKERS`、不进 `--check` 表 |
| doc-llm 不可确定，无法回归 | 明确排除：V2 由 agent 覆盖，本工具只做确定性示例 |

## 十四、泛用版 examples 检查器（独立未来路线图项，非本方案）

若将来想要「**能校验任意用户技能自己文档示例**」的能力，那是**另一回事**，需另立方案：
- 在 SKILL.md 规范里定义「示例块标注约定」（如 ` ```sh {example} ` + `expected=`）；
- 检查器解析**目标技能**示例块、在沙箱执行其命令、归一化后比对；
- 核心是**沙箱执行不可信命令**这一安全设计，工作量/风险明显大于本方案。
→ 记为本技能的**独立路线图项**，不与 Vector 3 混淆。

## 十五、结论

- **做不做**：建议做（可行性 GO，成本低于预期，零 token，纯静态）。
- **形态**：独立 `scripts/self_validate.py`，**非 `CHECKERS` 插件**，dev-only，不进 dist/部署副本。
- **价值**：守护 skill-doc-audit 自身文档示例不过期，是维护者 CI/回归护栏。
- **不阻塞**：v1.24.1 已发布，本方案是下一步规划。
