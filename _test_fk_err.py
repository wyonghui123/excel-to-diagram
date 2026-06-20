import sqlite3
conn = sqlite3.connect(':memory:')
c = conn.cursor()
c.execute('CREATE TABLE parent (id INTEGER PRIMARY KEY)')
c.execute('CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER, FOREIGN KEY (parent_id) REFERENCES parent(id))')
try:
    c.execute('INSERT INTO child (id, parent_id) VALUES (1, 99)')
except sqlite3.IntegrityError as e:
    print(repr(str(e)))
    print(str(e))