# -*- coding: utf-8 -*-
"""主数据生命周期（D1）消费端核对测试。

依据: docs/specs/p2-master-data-pricing-variant/spec.md §1
      meta/schemas/item.yaml L606-686（status 四态 + activate/deactivate 状态机）

三组断言:
  1) 台账: 单据/明细对象引用主数据锚的字段，必须声明 status 过滤（否则 draft/inactive 静默放行）
  2) 写入: draft / inactive 物料被通用写校验拒绝，active 放行
  3) 结算: 引用已 inactive 物料的老单据，金额/税额照常重算（inactive 可结算）
"""

import os
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from meta.core.models import FieldType, MetaField, MetaObject, registry
from meta.core.value_help_accessor import (
    get_validation_flag,
    get_value_help,
    validate_value_helps,
)
from meta.core.yaml_loader import load_yaml_file
from meta.services.sales_order_amount_service import SalesOrderAmountService

_SCHEMA_DIR = os.path.join(PROJECT_ROOT, 'meta', 'schemas')

#: 被引用的主数据锚/主数据对象（D1 承诺的适用范围）
MASTER_DATA_TARGETS = {
    'item', 'party', 'org', 'location', 'uom', 'currency', 'tax_code',
    'territory', 'item_group', 'price_list', 'rate_table', 'salesperson',
}

#: 单据对象清单（覆盖未声明 bo_sub_category 的销售订单族；按 id 显式列举）
DOCUMENT_OBJECT_IDS = {
    'sales_order', 'sales_order_line', 'sales_order_schedule',
    'adjustment', 'calc_result', 'calc_detail',
}

#: 白名单：{('object_id', 'field_id'): '允许不带 status 过滤的理由'}（初始为空）
STATUS_FILTER_EXEMPT = {}


def _sub_category_value(meta_obj):
    sub = getattr(meta_obj, 'bo_sub_category', None)
    return getattr(sub, 'value', sub)


def _is_document_object(meta_obj) -> bool:
    return (_sub_category_value(meta_obj) == 'document'
            or meta_obj.id in DOCUMENT_OBJECT_IDS)


@pytest.fixture(scope='module', autouse=True)
def _load_registry():
    """加载全量 YAML（台账需要遍历全部已注册对象）。"""
    registry.reload(os.path.join(PROJECT_ROOT, 'meta', 'schemas'))
    yield


def _collect_gaps():
    gaps = []
    for obj_id, meta_obj in registry.get_all().items():
        if not _is_document_object(meta_obj):
            continue
        for field in meta_obj.fields:
            vh = get_value_help(field)
            if not vh or getattr(vh.source, 'type', None) != 'bo':
                continue
            target = getattr(vh.source, 'target_bo', None)
            if target not in MASTER_DATA_TARGETS:
                continue
            if (obj_id, field.id) in STATUS_FILTER_EXEMPT:
                continue
            value_filter = getattr(vh.source, 'value_filter', None) or {}
            has_status = 'status' in value_filter or 'status__in' in value_filter
            if not has_status:
                gaps.append((obj_id, field.id, target, 'missing_status_filter'))
            elif not get_validation_flag(vh):
                gaps.append((obj_id, field.id, target, 'validation_off'))
    return gaps


def test_all_document_reference_fields_declare_status_filter():
    """台账：单据对象引用主数据锚时必须声明 status 过滤 + 写校验开启。"""
    gaps = _collect_gaps()
    assert gaps == [], (
        '以下字段引用主数据但未声明 status 过滤（draft/inactive 会被静默放行）：\n'
        + '\n'.join(f'  {obj}.{field} -> {target}: {why}'
                    for obj, field, target, why in gaps)
    )


class _CountDS:
    """固定命中数的假数据源：count=0 表示「按 value_filter 查不到该行」。

    `validate_value_helps` 的查询恒为 `WHERE id = ? AND status = 'active'`，
    因此 draft / inactive 物料等价于「查到 0 行」，active 物料等价于「查到 1 行」。
    """

    def __init__(self, count):
        self.count = count

    def execute(self, sql, params=None):
        return _Cursor((self.count,))


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


@pytest.fixture
def item_registered():
    """sales_order_line.item_id 的 target_bo=item 需要有可解析的最小对象。"""
    previous = registry.get('item')
    registry.register(MetaObject(
        id='item',
        name='物料',
        table_name='items',
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id'),
            MetaField(id='status', name='状态', field_type=FieldType.STRING,
                      db_column='status'),
        ],
    ))
    yield
    if previous is not None:
        registry.register(previous)
    else:
        registry.unregister('item')


def _line_meta():
    return load_yaml_file(os.path.join(_SCHEMA_DIR, 'sales_order_line.yaml'))


def test_draft_item_rejected_on_line_create(item_registered):
    """draft 物料不可被单据行引用（D1 硬门槛）。

    value_filter.status='active' 生效时，draft 物料在受控查询里命中 0 行。
    """
    errors = validate_value_helps(
        _CountDS(0), _line_meta(), {'item_id': 999})
    assert len(errors) >= 1 and '999' in errors[0]


def test_inactive_item_rejected_on_new_line(item_registered):
    """inactive 物料阻止新单据引用。"""
    errors = validate_value_helps(
        _CountDS(0), _line_meta(), {'item_id': 999})
    assert len(errors) >= 1 and '999' in errors[0]


def test_active_item_accepted_on_line_create(item_registered):
    """active 物料通过写校验。"""
    errors = validate_value_helps(
        _CountDS(1), _line_meta(), {'item_id': 999})
    assert errors == []


class _InactiveItemAmountService(SalesOrderAmountService):
    """注入式替身：行引用已 inactive 的物料，验证结算不被拦截。"""

    def __init__(self):
        super().__init__(data_source=None)
        self.order = {
            'id': 10, 'order_type_id': 1, 'order_date': '2026-10-15',
            'currency_id': 8,
        }
        self.line = {
            'id': 1, 'order_id': 10, 'qty': 2, 'unit_price': 50,
            'tax_code_id': 5, 'header_discount_amount': 0,
            'header_surcharge_amount': 0,
            'item_id': 7,          # 引用物料已停用（金额服务不应读 item.status）
            'item_status': 'inactive',
        }
        self.line_written = {}
        self.order_written = {}

    def _load_line(self, line_id):
        return dict(self.line) if line_id == 1 else None

    def _load_order(self, order_id):
        return dict(self.order) if order_id == 10 else None

    def _sum_lines(self, order_id):
        merged = dict(self.line)
        merged.update(self.line_written)
        return [merged]

    def _currency_decimals(self, currency_id):
        return 2

    def _document_category(self, order_type_id):
        return 'standard'

    def _lookup_rate_percent(self, tax_code_id, order_date):
        return Decimal('13')

    def _lookup_tax_rounding(self, tax_code_id):
        return 'round'

    def _write_line(self, line_id, values):
        self.line_written.update(values)

    def _write_order(self, order_id, values):
        self.order_written.update(values)


def test_inactive_item_settlement_not_blocked():
    """inactive 可结算：老单据金额/税额照常重算，不因物料停用而报错。"""
    service = _InactiveItemAmountService()
    line = service.recompute_line(1)
    assert line is not None, '停用物料的存量行应可继续结算'
    assert line['net_amount'] == Decimal('100.00')
    assert line['tax_rate_percent'] == Decimal('13')
    assert line['tax_amount'] == Decimal('13.00')
    assert line['gross_amount'] == Decimal('113.00')

    totals = service.recompute_order(10)
    assert totals['net_amount'] == Decimal('100.00')
    assert totals['tax_amount'] == Decimal('13.00')
    assert totals['gross_amount'] == Decimal('113.00')
