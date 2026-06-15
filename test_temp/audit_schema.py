# -*- coding: utf-8 -*-
"""
[MODULE] 审查 audit_logs 表结构
"""
import sqlite3
import os

DB_PATH = r'd:/filework/excel-to-diagram/meta/architecture.db'


def main():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()

    print("=" * 80)
    print("  audit_logs 表结构")
    print("=" * 80)

    cur.execute("PRAGMA table_info(audit_logs)")
    for r in cur.fetchall():
        cid, name, type_, notnull, dflt, pk = r
        print(f"  {name:<25} {type_:<10} notnull={notnull} default={dflt} pk={pk}")

    print("\n=== 索引 ===")
    cur.execute("PRAGMA index_list(audit_logs)")
    for r in cur.fetchall():
        print(f"  index: {r}")

    print("\n=== 总数 ===")
    cur.execute("SELECT COUNT(*) FROM audit_logs")
    print(f"  total: {cur.fetchone()[0]}")

    print("\n=== trace_id 列 ===")
    cur.execute("PRAGMA table_info(audit_logs)")
    has_trace = any(r[1] == 'trace_id' for r in cur.fetchall())
    print(f"  trace_id column exists: {has_trace}")

    print("\n=== 字段填充 (最近 10 分钟) ===")
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN object_type IS NULL OR object_type = '' THEN 1 ELSE 0 END) as no_obj,
            SUM(CASE WHEN object_id IS NULL OR object_id = '' THEN 1 ELSE 0 END) as no_oid,
            SUM(CASE WHEN action IS NULL OR action = '' THEN 1 ELSE 0 END) as no_act,
            SUM(CASE WHEN user_id IS NULL OR user_id = '' THEN 1 ELSE 0 END) as no_uid,
            SUM(CASE WHEN user_name IS NULL OR user_name = '' THEN 1 ELSE 0 END) as no_un,
            SUM(CASE WHEN ip_address IS NULL OR ip_address = '' THEN 1 ELSE 0 END) as no_ip,
            SUM(CASE WHEN trace_id IS NULL OR trace_id = '' THEN 1 ELSE 0 END) as no_tid,
            SUM(CASE WHEN user_agent IS NULL OR user_agent = '' THEN 1 ELSE 0 END) as no_ua
        FROM audit_logs
        WHERE created_at >= datetime('now', '-10 minutes')
    """)
    r = cur.fetchone()
    fields = ['total', 'object_type', 'object_id', 'action', 'user_id', 'user_name', 'ip_address', 'trace_id', 'user_agent']
    for f, v in zip(fields, r):
        rate = v / r[0] * 100 if r[0] else 0
        print(f"  {f:<15} missing={v:>5} ({rate:.1f}%)")

    # cascade 引起的 trace_id 缺失占总比
    print("\n=== DISSOCIATE/CREATE 缺失 trace_id 是否都是 cascade? ===")
    cur.execute("""
        SELECT
            action,
            COUNT(*) as total,
            SUM(CASE WHEN extra_data LIKE '%cascade_reason%' OR extra_data LIKE '%through_table%' THEN 1 ELSE 0 END) as cascade,
            SUM(CASE WHEN (extra_data IS NULL OR extra_data NOT LIKE '%cascade%') AND (trace_id IS NULL OR trace_id = '') THEN 1 ELSE 0 END) as non_cascade
        FROM audit_logs
        WHERE (trace_id IS NULL OR trace_id = '')
          AND created_at >= datetime('now', '-10 minutes')
        GROUP BY action
    """)
    for r in cur.fetchall():
        print(f"  {r[0]:<20} missing={r[1]:>4} cascade={r[2]:>4} non_cascade={r[3]:>4}")

    conn.close()


if __name__ == '__main__':
    main()
