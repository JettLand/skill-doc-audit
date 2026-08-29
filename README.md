# skill-doc-audit 技能工程仓库

本仓库是 SkillHub 技能 **skill-doc-audit（技能文档审计）** 的源管理与发布工程仓库，并非技能本身。正式上架版本发布于 SkillHub（slug：`skill-doc-audit`），平台综合评测 **4.8/5（优秀）**。

## 仓库布局
- `src/`：技能根目录（即发布包内容）
  - `src/SKILL.md`：技能定义与用法（SkillHub 据此生成技能主页）
  - `src/scripts/audit_docs.py`：核心静态体检脚本
  - `src/references/checkers.md`：检查器明细基准
  - `src/dist/skill-doc-audit.zip`：可发布制品
- `icons/`：已选定技能图标
- `skillhub_upload_checklist.md`：发布前自检清单（内部流程记录）
- `backups/`：本地编辑期快照，不进版本库，仅留本机

## 本地开发 / 自测
```bash
# 对技能源做全检查器自审计（应 0 ERROR，退出码 0）
python src/scripts/audit_docs.py --skill src --all-checks
```

## 打包与发布
1. 修改 `src/` 内源文件，自测通过；
2. 重新打包制品为 `src/dist/skill-doc-audit.zip`（含 SKILL.md / audit_docs.py / checkers.md）；
3. 经 SkillHub CLI 发布：`skillhub publish src/dist/skill-doc-audit.zip --version x.y.z --changelog "..."`；
4. 提交并推送本仓库：`git add ... && git commit && git push origin main`。

## 版本与评测
| 版本 | 综合评分 | 说明 |
|---|---|---|
| 1.5.2 | 4.7/5 优秀 | 进阶用法示例 + 报错提示通俗化 |
| 1.5.3 | 4.8/5 优秀 | 检查项中文标签（category_cn）+ 错误码对照表，报告自解释；异常处理 4.3→4.8 |

> 评测由 SkillHub 平台在每次发布后自动重跑（TRACE 五维）。
