"""
E2E 测试: 创建 annotation 备注 → 验证 domain 详情页操作日志 tab 能看到
"""
import requests
import time

r = requests.post('http://localhost:3010/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
cookies = {'auth_token': r.json()['data']['token']}
print(f'Login: {r.status_code}')

# 1. 创建 annotation 备注 (target=domain, target_id=683)
ts = int(time.time())
print(f'\n=== 1. Create annotation (target=domain/683) ===')
r = requests.post('http://localhost:3010/api/v1/annotations',
    cookies=cookies,
    json={
        'target_type': 'domain',
        'target_id': 683,
        'category': 'info',
        'content': f'TEST_ANNOT_{ts}: 备注测试'
    },
    timeout=5)
print(f'  status: {r.status_code}')
if r.status_code == 201:
    ann_id = r.json()['data']['id']
    print(f'  annotation_id: {ann_id}')
else:
    print(f'  body: {r.text[:300]}')
    ann_id = None

# 2. 验证 audit_logs 表 (应当有 annotation 创建记录, parent_object_type=domain, parent_object_id=683)
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("""
    SELECT id, object_type, object_id, action, parent_object_type, parent_object_id
    FROM audit_logs
    WHERE object_type = 'annotation' AND object_id = ?
    ORDER BY id DESC LIMIT 1
""", (ann_id,))
row = cur.fetchone()
print(f'\n=== 2. DB audit_log for annotation/{ann_id} ===')
print(f'  id={row[0]} object_type={row[1]} object_id={row[2]} action={row[3]} parent_type={row[4]} parent_id={row[5]}')
conn.close()

# 3. 验证 /audit/logs 端点能否找到 (通过 OR 联合)
print(f'\n=== 3. /audit/logs API check (domain/683 + parent=683) ===')
r = requests.get(f'http://localhost:3010/api/v1/audit/logs?object_type=domain&object_id=683&parent_object_id=683&page=1&page_size=20', cookies=cookies, timeout=5)
data = r.json()
items = data.get('data', [])
print(f'  total={data.get("total")} items={len(items)}')
for it in items[:3]:
    print(f'    [{it["id"]}] {it["action"]:7s} {it["object_type"]:15s} {it["object_id"]} biz={it["business_key"]}')

# 4. 更新 annotation
print(f'\n=== 4. Update annotation {ann_id} ===')
r = requests.put(f'http://localhost:3010/api/v1/annotations/{ann_id}',
    cookies=cookies,
    json={'content': f'UPDATED_ANNOT_{ts}: 备注更新'},
    timeout=5)
print(f'  status: {r.status_code}')

# 5. 删除 annotation
print(f'\n=== 5. Delete annotation {ann_id} ===')
r = requests.delete(f'http://localhost:3010/api/v1/annotations/{ann_id}', cookies=cookies, timeout=5)
print(f'  status: {r.status_code}')

# 6. 再次验证 audit_logs (应当有 3 条: CREATE/UPDATE/DELETE)
print(f'\n=== 6. Final audit log check for annotation ===')
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("""
    SELECT id, object_type, object_id, action, parent_object_type, parent_object_id
    FROM audit_logs
    WHERE object_type = 'annotation' AND object_id = ?
    ORDER BY id
""", (ann_id,))
for row in cur.fetchall():
    print(f'  id={row[0]} action={row[3]:7s} parent_type={row[4]:15s} parent_id={row[5]}')
conn.close()
