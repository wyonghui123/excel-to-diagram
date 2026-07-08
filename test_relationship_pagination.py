"""完整模拟 VirtualSort 在 yonaa 上的 page=3, page_size=500, offset=1000 场景"""
import sqlite3
import time

db = r'D:\filework\release-prep-worktree\meta\architecture.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

# 模拟 execute_virtual_field_query 的实际 SQL 路径
def query_relationship_page(page, page_size):
    """完整模拟 VirtualSort SQL"""
    offset = (page - 1) * page_size
    table_name = 'relationships'

    # 1. count_sql
    count_sql = f"SELECT COUNT(*) as cnt FROM {table_name}"
    cur.execute(count_sql)
    total = cur.fetchone()[0]
    print(f'  total: {total}')

    # 2. subquery with JOIN
    subquery_select = f"""
    SELECT {table_name}.*, _audit_sort._audit_value AS _sort_val
    FROM {table_name}
    LEFT JOIN (
        SELECT object_id, MAX(created_at) AS _audit_value
        FROM audit_logs
        WHERE object_type = 'relationship' AND action = 'UPDATE'
        GROUP BY object_id
    ) _audit_sort ON _audit_sort.object_id = {table_name}.id
    """

    sql_with_join = f"""
    SELECT _vsq.* FROM ({subquery_select}) AS _vsq
    ORDER BY _vsq._sort_val DESC
    LIMIT {page_size} OFFSET {offset}
    """

    start = time.time()
    cur.execute(sql_with_join)
    rows = cur.fetchall()
    elapsed = (time.time() - start) * 1000
    print(f'  page={page}, page_size={page_size}, offset={offset}: {elapsed:.0f}ms, {len(rows)} rows')
    return elapsed, len(rows)


print('测试分页查询:')
total_time = 0
for page in [1, 2, 3]:
    elapsed, rows = query_relationship_page(page, 500)
    total_time += elapsed

print(f'\n3 页累计: {total_time:.0f}ms')

# 看是否有索引
print('\n索引检查:')
cur.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND tbl_name='audit_logs'")
for row in cur.fetchall():
    print(f'  {row}')

conn.close()