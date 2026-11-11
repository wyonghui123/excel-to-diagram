# -*- coding: utf-8 -*-
"""[E2 2026-11-11] DDL 单源：类型归一 / CHECK 渲染 / 漂移比对 / v256+v257 迁移

覆盖 spec-bo-metadata-single-source-2026-11-11 §16.5 E2 验收口径：
  1. STRING 按声明长度渲染；缺省 200
  2. 枚举列渲染 CHECK；BOOLEAN 归一为 1/0；枚举数量超限（>50）/ 非 SQLite 跳过
  3. 生成 DDL 与实际库自洽（compare_schema 无差异）
  4. 漂移负例：列缺失 / 类型亲和性不符 / CHECK 缺失均能被识别；VARCHAR 长度差异忽略
  5. v256 迁移幂等重建缺 CHECK 的状态表，且 CHECK 真正拦截非法状态值
  6. v257 迁移一次重建完成类型 + CHECK，并修复 menus.page_type 空串
  7. --apply 补 ADD COLUMN / 对齐类型亲和性 / 补 CHECK
  8. 应用层 max_length / pattern 负例（SQLite 不强制 VARCHAR 长度）
"""
import copy
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

# 迁移重建 / 漂移比对需要最小裸 DDL 库，按 test.py 约定显式放行 raw SQL
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta import get_meta_object, registry
from meta.core import schema_generator
from meta.core.datasource import get_data_source
from meta.core.metadata_driven_validator import MetadataDrivenValidator
from meta.core.models import FieldType
from meta.core.schema_generator import (
    SchemaGenerator, _replace_column_type, enum_check_values, parse_schema_text,
    sqlite_type_affinity)
from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory
from meta.migrations.v256__align_status_check import _has_status_check, migrate, verify
from meta.migrations.v257__align_types_and_checks import (
    MAPPING_PATH, migrate as migrate_v257, verify as verify_v257)
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


def _all_expected():
    objects = [get_meta_object(oid) for oid in registry.list_objects()]
    return build_expected_schema([obj for obj in objects if obj])


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


def test_type_affinity_ignores_varchar_length():
    """SQLite 不强制 VARCHAR(n)：长度/精度差异不算类型漂移。"""
    assert sqlite_type_affinity('VARCHAR(10)') == sqlite_type_affinity('VARCHAR(200)') == 'TEXT'
    assert sqlite_type_affinity('DECIMAL(10,2)') == 'NUMERIC'
    assert sqlite_type_affinity('BOOLEAN') == 'NUMERIC'
    assert sqlite_type_affinity('INTEGER') == 'INTEGER'
    assert sqlite_type_affinity('REAL') == 'REAL'
    assert sqlite_type_affinity('') == 'BLOB'


def test_replace_column_type_keeps_constraints():
    definition = '"code" VARCHAR(10) NOT NULL DEFAULT \'X\' CHECK (code IN (\'A\'))'
    replaced = _replace_column_type(definition, 'code', 'VARCHAR(32)')
    assert replaced.startswith('"code"\tVARCHAR(32) NOT NULL')
    assert 'DEFAULT \'X\'' in replaced
    assert 'CHECK (code IN' in replaced


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


def test_boolean_enum_check_uses_1_0():
    """SQLite 布尔列实际写 0/1；CHECK 不能渲染成 'True'/'False'。"""
    expected = _all_expected()
    check = expected['enum_values']['columns']['is_active']['check']
    assert set(check) == {'1', '0'}
    assert 'True' not in check and 'False' not in check


def test_yaml_unquoted_no_parses_as_string():
    """YAML 1.1 会把未加引号的 no 解析为布尔 False，必须显式加引号。"""
    check = _all_expected()['configurations']['columns']['match_policy_used']['check']
    assert 'no' in check
    assert 'False' not in check


def test_runtime_status_columns_exempt_from_check():
    """users/audit_logs 的运行时列由业务自由写入，不得生成 CHECK。"""
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
    for column in ('action', 'log_category', 'log_level', 'object_type'):
        assert expected['audit_logs']['columns'][column]['check'] is None


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
    columns['status']['type'] = 'INTEGER'
    columns['status']['check'] = None

    report = compare_schema(expected, actual)
    assert '{0}.{1}'.format(table, removed) in report['missing_columns']
    assert any(item.startswith('{0}.status:'.format(table)) for item in report['type_mismatches'])
    assert '{0}.status'.format(table) in report['check_missing']


def test_varchar_length_difference_is_not_drift():
    """纯长度差异不进入漂移报告：SQLite 不强制 VARCHAR(n)。"""
    expected = {'demo': {'columns': {
        'status': {'type': 'VARCHAR(20)', 'check': None}}}}
    actual = {'demo': {'columns': {
        'status': {'type': 'VARCHAR(200)', 'check': None}}}}
    assert compare_schema(expected, actual)['type_mismatches'] == []


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
# v257 迁移
# ─────────────────────────────────────────────────────────────────────────────

V257_MAPPING = {
    'menus_page_type_fix': {
        'table': 'menus', 'column': 'page_type', 'from': '', 'to': 'object_list'},
    'tables': {
        'widgets': {
            'types': {'amount': 'REAL'},
            'checks': {'status': ['draft', 'posted']},
        },
    },
}


def _create_legacy_v257_db(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE menus (id INTEGER PRIMARY KEY, page_type VARCHAR(50))")
    conn.execute("INSERT INTO menus (id, page_type) VALUES (1, '')")
    conn.execute("INSERT INTO menus (id, page_type) VALUES (2, 'object_list')")
    conn.execute(
        "CREATE TABLE widgets ("
        " id INTEGER PRIMARY KEY,"
        " status VARCHAR(200),"
        " amount VARCHAR(200))")
    conn.execute("INSERT INTO widgets (status, amount) VALUES ('draft', '1.5')")
    conn.commit()
    conn.close()


def _widgets_sql(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='widgets'").fetchone()
        return row[0] if row else ''
    finally:
        conn.close()


def test_v257_aligns_type_check_and_menus(tmp_path):
    db_path = tmp_path / 'v257.db'
    _create_legacy_v257_db(db_path)

    assert migrate_v257(str(db_path), mapping=V257_MAPPING) is True
    assert verify_v257(str(db_path), mapping=V257_MAPPING) is True

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM menus WHERE TRIM(COALESCE(page_type, ''))=''").fetchone()[0] == 0
        types = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(widgets)")}
        assert types['amount'] == 'REAL'
        assert conn.execute("SELECT amount FROM widgets").fetchone()[0] == 1.5
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO widgets (status) VALUES ('bogus')")
    finally:
        conn.close()


def test_v257_is_idempotent(tmp_path):
    db_path = tmp_path / 'v257_twice.db'
    _create_legacy_v257_db(db_path)
    migrate_v257(str(db_path), mapping=V257_MAPPING)
    before = _widgets_sql(db_path)
    assert migrate_v257(str(db_path), mapping=V257_MAPPING) is True
    assert _widgets_sql(db_path) == before


def test_v257_mapping_artifact_shape():
    payload = json.loads(Path(MAPPING_PATH).read_text(encoding='utf-8'))
    assert payload['menus_page_type_fix']['to'] == 'object_list'
    tables = payload['tables']
    for excluded in payload['excluded_tables']:
        assert excluded not in tables
    assert len(tables) > 100
    for table, spec in tables.items():
        assert spec['types'] or spec['checks'], table
        assert all(spec['types'].values()), table
        assert all(spec['checks'].values()), table

    # 本轮 YAML 扩枚举必须进入冻结映射
    document_category = tables['type_definitions']['checks']['document_category']
    assert 'invoice' in document_category and 'cancellation' in document_category
    line_category = tables['type_definitions']['checks']['line_category']
    assert {'asset', 'expense', 'subcontract'} <= set(line_category)
    assert 'object_list' in tables['menus']['checks']['page_type']


# ─────────────────────────────────────────────────────────────────────────────
# --apply：ADD COLUMN / 类型亲和性 / CHECK
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


def test_apply_aligns_type_and_check_in_one_rebuild(tmp_path):
    db_path = tmp_path / 'apply_type.db'
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE demo (id INTEGER PRIMARY KEY,"
        " status VARCHAR(200), amount VARCHAR(200))")
    conn.execute("INSERT INTO demo (status, amount) VALUES ('draft', '2')")
    conn.commit()
    conn.close()

    expected = {'demo': {'columns': {
        'status': {'type': 'VARCHAR(20)', 'check': ['draft', 'posted']},
        'amount': {'type': 'REAL', 'check': None},
    }}}
    report = _empty_report()
    report['type_mismatches'] = ['demo.amount: 期望 REAL / 实际 VARCHAR(200)']
    report['check_missing'] = ['demo.status']

    assert apply_schema_fixes(str(db_path), report, expected) == 1

    conn = sqlite3.connect(str(db_path))
    try:
        types = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(demo)")}
        assert types['amount'] == 'REAL'
        demo_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='demo'").fetchone()[0]
        assert 'CHECK (status IN' in demo_sql
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO demo (status) VALUES ('bogus')")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 应用层长度 / 正则（SQLite 不强制 VARCHAR 长度）
# ─────────────────────────────────────────────────────────────────────────────

def test_app_layer_max_length_enforces_type_definition_code():
    validator = MetadataDrivenValidator(None)
    code = _field(get_meta_object('type_definition'), 'code')
    assert code.max_length == 32
    assert validator._check_max_length(code, 'A' * 32, 'code') == []
    assert validator._check_max_length(code, 'A' * 33, 'code')


def test_division_code_allows_hyphen_and_32_chars():
    validator = MetadataDrivenValidator(None)
    code = _field(get_meta_object('division'), 'code')
    assert validator._check_pattern(code, 'SCN-SO-MD-DIV-D01', 'code') == []
    assert validator._check_max_length(code, 'A' * 32, 'code') == []
    assert validator._check_max_length(code, 'A' * 33, 'code')