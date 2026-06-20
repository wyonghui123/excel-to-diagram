"""Business view analysis v3."""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('meta/architecture.db')
c = conn.cursor()
td = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')

print('=== N. system user - ip/ua breakdown ===')
c.execute("""SELECT COALESCE(ip_address, 'NULL'), COALESCE(user_agent, 'NULL'), COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND user_name = 'system' GROUP BY ip_address, user_agent ORDER BY 3 DESC""", (td,))
for r in c.fetchall():
    print(f'  ip={r[0]:15} ua={r[1][:40]:40} count={r[2]}')

print()
print('=== O. UPDATE NULL fields ===')
c.execute("""SELECT COUNT(*) FROM audit_logs WHERE created_at >= ? AND action = 'UPDATE' AND (old_value IS NULL OR new_value IS NULL)""", (td,))
print('  UPDATE with NULL old/new:', c.fetchone()[0])

print()
print('=== P. UPDATE field_name distribution ===')
c.execute("""SELECT field_name, COUNT(*) FROM audit_logs WHERE created_at >= ? AND action = 'UPDATE' GROUP BY field_name ORDER BY 2 DESC""", (td,))
for r in c.fetchall():
    print(f'  {str(r[0]):35} {r[1]}')

print()
print('=== Q. 19:00 activity (bulk import) ===')
c.execute("""SELECT strftime('%Y-%m-%d %H:%M', created_at), COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND strftime('%H', created_at) = '19' GROUP BY 1 ORDER BY 1""", (td,))
for r in c.fetchall():
    print(f'  {r[0]} {r[1]}')

print()
print('=== R. system user range ===')
c.execute("""SELECT MIN(created_at), MAX(created_at), COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND user_name = 'system'""", (td,))
print('  ', c.fetchone())

print()
print('=== S. last 24h by user ===')
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
c.execute("""SELECT user_name, COUNT(*) FROM audit_logs WHERE created_at >= ? GROUP BY user_name ORDER BY 2 DESC""", (yesterday,))
for r in c.fetchall():
    print(f'  {str(r[0]):25} {r[1]}')

print()
print('=== T. Admin (admin) ua distribution ===')
c.execute("""SELECT DISTINCT user_agent, COUNT(*) FROM audit_logs WHERE user_name = 'Admin (admin)' AND created_at >= ? GROUP BY user_agent""", (td,))
for r in c.fetchall():
    print(f'  ua={r[0]!r} count={r[1]}')

print()
print('=== U. Admin (admin) check ALL time ===')
c.execute("""SELECT COUNT(*) FROM audit_logs WHERE user_name = 'Admin (admin)'""")
print('  All-time Admin (admin) count:', c.fetchone()[0])
c.execute("""SELECT MIN(created_at), MAX(created_at) FROM audit_logs WHERE user_name = 'Admin (admin)'""")
print('  range:', c.fetchone())

print()
print('=== V. outcome by action (was anything failed?) ===')
c.execute("""SELECT action, outcome, COUNT(*) FROM audit_logs WHERE created_at >= ? GROUP BY action, outcome ORDER BY action""", (td,))
for r in c.fetchall():
    print(f'  {r[0]:10} {r[1]:15} {r[2]}')

print()
print('=== W. retention_until populated? ===')
c.execute("""SELECT SUM(CASE WHEN retention_until IS NOT NULL THEN 1 ELSE 0 END), COUNT(*) FROM audit_logs WHERE created_at >= ?""", (td,))
r = c.fetchone()
print(f'  retention set: {r[0]}/{r[1]} ({r[0]*100/r[1]:.1f}%)')

print()
print('=== X. row_hash coverage (immutable proof) ===')
c.execute("""SELECT SUM(CASE WHEN row_hash IS NOT NULL AND row_hash != '' THEN 1 ELSE 0 END), COUNT(*) FROM audit_logs WHERE created_at >= ?""", (td,))
r = c.fetchone()
print(f'  row_hash set: {r[0]}/{r[1]} ({r[0]*100/r[1]:.1f}%)')

print()
print('=== Y. Do 12 Admin(admin) records share with non-leak records? ===')
c.execute("""SELECT a.transaction_id, a2.user_name, COUNT(*)
             FROM audit_logs a LEFT JOIN audit_logs a2 ON a.transaction_id = a2.transaction_id
             WHERE a.user_name = 'Admin (admin)' AND a.created_at >= ?
             GROUP BY a.transaction_id, a2.user_name""", (td,))
for r in c.fetchall():
    print(f'  tx={r[0][:20]} user={r[1]} count={r[2]}')

print()
print('=== Z. Same tx_id, mixed user_names? ===')
c.execute("""SELECT transaction_id, COUNT(DISTINCT user_name) FROM audit_logs
             WHERE created_at >= ? AND transaction_id IS NOT NULL
             GROUP BY transaction_id HAVING COUNT(DISTINCT user_name) > 1 LIMIT 5""", (td,))
for r in c.fetchall():
    print(f'  tx={r[0]} users={r[1]}')

conn.close()