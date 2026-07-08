# -*- coding: utf-8 -*-
"""
权限模型统一语义迁移脚本

迁移目标：
- 资源 = 业务对象
- 操作 = 服务动作（由 YAML 声明，不再使用 meta_actions 表）
- 权限 = 业务对象 + 服务动作
"""

import sqlite3
import os
import shutil
from datetime import datetime

def migrate_permission_unified_semantic(db_path):
    """迁移权限模型到统一语义"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("权限模型统一语义迁移")
    print("=" * 60)
    
    print("\n[步骤1] meta_actions 表已废弃，跳过创建")
    
    print("\n[步骤2] 为permissions表添加新字段...")
    
    cursor.execute("PRAGMA table_info(permissions)")
    columns = [col[1] for col in cursor.fetchall()]
    
    new_columns = [
        ('resource_id', 'INTEGER'),
        ('scope', 'VARCHAR(200) DEFAULT "all"'),
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE permissions ADD COLUMN {col_name} {col_type}")
            print(f"  [OK] 添加字段: {col_name}")
        else:
            print(f"  ⏭️  字段 {col_name} 已存在，跳过")
    
    print("\n[步骤3] 跳过 action_id/action_code 迁移")
    
    print("\n[步骤4] 创建索引...")
    
    print("  跳过 meta_actions 相关索引")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print("[OK] 权限模型统一语义迁移完成！")
    print("=" * 60)

def backup_database(db_path):
    """备份数据库"""
    if not os.path.exists(db_path):
        print(f"[WARNING]  数据库文件不存在: {db_path}")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    
    print(f"正在备份数据库...")
    shutil.copy2(db_path, backup_path)
    print(f"[OK] 数据库已备份到: {backup_path}")
    
    return backup_path

if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'architecture.db')
    print(f"数据库路径: {db_path}")
    
    backup_path = backup_database(db_path)
    
    if backup_path:
        migrate_permission_unified_semantic(db_path)
