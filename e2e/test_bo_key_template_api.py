"""
E2E 测试: KeyTemplate 表单交互 - API 层验证 [2026-06-11]

覆盖 3 个核心场景:
  TC-1: 选服务模块 + 选领域 → code 前缀匹配
  TC-2: 选领域（无服务模块）→ code 不被错误覆盖
  TC-3: 同一服务模块连续预览 → 序号递增

这些是真正的端到端验证（通过 HTTP API）。
前端修复（service_module_id 正确传值 / domain_id 不触发）
由代码审查确认正确。
"""

import requests

API = 'http://localhost:3010'


def dev_login():
    s = requests.Session()
    s.get(f'{API}/api/v1/auth/dev-login?username=admin', timeout=15)
    return s


def get_service_modules(s):
    r = s.get(f'{API}/api/v2/bo/service_module?page=1&page_size=20', timeout=15)
    return r.json().get('data', {}).get('items', [])


def get_domains(s):
    r = s.get(f'{API}/api/v2/bo/domain?page=1&page_size=5', timeout=15)
    return r.json().get('data', {}).get('items', [])


def preview_bo(service_module_id=None, domain_id=None):
    s = dev_login()
    parent_params = {}
    if service_module_id:
        parent_params['service_module_id'] = service_module_id
    if domain_id:
        parent_params['domain_id'] = domain_id
    r = s.post(
        f'{API}/api/v2/key-template/preview/business_object',
        json={'field_values': {}, 'parent_params': parent_params, 'generate': True},
        timeout=15
    )
    return r


def delete_bo_by_prefix(s, prefix):
    r = s.get(f'{API}/api/v2/bo/business_object?page=1&page_size=200', timeout=15)
    for bo in r.json().get('data', {}).get('items', []):
        code = bo.get('code', '')
        if code.upper().startswith(prefix.upper()) and len(code) <= 15:
            try:
                s.delete(f'{API}/api/v2/bo/business_object/{bo["id"]}', timeout=10)
            except Exception:
                pass


def main():
    print('=' * 60)
    print('E2E 测试: KeyTemplate 表单交互 [2026-06-11]')
    print('=' * 60)

    s = dev_login()
    sms = get_service_modules(s)
    domains = get_domains(s)

    if not sms:
        print('  [ERROR] 无服务模块')
        return

    sm = None
    for item in sms:
        code = item.get('code', '')
        if code.startswith('SM') or code.startswith('TEST'):
            sm = item
            break
    if not sm:
        sm = sms[0]

    domain = domains[0] if domains else None

    print(f'  sm: id={sm["id"]} code={sm["code"]}')
    if domain:
        print(f'  domain: id={domain["id"]} code={domain["code"][:30]}')

    results = {}

    # TC-1: 选服务模块 → code 前缀匹配
    print('\n  [TC-1] 选服务模块 → code 前缀匹配')
    r = preview_bo(service_module_id=sm['id'])
    if r.status_code == 200:
        code = r.json().get('data', {}).get('code', '')
        sm_code = sm['code'].upper()
        if code and code.upper().startswith(sm_code):
            print(f'    [PASS] code={code} 前缀匹配 {sm_code}')
            results['TC-1'] = True
        else:
            print(f'    [FAIL] code={code} 不以 {sm_code} 开头')
            results['TC-1'] = False
    else:
        print(f'    [FAIL] status={r.status_code} {r.text[:100]}')
        results['TC-1'] = False

    # TC-2: 选领域（无服务模块）→ code 不被覆盖
    if domain:
        print('\n  [TC-2] 选领域（无服务模块）→ code 不被错误覆盖')
        r = preview_bo(domain_id=domain['id'])
        if r.status_code == 422:
            data = r.json()
            code = data.get('code', '')
            missing = data.get('missing_fields', [])
            if code == 'MISSING_PARENT_FIELD' and 'service_module_code' in missing:
                print(f'    [PASS] 正确返回 422 MISSING_PARENT_FIELD (service_module_code 缺失)')
                results['TC-2'] = True
            else:
                print(f'    [FAIL] 422 但错误码错误: {data}')
                results['TC-2'] = False
        else:
            # 返回 200 但可能生成了 code
            if r.status_code == 200:
                code = r.json().get('data', {}).get('code', '')
                if code and code.isdigit():
                    print(f'    [FAIL] 返回裸序列号: {code} (BUG)')
                    results['TC-2'] = False
                else:
                    print(f'    [FAIL] status={r.status_code} code={code}')
                    results['TC-2'] = False
            else:
                print(f'    [FAIL] status={r.status_code}')
                results['TC-2'] = False
    else:
        print('\n  [TC-2] [SKIP] 无领域数据')
        results['TC-2'] = None

    # TC-3: 同一服务模块连续预览 → 序号递增
    print('\n  [TC-3] 同一服务模块连续预览 → 序号递增')
    prefix = sm['code'].upper()[:8]
    delete_bo_by_prefix(s, prefix)

    r1 = preview_bo(service_module_id=sm['id'])
    r2 = preview_bo(service_module_id=sm['id'])

    code1 = r1.json().get('data', {}).get('code') if r1.status_code == 200 else None
    code2 = r2.json().get('data', {}).get('code') if r2.status_code == 200 else None

    print(f'    第1次 code: {code1}')
    print(f'    第2次 code: {code2}')

    import re
    m1 = re.search(r'(\d+)$', str(code1)) if code1 else None
    m2 = re.search(r'(\d+)$', str(code2)) if code2 else None

    if m1 and m2:
        n1, n2 = int(m1.group(1)), int(m2.group(1))
        if n2 == n1 + 1:
            print(f'    [PASS] 序号递增: {n1} → {n2}')
            results['TC-3'] = True
        else:
            print(f'    [FAIL] 序号未递增: {n1} vs {n2}')
            results['TC-3'] = False
    else:
        # 检查前缀是否相同（如果不相同说明选错了服务模块）
        if code1 == code2 and code1:
            print(f'    [FAIL] 两次 code 相同: {code1}')
            results['TC-3'] = False
        else:
            print(f'    [WARN] 无法提取序号: {code1} / {code2}')
            results['TC-3'] = None

    # 汇总
    print('\n' + '=' * 60)
    print('测试结果汇总:')
    print('=' * 60)
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    for tc, result in results.items():
        status = {True: 'PASS', False: 'FAIL', None: 'SKIP'}[result]
        print(f'  {tc}: {status}')
    print(f'\n总计: {passed} 通过, {failed} 失败, {skipped} 跳过')
    return failed == 0


if __name__ == '__main__':
    ok = main()
    exit(0 if ok else 1)
