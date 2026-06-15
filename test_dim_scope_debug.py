import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
db_path = os.path.join(os.path.dirname(os.path.abspath('meta')), 'architecture.db')
ds = get_data_source('sqlite', database='meta/architecture.db')

from meta.services.dimension_scope_engine import DimensionScopeEngine
engine = DimensionScopeEngine(ds)

# TEST888 user_id = 5970
conditions = engine.derive_data_conditions(5970)
print('derive_data_conditions(5970):')
for obj_type, conds in conditions.items():
    print(f'  {obj_type}: {conds}')

# Also check what roles/scopes TEST888 has
cursor = ds.execute("""
    SELECT rs.id, rs.role_id, r.name as role_name, r.code as role_code,
           rs.dimension_id, d.name as dim_name, d.code as dim_code,
           rs.dimension_values, rs.inherit_children
    FROM role_dimension_scopes rs
    JOIN roles r ON rs.role_id = r.id
    JOIN management_dimensions d ON rs.dimension_id = d.id
    JOIN group_roles gr ON gr.role_id = r.id
    JOIN user_group_members ugm ON gr.group_id = ugm.group_id
    WHERE ugm.user_id = 5970
""", [])
rows = cursor.fetchall()
print(f'\nrole_dimension_scopes for user 5970:')
for row in rows:
    print(f'  {row}')
