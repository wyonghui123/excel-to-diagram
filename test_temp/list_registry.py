# -*- coding: utf-8 -*-
"""查看系统所有可审计的 object_type (从 meta registry)"""
import os
import sys

PROJECT_ROOT = r'd:/filework/excel-to-diagram'
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# 用 list_objects() 初始化 registry
from meta.core.models import registry, MetaRegistry
all_types = registry.list_objects()
print(f"=== Registry 共有 {len(all_types)} 个 object_type ===")
for t in sorted(all_types):
    print(f"  - {t}")
