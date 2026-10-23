# -*- coding: utf-8 -*-
"""
[v100 2026-10-23] 行政区划管理页改版：object_list → multi_object_hub（左树 + 列表）

背景:
  region-list 是 menu_auto_generator 自动生成的 object_list 菜单
  (auto_generated=1, menu_path='/region', 无左侧树)。region 是国/省/市/区
  四级自引用树 (parent_id + level), 具备左树条件。与位置管理(区域/仓库/库位)
  同款改造, 保持主数据页形态一致。

改动:
  1. src/components/common/RegionScopeTree/RegionScopeTree.vue  新增: 区划树
     (节点标 level: 国家/省级/地市/区县)。
  2. src/views/MasterData/RegionManagement.vue  新增: MOMP 配置注入页
     (objectTypes=['region'], filterStrategies.region 按 effective 走 id__in)。
  3. src/views/GenericTabContainer.vue  注册 REGION_MANAGEMENT_LOADER
     (menu_code='region-list')。
  4. init_menu_permissions.py  手工声明 region-list (auto_generated=0)。
  5. meta/schemas/region.yaml  删掉 list.columns 里的 updated_at ——
     字典表该列永远等于种入时间(updated_at 是审计派生字段, 无更新记录时回退
     created_at), 没有信息量。
  6. 本 migration 改写存量菜单行。

  同 location-list: menu_path 保持 '/region', object_type_route_map['region']
  不受影响; required_permissions 收敛为 permissions 表真实存在的 5 条
  (老行里的 region:import / region:export 并不存在, 路由守卫 every 判定必拦)。

幂等: UPDATE 带状态判据; 菜单不存在时跳过 (交由 init 创建)。
回滚: 恢复 object_list / auto_generated=1 与旧权限码。
"""
import json
import sqlite3
from pathlib import Path


MENU_CODE = 'region-list'

# 旧形态 (自动生成器口径), 供 downgrade 复原
OLD_PAGE_TYPE = 'object_list'
OLD_BO_BINDINGS = [
    {'bo_id': 'region', 'role': 'primary',
     'include_actions': ['export', 'region_update', 'region_list',
                         'region_delete', 'import', 'region_create',
                         'region_read']}
]
OLD_PERMISSIONS = [
    'region:export', 'region:region_update', 'region:region_list',
    'region:region_delete', 'region:import', 'region:region_create',
    'region:region_read'
]

# 新形态 (与 init_menu_permissions.py 的声明保持一致)
NEW_PAGE_TYPE = 'multi_object_hub'
NEW_BO_BINDINGS = [
    {'bo_id': 'region', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']}
]
NEW_PERMISSIONS = [
    'region:region_create',
    'region:region_read',
    'region:region_update',
    'region:region_delete',
    'region:region_list',
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
            and 'region:import' not in (req_perms or ''):
        print(f'  - [SKIP] {MENU_CODE} ({menu_name}) 已是新形态')
        return

    conn.execute(
        "UPDATE menus SET page_type = ?, primary_object_type = ?, "
        "object_types = ?, bo_bindings = ?, required_permissions = ?, "
        "parent_menu = 'master-data', icon = 'Box', sort_order = 69, "
        "auto_generated = 0 "
        "WHERE menu_code = ?",
        (
            NEW_PAGE_TYPE,
            'region',
            json.dumps(['region']),
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
    print(f'  [REVERT] {getattr(cur, "rowcount", 0) or 0} 条菜单恢复 object_list')
    print('  [REVERT] 菜单声明需从 init_menu_permissions.py 移除')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v100] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v100] 开始: 行政区划管理改版 object_list → multi_object_hub (左树 + 列表)')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v100] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """region-list 已是 MOMP 形态, 且 required_permissions 全部真实存在。"""
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
            print(f'[v100 verify] FAIL: {MENU_CODE} 不存在')
            return False
        page_type, auto_generated, is_active, menu_path, pot, req = row
        if page_type != NEW_PAGE_TYPE:
            print(f'[v100 verify] FAIL: page_type={page_type}, 期望 {NEW_PAGE_TYPE}')
            return False
        if is_active != 1:
            print(f'[v100 verify] FAIL: is_active={is_active}, 期望 1')
            return False
        if auto_generated != 0:
            print(f'[v100 verify] FAIL: auto_generated={auto_generated}, 期望 0')
            return False
        if menu_path != '/region' or pot != 'region':
            print(f'[v100 verify] FAIL: menu_path={menu_path}, '
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
            print(f'[v100 verify] FAIL: required_permissions 含不存在的权限码 {missing}')
            return False
        print(f'[v100 verify] OK: {MENU_CODE} 已是 {NEW_PAGE_TYPE} @ /region, '
              f'{len(codes)} 条权限码全部有效')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v100] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v100] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v100] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v100] verify: {"PASS" if _v else "FAIL"}')
