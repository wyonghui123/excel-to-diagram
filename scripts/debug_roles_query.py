import sys
import os
sys.path.insert(0, '.')
from meta.core.datasource import get_data_source

db_path = os.path.join('meta', 'architecture.db')
ds = get_data_source('sqlite', database=db_path)
try:
    cursor = ds.execute('SELECT * FROM roles ORDER BY id')
    rows = cursor.fetchall()
    print('OK, rows:', len(rows))
    cols = [c[0] for c in cursor.description]
    print('Cols:', cols)
    for row in rows[:3]:
        d = dict(zip(cols, row))
        print(' ', d)
except Exception as e:
    import traceback
    traceback.print_exc()
