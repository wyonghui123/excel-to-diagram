# -*- coding: utf-8 -*-
"""V1 权限审计快速检查脚本"""
import sqlite3

DB_PATH = 'd:/filework/excel-to-diagram/meta/architecture.db'

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print("V1 权限体系审计报告")
    print("=" * 60)

    # 2.1 所有管理员
    print("\n[2.1] 所有管理员 (拥有 '*' 权限的用户)")
    print("-" * 60)
    cursor.execute('''
        SELECT DISTINCT u.id, u.username, u.display_name, u.email, u.status
        FROM users u
        JOIN user_roles ur ON u.id = ur.user_id
        JOIN roles r ON ur.role_id = r.id
        JOIN role_permissions rp ON r.id = rp.role_id
        JOIN permissions p ON rp.permission_id = p.id
        WHERE p.code = '*' AND r.is_active = 1
        ORDER BY u.username
    ''')
    admins = cursor.fetchall()
    if admins:
        print(f"{'ID':<5} {'Username':<20} {'Display Name':<20} {'Email':<25} {'Status'}")
        print("-" * 60)
        for row in admins:
            print(f"{row[0]:<5} {row[1]:<20} {row[2] or '':<20} {row[3] or '':<25} {row[4] or 'active'}")
    else:
        print("无管理员")

    # 2.3 admin 角色详情
    print("\n[2.3] admin 角色详情")
    print("-" * 60)
    cursor.execute('SELECT id, code, name, description, is_active, is_system FROM roles WHERE code = "admin"')
    admin_role = cursor.fetchone()
    if admin_role:
        print(f"ID: {admin_role[0]}")
        print(f"Code: {admin_role[1]}")
        print(f"Name: {admin_role[2]}")
        print(f"Description: {admin_role[3]}")
        print(f"Active: {'Yes' if admin_role[4] else 'No'}")
        print(f"System: {'Yes' if admin_role[5] else 'No'}")
    else:
        print("admin 角色不存在")

    # 2.4 admin 角色权限
    print("\n[2.4] admin 角色权限")
    print("-" * 60)
    cursor.execute('''
        SELECT p.id, p.code, p.name, p.description
        FROM permissions p
        JOIN role_permissions rp ON p.id = rp.permission_id
        JOIN roles r ON rp.role_id = r.id
        WHERE r.code = "admin"
    ''')
    perms = cursor.fetchall()
    if perms:
        print(f"{'ID':<5} {'Code':<20} {'Name':<20} Description")
        print("-" * 60)
        for row in perms:
            print(f"{row[0]:<5} {row[1]:<20} {row[2] or '':<20} {row[3] or ''}")
    else:
        print("无权限")

    # 8. 统计数据
    print("\n[8] 权限体系统计")
    print("-" * 60)
    tables = [
        ('users', '用户总数'),
        ('roles', '角色总数'),
        ('permissions', '权限总数'),
        ('user_groups', '用户组总数'),
        ('user_group_members', '用户组成员关系数'),
    ]
    for table, label in tables:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        count = cursor.fetchone()[0]
        print(f"{label}: {count}")

    # 7.4 检查孤立用户
    print("\n[7.4] Orphaned 用户 (无任何权限)")
    print("-" * 60)
    cursor.execute('''
        SELECT u.id, u.username, u.display_name
        FROM users u
        WHERE u.status = 'active'
          AND u.id NOT IN (
            SELECT DISTINCT ur.user_id FROM user_roles ur
            JOIN roles r ON ur.role_id = r.id
            JOIN role_permissions rp ON r.id = rp.role_id
            WHERE r.is_active = 1
          )
        ORDER BY u.username
    ''')
    orphaned = cursor.fetchall()
    if orphaned:
        print(f"发现 {len(orphaned)} 个孤立用户:")
        for row in orphaned:
            print(f"  - {row[1]}: {row[2]}")
    else:
        print("无孤立用户")

    conn.close()
    print("\n" + "=" * 60)
    print("审计完成")
    print("=" * 60)

if __name__ == '__main__':
    main()
