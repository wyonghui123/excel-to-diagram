import sqlite3
import os

print("STARTING...", flush=True)

OUT_PATH = r"d:\filework\excel-to-diagram\_diag_user_result.txt"

def main():
    conn = sqlite3.connect(r"d:\filework\excel-to-diagram\meta\architecture.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    lines = []

    def w(s):
        lines.append(s)

    w("="*70)
    w("1. 查找 TEST333 用户")
    w("="*70)
    cur.execute("SELECT id, username, display_name, email, role_id, is_active, created_at FROM users WHERE username LIKE '%TEST333%' OR username LIKE '%test333%' OR username LIKE '%test%' LIMIT 50")
    users = cur.fetchall()
    w(f"找到 {len(users)} 个匹配用户")
    for u in users[:30]:
        w(f"  id={u['id']} username={u['username']} display_name={u['display_name']} role_id={u['role_id']} active={u['is_active']}")

    w("")
    w("2. 全部 tables 列表 (scope/permission 相关)")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r['name'] for r in cur.fetchall()]
    w(f"TOTAL tables: {len(tables)}")
    relevant = [t for t in tables if any(k in t.lower() for k in ['user', 'role', 'permission', 'scope', 'dimension', 'data'])]
    for t in relevant:
        w(f"  {t}")

    w("")
    w("3. 查找 TEST33388 业务对象记录")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='business_objects'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(business_objects)")
        cols = [c[1] for c in cur.fetchall()]
        w(f"business_objects columns: {cols}")
        cur.execute("SELECT * FROM business_objects WHERE code = 'TEST33388' OR name = 'TEST33388'")
        rows = cur.fetchall()
        w(f"code/name='TEST33388': {len(rows)} records")
        for r in rows:
            w(f"  {dict(r)}")

    w("")
    w("4. 查找 BO_WAREHOUSE_BO_INVENTORY_01 关系记录")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='relationships'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(relationships)")
        cols = [c[1] for c in cur.fetchall()]
        w(f"relationships columns: {cols}")
        cur.execute("SELECT * FROM relationships WHERE code = 'BO_WAREHOUSE_BO_INVENTORY_01'")
        rows = cur.fetchall()
        w(f"code='BO_WAREHOUSE_BO_INVENTORY_01': {len(rows)} records")
        for r in rows:
            w(f"  {dict(r)}")
        cur.execute("SELECT * FROM relationships WHERE code LIKE '%WAREHOUSE%' AND code LIKE '%INVENTORY%'")
        rows2 = cur.fetchall()
        w(f"LIKE WAREHOUSE+INVENTORY: {len(rows2)} records")
        for r in rows2[:5]:
            w(f"  {dict(r)}")

    w("")
    w("5. audit_logs 最近 50 条 (查找 TEST33388 / WAREHOUSE 操作)")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(audit_logs)")
        cols = [c[1] for c in cur.fetchall()]
        w(f"audit_logs columns: {cols[:15]}...")
        cur.execute("SELECT * FROM audit_logs WHERE (object_id LIKE '%TEST33388%' OR object_id LIKE '%WAREHOUSE%' OR object_type='business_object' OR object_type='relationship') ORDER BY id DESC LIMIT 50")
        rows = cur.fetchall()
        w(f"\n对象包含 TEST33388/WAREHOUSE 的 audit: {len(rows)} 条")
        for r in rows[:20]:
            d = dict(r)
            line = " | ".join(f"{k}={str(d.get(k,''))[:50]}" for k in ['id','action','object_type','object_id','user_id','user_name','trace_id'] if k in d)
            w(f"  {line}")

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"DONE: wrote to {OUT_PATH}", flush=True)
    print(f"file size: {os.path.getsize(OUT_PATH)} bytes", flush=True)

if __name__ == '__main__':
    main()