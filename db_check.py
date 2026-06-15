import sqlite3
c = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
print('business_objects id=468:', c.execute('SELECT id, code FROM business_objects WHERE id=468').fetchall())
print('business_objects id=467:', c.execute('SELECT id, code FROM business_objects WHERE id=467').fetchall())
print('count business_objects:', c.execute('SELECT COUNT(*) FROM business_objects').fetchone())
# 所有表
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('tables with "object" in name:')
for t in tables:
    if 'object' in t.lower():
        print(f'  {t}: {c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]} rows')