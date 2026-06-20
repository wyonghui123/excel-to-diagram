"""Audit log business view analysis - recent 2 days."""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('meta/architecture.db')
c = conn.cursor()
td = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')

print('=== F. tx_id coverage by action ===')
c.execute("""SELECT action,
  COUNT(*) AS total,
  SUM(CASE WHEN transaction_id IS NOT NULL AND transaction_id != '' THEN 1 ELSE 0 END) AS with_tx
  FROM audit_logs WHERE created_at >= ? GROUP BY action""", (td,))
for row in c.fetchall():
    pct = row[2]*100/row[1] if row[1] else 0
    print(f'  {row[0]:10}  total={row[1]:5}  with_tx={row[2]:5} ({pct:.1f}%)')

print()
print('=== G. tx_id coverage by user_name ===')
c.execute("""SELECT user_name,
  COUNT(*) AS total,
  SUM(CASE WHEN transaction_id IS NOT NULL AND transaction_id != '' THEN 1 ELSE 0 END) AS with_tx
  FROM audit_logs WHERE created_at >= ? GROUP BY user_name""", (td,))
for row in c.fetchall():
    pct = row[2]*100/row[1] if row[1] else 0
    print(f'  {str(row[0]):20}  total={row[1]:5}  with_tx={row[2]:5} ({pct:.1f}%)')

print()
print('=== H. agent_id / tool_call_id / agent_reasoning coverage ===')
c.execute("""SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN agent_id IS NOT NULL AND agent_id != '' THEN 1 ELSE 0 END) AS with_agent,
  SUM(CASE WHEN tool_call_id IS NOT NULL AND tool_call_id != '' THEN 1 ELSE 0 END) AS with_tool,
  SUM(CASE WHEN agent_reasoning IS NOT NULL AND agent_reasoning != '' THEN 1 ELSE 0 END) AS with_reason
  FROM audit_logs WHERE created_at >= ?""", (td,))
r = c.fetchone()
print(f'  total={r[0]}  agent_id={r[1]}  tool_call_id={r[2]}  agent_reasoning={r[3]}')

print()
print('=== I. Hour distribution (peak hour activity) ===')
c.execute("""SELECT strftime('%H', created_at) as hour, COUNT(*) FROM audit_logs
             WHERE created_at >= ? GROUP BY hour ORDER BY hour""", (td,))
for row in c.fetchall():
    print(f'  {row[0]}:00  {row[1]:>4}  {"#"*min(row[1]//10, 50)}')

print()
print('=== J. parent_object_type distribution (cascade / child operations) ===')
c.execute("""SELECT COALESCE(parent_object_type, '<NULL>') AS pt, COUNT(*) FROM audit_logs
             WHERE created_at >= ? GROUP BY pt ORDER BY 2 DESC""", (td,))
for row in c.fetchall():
    print(f'  {row[0]:30} {row[1]:>5}')

print()
print('=== K. The 12 Admin (admin) records - check entry path ===')
c.execute("""SELECT id, transaction_id, agent_id, ip_address, user_agent, parent_object_type
             FROM audit_logs WHERE user_name = 'Admin (admin)' AND created_at >= ? ORDER BY id""", (td,))
for row in c.fetchall():
    ua = row[4][:30] if row[4] else ''
    print(f'  id={row[0]} tx={row[1]!r} agent={row[2]!r} ip={row[3]!r} parent={row[5]!r} ua={ua!r}')

print()
print('=== L. cascade_root_id usage (chain tracking) ===')
c.execute("""SELECT
  SUM(CASE WHEN cascade_root_id IS NOT NULL THEN 1 ELSE 0 END) AS with_root,
  SUM(CASE WHEN cascade_root_action IS NOT NULL THEN 1 ELSE 0 END) AS with_action
  FROM audit_logs WHERE created_at >= ?""", (td,))
r = c.fetchone()
print(f'  cascade_root_id={r[0]}  cascade_root_action={r[1]}')

print()
print('=== M. Hourly bucket activity for last 48 hours ===')
c.execute("""SELECT strftime('%Y-%m-%d %H:00', created_at) as bucket, COUNT(*) FROM audit_logs
             WHERE created_at >= ? GROUP BY bucket ORDER BY bucket""", (td,))
for row in c.fetchall():
    print(f'  {row[0]}  {row[1]:>4}  {"#"*min(row[1]//10, 50)}')

conn.close()