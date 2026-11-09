# -*- coding: utf-8 -*-
"""规则中心元数据契约测试（spec §13.4 闭合矩阵 / §13.9 验收）。

只验证「视图元数据与代码声明是否闭合」以及「rule_key 生成/解析是否唯一」，
不重复 test_rule_center_api.py 的接口行为测试。
"""

import copy
import os

import pytest
import yaml

from meta.core import rule_keys
from meta.core.rule_trace_service import (
    DECISION_KINDS,
    DIMENSION_FIELDS,
    SCOPE_DOWNSTREAM,
    SCOPE_EVALUATED,
    SCOPE_NOT_TRIGGERED,
    SOURCE_TYPES,
    TRACE_SCENARIOS,
    TRACE_STAGES,
)
from meta.services.rule_catalog_service import (
    NOT_INSTRUMENTED,
    SOURCES,
    RuleCatalogError,
    RuleCatalogService,
    RuleFilterError,
)
from meta.services.rule_simulate_service import CONFIG_MODES, MAX_CODES

VIEW_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'meta', 'schemas', 'rule_center_view.yaml'))


def _load_view():
    with open(VIEW_PATH, 'r', encoding='utf-8') as handle:
        return yaml.safe_load(handle)


def _service_from(tmp_path, mutate):
    config = copy.deepcopy(_load_view())
    mutate(config)
    path = tmp_path / 'rule_center_view.yaml'
    path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding='utf-8')
    return RuleCatalogService(view_path=str(path))


@pytest.fixture(scope='module')
def service():
    return RuleCatalogService(view_path=VIEW_PATH)


# ---------------------------------------------------------------------------
# 正向：真实 YAML 与代码声明逐项闭合
# ---------------------------------------------------------------------------

def test_view_config_is_closed_against_code_declarations(service):
    config = service.get_view_config()

    declared = [entry['id'] for entry in config['sources']]
    assert len(declared) == len(rule_keys.RULE_SOURCES)
    assert set(declared) == set(rule_keys.RULE_SOURCES)

    options = config['filter_options']
    assert options['source'] == list(rule_keys.RULE_SOURCES)
    assert options['rule_type'] == list(rule_keys.RULE_TYPES)
    assert set(options) == {
        'status', 'severity', 'enabled', 'configurable', 'source', 'rule_type',
    }

    trace = config['trace']
    assert trace['scenarios'] == list(TRACE_SCENARIOS)
    assert set(trace['scenario_labels']) == set(TRACE_SCENARIOS)
    assert set(trace['stages']) == set(TRACE_STAGES)
    assert set(trace['decisions']) >= set(DECISION_KINDS)
    assert set(trace['kinds']) >= set(DECISION_KINDS.values())
    assert trace['factor_keys'] == list(DIMENSION_FIELDS)
    assert set(trace['factor_labels']) == set(DIMENSION_FIELDS)
    assert set(trace['source_types']) == set(SOURCE_TYPES)
    assert set(trace['scopes']) == {
        SCOPE_EVALUATED, SCOPE_NOT_TRIGGERED, SCOPE_DOWNSTREAM,
    }

    simulate = config['simulate']
    assert simulate['config_modes'] == list(CONFIG_MODES)
    assert simulate['max_codes'] == MAX_CODES


def test_trace_and_simulate_forms_cover_factor_axes(service):
    config = service.get_view_config()
    factors = set(config['trace']['factor_keys'])

    assert factors <= set(config['trace']['tab']['fields']), (
        '推导表单必须覆盖全部因子轴，否则 line_type 等场景无法按因子推导')
    assert factors <= set(config['simulate']['fields']), (
        '试算表单必须覆盖全部因子轴')
    assert config['simulate']['candidate_columns'], (
        '候选集列中文名必须由视图元数据下发，前端不得写死或回落原始键')


def test_derived_filter_options_are_not_inlined_in_yaml():
    raw = _load_view()

    for key in ('source', 'rule_type', 'domain'):
        assert key not in (raw.get('filter_options') or {}), (
            f'filter_options.{key} 必须由服务端派生，不得在 YAML 内联')


def test_sources_and_not_instrumented_share_one_source():
    assert SOURCES == rule_keys.RULE_SOURCES
    assert NOT_INSTRUMENTED == rule_keys.NOT_INSTRUMENTED_SOURCES


def test_rule_types_whitelist_is_unique():
    assert len(set(rule_keys.RULE_TYPES)) == len(rule_keys.RULE_TYPES)
    for derived in rule_keys.DERIVED_RULE_TYPES:
        assert derived in rule_keys.RULE_TYPES


# ---------------------------------------------------------------------------
# 负向：任一环节漂移必须在加载期失败
# ---------------------------------------------------------------------------

def _version_1(config):
    config['version'] = 1


def _drop_source(config):
    config['sources'].pop()


def _add_unknown_source(config):
    config['sources'].append({'id': 'ghost_source', 'label': '幽灵来源'})


def _inline_derived_filter(config):
    config['filter_options']['rule_type'] = ['validation']


def _shrink_closed_filter(config):
    config['filter_options']['status'] = ['active']


def _add_unknown_filter(config):
    config['filter_options']['owner'] = ['a']


def _unknown_tab_kind(config):
    for tab in config['tabs']:
        if tab['id'] == 'simulate':
            tab['kind'] = 'chart'


def _unknown_column(config):
    config['tabs'][0]['columns'].append('ghost_column')


def _not_instrumented_in_table_tab(config):
    config['tabs'][0]['sources'].append('state_machine')


def _unknown_action(config):
    config['tabs'][0]['actions'].append('ghost_action')


def _unknown_detail_widget(config):
    config['detail']['sections'][0]['widget'] = 'ghost_widget'


def _trace_scenario_mismatch(config):
    config['trace']['scenarios'].pop()


def _trace_factor_keys_mismatch(config):
    config['trace']['factor_keys'] = ['org_id']
    config['trace']['factor_labels'] = {'org_id': '组织'}


def _trace_source_types_mismatch(config):
    config['trace']['source_types'].pop('missing')


def _trace_scopes_mismatch(config):
    config['trace']['scopes'].pop('downstream')


def _simulate_modes_mismatch(config):
    config['simulate']['config_modes'].pop()


def _simulate_max_codes_mismatch(config):
    config['simulate']['max_codes'] = MAX_CODES + 1


def _trace_tab_fields_drop_factor(config):
    config['trace']['tab']['fields'].remove('line_type_id')


def _trace_tab_fields_unknown(config):
    config['trace']['tab']['fields'].append('ghost_field')


def _simulate_fields_drop_factor(config):
    config['simulate']['fields'].remove('line_type_id')


@pytest.mark.parametrize('mutate', [
    _version_1,
    _drop_source,
    _add_unknown_source,
    _inline_derived_filter,
    _shrink_closed_filter,
    _add_unknown_filter,
    _unknown_tab_kind,
    _unknown_column,
    _not_instrumented_in_table_tab,
    _unknown_action,
    _unknown_detail_widget,
    _trace_scenario_mismatch,
    _trace_factor_keys_mismatch,
    _trace_source_types_mismatch,
    _trace_scopes_mismatch,
    _simulate_modes_mismatch,
    _simulate_max_codes_mismatch,
    _trace_tab_fields_drop_factor,
    _trace_tab_fields_unknown,
    _simulate_fields_drop_factor,
], ids=lambda func: func.__name__)
def test_view_config_rejects_unclosed_metadata(tmp_path, mutate):
    with pytest.raises(RuleCatalogError):
        _service_from(tmp_path, mutate).get_view_config()


# ---------------------------------------------------------------------------
# 请求期：非法筛选值必须报错而不是静默返回空列表
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('kwargs', [
    {'sources': ['no_such_source']},
    {'rule_type': 'no_such_type'},
    {'status': 'no_such_status'},
    {'layer': 'L9'},
], ids=['source', 'rule_type', 'status', 'layer'])
def test_unknown_filter_value_rejected(service, kwargs):
    with pytest.raises(RuleFilterError):
        service.list_rules(limit=1, **kwargs)


def test_declared_filter_value_accepted(service):
    result = service.list_rules(
        sources=['control_parameter'], rule_type='control_parameter',
        status='active', layer='L2', limit=1)

    for item in result['items']:
        assert item['source'] == 'control_parameter'
        assert item['rule_type'] == 'control_parameter'


# ---------------------------------------------------------------------------
# rule_key：唯一生成器 / 解析器
# ---------------------------------------------------------------------------

def test_rule_key_builders():
    assert rule_keys.bo_yaml_key('sales_order', 'r1') == 'bo_yaml:sales_order.r1'
    assert rule_keys.control_parameter_key('CP1') == 'control_parameter:CP1'
    assert rule_keys.control_parameter_codes_key(['A', 'B']) == 'control_parameter:A,B'
    assert rule_keys.line_type_key(3, None) == 'line_type:3.*'
    assert rule_keys.doc_flow_key('flow_1') == 'doc_flow:flow_1'
    assert rule_keys.approval_key('sales_order') == 'approval:sales_order'


def test_split_key_round_trip():
    cases = [
        (rule_keys.bo_yaml_key('sales_order', 'r1'), ('bo_yaml', 'sales_order.r1')),
        (rule_keys.control_parameter_key('CP1'), ('control_parameter', 'CP1')),
        (rule_keys.line_type_key(None, 3), ('line_type', '*.3')),
        (rule_keys.doc_flow_key('flow_1'), ('doc_flow', 'flow_1')),
        (rule_keys.approval_key('sales_order'), ('approval', 'sales_order')),
    ]
    for rule_key, expected in cases:
        assert rule_keys.split_key(rule_key) == expected

    assert rule_keys.split_key('ghost:abc') is None
    assert rule_keys.split_key('no_prefix') is None
    assert rule_keys.split_key('') is None


def test_publish_keys_are_dimension_stable():
    row = {'org_id': 1, 'document_type_id': None, 'line_type_id': '', 'item_group_id': 5}

    assert rule_keys.control_parameter_value_key('CP1', row) == 'CP1|1|*|*|5'
    assert rule_keys.line_type_assignment_key(3) == '3.*'
    assert rule_keys.line_type_assignment_key(3, 4) == '3.4'


def test_catalog_items_use_declared_source_prefix(service):
    result = service.list_rules(limit=200)

    assert set(result['sources']) == set(rule_keys.RULE_SOURCES)
    for item in result['items']:
        split = rule_keys.split_key(item['rule_key'])
        assert split is not None, f'规则键不可解析: {item["rule_key"]}'
        assert split[0] == item['source'], (
            f'规则键前缀与来源不一致: {item["rule_key"]} / {item["source"]}')


# ---------------------------------------------------------------------------
# 可编辑目标：links 由适配器下发（F-13-05）
# ---------------------------------------------------------------------------

def test_configurable_targets_declared_once():
    from meta.core.rule_targets import RULE_TARGETS, target_for_source

    assert {spec['source'] for spec in RULE_TARGETS.values()} == {
        'control_parameter', 'line_type',
    }
    assert target_for_source('control_parameter') == 'control_parameter_value'
    assert target_for_source('line_type') == 'line_type_assignment'
    assert target_for_source('bo_yaml') is None


def test_editable_items_expose_links(service):
    from meta.core.rule_targets import target_for_source

    configurable = service.list_rules(configurable=True, include_draft=True, limit=500)
    assert configurable['items'], '需要至少一条可配置规则验证 links'

    for item in configurable['items']:
        target = target_for_source(item['source'])
        links = item.get('links') or {}

        assert target, f'可配置来源缺少 target 声明: {item["source"]}'
        assert links.get('edit', {}).get('target') == target
        if item['status'] == 'draft':
            assert links.get('publish', {}).get('target') == target
            assert links.get('rollback', {}).get('target') == target
        else:
            assert 'publish' not in links

    readonly = service.list_rules(configurable=False, limit=50)
    for item in readonly['items']:
        if item['source'] == 'sourcing':
            # 来源规则走 BO 生命周期：edit 指向 BO 页面，不得出现发布/回滚动作
            links = item.get('links') or {}
            assert links.get('edit', {}).get('target') == 'sourcing_rule'
            assert 'publish' not in links and 'rollback' not in links
            continue
        assert 'links' not in item, f'只读规则不得下发可编辑 links: {item["rule_key"]}'


# ---------------------------------------------------------------------------
# 元数据版本 / 指纹（F-13-10）与草稿口径（F-13-11）
# ---------------------------------------------------------------------------

def test_view_config_carries_version_and_hash(service):
    import re

    config = service.get_view_config()

    assert config['version'] == 2
    assert re.fullmatch(r'[0-9a-f]{64}', config['hash'] or ''), '视图元数据必须下发内容指纹'


def test_include_draft_defaults_to_active_only(service):
    db_sources = ['control_parameter', 'line_type']

    default = service.list_rules(sources=db_sources, limit=500)
    assert all(item['status'] == 'active' for item in default['items']), (
        '默认口径应只看生效态（与运行时一致）')

    drafts = service.list_rules(
        sources=db_sources, status='draft', include_draft=True, limit=500)
    assert all(item['status'] == 'draft' for item in drafts['items'])