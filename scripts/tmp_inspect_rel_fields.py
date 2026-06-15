"""查 enum_values 表和字段关系"""
import json
import sqlite3

con = sqlite3.connect('meta/architecture.db')
cur = con.cursor()

# 查 enum_values 表里的 relation_type / relation_direction
print("=== enum_values 表里的 relation_type / relation_direction / hierarchy_scope_type ===")
cur.execute("""
    SELECT enum_type_id, code, name, is_active, sort_order
    FROM enum_values
    WHERE enum_type_id IN ('relation_type', 'relation_direction', 'hierarchy_scope_type')
    ORDER BY enum_type_id, sort_order, code
""")
rows = cur.fetchall()
print(f'Total rows: {len(rows)}')
for r in rows:
    print('  ', r)

# 查 enum_types
print("\n=== enum_types 表 (定义) ===")
cur.execute("""
    SELECT id, name, category, mutability
    FROM enum_types
    WHERE id IN ('relation_type', 'relation_direction', 'hierarchy_scope_type')
""")
for r in cur.fetchall():
    print('  ', r)

# 查实际 relationships 表数据
print("\n=== relationships 表现有数据 (前 3 条) ===")
cur.execute("""
    SELECT id, code, relation_type, relation_direction, category_type
    FROM relationships
    WHERE relation_type IS NOT NULL OR relation_direction IS NOT NULL
    LIMIT 3
""")
for r in cur.fetchall():
    print('  ', r)

con.close()
