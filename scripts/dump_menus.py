# -*- coding: utf-8 -*-
"""Dump menus to a file so we can Read it."""
import sqlite3
import os

# Try multiple DB locations
db_candidates = [
    r'meta/architecture.db',
    r'meta/api/architecture.db',
    r'meta/database/architecture.db',
    r'meta/core/architecture.db',
    r'meta/scripts/architecture.db',
]
db_path = None
for c in db_candidates:
    full = os.path.abspath(os.path.join(r'd:\filework\excel-to-diagram', c))
    if os.path.exists(full):
        db_path = full
        break

if not db_path:
    print("NO DB FOUND")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.execute(
    "SELECT menu_code, menu_name, menu_path, IFNULL(parent_menu,'') AS parent_menu, "
    "is_active, show_in_sidebar, sort_order "
    "FROM menus ORDER BY sort_order"
)
rows = cur.fetchall()
conn.close()

# 输出到文本文件
out = r'd:\filework\excel-to-diagram\debug_menus_dump.txt'
with open(out, 'w', encoding='utf-8') as f:
    f.write(f"DB: {db_path}\n")
    f.write(f"Total menus: {len(rows)}\n\n")
    f.write(f"{'CODE':<35}{'NAME':<20}{'PATH':<35}{'PARENT':<25}{'ACT':<5}{'SB':<5}{'SORT'}\n")
    f.write("-" * 140 + "\n")
    for r in rows:
        f.write(f"{r[0]:<35}{r[1]:<20}{r[2]:<35}{r[3]:<25}{r[4]:<5}{r[5]:<5}{r[6]}\n")
print(f"Wrote {len(rows)} rows to {out}")