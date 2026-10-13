# -*- coding: utf-8 -*-
"""任务管理入口收敛回归（P1 拍板：task.v1 直接接管，不与遗留并存）

依据: docs/superpowers/specs/2026-09-07-task-model-design.md §9.4「P1 落地」

背景: /system/task-management 已切挂为 task.v1 监控视图，但菜单层遗留未清——
  1. menus.task-management.menu_name仍为「任务调度」（旧名），且 object_types /
     bo_bindings / required_permissions 仍绑 scheduled_task / task_queue /
     task_execution / ai_async_task 四个遗留实体；
  2. menus 表仍有 4 条叶子菜单（task-definitions / task-queues /
     task-executions / ai-async-tasks），前端 system.js 亦保留对应静态路由，
     URL 直访会落到遗留 GenericObjectList。

本测试锁定「入口收敛」这一状态：菜单层只剩 task-management 一个节点，
不绑任何遗留实体，且 task.v1 页面路由所需的 task 管理权限不再挂在遗留码上。
"""
import json
import sqlite3

import pytest

from meta.scripts.init_task_menus import init_task_menus

#遗留实体 BO：入口收敛后不应再出现在 task-management 的任何绑定里
LEGACY_BOS = ('scheduled_task', 'task_queue', 'task_execution', 'ai_async_task')

# 遗留叶子菜单 code：应从 menus 表彻底消失
LEGACY_LEAF_CODES = ('task-definitions', 'task-queues', 'task-executions', 'ai-async-tasks')


@pytest.fixture
def ds(tmp_path):
    """最小 data_source 替身：只需 query / execute / commit。"""
    con = sqlite3.connect(':memory:')
    con.execute("""CREATE TABLE menus (
        menu_code TEXT PRIMARY KEY, menu_name TEXT, menu_path TEXT,
        page_type TEXT, primary_object_type TEXT, object_types TEXT,
        bo_bindings TEXT, required_permissions TEXT, parent_menu TEXT,
        icon TEXT, color TEXT, description TEXT, sort_order INTEGER,
        is_active INTEGER, show_in_sidebar INTEGER, auto_generated INTEGER,
        page_config TEXT)""")
    con.execute("""CREATE TABLE menu_permissions (
        menu_code TEXT PRIMARY KEY, menu_name TEXT, menu_path TEXT,
        required_permissions TEXT, required_any_permission INTEGER,
        parent_menu TEXT, icon TEXT, sort_order INTEGER, is_active INTEGER,
        data_permission_hint TEXT)""")

    class _DS:
        def query(self, sql, params=()):
            cur = con.execute(sql, params)
            return cur.fetchall()

        def execute(self, sql, params=()):
            return con.execute(sql, params)

        def commit(self):
            con.commit()

    yield _DS()
    con.close()


def _menu(ds, code):
    """按列名取值，避免依赖 SELECT * 的列序。"""
    rows = ds.query(
        "SELECT menu_name, page_type, show_in_sidebar, auto_generated,"
        " object_types, bo_bindings, required_permissions"
        " FROM menus WHERE menu_code = ?", (code,))
    assert rows, f"菜单 {code} 应存在"
    return rows[0]


def _cols(row):
    return {
        'object_types': json.loads(row[4] or '[]'),
        'bo_bindings': json.loads(row[5] or '[]'),
        'required_permissions': json.loads(row[6] or '[]'),
    }


@pytest.mark.unit
class Test入口收敛:
    """init_task_menus 跑完后，菜单层应只剩 task.v1 一个任务入口"""

    def test_menu_name_is_任务管理(self, ds):
        """[收敛-1] 菜单名应为「任务管理」，不是旧的「任务调度」"""
        init_task_menus(ds)
        assert _menu(ds, 'task-management')[0] == '任务管理'

    def test_no_legacy_leaf_menus(self, ds):
        """[收敛-2] 4 条遗留叶子菜单不应再被种子写入"""
        init_task_menus(ds)
        for code in LEGACY_LEAF_CODES:
            assert ds.query("SELECT menu_code FROM menus WHERE menu_code = ?", (code,)) == [], (
                f"遗留叶子菜单 {code} 不应写入")

    def test_task_management_binds_no_legacy_bo(self, ds):
        """[收敛-3] task-management 不得再绑任何遗留实体 BO"""
        init_task_menus(ds)
        cols = _cols(_menu(ds, 'task-management'))
        for field in ('object_types', 'bo_bindings'):
            for bo in cols[field]:
                assert not str(bo).startswith(LEGACY_BOS), (
                    f"{field} 仍含遗留 BO: {bo}")
        for perm in cols['required_permissions']:
            assert not perm.startswith(LEGACY_BOS), (
                f"required_permissions 仍含遗留权限码: {perm}")

    def test_legacy_rows_purged_on_rerun(self, ds):
        """[收敛-4] 幂等重跑时须主动 DELETE 遗留菜单行（含历史库已有数据）"""
        #先手工塞入遗留行，模拟"旧版本已写过"的历史库
        for code in LEGACY_LEAF_CODES:
            ds.execute(
                "INSERT INTO menus (menu_code, menu_name, menu_path, page_type,"
                " parent_menu, is_active, show_in_sidebar)"
                " VALUES (?, ?, ?, 'object_list', 'task-management', 1, 0)",
                (code, code, f'/system/{code}'))
        ds.execute(
            "INSERT INTO menu_permissions (menu_code, menu_name, menu_path,"
            " required_permissions, required_any_permission, parent_menu,"
            " icon, sort_order, is_active)"
            " VALUES ('task-definitions', '任务定义', '/system/task-definitions',"
            " '[]', 0, 'task-management', 'List', 1, 1)")

        init_task_menus(ds)

        for code in LEGACY_LEAF_CODES:
            assert ds.query("SELECT menu_code FROM menus WHERE menu_code = ?", (code,)) == [], (
                f"遗留菜单行 {code} 未被清除")
            assert ds.query(
                "SELECT menu_code FROM menu_permissions WHERE menu_code = ?", (code,)) == [], (
                f"遗留权限行 {code} 未被清除")

    def test_task_management_remains_sidebar_visible(self, ds):
        """[收敛-5] 收敛后主入口仍须留在侧栏（不能连入口一起收掉）"""
        init_task_menus(ds)
        row = _menu(ds, 'task-management')
        assert row[2] == 1, 'task-management 应 show_in_sidebar=1'
        assert row[3] == 0, 'task-management 应 auto_generated=0（人工维护）'
        assert row[1] == 'custom_page', 'task-management 应挂自定义页面（非遗留 hub）'