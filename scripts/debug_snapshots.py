import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'meta', 'architecture.db'
)
print('Live DB:', DB_PATH)
conn = sqlite3.connect(DB_PATH)
for row in conn.execute('PRAGMA table_info(roles)').fetchall():
    print(' ', row)
print()
print('Test output dir snapshots:')
test_temp = 'D:/filework/test_temp'
if os.path.exists(test_temp):
    for f in os.listdir(test_temp):
        if 'snapshot' in f and f.endswith('.db'):
            p = os.path.join(test_temp, f)
            try:
                c2 = sqlite3.connect(p)
                cols = [r[1] for r in c2.execute('PRAGMA table_info(roles)').fetchall()]
                print(f'  {f}: has_priority={("priority" in cols)}')
                c2.close()
            except Exception as e:
                print(f'  {f}: ERROR {e}')
