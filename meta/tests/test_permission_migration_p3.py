# -*- coding: utf-8 -*-
"""
[FILE] test_permission_migration_p3.py
[DESCRIPTION] Phase 3 data_permission_rules 统一表 — TDD 测试用例
[SPEC] spec-permission-system-unification-2026-07-19 §8.3
[FR] FR-007 / FR-008 / FR-009

测试层次 (覆盖 P3-T1~T3):
  T1: data_permission_rules DDL 创建成功
  T2: role_dimension_scopes 数据迁移 (rule_type='dimension')
  T3: permission_rules 数据迁移 (rule_type='condition')

实现状态: [TDD RED → GREEN] 实施 P3-T1~T3 后应全部 PASS
"""
import pytest

pytestmark = pytest.mark.unit

import sys
import os
import json
import sqlite3
import tempfile
from unittest.mock import Mock, MagicMock, patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_with_legacy_tables():
    """创建含 role_dimension_scopes + permission_rules + data_permission_rules 的测试数据库"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        -- [P3-T1] 新统一表
        CREATE TABLE IF NOT EXISTS data_permission_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            rule_type VARCHAR(50) NOT NULL DEFAULT 'condition',
            resource_type VARCHAR(200),
            dimension_code VARCHAR(200),
            condition TEXT,
            scope_mode VARCHAR(50) DEFAULT 'include',
            permission_level VARCHAR(50) DEFAULT 'read',
            is_denied INTEGER DEFAULT 0,
            inherit_to_children INTEGER DEFAULT 1,
            propagate_to_parents INTEGER DEFAULT 0,
            source_table VARCHAR(100),
            source_id INTEGER,
            created_at VARCHAR(200),
            updated_at VARCHAR(200)
        );

        -- 旧表 (P3-T2 来源)
        CREATE TABLE IF NOT EXISTS role_dimension_scopes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            dimension_code VARCHAR(200) NOT NULL,
            dimension_values TEXT NOT NULL,
            inherit_children INTEGER DEFAULT 1,
            scope_mode VARCHAR(200) DEFAULT 'include'
        );

        -- 旧表 (P3-T3 来源)
        CREATE TABLE IF NOT EXISTS permission_rules (
            role_id INTEGER NOT NULL,
            resource_type VARCHAR(200) NOT NULL,
            condition TEXT NOT NULL,
            permission_level VARCHAR(200) NOT NULL DEFAULT 'read',
            is_denied INTEGER DEFAULT 0,
            inherit_to_children INTEGER DEFAULT 1,
            propagate_to_parents INTEGER DEFAULT 1,
            analysis_mode VARCHAR(200),
            created_at VARCHAR(200),
            created_by INTEGER,
            updated_at VARCHAR(200)
        );

        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(200) UNIQUE NOT NULL,
            name VARCHAR(200)
        );
    """)
    # 测试数据
    conn.execute("INSERT INTO roles (id, code, name) VALUES (1, 'admin', 'Admin')")
    conn.execute("INSERT INTO roles (id, code, name) VALUES (2, 'user', 'User')")
    # role_dimension_scopes 测试数据 (3 行)
    conn.execute(
        "INSERT INTO role_dimension_scopes (id, role_id, dimension_code, dimension_values, scope_mode) "
        "VALUES (1, 1, 'product', '[1, 2]', 'include')"
    )
    conn.execute(
        "INSERT INTO role_dimension_scopes (id, role_id, dimension_code, dimension_values, scope_mode) "
        "VALUES (2, 1, 'version', '[10, 11]', 'include')"
    )
    conn.execute(
        "INSERT INTO role_dimension_scopes (id, role_id, dimension_code, dimension_values, scope_mode) "
        "VALUES (3, 2, 'product', '[]', 'all')"
    )
    # permission_rules 测试数据 (2 行)
    conn.execute(
        "INSERT INTO permission_rules "
        "(role_id, resource_type, condition, permission_level, is_denied) "
        "VALUES (1, 'product', \"status = 'active'\", 'read', 0)"
    )
    conn.execute(
        "INSERT INTO permission_rules "
        "(role_id, resource_type, condition, permission_level, is_denied) "
        "VALUES (2, 'business_object', \"owner_id = 1\", 'write', 0)"
    )
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection

        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor

        def commit(self):
            self._conn.commit()

    yield MockDS(conn)
    conn.close()
    os.unlink(db_path)


# ============================================================================
# T1: data_permission_rules DDL (P3-T1)
# ============================================================================

class TestDataPermissionRulesDDL:
    """P3-T1: data_permission_rules 表 DDL 验证"""

    def test_table_exists_in_schema(self):
        """generated_schema.sql 包含 data_permission_rules CREATE TABLE"""
        schema_path = os.path.join(_PROJECT_ROOT, 'meta', 'schemas', 'generated_schema.sql')
        with open(schema_path, encoding='utf-8') as f:
            content = f.read()
        assert 'CREATE TABLE' in content
        assert 'data_permission_rules' in content

    def test_table_has_required_columns(self, db_with_legacy_tables):
        """表结构包含必要字段"""
        ds = db_with_legacy_tables
        cols = ds.execute(
            "PRAGMA table_info(data_permission_rules)"
        ).fetchall()
        col_names = {c[1] for c in cols}
        required = {
            'id', 'role_id', 'rule_type', 'resource_type', 'dimension_code',
            'condition', 'scope_mode', 'permission_level',
            'is_denied', 'inherit_to_children', 'propagate_to_parents',
            'source_table', 'source_id',
        }
        missing = required - col_names
        assert not missing, f"Missing columns: {missing}"


# ============================================================================
# T2: role_dimension_scopes 迁移 (P3-T2)
# ============================================================================

class TestMigrateRoleDimensionScopes:
    """P3-T2: role_dimension_scopes → data_permission_rules (rule_type='dimension')"""

    def test_migrate_all_rows(self, db_with_legacy_tables):
        """迁移行数 = 原表行数"""
        from meta.services.permission_migration import migrate_role_dimension_scopes
        ds = db_with_legacy_tables
        migrated = migrate_role_dimension_scopes(ds)
        assert migrated == 3

    def test_migrated_rows_have_rule_type_dimension(self, db_with_legacy_tables):
        """迁移行的 rule_type='dimension'"""
        from meta.services.permission_migration import migrate_role_dimension_scopes
        ds = db_with_legacy_tables
        migrate_role_dimension_scopes(ds)
        rows = ds.execute(
            "SELECT rule_type, COUNT(*) FROM data_permission_rules "
            "WHERE source_table='role_dimension_scopes' GROUP BY rule_type"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 'dimension'
        assert rows[0][1] == 3

    def test_migrated_rows_have_correct_dimension_code(self, db_with_legacy_tables):
        """迁移行的 dimension_code 与原表一致"""
        from meta.services.permission_migration import migrate_role_dimension_scopes
        ds = db_with_legacy_tables
        migrate_role_dimension_scopes(ds)
        rows = ds.execute(
            "SELECT dimension_code FROM data_permission_rules "
            "WHERE source_table='role_dimension_scopes' "
            "ORDER BY source_id"
        ).fetchall()
        codes = [r[0] for r in rows]
        assert codes == ['product', 'version', 'product']

    def test_migrated_rows_have_scope_mode_preserved(self, db_with_legacy_tables):
        """迁移行的 scope_mode 保留 (含 'all')"""
        from meta.services.permission_migration import migrate_role_dimension_scopes
        ds = db_with_legacy_tables
        migrate_role_dimension_scopes(ds)
        row = ds.execute(
            "SELECT scope_mode FROM data_permission_rules "
            "WHERE source_id=3"
        ).fetchone()
        assert row[0] == 'all'

    def test_migrate_idempotent(self, db_with_legacy_tables):
        """重复迁移不会插入重复行"""
        from meta.services.permission_migration import migrate_role_dimension_scopes
        ds = db_with_legacy_tables
        first = migrate_role_dimension_scopes(ds)
        second = migrate_role_dimension_scopes(ds)
        assert first == 3
        assert second == 0  # 已迁移, skip

    def test_migrate_without_target_table_raises(self, db_with_legacy_tables):
        """目标表不存在时抛异常"""
        from meta.services.permission_migration import migrate_role_dimension_scopes
        ds = db_with_legacy_tables
        ds.execute("DROP TABLE data_permission_rules")
        with pytest.raises(RuntimeError, match='data_permission_rules'):
            migrate_role_dimension_scopes(ds)


# ============================================================================
# T3: permission_rules 迁移 (P3-T3)
# ============================================================================

class TestMigratePermissionRules:
    """P3-T3: permission_rules → data_permission_rules (rule_type='condition')"""

    def test_migrate_all_rows(self, db_with_legacy_tables):
        """迁移行数 = 原表行数"""
        from meta.services.permission_migration import migrate_permission_rules
        ds = db_with_legacy_tables
        migrated = migrate_permission_rules(ds)
        assert migrated == 2

    def test_migrated_rows_have_rule_type_condition(self, db_with_legacy_tables):
        """迁移行的 rule_type='condition'"""
        from meta.services.permission_migration import migrate_permission_rules
        ds = db_with_legacy_tables
        migrate_permission_rules(ds)
        rows = ds.execute(
            "SELECT rule_type, COUNT(*) FROM data_permission_rules "
            "WHERE source_table='permission_rules' GROUP BY rule_type"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 'condition'
        assert rows[0][1] == 2

    def test_migrated_rows_have_correct_condition(self, db_with_legacy_tables):
        """迁移行的 condition 与原表一致"""
        from meta.services.permission_migration import migrate_permission_rules
        ds = db_with_legacy_tables
        migrate_permission_rules(ds)
        rows = ds.execute(
            "SELECT condition, resource_type FROM data_permission_rules "
            "WHERE source_table='permission_rules' ORDER BY source_id"
        ).fetchall()
        assert (rows[0][0], rows[0][1]) == ("status = 'active'", 'product')
        assert (rows[1][0], rows[1][1]) == ("owner_id = 1", 'business_object')

    def test_migrate_idempotent(self, db_with_legacy_tables):
        """重复迁移不会插入重复行"""
        from meta.services.permission_migration import migrate_permission_rules
        ds = db_with_legacy_tables
        first = migrate_permission_rules(ds)
        second = migrate_permission_rules(ds)
        assert first == 2
        assert second == 0

    def test_migrate_preserves_is_denied(self, db_with_legacy_tables):
        """is_denied 字段保留 (默认 0)"""
        from meta.services.permission_migration import migrate_permission_rules
        ds = db_with_legacy_tables
        # 插入一行 is_denied=1
        ds.execute(
            "INSERT INTO permission_rules "
            "(role_id, resource_type, condition, is_denied) "
            "VALUES (1, 'product', \"status = 'archived'\", 1)"
        )
        migrate_permission_rules(ds)
        row = ds.execute(
            "SELECT is_denied FROM data_permission_rules "
            "WHERE source_table='permission_rules' AND condition LIKE '%archived%'"
        ).fetchone()
        assert row[0] == 1


# ============================================================================
# T-集成: 完整迁移流程
# ============================================================================

class TestMigrateAll:
    """完整迁移: P3-T2 + P3-T3 一起执行"""

    def test_migrate_all_returns_summary(self, db_with_legacy_tables):
        """migrate_all 返回汇总字典"""
        from meta.services.permission_migration import migrate_all
        ds = db_with_legacy_tables
        result = migrate_all(ds)
        assert result == {'dimension': 3, 'condition': 2, 'total': 5}

    def test_migrate_all_total_rows_in_new_table(self, db_with_legacy_tables):
        """迁移完成后新表行数 = 3+2 = 5"""
        from meta.services.permission_migration import migrate_all
        ds = db_with_legacy_tables
        migrate_all(ds)
        row = ds.execute(
            "SELECT COUNT(*) FROM data_permission_rules"
        ).fetchone()
        assert row[0] == 5