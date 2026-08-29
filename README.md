# skill-doc-audit 技能工程仓库

本仓库是 SkillHub 技能 **skill-doc-audit（技能文档审计）** 的源管理与发布工程仓库，并非技能本身。正式上架版本发布于 SkillHub（slug：`skill-doc-audit`），平台综合评测 **4.8/5（优秀）**。

## 仓库布局
- `src/`：技能根目录（即发布包内容）
  - `src/SKILL.md`：技能定义与用法（SkillHub 据此生成技能主页）
  - `src/scripts/audit_docs.py`：核心静态体检脚本
  - `src/references/checkers.md`：检查器明细基准
  - `src/dist/skill-doc-audit.zip`：可发布制品
- `icons/`：已选定技能图标
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
| 1.6.0 | 4.8/5 优秀 | 新增 deadcode 死代码检查器（--check deadcode 启用，默认不随 --all-checks） |
| 1.7.0 | 待复评 | deadcode 并入 --all-checks 默认集；运行前按 --deadcode-mode 询问精度（vulture/ast/skip），超时回退 ast |
| 1.8.0 | 已发布（平台审核中） | deadcode 投产打磨：修复 vulture API 调用；vulture 模式去重（不重复报 AST 项）；`# keep` 白名单统一作用于 vulture 分支；vulture 异常改 stderr 告警不静默；ast/vulture 分工明确。`doc` 检查器 `UNKNOWN_IDENT` 误报修复：自动识别 frontmatter `allowed-tools`/`tools` 与文档中的 `mcp__*__<name>` 外部工具名并跳过，不再对 MCP/Agent 类技能刷海量误报；该检查由 ERROR 降级为 WARN（本就是「可能拼写有误」的猜测），并按标识符去重。**同窗口内追加三项打磨**：① 死代码 `unused_def` 增加跨文件引用感知（多文件技能「本文件定义、他文件调用」不再误报），`orphan_asset` 增加 import 模块名豁免；② 代码/配置文件扫描扩展至多语言（.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua 等），含多语言硬编码密钥检测；③ 新增 `--preview` 检查预览（只列出将运行的检查器与将扫描的文件，不产出发现，退出码 0），缓解「参数偏多/文档偏长」的首次使用门槛 |

> 评测由 SkillHub 平台在每次发布后自动重跑（TRACE 五维）。

## 1.8.0 打磨明细（发布窗口内就地修正）

| 打磨项 | 改动 | 验证（均通过，0 回归） |
|---|---|---|
| 死代码跨文件感知 | `check_deadcode` 预扫描全技能 `.py` 构建全局 `global_used` + `imported_modules`，`unused_def` 仅当全技能范围都未引用才报；`orphan_asset` 增加 import 模块名豁免 | `temp/fixtures/multifile`（a.py 定义 `shared_helper`、b.py 调用）不再误报 `unused_def`；真阳性 `EXIT_CODE_ONLY` 保留 |
| 多语言扫描覆盖 | `CODE_EXT` 由 `.py/.js/.sh/.ps1/.json` 扩展至含 `.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua` 等；`FILE_REF_RE`/`structure`/`runtime` 引用正则同步扩展 | `temp/fixtures/ts-skill` 的 `runGame` 不再误报 `UNKNOWN_IDENT`；`.ts` 内硬编码密钥被 `security` 抓到 |
| 检查预览 `--preview` | `main()` 新增 `--preview`：只打印将运行检查器 / deadcode 精度模式 / 文档存在性 / 将扫描文件清单 / 跳过的大文件，退出码 0 | `temp/fixtures/multifile --all-checks --preview` 退出码 0、列出 2 个文件、无发现 |
| `UNKNOWN_IDENT` 误报修复 | 提取 frontmatter `allowed-tools`/`tools` 与全仓库 `mcp__*__<name>` 标记为 `declared_tools` 并跳过；级别 ERROR→WARN；按标识符去重 | `weixin-minigame-helper` 原 57 ERROR → 0 ERROR；`godot-core`（MCP 技能）26 个外部工具名由 ERROR 降为 WARN（仍保留，提示作者在 frontmatter 声明）；真阳性 `tune_model` 仍报出 |
| 文档渐进式披露 | `SKILL.md` 新增「快速开始」小节（3 条核心命令 + 意图→命令速查表）；`--preview` 进入用法示例；`checkers.md` 新增「命令行参数速查」 | 文档偏长/参数偏多感知缓解 |

复测总览：`py_compile` 通过；自审 5 检查器 + `--all-checks` 均 0 ERROR；`dirty-skill` 14 类缺陷全命中 0 漏报；`tricky-clean` 0 误报；`--all` 扫已装技能 1.7s 无崩溃；市场随机抽检 6 技能无崩溃、`UNKNOWN_IDENT` 稳定为 WARN。
