import sys
import os
sys.path.insert(0, '.')

# Mirror test path resolution
DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath('meta/tests/test_role_v1_cleanup.py')),
    'meta', 'architecture.db'
)
print('Resolved DB path:', DB_PATH)
print('Exists:', os.path.exists(DB_PATH))
print()

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database=DB_PATH)
print('ds._db_path:', ds._db_path if hasattr(ds, '_db_path') else 'N/A')
print()

cursor = ds.execute("PRAGMA table_info(roles)")
cols = [(r[1] if not isinstance(r, dict) else r['name']) for r in cursor.fetchall()]
print('Roles columns:', cols)
print('has priority:', 'priority' in cols)
print('has is_super_admin:', 'is_super_admin' in cols)
