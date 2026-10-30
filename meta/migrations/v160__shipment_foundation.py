# -*- coding: utf-8 -*-
"""[v160] 交货单地基（shipments / shipment_lines）+ 计划行交付列

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.2 对象模型 / §10.8 迁移

设计:
  · 两张表由 `shipment.yaml` / `shipment_line.yaml` 声明、`sync_schema` 生成；
    本迁移只做「断言 + 兜底 CREATE + 补列 + 补索引」，不手写完整业务约束
  · `sales_order_schedules` 增两列：
      delivery_id     INTEGER NULL        —— 最近一次交货单（仅展示，非事实源）
      delivered_qty   REAL NOT NULL DEFAULT 0 —— 累计交付量，ship confirm 唯一写者
  · delivered_qty 是 D10 派生 partial 的唯一输入，必须 NOT NULL DEFAULT 0，
    避免 COALESCE 在聚合里掩盖 NULL 与 0 的语义差异

幂等:
  表 / 列 / 索引先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删索引 + 删表（先 shipment_lines 后 shipments）+ 尽量删列
  （SQLite 旧版不支持 DROP COLUMN 时打印 [KEEP]）。
"""
import sqlite3
import sys
from pathlib import Path

SHIPMENTS_TABLE = 'shipments'
LINES_TABLE = 'shipment_lines'
SCHEDULE_TABLE = 'sales_order_schedules'

SHIPMENTS_DDL = """
CREATE TABLE IF NOT EXISTS shipments (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_no           TEXT NOT NULL,
    order_id              INTEGER NOT NULL,
    ship_from_location_id INTEGER NOT NULL,
    ship_to_party_id      INTEGER NULL,
    ship_to_address_text  TEXT NOT NULL,
    carrier_name          TEXT NULL,
    tracking_no           TEXT NULL,
    waybill_no            TEXT NULL,
    planned_ship_date     TEXT NULL,
    actual_ship_date      TEXT NULL,
    actual_arrival_date   TEXT NULL,
    signature_ref         TEXT NULL,
    status                TEXT NOT NULL DEFAULT 'draft',
    source                TEXT NOT NULL DEFAULT 'manual',
    remark                TEXT NULL,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

LINES_DDL = """
CREATE TABLE IF NOT EXISTS shipment_lines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id   INTEGER NOT NULL,
    schedule_id   INTEGER NOT NULL,
    order_line_id INTEGER NOT NULL,
    item_id       INTEGER NOT NULL,
    uom_id        INTEGER NOT NULL,
    qty           REAL NOT NULL,
    lot_no        TEXT NULL,
    serial_no     TEXT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

INDEXES = (
    ('uq_shipment_delivery_no',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_delivery_no '
     f'ON {SHIPMENTS_TABLE}(delivery_no)'),
    ('idx_shipment_order_status',
     f'CREATE INDEX IF NOT EXISTS idx_shipment_order_status '
     f'ON {SHIPMENTS_TABLE}(order_id, status)'),
    ('idx_shipment_line_delivery',
     f'CREATE INDEX IF NOT EXISTS idx_shipment_line_delivery '
     f'ON {LINES_TABLE}(delivery_id)'),
    ('idx_shipment_line_schedule',
     f'CREATE INDEX IF NOT EXISTS idx_shipment_line_schedule '
     f'ON {LINES_TABLE}(schedule_id)'),
)

# 计划行新增列：(列名, DDL 片段)
SCHEDULE_COLUMNS = (
    ('delivery_id', 'INTEGER NULL'),
    ('delivered_qty', 'REAL NOT NULL DEFAULT 0'),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> bool:
    if name in _columns(conn, table):
        print(f'  - [SKIP] 列 {table}.{name} 已存在')
        return False
    conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')
    print(f'  - [ADD] 列 {table}.{name}')
    return True


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v160] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v160] 开始: 交货单地基')

        if _table_exists(conn, SHIPMENTS_TABLE):
            print(f'  - [SKIP] 表 {SHIPMENTS_TABLE} 已存在')
        else:
            conn.execute(SHIPMENTS_DDL)
            print(f'  - [CREATE] 表 {SHIPMENTS_TABLE}')

        if _table_exists(conn, LINES_TABLE):
            print(f'  - [SKIP] 表 {LINES_TABLE} 已存在')
        else:
            conn.execute(LINES_DDL)
            print(f'  - [CREATE] 表 {LINES_TABLE}')

        for name, sql in INDEXES:
            if _index_exists(conn, name):
                print(f'  - [SKIP] 索引 {name} 已存在')
            else:
                conn.execute(sql)
                print(f'  - [ADD] 索引 {name}')

        # 计划行两列：表由 sync_schema 建；这里仅补列，缺表则明确失败
        if not _table_exists(conn, SCHEDULE_TABLE):
            print(f'  - [FAIL] 缺表 {SCHEDULE_TABLE}'
                  '（请先 sync_schema --execute 建表后重跑本迁移）')
            conn.rollback()
            return False
        for name, ddl in SCHEDULE_COLUMNS:
            _ensure_column(conn, SCHEDULE_TABLE, name, ddl)

        conn.commit()
        print('[v160] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v160] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v160 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table in (SHIPMENTS_TABLE, LINES_TABLE):
            if not _table_exists(conn, table):
                print('[v160 verify] FAIL: 缺表 %s' % table)
                ok = False

        if _table_exists(conn, SHIPMENTS_TABLE):
            have = _columns(conn, SHIPMENTS_TABLE)
            for col in ('delivery_no', 'order_id', 'ship_from_location_id',
                        'ship_to_address_text', 'status', 'source'):
                if col not in have:
                    print('[v160 verify] FAIL: 缺列 %s.%s' % (SHIPMENTS_TABLE, col))
                    ok = False

        if _table_exists(conn, LINES_TABLE):
            have = _columns(conn, LINES_TABLE)
            for col in ('delivery_id', 'schedule_id', 'order_line_id',
                        'item_id', 'uom_id', 'qty', 'status'):
                if col not in have:
                    print('[v160 verify] FAIL: 缺列 %s.%s' % (LINES_TABLE, col))
                    ok = False

        if not _table_exists(conn, SCHEDULE_TABLE):
            print('[v160 verify] FAIL: 缺表 %s' % SCHEDULE_TABLE)
            ok = False
        else:
            have = _columns(conn, SCHEDULE_TABLE)
            for name, _ddl in SCHEDULE_COLUMNS:
                if name not in have:
                    print('[v160 verify] FAIL: 缺列 %s.%s' % (SCHEDULE_TABLE, name))
                    ok = False

        for name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v160 verify] FAIL: 缺索引 %s' % name)
                ok = False

        print('[v160 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v160 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')
            else:
                print(f'  - [SKIP] 索引 {name} 不存在')

        for table in (LINES_TABLE, SHIPMENTS_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')
            else:
                print(f'  - [SKIP] 表 {table} 不存在')

        if _table_exists(conn, SCHEDULE_TABLE):
            have = _columns(conn, SCHEDULE_TABLE)
            for name, _ddl in SCHEDULE_COLUMNS:
                if name not in have:
                    print(f'  - [SKIP] 列 {SCHEDULE_TABLE}.{name} 不存在')
                    continue
                try:
                    conn.execute(f'ALTER TABLE {SCHEDULE_TABLE} DROP COLUMN {name}')
                    print(f'  - [DROP] 列 {SCHEDULE_TABLE}.{name}')
                except sqlite3.OperationalError as e:
                    print(f'  - [KEEP] 无法删除列 {name}（{e}），保留残留列')
        else:
            print(f'  - [SKIP] 表 {SCHEDULE_TABLE} 不存在')

        conn.commit()
        print('[v160 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v160 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)
