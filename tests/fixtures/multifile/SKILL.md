---
name: multifile
displayName: Multifile
description: 多文件死代码误报验证夹具。
version: "0.1.0"
license: MIT
author: test
tags: [test]
---

# Multifile

scripts/a.py 定义 shared_helper，scripts/b.py 通过 `from a import shared_helper` 使用它。
