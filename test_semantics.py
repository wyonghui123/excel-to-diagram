"""测试 status 字段的 semantics"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.registry import registry

# 获取 user 对象
meta_object = registry.get('user')
if meta_object:
    # 找到 status 字段
    for field in meta_object.fields:
        if field.id == 'status':
            print(f'Field: {field.id}')
            semantics = getattr(field, 'semantics', None)
            print(f'  semantics: {semantics}')
            if semantics:
                print(f'  semantics.filter_type: {repr(getattr(semantics, "filter_type", "NOT_SET"))}')
                print(f'  semantics.filterable: {repr(getattr(semantics, "filterable", "NOT_SET"))}')
            print(f'  field.enum_values: {field.enum_values}')
            print(f'  field.field_type: {field.field_type}')
else:
    print('User object not found')
