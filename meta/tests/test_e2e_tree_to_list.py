import pytest

pytestmark = pytest.mark.e2e

# -*- coding: utf-8 -*-
"""
端到端场景测试：树节点选择 -> 列表过滤 -> 数据展示

覆盖用户报告的真实场景：
1. 一级节点（领域）选择后列表有反应
2. 二级节点（子领域）选择后列表有反应
3. 混合选择时数据完整性
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.tests.test_utils import get_test_db_path
from meta.services.auth_provider import UserInfo
from meta.services.token_service import TokenService


@pytest.fixture(scope='module')
def app():
    from meta.tests.conftest import get_shared_app
    _app, _ = get_shared_app()
    return _app


@pytest.fixture(scope='module')
def auth_headers():
    test_user = UserInfo(
        user_id='1', username='test_user', display_name='Test User',
        email='test@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(test_user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }


def _extract_list_data(resp_json):
    if resp_json.get('data') is None:
        return [], 0
    data = resp_json['data']
    if isinstance(data, dict) and 'items' in data:
        return data.get('items', []), data.get('total', len(data.get('items', [])))
    if isinstance(data, list):
        return data, resp_json.get('total', len(data))
    return [], 0


class TestTreeNodeSelectionToList:
    """端到端：树节点选择 -> 列表过滤"""

    def test_01_domain_selection_shows_domains(self, app, auth_headers):
        client = app.test_client()

        rows = get_data_source("sqlite", database=get_test_db_path()).execute(
            "SELECT id FROM domains WHERE version_id = 1 LIMIT 3"
        ).fetchall()
        domain_ids = [str(r[0]) for r in rows]

        if len(domain_ids) < 1:
            pytest.fail("No domains available")

        qs = "version_id=1&page_size=100"

        resp = client.get(f"/api/v2/bo/domain?{qs}", headers=auth_headers)
        data = resp.get_json()

        assert data.get('success'), "API should succeed"
        items, total = _extract_list_data(data)
        assert total >= len(domain_ids), \
            f"Expected at least {len(domain_ids)} domains, got {total}"

        returned_ids = {r['id'] for r in items}
        for did in [int(d) for d in domain_ids]:
            assert did in returned_ids, f"Domain {did} should be in results"

    def test_02_sub_domain_selection_shows_sub_domains(self, app, auth_headers):
        client = app.test_client()

        rows = get_data_source("sqlite", database=get_test_db_path()).execute(
            "SELECT id FROM sub_domains WHERE version_id = 1 LIMIT 3"
        ).fetchall()
        sub_domain_ids = [str(r[0]) for r in rows]

        if len(sub_domain_ids) < 1:
            pytest.fail("No sub_domains available")

        qs = "version_id=1&" + "&".join([f"sub_domain_id={sdid}" for sdid in sub_domain_ids])

        resp = client.get(f"/api/v2/bo/sub_domain?{qs}", headers=auth_headers)
        data = resp.get_json()

        assert data.get('success'), "API should succeed"
        items, total = _extract_list_data(data)
        assert total >= len(sub_domain_ids), \
            f"Expected at least {len(sub_domain_ids)} sub_domains, got {total}"

        returned_ids = {r['id'] for r in items}
        for sdid in [int(d) for d in sub_domain_ids]:
            assert sdid in returned_ids, f"SubDomain {sdid} should be in results"

    def test_03_sub_domain_selection_filters_business_objects(self, app, auth_headers):
        client = app.test_client()
        ds = get_data_source("sqlite", database=get_test_db_path())

        sm_with_bo = ds.execute("""
            SELECT sm.id, sm.sub_domain_id
            FROM service_modules sm
            INNER JOIN business_objects bo ON bo.service_module_id = sm.id
            LIMIT 1
        """).fetchone()

        if not sm_with_bo:
            pytest.skip("No service_module with business_objects available")

        sm_id, sub_domain_id = sm_with_bo

        resp = client.get(f"/api/v2/bo/business_object?version_id=1&sub_domain_id={sub_domain_id}", headers=auth_headers)
        data = resp.get_json()

        assert data.get('success'), "API should succeed"

    def test_04_mixed_selection_domain_tab(self, app, auth_headers):
        client = app.test_client()
        ds = get_data_source("sqlite", database=get_test_db_path())

        domain = ds.execute(
            "SELECT id FROM domains WHERE version_id = 1 LIMIT 1"
        ).fetchone()

        if not domain:
            pytest.fail("No domain available")

        domain_id = domain[0]

        sub_domain = ds.execute(
            "SELECT id FROM sub_domains WHERE domain_id = ? AND version_id = 1 LIMIT 1",
            (domain_id,)
        ).fetchone()

        sub_domain_id = sub_domain[0] if sub_domain else 99999

        qs = f"version_id=1&page_size=100"

        resp = client.get(f"/api/v2/bo/domain?{qs}", headers=auth_headers)
        data = resp.get_json()

        assert data.get('success'), "API should succeed"
        items, total = _extract_list_data(data)
        assert total >= 1, "Should show at least the domain"

        returned_ids = {r['id'] for r in items}
        assert domain_id in returned_ids, \
            f"Domain {domain_id} should be in results"

    def test_05_leaf_domain_included(self, app, auth_headers):
        client = app.test_client()
        ds = get_data_source("sqlite", database=get_test_db_path())

        all_domains = ds.execute(
            "SELECT id FROM domains WHERE version_id = 1"
        ).fetchall()
        all_domain_ids = [str(r[0]) for r in all_domains]

        if len(all_domain_ids) < 2:
            pytest.fail("Need at least 2 domains")

        domains_with_sub = ds.execute(
            "SELECT DISTINCT domain_id FROM sub_domains WHERE version_id = 1"
        ).fetchall()
        domains_with_sub_ids = {r[0] for r in domains_with_sub}

        leaf_domains = [int(d) for d in all_domain_ids if int(d) not in domains_with_sub_ids]

        qs = "version_id=1&page_size=100"

        resp = client.get(f"/api/v2/bo/domain?{qs}", headers=auth_headers)
        data = resp.get_json()

        items, total = _extract_list_data(data)

        returned_ids = {r['id'] for r in items}

        for leaf_id in leaf_domains:
            assert leaf_id in returned_ids, \
                f"Leaf domain {leaf_id} (no sub_domains) should be in results"

    def test_06_service_module_selection(self, app, auth_headers):
        client = app.test_client()
        ds = get_data_source("sqlite", database=get_test_db_path())

        sm = ds.execute(
            "SELECT id FROM service_modules WHERE version_id = 1 LIMIT 3"
        ).fetchall()
        sm_ids = [str(r[0]) for r in sm]

        if len(sm_ids) < 1:
            pytest.fail("No service_modules available")

        qs = "version_id=1&" + "&".join([f"service_module_id={sid}" for sid in sm_ids])

        resp = client.get(f"/api/v2/bo/service_module?{qs}", headers=auth_headers)
        data = resp.get_json()

        assert data.get('success'), "API should succeed"
        items, total = _extract_list_data(data)
        assert total >= len(sm_ids), \
            f"Expected at least {len(sm_ids)} service_modules, got {total}"

    def test_07_full_flow_simulation(self, app, auth_headers):
        client = app.test_client()
        ds = get_data_source("sqlite", database=get_test_db_path())

        domain = ds.execute(
            "SELECT id, name FROM domains WHERE version_id = 1 LIMIT 1"
        ).fetchone()

        if not domain:
            pytest.fail("No domain available")

        domain_id, domain_name = domain

        resp1 = client.get(f"/api/v2/bo/domain?version_id=1&page_size=100", headers=auth_headers)
        data1 = resp1.get_json()
        assert data1.get('success')
        _, total1 = _extract_list_data(data1)
        assert total1 >= 1

        sub_domain = ds.execute(
            "SELECT id, name FROM sub_domains WHERE domain_id = ? AND version_id = 1 LIMIT 1",
            (domain_id,)
        ).fetchone()

        if sub_domain:
            sub_domain_id, sub_domain_name = sub_domain

            resp2 = client.get(f"/api/v2/bo/sub_domain?version_id=1&sub_domain_id={sub_domain_id}", headers=auth_headers)
            data2 = resp2.get_json()
            assert data2.get('success')

            resp3 = client.get(f"/api/v2/bo/business_object?version_id=1&sub_domain_id={sub_domain_id}", headers=auth_headers)
            data3 = resp3.get_json()
            assert data3.get('success')


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
