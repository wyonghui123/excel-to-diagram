"""检查 audit_logs 表索引情况"""
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

print('=== audit_logs 表所有索引 ===')
cur.execute("PRAGMA index_list(audit_logs)")
for row in cur.fetchall():
    idx_name = row[1]
    cur.execute(f"PRAGMA index_info({idx_name})")
    cols = [c[2] for c in cur.fetchall()]
    print(f'  {idx_name:30s}  {cols}')

# EXPLAIN QUERY PLAN for our /audit/logs query
print()
print('=== EXPLAIN QUERY PLAN (object_type=X AND object_id=Y) ===')
cur.execute("""
    EXPLAIN QUERY PLAN
    SELECT * FROM audit_logs
    WHERE object_type = ? AND object_id = ?
        AND (parent_object_id = ? OR (parent_object_id IS NULL AND object_id = ?))
    ORDER BY created_at DESC LIMIT 20
""", ('domain', 683, 683, 683))
for row in cur.fetchall():
    print(f'  {row[3]}')

print()
print('=== EXPLAIN QUERY PLAN (OR 联合查询) ===')
cur.execute("""
    EXPLAIN QUERY PLAN
    SELECT * FROM audit_logs
    WHERE (object_type = ? AND object_id = ?)
       OR (parent_object_id = ?)
    ORDER BY created_at DESC LIMIT 20
""", ('domain', 683, 683))
for row in cur.fetchall():
    print(f'  {row[3]}')

print()
print('=== 当前实际查询条件 (status=written, 不算) ===')
cur.execute("""
    EXPLAIN QUERY PLAN
    SELECT * FROM audit_logs
    WHERE (object_type = ? AND object_id = ?) OR (parent_object_type = ? AND parent_object_id = ?)
    ORDER BY created_at DESC LIMIT 20
""", ('domain', 683, 'domain', 683))
for row in cur.fetchall():
    print(f'  {row[3]}')

conn.close()
