"""
性能索引迁移脚本

新增索引:
- idx_audit_logs_type_id: audit_logs(object_type, object_id) 联合索引
- idx_relationships_source_target: relationships(source_bo_id, target_bo_id) 联合索引
- idx_business_objects_module: business_objects(service_module_id) 索引

运行: python meta/migrations/add_performance_indexes_v2.py
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

INDEXES = [
    {
        'name': 'idx_audit_logs_type_id',
        'table': 'audit_logs',
        'columns': 'object_type, object_id',
        'sql': 'CREATE INDEX IF NOT EXISTS idx_audit_logs_type_id ON audit_logs(object_type, object_id)',
        'priority': 'high',
        'reason': '加速审计日志按对象类型+ID查询（列表/详情页关联填充）',
    },
    {
        'name': 'idx_relationships_source_target',
        'table': 'relationships',
        'columns': 'source_bo_id, target_bo_id',
        'sql': 'CREATE INDEX IF NOT EXISTS idx_relationships_source_target ON relationships(source_bo_id, target_bo_id)',
        'priority': 'high',
        'reason': '加速级联删除中关联关系批量查询（已优化为单次OR查询）',
    },
    {
        'name': 'idx_business_objects_module',
        'table': 'business_objects',
        'columns': 'service_module_id',
        'sql': 'CREATE INDEX IF NOT EXISTS idx_business_objects_module ON business_objects(service_module_id)',
        'priority': 'medium',
        'reason': '加速按服务模块筛选业务对象列表',
    },
]


def get_db_path():
    db_path = os.environ.get('DB_PATH')
    if db_path:
        return db_path
    default_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db'
    )
    return default_path


def create_indexes(conn):
    cursor = conn.cursor()
    created = []
    skipped = []
    failed = []

    for idx in INDEXES:
        try:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (idx['name'],)
            )
            existing = cursor.fetchone()
            if existing:
                skipped.append(idx['name'])
                continue

            cursor.execute(idx['sql'])
            created.append(idx['name'])
            print(f"  ✓ Created: {idx['name']} ON {idx['table']}({idx['columns']}) [{idx['priority']}]")
        except Exception as e:
            failed.append((idx['name'], str(e)))
            print(f"  ✗ Failed: {idx['name']} - {e}")

    conn.commit()

    print(f"\nSummary: {len(created)} created, {len(skipped)} skipped, {len(failed)} failed")
    return created, skipped, failed


def verify_indexes(conn):
    cursor = conn.cursor()
    print("\n--- Index Verification ---")
    all_present = True
    for idx in INDEXES:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (idx['name'],)
        )
        if cursor.fetchone():
            print(f"  ✓ {idx['name']} exists")
        else:
            print(f"  ✗ {idx['name']} MISSING")
            all_present = False
    return all_present


def main():
    db_path = get_db_path()
    print(f"Database: {db_path}")

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        create_indexes(conn)
        verify_indexes(conn)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
