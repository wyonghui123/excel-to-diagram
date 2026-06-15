"""H11.1 e2e 测试: 多 role always_true 占位修复

场景: TEST333 (id=3385) 配 role 5434 (无 dim scope) + role 5970 (dim scope product=[475]+domain=[1,703])
       这就是 user 实际场景: 产品 read + 采购管理编辑

验证:
- 修复前 (v1.0.5): TEST333 看到 5 个 product (自己 owned) — dim scope 卡死
- 修复后 (v1.0.6): TEST333 看到 7 个 product — 包含 vis=public 的他人产品 (19, 16)

475 (供应链管理) 仍看不到 — 因为它是脏数据 (vis=None, owner=None). 这是数据问题, 不是代码问题.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
import requests


BASE_URL = 'http://localhost:3010'
DB_PATH = 'd:/filework/excel-to-diagram/meta/architecture.db'


def setup_test333_roles(conn, user_id, group_id=8100):
    """确保 TEST333 跟 role 5434, 5970 关联 (user 实际配置)"""
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO user_groups (id, name, code) VALUES (?, ?, ?)", (group_id, 'TEST333_H11_GROUP', 'TEST333_H11_GROUP'))
    cur.execute("INSERT OR REPLACE INTO group_roles (group_id, role_id) VALUES (?, ?)", (group_id, 5434))
    cur.execute("INSERT OR REPLACE INTO group_roles (group_id, role_id) VALUES (?, ?)", (group_id, 5970))
    cur.execute("INSERT OR REPLACE INTO user_group_members (user_id, group_id, is_manager) VALUES (?, ?, 0)", (user_id, group_id))
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    user_id = 3385  # TEST333

    # 备份原 user_group
    backup = list(conn.execute('SELECT * FROM user_group_members WHERE user_id=?', (user_id,)))
    print(f'Backup: TEST333 has {len(backup)} user_group links')

    try:
        # 配 TEST333 跟 role 5434 (无 dim scope) + 5970 (有 dim scope)
        # (user 实际场景)
        setup_test333_roles(conn, user_id)

        # 验证 user_group 链路
        roles = list(conn.execute('''
            SELECT gr.role_id FROM group_roles gr
            JOIN user_group_members ugm ON ugm.group_id = gr.group_id
            WHERE ugm.user_id=?
        ''', (user_id,)))
        print(f'TEST333 roles: {[r[0] for r in roles]}')

        # dev-login
        s = requests.Session()
        r = s.get(f'{BASE_URL}/api/v1/auth/dev-login?username=TEST333', allow_redirects=True)
        assert r.status_code == 200

        # 跑 product list
        r = s.get(f'{BASE_URL}/api/v2/bo/product?page=1&page_size=100')
        assert r.status_code == 200, f'product list failed: {r.status_code} {r.text[:200]}'
        data = r.json()
        items = data.get('data', {}).get('items', [])
        total = data.get('data', {}).get('total', '?')
        ids = sorted([p['id'] for p in items])

        print()
        print(f'=== TEST333 product list ===')
        print(f'  total={total}')
        print(f'  ids={ids}')

        # 验证修复生效
        print()
        print('=== 验证 v1.0.6 always_true 占位修复 ===')

        # TEST333 应该看到自己 owned 的 5 个 product
        owned_ids = [322, 323, 335, 473, 476]
        for oid in owned_ids:
            if oid in ids:
                print(f'  [OK] owned product {oid} visible')
            else:
                print(f'  [FAIL] owned product {oid} NOT visible')

        # TEST333 应该看到 vis=public 的他人产品 19, 16 (v1.0.6 修复后)
        # 修复前 (v1.0.5): role 5434 无 dim scope 派生被吞, 整体被 role 5970 dim scope (1, 475) 卡死
        # 修复后 (v1.0.6): role 5434 派生 always_true, 多 role OR-of-AND = 1=1, vis scope 生效
        public_ids = [19, 16]
        for pid in public_ids:
            if pid in ids:
                print(f'  [OK] vis=public product {pid} visible (v1.0.6 修复生效)')
            else:
                print(f'  [WARN] vis=public product {pid} NOT visible (v1.0.6 修复可能没生效)')

        # 475 (供应链管理) 因为是脏数据 (vis=None, owner=None) 看不到
        # 这是数据问题, 不是代码问题
        if 475 not in ids:
            print(f'  [INFO] 475 (供应链管理) 看不到, 因为是脏数据 (vis=None, owner=None)')

        # 断言: 至少 5 个 owned + 2 个 public = 7 个
        expected = sorted(owned_ids + public_ids)
        actual_visible = [i for i in expected if i in ids]
        if len(actual_visible) == 7:
            print()
            print('  [PASS] TEST333 看到 7 个 product (5 owned + 2 public), v1.0.6 修复生效')
            return 0
        else:
            print()
            print(f'  [PARTIAL] TEST333 只看到 {len(actual_visible)}/7 个 product')
            return 1

    finally:
        # 恢复
        cur = conn.cursor()
        cur.execute("DELETE FROM user_group_members WHERE user_id=?", (user_id,))
        for b in backup:
            cur.execute("INSERT INTO user_group_members (id, user_id, group_id, is_manager, joined_at) VALUES (?, ?, ?, ?, ?)", b)
        conn.commit()
        print()
        print('  [Cleanup] TEST333 user_group restored')


if __name__ == '__main__':
    import sys
    sys.exit(main())
