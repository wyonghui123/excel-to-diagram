import sqlite3
db_path = r'd:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 查看 business_objects 表结构
cur.execute("PRAGMA table_info(business_objects)")
cols = cur.fetchall()
print("business_objects columns:")
for c in cols:
    print(f"  {c}")
print()

# 查看 service_modules 表
cur.execute("PRAGMA table_info(service_modules)")
cols = cur.fetchall()
print("service_modules columns:")
for c in cols:
    print(f"  {c}")
print()

# 查看 domains 表
cur.execute("PRAGMA table_info(domains)")
cols = cur.fetchall()
print("domains columns:")
for c in cols:
    print(f"  {c}")
print()

# 查看 sub_domains 表
cur.execute("PRAGMA table_info(sub_domains)")
cols = cur.fetchall()
print("sub_domains columns:")
for c in cols:
    print(f"  {c}")
print()

# 看 business_object id=316 的实际行
cur.execute("SELECT * FROM business_objects WHERE id=316")
row = cur.fetchone()
print("bo id=316:")
cur.execute("PRAGMA table_info(business_objects)")
for i, c in enumerate(cur.fetchall()):
    print(f"  {c[1]} = {row[i] if i < len(row) else '?'}")
print()

# 看一下 business_objects 表中带 domain_name 的 row count
cur.execute("SELECT COUNT(*) FROM business_objects")
total = cur.fetchone()[0]
print("total BO:", total)

conn.close()
