# -*- coding: utf-8 -*-
"""
[v102 2026-10-23] 作业日历 / 日历例外日菜单：自动生成行 → 手工声明（权限码收敛）

背景:
  calendar-list / calendar_day-list 是 menu_auto_generator 自动生成的 object_list
  菜单 (auto_generated=1)。页面形态本身没问题（日历是「基准 + 派生子日历」两层结构，
  不需要 region/address 那样的左树右表），问题在自动生成的
  required_permissions / bo_bindings 里带了 calendar:import / calendar:export /
  calendar_day:import / calendar_day:export —— 这四个权限码在 permissions 表并不存在
  （该表只有双段式的 5 条：calendar:calendar_create/_read/_update/_delete/_list 与
  calendar_day:calendar_day_*），前端路由守卫按 every 判定会把整页拦下
  （同 v099 location / v100 region / v101 address）。

改动:
  1. init_menu_permissions.py  手工声明这两条菜单 (auto_generated=0)，权限收敛为
     permissions 表真实存在的 5+5 条。
  2. 本 migration 改写存量菜单行：auto_generated 1→0、清除 import/export。

  菜单形态保持 object_list，menu_path / menu_name / icon / color / sort_order 均不变
  ⇒ object_type_route_map 落点与存量书签均不受影响。

幂等: UPDATE 带状态判据; 菜单不存在时跳过 (交由 init 创建)。
回滚: 恢复 auto_generated=1 与旧权限码。
"""
import json
import sqlite3
from pathlib import Path


# 两条菜单共用同一套升级/降级逻辑，按 MENU_SPECS 驱动
MENU_SPECS = [
    {
        'menu_code': 'calendar-list',
        'bo_id': 'calendar',
        'primary_object_type': 'calendar',
        'object_types': ['calendar'],
        'sort_order': 71,
        'old_bo_bindings': [
            {'bo_id': 'calendar', 'role': 'primary',
             'include_actions': ['calendar_create', 'calendar_delete',
                                 'calendar_update', 'calendar_list', 'export',
                                 'import', 'calendar_read']}
        ],
        'old_permissions': [
            'calendar:calendar_create', 'calendar:calendar_delete',
            'calendar:calendar_update', 'calendar:calendar_list',
            'calendar:export', 'calendar:import', 'calendar:calendar_read',
        ],
        'new_bo_bindings': [
            {'bo_id': 'calendar', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']}
        ],
        'new_permissions': [
            'calendar:calendar_create',
            'calendar:calendar_read',
            'calendar:calendar_update',
            'calendar:calendar_delete',
            'calendar:calendar_list',
        ],
    },
    {
        'menu_code': 'calendar_day-list',
        'bo_id': 'calendar_day',
        'primary_object_type': 'calendar_day',
        'object_types': ['calendar_day'],
        'sort_order': 72,
        'old_bo_bindings': [
            {'bo_id': 'calendar_day', 'role': 'primary',
             'include_actions': ['calendar_day_read', 'calendar_day_delete',
                                 'calendar_day_list', 'calendar_day_create',
                                 'export', 'import', 'calendar_day_update']}
        ],
        'old_permissions': [
            'calendar_day:calendar_day_read', 'calendar_day:calendar_day_delete',
            'calendar_day:calendar_day_list', 'calendar_day:calendar_day_create',
            'calendar_day:export', 'calendar_day:import',
            'calendar_day:calendar_day_update',
        ],
        'new_bo_bindings': [
            {'bo_id': 'calendar_day', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']}
        ],
        'new_permissions': [
            'calendar_day:calendar_day_create',
            'calendar_day:calendar_day_read',
            'calendar_day:calendar_day_update',
            'calendar_day:calendar_day_delete',
            'calendar_day:calendar_day_list',
        ],
    },
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过')
        return

    for spec in MENU_SPECS:
        menu_code = spec['menu_code']
        row = conn.execute(
            "SELECT menu_name, page_type, auto_generated, required_permissions "
            "FROM menus WHERE menu_code = ?",
            (menu_code,),
        ).fetchone()
        if not row:
            print(f'  - [MISS] {menu_code} 不存在, 跳过 (交由 init_menu_permissions.py 创建)')
            continue

        menu_name, page_type, auto_generated, req_perms = row
        # 幂等判据: 已是手工声明且不含 import/export ⇒ 无需改动
        if auto_generated == 0 and 'import' not in (req_perms or ''):
            print(f'  - [SKIP] {menu_code} ({menu_name}) 已是新形态')
            continue

        conn.execute(
            "UPDATE menus SET page_type = ?, primary_object_type = ?, "
            "object_types = ?, bo_bindings = ?, required_permissions = ?, "
            "parent_menu = 'master-data', icon = 'Box', sort_order = ?, "
            "auto_generated = 0 "
            "WHERE menu_code = ?",
            (
                'object_list',
                spec['primary_object_type'],
                json.dumps(spec['object_types'], ensure_ascii=False),
                json.dumps(spec['new_bo_bindings'], ensure_ascii=False),
                json.dumps(spec['new_permissions'], ensure_ascii=False),
                spec['sort_order'],
                menu_code,
            ),
        )
        print(f'  - [UPGRADE] {menu_code} ({menu_name}): auto_generated '
              f'{auto_generated} → 0, page_type 保持 {page_type}')
        print(f'  - [UPGRADE] required_permissions 收敛为 '
              f'{len(spec["new_permissions"])} 条 (去除 import/export)')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    for spec in MENU_SPECS:
        cur = conn.execute(
            "UPDATE menus SET page_type = ?, bo_bindings = ?, required_permissions = ?, "
            "auto_generated = 1 WHERE menu_code = ?",
            (
                'object_list',
                json.dumps(spec['old_bo_bindings'], ensure_ascii=False),
                json.dumps(spec['old_permissions'], ensure_ascii=False),
                spec['menu_code'],
            ),
        )
        print(f'  [REVERT] {spec["menu_code"]}: '
              f'{getattr(cur, "rowcount", 0) or 0} 条恢复自动生成形态')
    print('  [REVERT] 菜单声明需从 init_menu_permissions.py 移除')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v102] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v102] 开始: 作业日历 / 例外日菜单权限码收敛 (自动生成行 → 手工声明)')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v102] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """两条日历菜单已是手工声明，且 required_permissions 全部真实存在。"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            return False
        for spec in MENU_SPECS:
            menu_code = spec['menu_code']
            row = conn.execute(
                "SELECT page_type, auto_generated, is_active, menu_path, "
                "primary_object_type, required_permissions "
                "FROM menus WHERE menu_code = ?",
                (menu_code,),
            ).fetchone()
            if not row:
                print(f'[v102 verify] FAIL: {menu_code} 不存在')
                return False
            page_type, auto_generated, is_active, menu_path, pot, req = row
            if page_type != 'object_list':
                print(f'[v102 verify] FAIL: {menu_code} page_type={page_type}, '
                      f'期望 object_list')
                return False
            if is_active != 1:
                print(f'[v102 verify] FAIL: {menu_code} is_active={is_active}, 期望 1')
                return False
            if auto_generated != 0:
                print(f'[v102 verify] FAIL: {menu_code} auto_generated={auto_generated}, '
                      f'期望 0')
                return False
            if pot != spec['primary_object_type']:
                print(f'[v102 verify] FAIL: {menu_code} '
                      f'primary_object_type={pot}, 期望 {spec["primary_object_type"]}')
                return False
            if not menu_path:
                print(f'[v102 verify] FAIL: {menu_code} menu_path 为空')
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
                print(f'[v102 verify] FAIL: {menu_code} required_permissions '
                      f'含不存在的权限码 {missing}')
                return False
            print(f'[v102 verify] OK: {menu_code} 已是手工声明 @ {menu_path}, '
                  f'{len(codes)} 条权限码全部有效')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v102] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v102] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v102] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v102] verify: {"PASS" if _v else "FAIL"}')
