"""检查用户组删除的 audit log 是否有明细 JSON"""
import sqlite3
conn = sqlite3.connect(r'd:\filework\excel-to-diagram\meta\architecture.db')
cur = conn.cursor()

print('=== 78511/78512 两条日志的完整内容 ===')
cur.execute("""
    SELECT id, object_type, object_id, action, field_name, old_value, new_value,
           extra_data, created_at, parent_object_type, parent_object_id
    FROM audit_logs WHERE id IN (78511, 78512)
""")
for row in cur.fetchall():
    print(f'\n--- id={row[0]} ---')
    print(f'  object_type: {row[1]!r}')
    print(f'  object_id: {row[2]!r}')
    print(f'  action: {row[3]!r}')
    print(f'  field_name: {row[4]!r}')
    print(f'  old_value: {row[5]!r}')
    print(f'  new_value: {row[6]!r}')
    print(f'  extra_data: {row[7]!r}')
    print(f'  parent_object_type: {row[10]!r}')

print()
print('=== 验证用户组 475/482 存在性 ===')
cur.execute("SELECT id, name, code FROM user_groups WHERE id IN (475, 482)")
for row in cur.fetchall():
    print(f'  - id={row[0]} name={row[1]!r} code={row[2]!r}')

print()
print('=== 看看删除 (DELETE action) 日志一般如何写 extra_data ===')
cur.execute("""
    SELECT id, object_type, object_id, action, extra_data
    FROM audit_logs
    WHERE action IN ('DELETE', 'DELETE_BLOCKED')
    ORDER BY id DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(f'\n--- id={row[0]} action={row[3]} obj={row[1]}#{row[2]} ---')
    print(f'  extra_data: {row[4]!r}')

conn.close()
