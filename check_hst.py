import sqlite3
conn = sqlite3.connect('meta/architecture.db')
c = conn.cursor()
c.execute("SELECT * FROM enum_types WHERE id='hierarchy_scope_type'")
print('TYPE:', c.fetchall())
c.execute("SELECT id, code, name, sort_order, is_active FROM enum_values WHERE enum_type_id='hierarchy_scope_type' ORDER BY sort_order, code")
rows = c.fetchall()
print('VALUES count:', len(rows))
for r in rows:
    print(r)
