import sqlite3
conn = sqlite3.connect('meta/architecture.db')

# 查询 AUDIT_WRITE_FAILED 总数
cur = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='AUDIT_WRITE_FAILED'")
print('AUDIT_WRITE_FAILED count:', cur.fetchone()[0])

# 查询已重试的记录数
cur = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='AUDIT_WRITE_FAILED' AND status='retried'")
print('Retried count:', cur.fetchone()[0])

# 查询待重试的记录数
cur = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='AUDIT_WRITE_FAILED' AND status='failed'")
print('Failed (pending retry) count:', cur.fetchone()[0])

conn.close()
