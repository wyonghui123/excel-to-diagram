# -*- coding: utf-8 -*-
"""v241 —— 销售发票计划期次开票（S8 Wave B）。

背景：
  Wave A 发票行来源仅 shipment / sales_order / manual。Wave B 支持从
  `sales_order_schedules(schedule_kind='billing')` 期次直接开票，需要：
    1. 一条 source_bo=sales_order_schedule 的 doc_flow 规则，让期次 →
       发票行（customer_invoice_line）的流转事实边可被 attach；
    2. 到期清单查询（schedule_kind + billing_status + promised_date）
       的联合索引。

内容：
  1. doc_flow_rule 种子 billing_schedule_to_customer_invoice
     （source_bo=sales_order_schedule，target_bo=customer_invoice_line，
      source_qty_field=billing_percent，pool=billing）
  2. 索引 idx_sos_billing_due(schedule_kind, billing_status, promised_date)
  3. verify：规则存在且 status='active'、pool 正确；索引存在
  4. rollback：删除规则与索引

幂等：规则 ON CONFLICT(rule_id) DO UPDATE（与 v240 同口径）；
      索引 CREATE INDEX IF NOT EXISTS。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATION_NAME = 'v241__customer_invoice_billing_plan'

RULE_TABLE = 'doc_flow_rule'
RULE_ID = 'billing_schedule_to_customer_invoice'
RULE = {
    'rule_id': RULE_ID,
    'source_bo': 'sales_order_schedule',
    'target_bo': 'customer_invoice_line',
    'source_qty_field': 'billing_percent',
    'pool': 'billing',
}

SCHEDULE_TABLE = 'sales_order_schedules'
INDEX_NAME = 'idx_sos_billing_due'
INDEX_SQL = (
    'CREATE INDEX IF NOT EXISTS %s ON %s '
    '(schedule_kind, billing_status, promised_date)' % (INDEX_NAME, SCHEDULE_TABLE)
)


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _index_exists(conn, index):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
        [index]).fetchone()
    return row is not None


def _do_rule(conn):
    if not _table_exists(conn, RULE_TABLE):
        print('[v241] SKIP: %s 表不存在' % RULE_TABLE)
        return False
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
            status='active',
            updated_at=excluded.updated_at
        """,
        (RULE['rule_id'], RULE['source_bo'], RULE['target_bo'],
         RULE['source_qty_field'], RULE['pool'], now, now))
    print('[v241] doc_flow 规则 %s 已写入（pool=%s）'
          % (RULE_ID, RULE['pool']))
    return True


def _do_index(conn):
    if not _table_exists(conn, SCHEDULE_TABLE):
        print('[v241] SKIP: %s 表不存在（索引未建）' % SCHEDULE_TABLE)
        return False
    conn.execute(INDEX_SQL)
    print('[v241] 索引 %s 已建立' % INDEX_NAME)
    return True


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v241] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, RULE_TABLE):
            print('[v241] SKIP: %s 表不存在' % RULE_TABLE)
            return False
        _do_rule(conn)
        _do_index(conn)
        conn.commit()
        return True
    finally:
        conn.close()


def verify(db_path):
    path = Path(db_path)
    if not path.exists():
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, RULE_TABLE):
            print('[v241] verify: 缺表 %s' % RULE_TABLE)
            return False
        row = conn.execute(
            'SELECT status, pool FROM %s WHERE rule_id = ?' % RULE_TABLE,
            [RULE_ID]).fetchone()
        if not row:
            print('[v241] verify: 缺规则 %s' % RULE_ID)
            return False
        if row[0] != 'active':
            print('[v241] verify: 规则 %s 非 active（%s）' % (RULE_ID, row[0]))
            return False
        if row[1] != RULE['pool']:
            print('[v241] verify: 规则 %s pool 不符（%s）' % (RULE_ID, row[1]))
            return False
        if not _index_exists(conn, INDEX_NAME):
            print('[v241] verify: 缺索引 %s' % INDEX_NAME)
            return False
        return True
    finally:
        conn.close()


def rollback(db_path):
    path = Path(db_path)
    if not path.exists():
        return False

    conn = _connect(path)
    try:
        if _table_exists(conn, RULE_TABLE):
            conn.execute('DELETE FROM %s WHERE rule_id = ?' % RULE_TABLE,
                         [RULE_ID])
        if _index_exists(conn, INDEX_NAME):
            conn.execute('DROP INDEX %s' % INDEX_NAME)
        conn.commit()
        print('[v241] rollback: 已删除规则 %s 与索引 %s'
              % (RULE_ID, INDEX_NAME))
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)