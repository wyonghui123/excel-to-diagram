"""Failure and retry analysis."""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('meta/architecture.db')
c = conn.cursor()
seven_days = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
two_days = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')

print('=== Failure status distribution (last 7 days, ALL statuses) ===')
c.execute("""SELECT COALESCE(status, 'NULL') as s, COALESCE(outcome, 'NULL') as o, COUNT(*) FROM audit_logs
             WHERE created_at >= ? GROUP BY s, o ORDER BY 3 DESC""", (seven_days,))
for r in c.fetchall():
    print(f'  status={r[0]:20} outcome={r[1]:15} {r[2]}')

print()
print('=== Failure records in last 2 days (action, status, object_type) ===')
c.execute("""SELECT action, COALESCE(status, 'NULL') as s, object_type, COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND (status != 'success' AND status IS NOT NULL)
             GROUP BY action, status, object_type ORDER BY 4 DESC""", (two_days,))
rows = c.fetchall()
print(f'  total: {sum(r[3] for r in rows)}')
for r in rows:
    print(f'  {r[0]:15} status={r[1]:15} obj={r[2]:25} {r[3]}')

print()
print('=== retry_count distribution (recent 2 days) ===')
c.execute("""SELECT retry_count, COUNT(*) FROM audit_logs WHERE created_at >= ? GROUP BY retry_count""", (two_days,))
for r in c.fetchall():
    print(f'  retry={r[0]}  count={r[1]}')

print()
print('=== records with retry_count > 0 ===')
c.execute("""SELECT id, action, object_type, retry_count, status, error_message, created_at
             FROM audit_logs WHERE created_at >= ? AND retry_count > 0 ORDER BY retry_count DESC LIMIT 5""", (two_days,))
for r in c.fetchall():
    em = (r[5][:50] if r[5] else '')
    print(f'  id={r[0]} {r[1]:10} obj={r[2]:20} retry={r[3]} status={r[4]} err={em!r}')

print()
print('=== Top failed operations detail ===')
c.execute("""SELECT id, action, object_type, object_id, status, error_message, user_name, created_at
             FROM audit_logs WHERE created_at >= ? AND status = 'AUDIT_WRITE_FAILED' ORDER BY created_at DESC LIMIT 5""", (two_days,))
for r in c.fetchall():
    em = (r[5][:60] if r[5] else '')
    print(f'  id={r[0]} {r[1]} obj={r[2]}/{r[3]} status={r[4]} user={r[6]} err={em!r}')

conn.close()