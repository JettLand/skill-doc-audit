---
name: dirty-wrong
displayName: Dirty Test
description: 测试用的脏技能，含多种文档漂移与死代码问题。
version: "0.0.1"
license: MIT
author: test
tags: [test]
---

# Dirty Test

本技能用于压力测试，故意制造多种文档漂移、安全与死代码问题。

## 用法

```sh
python scripts/main.py --recalc
```

参考脚本 `scripts/ghost.py` 与历史说明 `references/old_notes.md`。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `7` | 部分失败（文档声明但代码从不返回） |

## 内部

调用 `tune_model` 完成训练流程。

TODO: fix this section
