"""H13 e2e: TEST333 改 475 (供应链管理系统, owner=admin) 应该被拒
预期: 改 475 失败 (403), 改 476 (TEST333 owned) 成功 (200)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
import requests
import json

BASE_URL = 'http://localhost:3010'
DB_PATH = 'd:/filework/excel-to-diagram/meta/architecture.db'

def setup_link(conn, user_id, group_id=8100):
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO user_groups (id, name, code) VALUES (?, ?, ?)", (group_id, 'TEST333_H11_GROUP', 'TEST333_H11_GROUP'))
    cur.execute("INSERT OR REPLACE INTO group_roles (group_id, role_id) VALUES (?, ?)", (group_id, 5434))
    cur.execute("INSERT OR REPLACE INTO group_roles (group_id, role_id) VALUES (?, ?)", (group_id, 5970))
    cur.execute("INSERT OR REPLACE INTO user_group_members (user_id, group_id, is_manager) VALUES (?, ?, 0)", (user_id, group_id))
    conn.commit()

conn = sqlite3.connect(DB_PATH, timeout=10)
user_id = 3385  # TEST333

# backup + link
backup = list(conn.execute('SELECT * FROM user_group_members WHERE user_id=?', (user_id,)))
setup_link(conn, user_id)

try:
    # 看 475 实际状态 (修复后 owner=admin, vis=public)
    cur = conn.cursor()
    print('=== 475 当前 ===')
    for r in cur.execute('SELECT id, name, owner_id, visibility, updated_at FROM products WHERE id=475'):
        print(f'  id={r[0]} name={r[1]!r} owner={r[2]} vis={r[3]!r} updated={r[4]}')

    # dev-login
    s = requests.Session()
    r = s.get(f'{BASE_URL}/api/v1/auth/dev-login?username=TEST333', allow_redirects=True)
    print('login:', r.status_code)

    # TEST333 改 475 (供应链管理系统, owner=admin) — 期望 403
    print()
    print('=== TEST333 改 product 475 (owner=admin, 期望 403) ===')
    original_name = '供应链管理系统'
    new_name = 'H13_TEST_UPDATE_475'
    r = s.put(f'{BASE_URL}/api/v2/bo/product/475', json={
        'name': new_name,
        '_change_reason': 'H13 e2e test (should be rejected)',
    })
    print(f'PUT 475 status: {r.status_code}')
    print(f'PUT 475 response (top 300): {r.text[:300]}')

    # 验证 475 是否真的被改
    print()
    print('=== 改后 475 状态 ===')
    for r in cur.execute('SELECT id, name, owner_id, visibility, updated_at FROM products WHERE id=475'):
        print(f'  id={r[0]} name={r[1]!r} owner={r[2]} vis={r[3]!r} updated={r[4]}')
        if r[1] == new_name:
            print('  [BUG] 475 被改了! WriteScopeInterceptor 没拒绝!')
        else:
            print('  [OK] 475 没被改 (要么被拒要么没生效)')

    # TEST333 改 476 (TEST333 owned) — 期望 200
    print()
    print('=== TEST333 改 product 476 (TEST333 owned, 期望 200) ===')
    for r in cur.execute('SELECT name FROM products WHERE id=476'):
        original_476 = r[0]
    r = s.put(f'{BASE_URL}/api/v2/bo/product/476', json={
        'description': f'H13 e2e test (allowed) - {original_476}',
        '_change_reason': 'H13 e2e test (should be allowed)',
    })
    print(f'PUT 476 status: {r.status_code}')
    print(f'PUT 476 response (top 200): {r.text[:200]}')

    # 恢复 476
    s2 = requests.Session()
    s2.get(f'{BASE_URL}/api/v1/auth/dev-login?username=admin', allow_redirects=True)
    r = s2.put(f'{BASE_URL}/api/v2/bo/product/476', json={
        'description': '',
        '_change_reason': 'H13 e2e cleanup',
    })
    print(f'admin reset 476 status: {r.status_code}')

finally:
    # 恢复 TEST333 user_group
    cur = conn.cursor()
    cur.execute("DELETE FROM user_group_members WHERE user_id=?", (user_id,))
    for b in backup:
        cur.execute("INSERT INTO user_group_members (id, user_id, group_id, is_manager, joined_at) VALUES (?, ?, ?, ?, ?)", b)
    conn.commit()
    print()
    print('[Cleanup] TEST333 user_group restored')
