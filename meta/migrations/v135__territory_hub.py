# -*- coding: utf-8 -*-
"""[v135] 销售区域（TER-M4）：菜单页形态 object_list → multi_object_hub

依据:
  docs/superpowers/specs/2026-10-26-sales-territory-design.md
    §8 UI 方案 / §9 M4 / D-TER-7

背景:
  销售区域页在 v132 以 `page_type='object_list'` 声明；M4 起改为左树右表
  （左树 = 销售区域层级，右表 = 区域列表），页面形态由 `territory.yaml` 的
  `ui_view_config.hub` 驱动。前端 `dynamicRoutes` 按菜单 `page_type` 选组件：
  `multi_object_hub` → GenericTabContainer → MultiObjectHubPage → MOMP。
  菜单只需切换 `page_type`；`object_types` / `bo_bindings` / 权限要求均不变。

口径说明:
  设计 §7.1 的 territory 权限维度是运行时 YAML 加载
  （`dimension_object_mapping.yaml`，`persistent: false`），不入库，
  故本迁移不涉及维度表。

幂等:
  已是 multi_object_hub → [SKIP]；菜单行不存在（v132 未执行 / 未初始化）→
  [SKIP] 并继续；menus 表缺失 → 终止。

回滚:
  把 `page_type` 改回 `object_list`。
"""
import sqlite3
from pathlib import Path

MENU_CODE = 'territory-list'
PAGE_TYPE_NEW = 'multi_object_hub'
PAGE_TYPE_OLD = 'object_list'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_page_type(conn: sqlite3.Connection, page_type: str) -> int:
    """把菜单页形态改为 `page_type`；已是目标值则跳过。返回变更行数。"""
    row = conn.execute(
        "SELECT page_type FROM menus WHERE menu_code = ?", (MENU_CODE,)
    ).fetchone()
    if not row:
        print(f'  - [SKIP] 菜单 {MENU_CODE} 不存在（由 v132 创建）')
        return 0
    if row[0] == page_type:
        print(f'  - [SKIP] 菜单 {MENU_CODE} page_type 已是 {page_type}')
        return 0
    cur = conn.execute(
        "UPDATE menus SET page_type = ? WHERE menu_code = ?",
        (page_type, MENU_CODE))
    print(f'  - [UPDATE] menus: {MENU_CODE} page_type {row[0]!r} → {page_type!r}')
    return cur.rowcount


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v135] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v135] 开始: 销售区域页形态 → multi_object_hub')
        if not _table_exists(conn, 'menus'):
            print('[v135] menus 表不存在, 终止')
            return False
        _do_page_type(conn, PAGE_TYPE_NEW)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v135] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言菜单 territory-list 的 page_type = multi_object_hub。"""
    if not db_path.exists():
        print('[v135 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            print('[v135 verify] FAIL: menus 表不存在')
            return False
        row = conn.execute(
            "SELECT page_type FROM menus WHERE menu_code = ?", (MENU_CODE,)
        ).fetchone()
        if not row:
            print(f'[v135 verify] FAIL: 菜单 {MENU_CODE} 不存在')
            return False
        if row[0] != PAGE_TYPE_NEW:
            print(f'[v135 verify] FAIL: page_type = {row[0]!r}, '
                  f'期望 {PAGE_TYPE_NEW!r}')
            return False
        print(f'[v135 verify] OK: 菜单 {MENU_CODE} page_type = {PAGE_TYPE_NEW}')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """把菜单页形态改回 object_list。"""
    if not db_path.exists():
        print(f'[v135] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _table_exists(conn, 'menus'):
            _do_page_type(conn, PAGE_TYPE_OLD)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v135] rollback 失败: {e}')
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
        print(f'[v135] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v135] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v135] verify: {"PASS" if _v else "FAIL"}')
