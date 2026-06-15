# -*- coding: utf-8 -*-
"""快速审计问题诊断"""
import sqlite3
import json
import sys

DB = r'd:/filework/excel-to-diagram/meta/architecture.db'
conn = sqlite3.connect(DB, timeout=10)
cur = conn.cursor()

print('=== DISSOCIATE 缺 trace_id 样本 (5条) ===')
for row in cur.execute("""
    SELECT id, action, object_type, object_id, user_name, ip_address, user_agent,
           trace_id, transaction_id, old_value, new_value, extra_data
    FROM audit_logs
    WHERE action = 'DISSOCIATE' AND (trace_id IS NULL OR trace_id = '')
    ORDER BY id DESC LIMIT 5
"""):
    print(f'ID={row[0]} action={row[1]} obj={row[2]}#{row[3]} user={row[4]} ua={row[6]!r} trace={row[7]!r}')
    print(f'  old_value={(row[9] or "")[:200]}')
    print(f'  new_value={(row[10] or "")[:200]}')
    print(f'  extra_data={(row[11] or "")[:200]}')
    print()

print('=== DISSOCIATE 缺 trace_id 总数 ===')
cnt = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='DISSOCIATE' AND (trace_id IS NULL OR trace_id='')").fetchone()[0]
total_dis = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='DISSOCIATE'").fetchone()[0]
print(f'  DISSOCIATE 总数: {total_dis}, 缺 trace_id: {cnt} ({100*cnt/total_dis:.1f}%)')

print('\n=== DISSOCIATE 缺 user_agent 比例 ===')
cnt2 = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='DISSOCIATE' AND (user_agent IS NULL OR user_agent='')").fetchone()[0]
print(f'  DISSOCIATE 缺 user_agent: {cnt2}/{total_dis} ({100*cnt2/total_dis:.1f}%)')

print('\n=== ASSOCIATE 缺 user_agent 比例 ===')
cnt3 = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='ASSOCIATE' AND (user_agent IS NULL OR user_agent='')").fetchone()[0]
total_ass = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='ASSOCIATE'").fetchone()[0]
print(f'  ASSOCIATE 缺 user_agent: {cnt3}/{total_ass} ({100*cnt3/total_ass:.1f}%)')

print('\n=== target_display 缺失样本 (3条) ===')
n_missing = 0
for row in cur.execute("""
    SELECT id, action, object_type, object_id, new_value, old_value
    FROM audit_logs
    WHERE action IN ('ASSOCIATE', 'DISSOCIATE')
    ORDER BY id DESC LIMIT 200
"""):
    payload_str = row[4] or row[5] or ''
    try:
        p = json.loads(payload_str)
        if not p.get('target_display'):
            n_missing += 1
            if n_missing <= 3:
                print(f'ID={row[0]} {row[1]} {row[2]}#{row[3]} target={p.get("target_type")}#{p.get("target_id")} display={p.get("target_display")!r}')
    except Exception:
        pass
print(f'  200条样本中 target_display 缺失: {n_missing}')

print('\n=== DELETE_BLOCKED 样本 (看可理解性) ===')
for row in cur.execute("""
    SELECT id, object_type, object_id, user_name, action, new_value, old_value, extra_data, trace_id, log_level
    FROM audit_logs
    WHERE action = 'DELETE_BLOCKED'
    ORDER BY id DESC LIMIT 5
"""):
    print(f'ID={row[0]} {row[4]} {row[1]}#{row[2]} user={row[3]} trace={row[8]} log_level={row[9]}')
    print(f'  new_value={(row[5] or "")[:200]}')
    print(f'  extra_data={(row[7] or "")[:200]}')

print('\n=== AUDIT_WRITE_FAILED 样本 (看可理解性) ===')
for row in cur.execute("""
    SELECT id, object_type, object_id, user_name, action, new_value, old_value, extra_data, trace_id, log_level
    FROM audit_logs
    WHERE action = 'AUDIT_WRITE_FAILED'
    ORDER BY id DESC LIMIT 5
"""):
    print(f'ID={row[0]} {row[4]} {row[1]}#{row[2]} user={row[3]} trace={row[8]} log_level={row[9]}')
    print(f'  new_value={(row[5] or "")[:200]}')
    print(f'  extra_data={(row[7] or "")[:200]}')

print('\n=== 看 log_level/outcome/log_category 字段类型 ===')
for row in cur.execute("PRAGMA table_info(audit_logs)"):
    if row[1] in ('log_level', 'outcome', 'action_kind', 'log_category', 'parent_action_id', 'log_category'):
        print(f'  {row[1]}: type={row[2]}')

print('\n=== 看 v2 字段 (log_category, log_level) 填充率 ===')
total = cur.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0]
for col in ('log_category', 'log_level', 'parent_object_type', 'parent_object_id'):
    cnt = cur.execute(f"SELECT COUNT(*) FROM audit_logs WHERE {col} IS NOT NULL AND {col} != ''").fetchone()[0]
    print(f'  {col}: {cnt}/{total} ({100*cnt/total:.1f}%)')
