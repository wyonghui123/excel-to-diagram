# -*- coding: utf-8 -*-
"""
数据库迁移：审计日志表添加日志类型和级别字段

新增字段：
- log_category: 日志类型 (business/security/operation/performance/system)
- log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)

新增索引：
- idx_audit_category: 按 log_category 索引
- idx_audit_category_action_time: 复合索引 (log_category, action, created_at)
- idx_audit_level: 按 log_level 索引

使用方式：
    python -m meta.migrations.add_log_category_and_level [db_path]
"""

import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


NEW_COLUMNS = [
    ("log_category", "TEXT DEFAULT 'business'"),
    ("log_level", "TEXT DEFAULT 'INFO'"),
]

NEW_INDEXES = [
    ("idx_audit_category", "audit_logs(log_category)"),
    ("idx_audit_category_action_time", "audit_logs(log_category, action, created_at)"),
    ("idx_audit_level", "audit_logs(log_level)"),
]


def add_log_category_and_level(db_path: str):
    """
    添加 log_category 和 log_level 字段到 audit_logs 表
    
    Args:
        db_path: 数据库文件路径
    """
    print(f"\n[Migration] Adding log_category and log_level to audit_logs...")
    print(f"  Database: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"  x Database file not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"
    )
    if not cursor.fetchone():
        print("  x audit_logs table not found, skipping")
        conn.close()
        return False
    
    # 获取现有列
    cursor.execute("PRAGMA table_info(audit_logs)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # 添加新列
    added_columns = 0
    for col_name, col_type in NEW_COLUMNS:
        if col_name in existing_columns:
            print(f"  = audit_logs.{col_name}: already exists")
            continue
        try:
            cursor.execute(
                f"ALTER TABLE audit_logs ADD COLUMN {col_name} {col_type}"
            )
            added_columns += 1
            print(f"  + audit_logs.{col_name}: added ({col_type})")
        except Exception as e:
            print(f"  x audit_logs.{col_name}: failed - {e}")
    
    # 获取现有索引
    added_indexes = 0
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_audit_%'"
    )
    existing_indexes = {row[0] for row in cursor.fetchall()}
    
    # 添加新索引
    for idx_name, idx_def in NEW_INDEXES:
        if idx_name in existing_indexes:
            print(f"  = {idx_name}: already exists")
            continue
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
            added_indexes += 1
            print(f"  + {idx_name}: created")
        except Exception as e:
            print(f"  x {idx_name}: failed - {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n[Migration] Completed: {added_columns} columns, {added_indexes} indexes added")
    return True


def rollback(db_path: str):
    """
    回滚迁移（SQLite 不支持 DROP COLUMN，仅删除索引）
    
    Args:
        db_path: 数据库文件路径
    """
    print(f"\n[Migration] Rolling back log_category and log_level...")
    
    if not os.path.exists(db_path):
        print(f"  x Database file not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 删除索引
    for idx_name, _ in NEW_INDEXES:
        try:
            cursor.execute(f"DROP INDEX IF EXISTS {idx_name}")
            print(f"  - {idx_name}: dropped")
        except Exception as e:
            print(f"  x {idx_name}: failed - {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n[Migration] Rollback completed (indexes dropped, columns remain)")
    print(f"  Note: SQLite does not support DROP COLUMN")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m meta.migrations.add_log_category_and_level <db_path> [--rollback]")
        print("Example: python -m meta.migrations.add_log_category_and_level data/meta.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    if "--rollback" in sys.argv:
        rollback(db_path)
    else:
        add_log_category_and_level(db_path)
