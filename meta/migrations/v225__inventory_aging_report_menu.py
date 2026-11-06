# -*- coding: utf-8 -*-
"""v225 - 库存库龄报表菜单（P9 元数据驱动报表页首个消费者）

依据: docs/specs/p8-inventory-aging-model/tasks.md（P8-17 后续）
      2026-11-06 P9 方案：report 页型 + MetaReportPage

动作:
  1. 新增菜单 inventory-aging-report（page_type=report）
     · primary_object_type=inventory_balance
     · 页面配置来自 meta/schemas/inventory_balance.yaml 的 ui_view_config.report
     · 权限复用 inventory_balance:inventory_balance_read（不新增权限码）
  2. 同步 menu_permissions（旧权限表兼容），已存在则跳过

回滚:
  DELETE 菜单与 menu_permissions 行；不涉及业务数据。

[ALLOW_DESTRUCTIVE] rollback 仅删除本次新增的菜单行。
"""
from __future__ import annotations

import json
import os
import sqlite3

MIGRATION_NAME = 'v225__inventory_aging_report_menu'

PARENT_MENU_CODE = 'inventory-balance-management'

MENU = {
    'menu_code': 'inventory-aging-report',
    'menu_name': '库存库龄',
    'menu_path': '/inventory-aging',
    'page_type': 'report',
    'primary_object_type': 'inventory_balance',
    'object_types': ['inventory_balance'],
    'bo_bindings': [
        {'bo_id': 'inventory_balance', 'role': 'primary',
         'include_actions': ['read', 'list']},
    ],
    'required_permissions': ['inventory_balance:inventory_balance_read'],
    'parent_menu': PARENT_MENU_CODE,
    'icon': 'TrendCharts',
    'color': '#f59e0b',
    'description': '按余额行最早入库日分桶的只读库龄报表',
    'sort_order': 7,
    'show_in_sidebar': 1,
    'data_permission_hint': {
        'resource_types': ['inventory_balance'],
        'message': '建议按库存组织分配库存余额数据权限',
    },
}


def _table_exists(conn, name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone())


def _insert_menu(conn):
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在，跳过')
        return
    if conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                    (MENU['menu_code'],)).fetchone():
        print("  - [SKIP] 菜单 %s 已存在" % MENU['menu_code'])
        # 幂等修正：报表页必须进侧边栏，否则 /menu-permission/visible 不下发、前端无路由
        conn.execute(
            "UPDATE menus SET show_in_sidebar=1, is_active=1 WHERE menu_code=?",
            (MENU['menu_code'],))
    else:
        conn.execute(
            "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
            "object_types, primary_object_type, bo_bindings, "
            "required_permissions, parent_menu, icon, color, description, "
            "sort_order, is_active, show_in_sidebar, auto_generated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 0)",
            (
                MENU['menu_code'], MENU['menu_name'], MENU['menu_path'],
                MENU['page_type'],
                json.dumps(MENU['object_types'], ensure_ascii=False),
                MENU['primary_object_type'],
                json.dumps(MENU['bo_bindings'], ensure_ascii=False),
                json.dumps(MENU['required_permissions'], ensure_ascii=False),
                MENU['parent_menu'], MENU['icon'], MENU['color'],
                MENU['description'], MENU['sort_order'],
                MENU['show_in_sidebar'],
            ),
        )
        print("  - [NEW] 菜单 %s (%s)" % (MENU['menu_code'], MENU['menu_name']))

    if _table_exists(conn, 'menu_permissions'):
        conn.execute(
            "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, "
            "menu_path, required_permissions, required_any_permission, "
            "parent_menu, icon, sort_order, is_active, data_permission_hint) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, ?)",
            (
                MENU['menu_code'], MENU['menu_name'], MENU['menu_path'],
                json.dumps(MENU['required_permissions'], ensure_ascii=False),
                MENU['parent_menu'], MENU['icon'], MENU['sort_order'],
                json.dumps(MENU['data_permission_hint'], ensure_ascii=False),
            ),
        )
        print("  - [SYNC] menu_permissions: %s" % MENU['menu_code'])


def _do_upgrade(conn):
    _insert_menu(conn)
    return True


def migrate(db_path, skip_backup=False):
    print('[v225] 库存库龄报表菜单')
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(db_path)
    try:
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path):
    if not os.path.exists(db_path):
        print('  - [FAIL] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            'SELECT page_type, primary_object_type FROM menus '
            'WHERE menu_code=?', (MENU['menu_code'],)).fetchone()
        if not row:
            print('  - [FAIL] 菜单缺失')
            return False
        if row[0] != 'report' or row[1] != 'inventory_balance':
            print('  - [FAIL] 菜单属性不符: %s' % (row,))
            return False
        print('  - [OK] menu=%s page_type=%s primary=%s'
              % (MENU['menu_code'], row[0], row[1]))
        return True
    finally:
        conn.close()
