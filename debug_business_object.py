import sys
sys.path.insert(0, '.')
from meta.core.datasource import DataSourceFactory, DataSourceType

ds = DataSourceFactory.create(DataSourceType.SQLITE, path='meta/architecture.db')

# Test 1: Check if business_object 468 exists
print('=== Check business_object 468 ===', flush=True)
r = ds.execute('SELECT id, code, name, service_module_id FROM business_objects WHERE id = ?', (468,))
for row in r:
    print(' ', row, flush=True)

# Test 2: Check the join SQL directly
print('\n=== Test hierarchy SQL ===', flush=True)
sql = """
    SELECT
        bo.id,
        bo.service_module_id,
        sm.sub_domain_id,
        sd.domain_id
    FROM business_objects bo
    LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
    LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id
    WHERE bo.id IN (468, 470)
"""
r = ds.execute(sql)
for row in r:
    print(' ', row, flush=True)

# Test 3: Check if compute_by_semantics works on the search result
print('\n=== Direct compute test on search result ===', flush=True)
from meta.services.computation_service import computation_service

# Simulate the search result
test_records = [
    {'id': 136, 'source_bo_id': 468, 'target_bo_id': 14, 'relation_type': 'dependency'},
]
print('Before compute:', test_records, flush=True)
computation_service.compute_by_semantics('relationship', test_records, ds)
print('After compute:', test_records, flush=True)
