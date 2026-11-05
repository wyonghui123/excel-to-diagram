# -*- coding: utf-8 -*-
"""组织上下文解析器回归：优先级、兜底与「不猜」边界。

种子数据来自 inventory_test_doubles（seed 提供两组织 + 两库位），
缺失表的场景用最小 FakeDS 表达，避免在测试文件里写 raw SQL。
"""

import pytest

from meta.services.org_context_resolver import (
    OrgContextResolver, OrgNotResolved,
)
from meta.tests.inventory_test_doubles import (
    ORG_ID, OTHER_LOCATION_ID, OTHER_ORG_ID, MemDS, seed,
)


class _FakeDS:
    def __init__(self, rows_by_table=None):
        self._rows = rows_by_table or {}

    def query(self, sql, params=None):
        for table, rows in self._rows.items():
            if 'FROM %s' % table in sql:
                return list(rows)
        return []


def test_priority_fields_first_hit_wins():
    resolver = OrgContextResolver(MemDS(seed()))
    org = resolver.from_fields({'provider_org_id': 2, 'requester_org_id': 1},
                               ('provider_org_id', 'requester_org_id'))
    assert org == 2


def test_no_source_raises():
    with pytest.raises(OrgNotResolved):
        OrgContextResolver(MemDS(seed())).from_fields({}, ('provider_org_id',))


def test_sales_order_line_prefers_location_org():
    org, location = OrgContextResolver(MemDS(seed())).from_sales_order_line(
        {'id': 88, 'plant_location_id': OTHER_LOCATION_ID,
         'header_org_id': ORG_ID})
    assert (org, location) == (OTHER_ORG_ID, OTHER_LOCATION_ID)


def test_sales_order_line_falls_back_to_header_org():
    org, location = OrgContextResolver(MemDS(seed())).from_sales_order_line(
        {'id': 88, 'header_org_id': ORG_ID})
    assert (org, location) == (ORG_ID, 0)


def test_sales_order_line_without_org_raises():
    with pytest.raises(OrgNotResolved):
        OrgContextResolver(MemDS(seed())).from_sales_order_line({'id': 88})


def test_project_org_resolved():
    resolver = OrgContextResolver(
        _FakeDS({'projects': [{'org_id': OTHER_ORG_ID}]}))
    assert resolver.from_project(1) == OTHER_ORG_ID


def test_work_order_falls_back_to_single_active_org():
    resolver = OrgContextResolver(_FakeDS({'orgs': [{'id': ORG_ID}]}))
    assert resolver.from_work_order({'order_id': 99}) == ORG_ID


def test_work_order_with_multiple_orgs_raises():
    resolver = OrgContextResolver(
        _FakeDS({'orgs': [{'id': ORG_ID}, {'id': OTHER_ORG_ID}]}))
    with pytest.raises(OrgNotResolved):
        resolver.from_work_order({'order_id': 99})
