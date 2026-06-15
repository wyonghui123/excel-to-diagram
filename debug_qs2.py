import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory
from meta.core.datasource import DataSourceFactory, DataSourceType
from meta.services.query_service import QueryService, SearchRequest, QueryCondition
from meta.core.models import registry

register_from_directory('meta/schemas')
ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')
qs = QueryService(ds)

# Test: 直接调用 search
print('=== Test 1: direct search, version_id=1 ===', flush=True)
req = SearchRequest(
    object_type='relationship',
    conditions=[QueryCondition(field='version_id', operator='eq', value='1')],
    page=1,
    page_size=5,
)
result = qs.search(req)
data = result.data or []
print(f'Got {len(data)} records from search result', flush=True)
for i, r in enumerate(data[:3]):
    print(f'\nRecord {i}:', flush=True)
    print(f'  id: {r.get("id")}', flush=True)
    print(f'  source_bo_id: {r.get("source_bo_id")}', flush=True)
    print(f'  category_label: {r.get("category_label", "(MISSING - empty)")!r}', flush=True)
    print(f'  source_domain_id: {r.get("source_domain_id", "(missing)")!r}', flush=True)
    print(f'  source_bo_code: {r.get("source_bo_code", "(missing)")!r}', flush=True)
