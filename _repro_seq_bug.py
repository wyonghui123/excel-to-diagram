"""Reproduce: PROC_REQ_MNG01 已存在，新建建议却是 PROC_REQ_MNG01"""
import requests

API = 'http://localhost:3010'
s = requests.Session()
s.get(f'{API}/api/v1/auth/dev-login?username=admin', timeout=15)

# 找一个存在旧 BO 的服务模块
r = s.get(f'{API}/api/v2/bo/business_object?page=1&page_size=200', timeout=15)
bos = r.json().get('data', {}).get('items', [])
print("已有 BO 列表:")
for bo in bos[:10]:
    print(f"  code={bo.get('code', '')[:20]} name={bo.get('name', '')[:20]} sm_id={bo.get('service_module_id')}")

# 找第一个有旧 BO 的服务模块
sm_id = None
sm_code = None
target_sm_with_max = None
max_seq = 0
for bo in bos:
    code = bo.get('code', '')
    sm_id_bo = bo.get('service_module_id')
    # 提取数字部分
    import re
    m = re.search(r'(\d+)$', code)
    if m:
        seq = int(m.group(1))
        if seq > max_seq:
            max_seq = seq
            target_sm_with_max = (sm_id_bo, code)

print(f"\n最高序号 BO: {target_sm_with_max}")

# 找对应的服务模块
if target_sm_with_max:
    sm_id = target_sm_with_max[0]
    r = s.get(f'{API}/api/v2/bo/service_module/{sm_id}', timeout=15)
    if r.status_code == 200:
        sm_code = r.json().get('data', {}).get('code', '')
        print(f"服务模块: id={sm_id} code={sm_code}")
        print(f"该 SM 下最大序号: {max_seq} (应建议 {sm_code}{max_seq+1:02d})")

        # 测试 preview
        r = s.post(
            f'{API}/api/v2/key-template/preview/business_object',
            json={
                'field_values': {},
                'parent_params': {'service_module_id': sm_id},
                'generate': False,  # 不消耗
            },
            timeout=15
        )
        if r.status_code == 200:
            code = r.json().get('data', {}).get('code', '')
            print(f"\n预览建议 code: {code}")
            print(f"  期望: {sm_code}{max_seq+1:02d} (下一个序号)")
            print(f"  实际: {code}")
            if code.endswith(f"{max_seq+1:02d}"):
                print(f"  [PASS]")
            else:
                print(f"  [FAIL] 序号不递增!")
        else:
            print(f"Preview status: {r.status_code} {r.text[:200]}")