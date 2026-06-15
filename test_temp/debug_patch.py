"""debug: check if monkeypatch on audit_api._data_source actually works"""
import os
import sys
import tempfile
import sqlite3

sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.environ['TEST_ENTRY'] = '1'

# 1. Create temp DB with 1 row
fd, path = tempfile.mkstemp(suffix='.db')
os.close(fd)
conn = sqlite3.connect(path)
conn.executescript("""
    CREATE TABLE audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_type TEXT,
        object_id TEXT,
        action TEXT,
        field_name TEXT,
        old_value TEXT,
        new_value TEXT,
        user_id TEXT,
        user_name TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT,
        trace_id TEXT,
        transaction_id TEXT,
        status TEXT DEFAULT 'written',
        retry_count INTEGER DEFAULT 0,
        error_message TEXT,
        log_category TEXT DEFAULT 'business',
        log_level TEXT DEFAULT 'INFO',
        extra_data TEXT,
        parent_object_type TEXT,
        parent_object_id TEXT
    );
""")
conn.execute("INSERT INTO audit_logs (id, object_type, object_id, action, parent_object_type, parent_object_id) VALUES (1, 'role', '1', 'UPDATE', '', '')")
conn.commit()
conn.close()

# 2. Get shared app
from meta.tests.conftest import get_shared_app
app, client = get_shared_app()

# 3. Check what audit_api._data_source points to
import meta.api.audit_api as audit_api_mod
print(f"Before patch: _data_source = {audit_api_mod._data_source}")
print(f"  type = {type(audit_api_mod._data_source)}")
print(f"  has db_path: {hasattr(audit_api_mod._data_source, 'database') or hasattr(audit_api_mod._data_source, '_db_path')}")

# 4. Patch with temp DB
from meta.core.datasource import get_data_source
temp_ds = get_data_source("sqlite", database=path)
audit_api_mod._data_source = temp_ds
print(f"After patch: _data_source = {audit_api_mod._data_source}")

# 5. Check via direct call (bypassing HTTP)
cursor = audit_api_mod._data_source.execute("SELECT COUNT(*) FROM audit_logs")
print(f"Direct query count: {cursor.fetchone()[0]}")

# 6. Now make HTTP request
import requests
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo
u = UserInfo(user_id='1', username='d', display_name='D', email='d@t.com', roles=['admin'], permissions=['*'])
token, _ = TokenService.create_token(u)

# Use the test client (in-process)
resp = client.get('/api/v1/audit/logs?page=1&page_size=10', headers={'Authorization': f'Bearer {token}'})
print(f"HTTP status: {resp.status_code}")
body = resp.get_json()
print(f"HTTP body total: {body.get('total')}")
print(f"HTTP body items: {len(body.get('data') or [])}")
if body.get('data'):
    print(f"  first id: {body['data'][0].get('id')}")

# 7. Re-check audit_api._data_source
print(f"After HTTP: _data_source = {audit_api_mod._data_source}")

os.unlink(path)
