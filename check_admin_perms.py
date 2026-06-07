import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 检查 admin 用户
cursor.execute('SELECT id, username FROM users WHERE username = "admin"')
admin = cursor.fetchone()
print(f"Admin user: {admin}")

if admin:
    admin_id = admin[0]
    
    # 检查 admin 的用户组成员关系
    cursor.execute('''
        SELECT ugm.group_id, ug.name
        FROM user_group_members ugm
        JOIN user_groups ug ON ugm.group_id = ug.id
        WHERE ugm.user_id = ?
    ''', [admin_id])
    groups = cursor.fetchall()
    print(f"\nAdmin groups: {groups}")
    
    # 检查这些组的角色
    if groups:
        group_ids = [g[0] for g in groups]
        ph = ','.join('?' * len(group_ids))
        cursor.execute(f'''
            SELECT DISTINCT gr.role_id, r.name
            FROM group_roles gr
            JOIN roles r ON gr.role_id = r.id
            WHERE gr.group_id IN ({ph})
        ''', group_ids)
        roles = cursor.fetchall()
        print(f"\nAdmin roles: {roles}")
        
        # 检查这些角色的权限
        if roles:
            role_ids = [r[0] for r in roles]
            ph = ','.join('?' * len(role_ids))
            cursor.execute(f'''
                SELECT DISTINCT p.code
                FROM role_permissions rp
                JOIN permissions p ON rp.permission_id = p.id
                WHERE rp.role_id IN ({ph})
            ''', role_ids)
            perms = cursor.fetchall()
            print(f"\nAdmin permissions: {[p[0] for p in perms]}")

conn.close()
