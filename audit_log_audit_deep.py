"""
深入审查发现的问题
"""
import sqlite3
from collections import Counter

conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 问题 1: status=retried 的日志 (上次失败的 2830 条)
print('=' * 80)
print('问题 1: status=retried (上次失败后重试成功)')
print('=' * 80)
cur.execute("""
    SELECT id, object_type, object_id, action, error_message, status
    FROM audit_logs
    WHERE status = 'retried'
    ORDER BY id DESC
    LIMIT 5
""")
for row in cur.fetchall():
    print(f'  [{row[0]}] {row[1]}/{row[2]} action={row[3]} status={row[4]} err={row[5][:100] if row[5] else ""}')

# 问题 2: failed=8 条记录详情
print()
print('=' * 80)
print('问题 2: status=failed (8 条真正的失败)')
print('=' * 80)
cur.execute("""
    SELECT id, object_type, object_id, action, error_message, retry_count, created_at
    FROM audit_logs
    WHERE status = 'failed'
    ORDER BY id DESC
""")
for row in cur.fetchall():
    print(f'  [{row[0]}] {row[1]}/{row[2]} action={row[3]} retry={row[5]} at {row[6]}')
    print(f'    err: {row[4][:300] if row[4] else ""}')

# 问题 3: action=UNKNOWN 1428 条 - 哪些 object_type?
print()
print('=' * 80)
print('问题 3: action=UNKNOWN (1428 条) - 哪些 object_type?')
print('=' * 80)
cur.execute("""
    SELECT object_type, COUNT(*)
    FROM audit_logs
    WHERE action = 'UNKNOWN'
    GROUP BY object_type
    ORDER BY 2 DESC
    LIMIT 20
""")
for row in cur.fetchall():
    print(f'  {row[0]:30s} {row[1]:5d}')

# 问题 4: __audit_failure__ 是啥
print()
print('=' * 80)
print('问题 4: object_type=__audit_failure__ (2830 条) - 啥东西?')
print('=' * 80)
cur.execute("""
    SELECT id, action, status, error_message, created_at
    FROM audit_logs
    WHERE object_type = '__audit_failure__'
    ORDER BY id DESC
    LIMIT 5
""")
for row in cur.fetchall():
    print(f'  [{row[0]}] action={row[1]} status={row[2]} at {row[4]}')
    print(f'    err: {row[3][:200] if row[3] else ""}')

# 问题 5: _record 字段滥用 - UPDATE 25 条 + DELETE 453 条
print()
print('=' * 80)
print('问题 5: _record 字段异常 (UPDATE/DELETE 大量 _record)')
print('=' * 80)
cur.execute("""
    SELECT action, COUNT(*), object_type
    FROM audit_logs
    WHERE field_name = '_record'
    GROUP BY action, object_type
    ORDER BY 2 DESC
    LIMIT 15
""")
for row in cur.fetchall():
    print(f'  {row[0]:10s} {row[2]:25s} {row[1]:5d}')

# 问题 6: user 2362 (95%) 无 parent_id 是预期? user 顶层不需要
print()
print('=' * 80)
print('问题 6: 哪些 object_type 是顶层对象 (无 parent_id 是合理)')
print('=' * 80)
top_level = ['user', 'role', 'product', 'version', 'enum_type', 'scheduled_task', 'menu_permission', 'permission', 'permission_bundle']
for ot in top_level:
    cur.execute("""
        SELECT COUNT(*) FROM audit_logs
        WHERE object_type = ?
            AND (parent_object_id IS NULL OR parent_object_id = '')
    """, (ot,))
    cur.execute("""
        SELECT COUNT(*) FROM audit_logs WHERE object_type = ?
    """, (ot,))
    total = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM audit_logs
        WHERE object_type = ?
            AND parent_object_id IS NOT NULL AND parent_object_id != ''
    """, (ot,))
    has_p = cur.fetchone()[0]
    print(f'  {ot:25s} 总 {total:5d}  有 parent {has_p:5d}  无 parent {total-has_p:5d}')

# 问题 7: association_id 没有
print()
print('=' * 80)
print('问题 7: association_id (如 user_group_member 应该指向 user_group) 填充情况')
print('=' * 80)
cur.execute("""
    SELECT
        object_type,
        COUNT(*) as total,
        SUM(CASE WHEN parent_object_id IS NOT NULL AND parent_object_id != '' THEN 1 ELSE 0 END) as has_p
    FROM audit_logs
    WHERE object_type IN ('user_group_member', 'role_menu', 'role_dimension_scope',
                          'role_permissions', 'role_data_permission', 'employee_data_scope',
                          'permission_rule', 'user_group', 'annotation')
    GROUP BY object_type
""")
for row in cur.fetchall():
    rate = row[2]*100//row[1] if row[1] else 0
    print(f'  {row[0]:25s} 总 {row[1]:5d}  有 parent {row[2]:5d} ({rate}%)')

# 问题 8: enum_type 没有 parent 是预期的, 但 2413 全无 parent_object_type 有 202 个有
print()
print('=' * 80)
print('问题 8: enum_type 的 parent 情况')
print('=' * 80)
cur.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN parent_object_type IS NOT NULL AND parent_object_type != '' THEN 1 ELSE 0 END) as has_pt
    FROM audit_logs
    WHERE object_type = 'enum_type'
""")
row = cur.fetchone()
print(f'  enum_type 总 {row[0]}, 有 parent_type {row[1]} ({row[1]*100//row[0]}%)')
cur.execute("""
    SELECT DISTINCT parent_object_type
    FROM audit_logs
    WHERE object_type = 'enum_type' AND parent_object_type IS NOT NULL
""")
print(f'  parent_type values: {[r[0] for r in cur.fetchall()]}')

# 问题 9: 日志数最多的对象的额外信息
print()
print('=' * 80)
print('问题 9: user/1 有 651 条日志 - 时间分布')
print('=' * 80)
cur.execute("""
    SELECT action, COUNT(*)
    FROM audit_logs
    WHERE object_type = 'user' AND object_id = 1
    GROUP BY action
    ORDER BY 2 DESC
""")
for row in cur.fetchall():
    print(f'  {row[0]:20s} {row[1]:5d}')

# 问题 10: ai_async_task 50 条
print()
print('=' * 80)
print('问题 10: ai_async_task 50 条 日志详情')
print('=' * 80)
cur.execute("""
    SELECT action, COUNT(*)
    FROM audit_logs
    WHERE object_type = 'ai_async_task'
    GROUP BY action
""")
for row in cur.fetchall():
    print(f'  {row[0]:20s} {row[1]:5d}')

# 问题 11: _unknown 950 条
print()
print('=' * 80)
print('问题 11: object_type=_unknown (950 条) - 啥?')
print('=' * 80)
cur.execute("""
    SELECT action, COUNT(*)
    FROM audit_logs
    WHERE object_type = '_unknown'
    GROUP BY action
    ORDER BY 2 DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(f'  {row[0]:25s} {row[1]:5d}')

# 问题 12: extra_data 字段
print()
print('=' * 80)
print('问题 12: extra_data 使用情况')
print('=' * 80)
cur.execute("""
    SELECT
        SUM(CASE WHEN extra_data IS NULL OR extra_data = '' OR extra_data = '{}' THEN 1 ELSE 0 END) as empty,
        SUM(CASE WHEN extra_data IS NOT NULL AND extra_data != '' AND extra_data != '{}' THEN 1 ELSE 0 END) as nonempty
    FROM audit_logs
""")
row = cur.fetchone()
print(f'  空 extra_data: {row[0]}, 非空: {row[1]}')

# 问题 13: 业务对象 (domain/sub_domain/business_object/relationship) 详情页完备性
print()
print('=' * 80)
print('问题 13: 业务核心对象日志覆盖 (domain/sub_domain/business_object/relationship/annotation)')
print('=' * 80)
for ot in ['domain', 'sub_domain', 'business_object', 'relationship', 'annotation', 'service_module']:
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN action='CREATE' THEN 1 ELSE 0 END) as c,
            SUM(CASE WHEN action='UPDATE' THEN 1 ELSE 0 END) as u,
            SUM(CASE WHEN action='DELETE' THEN 1 ELSE 0 END) as d
        FROM audit_logs
        WHERE object_type = ?
    """, (ot,))
    row = cur.fetchone()
    print(f'  {ot:20s} CREATE={row[1]:5d} UPDATE={row[2]:5d} DELETE={row[3]:5d}')

conn.close()
