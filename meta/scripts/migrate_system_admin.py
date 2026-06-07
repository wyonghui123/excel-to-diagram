# -*- coding: utf-8 -*-
"""
系统管理员迁移脚本

功能：
1. 创建 group_roles 表（用户组-角色关联表）
2. 创建系统管理员用户组
3. 将 admin 用户添加到系统管理员用户组
4. 将系统管理员角色分配给用户组
"""

import sqlite3
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_group_roles_table(conn):
    """创建用户组-角色关联表"""
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM group_roles LIMIT 1")
        print("group_roles 表已存在")
    except sqlite3.OperationalError:
        cursor.execute("""
            CREATE TABLE group_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(group_id, role_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_roles_group ON group_roles(group_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_roles_role ON group_roles(role_id)")
        conn.commit()
        print("创建 group_roles 表成功")


def create_system_admin_group(conn):
    """创建系统管理员用户组"""
    cursor = conn.cursor()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("SELECT id FROM user_groups WHERE code = 'system_admin'")
    row = cursor.fetchone()
    
    if row:
        print(f"系统管理员用户组已存在: ID={row['id']}")
        return row['id']
    
    cursor.execute(
        "INSERT INTO user_groups (name, code, description, created_at) VALUES (?, ?, ?, ?)",
        ('系统管理员', 'system_admin', '系统管理员用户组，拥有系统最高权限', now)
    )
    
    group_id = cursor.lastrowid
    conn.commit()
    print(f"创建系统管理员用户组成功: ID={group_id}")
    return group_id


def add_admin_to_group(conn, group_id):
    """将 admin 用户添加到系统管理员用户组"""
    cursor = conn.cursor()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    user_row = cursor.fetchone()
    
    if not user_row:
        print("警告: admin 用户不存在，请先运行 init_auth.py")
        return None
    
    user_id = user_row['id']
    
    cursor.execute(
        "SELECT id FROM user_group_members WHERE user_id = ? AND group_id = ?",
        (user_id, group_id)
    )
    
    if cursor.fetchone():
        print(f"admin 用户已在系统管理员用户组中")
        return user_id
    
    cursor.execute(
        "INSERT INTO user_group_members (user_id, group_id, is_manager, joined_at) VALUES (?, ?, ?, ?)",
        (user_id, group_id, 1, now)
    )
    
    conn.commit()
    print(f"将 admin 用户添加到系统管理员用户组成功")
    return user_id


def assign_role_to_group(conn, group_id):
    """将系统管理员角色分配给用户组"""
    cursor = conn.cursor()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("SELECT id FROM roles WHERE code = 'admin'")
    role_row = cursor.fetchone()
    
    if not role_row:
        print("警告: admin 角色不存在，请先运行 init_auth.py")
        return None
    
    role_id = role_row['id']
    
    cursor.execute(
        "SELECT id FROM group_roles WHERE group_id = ? AND role_id = ?",
        (group_id, role_id)
    )
    
    if cursor.fetchone():
        print(f"系统管理员角色已分配给用户组")
        return role_id
    
    cursor.execute(
        "INSERT INTO group_roles (group_id, role_id, created_at) VALUES (?, ?, ?)",
        (group_id, role_id, now)
    )
    
    conn.commit()
    print(f"将系统管理员角色分配给用户组成功")
    return role_id


def verify_migration(conn):
    """验证迁移结果"""
    cursor = conn.cursor()
    
    print("\n=== 迁移验证 ===")
    
    cursor.execute("SELECT id, name, code FROM user_groups WHERE code = 'system_admin'")
    group = cursor.fetchone()
    if group:
        print(f"[DECORATIVE] 用户组: {group['name']} ({group['code']})")
        
        cursor.execute("""
            SELECT u.username, u.display_name 
            FROM user_group_members ugm 
            JOIN users u ON u.id = ugm.user_id 
            WHERE ugm.group_id = ?
        """, (group['id'],))
        members = cursor.fetchall()
        print(f"  成员: {', '.join([m['username'] for m in members])}")
        
        cursor.execute("""
            SELECT r.name, r.code 
            FROM group_roles gr 
            JOIN roles r ON r.id = gr.role_id 
            WHERE gr.group_id = ?
        """, (group['id'],))
        roles = cursor.fetchall()
        print(f"  角色: {', '.join([r['name'] for r in roles])}")
    
    cursor.execute("SELECT id, username, display_name FROM users WHERE username = 'admin'")
    user = cursor.fetchone()
    if user:
        print(f"\n[DECORATIVE] 用户: {user['username']} ({user['display_name']})")
        
        cursor.execute("""
            SELECT r.name, r.code 
            FROM user_roles ur 
            JOIN roles r ON r.id = ur.role_id 
            WHERE ur.user_id = ?
        """, (user['id'],))
        roles = cursor.fetchall()
        print(f"  直接角色: {', '.join([r['name'] for r in roles])}")
        
        cursor.execute("""
            SELECT ug.name, ug.code 
            FROM user_group_members ugm 
            JOIN user_groups ug ON ug.id = ugm.group_id 
            WHERE ugm.user_id = ?
        """, (user['id'],))
        groups = cursor.fetchall()
        print(f"  所属用户组: {', '.join([g['name'] for g in groups])}")


def run_migration():
    """执行迁移"""
    print(f"开始系统管理员迁移...")
    print(f"数据库路径: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print(f"错误: 数据库文件不存在: {DB_PATH}")
        print("请先运行 init_auth.py 初始化数据库")
        return False
    
    conn = get_db()
    try:
        create_group_roles_table(conn)
        group_id = create_system_admin_group(conn)
        
        if group_id:
            add_admin_to_group(conn, group_id)
            assign_role_to_group(conn, group_id)
        
        verify_migration(conn)
        
        print("\n[OK] 系统管理员迁移完成!")
        return True
    except Exception as e:
        print(f"\n[X] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    run_migration()
