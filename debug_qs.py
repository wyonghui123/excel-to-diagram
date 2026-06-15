import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory, get_meta_object
register_from_directory('meta/schemas')
from meta.services.query_service import QueryService, SearchRequest, QueryCondition
from meta.core.datasource import DataSourceFactory, DataSourceType

ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')
qs = QueryService(ds)

# 直接调用 query_service.search (不通过 _query_with_hierarchy)
print('=== Direct QueryService.search ===', flush=True)
req = SearchRequest(
    object_type='relationship',
    conditions=[],
    page=1,
    page_size=5,
)
result = qs.search(req)
data = result.data or []
print(f'Got {len(data)} records', flush=True)
for i, r in enumerate(data[:3]):
    print(f'\nRecord {i}:', flush=True)
    print(f'  id: {r.get("id")}', flush=True)
    print(f'  source_bo_id: {r.get("source_bo_id")}', flush=True)
    print(f'  source_bo_code: {r.get("source_bo_code", "(missing)")!r}', flush=True)
    print(f'  category_label: {r.get("category_label", "(MISSING - empty)")!r}', flush=True)
    print(f'  source_domain_id: {r.get("source_domain_id", "(missing)")!r}', flush=True)
