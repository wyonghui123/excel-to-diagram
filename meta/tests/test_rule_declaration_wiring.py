# -*- coding: utf-8 -*-
"""M7-1 / FR-012：加载期规则声明校验接线。

覆盖：
  1. 未知 rule_type 默认抛 RULE_TYPE_UNKNOWN；RULE_LOAD_ALLOW_UNKNOWN=1 降级
  2. 非选择型 rule_type 声明 hit_policy=first → RULE_HIT_POLICY_UNSUPPORTED
  3. 选择型（default）声明 hit_policy=first → 不报
  4. 未声明 hit_policy → 不误报
  5. load_yaml_file 接线：默认告警缓存；RULE_DECLARATION_STRICT=1 抛错

测试入口: python d:\\filework\\test.py --file meta/tests/test_rule_declaration_wiring.py
"""

import pytest

from meta.core import yaml_loader
from meta.core.models_enums import RuleType
from meta.core.rule_declaration_validator import (
    RuleDeclarationError,
    validate_hit_policies,
)


# ────────────────────────────────────────
# 1. 未知 rule_type
# ────────────────────────────────────────
def test_unknown_rule_type_raises_by_default(monkeypatch):
    monkeypatch.delenv('RULE_LOAD_ALLOW_UNKNOWN', raising=False)
    with pytest.raises(RuleDeclarationError) as exc_info:
        yaml_loader.parse_rule({'id': 'R1', 'name': '未知类型',
                                'type': 'no_such_type'})
    assert [error.code for error in exc_info.value.errors] == [
        'RULE_TYPE_UNKNOWN']


def test_unknown_rule_type_downgraded_with_flag(monkeypatch):
    monkeypatch.setenv('RULE_LOAD_ALLOW_UNKNOWN', '1')
    rule = yaml_loader.parse_rule({'id': 'R1', 'name': '未知类型',
                                   'type': 'no_such_type'})
    assert rule.rule_type == RuleType.VALIDATION


# ────────────────────────────────────────
# 2-4. hit_policy 声明合法性
# ────────────────────────────────────────
def _rule(rule_id, hit_policy='', condition='amount > 100',
          rule_type='validation'):
    return type('Rule', (), {
        'id': rule_id,
        'hit_policy': hit_policy,
        'condition': condition,
        'rule_type': rule_type,
    })()


def _object(rules):
    return type('MetaObject', (), {'id': 'purchase_order', 'rules': rules})()


def test_non_selective_rule_type_first_is_unsupported():
    errors = validate_hit_policies([_object([
        _rule('R1', 'first', rule_type='validation'),
    ])])
    assert [error.code for error in errors] == ['RULE_HIT_POLICY_UNSUPPORTED']
    assert 'R1' in errors[0].message


def test_selective_rule_type_first_is_allowed():
    errors = validate_hit_policies([_object([
        _rule('R1', 'first', rule_type=RuleType.DEFAULT.value),
    ])])
    assert errors == []


def test_undeclared_hit_policy_not_reported():
    assert validate_hit_policies([_object([_rule('R1')])]) == []


# ────────────────────────────────────────
# 5. load_yaml_file 接线
# ────────────────────────────────────────
_DECLARATION = """\
id: wiring_demo
name: 接线演示
table_name: wiring_demos
fields:
  - id: name
    name: 名称
    type: string
rules:
  - id: first_hit_check
    name: 首命中声明
    type: validation
    condition: amount > 100
    hit_policy: first
"""


@pytest.fixture()
def declaration_file(tmp_path):
    """落盘临时 schema，并清空加载器缓存避免缓存命中跳过校验。"""
    path = tmp_path / '_wiring_demo.yaml'
    path.write_text(_DECLARATION, encoding='utf-8')
    yaml_loader._yaml_cache.clear()
    yaml_loader._declaration_errors.clear()
    try:
        yield path
    finally:
        yaml_loader._yaml_cache.clear()
        yaml_loader._declaration_errors.clear()


def test_load_yaml_file_caches_declaration_errors(declaration_file, monkeypatch):
    monkeypatch.delenv('RULE_DECLARATION_STRICT', raising=False)

    obj = yaml_loader.load_yaml_file(str(declaration_file))
    assert obj is not None
    errors = yaml_loader._declaration_errors.get(str(declaration_file)) or []
    assert [error.code for error in errors] == ['RULE_HIT_POLICY_UNSUPPORTED']


def test_load_yaml_file_strict_mode_raises(declaration_file, monkeypatch):
    monkeypatch.setenv('RULE_DECLARATION_STRICT', '1')

    with pytest.raises(RuleDeclarationError):
        yaml_loader.load_yaml_file(str(declaration_file))