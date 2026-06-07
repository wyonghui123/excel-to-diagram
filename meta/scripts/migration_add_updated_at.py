# -*- coding: utf-8 -*-
"""
数据库迁移脚本：为角色表和用户组表添加 updated_at 字段

用于添加缺失的时间戳字段，支持创建时间和变更时间的完整追踪
"""

import sqlite3
import os

def migrate_add_updated_at(db_path):
    """添加 updated_at 字段到 roles 和 user_groups 表"""
    
    if not os.path.exists(db_path):
        print(f"[X] 数据库文件不存在: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查 roles 表是否有 updated_at 字段
        cursor.execute("PRAGMA table_info(roles)")
        roles_columns = [col[1] for col in cursor.fetchall()]
        
        if 'updated_at' not in roles_columns:
            print("[DECORATIVE] 为 roles 表添加 updated_at 字段...")
            # SQLite 不支持在 ALTER TABLE 中使用非常量默认值，所以分两步执行
            cursor.execute("""
                ALTER TABLE roles 
                ADD COLUMN updated_at DATETIME
            """)

            # 更新现有记录的 updated_at 值（使用 created_at 的值）
            cursor.execute("""
                UPDATE roles SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)
            """)
            print("[OK] roles 表已添加 updated_at 字段")
        else:
            print("ℹ️  roles 表已有 updated_at 字段")

        # 检查 user_groups 表是否有 updated_at 字段
        cursor.execute("PRAGMA table_info(user_groups)")
        group_columns = [col[1] for col in cursor.fetchall()]

        if 'updated_at' not in group_columns:
            print("[DECORATIVE] 为 user_groups 表添加 updated_at 字段...")
            # SQLite 不支持在 ALTER TABLE 中使用非常量默认值，所以分两步执行
            cursor.execute("""
                ALTER TABLE user_groups
                ADD COLUMN updated_at DATETIME
            """)

            # 更新现有记录的 updated_at 值（使用 created_at 的值）
            cursor.execute("""
                UPDATE user_groups SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)
            """)
            print("[OK] user_groups 表已添加 updated_at 字段")
        else:
            print("ℹ️  user_groups 表已有 updated_at 字段")
        
        # 创建更新触发器：当记录被更新时自动更新 updated_at
        
        # 删除旧触发器（如果存在）
        cursor.execute("DROP TRIGGER IF EXISTS trg_roles_updated_at")
        cursor.execute("DROP TRIGGER IF EXISTS trg_user_groups_updated_at")
        
        # 为 roles 表创建触发器
        cursor.execute("""
            CREATE TRIGGER trg_roles_updated_at
            AFTER UPDATE ON roles
            FOR EACH ROW
            WHEN OLD.updated_at IS NOT NULL OR NEW.updated_at IS NOT NULL
            BEGIN
                UPDATE roles SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END
        """)
        print("[OK] 已创建 roles 表更新触发器")
        
        # 为 user_groups 表创建触发器
        cursor.execute("""
            CREATE TRIGGER trg_user_groups_updated_at
            AFTER UPDATE ON user_groups
            FOR EACH ROW
            WHEN OLD.updated_at IS NOT NULL OR NEW.updated_at IS NOT NULL
            BEGIN
                UPDATE user_groups SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END
        """)
        print("[OK] 已创建 user_groups 表更新触发器")
        
        conn.commit()
        
        # 验证迁移结果
        print("\n[DECORATIVE] 验证迁移结果:")
        
        cursor.execute("SELECT COUNT(*) FROM roles WHERE updated_at IS NOT NULL")
        roles_count = cursor.fetchone()[0]
        print(f"   - roles 表: {roles_count} 条记录有 updated_at 值")
        
        cursor.execute("SELECT COUNT(*) FROM user_groups WHERE updated_at IS NOT NULL")
        groups_count = cursor.fetchone()[0]
        print(f"   - user_groups 表: {groups_count} 条记录有 updated_at 值")
        
        print("\n[OK] 数据库迁移完成!")
        return True
        
    except Exception as e:
        print(f"[X] 迁移失败: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    print(f"数据库路径: {db_path}\n")
    migrate_add_updated_at(db_path)
