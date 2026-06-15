import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database='meta/architecture.db')

from meta.services.dimension_scope_engine import DimensionScopeEngine
engine = DimensionScopeEngine(ds)

# Find TEST888's role_ids
cursor = ds.execute("""
    SELECT DISTINCT gr.role_id, r.name, r.code
    FROM group_roles gr
    JOIN user_group_members ugm ON gr.group_id = ugm.group_id
    JOIN roles r ON gr.role_id = r.id
    WHERE ugm.user_id = 5970
""", [])
role_rows = cursor.fetchall()
print('TEST888 roles:')
for row in role_rows:
    print(f'  role_id={row[0]} name={row[1]} code={row[2]}')
    # derive conditions per role
    conditions = engine.derive_data_conditions(row[0])
    print(f'  derive_data_conditions({row[0]}):')
    for obj_type, conds in conditions.items():
        print(f'    {obj_type}: {conds}')

# Also check: what does derive_data_conditions(5970) return (as user_id)?
conditions = engine.derive_data_conditions(5970)
print('\nderive_data_conditions(user_id=5970):')
for obj_type, conds in conditions.items():
    print(f'  {obj_type}: {conds}')
