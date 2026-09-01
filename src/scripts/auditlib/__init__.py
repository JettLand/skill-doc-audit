# auditlib 包（v1.25.0 由 audit_docs.py 拆分而来）
from . import checkers  # 副作用导入：触发各检查器自注册 CHECKERS["name"] = fn
from . import cli
