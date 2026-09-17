# -*- coding: utf-8 -*-
"""
[Spec16 Plan D 收尾 v074 2026-08-31]
两个独立的修复合在一个 migration 里:

1. **隐藏 legacy 菜单** (前端菜单与 staging 后端不一致)
   staging 上有两个仍在 sidebar 显示的 Spec15 残留菜单, spec16 后应该被取代:
     - org-list            (auto-generated, "组织管理",     /user-permission/orgs)
                           → 已被顶级菜单 org-management (/org-management) 取代
     - org_function-list   (auto-generated, "组织职能管理", /user-permission/org-functions)
                           → spec16 把 user_group 提到顶级 org-management,
                             org_function 作为旧角色概念不再需要独立菜单

   修法: UPDATE menus SET show_in_sidebar=0 WHERE menu_code IN (...)
   (不删菜单, 只 hide. 留 menu_permissions / role_menu_permissions 里的映射,
    方便将来如需恢复直接改回 show_in_sidebar=1)

2. **data_permission_rules 表 spec16 列对齐**
   staging 上 data_permission_rules 还是纯 Spec15 schema:
     - 有 role_id (Spec15), 没有 permission_set_id (Spec16)
     - 但 spec16 代码 (bo_api.list_permission_rules_v2) 用 ConditionPermissionService
       查询 data_permission_rules 时硬 SELECT permission_set_id 列, → 500
   前一轮 spec16 全列修复只改了 permission_rules / permission_set_permissions / 等,
   **漏了 data_permission_rules** (它的 column 补齐需要单独的 migration).

   修法: ALTER TABLE data_permission_rules ADD COLUMN permission_set_id INTEGER
   staging 上 data_permission_rules 是 0 行 (2026-08-31 实测), 无需数据迁移;
   若将来发现非空, 需要做 role_id → permission_set_id 的回填 (类比 permission_rules
   已有的 fix: permission_set_id = role_id, 因为 spec16 rename 是 1:1 同 id).

幂等性:
  - ALTER TABLE ADD COLUMN 在 SQLite 里重复执行会报错, 用 _column_exists 守护
  - UPDATE menus WHERE ... 用 SQL 层判断 (UPDATE rows changed count)
"""
import sqlite3
from pathlib import Path


# 需要 hide 的菜单 (spec16 后应该不显示在 sidebar)
LEGACY_ORG_MENUS_TO_HIDE = ('org-list', 'org_function-list')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())


def _hide_legacy_org_menus(conn: sqlite3.Connection) -> None:
    """把两个 legacy 菜单从 sidebar 隐藏."""
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单 hide')
        return
    placeholders = ','.join('?' * len(LEGACY_ORG_MENUS_TO_HIDE))
    cur = conn.execute(
        f"SELECT menu_code, menu_name, show_in_sidebar FROM menus "
        f"WHERE menu_code IN ({placeholders})",
        LEGACY_ORG_MENUS_TO_HIDE,
    )
    rows = cur.fetchall()
    for menu_code, menu_name, current in rows:
        if current == 0:
            print(f'  - {menu_code} ({menu_name}) 已经是 hidden, 跳过')
            continue
        conn.execute(
            "UPDATE menus SET show_in_sidebar = 0 WHERE menu_code = ?",
            (menu_code,),
        )
        print(f'  [HIDE] {menu_code} ({menu_name}) show_in_sidebar: {current} → 0')
    # 也清理菜单配置里残留的 sidebar 路由 (可选, 对齐 role-list/user_group-list 的处理)
    # 不清, 因为 show_in_sidebar=0 已足够让 API 不返回


def _fix_data_permission_rules_schema(conn: sqlite3.Connection) -> None:
    """给 data_permission_rules 补 permission_set_id 列."""
    if not _table_exists(conn, 'data_permission_rules'):
        print('  - data_permission_rules 表不存在, 跳过 (无需创建)')
        return

    # 1. 检查是否已有 permission_set_id
    if _column_exists(conn, 'data_permission_rules', 'permission_set_id'):
        print('  - data_permission_rules.permission_set_id 已存在, 跳过 ALTER')
    else:
        conn.execute(
            "ALTER TABLE data_permission_rules ADD COLUMN permission_set_id INTEGER"
        )
        print('  [ALTER] data_permission_rules ADD COLUMN permission_set_id INTEGER')

    # 2. 数据回填 (spec16 rename 是 1:1 同 id, role_id 即 permission_set_id)
    #    staging 上 0 行, 无需回填, 但逻辑保留以防将来有数据
    cur = conn.execute(
        "SELECT COUNT(*) FROM data_permission_rules WHERE permission_set_id IS NULL AND role_id IS NOT NULL"
    )
    need_backfill = cur.fetchone()[0]
    if need_backfill > 0:
        conn.execute(
            "UPDATE data_permission_rules SET permission_set_id = role_id "
            "WHERE permission_set_id IS NULL AND role_id IS NOT NULL"
        )
        print(f'  [BACKFILL] data_permission_rules: {need_backfill} rows '
              f'(permission_set_id = role_id)')
    else:
        print('  - data_permission_rules 无需数据回填 (空表或 permission_set_id 已填)')


def _do_upgrade(conn: sqlite3.Connection) -> None:
    print('[v074] 开始 spec16 收尾: 隐藏 legacy 菜单 + 修复 data_permission_rules')
    print('  --- 1/2 hide legacy org menus ---')
    _hide_legacy_org_menus(conn)
    print('  --- 2/2 fix data_permission_rules ---')
    _fix_data_permission_rules_schema(conn)
    print('[v074] 完成')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    """回滚: 把 hide 的菜单恢复 + DROP column (SQLite 不支持 DROP COLUMN, 留 stub)."""
    print('[v074] 开始回滚')
    if _table_exists(conn, 'menus'):
        placeholders = ','.join('?' * len(LEGACY_ORG_MENUS_TO_HIDE))
        conn.execute(
            f"UPDATE menus SET show_in_sidebar = 1 WHERE menu_code IN ({placeholders}) "
            f"AND menu_code NOT IN (SELECT menu_code FROM menus WHERE menu_code IN "
            f"('role-list','user_group-list'))",
            LEGACY_ORG_MENUS_TO_HIDE,
        )
        print('  [RESTORE] legacy 菜单 show_in_sidebar → 1')
    # SQLite 不支持 DROP COLUMN, 列保留; 数据保留为 NULL
    print('  注: data_permission_rules.permission_set_id 列保留 (SQLite 无 DROP COLUMN)')


# ─── 入口签名 (meta/migrations/README.md §2) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """
    v074: spec16 收尾
      - hide legacy org-list / org_function-list (前端 sidebar 重复组织管理)
      - data_permission_rules ADD permission_set_id 列 (修 /api/v2/permission-rules 500)

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 是否跳过备份 (runner 已统一备份, 内部可跳过)

    Returns:
        True 如果成功执行或已执行 (幂等)
    """
    if not db_path.exists():
        print(f'[v074] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v074] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证 v074: 2 个菜单 show_in_sidebar=0 + dpr 有 permission_set_id 列"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        # 1. menus hide
        if _table_exists(conn, 'menus'):
            placeholders = ','.join('?' * len(LEGACY_ORG_MENUS_TO_HIDE))
            cur = conn.execute(
                f"SELECT menu_code, show_in_sidebar FROM menus "
                f"WHERE menu_code IN ({placeholders})",
                LEGACY_ORG_MENUS_TO_HIDE,
            )
            rows = cur.fetchall()
            for menu_code, sidebar in rows:
                if sidebar != 0:
                    print(f'  [VERIFY-FAIL] {menu_code} show_in_sidebar={sidebar}, expected 0')
                    return False
        # 2. data_permission_rules permission_set_id column
        if _table_exists(conn, 'data_permission_rules'):
            if not _column_exists(conn, 'data_permission_rules', 'permission_set_id'):
                print('  [VERIFY-FAIL] data_permission_rules 缺 permission_set_id 列')
                return False
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """
    v074 回滚: 恢复被 hide 的 legacy 菜单 (permission_set_id 列保留, SQLite 无 DROP COLUMN)

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 是否跳过备份 (runner 已统一备份, 内部可跳过)

    Returns:
        True 如果成功执行
    """
    if not db_path.exists():
        print(f'[v074] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v074] downgrade 失败: {e}')
        raise
    finally:
        conn.close()
