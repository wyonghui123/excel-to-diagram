import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.services.query_service import QueryService, SearchRequest
from meta.services.data_permission_service import DataPermissionService
import tempfile

db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
db_path = db_file.name
db_file.close()

ds = get_data_source('sqlite', database=db_path)
ds.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT, display_name TEXT, status TEXT DEFAULT 'active', roles TEXT DEFAULT '[]')''')
ds.execute('''CREATE TABLE IF NOT EXISTS data_permissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, resource_type TEXT NOT NULL, resource_id INTEGER NOT NULL, permission_level TEXT DEFAULT 'read')''')
ds.execute('''CREATE TABLE IF NOT EXISTS role_data_permissions (id INTEGER PRIMARY KEY AUTOINCREMENT, role_id INTEGER NOT NULL, resource_type TEXT NOT NULL, resource_id INTEGER NOT NULL)''')
ds.execute('''CREATE TABLE IF NOT EXISTS group_data_permissions (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER NOT NULL, resource_type TEXT NOT NULL, resource_id INTEGER NOT NULL)''')
ds.execute('''CREATE TABLE IF NOT EXISTS user_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)''')
ds.execute('''CREATE TABLE IF NOT EXISTS user_group_members (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, group_id INTEGER NOT NULL)''')
ds.execute('''CREATE TABLE IF NOT EXISTS user_roles (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, role_id INTEGER NOT NULL)''')
ds.execute('''CREATE TABLE IF NOT EXISTS domains (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, version_id INTEGER)''')
ds.execute('''CREATE TABLE IF NOT EXISTS business_objects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT, domain_id INTEGER)''')

ds.execute("INSERT INTO users VALUES(1,'admin','hash','Admin','active','[\"admin\"]')")
ds.execute("INSERT INTO users VALUES(2,'demo','hash','Demo','active','[\"viewer\"]')")
for i in range(1, 6):
    ds.execute(f'INSERT INTO domains VALUES({i}, "D{i}", 13)')
for i in range(1, 51):
    ds.execute(f'INSERT INTO business_objects VALUES({i}, "BO_{i}", "desc", {((i-1)%5)+1})')

ps = DataPermissionService(ds)
ps.add_data_permission(2, 'business_object', 1, 'read')
ps.add_data_permission(2, 'business_object', 3, 'read')
ps.add_data_permission(2, 'business_object', 5, 'read')

import meta.services.auth_middleware as am
orig_get = am.get_current_user
orig_is = am.is_admin
am.get_current_user = lambda: {'user_id': 2, 'roles': ['viewer']}
am.is_admin = lambda u=None: False

qs = QueryService(ds)

print("=== Test: partial BO permissions [1,3,5] ===")
req = SearchRequest(object_type='business_object', conditions=[], page=1, page_size=100)
result = qs.search(req)
print(f'Total: {result.total}')
print(f'Data count: {len(result.data)}')
ids = sorted([r['id'] for r in result.data])
print(f'IDs: {ids}')

print("\n=== Test: no service_module permissions ===")
req2 = SearchRequest(object_type='service_module', conditions=[], page=1, page_size=100)
result2 = qs.search(req2)
print(f'Total: {result2.total}')
print(f'Data count: {len(result2.data)}')

am.get_current_user = orig_get
am.is_admin = orig_is
os.unlink(db_path)
