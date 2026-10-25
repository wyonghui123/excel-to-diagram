# -*- coding: utf-8 -*-
"""销售订单行结构展开测试（P1 · E1 ~ E8）

依据: meta/services/sales_order_expand_service.py 头注释
      meta/schemas/sales_order_line.yaml 头注释 ⑥ / ⑦

测试口径:
  · 求解与金额由桩件替代 —— 本文件只测展开服务的分派与落行规则；
    配置求解自身行为见 test_item_structure_config.py，金额见 test_sales_order_amount.py。
  · FakeDS 是一张内存订单行表，覆盖展开服务用到的查询与父行回写。
"""

from contextlib import contextmanager
from types import SimpleNamespace

import os

import pytest

# FakeDS 以 SQL 片段分流（无 Factory 可复用），按仓库惯例走 raw SQL escape hatch。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

pytestmark = pytest.mark.unit

from meta.services.sales_order_expand_service import (
    SalesOrderExpandError,
    SalesOrderExpandService,
)

ORDER = {
    'id': 10, 'order_no': 'SO-202610-000001', 'order_type_id': 1,
    'order_date': '2026-10-25', 'status': 'draft', 'currency_id': 8,
}

PARENT_LINE = {
    'id': 100, 'order_id': 10, 'line_no': '10', 'line_type_id': 101,
    'item_id': 500, 'qty': 2, 'uom_id': 1, 'unit_price': 100.0,
    'tax_code_id': None, 'requested_date': '2026-11-01',
    'plant_location_id': 7, 'status': 'open', 'parent_line_id': None,
    'component_no': None, 'configuration_id': None,
    'pricing_mode': 'standalone',
}

STRUCTURE = {
    'id': 900, 'item_id': 500, 'revision': 'A', 'usage': 'sales',
    'alternative_no': 1, 'base_qty': 1, 'status': 'active',
    'valid_from': '2026-01-01', 'valid_to': None,
}

ITEMS = {
    501: {'id': 501, 'code': 'C1', 'name': '组件一', 'item_type': 'goods'},
    502: {'id': 502, 'code': 'SVC1', 'name': '安装服务', 'item_type': 'service'},
}

UOMS = {'PCS': 1, 'SET': 2}

TYPES = {'STD': 101, 'SVC': 102}

COMPONENTS = [
    {'component_key': 'L0010', 'parent_component_key': None,
     'component_item_id': 501, 'qty': 2, 'uom_code': 'PCS',
     'selection_source': 'auto'},
    {'component_key': 'L0010.L0020', 'parent_component_key': 'L0010',
     'component_item_id': 502, 'qty': 1, 'uom_code': 'PCS',
     'selection_source': 'auto'},
]


class _FakeDS:
    """内存订单行表 + 按 SQL 片段分流的只读查询。"""

    def __init__(self, orders=None, lines=None, structures=None,
                 items=None, uoms=None, types=None, fail_on_insert=None):
        self.orders = {row['id']: dict(row) for row in (orders or [ORDER])}
        self.lines = {row['id']: dict(row) for row in (lines or [PARENT_LINE])}
        self.structures = list(structures if structures is not None else [STRUCTURE])
        self.items = items or ITEMS
        self.uoms = uoms or UOMS
        self.types = types or TYPES
        self.fail_on_insert = fail_on_insert
        self._next_id = max(self.lines.keys() or [0]) + 1

    def query(self, sql, params=None):
        p = list(params or [])

        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        if 'MAX(CAST(line_no' in sql:
            order_id = str(p[0])
            numbers = [
                int(line['line_no']) for line in self.lines.values()
                if str(line.get('order_id')) == order_id
                and str(line.get('line_no') or '').isdigit()]
            return [{'mx': max(numbers) if numbers else None}]
        if 'FROM sales_order_lines WHERE parent_line_id' in sql:
            hit = any(str(line.get('parent_line_id')) == str(p[0])
                      for line in self.lines.values())
            return [{'ok': 1}] if hit else []
        if 'FROM sales_order_lines WHERE id' in sql:
            row = self.lines.get(p[0])
            return [row] if row else []
        if 'FROM item_structures' in sql:
            item_id, usage, as_of = p[0], p[1], p[2]
            return [
                s for s in self.structures
                if s['item_id'] == item_id and s['usage'] == usage
                and s['status'] == 'active'
                and (s.get('valid_from') in (None, '') or s['valid_from'] <= as_of)
                and (s.get('valid_to') in (None, '') or s['valid_to'] >= as_of)]
        if 'FROM items WHERE id IN' in sql:
            return [self.items[i] for i in p if i in self.items]
        if 'FROM uoms WHERE code' in sql:
            uom_id = self.uoms.get(p[0])
            return [{'id': uom_id}] if uom_id is not None else []
        if 'FROM type_definitions' in sql:
            type_id = self.types.get(p[-1])
            return [{'id': type_id}] if type_id is not None else []
        raise AssertionError('unexpected sql: %s' % sql)

    def insert(self, table_name, data):
        if self.fail_on_insert and table_name == self.fail_on_insert:
            raise RuntimeError('insert failed')
        row = dict(data)
        row['id'] = self._next_id
        self._next_id += 1
        self.lines[row['id']] = row
        return row['id']

    def execute(self, command, params=None):
        p = list(params or [])
        if command.startswith('UPDATE sales_order_lines SET'):
            line = self.lines[p[-1]]
            line['configuration_id'] = p[0]
            line['pricing_mode'] = p[1]
            if 'unit_price = NULL' in command:
                line['unit_price'] = None
            return SimpleNamespace(rowcount=1)
        raise AssertionError('unexpected command: %s' % command)

    @contextmanager
    def transaction(self):
        yield


class _FakeConfig:
    """固定返回一份求解结果，记录收到的求解参数。"""

    def __init__(self, components=None, configuration_id=901,
                 config_hash='hash-901', warnings=None):
        self.components = components if components is not None else COMPONENTS
        self.configuration_id = configuration_id
        self.config_hash = config_hash
        self.warnings = warnings or []
        self.calls = []

    def solve(self, structure_id, **kwargs):
        self.calls.append({'structure_id': structure_id, **kwargs})
        return {
            'configuration_id': self.configuration_id,
            'config_hash': self.config_hash,
            'components': self.components,
            'values': [],
            'warnings': self.warnings,
        }


class _FakeAmount:
    def __init__(self):
        self.recomputed = []
        self.orders = []

    def recompute_line(self, line_id):
        self.recomputed.append(line_id)
        return {}

    def recompute_order(self, order_id):
        self.orders.append(order_id)
        return {}


def _service(ds, config=None, amount=None):
    return SalesOrderExpandService(
        ds, config_service=config or _FakeConfig(),
        amount_service=amount or _FakeAmount())


# ---------------------------------------------------------------- 正常路径


def test_expand_builds_children_tree():
    ds = _FakeDS()
    config, amount = _FakeConfig(), _FakeAmount()

    result = _service(ds, config, amount).expand(10, 100)

    assert result['configuration_id'] == 901
    assert result['pricing_mode'] == 'bundle_price'
    assert result['component_count'] == 2

    first, second = result['lines']
    # 父行行号 10 → 子行从 20 起，每条 +10
    assert first['line_no'] == '20'
    assert second['line_no'] == '30'
    # 顶层组件挂父行，嵌套组件挂上一层组件行
    assert first['parent_line_id'] == 100
    assert second['parent_line_id'] == first['id']
    assert first['component_no'] == 'L0010'
    assert second['component_no'] == 'L0010.L0020'

    parent = ds.lines[100]
    assert parent['configuration_id'] == 901
    assert parent['pricing_mode'] == 'bundle_price'
    assert parent['unit_price'] == 100.0

    # 子行不重复写配置实例；金额逐行重算后汇总抬头
    assert ds.lines[first['id']]['configuration_id'] is None
    assert amount.recomputed == [first['id'], second['id']]
    assert amount.orders == [10]


def test_expand_marks_service_component():
    ds = _FakeDS()
    result = _service(ds).expand(10, 100)

    service_line = ds.lines[result['lines'][1]['id']]
    assert service_line['line_type_id'] == 102
    assert service_line['plant_location_id'] is None
    assert service_line['requested_date'] is None
    assert service_line['item_id'] == 502


def test_expand_passes_line_qty_and_order_date_to_solver():
    config = _FakeConfig()
    _service(_FakeDS(), config).expand(10, 100)

    call = config.calls[0]
    assert call['structure_id'] == 900
    assert call['qty'] == 2
    assert call['as_of'] == '2026-10-25'
    assert call['context']['line_id'] == 100


def test_component_price_clears_parent_unit_price():
    ds = _FakeDS()
    _service(ds).expand(10, 100, pricing_mode='component_price')

    assert ds.lines[100]['unit_price'] is None
    assert ds.lines[100]['pricing_mode'] == 'component_price'


# ---------------------------------------------------------------- E1 前提


def test_rejects_non_draft_order():
    ds = _FakeDS(orders=[dict(ORDER, status='submitted')])
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(ds).expand(10, 100)
    assert exc.value.rule == 'expand_order_not_draft'


def test_rejects_unknown_order():
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS()).expand(999, 100)
    assert exc.value.rule == 'order_not_found'


def test_rejects_line_of_other_order():
    orders = [ORDER, dict(ORDER, id=11, order_no='SO-202610-000002')]
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(orders=orders)).expand(11, 100)
    assert exc.value.rule == 'line_order_mismatch'


def test_rejects_already_expanded_line():
    line = dict(PARENT_LINE, configuration_id=901)
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(lines=[line])).expand(10, 100)
    assert exc.value.rule == 'line_already_expanded'


def test_rejects_line_with_children_when_configuration_missing():
    child = dict(PARENT_LINE, id=200, line_no='20', parent_line_id=100)
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(lines=[PARENT_LINE, child])).expand(10, 100)
    assert exc.value.rule == 'line_already_expanded'


def test_rejects_child_line_expand():
    child = dict(PARENT_LINE, parent_line_id=999)
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(lines=[child])).expand(10, 100)
    assert exc.value.rule == 'line_is_component'


def test_rejects_line_without_item():
    line = dict(PARENT_LINE, item_id=None)
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(lines=[line])).expand(10, 100)
    assert exc.value.rule == 'line_item_required'


def test_rejects_closed_line():
    line = dict(PARENT_LINE, status='closed')
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(lines=[line])).expand(10, 100)
    assert exc.value.rule == 'line_not_open'


# ---------------------------------------------------------------- E2 结构


def test_rejects_structure_missing_for_sales_usage():
    structure = dict(STRUCTURE, usage='production')
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(structures=[structure])).expand(10, 100)
    assert exc.value.rule == 'item_structure_not_found_for_sales'


def test_picks_lowest_alternative_no_as_default():
    structures = [
        dict(STRUCTURE, id=902, alternative_no=2, revision='B'),
        dict(STRUCTURE, id=901, alternative_no=1, revision='A'),
    ]
    cfg = _FakeConfig()
    result = _service(_FakeDS(structures=structures), cfg).expand(10, 100)
    assert cfg.calls[0]['structure_id'] == 901
    assert result['component_count'] == 2


def test_prefers_latest_valid_from_within_same_alternative():
    structures = [
        dict(STRUCTURE, id=903, alternative_no=1, revision='B',
             valid_from='2026-06-01'),
        dict(STRUCTURE, id=901, alternative_no=1, revision='A'),
    ]
    cfg = _FakeConfig()
    _service(_FakeDS(structures=structures), cfg).expand(10, 100)
    assert cfg.calls[0]['structure_id'] == 903


def test_rejects_structure_outside_validity():
    structure = dict(STRUCTURE, valid_to='2026-09-30')
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(structures=[structure])).expand(10, 100)
    assert exc.value.rule == 'item_structure_not_found_for_sales'


# ---------------------------------------------------------------- E5 定价


def test_rejects_unknown_pricing_mode():
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS()).expand(10, 100, pricing_mode='gift')
    assert exc.value.rule == 'pricing_mode_invalid'


def test_explicit_standalone_pricing_mode_rejected():
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS()).expand(10, 100, pricing_mode='standalone')
    assert exc.value.rule == 'pricing_mode_invalid'


def test_inherits_pricing_mode_from_line():
    line = dict(PARENT_LINE, pricing_mode='base_plus_option')
    result = _service(_FakeDS(lines=[line])).expand(10, 100)
    assert result['pricing_mode'] == 'base_plus_option'


# ---------------------------------------------------------------- E4/E6 落行


def test_rejects_component_with_invalid_qty():
    components = [dict(COMPONENTS[0], qty=0)]
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(), _FakeConfig(components)).expand(10, 100)
    assert exc.value.rule == 'component_qty_invalid'


def test_rejects_component_without_uom():
    parent = dict(PARENT_LINE, uom_id=None)
    components = [dict(COMPONENTS[0], uom_code=None)]
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(lines=[parent]), _FakeConfig(components)).expand(10, 100)
    assert exc.value.rule == 'component_uom_missing'


def test_falls_back_to_parent_uom_when_component_uom_unknown():
    components = [dict(COMPONENTS[0], uom_code='UNKNOWN')]
    result = _service(_FakeDS(), _FakeConfig(components)).expand(10, 100)
    assert result['lines'][0]['uom_code'] == 'UNKNOWN'
    # uom_id 回退父行的 1
    assert result['component_count'] == 1


def test_rejects_orphan_component_reference():
    components = [dict(COMPONENTS[1])]  # 只有子组件，父组件不在结果里
    with pytest.raises(SalesOrderExpandError) as exc:
        _service(_FakeDS(), _FakeConfig(components)).expand(10, 100)
    assert exc.value.rule == 'component_parent_unknown'


def test_line_no_continues_after_existing_lines():
    other = dict(PARENT_LINE, id=101, line_no='40')
    ds = _FakeDS(lines=[PARENT_LINE, other])
    result = _service(ds).expand(10, 100)
    assert result['lines'][0]['line_no'] == '50'
    assert result['lines'][1]['line_no'] == '60'
