# -*- coding: utf-8 -*-
"""F1 · FK 显示名解析口径与候选集口径分离 (2026-10-20)

报障（用户手机端实测）：
  身份档案（对外）详情页「往来关系」分区的「对方」列显示技术 id（8）而不是名称。

根因：
  party_relation 存的是 parties.id 外键；显示名解析走
  enrichment_engine.enrich_fk_display_names —— 它按 value_help.source.target_bo
  取表后直查。party1_id 的 target_bo = party_internal（谓词 source='org'），
  而历史行的 party1_id 指向 source≠'org' 的 party ⇒ 查不到 ⇒ *_display = null
  ⇒ 前端 AssociationSection.vue 回退显示原始 id。

修复（口径分离）：
  value_help.source.target_bo        = **候选集口径**（下拉里能被选到哪些行）
  value_help.source.display_target_bo = **展示解析口径**（已存量行的显示名去哪取）
  两侧均声明 display_target_bo: party（身份锚）⇒ 候选集仍收窄在视图，
  显示名一律回身份锚取。

覆盖：
  1. YAML 声明   : 两侧 target_bo 保持视图（候选集口径不变），display_target_bo = party
  2. 模型层      : yaml_loader 把 display_target_bo 解析进 ValueHelpSource
  3. 行为层      : enrichment 对"视图外的 party"仍解析出名称（而不是 null）
  4. 行为层      : 未声明 display_target_bo 的字段仍按 target_bo 解析（向后兼容）

resolve 链路（编辑态下拉回显）—— 上面只覆盖了列表/详情表格列；编辑态回显走
  另一条链（useValueHelp → boSearchHelpService → GET /value-help/bo/{bo}/resolve
  → BoValueHelpProvider.resolve），且该端点按 URL 参数重建 source（不读 YAML）
  ⇒ 需三段补齐：
  5. 序列化层    : value_help_to_dict 输出 display_target_bo（前端拿得到）
  6. 端点层      : resolve 端点从 request.args 读取该参数；search 端点不读
  7. 行为层      : provider.resolve 在候选集口径外时回落到 display_target_bo 取名

测试隔离: temp DB（SQLiteAdapter）+ 元模型注册；不触碰 architecture.db
"""
import os
import sys

import pytest
import yaml

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.factories._raw_sql_bridge import insert

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_yaml(name='party_relation.yaml'):
    with open(os.path.join(_SCHEMA_DIR, name), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _field(name, field_id):
    for f in _load_yaml(name)['fields']:
        if f['id'] == field_id:
            return f
    raise AssertionError(f'字段不存在: {field_id}')


def _source(name, field_id):
    return _field(name, field_id)['value_help']['source']


# ────────────────────────────────────────
# 1. YAML 声明
# ────────────────────────────────────────
class TestYamlDeclaration:
    def test_party1_keeps_view_as_candidate_scope(self):
        """候选集口径不变：我方侧下拉仍只见内部主体（party_internal 视图）"""
        assert _source('party_relation.yaml', 'party1_id')['target_bo'] == 'party_internal'

    def test_party2_keeps_view_as_candidate_scope(self):
        """对手侧候选集仍是对外档案面 party_archive"""
        assert _source('party_relation.yaml', 'party2_id')['target_bo'] == 'party_archive'

    @pytest.mark.parametrize('field_id', ['party1_id', 'party2_id'])
    def test_display_target_is_identity_anchor(self, field_id):
        """展示解析口径 = 身份锚 party（FK 存的就是 parties.id）"""
        assert _source('party_relation.yaml', field_id)['display_target_bo'] == 'party'

    @pytest.mark.parametrize('field_id', ['party1_id', 'party2_id'])
    def test_candidate_excludes_inactive(self, field_id):
        """[2026-10-20 问题 F] 两侧候选集只取启用主体（停用行不得新建关系）

        形态是 value_help.source.value_filter（单字段 eq）——resolve 不读该参数，
        故停用行的存量回显仍走 display_target_bo 兜底。
        """
        assert _source('party_relation.yaml', field_id).get('value_filter') == {
            'status': 'active'}

    def test_other_fields_have_no_display_target(self):
        """未声明的字段保持同口径（向后兼容）

        [2026-10-20] 取样字段由 le_org_id 改为 group_id：le_org_id 的候选集已收窄到
        org_legal_entity 视图，须声明 display_target_bo=org 才能在法人失去职能后回显
        存量行名称（见 test_f1_le_org_legal_entity_view.py），故它已属"已声明"。
        group_id（→ party_group 真表）无候选集收窄需求，仍是未声明口径的样本。
        """
        assert 'display_target_bo' not in _source('party_relation.yaml', 'group_id')


# ────────────────────────────────────────
# 2. 模型层
# ────────────────────────────────────────
class TestModelLayer:
    def test_loader_parses_display_target_bo(self):
        from meta.core.yaml_loader import load_yaml_file
        from meta.core.value_help_accessor import get_value_help

        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
        assert obj is not None, 'party_relation.yaml 加载失败'

        field = next(f for f in obj.fields if f.id == 'party1_id')
        vh = get_value_help(field)
        assert vh is not None
        assert vh.source.display_target_bo == 'party'
        assert vh.source.target_bo == 'party_internal'

    def test_default_is_empty(self):
        """未声明时为空串（= 与 target_bo 同口径）"""
        from meta.core.models import ValueHelpSource
        assert ValueHelpSource().display_target_bo == ''


# ────────────────────────────────────────
# 3+4. 行为层
# ────────────────────────────────────────
@pytest.fixture()
def enrich_env(tmp_path):
    """临时库：parties（含视图内外两类行）+ orgs + party_groups

    - id=1: source=NULL（对外主体，不在 party_internal 视图内）← 复现报障的当事行
    - id=2: source='org'（内部组织表示，在 party_internal 视图内）
    """
    from meta.core.sql_adapters import SQLiteAdapter
    from meta.core.yaml_loader import load_yaml_file
    from meta.core.models import registry
    from meta.core.enrichment_engine import EnrichmentEngine
    from meta.core.redundancy_registry import redundancy_registry

    ds = SQLiteAdapter()
    assert ds.connect(path=str(tmp_path / 'party_display_target.db'))
    ds.execute("CREATE TABLE parties (id INTEGER PRIMARY KEY, name TEXT, source TEXT)")
    ds.execute("CREATE TABLE orgs (id INTEGER PRIMARY KEY, name TEXT, code TEXT)")
    ds.execute("CREATE TABLE party_groups (id INTEGER PRIMARY KEY, name TEXT)")
    insert(ds, 'parties', id=1, name='对外伙伴甲', source=None)
    insert(ds, 'parties', id=2, name='内部组织表示乙', source='org')
    insert(ds, 'orgs', id=10, name='大财务应用架构', code='FIN')

    # 元模型注册（party 供显示名解析目标；party_relation 供字段 value_help）
    for schema in ('party.yaml', 'party_relation.yaml'):
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, schema))
        assert obj is not None, f'{schema} 加载失败'
        registry.register(obj)

    meta_obj = registry.get('party_relation')
    engine = EnrichmentEngine(ds, redundancy_registry)
    yield ds, engine, meta_obj


class TestEnrichmentBehavior:
    def test_display_name_resolves_outside_view(self, enrich_env):
        """party1_id 指向 party_internal 视图外的行 ⇒ 显示名仍为名称（不是 null）"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 1, 'party2_id': 2, 'le_org_id': 10}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert records[0]['party1_id_display'] == '对外伙伴甲'
        assert records[0]['party2_id_display'] == '内部组织表示乙'

    def test_field_without_display_target_keeps_target_bo(self, enrich_env):
        """未声明 display_target_bo 的字段仍按 target_bo 解析（向后兼容）"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 1, 'party2_id': 2, 'le_org_id': 10}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert records[0]['le_org_id_display'] == '大财务应用架构'


# ────────────────────────────────────────
# 5. 序列化层（前端要能拿到 display_target_bo）
# ────────────────────────────────────────
class TestFormatterOutput:
    """value_help_to_dict 必须输出 display_target_bo

    resolve 端点按 URL 参数重建 source、不读 YAML ⇒ 前端若拿不到该字段，
    resolve 请求就带不上口径，编辑态回显会退化成技术 id。
    """

    def _party1_source_dict(self):
        from meta.core.ui_config.value_help_formatter import value_help_to_dict
        from meta.core.yaml_loader import load_yaml_file
        from meta.core.value_help_accessor import get_value_help

        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
        assert obj is not None
        field = next(f for f in obj.fields if f.id == 'party1_id')
        return value_help_to_dict(get_value_help(field))['source']

    def test_dict_contains_display_target_bo(self):
        assert self._party1_source_dict()['display_target_bo'] == 'party'

    def test_dict_keeps_candidate_scope_intact(self):
        """序列化不得把候选集口径改成身份锚（下拉可见范围会失控）"""
        assert self._party1_source_dict()['target_bo'] == 'party_internal'

    def test_undeclared_field_serializes_empty_string(self):
        """未声明时序列化为空串（前端据此不传参数 ⇒ 与 target_bo 同口径）

        [2026-10-20] 取样字段由 le_org_id 改为 group_id（原因同上：le_org_id 已声明）。
        """
        from meta.core.ui_config.value_help_formatter import value_help_to_dict
        from meta.core.yaml_loader import load_yaml_file
        from meta.core.value_help_accessor import get_value_help

        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
        field = next(f for f in obj.fields if f.id == 'group_id')
        assert value_help_to_dict(get_value_help(field))['source']['display_target_bo'] == ''


# ────────────────────────────────────────
# 6. 端点层（resolve 读参数 / search 不读）
# ────────────────────────────────────────
@pytest.fixture()
def captured_source(monkeypatch):
    """拦截 get_provider：捕获端点按 URL 参数重建出来的 ValueHelpSource"""
    from meta.api import value_help_api

    captured = {}

    class _StubProvider:
        def resolve(self, value, user_context=None):
            return {'value': value, 'display': 'STUB', 'code': ''}

        def search(self, **kwargs):
            return {'data': [], 'total': 0, 'has_more': False}

    def _fake_get_provider(source):
        captured['source'] = source
        return _StubProvider()

    monkeypatch.setattr(value_help_api, 'get_provider', _fake_get_provider)
    return captured


def _call_view(view_name, query):
    """在 test_request_context 内直调未装饰的视图函数（绕过 login_required）"""
    from flask import Flask
    from meta.api import value_help_api

    app = Flask(__name__)
    view = getattr(value_help_api, view_name)
    view = getattr(view, '__wrapped__', view)   # login_required 用 @wraps 包装
    with app.test_request_context(query):
        view(*_route_args(query))
    return view


def _route_args(query):
    """按端点路由规则还原 (source_type, source_id)"""
    from urllib.parse import urlsplit
    parts = urlsplit(query).path.strip('/').split('/')
    # /api/v2/value-help/<source_type>/<source_id>[/resolve]
    return parts[3], parts[4]


class TestResolveEndpoint:
    def test_resolve_reads_display_target_bo(self, captured_source):
        _call_view('resolve_value_help',
                   '/api/v2/value-help/bo/party_internal/resolve?value=8&display_target_bo=party')
        assert captured_source['source'].display_target_bo == 'party'
        assert captured_source['source'].target_bo == 'party_internal'

    def test_resolve_without_param_is_empty(self, captured_source):
        """不传即空串 ⇒ 与 target_bo 同口径（向后兼容）"""
        _call_view('resolve_value_help',
                   '/api/v2/value-help/bo/party_internal/resolve?value=8')
        assert captured_source['source'].display_target_bo == ''

    def test_search_endpoint_ignores_display_target_bo(self, captured_source):
        """search 端点不得读该参数 —— 否则候选集口径会被展示口径污染"""
        _call_view('search_value_help',
                   '/api/v2/value-help/bo/party_internal?page_size=50&display_target_bo=party')
        assert captured_source['source'].display_target_bo == ''


# ────────────────────────────────────────
# 7. 行为层（provider.resolve 回落取名）
# ────────────────────────────────────────
@pytest.fixture()
def resolve_env(tmp_path):
    """临时库：parties 基表 + party_internal 视图；注入 query_service 数据源

    BOEngine 经 meta.services.query_service._get_data_source() 取库，
    该函数读模块级 _data_source_instance ⇒ 必须注入并在 teardown 复位。
    """
    from meta.core.sql_adapters import SQLiteAdapter
    from meta.core.yaml_loader import load_yaml_file
    from meta.core.models import registry
    from meta.services import query_service

    ds = SQLiteAdapter()
    assert ds.connect(path=str(tmp_path / 'party_resolve_target.db'))
    ds.execute("CREATE TABLE parties (id INTEGER PRIMARY KEY, code TEXT, "
               "name TEXT, party_type TEXT, source TEXT, org_id INTEGER)")
    ds.execute("CREATE VIEW party_internal AS SELECT id, code, name, "
               "party_type, source, org_id FROM parties WHERE source = 'org'")
    # id=8: source=NULL —— 在 party_internal 视图外（复现报障的存量行）
    insert(ds, 'parties', id=8, code='P-0008', name='对外伙伴甲',
           party_type='organization', source=None)
    # id=12: source='org' —— 在视图内
    insert(ds, 'parties', id=12, code='P-0012', name='内部组织乙',
           party_type='organization', source='org', org_id=1)

    for schema in ('party.yaml', 'party_internal.yaml'):
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, schema))
        assert obj is not None, f'{schema} 加载失败'
        registry.register(obj)

    query_service._data_source_instance = ds
    yield ds
    query_service._data_source_instance = None


def _provider(target_bo='party_internal', display_target_bo=''):
    from meta.core.models import ValueHelpSource
    from meta.core.value_help_providers import BoValueHelpProvider

    return BoValueHelpProvider(ValueHelpSource(
        type='bo',
        target_bo=target_bo,
        value_field='id',
        display_field='name',
        code_field='code',
        display_target_bo=display_target_bo,
    ))


class TestProviderResolveFallback:
    def test_falls_back_to_display_target(self, resolve_env):
        """值落在候选集口径外 ⇒ 回身份锚取名（编辑态不再显示技术 id）"""
        result = _provider(display_target_bo='party').resolve(8)
        assert result is not None
        assert result['display'] == '对外伙伴甲'
        assert result['value'] == 8

    def test_without_display_target_returns_none(self, resolve_env):
        """未声明时维持原行为：视图外查不到 ⇒ None（前端回退显示 id）"""
        assert _provider().resolve(8) is None

    def test_inside_candidate_scope_still_resolves(self, resolve_env):
        """值在视图内时优先按 target_bo 解析（回落分支不应抢跑）"""
        result = _provider(display_target_bo='party').resolve(12)
        assert result['display'] == '内部组织乙'

    def test_same_scope_skips_fallback_lookup(self, resolve_env):
        """display_target_bo == target_bo 时不做二次查询"""
        assert _provider(display_target_bo='party_internal').resolve(8) is None
