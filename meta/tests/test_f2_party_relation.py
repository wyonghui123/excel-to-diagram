# -*- coding: utf-8 -*-
"""F2 · 关系实例（party_relation）命名与唯一键测试 (2026-10-05)

依据: docs/superpowers/specs/2026-10-05-f2-party-relationship-naming-and-identifier.md
      (§10 D4 命名 / D5 键与唯一约束 / D6 不建独立号 / D7 禁忌词)；蓝图 v2.5 §3.3 / §4.3

覆盖:
1. 命名 (D4) : 技术标识 party_relation / 物理表 party_relations；禁用词 relationship / role·roles / product
2. 结构      : 字段 id / party1_id / party2_id / role / internal_mark / le_org_id
3. 枚举      : role = {customer, vendor}；internal_mark = {internal, external}
4. D6        : 不建 code，无 key_template
5. D5        : 四元组 (party1_id, party2_id, role, le_org_id) 部分唯一索引；le_org_id 非空参与唯一；internal_mark 不入键
6. 建表/强制 : sync_schema_from_meta 建出表与部分唯一索引；四元组重复被拒、internal_mark 不影响唯一、le_org_id 为空可重复

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db;
         DML 走 ds.insert API（本文件无裸写语句 —— conftest raw-SQL 守卫）
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.factories._raw_sql_bridge import insert

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

_FORBIDDEN = ('relationship', 'role', 'roles', 'product')

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_yaml():
    import yaml
    with open(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _fields():
    return {f['id']: f for f in _load_yaml()['fields']}


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture()
def pr_ds(tmp_path):
    """临时库: party_relations 表 + 索引 + 父表 parties / orgs / party_groups

    [FK 2026-10-07] party_relations 三条真外键（party1_id / party2_id →
    parties、le_org_id → orgs）落地，单表库须补父表与父行。
    [FK 2026-10-07 / party_group] 新增第四条 group_id → party_groups，
    用例不挂组（group_id 恒 NULL），仅需建父表本体。
    """
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file

    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
    assert obj is not None, 'party_relation.yaml 加载失败'

    ds = get_data_source("sqlite", database=str(tmp_path / 'f2_party_relation.db'))
    sync_schema_from_meta(ds, [obj])
    # 最小父表 + 父行（用例中 party 用 1–8、le_org 用 10/20/30/31）
    # [internal_mark 派生] parties 需带 source 列：派生口径为 source='org' ⇒ internal。
    ds.execute("CREATE TABLE IF NOT EXISTS parties "
               "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, source TEXT)")
    ds.execute("CREATE TABLE IF NOT EXISTS orgs "
               "(id INTEGER PRIMARY KEY AUTOINCREMENT)")
    ds.execute("CREATE TABLE IF NOT EXISTS party_groups "
               "(id INTEGER PRIMARY KEY AUTOINCREMENT)")
    for pid in range(1, 9):
        insert(ds, 'parties', id=pid, name='单位%d' % pid,
               source='org' if pid == 1 else None)
    for oid in (10, 20, 30, 31):
        insert(ds, 'orgs', id=oid)
    yield ds
    _clear_data_source_cache_for_testing()


def _row(party1, party2, role, le_org_id, mark='external'):
    return {
        'id': _row.n,
        'party1_id': party1,
        'party2_id': party2,
        'role': role,
        'internal_mark': mark,
        'le_org_id': le_org_id,
    }


_row.n = 0


def _next_row(ds, party1, party2, role, le_org_id, mark='external'):
    _row.n += 1
    ds.insert('party_relations', _row(party1, party2, role, le_org_id, mark))


# ────────────────────────────────────────
# 1. 命名（§10 D4）
# ────────────────────────────────────────
class TestNaming:
    def test_technical_id_and_table(self):
        data = _load_yaml()
        assert data['id'] == 'party_relation'
        assert data['table_name'] == 'party_relations'

    def test_no_forbidden_names(self):
        """D7 禁忌词：不得用 relationship（meta 关系 BO 已占用）等"""
        data = _load_yaml()
        assert data['id'] not in _FORBIDDEN
        assert data['table_name'] not in _FORBIDDEN
        assert not data['id'].startswith('product')


# ────────────────────────────────────────
# 2. 结构（蓝图 §3.3）
# ────────────────────────────────────────
class TestStructure:
    def test_required_fields_present(self):
        fields = _fields()
        for fid in ('id', 'party1_id', 'party2_id', 'role', 'internal_mark', 'le_org_id'):
            assert fid in fields, '结构字段缺失: %s' % fid

    def test_party_refs_are_required_integers(self):
        fields = _fields()
        for fid in ('party1_id', 'party2_id'):
            f = fields[fid]
            assert f['type'] == 'integer'
            assert f['required'] is True


# ────────────────────────────────────────
# 3. 枚举（D4 role；I3-A internal_mark）
# ────────────────────────────────────────
class TestEnums:
    def test_role_values(self):
        vals = {e['value'] for e in _fields()['role']['enum_values']}
        assert vals == {'customer', 'vendor'}

    def test_internal_mark_values(self):
        vals = {e['value'] for e in _fields()['internal_mark']['enum_values']}
        assert vals == {'internal', 'external'}


# ────────────────────────────────────────
# 3b. internal_mark 由系统派生（不人工录入）
# ────────────────────────────────────────
class TestInternalMarkDerived:
    def test_not_in_create_form(self):
        sections = _load_yaml()['ui_view_config']['form']['sections']
        ids = [fid for s in sections
               for c in (s.get('columns') or []) for fid in c.get('fields', [])]
        assert 'internal_mark' not in ids

    def test_readonly_display_kept(self):
        facets = _load_yaml()['ui_view_config']['detail']['facets']
        ids = [fid for fc in facets for fid in fc.get('fields', [])]
        assert 'internal_mark' in ids
        ui = _fields()['internal_mark']['ui']
        assert ui['editable'] is False
        assert ui['readonly'] is True
        assert 'readonly_always' not in _fields()['internal_mark'].get('semantics', {})

    def test_not_importable(self):
        assert _fields()['internal_mark']['semantics']['import_visible'] is False

    def test_derive_by_party_source(self, pr_ds):
        from meta.services.party_relation_guard_service import PartyRelationGuardService
        svc = PartyRelationGuardService(pr_ds)
        # party 1 是 source='org' 的内部组织表示
        assert svc.derive_internal_mark({'party2_id': 1})['internal_mark'] == 'internal'
        # 其余 source 为 NULL ⇒ 对外
        assert svc.derive_internal_mark({'party2_id': 2})['internal_mark'] == 'external'

    def test_client_value_discarded(self, pr_ds):
        from meta.services.party_relation_guard_service import PartyRelationGuardService
        svc = PartyRelationGuardService(pr_ds)
        data = svc.derive_internal_mark({'party2_id': 3, 'internal_mark': 'internal'})
        assert data['internal_mark'] == 'external'

    def test_no_party2_drops_client_value(self, pr_ds):
        from meta.services.party_relation_guard_service import PartyRelationGuardService
        data = PartyRelationGuardService(pr_ds).derive_internal_mark(
            {'party1_id': 1, 'internal_mark': 'internal'})
        assert 'internal_mark' not in data

    def test_hook_applied_only_to_registered_object(self, pr_ds):
        from meta.core.consistency_guard import ComputedFieldHandler
        from meta.services.party_relation_guard_service import derive_internal_mark_hook
        ComputedFieldHandler.register_hook('party_relation', derive_internal_mark_hook)
        try:
            out = ComputedFieldHandler(pr_ds).on_before_save(
                'party_relation', {'party2_id': 1})
            assert out['internal_mark'] == 'internal'
            other = ComputedFieldHandler(pr_ds).on_before_save(
                'party', {'party2_id': 1})
            assert 'internal_mark' not in other
        finally:
            ComputedFieldHandler.clear_hooks()


# ────────────────────────────────────────
# 4. D6：不建独立识别号
# ────────────────────────────────────────
class TestNoIdentifier:
    def test_no_code_field(self):
        assert 'code' not in _fields()

    def test_no_key_template(self):
        assert not _load_yaml().get('key_template')


# ────────────────────────────────────────
# 5. D5：四元组部分唯一索引
# ────────────────────────────────────────
class TestUniqueKey:
    def _unique_indexes(self):
        return [i for i in (_load_yaml().get('indexes') or []) if i.get('unique')]

    def test_four_tuple_partial_unique(self):
        uniq = self._unique_indexes()
        assert len(uniq) == 1, '应恰有一个唯一索引'
        idx = uniq[0]
        assert idx['fields'] == ['party1_id', 'party2_id', 'role', 'le_org_id']
        assert idx.get('type') == 'partial'
        assert idx.get('condition') == 'le_org_id IS NOT NULL'

    def test_internal_mark_not_in_key(self):
        for idx in self._unique_indexes():
            assert 'internal_mark' not in idx['fields']


# ────────────────────────────────────────
# 7. [分区落点 2026-10-22] 客户档案 / 供应商档案进本详情页
# ────────────────────────────────────────
class TestAccountSections:
    """档案从独立菜单收进本详情页的关联分区（方案 A）

    落点理由：档案挂 party_relation 之上 1:1（relation_id 唯一），是关系侧属性
    而非与 party 并列的主体实体；本对象自己的独立菜单已于 2026-10-17 同款下架。
    """

    def _sections(self):
        facets = _load_yaml()['ui_view_config']['detail']['facets']
        return [f for f in facets if f.get('type') == 'association']

    def test_two_account_sections_declared(self):
        assert {s['association'] for s in self._sections()} == {
            'customer_account', 'vendor_account'}

    def test_use_custom_fetcher_not_platform_assoc(self):
        """必须走自定义取数器：associationFilters 过滤列写死 `{父对象类型}_id`，
        本对象会得 party_relation_id，而两个档案表的列名是 relation_id；
        列名不匹配时后端忽略条件返回全量 ⇒ 一个关系页列出所有人的档案。"""
        for s in self._sections():
            assert s['customFetcher'] == 'relation_accounts'

    def test_no_platform_association_declared(self):
        """分区不依赖 associations 声明（走自定义取数器，不占平台关联名）"""
        names = {a['name'] for a in (_load_yaml().get('associations') or [])}
        assert 'customer_account' not in names
        assert 'vendor_account' not in names

    def test_readonly_with_create_action(self):
        """行只读（1:1 明细，编辑走弹窗），但保留 create 入口"""
        for s in self._sections():
            assert s['readonly'] is True
            keys = {a['key'] for a in s['actions']}
            assert keys == {'create'}

    def test_create_permission_is_two_segment(self):
        for s in self._sections():
            create = next(a for a in s['actions'] if a['key'] == 'create')
            assert create['permission'] == \
                f"{s['association']}:{s['association']}_create"

    def test_both_sections_always_rendered(self):
        """两侧分区恒声明（不按父行 role 隐藏）—— role 可编辑，
        隐藏会让改完 role 后该侧分区立刻消失、用户失去入口。"""
        assert len(self._sections()) == 2


# ────────────────────────────────────────
# 6. 建表与唯一约束强制（端到端）
# ────────────────────────────────────────
class TestUniqueEnforced:
    def test_index_created(self, pr_ds):
        names = {r[1] for r in pr_ds.execute(
            "PRAGMA index_list('party_relations')").fetchall()}
        assert 'idx_party_relation_unique' in names

    def test_duplicate_four_tuple_rejected(self, pr_ds):
        _next_row(pr_ds, 1, 2, 'customer', 10)
        with pytest.raises(Exception):
            _next_row(pr_ds, 1, 2, 'customer', 10)

    def test_internal_mark_not_part_of_key(self, pr_ds):
        """internal_mark 不入键 ⇒ 同四元组仅改标记仍冲突"""
        _next_row(pr_ds, 3, 4, 'vendor', 20, mark='external')
        with pytest.raises(Exception):
            _next_row(pr_ds, 3, 4, 'vendor', 20, mark='internal')

    def test_different_role_or_le_org_id_allowed(self, pr_ds):
        _next_row(pr_ds, 5, 6, 'customer', 30)
        _next_row(pr_ds, 5, 6, 'vendor', 30)      # 双角色 = 两条实例
        _next_row(pr_ds, 5, 6, 'customer', 31)    # 不同域
        cnt = pr_ds.execute(
            'SELECT COUNT(*) FROM party_relations').fetchone()[0]
        assert cnt == 3

    def test_null_le_org_id_rows_not_in_key(self, pr_ds):
        """部分唯一索引: le_org_id 为空的行不入键 ⇒ 可重复"""
        _next_row(pr_ds, 7, 8, 'customer', None)
        _next_row(pr_ds, 7, 8, 'customer', None)
        cnt = pr_ds.execute(
            'SELECT COUNT(*) FROM party_relations').fetchone()[0]
        assert cnt == 2