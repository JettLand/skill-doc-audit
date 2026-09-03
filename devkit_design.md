# edit-verify-kit 设计方案（摆脱对 bash 的脆弱依赖）

> 来源：本会话反复踩中两类执行层故障后归纳。对应待办 #68。

## 一、两类故障现象与根因

### 故障 A：Edit 工具 phantom success（报成功、磁盘未变）
- **触发**：含反斜杠转义、多字节/非 ASCII、枚举串、中文嵌套引号的字符串替换。
- **后果**：agent 误以为已落盘，后续逻辑建立在错误假设上。
- **旧缓解**：手写字节级 `patch_*.py` 脚本（`str.replace` + `assert count==1` + 保 LF 写回），再用 Read 复核磁盘。
- **残留痛点**：每次都要现写脚本 + 现跑 bash，bash 往返多 → 易撞上故障 B。

### 故障 B：Bash/PowerShell harness 瞬时故障
- **现象**：偶发 `Parameter "command" expected string, but received undefined`
  / harness 级拒绝，**与命令内容无关**（连 `echo ok` 也失败）。
- **根因判断**：shell 调用层的参数序列化瞬时故障（非 Python 本身、非网络）。
  本会话中 bash 多次「不可用 ↔ 恢复正常」交替，证实为瞬时性。
- **后果**：`py_compile` / `grep` / `git` / 运行验证脚本全部卡死，整轮工作停滞。

## 二、核心认识：无法「零 shell」执行，但能「让唯一一次 shell 调用足够简单、足够少、足够稳」

- 运行任何代码都须经 shell（`python x.py`）。devkit 不能凭空消除 shell。
- 真正的收益在三处：
  1. **把多字节/转义内容移出命令行**：旧值、新值、待匹配串一律从*文件*读
     （`--old-file`/`--new-file`/`--contains-file`）。bash 命令只剩 ASCII 路径与标志，
     **规避引号/中文触发的序列化故障**（故障 B 的直接诱因）。
  2. **单进程批量执行**：`run-plan` 读 JSON 计划，在**一个 Python 进程**内依次做
     patch/verify/compile/status，把 N 次 bash 往返压成 1 次 → 命中故障 B 的概率大幅下降。
  3. **验证不依赖 bash echo/cat**：`verify` 直接读字节、对匹配行打印 `repr()`，
     等价于用 Read 工具复核磁盘，但可在同一次进程内完成。

## 三、devkit.py 子命令

| 子命令 | 作用 | 替代的旧 bash 模式 |
|---|---|---|
| `patch --file F --old-file O --new-file N [--once]` | 字节级替换（断言次数 + 保 LF） | 现写 `patch_*.py` + `python patch_*.py` |
| `verify --file F [--contains-file C] [--not-contains-file N]` | 断言含/不含子串，打印匹配行 repr | `grep` + `echo` 复核 |
| `compile [--root src/scripts]` | 递归 py_compile 全部 .py | `python -m py_compile ...` |
| `bump --version X.Y.Z [--section ...]` | 三锚点同步 + CHANGELOG 小节 | 现写 `bump_*.py` |
| `grep --pattern P [--path G]` | 纯 Python grep（Grep 工具备用） | `grep -rn` |
| `status` | `git status --short`（一次 subprocess） | `git status` |
| `run-plan --plan P.json` | 单进程批量执行计划 | 多次 bash 往返 |
| `selftest` | 内置自测 | — |

文件位置：`src/scripts/devkit.py`，已加入 `DEV_TOOLS`（core.py:110）排除集，不进发布面审计。

## 四、推荐工作流（针对故障 A+B）

**场景：替换一处含中文/转义的字符串（旧痛点：Edit phantom success + bash 故障）**

1. 用 Write 工具把旧串、新串分别写到 `old.txt` / `new.txt`（Write 处理多字节稳定）。
2. 唯一一次 bash 调用（纯 ASCII）：
   ```bash
   python src/scripts/devkit.py patch --file <目标> --old-file old.txt --new-file new.txt --once
   python src/scripts/devkit.py verify --file <目标> --contains-file new.txt --not-contains-file old.txt
   ```
   或合并为一次 `run-plan`：
   ```bash
   python src/scripts/devkit.py run-plan --plan plan.json
   ```
   其中 `plan.json` 列出 patch + verify 两步，单进程执行。

**场景：提交前回归**
```bash
python src/scripts/devkit.py compile            # 语法
python src/scripts/devkit.py status             # git 状态
python src/scripts/devkit.py selftest           # 套件自测
```

## 五、局限与后续

- 仍依赖一次 shell 启动 Python；若 shell 完全不可用，devkit 也无法运行（届时退回 Read/Grep 工具做静态复核，git 操作交用户手动）。
- `bump` 的 CHANGELOG 锚点写死「排序说明」行；若该行改动需同步。
- 后续可把 `dev_commit.py` 的提交动作也纳入 `run-plan`，使「patch→verify→compile→commit」
  全链路单进程化（需谨慎处理 git 凭据交互，仍归用户）。
- 建议：`self_validate.py` / `dev_self_audit.py` 的发布门禁保持不变；devkit 仅作为
  agent 开发期的「抗脆弱」辅助，不进部署副本、不影响被审技能质量。
