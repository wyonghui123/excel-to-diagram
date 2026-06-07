"""调试 YAML 解析"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.yaml_loader import load_object_from_yaml

# 强制重新加载
from meta.core.models import MetaRegistry
MetaRegistry.__force_reload__ = True

# 加载 user_group
obj = load_object_from_yaml('user_group')
print(f"Loaded: {obj.id}")

# 检查 parent_id 字段
for field in obj.fields:
    if field.id == 'parent_id':
        print(f"\nparent_id field:")
        print(f"  id: {field.id}")
        print(f"  name: {field.name}")
        print(f"  value_help: {field.value_help}")
        if field.value_help:
            print(f"    source: {field.value_help.source}")
            print(f"    behavior: {field.value_help.behavior}")
            print(f"    presentation: {field.value_help.presentation}")
