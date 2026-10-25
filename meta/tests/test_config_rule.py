# -*- coding: utf-8 -*-
"""配置规则与结果层测试（schema 接线 + 守卫 R8 / R9 / R16 + §5.5 形状 + 拦截器）

依据: meta/schemas/config_rule.yaml / config_rule_term.yaml
      meta/schemas/configuration.yaml / configuration_value.yaml / configuration_component.yaml
      meta/services/config_rule_guard_service.py
"""

import os

# 只用 :memory: sqlite 造最小表，按项目惯例解除 raw-SQL 守卫跳过。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.config_rule_guard_interceptor import (
    ConfigRuleGuardInterceptor,
)
from meta.services.config_rule_guard_service import (
    ConfigRuleGuardError,
    ConfigRuleGuardService,
)

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'


class _SqliteDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _new_db():
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE items (id INTEGER PRIMARY KEY, structure_role TEXT)')
    conn.execute(
        'CREATE TABLE item_structures (id INTEGER PRIMARY KEY, item_id INTEGER, '
        'revision TEXT)')
    conn.execute(
        'CREATE TABLE item_structure_lines (id INTEGER PRIMARY KEY, '
        'structure_id INTEGER, component_item_id INTEGER)')
    conn.execute(
        'CREATE TABLE item_structure_attributes (id INTEGER PRIMARY KEY, '
        'structure_id INTEGER, attribute_code TEXT)')
    conn.execute(
        'CREATE TABLE config_rules (id INTEGER PRIMARY KEY, structure_id INTEGER, '
        'rule_type TEXT)')
    conn.execute(
        'CREATE TABLE config_rule_terms (id INTEGER PRIMARY KEY, rule_id INTEGER, '
        'clause TEXT, target_line_id INTEGER, target_class_item_id INTEGER, '
        'attribute_code TEXT, operator TEXT)')
    return conn


def _seed(conn):
    """结构树：10(模型) → 选项类 11；12 / 13 / 15 在树外；14 是另一个模型。"""
    for iid, role in ((1, 'model'), (2, 'none'), (3, 'option_class'),
                      (4, 'option_class'), (5, 'model')):
        conn.execute('INSERT INTO items VALUES (?, ?)', (iid, role))
    for sid, item_id in ((10, 1), (11, 3), (12, 2), (13, 4),
                         (14, 5), (15, 2)):
        conn.execute('INSERT INTO item_structures VALUES (?, ?, ?)',
                     (sid, item_id, 'A'))
    for lid, sid, item_id in ((100, 10, 3), (101, 11, 2), (102, 12, 2),
                              (103, 13, 2), (104, 15, 2)):
        conn.execute('INSERT INTO item_structure_lines VALUES (?, ?, ?)',
                     (lid, sid, item_id))
    conn.execute('INSERT INTO item_structure_attributes VALUES (1, 10, ?)', ('color',))

    conn.execute("INSERT INTO config_rules VALUES (200, 10, 'require')")
    conn.execute("INSERT INTO config_rules VALUES (201, 10, 'condition')")
    conn.execute("INSERT INTO config_rules VALUES (202, 10, 'bind')")
    conn.execute("INSERT INTO config_rules VALUES (203, 10, 'require')")
    conn.execute("INSERT INTO config_rules VALUES (204, 14, 'require')")

    conn.execute(
        "INSERT INTO config_rule_terms VALUES (300, 200, 'then', 101, NULL, NULL, 'selected')")
    conn.execute(
        "INSERT INTO config_rule_terms VALUES (301, 202, 'if', 101, NULL, NULL, 'selected')")
    conn.execute(
        "INSERT INTO config_rule_terms VALUES (302, 204, 'then', 101, NULL, NULL, 'selected')")


# ─────────────────────────────────────────────────────────────────────────────
# schema 接线
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaWiring:
    def _load(self, name):
        with open(_SCHEMA_DIR / f'{name}.yaml', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_config_rule_header(self):
        obj = self._load('config_rule')
        assert obj['table_name'] == 'config_rules'
        assert obj['parent_object'] == 'item_structure'
        assert obj['hierarchy']['parent_field'] == 'structure_id'
        assert obj['deletion_policy']['mode'] == 'cascade'
        assert obj['ui_view_config']['skip_auto_menu'] is True
        children = obj['ui_view_config']['child_sections']
        assert [c['child_object'] for c in children] == ['config_rule_term']

    def test_config_rule_term(self):
        obj = self._load('config_rule_term')
        assert obj['table_name'] == 'config_rule_terms'
        assert obj['parent_object'] == 'config_rule'
        assert obj['hierarchy']['parent_field'] == 'rule_id'
        assert obj['deletion_policy']['mode'] == 'cascade'
        assert obj['ui_view_config']['skip_auto_menu'] is True
        unique_keys = [i['fields'] for i in obj['indexes'] if i.get('unique')]
        assert ['rule_id', 'seq'] in unique_keys

    def test_configuration_header(self):
        obj = self._load('configuration')
        assert obj['table_name'] == 'configurations'
        assert obj['ui_view_config']['skip_auto_menu'] is True
        children = obj['ui_view_config']['child_sections']
        assert [c['child_object'] for c in children] == [
            'configuration_value', 'configuration_component']
        # 同 hash 可复用多实例，故 (structure_id, config_hash) 不得唯一
        assert all(not i.get('unique') for i in obj['indexes'])
        relations = {r['source_field']: r['target'] for r in obj['relations']}
        assert relations['reused_from_id'] == 'configuration'

    def test_configuration_value(self):
        obj = self._load('configuration_value')
        assert obj['table_name'] == 'configuration_values'
        assert obj['parent_object'] == 'configuration'
        assert obj['hierarchy']['parent_field'] == 'configuration_id'
        unique_keys = [i['fields'] for i in obj['indexes'] if i.get('unique')]
        assert ['configuration_id', 'attribute_code', 'seq'] in unique_keys

    def test_configuration_component(self):
        obj = self._load('configuration_component')
        assert obj['table_name'] == 'configuration_components'
        assert obj['parent_object'] == 'configuration'
        assert obj['hierarchy']['parent_field'] == 'configuration_id'
        unique_keys = [i['fields'] for i in obj['indexes'] if i.get('unique')]
        assert ['configuration_id', 'component_key'] in unique_keys


# ─────────────────────────────────────────────────────────────────────────────
# 守卫
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigRuleGuard:
    def setup_method(self):
        self.conn = _new_db()
        _seed(self.conn)
        self.svc = ConfigRuleGuardService(_SqliteDS(self.conn))

    def _rule_err(self, data, exclude_id=None):
        with pytest.raises(ConfigRuleGuardError) as e:
            self.svc.validate_rule_write(data, exclude_id=exclude_id)
        return e.value.rule

    def _term_err(self, data, exclude_id=None):
        with pytest.raises(ConfigRuleGuardError) as e:
            self.svc.validate_term_write(data, exclude_id=exclude_id)
        return e.value.rule

    def _term(self, **kwargs):
        base = {'rule_id': 203, 'clause': 'if', 'target_type': 'structure_line',
                'target_line_id': 101, 'operator': 'selected'}
        base.update(kwargs)
        return base

    # ---- 规则头 ----

    def test_r9_requires_model(self):
        assert self._rule_err({'structure_id': 11}) == 'config_rule_requires_model'
        self.svc.validate_rule_write({'structure_id': 10})  # 模型放行

    def test_structure_locked_when_terms_exist(self):
        assert self._rule_err({'structure_id': 14}, exclude_id=200) \
            == 'config_rule_structure_locked'
        # 无条件的规则可改结构（规则 203 没有条件项）
        self.svc.validate_rule_write({'structure_id': 14}, exclude_id=203)

    # ---- R8 目标列 ----

    def test_target_exclusive(self):
        zero = self._term(target_line_id=None)
        assert self._term_err(zero) == 'config_rule_term_target_exclusive'
        two = self._term(attribute_code='color')
        assert self._term_err(two) == 'config_rule_term_target_exclusive'

    def test_target_mismatch(self):
        data = self._term(target_type='characteristic')
        assert self._term_err(data) == 'config_rule_term_target_mismatch'

    # ---- R16 作用域 ----

    def test_line_scope(self):
        self.svc.validate_term_write(self._term(target_line_id=101))  # 选项类子结构内
        self.svc.validate_term_write(self._term(target_line_id=100))  # 根结构内
        out = self._term(target_line_id=102)
        assert self._term_err(out) == 'config_rule_term_out_of_scope'

    def test_option_class_scope(self):
        inside = self._term(target_type='option_class', target_line_id=None,
                            target_class_item_id=3)
        self.svc.validate_term_write(inside)
        outside = self._term(target_type='option_class', target_line_id=None,
                             target_class_item_id=4)
        assert self._term_err(outside) == 'config_rule_term_out_of_scope'
        not_class = self._term(target_type='option_class', target_line_id=None,
                               target_class_item_id=2)
        assert self._term_err(not_class) == 'config_rule_term_not_option_class'

    def test_characteristic_scope(self):
        declared = self._term(target_type='characteristic', target_line_id=None,
                              attribute_code='color', operator='equals')
        self.svc.validate_term_write(declared)
        undeclared = self._term(target_type='characteristic', target_line_id=None,
                                attribute_code='size', operator='equals')
        assert self._term_err(undeclared) == 'config_rule_term_attribute_undeclared'

    # ---- §5.5 形状 ----

    def test_operator_target_mismatch(self):
        data = self._term(target_type='characteristic', target_line_id=None,
                          attribute_code='color', operator='qty_ge',
                          value_number=1)
        assert self._term_err(data) == 'config_rule_term_operator_target_mismatch'

    def test_unknown_operator(self):
        data = self._term(operator='foo')
        assert self._term_err(data) == 'config_rule_term_operator_invalid'

    def test_then_operator_by_rule_type(self):
        bad = self._term(rule_id=200, clause='then', operator='not_selected')
        assert self._term_err(bad) == 'config_rule_term_then_operator_invalid'
        cond_ok = self._term(rule_id=201, clause='then', operator='enabled')
        self.svc.validate_term_write(cond_ok)

    def test_enabled_only_in_condition_then(self):
        data = self._term(rule_id=201, clause='if', operator='enabled')
        assert self._term_err(data) == 'config_rule_term_operator_clause_mismatch'
        wrong_rule = self._term(rule_id=203, clause='then', operator='enabled')
        assert self._term_err(wrong_rule) == 'config_rule_term_then_operator_invalid'

    def test_value_shape(self):
        missing_upper = self._term(operator='qty_between', value_number=1)
        assert self._term_err(missing_upper) == 'config_rule_term_value_missing'
        reversed_range = self._term(operator='qty_between', value_number=5,
                                    value_number_to=1)
        assert self._term_err(reversed_range) == 'config_rule_term_value_range_invalid'
        in_without_list = self._term(target_type='characteristic',
                                     target_line_id=None, attribute_code='color',
                                     operator='in')
        assert self._term_err(in_without_list) == 'config_rule_term_value_missing'
        qty_ge_missing = self._term(operator='qty_ge')
        assert self._term_err(qty_ge_missing) == 'config_rule_term_value_missing'

    def test_then_at_most_one(self):
        data = self._term(rule_id=200, clause='then', operator='selected')
        assert self._term_err(data) == 'config_rule_term_then_multiple'

    def test_single_if_types(self):
        data = self._term(rule_id=202, clause='if', operator='selected')
        assert self._term_err(data) == 'config_rule_term_if_multiple'
        # require 允许多项 if（合取）
        self.svc.validate_term_write(self._term(rule_id=203, clause='if'))


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器
# ─────────────────────────────────────────────────────────────────────────────

class TestInterceptor:
    def _ctx(self, object_id, action, params=None, old=None, oid=None):
        return SimpleNamespace(
            meta_object=SimpleNamespace(id=object_id),
            action=action,
            params=params or {},
            old_data=old or {},
            object_id=oid,
            data_source=None,
        )

    def test_priority_and_scope(self):
        ic = ConfigRuleGuardInterceptor()
        assert ic.priority == 47
        assert ic.should_execute(self._ctx('config_rule', 'crud_create')) is True
        assert ic.should_execute(self._ctx('config_rule', 'crud_update')) is True
        assert ic.should_execute(self._ctx('config_rule', 'crud_delete')) is False
        assert ic.should_execute(self._ctx('config_rule_term', 'crud_create')) is True
        assert ic.should_execute(self._ctx('config_rule_term', 'crud_list')) is False
        assert ic.should_execute(self._ctx('item_structure', 'crud_create')) is False

    def test_error_mapping(self):
        conn = _new_db()
        _seed(conn)
        ic = ConfigRuleGuardInterceptor()
        ctx = self._ctx('config_rule', 'crud_create', params={'structure_id': 11})
        ctx.data_source = _SqliteDS(conn)
        with pytest.raises(ValidationFailedError) as e:
            ic.before_action(ctx)
        assert e.value.details[0]['rule'] == 'config_rule_requires_model'
        assert e.value.details[0]['field_name'] == 'structure_id'

    def test_update_merges_old_data(self):
        conn = _new_db()
        _seed(conn)
        ic = ConfigRuleGuardInterceptor()
        ctx = self._ctx('config_rule_term', 'crud_update',
                        params={'clause': 'if'},
                        old={'id': 303, 'rule_id': 203, 'target_type': 'structure_line',
                             'target_line_id': 101, 'operator': 'selected'},
                        oid=303)
        ctx.data_source = _SqliteDS(conn)
        ic.before_action(ctx)  # 合并后条件项完整 → 放行
