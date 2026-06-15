"""Reproduce: PROC_REQ_MNG 已存在 PROC_REQ_MNG01, 新建应建议 PROC_REQ_MNG02"""
import requests

API = 'http://localhost:3010'
s = requests.Session()
s.get(f'{API}/api/v1/auth/dev-login?username=admin', timeout=15)

# PROC_REQ_MNG service module
r = s.get(f'{API}/api/v2/bo/service_module?page=1&page_size=30', timeout=15)
sms = r.json().get('data', {}).get('items', [])

proc_req_mng = None
for sm in sms:
    if sm.get('code') == 'PROC_REQ_MNG':
        proc_req_mng = sm
        break

if not proc_req_mng:
    print("没找到 PROC_REQ_MNG 服务模块")
    raise SystemExit(1)

sm_id = proc_req_mng['id']
print(f"PROC_REQ_MNG: id={sm_id}")

# 列出该 SM 下所有 BO
r = s.get(f'{API}/api/v2/bo/business_object?page=1&page_size=200', timeout=15)
bos = r.json().get('data', {}).get('items', [])
existing = []
for bo in bos:
    if bo.get('service_module_id') == sm_id:
        existing.append(bo.get('code'))
print(f"\n该 SM 下已有 BO: {existing}")

# 预览 (不消耗序列)
r = s.post(
    f'{API}/api/v2/key-template/preview/business_object',
    json={
        'field_values': {},
        'parent_params': {'service_module_id': sm_id},
        'generate': False,
    },
    timeout=15
)
print(f"\n预览 status: {r.status_code}")
print(f"预览 body: {r.text[:300]}")
if r.status_code == 200:
    code = r.json().get('data', {}).get('code', '')
    print(f"\n建议 code: {code}")
    # 检查是否为 PROC_REQ_MNG01（应递增为 02）
    if code == 'PROC_REQ_MNG01':
        print(f"  [BUG] 建议了 PROC_REQ_MNG01（已有重复）")
    elif code.endswith('02'):
        print(f"  [OK] 建议了下一个序号")
    else:
        print(f"  [?] 建议了 {code}")