# -*- coding: utf-8 -*-
"""party 生命周期（status + activate/deactivate）接线测试 (2026-10-07)

依据: docs/superpowers/specs/2026-10-04-foundation-object-model-and-architecture.md
      §5.4（主数据生命周期统一约定：party = 最小 active/inactive，映射 activate/deactivate）
      §3.4.8 D4（停用语义 = 瞬时开关 + 不加生效日列；"某日才停用"属未来动作 → scheduled_tasks）
      §3.4.8 D9（动作语义互斥：lock/unlock 为 user 专属"限制登录"，party 不取）

覆盖:
1. status 字段   : required + default active + 两态枚举 active/inactive（无第三态）
2. 无生效日列    : 全库零 inactive_date / end_date 之类列（D4 硬判据）
3. 状态机定义    : activate_party / deactivate_party 两条，state_field=status，
                   取向互逆；**且仅此两条**（不出现 freeze / lock / unfreeze / unlock）
4. 动作语义      : action_ref 复用平台标准动作池 activate / deactivate
5. 索引          : idx_party_status 随建表落
6. 读面同列      : party_archive / party_internal 视图含 status 出口径，谓词不变
7. 建表与行为   : 临时库真实建表 → 默认值 / 显式 inactive / 两读面口径 / 索引过滤 / FK 拦截

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db;
         DML 走 ds.insert API（本文件无裸写语句 —— conftest raw-SQL 守卫）
"""
import os
import sys

import pytest
import yaml

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

_BASE = 'party'
_FACETS = ('party_archive', 'party_internal')
# D4：停用不加生效日列 —— 这些列名一旦出现即违规
_FORBIDDEN_DATE_COLS = ('inactive_date', 'disable_date', 'end_date',
                        'deactivate_date', 'status_date')

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_raw(bo_id):
    with open(os.path.join(_SCHEMA_DIR, bo_id + '.yaml'), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get('fields') or []:
        if f.get('id') == field_id:
            return f
    return None


def _rules(schema):
    return {r['id']: r for r in (schema.get('rules') or [])
            if r.get('type') == 'state_transition'}


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture()
def pst_ds(tmp_path):
    """临时库: parties 基表 + 两个只读视图 + 索引

    [生命周期 2026-10-07] parties 新增 status 列（NOT NULL DEFAULT 'active'）
    与 idx_party_status；两个面为真视图（DROP/CREATE 投影），随建表重建。
    """
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml
    from meta.core.models import registry

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    objs = []
    for fn in ('party.yaml', 'party_archive.yaml', 'party_internal.yaml',
               'org.yaml'):
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, fn),
                             aspects_defs=aspects)
        assert obj is not None, 'YAML 加载失败: %s' % fn
        if registry.get(obj.id) is None:
            registry.register(obj)      # 保 FK 目标解析确定
        objs.append(obj)

    ds = get_data_source('sqlite', database=str(tmp_path / 'party_status.db'))
    sync_schema_from_meta(ds, objs)
    # 父行：内部表示行须有 orgs 行（parties.org_id → orgs.id 真外键）
    org_cols = [r[1] for r in ds.execute('PRAGMA table_info(orgs)').fetchall()]
    # [FIX] orgs.parent_id 为真自引用外键（9018570a 落库）⇒ 探针父行该列须显式 NULL，
    #   'PROBE' 会触发 FOREIGN KEY constraint failed 使整类 setup 报错
    sample = {'code': 'ORG-PROBE', 'name': '探针组织', 'org_type': 'company',
              'org_scope': 'internal', 'parent_id': None}
    ds.insert('orgs', {c: (1 if c == 'id' else sample.get(c, 'PROBE'))
                       for c in org_cols})
    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 1. status 字段（§5.4 最小两态）
# ────────────────────────────────────────
class TestStatusField:
    def test_status_exists_and_required(self):
        f = _field(_load_raw(_BASE), 'status')
        assert f is not None, 'party.status 缺失（party 曾是唯一无 status 的锚对象）'
        assert f['type'] == 'string'
        assert f['db_column'] == 'status'
        assert f['required'] is True

    def test_default_active(self):
        """默认 active：新登记的身份主体默认可用，无需显式启用"""
        f = _field(_load_raw(_BASE), 'status')
        assert f.get('default') == 'active'

    def test_two_states_only(self):
        """最小两态 active/inactive（§5.4；不引入 draft / frozen / obsolete）"""
        vals = {e['value'] for e in _field(_load_raw(_BASE),
                                           'status')['enum_values']}
        assert vals == {'active', 'inactive'}

    def test_initial_state_marked(self):
        enums = _field(_load_raw(_BASE), 'status')['enum_values']
        initial = [e['value'] for e in enums if e.get('is_initial')]
        assert initial == ['active']

    def test_status_filterable(self):
        """可筛选（消费方按状态过滤：停用方不进入新关系选择候选）"""
        sem = _field(_load_raw(_BASE), 'status').get('semantics') or {}
        assert sem.get('filterable') is True
        assert sem.get('filter_type') == 'enum'


# ────────────────────────────────────────
# 2. D4：停用不加生效日列
# ────────────────────────────────────────
class TestNoEffectiveDateColumn:
    def test_no_inactive_date_field(self):
        ids = {f['id'] for f in _load_raw(_BASE)['fields']}
        for bad in _FORBIDDEN_DATE_COLS:
            assert bad not in ids, 'D4 禁生效日列，但 party 出现 %s' % bad

    def test_status_description_states_transient_switch(self):
        desc = _field(_load_raw(_BASE), 'status').get('description') or ''
        assert 'D4' in desc and '生效日' in desc


# ────────────────────────────────────────
# 3+4. 状态机（复用平台标准动作）
# ────────────────────────────────────────
class TestStateMachine:
    def test_exactly_two_transitions(self):
        """仅两条：activate / deactivate —— 不取 freeze / lock 系"""
        rules = _rules(_load_raw(_BASE))
        assert set(rules) == {'activate_party', 'deactivate_party'}

    def test_activate_transition(self):
        r = _rules(_load_raw(_BASE))['activate_party']
        assert r['action_ref'] == 'activate'
        assert r['state_field'] == 'status'
        assert r['from_states'] == ['inactive']
        assert r['to_state'] == 'active'
        assert 'before_update' in r['triggers']

    def test_deactivate_transition(self):
        r = _rules(_load_raw(_BASE))['deactivate_party']
        assert r['action_ref'] == 'deactivate'
        assert r['state_field'] == 'status'
        assert r['from_states'] == ['active']
        assert r['to_state'] == 'inactive'
        assert 'before_update' in r['triggers']

    def test_transitions_are_inverse(self):
        rules = _rules(_load_raw(_BASE))
        act, deact = rules['activate_party'], rules['deactivate_party']
        assert act['from_states'] == [deact['to_state']]
        assert deact['from_states'] == [act['to_state']]
        assert act['from_states'] and act['from_states'][0] == 'inactive'

    def test_no_user_only_actions(self):
        """D9：lock / unlock 为 user 专属"限制登录"，party 不得取用"""
        refs = {r.get('action_ref') for r in _rules(_load_raw(_BASE)).values()}
        assert not (refs & {'lock', 'unlock', 'freeze', 'unfreeze'}), refs

    def test_action_refs_in_standard_pool(self):
        """action_ref 必须取自平台标准动作池（_standard_actions.yaml）"""
        pool = {a['id'] for a in _load_raw('_standard_actions')[
            'standard_actions']}
        for r in _rules(_load_raw(_BASE)).values():
            assert r['action_ref'] in pool, \
                '%s 不在标准动作池' % r['action_ref']


# ────────────────────────────────────────
# 5+6. 索引与读面
# ────────────────────────────────────────
class TestIndexAndFacets:
    def test_status_index_declared(self):
        idx = _load_raw(_BASE).get('indexes') or []
        assert {'fields': ['status'], 'name': 'idx_party_status'} in idx

    @pytest.mark.parametrize('bo_id', _FACETS)
    def test_facet_exposes_status(self, bo_id):
        assert _field(_load_raw(bo_id), 'status') is not None, \
            '%s 面未同列出 status（消费方无法按状态过滤）' % bo_id

    @pytest.mark.parametrize('bo_id', _FACETS)
    def test_facet_view_definition_includes_status(self, bo_id):
        assert 'status' in (_load_raw(bo_id).get('view_definition') or '')

    @pytest.mark.parametrize('bo_id', _FACETS)
    def test_facet_predicate_unchanged(self, bo_id):
        """F1 治理分域谓词不得因加状态而改变"""
        vd = ' '.join((_load_raw(bo_id).get('view_definition') or '').split())
        if bo_id == 'party_archive':
            assert "COALESCE(source, '') <> 'org'" in vd
        else:
            assert "source = 'org'" in vd

    @pytest.mark.parametrize('bo_id', _FACETS)
    def test_facet_write_policy(self, bo_id):
        """写策略分层：archive 有写锚（写转发基表 party）；internal 无写锚（只读）"""
        data = _load_raw(bo_id)
        assert data.get('object_type') == 'view'
        assert (data.get('import_export') or {}).get('auto_crud') is False
        has_write = any(a.get('method') in ('POST', 'PUT', 'DELETE')
                        for a in (data.get('actions') or []))
        if bo_id == 'party_archive':
            # F1 §3.5 / §7.1-4：archive 为对外档案单入口，写经 write_anchor 转发锚
            assert data.get('write_anchor') == 'party'
            assert has_write, 'archive 应声明写动作（转发到 write_anchor）'
        else:
            # F1 §7.1-4：internal 无写锚 ⇒ 不得声明写动作
            assert not has_write, 'internal 只读面不得声明写动作'


# ────────────────────────────────────────
# 7. 建表与行为（端到端）
# ────────────────────────────────────────
class TestSchemaLands:
    def test_status_column_notnull_default(self, pst_ds):
        cols = {r[1]: r for r in pst_ds.execute(
            'PRAGMA table_info(parties)').fetchall()}
        assert 'status' in cols
        assert cols['status'][3] == 1, 'status 未设 NOT NULL'
        assert cols['status'][4] == "'active'"

    def test_status_index_created(self, pst_ds):
        names = {r[1] for r in pst_ds.execute(
            "PRAGMA index_list('parties')").fetchall()}
        assert 'idx_party_status' in names

    def test_facets_created_as_views(self, pst_ds):
        kinds = {r[0] for r in pst_ds.execute(
            "SELECT type FROM sqlite_master WHERE name IN "
            "('party_archive', 'party_internal')").fetchall()}
        assert kinds == {'view'}

    def test_default_status_on_insert(self, pst_ds):
        """省略 status 时落 active（默认值生效）"""
        pst_ds.insert('parties', {'code': 'PST-A', 'name': '外部甲',
                                  'party_type': 'organization'})
        row = pst_ds.execute(
            "SELECT status FROM parties WHERE code = 'PST-A'").fetchone()
        assert row[0] == 'active'

    def test_explicit_inactive_allowed(self, pst_ds):
        pst_ds.insert('parties', {'code': 'PST-B', 'name': '外部乙',
                                  'party_type': 'organization',
                                  'status': 'inactive'})
        row = pst_ds.execute(
            "SELECT status FROM parties WHERE code = 'PST-B'").fetchone()
        assert row[0] == 'inactive'

    def test_archive_facet_reads_status(self, pst_ds):
        # 夹具 function-scoped，用例间不共享数据 ⇒ 本用例自备两行
        pst_ds.insert('parties', {'code': 'PST-A', 'name': '外部甲',
                                  'party_type': 'organization'})
        pst_ds.insert('parties', {'code': 'PST-C', 'name': '外部丙',
                                  'party_type': 'organization',
                                  'status': 'inactive'})
        got = dict(pst_ds.execute(
            "SELECT code, status FROM party_archive "
            "WHERE code IN ('PST-A', 'PST-C') ORDER BY code").fetchall())
        assert got == {'PST-A': 'active', 'PST-C': 'inactive'}

    def test_internal_facet_reads_status(self, pst_ds):
        """内部行同样可停用，且 internal 面出口径"""
        pst_ds.insert('parties', {'code': 'PST-D', 'name': '内部表示',
                                  'party_type': 'organization',
                                  'source': 'org', 'org_id': 1,
                                  'status': 'inactive'})
        row = pst_ds.execute(
            "SELECT status FROM party_internal WHERE code = 'PST-D'"
        ).fetchone()
        assert row[0] == 'inactive'

    def test_status_index_filters(self, pst_ds):
        pst_ds.insert('parties', {'code': 'PST-A', 'name': '外部甲',
                                  'party_type': 'organization'})
        pst_ds.insert('parties', {'code': 'PST-E', 'name': '外部丁',
                                  'party_type': 'organization',
                                  'status': 'inactive'})
        codes = [r[0] for r in pst_ds.execute(
            'SELECT code FROM parties WHERE status = ? ORDER BY code',
            ('inactive',)).fetchall()]
        assert 'PST-E' in codes
        assert 'PST-A' not in codes

    def test_org_fk_still_enforced(self, pst_ds):
        """加 status 不得削弱既有真外键（org_id → orgs.id）"""
        with pytest.raises(Exception):
            pst_ds.insert('parties', {'code': 'PST-X', 'name': '孤儿行',
                                      'party_type': 'organization',
                                      'source': 'org', 'org_id': 999,
                                      'status': 'active'})