import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
回归：混合选择「有子节点的域 + 空叶子域」时不得漏掉任何一个域

原文件是纯 print 诊断脚本（无断言），且因内联 DML 被 raw-SQL 守卫整文件 skip。
现改为断言式回归测试：DML 走 factories 桥接，断言锁定不变量：

`HierarchyFilterService.resolve_conditions` 产生的 `id` 条件必须**唯一**
（实现会把所有 id 条件按并集合并，不会用 AND 取交集把空叶子域排除），
且用户选中的两个域 id 都必须在结果内。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services
from meta.services.hierarchy_filter_service import HierarchyFilterService
from meta.services.query_service import QueryService
from meta.tests.factories._raw_sql_bridge import insert
from meta.tests.test_utils import get_test_db_path


def _ensure_leaf_test_data(ds):
    """确保某版本下同时存在非叶子域与空叶子域（幂等），返回所用 version_id。"""
    row = ds.execute("SELECT id FROM versions ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return None
    version_id = row[0]

    parent_count = ds.execute(
        "SELECT COUNT(*) FROM domains d WHERE d.version_id = ? AND EXISTS"
        " (SELECT 1 FROM sub_domains s WHERE s.domain_id = d.id)",
        (version_id,)).fetchone()[0]
    if not parent_count:
        row = ds.execute(
            "SELECT id FROM domains WHERE code = 'TEST_PARENT'").fetchone()
        parent_id = row[0] if row else None
        if parent_id is None:
            insert(ds, 'domains', name='TEST_PARENT', code='TEST_PARENT',
                   version_id=version_id)
            parent_id = ds.execute(
                "SELECT id FROM domains WHERE code = 'TEST_PARENT'").fetchone()[0]
        insert(ds, 'sub_domains', name='TEST_CHILD', code='TEST_CHILD',
               version_id=version_id, domain_id=parent_id)

    leaf_count = ds.execute(
        "SELECT COUNT(*) FROM domains d WHERE d.version_id = ? AND NOT EXISTS"
        " (SELECT 1 FROM sub_domains s WHERE s.domain_id = d.id)",
        (version_id,)).fetchone()[0]
    if not leaf_count:
        exists = ds.execute(
            "SELECT id FROM domains WHERE code = 'TEST_LEAF'").fetchone()
        if not exists:
            insert(ds, 'domains', name='TEST_LEAF', code='TEST_LEAF',
                   version_id=version_id)
    ds.commit()
    return version_id


@pytest.fixture(scope='module')
def ds():
    _ds = get_data_source("sqlite", database=get_test_db_path())
    init_services(_ds)
    return _ds


@pytest.fixture(scope='module')
def version_id(ds):
    vid = _ensure_leaf_test_data(ds)
    if vid is None:
        pytest.skip("Test DB has no versions row")
    return vid


class TestLeafDomainSelection:
    def test_diagnose_condition_tree_with_leaf_domain(self, ds, version_id):
        """空叶子域 + 有子节点的域混合选择：两个域都不得被排除"""
        all_domains = ds.execute(
            "SELECT id, name FROM domains WHERE version_id = ? ORDER BY id",
            (version_id,)
        ).fetchall()

        if len(all_domains) < 2:
            pytest.skip("Need at least 2 domains")

        domain_with_children = None
        leaf_domains = []
        for d in all_domains:
            children = ds.execute(
                "SELECT COUNT(*) FROM sub_domains WHERE domain_id = ?",
                (d[0],)
            ).fetchone()[0]
            if children > 0 and domain_with_children is None:
                domain_with_children = d
            elif children == 0:
                leaf_domains.append(d)

        if not domain_with_children or not leaf_domains:
            pytest.skip("Need both leaf and non-leaf domains")

        parent_domain = domain_with_children
        leaf_domain = leaf_domains[0]

        sub_domains_under_parent = ds.execute(
            "SELECT id FROM sub_domains WHERE domain_id = ?", (parent_domain[0],)
        ).fetchall()
        sms_under_parent = ds.execute("""
            SELECT sm.id FROM service_modules sm
            JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            WHERE sd.domain_id = ?
        """, (parent_domain[0],)).fetchall()

        condition_tree = {
            'version_id': [str(version_id)],
            'domain_id': [str(parent_domain[0]), str(leaf_domain[0])],
        }
        if sub_domains_under_parent:
            condition_tree['sub_domain_id'] = [str(s[0]) for s in sub_domains_under_parent[:2]]
        if sms_under_parent:
            condition_tree['service_module_id'] = [str(s[0]) for s in sms_under_parent[:2]]

        query_svc = QueryService(ds)
        svc = HierarchyFilterService(query_svc, ds)
        conditions = svc.resolve_conditions('domains', condition_tree)

        id_conditions = [c for c in conditions if c.field == 'id']
        assert len(id_conditions) == 1, (
            f"id 条件应合并为唯一一条，实际 {len(id_conditions)} 条: "
            f"{[(c.operator, getattr(c, 'values', getattr(c, 'value', None))) for c in id_conditions]}"
        )
        resolved_ids = set(id_conditions[0].values)
        assert parent_domain[0] in resolved_ids, (
            f"有子节点的域 {parent_domain[0]} 被排除，实际 id 集合 {resolved_ids}")
        assert leaf_domain[0] in resolved_ids, (
            f"空叶子域 {leaf_domain[0]} 被排除，实际 id 集合 {resolved_ids}")
