---
name: skill-doc-audit
description: 技能文档审计：审计技能文档与代码的一致性及静态质量，找出版本迭代造成的文档漂移与结构/安全/可运行性/依赖隐患——死链接、失效的命令行参数、退出码表不符、状态或配置项漏写、描述脱节，以及 frontmatter 不规范、硬编码密钥、脚本语法错误、外部依赖与运行平台未声明等。当你刚改完某个技能的脚本或配置、担心文档没跟上，或某个技能经历多次版本迭代后想做一次体检/质量检查/一致性校验时使用。可审计任意本地技能目录，也可批量审计全部已安装技能。
version: "1.4.2"
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

各检查器的完整项、判定口径与误报抑制细节见 `references/checkers.md`。

脚本只能枚举差异、不能判定对错的，以及完全查不出、必须 AI 读代码判断的语义项（如描述是否仍成立、提示是否误导、跨文件一致性），详见 `references/checkers.md`。**不要只用脚本结论就下判断**——扫描报告是线索，不是裁决。

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
# CI 门禁：WARN 也计入退出码（默认仅 ERROR 计入）
python scripts/audit_docs.py --skill <目录> --all-checks --strict
```

退出码：`0` 未发现 ERROR 级问题（--strict 下还需无 WARN）；`1` 发现 ERROR 级问题（或 --strict 下存在 WARN）；`2` 参数或路径错误。报告同时提供人类可读分组与 `--json` 机读（每条含 `checker/severity/category/message/file/line/suggestion`）。

## 回滚

```sh
cp SKILL.md.bak.<时间戳> SKILL.md
```

## 触发与实测

本技能在以下真实对话口吻下应被准确触发（正例），以及在相似但不同诉求下不应触发（near-miss 反例）。

**正例（应触发）**
- 「帮我体检一下这个技能的文档，看看版本迭代后有没有漂移」→ 触发 `doc` 一致性检查。
- 「审计一下这个技能的安全红线，有没有硬编码密钥或路径穿越」→ 触发 `security` 检查器（含上下文感知的 `path_traversal`，自动排除 `https://.../v2` 这类文档 URL 与合法资源上溯，不再误报）。
- 「我想批量检查一下所有已安装技能的依赖和平台声明」→ 触发 `--all --all-checks`（含 `deps`）。

**Near-miss 反例（不应触发）**
- 「帮我优化这段代码的性能」→ 属通用编码任务，非文档/静态体检，本技能不介入。
- 「把这个技能打包成 Docker 镜像」→ 属部署范畴，超出静态体检边界，不触发。

> 触发判据：用户意图围绕「文档与代码一致性 / 结构 / 安全红线 / 可运行性 / 依赖平台」的静态审计时使用；纯运行期、动态行为或部署类诉求不在范围内。

**误报自纠错能力**：`security` 检查器对所有正则统一采用上下文感知过滤，自动排除注释、文档 URL、自引用资源上溯，避免上下文盲误报。完整机制见 `references/checkers.md`。
