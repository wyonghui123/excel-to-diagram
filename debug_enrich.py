import sys
sys.path.insert(0, r'd:\filework\excel-to-diagram')
import os
os.chdir(r'd:\filework\excel-to-diagram')

# 强制开发环境，关闭rate limit
os.environ['FLASK_ENV'] = 'production'
os.environ['TESTING'] = 'true'
os.environ['DISABLE_RATE_LIMIT'] = 'true'

from meta.core.models import registry
from meta.core.enrichment_engine import EnrichmentEngine
from meta.core.datasource import get_data_source

ds = get_data_source("sqlite", database=r'd:\filework\excel-to-diagram\meta\architecture.db')
meta_obj = registry.get('business_object')

print('=== business_object fields ===')
for f in meta_obj.fields:
    vh = getattr(f, 'value_help', None)
    src_type = None
    target_bo = None
    display_field = None
    if vh:
        src = getattr(vh, 'source', None)
        if src:
            src_type = getattr(src, 'type', None)
            target_bo = getattr(src, 'target_bo', None)
            display_field = getattr(src, 'display_field', None)
    ui = getattr(f, 'ui', None)
    relation = None
    if ui:
        relation = getattr(ui, 'relation', None)
    print(f'  {f.id:30s} relation={relation:15s} vh_src={src_type:10s} target_bo={target_bo:20s} display_field={display_field}')

print()
print('=== Test enrich_fk_display_names for BO 316 ===')
# 模拟一条 record
test_record = {
    'id': 316,
    'code': 'PROC_REQ_MNG03',
    'name': 'ASDFSADF',
    'version_id': 1,
    'service_module_id': 1,
    'domain_id': 1,
    'sub_domain_id': 1,
}

engine = EnrichmentEngine.for_data_source(ds)
result = engine.enrich_fk_display_names(meta_obj, [test_record])
print('After enrich_fk_display_names:')
for k, v in result[0].items():
    if k.endswith('_display') or k.endswith('_id') or k.endswith('_name'):
        print(f'  {k}: {v}')
