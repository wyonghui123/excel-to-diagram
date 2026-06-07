"""检查后端返回的 user_group 配置"""
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
fields_url = 'http://localhost:3010/api/v1/meta/user_group/view-config?view_name=table'
with opener.open(fields_url) as resp:
    data = json.loads(resp.read().decode())
    if data.get('success'):
        list_config = data['data'].get('list', {})

        # 检查 columns
        columns = list_config.get('columns', [])
        print(f'\ncolumns: {len(columns)} 个')

        # 找到 parent_id 和 manager_id 列
        for col in columns:
            key = col.get('key', '')
            if 'parent' in key.lower() or 'manager' in key.lower():
                print(f"\n=== {key} 列 ===")
                print(f"filter_type: {repr(col.get('filter_type'))}")
                print(f"value_help_config: {'有' if col.get('value_help_config') else '无'}")
                if col.get('value_help_config'):
                    print(f"value_help_config.behavior.multiple: {col['value_help_config'].get('behavior', {}).get('multiple')}")

        # 检查 filters
        filters = list_config.get('filters', [])
        print(f'\nfilters: {len(filters)} 个')

        for f in filters:
            if 'parent' in f.get('field', '').lower() or 'manager' in f.get('field', '').lower():
                print(f"\n=== {f.get('field')} filter ===")
                print(f"type: {repr(f.get('type'))}")
                print(f"value_help: {'有' if f.get('value_help') else '无'}")
                if f.get('value_help'):
                    print(f"value_help.behavior.multiple: {f['value_help'].get('behavior', {}).get('multiple')}")
    else:
        print('Error:', data.get('error'))
