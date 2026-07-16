# -*- coding: utf-8 -*-
"""
迁移脚本: 删除 user_roles 表

【架构决策 2026-06-02】
用户角色分配统一通过用户组实现，移除直接 user_roles 路径。
执行本迁移前请确保所有用户角色已迁移到用户组路径。

用法:
    python meta/migrations/drop_user_roles_table.py
"""

import sqlite3
import os
import sys


def get_db_path():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'meta', 'architecture.db')


def drop_user_roles_table():
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_roles'")
    if cursor.fetchone():
        print("删除 user_roles 表...")
        cursor.execute("DROP TABLE IF EXISTS user_roles")
        conn.commit()
        print("✓ user_roles 表已删除")
    else:
        print("user_roles 表不存在，无需删除")
    
    conn.close()
    print("迁移完成")


if __name__ == '__main__':
    drop_user_roles_table()
