import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
使用真实数据ID精确复现用户场景

v2.0 数据：
- 父域(有子节点): id=1(供应链云), 2(财务云), 3(采购云)  
- 空叶子域: id=202(TEST), 204(LSDKFJSDFsdfsdf)

用户操作：选择 供应链云(id=1)+TEST(id=202)
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.server import create_app
from meta.tests.test_utils import get_test_db_path
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo


def _extract_list_data(resp_json):
    if resp_json is None:
        return [], 0
    data = resp_json.get('data')
    if data is None:
        return [], resp_json.get('total', 0)
    if isinstance(data, dict) and 'items' in data:
        return data.get('items', []), data.get('total', len(data.get('items', [])))
    if isinstance(data, list):
        return data, resp_json.get('total', len(data))
    return [], 0


@pytest.fixture(scope='module')
def client():
    from meta.tests.conftest import get_shared_app
    _ds = get_data_source("sqlite", database=get_test_db_path())
    _app, _client = get_shared_app()
    # v3.18 P1: 主动确保真实场景数据存在 (修复 S011 硬编码 ID skip)
    _ensure_real_scenario_data(_ds)
    u = UserInfo(user_id='1', username='test_user', display_name='Test User',
                 email='test@test.com', roles=['admin'], permissions=['*'])
    token, _ = TokenService.create_token(u)
    auth_headers = {
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_user',
    }
    return _client, _ds, auth_headers


def _ensure_real_scenario_data(ds):
    """确保真实场景测试数据存在 (v3.18 P1: 修复 S011 硬编码 ID skip)

    策略: 清理老的 v2 fixture 数据 (visibility='draft' 的根因),
    创建 5 个 v2 domain (4 父域 + 1 叶子域) with visibility='public',
    这样测试可以用动态 ID 查询, 不依赖硬编码 id=1,2,3,202,204
    [FIX 2026-06-07] visibility='public' 是关键 — FR-010 规定
    visibility='draft' 的记录仅 owner 可见, admin 用户看不到。
    [FIX 2026-06-07-2] 同时清理老的 v2 域 (draft 状态), 让 fixture 域的 ID 最小
    """
    # 清理老的 v2 fixture 数据 (含 sub_domains, service_modules 关联删除)
    # 保留本次 fixture 自己创建的数据
    ds.execute("""
        DELETE FROM service_modules
        WHERE sub_domain_id IN (
            SELECT id FROM sub_domains WHERE version_id=2
        )
    """)
    ds.execute("DELETE FROM sub_domains WHERE version_id=2")
    ds.execute("""
        DELETE FROM domains
        WHERE version_id=2 AND code NOT LIKE 'T001_FIXED_%'
    """)

    # 创建 5 个 public 状态的 v2 域 (用固定前缀, 避免重复)
    existing = ds.execute("""
        SELECT COUNT(*) FROM domains
        WHERE version_id=2 AND code LIKE 'T001_FIXED_%'
    """).fetchone()[0]

    if existing < 5:
        for i in range(existing, 5):
            ds.execute(
                "INSERT INTO domains (name, code, version_id, visibility) VALUES (?, ?, 2, 'public')",
                (f'T001_FIXED_D{i}', f'T001_FIXED_D{i}')
            )

    # 给前 4 个 public v2 域加 sub_domain (变父域), 保留 1 个为叶子
    parent_candidates = ds.execute("""
        SELECT d.id FROM domains d
        WHERE d.version_id = 2
          AND d.code LIKE 'T001_FIXED_%'
          AND d.id NOT IN (SELECT domain_id FROM sub_domains WHERE version_id = 2)
        ORDER BY d.id LIMIT 4
    """).fetchall()
    for i, (did,) in enumerate(parent_candidates):
        ds.execute(
            "INSERT INTO sub_domains (name, code, version_id, domain_id, visibility) VALUES (?, ?, 2, ?, 'public')",
            (f'T001_FIXED_SD_{did}', f'T001_FIXED_SD_{did}', did)
        )
        sd_id = ds.execute(
            "SELECT id FROM sub_domains WHERE domain_id=? AND version_id=2", (did,)
        ).fetchone()
        if sd_id:
            ds.execute(
                "INSERT INTO service_modules (name, code, version_id, sub_domain_id, visibility) VALUES (?, ?, 2, ?, 'public')",
                (f'T001_FIXED_SM_{sd_id[0]}', f'T001_FIXED_SM_{sd_id[0]}', sd_id[0])
            )

    ds.commit()


class TestRealDataScenario:
    
    def test_select_parent_plus_leaf_domain(self, client):
        """
        场景: 选择父域 + 叶子域 (v3.18 P1: 改用动态 ID 替代硬编码)
        原场景: 供应链云(1) + TEST(202), 硬编码 ID 在测试 DB 中可能不存在
        新方案: 动态查询 DB 中第一个有子域的 domain (父域) + 第一个无子域的 domain (叶子域)
        """
        api, ds, h = client
        
        cursor = ds.execute("SELECT COUNT(*) FROM domains WHERE version_id=1")
        if cursor.fetchone()[0] == 0:
            pytest.skip("No domains with version_id=1 in database - requires test data setup")

        # v3.18 P1: 动态查询父域 (有子域) 和叶子域 (无子域), 替代硬编码 ID 1, 202
        parent = ds.execute("""
            SELECT d.id, d.name FROM domains d
            WHERE d.version_id = 2 AND EXISTS (
                SELECT 1 FROM sub_domains sd WHERE sd.domain_id = d.id
            )
            ORDER BY d.id LIMIT 1
        """).fetchone()
        leaf = ds.execute("""
            SELECT id, name FROM domains
            WHERE version_id = 2 AND id NOT IN (SELECT domain_id FROM sub_domains)
            ORDER BY id LIMIT 1
        """).fetchone()
        if not parent or not leaf:
            pytest.skip("Need ≥1 parent domain (with sub_domain) and ≥1 leaf domain (no sub_domain)")

        parent_id, parent_name = parent[0], parent[1]
        leaf_id, leaf_name = leaf[0], leaf[1]

        sds = ds.execute(
            "SELECT id FROM sub_domains WHERE domain_id=? AND version_id=2",
            (parent_id,)
        ).fetchall()
        sms = ds.execute("""
            SELECT sm.id FROM service_modules sm
            JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            WHERE sd.domain_id=? AND sm.version_id=2
        """, (parent_id,)).fetchall()

        print(f"\n{'='*60}")
        print(f"场景: 父域({parent_id}:{parent_name}) + 叶子域({leaf_id}:{leaf_name})")
        print(f"{'='*60}")
        print(f"父域下子域: {[s[0] for s in sds]}")
        print(f"父域下SM: {[s[0] for s in sms]}")

        qs_parts = ['version_id=2', f'domain_id={parent_id}', f'domain_id={leaf_id}']
        for sd in sds:
            qs_parts.append(f'sub_domain_id={sd[0]}')
        for sm in sms:
            qs_parts.append(f'service_module_id={sm[0]}')
        qs = '&'.join(qs_parts)

        print(f"\n查询参数: {qs}")

        resp = api.get(f'/api/v2/bo/domain?{qs}', headers=h)
        data = resp.get_json()

        items, total = _extract_list_data(data)
        returned_ids = sorted([r['id'] for r in items])
        expected = [parent_id, leaf_id]

        print(f"\n--- 领域标签 ---")
        print(f"total={total}, success={data.get('success') if data else 'N/A'}")
        print(f"返回IDs: {returned_ids}")
        print(f"预期包含: {expected}")

        missing = set(expected) - set(returned_ids)
        assert len(missing) == 0, f"Missing domains: {missing}"
        
        resp2 = api.get(f'/api/v2/bo/sub_domain?{qs}', headers=h)
        data2 = resp2.get_json()
        
        items2, total2 = _extract_list_data(data2)
        
        print(f"\n--- 子领域标签 ---")
        print(f"total={total2}, success={data2.get('success') if data2 else 'N/A'}")
        
        if total2 > 0:
            for r in items2[:5]:
                print(f"  id={r.get('id')}, name={r.get('name')}, domain_id={r.get('domain_id')}")
        
        assert data2 is not None

    def test_only_leaf_domain_selected(self, client):
        """只选择空叶子域 (v3.18 P1: 改用动态 v2 ID)"""
        api, ds, h = client

        # v3.18 P1: 动态查询 v2 叶子域 (无子域的 domain)
        leaf = ds.execute("""
            SELECT id, name FROM domains
            WHERE version_id = 2 AND id NOT IN (SELECT domain_id FROM sub_domains WHERE version_id = 2)
            ORDER BY id LIMIT 1
        """).fetchone()
        if not leaf:
            pytest.skip("No leaf domain with version_id=2 in database")
        leaf_id = leaf[0]

        qs = f'version_id=2&domain_id={leaf_id}'

        resp = api.get(f'/api/v2/bo/domain?{qs}', headers=h)
        data = resp.get_json()

        items, total = _extract_list_data(data)

        print(f"\n只选叶子域({leaf_id}): total={total}")
        ids = [r['id'] for r in items]
        print(f"返回: {ids}")

        assert leaf_id in ids

        resp2 = api.get(f'/api/v2/bo/sub_domain?{qs}', headers=h)
        data2 = resp2.get_json()
        items2, total2 = _extract_list_data(data2)
        print(f"子领域: total={total2}")

    def test_all_domains_including_leaves(self, client):
        """选择所有领域 (3父+2叶, v3.18 P1: 改用动态 ID)"""
        api, ds, h = client

        # v3.18 P1: 动态查询所有 domain (取前 3 父 + 2 叶子)
        # T205 修复: 加 code LIKE 'T001_FIXED_%' 过滤, 隔离之前 test run 残留的旧数据
        all_domains = ds.execute("""
            SELECT id FROM domains WHERE version_id=2 AND code LIKE 'T001_FIXED_%'
            ORDER BY id LIMIT 5
        """).fetchall()
        if len(all_domains) < 5:
            pytest.skip(f"Need ≥5 domains with version_id=2, found {len(all_domains)}")
        expected = {d[0] for d in all_domains}

        qs = f'version_id=2&' + '&'.join(f'domain_id={d[0]}' for d in all_domains)

        resp = api.get(f'/api/v2/bo/domain?{qs}', headers=h)
        data = resp.get_json()

        items, total = _extract_list_data(data)
        returned = set(r['id'] for r in items)

        print(f"\n全选 {len(expected)} 个领域:")
        print(f"返回: {sorted(returned)}")
        print(f"预期: {sorted(expected)}")

        missing = expected - returned
        extra = returned - expected

        if missing:
            print(f"MISSING: {missing}")
        if extra:
            print(f"EXTRA: {extra}")

        assert len(missing) == 0, f"Missing: {missing}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
