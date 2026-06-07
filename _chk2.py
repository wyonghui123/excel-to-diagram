import sqlite3
c = sqlite3.connect('d:/filework/excel-to-diagram/architecture.db')

for obj_type in ['table', 'index', 'trigger']:
    r = c.execute(f"SELECT name, sql FROM sqlite_master WHERE type='{obj_type}' AND tbl_name='annotations'")
    rows = r.fetchall()
    if rows:
        print(f"=== {obj_type}s on annotations ===")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    else:
        print(f"No {obj_type}s on annotations")

c.close()
