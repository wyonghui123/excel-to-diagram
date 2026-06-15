"""
直接调 get_allowed_resource_ids 看 TEST888 对各类型的 allowed_ids
"""
import os, sys
os.environ.setdefault('AGENT_PORT', '3011')
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))

# 不启动 server, 只 import + 调 service
from meta.core.datasource import get_data_source
from meta.services.data_permission_service import DataPermissionService

ds = get_data_source('sqlite', path='meta/architecture.db')
service = DataPermissionService(ds)

# TEST888 user_id=3371
user_id = 3371
print(f'=== TEST888 (user_id={user_id}) allowed_resource_ids ===')
for obj_type in ['product', 'version', 'domain', 'sub_domain', 'business_object', 'service_module', 'relationship']:
    try:
        ids = service.get_allowed_resource_ids(user_id, obj_type)
        print(f'  {obj_type}: {len(ids) if ids else 0} ids {ids[:5] if ids else []}')
    except Exception as e:
        print(f'  {obj_type}: ERR {e}')

print()
print('=== admin (user_id=1) ===')
for obj_type in ['product', 'version', 'domain', 'sub_domain']:
    try:
        ids = service.get_allowed_resource_ids(1, obj_type)
        print(f'  {obj_type}: {len(ids) if ids else 0} ids')
    except Exception as e:
        print(f'  {obj_type}: ERR {e}')

# 看 _get_all_effective_permissions
print('\n=== TEST888 _get_all_effective_permissions ===')
try:
    eff = service._get_all_effective_permissions(user_id)
    for p in eff[:10]:
        print(f'  {p}')
    print(f'  total: {len(eff)}')
except Exception as e:
    print(f'  ERR: {e}')
