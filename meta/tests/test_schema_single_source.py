# -*- coding: utf-8 -*-
"""[E2 2026-11-11] DDL 单源：类型归一 / CHECK 渲染 / 漂移比对 / v256 迁移

覆盖 spec-bo-metadata-single-source-2026-11-11 §16.5 E2 验收口径：
  1. STRING 按声明长度渲染；缺省 200
  2. 枚举列渲染 CHECK；枚举数量超限（>50）跳过；非 SQLite 方言跳过
  3. 生成 DDL 与实际库自洽（compare_schema 无差异）
  4. 漂移负例：列缺失 / 类型不符 / CHECK 缺失 均能被识别
  5. v256 迁移幂等重建缺 CHECK 的状态表，且 CHECK 真正拦截非法状态值
  6. --apply 仅补 ADD COLUMN
"""
import copy
import sqlite3
from types import SimpleNamespace

# 迁移重建 / 漂移比对需要最小裸 DDL 库，按 test.py 约定显式放行 raw SQL
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta import get_meta_object, registry
from meta.core import schema_generator
from meta.core.datasource import get_data_source
from meta.core.models import FieldType
from meta.core.schema_generator import SchemaGenerator, enum_check_values
from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory
from meta.migrations.v256__align_status_check import _has_status_check, migrate, verify
from meta.tools.sync_schema import (
    apply_schema_fixes,
    build_expected_schema,
    compare_schema,
    load_db_schema,
)

RECEIPT_ID = 'receipt'


@pytest.fixture(scope='module', autouse=True)
def _load_meta():
    if not registry.list_objects():
        register_from_directory(get_yaml_schema_dir())


def _receipt():
    obj = get_meta_object(RECEIPT_ID)
    assert obj is not None, 'receipt 元对象未加载'
    return obj


def _field(obj, name):
    for field in obj.fields:
        if field.id == name:
            return field
    raise AssertionError('字段未找到: {0}'.format(name))


def _empty_report():
    return {
        'missing_tables': [],
        'missing_columns': [],
        'type_mismatches': [],
        'check_missing': [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 类型归一
# ─────────────────────────────────────────────────────────────────────────────

def test_string_type_uses_declared_max_length():
    generator = SchemaGenerator('sqlite')
    status = _field(_receipt(), 'status')
    assert generator._sql_type(status) == 'VARCHAR({0})'.format(
        status.semantics.max_length or status.max_length)


def test_string_type_defaults_to_200():
    generator = SchemaGenerator('sqlite')
    stub = SimpleNamespace(
        field_type=FieldType.STRING,
        max_length=None,
        semantics=SimpleNamespace(max_length=None),
    )
    assert generator._sql_type(stub) == 'VARCHAR(200)'


def test_normalize_sql_type_ignores_case_and_spaces():
    assert schema_generator.normalize_sql_type(' varchar ( 20 ) ') == 'VARCHAR(20)'
    assert schema_generator.normalize_sql_type(None) == ''


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 渲染
# ─────────────────────────────────────────────────────────────────────────────

def test_enum_values_rendered_as_check():
    status = _field(_receipt(), 'status')
    values = enum_check_values(status)
    assert values, 'receipt.status 应有枚举值'
    check = SchemaGenerator('sqlite')._sql_check(status)
    assert check == 'CHECK (status IN ({0}))'.format(
        ', '.join("'{0}'".format(v) for v in values))


def test_check_skipped_when_enum_too_long(monkeypatch):
    monkeypatch.setattr(schema_generator, 'MAX_ENUM_CHECK_VALUES', 1)
    assert SchemaGenerator('sqlite')._sql_check(_field(_receipt(), 'status')) is None


def test_check_skipped_for_non_sqlite_dialect():
    assert SchemaGenerator('mysql')._sql_check(_field(_receipt(), 'status')) is None


def test_column_definition_contains_check():
    generator = SchemaGenerator('sqlite')
    definition = generator._generate_column_definition(_field(_receipt(), 'status'))
    assert 'CHECK (status IN (' in definition


def test_runtime_status_columns_exempt_from_check():
    """users/audit_logs.status 由运行时写入 archived/retried/success 等，不得生成 CHECK。"""
    generator = SchemaGenerator('sqlite')
    objects = [get_meta_object(oid) for oid in registry.list_objects()]
    objects = {obj.table_name: obj for obj in objects if obj}
    for table in ('users', 'audit_logs'):
        sql = generator.generate_create_table(objects[table])
        status_lines = [line for line in sql.splitlines() if 'status' in line]
        assert not any('CHECK' in line for line in status_lines), table

    expected = build_expected_schema(list(objects.values()))
    assert expected['users']['columns']['status']['check'] is None
    assert expected['audit_logs']['columns']['status']['check'] is None


# ─────────────────────────────────────────────────────────────────────────────
# 漂移比对
# ─────────────────────────────────────────────────────────────────────────────

def test_generated_ddl_matches_itself(tmp_path):
    obj = _receipt()
    generator = SchemaGenerator('sqlite')
    ds = get_data_source('sqlite', path=str(tmp_path / 'generated.db'))
    try:
        ds.execute(generator.generate_create_table(obj))
        actual = load_db_schema(ds)
    finally:
        ds.disconnect()

    report = compare_schema(build_expected_schema([obj]), actual)
    assert all(not items for items in report.values()), report


def test_drift_detects_missing_column_type_and_check(tmp_path):
    obj = _receipt()
    generator = SchemaGenerator('sqlite')
    ds = get_data_source('sqlite', path=str(tmp_path / 'drift.db'))
    try:
        ds.execute(generator.generate_create_table(obj))
        actual = load_db_schema(ds)
    finally:
        ds.disconnect()

    expected = build_expected_schema([obj])
    table = obj.table_name
    actual = copy.deepcopy(actual)
    columns = actual[table]['columns']
    removed = next(name for name in columns if name != 'status')
    del columns[removed]
    columns['status']['type'] = 'TEXT'
    columns['status']['check'] = None

    report = compare_schema(expected, actual)
    assert '{0}.{1}'.format(table, removed) in report['missing_columns']
    assert any(item.startswith('{0}.status:'.format(table)) for item in report['type_mismatches'])
    assert '{0}.status'.format(table) in report['check_missing']


def test_missing_table_reported():
    expected = {'no_such_table': {'columns': {'id': {'type': 'INTEGER', 'check': None}}}}
    report = compare_schema(expected, {})
    assert report['missing_tables'] == ['no_such_table']


# ─────────────────────────────────────────────────────────────────────────────
# v256 迁移
# ─────────────────────────────────────────────────────────────────────────────

def _create_legacy_receipts(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE receipts ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " code VARCHAR(50) NOT NULL,"
        " status VARCHAR(200))")
    conn.execute("INSERT INTO receipts (code, status) VALUES ('R-1', 'draft')")
    conn.commit()
    conn.close()


def _receipts_sql(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='receipts'").fetchone()
        return row[0] if row else ''
    finally:
        conn.close()


def _receipts_has_check(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return _has_status_check(conn, 'receipts')
    finally:
        conn.close()


def test_v256_rebuild_preserves_data_and_enforces_check(tmp_path):
    db_path = tmp_path / 'migration.db'
    _create_legacy_receipts(db_path)
    assert not _receipts_has_check(db_path)

    assert migrate(str(db_path)) is True
    assert verify(str(db_path)) is True

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT code, status FROM receipts").fetchone() == ('R-1', 'draft')
        assert _has_status_check(conn, 'receipts')
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO receipts (code, status) VALUES ('R-2', 'bogus')")
    finally:
        conn.close()


def test_v256_is_idempotent(tmp_path):
    db_path = tmp_path / 'migration_twice.db'
    _create_legacy_receipts(db_path)
    migrate(str(db_path))
    before = _receipts_sql(db_path)
    assert migrate(str(db_path)) is True
    assert _receipts_sql(db_path) == before


def test_v256_keeps_dependent_views_and_indexes(tmp_path):
    """真实库有引用单据表的视图：重建表必须先降后升视图，且不丢索引/数据。"""
    db_path = tmp_path / 'migration_view.db'
    _create_legacy_receipts(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE INDEX idx_receipts_status ON receipts(status)")
    conn.execute(
        "CREATE VIEW receipt_brief_view AS SELECT code, status FROM receipts")
    conn.commit()
    conn.close()

    assert migrate(str(db_path)) is True

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute(
            "SELECT code, status FROM receipt_brief_view").fetchall() == [('R-1', 'draft')]
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='receipts'")}
        assert 'idx_receipts_status' in indexes
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO receipts (code, status) VALUES ('R-2', 'bogus')")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# --apply：只补 ADD COLUMN
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_adds_missing_column_only(tmp_path):
    db_path = tmp_path / 'apply.db'
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    expected = {'demo': {'columns': {'extra': {'type': 'VARCHAR(20)', 'check': None}}}}
    report = _empty_report()
    report['missing_columns'] = ['demo.extra']

    assert apply_schema_fixes(str(db_path), report, expected) == 1
    conn = sqlite3.connect(str(db_path))
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(demo)")]
    finally:
        conn.close()
    assert 'extra' in columns