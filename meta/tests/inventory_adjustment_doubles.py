# -*- coding: utf-8 -*-
"""INV-4 调整 / 盘点测试替身：在 INV-1 替身（v201）之上安装 v203。

只供 meta/tests/test_inventory_adjustment_*.py 与盘点 / 冻结测试使用；
不触碰真实库。DDL 与种子直接复用 v203 迁移常量，避免测试与迁移漂移。
"""

import itertools
import sqlite3
from typing import Any, Dict, Optional

from meta.migrations import v203__inventory_adjustment as v203
from meta.migrations import v231__rule_hold as v231
from meta.tests import inventory_test_doubles as inv

DEFAULT_DATE = '2026-11-03'

_balance_seq = itertools.count(1)


def install_adjustment(conn: sqlite3.Connection) -> sqlite3.Connection:
    """在 `inv.build_db()` + `inv.seed()` 之后安装 v203（表/索引/类型/序列/参数）。"""
    v203._do_tables(conn)
    v203._do_indexes(conn)
    v203._do_types(conn)
    v203._do_number_sequences(conn)
    v203._do_params(conn)
    # 盘点 submit/approve 依赖规则挂起表 holds（spec-rule-model §10.4）
    v231._do_tables(conn)
    v231._do_indexes(conn)
    conn.commit()
    return conn


def build_adjustment_db() -> sqlite3.Connection:
    """一步到位：v201 三表 + 主数据种子 + v203 全部对象。"""
    return install_adjustment(inv.seed())


def set_numeric_param(conn: sqlite3.Connection, code: str, value: Any) -> None:
    """写数值型控制参数默认值。

    `inv.set_param` 会把 value_type 强制写成 bool，盘点容差比例等数值参数
    必须用本函数，保证 ControlParameterResolver 按 number 语义读取。
    """
    row = conn.execute(
        'SELECT id FROM control_parameter_defs WHERE code=?', [code]).fetchone()
    if row:
        conn.execute(
            'UPDATE control_parameter_defs SET default_value=?, '
            "value_type='number' WHERE code=?", [str(value), code])
    else:
        conn.execute(
            'INSERT INTO control_parameter_defs '
            "(code, default_value, status, value_type) "
            "VALUES (?, ?, 'active', 'number')", [code, str(value)])
    conn.commit()


def adjustment_service(conn: sqlite3.Connection):
    from meta.services.inventory_adjustment_service import (
        InventoryAdjustmentService,
    )
    return InventoryAdjustmentService(inv.MemDS(conn))


def count_service(conn: sqlite3.Connection):
    from meta.services.inventory_count_service import InventoryCountService
    return InventoryCountService(inv.MemDS(conn))


def _table_columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % table).fetchall()}


def insert_row(conn: sqlite3.Connection, table: str,
               data: Dict[str, Any]) -> int:
    """按表列过滤后插入一行，返回 lastrowid（跳过 prepare_create 的多余键）。"""
    columns = _table_columns(conn, table)
    row = {k: v for k, v in data.items() if k in columns}
    keys = list(row)
    cursor = conn.execute(
        'INSERT INTO %s (%s) VALUES (%s)' % (
            table, ', '.join(keys), ', '.join('?' * len(keys))),
        [row[k] for k in keys])
    return cursor.lastrowid


def insert_adjustment(conn: sqlite3.Connection,
                      data: Dict[str, Any]) -> int:
    return insert_row(conn, v203.ADJ_TABLE, data)


def insert_count(conn: sqlite3.Connection, data: Dict[str, Any]) -> int:
    return insert_row(conn, v203.CNT_TABLE, data)


def add_adjustment_line(conn: sqlite3.Connection, adjustment_id: int,
                        line_no: Optional[int] = None,
                        item_id: Any = inv.ITEM_ID,
                        location_id: Any = inv.LOCATION_ID,
                        batch_id: Any = None,
                        uom_id: Any = inv.UOM_ID,
                        qty: float = 1.0,
                        from_stock_status: Any = None,
                        to_stock_status: Any = None,
                        remark: Any = None) -> int:
    if line_no is None:
        row = conn.execute(
            'SELECT MAX(line_no) FROM %s WHERE adjustment_id=?'
            % v203.ADJ_LINE_TABLE, [adjustment_id]).fetchone()
        line_no = int(row[0] or 0) + 1
    cursor = conn.execute(
        'INSERT INTO %s (adjustment_id, line_no, item_id, location_id, '
        'batch_id, uom_id, qty, from_stock_status, to_stock_status, remark) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)' % v203.ADJ_LINE_TABLE,
        [adjustment_id, line_no, item_id, location_id, batch_id, uom_id, qty,
         from_stock_status, to_stock_status, remark])
    return cursor.lastrowid


def post_balance(conn: sqlite3.Connection, qty: float,
                 batch_id: Any = None,
                 stock_status: str = 'unrestricted',
                 org_id: Any = inv.ORG_ID,
                 location_id: Any = inv.LOCATION_ID,
                 item_id: Any = inv.ITEM_ID,
                 uom_id: Any = inv.UOM_ID,
                 transaction_type: str = 'RCV_PO',
                 source_key: Optional[str] = None) -> Dict[str, Any]:
    """用日常入账快速制造余额（默认组织/库位/物料/单位取 INV-1 种子）。"""
    service = inv.posting_service(conn)
    key = source_key or 'test:balance:%d' % next(_balance_seq)
    entry = {
        'transaction_type': transaction_type,
        'transaction_date': DEFAULT_DATE,
        'org_id': org_id,
        'location_id': location_id,
        'item_id': item_id,
        'uom_id': uom_id,
        'qty': qty,
        'direction': 'in',
        'batch_id': batch_id,
        'stock_status': stock_status,
        'source_line_id': '1',
    }
    return service.post(
        [entry],
        {'source_doc_type': 'receipt', 'source_doc_id': 1,
         'source_event_key': key, 'transaction_date': DEFAULT_DATE},
        allow_non_unrestricted=True)


def balance_qty(conn: sqlite3.Connection,
                batch_id: Any = None,
                stock_status: str = 'unrestricted',
                org_id: Any = inv.ORG_ID,
                location_id: Any = inv.LOCATION_ID,
                item_id: Any = inv.ITEM_ID) -> float:
    return inv.posting_service(conn).on_hand(
        org_id, location_id, item_id, batch_id, stock_status)
