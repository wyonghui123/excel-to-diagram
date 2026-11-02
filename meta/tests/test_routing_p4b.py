# -*- coding: utf-8 -*-
"""统一资源模型 P4b 测试（spec-routing-process-manufacturing-benchmark §10）

覆盖:
  · YAML 声明：recipe 枚举 / 5 列 / 索引；工序产出与过程指令的表 / 索引 / 枚举。
  · v191 / v192 迁移：临时库建依赖表 → migrate → verify；唯一约束与部分唯一索引
    真实生效；重复执行幂等；rollback 生效。
  · WorkDefinitionService：配方基准、routing 基准列禁填、单位组、有效期、类型/基准
    冻结、主产出唯一、成本分摊、计划量缩放、替代包一致性。
  · ProcessInstructionService：text / parameter 字段矩阵、numeric 区间、绑定资源类型。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pathlib
import sqlite3

import pytest
import yaml

pytestmark = pytest.mark.unit

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / 'schemas'

BASE_SCHEMA = """
CREATE TABLE work_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    definition_kind TEXT DEFAULT 'routing',
    item_id INTEGER,
    revision TEXT,
    status TEXT DEFAULT 'draft',
    org_id INTEGER,
    base_qty REAL,
    base_uom_id INTEGER,
    batch_qty REAL,
    valid_from TEXT,
    valid_to TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE work_definition_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    definition_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    operation_name TEXT,
    qty_per REAL DEFAULT 1,
    status TEXT DEFAULT 'draft',
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, base_uom INTEGER);
CREATE TABLE uoms (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, uom_group_id INTEGER);
CREATE TABLE resources (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, resource_kind TEXT);
CREATE TABLE resource_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT);
CREATE TABLE work_definition_operation_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL,
    output_type TEXT NOT NULL DEFAULT 'product',
    item_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    qty_uom_id INTEGER,
    is_primary INTEGER NOT NULL DEFAULT 0,
    cost_allocation_pct REAL,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE operation_resource_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL,
    role TEXT,
    qty REAL,
    required_skill_id INTEGER,
    min_level INTEGER,
    is_primary INTEGER DEFAULT 0,
    priority INTEGER DEFAULT 1,
    resource_id INTEGER,
    resource_group_id INTEGER,
    substitute_group TEXT,
    replacement_group TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE enum_types (
    id TEXT PRIMARY KEY,
    name TEXT,
    category TEXT,
    mutability TEXT,
    dimension_schema TEXT,
    description TEXT,
    created_at TEXT
);
CREATE TABLE enum_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enum_type_id TEXT,
    code TEXT,
    name TEXT,
    name_en TEXT,
    sort_order INTEGER,
    is_active INTEGER,
    is_system INTEGER,
    created_at TEXT
);
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    name TEXT,
    resource_type TEXT,
    action TEXT
);
CREATE TABLE permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE permission_set_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER,
    permission_code TEXT,
    permission_id INTEGER,
    granted INTEGER,
    created_at TEXT
);
"""


class MemDS:
    """sqlite3 连接 → DataSource 形状。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


def _build(seed_master=True):
    conn = sqlite3.connect(':memory:')
    conn.executescript(BASE_SCHEMA)
    if seed_master:
        conn.executemany(
            'INSERT INTO uoms (id, code, uom_group_id) VALUES (?, ?, ?)',
            [(1, 'KG', 10), (2, 'G', 10), (3, 'L', 20)])
        conn.executemany(
            'INSERT INTO items (id, code, base_uom) VALUES (?, ?, ?)',
            [(1, 'ITEM1', 1), (2, 'ITEM2', 3)])
        conn.executemany(
            'INSERT INTO resources (id, code, resource_kind) VALUES (?, ?, ?)',
            [(1, 'M1', 'machine'), (2, 'P1', 'person'),
             (3, 'F1', 'facility'), (4, 'T1', 'tool')])
        conn.execute("INSERT INTO resource_groups (id, code) VALUES (1, 'GRP1')")
    return conn


def _wd_service(conn):
    from meta.services.work_definition_service import WorkDefinitionService
    return WorkDefinitionService(MemDS(conn))


def _pi_service(conn):
    from meta.services.process_instruction_service import ProcessInstructionService
    return ProcessInstructionService(MemDS(conn))


def _add_definition(conn, did, kind='recipe', item_id=1, base_qty=None,
                    base_uom_id=None, status='draft'):
    conn.execute(
        'INSERT INTO work_definitions (id, definition_kind, item_id, base_qty, '
        'base_uom_id, status) VALUES (?, ?, ?, ?, ?, ?)',
        [did, kind, item_id, base_qty, base_uom_id, status])


def _add_operation(conn, oid, definition_id, seq=10, qty_per=1):
    conn.execute(
        'INSERT INTO work_definition_operations (id, definition_id, seq, '
        'operation_name, qty_per) VALUES (?, ?, ?, ?, ?)',
        [oid, definition_id, seq, 'OP%d' % oid, qty_per])


def _load_yaml(name):
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _field_ids(doc):
    return {field['id'] for field in doc['fields']}


def _index(doc, name):
    return next(item for item in doc['indexes'] if item.get('name') == name)


# ---------------------------------------------------------------------------
# YAML 声明
# ---------------------------------------------------------------------------
def test_work_definition_recipe_columns_declared():
    doc = _load_yaml('work_definition.yaml')
    fields = {field['id']: field for field in doc['fields']}

    values = {item['value'] for item in fields['definition_kind']['enum_values']}
    assert {'routing', 'recipe', 'service_template'} <= values

    for name in ('base_qty', 'base_uom_id', 'batch_qty', 'valid_from', 'valid_to'):
        assert name in fields
    assert _index(doc, 'idx_work_definition_validity')['fields'] == [
        'valid_from', 'valid_to']
    assert _index(doc, 'idx_work_definition_base_uom')['fields'] == ['base_uom_id']


def test_operation_output_schema_declared():
    doc = _load_yaml('work_definition_operation_output.yaml')
    assert doc['table_name'] == 'work_definition_operation_outputs'
    assert {'operation_id', 'output_type', 'item_id', 'qty', 'qty_uom_id',
            'is_primary', 'cost_allocation_pct'} <= _field_ids(doc)

    values = {item['value'] for item in
              next(f for f in doc['fields'] if f['id'] == 'output_type')['enum_values']}
    assert values == {'product', 'co_product', 'by_product'}

    assert _index(doc, 'uq_work_definition_output_operation_item')['unique'] is True
    primary = _index(doc, 'uq_work_definition_output_primary')
    assert primary['type'] == 'partial'
    assert primary['condition'] == 'is_primary = 1'


def test_requirement_substitute_columns_declared():
    doc = _load_yaml('operation_resource_requirement.yaml')
    assert {'substitute_group', 'replacement_group'} <= _field_ids(doc)
    assert _index(doc, 'idx_operation_resource_requirement_substitute')['fields'] == [
        'operation_id', 'substitute_group']


def test_process_instruction_schema_declared():
    doc = _load_yaml('process_instruction.yaml')
    assert doc['table_name'] == 'process_instructions'
    assert {'operation_id', 'seq', 'instruction_kind', 'title', 'content',
            'parameter_code', 'parameter_name', 'data_type', 'uom_id',
            'target_value', 'min_value', 'max_value', 'direction',
            'resource_id'} <= _field_ids(doc)

    parameter = _index(doc, 'uq_process_instruction_parameter')
    assert parameter['type'] == 'partial'
    assert parameter['condition'] == 'parameter_code IS NOT NULL'
    assert _index(doc, 'uq_process_instruction_seq')['unique'] is True


# ---------------------------------------------------------------------------
# v191 / v192 迁移
# ---------------------------------------------------------------------------
@pytest.fixture()
def migrated_db(tmp_path):
    db_path = tmp_path / 'p4b.db'
    conn = sqlite3.connect(str(db_path))
    conn.executescript(BASE_SCHEMA)
    conn.executemany('INSERT INTO permission_sets (id, code, is_active) '
                     'VALUES (?, ?, 1)', [(1, 'admin'), (2, 'default')])
    conn.executemany(
        'INSERT INTO uoms (id, code, uom_group_id) VALUES (?, ?, ?)',
        [(1, 'KG', 10), (2, 'G', 10)])
    conn.execute("INSERT INTO items (id, code, base_uom) VALUES (1, 'ITEM1', 1)")
    conn.commit()
    conn.close()
    return db_path


def test_migrations_migrate_verify_and_idempotent(migrated_db):
    from meta.migrations import v191__routing_p4b_1 as v191
    from meta.migrations import v192__routing_p4b_2 as v192

    assert v191.migrate(migrated_db, skip_backup=True) is True
    assert v191.verify(migrated_db) is True
    assert v192.migrate(migrated_db, skip_backup=True) is True
    assert v192.verify(migrated_db) is True

    # 幂等：重复执行不报错
    assert v191.migrate(migrated_db, skip_backup=True) is True
    assert v192.migrate(migrated_db, skip_backup=True) is True


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def test_output_unique_constraints_real(migrated_db):
    from meta.migrations import v191__routing_p4b_1 as v191
    v191.migrate(migrated_db, skip_backup=True)

    conn = sqlite3.connect(str(migrated_db))
    try:
        conn.execute(
            'INSERT INTO work_definition_operations (id, definition_id, seq, '
            'operation_name) VALUES (1, 1, 10, \'OP1\')')
        conn.execute(
            "INSERT INTO work_definition_operation_outputs "
            "(operation_id, output_type, item_id, qty, is_primary) "
            "VALUES (1, 'product', 1, 10, 1)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO work_definition_operation_outputs "
                "(operation_id, output_type, item_id, qty, is_primary) "
                "VALUES (1, 'product', 1, 5, 0)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO work_definition_operation_outputs "
                "(operation_id, output_type, item_id, qty, is_primary) "
                "VALUES (1, 'co_product', 2, 5, 1)")
        # 非主产出的多条允许
        conn.execute(
            "INSERT INTO work_definition_operation_outputs "
            "(operation_id, output_type, item_id, qty, is_primary) "
            "VALUES (1, 'co_product', 2, 5, 0)")
    finally:
        conn.close()


def test_instruction_unique_constraints_real(migrated_db):
    from meta.migrations import v192__routing_p4b_2 as v192
    v192.migrate(migrated_db, skip_backup=True)

    conn = sqlite3.connect(str(migrated_db))
    try:
        conn.execute(
            'INSERT INTO process_instructions '
            '(operation_id, seq, instruction_kind, title) '
            "VALUES (1, 1, 'text', 'T1')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO process_instructions '
                '(operation_id, seq, instruction_kind, title) '
                "VALUES (1, 1, 'text', 'T2')")

        conn.execute(
            'INSERT INTO process_instructions '
            '(operation_id, seq, instruction_kind, parameter_code) '
            "VALUES (1, 2, 'parameter', 'TEMP')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO process_instructions '
                '(operation_id, seq, instruction_kind, parameter_code) '
                "VALUES (1, 3, 'parameter', 'TEMP')")

        # parameter_code 为 NULL 不受部分唯一索引约束
        conn.execute(
            'INSERT INTO process_instructions '
            '(operation_id, seq, instruction_kind, title) '
            "VALUES (1, 4, 'text', 'T3')")
        conn.execute(
            'INSERT INTO process_instructions '
            '(operation_id, seq, instruction_kind, title) '
            "VALUES (1, 5, 'text', 'T4')")
    finally:
        conn.close()


def test_rollback_drops_tables(migrated_db):
    from meta.migrations import v191__routing_p4b_1 as v191
    from meta.migrations import v192__routing_p4b_2 as v192

    v191.migrate(migrated_db, skip_backup=True)
    v192.migrate(migrated_db, skip_backup=True)
    assert v192.rollback(migrated_db) is True
    assert v191.rollback(migrated_db) is True

    conn = sqlite3.connect(str(migrated_db))
    try:
        assert not _table_exists(conn, 'process_instructions')
        assert not _table_exists(conn, 'work_definition_operation_outputs')
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# WorkDefinitionService：配方基准
# ---------------------------------------------------------------------------
def test_recipe_base_valid():
    conn = _build()
    merged = _wd_service(conn).validate_definition({
        'definition_kind': 'recipe', 'item_id': 1,
        'base_qty': 10, 'base_uom_id': 2})
    assert merged['base_qty'] == 10


def test_recipe_requires_item():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_definition({
            'definition_kind': 'recipe', 'base_qty': 10, 'base_uom_id': 2})
    assert exc.value.rule == 'WD_RECIPE_ITEM_REQUIRED'


def test_recipe_base_qty_must_be_positive():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_definition({
            'definition_kind': 'recipe', 'item_id': 1,
            'base_qty': 0, 'base_uom_id': 2})
    assert exc.value.rule == 'WD_BASE_QTY_INVALID'


def test_recipe_base_uom_group_mismatch():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_definition({
            'definition_kind': 'recipe', 'item_id': 1,
            'base_qty': 10, 'base_uom_id': 3})
    assert exc.value.rule == 'WD_BASE_UOM_GROUP'


def test_routing_must_not_fill_base_columns():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_definition({
            'definition_kind': 'routing', 'item_id': 1, 'base_qty': 10})
    assert exc.value.rule == 'WD_BASE_NOT_ALLOWED'


def test_validity_end_must_be_after_start():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_definition({
            'definition_kind': 'routing', 'item_id': 1,
            'valid_from': '2026-11-01', 'valid_to': '2026-11-01'})
    assert exc.value.rule == 'WD_VALIDITY_INVALID'


def test_kind_immutable_after_operations():
    conn = _build()
    _add_definition(conn, 1, kind='routing', item_id=1)
    _add_operation(conn, 11, 1)
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_definition(
            {'definition_kind': 'recipe', 'base_qty': 10, 'base_uom_id': 2},
            {'id': 1, 'definition_kind': 'routing', 'status': 'draft'})
    assert exc.value.rule == 'WD_KIND_IMMUTABLE'


def test_recipe_base_frozen_after_operations():
    conn = _build()
    _add_definition(conn, 1, kind='recipe', item_id=1,
                    base_qty=10, base_uom_id=2)
    _add_operation(conn, 11, 1)
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_definition(
            {'base_qty': 20},
            {'id': 1, 'definition_kind': 'recipe', 'status': 'draft',
             'base_qty': 10, 'base_uom_id': 2})
    assert exc.value.rule == 'WD_BASE_IMMUTABLE'


def test_active_recipe_requires_primary_output():
    conn = _build()
    _add_definition(conn, 1, kind='recipe', item_id=1,
                    base_qty=10, base_uom_id=2, status='draft')
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_definition(
            {'status': 'active'},
            {'id': 1, 'definition_kind': 'recipe', 'status': 'draft',
             'item_id': 1, 'base_qty': 10, 'base_uom_id': 2})
    assert exc.value.rule == 'WD_RECIPE_PRIMARY_REQUIRED'


# ---------------------------------------------------------------------------
# WorkDefinitionService：工序产出
# ---------------------------------------------------------------------------
def test_output_primary_must_be_product():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_operation_outputs(11, {
            'operation_id': 11, 'output_type': 'co_product',
            'item_id': 1, 'qty': 5, 'is_primary': True})
    assert exc.value.rule == 'WD_OUTPUT_PRIMARY_TYPE'


def test_output_at_most_one_primary():
    conn = _build()
    conn.execute(
        'INSERT INTO work_definition_operation_outputs '
        '(operation_id, output_type, item_id, qty, is_primary) '
        "VALUES (11, 'product', 1, 10, 1)")
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_operation_outputs(11, {
            'operation_id': 11, 'output_type': 'product',
            'item_id': 2, 'qty': 5, 'is_primary': True})
    assert exc.value.rule == 'WD_OUTPUT_PRIMARY_DUPLICATE'


def test_output_duplicate_item_rejected():
    conn = _build()
    conn.execute(
        'INSERT INTO work_definition_operation_outputs '
        '(operation_id, output_type, item_id, qty, is_primary) '
        "VALUES (11, 'co_product', 1, 5, 0)")
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_operation_outputs(11, {
            'operation_id': 11, 'output_type': 'by_product',
            'item_id': 1, 'qty': 2})
    assert exc.value.rule == 'WD_OUTPUT_ITEM_DUPLICATE'


def test_output_allocation_total_capped():
    conn = _build()
    conn.execute(
        'INSERT INTO work_definition_operation_outputs '
        '(operation_id, output_type, item_id, qty, is_primary, cost_allocation_pct) '
        "VALUES (11, 'co_product', 1, 5, 0, 60)")
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_operation_outputs(11, {
            'operation_id': 11, 'output_type': 'by_product',
            'item_id': 2, 'qty': 5, 'cost_allocation_pct': 50})
    # 库内已有 60，本次再 50，合计 110 触发上限
    assert exc.value.rule == 'WD_OUTPUT_ALLOC_TOTAL'


def test_output_allocation_not_allowed_on_product():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_operation_outputs(11, {
            'operation_id': 11, 'output_type': 'product',
            'item_id': 1, 'qty': 5, 'cost_allocation_pct': 10})
    assert exc.value.rule == 'WD_OUTPUT_ALLOC_NOT_ALLOWED'


def test_output_qty_must_be_positive():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_operation_outputs(11, {
            'operation_id': 11, 'output_type': 'product',
            'item_id': 1, 'qty': 0})
    assert exc.value.rule == 'WD_OUTPUT_QTY_INVALID'


def test_output_uom_group_mismatch():
    conn = _build()
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_operation_outputs(11, {
            'operation_id': 11, 'output_type': 'product',
            'item_id': 1, 'qty': 5, 'qty_uom_id': 3})
    assert exc.value.rule == 'WD_OUTPUT_UOM_GROUP'


# ---------------------------------------------------------------------------
# WorkDefinitionService：计划量缩放
# ---------------------------------------------------------------------------
def test_scale_outputs_recipe_factor():
    conn = _build()
    _add_definition(conn, 1, kind='recipe', item_id=1,
                    base_qty=10, base_uom_id=2)
    _add_operation(conn, 11, 1, seq=10, qty_per=2)
    conn.execute(
        'INSERT INTO work_definition_operation_outputs '
        '(operation_id, output_type, item_id, qty, qty_uom_id, is_primary) '
        "VALUES (11, 'product', 1, 5, 2, 1)")

    rows = _wd_service(conn).scale_operation_outputs(1, 30)
    assert len(rows) == 1
    assert rows[0]['qty'] == pytest.approx(30.0)  # 5 * (30/10) * 2


def test_scale_outputs_routing_base_is_one():
    conn = _build()
    _add_definition(conn, 2, kind='routing', item_id=1)
    _add_operation(conn, 12, 2, seq=10, qty_per=1)
    conn.execute(
        'INSERT INTO work_definition_operation_outputs '
        '(operation_id, output_type, item_id, qty, qty_uom_id, is_primary) '
        "VALUES (12, 'product', 1, 5, 2, 1)")

    rows = _wd_service(conn).scale_operation_outputs(2, 30)
    assert rows[0]['qty'] == pytest.approx(150.0)  # 5 * 30 * 1


# ---------------------------------------------------------------------------
# WorkDefinitionService：替代资源组
# ---------------------------------------------------------------------------
def _requirement(conn, rid, role='machine', qty=1, primary=0, priority=1,
                 substitute=None, replacement=None, resource_id=None,
                 group_id=None):
    conn.execute(
        'INSERT INTO operation_resource_requirements '
        '(id, operation_id, role, qty, is_primary, priority, substitute_group, '
        'replacement_group, resource_id, resource_group_id) '
        'VALUES (?, 11, ?, ?, ?, ?, ?, ?, ?, ?)',
        [rid, role, qty, primary, priority, substitute, replacement,
         resource_id, group_id])


def test_replacement_requires_substitute_group():
    conn = _build()
    _requirement(conn, 1, replacement='PKG-A', resource_id=1)
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_substitute_groups(11)
    assert exc.value.rule == 'WD_SUBSTITUTE_GROUP_REQUIRED'


def test_package_fields_must_match():
    conn = _build()
    _requirement(conn, 1, role='machine', qty=1, substitute='S1',
                 replacement='PKG-A', resource_id=1)
    _requirement(conn, 2, role='machine', qty=2, substitute='S1',
                 replacement='PKG-A', resource_id=3)
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_substitute_groups(11)
    assert exc.value.rule == 'WD_SUBSTITUTE_PACKAGE_MISMATCH'
    assert exc.value.field_name == 'qty'


def test_single_package_warns_on_save():
    conn = _build()
    _requirement(conn, 1, role='machine', qty=1, primary=1, substitute='S1',
                 replacement='PKG-A', resource_id=1)
    warnings = _wd_service(conn).validate_substitute_groups(11, active=False)
    assert len(warnings) == 1
    assert '至少需要 2 个' in warnings[0]


def test_single_package_blocks_on_active():
    conn = _build()
    _requirement(conn, 1, role='machine', qty=1, primary=1, substitute='S1',
                 replacement='PKG-A', resource_id=1)
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_substitute_groups(11, active=True)
    assert exc.value.rule == 'WD_SUBSTITUTE_PACKAGES'


def test_two_packages_pass():
    conn = _build()
    _requirement(conn, 1, role='machine', qty=1, primary=1, substitute='S1',
                 replacement='PKG-A', resource_id=1)
    _requirement(conn, 2, role='machine', qty=1, primary=0, substitute='S1',
                 replacement='PKG-B', resource_id=3)
    assert _wd_service(conn).validate_substitute_groups(11, active=True) == []


def test_primary_duplicate_within_group_rejected():
    conn = _build()
    _requirement(conn, 1, role='machine', qty=1, primary=1, substitute='S1',
                 replacement='PKG-A', resource_id=1)
    _requirement(conn, 2, role='machine', qty=1, primary=1, substitute='S1',
                 replacement='PKG-B', resource_id=3)
    from meta.services.work_definition_service import WorkDefinitionError
    with pytest.raises(WorkDefinitionError) as exc:
        _wd_service(conn).validate_substitute_groups(11)
    assert exc.value.rule == 'WD_SUBSTITUTE_PRIMARY_DUPLICATE'


def test_resolve_substitute_options_ordered_and_satisfiable():
    conn = _build()
    _requirement(conn, 1, role='machine', qty=1, primary=0, priority=2,
                 substitute='S1', replacement='PKG-B', resource_id=3)
    _requirement(conn, 2, role='machine', qty=1, primary=0, priority=1,
                 substitute='S1', replacement='PKG-A', resource_id=1)
    _requirement(conn, 3, role='machine', qty=1, primary=0, priority=3,
                 substitute='S1', replacement='PKG-C', resource_id=99)

    options = _wd_service(conn).resolve_substitute_options(11)
    assert [item['replacement_group'] for item in options] == [
        'PKG-A', 'PKG-B', 'PKG-C']
    assert [item['satisfiable'] for item in options] == [True, True, False]


# ---------------------------------------------------------------------------
# ProcessInstructionService
# ---------------------------------------------------------------------------
def test_text_instruction_valid():
    conn = _build()
    result = _pi_service(conn).validate({
        'operation_id': 11, 'instruction_kind': 'text', 'seq': 1,
        'title': '开机检查', 'content': '确认气源压力'})
    assert result['instruction_kind'] == 'text'


def test_text_requires_content():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'text', 'title': 'T'})
    assert exc.value.rule == 'PI_TEXT_CONTENT_REQUIRED'


def test_text_rejects_parameter_fields():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'text',
            'title': 'T', 'content': 'C', 'parameter_code': 'TEMP'})
    assert exc.value.rule == 'PI_TEXT_PARAMETER_NOT_ALLOWED'


def test_parameter_requires_fields():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'parameter',
            'parameter_code': 'TEMP', 'data_type': 'numeric',
            'direction': 'set'})
    assert exc.value.rule == 'PI_PARAMETER_FIELD_REQUIRED'
    assert exc.value.field_name == 'parameter_name'


def test_parameter_rejects_text_fields():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'parameter',
            'parameter_code': 'TEMP', 'parameter_name': '温度',
            'data_type': 'numeric', 'direction': 'set',
            'target_value': '80', 'title': 'T'})
    assert exc.value.rule == 'PI_PARAMETER_TEXT_NOT_ALLOWED'


def test_set_direction_requires_target():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'parameter',
            'parameter_code': 'TEMP', 'parameter_name': '温度',
            'data_type': 'numeric', 'direction': 'set'})
    assert exc.value.rule == 'PI_TARGET_REQUIRED'


def test_collect_direction_allows_empty_target():
    conn = _build()
    result = _pi_service(conn).validate({
        'operation_id': 11, 'instruction_kind': 'parameter',
        'parameter_code': 'TEMP', 'parameter_name': '温度',
        'data_type': 'numeric', 'direction': 'collect'})
    assert result['direction'] == 'collect'


def test_numeric_target_must_parse():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'parameter',
            'parameter_code': 'TEMP', 'parameter_name': '温度',
            'data_type': 'numeric', 'direction': 'set',
            'target_value': 'abc'})
    assert exc.value.rule == 'PI_TARGET_INVALID'


def test_numeric_range_invalid():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'parameter',
            'parameter_code': 'TEMP', 'parameter_name': '温度',
            'data_type': 'numeric', 'direction': 'set',
            'target_value': '80', 'min_value': '90', 'max_value': '100'})
    assert exc.value.rule == 'PI_TARGET_OUT_OF_RANGE'


def test_numeric_min_greater_than_max():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'parameter',
            'parameter_code': 'TEMP', 'parameter_name': '温度',
            'data_type': 'numeric', 'direction': 'set',
            'target_value': '80', 'min_value': '100', 'max_value': '90'})
    assert exc.value.rule == 'PI_RANGE_INVALID'


def test_uom_only_for_numeric():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'parameter',
            'parameter_code': 'COLOR', 'parameter_name': '颜色',
            'data_type': 'text', 'direction': 'set',
            'target_value': 'red', 'uom_id': 1})
    assert exc.value.rule == 'PI_UOM_NOT_ALLOWED'


def test_resource_kind_restricted():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'text', 'seq': 1,
            'title': 'T', 'content': 'C', 'resource_id': 2})
    assert exc.value.rule == 'PI_RESOURCE_KIND'


def test_resource_missing_rejected():
    conn = _build()
    from meta.services.process_instruction_service import ProcessInstructionError
    with pytest.raises(ProcessInstructionError) as exc:
        _pi_service(conn).validate({
            'operation_id': 11, 'instruction_kind': 'text', 'seq': 1,
            'title': 'T', 'content': 'C', 'resource_id': 99})
    assert exc.value.rule == 'PI_RESOURCE_NOT_FOUND'


def test_machine_resource_allowed():
    conn = _build()
    result = _pi_service(conn).validate({
        'operation_id': 11, 'instruction_kind': 'parameter',
        'parameter_code': 'TEMP', 'parameter_name': '温度',
        'data_type': 'numeric', 'direction': 'set', 'target_value': '80',
        'resource_id': 1})
    assert result['resource_id'] == 1
