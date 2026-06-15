import sys
sys.path.insert(0, '.')

# Patch computation_service module before query_service is loaded
import meta.services.computation_service as cs_module

original_compute = cs_module.computation_service.compute_by_semantics
def patched_compute(object_type, records, data_source=None):
    print(f'[PATCH] compute_by_semantics: object_type={object_type!r}, records_len={len(records)}', flush=True)
    if records:
        print(f'[PATCH] first id={records[0].get("id")}', flush=True)
    result = original_compute(object_type, records, data_source)
    if records:
        print(f'[PATCH] AFTER: category_label={records[0].get("category_label")!r}', flush=True)
    return result

cs_module.computation_service.compute_by_semantics = patched_compute

# Also patch the module-level reference
cs_module.ComputationService.compute_by_semantics = patched_compute

# Now load query_service
from meta.core.yaml_loader import register_from_directory
from meta.core.datasource import DataSourceFactory, DataSourceType
from meta.services.query_service import QueryService, SearchRequest, QueryCondition

register_from_directory('meta/schemas')
ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')
qs = QueryService(ds)

print('\n=== Calling search ===', flush=True)
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

# Manually check the data right after search
print('\n=== Manually invoke compute_by_semantics on result ===', flush=True)
cs_module.computation_service.compute_by_semantics('relationship', data, ds)
if data:
    print(f'  After manual compute, category_label: {data[0].get("category_label", "(MISSING)")!r}', flush=True)
