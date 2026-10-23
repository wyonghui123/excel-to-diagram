# -*- coding: utf-8 -*-
"""[v103] 作业日历页改版迁移测试（object_list → multi_object_hub）

覆盖 v103__calendar_momp_page.py 的三件事:
  1. calendar-list 升级为 multi_object_hub，object_types 跨承载 calendar_day
  2. calendar_day-list 存量行与 menu_permissions 冗余行被物理删除
  3. verify 会拦下「权限码不存在」——这是 v099~v102 反复踩过的坑
     （前端路由守卫按 every 判定，required_permissions 里混入假码会整页被拦）

测试隔离: tmp_path 建最小 menus / permissions / menu_permissions /
         permission_set_menu_permissions 四表，不触碰 architecture.db。
"""
import importlib.util
import json
import os
import sqlite3
from pathlib import Path

# 菜单/权限表暂无 Factory，按仓库既有惯例走 raw SQL escape hatch
# （同 test_f4_calendar.py），避免整文件被 conftest 的 raw-SQL 门控拦跳。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

_MIGRATION = (Path(__file__).resolve().parents[1]
              / 'migrations' / 'v103__calendar_momp_page.py')

_DDL = """
CREATE TABLE menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code VARCHAR(200) NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200),
    page_type VARCHAR(200) NOT NULL,
    object_types TEXT,
    primary_object_type VARCHAR(200),
    bo_bindings TEXT,
    required_permissions TEXT,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    color VARCHAR(200),
    sort_order INTEGER,
    is_active INTEGER,
    show_in_sidebar INTEGER,
    auto_generated INTEGER
);
CREATE TABLE permissions (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          code VARCHAR(200) NOT NULL);
CREATE TABLE menu_permissions (
    menu_code VARCHAR(200) NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200) NOT NULL,
    required_permissions TEXT
);
CREATE TABLE permission_set_menu_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER NOT NULL,
    menu_code VARCHAR(200) NOT NULL
);
"""

# permissions 表真实存在的 10 条（calendars / calendar_days 的 list 动作）
_REAL_CODES = [
    'calendar:calendar_create', 'calendar:calendar_read',
    'calendar:calendar_update', 'calendar:calendar_delete',
    'calendar:calendar_list',
    'calendar_day:calendar_day_create', 'calendar_day:calendar_day_read',
    'calendar_day:calendar_day_update', 'calendar_day:calendar_day_delete',
    'calendar_day:calendar_day_list',
]


def _load_module():
    spec = importlib.util.spec_from_file_location('v103_calendar_momp', _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed(db_path: Path, permissions=None):
    """建表并灌入 v102 形态的两条菜单（手工声明 / object_list）。"""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_DDL)
        for code in (permissions if permissions is not None else _REAL_CODES):
            conn.execute("INSERT INTO permissions (code) VALUES (?)", (code,))
        rows = [
            ('calendar-list', '作业日历管理', '/calendar', 'object_list',
             '["calendar"]', 'calendar', 0, 1,
             json.dumps(_REAL_CODES[:5]), 'master-data'),
            ('calendar_day-list', '日历例外日管理', '/calendar-day', 'object_list',
             '["calendar_day"]', 'calendar_day', 0, 1,
             json.dumps(_REAL_CODES[5:]), 'master-data'),
        ]
        for (code, name, path, ptype, ots, pot, auto, active, perms, parent) in rows:
            conn.execute(
                "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
                "object_types, primary_object_type, auto_generated, is_active, "
                "required_permissions, parent_menu, bo_bindings) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')",
                (code, name, path, ptype, ots, pot, auto, active, perms, parent),
            )
            conn.execute(
                "INSERT INTO menu_permissions (menu_code, menu_name, menu_path, "
                "required_permissions) VALUES (?, ?, ?, ?)",
                (code, name, path, perms),
            )
        conn.commit()
    finally:
        conn.close()


def _fetch(db_path: Path, code):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT page_type, auto_generated, is_active, menu_path, "
            "primary_object_type, object_types, required_permissions "
            "FROM menus WHERE menu_code = ?", (code,)).fetchone()
    finally:
        conn.close()


def _count(db_path: Path, table, code):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            f"SELECT COUNT(1) FROM {table} WHERE menu_code = ?", (code,)).fetchone()[0]
    finally:
        conn.close()


class TestUpgrade:
    def test_calendar_list_becomes_hub_with_calendar_day(self, tmp_path):
        db = tmp_path / 'm.db'
        _seed(db)
        mod = _load_module()
        assert mod.migrate(db) is True

        row = _fetch(db, 'calendar-list')
        assert row[0] == 'multi_object_hub'
        assert row[1] == 0                      # 手工声明
        assert row[2] == 1                      # 菜单仍启用
        assert row[3] == '/calendar'            # 落点不变（书签/route_map 不受影响）
        assert row[4] == 'calendar'
        assert set(json.loads(row[5])) == {'calendar', 'calendar_day'}
        assert json.loads(row[6]) == _REAL_CODES

    def test_retired_menu_and_permission_rows_removed(self, tmp_path):
        db = tmp_path / 'm.db'
        _seed(db)
        mod = _load_module()
        assert mod.migrate(db) is True

        assert _fetch(db, 'calendar_day-list') is None
        assert _count(db, 'menu_permissions', 'calendar_day-list') == 0
        # calendar-list 自己的 menu_permissions 行不该被误删
        assert _count(db, 'menu_permissions', 'calendar-list') == 1

    def test_idempotent(self, tmp_path):
        db = tmp_path / 'm.db'
        _seed(db)
        mod = _load_module()
        assert mod.migrate(db) is True
        first = _fetch(db, 'calendar-list')
        assert mod.migrate(db) is True          # 第二次应为 no-op
        assert _fetch(db, 'calendar-list') == first


class TestVerify:
    def test_verify_passes_after_migrate(self, tmp_path):
        db = tmp_path / 'm.db'
        _seed(db)
        mod = _load_module()
        assert mod.migrate(db) is True
        assert mod.verify(db) is True

    def test_verify_fails_on_missing_permission_code(self, tmp_path):
        """权限码混入假值 → 前端守卫会整页拦下，verify 必须报 FAIL。"""
        db = tmp_path / 'm.db'
        _seed(db, permissions=_REAL_CODES[:5])   # 缺 calendar_day 的 5 条
        mod = _load_module()
        assert mod.migrate(db) is True
        assert mod.verify(db) is False

    def test_verify_fails_when_retired_menu_still_present(self, tmp_path):
        db = tmp_path / 'm.db'
        _seed(db)
        mod = _load_module()
        assert mod.migrate(db) is True
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
                "auto_generated, is_active) VALUES "
                "('calendar_day-list', '日历例外日管理', '/calendar-day', "
                "'object_list', 0, 1)")
            conn.commit()
        finally:
            conn.close()
        assert mod.verify(db) is False


class TestDowngrade:
    def test_downgrade_restores_object_list(self, tmp_path):
        db = tmp_path / 'm.db'
        _seed(db)
        mod = _load_module()
        assert mod.migrate(db) is True
        assert mod.downgrade(db) is True
        row = _fetch(db, 'calendar-list')
        assert row[0] == 'object_list'
        assert json.loads(row[5]) == ['calendar']
        assert len(json.loads(row[6])) == 5
