import requests
import json

def check_api():
    """检查 API v2 响应（无需浏览器）"""
    session = requests.Session()

    # dev-login
    session.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'admin'})

    # 调用 API v2
    resp = session.get('http://localhost:3010/api/v2/bo/role', params={'pageSize': 1})
    data = resp.json()

    print("\n=== API v2 响应 ===")
    print(f"success: {data.get('success')}")

    if data.get('data'):
        d = data['data']
        print(f"\nitems 数量: {len(d.get('items', []))}")
        print(f"total: {d.get('total')}")
        print(f"page: {d.get('page')}")
        print(f"page_size: {d.get('page_size')}")

        print(f"\nfilters 数量: {len(d.get('filters', []))}")
        if d.get('filters'):
            print("\nfilters 内容:")
            print(json.dumps(d['filters'], indent=2, ensure_ascii=False))

        if d.get('items') and len(d['items']) > 0:
            print("\n\n第一行数据:")
            print(json.dumps(d['items'][0], indent=2, ensure_ascii=False))

if __name__ == '__main__':
    check_api()