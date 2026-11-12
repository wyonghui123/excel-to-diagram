# -*- coding: utf-8 -*-
"""[v171 2026-11-01] 单据类型命名统一 —— sales_orders.order_type_id → document_type_id

依据:
  docs/specs/spec-procurement-task-object-model-2026-10-31.md T-D20（单据类型规范）

规范:
  业务单据头的类型列统一命名 `document_type_id`，与平台切面
  `document_type_aspect`（meta/schemas/aspects.yaml）同名同义。
  销售订单是最后一张仍沿用 `order_type_id` 的单据。

本迁移（幂等）:
  ① `sales_orders.order_type_id` → `document_type_id`
  ② 旧索引 `idx_sales_order_type` → `idx_sales_order_document_type`
     （SQLite 的 RENAME COLUMN 只改写索引定义、不重命名索引，故需手工换名）

SQLite 3.25+ 的 `ALTER TABLE ... RENAME COLUMN` 会同步改写 FK 定义，
故无需重建表；重复执行时按「旧列存在且新列不存在」判定。

注意:
  `pricing_determinations.order_type_id` 是取价规则维度，不是单据头字段，
  本迁移不动它。

回滚: 反向改名。
"""
import sqlite3
import sys
from pathlib import Path

TABLE = 'sales_orders'
OLD_COLUMN = 'order_type_id'
NEW_COLUMN = 'document_type_id'
OLD_INDEX = 'idx_sales_order_type'
NEW_INDEX = 'idx_sales_order_document_type'


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


def _rename(conn: sqlite3.Connection, old: str, new: str) -> str:
    cols = _columns(conn, TABLE)
    if not cols:                      # 新库由 YAML 直接建新列名
        return 'skip_missing_table'
    if new in cols and old not in cols:
        return 'skip_done'
    if old not in cols:
        return 'skip_no_old'
    conn.execute(f'ALTER TABLE {TABLE} RENAME COLUMN {old} TO {new}')
    return 'renamed'


def _swap_index(conn: sqlite3.Connection) -> None:
    if _index_exists(conn, OLD_INDEX):
        conn.execute(f'DROP INDEX IF EXISTS {OLD_INDEX}')
        print(f'  - [DROP] 索引 {OLD_INDEX}')
    if _index_exists(conn, NEW_INDEX):
        print(f'  - [SKIP] 索引 {NEW_INDEX} 已存在')
        return
    conn.execute(
        f'CREATE INDEX IF NOT EXISTS {NEW_INDEX} ON {TABLE}({NEW_COLUMN})')
    print(f'  - [ADD] 索引 {NEW_INDEX}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v171] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v171] 开始: sales_orders 类型列命名统一')
        conn.execute('PRAGMA foreign_keys = OFF')
        result = _rename(conn, OLD_COLUMN, NEW_COLUMN)
        print(f'  - [{result.upper()}] {TABLE}.{OLD_COLUMN} → {NEW_COLUMN}')
        _swap_index(conn)
        conn.commit()
        print('[v171] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v171] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v171 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        cols = _columns(conn, TABLE)
        if not cols:
            print(f'[v171 verify] SKIP: 缺表 {TABLE}')
            print('[v171 verify] PASS')
            return True

        ok = True
        if OLD_COLUMN in cols:
            print(f'[v171 verify] FAIL: {TABLE}.{OLD_COLUMN} 仍存在')
            ok = False
        if NEW_COLUMN not in cols:
            print(f'[v171 verify] FAIL: 缺列 {TABLE}.{NEW_COLUMN}')
            ok = False
        if not _index_exists(conn, NEW_INDEX):
            print(f'[v171 verify] FAIL: 缺索引 {NEW_INDEX}')
            ok = False
        if _index_exists(conn, OLD_INDEX):
            print(f'[v171 verify] FAIL: 旧索引 {OLD_INDEX} 仍存在')
            ok = False

        total = conn.execute(f'SELECT COUNT(*) FROM {TABLE}').fetchone()[0]
        nulls = conn.execute(
            f'SELECT COUNT(*) FROM {TABLE} WHERE {NEW_COLUMN} IS NULL').fetchone()[0]
        print(f'[v171 verify] {TABLE}: {total} 行，NULL {NEW_COLUMN} {nulls} 条')

        print('[v171 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v171 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v171 rollback] 列名恢复 order_type_id')
        conn.execute('PRAGMA foreign_keys = OFF')
        result = _rename(conn, NEW_COLUMN, OLD_COLUMN)
        print(f'  - [{result.upper()}] {TABLE}.{NEW_COLUMN} → {OLD_COLUMN}')
        if _index_exists(conn, NEW_INDEX):
            conn.execute(f'DROP INDEX IF EXISTS {NEW_INDEX}')
            print(f'  - [DROP] 索引 {NEW_INDEX}')
        if _columns(conn, TABLE) and not _index_exists(conn, OLD_INDEX):
            conn.execute(f'CREATE INDEX IF NOT EXISTS {OLD_INDEX} ON {TABLE}({OLD_COLUMN})')
            print(f'  - [ADD] 索引 {OLD_INDEX}')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print('[v171 rollback] 失败: %s' % e)
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
