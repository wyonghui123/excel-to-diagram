import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
诊断：选择空叶子域后列表展示问题

精确复现：
- 用户选择：供应链云(domain_1,有子节点) + TEST(domain_4,空叶子)
- 条件树：{domain_id: [1,4], sub_domain_id: [10], service_module_id: [100]}
- 在领域tab查看 → 预期显示2条，实际可能只显示1条
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services, manage_bp
from meta.services.hierarchy_filter_service import HierarchyFilterService
from meta.services.query_service import QueryService
from meta.services.auth_provider import UserInfo
from meta.services.token_service import TokenService
from flask import Flask
from meta.tests.test_utils import get_test_db_path


def _ensure_leaf_test_data(ds):
    """v3.18 P1: 修复 S009 数据依赖 skip
    确保至少 2 个 domain (含叶子+非叶子)
    """
    cursor = ds.execute("SELECT COUNT(*) FROM domains")
    if cursor.fetchone()[0] < 2:
        # 添加 1 个父域 (非叶子)
        ds.execute("INSERT INTO domains (name, code, version_id) VALUES ('TEST_PARENT', 'TEST_PARENT', 1)")
        # 添加 1 个子域挂到父域下
        parent_id = ds.execute("SELECT id FROM domains WHERE code='TEST_PARENT' LIMIT 1").fetchone()
        if parent_id:
            ds.execute("INSERT INTO sub_domains (name, code, version_id, domain_id) VALUES ('TEST_CHILD', 'TEST_CHILD', 1, ?)", (parent_id[0],))
        # 添加 1 个叶子域 (无 sub_domain)
        ds.execute("INSERT INTO domains (name, code, version_id) VALUES ('TEST_LEAF', 'TEST_LEAF', 1)")
        ds.commit()


@pytest.fixture(scope='module')
def ds():
    _ds = get_data_source("sqlite", database=get_test_db_path())
    init_services(_ds)
    _ensure_leaf_test_data(_ds)
    return _ds


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


class TestLeafDomainSelection:
    def test_diagnose_condition_tree_with_leaf_domain(self, ds):
        """诊断：空叶子域+有子节点的域混合选择"""
        
        all_domains = ds.execute("""
            SELECT id, name FROM domains WHERE version_id = 1 ORDER BY id
        """).fetchall()
        
        if len(all_domains) < 2:
            pytest.skip("Need at least 2 domains")
        
        # 找一个有子领域的域
        domain_with_children = None
        for d in all_domains:
            children = ds.execute(
                "SELECT COUNT(*) FROM sub_domains WHERE domain_id = ?",
                (d[0],)
            ).fetchone()[0]
            if children > 0:
                domain_with_children = d
                break
        
        # 找一个没有子领域的域（空叶子）
        leaf_domains = []
        for d in all_domains:
            children = ds.execute(
                "SELECT COUNT(*) FROM sub_domains WHERE domain_id = ?",
                (d[0],)
            ).fetchone()[0]
            if children == 0:
                leaf_domains.append(d)
        
        if not domain_with_children or not leaf_domains:
            pytest.skip("Need both leaf and non-leaf domains")
        
        parent_domain = domain_with_children
        leaf_domain = leaf_domains[0]
        
        print(f"\n=== 场景 ===")
        print(f"有子节点的域: id={parent_domain[0]}, name={parent_domain[1]}")
        print(f"空叶子域: id={leaf_domain[0]}, name={leaf_domain[1]}")
        
        # 获取有子节点的域下的子领域和服务模块
        sub_domains_under_parent = ds.execute(
            "SELECT id FROM sub_domains WHERE domain_id = ?", (parent_domain[0],)
        ).fetchall()
        sms_under_parent = ds.execute("""
            SELECT sm.id FROM service_modules sm
            JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            WHERE sd.domain_id = ?
        """, (parent_domain[0],)).fetchall()
        
        # 构建条件树（模拟用户选择两个域+其下的子节点）
        condition_tree = {
            'version_id': ['1'],
            'domain_id': [str(parent_domain[0]), str(leaf_domain[0])],
        }
        if sub_domains_under_parent:
            condition_tree['sub_domain_id'] = [str(s[0]) for s in sub_domains_under_parent[:2]]
        if sms_under_parent:
            condition_tree['service_module_id'] = [str(s[0]) for s in sms_under_parent[:2]]
        
        print(f"\n=== 条件树 ===")
        for k, v in condition_tree.items():
            print(f"  {k}: {v}")
        
        query_svc = QueryService(ds)
        svc = HierarchyFilterService(query_svc, ds)
        
        print(f"\n=== 后端 resolve_conditions('domains', condition_tree) ===")
        conditions = svc.resolve_conditions('domains', condition_tree)
        
        for i, c in enumerate(conditions):
            vals = getattr(c, 'values', getattr(c, 'value', None))
            print(f"  条件{i+1}: field='{c.field}', op='{c.operator}', values={vals}")
        
        # 分析问题
        id_conditions = [c for c in conditions if c.field == 'id']
        
        print(f"\n=== 问题分析 ===")
        print(f"id 条件数: {len(id_conditions)}")
        
        if len(id_conditions) > 1:
            print("[WARNING] 有多个id条件！它们会用AND连接！")
            all_ids_sets = []
            for ic in id_conditions:
                ids = ic.values if hasattr(ic, 'values') else [ic.value]
                all_ids_sets.append(set(ids))
                print(f"  id IN {ids}")
            
            # 计算AND交集
            intersection = all_ids_sets[0]
            for s in all_ids_sets[1:]:
                intersection = intersection & s
            
            print(f"\n  AND交集结果: {intersection}")
            print(f"  预期应包含: {{{parent_domain[0]}, {leaf_domain[0]}}}")
            
            if leaf_domain[0] not in intersection:
                print(f"  [X] 空叶子域 {leaf_domain[0]} ({leaf_domain[1]}) 被排除!")
            
            if parent_domain[0] not in intersection:
                print(f"  [X] 有子节点的域 {parent_domain[0]} 也被排除!")

    def test_api_call_with_mixed_selection(self, ds, auth_headers):
        """API调用验证"""
        app = Flask(__name__)
        app.register_blueprint(manage_bp)
        client = app.test_client()
        
        all_domains = ds.execute(
            "SELECT id FROM domains WHERE version_id = 1"
        ).fetchall()
        
        if len(all_domains) < 2:
            pytest.skip("Need at least 2 domains")
        
        domain_ids = [str(r[0]) for r in all_domains]
        
        qs = "version_id=1&" + "&".join([f"domain_id={d}" for d in domain_ids])
        
        resp = client.get(f"/api/v2/bo/domain?{qs}", headers=auth_headers)
        data = resp.get_json()
        if data is None:
            pytest.skip("API returned non-JSON response")
        
        returned_ids = set(r.get('id') for r in data.get('data', {}).get('items', []))
        expected_ids = set(int(d) for d in domain_ids)
        
        missing = expected_ids - returned_ids
        if missing:
            print(f"\n[X] 缺失的domain IDs: {missing}")
            for mid in sorted(missing):
                name = ds.execute("SELECT name FROM domains WHERE id=?", (mid,)).fetchone()
                print(f"   {mid}: {name[0] if name else '?'}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
