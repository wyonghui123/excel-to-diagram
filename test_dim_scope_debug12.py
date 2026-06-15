import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database='meta/architecture.db')

from meta.services.dimension_scope_engine import DimensionScopeEngine
engine = DimensionScopeEngine(ds)

# TEST888's role_id = 5970
conditions = engine.derive_data_conditions(5970)
print('derive_data_conditions(5970):')
for obj_type, conds in conditions.items():
    print(f'  {obj_type}: {conds}')

# Check if service_module/business_object have conditions
print(f'\nservice_module in conditions: {"service_module" in conditions}')
print(f'business_object in conditions: {"business_object" in conditions}')

# Check dimension_object_mapping.yaml
from meta.core.dimension_object_mapping_loader import get_dimension_object_mapping_loader
loader = get_dimension_object_mapping_loader()
print(f'\nYAML mapping loaded: {loader.is_loaded()}')

# Check what mappings exist for service_module and business_object
for dim_code in ['product', 'version', 'domain', 'sub_domain']:
    for bo in ['service_module', 'business_object']:
        binding = loader.get_field_for_bo(dim_code, bo)
        if binding:
            print(f'  {dim_code} -> {bo}: {binding}')
