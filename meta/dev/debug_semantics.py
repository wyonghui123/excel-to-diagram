# -*- coding: utf-8 -*-
"""
调试脚本：检查 field.semantics 的类型
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from meta.core.models import registry

# 加载 relationship 元模型
meta_obj = registry.get('relationship')

print(f"元模型: {meta_obj.id}")
print(f"字段数: {len(meta_obj.fields)}")
print()

# 查找 relation_code 字段
for field in meta_obj.fields:
    if field.id == 'relation_code':
        print(f"字段ID: {field.id}")
        print(f"字段名: {field.name}")
        print(f"hasattr(field, 'semantics'): {hasattr(field, 'semantics')}")
        print(f"field.semantics: {field.semantics}")
        print(f"type(field.semantics): {type(field.semantics)}")
        
        if field.semantics:
            if isinstance(field.semantics, dict):
                print(f"semantics 是字典")
                print(f"enum_type_ref: {field.semantics.get('enum_type_ref')}")
                print(f"enum_join_fields: {field.semantics.get('enum_join_fields')}")
            else:
                print(f"semantics 是对象")
                print(f"enum_type_ref: {getattr(field.semantics, 'enum_type_ref', None)}")
                print(f"enum_join_fields: {getattr(field.semantics, 'enum_join_fields', None)}")
