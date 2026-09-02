# auditlib 包（v1.25.0 由 audit_docs.py 拆分而来）
import sys as _sys

# 跨平台 stdout/stderr 编码加固：git 钩子（pre-push/pre-commit）以管道/文件重定向脚本
# stdout 时，Windows 默认回退 GBK 码页，无法编码 ✓/✗/⚠ 等符号与中文，触发
# UnicodeEncodeError 使脚本异常退出（曾误拦 push）。强制 UTF-8 且 errors=replace 兜底，
# 任何环境都不崩；终端与重定向报告均按 UTF-8 落盘。
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from . import checkers  # 副作用导入：触发各检查器自注册 CHECKERS["name"] = fn
from . import cli
