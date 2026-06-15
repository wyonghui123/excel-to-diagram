# -*- coding: utf-8 -*-
"""Verify TEST607777 owner_id and current dimension scope filter behavior"""
import sqlite3
import sys

DB = r'd:\filework\excel-to-diagram\meta\architecture.db'

def main():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    print('=' * 70)
    print('1. Find TEST607777 in versions table')
    print('=' * 70)
    cursor.execute("SELECT id, name, owner_id, created_by, created_at FROM versions WHERE name LIKE '%7777%' OR name LIKE '%TEST60%'")
    rows = cursor.fetchall()
    for r in rows:
        print(f'  id={r[0]} name={r[1]} owner_id={r[2]} created_by={r[3]} created_at={r[4]}')

    if not rows:
        cursor.execute("SELECT id, name, owner_id, created_by, created_at FROM versions ORDER BY id DESC LIMIT 15")
        rows = cursor.fetchall()
        print('  (latest 15 versions)')
        for r in rows:
            print(f'  id={r[0]} name={r[1]} owner_id={r[2]} created_by={r[3]} created_at={r[4]}')

    print()
    print('=' * 70)
    print('2. Find TEST60 user_id')
    print('=' * 70)
    cursor.execute("SELECT id, username FROM users WHERE username = 'TEST60'")
    user = cursor.fetchone()
    if user:
        test60_id = user[0]
        print(f'  TEST60 id = {test60_id}')
    else:
        print('  TEST60 user NOT FOUND')
        return

    print()
    print('=' * 70)
    print('3. TEST60 dimension scopes (role_dimension_scopes)')
    print('=' * 70)
    cursor.execute("""
        SELECT rds.role_id, rds.dimension_type, rds.dimension_values, r.code, r.name
        FROM role_dimension_scopes rds
        JOIN roles r ON r.id = rds.role_id
        JOIN group_roles gr ON gr.role_id = r.id
        JOIN user_group_members ugm ON ugm.group_id = gr.group_id
        WHERE ugm.user_id = ?
    """, [test60_id])
    rows = cursor.fetchall()
    if not rows:
        print('  NO dimension scopes')
    for r in rows:
        print(f'  role={r[3]}({r[4]}) dim_type={r[1]} values={r[2]}')

    print()
    print('=' * 70)
    print('4. Check versions table schema (has owner_id?)')
    print('=' * 70)
    cursor.execute("PRAGMA table_info(versions)")
    cols = cursor.fetchall()
    owner_id_col = None
    for c in cols:
        if 'owner' in c[1].lower():
            owner_id_col = c[1]
            print(f'  [FOUND] {c}')
    if not owner_id_col:
        print('  [NO owner_id column in versions table]')
    print(f'  Total columns: {len(cols)}')

    print()
    print('=' * 70)
    print('5. Simulate: TEST60 querying versions list (last 20)')
    print('=' * 70)
    cursor.execute("SELECT id, name, owner_id FROM versions ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    for r in rows:
        marker = ' <-- owner=TEST60' if r[2] == test60_id else ''
        print(f'  id={r[0]} name={r[1]} owner_id={r[2]}{marker}')

    print()
    print('=' * 70)
    print('6. Check meta/schemas/version.yaml for auto_owner')
    print('=' * 70)
    import os
    yaml_path = r'd:\filework\excel-to-diagram\meta\schemas\version.yaml'
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            content = f.read()
        for line in content.split('\n'):
            if 'auto_owner' in line or 'owner_id' in line or 'scope' in line:
                print(f'  {line.strip()}')

    conn.close()

if __name__ == '__main__':
    main()