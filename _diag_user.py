"""诊断脚本: 查询 TEST333 用户 + 业务对象 TEST33388 + 关系 BO_WAREHOUSE_BO_INVENTORY_01"""
import sqlite3
import json

conn = sqlite3.connect('meta/architecture.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

OUT = []

def log(s):
    OUT.append(s)
    print(s)

log("="*70)
log("1. 查找 TEST333 用户")
log("="*70)
cur.execute("SELECT id, username, display_name, email, role_id, is_active, created_at FROM users WHERE username LIKE '%TEST333%' OR username LIKE '%test333%'")
users = cur.fetchall()
log(f"找到 {len(users)} 个匹配用户")
for u in users:
    log(f"  id={u['id']} username={u['username']} display_name={u['display_name']} role_id={u['role_id']} active={u['is_active']}")

if users:
    user = users[0]
    user_id = user['id']
    role_id = user['role_id']

    log("")
    log("="*70)
    log(f"2. TEST333 用户 (id={user_id}) 的角色 role_id={role_id}")
    log("="*70)
    cur.execute("SELECT * FROM roles WHERE id = ?", (role_id,))
    role = cur.fetchone()
    if role:
        log(f"Role: id={role['id']} code={role['code']} name={role['name']} is_system={role['is_system']}")
        # 显示 role 的所有列
        log("Columns:")
        for k in role.keys():
            log(f"  {k} = {role[k]}")
    else:
        log("未找到角色")

    log("")
    log("="*70)
    log(f"3. role_id={role_id} 的 dimension_scope 记录")
    log("="*70)
    # 先查 schema
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%scope%'")
    tables = [r['name'] for r in cur.fetchall()]
    log(f"包含 scope 的表: {tables}")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%role%'")
    tables2 = [r['name'] for r in cur.fetchall()]
    log(f"包含 role 的表: {tables2}")

    # 看 role_dimension_scope 表
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='role_dimension_scope'")
        if cur.fetchone():
            log("\nrole_dimension_scope 表存在, schema:")
            cur.execute("PRAGMA table_info(role_dimension_scope)")
            for c in cur.fetchall():
                log(f"  {c}")
            cur.execute("SELECT * FROM role_dimension_scope WHERE role_id = ?", (role_id,))
            rows = cur.fetchall()
            log(f"\nrole_id={role_id} 的 dimension_scope: {len(rows)} 条")
            for r in rows:
                log(f"  {dict(r)}")
    except Exception as e:
        log(f"err: {e}")

    # 看 data_permission 相关
    log("")
    log("="*70)
    log(f"4. role_id={role_id} 的权限/角色关系")
    log("="*70)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%permission%' OR name LIKE '%data%')")
    perm_tables = [r['name'] for r in cur.fetchall()]
    log(f"permission/data 相关表: {perm_tables}")

    # user_role / user_groups
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'user_%'")
    user_tables = [r['name'] for r in cur.fetchall()]
    log(f"user_* 表: {user_tables}")

log("")
log("="*70)
log("5. 查找 TEST33388 业务对象记录")
log("="*70)
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='business_objects'")
if cur.fetchone():
    cur.execute("PRAGMA table_info(business_objects)")
    log("business_objects 表字段:")
    for c in cur.fetchall():
        log(f"  {c[1]} ({c[2]})")
    log("")
    cur.execute("SELECT * FROM business_objects WHERE code = 'TEST33388' OR name = 'TEST33388'")
    rows = cur.fetchall()
    log(f"code/name='TEST33388' 的记录: {len(rows)} 条")
    for r in rows:
        log(f"  {dict(r)}")

log("")
log("="*70)
log("6. 查找 BO_WAREHOUSE_BO_INVENTORY_01 关系记录")
log("="*70)
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='relationships'")
if cur.fetchone():
    cur.execute("PRAGMA table_info(relationships)")
    log("relationships 表字段:")
    for c in cur.fetchall():
        log(f"  {c[1]} ({c[2]})")
    log("")
    cur.execute("SELECT * FROM relationships WHERE code = 'BO_WAREHOUSE_BO_INVENTORY_01'")
    rows = cur.fetchall()
    log(f"code='BO_WAREHOUSE_BO_INVENTORY_01' 的记录: {len(rows)} 条")
    for r in rows:
        log(f"  {dict(r)}")
    # 也尝试模糊查询
    cur.execute("SELECT * FROM relationships WHERE code LIKE '%WAREHOUSE%INVENTORY%' OR name LIKE '%仓库%库存%'")
    rows2 = cur.fetchall()
    log(f"模糊查询 WAREHOUSE+INVENTORY: {len(rows2)} 条")
    for r in rows2[:5]:
        log(f"  {dict(r)}")

log("")
log("="*70)
log("7. 审计日志 - 查看 TEST33388 / 关系 的最近 UPDATE 操作")
log("="*70)
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'")
if cur.fetchone():
    cur.execute("PRAGMA table_info(audit_logs)")
    cols = [c[1] for c in cur.fetchall()]
    log(f"audit_logs 字段: {cols[:20]}...")
    # 最近 20 条
    cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 30")
    rows = cur.fetchall()
    log(f"\n最近 30 条 audit_log:")
    for r in rows:
        d = dict(r)
        # 截短字段
        line = " | ".join(f"{k}={str(d.get(k, ''))[:60]}" for k in ['id','action','object_type','object_id','user_id','user_name','trace_id','transaction_id','field_name'] if k in d)
        log(f"  {line}")

with open('d:/filework/_diag_user_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUT))
print("\n[OK] 结果已写入 d:/filework/_diag_user_result.txt")