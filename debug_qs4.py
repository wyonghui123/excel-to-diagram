import sys
sys.path.insert(0, '.')
import logging
logging.basicConfig(level=logging.WARNING, format='[%(name)s] %(levelname)s: %(message)s')

from meta.core.yaml_loader import register_from_directory
from meta.core.datasource import DataSourceFactory, DataSourceType
from meta.services.query_service import QueryService, SearchRequest, QueryCondition

register_from_directory('meta/schemas')
ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')
qs = QueryService(ds)

# Enable logger for query_service
import meta.services.query_service
logger = logging.getLogger('meta.services.query_service')
logger.setLevel(logging.DEBUG)

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
    print(f'  category_label: {r.get("category_label", "(MISSING)")!r}', flush=True)
    print(f'  source_domain_id: {r.get("source_domain_id", "(MISSING)")!r}', flush=True)
