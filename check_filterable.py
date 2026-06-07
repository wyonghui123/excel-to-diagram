#!/usr/bin/env python
"""检查 filterable 的类型和值"""
import requests

s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
login_data = r.json()

if 'data' in login_data:
    # 检查 v1 API
    r = s.get('http://localhost:3010/api/v1/meta/user_group/view-config/default')
    data = r.json()

    if 'data' in data:
        inner = data['data']
        list_config = inner.get('list', {})
        columns = list_config.get('columns', [])

        print("Columns filterable analysis:")
        for col in columns:
            key = col.get('key', 'N/A')
            filterable = col.get('filterable')
            print(f"  {key}: filterable={repr(filterable)} (type={type(filterable).__name__})")
