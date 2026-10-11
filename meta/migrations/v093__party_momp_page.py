# -*- coding: utf-8 -*-
"""
[v093 2026-10-11] 往来单位聚合页：往来单位组从独立菜单降级为 MOMP 页 tab

背景:
  往来单位组 (party_group) 此前有自动生成的独立菜单 party_group-list (so=63,
  parent=master-data), 与往来单位菜单 party-management (so=59) 平级。但 party
  不直挂 group —— 分组关系在关系层 party_relations.group_id (N:1) → party_groups,
  伙伴侧是 party2_id。查"某组下有哪些伙伴"只能去关系页手工筛组, 割裂且反直觉。

改动:
  1. init_menu_permissions.py 把 party-management 从 object_list 升级为
     multi_object_hub 单页 hub (object_types=['party','party_group']), 前端
     GenericTabContainer 精确映射到 PartyManagement.vue (MOMP 泛化页):
     左树 = 往来单位组 (勾选过滤), 右表 = 往来单位 / 往来单位组 两个 tab。
  2. 本 migration 下架 party_group-list (入口收进 MOMP 页的往来单位组 tab,
     同 v092 对 item-group-list 的处理)。

  下架方式用 is_active=0 而非 DELETE (同 v092):
    - 菜单被权限集/角色的 grant 关系引用, 物理删除会留下悬挂引用
    - 保留行便于回滚 (downgrade 直接 is_active=1) 与排查

为何需要 migration 而不是只改 init_menu_permissions.py:
  party_group-list 是 menu_auto_generator 用 INSERT OR IGNORE 写入的
  (auto_generated=1), 不在 system_menus 列表里, init 脚本不会碰它。
  生成器管叶子, migration 管下架与挂载 (同 v091/v092)。

幂等性:
  全部操作为 "仅当 is_active != 0 才 UPDATE", 重复执行为 no-op。
  party-management 不存在时直接跳过 (交由 init_menu_permissions.py 先创建)。

回滚:
  把 party_group-list is_active 恢复为 1, 并把 sort_order 复原 (63)。
  party-management 本身交由 init_menu_permissions.py 回收 (从 system_menus
  移除该条, 并把 page_type 回滚为 object_list 形态即可)。
"""
import sqlite3
from pathlib import Path


PARENT_CODE = 'master-data'

# (menu_code, 恢复用的 sort_order)
RETIRED = [
    ('party_group-list', 63),
]
RETIRED_CODES = [code for code, _ in RETIRED]

# 接管往来单位域的新菜单, 必须存在才能下架旧菜单
NEW_MENU_CODE = 'party-management'


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

    new_menu = conn.execute(
        "SELECT menu_name, sort_order, is_active FROM menus WHERE menu_code = ?",
        (NEW_MENU_CODE,),
    ).fetchone()
    if not new_menu:
        print(f'  - 新菜单 {NEW_MENU_CODE} 不存在, 跳过 '
              f'(请先跑 init_menu_permissions.py 创建)')
        return
    if new_menu[2] != 1:
        print(f'  - 新菜单 {NEW_MENU_CODE} 当前 is_active={new_menu[2]}, 跳过下架')
        return
    print(f'  - 新菜单就绪: {NEW_MENU_CODE} ({new_menu[0]}, so={new_menu[1]})')

    retired = 0
    for code, _ in RETIRED:
        row = conn.execute(
            "SELECT menu_name, is_active FROM menus WHERE menu_code = ?",
            (code,),
        ).fetchone()
        if not row:
            print(f'  - [MISS] {code} 不存在, 跳过')
            continue
        if row[1] == 0:
            print(f'  - [SKIP] {code} ({row[0]}) 已下架')
            continue
        conn.execute("UPDATE menus SET is_active = 0 WHERE menu_code = ?", (code,))
        print(f'  - [RETIRE] {code} ({row[0]}) is_active: 1 → 0')
        retired += 1

    print(f'  - [SUMMARY] 下架 {retired} 条, 共 {len(RETIRED_CODES)} 条目标')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    restored = 0
    for code, sort_order in RETIRED:
        cur = conn.execute(
            "UPDATE menus SET is_active = 1, parent_menu = ?, sort_order = ? "
            "WHERE menu_code = ?",
            (PARENT_CODE, sort_order, code),
        )
        restored += getattr(cur, 'rowcount', 0) or 0
    print(f'  [REVERT] {restored} 条菜单 is_active → 1, 挂回 {PARENT_CODE}')


# ─── 入口签名 (与 v092 保持一致) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v093] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v093] 开始: 下架 party_group-list (往来单位域收进 MOMP 页)')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v093] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """party_group-list 已下架, 新菜单可用。"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            return False
        new_menu = conn.execute(
            "SELECT is_active FROM menus WHERE menu_code = ?", (NEW_MENU_CODE,)
        ).fetchone()
        if not new_menu or new_menu[0] != 1:
            print(f'[v093 verify] FAIL: {NEW_MENU_CODE} 不存在或未启用')
            return False
        still_on = conn.execute(
            "SELECT menu_code, menu_name FROM menus "
            "WHERE menu_code IN ({0}) AND is_active != 0".format(
                ','.join('?' for _ in RETIRED_CODES)
            ),
            RETIRED_CODES,
        ).fetchall()
        if still_on:
            print(f'[v093 verify] FAIL: 仍未下架 {[r[0] for r in still_on]}')
            return False
        print(f'[v093 verify] OK: {NEW_MENU_CODE} 已启用, '
              f'{len(RETIRED_CODES)} 条旧菜单已下架')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v093] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v093] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v093] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v093] verify: {"PASS" if _v else "FAIL"}')