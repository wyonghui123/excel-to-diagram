import sqlite3, os

db = os.path.join('meta', 'architecture.db')
c = sqlite3.connect(db).cursor()

tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
relevant = [t for t in tables if 'menu' in t.lower() or 'dimension' in t.lower() or 'role_dim' in t.lower()]
print("Relevant tables:", relevant)

try:
    c.execute("SELECT COUNT(*) FROM menus")
    print("menus count:", c.fetchone()[0])
    c.execute("SELECT COUNT(*) FROM menu_permissions")
    print("menu_permissions count:", c.fetchone()[0])
except Exception as e:
    print("menus query error:", e)

try:
    c.execute("SELECT COUNT(*) FROM role_dimension_scopes")
    print("role_dimension_scopes count:", c.fetchone()[0])
except Exception as e:
    print("role_dimension_scopes error:", e)
