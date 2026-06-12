"""V1 Cleanup 完整回归测试 - admin login + role CRUD"""
import requests
import time

s = requests.Session()
BASE = 'http://localhost:3010/api/v1'

results = []
def test(name, fn):
    try:
        r = fn()
        ok = 200 <= r.status_code < 300
        msg = r.text[:100] if not ok else 'OK'
        results.append((name, r.status_code, ok, msg))
        marker = '[OK]' if ok else '[FAIL]'
        print(f'  {marker} {name}: {r.status_code} - {msg}')
    except Exception as e:
        results.append((name, 0, False, str(e)[:80]))
        print(f'  [FAIL] {name}: EXCEPTION - {str(e)[:80]}')

print('=== V1 Cleanup 完整回归 ===')

# 1. dev-login
test('1. dev-login', lambda: s.get(f'{BASE}/auth/dev-login?username=admin', timeout=10))

# 2. /auth/me
def me():
    r = s.get(f'{BASE}/auth/me', timeout=10)
    d = r.json().get('data', {})
    assert d.get('is_admin') is True, 'is_admin should be True'
    assert 'is_super_admin' not in d, 'is_super_admin should NOT be in response'
    return r
test('2. /auth/me (is_admin=True, no is_super_admin)', me)

# 3. list roles
def list_roles():
    r = s.get(f'{BASE}/roles', timeout=15)
    roles = r.json().get('data', [])
    for x in roles:
        assert 'is_super_admin' not in x, f'role {x.get("code")} has is_super_admin'
        assert 'priority' not in x, f'role {x.get("code")} has priority'
    return r
test('3. GET /roles (no is_super_admin/priority)', list_roles)

# 4-7. create + read + update + delete
new_id = None
def create():
    global new_id
    code = f'v1reg_{int(time.time())}'
    r = s.post(f'{BASE}/roles', json={'code': code, 'name': 'V1 Reg', 'description': 'regression'}, timeout=10)
    if r.status_code == 201:
        new_id = r.json().get('data', {}).get('id')
    return r
test('4. POST /roles', create)

def read_one():
    assert new_id, 'no role created'
    return s.get(f'{BASE}/roles/{new_id}', timeout=10)
test('5. GET /roles/<id>', read_one)

def update():
    assert new_id
    return s.put(f'{BASE}/roles/{new_id}', json={'name': 'V1 Reg Updated'}, timeout=10)
test('6. PUT /roles/<id>', update)

def delete():
    assert new_id
    return s.delete(f'{BASE}/roles/{new_id}', timeout=10)
test('7. DELETE /roles/<id>', delete)

# Summary
passed = sum(1 for _, _, ok, _ in results if ok)
total = len(results)
print()
print(f'=== 总计: {passed}/{total} 通过 ===')
exit(0 if passed == total else 1)
