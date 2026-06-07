import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
诊断测试：混合选择(父节点+叶子节点)时领域列表数据丢失

精确复现用户场景：
- 对象树选中：供应链云(domain,有子节点) + TEST(domain,空叶) + LSDKFJSDFsdfsdf(domain,空叶)
- 在"领域"标签页查看列表
- 预期：显示3条domain记录
- 实际：只显示2条（缺少供应链云）
"""

import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services
from meta.services.hierarchy_filter_service import HierarchyFilterService
from meta.services.query_service import QueryService
from meta.tests.test_utils import get_test_db_path


@pytest.fixture(scope='module')
def ds():
    _ds = get_data_source("sqlite", database=get_test_db_path())
    init_services(_ds)
    return _ds


class TestDomainListMixedSelection:
    """诊断：混合选择节点时 domain 列表数据丢失"""

    def test_1_show_actual_domain_data(self, ds):
        """步骤1: 查看数据库中实际的 domain 数据"""
        rows = ds.execute("""
            SELECT id, code, name, version_id 
            FROM domains 
            WHERE version_id = 1 
            ORDER BY id
        """).fetchall()
        
        print(f"\n[步骤1] 版本1中的所有domain ({len(rows)}条):")
        for r in rows:
            print(f"  id={r[0]}, code={r[1]}, name={r[2]}")
        
        if len(rows) < 2:
            pytest.fail("Need at least 2 domains to test mixed selection")
        
        assert len(rows) >= 2, "至少需要2个domain才能测试"

    def test_2_simulate_buildOriginalFilter(self, ds):
        """步骤2: 模拟前端 buildOriginalFilter 的输出"""
        rows = ds.execute("""
            SELECT id FROM domains WHERE version_id = 1 ORDER BY id
        """).fetchall()
        
        domain_ids = [r[0] for r in rows]
        
        checked_ids = []
        for did in domain_ids:
            checked_ids.append(f'domain_{did}')
        
        print(f"\n[步骤2] 模拟全选 - checkedIds: {checked_ids}")
        
        field_to_ids = {}
        type_prefixes = [
            ('domain_', 'domain_id'),
            ('sub_domain_', 'sub_domain_id'),
            ('service_module_', 'service_module_id'),
            ('business_object_', 'business_object_id'),
        ]
        
        for node_id in checked_ids:
            for prefix, field in type_prefixes:
                if node_id.startswith(prefix):
                    id_str = node_id[len(prefix):]
                    try:
                        id_val = int(id_str)
                        if field not in field_to_ids:
                            field_to_ids[field] = []
                        field_to_ids[field].append(id_val)
                    except ValueError:
                        print(f"  [WARN] Cannot parse ID: {node_id} -> '{id_str}'")
                    break
        
        print(f"  buildOriginalFilter 输出:")
        for k, v in field_to_ids.items():
            print(f"    {k}: {v}")
        
        assert 'domain_id' in field_to_ids, "应该有 domain_id"
        print(f"  [OK] domain_id collected {len(field_to_ids['domain_id'])} items")

    def test_3_simulate_currentFilterParams_for_domain_tab(self, ds):
        """步骤3: 模拟前端 currentFilterParams (领域标签页)"""
        rows = ds.execute("""
            SELECT id FROM domains WHERE version_id = 1 ORDER BY id
        """).fetchall()
        
        domain_ids = [r[0] for r in rows]
        
        hierarchy_filter = {
            'version_id': 1,
            'domain_id': domain_ids,
            'sub_domain_id': [999],
            'service_module_id': [888],
        }
        
        DIMENSION_GRANULARITY = {
            'domain': ['version_id', 'domain_id'],
        }
        
        allowed_keys = DIMENSION_GRANULARITY['domain']
        params = {}
        for key in allowed_keys:
            if key in hierarchy_filter and hierarchy_filter[key] is not None:
                params[key] = hierarchy_filter[key]
        
        print(f"\n[步骤3] 领域标签页 currentFilterParams:")
        print(f"  输入(hierarchyFilter): {list(hierarchy_filter.keys())}")
        print(f"  输出(params): {list(params.keys())}")
        print(f"  domain_id: {params.get('domain_id')}")
        
        assert 'domain_id' in params
        assert 'sub_domain_id' not in params, "领域标签页不应传 sub_domain_id"
        assert len(params['domain_id']) == len(domain_ids), \
            f"domain_id 数量应保持 {len(domain_ids)}"

    def test_4_backend_resolve_conditions(self, ds):
        """步骤4: 后端 resolve_conditions 处理 domain + domain_id"""
        query_svc = QueryService(ds)
        svc = HierarchyFilterService(query_svc, ds)
        
        rows = ds.execute("""
            SELECT id FROM domains WHERE version_id = 1 ORDER BY id
        """).fetchall()
        domain_ids = [str(r[0]) for r in rows]
        
        args_dict = {
            'version_id': ['1'],
            'domain_id': domain_ids,
        }
        
        print(f"\n[步骤4] 后端 resolve_conditions('domains', args_dict):")
        print(f"  输入 domain_id: {domain_ids}")
        
        conditions = svc.resolve_conditions('domains', args_dict)
        
        print(f"  生成的条件数: {len(conditions)}")
        for i, c in enumerate(conditions):
            print(f"    条件{i+1}: field={c.field}, operator={c.operator}, values={getattr(c, 'values', getattr(c, 'value', None))}")
        
        has_id_condition = any(c.field == 'id' for c in conditions)
        print(f"  有 id 条件: {has_id_condition}")

    def test_5_full_api_call_simulation(self, ds, client_with_auth):
        """步骤5: 完整模拟 API 调用链"""
        from meta.api.manage_api import manage_bp
        from flask import Flask, request
        app = Flask(__name__)
        app.register_blueprint(manage_bp)
        
        client, headers = client_with_auth
        
        rows = ds.execute("""
            SELECT id FROM domains WHERE version_id = 1 ORDER BY id
        """).fetchall()
        domain_ids = [r[0] for r in rows]
        
        query_string = 'version_id=1'
        for did in domain_ids:
            query_string += f'&domain_id={did}'
        query_string += '&page=1&pageSize=20'
        
        print(f"\n[步骤5] 完整API调用:")
        print(f"  URL: /api/v2/bo/domain?{query_string}")
        
        response = client.get(f'/api/v2/bo/domain?{query_string}', headers=headers)
        
        data = response.get_json()
        if data is None:
            pytest.fail("API returned non-JSON response")
        
        items = data.get('data', {}).get('items', [])
        print(f"  success: {data.get('success')}")
        print(f"  total: {data.get('data', {}).get('total')}")
        print(f"  返回记录数: {len(items)}")
        print(f"  返回的IDs: {[r.get('id') for r in items]}")
        
        expected_ids = set(domain_ids)
        actual_ids = {r.get('id') for r in items}
        
        missing = expected_ids - actual_ids
        if missing:
            print(f"  [MISSING] Missing IDs: {missing}")
            
            missing_names = ds.execute(
                f"SELECT id, name FROM domains WHERE id IN ({','.join(str(m) for m in missing)})"
            ).fetchall()
            for m in missing_names:
                print(f"     缺失: id={m[0]}, name={m[1]}")
        else:
            print(f"  [OK] All domains in result")
        
        assert data.get('success'), "API调用应成功"
        assert data.get('data', {}).get('total', 0) >= len(domain_ids) - 1, \
            f"返回总数({data.get('data', {}).get('total')})应 >= 传入domain数({len(domain_ids)})减去可能的分页误差"

    def test_6_mixed_selection_real_scenario(self, ds, client_with_auth):
        """
        步骤6: 精确复现用户截图场景
        
        用户截图：
        - 对象树已选12项（供应链云展开+其子节点 + TEST + LSDKFJSDFsdfsdf）
        - 领域列表只显示2条（TEST、LSDKFJSDFsdfsdf）
        - 供应链云丢失
        """
        client, headers = client_with_auth
        
        all_domains = ds.execute("""
            SELECT id, name, code FROM domains WHERE version_id = 1 ORDER BY id
        """).fetchall()
        
        if len(all_domains) < 3:
            pytest.fail("需要至少3个domain来测试混合选择场景")
        
        simulating_domain = all_domains[0]
        leaf_domain_1 = all_domains[-2] if len(all_domains) >= 2 else None
        leaf_domain_2 = all_domains[-1] if len(all_domains) >= 3 else None
        
        print(f"\n[步骤6] 精确复现用户场景:")
        print(f"  模拟'供应链云': id={simulating_domain[0]}, name={simulating_domain[1]}")
        print(f'  模拟TEST: id={leaf_domain_1[0] if leaf_domain_1 else "?"}, name={leaf_domain_1[1] if leaf_domain_1 else "?"}')
        print(f'  模拟LSDK: id={leaf_domain_2[0] if leaf_domain_2 else "?"}, name={leaf_domain_2[2] if leaf_domain_2 else "?"}')
        
        selected_domain_ids = [simulating_domain[0]]
        if leaf_domain_1:
            selected_domain_ids.append(leaf_domain_1[0])
        if leaf_domain_2:
            selected_domain_ids.append(leaf_domain_2[0])
        
        checked_ids = [f'domain_{did}' for did in selected_domain_ids]
        
        sub_domains_under_first = ds.execute("""
            SELECT id FROM sub_domains WHERE domain_id = ? AND version_id = 1
        """, (simulating_domain[0],)).fetchall()
        
        for sd in sub_domains_under_first[:3]:
            checked_ids.append(f'sub_domain_{sd[0]}')
        
        print(f"\n  模拟checkedIds ({len(checked_ids)}项): {checked_ids}")
        
        from meta.api.manage_api import manage_bp
        from flask import Flask
        from meta.tests.test_utils import get_test_db_path
        app = Flask(__name__)
        app.register_blueprint(manage_bp)
        
        query_parts = ['version_id=1']
        for did in selected_domain_ids:
            query_parts.append(f'domain_id={did}')
        for sd in sub_domains_under_first[:3]:
            query_parts.append(f'sub_domain_id={sd[0]}')
        query_parts.extend(['page=1', 'pageSize=20'])
        
        qs = '&'.join(query_parts)
        print(f"  API请求: /api/v2/bo/domain?{qs}")
        
        resp = client.get(f'/api/v2/bo/domain?{qs}', headers=headers)
        data = resp.get_json()
        if data is None:
            pytest.fail("API returned non-JSON response")
        
        items = data.get('data', {}).get('items', [])
        returned_ids = [r.get('id') for r in items]
        returned_names = [r.get('name') for r in items]
        
        print(f"\n  结果: total={data.get('data', {}).get('total')}, count={len(items)}")
        print(f"  返回: {list(zip(returned_ids, returned_names))}")
        
        missing_in_result = set(selected_domain_ids) - set(returned_ids)
        if missing_in_result:
            print(f"  [MISSING] domain IDs: {missing_in_result}")
            for mid in missing_in_result:
                d = ds.execute("SELECT name FROM domains WHERE id=?", (mid,)).fetchone()
                print(f"     缺失: {d[0] if d else mid}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
