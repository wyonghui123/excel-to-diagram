# -*- coding: utf-8 -*-
"""
[v103 2026-10-23] 作业日历管理页改版：object_list → multi_object_hub（左树 + 两个 tab）

背景:
  calendar 是「基准日历 → 派生日历」自引用树（parent_calendar_id，max_depth=2），
  日历例外日 calendar_day 是它的 association 子对象（parent_object: calendar、
  hierarchy.parent_field: calendar_id）。但侧边栏里 calendar-list(/calendar) 与
  calendar_day-list(/calendar-day) 是两条平级 object_list 菜单 —— 子表与父表平级
  属「放错层」，与 party_relation 收进业务伙伴页第三 tab 同款问题。

改动:
  1. init_menu_permissions.py 把 calendar-list 从 object_list 升级为 multi_object_hub
     （object_types=['calendar','calendar_day']，权限 5+5 条），并把 calendar_day-list
     加入 deprecated_codes（步骤 4.5 删除存量声明行）。
  2. 前端新增 CalendarScopeTree（日历树，节点标「基准/派生」）与
     CalendarManagement.vue（MOMP 配置注入），GenericTabContainer 注册映射。
  3. 本 migration 改写存量菜单行：calendar-list 升级 + 跨承载 calendar_day，
     并删除 calendar_day-list 及其 menu_permissions 行。

  菜单落点不变: menu_path 保持 '/calendar' ⇒ object_type_route_map['calendar'] 与
  存量书签不受影响；object_types 登记 calendar_day ⇒ route_map['calendar_day']
  = '/calendar'（FK 链接仍可跳转）。

  删除而非 is_active=0 的理由同 init 步骤 4.5 对 party-relation-management 的处理:
  calendar_day-list 是**手工声明**行，步骤 5/6 的 UPSERT 会把它强制 is_active=1，
  留在库里会被重新激活。菜单若无任何授权引用，删除不会留下悬挂授权（本 migration
  会先打印引用计数便于排查）。

幂等: UPDATE 带状态判据；calendar_day-list 不存在时跳过；重复执行为 no-op。
回滚: calendar-list 恢复 object_list / 旧权限码；calendar_day-list 声明需重新加回
      init_menu_permissions.py 后重建（DELETE 不可逆）。
"""
import json
import sqlite3
from pathlib import Path


MENU_CODE = 'calendar-list'
RETIRED_CODE = 'calendar_day-list'

# 旧形态（v102 手工声明口径），供 downgrade 复原
OLD_PAGE_TYPE = 'object_list'
OLD_OBJECT_TYPES = ['calendar']
OLD_BO_BINDINGS = [
    {'bo_id': 'calendar', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']}
]
OLD_PERMISSIONS = [
    'calendar:calendar_create',
    'calendar:calendar_read',
    'calendar:calendar_update',
    'calendar:calendar_delete',
    'calendar:calendar_list',
]

# 新形态（与 init_menu_permissions.py 的声明保持一致）
NEW_PAGE_TYPE = 'multi_object_hub'
NEW_OBJECT_TYPES = ['calendar', 'calendar_day']
NEW_BO_BINDINGS = [
    {'bo_id': 'calendar', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']},
    {'bo_id': 'calendar_day', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']},
]
NEW_PERMISSIONS = [
    'calendar:calendar_create',
    'calendar:calendar_read',
    'calendar:calendar_update',
    'calendar:calendar_delete',
    'calendar:calendar_list',
    'calendar_day:calendar_day_create',
    'calendar_day:calendar_day_read',
    'calendar_day:calendar_day_update',
    'calendar_day:calendar_day_delete',
    'calendar_day:calendar_day_list',
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
        "SELECT menu_name, page_type, auto_generated, object_types "
        "FROM menus WHERE menu_code = ?",
        (MENU_CODE,),
    ).fetchone()
    if not row:
        print(f'  - [MISS] {MENU_CODE} 不存在, 跳过 (交由 init_menu_permissions.py 创建)')
        return

    menu_name, page_type, auto_generated, object_types = row
    try:
        current_types = json.loads(object_types or '[]')
    except Exception:
        current_types = []
    if page_type == NEW_PAGE_TYPE and auto_generated == 0 \
            and 'calendar_day' in current_types:
        print(f'  - [SKIP] {MENU_CODE} ({menu_name}) 已是新形态')
    else:
        conn.execute(
            "UPDATE menus SET page_type = ?, primary_object_type = ?, "
            "object_types = ?, bo_bindings = ?, required_permissions = ?, "
            "parent_menu = 'master-data', sort_order = 71, auto_generated = 0 "
            "WHERE menu_code = ?",
            (
                NEW_PAGE_TYPE,
                'calendar',
                json.dumps(NEW_OBJECT_TYPES),
                json.dumps(NEW_BO_BINDINGS, ensure_ascii=False),
                json.dumps(NEW_PERMISSIONS, ensure_ascii=False),
                MENU_CODE,
            ),
        )
        print(f'  - [UPGRADE] {MENU_CODE} ({menu_name}): page_type '
              f'{page_type} → {NEW_PAGE_TYPE}, object_types {current_types} → '
              f'{NEW_OBJECT_TYPES}')
        print(f'  - [UPGRADE] required_permissions 扩为 {len(NEW_PERMISSIONS)} 条 '
              f'(含 calendar_day 5 条)')

    retired = conn.execute(
        "SELECT menu_name FROM menus WHERE menu_code = ?", (RETIRED_CODE,)
    ).fetchone()
    if not retired:
        print(f'  - [SKIP] {RETIRED_CODE} 不存在 (已删除)')
    else:
        refs = 0
        if _table_exists(conn, 'permission_set_menu_permissions'):
            refs = conn.execute(
                "SELECT COUNT(*) FROM permission_set_menu_permissions "
                "WHERE menu_code = ?", (RETIRED_CODE,)
            ).fetchone()[0]
        if refs:
            print(f'  - [WARN] {RETIRED_CODE} 仍被 {refs} 个权限集引用, '
                  f'删除后这些授权将失效')
        conn.execute("DELETE FROM menus WHERE menu_code = ?", (RETIRED_CODE,))
        print(f'  - [RETIRE] {RETIRED_CODE} ({retired[0]}) 已删除 '
              f'(入口收进 {MENU_CODE} 第二 tab)')

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "DELETE FROM menu_permissions WHERE menu_code = ?", (RETIRED_CODE,))
        cleaned = getattr(cur, 'rowcount', 0) or 0
        if cleaned:
            print(f'  - [CLEAN] menu_permissions 清理 {cleaned} 条冗余行')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    cur = conn.execute(
        "UPDATE menus SET page_type = ?, object_types = ?, bo_bindings = ?, "
        "required_permissions = ? WHERE menu_code = ?",
        (
            OLD_PAGE_TYPE,
            json.dumps(OLD_OBJECT_TYPES),
            json.dumps(OLD_BO_BINDINGS, ensure_ascii=False),
            json.dumps(OLD_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ),
    )
    print(f'  [REVERT] {getattr(cur, "rowcount", 0) or 0} 条菜单恢复 object_list')
    print(f'  [REVERT] {RETIRED_CODE} 已被物理删除, 需从 init_menu_permissions.py '
          f'重新声明后重建')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v103] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v103] 开始: 作业日历页改版 object_list → multi_object_hub (左树 + 两个 tab)')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v103] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """calendar-list 已是 MOMP 形态，calendar_day-list 已删除，权限码全部真实存在。"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            return False
        row = conn.execute(
            "SELECT page_type, auto_generated, is_active, menu_path, "
            "primary_object_type, object_types, required_permissions "
            "FROM menus WHERE menu_code = ?",
            (MENU_CODE,),
        ).fetchone()
        if not row:
            print(f'[v103 verify] FAIL: {MENU_CODE} 不存在')
            return False
        page_type, auto_generated, is_active, menu_path, pot, ots, req = row
        if page_type != NEW_PAGE_TYPE:
            print(f'[v103 verify] FAIL: page_type={page_type}, 期望 {NEW_PAGE_TYPE}')
            return False
        if is_active != 1:
            print(f'[v103 verify] FAIL: is_active={is_active}, 期望 1')
            return False
        if auto_generated != 0:
            print(f'[v103 verify] FAIL: auto_generated={auto_generated}, 期望 0')
            return False
        if menu_path != '/calendar' or pot != 'calendar':
            print(f'[v103 verify] FAIL: menu_path={menu_path}, '
                  f'primary_object_type={pot}')
            return False
        try:
            types = json.loads(ots or '[]')
        except Exception:
            types = []
        if 'calendar' not in types or 'calendar_day' not in types:
            print(f'[v103 verify] FAIL: object_types={types}, '
                  f'期望含 calendar 与 calendar_day')
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
            print(f'[v103 verify] FAIL: required_permissions 含不存在的权限码 {missing}')
            return False
        gone = conn.execute(
            "SELECT 1 FROM menus WHERE menu_code = ?", (RETIRED_CODE,)
        ).fetchone()
        if gone:
            print(f'[v103 verify] FAIL: {RETIRED_CODE} 仍存在')
            return False
        print(f'[v103 verify] OK: {MENU_CODE} 已是 {NEW_PAGE_TYPE} @ /calendar '
              f'(object_types={types}), {len(codes)} 条权限码全部有效, '
              f'{RETIRED_CODE} 已删除')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v103] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v103] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v103] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v103] verify: {"PASS" if _v else "FAIL"}')
