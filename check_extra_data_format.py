import sqlite3
import json
conn = sqlite3.connect('meta/architecture.db')

# 查看是否有包含 original_action 的 AUDIT_WRITE_FAILED 记录
cur = conn.execute("""
    SELECT id, extra_data
    FROM audit_logs
    WHERE action='AUDIT_WRITE_FAILED'
    ORDER BY id DESC
    LIMIT 20
""")

print("Checking extra_data format in AUDIT_WRITE_FAILED records:")
has_original_action = 0
no_original_action = 0

for row in cur.fetchall():
    audit_id = row[0]
    extra_data_str = row[1]
    if extra_data_str:
        try:
            extra_data = json.loads(extra_data_str)
            if 'original_action' in extra_data:
                has_original_action += 1
                print(f"ID={audit_id}: HAS original_action={extra_data.get('original_action')}")
            else:
                no_original_action += 1
                print(f"ID={audit_id}: NO original_action (old format)")
        except:
            no_original_action += 1
            print(f"ID={audit_id}: Invalid JSON")
    else:
        no_original_action += 1
        print(f"ID={audit_id}: No extra_data")

print(f"\nSummary:")
print(f"  Records with original_action: {has_original_action}")
print(f"  Records without original_action: {no_original_action}")

conn.close()
