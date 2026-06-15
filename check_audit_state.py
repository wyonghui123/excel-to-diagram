#!/usr/bin/env python
"""Check audit_logs for permission object types"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'meta', 'architecture.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Count by object_type
print("=" * 80)
print("--- audit_logs count by object_type (permission-related) ---")
cur.execute("""
    SELECT object_type, COUNT(*) as cnt
    FROM audit_logs
    WHERE object_type IN (
        'role_menu', 'role_permissions', 'role_data_permission',
        'role_dimension_scope', 'role_v2_menu_permissions', 'permission_rule'
    )
    GROUP BY object_type
    ORDER BY object_type
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

print("=" * 80)
print("--- Latest 10 audit logs (any object_type) ---")
cur.execute("""
    SELECT id, object_type, object_id, action, user_name, created_at, parent_object_type, parent_object_id
    FROM audit_logs
    ORDER BY id DESC
    LIMIT 10
""")
for r in cur.fetchall():
    pid = r[7] if r[7] is not None else '-'
    pot = r[6] or '-'
    print(f"  id={r[0]:5d}  {r[1]:30s} obj={r[2]}  act={r[3]:8s} user={str(r[4] or '')[:25]:25s} parent={pot}/{pid}  at={r[5]}")

print("=" * 80)
print("--- Latest 10 permission-related logs ---")
cur.execute("""
    SELECT id, object_type, object_id, action, user_name, created_at, parent_object_type, parent_object_id
    FROM audit_logs
    WHERE object_type IN (
        'role_menu', 'role_permissions', 'role_data_permission',
        'role_dimension_scope', 'role_v2_menu_permissions', 'permission_rule'
    )
    ORDER BY id DESC
    LIMIT 10
""")
rows = cur.fetchall()
if not rows:
    print("  (NO ROWS - this is the issue!)")
else:
    for r in rows:
        pid = r[7] if r[7] is not None else '-'
        pot = r[6] or '-'
        print(f"  id={r[0]:5d}  {r[1]:30s} obj={r[2]}  act={r[3]:8s} user={str(r[4] or '')[:25]:25s} parent={pot}/{pid}  at={r[5]}")

print("=" * 80)
# Test the actual query: parent_object_type='role' AND parent_object_id=?
# (this is what RoleDetailDrawer would call)
cur.execute("SELECT id, name, code FROM roles ORDER BY id LIMIT 5")
roles = cur.fetchall()
print(f"--- Query by parent_object for first 5 roles ---")
for r in roles:
    cur.execute("""
        SELECT id, object_type, action, user_name, created_at
        FROM audit_logs
        WHERE (object_type = 'role' AND object_id = ?)
           OR (parent_object_type = 'role' AND parent_object_id = ?)
        ORDER BY id DESC
        LIMIT 5
    """, [r[0], r[0]])
    rs = cur.fetchall()
    if rs:
        print(f"  role_id={r[0]} ({r[1]}): {len(rs)} logs")
        for log in rs:
            print(f"    {log[1]:30s} {log[2]:8s} {log[3] or '':25s} {log[4]}")

conn.close()
