import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory, get_meta_object
register_from_directory('meta/schemas')
from meta.services.import_export_service import ImportExportService
from meta.services.query_service import SearchRequest
from meta.core.datasource import DataSourceFactory, DataSourceType

ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')
service = ImportExportService(ds)

# 直接调用 search 来检查 (绕过 _query_with_hierarchy)
from meta.services.query_service import QueryService, QueryCondition
qs = service.query_service
req = SearchRequest(
    object_type='relationship',
    conditions=[QueryCondition(field='version_id', operator='eq', value='1')],
    page=1,
    page_size=3,
)
print('=== Direct search through service.query_service ===', flush=True)
result = qs.search(req)
data = result.data or []
if data:
    r = data[0]
    print(f'  Direct search category_label: {r.get("category_label", "(MISSING)")!r}', flush=True)
    print(f'  Direct search source_domain_id: {r.get("source_domain_id", "(MISSING)")!r}', flush=True)
    print(f'  Direct search source_bo_code: {r.get("source_bo_code", "(MISSING)")!r}', flush=True)

# Also: search the SAME record (id=2) through direct search
print('\n=== Direct search for id=2 ===', flush=True)
req2 = SearchRequest(
    object_type='relationship',
    conditions=[QueryCondition(field='id', operator='eq', value='2')],
    page=1,
    page_size=1,
)
result2 = qs.search(req2)
data2_direct = result2.data or []
if data2_direct:
    r = data2_direct[0]
    print(f'  Direct search (id=2) category_label: {r.get("category_label", "(MISSING)")!r}', flush=True)
    print(f'  Direct search (id=2) source_bo_id: {r.get("source_bo_id", "(MISSING)")!r}', flush=True)

# 模拟 _query_with_hierarchy
print('\n=== Calling _query_with_hierarchy ===', flush=True)
data2 = service._query_with_hierarchy('relationship', {'version_id': '1'}, {'include_hierarchy_path': True})
print(f'\nReturned {len(data2)} records', flush=True)
# Find record with id=2
for r in data2:
    if r.get('id') == 2:
        print(f'  Found id=2 in _query_with_hierarchy results:', flush=True)
        print(f'    category_label: {r.get("category_label", "(MISSING)")!r}', flush=True)
        print(f'    source_bo_id: {r.get("source_bo_id")!r}', flush=True)
        break
