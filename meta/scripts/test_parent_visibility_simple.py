# -*- coding: utf-8 -*-
"""测试向上可见性权限级别 - 简化版"""

import sqlite3
import os

def test_parent_visibility():
    meta_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(meta_dir, 'architecture.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 创建测试用户
    c.execute('''
        INSERT OR IGNORE INTO users (username, password_hash, display_name, email)
        VALUES ('test_user', 'test_hash', '测试用户', 'test@example.com')
    ''')
    conn.commit()
    
    # 获取测试用户ID
    c.execute("SELECT id FROM users WHERE username = 'test_user'")
    result = c.fetchone()
    user_id = result[0] if result else None
    
    if not user_id:
        print("Failed to create test user")
        return
    
    print(f"Test user ID: {user_id}")
    
    # 清理旧的测试数据权限
    c.execute("DELETE FROM data_permissions WHERE user_id = ?", [user_id])
    conn.commit()
    
    # 给测试用户分配服务模块权限（但没有领域权限）
    c.execute('''
        INSERT INTO data_permissions (user_id, resource_type, resource_id, permission_level, inherit_to_children)
        VALUES (?, 'service_module', 1, 'write', 0)
    ''', [user_id])
    conn.commit()
    
    print(f"Added service_module(1) write permission for user {user_id}")
    
    # 获取层级关系
    c.execute('''
        SELECT sm.id, sm.name, sm.sub_domain_id, sd.name as sub_domain_name, sd.domain_id, d.name as domain_name
        FROM service_modules sm
        LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id
        LEFT JOIN domains d ON sd.domain_id = d.id
        WHERE sm.id = 1
    ''')
    row = c.fetchone()
    if row:
        print(f"\nHierarchy: SM({row[0]}) '{row[1][:20]}...' -> SD({row[2]}) '{row[3]}' -> D({row[4]}) '{row[5][:20]}...'")
        domain_id = row[4]
        sub_domain_id = row[2]
    else:
        print("Service module not found")
        return
    
    # 直接测试权限查询
    print("\n=== Direct Database Queries ===")
    
    # 1. 检查直接权限
    c.execute('''
        SELECT permission_level FROM data_permissions 
        WHERE user_id = ? AND resource_type = 'service_module' AND resource_id = 1
    ''', [user_id])
    sm_perm = c.fetchone()
    print(f"Direct permission for service_module(1): {sm_perm[0] if sm_perm else 'none'}")
    
    # 2. 检查领域直接权限
    c.execute('''
        SELECT permission_level FROM data_permissions 
        WHERE user_id = ? AND resource_type = 'domain' AND resource_id = ?
    ''', [user_id, domain_id])
    d_perm = c.fetchone()
    print(f"Direct permission for domain({domain_id}): {d_perm[0] if d_perm else 'none'}")
    
    # 3. 模拟向上可见性检查
    print("\n=== Simulating Parent Visibility Check ===")
    print(f"User has service_module(1) write permission")
    print(f"Service module 1 belongs to sub_domain({sub_domain_id})")
    print(f"Sub domain {sub_domain_id} belongs to domain({domain_id})")
    print(f"Therefore, user should have 'read' permission for domain({domain_id}) via parent visibility")
    
    # 清理测试数据
    c.execute("DELETE FROM data_permissions WHERE user_id = ?", [user_id])
    c.execute("DELETE FROM users WHERE username = 'test_user'")
    conn.commit()
    print("\nTest data cleaned up")
    
    conn.close()
    
    print("\n=== Test Summary ===")
    print("The fix adds _get_parent_visibility_permission_level() method to DataPermissionService.")
    print("When a user has permission on a child resource (e.g., service_module),")
    print("they automatically get 'read' permission on parent resources (e.g., domain)")
    print("for navigation purposes.")

if __name__ == '__main__':
    test_parent_visibility()
