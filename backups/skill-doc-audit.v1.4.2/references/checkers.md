# 检查器清单与口径（skill-doc-audit 细则）

本文件是 `SKILL.md` 的加载式补充，列明各检查器的完整项、判定口径与误报抑制机制。SKILL.md 仅保留能力边界概述，执行审计时以本文件为明细基准。

## 检查器总览

脚本能可靠判定的偏差由以下检查器产出，可按需启用：

- `doc`（常驻默认开）：文档一致性
- `structure`：结构体检 + 元信息
- `security`：安全红线静态子集
- `runtime`：脚本可运行性
- `deps`：依赖与平台声明

## 检查项明细

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
| security | `path_traversal` | 路径穿越('../')（上下文感知：排除注释/文档URL/自引用上溯，避免误报）|
| security | `destructive_wildcard` | 用户目录通配删除 'rm -rf *' |
| runtime | `py_syntax` | Python 脚本语法错误 |
| runtime | `script_ref_missing` | 文档引用的脚本不存在 |
| deps | `undeclared_cli` | 代码调用外部 CLI 但文档未声明依赖（WARN） |
| deps | `platform_undeclared` | 代码含 Windows 专属 API 但未声明运行平台（INFO） |

## 判定提示

> `structure`/`security`/`runtime` 中的 `WARN`/`INFO` 项（如 description 长度、混淆、动态执行、能力预检清单）为提示性质，需结合上下文判断，勿直接当错误处置。

> 即便 `doc` 类的 `DEAD_PATH` 也需看一眼上下文：它可能是文档在引用**运行期生成的产物**（例如某技能会在目标项目里创建 `.learnings/` 目录，或脚本在临时目录生成 state）。这类引用在本技能目录下确实找不到，却并非漂移。判定前留意引用处是否含「生成 / 创建 / 写入」等含义。

## 需 AI 语义复核的部分

**脚本只能枚举差异、需 AI 判断的（默认多为误报）**

运行状态全集、配置项全集。内部实现细节本就不必写进面向用户的文档，故「未提及」通常是正常的——**只有当该状态或配置属于用户可感知行为**（如退出码含义、可手动调整的开关）时才需要补写。脚本只呈现事实，不判定对错。

**脚本完全查不出、必须由 AI 读代码判断的**

- 描述是否准确反映实际行为（例如文档写某功能是「兜底」，实测它早已失效）
- 提示文案是否误导用户
- 代码注释与实现是否一致
- 跨文件一致性（项目记忆、报告与 SKILL.md 之间）

> 因此**不要只用脚本结论就下判断**。扫描报告是线索，不是裁决。

## 误报自纠错能力

`security` 检查器对所有正则（硬编码密钥 / 混淆 / 动态执行 / 路径穿越 / 通配删除）统一采用上下文感知过滤，自动排除以下情形，避免上下文盲误报：

1. **注释行**：以 `#`、`//`、`/*`、`*`、`<!--` 开头的整行；
2. **文档 URL**：含 `://` 的行（例如文档里出现的 API 基地址中 `.../` 段，曾被误判为路径穿越）；
3. **自引用资源上溯**：含 `__file__`/`dirname`/`.asar`/`install_dir` 等标记的行（合法定位安装目录，非真实穿越）。

真实漏洞（如将外部可控字符串拼入用于 `open`/`os.remove`/`shutil` 的落盘路径并含相对上溯）仍正常报出。该机制无需人工逐条标注，统一作用于全部 security 正则，只减误报、绝不增 ERROR。
