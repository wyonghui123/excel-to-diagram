"""
P2-1: 迁移 8 条 status=failed (action_kind schema 错误已修) 为 status=retried
"""
import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 1. 确认迁移前数量
cur.execute("SELECT COUNT(*) FROM audit_logs WHERE status='failed'")
before = cur.fetchone()[0]
print(f'迁移前 status=failed: {before}')

# 2. 迁移
cur.execute("""
    UPDATE audit_logs
    SET status = 'retried',
        error_message = error_message || ' | [migrated 2026-06-15] action_kind->action schema mismatch resolved, manually retried'
    WHERE status = 'failed'
        AND error_message LIKE '%action_kind%'
""")
conn.commit()
print(f'迁移影响行数: {cur.rowcount}')

# 3. 确认迁移后
cur.execute("SELECT COUNT(*) FROM audit_logs WHERE status='failed'")
after = cur.fetchone()[0]
print(f'迁移后 status=failed: {after}')

# 4. 验证
cur.execute("""
    SELECT id, action, status, error_message
    FROM audit_logs
    WHERE error_message LIKE '%migrated 2026-06-15%'
    ORDER BY id
""")
print('\n已迁移的记录:')
for row in cur.fetchall():
    print(f'  [{row[0]}] {row[1]:15s} status={row[2]:8s} err={row[3][:120]}')

conn.close()
