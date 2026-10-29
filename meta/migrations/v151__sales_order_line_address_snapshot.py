# -*- coding: utf-8 -*-
"""[v151] 销售订单行地址文本快照列（B7）

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/spec.md D2 / §9.3

设计:
  · 行本身不存地址引用列，只存两列文本快照（确认时由守卫服务按抬头快照逐行写入）
  · 列由 `sales_order_line.yaml` 声明、`sync_schema` 生成；本迁移只做「断言 + 兜底 ADD + 存量回填」
  · 存量回填取抬头已冻结的地址快照（抬头为空则保持 NULL，不编造）

幂等:
  列已存在则 [SKIP]；回填只更新 NULL 行，重复执行终态一致。

回滚:
  SQLite 3.35+ 支持 DROP COLUMN，低版本打印告警后跳过（数据列残留无副作用）。
"""
import sqlite3
import sys
from pathlib import Path

TABLE = 'sales_order_lines'
PARENT_TABLE = 'sales_orders'
COLUMNS = (
    ('ship_to_address_text', 'TEXT NULL'),
    ('bill_to_address_text', 'TEXT NULL'),
)


def _column_names(conn: sqlite3.Connection, table: str) -> set:
    try:
        rows = conn.execute(f'PRAGMA table_info({table})').fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row[1] for row in rows}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v151] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v151] 开始: 销售订单行地址文本快照')

        if not _table_exists(conn, TABLE):
            print(f'  - [FAIL] 缺表 {TABLE}')
            return False

        existing = _column_names(conn, TABLE)
        for name, ddl in COLUMNS:
            if name in existing:
                print(f'  - [SKIP] 列 {TABLE}.{name} 已存在')
            else:
                conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}')
                print(f'  - [ADD] 列 {TABLE}.{name}')

        # 存量回填：抬头已确认并冻结的快照 → 行（只补 NULL，不覆盖已有值）
        if _table_exists(conn, PARENT_TABLE):
            for name, _ddl in COLUMNS:
                cursor = conn.execute(
                    f'UPDATE {TABLE} SET {name} = ('
                    f'  SELECT o.{name} FROM {PARENT_TABLE} o'
                    f'  WHERE o.id = {TABLE}.order_id)'
                    f' WHERE {name} IS NULL AND EXISTS ('
                    f'  SELECT 1 FROM {PARENT_TABLE} o'
                    f'  WHERE o.id = {TABLE}.order_id'
                    f'    AND o.{name} IS NOT NULL)')
                print(f'  - [BACKFILL] {name}: {cursor.rowcount} 行')
        else:
            print(f'  - [SKIP] 表 {PARENT_TABLE} 不存在，跳过回填')

        conn.commit()
        print('[v151] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v151] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v151 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, TABLE):
            print('[v151 verify] FAIL: 缺表 %s' % TABLE)
            return False
        existing = _column_names(conn, TABLE)
        for name, _ddl in COLUMNS:
            if name not in existing:
                print('[v151 verify] FAIL: 缺列 %s.%s' % (TABLE, name))
                ok = False
        print('[v151 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v151 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        existing = _column_names(conn, TABLE)
        for name, _ddl in COLUMNS:
            if name not in existing:
                print(f'  - [SKIP] 列 {TABLE}.{name} 不存在')
                continue
            try:
                conn.execute(f'ALTER TABLE {TABLE} DROP COLUMN {name}')
                print(f'  - [DROP] 列 {TABLE}.{name}')
            except sqlite3.OperationalError as e:
                print(f'  - [WARN] 无法删除列 {name}（{e}），保留残留列')
        conn.commit()
        print('[v151 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v151 rollback] 失败: %s' % e)
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
