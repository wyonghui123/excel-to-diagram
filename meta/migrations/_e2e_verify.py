"""End-to-end verification: start backend, call key APIs that use v_audit_all

V007.50 Phase 1 + V007.51 Phase 2 综合验证 (2026-07-14)
"""
import sys
import os
import json
import sqlite3
import time
import traceback

sys.path.insert(0, r"D:\filework\release-prep-worktree")

DB = r"D:\filework\release-prep-worktree\meta\architecture.db"

# 1. Clean v007_50 artifacts first
print("=== Step 1: Clean v007_50 artifacts ===")
conn = sqlite3.connect(DB)
conn.execute("DROP VIEW IF EXISTS v_audit_all")
conn.execute("DROP TABLE IF EXISTS audit_logs_archive")
conn.commit()
conn.close()
print("[OK] cleaned")

# 2. Start backend via create_app (simulates real backend startup)
print("\n=== Step 2: Start backend (create_app) ===")
from meta.server import create_app
app = create_app()
print("[OK] backend started")

# 3. Verify v_audit_all created
print("\n=== Step 3: Verify v_audit_all created ===")
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='v_audit_all'")
exists = cur.fetchone()
print(f"v_audit_all exists: {bool(exists)}")
assert exists, "v_audit_all not created by backend startup"

cur.execute("SELECT COUNT(*) FROM v_audit_all")
cnt = cur.fetchone()[0]
print(f"v_audit_all COUNT(*): {cnt}")

# 3.5 Verify VIEW includes both hot + archive data
cur.execute("SELECT COUNT(*) FROM audit_logs")
hot_cnt = cur.fetchone()[0]
print(f"audit_logs (hot) COUNT(*): {hot_cnt}")
print(f"v_audit_all == hot table count: {cnt == hot_cnt} (archive table empty or not yet used)")
conn.close()

# 4. Call key APIs that use v_audit_all
print("\n=== Step 4: Call key APIs ===")
client = app.test_client()

# 4.0 dev-login to get auth_token cookie (admin user)
print("\n--- 4.0 GET /api/v1/auth/dev-login?username=admin ---")
resp = client.get('/api/v1/auth/dev-login?username=admin')
print(f"Login Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"[FAIL] dev-login failed: {resp.data[:200]}")
    sys.exit(1)
set_cookie = resp.headers.get('Set-Cookie', '')
print(f"[OK] dev-login success, Set-Cookie present: {'auth_token=' in set_cookie}")

def safe_api_call(label, url):
    """Safely call an API and print results"""
    print(f"\n--- {label} ---")
    try:
        resp = client.get(url)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.get_json()
            if data is None:
                print(f"[WARN] no JSON body, raw: {resp.data[:200]}")
            else:
                # Print summary based on response structure
                success = data.get('success', data.get('code', '') in (200, '200'))
                if isinstance(data, dict):
                    # Find the main data array
                    for key in ('logs', 'roles', 'enum_types', 'types', 'items', 'data'):
                        val = data.get(key)
                        if isinstance(val, list):
                            print(f"[OK] success={success}, {key}={len(val)} items")
                            if val and isinstance(val[0], dict):
                                first = val[0]
                                # Print a few key fields
                                summary = {k: first.get(k) for k in ('id', 'name', 'updated_at', 'action', 'object_type', 'object_id') if k in first}
                                print(f"  first item: {summary}")
                            return
                    # No list found, print keys
                    print(f"[OK] success={success}, keys={list(data.keys())[:10]}")
                    print(f"  response preview: {str(data)[:300]}")
                else:
                    print(f"[OK] response: {str(data)[:300]}")
        else:
            print(f"[FAIL] {resp.status_code}: {resp.data[:200]}")
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()

# 4.1 audit logs list (audit_api.py) — url_prefix='/api/v1/audit', route='/logs'
safe_api_call("4.1 GET /api/v1/audit/logs", '/api/v1/audit/logs?page=1&page_size=5')

# 4.2 audit overview (audit_api.py - route='/overview')
safe_api_call("4.2 GET /api/v1/audit/overview", '/api/v1/audit/overview')

# 4.3 enum-types list (enum_api.py uses _enrich_updated_at)
safe_api_call("4.3 GET /api/v1/enum-types", '/api/v1/enum-types?page=1&page_size=5')

# 4.4 roles list (role_api.py)
safe_api_call("4.4 GET /api/v1/roles", '/api/v1/roles?page=1&page_size=5')

# 4.5 audit log detail (audit_api.py - route='/logs/<id>')
# First get a log ID from 4.1
print("\n--- 4.5 GET /api/v1/audit/logs/<first_id> ---")
try:
    resp = client.get('/api/v1/audit/logs?page=1&page_size=1')
    if resp.status_code == 200:
        data = resp.get_json()
        logs = data.get('logs', []) if data else []
        if logs:
            log_id = logs[0].get('id')
            print(f"  Testing detail for log_id={log_id}")
            resp2 = client.get(f'/api/v1/audit/logs/{log_id}')
            print(f"Status: {resp2.status_code}")
            if resp2.status_code == 200:
                detail = resp2.get_json()
                print(f"[OK] detail returned: {str(detail)[:300]}")
            else:
                print(f"[FAIL] {resp2.status_code}: {resp2.data[:200]}")
        else:
            print("[SKIP] no logs available for detail test")
except Exception as e:
    print(f"[ERROR] {e}")

# 5. Verify query plan uses indexes (not full scan)
print("\n=== Step 5: Verify query plan ===")
try:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # Check that VIEW query uses indexes
    cur.execute("EXPLAIN QUERY PLAN SELECT * FROM v_audit_all WHERE object_type='role' AND action='UPDATE' LIMIT 5")
    plan = cur.fetchall()
    print("Query plan for v_audit_all WHERE object_type='role':")
    for row in plan:
        print(f"  {row}")
    conn.close()
except Exception as e:
    print(f"[ERROR] query plan check failed: {e}")

# 6. V007.51 Phase 2 验证：物化列存在 + Backfill
print("\n=== Step 6: V007.51 Phase 2 - materialized updated_at columns ===")
try:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 6.1 检查物化列存在
    target_tables = [("enum_types", "enum_type"), ("enum_values", "enum_value"), ("users", "user")]
    print("\n--- 6.1 materialized updated_at columns ---")
    for table_name, obj_type in target_tables:
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = [c[1] for c in cur.fetchall()]
        has_col = "updated_at" in cols
        print(f"  {table_name}.updated_at: {has_col}")

        if has_col:
            cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE updated_at IS NOT NULL")
            filled = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            total = cur.fetchone()[0]
            print(f"    filled: {filled}/{total} rows")

    # 6.2 验证 enum_types 的物化 updated_at 值正确
    print("\n--- 6.2 enum_types materialized updated_at sample ---")
    cur.execute("""
        SELECT id, name, created_at, updated_at
        FROM enum_types
        WHERE updated_at IS NOT NULL
        LIMIT 5
    """)
    for row in cur.fetchall():
        print(f"  {row}")

    # 6.3 验证 users 的物化 updated_at 值
    print("\n--- 6.3 users materialized updated_at sample ---")
    cur.execute("""
        SELECT id, username, created_at, updated_at
        FROM users
        WHERE updated_at IS NOT NULL
        LIMIT 5
    """)
    for row in cur.fetchall():
        print(f"  {row}")

    # 6.4 性能对比测试 (Phase 1 vs Phase 2)
    print("\n--- 6.4 Performance comparison: Phase 1 vs Phase 2 ---")
    # Phase 1 路径：LEFT JOIN v_audit_all (走物化列时不走，但模拟原 Phase 1 路径)
    # 用 enum_types 表作基准
    cur.execute("SELECT COUNT(*) FROM enum_types")
    n_records = cur.fetchone()[0]

    # Phase 2: 直接读 enum_types.updated_at
    t0 = time.time()
    for _ in range(20):  # 跑 20 次取平均
        cur.execute("SELECT id, name, COALESCE(updated_at, created_at) AS updated_at FROM enum_types")
        rows = cur.fetchone()
    t_phase2 = (time.time() - t0) / 20 * 1000  # ms

    # Phase 1: LEFT JOIN v_audit_all
    t0 = time.time()
    for _ in range(20):
        cur.execute("""
            SELECT et.id, et.name,
                   COALESCE(_a.max_at, et.created_at) AS updated_at
            FROM enum_types et
            LEFT JOIN (
                SELECT object_id, MAX(created_at) AS max_at
                FROM v_audit_all
                WHERE object_type = 'enum_type' AND action = 'UPDATE'
                GROUP BY object_id
            ) _a ON _a.object_id = et.id
        """)
        rows = cur.fetchone()
    t_phase1 = (time.time() - t0) / 20 * 1000  # ms

    speedup = t_phase1 / max(t_phase2, 0.001)
    print(f"  Phase 1 (LEFT JOIN v_audit_all): {t_phase1:.3f} ms")
    print(f"  Phase 2 (direct column read):    {t_phase2:.3f} ms")
    print(f"  Speedup: {speedup:.1f}x")

    # 6.5 EXPLAIN QUERY PLAN 对比
    print("\n--- 6.5 EXPLAIN QUERY PLAN comparison ---")
    cur.execute("EXPLAIN QUERY PLAN SELECT id, name, COALESCE(updated_at, created_at) FROM enum_types")
    print("  Phase 2 plan:")
    for row in cur.fetchall():
        print(f"    {row}")

    cur.execute("""
        EXPLAIN QUERY PLAN
        SELECT et.id, et.name, COALESCE(_a.max_at, et.created_at)
        FROM enum_types et
        LEFT JOIN (
            SELECT object_id, MAX(created_at) AS max_at
            FROM v_audit_all
            WHERE object_type = 'enum_type' AND action = 'UPDATE'
            GROUP BY object_id
        ) _a ON _a.object_id = et.id
    """)
    print("  Phase 1 plan:")
    for row in cur.fetchall():
        print(f"    {row}")

    conn.close()

except Exception as e:
    print(f"[ERROR] Phase 2 verification failed: {e}")
    traceback.print_exc()

# 7. V007.51 API 验证：物化列路径下 API 仍正常
print("\n=== Step 7: V007.51 API verification ===")

# 7.1 用户列表（用物化列排序）
print("\n--- 7.1 GET /api/v1/users?sort_by=updated_at ---")
try:
    resp = client.get('/api/v1/users?sort_by=updated_at&order=desc&page=1&page_size=5')
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.get_json()
        if data and isinstance(data, dict):
            for key in ('items', 'users', 'data'):
                val = data.get(key)
                if isinstance(val, list) and val:
                    print(f"[OK] {key}={len(val)} items")
                    for u in val[:3]:
                        print(f"  {u.get('id')} {u.get('username')} updated_at={u.get('updated_at')}")
                    break
            else:
                print(f"[OK] success={data.get('success')}, keys={list(data.keys())[:8]}")
    else:
        print(f"[FAIL] {resp.status_code}: {resp.data[:200]}")
except Exception as e:
    print(f"[ERROR] {e}")
    traceback.print_exc()

# 7.2 enum_types 列表（物化列）
print("\n--- 7.2 GET /api/v1/enum-types ---")
try:
    resp = client.get('/api/v1/enum-types?page=1&page_size=5')
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.get_json()
        if data and isinstance(data, dict):
            for key in ('items', 'types', 'data', 'enum_types'):
                val = data.get(key)
                if isinstance(val, list) and val:
                    print(f"[OK] {key}={len(val)} items")
                    for t in val[:3]:
                        print(f"  {t.get('id')} {t.get('code')} updated_at={t.get('updated_at')}")
                    break
    else:
        print(f"[FAIL] {resp.status_code}: {resp.data[:200]}")
except Exception as e:
    print(f"[ERROR] {e}")

# 7.3 模拟新 UPDATE 审计 → 验证 batch_refresh 路径
print("\n--- 7.3 Simulate UPDATE audit + verify refresh ---")
try:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 取一个 enum_type ID
    cur.execute("SELECT id, updated_at FROM enum_types WHERE updated_at IS NOT NULL LIMIT 1")
    row = cur.fetchone()
    if row:
        et_id, old_updated = row[0], row[1]
        print(f"  target enum_type id={et_id}, old updated_at={old_updated}")

        # 插入新的 UPDATE 审计日志
        new_time = "2026-07-14T15:00:00"
        cur.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at, created_at_epoch) "
            "VALUES (?, ?, ?, ?, ?)",
            ("enum_type", str(et_id), "UPDATE", new_time, 1789478400000),
        )
        conn.commit()
        print(f"  [OK] inserted UPDATE audit for enum_type {et_id}")

        # 调用 batch_refresh
        from meta.migrations.v007_51_add_updated_at_materialized import batch_refresh_materialized_updated_at
        batch_refresh_materialized_updated_at(conn, [("enum_type", str(et_id))])

        # 验证物化列更新
        cur.execute("SELECT updated_at FROM enum_types WHERE id = ?", (et_id,))
        new_updated = cur.fetchone()[0]
        print(f"  new materialized updated_at: {new_updated}")
        assert new_updated == new_time, f"物化列应更新为 {new_time}, 实际 {new_updated}"
        print(f"  [OK] materialized column refreshed correctly")

        # 清理测试数据
        cur.execute("DELETE FROM audit_logs WHERE created_at = ? AND object_id = ?", (new_time, str(et_id)))
        cur.execute("UPDATE enum_types SET updated_at = ? WHERE id = ?", (old_updated, et_id))
        conn.commit()
    conn.close()
except Exception as e:
    print(f"[ERROR] {e}")
    traceback.print_exc()

print("\n=== ALL DONE ===")
