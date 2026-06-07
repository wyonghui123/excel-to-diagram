import sqlite3
import sys

conn = sqlite3.connect(r'meta\architecture.db')
cur = conn.cursor()
cur.execute('SELECT code, name FROM enum_values WHERE enum_type_id=?', ('annotation_category',))
for row in cur.fetchall():
    print(repr(row))
conn.close()
