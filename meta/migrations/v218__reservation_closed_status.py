# -*- coding: utf-8 -*-
"""[v218 2026-11-05] 预留状态新增 closed（INV-2 L0 收口）

依据:
  docs/specs/inv2-reservation-atp/spec.md §3.3 / §12.4

范围:
  1. 重建 inventory_reservations，把 status CHECK 扩展到
     open / partially_fulfilled / fulfilled / cancelled / closed / expired。
  2. 保留全部数据与既有索引；不新增列、不改权限 / 菜单 / 参数。

口径:
  · closed = 终止履行并保留历史，与 cancelled（承诺作废）区分。
  · 仅在旧表存在 status CHECK 且未包含 closed 时重建；无 CHECK 的库跳过。

回滚:
  closed 行先降级为 cancelled，再重建回旧 CHECK（避免回滚后数据违约）。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v218__reservation_closed_status'

TABLE = 'inventory_reservations'
NEW_TABLE = 'inventory_reservations_v218'
OLD_TABLE = 'inventory_reservations_old_v218'

DDL_NEW = """
CREATE TABLE IF NOT EXISTS inventory_reservations_v218 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_no VARCHAR(32) NOT NULL UNIQUE,
    org_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    uom_id INTEGER NOT NULL,
    demand_object_type VARCHAR(30) NOT NULL,
    demand_object_id INTEGER NOT NULL,
    demand_line_id INTEGER NOT NULL DEFAULT 0,
    location_id INTEGER,
    batch_id INTEGER,
    stock_segment_type VARCHAR(20) NOT NULL DEFAULT 'owned',
    project_id INTEGER NOT NULL DEFAULT 0,
    project_task_id INTEGER NOT NULL DEFAULT 0,
    sales_order_line_id INTEGER NOT NULL DEFAULT 0,
    owner_party_id INTEGER NOT NULL DEFAULT 0,
    qty_reserved REAL NOT NULL DEFAULT 0,
    qty_fulfilled REAL NOT NULL DEFAULT 0,
    peg_type VARCHAR(10) NOT NULL DEFAULT 'soft',
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    valid_from DATETIME,
    valid_to DATETIME,
    source_doc_type VARCHAR(50),
    source_doc_id INTEGER,
    source_line_id INTEGER,
    reservation_key VARCHAR(200) NOT NULL,
    remark TEXT,
    created_by VARCHAR(200),
    created_at DATETIME,
    updated_by VARCHAR(200),
    updated_at DATETIME,
    CHECK (qty_reserved > 0),
    CHECK (qty_fulfilled >= 0),
    CHECK (qty_fulfilled <= qty_reserved),
    CHECK (peg_type IN ('hard', 'soft')),
    CHECK (status IN ('open', 'partially_fulfilled', 'fulfilled',
                      'cancelled', 'closed', 'expired'))
)
"""

DDL_OLD = DDL_NEW.replace(NEW_TABLE, OLD_TABLE).replace(
    "'cancelled', 'closed', 'expired'", "'cancelled', 'expired'")


def _table_sql(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone()
    return row[0] if row else None


def _columns(conn: sqlite3.Connection, name: str):
    return [row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % name).fetchall()]


def _index_sql(conn: sqlite3.Connection):
    return [row[0] for row in conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
        "AND sql IS NOT NULL", (TABLE,)).fetchall()]


def _rebuild(conn: sqlite3.Connection, ddl: str, new_table: str) -> None:
    indexes = _index_sql(conn)
    columns = _columns(conn, TABLE)
    column_list = ', '.join(columns)
    conn.execute(ddl)
    conn.execute(
        'INSERT INTO %s (%s) SELECT %s FROM %s'
        % (new_table, column_list, column_list, TABLE))
    conn.execute('DROP TABLE %s' % TABLE)
    conn.execute('ALTER TABLE %s RENAME TO %s' % (new_table, TABLE))
    for sql in indexes:
        conn.execute(sql)
    print('  - [REBUILD] %s（保留 %s 列 / %s 个索引）'
          % (TABLE, len(columns), len(indexes)))


def apply_closed_status(conn: sqlite3.Connection) -> None:
    """迁移与内存测试替身共用：有旧 CHECK 时重建，已含 closed 则跳过。"""
    ddl = _table_sql(conn, TABLE)
    if ddl is None:
        print('  - [SKIP] 表 %s 不存在' % TABLE)
        return
    normalized = ddl.lower()
    if 'check (status in' not in normalized:
        print('  - [SKIP] %s 无 status CHECK' % TABLE)
        return
    if "'closed'" in normalized:
        print('  - [SKIP] %s 已支持 closed' % TABLE)
        return
    _rebuild(conn, DDL_NEW, NEW_TABLE)


def _do_downgrade(conn: sqlite3.Connection) -> None:
    ddl = _table_sql(conn, TABLE)
    if ddl is None or "'closed'" not in (ddl or '').lower():
        print('  - [SKIP] %s 无需降级' % TABLE)
        return
    conn.execute(
        "UPDATE %s SET status='cancelled', updated_at=CURRENT_TIMESTAMP "
        "WHERE status='closed'" % TABLE)
    print('  - [DATA] closed → cancelled')
    _rebuild(conn, DDL_OLD, OLD_TABLE)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v218] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v218] 开始: 预留状态 closed')
        conn.execute('PRAGMA foreign_keys = OFF')
        apply_closed_status(conn)
        conn.commit()
        print('[v218] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v218] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v218 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ddl = _table_sql(conn, TABLE)
        ok = ddl is None or "'closed'" in ddl.lower()
        print('[v218 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v218 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        conn.execute('PRAGMA foreign_keys = OFF')
        _do_downgrade(conn)
        conn.commit()
        print('[v218 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v218 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback
