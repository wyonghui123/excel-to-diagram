# -*- coding: utf-8 -*-
"""v240 —— 销售发票贷项反向 doc_flow 规则（B7）。

背景：
  红冲 / 贷项行数量为负，`doc_flow_attach.attach_edge` 对 qty <= 0 直接
  返回 False，原发票行 → 贷项行的流转事实边缺失。B7 改为按原行引用写
  正数量边，需要一条独立规则（source_bo 与原规则不同，Σ 池隔离）。

内容：
  1. doc_flow_rule 种子 customer_invoice_to_credit_memo
     （source_bo=target_bo=customer_invoice_line，
      source_qty_field=qty，pool=billing）
  2. verify：规则存在且 status='active'
  3. rollback：删除规则

幂等：ON CONFLICT(rule_id) DO UPDATE（与 v236 `_do_rule` 同口径）。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATION_NAME = 'v240__customer_invoice_credit_doc_flow'

RULE_TABLE = 'doc_flow_rule'
RULE_ID = 'customer_invoice_to_credit_memo'
RULE = {
    'rule_id': RULE_ID,
    'source_bo': 'customer_invoice_line',
    'target_bo': 'customer_invoice_line',
    'source_qty_field': 'qty',
    'pool': 'billing',
}


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _do_rule(conn):
    if not _table_exists(conn, RULE_TABLE):
        print('[v240] SKIP: %s 表不存在' % RULE_TABLE)
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
    print('[v240] doc_flow 规则 %s 已写入（pool=%s）'
          % (RULE_ID, RULE['pool']))
    return True


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v240] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, RULE_TABLE):
            print('[v240] SKIP: %s 表不存在' % RULE_TABLE)
            return False
        _do_rule(conn)
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
            print('[v240] verify: 缺表 %s' % RULE_TABLE)
            return False
        row = conn.execute(
            'SELECT status, pool FROM %s WHERE rule_id = ?' % RULE_TABLE,
            [RULE_ID]).fetchone()
        if not row:
            print('[v240] verify: 缺规则 %s' % RULE_ID)
            return False
        if row[0] != 'active':
            print('[v240] verify: 规则 %s 非 active（%s）' % (RULE_ID, row[0]))
            return False
        if row[1] != RULE['pool']:
            print('[v240] verify: 规则 %s pool 不符（%s）' % (RULE_ID, row[1]))
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
        if not _table_exists(conn, RULE_TABLE):
            return False
        conn.execute('DELETE FROM %s WHERE rule_id = ?' % RULE_TABLE, [RULE_ID])
        conn.commit()
        print('[v240] rollback: 已删除规则 %s' % RULE_ID)
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)
