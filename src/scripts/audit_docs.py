#!/usr/bin/env python3
# audit_docs.py —— 薄入口（v1.25.0 起：逻辑移至 auditlib 包）
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auditlib import cli

if __name__ == "__main__":
    cli.main()
