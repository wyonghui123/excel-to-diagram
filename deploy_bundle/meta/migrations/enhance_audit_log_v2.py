# -*- coding: utf-8 -*-
"""
数据库迁移：审计日志表结构增强 V2

新增字段：
- trace_id: 请求链路追踪ID
- transaction_id: 业务事务ID
- status: 审计记录状态 (written/pending/failed)
- retry_count: 重试次数
- error_message: 失败错误信息
- agent_id: AI Agent 标识
- agent_session_id: Agent 会话ID
- tool_call_id: 工具调用ID (幂等键)
- agent_reasoning: Agent 推理上下文

新增索引：
- idx_audit_trace: 按 trace_id 索引
- idx_audit_txn: 按 transaction_id 索引
- idx_audit_status: 按 status 索引

使用方式：
    python -m meta.migrations.enhance_audit_log_v2 [db_path]
"""

import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


NEW_COLUMNS = [
    ("trace_id", "TEXT"),
    ("transaction_id", "TEXT"),
    ("status", "TEXT DEFAULT 'written'"),
    ("retry_count", "INTEGER DEFAULT 0"),
    ("error_message", "TEXT"),
    ("agent_id", "TEXT"),
    ("agent_session_id", "TEXT"),
    ("tool_call_id", "TEXT"),
    ("agent_reasoning", "TEXT"),
    ("parent_object_type", "TEXT"),
    ("parent_object_id", "TEXT"),
]

NEW_INDEXES = [
    ("idx_audit_trace", "audit_logs(trace_id)"),
    ("idx_audit_txn", "audit_logs(transaction_id)"),
    ("idx_audit_status", "audit_logs(status)"),
    ("idx_audit_tool_call", "audit_logs(tool_call_id)"),
    ("idx_audit_parent", "audit_logs(parent_object_type, parent_object_id)"),
]


def enhance_audit_log(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"
    )
    if not cursor.fetchone():
        print("  audit_logs table not found, skipping")
        conn.close()
        return

    cursor.execute("PRAGMA table_info(audit_logs)")
    existing_columns = {row[1] for row in cursor.fetchall()}

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

    added_indexes = 0
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_audit_%'"
    )
    existing_indexes = {row[0] for row in cursor.fetchall()}

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

    print(f"\nMigration complete: {added_columns} columns added, {added_indexes} indexes created")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )

    if not os.path.exists(db_path):
        print("Database not found: {0}".format(db_path))
        sys.exit(1)

    print("Enhancing audit_logs table: {0}".format(db_path))
    enhance_audit_log(db_path)
