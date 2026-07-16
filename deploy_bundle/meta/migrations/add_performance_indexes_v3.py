"""
性能索引迁移脚本 v3

新增索引:
- idx_relationships_target_bo_id: relationships(target_bo_id) 单列索引 [P0]
- idx_relationships_source_bo_id: relationships(source_bo_id) 单列索引 [P1]
- idx_audit_logs_type_action_created: audit_logs(object_type, action, created_at) 覆盖索引 [P1]

运行: python meta/migrations/add_performance_indexes_v3.py
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

INDEXES = [
    {
        'name': 'idx_relationships_target_bo_id',
        'table': 'relationships',
        'columns': 'target_bo_id',
        'sql': 'CREATE INDEX IF NOT EXISTS idx_relationships_target_bo_id ON relationships(target_bo_id)',
        'priority': 'P0',
        'reason': 'target_bo_id 查询无索引覆盖, 影响 10+ 处查询 (特殊路由/级联/关联详情/consistency_guard)',
    },
    {
        'name': 'idx_relationships_source_bo_id',
        'table': 'relationships',
        'columns': 'source_bo_id',
        'sql': 'CREATE INDEX IF NOT EXISTS idx_relationships_source_bo_id ON relationships(source_bo_id)',
        'priority': 'P1',
        'reason': 'source_bo_id OR 查询优化, 复合索引 (source_bo_id,target_bo_id) 对 OR 右分支无效',
    },
    {
        'name': 'idx_audit_logs_type_action_created',
        'table': 'audit_logs',
        'columns': 'object_type, action, created_at',
        'sql': 'CREATE INDEX IF NOT EXISTS idx_audit_logs_type_action_created ON audit_logs(object_type, action, created_at)',
        'priority': 'P1',
        'reason': '审计日志列表页 object_type+action 筛选 + created_at 排序覆盖, 避免回表排序',
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
            print(f"  [v3] Created: {idx['name']} ON {idx['table']}({idx['columns']}) [{idx['priority']}]")
        except Exception as e:
            failed.append((idx['name'], str(e)))
            print(f"  [v3] Failed: {idx['name']} - {e}")

    conn.commit()

    print(f"  [v3] Summary: {len(created)} created, {len(skipped)} skipped, {len(failed)} failed")
    return created, skipped, failed


def verify_indexes(conn):
    cursor = conn.cursor()
    print("  [v3] --- Index Verification ---")
    all_present = True
    for idx in INDEXES:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (idx['name'],)
        )
        if cursor.fetchone():
            print(f"  [v3]   OK {idx['name']}")
        else:
            print(f"  [v3]   MISSING {idx['name']}")
            all_present = False
    return all_present


def main():
    db_path = get_db_path()
    print(f"[v3] Database: {db_path}")

    if not os.path.exists(db_path):
        print(f"[v3] ERROR: Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        create_indexes(conn)
        verify_indexes(conn)
    finally:
        conn.close()


if __name__ == '__main__':
    main()