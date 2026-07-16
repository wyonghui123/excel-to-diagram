# -*- coding: utf-8 -*-
"""
迁移: 重命名 product-management 菜单为"产品版本管理" (2026-06-10)

背景:
  用户决策: 顶级菜单 "产品管理" 改名为 "产品版本管理",
  以更准确表达其管理产品线+产品版本的职责。

变更:
  - menus 表: menu_name '产品管理' -> '产品版本管理'
  - menu_permissions 表: 同步更新

注意:
  DB 中已有 version-list 菜单（show_in_sidebar=0）也名为"产品版本管理",
  但因为不显示在 sidebar，无 UI 冲突。语义上有轻微混淆但不影响功能。

执行方式:
  python meta/migrations/rename_product_management_menu_2026.py

回滚:
  UPDATE menus SET menu_name = '产品管理' WHERE menu_code = 'product-management';
  UPDATE menu_permissions SET menu_name = '产品管理' WHERE menu_code = 'product-management';
"""
import sqlite3
import os
import sys

DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'architecture.db',
)

OLD_NAME = '产品管理'
NEW_NAME = '产品版本管理'
MENU_CODE = 'product-management'


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    if not os.path.exists(db_path):
        print(f"[ERROR] DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Check current state
    cursor.execute(
        "SELECT id, menu_code, menu_name, menu_path FROM menus WHERE menu_code = ?",
        (MENU_CODE,),
    )
    row = cursor.fetchone()
    if not row:
        print(f"[INFO] No menu with code '{MENU_CODE}' found, nothing to do.")
        conn.close()
        return

    print(f"[BEFORE] id={row[0]} code={row[1]} name={row[2]} path={row[3]}")

    if row[2] == NEW_NAME:
        print(f"[OK] Already renamed to '{NEW_NAME}', nothing to do.")
        conn.close()
        return

    if row[2] != OLD_NAME:
        print(f"[WARN] Current name '{row[2]}' doesn't match expected '{OLD_NAME}'.")
        print(f"[WARN] Manual review needed, aborting.")
        conn.close()
        sys.exit(2)

    # 2. Update menus
    cursor.execute(
        "UPDATE menus SET menu_name = ? WHERE menu_code = ?",
        (NEW_NAME, MENU_CODE),
    )
    print(f"[OK] Updated menus: {cursor.rowcount} row(s)")

    # 3. Update menu_permissions
    cursor.execute(
        "UPDATE menu_permissions SET menu_name = ? WHERE menu_code = ?",
        (NEW_NAME, MENU_CODE),
    )
    print(f"[OK] Updated menu_permissions: {cursor.rowcount} row(s)")

    # 4. Verify
    cursor.execute(
        "SELECT id, menu_code, menu_name, menu_path FROM menus WHERE menu_code = ?",
        (MENU_CODE,),
    )
    row = cursor.fetchone()
    print(f"[AFTER]  id={row[0]} code={row[1]} name={row[2]} path={row[3]}")

    cursor.execute(
        "SELECT menu_code, menu_name FROM menu_permissions WHERE menu_code = ?",
        (MENU_CODE,),
    )
    perm_row = cursor.fetchone()
    print(f"[VERIFY] menu_permissions: {perm_row}")

    conn.commit()
    conn.close()
    print()
    print("[DONE] Menu rename completed.")
    print("[NOTE] Frontend menu is cached; user may need to refresh or re-login.")


if __name__ == '__main__':
    main()