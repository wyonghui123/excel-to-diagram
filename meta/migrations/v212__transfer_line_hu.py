# -*- coding: utf-8 -*-
"""v212 - 调拨行增加包装容器列（P6a-2 §11.5 补充）。

spec §11.5 要求调拨「发运 / 收货」都能按容器执行；v211 只给收货行 /
发运行加了 hu_no，调拨行缺载体。本迁移补两列：

  · hu_no   VARCHAR(40)  调拨发运 / 收货的容器号（可空，非必填）
  · hu_type VARCHAR(20)  新建容器时的类型（可空，默认 service 侧 carton）

幂等：列已存在则 [SKIP]；verify / rollback 对称。
"""

import sqlite3
from pathlib import Path

TRANSFER_LINE_TABLE = 'transfer_order_lines'

LINE_COLUMNS = (
    (TRANSFER_LINE_TABLE, 'hu_no', 'VARCHAR(40)'),
    (TRANSFER_LINE_TABLE, 'hu_type', 'VARCHAR(20)'),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        return {row[1] for row in conn.execute(
            'PRAGMA table_info(%s)' % table).fetchall()}
    except sqlite3.Error:
        return set()


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v212] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v212] 开始: 调拨行包装容器列')
        for table, column, ddl_type in LINE_COLUMNS:
            if not _table_exists(conn, table):
                print('  - %s 表不存在, 跳过 %s 列' % (table, column))
                continue
            if column in _columns(conn, table):
                print('  - [SKIP] %s.%s 已存在' % (table, column))
                continue
            conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                         % (table, column, ddl_type))
            print('  - [NEW] %s.%s' % (table, column))
        conn.commit()
        print('[v212] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v212] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v212 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, TRANSFER_LINE_TABLE):
            print('[v212 verify] FAIL: 缺表 %s' % TRANSFER_LINE_TABLE)
            return False
        cols = _columns(conn, TRANSFER_LINE_TABLE)
        ok = True
        for _table, column, _ddl in LINE_COLUMNS:
            if column not in cols:
                print('[v212 verify] FAIL: %s 缺列 %s'
                      % (TRANSFER_LINE_TABLE, column))
                ok = False
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    """SQLite 不支持 DROP COLUMN（3.35 前），仅提示人工处理。"""
    if not db_path.exists():
        print('[v212 rollback] DB 不存在: %s' % db_path)
        return False
    print('[v212 rollback] SQLite 无法安全删除列；如需回退请从备份恢复')
    return False


downgrade = rollback
