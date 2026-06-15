import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory
from meta.core.datasource import DataSourceFactory, DataSourceType
from meta.services.query_service import QueryService, SearchRequest, QueryCondition
from meta.services.computation_service import computation_service
from meta.core.models import registry

register_from_directory('meta/schemas')
ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')
qs = QueryService(ds)

# 测试: 1. 先调用 search  (内部调用 compute_by_semantics)
print('=== Step 1: call search ===', flush=True)
req = SearchRequest(
    object_type='relationship',
    conditions=[QueryCondition(field='version_id', operator='eq', value='1')],
    page=1,
    page_size=5,
)
result = qs.search(req)
data = result.data or []
print(f'Got {len(data)} records from search', flush=True)
print(f'Sample: {data[0] if data else "(empty)"}', flush=True)

# 2. 手动再调用 compute_by_semantics
print('\n=== Step 2: manually call compute_by_semantics ===', flush=True)
computation_service.compute_by_semantics('relationship', data, ds)
print(f'After manual compute: {data[0] if data else "(empty)"}', flush=True)
print(f'category_label: {data[0].get("category_label", "(STILL MISSING)")!r}' if data else '', flush=True)

# 3. 检查 meta_obj.id 与 'relationship' 字符串
print('\n=== Step 3: check meta_obj.id ===', flush=True)
meta_obj = registry.get('relationship')
print(f'meta_obj.id: {meta_obj.id!r}', flush=True)
print(f'meta_obj.table_name: {meta_obj.table_name!r}', flush=True)
print(f'fields count: {len(meta_obj.fields)}', flush=True)

# 4. 看下 fields 中 category_label 的字段名
for f in meta_obj.fields:
    if 'category' in f.id:
        print(f'  Field: id={f.id!r}, name={f.name!r}', flush=True)
