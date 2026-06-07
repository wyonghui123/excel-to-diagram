import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

# 测试 registry
print("=== 测试 registry ===")
from meta.core.models import registry
print(f"registry: {registry}")
print(f"registry type: {type(registry)}")

# 测试 get 方法
print("\n=== 测试 registry.get ===")
user_group = registry.get('user_group')
print(f"user_group: {user_group}")

# 测试 list_objects
print("\n=== 测试 registry.list_objects ===")
objects = registry.list_objects()
print(f"objects count: {len(objects)}")
print(f"first 5: {objects[:5]}")
