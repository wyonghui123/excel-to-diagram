# -*- coding: utf-8 -*-
"""[v133] 销售区域 M2：客户区域分配索引 + 菜单中文名收口

依据:
  docs/superpowers/specs/2026-10-26-sales-territory-design.md
    §3.3 落地命名清单（区域 → 销售区域）
    §4.4 territory_account_assignment（客户侧分配）
    §5 不变量 R-TER-6 / R-TER-7

背景:
  `territory_account_assignment` 由 YAML 声明（skip_auto_menu: true），
  表结构与索引随 sync_schema 建出；本迁移只做两件同步层的事：
  1. 补建 YAML 已声明的 4 条索引（缺失时补齐，建唯一索引前先查重复数据）
  2. 把 v132 建立的 `territory-list` 菜单中文名从「区域」改为「销售区域」
     （对象标识 / 表名 / 权限码不变；v132 的 _do_menus 对已存在行只 SKIP，
     故改名必须由独立迁移落库）

幂等:
  索引已存在只输出 [SKIP]；菜单名已是「销售区域」时只输出 [SKIP]。
  表不存在（未跑 sync_schema）时终止并返回 False。

回滚:
  删除本次补建的索引；菜单名改回「区域」。不删表（由 sync_schema 管理）。
"""
import sqlite3
from pathlib import Path

TERRITORY_TABLE = 'territories'
ASSIGNMENT_TABLE = 'territory_account_assignments'

UIDX_ASSIGN_TRIPLE = 'uq_taa_triple'
UIDX_ASSIGN_PRIMARY = 'uq_taa_primary'
IDX_ASSIGN_TERRITORY = 'idx_taa_territory'
IDX_ASSIGN_CUSTOMER = 'idx_taa_customer'

MENU_CODE = 'territory-list'
MENU_NAME_NEW = '销售区域'
MENU_NAME_OLD = '区域'

_INDEX_DDL = (
    (UIDX_ASSIGN_TRIPLE,
     f'CREATE UNIQUE INDEX IF NOT EXISTS {UIDX_ASSIGN_TRIPLE} '
     f'ON {ASSIGNMENT_TABLE} '
     f'(customer_account_id, territory_id, effective_from)'),
    (UIDX_ASSIGN_PRIMARY,
     f'CREATE UNIQUE INDEX IF NOT EXISTS {UIDX_ASSIGN_PRIMARY} '
     f'ON {ASSIGNMENT_TABLE} (customer_account_id, effective_from) '
     f'WHERE is_primary = 1'),
    (IDX_ASSIGN_TERRITORY,
     f'CREATE INDEX IF NOT EXISTS {IDX_ASSIGN_TERRITORY} '
     f'ON {ASSIGNMENT_TABLE} (territory_id)'),
    (IDX_ASSIGN_CUSTOMER,
     f'CREATE INDEX IF NOT EXISTS {IDX_ASSIGN_CUSTOMER} '
     f'ON {ASSIGNMENT_TABLE} (customer_account_id)'),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _duplicate_assignments(conn: sqlite3.Connection):
    return conn.execute(
        f'SELECT customer_account_id, territory_id, effective_from, '
        f'COUNT(*) AS n FROM {ASSIGNMENT_TABLE} '
        f'GROUP BY customer_account_id, territory_id, effective_from '
        f'HAVING n > 1').fetchall()


def _duplicate_primary(conn: sqlite3.Connection):
    return conn.execute(
        f'SELECT customer_account_id, effective_from, COUNT(*) AS n '
        f'FROM {ASSIGNMENT_TABLE} WHERE is_primary = 1 '
        f'GROUP BY customer_account_id, effective_from '
        f'HAVING n > 1').fetchall()


def _do_indexes(conn: sqlite3.Connection) -> bool:
    for table in (TERRITORY_TABLE, ASSIGNMENT_TABLE):
        if not _table_exists(conn, table):
            print(f'  - 表 {table} 不存在：请先执行 sync_schema 建表')
            return False

    triples = _duplicate_assignments(conn)
    if triples:
        print(f'  - 发现重复 (客户, 区域, 生效日) 组合，无法建唯一索引: {triples}')
        return False
    primaries = _duplicate_primary(conn)
    if primaries:
        print(f'  - 发现重复主区域 (客户, 生效日)，无法建唯一索引: {primaries}')
        return False

    for name, ddl in _INDEX_DDL:
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
        else:
            conn.execute(ddl)
            print(f'  - [NEW] 索引 {name}')
    return True


def _do_menu_rename(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单改名')
        return

    row = conn.execute(
        "SELECT menu_name FROM menus WHERE menu_code = ?", (MENU_CODE,)
    ).fetchone()
    if not row:
        print(f'  - [SKIP] 菜单 {MENU_CODE} 不存在（由 v132 创建）')
    elif row[0] == MENU_NAME_NEW:
        print(f'  - [SKIP] 菜单 {MENU_CODE} 已是「{MENU_NAME_NEW}」')
    else:
        conn.execute(
            "UPDATE menus SET menu_name = ? WHERE menu_code = ?",
            (MENU_NAME_NEW, MENU_CODE))
        print(f'  - [UPDATE] menus: {MENU_CODE} {row[0]!r} → {MENU_NAME_NEW!r}')

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "UPDATE menu_permissions SET menu_name = ? "
            "WHERE menu_code = ? AND menu_name <> ?",
            (MENU_NAME_NEW, MENU_CODE, MENU_NAME_NEW))
        if cur.rowcount:
            print(f'  - [UPDATE] menu_permissions: {cur.rowcount} 条改名')
        else:
            print(f'  - [SKIP] menu_permissions: {MENU_CODE} 名称无变化')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v133] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v133] 开始: 客户区域分配索引 / 菜单中文名收口')
        required = (TERRITORY_TABLE, ASSIGNMENT_TABLE)
        missing = [t for t in required if not _table_exists(conn, t)]
        if missing:
            print(f'[v133] 缺少表 {missing}, 终止')
            return False
        if not _do_indexes(conn):
            conn.rollback()
            return False
        _do_menu_rename(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v133] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言两张表 / 4 条索引 / 菜单名为「销售区域」。"""
    if not db_path.exists():
        print('[v133 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for table in (TERRITORY_TABLE, ASSIGNMENT_TABLE):
            if not _table_exists(conn, table):
                print(f'[v133 verify] FAIL: {table} 表不存在')
                return False

        for name, _ddl in _INDEX_DDL:
            if not _index_exists(conn, name):
                print(f'[v133 verify] FAIL: 缺索引 {name}')
                return False

        row = conn.execute(
            "SELECT menu_name FROM menus WHERE menu_code = ?", (MENU_CODE,)
        ).fetchone()
        if not row:
            print(f'[v133 verify] FAIL: 菜单 {MENU_CODE} 不存在')
            return False
        if row[0] != MENU_NAME_NEW:
            print(f'[v133 verify] FAIL: 菜单名为 {row[0]!r}, 期望 {MENU_NAME_NEW!r}')
            return False

        print(f'[v133 verify] OK: 4 条客户分配索引, 菜单 {MENU_CODE} = {MENU_NAME_NEW}')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """删除本次补建的索引，并把菜单名改回「区域」。"""
    if not db_path.exists():
        print(f'[v133] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for name, _ddl in _INDEX_DDL:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX {name}')
                print(f'  - [DROP] 索引 {name}')
        if _table_exists(conn, 'menus'):
            cur = conn.execute(
                "UPDATE menus SET menu_name = ? WHERE menu_code = ?",
                (MENU_NAME_OLD, MENU_CODE))
            print(f'  - [REVERT] menus: {cur.rowcount} 条改回「{MENU_NAME_OLD}」')
        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                "UPDATE menu_permissions SET menu_name = ? WHERE menu_code = ?",
                (MENU_NAME_OLD, MENU_CODE))
            print(f'  - [REVERT] menu_permissions: {cur.rowcount} 条改回「{MENU_NAME_OLD}」')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v133] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v133] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v133] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v133] verify: {"PASS" if _v else "FAIL"}')
