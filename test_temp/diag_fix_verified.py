# -*- coding: utf-8 -*-
"""验证最新修复效果：看最近 10 分钟的 audit log"""
import sqlite3
import json

DB = r'd:/filework/excel-to-diagram/meta/architecture.db'
conn = sqlite3.connect(DB, timeout=10)
cur = conn.cursor()

print('=== 最近 10 分钟的 audit_logs (新生成) ===')
cur.execute("""
    SELECT id, action, object_type, object_id, user_name, ip_address, user_agent,
           trace_id, transaction_id
    FROM audit_logs
    WHERE created_at >= datetime('now', '-10 minutes')
    ORDER BY id DESC
""")
cols = ['id', 'action', 'obj_type', 'obj_id', 'user_name', 'ip', 'ua', 'trace_id', 'tx_id']
rows = cur.fetchall()
print(f'总计: {len(rows)}')
for r in rows[:30]:
    print(f'  ID={r[0]:5d} {r[1]:<14} {r[2]:<20}#{r[3]:<5} ua={r[6][:30]!r:<32} trace={r[7][:8] if r[7] else "None":<10}')

print('\n=== 修复后统计 (新生成数据) ===')
n_diss = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='DISSOCIATE' AND created_at >= datetime('now', '-10 minutes')").fetchone()[0]
n_diss_trace = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='DISSOCIATE' AND created_at >= datetime('now', '-10 minutes') AND (trace_id IS NOT NULL AND trace_id != '')").fetchone()[0]
n_diss_ua = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='DISSOCIATE' AND created_at >= datetime('now', '-10 minutes') AND (user_agent IS NOT NULL AND user_agent != '')").fetchone()[0]
print(f'  DISSOCIATE: {n_diss_trace}/{n_diss} 有 trace_id ({100*n_diss_trace/max(n_diss,1):.1f}%)')
print(f'  DISSOCIATE: {n_diss_ua}/{n_diss} 有 user_agent ({100*n_diss_ua/max(n_diss,1):.1f}%)')

# 验证 target_display
n_diss_td = 0
n_diss_with_payload = 0
for row in cur.execute("""
    SELECT old_value, new_value FROM audit_logs
    WHERE action='DISSOCIATE' AND created_at >= datetime('now', '-10 minutes')
"""):
    payload = row[0] or row[1] or ''
    if payload:
        try:
            p = json.loads(payload)
            n_diss_with_payload += 1
            if p.get('target_display'):
                n_diss_td += 1
        except Exception:
            pass
print(f'  DISSOCIATE: {n_diss_td}/{n_diss_with_payload} 有 target_display ({100*n_diss_td/max(n_diss_with_payload,1):.1f}%)')

# 看 1-2 个有 target_display 的样本
print('\n=== DISSOCIATE 新样本 (有 target_display) ===')
n = 0
for row in cur.execute("""
    SELECT id, action, object_type, object_id, old_value, new_value, user_name, trace_id, user_agent
    FROM audit_logs
    WHERE action='DISSOCIATE' AND created_at >= datetime('now', '-10 minutes')
    ORDER BY id DESC LIMIT 100
"""):
    payload = row[4] or row[5] or ''
    try:
        p = json.loads(payload)
        if p.get('target_display') and n < 3:
            print(f'  ID={row[0]} obj={row[2]}#{row[3]} user={row[6]!r}')
            print(f'    payload: {p}')
            print(f'    trace_id={row[7][:8] if row[7] else None} ua={row[8][:40]!r}')
            n += 1
    except Exception:
        pass

# 看 DELETE_BLOCKED 完整可读性
print('\n=== DELETE_BLOCKED 完整内容 (可读性) ===')
for row in cur.execute("""
    SELECT id, object_type, object_id, user_name, trace_id, extra_data
    FROM audit_logs
    WHERE action = 'DELETE_BLOCKED'
    ORDER BY id DESC LIMIT 2
"""):
    print(f'ID={row[0]} {row[1]}#{row[2]} user={row[3]!r} trace={row[4][:8] if row[4] else None}')
    try:
        ed = json.loads(row[5] or '{}')
        print(f'  blocked={ed.get("blocked")} error_code={ed.get("error_code")}')
        print(f'  message: {ed.get("message")}')
        print(f'  recovery: {ed.get("recovery", ed.get("recovery_suggestion", ed.get("hint", "<none>")))}')
    except Exception as e:
        print(f'  raw: {row[5]}')
