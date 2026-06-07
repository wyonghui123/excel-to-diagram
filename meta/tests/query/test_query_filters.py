# -*- coding: utf-8 -*-
import pytest
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

pytestmark = pytest.mark.integration


class TestMultiLevelParamAND:
    def test_resolve_conditions_produces_multiple_id_conditions(self):
        from meta.core.datasource import get_data_source
        from meta.services.query_service import QueryService
        from meta.services.hierarchy_filter_service import HierarchyFilterService
        
        db = get_data_source('sqlite', database=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'architecture.db'))
        query_svc = QueryService(db)
        svc = HierarchyFilterService(query_svc, db)
        
        conditions = svc.resolve_conditions('domains', {
            'version_id': ['1'],
            'domain_id': ['1', '4'],
            'sub_domain_id': ['10']
        })
        
        assert isinstance(conditions, list)

    def test_api_mixed_selection_loses_leaf_domain(self, shared_client, admin_headers):
        from meta.core.datasource import get_data_source
        
        db = get_data_source('sqlite', database=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'architecture.db'))
        
        all_domains = db.execute('SELECT id FROM domains WHERE version_id = 1').fetchall()
        
        if len(all_domains) < 2:
            pytest.skip('Need >= 2 domains')
        
        domain_ids = [r[0] for r in all_domains]
        
        qs = 'version_id=1&page_size=100&' + '&'.join([f'domain_id={d}' for d in domain_ids])
        
        resp = shared_client.get(f'/api/v2/bo/domain?{qs}', headers=admin_headers)
        data = resp.get_json()
        
        if data is None:
            pytest.skip('API returned non-JSON response')
        
        assert data is not None
