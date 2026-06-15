"""
Audit Log 全面审查
"""
import sqlite3
import json
from collections import Counter, defaultdict
from datetime import datetime

conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 1. Schema
print('=' * 80)
print('1. audit_logs 表 Schema')
print('=' * 80)
cur.execute("PRAGMA table_info(audit_logs)")
for col in cur.fetchall():
    print(f'  {col[1]:30s} {col[2]:15s} {"NULL" if col[3] else "NOT NULL"}')

# 2. 总量
print()
print('=' * 80)
print('2. 总量统计')
print('=' * 80)
cur.execute("SELECT COUNT(*) FROM audit_logs")
total = cur.fetchone()[0]
print(f'  audit_logs 总条数: {total}')
cur.execute("SELECT MIN(created_at), MAX(created_at) FROM audit_logs")
row = cur.fetchone()
print(f'  时间范围: {row[0]} ~ {row[1]}')

# 3. 按 object_type 分布
print()
print('=' * 80)
print('3. 按 object_type 分布 (Top 30)')
print('=' * 80)
cur.execute("""
    SELECT object_type, COUNT(*) as cnt
    FROM audit_logs
    GROUP BY object_type
    ORDER BY cnt DESC
    LIMIT 30
""")
for row in cur.fetchall():
    bar = '█' * min(50, row[1] // 10)
    print(f'  {row[0]:25s} {row[1]:6d}  {bar}')

# 4. 按 action 分布
print()
print('=' * 80)
print('4. 按 action 分布')
print('=' * 80)
cur.execute("""
    SELECT action, COUNT(*) as cnt
    FROM audit_logs
    GROUP BY action
    ORDER BY cnt DESC
""")
for row in cur.fetchall():
    bar = '█' * min(50, row[1] // 10)
    print(f'  {row[0]:20s} {row[1]:6d}  {bar}')

# 5. 按 status 分布
print()
print('=' * 80)
print('5. 按 status 分布')
print('=' * 80)
cur.execute("""
    SELECT status, COUNT(*) as cnt
    FROM audit_logs
    GROUP BY status
    ORDER BY cnt DESC
""")
for row in cur.fetchall():
    bar = '█' * min(50, row[1] // 10)
    print(f'  {row[0]:20s} {row[1]:6d}  {bar}')

# 6. 失败日志
print()
print('=' * 80)
print('6. 失败日志 AUDIT_WRITE_FAILED (status=failed, action=AUDIT_WRITE_FAILED)')
print('=' * 80)
cur.execute("""
    SELECT COUNT(*) FROM audit_logs
    WHERE action = 'AUDIT_WRITE_FAILED' AND status = 'failed'
""")
failed_count = cur.fetchone()[0]
print(f'  当前失败日志: {failed_count}')
if failed_count > 0:
    cur.execute("""
        SELECT id, object_type, object_id, created_at, error_message
        FROM audit_logs
        WHERE action = 'AUDIT_WRITE_FAILED' AND status = 'failed'
        ORDER BY id DESC
        LIMIT 5
    """)
    for row in cur.fetchall():
        print(f'  [{row[0]}] {row[1]}/{row[2]} at {row[3]} - {row[4][:100] if row[4] else "no err msg"}')

# 7. parent_object 填充情况
print()
print('=' * 80)
print('7. parent_object_* 填充情况')
print('=' * 80)
cur.execute("""
    SELECT
        SUM(CASE WHEN parent_object_type IS NULL OR parent_object_type = '' THEN 1 ELSE 0 END) as no_parent_type,
        SUM(CASE WHEN parent_object_id IS NULL OR parent_object_id = '' THEN 1 ELSE 0 END) as no_parent_id,
        SUM(CASE WHEN parent_object_type IS NOT NULL AND parent_object_type != '' THEN 1 ELSE 0 END) as has_parent_type,
        SUM(CASE WHEN parent_object_id IS NOT NULL AND parent_object_id != '' THEN 1 ELSE 0 END) as has_parent_id,
        COUNT(*) as total
    FROM audit_logs
""")
row = cur.fetchone()
print(f'  无 parent_type: {row[0]} / 总 {row[4]} ({row[0]*100//row[4]}%)')
print(f'  无 parent_id:   {row[1]} / 总 {row[4]} ({row[1]*100//row[4]}%)')
print(f'  有 parent_type: {row[2]}')
print(f'  有 parent_id:   {row[3]}')

# 8. 按 object_type 看 parent 填充率
print()
print('=' * 80)
print('8. 各 object_type 的 parent_object 填充率 (只显示总 >= 10 的)')
print('=' * 80)
cur.execute("""
    SELECT
        object_type,
        COUNT(*) as total,
        SUM(CASE WHEN parent_object_id IS NULL OR parent_object_id = '' THEN 1 ELSE 0 END) as no_p
    FROM audit_logs
    GROUP BY object_type
    HAVING total >= 10
    ORDER BY no_p DESC, total DESC
""")
for row in cur.fetchall():
    rate = row[2] * 100 // row[1]
    bar = '█' * (rate // 5)
    print(f'  {row[0]:25s} 总 {row[1]:5d} 无 parent_id {row[2]:5d} ({rate:3d}%) {bar}')

# 9. 字段日志 (CREATE/UPDATE 类型的 field_name 分布)
print()
print('=' * 80)
print('9. 字段级日志 (CREATE/UPDATE/DELETE) field_name 分布 Top 30')
print('=' * 80)
cur.execute("""
    SELECT field_name, COUNT(*) as cnt
    FROM audit_logs
    WHERE action IN ('CREATE', 'UPDATE', 'DELETE')
        AND field_name IS NOT NULL AND field_name != ''
    GROUP BY field_name
    ORDER BY cnt DESC
    LIMIT 30
""")
for row in cur.fetchall():
    bar = '█' * min(50, row[1] // 10)
    print(f'  {row[0]:35s} {row[1]:6d}  {bar}')

# 10. 异常 content / value 检查
print()
print('=' * 80)
print('10. 异常/可疑日志 (action 异常, 错误信息, 空值过多)')
print('=' * 80)
cur.execute("""
    SELECT action, COUNT(*)
    FROM audit_logs
    WHERE action NOT IN ('CREATE', 'UPDATE', 'DELETE', 'READ', 'LOGIN', 'LOGOUT',
                         'EXPORT', 'IMPORT', 'ASSIGN', 'UNASSIGN', 'EXECUTE', 'RESTORE',
                         'AUDIT_WRITE_FAILED', 'CASCADE_DELETE', 'BATCH_CREATE', 'BATCH_UPDATE',
                         'DISSOCIATE', 'ASSOCIATE', 'AUDIT_RETRY_SUCCESS', 'AUDIT_RETRY_FAILED')
    GROUP BY action
""")
extra_actions = cur.fetchall()
if extra_actions:
    print('  异常 action 类型:')
    for row in extra_actions:
        print(f'    {row[0]}: {row[1]}')
else:
    print('  (无异常 action)')

# 11. _record 字段滥用
print()
print('=' * 80)
print('11. _record 字段使用情况 (CREATE 时 1 条 _record=CREATE 应该是聚合 summary)')
print('=' * 80)
cur.execute("""
    SELECT COUNT(*),
        SUM(CASE WHEN action='CREATE' THEN 1 ELSE 0 END) as c,
        SUM(CASE WHEN action='UPDATE' THEN 1 ELSE 0 END) as u,
        SUM(CASE WHEN action='DELETE' THEN 1 ELSE 0 END) as d
    FROM audit_logs
    WHERE field_name = '_record'
""")
row = cur.fetchone()
print(f'  _record 总: {row[0]} (CREATE: {row[1]}, UPDATE: {row[2]}, DELETE: {row[3]})')

# 12. 同一 transaction 的日志数分布
print()
print('=' * 80)
print('12. 同一 transaction 的日志条数分布 (Top 15)')
print('=' * 80)
cur.execute("""
    SELECT tx_count, COUNT(*) as num_transactions
    FROM (
        SELECT transaction_id, COUNT(*) as tx_count
        FROM audit_logs
        WHERE transaction_id IS NOT NULL AND transaction_id != ''
        GROUP BY transaction_id
    )
    GROUP BY tx_count
    ORDER BY tx_count DESC
    LIMIT 15
""")
for row in cur.fetchall():
    print(f'  transaction 含 {row[0]:3d} 条日志  ->  共 {row[1]:5d} 个 transactions')

# 13. 同一对象 (object_type+object_id) 的日志数
print()
print('=' * 80)
print('13. 日志最多的 Top 10 对象')
print('=' * 80)
cur.execute("""
    SELECT object_type, object_id, COUNT(*) as cnt
    FROM audit_logs
    GROUP BY object_type, object_id
    ORDER BY cnt DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(f'  {row[0]:20s} {str(row[1]):15s} {row[2]:5d} 条')

# 14. 失败 (status != written/'') 情况
print()
print('=' * 80)
print('14. 非 written 状态的日志')
print('=' * 80)
cur.execute("""
    SELECT status, COUNT(*) as cnt
    FROM audit_logs
    WHERE status IS NOT NULL AND status != 'written' AND status != ''
    GROUP BY status
""")
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')

# 15. 抽样: 最新 3 条不同 action 的日志
print()
print('=' * 80)
print('15. 抽样: 各 action 最新一条记录')
print('=' * 80)
for action in ['CREATE', 'UPDATE', 'DELETE', 'LOGIN']:
    cur.execute("""
        SELECT id, object_type, object_id, field_name, old_value, new_value, user_name, created_at
        FROM audit_logs
        WHERE action = ?
        ORDER BY id DESC
        LIMIT 1
    """, (action,))
    row = cur.fetchone()
    if row:
        old_v = (row[4] or '')[:50]
        new_v = (row[5] or '')[:50]
        print(f'  [{row[0]}] {action:8s} {row[1]:20s} {row[2]} field={row[3]} by={row[6]} at {row[7]}')
        print(f'         old: {old_v!r}')
        print(f'         new: {new_v!r}')

conn.close()
print()
print('=' * 80)
print('审查完成')
