import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory
from meta.core.datasource import DataSourceFactory, DataSourceType
from meta.services.computation_service import computation_service
from meta.core.models import registry

register_from_directory('meta/schemas')
ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')

# Check 1: registry.get('relationship')
meta_obj = registry.get('relationship')
print(f'registry.get(relationship) = {meta_obj}', flush=True)
print(f'meta_obj.id = {meta_obj.id if meta_obj else None}', flush=True)

# Check 2: compute_by_semantics
test_records = [
    {'id': 136, 'source_bo_id': 468, 'target_bo_id': 14, 'relation_type': 'dependency'},
]
print(f'\nBefore compute_by_semantics: {test_records}', flush=True)
result = computation_service.compute_by_semantics('relationship', test_records, ds)
print(f'After compute_by_semantics: {result}', flush=True)
print(f'Result is same object: {result is test_records}', flush=True)

# Check 3: direct _compute_hierarchy_scope
test_records2 = [
    {'id': 136, 'source_bo_id': 468, 'target_bo_id': 14, 'relation_type': 'dependency'},
]
print(f'\nBefore _compute_hierarchy_scope: {test_records2}', flush=True)
computation_service._compute_hierarchy_scope(test_records2, ['category_label', 'category_type'], ds)
print(f'After _compute_hierarchy_scope: {test_records2}', flush=True)
