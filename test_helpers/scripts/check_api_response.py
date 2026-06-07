import requests
import json

def check_api():
    """检查 API v1 响应中的 columns 配置（无需浏览器）"""
    session = requests.Session()

    # dev-login
    session.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'admin'})

    # 调用 API
    resp = session.get('http://localhost:3010/api/v1/bo/role', params={'pageSize': 1})
    data = resp.json()

    print("\nAPI v1 响应中的 columns 配置:")
    if data.get('columns'):
        for col in data['columns']:
            if col.get('prop') == 'is_system':
                print(f"\nis_system 列配置:")
                print(f"  filter_type: {col.get('filter_type')}")
                print(f"  filterable: {col.get('filterable')}")
                print(f"  filter_options: {col.get('filter_options')}")
                print(f"  options: {col.get('options')}")
                print(f"  enum_type: {col.get('enum_type')}")
                print(f"\n完整列配置:")
                print(json.dumps(col, indent=2, ensure_ascii=False))

    print("\n\nfilters 配置:")
    print(json.dumps(data.get('filters', []), indent=2, ensure_ascii=False))

if __name__ == '__main__':
    check_api()