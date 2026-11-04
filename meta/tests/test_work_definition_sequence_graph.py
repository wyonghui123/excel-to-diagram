# -*- coding: utf-8 -*-
"""P5 路线序列图校验与展开测试（spec §12.2–§12.4 / §7.1）。

覆盖:
  · YAML：5 字段 / parallel / 部分唯一索引 / UI 分组。
  · v199 迁移：5 列 + grade_code + 索引 + 枚举 + 权限 + 菜单；
    migrate → verify → 幂等 → rollback → verify 失败。
  · WorkDefinitionSequenceService：G1–G11 硬失败、G1/G12 只告警、
    expand_sequences 替代/并行/回退。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json
import pathlib
import sqlite3
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from meta.services.work_definition_sequence_service import (  # noqa: E402
    WorkDefinitionSequenceError,
    WorkDefinitionSequenceService,
)

pytestmark = pytest.mark.unit

SCHEMA_DIR = ROOT / 'meta' / 'schemas'

BASE_SCHEMA = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT,
    base_uom INTEGER, item_group_id INTEGER
);
CREATE TABLE orgs (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT);
CREATE TABLE uoms (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT,
                   uom_group_id INTEGER);
CREATE TABLE item_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT);
CREATE TABLE item_structures (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT);
CREATE TABLE work_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT,
    definition_kind TEXT, revision TEXT, status TEXT
);
CREATE TABLE attribute_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER DEFAULT 0,
    code TEXT, name TEXT, data_type TEXT DEFAULT 'string',
    multi_value_flag INTEGER DEFAULT 0, status TEXT DEFAULT 'active'
);
CREATE TABLE enum_types (
    id TEXT PRIMARY KEY, name TEXT, category TEXT, mutability TEXT,
    dimension_schema TEXT, description TEXT, created_at TEXT
);
CREATE TABLE enum_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT, enum_type_id TEXT, code TEXT,
    name TEXT, name_en TEXT, sort_order INTEGER, is_active INTEGER,
    is_system INTEGER, created_at TEXT
);
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT,
    resource_type TEXT, action TEXT
);
CREATE TABLE permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE permission_set_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, permission_set_id INTEGER,
    permission_code TEXT, permission_id INTEGER, granted INTEGER,
    created_at TEXT
);
CREATE TABLE menus (
    menu_code TEXT PRIMARY KEY, menu_name TEXT, menu_path TEXT,
    page_type TEXT, object_types TEXT, primary_object_type TEXT,
    bo_bindings TEXT, required_permissions TEXT, parent_menu TEXT,
    icon TEXT, color TEXT, description TEXT, sort_order INTEGER,
    is_active INTEGER DEFAULT 1, show_in_sidebar INTEGER DEFAULT 0,
    auto_generated INTEGER DEFAULT 0
);
CREATE TABLE menu_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, menu_code TEXT, menu_name TEXT,
    menu_path TEXT, required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0, parent_menu TEXT,
    icon TEXT, sort_order INTEGER, is_active INTEGER DEFAULT 1,
    data_permission_hint TEXT, UNIQUE (menu_code)
);
CREATE TABLE work_definition_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, definition_id INTEGER,
    seq INTEGER, status TEXT DEFAULT 'active', sequence_id INTEGER
);
"""

SERVICE_SCHEMA = """
CREATE TABLE work_definition_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT, definition_id INTEGER,
    seq_no INTEGER NOT NULL, seq_type TEXT NOT NULL DEFAULT 'std',
    description TEXT, branch_operation_seq INTEGER,
    return_operation_seq INTEGER, lot_min REAL, lot_max REAL,
    priority INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE work_definition_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, definition_id INTEGER,
    seq INTEGER, status TEXT DEFAULT 'active', sequence_id INTEGER
);
CREATE TABLE production_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, work_definition_id INTEGER,
    lot_min REAL, lot_max REAL, status TEXT DEFAULT 'active'
);
"""


def _load_yaml(name):
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _field(doc, field_id):
    return next(f for f in doc['fields'] if f['id'] == field_id)


def _index(doc, name):
    return next(i for i in doc['indexes'] if i.get('name') == name)


class MemDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# YAML 声明
# ---------------------------------------------------------------------------
def test_yaml_p5_fields_and_parallel():
    doc = _load_yaml('work_definition_sequence.yaml')
    for field_id in ('branch_operation_seq', 'return_operation_seq',
                     'lot_min', 'lot_max', 'priority'):
        assert field_id in {f['id'] for f in doc['fields']}

    assert _field(doc, 'branch_operation_seq')['nullable'] is True
    assert _field(doc, 'return_operation_seq')['nullable'] is True
    assert _field(doc, 'lot_min')['nullable'] is True
    assert _field(doc, 'lot_max')['nullable'] is True
    priority = _field(doc, 'priority')
    assert priority['required'] is True
    assert priority['default'] == 1
    assert priority['constraints'][0]['gte'] == 1

    seq_type = _field(doc, 'seq_type')
    assert [v['value'] for v in seq_type['enum_values']] == [
        'std', 'parallel', 'alternative']
    assert seq_type['enum_values'][1]['label'] == '并行'

    partial = _index(doc, 'uq_work_definition_sequence_branch_priority')
    assert partial['unique'] is True
    assert partial['type'] == 'partial'
    assert partial['fields'] == [
        'definition_id', 'branch_operation_seq', 'priority']
    assert "seq_type = 'alternative'" in partial['condition']
    assert _index(doc, 'idx_work_definition_sequence_branch')['fields'] == [
        'definition_id', 'branch_operation_seq']

    titles = [s['title'] for s in doc['ui_view_config']['form']['sections']]
    assert '分支' in titles and '适用范围' in titles


# ---------------------------------------------------------------------------
# v199 迁移
# ---------------------------------------------------------------------------
@pytest.fixture()
def migrated_db(tmp_path):
    db_path = tmp_path / 'p5.db'
    conn = sqlite3.connect(str(db_path))
    conn.executescript(BASE_SCHEMA)
    from meta.migrations import v188__routing_p4a as v188
    from meta.migrations import v196__batch_foundation as v196
    for _name, ddl in v188.TABLES:
        conn.execute(ddl)
    for _name, ddl in v196.TABLES:
        conn.execute(ddl)
    conn.executemany('INSERT INTO permission_sets (id, code, is_active) '
                     'VALUES (?, ?, 1)', [(1, 'admin'), (2, 'default')])
    conn.execute("INSERT INTO menus (menu_code, menu_name, menu_path, sort_order) "
                 "VALUES ('master-data', '主数据', '/master-data', 100)")
    conn.execute("INSERT INTO items (id, code, base_uom, item_group_id) "
                 "VALUES (1, 'ITEM1', 1, 1)")
    conn.execute("INSERT INTO orgs (id, code) VALUES (1, 'PLANT1')")
    conn.execute("INSERT INTO uoms (id, code, uom_group_id) VALUES (1, 'KG', 10)")
    conn.execute("INSERT INTO item_groups (id, code) VALUES (1, 'FG')")
    conn.execute("INSERT INTO attribute_definitions (id, code, name) "
                 "VALUES (1, 'color', '颜色')")
    conn.commit()
    conn.close()
    return db_path


def test_v199_migrate_verify_idempotent(migrated_db):
    from meta.migrations import v199__routing_p5 as v199

    assert v199.migrate(migrated_db, skip_backup=True) is True
    assert v199.verify(migrated_db) is True
    assert v199.migrate(migrated_db, skip_backup=True) is True
    assert v199.verify(migrated_db) is True


def test_v199_columns_indexes_enums_menu_real(migrated_db):
    from meta.migrations import v199__routing_p5 as v199

    v199.migrate(migrated_db, skip_backup=True)
    conn = sqlite3.connect(str(migrated_db))
    try:
        info = {row[1]: row for row in conn.execute(
            'PRAGMA table_info(work_definition_sequences)')}
        for col in ('branch_operation_seq', 'return_operation_seq',
                    'lot_min', 'lot_max', 'priority'):
            assert col in info
        assert info['priority'][3] == 1
        assert str(info['priority'][4]) == '1'

        batch_info = {row[1] for row in conn.execute(
            'PRAGMA table_info(batches)')}
        assert 'grade_code' in batch_info

        partial = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            ('uq_work_definition_sequence_branch_priority',)).fetchone()
        assert partial and 'WHERE' in partial[0]
        assert "seq_type = 'alternative'" in partial[0]

        policy_partial = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            ('uq_batch_selection_policy_scope_priority',)).fetchone()
        assert policy_partial and "WHERE status = 'active'" in policy_partial[0]

        menu = conn.execute(
            'SELECT menu_path, parent_menu, primary_object_type, sort_order '
            'FROM menus WHERE menu_code=?',
            ('batch-selection-policy-list',)).fetchone()
        assert menu == ('/master-data/batch-selection-policy', 'master-data',
                        'batch_selection_policy', 106)

        assert conn.execute(
            "SELECT 1 FROM enum_values WHERE enum_type_id='sequence_type' "
            "AND code='parallel'").fetchone() is not None
        assert conn.execute(
            "SELECT COUNT(*) FROM enum_values WHERE "
            "enum_type_id='batch_selection_scope'").fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM enum_values WHERE "
            "enum_type_id='batch_selection_policy_status'").fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM permissions WHERE resource_type='batch_selection_policy'"
        ).fetchone()[0] == 4
    finally:
        conn.close()


def test_v199_rollback_reverts(migrated_db):
    from meta.migrations import v199__routing_p5 as v199

    assert v199.migrate(migrated_db, skip_backup=True) is True
    assert v199.rollback(migrated_db) is True
    assert v199.verify(migrated_db) is False

    conn = sqlite3.connect(str(migrated_db))
    try:
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ('batch_selection_policies',)).fetchone() is None
        seq_info = {row[1] for row in conn.execute(
            'PRAGMA table_info(work_definition_sequences)')}
        assert 'priority' not in seq_info
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 服务：构造
# ---------------------------------------------------------------------------
def _service_db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(SERVICE_SCHEMA)
    return conn


def _add_sequence(conn, definition_id, seq_no, seq_type='std', branch=None,
                  return_seq=None, lot_min=None, lot_max=None, priority=1):
    cur = conn.execute(
        'INSERT INTO work_definition_sequences '
        '(definition_id, seq_no, seq_type, branch_operation_seq, '
        'return_operation_seq, lot_min, lot_max, priority) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [definition_id, seq_no, seq_type, branch, return_seq,
         lot_min, lot_max, priority])
    return cur.lastrowid


def _add_op(conn, definition_id, seq, sequence_id=None, status='active'):
    cur = conn.execute(
        'INSERT INTO work_definition_operations '
        '(definition_id, seq, status, sequence_id) VALUES (?, ?, ?, ?)',
        [definition_id, seq, status, sequence_id])
    return cur.lastrowid


def _service(conn):
    return WorkDefinitionSequenceService(MemDS(conn))


def _expect(service, payload, rule, existing=None):
    with pytest.raises(WorkDefinitionSequenceError) as exc:
        service.validate_sequence(payload, existing)
    assert exc.value.rule == rule
    return exc.value


def _base_payload(**kwargs):
    data = {'definition_id': 1, 'seq_no': 2, 'seq_type': 'std',
            'priority': 1}
    data.update(kwargs)
    return data


# ---------------------------------------------------------------------------
# 服务：行级规则
# ---------------------------------------------------------------------------
def test_row_rules_g2_g3_g4_g7_priority():
    conn = _service_db()
    service = _service(conn)
    _add_op(conn, 1, 10)
    _add_op(conn, 1, 30)

    _expect(service, _base_payload(seq_type='std', branch_operation_seq=10),
            'SEQUENCE_STD_HAS_BRANCH')
    _expect(service, _base_payload(seq_type='parallel', seq_no=2),
            'SEQUENCE_PARALLEL_BRANCH_REQUIRED')
    _expect(service, _base_payload(seq_type='parallel', branch_operation_seq=30,
                                   return_operation_seq=10),
            'SEQUENCE_RETURN_NOT_AFTER_BRANCH')
    _expect(service, _base_payload(seq_type='alternative', seq_no=2),
            'SEQUENCE_ALTERNATIVE_BOUNDARY_REQUIRED')
    _expect(service, _base_payload(seq_type='alternative',
                                   branch_operation_seq=10,
                                   return_operation_seq=10),
            'SEQUENCE_BOUNDARY_INVALID')
    _expect(service, _base_payload(lot_min=-1),
            'SEQUENCE_LOT_MIN_NEGATIVE')
    _expect(service, _base_payload(lot_min=10, lot_max=10),
            'SEQUENCE_LOT_RANGE_INVALID')
    _expect(service, _base_payload(priority=0),
            'SEQUENCE_PRIORITY_INVALID')


def test_std_duplicate_rejected_on_write():
    conn = _service_db()
    service = _service(conn)
    _add_sequence(conn, 1, 1, 'std')
    _expect(service, _base_payload(seq_type='std', seq_no=2),
            'MULTIPLE_STD_SEQUENCE')


def test_branch_and_return_must_exist_in_std():
    conn = _service_db()
    service = _service(conn)
    _add_op(conn, 1, 10)
    _add_op(conn, 1, 30)
    _expect(service, _base_payload(seq_type='alternative', branch_operation_seq=99,
                                   return_operation_seq=100),
            'SEQUENCE_BRANCH_NOT_IN_STD')
    _expect(service, _base_payload(seq_type='alternative', branch_operation_seq=10,
                                   return_operation_seq=99),
            'SEQUENCE_RETURN_NOT_IN_STD')


def test_alternative_priority_unique_per_branch():
    conn = _service_db()
    service = _service(conn)
    _add_op(conn, 1, 10)
    _add_op(conn, 1, 30)
    _add_sequence(conn, 1, 2, 'alternative', 10, 30, priority=1)
    _expect(service, _base_payload(seq_no=3, seq_type='alternative',
                                   branch_operation_seq=10,
                                   return_operation_seq=30,
                                   priority=1),
            'SEQUENCE_BRANCH_PRIORITY_DUPLICATE')


def test_non_std_requires_operations():
    conn = _service_db()
    _add_op(conn, 1, 10)
    _add_op(conn, 1, 30)
    _add_sequence(conn, 1, 2, 'alternative', 10, 30)
    rules = {w['rule'] for w in _service(conn).validate_sequence_graph(1)}
    assert 'SEQUENCE_NO_OPERATION' in rules


# ---------------------------------------------------------------------------
# 服务：图规则（只读巡检）
# ---------------------------------------------------------------------------
def test_graph_flags_duplicate_and_boundary_operation():
    conn = _service_db()
    for seq in (10, 20, 30):
        _add_op(conn, 1, seq)
    alt = _add_sequence(conn, 1, 2, 'alternative', 10, 30)
    _add_op(conn, 1, 20, alt)
    _add_op(conn, 1, 20, alt)
    rules = {w['rule'] for w in _service(conn).validate_sequence_graph(1)}
    assert 'SEQUENCE_OPERATION_SEQ_DUPLICATE' in rules

    conn.execute('DELETE FROM work_definition_operations WHERE sequence_id = ?',
                 [alt])
    _add_op(conn, 1, 10, alt)
    rules = {w['rule'] for w in _service(conn).validate_sequence_graph(1)}
    assert 'SEQUENCE_OPERATION_CONFLICTS_BOUNDARY' in rules


def test_graph_flags_boundary_operation_on_other_sequence():
    conn = _service_db()
    for seq in (10, 20, 30, 40):
        _add_op(conn, 1, seq)
    alt_a = _add_sequence(conn, 1, 2, 'alternative', 10, 30)
    alt_b = _add_sequence(conn, 1, 3, 'alternative', 20, 40)
    _add_op(conn, 1, 20, alt_a)
    _add_op(conn, 1, 30, alt_b)
    rules = {w['rule'] for w in _service(conn).validate_sequence_graph(1)}
    assert 'SEQUENCE_BOUNDARY_OPERATION_NOT_STD' in rules


def test_graph_flags_cycle():
    conn = _service_db()
    for seq in (10, 20, 30):
        _add_op(conn, 1, seq)
    alt_a = _add_sequence(conn, 1, 2, 'alternative', 10, 30)
    alt_b = _add_sequence(conn, 1, 3, 'alternative', 30, 10)
    _add_op(conn, 1, 20, alt_a)
    _add_op(conn, 1, 20, alt_b)
    rules = {w['rule'] for w in _service(conn).validate_sequence_graph(1)}
    assert 'SEQUENCE_GRAPH_CYCLE' in rules


def test_graph_warns_multiple_std_and_lot_coverage():
    conn = _service_db()
    _add_sequence(conn, 1, 1, 'std')
    _add_sequence(conn, 1, 2, 'std')
    _add_sequence(conn, 1, 3, 'alternative', 10, 20,
                  lot_min=100, lot_max=200)
    conn.execute('INSERT INTO production_versions '
                 '(work_definition_id, lot_min, lot_max, status) '
                 "VALUES (1, 0, 50, 'active')")
    rules = {w['rule'] for w in _service(conn).validate_sequence_graph(1)}
    assert 'MULTIPLE_STD_SEQUENCE' in rules
    assert 'SEQUENCE_LOT_NOT_COVERED' in rules


def test_graph_lot_covered_has_no_warning():
    conn = _service_db()
    _add_sequence(conn, 1, 1, 'std')
    _add_sequence(conn, 1, 2, 'alternative', 10, 20,
                  lot_min=100, lot_max=200)
    conn.execute('INSERT INTO production_versions '
                 '(work_definition_id, lot_min, lot_max, status) '
                 "VALUES (1, 50, 500, 'active')")
    rules = {w['rule'] for w in _service(conn).validate_sequence_graph(1)}
    assert 'SEQUENCE_LOT_NOT_COVERED' not in rules


# ---------------------------------------------------------------------------
# 服务：工序校验 G11
# ---------------------------------------------------------------------------
def test_operation_boundary_seq_cannot_change():
    conn = _service_db()
    service = _service(conn)
    op = _add_op(conn, 1, 10)
    _add_sequence(conn, 1, 2, 'alternative', 10, 30)
    with pytest.raises(WorkDefinitionSequenceError) as exc:
        service.validate_operation(
            {'definition_id': 1, 'seq': 11, 'sequence_id': None},
            {'id': op, 'definition_id': 1, 'seq': 10, 'sequence_id': None})
    assert exc.value.rule == 'SEQUENCE_BOUNDARY_OPERATION_REFERENCED'


def test_operation_in_non_std_cannot_take_boundary_seq():
    conn = _service_db()
    service = _service(conn)
    _add_op(conn, 1, 10)
    _add_op(conn, 1, 30)
    alt = _add_sequence(conn, 1, 2, 'alternative', 10, 30)
    with pytest.raises(WorkDefinitionSequenceError) as exc:
        service.validate_operation(
            {'definition_id': 1, 'seq': 10, 'sequence_id': alt})
    assert exc.value.rule == 'SEQUENCE_OPERATION_CONFLICTS_BOUNDARY'


# ---------------------------------------------------------------------------
# 服务：展开
# ---------------------------------------------------------------------------
def _expand_setup(conn, definition_id, alt_lot=None):
    _add_sequence(conn, definition_id, 1, 'std')
    for seq in (10, 20, 30, 40):
        _add_op(conn, definition_id, seq)
    if alt_lot is not None:
        alt = _add_sequence(conn, definition_id, 2, 'alternative', 10, 30,
                            lot_min=alt_lot[0], lot_max=alt_lot[1])
    else:
        alt = _add_sequence(conn, definition_id, 2, 'alternative', 10, 30)
    _add_op(conn, definition_id, 15, alt)
    _add_op(conn, definition_id, 25, alt)


def test_expand_alternative_replaces_interval():
    conn = _service_db()
    _expand_setup(conn, 1, alt_lot=(1, 100))
    result = _service(conn).expand_sequences(1, 50)
    assert [op['seq'] for op in result['operations']] == [10, 15, 25, 30, 40]
    assert [op['source'] for op in result['operations']] == [
        'std', 'alternative', 'alternative', 'std', 'std']
    decision = result['decisions'][0]
    assert decision['rule'] == 'ROUTE_ALTERNATIVE_SELECTED'
    assert decision['return'] == 30


def test_expand_falls_back_when_lot_out_of_range():
    conn = _service_db()
    _expand_setup(conn, 1, alt_lot=(1, 100))
    result = _service(conn).expand_sequences(1, 500)
    assert [op['seq'] for op in result['operations']] == [10, 20, 30, 40]
    assert result['decisions'][0]['rule'] == 'ROUTE_FALLBACK_STD'


def test_expand_parallel_side_by_side():
    conn = _service_db()
    _add_sequence(conn, 2, 1, 'std')
    _add_op(conn, 2, 50)
    _add_op(conn, 2, 60)
    par = _add_sequence(conn, 2, 2, 'parallel', 50)
    _add_op(conn, 2, 51, par)
    _add_op(conn, 2, 52, par)
    result = _service(conn).expand_sequences(2)
    assert [op['seq'] for op in result['operations']] == [50, 51, 52, 60]
    assert [op['source'] for op in result['operations']] == [
        'std', 'parallel', 'parallel', 'std']


def test_expand_without_lot_uses_first_alternative():
    conn = _service_db()
    _expand_setup(conn, 1, alt_lot=(1, 100))
    result = _service(conn).expand_sequences(1, None)
    assert [op['seq'] for op in result['operations']] == [10, 15, 25, 30, 40]
    assert result['decisions'][0]['rule'] == 'ROUTE_ALTERNATIVE_SELECTED'
