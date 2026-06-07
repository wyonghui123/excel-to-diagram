# -*- coding: utf-8 -*-
"""
详细调试 resolve_conditions 处理 domain_id 的过程
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services
from meta.core.models import registry as meta_registry, FieldStorage


ds = get_data_source("sqlite", database=get_test_db_path())
init_services(ds)

meta_obj = meta_registry.get('sub_domain')

print("=" * 60)
print("检查 sub_domain 的 domain_id 字段")
print("=" * 60)

field = meta_obj.get_field('domain_id')
print(f"\nfield: {field}")
if field:
    print(f"  id: {field.id}")
    print(f"  name: {field.name}")
    print(f"  type: {field.type}")
    print(f"  storage: {field.storage}")
    print(f"  storage.value: {field.storage.value if hasattr(field.storage, 'value') else field.storage}")
    print(f"  is FieldStorage.VIRTUAL: {field.storage == FieldStorage.VIRTUAL}")
    
    semantics = getattr(field, 'semantics', None)
    if semantics:
        virtual = getattr(semantics, 'virtual', False)
        print(f"  semantics.virtual: {virtual}")
    
    is_virtual = (field.storage == FieldStorage.VIRTUAL) or (getattr(semantics, 'virtual', False) if semantics else False)
    print(f"\n  is_virtual 最终判断: {is_virtual}")
    print(f"  应该走直接字段分支: {not is_virtual}")
else:
    print("  field is None!")

# 测试所有字段
print(f"\n所有字段:")
for f in meta_obj.fields:
    storage = getattr(f, 'storage', None)
    storage_val = storage.value if hasattr(storage, 'value') else storage
    is_virtual_storage = storage == FieldStorage.VIRTUAL
    semantics = getattr(f, 'semantics', None)
    is_virtual_semantics = getattr(semantics, 'virtual', False) if semantics else False
    print(f"  {f.id}: storage={storage_val}, virtual_storage={is_virtual_storage}, virtual_semantics={is_virtual_semantics}")
