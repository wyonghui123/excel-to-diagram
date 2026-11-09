# -*- coding: utf-8 -*-
"""服务域契约测试（service_request 状态机 / service 计划行解禁）。

[TEST-EFF P2-1] 由两个同域（service 域 YAML 声明 + 守卫，纯内存）的 <=5 用例
小文件合并：
- test_service_request_lifecycle_rules.py (service_request 状态机声明回归)
- test_service_schedule_kind.py           (B6 验收第 7 条 + 枚举解禁)
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from meta.services import sales_order_guard_service as guard_module
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)

pytestmark = pytest.mark.unit

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'
SCHEMA = _SCHEMA_DIR / 'service_request.yaml'


# ===========================================================================
# 一、service_request 状态机声明回归
# ===========================================================================
# schema 的 `rules: type=state_transition` 是服务请求生命周期的唯一真源；
# 本用例锁定规则形状与状态边，防止声明被悄悄改掉后服务层与前端动作失配。

def _rules():
    data = yaml.safe_load(SCHEMA.read_text(encoding='utf-8'))
    return [r for r in (data.get('rules') or [])
            if r.get('type') == 'state_transition']


def test_every_rule_has_state_field_and_triggers():
    rules = _rules()
    assert rules, 'service_request.yaml 未声明 state_transition 规则'
    assert len({r['id'] for r in rules}) == len(rules), '规则 id 重复'
    for rule in rules:
        assert rule['state_field'] == 'status', rule['id']
        assert rule['from_states'], rule['id']
        assert rule['to_state'] not in rule['from_states'], rule['id']
        assert rule.get('triggers') == ['before_update'], rule['id']


def test_lifecycle_edges_match_documented_machine():
    pairs = {(tuple(r['from_states']), r['to_state']) for r in _rules()}
    assert pairs == {
        (('draft',), 'submitted'),
        (('submitted',), 'approved'),
        (('submitted',), 'rejected'),
        (('approved',), 'completed'),
        (('completed',), 'closed'),
        (('draft', 'submitted', 'approved'), 'cancelled'),
    }


def test_reject_only_from_submitted_but_cancel_covers_pre_commit_states():
    pairs = {(tuple(r['from_states']), r['to_state']) for r in _rules()}
    assert (('submitted',), 'rejected') in pairs
    assert (('approved',), 'rejected') not in pairs
    assert (('draft', 'submitted', 'approved'), 'cancelled') in pairs


# ---------------- 守卫按声明拒绝非法迁移 ----------------------------


def _ensure_registry():
    from meta.core.models import registry
    if registry.get('service_request') is None:
        registry.reload(str(SCHEMA.parent))


class _EmptyDS:
    """非法迁移应在触库前被拒绝，这里刻意返回空结果。"""

    def query(self, sql, params=None):
        return []

    def execute(self, sql, params=None):
        raise AssertionError('非法迁移不应触库: ' + sql)


def _ctx(object_type, current_status, target_status):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_type),
        action='crud_update',
        params={'id': 1, 'status': target_status},
        data_source=_EmptyDS(),
        old_data={'id': 1, 'status': current_status},
        extra={},
    )


@pytest.fixture(scope='module', autouse=True)
def _registry_loaded():
    _ensure_registry()


@pytest.mark.parametrize('object_type,current,target', [
    ('service_request', 'draft', 'approved'),
    ('service_request', 'approved', 'submitted'),
    ('service_request', 'completed', 'cancelled'),
    ('requisition', 'rejected', 'submitted'),
])
def test_guard_rejects_undeclared_transition(object_type, current, target):
    from meta.core.exceptions import StateMachineViolationError
    from meta.core.interceptors.demand_entry_guard_interceptor import (
        DemandEntryGuardInterceptor,
    )

    with pytest.raises(StateMachineViolationError) as exc:
        DemandEntryGuardInterceptor().before_action(
            _ctx(object_type, current, target))
    assert exc.value.code == 'STATE_MACHINE_VIOLATION'


def test_guard_allows_declared_transition():
    from meta.core.interceptors.demand_entry_guard_interceptor import (
        DemandEntryGuardInterceptor,
    )

    DemandEntryGuardInterceptor().before_action(
        _ctx('service_request', 'submitted', 'approved'))


# ===========================================================================
# 二、service 计划行解禁（B6 验收第 7 条 + 枚举解禁）
# ===========================================================================
# 依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md
#       §10.6 R-ST-0 / §10.10 B6-7 / §10.15
# 口径说明: spec §10.10-7 写作 `SCHEDULE_VISIT_NO_REQUIRED`，守卫实际错误码为
# `SERVICE_VISIT_NO_REQUIRED`（sales_order_guard_service.py L1595-1601），本测试以代码为准。

_SCHEMA_PATH = _SCHEMA_DIR / 'sales_order_schedule.yaml'


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
