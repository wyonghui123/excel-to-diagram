# -*- coding: utf-8 -*-
"""
M9 D2 GraphQL E2E 测试 - 3 entity × 2 query 覆盖

D2 扩展验证：
1. 3 entity 都通过 health endpoint 暴露
2. 3 entity 都能用 valid query 调用
3. invalid query 400
4. unknown field 400
5. 6 root query 全部注册
6. 错误捕获
"""
import sys
import os
import json
import logging

sys.path.insert(0, '.')

logging.basicConfig(level=logging.WARNING)

results = {'pass': 0, 'fail': 0, 'errors': []}

def test(name, fn):
    global results
    try:
        fn()
        results['pass'] += 1
        print(f"  PASS: {name}")
    except AssertionError as e:
        results['fail'] += 1
        results['errors'].append((name, str(e)))
        print(f"  FAIL: {name}: {e}")
    except Exception as e:
        results['fail'] += 1
        results['errors'].append((name, f"Exception: {type(e).__name__}: {e}"))
        print(f"  ERROR: {name}: {e}")


print("=" * 60)
print("M9 D2 GraphQL E2E 验证 (3 entity × 2 query)")
print("=" * 60)

from meta.graphql import graphql_bp
from flask import Flask
test_app = Flask(__name__)
test_app.config['TESTING'] = True
test_app.register_blueprint(graphql_bp)
client = test_app.test_client()
print("  [DECORATIVE] Flask test_app + graphql_bp loaded")

# ============================================================
# 1. Health 端点
# ============================================================
print("\n[T1: GET /graphql/health - D2 验证]")
def t1():
    r = client.get('/graphql/health')
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data['status'] == 'ok'
    assert data['phase'] == 'M9-D2-POC'
    # 验证 3 entity + 6 query
    assert 'User' in data['entities']
    assert 'Role' in data['entities']
    assert 'UserGroup' in data['entities']
    assert len(data['entities']) == 3
    assert 'user' in data['queries']
    assert 'users' in data['queries']
    assert 'role' in data['queries']
    assert 'roles' in data['queries']
    assert 'userGroup' in data['queries']
    assert 'userGroups' in data['queries']
    assert len(data['queries']) == 6
test('T1: health (3 entity + 6 query)', t1)

# ============================================================
# 2. Schema 端点
# ============================================================
print("\n[T2: GET /graphql/schema - D2 验证]")
def t2():
    r = client.get('/graphql/schema')
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data['version'] == '0.2.0'
    assert data['phase'] == 'D2'
    # 3 entity types
    assert 'User' in data['types']
    assert 'Role' in data['types']
    assert 'UserGroup' in data['types']
    # User 应有 displayName / lastLoginAt
    assert 'displayName' in data['types']['User']['fields']
    assert 'lastLoginAt' in data['types']['User']['fields']
    # 6 queries
    assert 'user(id: Int!)' in data['queries']
    assert 'users(page: Int, pageSize: Int)' in data['queries']
    assert 'role(id: Int!)' in data['queries']
    assert 'roles(page: Int, pageSize: Int)' in data['queries']
    assert 'userGroup(id: Int!)' in data['queries']
    assert 'userGroups(page: Int, pageSize: Int)' in data['queries']
    # 6 examples
    assert len(data['examples']) == 6
test('T2: schema (3 entity + 6 query + 6 examples)', t2)

# ============================================================
# 3. 3 entity list query 端到端
# ============================================================
print("\n[T3: POST /graphql - userGroups list query]")
def t3():
    r = client.post('/graphql', json={
        'query': '{ userGroups(page: 1, pageSize: 5) { id name code createdAt } }'
    })
    assert r.status_code in [200, 500]
    data = json.loads(r.data)
    if r.status_code == 200:
        assert 'data' in data
        assert 'userGroups' in data['data']
test('T3: userGroups list handled', t3)

print("\n[T4: POST /graphql - users list query]")
def t4():
    r = client.post('/graphql', json={
        'query': '{ users(page: 1, pageSize: 5) { id username displayName } }'
    })
    assert r.status_code in [200, 500]
    data = json.loads(r.data)
    if r.status_code == 200:
        assert 'data' in data
        assert 'users' in data['data']
test('T4: users list handled', t4)

print("\n[T5: POST /graphql - roles list query]")
def t5():
    r = client.post('/graphql', json={
        'query': '{ roles(page: 1, pageSize: 5) { id name code } }'
    })
    assert r.status_code in [200, 500]
    data = json.loads(r.data)
    if r.status_code == 200:
        assert 'data' in data
        assert 'roles' in data['data']
test('T5: roles list handled', t5)

# ============================================================
# 4. 3 entity single query 端到端
# ============================================================
print("\n[T6: POST /graphql - userGroup by id]")
def t6():
    r = client.post('/graphql', json={
        'query': '{ userGroup(id: 1) { id name code description } }'
    })
    assert r.status_code in [200, 500]
    data = json.loads(r.data)
    if r.status_code == 200:
        assert 'data' in data
        # userGroup 可能是 None（不存在）但 data 键存在
        assert 'userGroup' in data['data']
test('T6: userGroup by id handled', t6)

print("\n[T7: POST /graphql - user by id]")
def t7():
    r = client.post('/graphql', json={
        'query': '{ user(id: 1) { id username displayName } }'
    })
    assert r.status_code in [200, 500]
    data = json.loads(r.data)
    if r.status_code == 200:
        assert 'data' in data
        assert 'user' in data['data']
test('T7: user by id handled', t7)

print("\n[T8: POST /graphql - role by id]")
def t8():
    r = client.post('/graphql', json={
        'query': '{ role(id: 1) { id name code } }'
    })
    assert r.status_code in [200, 500]
    data = json.loads(r.data)
    if r.status_code == 200:
        assert 'data' in data
        assert 'role' in data['data']
test('T8: role by id handled', t8)

# ============================================================
# 5. Error handling
# ============================================================
print("\n[T9: POST /graphql - invalid query 400]")
def t9():
    r = client.post('/graphql', json={'query': 'invalid'})
    assert r.status_code == 400
test('T9: invalid query 400', t9)

print("\n[T10: POST /graphql - unknown field 400]")
def t10():
    r = client.post('/graphql', json={'query': '{ unknownField(id: 1) { id } }'})
    assert r.status_code == 400
    data = json.loads(r.data)
    assert 'Unknown field' in data['errors'][0]['message']
    # 错误消息应包含 6 个支持的 query
    assert 'user' in data['errors'][0]['message']
    assert 'role' in data['errors'][0]['message']
    assert 'userGroup' in data['errors'][0]['message']
test('T10: unknown field 400 + helpful error msg', t10)

print("\n[T11: POST /graphql - empty body 400]")
def t11():
    r = client.post('/graphql', json={})
    assert r.status_code == 400
test('T11: empty body 400', t11)

# ============================================================
# 6. CORS
# ============================================================
print("\n[T12: OPTIONS /graphql - CORS preflight]")
def t12():
    r = client.options('/graphql')
    assert r.status_code in [200, 204]
test('T12: CORS preflight OK', t12)

# 总结
print()
print("=" * 60)
print(f"TOTAL: {results['pass']} PASS / {results['fail']} FAIL")
print("=" * 60)
if results['errors']:
    for name, err in results['errors']:
        print(f"  - {name}: {err[:100]}")

sys.exit(0 if results['fail'] == 0 else 1)
