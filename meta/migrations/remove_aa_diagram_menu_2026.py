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
        print("[OK] No aa-diagram menu found, nothing to do.")
        conn.close()
        return

    print(f"[INFO] Found {len(rows)} aa-diagram menu entry(ies):")
    for r in rows:
        print(f"  id={r[0]} code={r[1]} name={r[2]} path={r[3]}")

    # 2. 删除 menu_permissions 关联（如果有）
    menu_ids = [r[0] for r in rows]
    placeholders = ','.join('?' * len(menu_ids))
    cursor.execute(
        f"DELETE FROM menu_permissions WHERE menu_id IN ({placeholders})",
        menu_ids,
    )
    deleted_perms = cursor.rowcount
    print(f"[OK] Deleted {deleted_perms} menu_permissions rows.")

    # 3. 删除菜单条目
    cursor.execute(
        f"DELETE FROM menus WHERE id IN ({placeholders})",
        menu_ids,
    )
    deleted_menus = cursor.rowcount
    print(f"[OK] Deleted {deleted_menus} menus rows.")

    conn.commit()
    conn.close()
    print("[DONE] aa-diagram menu cleanup completed.")


if __name__ == '__main__':
    main()