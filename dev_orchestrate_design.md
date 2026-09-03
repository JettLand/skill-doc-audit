# dev-orchestrate 设计方案（开发编排层：压缩 shell 暴露面 + 幂等重试 + 跨 shell 冗余）

> 来源：本会话反复踩中两类执行层故障后归纳。对应待办 #68。v1.34.7 由 `devkit.py` 重命名而来（定位从「edit-verify-kit」调整为「开发编排层」）。

## 一、两类故障现象与根因（已纠正误判）

### 故障 A：Edit 工具 phantom success（报成功、磁盘未变）
- **触发**：含反斜杠转义、多字节/非 ASCII、枚举串、中文嵌套引号的字符串替换。
- **后果**：agent 误以为已落盘，后续逻辑建立在错误假设上。
- **旧缓解**：手写字节级 `patch_*.py` 脚本（`str.replace` + `assert count==1` + 保 LF 写回），再用 Read 复核磁盘。
- **残留痛点**：每次都要现写脚本 + 现跑 bash，bash 往返多 → 易撞上故障 B。

### 故障 B：工具调用参数传输层间歇丢参（**修正旧误判**）
- **现象**：harness 级故障——`Bash.command` / `PowerShell.command` /
  `Read.file_path` 等**任意字符串参数**会随机变成 `undefined`
  （报错 `command expected string, but received undefined` / `file_path expected string,
  but received undefined`），**与命令内容无关**（连纯 ASCII 的 `echo ok` 也失败）。
- **根因（纠正）**：脆弱点在 **agent 工具调用的参数传输层**，间歇丢弃任意字符串参数；
  Bash / PowerShell / Read **工具均会中招**（本会话实测 `Read.file_path` 与 `Bash.command`
  同回合交替失败、Glob 正常）。**旧文档写成「bash 命令里的引号/中文触发序列化」是错的**——
  该解释无法解释纯 ASCII `echo ok` 失败、也无法解释 Read 工具同样丢参。
- **后果**：`py_compile` / `grep` / `git` / 运行验证脚本全部卡死，整轮工作停滞。

## 二、核心定位：开发编排层（dev orchestration layer），而非「替代 bash」

- 运行任何代码都须经 shell（`python x.py`）。dev-orchestrate **不能凭空消除 shell**——
  这是物理事实，绕不开。故**不叫"替代 bash"**，而叫**开发编排层**：把开发期对 shell 的
  脆弱依赖**压缩到最小 + 幂等可重跑 + 跨 shell 工具冗余**。
- 真正的收益在三处：
  1. **把多字节/转义内容移出命令行**：旧值、新值、待匹配串一律从*文件*读
     （`--old-file`/`--new-file`/`--contains-file`）。shell 启动命令只剩 ASCII 路径与标志，
     **直接规避参数传输层对中文/引号的丢参**（故障 B 的暴露面）。
  2. **单进程批量执行**：`run-plan` 读 JSON 计划，在**一个 Python 进程**内依次做
     patch/verify/compile/status，把 N 次 shell 往返压成 1 次 → 命中故障 B 的概率大幅下降；
     启动那一行若丢参，重试一行即恢复（计划幂等）。
  3. **验证不依赖 bash echo/cat**：`verify` 直接读字节、对匹配行打印 `repr()`，
     等价于用 Read 工具复核磁盘，但可在同一次进程内完成。

## 三、跨 shell 工具冗余（覆盖 PowerShell / Bash 故障，v1.34.7 新增）

故障 B 的特征是**任意工具**的参数都可能被传输层丢弃，dev-orchestrate 自身启动也受威胁。
应对原则是**减少暴露面 + 幂等重试 + 跨工具冗余**，而非"修复"：

- **启动行纯 ASCII、跨 shell 通用**：
  ```bash
  python src/scripts/dev_orchestrate.py <sub> [--flags]
  ```
  bash / powershell / cmd 均认这同一行。当 **Bash 工具丢参**时，改用 **PowerShell 工具**
  （或反之）用**同一行**重试——这是针对传输层丢参的冗余容错。
- **幂等**：每个子命令只读/写明确路径、无副作用累积；计划中断后重跑安全。
- **一次 shell 暴露**：把 N 次往返压成 1 次，即使那 1 次失败，重试成本低、不会半途污染磁盘
  （`run-plan` 任一步失败即中止、不续写后续步骤）。

## 四、dev_orchestrate.py 子命令

| 子命令 | 作用 | 替代的旧 bash 模式 |
|---|---|---|
| `patch --file F --old-file O --new-file N [--once]` | 字节级替换（断言次数 + 保 LF） | 现写 `patch_*.py` + `python patch_*.py` |
| `verify --file F [--contains-file C] [--not-contains-file N]` | 断言含/不含子串，打印匹配行 repr | `grep` + `echo` 复核 |
| `compile [--root src/scripts]` | 递归 py_compile 全部 .py | `python -m py_compile ...` |
| `bump --version X.Y.Z [--section ...]` | 三锚点同步 + CHANGELOG 小节 | 现写 `bump_*.py` |
| `grep --pattern P [--path G]` | 纯 Python grep（Grep 工具备用） | `grep -rn` |
| `status` | `git status --short`（一次 subprocess） | `git status` |
| `doctor` | 纯 Python 环境探针（python 版本 / git 在 PATH / 部署副本 / 三锚点一致），**零 shell 依赖** | 手写多行 shell 探针 |
| `run-plan --plan P.json` | 单进程批量执行计划 | 多次 bash 往返 |
| `selftest` | 内置自测 | — |

文件位置：`src/scripts/dev_orchestrate.py`，已加入 `DEV_TOOLS`（core.py）排除集，不进发布面审计。
（过渡期旧 `devkit.py` 仍列于 `DEV_TOOLS`，待 Bash 恢复后 `git rm` 删除。）

## 五、推荐工作流（针对故障 A+B）

**场景：替换一处含中文/转义的字符串（旧痛点：Edit phantom success + bash 故障）**

1. 用 Write 工具把旧串、新串分别写到 `old.txt` / `new.txt`（Write 处理多字节稳定）。
2. 唯一一次 shell 调用（纯 ASCII；若 Bash 丢参，改 PowerShell 用同一行重试）：
   ```bash
   python src/scripts/dev_orchestrate.py patch --file <目标> --old-file old.txt --new-file new.txt --once
   python src/scripts/dev_orchestrate.py verify --file <目标> --contains-file new.txt --not-contains-file old.txt
   ```
   或合并为一次 `run-plan`：
   ```bash
   python src/scripts/dev_orchestrate.py run-plan --plan plan.json
   ```
   其中 `plan.json` 列出 patch + verify 两步，单进程执行。

**场景：提交前回归**
```bash
python src/scripts/dev_orchestrate.py compile            # 语法
python src/scripts/dev_orchestrate.py status             # git 状态
python src/scripts/dev_orchestrate.py doctor             # 环境探针（零 shell 依赖）
python src/scripts/dev_orchestrate.py selftest           # 套件自测
```

## 六、局限与后续

- 仍依赖至少一次 shell 启动 Python；若 shell 完全不可用，dev-orchestrate 也无法运行
  （届时退回 Read/Grep 工具做静态复核，git 操作交用户手动）。
- `bump` 的 CHANGELOG 锚点写死「排序说明」行；若该行改动需同步。
- 后续可把 `dev_commit.py` 的提交动作也纳入 `run-plan`，使「patch→verify→compile→commit」
  全链路单进程化（需谨慎处理 git 凭据交互，仍归用户）。
- 建议：`self_validate.py` / `dev_self_audit.py` 的发布门禁保持不变；dev-orchestrate 仅作为
  agent 开发期的「抗脆弱」辅助，不进部署副本、不影响被审技能质量。
- **沉淀为可复用经验**：本「工具调用参数间歇丢参 → 重试 + 单进程编排降暴露面 + 跨 shell 工具冗余」
  的应对是跨项目通用的，建议沉淀为 skill（如 `toolcall-resilience`），供其他项目复用。
