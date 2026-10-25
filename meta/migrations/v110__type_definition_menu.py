# -*- coding: utf-8 -*-
"""[v110 2026-10-25] 类型字典菜单与权限 + 旧两页停用

背景:
  单据类型 / 行类型统一为 type_definition（见 v110__type_definitions.py）。
  旧「销售单据类型」「销售行类型」两个页面已降级为只读兼容面，不应再作为
  可写入口暴露；本迁移把它们停用（不删行，保留历史），并新增唯一可写页
  「类型字典」。

落位:
  type-definition-management → /type-definitions，挂 master-data（主数据，
  page_type=multi_object_hub）下，show_in_sidebar=0，与 party / item /
  sourcing 等主数据子页同款。sort_order 复用 74（旧单据类型页原位）。

权限口径:
  type_definition:create / read / update / delete / list（单段式
  {object}:{action}，与 PermissionSyncService 自动推导及按钮权限码一致）。
  旧权限码 sales_document_type:* / sales_line_type:* 保留不回收
  （可能已被角色授予；回收有风险）。

幂等:
  permissions INSERT OR IGNORE；menus 按 menu_code 判存在，缺失才 INSERT；
  旧菜单停用用 UPDATE ... WHERE menu_code IN (...)，重复执行无副作用。

回滚:
  删除 type-definition-management 菜单与 menu_permissions 行；恢复旧两页
  is_active=1。permissions 行保留。
"""
import json
import sqlite3
from pathlib import Path

PARENT_MENU = 'master-data'

MENU_CODE = 'type-definition-management'
OLD_MENU_CODES = ('sales-document-type-management', 'sales-line-type-management')

PERMISSION_ACTIONS = ('create', 'read', 'update', 'delete', 'list')
PERMISSION_LABELS = {
    'create': '新建类型',
    'read': '查看类型',
    'update': '修改类型',
    'delete': '删除类型',
    'list': '查询类型列表',
}

MENU = {
    'menu_code': MENU_CODE,
    'menu_name': '类型字典',
    'menu_path': '/type-definitions',
    'page_type': 'object_list',
    'primary_object_type': 'type_definition',
    'object_types': ['type_definition'],
    'bo_bindings': [
        {'bo_id': 'type_definition', 'role': 'primary',
         'include_actions': ['create', 'read', 'update', 'delete', 'list']},
    ],
    'required_permissions': ['type_definition:%s' % a for a in PERMISSION_ACTIONS],
    'parent_menu': PARENT_MENU,
    'icon': 'List',
    'color': '#0ea5e9',
    'description': '单据类型 / 行类型的统一字典；按归属对象 + 层级判别',
    'sort_order': 74,
    'is_active': 1,
    'show_in_sidebar': 0,
    'auto_generated': 0,
    'data_permission_hint': {
        'resource_types': ['type_definition'],
        'message': '建议分配类型字典数据权限',
    },
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    created = 0
    for action in PERMISSION_ACTIONS:
        code = 'type_definition:%s' % action
        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            (code, PERMISSION_LABELS[action], 'type_definition', action),
        )
        if cur.rowcount:
            created += 1
            print('  - [NEW] 权限 %s (%s)' % (code, PERMISSION_LABELS[action]))
    if created:
        print('  - [SUMMARY] permissions: +%d 新增' % created)
    else:
        print('  - [SKIP] 5 条权限码均已存在, 无新增')


def _do_menu(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return
    if conn.execute("SELECT 1 FROM menus WHERE menu_code = ?",
                    (MENU['menu_code'],)).fetchone():
        print("  - [SKIP] 菜单 %s 已存在" % MENU['menu_code'])
        return

    conn.execute(
        "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
        "object_types, primary_object_type, bo_bindings, required_permissions, "
        "parent_menu, icon, color, description, sort_order, is_active, "
        "show_in_sidebar, auto_generated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            MENU['menu_code'], MENU['menu_name'], MENU['menu_path'],
            MENU['page_type'],
            json.dumps(MENU['object_types'], ensure_ascii=False),
            MENU['primary_object_type'],
            json.dumps(MENU['bo_bindings'], ensure_ascii=False),
            json.dumps(MENU['required_permissions'], ensure_ascii=False),
            MENU['parent_menu'], MENU['icon'], MENU['color'], MENU['description'],
            MENU['sort_order'], MENU['is_active'], MENU['show_in_sidebar'],
            MENU['auto_generated'],
        ),
    )
    print("  - [NEW] 菜单 %s @ %s, sort_order=%s"
          % (MENU['menu_code'], MENU['menu_path'], MENU['sort_order']))


def _do_menu_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menu_permissions'):
        print('  - menu_permissions 表不存在, 跳过同步')
        return
    cur = conn.execute(
        "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, menu_path, "
        "required_permissions, required_any_permission, parent_menu, icon, "
        "sort_order, is_active, data_permission_hint) "
        "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
        (
            MENU['menu_code'], MENU['menu_name'], MENU['menu_path'],
            json.dumps(MENU['required_permissions'], ensure_ascii=False),
            MENU['parent_menu'], MENU['icon'], MENU['sort_order'],
            MENU['is_active'],
            json.dumps(MENU['data_permission_hint'], ensure_ascii=False),
        ),
    )
    print('  - [%s] menu_permissions: %s'
          % ('NEW' if cur.rowcount else 'SKIP', MENU['menu_code']))


def _do_deactivate_old(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    placeholders = ', '.join('?' * len(OLD_MENU_CODES))
    cur = conn.execute(
        "UPDATE menus SET is_active = 0 WHERE menu_code IN (%s) AND is_active = 1"
        % placeholders, OLD_MENU_CODES,
    )
    print('  - [OFF] 旧菜单停用: %d 条' % cur.rowcount)
    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "UPDATE menu_permissions SET is_active = 0 "
            "WHERE menu_code IN (%s) AND is_active = 1" % placeholders,
            OLD_MENU_CODES,
        )
        print('  - [OFF] menu_permissions 旧菜单停用: %d 条' % cur.rowcount)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v110-menu] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v110-menu] 开始: 类型字典菜单 + 旧两页停用')
        _do_permissions(conn)
        _do_menu(conn)
        _do_menu_permissions(conn)
        _do_deactivate_old(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print('[v110-menu] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            print('[v110-menu verify] FAIL: menus 表不存在')
            return False
        row = conn.execute(
            "SELECT page_type, is_active, menu_path, primary_object_type, "
            "parent_menu, required_permissions FROM menus WHERE menu_code = ?",
            (MENU_CODE,),
        ).fetchone()
        if not row:
            print('[v110-menu verify] FAIL: 菜单 %s 不存在' % MENU_CODE)
            return False
        page_type, is_active, menu_path, pot, parent, req = row
        if page_type != 'object_list' or is_active != 1:
            print('[v110-menu verify] FAIL: 形态不对 (page_type=%s, is_active=%s)'
                  % (page_type, is_active))
            return False
        if menu_path != '/type-definitions' or pot != 'type_definition':
            print('[v110-menu verify] FAIL: 路径/主对象不符')
            return False
        if parent != PARENT_MENU:
            print('[v110-menu verify] FAIL: parent_menu=%s' % parent)
            return False

        codes = json.loads(req or '[]')
        for code in codes:
            if not conn.execute("SELECT 1 FROM permissions WHERE code = ?",
                                (code,)).fetchone():
                print('[v110-menu verify] FAIL: 权限码不存在 %s' % code)
                return False

        for code in OLD_MENU_CODES:
            row = conn.execute(
                "SELECT is_active FROM menus WHERE menu_code = ?", (code,)
            ).fetchone()
            if row and row[0] != 0:
                print('[v110-menu verify] FAIL: 旧菜单 %s 仍启用' % code)
                return False

        print('[v110-menu verify] OK: 类型字典页启用, 旧两页停用, 权限码齐备')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v110-menu] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _table_exists(conn, 'menus'):
            conn.execute("DELETE FROM menus WHERE menu_code = ?", (MENU_CODE,))
            placeholders = ', '.join('?' * len(OLD_MENU_CODES))
            conn.execute("UPDATE menus SET is_active = 1 WHERE menu_code IN (%s)"
                         % placeholders, OLD_MENU_CODES)
        if _table_exists(conn, 'menu_permissions'):
            conn.execute("DELETE FROM menu_permissions WHERE menu_code = ?",
                         (MENU_CODE,))
            placeholders = ', '.join('?' * len(OLD_MENU_CODES))
            conn.execute("UPDATE menu_permissions SET is_active = 1 "
                         "WHERE menu_code IN (%s)" % placeholders, OLD_MENU_CODES)
        print('  - [KEEP] permissions 行保留 (可能已被角色授予)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print('[v110-menu] rollback 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print('[v110-menu] migrate: %s' % ('OK' if _ok else 'FAIL'))
    _v = verify(_db)
    print('[v110-menu] verify: %s' % ('PASS' if _v else 'FAIL'))
