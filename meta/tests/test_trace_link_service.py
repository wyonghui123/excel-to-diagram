# -*- coding: utf-8 -*-
"""追溯链接写入：序列号链接幂等、容器链接只前进不回退。"""

import importlib

from meta.services.trace_link_service import link_hu, link_serial
from meta.tests.hu_test_doubles import build_db, ds

_V216 = importlib.import_module('meta.migrations.v216__document_hu_links')


def _build():
    """build_db 自带 serial 链接表；v216 补上 document_hu_links。"""
    conn = build_db()
    database = ds(conn)
    for _table, ddl in _V216.TABLES:
        database.execute(ddl)
    for _table, _name, ddl in _V216.INDEXES:
        database.execute(ddl)
    return conn, database


def _rows(conn, table):
    return ds(conn).query('SELECT * FROM %s' % table)


def test_serial_link_is_idempotent():
    conn, database = _build()
    assert link_serial(database, 'receipt', 1, 10, 900, 'in') is True
    assert link_serial(database, 'receipt', 1, 10, 900, 'in') is False
    assert len(_rows(conn, 'document_serial_links')) == 1


def test_hu_link_insert_then_promote():
    conn, database = _build()
    assert link_hu(database, 'shipment', 1, 10, 7, 'out',
                   link_type='planned', qty=1) == 'inserted'
    assert link_hu(database, 'shipment', 1, 10, 7, 'out',
                   link_type='packed', qty=2) == 'promoted'
    row = _rows(conn, 'document_hu_links')[0]
    assert (row['link_type'], row['qty']) == ('packed', 2)


def test_hu_link_never_regresses():
    conn, database = _build()
    link_hu(database, 'shipment', 1, 10, 7, 'out',
            link_type='shipped', qty=1)
    assert link_hu(database, 'shipment', 1, 10, 7, 'out',
                   link_type='planned', qty=3) == 'qty'
    row = _rows(conn, 'document_hu_links')[0]
    assert (row['link_type'], row['qty']) == ('shipped', 3)


def test_hu_link_blank_qty_keeps_existing():
    conn, database = _build()
    link_hu(database, 'shipment', 1, 10, 7, 'out',
            link_type='packed', qty=2)
    assert link_hu(database, 'shipment', 1, 10, 7, 'out',
                   link_type='packed', qty=None) == 'kept'
    assert _rows(conn, 'document_hu_links')[0]['qty'] == 2
