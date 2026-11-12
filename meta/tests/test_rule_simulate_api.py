# -*- coding: utf-8 -*-
"""规则中心 P2：规则试算（FR-017 / IF-008）与配置发布流（FR-018）。

覆盖：
  1. 试算 baseline / draft / both 三种口径；
  2. 候选集标注（hit / draft 行）与对照 diff；
  3. 非法入参（未知场景、未知口径、缺 codes、超 20 个 codes）；
  4. 行类型按四维因子命中，draft 覆盖 active；缺 document_type_id 如实标注未接入；
  5. 委托场景（approval / doc_flow）透传 not_instrumented，缺上下文时报错；
  6. 缓存：同键二次命中；配置草稿保存后立即失效；
  7. 配置发布流闭环：保存草稿 → 发布（旧 active 置 inactive）→ 历史 → 回滚；
  8. HTTP 写路径闭环（临时库注入，零污染主库）。

同库隔离：试算用 Fake Resolver 注入数据；发布流用临时 SQLite（DDL 从主库复制），
不写主库。

ALLOW_RAW_SQL: 本文件仅在 tmp_path 临时库上执行 DDL 复制与种子插入，不触碰主库，
故对 raw-SQL 守卫做文件级声明放行（不放全局环境变量）。
"""

import sqlite3

import pytest

import meta.api.rule_center_api as rule_center_api
import meta.services.rule_simulate_service as simulate_module
from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.services import control_parameter_service as cp_module
from meta.services import line_type_service as lt_module
from meta.services.control_parameter_service import ControlParameterResolver
from meta.services.line_type_service import LineTypeResolver
from meta.services.rule_config_publish_service import (
    RuleConfigError,
    RuleConfigPublishService,
)
from meta.services.rule_simulate_service import (
    RuleSimulateError,
    RuleSimulateService,
    invalidate_simulate_cache,
)


# ---------------------------------------------------------------------------
# Fake Resolver：内存注入配置，不读主库
# ---------------------------------------------------------------------------

class _FakeControlParameterResolver(ControlParameterResolver):
    def __init__(self, defs, values):
        super().__init__(data_source=None)
        self._fake_defs = defs
        self._fake_values = values

    def _fetch_defs(self):
        return [dict(row) for row in self._fake_defs]

    def _fetch_values(self, include_draft=False):
        allowed = ('active', 'draft') if include_draft else ('active',)
        return [dict(row) for row in self._fake_values if row.get('status') in allowed]


class _FakeLineTypeResolver(LineTypeResolver):
    def __init__(self, assignments, doc_types):
        super().__init__(data_source=None)
        self._fake_assignments = assignments
        self._fake_doc_types = doc_types

    def _fetch_assignments(self, include_draft=False):
        allowed = ('active', 'draft') if include_draft else ('active',)
        return [dict(row) for row in self._fake_assignments
                if row.get('status') in allowed]

    def _fetch_doc_types(self):
        return [dict(row) for row in self._fake_doc_types]


@pytest.fixture
def simulator(monkeypatch):
    cp = _FakeControlParameterResolver(
        defs=[{
            'id': 1, 'code': 'payment_term', 'value_type': 'string',
            'default_value': 'net30', 'status': 'active',
        }],
        values=[
            {
                'id': 10, 'control_parameter_id': 1, 'org_id': None,
                'document_type_id': None, 'line_type_id': None,
                'item_group_id': None, 'specificity_rank': 100,
                'value': 'net30', 'status': 'active',
            },
            {
                'id': 11, 'control_parameter_id': 1, 'org_id': 1,
                'document_type_id': None, 'line_type_id': None,
                'item_group_id': None, 'specificity_rank': 50,
                'value': 'net45', 'status': 'draft',
            },
        ],
    )
    lt = _FakeLineTypeResolver(
        assignments=[
            {
                'id': 20, 'document_type_id': 3, 'item_group_id': None,
                'specificity_rank': 100, 'line_type_id': 5, 'status': 'active',
            },
            {
                'id': 21, 'document_type_id': 3, 'item_group_id': 2,
                'specificity_rank': 50, 'line_type_id': 7, 'status': 'draft',
            },
        ],
        doc_types=[{'id': 3, 'code': 'SO', 'default_type_id': 5, 'status': 'active'}],
    )

    monkeypatch.setattr(cp_module, 'get_control_parameter_resolver', lambda: cp)
    monkeypatch.setattr(lt_module, 'get_line_type_resolver', lambda: lt)
    invalidate_simulate_cache()
    return RuleSimulateService()


# ---------------------------------------------------------------------------
# 试算
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_baseline_ignores_draft_rows(self, simulator):
        result = simulator.simulate(
            'control_parameter', factors={'org_id': 1}, codes='payment_term')

        assert result['ok'] is True
        assert result['config_mode'] == 'baseline'
        assert result['decision'] == 'hit'
        assert result['final']['value'] == 'net30'
        assert result['candidates']
        assert all(row['status'] == 'active' for row in result['candidates'])
        assert result['cached'] is False

    def test_draft_mode_uses_draft_rows(self, simulator):
        result = simulator.simulate(
            'control_parameter', factors={'org_id': 1},
            codes='payment_term', config_mode='draft')

        assert result['config_mode'] == 'draft'
        assert result['final']['value'] == 'net45'
        hits = [row for row in result['candidates'] if row['hit']]
        assert len(hits) == 1
        assert hits[0]['status'] == 'draft'

    def test_both_mode_returns_diff(self, simulator):
        result = simulator.simulate(
            'control_parameter', factors={'org_id': 1},
            codes='payment_term', config_mode='both')

        assert result['baseline']['final']['value'] == 'net30'
        assert result['draft']['final']['value'] == 'net45'
        assert result['diff'] == [
            {'code': 'payment_term', 'baseline': 'net30', 'draft': 'net45'}
        ]
        assert result['final']['value'] == 'net45'

    def test_line_type_baseline_and_draft(self, simulator):
        baseline = simulator.simulate(
            'line_type', factors={'document_type_id': 3, 'item_group_id': 2})
        assert baseline['decision'] == 'hit'
        assert baseline['final']['line_type_id'] == 5

        invalidate_simulate_cache()
        draft = simulator.simulate(
            'line_type', factors={'document_type_id': 3, 'item_group_id': 2},
            config_mode='draft')
        assert draft['final']['line_type_id'] == 7

    def test_invalid_config_mode_rejected(self, simulator):
        with pytest.raises(RuleSimulateError):
            simulator.simulate(
                'control_parameter', codes='payment_term', config_mode='nope')

    def test_codes_required_for_control_parameter(self, simulator):
        with pytest.raises(RuleSimulateError):
            simulator.simulate('control_parameter', factors={'org_id': 1})

    def test_codes_limit_enforced(self, simulator):
        codes = ','.join(f'code_{i}' for i in range(21))
        with pytest.raises(RuleSimulateError):
            simulator.simulate('control_parameter', codes=codes)

    def test_delegate_requires_object_type(self, simulator):
        with pytest.raises(RuleSimulateError):
            simulator.simulate('approval', factors={'org_id': 1})

    def test_second_call_hits_cache(self, simulator):
        first = simulator.simulate(
            'control_parameter', factors={'org_id': 1}, codes='payment_term')
        second = simulator.simulate(
            'control_parameter', factors={'org_id': 1}, codes='payment_term')

        assert first['cached'] is False
        assert second['cached'] is True
        assert second['final'] == first['final']

    def test_codes_boundary_20_allowed(self, simulator):
        codes = ','.join(f'code_{i}' for i in range(20))
        result = simulator.simulate('control_parameter', codes=codes)

        assert result['ok'] is True
        assert len(result['results']) == 20
        assert result['decision'] == 'not_instrumented'

    def test_codes_are_trimmed_and_deduplicated(self, simulator):
        result = simulator.simulate(
            'control_parameter', codes=' payment_term , payment_term ,')

        assert len(result['results']) == 1
        assert result['results'][0]['code'] == 'payment_term'
        assert result['decision'] == 'hit'

    def test_line_type_without_document_type_is_not_instrumented(self, simulator):
        result = simulator.simulate('line_type', factors={})

        assert result['decision'] == 'not_instrumented'
        assert result['candidates'] == []
        assert result['final']['assignment_id'] is None
        assert '单据类型' in result['reason']

    def test_delegate_without_context_raises(self, simulator, monkeypatch):
        class _TraceRaises:
            def build(self, *args, **kwargs):
                from meta.core.rule_trace_service import RuleTraceError
                raise RuleTraceError('data 或 record_id 必须提供其一')

        monkeypatch.setattr(
            simulate_module, 'get_rule_trace_service', lambda: _TraceRaises())

        with pytest.raises(RuleSimulateError):
            simulator.simulate('approval', object_type='sales_order')

    def test_delegate_passes_through_not_instrumented(self, simulator, monkeypatch):
        class _TraceNotInstrumented:
            def build(self, *args, **kwargs):
                return {'scenarios': [{
                    'decision': 'not_instrumented',
                    'source': 'code',
                    'rule_id': 'approval:SO',
                    'reason': '审批规则未接入',
                    'detail': {},
                }]}

        monkeypatch.setattr(
            simulate_module, 'get_rule_trace_service',
            lambda: _TraceNotInstrumented())

        result = simulator.simulate(
            'approval', object_type='sales_order', data={'org_id': 1})

        assert result['decision'] == 'not_instrumented'
        assert result['rule_id'] == 'approval:SO'
        assert result['reason'] == '审批规则未接入'
        assert result['final'] is None
        assert result['candidates'] == []


# ---------------------------------------------------------------------------
# 配置发布流（临时库，DDL 复制主库）
# ---------------------------------------------------------------------------

_TABLES = (
    'control_parameter_defs',
    'control_parameter_values',
    'line_type_assignments',
    'type_definitions',
    'item_groups',
    'audit_logs',
    # 外键被引用表：datasource 打开 foreign_keys 后，INSERT 需能解析这些表
    'orgs',
    'enum_types',
    'number_sequences',
)

_CP_KEYS = {
    'control_parameter_id': 1,
    'org_id': None,
    'document_type_id': None,
    'line_type_id': None,
    'item_group_id': None,
}


def _build_publish_service(tmp_path):
    """临时库上构建发布服务（DDL 复制主库 + 一行 active 种子）。"""
    db_path = tmp_path / 'rule_console.db'
    main = sqlite3.connect(str(get_meta_db_path()))
    conn = sqlite3.connect(str(db_path))
    try:
        for name in _TABLES:
            row = main.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (name,)).fetchone()
            assert row, f'主库缺少表 {name}'
            conn.execute(row[0])

        conn.executescript(
            "INSERT INTO control_parameter_defs "
            "(id, code, name, value_type, default_value, status) "
            "VALUES (1, 'payment_term', '付款条件', 'string', 'net30', 'active');"
            "INSERT INTO control_parameter_values "
            "(id, control_parameter_id, org_id, document_type_id, line_type_id, "
            " item_group_id, specificity_rank, value, status, created_at) "
            "VALUES (10, 1, NULL, NULL, NULL, NULL, 100, 'net30', "
            "'active', '2026-01-01T00:00:00');"
        )
        conn.commit()
    finally:
        conn.close()
        main.close()

    ds = get_data_source('sqlite', database=str(db_path))
    return RuleConfigPublishService(data_source=ds)


@pytest.fixture
def publish_service(tmp_path):
    return _build_publish_service(tmp_path)


def _active_value(publish_service, value_id):
    rows = publish_service.ds.query(
        "SELECT id, value, status FROM control_parameter_values WHERE id = ?",
        (value_id,))
    return rows[0] if rows else None


class TestPublishFlow:
    def test_save_publish_history_rollback(self, publish_service):
        # 1) 保存草稿：同键无 draft → INSERT，不动 active
        saved = publish_service.save_draft(
            'control_parameter_value',
            dict(_CP_KEYS, value='net60'),
            user_id='u1', user_name='测试员')

        assert saved['status'] == 'draft'
        draft_id = saved['id']
        assert _active_value(publish_service, 10)['status'] == 'active'

        # 2) 发布：旧 active 置 inactive，草稿变 active
        published = publish_service.publish(
            'control_parameter_value', draft_id=draft_id,
            user_id='u1', user_name='测试员')

        assert published['status'] == 'active'
        assert published['superseded'] == 1
        assert _active_value(publish_service, 10)['status'] == 'inactive'
        assert _active_value(publish_service, draft_id)['status'] == 'active'

        # 3) 历史：目录风格 rule_key 能聚合到该参数的全部维度行
        history = publish_service.history(
            target='control_parameter_value',
            rule_key='control_parameter:payment_term')

        assert history['total'] >= 2
        actions = [item['action'] for item in history['items']]
        assert 'SAVE' in actions
        assert 'PUBLISH' in actions

        publish_item = next(i for i in history['items'] if i['action'] == 'PUBLISH')
        assert publish_item['after']
        assert publish_item['before']

        # 4) 回滚：恢复上一发布的 active 行
        rolled = publish_service.rollback(
            'control_parameter_value',
            {'rule_key': 'control_parameter:payment_term'},
            user_id='u1', user_name='测试员')

        assert rolled['restored'] == 1
        assert _active_value(publish_service, 10)['status'] == 'active'
        assert _active_value(publish_service, 10)['value'] == 'net30'
        assert _active_value(publish_service, draft_id)['status'] == 'inactive'

    def test_history_derives_target_from_rule_key(self, publish_service):
        publish_service.save_draft(
            'control_parameter_value', dict(_CP_KEYS, value='net60'))

        history = publish_service.history(
            rule_key='control_parameter:payment_term')

        assert history['total'] == 1
        assert history['items'][0]['action'] == 'SAVE'

    def test_history_unknown_rule_key_prefix_returns_empty(self, publish_service):
        publish_service.save_draft(
            'control_parameter_value', dict(_CP_KEYS, value='net60'))

        history = publish_service.history(rule_key='doc_flow:submit')

        assert history['total'] == 0
        assert history['items'] == []

    def test_save_draft_invalidates_simulate_cache(
            self, simulator, publish_service):
        factors = {'org_id': 1}
        first = simulator.simulate(
            'control_parameter', factors=factors, codes='payment_term')
        second = simulator.simulate(
            'control_parameter', factors=factors, codes='payment_term')
        assert first['cached'] is False
        assert second['cached'] is True

        publish_service.save_draft(
            'control_parameter_value', dict(_CP_KEYS, value='net60'))

        third = simulator.simulate(
            'control_parameter', factors=factors, codes='payment_term')
        assert third['cached'] is False

    def test_save_draft_updates_existing_draft(self, publish_service):
        first = publish_service.save_draft(
            'control_parameter_value', dict(_CP_KEYS, value='net60'))
        second = publish_service.save_draft(
            'control_parameter_value', dict(_CP_KEYS, value='net90'))

        assert first['id'] == second['id']
        assert _active_value(publish_service, second['id'])['value'] == 'net90'

    def test_save_draft_rejects_missing_required(self, publish_service):
        with pytest.raises(RuleConfigError):
            publish_service.save_draft('control_parameter_value', {'value': 'x'})

    def test_publish_requires_draft(self, publish_service):
        with pytest.raises(RuleConfigError):
            publish_service.publish(
                'control_parameter_value', dict(_CP_KEYS, value='net60'))

    def test_rollback_without_history(self, publish_service):
        with pytest.raises(RuleConfigError):
            publish_service.rollback(
                'control_parameter_value',
                {'rule_key': 'control_parameter:payment_term'})


# ---------------------------------------------------------------------------
# API 层（共享 app + dev-login）：只读路径 + "写前校验失败"分支 + 临时库写闭环，
# 写路径一律 monkeypatch 注入临时库服务，不污染主库。
# ---------------------------------------------------------------------------

class TestRuleCenterP2Endpoints:
    @classmethod
    def setup_class(cls):
        from meta.tests.conftest import get_shared_app

        _, cls.client = get_shared_app()
        cls.client.get('/api/v1/auth/dev-login?username=admin')

    def test_simulate_http_rejects_invalid_mode(self):
        resp = self.client.post('/api/v2/rules/simulate', json={
            'scenario': 'control_parameter',
            'codes': ['payment_term'],
            'config_mode': 'nope',
        })
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_simulate_http_rejects_missing_codes(self):
        resp = self.client.post('/api/v2/rules/simulate', json={
            'scenario': 'control_parameter',
        })
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_history_route_not_shadowed_by_rule_key(self):
        # GET /config/history 必须由静态路由命中，而非 /<path:rule_key>
        resp = self.client.get(
            '/api/v2/rules/config/history'
            '?rule_key=control_parameter:payment_term')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert 'items' in body['data']

    def test_draft_http_rejects_missing_required(self):
        resp = self.client.post('/api/v2/rules/config/draft', json={
            'target': 'control_parameter_value',
            'payload': {},
        })
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False
        assert body['code'] == 'RULE_CONFIG_INVALID'

    def test_publish_http_missing_draft_404(self):
        resp = self.client.post('/api/v2/rules/config/publish', json={
            'target': 'control_parameter_value',
            'draft_id': 987654321,
        })
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'NOT_FOUND'

    def test_rollback_http_without_history_404(self):
        resp = self.client.post('/api/v2/rules/config/rollback', json={
            'target': 'control_parameter_value',
            'payload': {'rule_key': 'control_parameter:__never__'},
        })
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'NOT_FOUND'

    def test_config_write_flow_http_closed_loop(self, tmp_path, monkeypatch):
        """draft → publish → history → rollback 全链路（临时库，不写主库）。"""
        service = _build_publish_service(tmp_path)
        monkeypatch.setattr(
            rule_center_api, 'get_rule_config_publish_service', lambda: service)

        resp = self.client.post('/api/v2/rules/config/draft', json={
            'target': 'control_parameter_value',
            'payload': dict(_CP_KEYS, value='net60'),
        })
        assert resp.status_code == 200
        draft = resp.get_json()['data']
        assert draft['status'] == 'draft'

        resp = self.client.post('/api/v2/rules/config/publish', json={
            'target': 'control_parameter_value', 'draft_id': draft['id'],
        })
        assert resp.status_code == 200
        published = resp.get_json()['data']
        assert published['status'] == 'active'
        assert published['superseded'] == 1

        resp = self.client.get(
            '/api/v2/rules/config/history'
            '?rule_key=control_parameter:payment_term')
        assert resp.status_code == 200
        actions = [item['action'] for item in resp.get_json()['data']['items']]
        assert 'SAVE' in actions
        assert 'PUBLISH' in actions

        resp = self.client.post('/api/v2/rules/config/rollback', json={
            'target': 'control_parameter_value',
            'payload': {'rule_key': 'control_parameter:payment_term'},
        })
        assert resp.status_code == 200
        rolled = resp.get_json()['data']
        assert rolled['restored'] == 1
        assert rolled['row']['value'] == 'net30'

    # ------------------------------------------------------------------
    # 单据推导（IF-007 / FR-015）：权限码 + 入参校验
    # ------------------------------------------------------------------

    def test_trace_http_forbidden_without_permission(self, monkeypatch):
        """trace 端点已挂 rule_center:trace，无权限必须 403。"""
        import meta.api.decorators as decorators

        monkeypatch.setattr(decorators, 'evaluate_code', lambda user, code: False)
        resp = self.client.get('/api/v2/bo/sales_order/1/rule-trace')
        assert resp.status_code == 403
        body = resp.get_json()
        assert body['success'] is False
        assert body['error'] == 'FORBIDDEN'

    def test_trace_http_rejects_invalid_scenario(self, monkeypatch):
        """scenarios 不在白名单 → 400，不允许静默丢弃。"""
        from meta.api import bo_api
        from meta.core import rule_trace_service as trace_module

        monkeypatch.setattr(
            bo_api, '_check_single_bo_in_dim_scope', lambda *a, **k: False)
        monkeypatch.setattr(
            trace_module.RuleTraceService, '_load_record',
            staticmethod(lambda object_type, record_id: {'id': record_id}))
        resp = self.client.get(
            '/api/v2/bo/sales_order/1/rule-trace?scenarios=not_a_scenario')
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_trace_http_unknown_object_404(self):
        resp = self.client.get('/api/v2/bo/__unknown_bo__/1/rule-trace')
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'NOT_FOUND'

    def test_trace_http_returns_envelope(self, monkeypatch):
        """正常路径：HTTP 透传 service 结果，envelope 结构不被包装破坏。"""
        from meta.api import bo_api

        envelope = {
            'trace_id': 'abc123',
            'object_type': 'sales_order',
            'record_id': 1,
            'factors': {'org_id': None},
            'scenarios': [{
                'ok': True,
                'scenario': 'default',
                'decision': 'resolved',
                'rule_id': 'doc_flow:sales_order',
                'source': 'db',
                'reason': '',
                'factors': {},
                'elapsed_ms': 0.1,
            }],
        }

        class _StubService:
            def build(self, object_type, **kwargs):
                assert object_type == 'sales_order'
                assert kwargs['record_id'] == 1
                return envelope

        monkeypatch.setattr(
            bo_api, '_check_single_bo_in_dim_scope', lambda *a, **k: False)
        monkeypatch.setattr(
            rule_center_api, 'get_rule_trace_service', lambda: _StubService())
        resp = self.client.get('/api/v2/bo/sales_order/1/rule-trace')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['scenarios'][0]['scenario'] == 'default'