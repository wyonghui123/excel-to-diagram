# -*- coding: utf-8 -*-
"""单据 ↔ 包装容器关系桥表（v216 / spec §11.15 D17-D19）。

ALLOW_RAW_SQL: 测试替身直接造假单据与关系表；Factory 尚无对应支持，仅豁免本文件。
"""

import importlib
import pathlib
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.services.handling_unit_service import (  # noqa: E402
    HandlingUnitError,
    document_links_ready,
)
from meta.tests.hu_test_doubles import (  # noqa: E402
    add_item,
    add_serial,
    build_db,
    ds,
    service,
)

LINK_DDL = """
CREATE TABLE IF NOT EXISTS document_hu_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    doc_id INTEGER NOT NULL,
    line_id INTEGER,
    hu_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'packed',
    tentative INTEGER NOT NULL DEFAULT 0,
    qty REAL,
    org_id INTEGER,
    created_at TEXT NOT NULL,
    created_by TEXT,
    updated_at TEXT,
    remark TEXT
)
"""

LINK_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_document_hu_link ON document_hu_links(
    doc_type, doc_id, COALESCE(line_id, 0), hu_id, direction)
"""


def enable_links(conn):
    ds(conn).execute(LINK_DDL)
    ds(conn).execute(LINK_INDEX)
    assert document_links_ready(ds(conn))


def _receipt_with_hu(conn, hu_no='HU-R'):
    ds(conn).execute(
        "INSERT INTO receipts (id, receipt_no, org_id, status) "
        "VALUES (1, 'RC-1', 1, 'posted')")
    ds(conn).execute(
        "INSERT INTO receipt_lines (id, receipt_id, item_id, qty_received, "
        "qty_rejected, hu_no, hu_type, putaway_location_id, status) "
        "VALUES (1, 1, 900, 1, 0, ?, 'carton', 7, 'open')", [hu_no])
    serial_id = add_serial(conn)
    ds(conn).execute(
        "INSERT INTO document_serial_links (doc_type, doc_id, line_id, "
        "serial_id, direction, created_at) "
        "VALUES ('receipt', 1, 1, ?, 'in', datetime('now'))", [serial_id])
    return serial_id


def _shipment_with_hu(conn, hu_no='HU-R', qty=1, lines=1):
    ds(conn).execute(
        "INSERT INTO shipments (id, delivery_no, ship_from_location_id, status) "
        "VALUES (1, 'DN-1', 7, 'confirmed')")
    for idx in range(1, lines + 1):
        ds(conn).execute(
            "INSERT INTO shipment_lines (id, delivery_id, item_id, qty, hu_no, "
            "status) VALUES (?, 1, ?, ?, ?, 'confirmed')",
            [idx, 900 + idx - 1, qty, hu_no])


def test_pack_receipt_writes_link_and_forward_query():
    conn = build_db()
    add_item(conn)
    _receipt_with_hu(conn)
    enable_links(conn)
    svc = service(conn)

    result = svc.pack_receipt(1)

    assert result['packed'] == 1
    links = svc.document_hus('receipt', 1)
    assert len(links) == 1
    link = links[0]
    assert link['hu_no'] == 'HU-R' and link['direction'] == 'in'
    assert link['link_type'] == 'packed' and link['qty'] == 1
    assert len(svc.hu_documents(link['hu_id'])) == 1


def test_ship_advances_link_to_shipped_and_reverse_steps_back():
    conn = build_db()
    add_item(conn)
    _receipt_with_hu(conn)
    enable_links(conn)
    _shipment_with_hu(conn)
    svc = service(conn)

    svc.pack_receipt(1)
    hu = ds(conn).query(
        'SELECT id FROM handling_units WHERE hu_no = ?', ['HU-R'])[0]
    shipped = svc.ship_shipment(1)

    assert shipped['shipped'] == 1
    out_links = [row for row in svc.hu_documents(hu['id'])
                 if row['direction'] == 'out']
    assert out_links and out_links[0]['link_type'] == 'shipped'

    svc.reverse_document('shipment', 1)

    out_links = [row for row in svc.hu_documents(hu['id'])
                 if row['direction'] == 'out']
    assert out_links[0]['link_type'] == 'packed'


def test_pack_line_supports_one_line_multi_hu_with_qty_guard():
    conn = build_db()
    add_item(conn)
    enable_links(conn)
    _shipment_with_hu(conn, hu_no='', qty=10, lines=1)
    svc = service(conn)
    hu_a = svc.create_hu({'hu_no': 'HU-A', 'org_id': 1, 'location_id': 7})
    hu_b = svc.create_hu({'hu_no': 'HU-B', 'org_id': 1, 'location_id': 7})

    first = svc.pack_line('shipment', 1, 1, hu_a['id'], qty=4)
    second = svc.pack_line('shipment', 1, 1, hu_b['id'], qty=6)

    assert first['qty'] == 4 and second['qty'] == 6
    links = svc.hu_documents(hu_a['id']) + svc.hu_documents(hu_b['id'])
    assert sorted(row['qty'] for row in links) == [4, 6]

    with pytest.raises(HandlingUnitError, match='超过单据行数量'):
        svc.pack_line('shipment', 1, 1, hu_a['id'], qty=1)

    # 已有整行/多容器后，不填数量必须拒绝
    with pytest.raises(HandlingUnitError, match='必须填写数量'):
        svc.pack_line('shipment', 1, 1, hu_a['id'])


def test_pack_line_requires_link_schema():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-A', 'org_id': 1, 'location_id': 7})
    with pytest.raises(HandlingUnitError, match='v216'):
        svc.pack_line('shipment', 1, 1, hu['id'], qty=1)


def test_document_hu_link_schema_loads():
    """YAML 能被 loader 正常解析，且表名/字段/索引与 v216 迁移一致。"""
    from meta.core.yaml_loader import get_yaml_schema_dir, load_yaml_file
    migration = importlib.import_module('meta.migrations.v216__document_hu_links')

    obj = load_yaml_file(str(
        pathlib.Path(get_yaml_schema_dir()) / 'document_hu_link.yaml'))
    assert obj is not None
    assert obj.id == 'document_hu_link'
    assert obj.table_name == migration.LINK_TABLE
    field_ids = {f.id for f in obj.fields}
    expect_columns = {
        'id', 'doc_type', 'doc_id', 'line_id', 'hu_id', 'direction',
        'link_type', 'tentative', 'qty', 'org_id', 'created_at',
    }
    assert expect_columns <= field_ids
    index_names = {index.name for index in obj.indexes}
    assert index_names == {name for _t, name, _sql in migration.INDEXES}


def test_migration_migrate_verify_backfill_and_rollback(tmp_path):
    """v216 前向/幂等/回填/回滚；唯一索引用 COALESCE 兜住 NULL 行号。"""
    migration = importlib.import_module('meta.migrations.v216__document_hu_links')
    v211 = importlib.import_module('meta.migrations.v211__handling_unit')
    db_path = tmp_path / 'meta.db'
    conn = sqlite3.connect(str(db_path))
    for _table, ddl in v211.TABLES:
        conn.executescript(ddl)
    conn.executescript(
        'CREATE TABLE receipt_lines (id INTEGER PRIMARY KEY, receipt_id INTEGER, '
        'item_id INTEGER, qty REAL, hu_no TEXT);')
    conn.execute(
        "INSERT INTO handling_units (hu_no, hu_type, org_id, status) "
        "VALUES ('HU-B', 'carton', 1, 'sealed')")
    hu_id = conn.execute(
        "SELECT id FROM handling_units WHERE hu_no = 'HU-B'").fetchone()[0]
    conn.execute(
        "INSERT INTO receipt_lines (id, receipt_id, item_id, qty, hu_no) "
        "VALUES (1, 1, 900, 5, 'HU-B')")
    conn.commit()

    assert migration.migrate(db_path, skip_backup=True) is True
    assert migration.verify(db_path) is True
    assert migration.migrate(db_path, skip_backup=True) is True
    assert migration.verify(db_path) is True

    link = conn.execute(
        'SELECT doc_type, doc_id, line_id, hu_id, direction, link_type, qty '
        'FROM document_hu_links').fetchone()
    assert link == ('receipt', 1, 1, hu_id, 'in', 'packed', 5)

    conn.execute(
        "INSERT INTO document_hu_links (doc_type, doc_id, line_id, hu_id, "
        "direction, link_type, tentative, created_at) "
        "VALUES ('receipt', 2, NULL, ?, 'in', 'packed', 0, '2026-11-05 00:00:00')",
        [hu_id])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO document_hu_links (doc_type, doc_id, line_id, hu_id, "
            "direction, link_type, tentative, created_at) "
            "VALUES ('receipt', 2, NULL, ?, 'in', 'packed', 0, '2026-11-05 00:00:00')",
            [hu_id])
    conn.rollback()
    conn.close()

    assert migration.rollback(db_path) is True
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='document_hu_links'").fetchone() is None
    finally:
        conn.close()
