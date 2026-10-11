# -*- coding: utf-8 -*-
"""
[v091 2026-10-11] 主数据父菜单：把 10 条孤儿主数据菜单挂到 master-data 下

背景:
  menu_auto_generator 生成的 10 条主数据菜单 (item-list / item_group-list / uom-list /
  location-list / calendar-list / calendar_day-list / address-list / currency-list /
  region-list / party_group-list) 实测状态为:
      parent_menu = '' 且 show_in_sidebar = 0
  get_visible_menu_tree 的主查询只捞 show_in_sidebar=1 (L322-324), 二级查询只捞
  show_in_sidebar=0 AND parent_menu IN (可见父节点) (L383-387) ⇒ 这 10 条既不在
  侧边栏、也没有父节点, 导航树上完全不可达.

  对照组 (本仓已有的三种可达形态):
    user-permission  → multi_object_hub + menu_path='' + 3 个 show_in_sidebar=1 子菜单
    task-management  → multi_object_hub + 4 个 show_in_sidebar=0 子菜单
    app_warehouse     → 应用根菜单 + 3 个 show_in_sidebar=0 子菜单 (app_registry._attach_app_menus_to_root)
  本次采用 task-management / app_warehouse 这一档: 父节点 show_in_sidebar=1,
  子菜单保持 show_in_sidebar=0 (即用户拍板的 "sb=0 只进侧边栏" 口径).

为何需要 migration 而不是只改 init_menu_permissions.py:
  init_menu_permissions.py 的步骤 6 UPSERT 只遍历 system_menus 列表; 这 10 条是
  menu_auto_generator 用 INSERT OR IGNORE 写入的, 不在 system_menus 里, 脚本不会碰它们.
  且 menu_auto_generator 生成时 parent_menu 恒为 '' (generate_object_list_menu 不返回该键),
  INSERT OR IGNORE 也不会覆盖已有行 ⇒ 只能由 migration 一次性接线.

不改 menu_auto_generator 的理由:
  生成器是"从 BO 元数据推导菜单"的通用引擎, 主数据分组是导航组织策略而非对象属性,
  塞进生成器会让所有 BO 都背上这个概念. 保持"生成器管叶子、migration 管挂载"的分工.

org 的处理:
  用户拍板 org 不进主数据组 —— org-management 留在 user-permission 下 (v075 决策),
  org-list 保持孤儿 (与本轮其它 10 条同构, 不单独处理).

幂等性:
  全部操作为 "仅当当前值 != 目标值才 UPDATE", 重复执行第二次为 no-op.
  父菜单不存在时直接跳过 (交由 init_menu_permissions.py 先创建).

回滚:
  把这 10 条的 parent_menu 改回 ''; master-data 本身交由
  init_menu_permissions.py 的步骤 7.6 冗余清理回收 (auto_generated=0 且不在 system_menus
  白名单的会被 DELETE) —— 故 downgrade 不主动删父菜单, 避免与脚本清理口径打架.
"""
import sqlite3
from pathlib import Path


PARENT_CODE = 'master-data'

# 挂到主数据组下的自动生成菜单。
# 顺序即侧边栏展示顺序 (业务序: 往来单位 → 物料 → 计量 → 位置/地址/区域 → 币种 → 日历)。
# customer-account-management(61) / vendor-account-management(62) 由
# init_menu_permissions.py 的 system_menus 声明, 此处从 63 接续。
CHILD_SORT = [
    ('party_group-list', 63),
    ('item-list', 64),
    ('item_group-list', 65),
    ('uom-list', 66),
    ('location-list', 67),
    ('address-list', 68),
    ('region-list', 69),
    ('currency-list', 70),
    ('calendar-list', 71),
    ('calendar_day-list', 72),
]
CHILD_CODES = [code for code, _ in CHILD_SORT]


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

    parent = conn.execute(
        "SELECT menu_name FROM menus WHERE menu_code = ?",
        (PARENT_CODE,),
    ).fetchone()
    if not parent:
        print(f'  - 父菜单 {PARENT_CODE} 不存在, 跳过 '
              f'(请先跑 init_menu_permissions.py 创建)')
        return
    print(f'  - 父菜单就绪: {PARENT_CODE} ({parent[0]})')

    attached = missing = 0
    for code, sort_order in CHILD_SORT:
        row = conn.execute(
            "SELECT menu_name, parent_menu, sort_order FROM menus "
            "WHERE menu_code = ?",
            (code,),
        ).fetchone()
        if not row:
            print(f'  - [MISS] {code} 不存在, 跳过')
            missing += 1
            continue
        if row[1] == PARENT_CODE and row[2] == sort_order:
            print(f'  - [SKIP] {code} ({row[0]}) 已在 {PARENT_CODE} 下且顺序正确')
            continue
        conn.execute(
            "UPDATE menus SET parent_menu = ?, sort_order = ? WHERE menu_code = ?",
            (PARENT_CODE, sort_order, code),
        )
        print(f'  - [LINK] {code} ({row[0]}) parent_menu: '
              f'"{row[1]}" → "{PARENT_CODE}", sort_order: {row[2]} → {sort_order}')
        attached += 1

    print(f'  - [SUMMARY] 挂载 {attached} 条, 跳过 {missing} 条不存在, '
          f'共 {len(CHILD_CODES)} 条目标')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    reset = 0
    for code, _ in CHILD_SORT:
        cur = conn.execute(
            "UPDATE menus SET parent_menu = '', sort_order = 99 "
            "WHERE menu_code = ? AND parent_menu = ?",
            (code, PARENT_CODE),
        )
        reset += getattr(cur, 'rowcount', 0) or 0
    print(f'  [REVERT] {reset} 条菜单 parent_menu → "" (顶级), sort_order → 99')


# ─── 入口签名 ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v091] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v091] 开始: 主数据菜单挂载到 master-data 父菜单下')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v091] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """10 条目标菜单全部挂在 master-data 下, 且父菜单本身可见。"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            return False
        parent = conn.execute(
            "SELECT show_in_sidebar FROM menus WHERE menu_code = ?",
            (PARENT_CODE,),
        ).fetchone()
        if not parent or parent[0] != 1:
            print('[v091 verify] FAIL: 父菜单不存在或 show_in_sidebar != 1')
            return False
        bad = conn.execute(
            "SELECT menu_code FROM menus "
            "WHERE menu_code IN ({0}) AND COALESCE(parent_menu, '') != ?".format(
                ','.join('?' for _ in CHILD_CODES)
            ),
            (*CHILD_CODES, PARENT_CODE),
        ).fetchall()
        if bad:
            print(f'[v091 verify] FAIL: 未挂载 {[r[0] for r in bad]}')
            return False
        missing = conn.execute(
            "SELECT menu_code FROM menus WHERE menu_code IN ({0})".format(
                ','.join('?' for _ in CHILD_CODES)
            ),
            CHILD_CODES,
        ).fetchall()
        got = {r[0] for r in missing}
        absent = [c for c in CHILD_CODES if c not in got]
        if absent:
            print(f'[v091 verify] WARN: 目标菜单不存在 {absent} (非本 migration 职责)')
        print(f'[v091 verify] OK: {len(CHILD_CODES) - len(absent)}/'
              f'{len(CHILD_CODES)} 条已挂载, 父菜单可见')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v091] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v091] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v091] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v091] verify: {"PASS" if _v else "FAIL"}')