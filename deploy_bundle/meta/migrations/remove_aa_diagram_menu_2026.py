# -*- coding: utf-8 -*-
"""
迁移: 移除 aa-diagram 菜单项 (2026-06-10)

背景:
  AA图菜单已经从导航栏隐藏 (router meta.hiddenFromMenu = true),
  入口迁移到 /system/archdata 的"图表"按钮。
  此脚本清理 DB 中残留的 menu_code = 'aa-diagram' 条目。

执行方式:
  python meta/migrations/remove_aa_diagram_menu_2026.py

回滚:
  重新运行 init_menu_permissions.py 重建
"""
import sqlite3
import os
import sys

DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'architecture.db',
)


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    if not os.path.exists(db_path):
        print(f"[ERROR] DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. 查找 aa-diagram 菜单
    cursor.execute(
        "SELECT id, menu_code, menu_name, menu_path FROM menus WHERE menu_code = ?",
        ('aa-diagram',),
    )
    rows = cursor.fetchall()
    if not rows:
        print("[OK] No aa-diagram menu found in `menus`, nothing to do.")
    else:
        print(f"[INFO] Found {len(rows)} aa-diagram menu entry(ies):")
        for r in rows:
            print(f"  id={r[0]} code={r[1]} name={r[2]} path={r[3]}")

        # 2. 删除 role_menu_permissions 关联（如果存在）
        cursor.execute(
            "DELETE FROM role_menu_permissions WHERE menu_code = ?",
            ('aa-diagram',),
        )
        deleted_role_menus = cursor.rowcount
        print(f"[OK] Deleted {deleted_role_menus} role_menu_permissions rows.")

        # 3. 删除 menu_permissions 行（如果存在）
        cursor.execute(
            "DELETE FROM menu_permissions WHERE menu_code = ?",
            ('aa-diagram',),
        )
        deleted_perms = cursor.rowcount
        print(f"[OK] Deleted {deleted_perms} menu_permissions rows.")

        # 4. 删除 menus 行
        cursor.execute(
            "DELETE FROM menus WHERE menu_code = ?",
            ('aa-diagram',),
        )
        deleted_menus = cursor.rowcount
        print(f"[OK] Deleted {deleted_menus} menus rows.")

    # 5. 验证：检查是否还有残留
    cursor.execute(
        "SELECT 'menus' AS tbl, COUNT(*) FROM menus WHERE menu_code='aa-diagram' "
        "UNION ALL "
        "SELECT 'menu_permissions', COUNT(*) FROM menu_permissions WHERE menu_code='aa-diagram' "
        "UNION ALL "
        "SELECT 'role_menu_permissions', COUNT(*) FROM role_menu_permissions WHERE menu_code='aa-diagram'"
    )
    residuals = cursor.fetchall()
    print()
    print("[VERIFY] Residual rows after cleanup:")
    for tbl, cnt in residuals:
        status = '[OK]' if cnt == 0 else '[FAIL]'
        print(f"  {status} {tbl}: {cnt}")

    conn.commit()
    conn.close()
    print()
    print("[DONE] aa-diagram menu cleanup completed.")
    print("[NOTE] Frontend menu is cached; user may need to refresh or re-login.")


if __name__ == '__main__':
    main()