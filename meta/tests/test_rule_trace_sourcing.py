# -*- coding: utf-8 -*-
"""sourcing trace 适配器测试（spec 2026-11-09 FR-005 / M2-P1）。

[定位] 只测 `RuleTraceService` 对 sourcing 场景的形状映射：三段 explain →
scope / filter / select 三个统一节点，不重算匹配与排序。

[口径] 命中时 `select.detail` 必须与 `SourcingResolver.resolve` 同输入结果
一致（同一规则、同一来源行）；失败时给出淘汰原因分类与 `skip_reason`。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.rule_trace_service import RuleTraceService  # noqa: E402
from meta.services.sourcing_service import SourcingResolver  # noqa: E402
from meta.tests.factories._raw_sql_bridge import insert  # noqa: E402

DAY = '2026-10-24'

# 最小 DDL（列名与 meta/schemas/*.yaml 的 db_column 一致）
DDL = [
    "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " item_group_id INTEGER)",
    "CREATE TABLE item_groups (id INTEGER PRIMARY KEY AUTOINCREMENT)",
    "CREATE TABLE orgs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " parent_id INTEGER, status TEXT)",
    "CREATE TABLE org_functions (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " org_id INTEGER, function_type TEXT, is_primary INTEGER DEFAULT 0,"
    " effective_from TEXT, effective_to TEXT)",
    "CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " org_id INTEGER)",
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
    adapter.connect(path=str(tmp_path / 'trace_sourcing.db'))
    for ddl in DDL:
        adapter.execute(ddl)
    yield adapter
    adapter.disconnect()


# ----------------------------------------------------------------------
# 造数助手
# ----------------------------------------------------------------------
def _base(ds, item_id=100, group_id=7):
    insert(ds, 'items', id=item_id, item_group_id=group_id)
    insert(ds, 'orgs', id=1, status='active')
    insert(ds, 'orgs', id=91, status='active')
    insert(ds, 'org_functions', org_id=91, function_type='inventory',
           is_primary=0, effective_from='2000-01-01', effective_to=None)


def _rule(ds, code, usage='all'):
    return insert(ds, 'sourcing_rules', code=code, name=code,
                  rule_usage=usage, effectivity_start='2020-01-01',
                  effectivity_end=None, status='active').lastrowid


def _assign(ds, rule_id, ref_id=100, rank=10):
    return insert(ds, 'sourcing_rule_assignments', rule_id=rule_id,
                  scope_type='item', scope_ref_id=ref_id, dest_org_id=1,
                  dest_location_id=None, specificity_rank=rank, seq=1,
                  effectivity_start='2020-01-01', effectivity_end=None,
                  status='active').lastrowid


def _line(ds, rule_id, seq=1, source_org_id=91, blocked=0):
    return insert(ds, 'sourcing_rule_lines', rule_id=rule_id, seq=seq,
                  source_type='internal_org', source_org_id=source_org_id,
                  source_location_id=None, supplier_party_id=None,
                  rank=1, allocation_pct=100, blocked=blocked, fixed=0,
                  effectivity_start='2020-01-01',
                  effectivity_end=None).lastrowid


def _data(**extra):
    data = {
        'item_id': 100, 'dest_org_id': 1,
        'usage': 'fulfillment', 'eval_date': DAY,
    }
    data.update(extra)
    return data


def _build(ds, data=None, dims=None):
    return RuleTraceService().build(
        'sales_order',
        data=data if data is not None else _data(),
        dims=dims,
        scenarios=['sourcing'],
        data_source=ds,
    )


def _stages(result):
    return {node['stage']: node for node in result['scenarios']}


# ----------------------------------------------------------------------
# FR-005：命中
# ----------------------------------------------------------------------
class TestSourcingTraceHit:
    def test_hit_maps_three_stages(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'SRC-001')
        line_id = _line(ds, rule_id)
        _assign(ds, rule_id)

        result = _build(ds)
        nodes = result['scenarios']

        assert [node['stage'] for node in nodes] == ['scope', 'filter', 'select']
        assert [node['kind'] for node in nodes] == ['hit', 'hit', 'hit']
        assert {node['scenario'] for node in nodes} == {'sourcing'}
        assert all(node['rule_id'] == 'sourcing:SRC-001' for node in nodes)
        assert nodes[2]['decision'] == 'hit'
        assert nodes[2]['detail']['line_id'] == line_id
        assert nodes[2]['detail']['source_org_id'] == 91
        assert nodes[2]['detail']['supply_mode'] is None
        assert result['kind_counts']['hit'] == 3

    def test_consistent_with_direct_resolve(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'SRC-001')
        _line(ds, rule_id)
        _assign(ds, rule_id)

        result = _build(ds)
        select = _stages(result)['select']
        direct = SourcingResolver(ds).resolve({
            'item_id': 100, 'dest_org_id': 1,
            'usage': 'fulfillment', 'date': DAY,
        })

        assert select['detail']['line_id'] == direct['line_id']
        assert select['detail']['source_org_id'] == direct['source_org_id']
        assert select['detail']['specificity_rank'] == direct['specificity_rank']
        assert select['rule_id'] == 'sourcing:%s' % direct['rule_code']

    def test_factor_snapshot_uses_sourcing_axes(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'SRC-001')
        _line(ds, rule_id)
        _assign(ds, rule_id)

        result = _build(ds, data=_data(dest_location_id=5))
        select = _stages(result)['select']
        assert select['factors'] == {
            'dest_org_id': 1, 'item_id': 100,
            'usage': 'fulfillment', 'eval_date': DAY,
        }
        # 库位不是因子轴（spec FR-004），只作为可选输入使用
        assert 'dest_location_id' not in select['factors']


# ----------------------------------------------------------------------
# FR-005：未命中与淘汰原因
# ----------------------------------------------------------------------
class TestSourcingTraceMiss:
    def test_no_assignment_is_scope_miss(self, ds):
        _base(ds)

        result = _build(ds)
        nodes = _stages(result)

        assert nodes['scope']['decision'] == 'not_matched'
        assert nodes['scope']['kind'] == 'miss'
        assert nodes['scope']['skip_reason'] == 'scope_mismatch'
        assert nodes['filter']['kind'] == 'skip'
        assert nodes['select']['kind'] == 'skip'

    def test_all_lines_blocked_reports_blocked(self, ds):
        _base(ds)
        rule_id = _rule(ds, 'SRC-001')
        _line(ds, rule_id, blocked=1)
        _assign(ds, rule_id)

        result = _build(ds)
        nodes = _stages(result)

        assert nodes['scope']['kind'] == 'hit'
        assert nodes['filter']['kind'] == 'miss'
        assert nodes['filter']['skip_reason'] == 'blocked'
        assert nodes['filter']['detail']['raw_reason'] == 'blocked'
        assert nodes['select']['kind'] == 'skip'

    def test_missing_input_does_not_touch_resolver(self, ds):
        result = _build(ds, data={'org_id': 1})
        nodes = _stages(result)

        assert [node['kind'] for node in result['scenarios']] == [
            'skip', 'skip', 'skip']
        assert nodes['scope']['skip_reason'] == 'invalid_input'

    def test_invalid_usage_reports_invalid_input(self, ds):
        _base(ds)

        result = _build(ds, data=_data(usage='bogus'))
        nodes = _stages(result)

        assert nodes['scope']['kind'] == 'skip'
        assert nodes['scope']['skip_reason'] == 'invalid_input'
