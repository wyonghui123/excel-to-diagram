#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_log schema 迁移脚本 (v3.18)

加 6 字段 + 4 索引:
  outcome (FR-005)
  cascade_root_id / cascade_root_action (FR-009)
  retention_until (FR-013)
  prev_hash / row_hash (FR-014)

回滚: 见 --rollback
"""
import sqlite3
import sys
import argparse
from pathlib import Path

# __file__ = meta/scripts/migrate_v318_audit.py
# parent.parent = meta/, parent.parent.parent = project_root
DB_PATH = Path(__file__).parent.parent / "architecture.db"

FIELDS_TO_ADD = [
    ("outcome", "VARCHAR(20) DEFAULT 'success'"),
    ("cascade_root_id", "INTEGER"),
    ("cascade_root_action", "VARCHAR(50)"),
    ("retention_until", "DATETIME"),
    ("prev_hash", "CHAR(64)"),
    ("row_hash", "CHAR(64)"),
]

INDEXES_TO_ADD = [
    ("idx_audit_outcome", "(outcome, created_at)"),
    ("idx_audit_cascade", "(cascade_root_action, object_type)"),
    ("idx_audit_retention", "(retention_until)"),
    ("idx_audit_hash", "(row_hash)"),
]

BACKFILL_SQL = [
    # outcome
    "UPDATE audit_logs SET outcome='blocked' WHERE action='DELETE_BLOCKED'",
    "UPDATE audit_logs SET outcome='failure' WHERE action='AUDIT_WRITE_FAILED'",
    # log_level
    "UPDATE audit_logs SET log_level='WARN' WHERE action IN ('DELETE_BLOCKED', 'ACCESS_DENIED')",
    "UPDATE audit_logs SET log_level='ERROR' WHERE action='AUDIT_WRITE_FAILED'",
    # retention_until: 3 层保留 (TBD-2 决策)
    "UPDATE audit_logs SET retention_until = datetime(created_at, '+2 years') WHERE log_category IN ('security', 'authz')",
    "UPDATE audit_logs SET retention_until = datetime(created_at, '+1 year')  WHERE log_category IN ('business', 'admin')",
    "UPDATE audit_logs SET retention_until = datetime(created_at, '+90 days') WHERE log_category IN ('access', 'system', 'cascade')",
]

ROLLBACK_SQL = [
    "DROP INDEX IF EXISTS idx_audit_outcome",
    "DROP INDEX IF EXISTS idx_audit_cascade",
    "DROP INDEX IF EXISTS idx_audit_retention",
    "DROP INDEX IF EXISTS idx_audit_hash",
    "ALTER TABLE audit_logs DROP COLUMN outcome",
    "ALTER TABLE audit_logs DROP COLUMN cascade_root_id",
    "ALTER TABLE audit_logs DROP COLUMN cascade_root_action",
    "ALTER TABLE audit_logs DROP COLUMN retention_until",
    "ALTER TABLE audit_logs DROP COLUMN prev_hash",
    "ALTER TABLE audit_logs DROP COLUMN row_hash",
]


def has_column(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())


def has_index(conn, name):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,))
    return cur.fetchone() is not None


def migrate(apply: bool):
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")  # 让写不阻塞读
    try:
        # 1. 加字段
        for col, ddl in FIELDS_TO_ADD:
            if has_column(conn, "audit_logs", col):
                print(f"  [SKIP] 字段 {col} 已存在")
            else:
                sql = f"ALTER TABLE audit_logs ADD COLUMN {col} {ddl}"
                if apply:
                    conn.execute(sql)
                    print(f"  [ADD]  字段 {col}")
                else:
                    print(f"  [DRY]  字段 {col} ({sql})")

        # 2. 加索引
        for name, cols in INDEXES_TO_ADD:
            if has_index(conn, name):
                print(f"  [SKIP] 索引 {name} 已存在")
            else:
                sql = f"CREATE INDEX {name} ON audit_logs{cols}"
                if apply:
                    conn.execute(sql)
                    print(f"  [ADD]  索引 {name}")
                else:
                    print(f"  [DRY]  索引 {name} ({sql})")

        # 3. Backfill
        if apply:
            for sql in BACKFILL_SQL:
                cur = conn.execute(sql)
                print(f"  [BACKFILL] {sql[:60]}... rows={cur.rowcount}")
        else:
            for sql in BACKFILL_SQL:
                print(f"  [DRY]  {sql[:80]}")

        conn.commit()
        print(f"\n{'='*50}\n  {'APPLIED' if apply else 'DRY-RUN'} (no errors)\n{'='*50}")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] {e}")
        raise
    finally:
        conn.close()


def rollback(apply: bool):
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        for sql in ROLLBACK_SQL:
            if apply:
                conn.execute(sql)
                print(f"  [DROP]  {sql[:60]}")
            else:
                print(f"  [DRY]  {sql[:60]}")
        conn.commit()
        print(f"\n{'='*50}\n  {'ROLLED BACK' if apply else 'DRY-RUN'}\n{'='*50}")
    finally:
        conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="真改 schema (默认 dry-run)")
    p.add_argument("--rollback", action="store_true", help="回滚")
    args = p.parse_args()

    print(f"DB: {DB_PATH}")
    if args.rollback:
        rollback(args.apply)
    else:
        migrate(args.apply)
