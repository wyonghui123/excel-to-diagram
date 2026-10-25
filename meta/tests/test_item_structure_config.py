# -*- coding: utf-8 -*-
"""配置编排测试（规则引擎 / config_hash / describe / validate / solve / freeze / 结果层守卫）

依据: docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md §5.5 / §6.4 / §7 / §8
      meta/services/item_structure_rule_engine.py
      meta/services/item_structure_config_service.py
      meta/services/configuration_guard_service.py
"""

import os

# 本文件只用 :memory: sqlite 造最小表，不碰真实库；按项目惯例解除 raw-SQL 守卫跳过。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.configuration_guard_interceptor import (
    ConfigurationGuardInterceptor,
)
from meta.services import item_structure_rule_engine as engine_module
from meta.services.configuration_guard_service import (
    ConfigurationGuardError,
    ConfigurationGuardService,
)
from meta.services.item_structure_config_service import (
    ItemStructureConfigError,
    ItemStructureConfigService,
)
from meta.services.item_structure_rule_engine import (
    ItemStructureRuleEngine,
    ItemStructureRuleError,
)
from meta.services.item_structure_select_service import ItemStructureSelectService

ROOT_STRUCTURE = 10
OPTION_STRUCTURE = 11
LINE_OPT = 100
LINE_PART_X = 101
LINE_PART_Y = 102
LINE_PART_Z = 103


# ─────────────────────────────────────────────────────────────────────────────
# 内存库
# ─────────────────────────────────────────────────────────────────────────────

class _SqliteDS:
    """最小数据源：query / insert / update / transaction。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def insert(self, table, data):
        columns = list(data.keys())
        sql = (f"INSERT INTO {table} ({', '.join(columns)}) "
               f"VALUES ({', '.join('?' for _ in columns)})")
        cur = self.conn.execute(sql, [data[col] for col in columns])
        return cur.lastrowid

    def update(self, table, row_id, data):
        assignments = ', '.join(f'{key} = ?' for key in data)
        self.conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            [*data.values(), row_id])

    @contextmanager
    def transaction(self):
        try:
            yield self
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()


def _new_db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(
        """
        CREATE TABLE items (id INTEGER PRIMARY KEY, code TEXT, name TEXT,
            structure_role TEXT, item_type TEXT, status TEXT, base_uom INTEGER,
            config_match_policy TEXT);
        CREATE TABLE item_structures (id INTEGER PRIMARY KEY, item_id INTEGER,
            usage TEXT, alternative_no INTEGER, revision TEXT, status TEXT,
            base_qty REAL, base_uom_code TEXT, min_select INTEGER,
            max_select INTEGER, valid_from TEXT, valid_to TEXT);
        CREATE TABLE item_structure_lines (id INTEGER PRIMARY KEY,
            structure_id INTEGER, line_no INTEGER, component_item_id INTEGER,
            qty_per REAL, fixed_qty REAL, optional_flag INTEGER,
            default_flag INTEGER, default_qty REAL, min_qty REAL, max_qty REAL,
            phantom_flag INTEGER, valid_from TEXT, valid_to TEXT);
        CREATE TABLE item_structure_attributes (id INTEGER PRIMARY KEY,
            structure_id INTEGER, attribute_code TEXT, required_flag INTEGER,
            default_value_text TEXT, seq INTEGER, ui_widget TEXT);
        CREATE TABLE attribute_definitions (id INTEGER PRIMARY KEY,
            tenant_id INTEGER, code TEXT, name TEXT, data_type TEXT,
            usage_class TEXT, value_domain_type TEXT, value_domain_ref TEXT,
            multi_value_flag INTEGER, uom_code TEXT, is_configurable INTEGER,
            status TEXT);
        CREATE TABLE enum_values (id INTEGER PRIMARY KEY, enum_type_id TEXT,
            code TEXT, is_active INTEGER);
        CREATE TABLE uoms (id INTEGER PRIMARY KEY, code TEXT);
        CREATE TABLE config_rules (id INTEGER PRIMARY KEY, structure_id INTEGER,
            code TEXT, rule_type TEXT, severity TEXT, priority INTEGER,
            message TEXT, status TEXT);
        CREATE TABLE config_rule_terms (id INTEGER PRIMARY KEY, rule_id INTEGER,
            seq INTEGER, clause TEXT, target_type TEXT, target_line_id INTEGER,
            target_class_item_id INTEGER, attribute_code TEXT, operator TEXT,
            value_text TEXT, value_number REAL, value_number_to REAL,
            value_list TEXT);
        CREATE TABLE configurations (id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_item_id INTEGER, structure_id INTEGER, status TEXT,
            config_hash TEXT, revision INTEGER, reused_from_id INTEGER,
            match_policy_used TEXT, source_level TEXT, context_json TEXT,
            validation_result_json TEXT, solved_at TEXT, frozen_at TEXT);
        CREATE TABLE configuration_values (id INTEGER PRIMARY KEY AUTOINCREMENT,
            configuration_id INTEGER, attribute_code TEXT, seq INTEGER,
            value_text TEXT, value_number REAL, value_boolean INTEGER,
            source TEXT, source_rule_id INTEGER);
        CREATE TABLE configuration_components (id INTEGER PRIMARY KEY AUTOINCREMENT,
            configuration_id INTEGER, component_key TEXT, structure_line_id INTEGER,
            component_item_id INTEGER, qty REAL, uom_code TEXT,
            parent_component_key TEXT, selection_source TEXT, source_rule_id INTEGER,
            substitute_for_key TEXT, child_configuration_id INTEGER, seq INTEGER);
        """
    )
    return conn


def _seed_model(conn):
    """模型 MODEL-A：根结构 10 → 必选选项类行 100 → 子结构 11 的 101/102/103。"""
    conn.execute("INSERT INTO uoms VALUES (1, 'EA')")
    conn.executemany(
        "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 'MODEL-A', '模型A', 'model', 'goods', 'active', 1, 'no'),
            (2, 'OPT-1', '选项类', 'option_class', 'goods', 'active', 1, 'no'),
            (3, 'PART-X', '部件X', 'none', 'goods', 'active', 1, 'no'),
            (4, 'PART-Y', '部件Y', 'none', 'goods', 'active', 1, 'no'),
            (5, 'PART-Z', '部件Z', 'none', 'goods', 'active', 1, 'no'),
        ],
    )
    conn.executemany(
        "INSERT INTO item_structures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (ROOT_STRUCTURE, 1, 'production', 1, 'A', 'active', 1, 'EA', None,
             None, '2026-01-01', None),
            (OPTION_STRUCTURE, 2, 'production', 1, 'A', 'active', 1, 'EA', None,
             None, '2026-01-01', None),
        ],
    )
    conn.executemany(
        "INSERT INTO item_structure_lines VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (LINE_OPT, ROOT_STRUCTURE, 1, 2, 1, None, 0, 0, None, None, None, 0,
             '2026-01-01', None),
            (LINE_PART_X, OPTION_STRUCTURE, 1, 3, 1, None, 1, 0, None, None, None,
             0, '2026-01-01', None),
            (LINE_PART_Y, OPTION_STRUCTURE, 2, 4, 1, None, 1, 0, None, None, None,
             0, '2026-01-01', None),
            (LINE_PART_Z, OPTION_STRUCTURE, 3, 5, 1, None, 1, 0, None, None, None,
             0, '2026-01-01', None),
        ],
    )
    conn.executemany(
        "INSERT INTO item_structure_attributes VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, ROOT_STRUCTURE, 'color', 0, None, 1, None),
            (2, ROOT_STRUCTURE, 'finish', 0, None, 2, None),
            (3, ROOT_STRUCTURE, 'length', 0, None, 3, None),
            (4, ROOT_STRUCTURE, 'tags', 0, None, 4, None),
        ],
    )
    conn.executemany(
        "INSERT INTO attribute_definitions VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 0, 'color', '颜色', 'string', 'config', 'none', None, 0, None, 1,
             'active'),
            (2, 0, 'finish', '表面处理', 'string', 'config', 'list', 'FINISH', 0,
             None, 1, 'active'),
            (3, 0, 'length', '长度', 'number', 'config', 'range', '[100, 200]', 0,
             None, 1, 'active'),
            (4, 0, 'tags', '标签', 'string', 'config', 'none', None, 1, None, 1,
             'active'),
        ],
    )
    conn.executemany(
        "INSERT INTO enum_values VALUES (?, ?, ?, ?)",
        [(1, 'FINISH', 'gloss', 1), (2, 'FINISH', 'matte', 1)],
    )


def _add_rule(conn, rule_id, rule_type, priority=100, severity='blocking',
              message=None, structure_id=ROOT_STRUCTURE, status='active'):
    conn.execute(
        "INSERT INTO config_rules VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (rule_id, structure_id, f'R{rule_id}', rule_type, severity, priority,
         message, status),
    )


def _add_term(conn, term_id, rule_id, seq, clause, target_type='structure_line',
              target_line_id=None, target_class_item_id=None,
              attribute_code=None, operator='selected', value_text=None,
              value_number=None, value_number_to=None, value_list=None):
    conn.execute(
        "INSERT INTO config_rule_terms VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (term_id, rule_id, seq, clause, target_type, target_line_id,
         target_class_item_id, attribute_code, operator, value_text,
         value_number, value_number_to, value_list),
    )


def _add_head(conn, head_id, status='draft', config_hash=None):
    conn.execute(
        "INSERT INTO configurations (id, model_item_id, structure_id, status, "
        "config_hash, revision, reused_from_id, match_policy_used, source_level, "
        "context_json, validation_result_json, solved_at, frozen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (head_id, 1, ROOT_STRUCTURE, status, config_hash, 1, None, 'no', 'L2',
         None, None,
         '2026-10-25T00:00:00' if status in ('solved', 'frozen', 'superseded')
         else None, None),
    )


@pytest.fixture()
def env():
    conn = _new_db()
    _seed_model(conn)
    return SimpleNamespace(conn=conn, ds=_SqliteDS(conn))


# ─────────────────────────────────────────────────────────────────────────────
# 规则引擎
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleEngine:
    def test_require_forward_propagation(self, env):
        _add_rule(env.conn, 500, 'require')
        _add_term(env.conn, 1, 500, 1, 'if', target_line_id=LINE_PART_X)
        _add_term(env.conn, 2, 500, 2, 'then', target_line_id=LINE_PART_Y)

        result = ItemStructureRuleEngine(env.ds).evaluate(
            ROOT_STRUCTURE, selections=[LINE_PART_X])
        assert result['selections'][LINE_PART_X] is True
        assert result['selections'][LINE_PART_Y] is True
        assert result['origins'][LINE_PART_Y] == 500

    def test_exclude_turns_target_off(self, env):
        _add_rule(env.conn, 501, 'exclude')
        _add_term(env.conn, 1, 501, 1, 'if', target_line_id=LINE_PART_X)
        _add_term(env.conn, 2, 501, 2, 'then', target_line_id=LINE_PART_Y)

        result = ItemStructureRuleEngine(env.ds).evaluate(
            ROOT_STRUCTURE, selections=[LINE_PART_X])
        assert not result['selections'].get(LINE_PART_Y, False)

    def test_negate_without_condition(self, env):
        _add_rule(env.conn, 502, 'negate')
        _add_term(env.conn, 1, 502, 1, 'then', target_line_id=LINE_PART_Y)

        result = ItemStructureRuleEngine(env.ds).evaluate(ROOT_STRUCTURE)
        assert not result['selections'].get(LINE_PART_Y, False)

    def test_bind_follows_condition(self, env):
        _add_rule(env.conn, 503, 'bind')
        _add_term(env.conn, 1, 503, 1, 'if', target_line_id=LINE_PART_X)
        _add_term(env.conn, 2, 503, 2, 'then', target_line_id=LINE_PART_Y)

        engine = ItemStructureRuleEngine(env.ds)
        assert engine.evaluate(
            ROOT_STRUCTURE, selections=[LINE_PART_X])['selections'][LINE_PART_Y] is True
        assert LINE_PART_Y not in engine.evaluate(ROOT_STRUCTURE)['selections']

    def test_condition_disables_optional_line(self, env):
        _add_rule(env.conn, 504, 'condition')
        _add_term(env.conn, 1, 504, 1, 'if', target_line_id=LINE_PART_X)
        _add_term(env.conn, 2, 504, 2, 'then', target_line_id=LINE_PART_Y,
                  operator='disabled')

        result = ItemStructureRuleEngine(env.ds).evaluate(
            ROOT_STRUCTURE, selections=[LINE_PART_X])
        assert result['selections'][LINE_PART_Y] is False

    def test_condition_conflicts_with_user_selection(self, env):
        _add_rule(env.conn, 504, 'condition')
        _add_term(env.conn, 1, 504, 1, 'if', target_line_id=LINE_PART_X)
        _add_term(env.conn, 2, 504, 2, 'then', target_line_id=LINE_PART_Y,
                  operator='disabled')

        with pytest.raises(ItemStructureRuleError) as info:
            ItemStructureRuleEngine(env.ds).evaluate(
                ROOT_STRUCTURE, selections=[LINE_PART_X, LINE_PART_Y])
        assert info.value.rule == 'config_conflict'
        assert info.value.conflicts[0]['target']['id'] == LINE_PART_Y

    def test_default_rule_selects_line(self, env):
        _add_rule(env.conn, 505, 'default')
        _add_term(env.conn, 1, 505, 1, 'then', target_line_id=LINE_PART_X)

        result = ItemStructureRuleEngine(env.ds).evaluate(ROOT_STRUCTURE)
        assert result['selections'][LINE_PART_X] is True
        assert result['origins'][LINE_PART_X] == 505

    def test_default_rule_fills_characteristic(self, env):
        _add_rule(env.conn, 506, 'default')
        _add_term(env.conn, 1, 506, 1, 'then', target_type='characteristic',
                  attribute_code='color', operator='equals', value_text='Red')

        result = ItemStructureRuleEngine(env.ds).evaluate(ROOT_STRUCTURE)
        cell = {row['attribute_code']: row for row in result['values']}['color']
        assert cell['value_text'] == 'Red'
        assert cell['source'] == 'rule'
        assert cell['source_rule_id'] == 506

    def test_characteristic_condition_case_insensitive(self, env):
        _add_rule(env.conn, 507, 'require')
        _add_term(env.conn, 1, 507, 1, 'if', target_type='characteristic',
                  attribute_code='color', operator='equals', value_text='red')
        _add_term(env.conn, 2, 507, 2, 'then', target_line_id=LINE_PART_Y)

        result = ItemStructureRuleEngine(env.ds).evaluate(
            ROOT_STRUCTURE, attribute_values={'color': 'Red'})
        assert result['selections'][LINE_PART_Y] is True

    def test_warning_severity_keeps_first_result(self, env):
        _add_rule(env.conn, 508, 'require', priority=10)
        _add_term(env.conn, 1, 508, 1, 'then', target_line_id=LINE_PART_Y)
        _add_rule(env.conn, 509, 'exclude', priority=20, severity='warning',
                  message='测试告警')
        _add_term(env.conn, 2, 509, 1, 'then', target_line_id=LINE_PART_Y)

        result = ItemStructureRuleEngine(env.ds).evaluate(ROOT_STRUCTURE)
        assert result['selections'][LINE_PART_Y] is True
        assert len(result['warnings']) == 1
        assert result['warnings'][0]['rule'] == 'config_rule_warning'

    def test_blocking_conflict_reports_minimal_set(self, env):
        _add_rule(env.conn, 510, 'require', priority=10, message='必须先选')
        _add_term(env.conn, 1, 510, 1, 'then', target_line_id=LINE_PART_Y)
        _add_rule(env.conn, 511, 'exclude', priority=20, message='必须反选')
        _add_term(env.conn, 2, 511, 1, 'then', target_line_id=LINE_PART_Y)

        with pytest.raises(ItemStructureRuleError) as info:
            ItemStructureRuleEngine(env.ds).evaluate(ROOT_STRUCTURE)
        assert info.value.rule == 'config_conflict'
        conflict = info.value.conflicts[0]
        assert conflict['target']['id'] == LINE_PART_Y
        rule_ids = [evidence.get('rule_id') for evidence in conflict['rules']]
        assert 511 in rule_ids
        assert 510 in rule_ids

    def test_propagation_timeout(self, env, monkeypatch):
        monkeypatch.setattr(engine_module, 'MAX_ROUNDS', 1)
        _add_rule(env.conn, 512, 'require', priority=10)
        _add_term(env.conn, 1, 512, 1, 'if', target_line_id=LINE_PART_X)
        _add_term(env.conn, 2, 512, 2, 'then', target_line_id=LINE_PART_Y)
        _add_rule(env.conn, 513, 'require', priority=10)
        _add_term(env.conn, 3, 513, 1, 'if', target_line_id=LINE_PART_Y)
        _add_term(env.conn, 4, 513, 2, 'then', target_line_id=LINE_PART_Z)

        with pytest.raises(ItemStructureRuleError) as info:
            ItemStructureRuleEngine(env.ds).evaluate(
                ROOT_STRUCTURE, selections=[LINE_PART_X])
        assert info.value.rule == 'config_timeout'

    def test_inactive_rule_is_ignored(self, env):
        _add_rule(env.conn, 514, 'require', status='inactive')
        _add_term(env.conn, 1, 514, 1, 'then', target_line_id=LINE_PART_Y)

        result = ItemStructureRuleEngine(env.ds).evaluate(ROOT_STRUCTURE)
        assert LINE_PART_Y not in result['selections']


# ─────────────────────────────────────────────────────────────────────────────
# config_hash 规范化
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigHash:
    def _service(self, env):
        return ItemStructureConfigService(env.ds)

    @staticmethod
    def _component(key='L0001.L0001', item_code='PART-X', qty=1.5):
        return {'component_key': key, 'component_item_code': item_code,
                'qty': qty}

    def test_number_normalization(self, env):
        service = self._service(env)
        first = service._compute_hash(
            'MODEL-A', 'A',
            [{'attribute_code': 'length', 'value_number': 1.5}],
            [self._component(qty=1.5)])
        second = service._compute_hash(
            'MODEL-A', 'A',
            [{'attribute_code': 'length', 'value_number': 1.50}],
            [self._component(qty=1.50)])
        assert first == second

    def test_code_is_case_insensitive(self, env):
        service = self._service(env)
        first = service._compute_hash(
            'model-a', 'A',
            [{'attribute_code': 'Color', 'value_text': 'Red'}],
            [self._component(item_code='part-x')])
        second = service._compute_hash(
            'MODEL-A', 'A',
            [{'attribute_code': 'color', 'value_text': 'Red'}],
            [self._component(item_code='PART-X')])
        assert first == second

    def test_multi_value_order_does_not_matter(self, env):
        service = self._service(env)
        first = service._compute_hash(
            'MODEL-A', 'A',
            [{'attribute_code': 'tags', 'value_text': 'b'},
             {'attribute_code': 'tags', 'value_text': 'a'}], [])
        second = service._compute_hash(
            'MODEL-A', 'A',
            [{'attribute_code': 'tags', 'value_text': 'a'},
             {'attribute_code': 'tags', 'value_text': 'b'}], [])
        assert first == second

    def test_blank_value_is_not_joined(self, env):
        service = self._service(env)
        with_blank = service._compute_hash(
            'MODEL-A', 'A',
            [{'attribute_code': 'color', 'value_text': ''}], [])
        without = service._compute_hash('MODEL-A', 'A', [], [])
        assert with_blank == without

    def test_component_order_does_not_matter(self, env):
        service = self._service(env)
        first = service._compute_hash(
            'MODEL-A', 'A', [],
            [self._component('L0001.L0002', 'PART-Y', 1),
             self._component('L0001.L0001', 'PART-X', 1)])
        second = service._compute_hash(
            'MODEL-A', 'A', [],
            [self._component('L0001.L0001', 'PART-X', 1),
             self._component('L0001.L0002', 'PART-Y', 1)])
        assert first == second

    def test_model_version_changes_hash(self, env):
        service = self._service(env)
        assert service._compute_hash('MODEL-A', 'A', [], []) \
            != service._compute_hash('MODEL-A', 'B', [], [])


# ─────────────────────────────────────────────────────────────────────────────
# describe / validate
# ─────────────────────────────────────────────────────────────────────────────

class TestDescribeAndValidate:
    def _service(self, env):
        return ItemStructureConfigService(env.ds)

    def test_describe_returns_version_and_characteristics(self, env):
        described = self._service(env).describe(ROOT_STRUCTURE)
        assert described['item_id'] == 1
        assert described['model_code'] == 'MODEL-A'
        assert described['revision'] == 'A'
        assert described['is_model'] is True
        assert described['base_uom_code'] == 'EA'
        assert [row['attribute_code'] for row in described['characteristics']] == [
            'color', 'finish', 'length', 'tags']
        assert len(described['lines']) == 1
        assert described['lines'][0]['structure_role'] == 'option_class'

    def test_describe_missing_structure(self, env):
        with pytest.raises(ItemStructureConfigError) as info:
            self._service(env).describe(999)
        assert info.value.code == 'CONFIG_VERSION_MISMATCH'

    def test_validate_returns_components(self, env):
        result = self._service(env).validate(
            ROOT_STRUCTURE, selections=[LINE_PART_X])
        assert result['valid'] is True
        keys = [row['component_key'] for row in result['components']]
        assert keys == ['L0001.L0001']

    def test_model_version_mismatch(self, env):
        result = self._service(env).validate(ROOT_STRUCTURE, model_version='B')
        assert result['valid'] is False
        assert result['error_code'] == 'CONFIG_VERSION_MISMATCH'
        assert result['rule'] == 'configuration_model_version_mismatch'

    def test_undeclared_attribute(self, env):
        result = self._service(env).validate(
            ROOT_STRUCTURE, attribute_values={'unknown': 'x'})
        assert result['error_code'] == 'CONFIG_INVALID_VALUE'
        assert result['rule'] == 'configuration_value_undeclared'

    def test_numeric_type_invalid(self, env):
        result = self._service(env).validate(
            ROOT_STRUCTURE, attribute_values={'length': 'abc'})
        assert result['error_code'] == 'CONFIG_INVALID_VALUE'
        assert result['rule'] == 'configuration_value_type_invalid'

    def test_enum_domain_invalid(self, env):
        result = self._service(env).validate(
            ROOT_STRUCTURE, attribute_values={'finish': 'satin'})
        assert result['error_code'] == 'CONFIG_INVALID_VALUE'
        assert result['rule'] == 'configuration_value_domain_invalid'

    def test_enum_domain_accepts_case_insensitive(self, env):
        result = self._service(env).validate(
            ROOT_STRUCTURE, attribute_values={'finish': 'Gloss'})
        assert result['valid'] is True
        row = result['values'][0]
        assert row['attribute_code'] == 'finish'
        assert row['value_text'] == 'Gloss'

    def test_range_domain_invalid(self, env):
        result = self._service(env).validate(
            ROOT_STRUCTURE, attribute_values={'length': 250})
        assert result['error_code'] == 'CONFIG_INVALID_VALUE'
        assert result['rule'] == 'configuration_value_domain_invalid'

    def test_unknown_selection_line(self, env):
        result = self._service(env).validate(ROOT_STRUCTURE, selections=[999])
        assert result['error_code'] == 'CONFIG_INVALID_VALUE'
        assert result['rule'] == 'item_structure_select_line_unknown'

    def test_timeout_maps_to_config_timeout(self, env, monkeypatch):
        monkeypatch.setattr(engine_module, 'MAX_ROUNDS', 1)
        _add_rule(env.conn, 520, 'require', priority=10)
        _add_term(env.conn, 1, 520, 1, 'if', target_line_id=LINE_PART_X)
        _add_term(env.conn, 2, 520, 2, 'then', target_line_id=LINE_PART_Y)
        _add_rule(env.conn, 521, 'require', priority=10)
        _add_term(env.conn, 3, 521, 1, 'if', target_line_id=LINE_PART_Y)
        _add_term(env.conn, 4, 521, 2, 'then', target_line_id=LINE_PART_Z)

        result = self._service(env).validate(
            ROOT_STRUCTURE, selections=[LINE_PART_X])
        assert result['error_code'] == 'CONFIG_TIMEOUT'
        assert result['rule'] == 'config_timeout'

    def test_multi_value_splits_rows(self, env):
        result = self._service(env).validate(
            ROOT_STRUCTURE, attribute_values={'tags': ['b', 'a']})
        assert result['valid'] is True
        seqs = [(row['attribute_code'], row['seq']) for row in result['values']]
        assert seqs == [('tags', 1), ('tags', 2)]


# ─────────────────────────────────────────────────────────────────────────────
# solve / freeze / read
# ─────────────────────────────────────────────────────────────────────────────

class TestSolveFreezeRead:
    def _service(self, env):
        return ItemStructureConfigService(env.ds)

    def _seed_rule(self, env):
        _add_rule(env.conn, 500, 'require')
        _add_term(env.conn, 1, 500, 1, 'if', target_line_id=LINE_PART_X)
        _add_term(env.conn, 2, 500, 2, 'then', target_line_id=LINE_PART_Y)

    def test_solve_persists_three_tables(self, env):
        self._seed_rule(env)
        solved = self._service(env).solve(
            ROOT_STRUCTURE, selections=[LINE_PART_X],
            attribute_values={'color': 'Red'})

        head = env.ds.query(
            "SELECT * FROM configurations WHERE id = ?", [solved['configuration_id']])[0]
        assert head['status'] == 'solved'
        assert head['config_hash'] == solved['config_hash']
        assert head['match_policy_used'] == 'no'
        assert head['source_level'] == 'L2'

        values = env.ds.query(
            "SELECT * FROM configuration_values WHERE configuration_id = ?",
            [solved['configuration_id']])
        assert len(values) == 1
        assert values[0]['attribute_code'] == 'color'
        assert values[0]['value_text'] == 'Red'
        assert values[0]['source'] == 'user'

        components = env.ds.query(
            "SELECT * FROM configuration_components WHERE configuration_id = ? "
            "ORDER BY component_key", [solved['configuration_id']])
        assert [row['component_key'] for row in components] == [
            'L0001.L0001', 'L0001.L0002']
        assert [row['selection_source'] for row in components] == ['user', 'rule']
        assert components[1]['source_rule_id'] == 500
        assert all(row['uom_code'] == 'EA' for row in components)
        assert all(row['qty'] == 1 for row in components)

    def test_component_keys_match_select_service(self, env):
        self._seed_rule(env)
        solved = self._service(env).solve(
            ROOT_STRUCTURE, selections=[LINE_PART_X])
        selected = ItemStructureSelectService(env.ds).select(
            ROOT_STRUCTURE, [LINE_PART_X, LINE_PART_Y])
        assert [row['component_key'] for row in solved['components']] == [
            row['component_key'] for row in selected['components']]

    def test_verify_hash_matches(self, env):
        service = self._service(env)
        solved = service.solve(ROOT_STRUCTURE, selections=[LINE_PART_X])
        check = service.verify_hash(solved['configuration_id'])
        assert check['match'] is True

    def test_freeze_is_idempotent_and_folds_status(self, env):
        service = self._service(env)
        solved = service.solve(ROOT_STRUCTURE, selections=[LINE_PART_X])
        frozen = service.freeze(solved['configuration_id'])
        assert frozen['status'] == 'frozen'
        assert frozen['status_out'] == 'solved'
        again = service.freeze(solved['configuration_id'])
        assert again['status'] == 'frozen'

    def test_freeze_rejects_tampered_content(self, env):
        service = self._service(env)
        solved = service.solve(ROOT_STRUCTURE, selections=[LINE_PART_X])
        component_id = solved['components'][0]['component_key']
        row = env.ds.query(
            "SELECT id FROM configuration_components WHERE component_key = ?",
            [component_id])[0]
        env.ds.update('configuration_components', row['id'], {'qty': 99})

        with pytest.raises(ItemStructureConfigError) as info:
            service.freeze(solved['configuration_id'])
        assert info.value.code == 'CONFIG_INVALID_VALUE'
        assert info.value.rule == 'configuration_hash_mismatch'

    def test_read_returns_folded_status(self, env):
        service = self._service(env)
        solved = service.solve(ROOT_STRUCTURE, selections=[LINE_PART_X])
        read = service.read(solved['configuration_id'])
        assert read['model_code'] == 'MODEL-A'
        assert read['model_version'] == 'A'
        assert read['status_out'] == 'solved'
        assert len(read['components']) == 1

    def test_record_invalid_keeps_trace(self, env):
        service = self._service(env)
        with pytest.raises(ItemStructureConfigError) as info:
            service.solve(ROOT_STRUCTURE, attribute_values={'length': 'abc'},
                          record_invalid=True)
        configuration_id = info.value.configuration_id
        assert configuration_id is not None

        head = env.ds.query(
            "SELECT * FROM configurations WHERE id = ?", [configuration_id])[0]
        assert head['status'] == 'invalid'
        assert head['config_hash'] is None
        payload = json.loads(head['validation_result_json'])
        assert payload['error_code'] == 'CONFIG_INVALID_VALUE'
        assert service.read(configuration_id)['status_out'] == 'invalid'

    def test_invalid_without_record_leaves_no_row(self, env):
        service = self._service(env)
        with pytest.raises(ItemStructureConfigError):
            service.solve(ROOT_STRUCTURE, attribute_values={'length': 'abc'})
        assert env.ds.query("SELECT id FROM configurations") == []


# ─────────────────────────────────────────────────────────────────────────────
# 结果层守卫
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigurationGuard:
    def _service(self, env):
        return ConfigurationGuardService(env.ds)

    def test_create_rejects_frozen(self, env):
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_head_write({'status': 'frozen'})
        assert info.value.rule == 'configuration_create_status_invalid'

    def test_create_solved_requires_hash(self, env):
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_head_write({'status': 'solved'})
        assert info.value.rule == 'configuration_hash_required'

    def test_create_draft_passes(self, env):
        self._service(env).validate_head_write({'status': 'draft'})

    def test_unknown_status(self, env):
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_head_write({'status': 'bogus'})
        assert info.value.rule == 'configuration_status_invalid'

    def test_illegal_transition(self, env):
        _add_head(env.conn, 1, status='draft')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_head_write(
                {'status': 'frozen'}, exclude_id=1)
        assert info.value.rule == 'configuration_status_transition_invalid'

    def test_solved_hash_is_immutable(self, env):
        _add_head(env.conn, 1, status='solved', config_hash='abc')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_head_write(
                {'status': 'solved', 'config_hash': 'zzz'}, exclude_id=1)
        assert info.value.rule == 'configuration_hash_immutable'

    def test_frozen_only_allows_status(self, env):
        _add_head(env.conn, 1, status='frozen', config_hash='abc')
        service = self._service(env)
        service.validate_head_write({'status': 'superseded'}, exclude_id=1)
        with pytest.raises(ConfigurationGuardError) as info:
            service.validate_head_write(
                {'status': 'superseded', 'context_json': '{}'}, exclude_id=1)
        assert info.value.rule == 'configuration_frozen_locked'

    def test_superseded_is_fully_locked(self, env):
        _add_head(env.conn, 1, status='superseded', config_hash='abc')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_head_write(
                {'status': 'superseded'}, exclude_id=1)
        assert info.value.rule == 'configuration_locked'

    def test_delete_only_draft(self, env):
        _add_head(env.conn, 1, status='draft')
        _add_head(env.conn, 2, status='solved', config_hash='abc')
        service = self._service(env)
        service.validate_head_delete(1)
        with pytest.raises(ConfigurationGuardError) as info:
            service.validate_head_delete(2)
        assert info.value.rule == 'configuration_delete_locked'

    def test_value_requires_draft_parent(self, env):
        _add_head(env.conn, 1, status='solved', config_hash='abc')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_value_write({
                'configuration_id': 1, 'attribute_code': 'color',
                'value_text': 'Red'})
        assert info.value.rule == 'configuration_value_parent_not_draft'

    def test_value_rule_source_requires_rule_id(self, env):
        _add_head(env.conn, 1, status='draft')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_value_write({
                'configuration_id': 1, 'attribute_code': 'color',
                'value_text': 'Red', 'source': 'rule'})
        assert info.value.rule == 'configuration_value_rule_required'

    def test_value_column_must_be_exclusive(self, env):
        _add_head(env.conn, 1, status='draft')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_value_write({
                'configuration_id': 1, 'attribute_code': 'color',
                'value_text': 'Red', 'value_number': 1})
        assert info.value.rule == 'configuration_value_column_exclusive'

    def test_value_valid_row_passes(self, env):
        _add_head(env.conn, 1, status='draft')
        self._service(env).validate_value_write({
            'configuration_id': 1, 'attribute_code': 'color',
            'value_text': 'Red', 'source': 'user'})

    def test_value_delete_locked_after_solve(self, env):
        _add_head(env.conn, 1, status='solved', config_hash='abc')
        env.conn.execute(
            "INSERT INTO configuration_values (id, configuration_id, "
            "attribute_code, seq, value_text, source) VALUES (1, 1, 'color', 1, "
            "'Red', 'user')")
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_value_delete(1)
        assert info.value.rule == 'configuration_value_parent_not_draft'

    def test_component_key_shape(self, env):
        _add_head(env.conn, 1, status='draft')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_component_write({
                'configuration_id': 1, 'component_key': 'X1',
                'structure_line_id': 101, 'component_item_id': 3,
                'uom_code': 'EA', 'qty': 1})
        assert info.value.rule == 'configuration_component_key_invalid'

    def test_component_required_fields(self, env):
        _add_head(env.conn, 1, status='draft')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_component_write({
                'configuration_id': 1, 'component_key': 'L0001',
                'structure_line_id': 101, 'component_item_id': 3,
                'qty': 1})
        assert info.value.rule == 'configuration_component_field_required'
        assert info.value.field_name == 'uom_code'

    def test_component_qty_not_negative(self, env):
        _add_head(env.conn, 1, status='draft')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_component_write({
                'configuration_id': 1, 'component_key': 'L0001',
                'structure_line_id': 101, 'component_item_id': 3,
                'uom_code': 'EA', 'qty': -1})
        assert info.value.rule == 'configuration_component_qty_invalid'

    def test_component_rule_source_requires_rule_id(self, env):
        _add_head(env.conn, 1, status='draft')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_component_write({
                'configuration_id': 1, 'component_key': 'L0001',
                'structure_line_id': 101, 'component_item_id': 3,
                'uom_code': 'EA', 'qty': 1, 'selection_source': 'rule'})
        assert info.value.rule == 'configuration_component_rule_required'

    def test_component_parent_key_must_exist(self, env):
        _add_head(env.conn, 1, status='draft')
        with pytest.raises(ConfigurationGuardError) as info:
            self._service(env).validate_component_write({
                'configuration_id': 1, 'component_key': 'L0009.L0001',
                'parent_component_key': 'L0009',
                'structure_line_id': 101, 'component_item_id': 3,
                'uom_code': 'EA', 'qty': 1})
        assert info.value.rule == 'configuration_component_parent_missing'

    def test_component_parent_key_accepted_when_present(self, env):
        _add_head(env.conn, 1, status='draft')
        env.conn.execute(
            "INSERT INTO configuration_components (id, configuration_id, "
            "component_key, structure_line_id, component_item_id, qty, uom_code, "
            "selection_source, seq) VALUES (1, 1, 'L0001', 100, 2, 1, 'EA', "
            "'auto', 1)")
        self._service(env).validate_component_write({
            'configuration_id': 1, 'component_key': 'L0001.L0001',
            'parent_component_key': 'L0001', 'structure_line_id': 101,
            'component_item_id': 3, 'uom_code': 'EA', 'qty': 1})

    def test_nested_component_key_shape(self, env):
        _add_head(env.conn, 1, status='draft')
        self._service(env).validate_component_write({
            'configuration_id': 1, 'component_key': 'L0001.L0002.L0003',
            'structure_line_id': 101, 'component_item_id': 3,
            'uom_code': 'EA', 'qty': 0, 'selection_source': 'auto'})


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器
# ─────────────────────────────────────────────────────────────────────────────

def _context(ds, object_id, action, params=None, old_data=None, row_id=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        params=params or {},
        old_data=old_data or {},
        object_id=row_id,
        data_source=ds,
    )


class TestConfigurationInterceptor:
    def test_priority_and_scope(self):
        interceptor = ConfigurationGuardInterceptor()
        assert interceptor.priority == 48
        ds = _SqliteDS(_new_db())
        assert interceptor.should_execute(
            _context(ds, 'configuration', 'crud_create')) is True
        assert interceptor.should_execute(
            _context(ds, 'configuration_component', 'crud_delete')) is True
        assert interceptor.should_execute(
            _context(ds, 'items', 'crud_create')) is False
        assert interceptor.should_execute(
            _context(ds, 'configuration', 'crud_list')) is False

    def test_hash_change_is_rejected(self, env):
        _add_head(env.conn, 1, status='solved', config_hash='abc')
        interceptor = ConfigurationGuardInterceptor()
        context = _context(
            env.ds, 'configuration', 'crud_update',
            params={'config_hash': 'zzz'},
            old_data={'id': 1, 'status': 'solved', 'config_hash': 'abc'},
            row_id=1)

        with pytest.raises(ValidationFailedError) as info:
            interceptor.before_action(context)
        assert info.value.details[0]['rule'] == 'configuration_hash_immutable'

    def test_delete_solved_is_rejected(self, env):
        _add_head(env.conn, 1, status='solved', config_hash='abc')
        interceptor = ConfigurationGuardInterceptor()
        context = _context(env.ds, 'configuration', 'crud_delete', row_id=1)

        with pytest.raises(ValidationFailedError) as info:
            interceptor.before_action(context)
        assert info.value.details[0]['rule'] == 'configuration_delete_locked'
