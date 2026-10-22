# -*- coding: utf-8 -*-
"""
[v098 2026-10-22] 下架客户档案 / 供应商档案的独立菜单, 入口收进伙伴关系详情页分区

背景:
  customer_account / vendor_account 此前有两条手工声明的独立菜单
  (customer-account-management so=61 / vendor-account-management so=62,
  parent=master-data, page_type=object_list), 2026-10-11 由用户拍板开为独立入口。

  但这两个档案挂在 party_relation 之上 1:1 (relation_id 唯一), 是「关系侧属性」,
  不是与 party 并列的主体实体。party_relation 自己已于 2026-10-17 下架独立菜单
  (收进往来单位页第三 tab), 其理由同款 —— 关系是连接两个 party 的边, 平级入口属
  「放错层」; 比关系更下一层的档案平级更说不通。

改动:
  1. init_menu_permissions.py 移除这两条菜单声明 (手工菜单走 UPSERT,
     只改声明文件不会删掉库里的存量行 —— 见下方「为何需要 migration」)。
  2. 本 migration 下架两条存量菜单行, 入口改到 party_relation 详情页的两个
     关联分区 (party_relation.yaml detail.facets 声明 customFetcher =
     relation_accounts, 前端 AssociationSection 走该分支按 relation_id 取数)。
  3. 两个档案对象补齐 ui_view_config (list/form/detail):
     此前只写了 skip_auto_menu, 未声明列与表单 ⇒ /ui-config 端点走
     config_builder 兜底推导, 把技术主键 id、created_at、审计字段全渲染成列
     (用户在菜单里看到的就是一列裸 id); 且编辑态走 form.sections 而两者皆无 ⇒
     新建/编辑抽屉零字段。

  下架方式用 is_active=0 而非 DELETE (同 v092/v093):
    - 菜单被权限集/角色的 grant 关系引用, 物理删除会留下悬挂引用
    - 保留行便于回滚 (downgrade 直接 is_active=1) 与排查

为何需要 migration 而不只改 init_menu_permissions.py:
  这两条是**手工声明**菜单 (auto_generated=0), 理论上 init 的「步骤7.5/7.6 冗余清理」
  会直接 DELETE 掉。但实测那段清理是**假成功**: conn.commit() 在 L1553, 而两个
  DELETE 在 L1555 之后的步骤 7.5/7.6, 脚本退出时连接关闭、未提交的改动被 SQLite
  回滚 —— 脚本照样打印「清理了 N 条冗余导航菜单」, 但行还在表里。
  (v092/v093 那两条是自动生成的, init 压根不碰, 故v098 不能沿用它们的理由。)
  故本次由 migration 显式下架 (它自己 commit), 并顺手清掉 menu_permissions 残留行
  —— 那张表的清理同样在未提交区间, 不由本 migration 清就会永久留下孤儿行。

  已核对 permission_set_menu_permissions 中这两个 menu_code 无任何 grant 引用,
  故不涉及悬挂授权。

幂等性:
  全部操作为 "仅当 is_active != 0 才 UPDATE", 重复执行为 no-op。

回滚:
  把两条菜单 is_active 恢复为 1 并挂回 master-data、复原 sort_order。
  菜单声明本身交由 init_menu_permissions.py 回收 (把两条加回 system_menus 即可)。
"""
import sqlite3
from pathlib import Path


PARENT_CODE = 'master-data'

# (menu_code, 恢复用的 sort_order)
RETIRED = [
    ('customer-account-management', 61),
    ('vendor-account-management', 62),
]
RETIRED_CODES = [code for code, _ in RETIRED]

# 接管这两个档案入口的新落点: 伙伴关系对象
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

    # 冗余的菜单权限行（init 步骤 7.5 同款清理，但那段未提交 ⇒ 由本 migration 兜底）
    cleaned_perm = 0
    if _table_exists(conn, 'menu_permissions'):
        for code, _ in RETIRED:
            cur = conn.execute(
                "DELETE FROM menu_permissions WHERE menu_code = ?", (code,))
            cleaned_perm += getattr(cur, 'rowcount', 0) or 0
        if cleaned_perm:
            print(f'  - [CLEAN] menu_permissions 清理 {cleaned_perm} 条冗余行')

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
    print('  [REVERT] menu_permissions 行需重跑 init_menu_permissions.py 重建')


# ─── 入口签名 (与 v092/v093 保持一致) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v098] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v098] 开始: 下架客户档案 / 供应商档案独立菜单 '
              '(入口收进伙伴关系详情页分区)')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v098] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """两条档案独立菜单已下架, 新菜单可用。"""
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
            print(f'[v098 verify] FAIL: {NEW_MENU_CODE} 不存在或未启用')
            return False
        still_on = conn.execute(
            "SELECT menu_code, menu_name FROM menus "
            "WHERE menu_code IN ({0}) AND is_active != 0".format(
                ','.join('?' for _ in RETIRED_CODES)
            ),
            RETIRED_CODES,
        ).fetchall()
        if still_on:
            print(f'[v098 verify] FAIL: 仍未下架 {[r[0] for r in still_on]}')
            return False
        # 冗余的菜单权限行必须一并清掉（init 步骤 7.5 的清理未提交，此处兜底校验）
        if _table_exists(conn, 'menu_permissions'):
            orphan = conn.execute(
                "SELECT menu_code FROM menu_permissions "
                "WHERE menu_code IN ({0})".format(
                    ','.join('?' for _ in RETIRED_CODES)
                ),
                RETIRED_CODES,
            ).fetchall()
            if orphan:
                print(f'[v098 verify] FAIL: menu_permissions 仍有孤儿行 '
                      f'{[r[0] for r in orphan]}')
                return False
        print(f'[v098 verify] OK: {NEW_MENU_CODE} 已启用, '
              f'{len(RETIRED_CODES)} 条档案菜单已下架')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v098] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v098] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v098] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v098] verify: {"PASS" if _v else "FAIL"}')