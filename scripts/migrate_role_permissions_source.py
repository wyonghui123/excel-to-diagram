# -*- coding: utf-8 -*-
"""
数据库迁移脚本：扩展 role_permissions 表添加权限来源字段

新增字段：
- source: 权限来源（manual/auto_menu/auto_role/auto_group）
- source_menu_code: 来源菜单编码（当 source=auto_menu 时）
- granted_at: 授权时间

使用方法：
    python scripts/migrate_role_permissions_source.py
"""

import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.datasource import get_data_source


def migrate_role_permissions_source():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    
    print(f"Database path: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("PRAGMA table_info(role_permissions)")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"Current columns: {columns}")
        
        migrations = []
        
        if 'source' not in columns:
            migrations.append("""
                ALTER TABLE role_permissions 
                ADD COLUMN source VARCHAR(20) DEFAULT 'manual'
            """)
            print("Will add column: source")
        
        if 'source_menu_code' not in columns:
            migrations.append("""
                ALTER TABLE role_permissions 
                ADD COLUMN source_menu_code VARCHAR(200)
            """)
            print("Will add column: source_menu_code")
        
        if 'granted_at' not in columns:
            migrations.append("""
                ALTER TABLE role_permissions 
                ADD COLUMN granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """)
            print("Will add column: granted_at")
        
        if not migrations:
            print("No migrations needed. All columns already exist.")
            return
        
        for sql in migrations:
            print(f"Executing: {sql.strip()}")
            cursor.execute(sql)
        
        conn.commit()
        print("Migration completed successfully!")
        
        cursor.execute("PRAGMA table_info(role_permissions)")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"Updated columns: {columns}")
        
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def migrate_menus_table():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("PRAGMA table_info(menus)")
        columns = [col[1] for col in cursor.fetchall()]
        
        migrations = []
        
        if 'bo_bindings' not in columns:
            migrations.append("ALTER TABLE menus ADD COLUMN bo_bindings TEXT")
        
        if 'required_permissions' not in columns:
            migrations.append("ALTER TABLE menus ADD COLUMN required_permissions TEXT")
        
        if 'required_any_permission' not in columns:
            migrations.append("ALTER TABLE menus ADD COLUMN required_any_permission BOOLEAN DEFAULT 0")
        
        if 'data_permission_hint' not in columns:
            migrations.append("ALTER TABLE menus ADD COLUMN data_permission_hint TEXT")
        
        if not migrations:
            print("menus table: No migrations needed.")
            return
        
        for sql in migrations:
            print(f"menus: {sql}")
            cursor.execute(sql)
        
        conn.commit()
        print("menus table migration completed!")
        
    except Exception as e:
        conn.rollback()
        print(f"menus table migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 50)
    print("Migrating role_permissions table...")
    print("=" * 50)
    migrate_role_permissions_source()
    
    print()
    print("=" * 50)
    print("Migrating menus table...")
    print("=" * 50)
    migrate_menus_table()
