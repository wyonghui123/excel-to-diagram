# -*- coding: utf-8 -*-
"""
[v099 2026-10-23] 位置管理页改版：object_list → multi_object_hub（左树 + 列表）

背景:
  location-list 是 menu_auto_generator 自动生成的 object_list 菜单
  (auto_generated=1, menu_path='/location', 无左侧树)。同为主数据页, 组织管理
  (/org-management) 与物料管理 (/material-management) 都是「左树 + 右表」形态,
  唯独位置管理是光板列表 —— 形态不一致。

  location 本身就是统一自引用树 (parent_id: site → warehouse → zone → bin),
  技术上完全具备左树条件。

改动:
  1. src/components/common/LocationScopeTree/LocationScopeTree.vue  新增: 位置范围树
     (节点标 location_type, 避免在错误层级勾选)。
  2. src/views/MasterData/LocationManagement.vue  新增: MOMP 配置注入页
     (objectTypes=['location'], scopeTree=LocationScopeTree,
      filterStrategies.location 按 effective 走 id__in)。
  3. src/views/GenericTabContainer.vue  注册 LOCATION_MANAGEMENT_LOADER
     (menu_code='location-list' 精确映射)。
  4. init_menu_permissions.py  把 location-list 从「自动生成」改为「手工声明」
     (page_type=multi_object_hub, auto_generated=0, menu_path 仍为 '/location')。
  5. 本 migration 改写存量行 (生成器只 INSERT OR IGNORE, 不改既有行)。

为何需要 migration 而不只改 init_menu_permissions.py:
  存量行是生成器写入的 (auto_generated=1)。init 的步骤 6 UPSERT 会更新已在
  system_menus 中声明的菜单 —— 声明落地后 UPSERT 即可覆盖 page_type。
  但 v098 实测过 init 的「步骤 7.5/7.6 清理」在 commit 之后, 不可依赖;
  且本地/存量环境跑迁移时 init 未必同步执行。故由本 migration 显式改写,
  保证「跑完迁移即是新形态」, 不依赖 init 的执行顺序。

  menu_path 保持 '/location' 不变 —— object_type_route_map['location'] 仍指向
  该路径 (FK 链接落点)、存量书签不失效。

required_permissions 收敛:
  自动生成的老行里带 location:import / location:export, 但 permissions 表只有
  5 条双段式权限码 (location:location_create / _read / _update / _delete / _list)。
  前端路由守卫对 required_permissions 是 every 判定, 引用不存在的权限码会把整页
  拦下, 故本次一并收敛为实际存在的 5 条。

幂等性:
  UPDATE 带 WHERE 条件保护 (page_type != 'multi_object_hub' OR auto_generated != 0
  OR required_permissions 仍含 import), 重复执行为 no-op。
  location-list 不存在时直接跳过。

回滚:
  恢复 page_type='object_list' / auto_generated=1 与旧的 bo_bindings、
  required_permissions; 菜单声明本身交由 init_menu_permissions.py 回收。
"""
import json
import sqlite3
from pathlib import Path


MENU_CODE = 'location-list'

# 旧形态 (自动生成器口径), 供 downgrade 复原
OLD_PAGE_TYPE = 'object_list'
OLD_BO_BINDINGS = [
    {'bo_id': 'location', 'role': 'primary',
     'include_actions': ['location_list', 'import', 'location_read',
                         'export', 'location_update', 'location_create',
                         'location_delete']}
]
OLD_PERMISSIONS = [
    'location:location_list', 'location:import', 'location:location_read',
    'location:export', 'location:location_update', 'location:location_create',
    'location:location_delete'
]

# 新形态 (与 init_menu_permissions.py 的声明保持一致)
NEW_PAGE_TYPE = 'multi_object_hub'
NEW_BO_BINDINGS = [
    {'bo_id': 'location', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']}
]
NEW_PERMISSIONS = [
    'location:location_create',
    'location:location_read',
    'location:location_update',
    'location:location_delete',
    'location:location_list',
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


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
        print(f'  - [MISS] {MENU_CODE} 不存在, 跳过 '
              f'(交由 init_menu_permissions.py 创建)')
        return

    menu_name, page_type, auto_generated, req_perms = row
    if page_type == NEW_PAGE_TYPE and auto_generated == 0 \
            and 'location:import' not in (req_perms or ''):
        print(f'  - [SKIP] {MENU_CODE} ({menu_name}) 已是新形态')
        return

    conn.execute(
        "UPDATE menus SET page_type = ?, primary_object_type = ?, "
        "object_types = ?, bo_bindings = ?, required_permissions = ?, "
        "parent_menu = 'master-data', icon = 'Box', sort_order = 67, "
        "auto_generated = 0 "
        "WHERE menu_code = ?",
        (
            NEW_PAGE_TYPE,
            'location',
            json.dumps(['location']),
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
        "auto_generated = 1 "
        "WHERE menu_code = ?",
        (
            OLD_PAGE_TYPE,
            json.dumps(OLD_BO_BINDINGS, ensure_ascii=False),
            json.dumps(OLD_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ),
    )
    restored = getattr(cur, 'rowcount', 0) or 0
    print(f'  [REVERT] {restored} 条菜单恢复 object_list / auto_generated=1')
    print('  [REVERT] 菜单声明需从 init_menu_permissions.py 移除')


# ─── 入口签名 (与 v092/v093/v098 保持一致) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v099] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v099] 开始: 位置管理改版 object_list → multi_object_hub (左树 + 列表)')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v099] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """location-list 已是 MOMP 形态, 且 required_permissions 全部真实存在。"""
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
            print(f'[v099 verify] FAIL: {MENU_CODE} 不存在')
            return False
        page_type, auto_generated, is_active, menu_path, pot, req = row
        if page_type != NEW_PAGE_TYPE:
            print(f'[v099 verify] FAIL: page_type={page_type}, 期望 {NEW_PAGE_TYPE}')
            return False
        if is_active != 1:
            print(f'[v099 verify] FAIL: is_active={is_active}, 期望 1')
            return False
        if auto_generated != 0:
            print(f'[v099 verify] FAIL: auto_generated={auto_generated}, 期望 0')
            return False
        if menu_path != '/location' or pot != 'location':
            print(f'[v099 verify] FAIL: menu_path={menu_path}, '
                  f'primary_object_type={pot}')
            return False
        # required_permissions 里的每条权限码必须真实存在, 否则路由守卫 every 判定必拦
        codes = json.loads(req or '[]')
        missing = []
        if _table_exists(conn, 'permissions'):
            for code in codes:
                found = conn.execute(
                    "SELECT 1 FROM permissions WHERE code = ?", (code,)
                ).fetchone()
                if not found:
                    missing.append(code)
        if missing:
            print(f'[v099 verify] FAIL: required_permissions 含不存在的权限码 {missing}')
            return False
        print(f'[v099 verify] OK: {MENU_CODE} 已是 {NEW_PAGE_TYPE} @ /location, '
              f'{len(codes)} 条权限码全部有效')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v099] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v099] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v099] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v099] verify: {"PASS" if _v else "FAIL"}')
