import sqlite3
conn = sqlite3.connect('meta/architecture.db')
c = conn.cursor()
c.execute('SELECT status, COUNT(*) FROM audit_logs GROUP BY status ORDER BY 2 DESC')
print('=== audit_logs status 分布 ===')
for r in c.fetchall():
    print(f'  {r[0]:15s} {r[1]:5d}')

c.execute("SELECT COUNT(*) FROM audit_logs WHERE error_message LIKE '%migrated 2026-06-15%'")
print(f'\n  migrated 标记: {c.fetchone()[0]} (期望 8)')

c.execute("SELECT COUNT(*) FROM audit_logs WHERE status='failed'")
print(f"  status=failed: {c.fetchone()[0]} (期望 0)")

c.execute("SELECT COUNT(*) FROM audit_logs WHERE object_type='__audit_failure__'")
print(f"  __audit_failure__ 总: {c.fetchone()[0]} (read 端默认过滤掉)")
