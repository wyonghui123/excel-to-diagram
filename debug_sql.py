import sqlite3
db_path = r'd:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 测试 4 个目标表的查询
for target_bo, target_table, display_field in [
    ('version', 'versions', 'name'),
    ('domain', 'domains', 'name'),
    ('sub_domain', 'sub_domains', 'name'),
    ('service_module', 'service_modules', 'name'),
]:
    try:
        sql = f'SELECT id, {display_field} FROM {target_table} WHERE id IN (1, 2, 3)'
        cur.execute(sql)
        rows = cur.fetchall()
        print(f'{target_bo} ({target_table}.{display_field}): {rows}')
    except Exception as e:
        print(f'{target_bo} ERROR: {e}')

# 看 table_name 注册表
print()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('versions', 'domains', 'sub_domains', 'service_modules', 'business_objects')")
print('Actual tables:', [r[0] for r in cur.fetchall()])
conn.close()
