# -*- coding: utf-8 -*-
"""销售订单行项目任务守卫测试（G15 P2-1 R1-R5）

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.1
  docs/specs/spec-project-g15-eto-P2-tasks.md 阶段 A
"""

import pytest

pytestmark = pytest.mark.unit

from meta.services.sales_order_guard_service import (
    SO_LINE_PROJECT_MISMATCH,
    SO_LINE_SEGMENT_TASK_CONFLICT,
    SO_LINE_TASK_PROJECT_REQUIRED,
    SalesOrderGuardError,
    SalesOrderGuardService,
)


class _FakeDS:
    """只覆盖行项目任务判定用到的查询。"""

    def __init__(self, orders=None, tasks=None, items=None, tables=None):
        self.orders = orders or {}
        self.tasks = tasks or {}
        self.items = items or {}
        #: 存在的表；缺省含 project_tasks / items / sales_orders
        self.tables = tables if tables is not None else {
            'project_tasks', 'items', 'sales_orders'}

    def query(self, sql, params=None):
        p = list(params or [])
        if "FROM sqlite_master WHERE type='table'" in sql:
            return [{'name': p[0]}] if p[0] in self.tables else []
        if 'FROM project_tasks WHERE id' in sql:
            row = self.tasks.get(p[0])
            return [row] if row else []
        if 'SELECT so_segment_enabled FROM items WHERE id' in sql:
            row = self.items.get(p[0])
            return [{'so_segment_enabled': row.get('so_segment_enabled', 0)}] \
                if row else []
        if 'FROM items WHERE id' in sql:
            row = self.items.get(p[0])
            return [row] if row else []
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        raise AssertionError('unexpected sql: %s' % sql)

    def execute(self, sql, params=None):
        raise AssertionError('unexpected write: %s' % sql)


ORDERS = {
    20: {'id': 20, 'order_no': 'SO-1', 'document_type_id': None,
         'status': 'draft', 'project_id': 9001},
    # 抬头未归集项目：行挂任务时无法归一化
    21: {'id': 21, 'order_no': 'SO-2', 'document_type_id': None,
         'status': 'draft', 'project_id': None},
}

TASKS = {
    5001: {'id': 5001, 'project_id': 9001, 'task_type': 'activity',
           'status': 'planned'},
    5002: {'id': 5002, 'project_id': 9002, 'task_type': 'activity',
           'status': 'planned'},
    5003: {'id': 5003, 'project_id': 9001, 'task_type': 'activity',
           'status': 'done'},
    5004: {'id': 5004, 'project_id': 9001, 'task_type': 'phase',
           'status': 'planned'},
    5005: {'id': 5005, 'project_id': 9001, 'task_type': 'activity',
           'status': 'in_progress'},
}

ITEMS = {
    7: {'id': 7, 'item_type': 'goods', 'status': 'active', 'base_uom': 1,
        'so_segment_enabled': 0},
    8: {'id': 8, 'item_type': 'goods', 'status': 'active', 'base_uom': 1,
        'so_segment_enabled': 1},
}


def _ds(**kwargs):
    return _FakeDS(orders=ORDERS, tasks=TASKS, items=ITEMS, **kwargs)


def _line(**overrides):
    data = {'order_id': 20, 'qty': 1, 'uom_id': 1, 'description': '行描述'}
    data.update(overrides)
    return data


def _validate(data, ds=None, old_data=None):
    return SalesOrderGuardService(ds or _ds()).validate_line_write(
        data, old_data=old_data, is_create=True)


class TestProjectTaskLink:

    def test_task_with_line_project_ok(self):
        _validate(_line(project_id=9001, project_task_id=5001))

    def test_task_normalized_from_header_project_ok(self):
        # 行项目为空 → 取抬头项目归一化后判定
        _validate(_line(project_task_id=5001))

    def test_in_progress_task_ok(self):
        _validate(_line(project_task_id=5005))

    def test_task_without_any_project_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate({'order_id': 21, 'qty': 1, 'uom_id': 1,
                       'description': '行描述', 'project_task_id': 5001})
        assert e.value.rule == SO_LINE_TASK_PROJECT_REQUIRED
        assert e.value.field_name == 'project_task_id'

    def test_task_of_other_project_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(project_id=9001, project_task_id=5002))
        assert e.value.rule == 'PROJECT_TASK_PROJECT_MISMATCH'
        assert e.value.field_name == 'project_task_id'

    def test_task_missing_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(project_id=9001, project_task_id=9999))
        assert e.value.rule == 'PROJECT_TASK_PROJECT_MISMATCH'

    def test_done_task_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(project_id=9001, project_task_id=5003))
        assert e.value.rule == 'PROJECT_TASK_NOT_EXECUTABLE'

    def test_phase_task_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(project_id=9001, project_task_id=5004))
        assert e.value.rule == 'PROJECT_TASK_NOT_EXECUTABLE'

    def test_line_and_header_project_mismatch_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(project_id=9002))
        assert e.value.rule == SO_LINE_PROJECT_MISMATCH
        assert e.value.field_name == 'project_id'

    def test_segment_item_with_task_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            _validate(_line(item_id=8, project_id=9001, project_task_id=5001))
        assert e.value.rule == SO_LINE_SEGMENT_TASK_CONFLICT
        assert e.value.field_name == 'project_task_id'

    def test_segment_item_without_task_ok(self):
        # R5 只拒绝「SO 段 + 任务」组合，单独各行不受影响
        _validate(_line(item_id=8, project_id=9001))

    def test_mts_line_without_task_unaffected(self):
        _validate(_line(item_id=7))

    def test_task_table_missing_is_fail_open(self):
        _validate(_line(project_id=9001, project_task_id=5001),
                  ds=_ds(tables={'items', 'sales_orders'}))

    def test_update_retarget_to_terminal_task_rejected(self):
        old = {'id': 1, 'order_id': 20, 'project_id': 9001,
               'project_task_id': 5001}
        data = dict(old, project_task_id=5003, qty=1, uom_id=1,
                    description='行描述')
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                data, old_data=old, is_create=False)
        assert e.value.rule == 'PROJECT_TASK_NOT_EXECUTABLE'
