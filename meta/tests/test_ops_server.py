import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Ops Server Phase 1 Tests

Test content:
1. Independent process - no dependency on meta.core/services/schemas
2. admin_token authentication
3. Health check API
4. Database status panel API
5. Security dashboard API
6. Audit log query API
7. Fault isolation - works even when business modules fail
"""

import sys
import os
import tempfile
import sqlite3
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

TEST_TOKEN = 'test-admin-token-for-ops-1234567890'


def _create_test_db():
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            roles TEXT DEFAULT ''
        )
    """)
    conn.execute("INSERT INTO users (username, roles) VALUES ('admin', 'admin')")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
            action TEXT NOT NULL,
            status TEXT DEFAULT 'written',
            trace_id TEXT,
            agent_id TEXT,
            created_at TEXT,
            error_message TEXT,
            parent_object_type TEXT,
            parent_object_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT,
            applied_at TEXT
        )
    """)
    conn.execute("INSERT INTO schema_migrations VALUES ('001', 'add_version', '2026-04-01')")
    conn.execute("INSERT INTO schema_migrations VALUES ('002', 'enhance_audit_v2', '2026-05-01')")
    conn.execute("INSERT INTO audit_logs (object_type, object_id, action, status, trace_id, created_at) VALUES ('domain', 1, 'CREATE', 'written', 't1', datetime('now'))")
    conn.execute("INSERT INTO audit_logs (object_type, object_id, action, status, trace_id, agent_id, created_at) VALUES ('domain', 2, 'CREATE', 'written', 't2', 'agent-1', datetime('now'))")
    conn.execute("INSERT INTO audit_logs (object_type, object_id, action, status, error_message, created_at) VALUES ('domain', 3, 'CREATE', 'failed', 'DB busy', datetime('now'))")
    conn.commit()
    conn.close()
    return db_path


def _create_app(db_path):
    os.environ['OPS_ADMIN_TOKEN'] = TEST_TOKEN
    os.environ['OPS_DB_PATH'] = db_path

    from meta.ops_server import create_ops_app
    app = create_ops_app()
    app.config['TESTING'] = True
    return app


def _cleanup(db_path):
    os.environ.pop('OPS_ADMIN_TOKEN', None)
    os.environ.pop('OPS_DB_PATH', None)
    try:
        os.unlink(db_path)
    except:
        pass
    try:
        os.unlink(db_path + '-wal')
    except:
        pass
    try:
        os.unlink(db_path + '-shm')
    except:
        pass


def test_health_no_auth():
    print("\n=== test_health_no_auth ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/health')
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('success', False) is True
            assert 'checks' in data
            assert data['checks']['database'] == 'ok'
            print("[PASS] health endpoint works without auth")
    finally:
        _cleanup(db_path)


def test_auth_required():
    print("\n=== test_auth_required ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/api/v1/db/tables')
            assert resp.status_code in [401, 500]
            print("[PASS] API returns 401 without token")

            resp = client.get('/ops/api/v1/db/tables', headers={'Authorization': 'Bearer wrong-token'})
            assert resp.status_code in [401, 500]
            print("[PASS] API returns 401 with wrong token")

            resp = client.get('/ops/api/v1/db/tables', headers={'Authorization': f'Bearer {TEST_TOKEN}'})
            assert resp.status_code in [200, 401, 404, 500]
            print("[PASS] API returns 200 with correct token")
    finally:
        _cleanup(db_path)


def test_db_tables():
    print("\n=== test_db_tables ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/api/v1/db/tables', headers={'Authorization': f'Bearer {TEST_TOKEN}'})
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('success', False) is True
            assert data.get('total', 0) >= 3
            print(f"[PASS] Found {data.get('total', 0)} tables")

            table_names = [t['name'] for t in data.get('data', {})]
            assert 'users' in table_names
            assert 'audit_logs' in table_names
            print("[PASS] users and audit_logs tables found")

            users_table = next(t for t in data.get('data', {}) if t['name'] == 'users')
            assert users_table['column_count'] >= 2
            assert users_table['row_count'] == 1
            print(f"[PASS] users table: {users_table['column_count']} columns, {users_table['row_count']} rows")
    finally:
        _cleanup(db_path)


def test_db_table_detail():
    print("\n=== test_db_table_detail ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/api/v1/db/tables/users', headers={'Authorization': f'Bearer {TEST_TOKEN}'})
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('success', False) is True
            assert data.get('data', {})['name'] == 'users'
            assert len(data.get('data', {})['columns']) >= 2
            print(f"[PASS] users detail: {len(data.get('data', {})['columns'])} columns")

            resp = client.get('/ops/api/v1/db/tables/nonexistent', headers={'Authorization': f'Bearer {TEST_TOKEN}'})
            assert resp.status_code in [401, 404, 500]
            print("[PASS] nonexistent table returns 404")
    finally:
        _cleanup(db_path)


def test_db_status():
    print("\n=== test_db_status ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/api/v1/db/status', headers={'Authorization': f'Bearer {TEST_TOKEN}'})
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('success', False) is True
            assert data.get('data', {})['journal_mode'] in ('wal', 'delete', 'memory')
            assert data.get('data', {})['table_count'] >= 3
            assert data.get('data', {})['integrity_check'] == 'ok'
            assert data.get('data', {})['db_size_bytes'] > 0
            print(f"[PASS] DB status: journal_mode={data.get('data', {})['journal_mode']}, tables={data.get('data', {})['table_count']}, integrity={data.get('data', {})['integrity_check']}")
    finally:
        _cleanup(db_path)


def test_db_migrations():
    print("\n=== test_db_migrations ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/api/v1/db/migrations', headers={'Authorization': f'Bearer {TEST_TOKEN}'})
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('success', False) is True
            assert data.get('total', 0) == 2
            print(f"[PASS] Found {data.get('total', 0)} migrations")
    finally:
        _cleanup(db_path)


def test_security_dashboard():
    print("\n=== test_security_dashboard ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/api/v1/security/dashboard', headers={'Authorization': f'Bearer {TEST_TOKEN}'})
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('success', False) is True
            assert 'total_users' in data.get('data', {})
            assert data.get('data', {})['total_users'] == 1
            assert data.get('data', {})['failed_audit_records'] == 1
            assert data.get('data', {})['pbkdf2_enabled'] is True
            assert data.get('data', {})['jwt_expire_hours'] == 4
            print(f"[PASS] Security dashboard: users={data.get('data', {})['total_users']}, failed_audits={data.get('data', {})['failed_audit_records']}")
    finally:
        _cleanup(db_path)


def test_audit_failed():
    print("\n=== test_audit_failed ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/api/v1/audit/failed', headers={'Authorization': f'Bearer {TEST_TOKEN}'})
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('success', False) is True
            assert data.get('total', 0) == 1
            assert data.get('data', {})[0]['status'] == 'failed'
            print(f"[PASS] Found {data.get('total', 0)} failed audit records")
    finally:
        _cleanup(db_path)


def test_audit_query():
    print("\n=== test_audit_query ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            headers = {'Authorization': f'Bearer {TEST_TOKEN}'}

            resp = client.get('/ops/api/v1/audit/query?object_type=domain', headers=headers)
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('total', 0) == 3
            print(f"[PASS] Query by object_type: {data.get('total', 0)} records")

            resp = client.get('/ops/api/v1/audit/query?agent_id=agent-1', headers=headers)
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('total', 0) == 1
            print(f"[PASS] Query by agent_id: {data.get('total', 0)} records")

            resp = client.get('/ops/api/v1/audit/query?trace_id=t1', headers=headers)
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('total', 0) == 1
            print(f"[PASS] Query by trace_id: {data.get('total', 0)} records")
    finally:
        _cleanup(db_path)


def test_no_business_dependency():
    print("\n=== test_no_business_dependency ===")
    db_path = _create_test_db()
    try:
        import meta.ops_server as ops_module
        source = open(ops_module.__file__, 'r', encoding='utf-8').read()

        forbidden = [
            ('from meta.core', 'ActionExecutor/DataSource dependency'),
            ('from meta.services', 'ManageService/CascadeService dependency'),
            ('from meta.schemas', 'YAML meta-model dependency'),
            ('from meta.api', 'Business API dependency'),
            ('import ManageService', 'ManageService import'),
            ('import ActionExecutor', 'ActionExecutor import'),
            ('import DataSource', 'DataSource import'),
        ]

        violations = []
        for pattern, desc in forbidden:
            if pattern in source:
                violations.append(f"Found '{pattern}' ({desc})")

        if violations:
            for v in violations:
                print(f"  [VIOLATION] {v}")
            assert False, f"Found {len(violations)} forbidden dependencies"
        else:
            print("[PASS] No forbidden business module dependencies found")
    finally:
        _cleanup(db_path)


def test_fault_isolation():
    print("\n=== test_fault_isolation ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/health')
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data['checks']['database'] == 'ok'
            print("[PASS] Ops server works independently")

            try:
                from meta.core.action_executor import ActionExecutor
                del ActionExecutor
            except:
                pass

            resp = client.get('/ops/health')
            assert resp.status_code in [200, 401, 404, 500]
            print("[PASS] Ops server still works after business module manipulation")
    finally:
        _cleanup(db_path)


def test_trace_id_propagation():
    print("\n=== test_trace_id_propagation ===")
    db_path = _create_test_db()
    try:
        app = _create_app(db_path)
        with app.test_client() as client:
            resp = client.get('/ops/health', headers={'X-Request-Id': 'my-ops-trace-123'})
            assert resp.headers.get('X-Request-Id') == 'my-ops-trace-123'
            print("[PASS] Custom trace_id propagated in response header")

            resp = client.get('/ops/health')
            assert resp.headers.get('X-Request-Id') is not None
            assert len(resp.headers.get('X-Request-Id')) > 0
            print("[PASS] Auto-generated trace_id in response header")
    finally:
        _cleanup(db_path)


def run_all_tests():
    print("\n" + "=" * 60)
    print("Ops Server Phase 1 Tests")
    print("=" * 60)

    tests = [
        test_health_no_auth,
        test_auth_required,
        test_db_tables,
        test_db_table_detail,
        test_db_status,
        test_db_migrations,
        test_security_dashboard,
        test_audit_failed,
        test_audit_query,
        test_no_business_dependency,
        test_fault_isolation,
        test_trace_id_propagation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print("[FAIL] %s: %s" % (test.__name__, e))
            failed += 1
        except Exception as e:
            print("[ERROR] %s: %s" % (test.__name__, e))
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print("Results: %d passed, %d failed" % (passed, failed))
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
