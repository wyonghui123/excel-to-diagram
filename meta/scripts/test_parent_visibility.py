# -*- coding: utf-8 -*-
"""测试向上可见性权限级别"""

import sqlite3
import sys
import os

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
meta_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(meta_dir)
sys.path.insert(0, meta_dir)

from core.datasource import get_data_source
from services.data_permission_service import DataPermissionService

def test_parent_visibility():
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
        print(f"\nHierarchy: SM({row[0]}) '{row[1]}' -> SD({row[2]}) '{row[3]}' -> D({row[4]}) '{row[5]}'")
        domain_id = row[4]
    else:
        print("Service module not found")
        return
    
    # 使用 DataPermissionService 测试
    ds = get_data_source("sqlite", database=db_path)
    dps = DataPermissionService(ds)
    
    # 测试服务模块权限
    sm_level = dps.get_effective_permission_level(user_id, 'service_module', 1)
    print(f"\nPermission level for service_module(1): {sm_level}")
    
    # 测试子领域权限（应该通过向下继承获得）
    sd_level = dps.get_effective_permission_level(user_id, 'sub_domain', 1)
    print(f"Permission level for sub_domain(1): {sd_level}")
    
    # 测试领域权限（应该通过向上可见性获得 read）
    d_level = dps.get_effective_permission_level(user_id, 'domain', domain_id)
    print(f"Permission level for domain({domain_id}): {d_level}")
    
    # 验证结果
    print("\n=== Verification ===")
    if sm_level == 'write':
        print("[OK] Service module permission is correct (write)")
    else:
        print(f"[X] Service module permission should be 'write', got '{sm_level}'")
    
    if d_level == 'read':
        print("[OK] Domain permission is correct (read - from parent visibility)")
    else:
        print(f"[X] Domain permission should be 'read' (parent visibility), got '{d_level}'")
    
    # 清理测试数据
    c.execute("DELETE FROM data_permissions WHERE user_id = ?", [user_id])
    conn.commit()
    print("\nTest data cleaned up")
    
    conn.close()

if __name__ == '__main__':
    test_parent_visibility()
