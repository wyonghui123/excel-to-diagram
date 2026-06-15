# -*- coding: utf-8 -*-
"""[MODULE] 查 user_agent 缺失新原因"""
import sqlite3

DB_PATH = r'd:/filework/excel-to-diagram/meta/architecture.db'

conn = sqlite3.connect(DB_PATH, timeout=10)
cur = conn.cursor()

print("=== 最近 10 分钟 user_agent 缺失按 action ===")
cur.execute("""
    SELECT action,
           COUNT(*) as total,
           SUM(CASE WHEN user_agent IS NULL OR user_agent = '' THEN 1 ELSE 0 END) as missing
    FROM audit_logs
    WHERE created_at >= datetime('now', '-10 minutes')
    GROUP BY action
    HAVING total > 5
    ORDER BY total DESC
""")
for r in cur.fetchall():
    rate = r[2] / r[1] * 100 if r[1] else 0
    print(f"  {r[0]:<20} total={r[1]:>5} missing={r[2]:>5} ({rate:.1f}%)")

print("\n=== CREATE user 缺失 user_agent 的最新 3 条 ===")
cur.execute("""
    SELECT id, action, object_type, object_id, user_name, ip_address, trace_id, user_agent
    FROM audit_logs
    WHERE action = 'CREATE' AND object_type = 'user'
      AND (user_agent IS NULL OR user_agent = '')
      AND created_at >= datetime('now', '-10 minutes')
    ORDER BY id DESC LIMIT 3
""")
for r in cur.fetchall():
    print(f"  ID={r[0]} {r[1]} {r[2]}#{r[3]} by {r[4]} trace_id={r[6][:8] if r[6] else 'NONE'} ua='{r[7]}'")

print("\n=== ASSOCIATE 的最新 5 条 (是否已修) ===")
cur.execute("""
    SELECT id, action, object_type, object_id, user_name, trace_id, user_agent
    FROM audit_logs
    WHERE action = 'ASSOCIATE'
    ORDER BY id DESC LIMIT 5
""")
for r in cur.fetchall():
    print(f"  ID={r[0]} {r[1]} {r[2]}#{r[3]} by {r[4]} trace_id={r[5][:8] if r[5] else 'NONE'} ua='{r[6][:30] if r[6] else 'NONE'}'")

print("\n=== DISSOCIATE 的最新 5 条 (cascade 是否还有) ===")
cur.execute("""
    SELECT id, action, object_type, object_id, user_name, trace_id, user_agent, extra_data
    FROM audit_logs
    WHERE action = 'DISSOCIATE'
    ORDER BY id DESC LIMIT 5
""")
for r in cur.fetchall():
    is_cascade = 'cascade_reason' in (r[7] or '')
    print(f"  ID={r[0]} {r[1]} {r[2]}#{r[3]} by {r[4]} ua='{r[6][:20] if r[6] else 'NONE'}' cascade={is_cascade}")

conn.close()
