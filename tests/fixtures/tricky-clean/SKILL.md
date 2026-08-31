---
name: tricky-clean
displayName: Tricky Clean
description: 用于验证误报抑制的干净技能，含字符串键分发、装饰器注册、# keep 白名单与文档 URL。
version: "1.0.0"
license: MIT
author: test
tags: [test]
---

# Tricky Clean

调用 `scripts/main.py`，详见 https://example.com/api/v2/guide 。

## 路由

用装饰器注册入口：@app.route。主入口为 main()。

文档 URL 示例 https://docs.example.org/v1/path/../resource （含 ../ 但属文档 URL，非真实穿越）。
