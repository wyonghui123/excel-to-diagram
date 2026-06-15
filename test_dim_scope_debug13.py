import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database='meta/architecture.db')

from meta.services.dimension_scope_engine import DimensionScopeEngine
engine = DimensionScopeEngine(ds)

# Check expand_dimension_values for role_id=5970
expanded = engine.expand_dimension_values(5970)
print('expand_dimension_values(5970):')
for dim_code, vals in expanded.items():
    print(f'  {dim_code}: {sorted(vals)}')
