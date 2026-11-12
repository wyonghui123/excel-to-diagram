# -*- coding: utf-8 -*-
"""[v213 2026-11-04] 包装容器查询 UI：object_list → multi_object_hub（左树 + 三 tab）

依据:
  docs/specs/p6-serial-number-model/spec.md §11.14（D4 查询 UI）

背景:
  v211 建了 handling-unit-list 菜单，但只写 page_type='object_list'
  （一个平铺容器列表，看不到嵌套关系与内容/事件）。D4 要的「容器内容树 +
  按容器号查看内容与事件」在 MOMP 里是纯元数据形态：
    meta/schemas/handling_unit.yaml 的 ui_view_config.hub 声明
      object_types = [handling_unit, handling_unit_item, hu_transaction]
      scope.parent_field = parent_hu_id（嵌套容器组树）
      filters.handling_unit.mode = direct（子容器 tab 只列直接子级）
  → 菜单只需把 page_type 改成 multi_object_hub，前端即渲染
    GenericTabContainer → MultiObjectHubPage → MultiObjectManagementPage。

  本迁移不改菜单路径（'/inventory/handling-units'），存量书签/route_map 不受影响。

改动:
  1. menus.handling-unit-list:
       page_type           object_list → multi_object_hub
       object_types        ['handling_unit'] → 三个对象（与 YAML hub 对齐）
       bo_bindings         primary handling_unit + 两个 related
       required_permissions 4 条 → 8 条（含 _item_list / hu_transaction_list）
  2. menu_permissions 同步 required_permissions（路由守卫按 every 判定，
     引用的权限码必须真实存在，否则整页被拦 —— v099~v102 反复踩过）。

幂等:
  UPDATE 带 WHERE 守卫（page_type / object_types / 权限串已一致即 [SKIP]）；
  菜单不存在时直接跳过（交由 v211 先建）。

回滚:
  page_type 回到 object_list，object_types / bo_bindings / required_permissions
  恢复 v211 形态；hub 声明在 YAML 里，无需回滚（page_type 不是 hub 时不会生效）。
"""
import json
import sqlite3
from pathlib import Path

MENU_CODE = 'handling-unit-list'

OLD_PAGE_TYPE = 'object_list'
OLD_OBJECT_TYPES = ['handling_unit']
OLD_PERMISSIONS = [
    'handling_unit:handling_unit_read',
    'handling_unit:handling_unit_create',
    'handling_unit:handling_unit_update',
    'handling_unit:handling_unit_delete',
]
OLD_BO_BINDINGS = [
    {'bo_id': 'handling_unit', 'role': 'primary',
     'include_actions': ['read', 'create', 'update', 'delete']}
]

NEW_PAGE_TYPE = 'multi_object_hub'
NEW_OBJECT_TYPES = ['handling_unit', 'handling_unit_item', 'hu_transaction']
NEW_PERMISSIONS = [
    'handling_unit:handling_unit_read',
    'handling_unit:handling_unit_create',
    'handling_unit:handling_unit_update',
    'handling_unit:handling_unit_delete',
    'handling_unit_item:handling_unit_item_read',
    'handling_unit_item:handling_unit_item_list',
    'hu_transaction:hu_transaction_read',
    'hu_transaction:hu_transaction_list',
]
NEW_BO_BINDINGS = [
    {'bo_id': 'handling_unit', 'role': 'primary',
     'include_actions': ['read', 'create', 'update', 'delete']},
    {'bo_id': 'handling_unit_item', 'role': 'related',
     'include_actions': ['read', 'list']},
    {'bo_id': 'hu_transaction', 'role': 'related',
     'include_actions': ['read', 'list']},
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _same_list(value, expected) -> bool:
    try:
        return json.loads(value or '[]') == expected
    except (TypeError, ValueError):
        return False


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过')
        return

    row = conn.execute(
        "SELECT menu_name, menu_path, page_type, object_types, "
        "bo_bindings, required_permissions, parent_menu, icon, sort_order "
        "FROM menus WHERE menu_code = ?",
        (MENU_CODE,),
    ).fetchone()
    if not row:
        print(f'  - [MISS] {MENU_CODE} 不存在, 跳过（需先执行 v211）')
        return

    (menu_name, menu_path, page_type, object_types,
     bo_bindings, req_perms, parent, icon, sort_order) = row
    if (page_type == NEW_PAGE_TYPE
            and _same_list(object_types, NEW_OBJECT_TYPES)
            and _same_list(bo_bindings, NEW_BO_BINDINGS)
            and _same_list(req_perms, NEW_PERMISSIONS)):
        print(f'  - [SKIP] {MENU_CODE} ({menu_name}) 已是 MOMP 形态')
        return

    conn.execute(
        "UPDATE menus SET page_type = ?, object_types = ?, bo_bindings = ?, "
        "required_permissions = ?, auto_generated = 0 WHERE menu_code = ?",
        (
            NEW_PAGE_TYPE,
            json.dumps(NEW_OBJECT_TYPES, ensure_ascii=False),
            json.dumps(NEW_BO_BINDINGS, ensure_ascii=False),
            json.dumps(NEW_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ),
    )
    print(f'  - [UPGRADE] {MENU_CODE} ({menu_name}): page_type '
          f'{page_type} → {NEW_PAGE_TYPE}')

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "UPDATE menu_permissions SET required_permissions = ? "
            "WHERE menu_code = ?",
            (json.dumps(NEW_PERMISSIONS, ensure_ascii=False), MENU_CODE),
        )
        if not cur.rowcount:
            conn.execute(
                'INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, '
                'menu_path, required_permissions, required_any_permission, '
                'parent_menu, icon, sort_order, is_active, data_permission_hint) '
                'VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, NULL)',
                (MENU_CODE, menu_name, menu_path,
                 json.dumps(NEW_PERMISSIONS, ensure_ascii=False),
                 parent, icon, sort_order),
            )
        print(f'  - [UPGRADE] menu_permissions.required_permissions → '
              f'{len(NEW_PERMISSIONS)} 条')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    cur = conn.execute(
        "UPDATE menus SET page_type = ?, object_types = ?, bo_bindings = ?, "
        "required_permissions = ? WHERE menu_code = ?",
        (
            OLD_PAGE_TYPE,
            json.dumps(OLD_OBJECT_TYPES, ensure_ascii=False),
            json.dumps(OLD_BO_BINDINGS, ensure_ascii=False),
            json.dumps(OLD_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ),
    )
    restored = getattr(cur, 'rowcount', 0) or 0
    if _table_exists(conn, 'menu_permissions'):
        conn.execute(
            "UPDATE menu_permissions SET required_permissions = ? "
            "WHERE menu_code = ?",
            (json.dumps(OLD_PERMISSIONS, ensure_ascii=False), MENU_CODE),
        )
    print(f'  [REVERT] {restored} 条菜单恢复 object_list / '
          f'{len(OLD_PERMISSIONS)} 条权限')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v213] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v213] 开始: handling-unit-list → multi_object_hub（容器树 + 三 tab）')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v213] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """handling-unit-list 为 MOMP 形态，且 required_permissions 全部真实存在。"""
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
            print(f'[v213 verify] FAIL: {MENU_CODE} 不存在')
            return False
        page_type, auto_generated, is_active, menu_path, pot, ots, req = row
        if page_type != NEW_PAGE_TYPE:
            print(f'[v213 verify] FAIL: page_type={page_type}, 期望 {NEW_PAGE_TYPE}')
            return False
        if is_active != 1:
            print(f'[v213 verify] FAIL: is_active={is_active}, 期望 1')
            return False
        if auto_generated != 0:
            print(f'[v213 verify] FAIL: auto_generated={auto_generated}, 期望 0')
            return False
        if menu_path != '/inventory/handling-units' or pot != 'handling_unit':
            print(f'[v213 verify] FAIL: menu_path={menu_path}, '
                  f'primary_object_type={pot}')
            return False
        if set(json.loads(ots or '[]')) != set(NEW_OBJECT_TYPES):
            print(f'[v213 verify] FAIL: object_types={ots}, '
                  f'期望 {NEW_OBJECT_TYPES}')
            return False
        codes = json.loads(req or '[]')
        if codes != NEW_PERMISSIONS:
            print(f'[v213 verify] FAIL: required_permissions 与 MOMP 形态不一致')
            return False
        # 权限码必须真实存在：路由守卫 every 判定，假码会整页被拦
        if _table_exists(conn, 'permissions'):
            missing = []
            for code in codes:
                if not conn.execute(
                    "SELECT 1 FROM permissions WHERE code = ?", (code,)
                ).fetchone():
                    missing.append(code)
            if missing:
                print(f'[v213 verify] FAIL: 含不存在的权限码 {missing}')
                return False
        print(f'[v213 verify] OK: {MENU_CODE} 已是 {NEW_PAGE_TYPE} '
              f'@ {menu_path}, {len(codes)} 条权限码全部有效')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v213] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v213] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v213] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v213] verify: {"PASS" if _v else "FAIL"}')
