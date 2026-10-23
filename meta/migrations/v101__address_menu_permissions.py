# -*- coding: utf-8 -*-
"""
[v101 2026-10-23] 地址管理菜单：自动生成行 → 手工声明（权限码收敛）

背景:
  address-list 是 menu_auto_generator 自动生成的 object_list 菜单
  (auto_generated=1, menu_path='/address')。页面形态本身没问题（地址是扁平列表，
  无层级树），问题在自动生成的 required_permissions / bo_bindings 里带了
  address:import / address:export —— 这两个权限码在 permissions 表并不存在，
  前端路由守卫按 every 判定会把整页拦下（同 v099 location / v100 region）。

改动:
  1. init_menu_permissions.py  手工声明 address-list (auto_generated=0)，权限收敛为
     permissions 表真实存在的 5 条。
  2. 本 migration 改写存量菜单行：auto_generated 1→0、清除 import/export。

  菜单形态保持 object_list（不引入左树）：地址是结构化字段 + 格式化全文的扁平列表，
  查看入口仍是 /address；menu_path 不变 ⇒ object_type_route_map['address'] 与
  存量书签均不受影响。

幂等: UPDATE 带状态判据; 菜单不存在时跳过 (交由 init 创建)。
回滚: 恢复 auto_generated=1 与旧权限码。
"""
import json
import sqlite3
from pathlib import Path


MENU_CODE = 'address-list'

# 旧形态 (自动生成器口径), 供 downgrade 复原
OLD_PAGE_TYPE = 'object_list'
OLD_BO_BINDINGS = [
    {'bo_id': 'address', 'role': 'primary',
     'include_actions': ['export', 'address_update', 'address_list',
                         'address_read', 'address_create', 'import',
                         'address_delete']}
]
OLD_PERMISSIONS = [
    'address:export', 'address:address_update', 'address:address_list',
    'address:address_read', 'address:address_create', 'address:import',
    'address:address_delete'
]

# 新形态 (与 init_menu_permissions.py 的声明保持一致)
NEW_PAGE_TYPE = 'object_list'
NEW_BO_BINDINGS = [
    {'bo_id': 'address', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']}
]
NEW_PERMISSIONS = [
    'address:address_create',
    'address:address_read',
    'address:address_update',
    'address:address_delete',
    'address:address_list',
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过')
        return

    row = conn.execute(
        "SELECT menu_name, page_type, auto_generated, required_permissions "
        "FROM menus WHERE menu_code = ?",
        (MENU_CODE,),
    ).fetchone()
    if not row:
        print(f'  - [MISS] {MENU_CODE} 不存在, 跳过 (交由 init_menu_permissions.py 创建)')
        return

    menu_name, page_type, auto_generated, req_perms = row
    if page_type == NEW_PAGE_TYPE and auto_generated == 0 \
            and 'address:import' not in (req_perms or ''):
        print(f'  - [SKIP] {MENU_CODE} ({menu_name}) 已是新形态')
        return

    conn.execute(
        "UPDATE menus SET page_type = ?, primary_object_type = ?, "
        "object_types = ?, bo_bindings = ?, required_permissions = ?, "
        "parent_menu = 'master-data', icon = 'Box', sort_order = 68, "
        "auto_generated = 0 "
        "WHERE menu_code = ?",
        (
            NEW_PAGE_TYPE,
            'address',
            json.dumps(['address']),
            json.dumps(NEW_BO_BINDINGS, ensure_ascii=False),
            json.dumps(NEW_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ),
    )
    print(f'  - [UPGRADE] {MENU_CODE} ({menu_name}): page_type '
          f'{page_type} → {NEW_PAGE_TYPE}, auto_generated {auto_generated} → 0')
    print(f'  - [UPGRADE] required_permissions 收敛为 {len(NEW_PERMISSIONS)} 条 '
          f'(去除 import/export)')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    cur = conn.execute(
        "UPDATE menus SET page_type = ?, bo_bindings = ?, required_permissions = ?, "
        "auto_generated = 1 WHERE menu_code = ?",
        (
            OLD_PAGE_TYPE,
            json.dumps(OLD_BO_BINDINGS, ensure_ascii=False),
            json.dumps(OLD_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ),
    )
    print(f'  [REVERT] {getattr(cur, "rowcount", 0) or 0} 条菜单恢复自动生成形态')
    print('  [REVERT] 菜单声明需从 init_menu_permissions.py 移除')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v101] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v101] 开始: 地址管理菜单权限码收敛 (自动生成行 → 手工声明)')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v101] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """address-list 已是手工声明, 且 required_permissions 全部真实存在。"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            return False
        row = conn.execute(
            "SELECT page_type, auto_generated, is_active, menu_path, "
            "primary_object_type, required_permissions "
            "FROM menus WHERE menu_code = ?",
            (MENU_CODE,),
        ).fetchone()
        if not row:
            print(f'[v101 verify] FAIL: {MENU_CODE} 不存在')
            return False
        page_type, auto_generated, is_active, menu_path, pot, req = row
        if page_type != NEW_PAGE_TYPE:
            print(f'[v101 verify] FAIL: page_type={page_type}, 期望 {NEW_PAGE_TYPE}')
            return False
        if is_active != 1:
            print(f'[v101 verify] FAIL: is_active={is_active}, 期望 1')
            return False
        if auto_generated != 0:
            print(f'[v101 verify] FAIL: auto_generated={auto_generated}, 期望 0')
            return False
        if menu_path != '/address' or pot != 'address':
            print(f'[v101 verify] FAIL: menu_path={menu_path}, '
                  f'primary_object_type={pot}')
            return False
        codes = json.loads(req or '[]')
        missing = []
        if _table_exists(conn, 'permissions'):
            for code in codes:
                if not conn.execute(
                        "SELECT 1 FROM permissions WHERE code = ?", (code,)
                ).fetchone():
                    missing.append(code)
        if missing:
            print(f'[v101 verify] FAIL: required_permissions 含不存在的权限码 {missing}')
            return False
        print(f'[v101 verify] OK: {MENU_CODE} 已是手工声明 @ /address, '
              f'{len(codes)} 条权限码全部有效')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v101] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v101] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v101] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v101] verify: {"PASS" if _v else "FAIL"}')
