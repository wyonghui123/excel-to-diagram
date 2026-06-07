"""检查 FK 字段的 semantics"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.models import registry

user_group = registry.get('user_group')
for field in user_group.fields:
    if field.id in ('parent_id', 'manager_id'):
        semantics = getattr(field, 'semantics', None)
        print(f'{field.id}:')
        print(f'  field_type: {field.field_type.value}')
        print(f'  semantics: {semantics}')
        if semantics:
            filter_type = getattr(semantics, 'filter_type', 'NOT_SET')
            print(f'  semantics.filter_type: {filter_type}')
