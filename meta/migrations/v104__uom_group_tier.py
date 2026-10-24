# -*- coding: utf-8 -*-
"""
[v104 2026-10-24] 计量单位两层模型：uom_type 枚举 → uom_group 组 + 组内换算

背景:
  一期（item_uom_conversion）只做了物料级换算，单位分类仍是 uom_type 枚举
  （quantity/weight/volume/...），没有"类层"主对象，也就没有组基本单位与组内标准换算。
  本次按 SAP（T006D dimension + T006 换算）/ Oracle（UOM_CLASS + 类级换算）的双层模型升级：
    uom_group（类层主对象，含 base_uom_id 组基本单位）
    uom_conversion（组内标准换算：1 个 uom = factor 个组基本单位）
    uom.uom_group_id 取代 uom_type；item_uom_conversion 降为物料级例外（保留）。

改动:
  1. 按 uoms.uom_type 的现存取值建组（7 个标准枚举用固定 code/name；其它值用大写 code），
     组基本单位取该组内启用状态、最小 id 的单位（组里暂无单位时留空，后续在 UI 补）；
  2. 回填 uoms.uom_group_id（仅处理 NULL 行，幂等）；
  3. 把 uom-list 菜单行从自动生成的 object_list 升级为 multi_object_hub（左树 + 两 tab），
     required_permissions 收敛为 permissions 表真实存在的 uom 5 条 + uom_group 5 条
     （老行里的 uom:import / uom:export 并不存在，会让前端路由守卫 every() 整页拦下）。

  表结构由平台 sync_schema_from_meta 自动创建 / 补列（uom_groups、uom_conversions、
  uoms.uom_group_id），本 migration 只负责数据回填与菜单行改写。
  注: uoms.uom_type 物理列因平台不支持删列而残留，YAML 已不再声明（drift 已容忍）。

幂等: 建组按 code 判重；回填只处理 uom_group_id IS NULL；菜单 UPDATE 带状态判据。
回滚: 菜单恢复 object_list 旧形态；组与回填数据保留（不删数据，避免不可逆）。
"""
import json
import sqlite3
from pathlib import Path

MENU_CODE = 'uom-list'

# uom_type 枚举 → (组编码, 组名称)
GROUP_SEEDS = {
    'quantity': ('QTY', '数量'),
    'weight': ('WGT', '重量'),
    'volume': ('VOL', '体积'),
    'length': ('LEN', '长度'),
    'area': ('AREA', '面积'),
    'time': ('TIME', '时间'),
    'packaging': ('PKG', '包装'),
}
FALLBACK_CODE = 'MISC'
FALLBACK_NAME = '未分类'

# 旧形态（自动生成口径），供 downgrade 复原
OLD_PAGE_TYPE = 'object_list'
OLD_OBJECT_TYPES = ['uom']
OLD_BO_BINDINGS = [
    {'bo_id': 'uom', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']}
]
OLD_PERMISSIONS = [
    'uom:import',
    'uom:export',
    'uom:uom_create',
    'uom:uom_read',
    'uom:uom_update',
    'uom:uom_delete',
    'uom:uom_list',
]

# 新形态（与 init_menu_permissions.py 的声明保持一致）
NEW_PAGE_TYPE = 'multi_object_hub'
NEW_OBJECT_TYPES = ['uom', 'uom_group']
NEW_BO_BINDINGS = [
    {'bo_id': 'uom', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']},
    {'bo_id': 'uom_group', 'role': 'primary',
     'include_actions': ['create', 'read', 'update', 'delete', 'list']},
]
NEW_PERMISSIONS = [
    'uom:uom_create',
    'uom:uom_read',
    'uom:uom_update',
    'uom:uom_delete',
    'uom:uom_list',
    'uom_group:uom_group_create',
    'uom_group:uom_group_read',
    'uom_group:uom_group_update',
    'uom_group:uom_group_delete',
    'uom_group:uom_group_list',
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _ensure_group(conn: sqlite3.Connection, code: str, name: str,
                  base_uom_id) -> int:
    row = conn.execute(
        "SELECT id FROM uom_groups WHERE code = ?", (code,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO uom_groups (code, name, base_uom_id, status) VALUES (?, ?, ?, 'active')",
        (code, name, base_uom_id))
    return cur.lastrowid


def _backfill_groups(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'uoms') or not _table_exists(conn, 'uom_groups'):
        print('  - uoms/uom_groups 表不存在, 跳过回填')
        return
    cols = _columns(conn, 'uoms')
    if 'uom_group_id' not in cols:
        print('  - uoms.uom_group_id 列不存在, 跳过回填')
        return
    if 'uom_type' not in cols:
        print('  - uoms.uom_type 列已不存在（新库）, 无需回填')
        return

    rows = conn.execute(
        "SELECT DISTINCT uom_type FROM uoms WHERE uom_group_id IS NULL").fetchall()
    types = [r[0] for r in rows]
    if not types:
        print('  - [SKIP] 所有单位均已归属计量单位组')
        return

    for uom_type in types:
        if uom_type and uom_type in GROUP_SEEDS:
            code, name = GROUP_SEEDS[uom_type]
        elif uom_type:
            code, name = str(uom_type).upper()[:20], str(uom_type)
        else:
            code, name = FALLBACK_CODE, FALLBACK_NAME

        base = conn.execute(
            "SELECT id FROM uoms WHERE uom_type IS ? AND status='active' "
            "ORDER BY id LIMIT 1", (uom_type,)).fetchone()
        base_id = base[0] if base else None
        group_id = _ensure_group(conn, code, name, base_id)
        cur = conn.execute(
            "UPDATE uoms SET uom_group_id = ? WHERE uom_type IS ? AND uom_group_id IS NULL",
            (group_id, uom_type))
        print(f'  - [GROUP] {code} {name}: 归属 {getattr(cur, "rowcount", 0) or 0} 个单位'
              f'（基本单位 {"#" + str(base_id) if base_id else "未设置"}）')


def _upgrade_menu(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过')
        return
    row = conn.execute(
        "SELECT menu_name, page_type, auto_generated, object_types "
        "FROM menus WHERE menu_code = ?", (MENU_CODE,)).fetchone()
    if not row:
        print(f'  - [MISS] {MENU_CODE} 不存在, 跳过 (交由 init_menu_permissions.py 创建)')
        return

    menu_name, page_type, auto_generated, object_types = row
    try:
        current_types = json.loads(object_types or '[]')
    except Exception:
        current_types = []
    if page_type == NEW_PAGE_TYPE and auto_generated == 0 \
            and 'uom_group' in current_types:
        print(f'  - [SKIP] {MENU_CODE} ({menu_name}) 已是新形态')
        return

    conn.execute(
        "UPDATE menus SET page_type = ?, primary_object_type = ?, "
        "object_types = ?, bo_bindings = ?, required_permissions = ?, "
        "parent_menu = 'master-data', sort_order = 66, auto_generated = 0 "
        "WHERE menu_code = ?",
        (
            NEW_PAGE_TYPE,
            'uom',
            json.dumps(NEW_OBJECT_TYPES),
            json.dumps(NEW_BO_BINDINGS, ensure_ascii=False),
            json.dumps(NEW_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ))
    print(f'  - [UPGRADE] {MENU_CODE} ({menu_name}): page_type '
          f'{page_type} → {NEW_PAGE_TYPE}, object_types {current_types} → {NEW_OBJECT_TYPES}')
    print(f'  - [UPGRADE] required_permissions 收敛为 {len(NEW_PERMISSIONS)} 条真实权限码')


def _downgrade_menu(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    cur = conn.execute(
        "UPDATE menus SET page_type = ?, object_types = ?, bo_bindings = ?, "
        "required_permissions = ?, auto_generated = 1 WHERE menu_code = ?",
        (
            OLD_PAGE_TYPE,
            json.dumps(OLD_OBJECT_TYPES),
            json.dumps(OLD_BO_BINDINGS, ensure_ascii=False),
            json.dumps(OLD_PERMISSIONS, ensure_ascii=False),
            MENU_CODE,
        ))
    print(f'  [REVERT] {getattr(cur, "rowcount", 0) or 0} 条菜单恢复 {OLD_PAGE_TYPE}')
    print('  [REVERT] uom_groups / uom_conversions / uom_group_id 回填数据保留（不删数据）')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v104] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v104] 开始: 计量单位两层模型（uom_type → uom_group + uom_conversion）')
        _backfill_groups(conn)
        _upgrade_menu(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v104] migrate 失败: {e}')
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
        # 1. 单位归属
        if _table_exists(conn, 'uoms'):
            cols = _columns(conn, 'uoms')
            if 'uom_group_id' in cols:
                left = conn.execute(
                    "SELECT COUNT(*) FROM uoms WHERE uom_group_id IS NULL").fetchone()[0]
                if left:
                    print(f'[v104 verify] FAIL: 仍有 {left} 个单位未归属计量单位组')
                    return False
        # 2. 菜单形态
        row = conn.execute(
            "SELECT page_type, auto_generated, is_active, menu_path, "
            "primary_object_type, object_types, required_permissions "
            "FROM menus WHERE menu_code = ?", (MENU_CODE,)).fetchone()
        if not row:
            print(f'[v104 verify] FAIL: {MENU_CODE} 不存在')
            return False
        page_type, auto_generated, is_active, menu_path, pot, ots, req = row
        if page_type != NEW_PAGE_TYPE or auto_generated != 0 or is_active != 1:
            print(f'[v104 verify] FAIL: page_type={page_type}, auto_generated={auto_generated}, '
                  f'is_active={is_active}')
            return False
        if menu_path != '/uom' or pot != 'uom':
            print(f'[v104 verify] FAIL: menu_path={menu_path}, primary_object_type={pot}')
            return False
        try:
            types = json.loads(ots or '[]')
        except Exception:
            types = []
        if 'uom' not in types or 'uom_group' not in types:
            print(f'[v104 verify] FAIL: object_types={types}, 期望含 uom 与 uom_group')
            return False
        # 3. 权限码有效性
        codes = json.loads(req or '[]')
        missing = []
        if _table_exists(conn, 'permissions'):
            for code in codes:
                if not conn.execute(
                        "SELECT 1 FROM permissions WHERE code = ?", (code,)).fetchone():
                    missing.append(code)
        if missing:
            print('[v104 verify] FAIL: required_permissions 含不存在的权限码 '
                  f'{missing}（需先跑 init_auth.seed_permissions 派生新对象权限）')
            return False
        groups = 0
        if _table_exists(conn, 'uom_groups'):
            groups = conn.execute("SELECT COUNT(*) FROM uom_groups").fetchone()[0]
        print(f'[v104 verify] OK: {MENU_CODE} 已是 {NEW_PAGE_TYPE} @ /uom '
              f'(object_types={types}), {len(codes)} 条权限码全部有效, '
              f'计量单位组 {groups} 个')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v104] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _downgrade_menu(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v104] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v104] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v104] verify: {"PASS" if _v else "FAIL"}')
