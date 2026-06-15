# -*- coding: utf-8 -*-
"""完整流程：preview → save (重复创建场景)"""
import sys, os, re
sys.path.insert(0, r'd:\filework\excel-to-diagram')
import requests, time

BASE = 'http://localhost:3010'
s = requests.Session()

# 1. 登录
r = s.get(f'{BASE}/api/v1/auth/dev-login?username=admin')
print(f'[LOGIN] {r.status_code}')

# 2. 找 BO_SUPPLIER 和 BO_LOCATION（分页查询）
all_items = []
page = 1
while True:
    r = s.get(f'{BASE}/api/v2/bo/business_object?page={page}&page_size=100')
    data = r.json()
    items = data.get('data', {}).get('items', data.get('data', []))
    if not items:
        break
    all_items.extend(items)
    if len(items) < 100:
        break
    page += 1
print(f'[BO] total={len(all_items)}')
supplier = next((b for b in all_items if b.get('code') == 'BO_SUPPLIER'), None)
location = next((b for b in all_items if b.get('code') == 'BO_LOCATION'), None)
print(f'BO_SUPPLIER: id={supplier["id"]} code={supplier["code"]}')
print(f'BO_LOCATION: id={location["id"]} code={location["code"]}')

# 找 version
r = s.get(f'{BASE}/api/v2/bo/version?page_size=10')
data = r.json()
versions = data.get('data', {}).get('items', data.get('data', []))
version_id = versions[0]['id'] if versions else 1
print(f'version_id={version_id}')

# 3. 清理之前测试残留：删除所有 BO_SUPPLIER->BO_LOCATION 的关系
r = s.get(f'{BASE}/api/v2/bo/relationship?page_size=200')
data = r.json()
items = data.get('data', {}).get('items', data.get('data', []))
existing = [r2 for r2 in items
            if str(r2.get('source_bo_id')) == str(supplier['id'])
            and str(r2.get('target_bo_id')) == str(location['id'])]
print(f'\n[EXISTING] {len(existing)}')
for r2 in existing:
    s.delete(f'{BASE}/api/v2/bo/relationship/{r2["id"]}')
    print(f'  DELETED id={r2["id"]} code={r2.get("code")}')

# 4. 创建第一条关系
r = s.post(f'{BASE}/api/v2/bo/relationship', json={
    'version_id': version_id,
    'source_bo_id': supplier['id'],
    'target_bo_id': location['id'],
    'relation_type': f'TEST_{int(time.time())}',
    'description': 'Repro_第1条'
})
print(f'\n[CREATE 1] status={r.status_code} body={r.text[:300]}')

# 5. 验证第一条 code
r = s.get(f'{BASE}/api/v2/bo/relationship?page_size=200')
data = r.json()
items = data.get('data', {}).get('items', data.get('data', []))
existing = [r2 for r2 in items
            if str(r2.get('source_bo_id')) == str(supplier['id'])
            and str(r2.get('target_bo_id')) == str(location['id'])]
print(f'\n[EXISTING after create 1]')
for r2 in existing:
    print(f'  id={r2["id"]} code={r2.get("code")} type={r2.get("relation_type")}')

# 6. 创建第二条（应该自动递增为 02）
r = s.post(f'{BASE}/api/v2/bo/relationship', json={
    'version_id': version_id,
    'source_bo_id': supplier['id'],
    'target_bo_id': location['id'],
    'relation_type': f'TEST_{int(time.time())}_2',
    'description': 'Repro_第2条'
})
print(f'\n[CREATE 2] status={r.status_code} body={r.text[:300]}')

# 7. 验证第二条 code
r = s.get(f'{BASE}/api/v2/bo/relationship?page_size=200')
data = r.json()
items = data.get('data', {}).get('items', data.get('data', []))
existing = [r2 for r2 in items
            if str(r2.get('source_bo_id')) == str(supplier['id'])
            and str(r2.get('target_bo_id')) == str(location['id'])]
print(f'\n[EXISTING after create 2]')
for r2 in existing:
    print(f'  id={r2["id"]} code={r2.get("code")} type={r2.get("relation_type")}')

# 验证两个 code 不同且序号递增
codes = sorted([r2.get('code', '') for r2 in existing])
print(f'\n[ALL CODES] {codes}')

if len(codes) >= 2:
    nums = [int(re.search(r'-(\d+)$', c).group(1)) for c in codes]
    if nums == sorted(set(nums)) and len(nums) == 2 and nums[1] - nums[0] == 1:
        print(f'PASS: 自增正确 {nums[0]} -> {nums[1]}')
    else:
        print(f'FAIL: 序号错误 {nums}')