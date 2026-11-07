# -*- coding: utf-8 -*-
"""规则中心 P1 只读层测试（spec v1.6 FR-014 / FR-015，IF-006 / IF-007）。

覆盖：
  1. 视图元数据（rule_center_view.yaml）可加载、8 页签、来源/动作封闭枚举校验；
  2. 目录聚合返回统一契约（items/total/sources/not_instrumented）；
  3. 可配置规则只来自控制参数与行类型（spec §9.6.1）；
  4. 未知 rule_key 详情返回 None（API 层映射 404 RULE_NOT_FOUND）；
  5. 非法视图元数据被拒绝（防前端壳渲染出脏结构）；
  6. rule-trace 路由与 bo_v2 的 `/<object_type>/<path:obj_id>` 不冲突。
"""

import pytest
from flask import Flask

from meta.api.bo_api import bo_bp
from meta.api.rule_center_api import rule_trace_bp
from meta.services.rule_catalog_service import (
    NOT_INSTRUMENTED,
    SOURCES,
    RuleCatalogError,
    RuleCatalogService,
)


@pytest.fixture(scope='module')
def service():
    return RuleCatalogService()


# ---------------------------------------------------------------------------
# 视图元数据
# ---------------------------------------------------------------------------

def test_view_config_has_expected_tabs(service):
    config = service.get_view_config()

    assert config.get('version') == 2
    assert config.get('title')

    tabs = config['tabs']
    tab_ids = [tab['id'] for tab in tabs]
    assert tab_ids == [
        'all', 'control_parameter', 'line_type', 'doc_flow',
        'approval', 'validation', 'simulate', 'health', 'trace',
    ]
    assert len(set(tab_ids)) == len(tab_ids)

    for tab in tabs:
        for source in tab.get('sources') or []:
            assert source in SOURCES


def test_view_config_labels_cover_columns(service):
    config = service.get_view_config()
    column_labels = config.get('column_labels') or {}
    filter_labels = config.get('filter_labels') or {}

    assert column_labels, '规则中心必须声明列显示名映射'
    assert filter_labels, '规则中心必须声明筛选显示名映射'

    for tab in config['tabs']:
        for column in tab.get('columns') or []:
            assert column in column_labels, f'列 {column} 缺少中文显示名'


def test_view_config_rejects_unknown_source(tmp_path):
    bad = tmp_path / 'bad_view.yaml'
    bad.write_text(
        'version: 1\ntabs:\n  - id: x\n    sources: [no_such_source]\n',
        encoding='utf-8',
    )

    with pytest.raises(RuleCatalogError):
        RuleCatalogService(view_path=str(bad)).get_view_config()


# ---------------------------------------------------------------------------
# 目录聚合
# ---------------------------------------------------------------------------

def test_list_rules_contract(service):
    result = service.list_rules(limit=5)

    assert set(result) >= {
        'items', 'total', 'limit', 'offset', 'sources', 'not_instrumented',
    }
    assert result['limit'] == 5
    assert result['total'] >= len(result['items'])
    assert result['not_instrumented'] == list(NOT_INSTRUMENTED)

    for source in NOT_INSTRUMENTED:
        assert result['sources'].get(source) == 'not_instrumented'

    for item in result['items']:
        assert item['rule_key']
        assert item['source'] in SOURCES
        assert item['layer'] in ('L1', 'L2')
        assert isinstance(item['configurable'], bool)


def test_configurable_rules_only_db_sources(service):
    result = service.list_rules(configurable=True, limit=500)

    sources = {item['source'] for item in result['items']}
    assert sources <= {'control_parameter', 'line_type'}


def test_filters_are_composable(service):
    result = service.list_rules(sources=['doc_flow'], status='active', limit=500)

    for item in result['items']:
        assert item['source'] == 'doc_flow'
        assert item['status'] == 'active'


def test_unknown_rule_key_returns_none(service):
    assert service.get_rule('no_such_rule_key') is None


# ---------------------------------------------------------------------------
# 路由优先级
# ---------------------------------------------------------------------------

def test_rule_trace_route_wins_over_generic_bo_route():
    app = Flask(__name__)
    app.register_blueprint(bo_bp)
    app.register_blueprint(rule_trace_bp)

    adapter = app.url_map.bind('')
    endpoint, _ = adapter.match('/api/v2/bo/sales_order/1/rule-trace', method='GET')

    assert endpoint.endswith('get_rule_trace')


# ---------------------------------------------------------------------------
# 单据规则推导（FR-015 / IF-007）
# ---------------------------------------------------------------------------

class TestRuleTraceService:
    @classmethod
    def setup_class(cls):
        from meta.core.rule_trace_service import RuleTraceService

        cls.service = RuleTraceService()

    def test_envelope_contract(self):
        result = self.service.build(
            'sales_order',
            data={'status': 'draft', 'org_id': 1},
            scenarios='default,doc_flow',
        )

        assert result['object_type'] == 'sales_order'
        assert result['factors']['org_id'] == 1
        assert len(result['scenarios']) == 2

        for envelope in result['scenarios']:
            assert set(envelope) >= {
                'ok', 'scenario', 'decision', 'kind', 'rule_id', 'source',
                'reason', 'factors', 'elapsed_ms',
            }
            assert envelope['kind'] in ('hit', 'miss', 'skip', 'error', 'info')

    def test_factor_sources_precedence(self):
        # 单据自带 org_id -> record；请求显式传 org_id -> override；其余无值 -> missing
        result = self.service.build(
            'sales_order',
            data={'status': 'draft', 'org_id': 1},
            scenarios=['default'],
        )
        assert result['factor_sources']['org_id'] == 'record'
        assert result['factor_sources']['document_type_id'] == 'missing'

        overridden = self.service.build(
            'sales_order',
            data={'status': 'draft', 'org_id': 1},
            dims={'org_id': 9},
            scenarios=['default'],
        )
        assert overridden['factors']['org_id'] == 9
        assert overridden['factor_sources']['org_id'] == 'override'

    def test_default_detail_lists_all_rules(self):
        result = self.service.build(
            'sales_order',
            data={'status': 'draft', 'org_id': 1},
            scenarios=['default'],
        )
        envelope = result['scenarios'][0]
        assert isinstance(envelope.get('detail', {}).get('rules'), list)
        for entry in envelope['detail']['rules']:
            assert entry['status'] in ('applied', 'skipped', 'not_matched')

    def test_control_parameter_all_codes_missing(self):
        result = self.service.build(
            'sales_order',
            data={'status': 'draft', 'org_id': 1},
            scenarios=['control_parameter'],
            codes=['__no_such_parameter__'],
        )
        envelope = result['scenarios'][0]
        assert envelope['decision'] == 'missing'
        assert envelope['kind'] == 'miss'
        assert envelope['reason'] == 'all_codes_missing'
        assert envelope['detail']['missing'] == ['__no_such_parameter__']

    def test_default_scenarios_exclude_permission(self):
        from meta.core.rule_trace_service import TRACE_SCENARIOS

        assert 'permission' not in TRACE_SCENARIOS

    def test_control_parameter_requires_codes(self):
        result = self.service.build(
            'sales_order',
            data={'status': 'draft', 'org_id': 1},
            scenarios=['control_parameter'],
        )

        envelope = result['scenarios'][0]
        assert envelope['decision'] == 'skipped'
        assert envelope['reason'] == 'no_codes_requested'

    def test_invalid_scenario_rejected(self):
        from meta.core.rule_trace_service import RuleTraceError

        with pytest.raises(RuleTraceError):
            self.service.build(
                'sales_order', data={'status': 'draft'}, scenarios=['nope'])

    def test_unknown_object_type_rejected(self):
        from meta.core.rule_trace_service import RuleTraceNotFound

        with pytest.raises(RuleTraceNotFound):
            self.service.build('no_such_bo', data={'status': 'draft'})

    # ------------------------------------------------------------------
    # L1 运行期节点字段（spec §11.3）
    # ------------------------------------------------------------------

    def test_node_fields_and_seq(self):
        from meta.core.rule_trace_service import STAGE_MAP

        result = self.service.build(
            'sales_order', data={'status': 'draft', 'org_id': 1})
        trace_id = result['trace_id']
        nodes = result['scenarios']

        assert result['truncated'] is False
        assert result['node_count'] == len(nodes)
        assert [node['seq'] for node in nodes] == list(range(1, len(nodes) + 1))

        for node in nodes:
            assert node['node_id'] == '{0}:{1}'.format(trace_id, node['seq'])
            assert node['parent_id'] is None
            assert node['stage'] == STAGE_MAP.get(node['scenario'], 'validate')
            assert isinstance(node['match'], dict)
            assert isinstance(node['match']['matched'], bool)
            assert isinstance(node['match']['conditions'], list)
            assert isinstance(node['output'], dict)

        assert len({node['node_id'] for node in nodes}) == len(nodes)

    def test_nodes_truncated_when_exceed_limit(self, monkeypatch):
        import meta.core.rule_trace_service as trace_mod

        monkeypatch.setattr(trace_mod, 'MAX_TRACE_NODES', 2)
        result = trace_mod.RuleTraceService().build(
            'sales_order', data={'status': 'draft', 'org_id': 1})

        assert result['truncated'] is True
        assert result['node_count'] == 2
        assert len(result['scenarios']) == 2
        # 截断只影响返回体积：kind_counts 仍按完整求值结果统计
        assert sum(result['kind_counts'].values()) == len(trace_mod.TRACE_SCENARIOS)

    def test_state_transition_match_and_output(self):
        result = self.service.build(
            'sales_order', data={'status': 'draft', 'org_id': 1},
            scenarios=['state_transition'], to_state='submitted',
        )
        node = result['scenarios'][0]

        assert node['decision'] == 'allowed'
        assert node['stage'] == 'status_transition'
        assert node['output'] == {'status': 'submitted'}

        conditions = {item['field']: item for item in node['match']['conditions']}
        assert conditions['from_state']['actual'] == 'draft'
        assert conditions['from_state']['passed'] is True
        # 期望值取状态机声明的全部出边，不硬编码具体迁移列表
        assert 'submitted' in conditions['to_state']['expected']
        assert conditions['to_state']['passed'] is True


# ---------------------------------------------------------------------------
# 端到端（共享 app + dev-login）
# ---------------------------------------------------------------------------

class TestRuleCenterEndpoints:
    @classmethod
    def setup_class(cls):
        from meta.tests.conftest import get_shared_app

        _, cls.client = get_shared_app()
        cls.client.get('/api/v1/auth/dev-login?username=admin')

    def test_view_config_ok(self):
        resp = self.client.get('/api/v2/rules/view-config')
        assert resp.status_code == 200

        body = resp.get_json()
        assert body['success'] is True
        assert len(body['data']['tabs']) == 9

    def test_list_rules_ok(self):
        resp = self.client.get('/api/v2/rules?limit=3')
        assert resp.status_code == 200

        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['limit'] == 3
        assert body['data']['not_instrumented'] == list(NOT_INSTRUMENTED)

    def test_unknown_rule_404(self):
        resp = self.client.get('/api/v2/rules/no_such_rule_key')
        assert resp.status_code == 404

        body = resp.get_json()
        assert body['success'] is False
        assert body.get('code') == 'RULE_NOT_FOUND'

    def test_menu_and_permission_seeded(self):
        import sqlite3

        from meta.core.db_path import get_meta_db_path

        conn = sqlite3.connect(get_meta_db_path())
        try:
            menu = conn.execute(
                "SELECT page_type, menu_path FROM menus WHERE menu_code = 'rule-center'"
            ).fetchone()
            perm = conn.execute(
                "SELECT required_permissions FROM menu_permissions "
                "WHERE menu_code = 'rule-center'"
            ).fetchone()
        finally:
            conn.close()

        assert menu == ('rule_center', '/system/rule-center')
        assert perm and 'rule_center:rule_center_read' in perm[0]