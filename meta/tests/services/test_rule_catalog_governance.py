# -*- coding: utf-8 -*-
"""规则中心治理字段单测（spec-rule-model-2026-11-10 §12.3 / M7-2）。

覆盖 DoD：
  D1  MetaRule 三个治理字段默认值：order_by=ORDER_BY / effective_to 空 / rule_key 空
  D2  parse_rule 出口注入：默认 order_by、声明值原样保留、effective_to 透传、
      bo_id 存在时派生 rule_key，缺失时留空
  D3  _descriptor 输出 4 个治理键，来源未声明时留空（不臆造默认）
  D4  list_rules 落地 severity / enabled 过滤；severity 空值行不匹配任何非空
      筛选值；非法 severity 抛 RuleFilterError
"""

from dataclasses import asdict

import pytest

from meta.core.models import MetaRule
from meta.core.rule_hit_policy import ORDER_BY
from meta.core.rule_keys import bo_yaml_key
from meta.core.yaml_loader import parse_rule
from meta.services.rule_catalog_service import (
    RuleCatalogService,
    RuleFilterError,
    _descriptor,
)

GOVERNANCE_KEYS = ('disposition', 'hit_policy', 'order_by', 'effective_to')


def _rule_data(**overrides):
    """最小可解析规则声明（parse_validation 无必填字段）。"""
    data = {'id': 'R1', 'name': 'n', 'type': 'validation'}
    data.update(overrides)
    return data


def _items():
    """三个覆盖 severity / enabled 三态的描述符。"""
    return [
        _descriptor(
            'bo_yaml', 'bo_yaml:bo.R1', 'r1',
            rule_type='validation', scope_bo='bo', status='active',
            severity='error', enabled=True, layer='L1',
        ),
        _descriptor(
            'bo_yaml', 'bo_yaml:bo.R2', 'r2',
            rule_type='validation', scope_bo='bo', status='active',
            severity='', enabled=False, layer='L1',
        ),
        _descriptor(
            'control_parameter', 'control_parameter:c1', 'c1',
            rule_type='control_parameter', configurable=True, status='active',
            severity='warning', enabled=None, layer='L2',
        ),
    ]


@pytest.fixture()
def service(monkeypatch):
    svc = RuleCatalogService()
    monkeypatch.setattr(
        svc, '_collect',
        lambda include_draft=False: (_items(), {'bo_yaml': 'ok'}),
    )
    return svc


# ------------------------- D1 模型默认值 -------------------------

def test_meta_rule_governance_defaults():
    snapshot = asdict(MetaRule(id='R1', name='n'))
    assert snapshot['order_by'] == list(ORDER_BY)
    assert snapshot['effective_to'] == ''
    assert snapshot['rule_key'] == ''


# ------------------------- D2 parse_rule 注入 -------------------------

def test_parse_rule_injects_default_governance():
    rule = parse_rule(_rule_data())
    assert rule.order_by == list(ORDER_BY)
    assert rule.effective_to == ''
    # 无 bo_id 上下文时不臆造键
    assert rule.rule_key == ''


def test_parse_rule_keeps_declared_governance():
    rule = parse_rule(
        _rule_data(order_by=['priority ASC'], effective_to='2027-01-01'),
        bo_id='sales_order',
    )
    assert rule.order_by == ['priority ASC']
    assert rule.effective_to == '2027-01-01'
    assert rule.rule_key == bo_yaml_key('sales_order', 'R1')


def test_parse_rule_stringifies_order_by_items():
    rule = parse_rule(_rule_data(order_by=[1, 'priority DESC']))
    assert rule.order_by == ['1', 'priority DESC']


# ------------------------- D3 描述符治理键 -------------------------

def test_descriptor_governance_keys_default_empty():
    item = _descriptor('bo_yaml', 'bo_yaml:bo.R1', 'n')
    for key in GOVERNANCE_KEYS:
        assert key in item
    assert item['disposition'] == ''
    assert item['hit_policy'] == ''
    assert item['order_by'] == []
    assert item['effective_to'] == ''


def test_descriptor_passes_governance_values():
    item = _descriptor(
        'bo_yaml', 'bo_yaml:bo.R1', 'n',
        disposition='block', hit_policy='all',
        order_by=['priority DESC'], effective_to='2026-12-31',
    )
    assert item['disposition'] == 'block'
    assert item['hit_policy'] == 'all'
    assert item['order_by'] == ['priority DESC']
    assert item['effective_to'] == '2026-12-31'


# ------------------------- D4 list_rules 过滤 -------------------------

def test_list_rules_filters_severity(service):
    assert service.list_rules(severity='error')['total'] == 1
    assert service.list_rules(severity='warning')['total'] == 1
    # severity 为空的行不匹配任何非空筛选值
    assert service.list_rules(severity='info')['total'] == 0
    assert service.list_rules()['total'] == 3


def test_list_rules_filters_enabled_three_states(service):
    assert service.list_rules(enabled=True)['total'] == 1
    assert service.list_rules(enabled=False)['total'] == 1
    assert service.list_rules(enabled=None)['total'] == 3


def test_list_rules_rejects_unknown_severity(service):
    with pytest.raises(RuleFilterError):
        service.list_rules(severity='fatal')