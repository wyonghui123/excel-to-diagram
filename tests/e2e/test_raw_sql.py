# -*- coding: utf-8 -*-
"""直接查询数据库验证 DESC sort"""
import sys, os, sqlite3, json

db_path = r'd:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check the raw DESC SQL
sql = """
SELECT users.*, _audit_sort._audit_value as _sort_val FROM users 
LEFT JOIN (
    SELECT object_id, MAX(created_at) AS _audit_value 
    FROM audit_logs 
    WHERE object_type = 'user' AND action = 'UPDATE' 
    GROUP BY object_id
) _audit_sort ON _audit_sort.object_id = users.id 
ORDER BY _audit_sort._audit_value DESC 
LIMIT 20 OFFSET 0
"""

cursor.execute(sql)
rows = cursor.fetchall()
cols = [d[0] for d in cursor.description]

print("=== DESC sort raw SQL ===")
for row in rows[:10]:
    d = dict(zip(cols, row))
    print(f"  id={d['id']}, username={d['username']}, _sort_val={d.get('_sort_val', 'NULL')}")

# Check if _sort_val matches updated_at from audit_logs
print("\n=== Check: _sort_val vs individual audit query ===")
for row in rows[:5]:
    d = dict(zip(cols, row))
    uid = d['id']
    # Query audit_logs directly
    cursor.execute(
        "SELECT MAX(created_at) FROM audit_logs WHERE object_type='user' AND object_id=? AND action='UPDATE'",
        (uid,)
    )
    audit_val = cursor.fetchone()[0]
    print(f"  id={uid}, _sort_val={d.get('_sort_val')}, audit MAX(created_at)={audit_val}, match={'YES' if d.get('_sort_val') == audit_val else 'NO'}")

# Check if the sort order is actually correct
print("\n=== Verify sort order ===")
sort_vals = []
for row in rows:
    d = dict(zip(cols, row))
    sort_vals.append((d['id'], d.get('_sort_val')))
    
for i in range(len(sort_vals)-1):
    if sort_vals[i][1] is not None and sort_vals[i+1][1] is not None:
        if sort_vals[i][1] < sort_vals[i+1][1]:
            print(f"  [FAIL] DESC order broken: id={sort_vals[i][0]} ({sort_vals[i][1]}) < id={sort_vals[i+1][0]} ({sort_vals[i+1][1]})")
            break
    elif sort_vals[i][1] is None and sort_vals[i+1][1] is not None:
        print(f"  [FAIL] NULL before non-NULL in DESC at index {i}")
        break

# Also check ASC
print("\n=== ASC sort raw SQL ===")
sql_asc = sql.replace('ORDER BY _audit_sort._audit_value DESC', 'ORDER BY _audit_sort._audit_value ASC')
cursor.execute(sql_asc)
rows_asc = cursor.fetchall()
for row in rows_asc[:10]:
    d = dict(zip(cols, row))
    print(f"  id={d['id']}, username={d['username']}, _sort_val={d.get('_sort_val', 'NULL')}")

conn.close()
