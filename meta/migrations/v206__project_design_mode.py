# -*- coding: utf-8 -*-
"""[v206 2026-11-04] 项目设计模式（G15 ETO）

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md

范围:
  1. projects 新增 design_mode（VARCHAR(20) NOT NULL DEFAULT 'standard'）：
       standard   标准产品交付
       engineered 按单设计（ETO）
  2. 不改其他表结构、不加权限 / 菜单 / 参数。

口径:
  · design_mode 只是行为开关（驱动 ETO 校验与 UI），不承载成本口径，也不决定 BOM 归属。
  · 存量项目一律回填 standard，与现状行为一致。

幂等:
  先查 pragma table_info 后加列；重复执行打印 [SKIP]。

回滚:
  SQLite 3.35+ 支持 DROP COLUMN；若 design_mode 已承载非默认值，拒绝回滚以保留事实。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v206__project_design_mode'

TABLE = 'projects'
COLUMN = 'design_mode'
COLUMN_DDL = "VARCHAR(20) NOT NULL DEFAULT 'standard'"
VALID_VALUES = ('standard', 'engineered')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    return any(row[1] == column for row in rows)


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TABLE):
        print('  - [SKIP] %s 不存在' % TABLE)
        return
    if _column_exists(conn, TABLE, COLUMN):
        print('  - [SKIP] %s.%s 已存在' % (TABLE, COLUMN))
        return
    conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (TABLE, COLUMN, COLUMN_DDL))
    print('  - [ADD] %s.%s %s' % (TABLE, COLUMN, COLUMN_DDL))


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TABLE) or not _column_exists(conn, TABLE, COLUMN):
        print('  - [SKIP] %s.%s 不存在' % (TABLE, COLUMN))
        return
    used = conn.execute(
        "SELECT 1 FROM %s WHERE %s <> 'standard' LIMIT 1" % (TABLE, COLUMN)
    ).fetchone()
    if used:
        print('  - [SKIP] %s.%s 已有 engineered 数据，保留列' % (TABLE, COLUMN))
        return
    conn.execute('ALTER TABLE %s DROP COLUMN %s' % (TABLE, COLUMN))
    print('  - [DEL] %s.%s' % (TABLE, COLUMN))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v206] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v206] 开始: 项目设计模式（G15 ETO）')
        _do_upgrade(conn)
        conn.commit()
        print('[v206] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v206] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v206 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, TABLE):
            print('[v206 verify] FAIL: 缺表 %s' % TABLE)
            return False
        if not _column_exists(conn, TABLE, COLUMN):
            print('[v206 verify] FAIL: 缺列 %s.%s' % (TABLE, COLUMN))
            return False
        bad = conn.execute(
            "SELECT COUNT(*) FROM %s WHERE %s IS NULL OR %s NOT IN (%s)"
            % (TABLE, COLUMN, COLUMN,
               ', '.join("'%s'" % v for v in VALID_VALUES))
        ).fetchone()[0]
        if bad:
            print('[v206 verify] FAIL: %s 条项目 design_mode 非法' % bad)
            return False
        print('[v206 verify] PASS')
        return True
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print(migrate(Path(sys.argv[1]), skip_backup=True))
        print(verify(Path(sys.argv[1])))
