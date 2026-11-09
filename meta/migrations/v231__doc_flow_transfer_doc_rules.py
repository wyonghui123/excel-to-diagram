# -*- coding: utf-8 -*-
"""v231 - 补齐调拨单据流两条断链规则（调拨行 → 发货行 / 收货行）

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §1 接入范围
      「单据 → 单据必须接」+ docs/specs/tasks-transfer-order-object-model-2026-11-02.md §12

背景:
  v215 只注册了调拨行 → 库存事务（transfer_order_line_to_issue_txn），
  调拨发货单（transfer_shipment）与调拨收货单（receipt）虽已真实挂载调拨行
  （transfer_shipment_line.transfer_order_line_id / receipt_line.source_line_id），
  但上游调拨行没有对应的单据流边，追溯链在此断为两段。

口径:
  1. 两条规则均为「单据行 → 单据行」attach 边：
     - transfer_order_line → transfer_shipment_line，pool = transfer_shipment
     - transfer_order_line → receipt_line，pool = transfer_receipt
  2. pool 独立：与调拨过账（transfer_move）互不干扰，Σ 校验按各自方向计算。
  3. 数量列名以实际 schema 为准：receipt_line 用 qty_received，
     transfer_shipment_line 用 qty。
  4. 规则 upsert 只覆盖声明字段，不覆盖 status（运行态由 set_rule_status 管理）。
"""

import os
import sqlite3
from datetime import datetime

MIGRATION_NAME = 'v231__doc_flow_transfer_doc_rules'

RULE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_rule (
    rule_id          TEXT PRIMARY KEY,
    source_bo        TEXT NOT NULL,
    target_bo        TEXT NOT NULL,
    source_qty_field TEXT NOT NULL DEFAULT 'quantity',
    target_qty_field TEXT NOT NULL DEFAULT '',
    pool             TEXT NOT NULL DEFAULT 'default',
    status           TEXT NOT NULL DEFAULT 'active',
    check_hook       TEXT,
    map_hook         TEXT,
    create_hook      TEXT,
    field_map        TEXT NOT NULL DEFAULT '{}',
    copied_fields    TEXT NOT NULL DEFAULT '[]',
    split_key        TEXT NOT NULL DEFAULT '[]',
    target_line_bo   TEXT NOT NULL DEFAULT '',
    head_fk_field    TEXT NOT NULL DEFAULT '',
    display_fields   TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT,
    updated_at       TEXT
)
"""

EDGE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_edges (
    id                  TEXT NOT NULL,
    source_bo           TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    source_item         TEXT DEFAULT '',
    target_bo           TEXT NOT NULL,
    target_id           TEXT NOT NULL,
    target_item         TEXT DEFAULT '',
    quantity            REAL NOT NULL,
    amount              REAL DEFAULT 0,
    currency            TEXT DEFAULT '',
    unit                TEXT DEFAULT '',
    quantity_sign       TEXT NOT NULL DEFAULT 'normal',
    rule_id             TEXT NOT NULL,
    derived_at          TEXT,
    derived_by          TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'active',
    pool                TEXT NOT NULL DEFAULT 'default',
    source_instance_id  TEXT DEFAULT '',
    target_instance_id  TEXT DEFAULT '',
    derive_key          TEXT DEFAULT '',
    edge_kind           TEXT NOT NULL DEFAULT 'normal',
    reverses_edge_id    TEXT DEFAULT ''
)
"""

EDGE_INDEXES = (
    ("uq_doc_flow_idem",
     "CREATE UNIQUE INDEX IF NOT EXISTS uq_doc_flow_idem ON doc_flow_edges("
     "source_bo, source_id, source_item, target_bo, target_id, target_item, rule_id)"),
    ("idx_doc_flow_source",
     "CREATE INDEX IF NOT EXISTS idx_doc_flow_source ON doc_flow_edges("
     "source_bo, source_id, status)"),
    ("idx_doc_flow_target",
     "CREATE INDEX IF NOT EXISTS idx_doc_flow_target ON doc_flow_edges("
     "target_bo, target_id, status)"),
)

CONSUMED_VIEW_DDL = """
CREATE VIEW IF NOT EXISTS v_doc_flow_consumed_qty AS
SELECT source_bo, source_id, source_item, pool,
       SUM(CASE WHEN status='active' AND quantity_sign='normal'
                THEN quantity ELSE 0 END)
     - SUM(CASE WHEN status='active' AND quantity_sign='red'
                THEN quantity ELSE 0 END) AS consumed_qty
FROM doc_flow_edges
GROUP BY source_bo, source_id, source_item, pool
"""

#: 调拨单据流两条断链规则
RULES = (
    {
        'rule_id': 'transfer_order_line_to_transfer_shipment_line',
        'source_bo': 'transfer_order_line',
        'target_bo': 'transfer_shipment_line',
        'source_qty_field': 'qty',
        'target_qty_field': 'qty',
        'pool': 'transfer_shipment',
    },
    {
        'rule_id': 'transfer_order_line_to_receipt_line',
        'source_bo': 'transfer_order_line',
        'target_bo': 'receipt_line',
        'source_qty_field': 'qty',
        # receipt_line 无 qty 字段，收货数量列名是 qty_received
        'target_qty_field': 'qty_received',
        'pool': 'transfer_receipt',
    },
)


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _view_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _index_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _do_upgrade(conn):
    now = datetime.now().isoformat(timespec='seconds')

    if _table_exists(conn, 'doc_flow_rule'):
        print('  - [SKIP] 表 doc_flow_rule 已存在')
    else:
        conn.execute(RULE_TABLE_DDL)
        print('  - [OK] 建表 doc_flow_rule')

    if _table_exists(conn, 'doc_flow_edges'):
        print('  - [SKIP] 表 doc_flow_edges 已存在')
    else:
        conn.execute(EDGE_TABLE_DDL)
        print('  - [OK] 建表 doc_flow_edges')

    for name, ddl in EDGE_INDEXES:
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
        else:
            conn.execute(ddl)
            print('  - [OK] 建索引 %s' % name)

    if _view_exists(conn, 'v_doc_flow_consumed_qty'):
        print('  - [SKIP] 视图 v_doc_flow_consumed_qty 已存在')
    else:
        conn.execute(CONSUMED_VIEW_DDL)
        print('  - [OK] 建视图 v_doc_flow_consumed_qty')

    for rule in RULES:
        conn.execute(
            """
            INSERT INTO doc_flow_rule
                (rule_id, source_bo, target_bo, source_qty_field,
                 target_qty_field, pool, copied_fields, status,
                 field_map, split_key, target_line_bo, head_fk_field,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, '[]', 'active', '{}', '[]', '', '', ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                source_bo=excluded.source_bo,
                target_bo=excluded.target_bo,
                source_qty_field=excluded.source_qty_field,
                target_qty_field=excluded.target_qty_field,
                pool=excluded.pool,
                updated_at=excluded.updated_at
            """,
            [rule['rule_id'], rule['source_bo'], rule['target_bo'],
             rule['source_qty_field'], rule['target_qty_field'], rule['pool'],
             now, now],
        )
        print('  - [OK] upsert 规则 %s' % rule['rule_id'])


def migrate(db_path, skip_backup=False):
    print('[v231] 补齐调拨单据流两条断链规则')
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return
    conn = sqlite3.connect(db_path)
    try:
        _do_upgrade(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path):
    if not os.path.exists(db_path):
        return {'ok': False, 'error': 'db not found'}
    conn = sqlite3.connect(db_path)
    try:
        checks = {
            'rule_table': _table_exists(conn, 'doc_flow_rule'),
            'edge_table': _table_exists(conn, 'doc_flow_edges'),
            'idem_index': _index_exists(conn, 'uq_doc_flow_idem'),
            'consumed_view': _view_exists(conn, 'v_doc_flow_consumed_qty'),
        }
        rows = conn.execute(
            'SELECT rule_id, status FROM doc_flow_rule WHERE rule_id IN (%s)'
            % ','.join(['?'] * len(RULES)),
            [rule['rule_id'] for rule in RULES]).fetchall()
        active = {row[0] for row in rows if row[1] == 'active'}
        checks['rules_active'] = len(active) == len(RULES)
        return {'ok': all(checks.values()), 'checks': checks}
    finally:
        conn.close()


def rollback(db_path):
    """回滚：只删规则声明，边表为 append-only 事实，不删除历史边。"""
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            'DELETE FROM doc_flow_rule WHERE rule_id = ?',
            [[rule['rule_id']] for rule in RULES])
        conn.commit()
    finally:
        conn.close()