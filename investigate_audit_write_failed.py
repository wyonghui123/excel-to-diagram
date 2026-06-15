# -*- coding: utf-8 -*-
"""
排查 AUDIT_WRITE_FAILED 持续新增的根因
- 拉取最近一批 AUDIT_WRITE_FAILED 记录
- 按 object_type / error_message 聚合
- 输出可疑接口和异常类型
"""
import sqlite3
import os
from collections import Counter
from datetime import datetime

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "meta", "architecture.db"
)

def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. 总览
    print("=" * 70)
    print("AUDIT_WRITE_FAILED 根因排查")
    print("=" * 70)

    cur.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
               SUM(CASE WHEN status='retried' THEN 1 ELSE 0 END) AS retried
        FROM audit_logs
        WHERE action='AUDIT_WRITE_FAILED'
    """)
    row = cur.fetchone()
    print(f"\n[总览]")
    print(f"  总数: {row['total']}")
    print(f"  状态=failed: {row['failed']}")
    print(f"  状态=retried: {row['retried']}")

    # 2. 按 object_type 聚合（看哪些对象类型产生失败最多）
    print(f"\n[按 object_type 聚合 TOP 20]")
    cur.execute("""
        SELECT object_type, COUNT(*) AS cnt
        FROM audit_logs
        WHERE action='AUDIT_WRITE_FAILED' AND status='failed'
        GROUP BY object_type
        ORDER BY cnt DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"  {row['object_type']:30s} {row['cnt']:6d}")

    # 3. 按 error_message 聚合
    print(f"\n[按 error_message 聚合 TOP 20]")
    cur.execute("""
        SELECT error_message, COUNT(*) AS cnt
        FROM audit_logs
        WHERE action='AUDIT_WRITE_FAILED' AND status='failed'
        GROUP BY error_message
        ORDER BY cnt DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        msg = (row['error_message'] or '<NULL>')[:120]
        print(f"  {row['cnt']:6d}  {msg}")

    # 4. 按 (object_type, action) 聚合（原始 action）
    print(f"\n[按 (object_type, 新值中的 original_action) 聚合 TOP 20]")
    cur.execute("""
        SELECT object_type,
               json_extract(extra_data, '$.original_action') AS orig_action,
               COUNT(*) AS cnt
        FROM audit_logs
        WHERE action='AUDIT_WRITE_FAILED' AND status='failed'
        GROUP BY object_type, orig_action
        ORDER BY cnt DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"  {row['object_type']:25s} {str(row['orig_action']):20s} {row['cnt']:6d}")

    # 5. 时间分布：最近 24h 增长曲线（按小时）
    print(f"\n[最近 24h 增长曲线 (按小时)]")
    cur.execute("""
        SELECT strftime('%Y-%m-%d %H:00', created_at) AS hour, COUNT(*) AS cnt
        FROM audit_logs
        WHERE action='AUDIT_WRITE_FAILED' AND status='failed'
          AND created_at > datetime('now', '-1 day')
        GROUP BY hour
        ORDER BY hour ASC
    """)
    for row in cur.fetchall():
        print(f"  {row['hour']}  {row['cnt']:5d}")

    # 6. 拉取最新 5 条样本，看完整字段
    print(f"\n[最新 5 条 AUDIT_WRITE_FAILED 样本]")
    cur.execute("""
        SELECT id, object_type, object_id, user_name, error_message,
               extra_data, created_at, ip_address, user_agent
        FROM audit_logs
        WHERE action='AUDIT_WRITE_FAILED' AND status='failed'
        ORDER BY id DESC
        LIMIT 5
    """)
    for row in cur.fetchall():
        print(f"\n  --- ID={row['id']} ---")
        print(f"  object_type: {row['object_type']}")
        print(f"  object_id:   {row['object_id']}")
        print(f"  user_name:   {row['user_name']}")
        print(f"  created_at:  {row['created_at']}")
        print(f"  ip_address:  {row['ip_address']}")
        print(f"  error_message: {(row['error_message'] or '')[:200]}")
        print(f"  extra_data: {(row['extra_data'] or '')[:300]}")

    conn.close()
    print("\n" + "=" * 70)
    print("排查完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
