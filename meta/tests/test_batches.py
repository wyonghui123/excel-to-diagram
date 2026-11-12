# -*- coding: utf-8 -*-
"""批次主数据 P4c 测试（spec §11.2 / §11.3 / §11.7）

覆盖:
  · YAML 声明：表名 / 字段 / 唯一索引 / 三组枚举 / 三态 UI 配置。
  · v196 迁移：临时库建依赖表 → migrate → verify；重复执行幂等；rollback 生效；
    唯一约束与 CHECK 真实生效。
  · BatchService：身份 / 数量与单位组 / 枚举 / 冻结不可关闭 / 日期 / 效价 /
    父批次自指·缺失·成环·超深 / 必填批次特性（对象级与物料分类级）。
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
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    base_uom INTEGER,
    item_group_id INTEGER
);
CREATE TABLE orgs (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT);
CREATE TABLE uoms (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT,
                   uom_group_id INTEGER);
CREATE TABLE item_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT);
CREATE TABLE attribute_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER DEFAULT 0,
    code TEXT,
    name TEXT,
    data_type TEXT DEFAULT 'string',
    multi_value_flag INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
);
CREATE TABLE attribute_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER DEFAULT 0,
    attribute_id INTEGER,
    scope_type TEXT,
    scope_ref TEXT,
    required_flag INTEGER DEFAULT 0,
    seq INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active'
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
CREATE TABLE menus (
    menu_code TEXT PRIMARY KEY,
    menu_name TEXT,
    menu_path TEXT,
    page_type TEXT,
    object_types TEXT,
    primary_object_type TEXT,
    bo_bindings TEXT,
    required_permissions TEXT,
    parent_menu TEXT,
    icon TEXT,
    color TEXT,
    description TEXT,
    sort_order INTEGER,
    is_active INTEGER DEFAULT 1,
    show_in_sidebar INTEGER DEFAULT 0,
    auto_generated INTEGER DEFAULT 0
);
CREATE TABLE menu_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code TEXT,
    menu_name TEXT,
    menu_path TEXT,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    parent_menu TEXT,
    icon TEXT,
    sort_order INTEGER,
    is_active INTEGER DEFAULT 1,
    data_permission_hint TEXT,
    UNIQUE (menu_code)
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


def _build_db(seed_master=True):
    conn = sqlite3.connect(':memory:')
    conn.executescript(BASE_SCHEMA)
    from meta.migrations import v196__batch_foundation as v196
    for _name, ddl in v196.TABLES:
        conn.execute(ddl)
    if seed_master:
        conn.executemany(
            'INSERT INTO uoms (id, code, uom_group_id) VALUES (?, ?, ?)',
            [(1, 'KG', 10), (2, 'G', 10), (3, 'L', 20)])
        conn.executemany(
            'INSERT INTO items (id, code, base_uom, item_group_id) VALUES (?, ?, ?, ?)',
            [(1, 'ITEM1', 1, 1), (2, 'ITEM2', 3, None)])
        conn.execute("INSERT INTO orgs (id, code) VALUES (1, 'PLANT1')")
        conn.execute("INSERT INTO item_groups (id, code) VALUES (1, 'FG')")
    return conn


def _batch_service(conn):
    from meta.services.batch_service import BatchService
    return BatchService(MemDS(conn))


def _payload(**kwargs):
    data = {
        'batch_no': 'B001',
        'item_id': 1,
        'org_id': 1,
        'qty': 10,
        'qty_uom_id': 1,
        'status': 'planned',
        'quality_status': 'unrestricted',
        'source': 'manual',
    }
    data.update(kwargs)
    return data


def _add_batch(conn, batch_id, batch_no, item_id=1, org_id=1,
               parent_batch_id=None, status='planned',
               quality_status='unrestricted'):
    conn.execute(
        'INSERT INTO batches (id, batch_no, item_id, org_id, qty, qty_uom_id, '
        'parent_batch_id, status, quality_status, source) '
        'VALUES (?, ?, ?, ?, 10, 1, ?, ?, ?, \'manual\')',
        [batch_id, batch_no, item_id, org_id, parent_batch_id,
         status, quality_status])


def _existing(conn, batch_id):
    rows = MemDS(conn).query(
        'SELECT * FROM batches WHERE id = ?', [batch_id])
    return rows[0] if rows else None


def _load_yaml(name):
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _field_ids(doc):
    return {field['id'] for field in doc['fields']}


def _index(doc, name):
    return next(item for item in doc['indexes'] if item.get('name') == name)


def _expect_rule(service, payload, rule, existing=None):
    from meta.services.batch_service import BatchError
    with pytest.raises(BatchError) as exc:
        service.validate_batch(payload, existing)
    assert exc.value.rule == rule
    return exc.value


# ---------------------------------------------------------------------------
# YAML 声明
# ---------------------------------------------------------------------------
def test_batch_schema_declared():
    doc = _load_yaml('batches.yaml')
    assert doc['id'] == 'batch'
    assert doc['table_name'] == 'batches'

    fields = _field_ids(doc)
    assert {'batch_no', 'item_id', 'org_id', 'qty', 'qty_uom_id',
            'parent_batch_id', 'status', 'quality_status', 'source',
            'produced_at', 'expiry_date', 'potency_pct', 'grade_code',
            'description'} <= fields

    status_field = next(f for f in doc['fields'] if f['id'] == 'status')
    assert {v['value'] for v in status_field['enum_values']} == {
        'planned', 'in_process', 'closed'}
    quality_field = next(f for f in doc['fields'] if f['id'] == 'quality_status')
    assert {v['value'] for v in quality_field['enum_values']} == {
        'unrestricted', 'inspection', 'blocked'}
    source_field = next(f for f in doc['fields'] if f['id'] == 'source')
    assert {v['value'] for v in source_field['enum_values']} == {
        'production', 'purchase', 'manual', 'adjustment'}

    unique = _index(doc, 'uq_batch_item_org_no')
    assert unique['unique'] is True
    assert unique['fields'] == ['item_id', 'org_id', 'batch_no']
    assert _index(doc, 'idx_batch_parent')['fields'] == ['parent_batch_id']
    grade = next(f for f in doc['fields'] if f['id'] == 'grade_code')
    assert grade['nullable'] is True
    assert grade['max_length'] == 20
    assert _index(doc, 'idx_batches_grade')['fields'] == ['item_id', 'grade_code']

    assert doc['ui_view_config']['skip_auto_menu'] is True
    assert {'list', 'form', 'detail'} <= set(doc['ui_view_config'])


def test_batch_value_schema_declared():
    doc = _load_yaml('batch_attribute_values.yaml')
    assert doc['id'] == 'batch_attribute_value'
    assert doc['table_name'] == 'batch_attribute_values'
    assert doc['parent_object'] == 'batch'

    assert {'tenant_id', 'batch_id', 'attribute_id', 'seq', 'description',
            'value_text', 'value_number', 'value_boolean', 'value_date',
            'value_datetime'} <= _field_ids(doc)

    unique = _index(doc, 'uidx_batch_attr_value')
    assert unique['unique'] is True
    assert unique['fields'] == ['tenant_id', 'batch_id', 'attribute_id', 'seq']
    assert _index(doc, 'idx_batch_attr_value_batch')['fields'] == [
        'tenant_id', 'batch_id']


# ---------------------------------------------------------------------------
# v196 迁移
# ---------------------------------------------------------------------------
@pytest.fixture()
def migrated_db(tmp_path):
    db_path = tmp_path / 'p4c.db'
    conn = sqlite3.connect(str(db_path))
    conn.executescript(BASE_SCHEMA)
    conn.executemany('INSERT INTO permission_sets (id, code, is_active) '
                     'VALUES (?, ?, 1)', [(1, 'admin'), (2, 'default')])
    conn.execute("INSERT INTO menus (menu_code, menu_name, menu_path, "
                 "sort_order) VALUES ('master-data', '主数据', '/master-data', 100)")
    conn.execute("INSERT INTO uoms (id, code, uom_group_id) VALUES (1, 'KG', 10)")
    conn.execute("INSERT INTO items (id, code, base_uom) VALUES (1, 'ITEM1', 1)")
    conn.execute("INSERT INTO orgs (id, code) VALUES (1, 'PLANT1')")
    conn.execute("INSERT INTO attribute_definitions (id, code, name) "
                 "VALUES (1, 'ATTR1', '属性1')")
    conn.commit()
    conn.close()
    return db_path


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def test_v196_migrate_verify_idempotent(migrated_db):
    from meta.migrations import v196__batch_foundation as v196

    assert v196.migrate(migrated_db, skip_backup=True) is True
    assert v196.verify(migrated_db) is True
    # 幂等：重复执行不报错、校验仍通过
    assert v196.migrate(migrated_db, skip_backup=True) is True
    assert v196.verify(migrated_db) is True


def test_v196_indexes_and_menu_real(migrated_db):
    from meta.migrations import v196__batch_foundation as v196
    v196.migrate(migrated_db, skip_backup=True)

    conn = sqlite3.connect(str(migrated_db))
    try:
        for _table, name, _sql in v196.INDEXES:
            assert conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (name,)).fetchone() is not None
        menu = conn.execute(
            'SELECT menu_path, parent_menu, primary_object_type, sort_order '
            'FROM menus WHERE menu_code=?', ('batch-management',)).fetchone()
        assert menu == ('/master-data/batch', 'master-data', 'batch', 104)
    finally:
        conn.close()


def test_batch_unique_and_check_constraints_real(migrated_db):
    from meta.migrations import v196__batch_foundation as v196
    v196.migrate(migrated_db, skip_backup=True)

    conn = sqlite3.connect(str(migrated_db))
    try:
        conn.execute(
            'INSERT INTO batches (batch_no, item_id, org_id, qty, qty_uom_id) '
            "VALUES ('B001', 1, 1, 10, 1)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO batches (batch_no, item_id, org_id, qty, qty_uom_id) '
                "VALUES ('B001', 1, 1, 10, 1)")
        # 换组织可复用同一批次号
        conn.execute(
            'INSERT INTO batches (batch_no, item_id, org_id, qty, qty_uom_id) '
            "VALUES ('B001', 1, 2, 10, 1)")
        # CHECK：数量必须 > 0
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO batches (batch_no, item_id, org_id, qty, qty_uom_id) '
                "VALUES ('B002', 1, 1, 0, 1)")
        # CHECK：效价 0–100
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO batches (batch_no, item_id, org_id, qty, qty_uom_id, '
                "potency_pct) VALUES ('B003', 1, 1, 10, 1, 120)")
        conn.execute(
            'INSERT INTO batches (batch_no, item_id, org_id, qty, qty_uom_id, '
            "potency_pct) VALUES ('B004', 1, 1, 10, 1, 98.5)")
    finally:
        conn.close()


def test_v196_rollback_drops_tables(migrated_db):
    from meta.migrations import v196__batch_foundation as v196
    v196.migrate(migrated_db, skip_backup=True)
    assert v196.rollback(migrated_db) is True

    conn = sqlite3.connect(str(migrated_db))
    try:
        assert not _table_exists(conn, 'batches')
        assert not _table_exists(conn, 'batch_attribute_values')
        assert conn.execute(
            'SELECT 1 FROM menus WHERE menu_code=?',
            ('batch-management',)).fetchone() is None
        assert conn.execute(
            'SELECT 1 FROM permissions WHERE code=?',
            ('batch:read',)).fetchone() is None
        # 枚举种子保留
        assert conn.execute(
            'SELECT 1 FROM enum_types WHERE id=?', ('batch_status',)).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# BatchService 规则
# ---------------------------------------------------------------------------
def test_valid_batch_passes():
    conn = _build_db()
    service = _batch_service(conn)
    merged = service.validate_batch(_payload())
    assert merged['status'] == 'planned'
    assert merged['quality_status'] == 'unrestricted'


def test_batch_no_required():
    conn = _build_db()
    _expect_rule(_batch_service(conn), _payload(batch_no='  '),
                 'BATCH_NO_REQUIRED')


def test_batch_item_and_org_required():
    conn = _build_db()
    _expect_rule(_batch_service(conn), _payload(item_id=None),
                 'BATCH_ITEM_REQUIRED')
    _expect_rule(_batch_service(conn), _payload(org_id=None),
                 'BATCH_ORG_REQUIRED')


def test_qty_must_be_positive():
    conn = _build_db()
    _expect_rule(_batch_service(conn), _payload(qty=0), 'BATCH_QTY_INVALID')
    _expect_rule(_batch_service(conn), _payload(qty=-3), 'BATCH_QTY_INVALID')


def test_uom_required_and_same_group():
    conn = _build_db()
    service = _batch_service(conn)
    _expect_rule(service, _payload(qty_uom_id=None), 'BATCH_UOM_REQUIRED')
    # 物料 1 基本单位 KG(组10)，L 属组 20 → 跨组拒绝
    _expect_rule(service, _payload(qty_uom_id=3), 'BATCH_UOM_GROUP')
    # 同组 G(组10) 允许
    assert service.validate_batch(_payload(qty_uom_id=2))['qty_uom_id'] == 2


def test_enum_values_converged():
    conn = _build_db()
    service = _batch_service(conn)
    _expect_rule(service, _payload(status='released'), 'BATCH_STATUS_INVALID')
    _expect_rule(service, _payload(quality_status='quarantine'),
                 'BATCH_QUALITY_STATUS_INVALID')
    _expect_rule(service, _payload(source='imported'), 'BATCH_SOURCE_INVALID')


def test_blocked_cannot_close():
    conn = _build_db()
    _expect_rule(_batch_service(conn),
                 _payload(quality_status='blocked', status='closed'),
                 'BATCH_BLOCKED_CANNOT_CLOSE')
    # 解冻后可关闭
    assert _batch_service(conn).validate_batch(
        _payload(quality_status='unrestricted', status='closed'))['status'] == 'closed'


def test_expiry_must_not_precede_produced():
    conn = _build_db()
    _expect_rule(_batch_service(conn),
                 _payload(produced_at='2026-11-10', expiry_date='2026-11-09'),
                 'BATCH_EXPIRY_INVALID')
    assert _batch_service(conn).validate_batch(
        _payload(produced_at='2026-11-10', expiry_date='2026-11-10'))


def test_potency_range():
    conn = _build_db()
    _expect_rule(_batch_service(conn), _payload(potency_pct=101),
                 'BATCH_POTENCY_INVALID')
    _expect_rule(_batch_service(conn), _payload(potency_pct=-1),
                 'BATCH_POTENCY_INVALID')
    assert _batch_service(conn).validate_batch(_payload(potency_pct=0))
    assert _batch_service(conn).validate_batch(_payload(potency_pct=100))


def test_parent_self_reference_rejected():
    conn = _build_db()
    _add_batch(conn, 5, 'B005')
    existing = _existing(conn, 5)
    _expect_rule(_batch_service(conn), {'parent_batch_id': 5},
                 'BATCH_PARENT_SELF', existing)


def test_parent_missing_rejected():
    conn = _build_db()
    _expect_rule(_batch_service(conn), _payload(parent_batch_id=99),
                 'BATCH_PARENT_MISSING')


def test_parent_cycle_rejected():
    conn = _build_db()
    _add_batch(conn, 1, 'B001', parent_batch_id=2)
    _add_batch(conn, 2, 'B002', parent_batch_id=1)
    existing = _existing(conn, 1)
    _expect_rule(_batch_service(conn), {'parent_batch_id': 2},
                 'BATCH_PARENT_CYCLE', existing)


def test_parent_depth_capped():
    conn = _build_db()
    # 1→2→…→12，共 11 步，超过上限 10
    for index in range(1, 13):
        parent = index + 1 if index < 12 else None
        _add_batch(conn, index, 'B%03d' % index, parent_batch_id=parent)
    existing = _existing(conn, 1)
    _expect_rule(_batch_service(conn), {'parent_batch_id': 2},
                 'BATCH_PARENT_CYCLE', existing)


def _seed_required_scope(conn, scope_type, scope_ref):
    conn.execute(
        "INSERT INTO attribute_definitions (id, tenant_id, code, name, "
        "data_type, status) VALUES (1, 0, 'COLOR', '颜色', 'string', 'active')")
    conn.execute(
        'INSERT INTO attribute_scopes (tenant_id, attribute_id, scope_type, '
        'scope_ref, required_flag, seq, status) '
        "VALUES (0, 1, ?, ?, 1, 1, 'active')", (scope_type, scope_ref))


def test_required_batch_attribute_missing_on_update():
    conn = _build_db()
    _seed_required_scope(conn, 'object', 'batch')
    _add_batch(conn, 7, 'B007')
    existing = _existing(conn, 7)
    _expect_rule(_batch_service(conn), {'description': '备注'},
                 'BATCH_REQUIRED_ATTRIBUTE_MISSING', existing)

    conn.execute(
        "INSERT INTO batch_attribute_values (tenant_id, batch_id, attribute_id, "
        "seq, value_text) VALUES (0, 7, 1, 1, '红色')")
    assert _batch_service(conn).validate_batch(
        {'description': '备注'}, existing)['description'] == '备注'


def test_required_batch_attribute_by_item_group():
    conn = _build_db()
    _seed_required_scope(conn, 'item_group', 'FG')
    _add_batch(conn, 8, 'B008')
    existing = _existing(conn, 8)
    _expect_rule(_batch_service(conn), {'description': '备注'},
                 'BATCH_REQUIRED_ATTRIBUTE_MISSING', existing)


def test_create_skips_required_attribute_check():
    """创建时无 batch_id，必填特性校验不可能成立，明确跳过。"""
    conn = _build_db()
    _seed_required_scope(conn, 'object', 'batch')
    assert _batch_service(conn).validate_batch(_payload())['batch_no'] == 'B001'
