import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
DerivationExecutor 单元测试

测试从 audit_logs 派生 created_by/updated_by 的查询机制
"""

import sys
import os
import tempfile
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.derivation_executor import DerivationExecutor, DerivationResult, DerivationRuleParser


def _create_test_db():
    """创建测试数据库"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
            action TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id TEXT,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            extra_data TEXT,
            trace_id TEXT,
            transaction_id TEXT,
            status TEXT DEFAULT 'written',
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            parent_object_type TEXT,
            parent_object_id TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            display_name TEXT,
            email TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    conn.commit()
    conn.close()

    return db_path


def _cleanup_db(db_path):
    """清理测试数据库"""
    try:
        os.unlink(db_path)
    except:
        pass


def _insert_audit_logs(db_path, logs):
    """插入测试数据"""
    conn = sqlite3.connect(db_path)
    for log in logs:
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'written')
        """, [log['object_type'], log['object_id'], log['action'], log['user_id'], log['user_name'], log['created_at']])
    conn.commit()
    conn.close()


def _insert_users(db_path, users):
    """插入用户数据"""
    conn = sqlite3.connect(db_path)
    for user in users:
        conn.execute("""
            INSERT INTO users (id, username, display_name, email)
            VALUES (?, ?, ?, ?)
        """, [user['id'], user['username'], user['display_name'], user['email']])
    conn.commit()
    conn.close()


class MockDataSource:
    """模拟数据源 - 使用真实的 SQLite 连接"""
    def __init__(self, db_path):
        self.db_path = db_path

    def execute(self, sql, params=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor

    def find(self, table, filters=None, order_by=None, limit=None):
        """模拟 DataSource.find() 方法"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        where_parts = []
        params = []
        
        if filters:
            for key, value in filters.items():
                if isinstance(value, (list, tuple)):
                    placeholders = ','.join(['?' for _ in value])
                    where_parts.append(f"{key} IN ({placeholders})")
                    params.extend(value)
                else:
                    where_parts.append(f"{key} = ?")
                    params.append(value)
        
        where_clause = " AND ".join(where_parts) if where_parts else "1=1"
        
        sql = f"SELECT * FROM {table} WHERE {where_clause}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {limit}"
        
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        return [dict(zip(columns, row)) for row in rows]


def test_derive_user_name_create_action():
    """测试从 audit_logs 派生 created_by (action = 'CREATE')"""
    print("\n=== test_derive_user_name_create_action ===")

    db_path = _create_test_db()
    try:
        _insert_users(db_path, [
            {'id': 1, 'username': 'admin', 'display_name': '管理员', 'email': 'admin@test.com'},
            {'id': 2, 'username': 'user1', 'display_name': '用户1', 'email': 'user1@test.com'},
        ])

        _insert_audit_logs(db_path, [
            {'object_type': 'user_group', 'object_id': 1, 'action': 'CREATE', 'user_id': '1', 'user_name': 'admin', 'created_at': '2026-05-08 10:00:00'},
            {'object_type': 'user_group', 'object_id': 1, 'action': 'UPDATE', 'user_id': '2', 'user_name': 'user1', 'created_at': '2026-05-08 11:00:00'},
        ])

        ds = MockDataSource(db_path)
        executor = DerivationExecutor(ds)

        result = executor.derive_field(
            object_type='user_group',
            object_id=1,
            field_name='created_by',
            derivation_rule="user_name WHERE action = 'CREATE'"
        )

        assert result.success, f"派生失败: {result.message}"
        assert result.value == 'admin', f"期望 'admin', 实际 '{result.value}'"
        print(f"[PASS] created_by = {result.value}")

    finally:
        _cleanup_db(db_path)


def test_derive_user_name_update_action():
    """测试从 audit_logs 派生 updated_by (action IN ('CREATE', 'UPDATE'))"""
    print("\n=== test_derive_user_name_update_action ===")

    db_path = _create_test_db()
    try:
        _insert_users(db_path, [
            {'id': 1, 'username': 'admin', 'display_name': '管理员', 'email': 'admin@test.com'},
            {'id': 2, 'username': 'user1', 'display_name': '用户1', 'email': 'user1@test.com'},
        ])

        _insert_audit_logs(db_path, [
            {'object_type': 'user_group', 'object_id': 1, 'action': 'CREATE', 'user_id': '1', 'user_name': 'admin', 'created_at': '2026-05-08 10:00:00'},
            {'object_type': 'user_group', 'object_id': 1, 'action': 'UPDATE', 'user_id': '2', 'user_name': 'user1', 'created_at': '2026-05-08 11:00:00'},
        ])

        ds = MockDataSource(db_path)
        executor = DerivationExecutor(ds)

        result = executor.derive_field(
            object_type='user_group',
            object_id=1,
            field_name='updated_by',
            derivation_rule="user_name ORDER BY created_at DESC LIMIT 1 WHERE action IN ('CREATE', 'UPDATE')"
        )

        assert result.success, f"派生失败: {result.message}"
        assert result.value == 'user1', f"期望 'user1' (最新操作), 实际 '{result.value}'"
        print(f"[PASS] updated_by = {result.value}")

    finally:
        _cleanup_db(db_path)


def test_derive_field_no_audit_logs():
    """测试 audit_logs 中无记录时返回失败结果"""
    print("\n=== test_derive_field_no_audit_logs ===")

    db_path = _create_test_db()
    try:
        ds = MockDataSource(db_path)
        executor = DerivationExecutor(ds)

        result = executor.derive_field(
            object_type='user_group',
            object_id=999,
            field_name='created_by',
            derivation_rule="user_name WHERE action = 'CREATE'"
        )

        assert result.success == False, f"期望派生失败, 实际 success={result.success}"
        assert result.value is None, f"期望 None, 实际 '{result.value}'"
        print(f"[PASS] 无记录时派生失败（success=False, value=None）")

    finally:
        _cleanup_db(db_path)


def test_derivation_rule_parser():
    """测试派生规则解析器"""
    print("\n=== test_derivation_rule_parser ===")

    parser = DerivationRuleParser()

    rule1 = "user_name WHERE action = 'CREATE'"
    parsed1 = parser.parse(rule1)
    assert parsed1.select_field == 'user_name', f"select_field 解析错误: {parsed1.select_field}"
    assert "action = 'CREATE'" in parsed1.where_clause, f"where_clause 解析错误: {parsed1.where_clause}"
    print(f"[PASS] 简单规则解析正确: {parsed1}")

    rule2 = "user_name ORDER BY created_at DESC LIMIT 1 WHERE action IN ('CREATE', 'UPDATE')"
    parsed2 = parser.parse(rule2)
    assert parsed2.select_field == 'user_name'
    assert parsed2.order_by == 'created_at DESC'
    assert parsed2.limit == 1
    assert "action IN" in parsed2.where_clause
    print(f"[PASS] 复杂规则解析正确: {parsed2}")


def test_derive_batch():
    """测试批量派生"""
    print("\n=== test_derive_batch ===")

    db_path = _create_test_db()
    try:
        _insert_users(db_path, [
            {'id': 1, 'username': 'admin', 'display_name': '管理员', 'email': 'admin@test.com'},
            {'id': 2, 'username': 'user1', 'display_name': '用户1', 'email': 'user1@test.com'},
        ])

        _insert_audit_logs(db_path, [
            {'object_type': 'user_group', 'object_id': 1, 'action': 'CREATE', 'user_id': '1', 'user_name': 'admin', 'created_at': '2026-05-08 10:00:00'},
            {'object_type': 'user_group', 'object_id': 2, 'action': 'CREATE', 'user_id': '2', 'user_name': 'user1', 'created_at': '2026-05-08 11:00:00'},
        ])

        ds = MockDataSource(db_path)
        executor = DerivationExecutor(ds)

        results = executor.derive_batch(
            object_type='user_group',
            object_ids=[1, 2],
            field_names=['created_by'],
            derivation_rules={
                'created_by': "user_name WHERE action = 'CREATE'"
            }
        )

        assert len(results) == 2, f"期望 2 条结果, 实际 {len(results)}"
        assert '1' in results, f"结果中缺少 ID='1'"
        assert '2' in results, f"结果中缺少 ID='2'"
        assert results['1']['created_by'].value == 'admin', f"ID=1 created_by 错误"
        assert results['2']['created_by'].value == 'user1', f"ID=2 created_by 错误"
        print(f"[PASS] 批量派生成功: {len(results)} 条")

    finally:
        _cleanup_db(db_path)


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("DerivationExecutor 单元测试")
    print("=" * 60)

    tests = [
        test_derive_user_name_create_action,
        test_derive_user_name_update_action,
        test_derive_field_no_audit_logs,
        test_derivation_rule_parser,
        test_derive_batch,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"结果: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
