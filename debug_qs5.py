import sys
sys.path.insert(0, '.')
import logging
import io

# Capture all logging output to string
log_stream = io.StringIO()
handler = logging.StreamHandler(log_stream)
handler.setLevel(logging.WARNING)
handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.WARNING)

from meta.core.yaml_loader import register_from_directory
from meta.core.datasource import DataSourceFactory, DataSourceType
from meta.services.query_service import QueryService, SearchRequest, QueryCondition

register_from_directory('meta/schemas')
ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')
qs = QueryService(ds)

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

print('\n--- LOG OUTPUT ---', flush=True)
print(log_stream.getvalue(), flush=True)
