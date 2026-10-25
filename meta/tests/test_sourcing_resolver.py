# -*- coding: utf-8 -*-
"""供应来源求值服务单测（SourcingResolver）。

[定位] 只测 `meta/services/sourcing_service.py` 的五步口径：选规则 / 解析
供应方式 / 资格过滤 / 排序取源 / 校验配置。API 契约由
`test_sourcing_api.py` 覆盖。

[数据构造] 全部直接写库（不经拦截器），故 specificity_rank 显式写入；
DDL 用最小列集，避免依赖 schema 生成器的顺序与全量注册。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.services.sourcing_service import (  # noqa: E402
    ALLOCATION_NOT_100,
    ALL_LINES_INELIGIBLE,
    ASSIGNMENT_CONFLICT,
    MODE_CONFLICT,
    NO_ASSIGNMENT,
    SOURCE_REF_MISMATCH,
    SourcingError,
    SourcingResolver,
)
from meta.tests.factories._raw_sql_bridge import insert, update  # noqa: E402

DAY = '2026-10-24'

# 最小 DDL：列名与 meta/schemas/*.yaml 的 db_column 一致
DDL = [
    "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " item_group_id INTEGER)",
    "CREATE TABLE item_groups (id INTEGER PRIMARY KEY AUTOINCREMENT)",
    "CREATE TABLE orgs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " parent_id INTEGER, status TEXT)",
    "CREATE TABLE org_functions (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " org_id INTEGER, function_type TEXT, is_primary INTEGER DEFAULT 0,"
    " effective_from TEXT, effective_to TEXT)",
    "CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT)",
    "CREATE TABLE party_relations (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " party1_id INTEGER, party2_id INTEGER, role TEXT, status TEXT)",
    "CREATE TABLE sourcing_rules (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " code TEXT, name TEXT, rule_usage TEXT, effectivity_start TEXT,"
    " effectivity_end TEXT, status TEXT, description TEXT,"
    " created_at TEXT, updated_at TEXT)",
    "CREATE TABLE sourcing_rule_lines (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " rule_id INTEGER, seq INTEGER, source_type TEXT, source_org_id INTEGER,"
    " source_location_id INTEGER, supplier_party_id INTEGER, rank INTEGER,"
    " allocation_pct REAL, blocked INTEGER DEFAULT 0,"
    " fixed INTEGER DEFAULT 0, effectivity_start TEXT, effectivity_end TEXT,"
    " note TEXT, created_at TEXT, updated_at TEXT)",
    "CREATE TABLE sourcing_rule_assignments (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " rule_id INTEGER, scope_type TEXT, scope_ref_id INTEGER,"
    " dest_org_id INTEGER, dest_location_id INTEGER,"
    " specificity_rank INTEGER, seq INTEGER, effectivity_start TEXT,"
    " effectivity_end TEXT, status TEXT, created_at TEXT, updated_at TEXT)",
    "CREATE TABLE sourcing_mode_policies (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " item_group_id INTEGER, item_id INTEGER, org_id INTEGER, mode TEXT,"
    " status TEXT, created_at TEXT, updated_at TEXT)",
]


@pytest.fixture()
def ds(tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter

    adapter = SQLiteAdapter()
    adapter.connect(path=str(tmp_path / "sourcing.db"))
    for ddl in DDL:
        adapter.execute(ddl)
    yield adapter
    adapter.disconnect()


# ----------------------------------------------------------------------
# 造数助手
# ----------------------------------------------------------------------
def _org(ds, org_id, parent_id=None, status='active'):
    insert(ds, 'orgs', id=org_id, parent_id=parent_id, status=status)
    return org_id


def _func(ds, org_id, function_type, start='2000-01-01', end=None):
    insert(ds, 'org_functions', org_id=org_id,
           function_type=function_type, is_primary=0,
           effective_from=start, effective_to=end)


def _item(ds, item_id, group_id=None):
    insert(ds, 'items', id=item_id, item_group_id=group_id)
    return item_id


def _rule(ds, code, usage='all', start='2020-01-01', end=None,
          status='active'):
    return insert(ds, 'sourcing_rules', code=code, name=code,
                  rule_usage=usage, effectivity_start=start,
                  effectivity_end=end, status=status).lastrowid


def _assign(ds, rule_id, scope_type='item', ref_id=None, dest_org_id=1,
            dest_location_id=None, rank=30, seq=1, start='2020-01-01',
            end=None, status='active'):
    return insert(ds, 'sourcing_rule_assignments', rule_id=rule_id,
                  scope_type=scope_type, scope_ref_id=ref_id,
                  dest_org_id=dest_org_id,
                  dest_location_id=dest_location_id,
                  specificity_rank=rank, seq=seq,
                  effectivity_start=start, effectivity_end=end,
                  status=status).lastrowid


def _line(ds, rule_id, seq, source_type, rank=1, allocation_pct=100,
          blocked=0, fixed=0, start='2020-01-01', end=None,
          source_org_id=None, source_location_id=None,
          supplier_party_id=None):
    return insert(ds, 'sourcing_rule_lines', rule_id=rule_id, seq=seq,
                  source_type=source_type, source_org_id=source_org_id,
                  source_location_id=source_location_id,
                  supplier_party_id=supplier_party_id, rank=rank,
                  allocation_pct=allocation_pct, blocked=blocked,
                  fixed=fixed, effectivity_start=start,
                  effectivity_end=end).lastrowid


def _mode(ds, org_id, mode, group_id=7, item_id=None, status='active'):
    insert(ds, 'sourcing_mode_policies', item_group_id=group_id,
           item_id=item_id, org_id=org_id, mode=mode, status=status)


def _vendor(ds, party_id, status='active'):
    insert(ds, 'party_relations', party1_id=party_id, party2_id=0,
           role='vendor', status=status)


def _spec(item_id=100, dest_org_id=1, usage='fulfillment', **extra):
    spec = {'item_id': item_id, 'dest_org_id': dest_org_id,
            'usage': usage, 'date': DAY}
    spec.update(extra)
    return spec


def _resolve(ds, spec):
    return SourcingResolver(ds).resolve(spec)


def _resolve_err(ds, spec):
    with pytest.raises(SourcingError) as excinfo:
        SourcingResolver(ds).resolve(spec)
    return excinfo.value


def _base(ds, item_id=100, group_id=7):
    """基础主数据：物料 + 目的组织 + 一个库存来源组织。"""
    _item(ds, item_id, group_id)
    _org(ds, 1)
    _org(ds, 91)
    _func(ds, 91, 'inventory')


# ----------------------------------------------------------------------
# ① 选规则：六档 specificity_rank
# ----------------------------------------------------------------------
class TestSpecificityRank:
    def test_six_ranks_in_priority_order(self, ds):
        _base(ds)
        rules = {}
        tiers = [
            ('item', 100, 1, 10),
            ('item_group', 7, 1, 20),
            ('item', 100, None, 30),
            ('item_group', 7, None, 40),
            ('global', None, 1, 50),
            ('global', None, None, 60),
        ]
        for scope_type, ref_id, dest_org_id, rank in tiers:
            rule_id = _rule(ds, 'R%d' % rank)
            _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
            _assign(ds, rule_id, scope_type=scope_type, ref_id=ref_id,
                    dest_org_id=dest_org_id, rank=rank)
            rules[rank] = rule_id

        # 由细到粗逐层验证：命中即胜出，停用后落到下一档
        for rank in (10, 20, 30, 40, 50, 60):
            out = _resolve(ds, _spec())
            assert out['rule_id'] == rules[rank]
            assert out['specificity_rank'] == rank
            update(ds, 'sourcing_rule_assignments', {'rule_id': rules[rank]},
                   status='inactive')

    def test_same_rank_then_seq_then_id(self, ds):
        _base(ds)
        first = _rule(ds, 'RA')
        second = _rule(ds, 'RB')
        third = _rule(ds, 'RC')
        for rule_id in (first, second, third):
            _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _assign(ds, first, scope_type='item_group', ref_id=7, rank=20, seq=1)
        _assign(ds, second, scope_type='item_group', ref_id=7, rank=20, seq=2)
        # 与 second 同 rank 同 seq，靠 id 决胜
        _assign(ds, third, scope_type='item_group', ref_id=7, rank=20, seq=2)

        assert _resolve(ds, _spec())['rule_id'] == first
        update(ds, 'sourcing_rule_assignments', {'rule_id': first},
               status='inactive')
        assert _resolve(ds, _spec())['rule_id'] == second
        update(ds, 'sourcing_rule_assignments', {'rule_id': second},
               status='inactive')
        assert _resolve(ds, _spec())['rule_id'] == third


# ----------------------------------------------------------------------
# ③ 资格过滤：blocked / 有效期 / 用途 / 不回退
# ----------------------------------------------------------------------
class TestLineEligibility:
    def test_blocked_and_expired_lines_are_dropped(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R1')
        blocked = _line(ds, rule_id, 1, 'internal_org', source_org_id=91,
                        blocked=1)
        expired = _line(ds, rule_id, 2, 'internal_org', source_org_id=91,
                        end='2026-01-01')
        good = _line(ds, rule_id, 3, 'internal_org', source_org_id=91)
        _assign(ds, rule_id, ref_id=100, rank=10)

        out = _resolve(ds, _spec())
        assert out['line_id'] == good
        dropped = {d['line_id']: d['reason'] for d in out['explain'][1]['dropped']}
        assert dropped == {blocked: 'blocked', expired: 'line_expired'}

    def test_usage_mismatch_means_no_assignment(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_BUY', usage='purchasing')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _assign(ds, rule_id, ref_id=100, rank=10)

        err = _resolve_err(ds, _spec(usage='fulfillment'))
        assert err.code == NO_ASSIGNMENT
        assert err.status_code == 422
        assert 'supply_mode' in err.extra

    def test_no_fallback_to_coarser_rule(self, ds):
        _base(ds)
        item_rule = _rule(ds, 'R_ITEM')
        _line(ds, item_rule, 1, 'internal_org', source_org_id=91, blocked=1)
        _assign(ds, item_rule, ref_id=100, rank=10)

        group_rule = _rule(ds, 'R_GROUP')
        _line(ds, group_rule, 1, 'internal_org', source_org_id=91)
        _assign(ds, group_rule, scope_type='item_group', ref_id=7, rank=20)

        err = _resolve_err(ds, _spec())
        assert err.code == ALL_LINES_INELIGIBLE
        # explain 里的命中必须是 item 级规则，且不回退
        assert err.extra['explain'][0]['hit']['rule_id'] == item_rule


# ----------------------------------------------------------------------
# ② 供应方式
# ----------------------------------------------------------------------
class TestSupplyMode:
    def test_make_only_accepts_production(self, ds):
        _base(ds)
        _org(ds, 92)
        _func(ds, 92, 'manufacturing')
        rule_id = _rule(ds, 'R_MAKE')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        production = _line(ds, rule_id, 2, 'production', source_org_id=92)
        _assign(ds, rule_id, ref_id=100, rank=10)
        _mode(ds, 1, 'make', group_id=7, item_id=100)

        out = _resolve(ds, _spec())
        assert out['supply_mode'] == 'make'
        assert out['source_type'] == 'production'
        assert out['source_org_id'] == 92
        assert out['line_id'] == production

    def test_buy_only_accepts_supplier(self, ds):
        _base(ds)
        _vendor(ds, 501)
        rule_id = _rule(ds, 'R_BUY')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        supplier = _line(ds, rule_id, 2, 'supplier', supplier_party_id=501)
        _assign(ds, rule_id, ref_id=100, rank=10)
        _mode(ds, 1, 'buy', group_id=7, item_id=100)

        out = _resolve(ds, _spec())
        assert out['supply_mode'] == 'buy'
        assert out['source_type'] == 'supplier'
        assert out['supplier_party_id'] == 501
        assert out['line_id'] == supplier

    def test_transfer_accepts_internal_org_and_location(self, ds):
        _base(ds)
        insert(ds, 'locations', id=1)
        _vendor(ds, 501)
        rule_id = _rule(ds, 'R_TRANSFER')
        org_line = _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        loc_line = _line(ds, rule_id, 2, 'internal_location',
                         source_location_id=1)
        supplier = _line(ds, rule_id, 3, 'supplier', supplier_party_id=501)
        _assign(ds, rule_id, ref_id=100, rank=10)
        _mode(ds, 1, 'transfer', group_id=7, item_id=100)

        out = _resolve(ds, _spec())
        assert out['supply_mode'] == 'transfer'
        assert set(out['explain'][1]['kept']) == {org_line, loc_line}
        assert {'line_id': supplier, 'reason': 'mode_mismatch'} \
            in out['explain'][1]['dropped']

    def test_all_mode_mismatch_is_mode_conflict(self, ds):
        _base(ds)
        _vendor(ds, 501)
        rule_id = _rule(ds, 'R_CONFLICT')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _line(ds, rule_id, 2, 'supplier', supplier_party_id=501)
        _assign(ds, rule_id, ref_id=100, rank=10)
        _mode(ds, 1, 'make', group_id=7, item_id=100)

        err = _resolve_err(ds, _spec())
        assert err.code == MODE_CONFLICT
        assert err.extra['supply_mode'] == 'make'
        assert err.extra['explain'][1]['dropped']

    def test_item_level_mode_overrides_group_level(self, ds):
        _base(ds)
        _org(ds, 92)
        _func(ds, 92, 'manufacturing')
        _vendor(ds, 501)
        rule_id = _rule(ds, 'R_PRIORITY')
        _line(ds, rule_id, 1, 'supplier', supplier_party_id=501)
        production = _line(ds, rule_id, 2, 'production', source_org_id=92)
        _assign(ds, rule_id, ref_id=100, rank=10)
        _mode(ds, 1, 'buy', group_id=7, item_id=None)       # 物料组级
        _mode(ds, 1, 'make', group_id=7, item_id=100)       # 物料级覆盖

        out = _resolve(ds, _spec())
        assert out['supply_mode'] == 'make'
        assert out['line_id'] == production


# ----------------------------------------------------------------------
# ③ 资格过滤：组织职能 / vendor / 跨法人
# ----------------------------------------------------------------------
class TestSourceEligibility:
    def test_internal_org_requires_inventory_function(self, ds):
        _base(ds)
        update(ds, 'org_functions', {'org_id': 91}, function_type='other')
        rule_id = _rule(ds, 'R_INV')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _assign(ds, rule_id, ref_id=100, rank=10)

        err = _resolve_err(ds, _spec())
        assert err.code == ALL_LINES_INELIGIBLE
        dropped = err.extra['explain'][1]['dropped']
        assert dropped[0]['reason'] == 'org_not_inventory'

    def test_production_requires_manufacturing_function(self, ds):
        _base(ds)
        _org(ds, 92)
        rule_id = _rule(ds, 'R_PROD')
        _line(ds, rule_id, 1, 'production', source_org_id=92)
        _assign(ds, rule_id, ref_id=100, rank=10)

        err = _resolve_err(ds, _spec())
        assert err.code == ALL_LINES_INELIGIBLE
        assert err.extra['explain'][1]['dropped'][0]['reason'] == \
            'org_not_manufacturing'

    def test_supplier_requires_vendor_relation(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_SUP')
        _line(ds, rule_id, 1, 'supplier', supplier_party_id=501)
        _assign(ds, rule_id, ref_id=100, rank=10)

        err = _resolve_err(ds, _spec())
        assert err.code == ALL_LINES_INELIGIBLE
        assert err.extra['explain'][1]['dropped'][0]['reason'] == \
            'supplier_not_vendor'

        _vendor(ds, 501)
        out = _resolve(ds, _spec())
        assert out['supplier_party_id'] == 501

    def test_cross_legal_entity_is_dropped(self, ds):
        _base(ds)
        _org(ds, 900)
        _func(ds, 900, 'legal_entity')
        update(ds, 'orgs', {'id': 91}, parent_id=900)
        _org(ds, 901)
        _func(ds, 901, 'legal_entity')
        _org(ds, 2, parent_id=901)

        rule_id = _rule(ds, 'R_LE')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _assign(ds, rule_id, ref_id=100, dest_org_id=2, rank=10)

        err = _resolve_err(ds, _spec(dest_org_id=2))
        assert err.code == ALL_LINES_INELIGIBLE
        assert err.extra['explain'][1]['dropped'][0]['reason'] == \
            'cross_legal_entity'

    def test_unresolved_legal_entity_is_allowed(self, ds):
        _item(ds, 100, 7)
        _org(ds, 3)
        _org(ds, 4)
        _func(ds, 4, 'inventory')
        rule_id = _rule(ds, 'R_NO_LE')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=4)
        _assign(ds, rule_id, ref_id=100, dest_org_id=3, rank=10)

        out = _resolve(ds, _spec(dest_org_id=3))
        assert out['source_org_id'] == 4


# ----------------------------------------------------------------------
# ④ 排序取源
# ----------------------------------------------------------------------
class TestLineOrdering:
    def test_fixed_beats_lower_rank(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_ORDER')
        normal = _line(ds, rule_id, 1, 'internal_org', source_org_id=91,
                       rank=1)
        fixed = _line(ds, rule_id, 2, 'internal_org', source_org_id=91,
                      rank=9, fixed=1)
        _assign(ds, rule_id, ref_id=100, rank=10)

        assert _resolve(ds, _spec())['line_id'] == fixed
        update(ds, 'sourcing_rule_lines', {'id': fixed}, fixed=0)
        assert _resolve(ds, _spec())['line_id'] == normal

    def test_rank_then_seq_then_id(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_ORDER2')
        seq2 = _line(ds, rule_id, 2, 'internal_org', source_org_id=91, rank=1)
        seq1 = _line(ds, rule_id, 1, 'internal_org', source_org_id=91, rank=1)
        _assign(ds, rule_id, ref_id=100, rank=10)

        assert _resolve(ds, _spec())['line_id'] == seq1
        update(ds, 'sourcing_rule_lines', {'id': seq1}, blocked=1)
        assert _resolve(ds, _spec())['line_id'] == seq2
        update(ds, 'sourcing_rule_lines', {'id': seq2}, blocked=1)

        # 同 rank 同 seq → 按 id（换一个物料，避免命中上一条已全淘汰的规则）
        _item(ds, 101, 7)
        rule2 = _rule(ds, 'R_ORDER3')
        first = _line(ds, rule2, 3, 'internal_org', source_org_id=91, rank=5)
        _line(ds, rule2, 3, 'internal_org', source_org_id=91, rank=5)
        _assign(ds, rule2, ref_id=101, rank=20)
        assert _resolve(ds, _spec(item_id=101))['line_id'] == first


# ----------------------------------------------------------------------
# ⑤ 确定性 + 校验
# ----------------------------------------------------------------------
class TestDeterminism:
    def test_same_input_same_result(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_DET')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _assign(ds, rule_id, ref_id=100, rank=10)
        _mode(ds, 1, 'transfer', group_id=7, item_id=100)

        first = _resolve(ds, _spec())
        second = _resolve(ds, _spec())
        first.pop('evaluated_at')
        second.pop('evaluated_at')
        assert first == second


class TestValidateRule:
    def test_unknown_rule_returns_none(self, ds):
        assert SourcingResolver(ds).validate_rule(999999) is None

    def test_valid_rule_is_ok(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_OK')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _assign(ds, rule_id, ref_id=100, rank=10)

        data = SourcingResolver(ds).validate_rule(rule_id)
        assert data['ok'] is True
        assert data['rule_id'] == rule_id
        assert data['line_count'] == 1
        assert data['assignment_count'] == 1
        assert data['ranks'] == [{'rank': 1, 'total': 100.0, 'ok': True}]
        assert data['conflicts'] == []
        assert data['errors'] == []

    def test_allocation_not_100(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_PCT')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91,
              allocation_pct=50)
        _line(ds, rule_id, 2, 'internal_org', source_org_id=91,
              allocation_pct=40)

        data = SourcingResolver(ds).validate_rule(rule_id)
        codes = [e['code'] for e in data['errors']]
        assert ALLOCATION_NOT_100 in codes
        assert data['ranks'][0]['total'] == 90.0
        assert data['ranks'][0]['ok'] is False

    def test_source_ref_mismatch(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_REF')
        _line(ds, rule_id, 1, 'supplier', supplier_party_id=None)

        data = SourcingResolver(ds).validate_rule(rule_id)
        codes = [e['code'] for e in data['errors']]
        assert SOURCE_REF_MISMATCH in codes

    def test_duplicate_active_assignment_is_conflict(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_CONFLICT_ASSIGN')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _assign(ds, rule_id, ref_id=100, rank=10, seq=1)
        _assign(ds, rule_id, ref_id=100, rank=10, seq=2)

        data = SourcingResolver(ds).validate_rule(rule_id)
        assert data['ok'] is False
        assert data['conflicts']
        codes = [e['code'] for e in data['errors']]
        assert ASSIGNMENT_CONFLICT in codes

    def test_global_scope_with_ref_is_mismatch(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'R_GLOBAL_REF')
        _line(ds, rule_id, 1, 'internal_org', source_org_id=91)
        _assign(ds, rule_id, scope_type='global', ref_id=100, rank=60)

        data = SourcingResolver(ds).validate_rule(rule_id)
        codes = [e['code'] for e in data['errors']]
        assert SOURCE_REF_MISMATCH in codes
