# -*- coding: utf-8 -*-
"""v248 —— 服务确认开票（TBD-11 A）。

背景：
  `sales_order_schedules` 的 service 期次（schedule_kind='service'，status
  ='completed'）是服务确认的事实源。TBD-11 A 支持从已兑现服务期次直接开票，
  需要一条 source_bo=sales_order_schedule 的 doc_flow 规则，让期次 → 发票行
  的流转事实边可被 attach（与 v241 的 billing 规则并列，口径同为 pool=billing）。

内容：
  1. doc_flow_rule 种子 service_confirmation_to_invoice_line
     （source_bo=sales_order_schedule，target_bo=customer_invoice_line，
      source_qty_field=promised_qty，pool=billing）
  2. 索引 idx_sos_service_due(schedule_kind, status, promised_date)
  3. 重建 customer_invoice_lines：来源互斥 CHECK 放行 service_confirmation
     （服务行与计划行一样携带 schedule_id；SQLite 无 ALTER CHECK，数据与索引原样保留）
  4. verify：规则存在且 status='active'、pool 正确；索引存在；来源 CHECK 已放行
  5. rollback：删除规则与索引（重建后的 CHECK 为超集，不回退，避免丢数据）

幂等：规则 ON CONFLICT(rule_id) DO UPDATE；索引 CREATE INDEX IF NOT EXISTS；
      重建前先查来源互斥 CHECK 是否已含 service_confirmation。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATION_NAME = 'v248__service_confirmation_invoice'

RULE_TABLE = 'doc_flow_rule'
RULE_ID = 'service_confirmation_to_invoice_line'
RULE = {
    'rule_id': RULE_ID,
    'source_bo': 'sales_order_schedule',
    'target_bo': 'customer_invoice_line',
    'source_qty_field': 'promised_qty',
    'pool': 'billing',
}

SCHEDULE_TABLE = 'sales_order_schedules'
INDEX_NAME = 'idx_sos_service_due'
INDEX_SQL = (
    'CREATE INDEX IF NOT EXISTS %s ON %s '
    '(schedule_kind, status, promised_date)' % (INDEX_NAME, SCHEDULE_TABLE)
)

LINE_TABLE = 'customer_invoice_lines'
#: 来源互斥 CHECK 的第二个枚举（只有这些来源可携带库存/期次来源列）
MUTUAL_ENUM_PREFIX = "source_doc_type IN ('shipment', 'billing_schedule'"


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


def _table_sql(conn, table):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row[0] if row else None


def _mutual_enum_bounds(sql):
    """定位来源互斥 CHECK 的第二个枚举 (start, end)，end 指向右括号。"""
    start = sql.find(MUTUAL_ENUM_PREFIX)
    if start < 0:
        return None
    end = sql.find(')', start)
    if end < 0:
        return None
    return start, end


def _source_type_supported(conn):
    """来源互斥 CHECK 是否已允许 service_confirmation 携带 schedule_id。"""
    sql = _table_sql(conn, LINE_TABLE) or ''
    bounds = _mutual_enum_bounds(sql)
    if not bounds:
        return False
    start, end = bounds
    return "'service_confirmation'" in sql[start:end]


def _do_rebuild_lines(conn):
    """SQLite 无 ALTER CHECK：重建表放行 service_confirmation 来源。"""
    if not _table_exists(conn, LINE_TABLE):
        print('[v248] SKIP: %s 表不存在（未扩展来源类型）' % LINE_TABLE)
        return False
    if _source_type_supported(conn):
        print('[v248] SKIP: %s 已允许 service_confirmation 携带期次'
              % LINE_TABLE)
        return False
    old_sql = _table_sql(conn, LINE_TABLE)
    bounds = _mutual_enum_bounds(old_sql)
    if not bounds:
        print('[v248] SKIP: %s 未找到来源互斥 CHECK（结构不符）' % LINE_TABLE)
        return False
    start, end = bounds
    new_sql = (old_sql[:start] + old_sql[start:end]
               + ", 'service_confirmation'" + old_sql[end:])

    tmp = LINE_TABLE + '__v248'
    old_columns = [row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % LINE_TABLE)]
    count = conn.execute('SELECT COUNT(*) FROM %s' % LINE_TABLE).fetchone()[0]
    index_sql = [row[0] for row in conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? "
        'AND sql IS NOT NULL', [LINE_TABLE]).fetchall()]

    new_sql = new_sql.replace(LINE_TABLE, tmp, 1)
    conn.execute('DROP TABLE IF EXISTS %s' % tmp)
    conn.execute(new_sql)
    new_columns = [row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % tmp)]
    shared = [column for column in new_columns if column in old_columns]
    columns = ', '.join(shared)
    conn.execute('INSERT INTO %s (%s) SELECT %s FROM %s'
                 % (tmp, columns, columns, LINE_TABLE))
    conn.execute('DROP TABLE %s' % LINE_TABLE)
    conn.execute('ALTER TABLE %s RENAME TO %s' % (tmp, LINE_TABLE))
    for statement in index_sql:
        conn.execute(statement)
    print('[v248] REBUILD: %s 来源类型扩展 service_confirmation（保留 %s 行）'
          % (LINE_TABLE, count))
    return True


def _do_rule(conn):
    if not _table_exists(conn, RULE_TABLE):
        print('[v248] SKIP: %s 表不存在' % RULE_TABLE)
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
    print('[v248] doc_flow 规则 %s 已写入（pool=%s）'
          % (RULE_ID, RULE['pool']))
    return True


def _do_index(conn):
    if not _table_exists(conn, SCHEDULE_TABLE):
        print('[v248] SKIP: %s 表不存在（索引未建）' % SCHEDULE_TABLE)
        return False
    conn.execute(INDEX_SQL)
    print('[v248] 索引 %s 已建立' % INDEX_NAME)
    return True


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v248] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, RULE_TABLE):
            print('[v248] SKIP: %s 表不存在' % RULE_TABLE)
            return False
        _do_rule(conn)
        _do_index(conn)
        _do_rebuild_lines(conn)
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
            print('[v248] verify: 缺表 %s' % RULE_TABLE)
            return False
        row = conn.execute(
            'SELECT status, pool FROM %s WHERE rule_id = ?' % RULE_TABLE,
            [RULE_ID]).fetchone()
        if not row:
            print('[v248] verify: 缺规则 %s' % RULE_ID)
            return False
        if row[0] != 'active':
            print('[v248] verify: 规则 %s 非 active（%s）' % (RULE_ID, row[0]))
            return False
        if row[1] != RULE['pool']:
            print('[v248] verify: 规则 %s pool 不符（%s）' % (RULE_ID, row[1]))
            return False
        if not _index_exists(conn, INDEX_NAME):
            print('[v248] verify: 缺索引 %s' % INDEX_NAME)
            return False
        if not _source_type_supported(conn):
            print('[v248] verify: %s 未放行 service_confirmation 来源'
                  % LINE_TABLE)
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
        print('[v248] rollback: 已删除规则 %s 与索引 %s'
              % (RULE_ID, INDEX_NAME))
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)