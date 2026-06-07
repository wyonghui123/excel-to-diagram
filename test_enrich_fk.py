import requests
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 获取用户组详情
print("=== 用户组详情 API ===")
resp = requests.get(
    'http://localhost:3010/api/v2/bo/user_group/591',
    headers=headers
)
data = resp.json()
if data.get('success'):
    record = data.get('data', {})
    print(f"id: {record.get('id')}")
    print(f"parent_id: {record.get('parent_id')}")
    print(f"parent_id_display: {record.get('parent_id_display')}")
    print(f"manager_id: {record.get('manager_id')}")
    print(f"manager_id_display: {record.get('manager_id_display')}")

# 测试 enrich_fk_display_names
print("\n=== 测试 enrich_fk_display_names ===")
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.models import registry

pi = PersistenceInterceptor()
meta_obj = registry.get('user_group')
print(f"meta_obj: {meta_obj}")
print(f"meta_obj.fields count: {len(meta_obj.fields) if meta_obj and hasattr(meta_obj, 'fields') else 'N/A'}")

# 检查 fields
if meta_obj and hasattr(meta_obj, 'fields'):
    for field in meta_obj.fields:
        vh = getattr(field, 'value_help', None)
        if vh:
            source = getattr(vh, 'source', None)
            if source:
                source_type = getattr(source, 'type', '')
                target_bo = getattr(source, 'target_bo', '')
                if source_type == 'bo':
                    print(f"FK field: {field.id} -> {target_bo}")

# 直接调用方法测试
print("\n=== 直接调用 _enrich_fk_display_names ===")
test_record = {'id': 591, 'parent_id': 2, 'manager_id': 3}
result = pi._enrich_fk_display_names(meta_obj, test_record, registry)
print(f"原始记录: {test_record}")
print(f"返回记录: {result}")
print(f"parent_id_display: {result.get('parent_id_display')}")
print(f"manager_id_display: {result.get('manager_id_display')}")
