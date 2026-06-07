# 检查后端返回的元数据配置
import requests
import json

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 获取用户组元数据 (使用 v2 API)
resp = requests.get(
    'http://localhost:3010/api/v2/bo/user_group',
    params={'page': 1, 'page_size': 1},
    headers=headers
)
data = resp.json()

if data.get('success'):
    meta = data['data']
    
    # 检查 filters
    filters = meta.get('filters', [])
    print(f"=== filters 数量: {len(filters)} ===")
    
    # 查找 parent_id 过滤器
    parent_filter = None
    for f in filters:
        if f.get('field') == 'parent_id' or f.get('key') == 'parent_id':
            parent_filter = f
            break
    
    if parent_filter:
        print("\n=== parent_id 过滤器配置 ===")
        print(f"field: {parent_filter.get('field')}")
        print(f"type: {parent_filter.get('type')}")
        print(f"has value_help: {bool(parent_filter.get('value_help'))}")
        if parent_filter.get('value_help'):
            vh = parent_filter['value_help']
            print(f"value_help.source.type: {vh.get('source', {}).get('type')}")
            print(f"value_help.source.target_bo: {vh.get('source', {}).get('target_bo')}")
            print(f"value_help.behavior.multiple: {vh.get('behavior', {}).get('multiple')}")
    else:
        print("\n[WARNING] 没有找到 parent_id 过滤器")
        print("过滤器字段列表:", [f.get('field') or f.get('key') for f in filters])
    
    # 检查 columns
    columns = meta.get('columns', [])
    print(f"\n=== columns 数量: {len(columns)} ===")
    
    # 查找 parent_id 列
    parent_col = None
    for c in columns:
        if c.get('prop') == 'parent_id' or c.get('key') == 'parent_id':
            parent_col = c
            break
    
    if parent_col:
        print("\n=== parent_id 列配置 ===")
        print(f"prop: {parent_col.get('prop')}")
        print(f"filter_type: {parent_col.get('filter_type')}")
        print(f"filterable: {parent_col.get('filterable')}")
        print(f"has valueHelpConfig: {bool(parent_col.get('valueHelpConfig'))}")
        print(f"has value_help: {bool(parent_col.get('value_help'))}")
    
else:
    print(f"请求失败: {data.get('message')}")
