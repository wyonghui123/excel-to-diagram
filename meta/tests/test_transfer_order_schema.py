# -*- coding: utf-8 -*-
"""调拨单元数据测试（spec-transfer-order-object-model §3 / §4）

覆盖：
  · YAML 可被注册表加载，头 / 行表名与父子关系；
  · 行 UNIQUE(transfer_order_id, line_no) / 10-20-30 行号口径声明；
  · v190 迁移种子：TRF_STD / TRF_GOODS / TRF 序列与绑定；
  · 迁移建表后的 UNIQUE 约束真实生效（不读生产 architecture.db）。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pathlib
import sqlite3

import pytest
import yaml

pytestmark = pytest.mark.unit

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / 'schemas'

BASE_TABLES = """
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    scope_bo TEXT,
    level TEXT,
    document_category TEXT,
    line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1,
    number_sequence_id INTEGER,
    default_type_id INTEGER,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE number_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    pattern TEXT,
    scope_fields TEXT,
    date_field TEXT,
    start_value INTEGER,
    on_exhaust TEXT,
    preview TEXT,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE orgs (id INTEGER PRIMARY KEY);
CREATE TABLE items (id INTEGER PRIMARY KEY);
CREATE TABLE uoms (id INTEGER PRIMARY KEY);
CREATE TABLE locations (id INTEGER PRIMARY KEY, org_id INTEGER);
CREATE TABLE projects (id INTEGER PRIMARY KEY);
"""


def _load(name):
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _fields(doc):
    return {f['id']: f for f in doc['fields']}


def _index(doc, name):
    return next(i for i in doc['indexes'] if i.get('name') == name)


@pytest.fixture(scope='module')
def transfer_doc():
    return _load('transfer_order.yaml')


@pytest.fixture(scope='module')
def line_doc():
    return _load('transfer_order_line.yaml')


@pytest.fixture(scope='module')
def registered_objects():
    from meta.tests._yaml_driver.loader import load_schemas
    return load_schemas()


# ---------------------------------------------------------------------------
# YAML 声明
# ---------------------------------------------------------------------------
def test_yaml_registered_as_meta_objects(registered_objects):
    header = registered_objects['transfer_order']
    line = registered_objects['transfer_order_line']

    assert header.table_name == 'transfer_orders'
    assert line.table_name == 'transfer_order_lines'
    assert line.parent_object == 'transfer_order'
    assert header.display_name_field == 'transfer_order_no'


def test_header_fields_complete(transfer_doc):
    expected = {
        'id', 'transfer_order_no', 'transfer_date', 'status',
        'fulfillment_status', 'from_org_id', 'to_org_id', 'legal_entity_id',
        'from_location_id', 'to_location_id', 'project_id', 'actual_ship_date',
        'carrier_name', 'waybill_no', 'remark', 'created_at', 'updated_at',
    }
    assert expected <= set(_fields(transfer_doc))
    # document_type_id 由 document_type_aspect 提供，不在 fields 显式声明
    assert 'document_type_id' not in _fields(transfer_doc)


def test_header_status_enum(transfer_doc):
    field = _fields(transfer_doc)['status']
    assert {item['value'] for item in field['enum_values']} == {
        'draft', 'released', 'closed', 'cancelled', 'reversed'}
    assert field['default'] == 'draft'


def test_header_fulfillment_enum(transfer_doc):
    field = _fields(transfer_doc)['fulfillment_status']
    assert {item['value'] for item in field['enum_values']} == {
        'open', 'partially_shipped', 'shipped', 'partially_received', 'received'}


def test_line_parent_hierarchy_and_fields(line_doc):
    assert line_doc['parent_object'] == 'transfer_order'
    assert line_doc['hierarchy'] == {'enabled': True,
                                     'parent_field': 'transfer_order_id'}
    expected = {
        'id', 'transfer_order_id', 'line_no', 'line_type_id', 'item_id',
        'uom_id', 'qty', 'qty_shipped', 'qty_received', 'status',
        'fulfillment_status', 'remark', 'created_at', 'updated_at',
    }
    assert expected <= set(_fields(line_doc))


def test_line_unique_index_on_order_and_line_no(line_doc):
    index = _index(line_doc, 'uidx_transfer_order_line_no')
    assert index['fields'] == ['transfer_order_id', 'line_no']
    assert index['unique'] is True

    registered = _load('transfer_order_line.yaml')
    assert registered['indexes'][0]['name'] == 'uidx_transfer_order_line_no'


def test_header_business_key_unique(transfer_doc):
    index = _index(transfer_doc, 'uidx_transfer_order_no')
    assert index['fields'] == ['transfer_order_no']
    assert index['unique'] is True


def test_deletion_policies(transfer_doc, line_doc):
    assert transfer_doc['deletion_policy']['mode'] == 'restrict'
    assert transfer_doc['deletion_policy']['cascade_delete'] == [
        'transfer_order_lines']
    assert line_doc['deletion_policy']['mode'] == 'cascade'


def test_line_skips_auto_menu(line_doc):
    assert line_doc['ui_view_config']['skip_auto_menu'] is True


def test_header_has_child_section(transfer_doc):
    children = transfer_doc['ui_view_config'].get('child_sections') or []
    assert [c['child_object'] for c in children] == ['transfer_order_line']


# ---------------------------------------------------------------------------
# v190 迁移
# ---------------------------------------------------------------------------
def _base_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(BASE_TABLES)
    conn.commit()
    conn.close()


@pytest.fixture()
def migrated_db(tmp_path):
    from meta.migrations import v190__transfer_order_object as v190
    db_path = tmp_path / 'meta.db'
    _base_db(db_path)
    assert v190.migrate(db_path) is True
    assert v190.verify(db_path) is True
    return db_path


def test_migration_seeds_header_and_line_types(migrated_db):
    conn = sqlite3.connect(str(migrated_db))
    try:
        header = conn.execute(
            "SELECT id, scope_bo, level, document_category, number_sequence_id, "
            "default_type_id, status FROM type_definitions WHERE code = 'TRF_STD'"
        ).fetchone()
        goods = conn.execute(
            "SELECT id, scope_bo, level, line_category, delivery_relevant, "
            "status FROM type_definitions WHERE code = 'TRF_GOODS'"
        ).fetchone()
        sequence = conn.execute(
            'SELECT id, pattern, date_field, on_exhaust, status '
            "FROM number_sequences WHERE code = 'TRF'"
        ).fetchone()
    finally:
        conn.close()

    assert header is not None
    assert header[1] == 'transfer_order'
    assert header[2] == 'header'
    assert header[3] == 'standard'
    assert header[4] == sequence[0]
    assert header[5] == goods[0]
    assert header[6] == 'active'

    assert goods is not None
    assert goods[1] == 'transfer_order'
    assert goods[2] == 'line'
    assert goods[3] == 'material'
    assert goods[4] == 1
    assert goods[5] == 'active'

    assert sequence[1] == 'TRF-{DATE:yyyymm}-{SEQ:6}'
    assert sequence[2] == 'transfer_date'
    assert sequence[3] == 'error'
    assert sequence[4] == 'active'


def test_migration_line_unique_constraint(migrated_db):
    conn = sqlite3.connect(str(migrated_db))
    try:
        conn.execute(
            "INSERT INTO transfer_orders (transfer_order_no, transfer_date, "
            "status, from_org_id, to_org_id, legal_entity_id) "
            "VALUES ('TRF-202611-000001', '2026-11-01', 'draft', 2, 3, 1)")
        order_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        goods_id = conn.execute(
            "SELECT id FROM type_definitions WHERE code = 'TRF_GOODS'"
        ).fetchone()[0]
        conn.execute(
            'INSERT INTO transfer_order_lines (transfer_order_id, line_no, '
            'line_type_id, item_id, uom_id, qty) VALUES (?, 10, ?, 900, 3, 100)',
            [order_id, goods_id])
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO transfer_order_lines (transfer_order_id, line_no, '
                'line_type_id, item_id, uom_id, qty) '
                'VALUES (?, 10, ?, 900, 3, 50)',
                [order_id, goods_id])
    finally:
        conn.close()
