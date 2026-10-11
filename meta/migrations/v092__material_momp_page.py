# -*- coding: utf-8 -*-
"""
[v092 2026-10-11] 物料管理改版：物料组从独立菜单降级为 MOMP 页左树

背景:
  物料组 (item_group) 原先是 master-data 下的独立菜单 item-group-list (so=65),
  与物料菜单 item-list (so=64) 平级。查物料时用户只能:
    点物料组菜单 → 记住组 id → 回物料菜单 → 手工填 item_group_id 筛选条件。
  物料组是物料的天然分类维度 (items.item_group_id 直 FK), 这个割裂的导航是
  纯粹的历史遗留 —— 自动生成的菜单只知道"每个 BO 一条菜单", 不知道它们有主从关系。

改动:
  1. init_menu_permissions.py 新增 material-management 菜单 (multi_object_hub,
     menu_path='/material-management', object_types=['item'], sort_order=64),
     前端 GenericTabContainer 精确映射到 MaterialManagement.vue (MOMP 泛化页):
     左树 = 物料组 (勾选过滤), 右表 = 物料。
  2. 本 migration 下架两条旧菜单:
     - item-list        (旧物料菜单, 被 material-management 取代, 避免侧边栏
                         出现两条同名「物料管理」)
     - item-group-list  (物料组入口收进 MOMP 页左树, 用户拍板「删掉, 只留 MOMP 页」)

  下架方式用 is_active=0 而非 DELETE:
    - 菜单表被权限集/角色的 grant 关系引用, 物理删除会留下悬挂引用
    - 保留行便于回滚 (downgrade 直接 is_active=1) 与排查

为何需要 migration 而不是只改 init_menu_permissions.py:
  这两条菜单是 menu_auto_generator 用 INSERT OR IGNORE 写入的
  (auto_generated=1), 不在 system_menus 列表里, init 脚本不会碰它们。
  与 v091 同理: 生成器管叶子, migration 管下架与挂载。

与 v091 的关系:
  v091 的 CHILD_SORT 里 item-list=64 / item_group-list=65 是"挂上去"的动作;
  本 migration 是把它们"撤下来"。执行顺序无要求 (v091 对已停用的菜单仍可
  重复挂载, 本 migration 幂等), 但建议 v091 → v092。

幂等性:
  全部操作为 "仅当 is_active != 0 才 UPDATE", 重复执行为 no-op。
  material-management 不存在时直接跳过 (交由 init_menu_permissions.py 先创建)。

回滚:
  把两条菜单 is_active 恢复为 1, 并把 sort_order 复原
  (item-list=64, item_group-list=65)。material-management 本身交由
  init_menu_permissions.py 回收 (从 system_menus 移除该条即可)。
"""
import sqlite3
from pathlib import Path


PARENT_CODE = 'master-data'

# (menu_code, 恢复用的 sort_order)
RETIRED = [
    ('item-list', 64),
    ('item_group-list', 65),
]
RETIRED_CODES = [code for code, _ in RETIRED]

# 接管物料域的新菜单, 必须存在才能下架旧菜单
NEW_MENU_CODE = 'material-management'


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


# ─── 入口签名 (与 v091 保持一致) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v092] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v092] 开始: 下架 item-list / item-group-list (物料域收进 MOMP 页)')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v092] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """两条旧菜单已下架, 新菜单可用。"""
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
            print(f'[v092 verify] FAIL: {NEW_MENU_CODE} 不存在或未启用')
            return False
        still_on = conn.execute(
            "SELECT menu_code, menu_name FROM menus "
            "WHERE menu_code IN ({0}) AND is_active != 0".format(
                ','.join('?' for _ in RETIRED_CODES)
            ),
            RETIRED_CODES,
        ).fetchall()
        if still_on:
            print(f'[v092 verify] FAIL: 仍未下架 {[r[0] for r in still_on]}')
            return False
        print(f'[v092 verify] OK: {NEW_MENU_CODE} 已启用, '
              f'{len(RETIRED_CODES)} 条旧菜单已下架')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v092] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v092] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v092] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v092] verify: {"PASS" if _v else "FAIL"}')