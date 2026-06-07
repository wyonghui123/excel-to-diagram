import sqlite3, os

db_path = os.path.join("d:/filework/excel-to-diagram", "meta", "architecture.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Check if service_modules.sub_domain_id is NULL
cur.execute("SELECT id, name, sub_domain_id, domain_id FROM service_modules WHERE version_id=15 LIMIT 10")
rows = cur.fetchall()
print("service_modules (first 10):")
for r in rows:
    print("  id=%s name=%s sub_domain_id=%s domain_id=%s" % (r[0], r[1][:30] if r[1] else None, r[2], r[3]))

# Check if business_objects.service_module_id is populated
cur.execute("SELECT id, name, service_module_id FROM business_objects WHERE version_id=15 LIMIT 10")
rows = cur.fetchall()
print("\nbusiness_objects (first 10):")
for r in rows:
    print("  id=%s name=%s service_module_id=%s" % (r[0], r[1][:30] if r[1] else None, r[2]))

# Test the JOIN query
sql = """
SELECT 
    bo.id, bo.code, bo.name,
    sm.name as service_module_name,
    sd.name as sub_domain_name,
    d.name as domain_name
FROM business_objects bo
LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id
LEFT JOIN domains d ON sd.domain_id = d.id
WHERE bo.version_id = 15
LIMIT 5
"""
cur.execute(sql)
rows = cur.fetchall()
print("\nJOIN query result (first 5):")
for r in rows:
    print("  bo_id=%s code=%s name=%s sm_name=%s sd_name=%s d_name=%s" % (r[0], r[1], r[2][:20] if r[2] else None, r[3], r[4], r[5]))

conn.close()
