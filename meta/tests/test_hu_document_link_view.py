# -*- coding: utf-8 -*-
"""单据 ↔ 容器只读视图（v220 / spec §11.16.2）。

覆盖:
  · 视图 18 列 / YAML view_definition 与迁移 SQL 逐字一致
  · 三种单据 doc_no / doc_date / line_no（发货回退 line_id）
  · hu_id 子树过滤（hub「关联单据」tab 的 effective 口径）
  · 迁移幂等 / rollback / 缺基表 [SKIP]

ALLOW_RAW_SQL: 视图测试直接造假单据与桥表行，Factory 无对应支持。
"""

import importlib
import sqlite3

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.tests.hu_test_doubles import SCHEMA, build_db  # noqa: E402
from meta.tests.test_hu_document_links import (  # noqa: E402
    LINK_DDL,
    LINK_INDEX,
    enable_links,
)

V220 = importlib.import_module('meta.migrations.v220__document_hu_link_view')
HU_MIGRATION = importlib.import_module('meta.migrations.v211__handling_unit')
STATUS_MIGRATION = importlib.import_module(
    'meta.migrations.v217__handling_unit_status')

VIEW = V220.VIEW_NAME
SCHEMA_PATH = (
    __import__('pathlib').Path(__file__).resolve().parents[1]
    / 'schemas' / 'document_hu_link_view.yaml')


def _add_hu(conn, hu_id, hu_no, status='open', org_id=1, location_id=7):
    conn.execute(
        'INSERT INTO handling_units (id, hu_no, hu_type, org_id, location_id, '
        'status) VALUES (?, ?, ?, ?, ?, ?)',
        [hu_id, hu_no, 'carton', org_id, location_id, status])


def _add_link(conn, doc_type, doc_id, hu_id, line_id=1, direction='in',
              link_type='packed', qty=1):
    conn.execute(
        'INSERT INTO document_hu_links (doc_type, doc_id, line_id, hu_id, '
        'direction, link_type, tentative, qty, org_id, created_at) '
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, 1, '2026-11-05 10:00:00')",
        [doc_type, doc_id, line_id, hu_id, direction, link_type, qty])


def _create_view(conn):
    conn.execute('CREATE VIEW %s AS\n%s' % (VIEW, V220.VIEW_SQL))


def _row(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [item[0] for item in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def test_columns_and_yaml_definition_match():
    conn = build_db()
    enable_links(conn)
    _create_view(conn)

    columns = [row[1] for row in
               conn.execute('PRAGMA table_info(%s)' % VIEW).fetchall()]
    assert columns == V220.EXPECTED_COLUMNS
    assert len(columns) == 18

    definition = yaml.safe_load(SCHEMA_PATH.read_text(encoding='utf-8'))
    assert definition['object_type'] == 'view'
    assert definition['table_name'] == VIEW
    assert definition['view_definition'].strip() == V220.VIEW_SQL.strip()


def test_receipt_projects_doc_no_date_and_line_no():
    conn = build_db()
    enable_links(conn)
    _create_view(conn)

    conn.execute(
        "INSERT INTO receipts (id, receipt_no, org_id, status, receipt_date) "
        "VALUES (1, 'RC-1', 1, 'posted', '2026-11-01')")
    conn.execute(
        "INSERT INTO receipt_lines (id, receipt_id, line_no, item_id, "
        "qty_received, status) VALUES (10, 1, '10', 900, 1, 'posted')")
    _add_hu(conn, 1, 'HU-R', status='sealed')
    _add_link(conn, 'receipt', 1, 1, line_id=10)

    row = _row(conn, 'SELECT * FROM %s WHERE doc_type = ? AND doc_id = ?' % VIEW,
               ['receipt', 1])
    assert row['doc_no'] == 'RC-1'
    assert row['doc_date'] == '2026-11-01'
    assert row['line_no'] == '10'
    assert row['doc_status'] == 'posted'
    assert row['hu_no'] == 'HU-R'
    assert row['hu_status'] == 'sealed'
    assert row['direction'] == 'in'


def test_shipment_falls_back_to_line_id_and_planned_date():
    conn = build_db()
    enable_links(conn)
    _create_view(conn)

    conn.execute(
        "INSERT INTO shipments (id, delivery_no, ship_from_location_id, "
        "status, planned_ship_date) VALUES (2, 'DN-1', 7, 'confirmed', "
        "'2026-11-02')")
    _add_hu(conn, 2, 'HU-S')
    _add_link(conn, 'shipment', 2, 2, line_id=3, direction='out',
              link_type='shipped')

    row = _row(conn, 'SELECT * FROM %s WHERE doc_type = ? AND doc_id = ?' % VIEW,
               ['shipment', 2])
    assert row['doc_no'] == 'DN-1'
    assert row['doc_date'] == '2026-11-02'
    assert row['line_no'] == '3'
    assert row['direction'] == 'out'

    conn.execute(
        "UPDATE shipments SET actual_ship_date = '2026-11-03' WHERE id = 2")
    row = _row(conn, 'SELECT * FROM %s WHERE doc_id = 2' % VIEW)
    assert row['doc_date'] == '2026-11-03'


def test_transfer_projects_transfer_order_no_and_line_no():
    conn = build_db()
    enable_links(conn)
    _create_view(conn)

    conn.execute(
        "INSERT INTO transfer_orders (id, transfer_order_no, from_org_id, "
        "to_org_id, status, transfer_date) VALUES (3, 'TR-1', 1, 2, 'posted', "
        "'2026-11-04')")
    conn.execute(
        "INSERT INTO transfer_order_lines (id, transfer_order_id, line_no, "
        "item_id, qty, status) VALUES (20, 3, '20', 900, 5, 'posted')")
    _add_hu(conn, 3, 'HU-T')
    _add_link(conn, 'transfer_order', 3, 3, line_id=20, direction='out')

    row = _row(conn, 'SELECT * FROM %s WHERE doc_type = ? AND doc_id = ?' % VIEW,
               ['transfer_order', 3])
    assert row['doc_no'] == 'TR-1'
    assert row['doc_date'] == '2026-11-04'
    assert row['line_no'] == '20'


def test_hu_id_in_filter_covers_subtree():
    conn = build_db()
    enable_links(conn)
    _create_view(conn)

    for hu_id, hu_no in ((1, 'HU-P'), (2, 'HU-C1'), (3, 'HU-C2')):
        _add_hu(conn, hu_id, hu_no)
    _add_link(conn, 'receipt', 1, 2, line_id=1)
    _add_link(conn, 'receipt', 1, 3, line_id=2)

    rows = conn.execute(
        'SELECT hu_no, line_no FROM %s WHERE hu_id IN (?, ?) ORDER BY hu_id'
        % VIEW, [2, 3]).fetchall()
    assert [row[0] for row in rows] == ['HU-C1', 'HU-C2']
    assert _row(conn, 'SELECT * FROM %s WHERE hu_id = ?' % VIEW, [1]) is None


def _file_db(path):
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.executescript(SCHEMA)
    for _table, ddl in HU_MIGRATION.TABLES:
        conn.executescript(ddl)
    for _table, _name, ddl in HU_MIGRATION.INDEXES:
        conn.execute(ddl)
    STATUS_MIGRATION._rebuild(conn, STATUS_MIGRATION.NEW_DDL)
    conn.executescript(LINK_DDL)
    conn.execute(LINK_INDEX)
    conn.commit()
    return conn


def test_migration_lifecycle_idempotent_and_rollback(tmp_path):
    db_path = tmp_path / 'view.db'
    conn = _file_db(db_path)
    conn.close()

    assert V220.migrate(db_path) is True
    assert V220.verify(db_path) is True
    assert V220.migrate(db_path) is True

    assert V220.rollback(db_path) is True
    assert V220.verify(db_path) is False


def test_migration_skips_without_base_tables(tmp_path):
    db_path = tmp_path / 'empty.db'
    sqlite3.connect(str(db_path)).close()

    assert V220.migrate(db_path) is True
    assert V220.verify(db_path) is True
    rows = sqlite3.connect(str(db_path)).execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = ?",
        [VIEW]).fetchall()
    assert rows == []
