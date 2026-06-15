import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database='meta/architecture.db')

from meta.services.dimension_scope_engine import DimensionScopeEngine
engine = DimensionScopeEngine(ds)

# Test _expand_down
result = engine._expand_down('domain', 'service_module', [703])
print(f'_expand_down(domain, service_module, [703]): {result}')

result = engine._expand_down('domain', 'business_object', [703])
print(f'_expand_down(domain, business_object, [703]): {result}')

# Check derive_data_conditions
conditions = engine.derive_data_conditions(5970)
print(f'\nderive_data_conditions(5970):')
for obj_type, conds in conditions.items():
    print(f'  {obj_type}: {conds}')

# Check RESOURCE_TABLE_MAP
from meta.services.dimension_scope_engine import RESOURCE_TABLE_MAP
print(f'\nRESOURCE_TABLE_MAP:')
for k, v in RESOURCE_TABLE_MAP.items():
    print(f'  {k}: {v}')

# Direct query
cursor = ds.execute("SELECT id, name, sub_domain_id FROM service_modules WHERE sub_domain_id IN (138, 139, 146)", [])
rows = cursor.fetchall()
print(f'\nService modules under sub_domains 138,139,146: {len(rows)}')
for r in rows[:5]:
    print(f'  id={r[0]} name={r[1]} sub_domain_id={r[2]}')
