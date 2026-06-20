"""Daily trend analysis."""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('meta/architecture.db')
c = conn.cursor()

print('=== Daily activity (last 14 days) ===')
c.execute("""SELECT strftime('%Y-%m-%d', created_at) as day, COUNT(*) FROM audit_logs
             WHERE created_at >= date('now', '-14 days') GROUP BY day ORDER BY day""")
for r in c.fetchall():
    print(f'  {r[0]}  {r[1]:>5}  {"#"*min(r[1]//20, 60)}')

print()
print('=== Total audit_logs / archived ===')
c.execute("SELECT COUNT(*) FROM audit_logs")
print('  audit_logs total:', c.fetchone()[0])
c.execute("SELECT COUNT(*) FROM audit_logs_archive")
print('  audit_logs_archive:', c.fetchone()[0])

print()
print('=== Audit log row_hash status (all time) ===')
c.execute("""SELECT SUM(CASE WHEN row_hash IS NOT NULL AND row_hash != '' THEN 1 ELSE 0 END), COUNT(*) FROM audit_logs""")
r = c.fetchone()
print(f'  row_hash: {r[0]}/{r[1]} ({r[0]*100/r[1]:.2f}%)')

print()
print('=== Audit log prev_hash status (all time) ===')
c.execute("""SELECT SUM(CASE WHEN prev_hash IS NOT NULL AND prev_hash != '' THEN 1 ELSE 0 END), COUNT(*) FROM audit_logs""")
r = c.fetchone()
print(f'  prev_hash: {r[0]}/{r[1]} ({r[0]*100/r[1]:.2f}%)')

conn.close()