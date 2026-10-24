# -*- coding: utf-8 -*-
"""
[v105 2026-10-24] 组织管理页改版：object_list → multi_object_hub + 权限码收敛

背景:
  组织管理页(org-management, /org-management)的页面形态在 2026-10-24 收敛为模型驱动:
  左树(组织层级) + 右表(组织列表) 取自 org.yaml 的 ui_view_config.hub, 前端不再有
  OrgManagement.vue / OrgScopeTree.vue 专用壳, 与 location/region/calendar/uom
  四个页同型。但组织页是**唯一没有配套迁移**的一页(v099/v100/v103/v104 都有),
  只改了 init_menu_permissions.py 的声明 —— 只跑迁移不跑种子的环境会退回 object_list。

  同时该行的 required_permissions 仍是单段式老口径
  (org:create / org:read / org:update / org:delete / org:list / org:import / org:export),
  其中 org:delete / org:list / org:import / org:export 在 permissions 表**不存在**
  (真实码为双段式 org:org_*)。角色配置界面会把这几条渲染成永远授不了的"假权限",
  与 v099–v104 对四页的收敛口径不一致。

改动:
  1. page_type: object_list → multi_object_hub; auto_generated → 0。
  2. required_permissions 收敛为 permissions 表真实存在的 5 条(org:org_*)。
  3. bo_bindings 的 include_actions 去掉 import / export(该页不导出)。
  4. menu_path 保持 '/org-management' ⇒ object_type_route_map['org'] 与书签不变;
     parent_menu 保持 'user-permission', sort_order 保持 53(与 user-management 并列)。

幂等: UPDATE 带状态判据(page_type + auto_generated + 权限串), 重复执行为 no-op。
回滚: 恢复 object_list / auto_generated=1 与旧 7 条权限码(仅作形态回退, 不重建已删组件)。

注: 库里另有 menu_auto_generator 生成的 org-list(/org, show_in_sidebar=0),
  不在 /visible 菜单接口的查询范围内(该接口只取 show_in_sidebar=1), 不影响本页;
  本 migration 不处理它。
"""
import json
import sqlite3
from pathlib import Path


MENU_CODE = 'org-management'

# 旧形态 (单段式手工声明口径), 供 downgrade 复原
OLD_PAGE_TYPE = 'object_list'
OLD_AUTO_GENERATED = 1
OLD_BO_BINDINGS = [
    {'bo_id': 'org', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list',
                         'import', 'export']}
]
OLD_PERMISSIONS = [
    'org:create', 'org:read', 'org:update',
    'org:delete', 'org:list', 'org:import', 'org:export',
]

# 新形态 (与 init_menu_permissions.py 的声明保持一致)
NEW_PAGE_TYPE = 'multi_object_hub'
NEW_OBJECT_TYPES = ['org']
NEW_BO_BINDINGS = [
    {'bo_id': 'org', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']}
]
NEW_PERMISSIONS = [
    'org:org_create',
    'org:org_read',
    'org:org_update',
    'org:org_delete',
    'org:org_list',
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
    try:
        current_codes = json.loads(req_perms or '[]')
    except Exception:
        current_codes = []
    if page_type == NEW_PAGE_TYPE and auto_generated == 0 \
            and current_codes == NEW_PERMISSIONS:
        print(f'  - [SKIP] {MENU_CODE} ({menu_name}) 已是新形态')
        return

    conn.execute(
        "UPDATE menus SET page_type = ?, primary_object_type = ?, "
        "object_types = ?, bo_bindings = ?, required_permissions = ?, "
        "auto_generated = 0 "
        "WHERE menu_code = ?",
        (
            NEW_PAGE_TYPE,
            'org',
            json.dumps(NEW_OBJECT_TYPES),
            json.dumps(NEW_BO_BINDINGS, ensure_ascii=False),
            json.dumps(NEW_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ),
    )
    print(f'  - [UPGRADE] {MENU_CODE} ({menu_name}): page_type '
          f'{page_type} → {NEW_PAGE_TYPE}, auto_generated {auto_generated} → 0')
    print(f'  - [UPGRADE] required_permissions {current_codes} → '
          f'{NEW_PERMISSIONS} (去掉表里不存在的单段式码)')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    cur = conn.execute(
        "UPDATE menus SET page_type = ?, auto_generated = ?, bo_bindings = ?, "
        "required_permissions = ? WHERE menu_code = ?",
        (
            OLD_PAGE_TYPE,
            OLD_AUTO_GENERATED,
            json.dumps(OLD_BO_BINDINGS, ensure_ascii=False),
            json.dumps(OLD_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ),
    )
    print(f'  [REVERT] {getattr(cur, "rowcount", 0) or 0} 条菜单恢复 object_list '
          f'(页面壳已删除, 需回滚代码方可恢复渲染)')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v105] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v105] 开始: 组织管理页改版 object_list → multi_object_hub + 权限码收敛')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v105] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """org-management 已是 MOMP 形态, 且 required_permissions 全部真实存在。"""
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
            print(f'[v105 verify] FAIL: {MENU_CODE} 不存在')
            return False
        page_type, auto_generated, is_active, menu_path, pot, req = row
        if page_type != NEW_PAGE_TYPE:
            print(f'[v105 verify] FAIL: page_type={page_type}, 期望 {NEW_PAGE_TYPE}')
            return False
        if is_active != 1:
            print(f'[v105 verify] FAIL: is_active={is_active}, 期望 1')
            return False
        if auto_generated != 0:
            print(f'[v105 verify] FAIL: auto_generated={auto_generated}, 期望 0')
            return False
        if menu_path != '/org-management' or pot != 'org':
            print(f'[v105 verify] FAIL: menu_path={menu_path}, '
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
            print(f'[v105 verify] FAIL: required_permissions 含不存在的权限码 {missing}')
            return False
        print(f'[v105 verify] OK: {MENU_CODE} 已是 {NEW_PAGE_TYPE} @ /org-management, '
              f'{len(codes)} 条权限码全部有效')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v105] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v105] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v105] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v105] verify: {"PASS" if _v else "FAIL"}')
