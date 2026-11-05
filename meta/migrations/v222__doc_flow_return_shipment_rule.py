# -*- coding: utf-8 -*-
"""v222 - 退货交货（方案 A）的移动类型 / 单据类型 / 转单规则 / 追溯视图口径

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.1 / §6 阶段 5 / §7

背景:
  退货不是独立对象：销售退货复用 shipments，方向只落在抬头 document_category；
  `ship_confirm` 按类别分支出库（ISSUE_TO_SHIP / out）或退货入库（RETURN_IN / in）。

范围:
  1. `inventory_transaction_types` 种子 `RETURN_IN`（category=receipt, direction=in）。
  2. `type_definitions` 种子退货交货类型（scope_bo='shipment', level='header',
     code='RETURN', document_category='return'）；缺表 [SKIP]。
  3. `doc_flow_rule` upsert `shipment_line_to_return_in_txn`（pool=inventory_return），
     不覆盖运行态 status。
  4. 刷新 `v_demand_trace_graph`：`signed_qty` 四分支符号映射
     （出库 +、退货 −、红字取反），列数不变（仍 17 列）。

幂等:
  类型 / 规则先查后用；视图 DROP + CREATE 重建；重复执行打印 [SKIP]。

[ALLOW_DESTRUCTIVE] upgrade 会 DROP VIEW IF EXISTS；只重建投影，不动表数据。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

MIGRATION_NAME = 'v222__doc_flow_return_shipment_rule'

TYPES_TABLE = 'inventory_transaction_types'
TYPE_DEF_TABLE = 'type_definitions'
RULE_TABLE = 'doc_flow_rule'

RETURN_IN = ('RETURN_IN', '销售退货入库', 'receipt', 'in', 1, 70,
             '退货交货确认形成的入库（业务退货，新事实；不等于红字冲销）')

#: (code, name, scope_bo, level, document_category, description)
RETURN_DOC_TYPE = (
    'RETURN', '退货交货单', 'shipment', 'header', 'return',
    '退货交货默认单据类型（方案 A：复用交货单，方向由 document_category 决定）',
)

RETURN_RULE = {
    'rule_id': 'shipment_line_to_return_in_txn',
    'source_bo': 'shipment_line',
    'target_bo': 'inventory_transaction',
    'source_qty_field': 'qty',
    'pool': 'inventory_return',
}

RULE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_rule (
    rule_id          TEXT PRIMARY KEY,
    source_bo        TEXT NOT NULL,
    target_bo        TEXT NOT NULL,
    source_qty_field TEXT NOT NULL DEFAULT 'quantity',
    pool             TEXT NOT NULL DEFAULT 'default',
    status           TEXT NOT NULL DEFAULT 'active',
    check_hook       TEXT,
    map_hook         TEXT,
    create_hook      TEXT,
    field_map        TEXT NOT NULL DEFAULT '{}',
    split_key        TEXT NOT NULL DEFAULT '[]',
    target_line_bo   TEXT NOT NULL DEFAULT '',
    head_fk_field    TEXT NOT NULL DEFAULT '',
    created_at       TEXT,
    updated_at       TEXT
)
"""

VIEW_NAME = 'v_demand_trace_graph'
EDGE_TABLE = 'doc_flow_edges'
TRACE_TABLE = 'demand_trace_links'

#: 退货规则边对源单履约量是负贡献；红字再取反（业务退货被冲销 ⇒ 恢复为正）
SIGNED_QTY_SQL = """\
    CASE
      WHEN e.rule_id = '%s'
        THEN CASE WHEN e.quantity_sign = 'red' THEN e.quantity ELSE -e.quantity END
      ELSE CASE WHEN e.quantity_sign = 'red' THEN -e.quantity ELSE e.quantity END
    END AS signed_qty""" % RETURN_RULE['rule_id']

#: 17 列；与 meta/schemas/demand_trace_graph.yaml 的 view_definition 逐字一致
VIEW_SQL = """\
SELECT
  'execution' AS layer,
  'E:' || e.id AS id,
  e.rule_id AS relation,
  e.source_bo AS source_object_type,
  e.source_id AS source_object_id,
  COALESCE(e.source_item, '') AS source_line_id,
  e.target_bo AS target_object_type,
  e.target_id AS target_object_id,
  COALESCE(e.target_item, '') AS target_line_id,
  e.quantity AS qty,
""" + SIGNED_QTY_SQL + """,
  e.status AS status,
  NULL AS peg_type,
  NULL AS plan_version,
  NULL AS valid_from,
  NULL AS valid_to,
  e.derived_at AS occurred_at
FROM doc_flow_edges e
UNION ALL
SELECT
  'plan' AS layer,
  'T:' || CAST(t.id AS TEXT) AS id,
  t.trace_type AS relation,
  t.supply_object_type AS source_object_type,
  CAST(t.supply_object_id AS TEXT) AS source_object_id,
  COALESCE(NULLIF(CAST(t.supply_line_id AS TEXT), '0'), '') AS source_line_id,
  t.demand_object_type AS target_object_type,
  CAST(t.demand_object_id AS TEXT) AS target_object_id,
  COALESCE(NULLIF(CAST(t.demand_line_id AS TEXT), '0'), '') AS target_line_id,
  t.allocated_qty AS qty,
  CASE WHEN t.valid_to IS NULL THEN t.allocated_qty ELSE 0 END AS signed_qty,
  CASE WHEN t.valid_to IS NULL THEN 'active' ELSE 'expired' END AS status,
  t.peg_type AS peg_type,
  t.plan_version AS plan_version,
  t.valid_from AS valid_from,
  t.valid_to AS valid_to,
  t.computed_at AS occurred_at
FROM demand_trace_links t"""

VIEW_DDL = 'CREATE VIEW IF NOT EXISTS {0} AS\n{1}'.format(VIEW_NAME, VIEW_SQL)


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


def _do_return_in_type(conn):
    if not _table_exists(conn, TYPES_TABLE):
        print('  - [SKIP] 缺表 %s，跳过 RETURN_IN' % TYPES_TABLE)
        return
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % TYPES_TABLE, [RETURN_IN[0]]
    ).fetchone()
    if row:
        print('  - [SKIP] 移动类型 %s 已存在' % RETURN_IN[0])
        return
    conn.execute(
        'INSERT INTO %s (code, name, category, direction, affects_on_hand, '
        'status, sort_order, description, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)' % TYPES_TABLE,
        (RETURN_IN[0], RETURN_IN[1], RETURN_IN[2], RETURN_IN[3], RETURN_IN[4],
         'active', RETURN_IN[5], RETURN_IN[6],
         datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
    )
    print('  - [ADD] 移动类型 %s（%s）' % (RETURN_IN[0], RETURN_IN[1]))


def _do_return_doc_type(conn):
    if not _table_exists(conn, TYPE_DEF_TABLE):
        print('  - [SKIP] 缺表 %s，跳过退货交货类型' % TYPE_DEF_TABLE)
        return
    code, name, scope, level, category, description = RETURN_DOC_TYPE
    row = conn.execute(
        'SELECT id FROM %s WHERE scope_bo=? AND level=? AND code=?'
        % TYPE_DEF_TABLE, [scope, level, code]
    ).fetchone()
    if row:
        print('  - [SKIP] 单据类型 %s/%s/%s 已存在 (id=%s)'
              % (scope, level, code, row[0]))
        return
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    cur = conn.execute(
        'INSERT INTO %s '
        '(code, name, scope_bo, level, document_category, status, description, '
        'created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)' % TYPE_DEF_TABLE,
        (code, name, scope, level, category, 'active', description, now),
    )
    print('  - [NEW] 单据类型 %s/%s/%s (id=%s)' % (scope, level, code,
                                                  cur.lastrowid))


def _do_rule(conn):
    if not _table_exists(conn, RULE_TABLE):
        conn.execute(RULE_TABLE_DDL)
        print('  - [OK] 建表 %s' % RULE_TABLE)
    now = datetime.now().isoformat(timespec='seconds')
    conn.execute(
        """
        INSERT INTO doc_flow_rule
            (rule_id, source_bo, target_bo, source_qty_field, pool, status,
             field_map, split_key, target_line_bo, head_fk_field,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', '{}', '[]', '', '', ?, ?)
        ON CONFLICT(rule_id) DO UPDATE SET
            source_bo=excluded.source_bo,
            target_bo=excluded.target_bo,
            source_qty_field=excluded.source_qty_field,
            pool=excluded.pool,
            updated_at=excluded.updated_at
        """,
        [RETURN_RULE['rule_id'], RETURN_RULE['source_bo'],
         RETURN_RULE['target_bo'], RETURN_RULE['source_qty_field'],
         RETURN_RULE['pool'], now, now],
    )
    print('  - [OK] upsert 规则 %s' % RETURN_RULE['rule_id'])


def _do_view(conn):
    if not (_table_exists(conn, EDGE_TABLE) and _table_exists(conn, TRACE_TABLE)):
        missing = [name for name in (EDGE_TABLE, TRACE_TABLE)
                   if not _table_exists(conn, name)]
        print('  - [SKIP] 缺基表 %s，不建视图 %s'
              % (', '.join(missing), VIEW_NAME))
        return False
    if _view_exists(conn, VIEW_NAME):
        conn.execute('DROP VIEW %s' % VIEW_NAME)
        print('  - [OK] 重建视图 %s（DROP + CREATE）' % VIEW_NAME)
    else:
        print('  - [OK] 建视图 %s' % VIEW_NAME)
    conn.execute(VIEW_DDL)
    return True


def _do_upgrade(conn):
    _do_return_in_type(conn)
    _do_return_doc_type(conn)
    _do_rule(conn)
    return _do_view(conn)


def migrate(db_path, skip_backup=False):
    print('[v222] 退货交货：移动类型 / 单据类型 / 转单规则 / 追溯视图')
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
        checks = {}
        # 基表缺失按 [SKIP] 口径视为通过（迁移只做可落地部分）
        checks['return_in_type'] = (True if not _table_exists(conn, TYPES_TABLE)
                                    else bool(conn.execute(
                                        'SELECT 1 FROM %s WHERE code=? AND category=? '
                                        'AND direction=? AND status=?'
                                        % TYPES_TABLE,
                                        [RETURN_IN[0], 'receipt', 'in', 'active']
                                    ).fetchone()))

        checks['return_doc_type'] = (True if not _table_exists(conn, TYPE_DEF_TABLE)
                                     else bool(conn.execute(
                                         'SELECT 1 FROM %s WHERE scope_bo=? AND level=? '
                                         'AND code=? AND document_category=?'
                                         % TYPE_DEF_TABLE,
                                         [RETURN_DOC_TYPE[2], RETURN_DOC_TYPE[3],
                                          RETURN_DOC_TYPE[0], 'return']
                                     ).fetchone()))

        checks['return_rule'] = (True if not _table_exists(conn, RULE_TABLE)
                                 else bool(conn.execute(
                                     'SELECT 1 FROM %s WHERE rule_id=? AND pool=? '
                                     'AND status=?' % RULE_TABLE,
                                     [RETURN_RULE['rule_id'], RETURN_RULE['pool'],
                                      'active']
                                 ).fetchone()))

        both_base = (_table_exists(conn, EDGE_TABLE)
                     and _table_exists(conn, TRACE_TABLE))
        view_exists = _view_exists(conn, VIEW_NAME)
        checks['view_exists_or_skipped'] = view_exists or not both_base
        checks['skipped_without_base_tables'] = not both_base and not view_exists
        if view_exists and both_base:
            cols = [row[1] for row in
                    conn.execute('PRAGMA table_info(%s)' % VIEW_NAME).fetchall()]
            checks['view_columns'] = len(cols) == 17
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='view' AND name=?",
                [VIEW_NAME]).fetchone()[0]
            checks['view_return_sign'] = RETURN_RULE['rule_id'] in (sql or '')
        else:
            checks['view_columns'] = True
            checks['view_return_sign'] = True

        return {'ok': all(v for k, v in checks.items()
                          if k != 'skipped_without_base_tables'),
                'checks': checks}
    finally:
        conn.close()
