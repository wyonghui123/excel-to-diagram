"""检查 status 字段的 semantics"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.models import registry

user = registry.get('user')
for field in user.fields:
    if field.id == 'status':
        semantics = getattr(field, 'semantics', None)
        print('semantics:', semantics)
        if semantics:
            print('filter_type:', getattr(semantics, 'filter_type', 'NOT_SET'))
