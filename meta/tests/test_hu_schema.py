# -*- coding: utf-8 -*-
"""包装容器表结构 / 迁移（spec §11.2 / §11.6）。

覆盖：三表与列齐全 / 索引齐全 / 部分唯一约束生效 / 迁移前向 + verify。

ALLOW_RAW_SQL: 本文件必须用原生 DDL / PRAGMA 断言表结构与部分唯一索引，
Factory 无法表达索引与约束，故按文件显式放行（仅豁免本文件）。
"""

import importlib
import sqlite3

import pytest

pytestmark = pytest.mark.unit

_MIGRATION = importlib.import_module('meta.migrations.v211__handling_unit')
_STATUS_MIGRATION = importlib.import_module(
    'meta.migrations.v217__handling_unit_status')

REQUIRED = {
    'handling_units': {
        'hu_no', 'hu_type', 'packaging_item_id', 'org_id', 'location_id',
        'parent_hu_id', 'root_hu_id', 'status', 'is_reusable', 'cycle_no',
        'gross_weight', 'tare_weight', 'net_weight', 'volume', 'uom_id',
        'source_doc_type', 'source_doc_id', 'sealed_at', 'shipped_at',
        'voided_at', 'remark', 'created_at', 'updated_at',
    },
    'handling_unit_items': {
        'hu_id', 'content_type', 'item_id', 'batch_id', 'serial_id',
        'child_hu_id', 'qty', 'uom_id', 'created_at',
    },
    'hu_transactions': {
        'hu_id', 'serial_id', 'child_hu_id', 'txn_type', 'from_hu_id',
        'to_hu_id', 'from_location_id', 'to_location_id', 'doc_type',
        'doc_id', 'line_id', 'txn_at', 'remark', 'created_at',
    },
}


def _columns(conn, table):
    return {row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % table).fetchall()}


def test_tables_and_columns_exist():
    from meta.tests.hu_test_doubles import build_db
    conn = build_db()
    for table, cols in REQUIRED.items():
        assert _columns(conn, table) >= cols, table


def test_all_indexes_exist():
    from meta.tests.hu_test_doubles import build_db
    conn = build_db()
    names = {row[1] for row in conn.execute(
        "SELECT * FROM sqlite_master WHERE type='index'").fetchall()}
    for _table, name, _sql in _MIGRATION.INDEXES:
        assert name in names


def test_hu_no_unique_per_org():
    from meta.tests.hu_test_doubles import build_db, service
    conn = build_db()
    svc = service(conn)
    svc.create_hu({'hu_no': 'HU-001', 'org_id': 1})
    with pytest.raises(Exception):
        service(conn).create_hu({'hu_no': 'HU-001', 'org_id': 1})
    # 跨组织允许同号
    service(conn).create_hu({'hu_no': 'HU-001', 'org_id': 2})


def test_serial_can_only_be_in_one_hu():
    from meta.tests.hu_test_doubles import add_item, add_serial, build_db, service
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    svc = service(conn)
    hu1 = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    hu2 = svc.create_hu({'hu_no': 'HU-002', 'org_id': 1, 'location_id': 7})
    svc.pack(hu1['id'], [{'content_type': 'material', 'serial_id': serial_id}])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            'INSERT INTO handling_unit_items (hu_id, content_type, item_id, '
            'serial_id, qty, created_at) VALUES (?, ?, ?, ?, 1, ?)',
            [hu2['id'], 'material', 900, serial_id, '2026-11-04 10:00:00'])


def test_migration_migrate_and_verify(tmp_path):
    db_path = tmp_path / 'meta.db'
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        'CREATE TABLE receipt_lines (id INTEGER PRIMARY KEY);'
        'CREATE TABLE shipment_lines (id INTEGER PRIMARY KEY);')
    conn.close()
    assert _MIGRATION.migrate(db_path, skip_backup=True) is True
    assert _MIGRATION.verify(db_path) is True

    conn = sqlite3.connect(str(db_path))
    try:
        # 单据行可选装箱列由迁移补齐
        assert 'hu_no' in _columns(conn, 'receipt_lines')
        assert 'hu_type' in _columns(conn, 'receipt_lines')
    finally:
        conn.close()


def test_status_fields_marked_immutable():
    """hu_no / status 等 8 个状态字段标 immutable（P1-3）。"""
    import yaml
    from pathlib import Path
    from meta.core.yaml_loader import get_yaml_schema_dir
    data = yaml.safe_load(
        (Path(get_yaml_schema_dir()) / 'handling_unit.yaml')
        .read_text(encoding='utf-8'))
    fields = {field['id']: field for field in data['fields']}
    for name in ('hu_no', 'status', 'parent_hu_id', 'root_hu_id', 'cycle_no',
                 'sealed_at', 'shipped_at', 'voided_at'):
        assert fields[name]['semantics']['immutable'] is True, name


def _status_sql(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='handling_units'"
    ).fetchone()
    return row[0]


def test_status_migration_rebuilds_to_six_states(tmp_path):
    db_path = tmp_path / 'meta.db'
    conn = sqlite3.connect(str(db_path))
    for _table, ddl in _MIGRATION.TABLES:
        conn.executescript(ddl)
    conn.execute(
        "INSERT INTO handling_units (hu_no, hu_type, org_id, status) "
        "VALUES ('HU-1', 'carton', 1, 'sealed')")
    conn.commit()
    conn.close()

    assert _STATUS_MIGRATION.migrate(db_path, skip_backup=True) is True
    assert _STATUS_MIGRATION.verify(db_path) is True
    assert _STATUS_MIGRATION.migrate(db_path, skip_backup=True) is True

    conn = sqlite3.connect(str(db_path))
    try:
        sql = _status_sql(conn)
        assert 'planned' in sql and 'in_transit' in sql
        assert conn.execute(
            "SELECT status FROM handling_units WHERE hu_no='HU-1'").fetchone()[0] \
            == 'sealed'
        conn.execute(
            "INSERT INTO handling_units (hu_no, hu_type, org_id, status) "
            "VALUES ('HU-2', 'carton', 1, 'in_transit')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO handling_units (hu_no, hu_type, org_id, status) "
                "VALUES ('HU-3', 'carton', 1, 'unknown')")
        conn.rollback()
        names = {row[1] for row in conn.execute(
            "SELECT * FROM sqlite_master WHERE type='index'").fetchall()}
        for name in ('uq_hu_no', 'idx_hu_parent', 'idx_hu_root',
                     'idx_hu_location', 'idx_hu_status'):
            assert name in names
    finally:
        conn.close()


def test_status_rollback_merges_transit_back_to_sealed(tmp_path):
    db_path = tmp_path / 'meta.db'
    conn = sqlite3.connect(str(db_path))
    for _table, ddl in _MIGRATION.TABLES:
        conn.executescript(ddl)
    conn.execute(
        "INSERT INTO handling_units (hu_no, hu_type, org_id, status) "
        "VALUES ('HU-1', 'carton', 1, 'sealed')")
    conn.commit()
    conn.close()
    assert _STATUS_MIGRATION.migrate(db_path, skip_backup=True) is True

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO handling_units (hu_no, hu_type, org_id, status, shipped_at) "
        "VALUES ('HU-T', 'carton', 1, 'in_transit', '2026-11-05 10:00:00')")
    conn.commit()
    conn.close()

    assert _STATUS_MIGRATION.rollback(db_path) is True
    conn = sqlite3.connect(str(db_path))
    try:
        sql = _status_sql(conn)
        assert 'in_transit' not in sql and 'planned' not in sql
        row = conn.execute(
            "SELECT status, shipped_at FROM handling_units WHERE hu_no='HU-T'"
        ).fetchone()
        assert row[0] == 'sealed' and row[1] is None
    finally:
        conn.close()
