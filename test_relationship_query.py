"""模拟 VirtualSort 给 relationship 加的 JOIN, 验证是否会触发问题"""
import sqlite3
import time
import sys

sys.path.insert(0, r'D:\filework\release-prep-worktree')

db = r'D:\filework\release-prep-worktree\meta\architecture.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

# 模拟 VirtualSort 给 relationship 加的 JOIN (来自 HANDOFF §2.2)
sql = """
SELECT *
FROM relationships
LEFT JOIN (
    SELECT object_id, MAX(created_at) AS _audit_value
    FROM audit_logs
    WHERE object_type = 'relationship' AND action = 'UPDATE'
    GROUP BY object_id
) _audit_sort ON _audit_sort.object_id = relationships.id
ORDER BY COALESCE(_audit_sort._audit_value, relationships.created_at) DESC
LIMIT 10
"""

start = time.time()
try:
    cur.execute(sql)
    rows = cur.fetchall()
    print(f'[OK] 查询成功, 耗时 {(time.time() - start) * 1000:.1f}ms, 返回 {len(rows)} 行')
    for r in rows[:3]:
        print(f'  {r[:5]}...')
except Exception as e:
    print(f'[FAIL] 查询失败: {e}')

# 测试 audit_logs 的 MAX(created_at) 聚合有多慢
print('\n测试 audit_logs 聚合性能:')
for size in [100, 500, 1000, 5000]:
    start = time.time()
    cur.execute(f"""
        SELECT object_id, MAX(created_at) AS _audit_value
        FROM audit_logs
        WHERE object_type = 'relationship' AND action = 'UPDATE'
        GROUP BY object_id
        LIMIT {size}
    """)
    rows = cur.fetchall()
    print(f'  LIMIT {size}: {(time.time() - start) * 1000:.1f}ms, {len(rows)} rows')

# 看 audit_logs 表大小
cur.execute("SELECT COUNT(*) FROM audit_logs")
print(f'\naudit_logs 总行数: {cur.fetchone()[0]}')

cur.execute("SELECT COUNT(*) FROM audit_logs WHERE object_type='relationship' AND action='UPDATE'")
print(f"audit_logs relationship/UPDATE 行数: {cur.fetchone()[0]}")

# 看 relationships 表大小
cur.execute("SELECT COUNT(*) FROM relationships")
print(f'relationships 总行数: {cur.fetchone()[0]}')

conn.close()