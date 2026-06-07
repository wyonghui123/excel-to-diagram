from meta.core.models import registry

meta_obj = registry.get('business_object')
print(f'MetaObject ID: {meta_obj.id}')
print(f'Analytical model: {meta_obj.analytical_model}')

cross_table_filters = meta_obj.analytical_model.get('cross_table_filters', [])
print(f'Cross table filters count: {len(cross_table_filters)}')

for ctf in cross_table_filters:
    print(f'  Filter: {ctf.get("id")}')
    assoc = ctf.get('association', {})
    print(f'    Target table: {assoc.get("target_table")}')
    print(f'    ON conditions: {assoc.get("on_conditions")}')
    print(f'    WHERE conditions: {assoc.get("where_conditions")}')
