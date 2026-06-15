"""Find 新测试2 version id."""
import sqlite3
db = sqlite3.connect(r'D:\filework\excel-to-diagram\meta\architecture.db')
cur = db.cursor()

print("--- versions matching '新测试' ---")
cur.execute("SELECT id, name, product_id FROM versions WHERE name LIKE '%新测试%' OR name LIKE '%1780%' OR name LIKE '%178%'")
for r in cur.fetchall():
    print(f"  v.id={r[0]}, name={r[1]}, product_id={r[2]}")

print()
print("--- all versions in 供应链管理系统 ---")
cur.execute("SELECT v.id, v.name, p.name, p.id FROM versions v JOIN products p ON v.product_id = p.id WHERE p.name LIKE '%供应链%'")
for r in cur.fetchall():
    print(f"  v.id={r[0]}, v.name={r[1]}, p.name={r[2]}, p.id={r[3]}")

print()
print("--- 采购管理 / 采购需求 sub_domain ---")
cur.execute("SELECT id, name, domain_id, version_id FROM sub_domains WHERE name LIKE '%采购%'")
for r in cur.fetchall():
    print(f"  sd.id={r[0]}, name={r[1]}, domain_id={r[2]}, version_id={r[3]}")

print()
print("--- 采购管理 / 采购需求 domain ---")
cur.execute("SELECT id, name, version_id FROM domains WHERE name LIKE '%采购%'")
for r in cur.fetchall():
    print(f"  d.id={r[0]}, name={r[1]}, version_id={r[2]}")

print()
print("--- product '供应链管理系统' ---")
cur.execute("SELECT id, name FROM products WHERE name LIKE '%供应链%'")
for r in cur.fetchall():
    print(f"  p.id={r[0]}, name={r[1]}")
