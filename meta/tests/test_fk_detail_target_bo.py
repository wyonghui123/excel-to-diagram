# -*- coding: utf-8 -*-
"""FK 跳转落点口径 detail_target_bo (2026-10-22)

报障（用户手机端实测）：
  往来关系列表页点「我方组织」落到 /detail/party_internal/14（内部治理台账），
  点「归属法人」落到 /detail/org_legal_entity/315（法人主体）——都不是组织档案。
  用户原话：「为什么要走这个中间的对象」，且落点页只有一个基本信息分区，
  比 org 基表（成员/权限集/权限预览/操作日志/往来关系）信息少。

根因：
  value_help.source 只有两套口径，缺第三套：
    - target_bo        = 候选集口径（下拉里能选到谁）→ 被刻意收窄到只读视图
    - display_target_bo = 展示解析口径（存量行显示名从哪回显）
  而「点击链接落到哪个详情页」从未定义过，前端 getFkTargetObjectType 就近复用了
  target_bo；FkLinkField 又拿 FK 列原始 id 直接拼 /detail/{bo}/{id}，不做 id 空间换算。
  ⇒ 候选集收窄（业务约束）被意外复用成了跳转落点。

修复（补第三套口径）：
  value_help.source.detail_target_bo      = 跳转落点 BO（留空 = 与 target_bo 同口径）
  value_help.source.detail_target_id_field = 落点 id 的取值列（id 空间不同源时用）
  enrichment 额外注入 {field}_link_object_type + {field}_link_id，
  前端 FkLinkField 用它们拼路由，不再猜口径。

覆盖：
  1. YAML 声明       : party1_id / le_org_id 声明 detail_target_bo=org
  2. 模型层          : yaml_loader 解析两个新字段；ValueHelpSource 默认空串
  3. 序列化层        : value_help_to_dict 下发两个新字段（前端要拿得到）
  4. 行为层          : enrichment 注入 link_object_type / link_id
  5. 行为层          : id 空间换算（parties.id → parties.org_id）
  6. 行为层          : 查不到中间列 ⇒ link_id=None（前端渲染纯文本，不给死链）
  7. 行为层          : 未声明 detail_target_bo 的字段不注入（向后兼容）

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
def _source(field_id, schema='party_relation.yaml'):
    with open(os.path.join(_SCHEMA_DIR, schema), 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    for fld in data['fields']:
        if fld['id'] == field_id:
            return fld['value_help']['source']
    raise AssertionError(f'字段不存在: {field_id}')


# ────────────────────────────────────────
# 1. YAML 声明
# ────────────────────────────────────────
class TestYamlDeclaration:
    @pytest.mark.parametrize('field_id', ['party1_id', 'le_org_id'])
    def test_detail_target_is_org_base_table(self, field_id):
        """落点 = 组织基表（五个分区，信息最全），不是只读视图"""
        assert _source(field_id)['detail_target_bo'] == 'org'

    def test_party1_declares_id_field(self):
        """我方组织：FK 存 parties.id，org 用 orgs.id ⇒ 必须声明换算列 org_id"""
        assert _source('party1_id')['detail_target_id_field'] == 'org_id'

    def test_le_org_needs_no_id_field(self):
        """归属法人：FK 存的就是 orgs.id，与 org 同源 ⇒ 无需换算"""
        assert 'detail_target_id_field' not in _source('le_org_id')

    def test_candidate_scope_unchanged(self):
        """候选集口径不得被顺手改成 org（下拉可见范围会失控）"""
        assert _source('party1_id')['target_bo'] == 'party_internal'
        assert _source('le_org_id')['target_bo'] == 'org_legal_entity'

    def test_display_scope_unchanged(self):
        """展示解析口径也不受影响"""
        assert _source('party1_id')['display_target_bo'] == 'party'
        assert _source('le_org_id')['display_target_bo'] == 'org'

    def test_party2_explicitly_lands_on_archive(self):
        """对手侧落点显式声明为对外档案面（与展示解析口径 party 同 id 空间）"""
        assert _source('party2_id')['detail_target_bo'] == 'party_archive'
        assert _source('party2_id')['display_target_bo'] == 'party'

    def test_party2_needs_no_id_field(self):
        """party2_id 与 party_archive 同 id 空间（视图直投影 parties.id）⇒ 无需换算"""
        assert 'detail_target_id_field' not in _source('party2_id')

    def test_group_id_stays_undeclared(self):
        """未声明的字段保持同口径（向后兼容）"""
        assert 'detail_target_bo' not in _source('group_id')


# ────────────────────────────────────────
# 2. 模型层
# ────────────────────────────────────────
class TestModelLayer:
    def test_loader_parses_detail_target(self):
        from meta.core.yaml_loader import load_yaml_file
        from meta.core.value_help_accessor import get_value_help

        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
        assert obj is not None, 'party_relation.yaml 加载失败'

        field = next(f for f in obj.fields if f.id == 'party1_id')
        vh = get_value_help(field)
        assert vh is not None
        assert vh.source.detail_target_bo == 'org'
        assert vh.source.detail_target_id_field == 'org_id'
        assert vh.source.target_bo == 'party_internal'

    def test_defaults_are_empty(self):
        from meta.core.models import ValueHelpSource
        src = ValueHelpSource()
        assert src.detail_target_bo == ''
        assert src.detail_target_id_field == ''


# ────────────────────────────────────────
# 3. 序列化层
# ────────────────────────────────────────
def _party1_source_dict():
    from meta.core.ui_config.value_help_formatter import value_help_to_dict
    from meta.core.yaml_loader import load_yaml_file
    from meta.core.value_help_accessor import get_value_help

    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
    field = next(f for f in obj.fields if f.id == 'party1_id')
    return value_help_to_dict(get_value_help(field))['source']


class TestFormatterOutput:
    def test_dict_contains_detail_target(self):
        assert _party1_source_dict()['detail_target_bo'] == 'org'

    def test_dict_contains_detail_target_id_field(self):
        assert _party1_source_dict()['detail_target_id_field'] == 'org_id'

    def test_dict_keeps_candidate_scope(self):
        assert _party1_source_dict()['target_bo'] == 'party_internal'

    def test_undeclared_field_serializes_empty(self):
        from meta.core.ui_config.value_help_formatter import value_help_to_dict
        from meta.core.yaml_loader import load_yaml_file
        from meta.core.value_help_accessor import get_value_help

        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
        field = next(f for f in obj.fields if f.id == 'group_id')
        src = value_help_to_dict(get_value_help(field))['source']
        assert src['detail_target_bo'] == ''
        assert src['detail_target_id_field'] == ''


# ────────────────────────────────────────
# 4+5+6+7. 行为层（enrichment）
# ────────────────────────────────────────
@pytest.fixture()
def enrich_env(tmp_path):
    """临时库：parties（含 org_id 有值/为 NULL 两类行）+ orgs

    - party id=14: org_id=315  ← 复现当事行（我方组织直落 org 315）
    - party id=17: org_id=318
    - party id=22: org_id=NULL ← 历史脏数据（外部主体没 org 行）
    """
    from meta.core.sql_adapters import SQLiteAdapter
    from meta.core.yaml_loader import load_yaml_file
    from meta.core.models import registry
    from meta.core.enrichment_engine import EnrichmentEngine
    from meta.core.redundancy_registry import redundancy_registry

    ds = SQLiteAdapter()
    assert ds.connect(path=str(tmp_path / 'fk_detail_target.db'))
    ds.execute("CREATE TABLE parties (id INTEGER PRIMARY KEY, code TEXT, "
               "name TEXT, party_type TEXT, source TEXT, org_id INTEGER, status TEXT)")
    ds.execute("CREATE TABLE orgs (id INTEGER PRIMARY KEY, code TEXT, "
               "name TEXT, status TEXT)")
    ds.execute("CREATE TABLE party_groups (id INTEGER PRIMARY KEY, name TEXT)")
    # party2_id 的落点表：对外档案面（真实为视图，谓词 COALESCE(source,'') <> 'org'）。
    # 这里用同构临时表模拟：只放外部行 22，内部行 14 不可见 ⇒ 点进去应不可点。
    ds.execute("CREATE TABLE party_archive (id INTEGER PRIMARY KEY, code TEXT, "
               "name TEXT, party_type TEXT, source TEXT, org_id INTEGER, status TEXT)")
    insert(ds, 'parties', id=14, code='P-0014', name='上海用友YonBIP有限公司',
           party_type='organization', source='org', org_id=315, status='active')
    insert(ds, 'parties', id=17, code='P-0017', name='北京分公司',
           party_type='organization', source='org', org_id=318, status='active')
    insert(ds, 'parties', id=22, code='P-0022', name='个人供应商·王芳',
           party_type='individual', source=None, org_id=None, status='active')
    insert(ds, 'party_archive', id=22, code='P-0022', name='个人供应商·王芳',
           party_type='individual', source=None, org_id=None, status='active')
    insert(ds, 'orgs', id=315, code='ORG-315', name='上海用友YonBIP有限公司',
           status='active')
    insert(ds, 'orgs', id=318, code='ORG-318', name='北京分公司', status='active')
    insert(ds, 'party_groups', id=7, name='核心供应商组')

    for schema in ('party.yaml', 'party_relation.yaml', 'party_archive.yaml'):
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, schema))
        assert obj is not None, f'{schema} 加载失败'
        registry.register(obj)

    meta_obj = registry.get('party_relation')
    engine = EnrichmentEngine(ds, redundancy_registry)
    yield ds, engine, meta_obj


class TestEnrichmentLinkTarget:
    def test_party1_link_id_mapped_to_org_id(self, enrich_env):
        """我方组织：parties.id=14 ⇒ link_id 换算成 orgs.id=315"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 14, 'le_org_id': 315}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert records[0]['party1_id_link_object_type'] == 'org'
        assert records[0]['party1_id_link_id'] == 315

    def test_le_org_link_id_is_fk_value(self, enrich_env):
        """归属法人：id 空间同源 ⇒ link_id = FK 原值"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 14, 'le_org_id': 315}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert records[0]['le_org_id_link_object_type'] == 'org'
        assert records[0]['le_org_id_link_id'] == 315

    def test_missing_org_row_yields_null_link_id(self, enrich_env):
        """历史脏数据（parties.org_id 为 NULL）⇒ link_id=None，前端渲染纯文本"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 22, 'le_org_id': None}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert records[0]['party1_id_link_object_type'] == 'org'
        assert records[0]['party1_id_link_id'] is None

    def test_undeclared_field_gets_no_link_keys(self, enrich_env):
        """未声明 detail_target_bo 的字段不注入 link_* ⇒ 前端保持旧行为"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 14, 'group_id': 7}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert 'group_id_link_object_type' not in records[0]
        assert 'group_id_link_id' not in records[0]

    def test_display_names_still_resolve(self, enrich_env):
        """落点改造不得破坏显示名解析（两条链路互不干扰）"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 14, 'le_org_id': 315}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert records[0]['party1_id_display'] == '上海用友YonBIP有限公司'
        assert records[0]['le_org_id_display'] == '上海用友YonBIP有限公司'

    def test_party2_external_lands_on_archive(self, enrich_env):
        """对手侧外部行（22 在对外档案面内）⇒ 落 party_archive 且 id 原值可用"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 14, 'party2_id': 22}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert records[0]['party2_id_link_object_type'] == 'party_archive'
        assert records[0]['party2_id_link_id'] == 22
        assert records[0]['party2_id_display'] == '个人供应商·王芳'

    def test_party2_internal_row_not_clickable(self, enrich_env):
        """对手侧指向内部行（14 不在对外档案面）⇒ link_id=None，渲染纯文本"""
        _ds, engine, meta_obj = enrich_env
        records = [{'id': 1, 'party1_id': 14, 'party2_id': 14}]

        engine.enrich_fk_display_names(meta_obj, records)

        assert records[0]['party2_id_link_object_type'] == 'party_archive'
        assert records[0]['party2_id_link_id'] is None
        # 显示名仍能解析（解析口径是 party，不受落点收窄影响）
        assert records[0]['party2_id_display'] == '上海用友YonBIP有限公司'