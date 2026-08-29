---
name: skill-doc-audit
description: 审计技能文档与代码的一致性及静态质量，找出版本迭代造成的文档漂移与结构/安全/可运行性/依赖隐患——死链接、失效的命令行参数、退出码表不符、状态或配置项漏写、描述脱节，以及 frontmatter 不规范、硬编码密钥、脚本语法错误、外部依赖与运行平台未声明等。当你刚改完某个技能的脚本或配置、担心文档没跟上，或某个技能经历多次版本迭代后想做一次体检时使用。可审计任意本地技能目录，也可批量审计全部已安装技能。
version: "1.3.0"
license: MIT
author: Jett
agent_created: true
allowed-tools: Bash, Read, Edit
---

# 技能文档审计与同步

## 为什么需要

技能文档会随着版本迭代漂移：代码改了、文档没跟上。典型症状是**死引用**（文档写着某个文件/参数，代码里早已删除）和**描述过时**（文档声称某个行为，实测已不成立）。这类偏差不会让脚本报错，却会误导后续维护者与调用方。

## 能力边界（务必先读）

这个技能是「机器扫描 + AI 语义复核」的组合，两者分工不同：

**脚本能可靠判定的（低误报，通常就是偏差）** —— 由以下检查器产出，可按需启用：

- `doc`（常驻默认开）：文档一致性
- `structure`：结构体检 + 元信息
- `security`：安全红线静态子集
- `runtime`：脚本可运行性
- `deps`：依赖与平台声明

| 检查器 | 项 | 说明 |
|---|---|---|
| doc | `DEAD_PATH` | 文档引用的文件路径已不存在 |
| doc | `DEAD_FLAG` | 文档提到的命令行参数在代码中无实现 |
| doc | `EXIT_DOC_ONLY` | 文档列了退出码，但代码从不返回 |
| doc | `EXIT_CODE_ONLY` | 代码会返回某退出码，但文档未列 |
| doc | `UNKNOWN_IDENT` | 文档提到的 snake_case 标识符在代码中不存在 |
| doc | `VERSION_MISSING` | SKILL.md 缺少 version 声明 |
| structure | `name_mismatch` | frontmatter name 与目录名不一致 |
| structure | `version_missing` | 缺少合规 version |
| structure | `desc_missing` | 缺少 description |
| structure | `broken_ref` | 加载式引用（references/、scripts/）目标不存在 |
| structure | `hardcoded_path` | 文档含硬编码用户绝对路径 |
| structure | `todo_marker` | 含 TODO/FIXME 标记 |
| security | `hardcoded_secret` | 疑似硬编码密钥/凭据 |
| security | `path_traversal` | 路径穿越('../') |
| security | `destructive_wildcard` | 用户目录通配删除 'rm -rf *' |
| runtime | `py_syntax` | Python 脚本语法错误 |
| runtime | `script_ref_missing` | 文档引用的脚本不存在 |
| deps | `undeclared_cli` | 代码调用外部 CLI 但文档未声明依赖（WARN） |
| deps | `platform_undeclared` | 代码含 Windows 专属 API 但未声明运行平台（INFO） |

> `structure`/`security`/`runtime` 中的 `WARN`/`INFO` 项（如 description 长度、混淆、动态执行、能力预检清单）为提示性质，需结合上下文判断，勿直接当错误处置。

> 即便 `doc` 类的 `DEAD_PATH` 也需看一眼上下文：它可能是文档在引用**运行期生成的产物**（例如某技能会在目标项目里创建 `.learnings/` 目录，或脚本在临时目录生成 state）。这类引用在本技能目录下确实找不到，却并非漂移。判定前留意引用处是否含「生成 / 创建 / 写入」等含义。

**脚本只能枚举差异、需 AI 判断的（默认多为误报）**

运行状态全集、配置项全集。内部实现细节本就不必写进面向用户的文档，故「未提及」通常是正常的——**只有当该状态或配置属于用户可感知行为**（如退出码含义、可手动调整的开关）时才需要补写。脚本只呈现事实，不判定对错。

**脚本完全查不出、必须由 AI 读代码判断的**

- 描述是否准确反映实际行为（例如文档写某功能是「兜底」，实测它早已失效）
- 提示文案是否误导用户
- 代码注释与实现是否一致
- 跨文件一致性（项目记忆、报告与 SKILL.md 之间）

> 因此**不要只用脚本结论就下判断**。扫描报告是线索，不是裁决。

## 流程

1. **备份并扫描**
   ```sh
   python scripts/audit_docs.py --skill ~/.workbuddy/skills/<技能名> --backup
   ```
   脚本会在审计前把 `SKILL.md` 备份为 `SKILL.md.bak.<时间戳>`。为防频繁迭代产生过多备份，同一 `SKILL.md` 的 `.bak.*` 文件**最多保留 3 个**——生成新备份前会先删除最旧者。可用 `--backup-limit N` 调整上限（如 `--backup-limit 5`）。

2. **AI 复核**：阅读报告后，针对每一条核对源码。重点甄别三类：
   - A 类里是否有「有意为之」的条目（例如文档标注「已弃用」的退出码，属正常）
   - B 类里哪些其实是用户可感知行为、应当补写
   - 脚本查不出的语义项：把文档逐段与代码行为对照，确认描述仍然成立

3. **直接修改**：本技能按「全自动改 + 备份」模式运行——判断清楚后直接编辑 `SKILL.md`，无需停下来等待确认。

4. **汇总**：列出改了什么、依据是什么，并告知备份位置与回滚方法。

## 修改原则

- **只改文档，不改代码**。若审计中发现是代码有问题，整理出来交由用户决策，不要顺手改代码。
- **保留「已弃用」标注**。例如某退出码已在文档标注弃用，那是刻意的向后兼容说明，不要因为它「代码从不返回」就删掉。
- **存疑时标注而非臆断**。语义判断没有把握时，在文档中写明「待确认」，好过写下一个错误的断言。
- 版本号按语义化规则递增：修正文档表述属补丁级，修复功能缺陷属小版本级。

## 用法

```sh
# doc 一致性（常驻默认）
python scripts/audit_docs.py --skill ~/.workbuddy/skills/workbuddy-checkin --backup

# 启用插件式检查器（doc 常驻 + 指定项，可重复 --check）
python scripts/audit_docs.py --skill <目录> --check structure --check security

# 全部检查器（doc + structure + security + runtime + deps）
python scripts/audit_docs.py --skill <目录> --all-checks

# 仅依赖/平台声明检查
python scripts/audit_docs.py --skill <目录> --check deps

# 备份上限可调；批量审计；JSON 机读（同时仍打印可读报告）
python scripts/audit_docs.py --skill <目录> --backup --backup-limit 5
python scripts/audit_docs.py --all --all-checks
python scripts/audit_docs.py --skill <目录> --all-checks --json
```

退出码：`0` 未发现 ERROR 级问题；`1` 发现 ERROR 级问题；`2` 参数或路径错误。报告同时提供人类可读分组与 `--json` 机读（每条含 `checker/severity/category/message/file/line/suggestion`）。

## 回滚

```sh
cp SKILL.md.bak.<时间戳> SKILL.md
```
