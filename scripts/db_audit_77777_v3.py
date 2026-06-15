#!/usr/bin/env python3
"""查 audit_logs 中所有 TEST77777 的真实记录"""
import sqlite3
import json

db_path = 'd:/filework/excel-to-diagram/meta/architecture.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 列名
cols = ['id', 'object_type', 'object_id', 'action', 'field_name', 'old_value', 'new_value',
        'user_id', 'user_name', 'ip_address', 'user_agent', 'created_at', 'extra_data',
        'log_category', 'log_level', 'parent_object_type', 'parent_object_id', 'trace_id',
        'transaction_id', 'status', 'status_entered_at', 'retry_count', 'error_message',
        'agent_id', 'agent_session_id', 'tool_call_id', 'agent_reasoning', 'outcome',
        'cascade_root_id', 'cascade_root_action', 'retention_until', 'prev_hash', 'row_hash']

# 查所有含 TEST77777 的 audit
print('=== audit_logs 中所有含 TEST77777 的记录 (按 id 倒序) ===')
cur.execute("""
SELECT id, object_type, object_id, action, field_name, user_id, ip_address, created_at, status, outcome, cascade_root_action, extra_data
FROM audit_logs
WHERE extra_data LIKE '%TEST77777%' OR new_value LIKE '%TEST77777%' OR old_value LIKE '%TEST77777%'
ORDER BY id DESC LIMIT 50
""")
for row in cur.fetchall():
    aid, otype, oid, action, fname, uid, ip, ts, status, outcome, cascade_action, extra = row
    extra_short = (extra or '')[:200]
    print(f'  id={aid} {action:6} {otype:12}:{oid:4} field={fname:15} user={uid} ip={ip}')
    print(f'    ts={ts} status={status} outcome={outcome} cascade={cascade_action}')
    if extra_short:
        print(f'    extra={extra_short}')

# 查 15:00-15:09 之间所有 product CREATE
print('\n=== 15:00-15:09 之间所有 CREATE product 记录 ===')
cur.execute("""
SELECT id, object_id, user_id, ip_address, created_at, status, outcome, extra_data
FROM audit_logs
WHERE object_type='product' AND action='CREATE'
  AND created_at >= '2026-06-14 15:00' AND created_at <= '2026-06-14 15:10'
ORDER BY id
""")
for row in cur.fetchall():
    aid, oid, uid, ip, ts, status, outcome, extra = row
    extra_short = (extra or '')[:300]
    print(f'  id={aid} product:{oid} user={uid} ip={ip} ts={ts} status={status} outcome={outcome}')
    if extra_short:
        print(f'    extra={extra_short}')

# 查 trace_id 关联: 找有 deep_insert 的事务
print('\n=== 找 transaction_id 包含 TEST77777 的事务 ===')
cur.execute("""
SELECT DISTINCT transaction_id, MIN(created_at), MAX(created_at), COUNT(*)
FROM audit_logs
WHERE (extra_data LIKE '%TEST77777%' OR new_value LIKE '%TEST77777%' OR old_value LIKE '%TEST77777%')
  AND transaction_id IS NOT NULL
GROUP BY transaction_id
""")
for row in cur.fetchall():
    tid, min_ts, max_ts, cnt = row
    print(f'  tx={tid} {min_ts} -> {max_ts} ({cnt} 条)')

conn.close()
