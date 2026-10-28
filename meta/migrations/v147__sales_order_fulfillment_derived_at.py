# -*- coding: utf-8 -*-
"""[v147] 销售订单履约派生时间戳 fulfillment_derived_at

依据:
  docs/superpowers/specs/2026-10-28-sales-order-fulfillment-status-writeback-spec.md
    §3.1 FR-011（记录派生时间戳，便于巡检与排障）
    §5.1 字段（fulfillment_derived_at: datetime，记录最近一次派生时间）

背景:
  `fulfillment_status` 是物理冗余派生字段（由 delivery 计划行聚合回写）。
  派生值本身不携带「何时算的」信息，巡检无法区分：
    · 数据漂移（派生值算错了）      -> check_drift 的 lines/orders 段
    · 数据陈旧（派生后输入变了没重算）-> 需要时间戳
  本迁移给两张表补 `fulfillment_derived_at`，记录最近一次派生确认时间。

时钟口径:
  与服务层 `sales_order_fulfillment_service.py` 一致 —— SQLite `datetime('now')`
  （UTC，秒精度，`YYYY-MM-DD HH:MM:SS`），与 `updated_at` 同源同格式。

回填策略:
  存量行置「迁移时刻基线」（datetime('now')），不置 NULL。
  理由：置 NULL 会让存量行全部落入「陈旧」判定，噪音淹没真问题；
  基线语义 = 「迁移时点已确认过一次」，此后由服务层刷新。

幂等:
  列先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  列由 YAML 声明，保留（时间戳可由派生动作重新产生，清除无收益）。
"""
import sqlite3
import sys
from pathlib import Path

LINE_TABLE = 'sales_order_lines'
ORDER_TABLE = 'sales_orders'

DERIVED_AT_COLUMN = 'fulfillment_derived_at'

#: 迁移影响的两张表（顺序：先行后抬头，与 INV-2 一致）
TARGET_TABLES = (LINE_TABLE, ORDER_TABLE)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str,
                   ddl: str, default) -> bool:
    """返回 True = 本次新增。"""
    if column in _columns(conn, table):
        print(f'  - [SKIP] {table}.{column} 已存在')
        return False
    conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')
    if default is not None:
        conn.execute(f'UPDATE {table} SET {column} = ? WHERE {column} IS NULL',
                     (default,))
    print(f'  - [ADD] {table}.{column}')
    return True


def _now(conn: sqlite3.Connection) -> str:
    """与业务服务层同口径：UTC、秒精度、空格分隔。"""
    return conn.execute("SELECT datetime('now')").fetchone()[0]


def _count_null(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(
        f'SELECT COUNT(*) AS n FROM {table} WHERE {DERIVED_AT_COLUMN} IS NULL'
    ).fetchone()[0]


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用，
    缺少该参数会被静默跳过（v146 的坑）。"""
    if not db_path.exists():
        print(f'[v147] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v147] 开始: 补履约派生时间戳 %s' % DERIVED_AT_COLUMN)

        missing_tables = [t for t in TARGET_TABLES if not _table_exists(conn, t)]
        if missing_tables:
            print('[v147] 表不存在: %s（请先 sync_schema --execute 建表）'
                  % ', '.join(missing_tables))
            return False

        baseline = _now(conn)
        for table in TARGET_TABLES:
            _ensure_column(conn, table, DERIVED_AT_COLUMN, 'TEXT', baseline)

        for table in TARGET_TABLES:
            nulls = _count_null(conn, table)
            print(f'  - [BASELINE] {table}: 基线 {baseline}，'
                  f'NULL 残留 {nulls} 条')

        conn.commit()
        print('[v147] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v147] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v147 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table in TARGET_TABLES:
            if DERIVED_AT_COLUMN not in _columns(conn, table):
                print('[v147 verify] FAIL: %s 缺列 %s' % (table, DERIVED_AT_COLUMN))
                ok = False
                continue
            nulls = _count_null(conn, table)
            total = conn.execute(
                f'SELECT COUNT(*) AS n FROM {table}').fetchone()[0]
            print('[v147 verify] %s: %d 行，NULL %d 条' % (table, total, nulls))
            if nulls:
                print('[v147 verify] FAIL: %s 存在 NULL 基线' % table)
                ok = False
        print('[v147 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    """列由 YAML 声明，保留；仅提示。"""
    if not db_path.exists():
        print('[v147 rollback] DB 不存在: %s' % db_path)
        return False
    print('  - [KEEP] %s 列保留（由 YAML 声明；清空无收益，'
          '派生动作会重新写入）' % DERIVED_AT_COLUMN)
    return True


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
