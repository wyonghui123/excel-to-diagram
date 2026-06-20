"""Business view analysis v4 - final."""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('meta/architecture.db')
c = conn.cursor()
td = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')

print('=== AA. CREATE by user + count breakdown ===')
c.execute("""SELECT user_name, COUNT(*), COUNT(DISTINCT transaction_id), COUNT(DISTINCT object_type)
             FROM audit_logs WHERE created_at >= ? AND action = 'CREATE' GROUP BY user_name""", (td,))
for r in c.fetchall():
    print(f'  {str(r[0]):20} total={r[1]} distinct_tx={r[2]} distinct_obj={r[3]}')

print()
print('=== BB. total distinct tx_id ===')
c.execute("""SELECT COUNT(DISTINCT transaction_id) FROM audit_logs WHERE created_at >= ?""", (td,))
print('  distinct tx_id:', c.fetchone()[0])

print()
print('=== CC. records per transaction distribution ===')
c.execute("""SELECT cnt, COUNT(*) as tx_count FROM (
             SELECT transaction_id, COUNT(*) as cnt FROM audit_logs
             WHERE created_at >= ? AND transaction_id IS NOT NULL
             GROUP BY transaction_id)
             GROUP BY cnt ORDER BY cnt""", (td,))
for r in c.fetchall():
    print(f'  {r[0]:4} records/tx  ->  {r[1]:4} transactions')

print()
print('=== DD. records WITHOUT tx_id by user ===')
c.execute("""SELECT user_name, COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND (transaction_id IS NULL OR transaction_id = '')
             GROUP BY user_name""", (td,))
for r in c.fetchall():
    print(f'  {str(r[0]):20} no_tx={r[1]}')

print()
print('=== EE. system user -- actions ===')
c.execute("""SELECT action, COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND user_name = 'system' GROUP BY action""", (td,))
for r in c.fetchall():
    print(f'  {r[0]:10} {r[1]}')

print()
print('=== FF. system user -- objects ===')
c.execute("""SELECT object_type, COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND user_name = 'system' GROUP BY object_type ORDER BY 2 DESC""", (td,))
for r in c.fetchall():
    print(f'  {r[0]:25} {r[1]}')

print()
print('=== GG. outcome ===')
c.execute("""SELECT outcome, COUNT(*) FROM audit_logs WHERE created_at >= ? GROUP BY outcome""", (td,))
for r in c.fetchall():
    print(f'  {r[0]:15} {r[1]}')

print()
print('=== HH. Recent 7 days UNKNOWN / failures ===')
seven_days = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
c.execute("""SELECT outcome, action, COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND (outcome != 'success' OR action = 'UNKNOWN')
             GROUP BY outcome, action""", (seven_days,))
rows = c.fetchall()
if not rows:
    print('  No failures / UNKNOWN in last 7 days')
else:
    for r in rows:
        print(f'  {r[0]:15} {r[1]:10} {r[2]}')

print()
print('=== II. audit_logs_archive total ===')
c.execute("SELECT COUNT(*) FROM audit_logs_archive")
print('  archive total:', c.fetchone()[0])

print()
print('=== JJ. Top parent_object_type combinations (object hierarchy depth) ===')
c.execute("""SELECT parent_object_type, object_type, COUNT(*) FROM audit_logs
             WHERE created_at >= ? AND parent_object_type IS NOT NULL
             GROUP BY parent_object_type, object_type ORDER BY 3 DESC LIMIT 15""", (td,))
for r in c.fetchall():
    print(f'  parent={r[0]:20} child={r[1]:25} {r[2]}')

conn.close()