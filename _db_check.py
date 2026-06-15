import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
print('=== products ===')
for r in cur.execute('SELECT id, name FROM products').fetchall():
    print(' ', r)
print()
print('=== versions (含 product 1) ===')
for r in cur.execute('SELECT id, name, product_id FROM versions WHERE product_id = 1').fetchall():
    print(' ', r)
print()
print('=== domains (含 采购) ===')
for r in cur.execute("SELECT id, name, version_id FROM domains WHERE name LIKE '%采购%'").fetchall():
    print(' ', r)
print()
print('=== relationships 范围统计 per version (product_id=1) ===')
for v in cur.execute('SELECT id, name FROM versions WHERE product_id=1 ORDER BY id').fetchall():
    vid, vname = v
    cur2 = conn.cursor()
    total = cur2.execute('SELECT COUNT(*) FROM relationships WHERE version_id=?', (vid,)).fetchone()[0]
    internal = cur2.execute("SELECT COUNT(*) FROM relationships WHERE version_id=? AND relation_type='INTERNAL'", (vid,)).fetchone()[0]
    cross = cur2.execute("SELECT COUNT(*) FROM relationships WHERE version_id=? AND relation_type='CROSS_BOUNDARY'", (vid,)).fetchone()[0]
    ext = cur2.execute("SELECT COUNT(*) FROM relationships WHERE version_id=? AND relation_type='EXTERNAL'", (vid,)).fetchone()[0]
    print(f'  v{vid} {vname}: total={total} INTERNAL={internal} CROSS={cross} EXTERNAL={ext}')

# Check what scope/relation_type column is named
print()
print('=== relationships schema ===')
for r in cur.execute('PRAGMA table_info(relationships)').fetchall():
    print(' ', r)
