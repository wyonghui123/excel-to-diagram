"""检查后端 API 返回的 filters"""
import urllib.request
import json
import http.cookiejar

# 先登录
login_url = 'http://localhost:3010/api/v1/auth/dev-login?username=admin'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

with opener.open(login_url) as resp:
    login_data = json.loads(resp.read().decode())
    print('Login:', login_data.get('success'))

# 获取视图配置
fields_url = 'http://localhost:3010/api/v1/meta/user/view-config?view_name=table'
with opener.open(fields_url) as resp:
    data = json.loads(resp.read().decode())
    if data.get('success'):
        list_config = data['data'].get('list', {})
        filters = list_config.get('filters', [])
        columns = list_config.get('columns', [])

        print(f'\nfilters: {len(filters)} 个')
        print(f'columns: {len(columns)} 个')

        # 找到 status 列
        for col in columns:
            if col.get('key') == 'status':
                print(f"\n=== status 列 ===")
                print(f"filter_type: {repr(col.get('filter_type'))}")
                print(f"enum_values: {len(col.get('enum_values', []))} 个")

        # 找到 status filter
        for f in filters:
            if f.get('field') == 'status':
                print(f"\n=== status filter ===")
                print(f"type: {repr(f.get('type'))}")
                print(f"value_help: {'有' if f.get('value_help') else '无'}")
                print(f"options: {len(f.get('options', []))} 个")
    else:
        print('Error:', data.get('error'))
