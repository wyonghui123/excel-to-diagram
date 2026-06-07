import urllib.request
import json

tests = [
    ("虚拟字段 domain_name", "http://localhost:5000/api/v1/service_module?page=1&page_size=5&sort_by=domain_name&sort_order=asc"),
    ("物理字段 name", "http://localhost:5000/api/v1/service_module?page=1&page_size=5&sort_by=name&sort_order=asc"),
    ("虚拟字段 sub_domain_name", "http://localhost:5000/api/v1/service_module?page=1&page_size=5&sort_by=sub_domain_name&sort_order=desc"),
]

for name, url in tests:
    print(f"\n测试: {name}")
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode())
            items = data.get('data', [])
            print(f"  [OK] 状态码 200, 返回 {len(items)} 条记录")
    except urllib.error.HTTPError as e:
        print(f"  [X] HTTP {e.code}: {e.read().decode()[:100]}")
    except Exception as ex:
        print(f"  [X] 错误: {ex}")

# 清理
import os
for f in ['check_vsort.py', 'fix_enum.py']:
    if os.path.exists(f):
        os.remove(f)
