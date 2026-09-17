# -*- coding: utf-8 -*-
"""
[v075 2026-08-31] 把"组织管理"菜单移到"用户与权限管理"子菜单下

历史:
  - v074 commit 1f8350c 把 org-management 注册为顶级菜单 (parent_menu=''),
    与 user-permission 同级兄弟
  - 但前端 GenericTabContainer.vue:103 注释明确写:
    "组织管理"为 user-permission 组下的子 tab (menu_code=org-management)
  - 前端路由 /user-permission/:tab? 支持 tab 路由, 但顶级 /org-management 也独立存在
  - 实际前端期望: 进入 /user-permission/org-management tab 看组织管理
  - 与 localhost:3007 本地开发对比: 本地显示 组织管理 在 用户与权限管理 下,
    staging 显示顶级菜单 → 不一致

根因:
  init_menu_permissions.py 里 org-management.parent_menu = '' (顶级)
  前端预期 parent_menu = 'user-permission' (子菜单)

修复:
  UPDATE menus SET parent_menu='user-permission' WHERE menu_code='org-management'

附加:
  - sort_order: org-management 当前 52, 与 user-permission (顶级 51) 冲突 (sort_order 在父菜单上下文里无意义)
    这里不强制改, 让 init_menu_permissions.py 后续 commit 改
  - role_menu_permissions / permission_set_menu_permissions 不需要改 (只关系菜单层级, 不关系 ps 绑定)

幂等性:
  - 用 SQL 检查 WHERE 条件: 仅在当前 parent_menu != 'user-permission' 时更新
  - 这样即使重复执行, 第二次也是 no-op
"""
import sqlite3
from pathlib import Path


TARGET_MENU = 'org-management'
TARGET_PARENT = 'user-permission'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print(f'  - menus 表不存在, 跳过')
        return

    # 检查目标父菜单是否存在
    parent_row = conn.execute(
        "SELECT menu_code, menu_name FROM menus WHERE menu_code = ?",
        (TARGET_PARENT,),
    ).fetchone()
    if not parent_row:
        print(f'  - 父菜单 {TARGET_PARENT} 不存在, 跳过 (将先创建用户与权限管理菜单)')
        return

    # 检查目标菜单当前状态
    cur_row = conn.execute(
        "SELECT menu_code, menu_name, parent_menu, show_in_sidebar FROM menus WHERE menu_code = ?",
        (TARGET_MENU,),
    ).fetchone()
    if not cur_row:
        print(f'  - {TARGET_MENU} 菜单不存在, 跳过 (请先跑 init_menu_permissions.py)')
        return

    cur_parent = cur_row[2]
    if cur_parent == TARGET_PARENT:
        print(f'  - {TARGET_MENU} 已经是 {TARGET_PARENT} 子菜单, 跳过')
        return

    conn.execute(
        "UPDATE menus SET parent_menu = ? WHERE menu_code = ?",
        (TARGET_PARENT, TARGET_MENU),
    )
    print(f'  [UPDATE] {TARGET_MENU} ({cur_row[1]}) parent_menu: "{cur_parent}" → "{TARGET_PARENT}"')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    """回滚: 改回顶级菜单"""
    if not _table_exists(conn, 'menus'):
        return
    conn.execute(
        "UPDATE menus SET parent_menu = '' WHERE menu_code = ?",
        (TARGET_MENU,),
    )
    print(f'  [REVERT] {TARGET_MENU} parent_menu → "" (顶级)')


# ─── 入口签名 ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v075] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v075] 开始: 把组织管理菜单移到用户与权限管理下')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v075] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            return False
        row = conn.execute(
            "SELECT parent_menu FROM menus WHERE menu_code = ?",
            (TARGET_MENU,),
        ).fetchone()
        if not row:
            return False
        return row[0] == TARGET_PARENT
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v075] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v075] 回滚: 把组织管理菜单改回顶级')
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v075] downgrade 失败: {e}')
        raise
    finally:
        conn.close()