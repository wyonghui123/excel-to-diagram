import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory, get_meta_object
from meta.core.models import registry
from meta.core.datasource import DataSourceFactory, DataSourceType
from meta.services.computation_service import computation_service

register_from_directory('meta/schemas')
ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')

# Debug step by step
print('=== registry.get("relationship") ===', flush=True)
meta_obj = registry.get('relationship')
print(f'Got meta_obj: {meta_obj}', flush=True)
print(f'meta_obj.id: {meta_obj.id}', flush=True)

print('\n=== Find fields with computed_by ===', flush=True)
by_computed = {}
for f in meta_obj.fields:
    sem = getattr(f, 'semantics', None)
    if not sem:
        continue
    cb = getattr(sem, 'computed_by', None)
    if cb:
        by_computed.setdefault(cb, []).append(f.id)
        print(f'  {f.id}: computed_by={cb!r}', flush=True)

print(f'\nby_computed: {by_computed}', flush=True)

# Test direct call to _compute_hierarchy_scope
print('\n=== Test _compute_hierarchy_scope directly ===', flush=True)
test_records = [
    {'id': 136, 'source_bo_id': 468, 'target_bo_id': 14, 'relation_type': 'dependency'},
]
print('Before:', test_records, flush=True)
field_ids = ['category_label', 'category_type']
computation_service._compute_hierarchy_scope(test_records, field_ids, ds)
print('After:', test_records, flush=True)
