# -*- coding: utf-8 -*-
"""[v116 2026-10-25] 停用对象级泛化遗留的自动菜单

背景:
  三个类型对象去掉 sales_ 前缀后（见 v115__type_definition_object_naming.py），
  schema sync 会按新 id 自动生成 document_type-list / line_type-list /
  line_type_assignment-list 三个菜单。旧 id 生成的三个自动菜单仍在库里、
  is_active=1，且指向已不存在的对象，属历史残留。

落位:
  旧三个自动菜单置 is_active=0（不删行，保留历史），menu_permissions 同步停用。
  新菜单由 schema sync 生成，show_in_sidebar=0，本迁移不创建。

幂等:
  按 menu_code 精确 UPDATE ... AND is_active = 1，重复执行无副作用。

回滚:
  旧三个自动菜单恢复 is_active=1。
"""
import sqlite3
from pathlib import Path

LEGACY_MENU_CODES = (
    'sales_document_type-list',
    'sales_line_type-list',
    'sales_line_type_assignment-list',
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _set_active(conn: sqlite3.Connection, active: int) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过')
        return
    placeholders = ', '.join('?' * len(LEGACY_MENU_CODES))
    cur = conn.execute(
        "UPDATE menus SET is_active = %d WHERE menu_code IN (%s) AND is_active = %d"
        % (active, placeholders, 1 - active),
        LEGACY_MENU_CODES,
    )
    print('  - [%s] menus: %d 条' % ('OFF' if active == 0 else 'ON', cur.rowcount))
    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "UPDATE menu_permissions SET is_active = %d "
            "WHERE menu_code IN (%s) AND is_active = %d"
            % (active, placeholders, 1 - active),
            LEGACY_MENU_CODES,
        )
        print('  - [%s] menu_permissions: %d 条'
              % ('OFF' if active == 0 else 'ON', cur.rowcount))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v116] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v116] 开始: 停用旧自动菜单')
        _set_active(conn, 0)
        conn.commit()
        print('[v116] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v116] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v116 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            print('[v116 verify] FAIL: menus 表不存在')
            return False
        placeholders = ', '.join('?' * len(LEGACY_MENU_CODES))
        rows = conn.execute(
            "SELECT menu_code, is_active FROM menus WHERE menu_code IN (%s)"
            % placeholders, LEGACY_MENU_CODES,
        ).fetchall()
        live = [code for code, active in rows if active == 1]
        if live:
            print('[v116 verify] FAIL: 旧菜单仍启用 %s' % live)
            return False
        print('[v116 verify] OK: 旧自动菜单均已停用')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v116 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _set_active(conn, 1)
        conn.commit()
        print('[v116 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v116 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else get_meta_db_path()
    if '--rollback' in sys.argv:
        rollback(db)
    else:
        migrate(db)
        verify(db)
