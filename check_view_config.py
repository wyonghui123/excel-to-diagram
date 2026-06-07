# 检查 metaService.getViewConfig 返回的数据
import requests
import json

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 获取视图配置 (正确的 API)
resp = requests.get(
    'http://localhost:3010/api/v2/meta/user_group/view-config/default',
    headers=headers
)
data = resp.json()

if data.get('success'):
    config = data['data']
    
    # 检查 list.filters
    list_config = config.get('list', {})
    filters = list_config.get('filters', [])
    print(f"=== list.filters 数量: {len(filters)} ===")
    
    # 检查 list.fields
    fields = list_config.get('fields', [])
    print(f"=== list.fields 数量: {len(fields)} ===")
    
    # 查找 parent_id 字段
    parent_field = None
    for f in fields:
        if f.get('id') == 'parent_id' or f.get('key') == 'parent_id':
            parent_field = f
            break
    
    if parent_field:
        print("\n=== parent_id 字段配置 (from fields) ===")
        print(f"id: {parent_field.get('id')}")
        print(f"type: {parent_field.get('type')}")
        print(f"has value_help: {bool(parent_field.get('value_help'))}")
        if parent_field.get('value_help'):
            vh = parent_field['value_help']
            print(f"value_help.source.type: {vh.get('source', {}).get('type')}")
            print(f"value_help.source.target_bo: {vh.get('source', {}).get('target_bo')}")
    else:
        print("\n[WARNING] 没有在 fields 中找到 parent_id")
        print("字段 ID 列表:", [f.get('id') or f.get('key') for f in fields[:10]])
    
    # 检查顶层 fields
    top_fields = config.get('fields', [])
    print(f"\n=== 顶层 fields 数量: {len(top_fields)} ===")
    
    # 查找 parent_id 顶层字段
    parent_top_field = None
    for f in top_fields:
        if f.get('id') == 'parent_id' or f.get('key') == 'parent_id':
            parent_top_field = f
            break
    
    if parent_top_field:
        print("\n=== parent_id 顶层字段配置 ===")
        print(f"id: {parent_top_field.get('id')}")
        print(f"has value_help: {bool(parent_top_field.get('value_help'))}")
    else:
        print("\n[WARNING] 没有在顶层 fields 中找到 parent_id")
    
else:
    print(f"请求失败: {data.get('message')}")
