# 分析用户选择的过滤值
import sqlite3

conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')

# 1. 查找 CRUD Group_92446 的 ID
print("=== 1. 查找 CRUD Group_92446 ===")
cur = conn.execute("SELECT id, name FROM user_groups WHERE name LIKE '%CRUD Group_92446%'")
rows = cur.fetchall()
print(f"找到 {len(rows)} 条匹配记录")
for r in rows:
    print(f"  id={r[0]}, name={r[1]}")
    
    # 查找以它为父组的子组
    cur2 = conn.execute(f"SELECT id, name, parent_id FROM user_groups WHERE parent_id = {r[0]}")
    children = cur2.fetchall()
    print(f"  → 子组数量: {len(children)}")
    for c in children[:3]:
        print(f"    - id={c[0]}, name={c[1]}")

# 2. 查找 no_pwd_d1a3798a 用户
print("\n=== 2. 查找 no_pwd_d1a3798a 用户 ===")
cur = conn.execute("SELECT id, username, display_name FROM users WHERE username LIKE '%no_pwd_d1a3798a%'")
rows = cur.fetchall()
print(f"找到 {len(rows)} 条匹配记录")
for r in rows:
    print(f"  id={r[0]}, username={r[1]}, display_name={r[2]}")
    
    # 查找以它为管理员的用户组
    cur2 = conn.execute(f"SELECT id, name, manager_id FROM user_groups WHERE manager_id = {r[0]}")
    managed = cur2.fetchall()
    print(f"  → 管理的用户组数量: {len(managed)}")
    for m in managed[:3]:
        print(f"    - id={m[0]}, name={m[1]}")

# 3. 统计有 parent_id 的用户组
print("\n=== 3. 统计有 parent_id 的用户组 ===")
cur = conn.execute("SELECT COUNT(*) FROM user_groups WHERE parent_id IS NOT NULL")
count = cur.fetchone()[0]
print(f"有 parent_id 的用户组数量: {count}")

# 4. 统计有 manager_id 的用户组
print("\n=== 4. 统计有 manager_id 的用户组 ===")
cur = conn.execute("SELECT COUNT(*) FROM user_groups WHERE manager_id IS NOT NULL")
count = cur.fetchone()[0]
print(f"有 manager_id 的用户组数量: {count}")

conn.close()
