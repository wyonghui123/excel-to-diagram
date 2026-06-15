import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory
from meta.core.datasource import DataSourceFactory, DataSourceType
from meta.services.query_service import QueryService, SearchRequest, QueryCondition
from meta.services.computation_service import computation_service

register_from_directory('meta/schemas')
ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')
qs = QueryService(ds)

# Monkey-patch compute_by_semantics to add print
original_compute = computation_service.compute_by_semantics
def patched_compute(object_type, records, data_source=None):
    print(f'[MONKEY] compute_by_semantics called: object_type={object_type!r}, records_len={len(records)}', flush=True)
    if records:
        print(f'[MONKEY] first record id={records[0].get("id")}, source_bo_id={records[0].get("source_bo_id")}', flush=True)
    result = original_compute(object_type, records, data_source)
    if records:
        print(f'[MONKEY] AFTER compute: first record category_label={records[0].get("category_label")!r}', flush=True)
    return result
computation_service.compute_by_semantics = patched_compute

print('=== Calling search ===', flush=True)
req = SearchRequest(
    object_type='relationship',
    conditions=[QueryCondition(field='version_id', operator='eq', value='1')],
    page=1,
    page_size=3,
)
result = qs.search(req)
data = result.data or []
print(f'Got {len(data)} records', flush=True)
if data:
    r = data[0]
    print(f'  Final category_label: {r.get("category_label", "(MISSING)")!r}', flush=True)
