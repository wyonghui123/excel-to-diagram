# -*- coding: utf-8 -*-
"""service 计划行解禁测试（B6 验收第 7 条 + 枚举解禁）

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md
      §10.6 R-ST-0 / §10.10 B6-7 / §10.15

口径说明: spec §10.10-7 写作 `SCHEDULE_VISIT_NO_REQUIRED`，守卫实际错误码为
`SERVICE_VISIT_NO_REQUIRED`（sales_order_guard_service.py L1595-1601），本测试以代码为准。
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.services import sales_order_guard_service as guard_module
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'schemas' / 'sales_order_schedule.yaml'


def _schema():
    return yaml.safe_load(_SCHEMA_PATH.read_text(encoding='utf-8'))


class _FakeDS:
    """只覆盖计划行守卫判定 service kind 所需的查询。"""

    def __init__(self, orders=None, lines=None):
        self.orders = orders or {}
        self.lines = lines or {}

    def query(self, sql, params=None):
        p = list(params or [])
        if 'FROM sales_order_lines l' in sql:
            row = self.lines.get(p[0])
            if not row:
                return []
            row = dict(row)
            row.setdefault('delivery_relevant', 1)
            return [row]
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        raise AssertionError('unexpected sql: %s' % sql)


_ORDERS = {10: {'id': 10, 'status': 'draft'}}
_LINES = {100: {'id': 100, 'order_id': 10, 'qty': 10, 'uom_id': 8,
               'plant_location_id': None}}


def _ds():
    return _FakeDS(orders=_ORDERS, lines=_LINES)


def _service(**over):
    data = {
        'schedule_no': 21,
        'line_id': 100,
        'order_id': 10,
        'schedule_kind': 'service',
        'promised_date': '2026-11-30',
        'promised_qty': None,
        'billing_percent': None,
        'plant_location_id': None,
        'service_visit_no': 1,
        'milestone_code': None,
        'status': 'planned',
    }
    data.update(over)
    return data


# ---------------- 枚举解禁 ----------------

def test_service_kind_declared_active():
    """YAML 中三种 schedule_kind 均 active（含 service）。"""
    schema = _schema()
    kinds = next(field for field in schema['fields']
                 if field['id'] == 'schedule_kind')
    categories = {item['value']: item.get('category') for item in kinds['enum_values']}
    assert categories == {'delivery': 'active', 'billing': 'active',
                          'service': 'active'}


def test_schedule_kinds_enabled_includes_service():
    assert guard_module.SCHEDULE_KINDS_ENABLED == \
        ('delivery', 'billing', 'service')


# ---------------- 第 7 条：service 必填服务次数 ----------------

def test_service_schedule_without_visit_no_rejected():
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _service(service_visit_no=None))
    assert exc.value.rule == 'SERVICE_VISIT_NO_REQUIRED'
    assert exc.value.field_name == 'service_visit_no'


def test_service_schedule_with_visit_no_allowed():
    SalesOrderGuardService(_ds()).validate_schedule_write(_service())
