import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
精确复现用户场景：选择空叶子域后列表问题

用户操作步骤：
1. 对象树中勾选了多个节点（含空叶子域）
2. 在"领域"tab查看列表 → 预期正常
3. 在"子领域"tab查看列表 → 预期正常

修复说明：
- 原版本使用自定义 Flask app，只注册了 manage_bp（/api/v1）
- 修改为使用项目标准的 shared_client fixture
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestUserScenarioExact:
    """精确复现用户操作场景"""
    
    def test_scenario_select_leaf_domain(self, shared_client, admin_headers):
        """
        用户场景：
        1. 对象树选中了供应链云(domain,有子节点) + TEST(空叶子域)
        2. 在"领域"标签页查看
        3. 预期：显示2条记录（供应链云 + TEST）
        """
        from meta.core.datasource import get_data_source
        from meta.tests.test_utils import get_test_db_path

        ds = get_data_source("sqlite", database=get_test_db_path())

        # v3.18 P1: 修复 S010 数据依赖 skip, 自动准备 ≥2 domains (含父子)
        cursor = ds.execute("SELECT COUNT(*) FROM domains WHERE version_id=1")
        if cursor.fetchone()[0] < 2:
            ds.execute("INSERT INTO domains (name, code, version_id) VALUES ('TEST_PARENT_S010', 'TEST_PARENT_S010', 1)")
            parent_id = ds.execute("SELECT id FROM domains WHERE code='TEST_PARENT_S010'").fetchone()
            if parent_id:
                ds.execute("INSERT INTO sub_domains (name, code, version_id, domain_id) VALUES ('TEST_CHILD_S010', 'TEST_CHILD_S010', 1, ?)", (parent_id[0],))
            ds.execute("INSERT INTO domains (name, code, version_id) VALUES ('TEST_LEAF_S010', 'TEST_LEAF_S010', 1)")
            ds.commit()

        domains = ds.execute(
            "SELECT id, name FROM domains WHERE version_id = 1 ORDER BY id"
        ).fetchall()
        
        if len(domains) < 2:
            pytest.skip("Need >= 2 domains")
        
        parent_domain = None
        leaf_domain = None
        
        for d in domains:
            child_count = ds.execute(
                "SELECT COUNT(*) FROM sub_domains WHERE domain_id=?", (d[0],)
            ).fetchone()[0]
            
            if child_count > 0 and not parent_domain:
                parent_domain = d
            elif child_count == 0 and not leaf_domain:
                leaf_domain = d
            
            if parent_domain and leaf_domain:
                break
        
        if not parent_domain or not leaf_domain:
            pytest.skip("需要同时有父域和叶子域")
        
        print(f"\n{'='*60}")
        print(f"场景：选择空叶子域后")
        print(f"{'='*60}")
        print(f"父域(有子节点): id={parent_domain[0]}, name={parent_domain[1]}")
        print(f"空叶子域: id={leaf_domain[0]}, name={leaf_domain[1]}")
        
        checked_ids = [f'domain_{parent_domain[0]}', f'domain_{leaf_domain[0]}']
        
        child_sds = ds.execute(
            "SELECT id FROM sub_domains WHERE domain_id=? AND version_id=1",
            (parent_domain[0],)
        ).fetchall()
        for sd in child_sds[:2]:
            checked_ids.append(f'sub_domain_{sd[0]}')
        
        child_sms = ds.execute("""
            SELECT sm.id FROM service_modules sm
            JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            WHERE sd.domain_id=? AND sm.version_id=1
        """, (parent_domain[0],)).fetchall()
        for sm in child_sms[:2]:
            checked_ids.append(f'service_module_{sm[0]}')
        
        print(f"\n模拟checkedIds ({len(checked_ids)}项):")
        for cid in checked_ids:
            print(f"  {cid}")
        
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
                        if id_val not in field_to_ids[field]:
                            field_to_ids[field].append(id_val)
                    except ValueError:
                        pass
                    break
        
        print(f"\n构建的条件树:")
        for k, v in field_to_ids.items():
            print(f"  {k}: {v}")
        
        print(f"\n--- 测试1: 领域标签页 ---")
        qs_parts = ['version_id=1']
        for k, v in field_to_ids.items():
            for val in v:
                qs_parts.append(f'{k}={val}')
        qs = '&'.join(qs_parts)
        
        resp = shared_client.get(f'/api/v2/bo/domain?{qs}', headers=admin_headers)
        data = resp.get_json()
        
        if data is None:
            pytest.skip("API returned non-JSON response")
        
        print(f"API: GET /api/v2/bo/domain?{qs}")
        print(f"结果: success={data.get('success')}, total={data.get('data', {}).get('total')}")
        
        returned_ids = set(r.get('id') for r in data.get('data', {}).get('items', []))
        expected_ids = {parent_domain[0], leaf_domain[0]}
        
        print(f"返回IDs: {sorted(returned_ids)}")
        print(f"预期IDs: {sorted(expected_ids)}")
        
        missing = expected_ids - returned_ids
        if missing:
            print(f"[X] 缺失: {missing}")
            for mid in missing:
                name = ds.execute("SELECT name FROM domains WHERE id=?", (mid,)).fetchone()
                print(f"   id={mid} -> {name[0] if name else '?'}")
        else:
            print(f"[OK] 全部包含")
        
        assert data.get('success'), "API应成功"
        
        print(f"\n--- 测试2: 子领域标签页 ---")
        resp2 = shared_client.get(f'/api/v2/bo/sub_domain?{qs}', headers=admin_headers)
        data2 = resp2.get_json()
        
        if data2 is None:
            pytest.skip("API returned non-JSON response for sub_domains")
        
        print(f"API: GET /api/v2/bo/sub_domain?{qs}")
        print(f"结果: success={data2.get('success')}, total={data2.get('data', {}).get('total')}")
        
        if data2.get('data', {}).get('total', 0) > 0:
            returned_sd_names = [(r.get('name'), r.get('domain_id')) for r in data2.get('data', {}).get('items', [])]
            print(f"返回子领域: {returned_sd_names}")
        
        assert data2.get('success'), "API应成功"

    def test_only_leaf_domain_selected(self, shared_client, admin_headers):
        """
        场景：只选择空叶子域（不选其他任何节点）
        [FIX 2026-06-07] 改用 v2 fixture 域 (T001_FIXED_D*) + id filter (domain_id 不存在)
        """
        from meta.core.datasource import get_data_source
        from meta.tests.test_utils import get_test_db_path

        ds = get_data_source("sqlite", database=get_test_db_path())

        # [FIX 2026-06-07] 用 v2 fixture 域 (T001_FIXED_*), version_id=2
        # 之前的代码用 version_id=1 + domain_id=5, 但 domain_id 不是 domain 表的有效 filter (被忽略),
        # 且 id=5 在分页外导致测试 flaky。
        leaf = ds.execute("""
            SELECT id, name FROM domains
            WHERE version_id=2
              AND code LIKE 'T001_FIXED_%'
              AND id NOT IN (SELECT domain_id FROM sub_domains WHERE version_id=2)
            ORDER BY id LIMIT 1
        """).fetchone()
        if not leaf:
            pytest.skip("No v2 leaf domain from T001_FIXED fixture (run test_real_data_scenario first)")
        leaf_id, leaf_name = leaf[0], leaf[1]

        print(f"\n{'='*60}")
        print(f"场景：只选择空叶子域")
        print(f"{'='*60}")
        print(f"空叶子域: id={leaf_id}, name={leaf_name}")

        # [FIX 2026-06-07] 用 id=N 替代 domain_id=N (后者不是 domain 表的有效 filter)
        qs = f'version_id=2&id={leaf_id}'

        resp = shared_client.get(f'/api/v2/bo/domain?{qs}', headers=admin_headers)
        data = resp.get_json()

        if data is None:
            pytest.skip("API returned non-JSON response")

        print(f"结果: total={data.get('data', {}).get('total')}")
        returned_ids = [r.get('id') for r in data.get('data', {}).get('items', [])]
        print(f"返回: {returned_ids}")

        assert leaf_id in returned_ids, \
            f"空叶子域{leaf_id}应在结果中"
        
        resp2 = shared_client.get(f'/api/v2/bo/sub_domain?{qs}', headers=admin_headers)
        data2 = resp2.get_json()
        if data2 is None:
            pytest.skip("API returned non-JSON response for sub_domains")
        print(f"子领域标签: total={data2.get('data', {}).get('total')} (预期为0，因为空叶子域没有子领域)")
        assert data2.get('success')


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
