# -*- coding: utf-8 -*-
"""foundation 生命周期（status + activate/deactivate）接线测试 (2026-10-07)

H3 拍板（2026-10-07 主数据系统性检查处置）补拍对象:
- party_group / item_group : 分类对象补两态（停用后不进入新挂靠候选；已挂靠保留）
- party_relation           : 只补关系层（停用 = 该法人范围冻结/复通；账户层不重复建）
- org                      : 两态（§5.4 原「org 沿用现有（状态集待定）」由此关闭）

依据: docs/superpowers/specs/2026-10-04-foundation-object-model-and-architecture.md
      §5.4（主数据生命周期统一约定：最小 active/inactive → activate/deactivate）
      §3.4.8 D4（停用语义 = 瞬时开关 + 不加生效日列）
      检查报告 2026-10-07-master-data-systematic-review.md §五 B1/B2/A7 + §六 H3

覆盖:
1. status 字段   : required + default active + 两态枚举（无第三态；is_initial=[active]）
2. 无生效日列    : D4 硬判据（inactive_date / end_date 等一律禁止）
3. 状态机定义    : activate_/deactivate_ 两条互逆，action_ref 取自标准动作池，
                   不取 freeze/unfreeze；lock/unlock 为 user 专属（D9）
4. 索引          : idx_<obj>_status 随建表落
5. UI 接线       : 有列表配置的 3 对象（party_group/item_group/org）list/form/detail 含 status；
                   party_relation skip_auto_menu 无列表接线需求
6. 建表与行为   : 临时库真实建表 → 4 表默认值 / 显式 inactive / 状态过滤 / FK 不削弱

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

# D4：停用不加生效日列 —— 这些列名一旦出现即违规
_FORBIDDEN_DATE_COLS = ('inactive_date', 'disable_date', 'end_date',
                        'deactivate_date', 'status_date')

# 4 个 H3 对象: bo_id / 表 / 索引 / 两条规则 / 建表探针值
_OBJECTS = [
    {'bo': 'party_group', 'table': 'party_groups',
     'activate': 'activate_party_group', 'deactivate': 'deactivate_party_group',
     'idx': 'idx_party_group_status',
     'insert': {'code': 'H3-A', 'name': '探针甲', 'role_scope': 'customer'},
     'insert_b': {'code': 'H3-B', 'name': '探针乙', 'role_scope': 'vendor'}},
    {'bo': 'item_group', 'table': 'item_groups',
     'activate': 'activate_item_group', 'deactivate': 'deactivate_item_group',
     'idx': 'idx_item_group_status',
     'insert': {'code': 'H3-A', 'name': '探针甲'},
     'insert_b': {'code': 'H3-B', 'name': '探针乙'}},
    {'bo': 'party_relation', 'table': 'party_relations',
     'activate': 'activate_party_relation', 'deactivate': 'deactivate_party_relation',
     'idx': 'idx_party_relation_status',
     'insert': {'party1_id': 1, 'party2_id': 2, 'role': 'customer',
                'internal_mark': 'external'},
     'insert_b': {'party1_id': 1, 'party2_id': 2, 'role': 'vendor',
                  'internal_mark': 'external'}},
    {'bo': 'org', 'table': 'orgs',
     'activate': 'activate_org', 'deactivate': 'deactivate_org',
     'idx': 'idx_org_status',
     'insert': {'code': 'H3-A', 'name': '探针甲', 'org_type': 'department',
                'org_scope': 'internal'},
     'insert_b': {'code': 'H3-B', 'name': '探针乙', 'org_type': 'team',
                  'org_scope': 'internal'}},
]
_IDS = [c['bo'] for c in _OBJECTS]
_UI_OBJECTS = ('party_group', 'item_group', 'org')  # party_relation 无列表（skip_auto_menu）

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _case(bo):
    for c in _OBJECTS:
        if c['bo'] == bo:
            return c
    raise KeyError(bo)


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


def _row(ds, table, values, id_val, status=None):
    """按 PRAGMA 全列构造插入行:
    - *_id 列未显式给值时置 None（避免误触 FK）
    - status 缺省不传（测 DB 默认值）
    """
    cols = [r[1] for r in ds.execute('PRAGMA table_info(%s)' % table).fetchall()]
    row = {}
    for c in cols:
        if c == 'status':
            continue
        if c in values:
            row[c] = values[c]
        elif c == 'id':
            row[c] = id_val
        elif c.endswith('_id'):
            row[c] = None
        else:
            row[c] = 'PROBE'  # 非约束列哨兵值（SQLite 动态类型）
    if status is not None:
        row['status'] = status
    return row


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture()
def h3_ds(tmp_path):
    """临时库: 5 对象建表（org / party / party_group / item_group / party_relation）

    父行: orgs id=1（parties.org_id FK 目标）+ parties id=1/2（party_relations FK 目标）。
    """
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml
    from meta.core.models import registry

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    objs = []
    for fn in ('org.yaml', 'party.yaml', 'party_group.yaml', 'item_group.yaml',
               'party_relation.yaml'):
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, fn), aspects_defs=aspects)
        assert obj is not None, 'YAML 加载失败: %s' % fn
        if registry.get(obj.id) is None:
            registry.register(obj)      # 保 FK 目标解析确定
        objs.append(obj)

    ds = get_data_source('sqlite', database=str(tmp_path / 'h3_status.db'))
    sync_schema_from_meta(ds, objs)

    ds.insert('orgs', _row(ds, 'orgs', {'code': 'ORG-PROBE', 'name': '探针组织',
                                        'org_type': 'company',
                                        'org_scope': 'internal'}, 1))
    for pid, code in ((1, 'PT-1'), (2, 'PT-2')):
        ds.insert('parties', _row(ds, 'parties', {'code': code,
                                                  'name': '外部%s' % pid,
                                                  'party_type': 'organization'},
                                  pid))
    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 1+2. status 字段（§5.4 最小两态）+ D4 无生效日列
# ────────────────────────────────────────
class TestStatusField:
    @pytest.mark.parametrize('bo', _IDS)
    def test_status_exists_required_default(self, bo):
        f = _field(_load_raw(bo), 'status')
        assert f is not None, '%s.status 缺失（H3 补拍对象）' % bo
        assert f['type'] == 'string'
        assert f['db_column'] == 'status'
        assert f['required'] is True
        assert f.get('default') == 'active'

    @pytest.mark.parametrize('bo', _IDS)
    def test_two_states_only_with_initial(self, bo):
        """最小两态 active/inactive；初态唯一 = active"""
        enums = _field(_load_raw(bo), 'status')['enum_values']
        assert {e['value'] for e in enums} == {'active', 'inactive'}
        initial = [e['value'] for e in enums if e.get('is_initial')]
        assert initial == ['active']

    @pytest.mark.parametrize('bo', _IDS)
    def test_status_filterable(self, bo):
        sem = _field(_load_raw(bo), 'status').get('semantics') or {}
        assert sem.get('filterable') is True
        assert sem.get('filter_type') == 'enum'

    @pytest.mark.parametrize('bo', _IDS)
    def test_no_effective_date_column(self, bo):
        ids = {f['id'] for f in _load_raw(bo)['fields']}
        for bad in _FORBIDDEN_DATE_COLS:
            assert bad not in ids, 'D4 禁生效日列，但 %s 出现 %s' % (bo, bad)

    @pytest.mark.parametrize('bo', _IDS)
    def test_transient_switch_documented(self, bo):
        desc = _field(_load_raw(bo), 'status').get('description') or ''
        assert 'D4' in desc and '生效日' in desc

    @pytest.mark.parametrize('bo', _IDS)
    def test_status_index_declared(self, bo):
        idx = _load_raw(bo).get('indexes') or []
        assert {'fields': ['status'], 'name': _case(bo)['idx']} in idx


# ────────────────────────────────────────
# 3. 状态机（复用平台标准动作）
# ────────────────────────────────────────
class TestStateMachine:
    @pytest.mark.parametrize('bo', _IDS)
    def test_exactly_two_transitions(self, bo):
        rules = _rules(_load_raw(bo))
        case = _case(bo)
        assert set(rules) == {case['activate'], case['deactivate']}

    @pytest.mark.parametrize('bo', _IDS)
    def test_transitions_inverse(self, bo):
        rules = _rules(_load_raw(bo))
        case = _case(bo)
        act, deact = rules[case['activate']], rules[case['deactivate']]
        assert act['action_ref'] == 'activate'
        assert act['state_field'] == 'status'
        assert act['from_states'] == ['inactive']
        assert act['to_state'] == 'active'
        assert deact['action_ref'] == 'deactivate'
        assert deact['state_field'] == 'status'
        assert deact['from_states'] == ['active']
        assert deact['to_state'] == 'inactive'
        assert act['from_states'] == [deact['to_state']]
        assert deact['from_states'] == [act['to_state']]
        assert 'before_update' in act['triggers']
        assert 'before_update' in deact['triggers']

    @pytest.mark.parametrize('bo', _IDS)
    def test_action_refs_in_standard_pool(self, bo):
        """action_ref 必须取自平台标准动作池（_standard_actions.yaml）"""
        pool = {a['id'] for a in _load_raw('_standard_actions')['standard_actions']}
        for r in _rules(_load_raw(bo)).values():
            assert r['action_ref'] in pool, \
                '%s 的 %s 不在标准动作池' % (bo, r['action_ref'])

    @pytest.mark.parametrize('bo', _IDS)
    def test_no_freeze_or_lock_actions(self, bo):
        """两态两动作：不取 freeze/unfreeze；lock/unlock 为 user 专属（D9）"""
        refs = {r.get('action_ref') for r in _rules(_load_raw(bo)).values()}
        assert not (refs & {'lock', 'unlock', 'freeze', 'unfreeze'}), refs


# ────────────────────────────────────────
# 4. 对象特定口径
# ────────────────────────────────────────
class TestObjectSpecific:
    def test_relation_status_scoped_to_legal_entity(self):
        """关系层停用粒度 = 法人域（对手在法人 A 停用、法人 B 继续交易）"""
        desc = _field(_load_raw('party_relation'), 'status').get('description') or ''
        assert '法人' in desc

    def test_group_inactive_not_in_candidate(self):
        """分类对象停用口径：不进入新挂靠候选；已挂靠保留"""
        for bo in ('party_group', 'item_group'):
            enums = _field(_load_raw(bo), 'status')['enum_values']
            inactive = [e for e in enums if e['value'] == 'inactive'][0]
            text = (inactive.get('description') or '') + \
                (inactive.get('label') or '')
            assert '停用' in text, bo


# ────────────────────────────────────────
# 5. UI 接线（有列表配置的对象）
# ────────────────────────────────────────
class TestUiWiring:
    @pytest.mark.parametrize('bo', _UI_OBJECTS)
    def test_status_in_list_columns(self, bo):
        cols = ((_load_raw(bo).get('ui_view_config') or {}).get('list') or {}) \
            .get('columns') or []
        assert any(c.get('field') == 'status' for c in cols), \
            '%s 列表缺 status 列' % bo

    @pytest.mark.parametrize('bo', _UI_OBJECTS)
    def test_status_in_form(self, bo):
        sections = ((_load_raw(bo).get('ui_view_config') or {}).get('form') or {}) \
            .get('sections') or []
        fields = [f for s in sections for col in (s.get('columns') or [])
                  for f in (col.get('fields') or [])]
        assert 'status' in fields, '%s 表单缺 status' % bo

    @pytest.mark.parametrize('bo', _UI_OBJECTS)
    def test_status_in_detail(self, bo):
        tabs = ((_load_raw(bo).get('ui_view_config') or {}).get('detail') or {}) \
            .get('tabs') or []
        fields = [f for t in tabs for f in (t.get('fields') or [])]
        assert 'status' in fields, '%s 详情缺 status' % bo

    def test_party_relation_has_no_list_config(self):
        """关系层无自动菜单（skip_auto_menu），无列表接线需求"""
        uic = _load_raw('party_relation').get('ui_view_config') or {}
        assert uic.get('skip_auto_menu') is True
        assert 'list' not in uic


# ────────────────────────────────────────
# 6. 建表与行为（端到端）
# ────────────────────────────────────────
class TestSchemaLands:
    @pytest.mark.parametrize('bo', _IDS)
    def test_status_column_notnull_default(self, h3_ds, bo):
        table = _case(bo)['table']
        cols = {r[1]: r for r in h3_ds.execute(
            'PRAGMA table_info(%s)' % table).fetchall()}
        assert 'status' in cols, '%s 缺 status 列' % table
        assert cols['status'][3] == 1, '%s.status 未设 NOT NULL' % table
        assert cols['status'][4] == "'active'"

    @pytest.mark.parametrize('bo', _IDS)
    def test_status_index_created(self, h3_ds, bo):
        case = _case(bo)
        names = {r[1] for r in h3_ds.execute(
            "PRAGMA index_list('%s')" % case['table']).fetchall()}
        assert case['idx'] in names

    @pytest.mark.parametrize('bo', _IDS)
    def test_default_and_explicit_inactive(self, h3_ds, bo):
        """省略 status 落 active（默认值生效）；显式 inactive 可写入"""
        case = _case(bo)
        h3_ds.insert(case['table'], _row(h3_ds, case['table'],
                                         case['insert'], 101))
        h3_ds.insert(case['table'], _row(h3_ds, case['table'],
                                         case['insert_b'], 102,
                                         status='inactive'))
        got = dict(h3_ds.execute(
            'SELECT id, status FROM %s WHERE id IN (101, 102)' % case['table']
        ).fetchall())
        assert got == {101: 'active', 102: 'inactive'}

    def test_status_filter_works(self, h3_ds):
        """按状态过滤（停用不进入候选）"""
        case = _case('item_group')
        h3_ds.insert(case['table'], _row(h3_ds, case['table'], case['insert'], 101))
        h3_ds.insert(case['table'], _row(h3_ds, case['table'], case['insert_b'],
                                         102, status='inactive'))
        active = [r[0] for r in h3_ds.execute(
            "SELECT id FROM item_groups WHERE status = 'active'").fetchall()]
        assert active == [101]

    def test_relation_fk_still_enforced(self, h3_ds):
        """加 status 不得削弱既有真外键（party_relations.party1_id → parties.id）"""
        case = _case('party_relation')
        bad = dict(case['insert'])
        bad['party1_id'] = 999
        with pytest.raises(Exception):
            h3_ds.insert(case['table'], _row(h3_ds, case['table'], bad, 103))


# ────────────────────────────────────────
# 7. org 自引用外键（FK 2026-10-08 · M1/B3 同类不一致修复）
# ────────────────────────────────────────
class TestOrgParentFkWiring:
    """org.parent_id 补对象级relations 声明 → 真外键落地。

    根因: org.yaml 的relations 原为 []，字段级 semantics.hierarchy_level
    .relation: self_reference 只表达 UI/层级语义；落库器只认 relations[].type
    ∈ (parent_child|reference) 且 reference 必带 source_field
    ⇒ parent_id 一直未落成真 FK，与 party_group/item_group/location/
    region/calendar 五处同类声明不一致（M1/B3 检查项）。
    """

    def test_yaml_declares_object_level_relation(self):
        """org.yaml 必须有对象级自引用声明且带 source_field（落库器硬条件）"""
        rels = _load_raw('org')['relations']
        assert isinstance(rels, list) and rels, 'org.relations 不得为空'
        decl = [r for r in rels
                if r.get('source_field') == 'parent_id'
                and r.get('target') == 'org']
        assert decl, '缺 parent_id → org 的自引用声明'
        assert decl[0].get('type') in ('reference', 'parent_child')

    def test_field_hierarchy_semantics_retained(self):
        """字段级自引用语义须保留（层级树/防环/弹窗依赖它）"""
        f = _field(_load_raw('org'), 'parent_id')
        assert f['semantics']['hierarchy_level']['relation'] == 'self_reference'
        assert f['semantics']['display']['type'] == 'association'
        assert f['semantics']['display']['target_type'] == 'org'

    def test_manager_id_not_declared(self):
        """manager_id 是已废弃死功能（v088 FR-011 完成）⇒ 刻意不建 FK"""
        rels = _load_raw('org')['relations']
        assert not [r for r in rels if r.get('source_field') == 'manager_id']

    def test_parent_id_landed_as_real_fk(self, h3_ds):
        """落库后 orgs 表 parent_id 必须是真外键"""
        fks = h3_ds.execute('PRAGMA foreign_key_list(orgs)').fetchall()
        assert [f for f in fks if f[3] == 'parent_id' and f[2] == 'orgs'], \
            'orgs.parent_id 未落成真外键'

    def test_orphan_parent_rejected(self, h3_ds):
        """孤儿 parent_id 必须被拒（约束真强制，非仅声明）"""
        row = _row(h3_ds, 'orgs', _case('org')['insert'], 201)
        row['parent_id'] = 999999
        with pytest.raises(Exception):
            h3_ds.insert('orgs', row)

    def test_valid_parent_accepted(self, h3_ds):
        """合法 parent_id 可写入（约束不误伤）+ NULL 根节点放行"""
        case = _case('org')
        h3_ds.insert('orgs', _row(h3_ds, 'orgs', case['insert'], 202))
        child = dict(case['insert'])
        child['parent_id'] = 202
        child['code'] = 'H3-A-CHILD'   # code 有 UNIQUE 约束，逐行取不同值
        h3_ds.insert('orgs', _row(h3_ds, 'orgs', child, 203))
        got = dict(h3_ds.execute(
            'SELECT id, parent_id FROM orgs WHERE id IN (202, 203)').fetchall())
        assert got == {202: None, 203: 202}

    def test_self_reference_chain_readable(self, h3_ds):
        """自引用三级链可读回（UI 组织树弹窗的数据基础）"""
        case = _case('org')
        h3_ds.insert('orgs', _row(h3_ds, 'orgs', case['insert'], 204))
        mid = dict(case['insert'])
        mid['parent_id'] = 204
        mid['code'] = 'H3-A-MID'
        h3_ds.insert('orgs', _row(h3_ds, 'orgs', mid, 205))
        leaf = dict(case['insert'])
        leaf['parent_id'] = 205
        leaf['code'] = 'H3-A-LEAF'
        h3_ds.insert('orgs', _row(h3_ds, 'orgs', leaf, 206))
        got = dict(h3_ds.execute(
            'SELECT id, parent_id FROM orgs WHERE id IN (204, 205, 206)'
        ).fetchall())
        assert got == {204: None, 205: 204, 206: 205}