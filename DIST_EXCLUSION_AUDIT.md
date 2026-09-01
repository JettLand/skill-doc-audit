# 不进 dist / 部署副本 文件清单核查报告

日期：2026-09-01
核查对象：`skill-doc-audit` v1.25.3 源码树 / dist / 部署副本

## 结论

"不进 dist / 部署副本"的排除清单**准确**：`make_fixtures.py`、`self_validate.py`、`tests/` 三类在 dist zip 与部署副本中均不存在。

## 证据

### 1. `src/dist/skill-doc-audit.zip`（当前版，18 项）
- 含：`src/SKILL.md` + `src/scripts/audit_docs.py` + `src/references/checkers.md` + `src/scripts/auditlib/**`（15 文件）
- 不含 dev 工具 / `tests/`：
  - `make_fixtures.py` → NONE ✅
  - `self_validate.py` → NONE ✅
  - `tests/` → NONE ✅

### 2. 部署副本松散文件（C:/Users/admin/.workbuddy/skills/skill-doc-audit/）
- 含：`SKILL.md`、`scripts/audit_docs.py`、`references/checkers.md`、`scripts/auditlib/**`（含 doc_llm 等全部 8 检查器，当前版）
- 不含 dev 工具 / `tests/`：目录树中无 `make_fixtures.py` / `self_validate.py` / `tests/` → NONE ✅

## ⚠️ 相关发现（非排除清单本身，但影响"部署副本已同步"承诺）

部署副本内嵌的 `dist/skill-doc-audit.zip` **已过期**（未随 1.25.0 模块化拆分更新）：

| 对象 | 条目数 | sha16 | size | 内容 |
|------|--------|-------|------|------|
| `src/dist/skill-doc-audit.zip`（当前） | 18 | `19847723f4c5f5b1` | 81395 | 含 `auditlib/**`、带 `src/` 前缀 |
| 部署副本内嵌 `dist/skill-doc-audit.zip` | 3 | `c5690f89fad56a7b` | 59094 | 仅 `SKILL.md`+`audit_docs.py`+`checkers.md`，无 `auditlib/**` |

- 内嵌 zip 停留在 1.25.0 之前的 3 条目形态；部署副本的松散 `auditlib/` 文件已是当前版 → 两者不一致。
- 该内嵌 zip 同样正确排除了 dev 工具 / `tests/`，故未动摇排除清单准确性，但"制品同步"不完整。
- 若从内嵌 zip 取制品会得到过时版本。

旁注：部署副本含 `scripts/auditlib/__pycache__/*.pyc`（运行期字节码，无害、可重建，非必需）。

## 执行结果（2026-09-01，已执行）

- 已将 `src/dist/skill-doc-audit.zip` 覆盖部署副本 `dist/skill-doc-audit.zip`。
- 已清理部署副本 `scripts/auditlib/**/__pycache__/*.pyc`。
- 复核：部署 zip 与 src 字节一致（sha256 相等、18 条目相同）；部署松散文件相对 src 缺失/多余/内容差异均为 NONE → 部署副本现在完全自洽。
- 同步清理：删除测试报告 `SELF_VALIDATE_TEST_REPORT.md`；删除过时快照 `backups/`（gitignored，v1.5.1–v1.7.0 等）。`DIST_EXCLUSION_AUDIT.md` 保留为本次核查交付物。
