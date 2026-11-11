# -*- coding: utf-8 -*-
"""[v254 2026-11-11] 采购发票对象模型（W3：单据流转规则 + 金额消耗视图）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §2.3 行来源策略 / §4.2 行字段 / §13 实施波次 W3

内容:
  1. doc_flow_rule 3 条（ON CONFLICT(rule_id) DO UPDATE，幂等）:
       po_schedule_to_vendor_invoice_line
           purchase_order_schedule.promised_qty → vendor_invoice_line   pool=billing
       receipt_line_to_vendor_invoice_line
           receipt_line.qty_received           → vendor_invoice_line   pool=ap_match
       vendor_invoice_line_to_credit_memo_line
           vendor_invoice_line.qty             → vendor_invoice_line   pool=billing
     说明: 红字方向不由规则声明，由 doc_flow_reversal 在冲销时写
     quantity_sign='red' 的边（与既有规则同口径）。
  2. 新增只读视图 v_doc_flow_consumed_amount（与 v_doc_flow_consumed_qty 同构，
     按行金额聚合）。既有 17 列 v_doc_flow_consumed_qty 不改动。

幂等: 规则 ON CONFLICT DO UPDATE；视图 CREATE VIEW IF NOT EXISTS。
回滚: 删 3 条规则；DROP VIEW v_doc_flow_consumed_amount。
"""

import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATION_NAME = 'v254__vendor_invoice_doc_flow'

RULE_TABLE = 'doc_flow_rule'
EDGE_TABLE = 'doc_flow_edges'

#: (rule_id, source_bo, target_bo, source_qty_field, pool)
RULES = (
    (
        'po_schedule_to_vendor_invoice_line',
        'purchase_order_schedule',
        'vendor_invoice_line',
        'promised_qty',
        'billing',
    ),
    (
        'receipt_line_to_vendor_invoice_line',
        'receipt_line',
        'vendor_invoice_line',
        'qty_received',
        'ap_match',
    ),
    (
        'vendor_invoice_line_to_credit_memo_line',
        'vendor_invoice_line',
        'vendor_invoice_line',
        'qty',
        'billing',
    ),
)

RULE_IDS = tuple(rule[0] for rule in RULES)

AMOUNT_VIEW = 'v_doc_flow_consumed_amount'
AMOUNT_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS v_doc_flow_consumed_amount AS
SELECT source_bo, source_id, source_item, pool,
       SUM(CASE WHEN status='active' AND quantity_sign='normal'
                THEN amount ELSE 0 END)
     - SUM(CASE WHEN status='active' AND quantity_sign='red'
                THEN amount ELSE 0 END) AS consumed_amount
FROM doc_flow_edges
GROUP BY source_bo, source_id, source_item, pool
"""


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _view_exists(conn, view):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'view' AND name = ?",
        [view]).fetchone()
    return row is not None


# ---------------------------------------------------------------------- rules

def _do_rules(conn):
    if not _table_exists(conn, RULE_TABLE):
        print('[v254] SKIP: %s 表不存在（未写规则）' % RULE_TABLE)
        return 0
    now = datetime.now().isoformat(timespec='seconds')
    written = 0
    for (rule_id, source_bo, target_bo, qty_field, pool) in RULES:
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
                status='active',
                updated_at=excluded.updated_at
            """,
            (rule_id, source_bo, target_bo, qty_field, pool, now, now))
        written += 1
        print('[v254] UPSERT: 规则 %s（pool=%s）' % (rule_id, pool))
    return written


def _do_amount_view(conn):
    if not _table_exists(conn, EDGE_TABLE):
        print('[v254] SKIP: %s 表不存在（未建视图）' % EDGE_TABLE)
        return False
    conn.execute(AMOUNT_VIEW_SQL)
    print('[v254] CREATE: 视图 %s' % AMOUNT_VIEW)
    return True


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v254] 开始: 采购发票单据流转规则 + 金额消耗视图')
    conn = _connect(db_path)
    try:
        _do_rules(conn)
        _do_amount_view(conn)
        conn.commit()
        print('[v254] 完成: 采购发票单据流转规则 + 金额消耗视图')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    problems = []
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, RULE_TABLE):
            problems.append('缺少表 %s' % RULE_TABLE)
        else:
            for (rule_id, source_bo, target_bo, qty_field, pool) in RULES:
                row = conn.execute(
                    'SELECT source_bo, target_bo, source_qty_field, pool, status '
                    'FROM %s WHERE rule_id = ?' % RULE_TABLE, [rule_id]).fetchone()
                if not row:
                    problems.append('缺少规则 %s' % rule_id)
                    continue
                expected = (source_bo, target_bo, qty_field, pool, 'active')
                if tuple(row) != expected:
                    problems.append('规则 %s 配置漂移: %r（期望 %r）'
                                    % (rule_id, tuple(row), expected))
        if not _view_exists(conn, AMOUNT_VIEW):
            problems.append('缺少视图 %s' % AMOUNT_VIEW)
        elif _view_exists(conn, 'v_doc_flow_consumed_qty'):
            cols = [row[1] for row in
                    conn.execute('PRAGMA table_info(v_doc_flow_consumed_qty)')]
            if len(cols) != 5:
                problems.append('既有视图 v_doc_flow_consumed_qty 列数变更为 %d'
                                % len(cols))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v254] FAIL: %s' % problem)
        return False
    print('[v254] PASS: 3 条流转规则 + 金额消耗视图齐备')
    return True


# ------------------------------------------------------------------ rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v254] 开始: 回滚采购发票单据流转规则 + 金额消耗视图')
    conn = _connect(db_path)
    try:
        if _view_exists(conn, AMOUNT_VIEW):
            conn.execute('DROP VIEW IF EXISTS %s' % AMOUNT_VIEW)
        if _table_exists(conn, RULE_TABLE):
            placeholders = ', '.join('?' for _ in RULE_IDS)
            conn.execute('DELETE FROM %s WHERE rule_id IN (%s)'
                         % (RULE_TABLE, placeholders), list(RULE_IDS))
        conn.commit()
        print('[v254] 完成: 已删除 3 条规则与金额消耗视图')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()