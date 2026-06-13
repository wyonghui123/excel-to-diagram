# -*- coding: utf-8 -*-
"""
GAP-006: enum_api 端到端测试 (15 用例)

[NEW] 2026-06-07 批次: 补齐 enum_api (13 端点) 的端到端测试
- 枚举类型: list / get / create / update / delete / history (6)
- 枚举值:   list / get / create / update / delete / options / query (7)
- 覆盖 happy + 系统枚举只读 + 锁定枚举不可写 + 404
"""
import json
import time
import pytest

pytestmark = pytest.mark.integration


ENUM_URL = '/api/v1'


class TestEnumAPI:
    """enum_api 端到端测试 (GAP-006)"""

    def test_list_enum_types(self, api_client, admin_headers):
        """GET /enum-types 列表"""
        resp = api_client.get(f'{ENUM_URL}/enum-types', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'data' in body
        # data 字段含 data 列表 + total + page + page_size
        assert 'data' in body['data']
        assert 'total' in body['data']

    def test_list_enum_types_with_pagination(self, api_client, admin_headers):
        """GET /enum-types?page=1&pageSize=5 分页"""
        resp = api_client.get(f'{ENUM_URL}/enum-types?page=1&pageSize=5', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert body['data']['page_size'] == 5

    def test_get_enum_type_404(self, api_client, admin_headers):
        """GET /enum-types/<unknown> 404"""
        resp = api_client.get(f'{ENUM_URL}/enum-types/__no_such_enum_type__', headers=admin_headers)
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False
        assert '不存在' in body.get('message', '')

    def test_get_enum_type_history_404(self, api_client, admin_headers):
        """GET /enum-types/<unknown>/history 404"""
        resp = api_client.get(f'{ENUM_URL}/enum-types/__no_such__/history', headers=admin_headers)
        assert resp.status_code == 404

    def test_create_enum_type_missing_fields_400(self, api_client, admin_headers):
        """POST /enum-types 缺 id/name → 400"""
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'description': 'only desc'},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('success') is False

    def test_create_then_get_enum_type(self, api_client, admin_headers):
        """端到端: 创建枚举类型 → 读取 (admin)"""
        enum_id = f'test_enum_{int(time.time())}'
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={
                'id': enum_id,
                'name': 'Test Enum Type',
                'category': 'business',
                'mutability': 'extensible',
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # 立即 GET
        resp2 = api_client.get(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)
        assert resp2.status_code == 200
        assert resp2.get_json()['data']['id'] == enum_id
        # 清理: DELETE
        resp3 = api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)
        assert resp3.status_code == 200

    def test_create_enum_value_in_known_type(self, api_client, admin_headers):
        """POST /enum-types/<id>/values 在已存在类型下创建值"""
        # 先创建类型
        enum_id = f'test_enum_v_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'Test V', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        # 创建值
        resp = api_client.post(
            f'{ENUM_URL}/enum-types/{enum_id}/values',
            json={'code': 'VAL_A', 'name': 'Value A', 'sort_order': 1},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # 清理
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_create_enum_value_in_unknown_type_404(self, api_client, admin_headers):
        """POST /enum-types/<unknown>/values → 404"""
        resp = api_client.post(
            f'{ENUM_URL}/enum-types/__no_type__/values',
            json={'code': 'X', 'name': 'X'},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_create_enum_value_missing_fields_400(self, api_client, admin_headers):
        """POST /enum-types/<id>/values 缺 code/name → 400"""
        enum_id = f'test_ef_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'T', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        resp = api_client.post(
            f'{ENUM_URL}/enum-types/{enum_id}/values',
            json={'sort_order': 1},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_list_enum_options_for_type(self, api_client, admin_headers):
        """GET /enums/<id>/options 轻量级选项 (仅 code/name)"""
        enum_id = f'test_opt_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'Opt', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        resp = api_client.get(f'{ENUM_URL}/enums/{enum_id}/options', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body['data'], list)
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_list_enum_values_for_type(self, api_client, admin_headers):
        """GET /enum-types/<id>/values 完整列表"""
        enum_id = f'test_lv_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'LV', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        resp = api_client.get(f'{ENUM_URL}/enum-types/{enum_id}/values', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'enum_type' in body['data']
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_update_enum_type_404(self, api_client, admin_headers):
        """PUT /enum-types/<unknown> → 404"""
        resp = api_client.put(
            f'{ENUM_URL}/enum-types/__no_such__',
            json={'name': 'New Name'},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_update_enum_type_works(self, api_client, admin_headers):
        """PUT /enum-types/<id> 业务枚举可更新"""
        enum_id = f'test_up_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'UP', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        resp = api_client.put(
            f'{ENUM_URL}/enum-types/{enum_id}',
            json={'name': 'UP Updated', 'description': 'Updated'},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        # 验证
        resp2 = api_client.get(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)
        assert resp2.get_json()['data']['name'] == 'UP Updated'
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_query_enum_values_via_general_endpoint(self, api_client, admin_headers):
        """GET /enum-values?enum_type_id=xxx 通用查询端点
        注: /api/v1/enum-values 已迁移 → 410"""
        enum_id = f'test_qy_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'QY', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        # 缺 enum_type_id → 400 (旧路径可能 410)
        resp = api_client.get(f'{ENUM_URL}/enum-values', headers=admin_headers)
        assert resp.status_code in (400, 410)
        # 含 enum_type_id → 200 或 410
        resp2 = api_client.get(f'{ENUM_URL}/enum-values?enum_type_id={enum_id}', headers=admin_headers)
        assert resp2.status_code in (200, 410)
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_system_enum_is_immutable(self, api_client, admin_headers):
        """系统枚举不可更新 (category='system')"""
        # 找一个系统枚举 (如果有)
        resp = api_client.get(f'{ENUM_URL}/enum-types?category=system', headers=admin_headers)
        if resp.status_code != 200:
            pytest.skip("Cannot filter by category")
        items = resp.get_json()['data']['data']
        if not items:
            pytest.skip("No system enum types")
        sys_enum_id = items[0]['id']
        # 尝试 PUT
        resp2 = api_client.put(
            f'{ENUM_URL}/enum-types/{sys_enum_id}',
            json={'name': 'Hacked Name'},
            headers=admin_headers,
        )
        # 400 + SYSTEM_ENUM_IMMUTABLE
        assert resp2.status_code == 400
        body = resp2.get_json()
        assert 'SYSTEM_ENUM_IMMUTABLE' in body.get('error_code', '') or '不可修改' in body.get('message', '')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [NEW] v3.18 enum-mgmt-spec: FR-001 / FR-006~010 校验测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestEnumAPIValidationFR:
    """
    API 端点的字段校验规则 (FR-001 / FR-006~010)

    FR-001: mutability 值空间校验 (3 档)
    FR-006: enum_value 必填校验
    FR-007: enum_value.code 格式 ^[A-Z][A-Z0-9_]*$
    FR-008: enum_value.code 不可改
    FR-009: (enum_type_id, name) 唯一
    FR-010: enum_type.id 不可改 (BO Action 路径, API 路径 id 来自 URL)
    """

    def _create_business_enum(self, api_client, headers, suffix=None, mutability='extensible'):
        """辅助: 创建一个业务枚举类型并返回 id"""
        import time as _t
        suffix = suffix or f'fr_{int(_t.time()*1000)}'
        enum_id = f'test_{suffix}'
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'FR Test', 'category': 'business', 'mutability': mutability},
            headers=headers,
        )
        assert resp.status_code == 200, f"setup failed: {resp.data}"
        return enum_id

    def _cleanup(self, api_client, headers, enum_id):
        """辅助: 清理"""
        try:
            api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=headers)
        except Exception:
            pass

    # ── FR-001: mutability 值空间校验 (3 档) ──

    @pytest.mark.parametrize('bad_mut', ['mutable', 'immutable', 'frozen', 'fully_editable', 'FULL_EDITABLE'])
    def test_fr001_invalid_mutability_on_create(self, api_client, admin_headers, bad_mut):
        """FR-001: enum_type create 传入非法 mutability → 400 INVALID_MUTABILITY"""
        import time as _t
        enum_id = f'test_fr001_{bad_mut}_{int(_t.time()*1000)}'
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'T', 'category': 'business', 'mutability': bad_mut},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('error_code') == 'INVALID_MUTABILITY' or 'mutability' in body.get('message', '').lower()
        # 清理 (可能创建失败, 不一定成功)
        self._cleanup(api_client, admin_headers, enum_id)

    @pytest.mark.parametrize('bad_mut', ['mutable', 'frozen'])
    def test_fr001_invalid_mutability_on_update(self, api_client, admin_headers, bad_mut):
        """FR-001: enum_type update 传入非法 mutability → 400 INVALID_MUTABILITY"""
        enum_id = self._create_business_enum(api_client, admin_headers, suffix='fr001u')
        try:
            resp = api_client.put(
                f'{ENUM_URL}/enum-types/{enum_id}',
                json={'mutability': bad_mut},
                headers=admin_headers,
            )
            assert resp.status_code == 400
            body = resp.get_json()
            assert body.get('error_code') == 'INVALID_MUTABILITY' or 'mutability' in body.get('message', '').lower()
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    def test_fr001_valid_mutability_fullEditable(self, api_client, admin_headers):
        """FR-001: fullEditable 是合法的"""
        import time as _t
        enum_id = f'test_fr001_fe_{int(_t.time()*1000)}'
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'T', 'category': 'business', 'mutability': 'fullEditable'},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        self._cleanup(api_client, admin_headers, enum_id)

    def test_fr001_valid_mutability_locked(self, api_client, admin_headers):
        """FR-001: locked 是合法的"""
        import time as _t
        enum_id = f'test_fr001_lk_{int(_t.time()*1000)}'
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'T', 'category': 'business', 'mutability': 'locked'},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        self._cleanup(api_client, admin_headers, enum_id)

    # ── FR-006: enum_value create 必填校验 ──

    def test_fr006_missing_code_returns_400(self, api_client, admin_headers):
        """FR-006: enum_value create 缺 code → 400"""
        enum_id = self._create_business_enum(api_client, admin_headers, suffix='fr006a')
        try:
            resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'name': 'No Code', 'sort_order': 1},
                headers=admin_headers,
            )
            assert resp.status_code == 400
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    def test_fr006_missing_name_returns_400(self, api_client, admin_headers):
        """FR-006: enum_value create 缺 name → 400"""
        enum_id = self._create_business_enum(api_client, admin_headers, suffix='fr006b')
        try:
            resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'NO_NAME', 'sort_order': 1},
                headers=admin_headers,
            )
            assert resp.status_code == 400
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    def test_fr006_missing_both_returns_400(self, api_client, admin_headers):
        """FR-006: enum_value create 缺 code 和 name → 400"""
        enum_id = self._create_business_enum(api_client, admin_headers, suffix='fr006c')
        try:
            resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'sort_order': 1},
                headers=admin_headers,
            )
            assert resp.status_code == 400
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    # ── FR-007: enum_value.code 格式 ^[A-Z][A-Z0-9_]*$ ──

    @pytest.mark.parametrize('bad_code', [
        'lowercase', '1NUMBER', '_UNDER', 'has-dash', 'has space', 'with.dot',
    ])
    def test_fr007_invalid_code_format_returns_400(self, api_client, admin_headers, bad_code):
        """FR-007: 非法 code 格式 → 400 INVALID_CODE_FORMAT"""
        enum_id = self._create_business_enum(api_client, admin_headers, suffix='fr007a')
        try:
            resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': bad_code, 'name': 'X'},
                headers=admin_headers,
            )
            assert resp.status_code == 400
            body = resp.get_json()
            assert body.get('error_code') == 'INVALID_CODE_FORMAT' or 'code' in body.get('message', '').lower()
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    @pytest.mark.parametrize('good_code', ['A', 'ABC', 'A_B_C', 'A1B2', 'X1_Y2_Z3', 'A_'])
    def test_fr007_valid_code_format_succeeds(self, api_client, admin_headers, good_code):
        """FR-007: 合法 code 格式 → 200"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr007_{good_code}_{int(_t.time()*1000)}',
        )
        try:
            resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': good_code, 'name': f'Name {good_code}'},
                headers=admin_headers,
            )
            assert resp.status_code == 200, f"good_code '{good_code}' 应通过, 实际: {resp.data}"
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    # ── FR-008: enum_value.code 不可改 ──

    def test_fr008_code_immutable_on_update(self, api_client, admin_headers):
        """FR-008: enum_value update 改 code → 400 CODE_IMMUTABLE"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr008_{int(_t.time()*1000)}',
        )
        try:
            # 先创建值
            create_resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'OLD_CODE', 'name': 'Old'},
                headers=admin_headers,
            )
            assert create_resp.status_code == 200, f"setup failed: {create_resp.data}"

            # 查找刚创建的值 (response 是 {'code': code} 没有 id)
            list_resp = api_client.get(
                f'{ENUM_URL}/enum-types/{enum_id}/values', headers=admin_headers
            )
            # data.data 才是值列表
            values = list_resp.get_json()['data'].get('data', [])
            value_id = next((v['id'] for v in values if v.get('code') == 'OLD_CODE'), None)
            assert value_id, f"setup failed: value not found, got {len(values)} values"

            # 尝试改 code (v1 enum_api 端点)
            resp = api_client.put(
                f'{ENUM_URL}/enum-values/{value_id}',
                json={'code': 'NEW_CODE', 'name': 'New'},
                headers=admin_headers,
            )
            assert resp.status_code == 400
            body = resp.get_json()
            assert body.get('error_code') == 'CODE_IMMUTABLE' or '不可修改' in body.get('message', '')
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    def test_fr008_code_same_value_allowed(self, api_client, admin_headers):
        """FR-008: code 传相同值不算修改 → 200"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr008b_{int(_t.time()*1000)}',
        )
        try:
            create_resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'SAME_CODE', 'name': 'Original'},
                headers=admin_headers,
            )
            assert create_resp.status_code == 200

            list_resp = api_client.get(
                f'{ENUM_URL}/enum-types/{enum_id}/values', headers=admin_headers
            )
            values = list_resp.get_json()['data'].get('data', [])
            value_id = next((v['id'] for v in values if v.get('code') == 'SAME_CODE'), None)
            assert value_id, "setup failed: value not found"

            # 传相同 code (v1 enum_api 端点)
            resp = api_client.put(
                f'{ENUM_URL}/enum-values/{value_id}',
                json={'code': 'SAME_CODE', 'name': 'Updated Name'},
                headers=admin_headers,
            )
            assert resp.status_code == 200, f"传相同 code 应通过, 实际: {resp.data}"
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    # ── FR-009: (enum_type_id, name) 唯一 ──

    def test_fr009_duplicate_name_returns_error(self, api_client, admin_headers):
        """FR-009: 同一 enum_type 下 name 重复 → 400 DUPLICATE_NAME"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr009_{int(_t.time()*1000)}',
        )
        try:
            # 创建第一个
            resp1 = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'FIRST_VAL', 'name': 'Unique Name'},
                headers=admin_headers,
            )
            assert resp1.status_code == 200

            # 创建同名 (不同 code)
            resp2 = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'SECOND_VAL', 'name': 'Unique Name'},
                headers=admin_headers,
            )
            assert resp2.status_code == 400
            body = resp2.get_json()
            assert body.get('error_code') == 'DUPLICATE_NAME' or '已存在' in body.get('message', '')
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    def test_fr009_duplicate_code_returns_error(self, api_client, admin_headers):
        """FR-009: 同一 enum_type 下 code 重复 → 400 DUPLICATE_CODE"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr009c_{int(_t.time()*1000)}',
        )
        try:
            # 创建第一个
            resp1 = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'DUP_CODE', 'name': 'Name 1'},
                headers=admin_headers,
            )
            assert resp1.status_code == 200

            # 创建同 code
            resp2 = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'DUP_CODE', 'name': 'Name 2'},
                headers=admin_headers,
            )
            assert resp2.status_code == 400
            body = resp2.get_json()
            assert body.get('error_code') in ('DUPLICATE_CODE', 'DUPLICATE_NAME') or '已存在' in body.get('message', '')
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    # ── FR-001: 系统枚举不可通过 API 创建 ──

    def test_fr001_system_enum_create_blocked(self, api_client, admin_headers):
        """FR-001: 不可通过 API 创建 category=system 的枚举"""
        import time as _t
        enum_id = f'test_sys_create_{int(_t.time()*1000)}'
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'X', 'category': 'system', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('error_code') == 'SYSTEM_ENUM_IMMUTABLE' or '系统枚举' in body.get('message', '')

    # ── 锁定枚举: enum_value 操作被拒 ──

    def test_locked_enum_blocks_create_value(self, api_client, admin_headers):
        """locked 枚举不可添加值 (FR-006 ~ ENUM_VALUE_LOCKED)"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr_lk_{int(_t.time()*1000)}',
            mutability='locked',
        )
        try:
            resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'NEW_VAL', 'name': 'New'},
                headers=admin_headers,
            )
            assert resp.status_code == 400
            body = resp.get_json()
            assert body.get('error_code') == 'ENUM_VALUE_LOCKED' or '锁定' in body.get('message', '')
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    def test_locked_enum_blocks_update_value(self, api_client, admin_headers):
        """locked 枚举不可改 enum_value (需先创建值再 lock, 这里改 mutability)"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr_lku_{int(_t.time()*1000)}',
            mutability='extensible',
        )
        try:
            # 创建值
            create_resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'VAL_A', 'name': 'Val A'},
                headers=admin_headers,
            )
            assert create_resp.status_code == 200
            list_resp = api_client.get(
                f'{ENUM_URL}/enum-types/{enum_id}/values', headers=admin_headers
            )
            values = list_resp.get_json()['data'].get('data', [])
            value_id = next((v['id'] for v in values if v.get('code') == 'VAL_A'), None)
            assert value_id, "setup failed"

            # 把 mutability 改成 locked
            api_client.put(
                f'{ENUM_URL}/enum-types/{enum_id}',
                json={'mutability': 'locked'},
                headers=admin_headers,
            )

            # 尝试 update value (v1 enum_api 端点)
            resp = api_client.put(
                f'{ENUM_URL}/enum-values/{value_id}',
                json={'name': 'Updated Name'},
                headers=admin_headers,
            )
            assert resp.status_code == 400
            body = resp.get_json()
            assert body.get('error_code') == 'ENUM_VALUE_LOCKED' or '锁定' in body.get('message', '')
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    def test_locked_enum_blocks_delete_value(self, api_client, admin_headers):
        """locked 枚举不可删 enum_value"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr_lkd_{int(_t.time()*1000)}',
            mutability='extensible',
        )
        try:
            create_resp = api_client.post(
                f'{ENUM_URL}/enum-types/{enum_id}/values',
                json={'code': 'VAL_D', 'name': 'Val D'},
                headers=admin_headers,
            )
            assert create_resp.status_code == 200
            list_resp = api_client.get(
                f'{ENUM_URL}/enum-types/{enum_id}/values', headers=admin_headers
            )
            values = list_resp.get_json()['data'].get('data', [])
            value_id = next((v['id'] for v in values if v.get('code') == 'VAL_D'), None)
            assert value_id, "setup failed"

            # 把 mutability 改成 locked
            api_client.put(
                f'{ENUM_URL}/enum-types/{enum_id}',
                json={'mutability': 'locked'},
                headers=admin_headers,
            )

            # 尝试 delete value (v1 enum_api 端点)
            resp = api_client.delete(
                f'{ENUM_URL}/enum-values/{value_id}',
                headers=admin_headers,
            )
            assert resp.status_code == 400
            body = resp.get_json()
            assert body.get('error_code') == 'ENUM_VALUE_LOCKED' or '锁定' in body.get('message', '')
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    # ── 系统预置值 (is_system=true) 保护 ──

    def test_system_value_blocked_update(self, api_client, admin_headers):
        """DEC-2: is_system=true 不可 update"""
        # 找一个 is_system=true 的枚举值 (v1 enum_api 端点, /enums/<id>/options 反查)
        resp = api_client.get(f'{ENUM_URL}/enum-values?is_system=1', headers=admin_headers)
        if resp.status_code == 410:
            # v1 已 sunset, 改用 v2 BO (object_type=enum_value)
            resp = api_client.get(f'/api/v2/bo/enum_value?is_system=1', headers=admin_headers)
        if resp.status_code != 200:
            pytest.skip("Cannot filter by is_system")
        body = resp.get_json()
        items = body.get('data', {}).get('data', []) if isinstance(body.get('data'), dict) else body.get('data', [])
        if not items:
            pytest.skip("No is_system=1 enum values")
        sys_value_id = items[0]['id']
        resp2 = api_client.put(
            f'{ENUM_URL}/enum-values/{sys_value_id}',
            json={'name': 'Hacked'},
            headers=admin_headers,
        )
        if resp2.status_code == 410:
            resp2 = api_client.put(
                f'/api/v2/bo/enum_value/{sys_value_id}',
                json={'name': 'Hacked'},
                headers=admin_headers,
            )
        assert resp2.status_code == 400
        body = resp2.get_json()
        assert body.get('error_code') == 'SYSTEM_VALUE_IMMUTABLE' or '系统预置' in body.get('message', '')

    def test_system_value_blocked_delete(self, api_client, admin_headers):
        """DEC-2: is_system=true 不可 delete"""
        resp = api_client.get(f'{ENUM_URL}/enum-values?is_system=1', headers=admin_headers)
        if resp.status_code == 410:
            resp = api_client.get(f'/api/v2/bo/enum_value?is_system=1', headers=admin_headers)
        if resp.status_code != 200:
            pytest.skip("Cannot filter by is_system")
        body = resp.get_json()
        items = body.get('data', {}).get('data', []) if isinstance(body.get('data'), dict) else body.get('data', [])
        if not items:
            pytest.skip("No is_system=1 enum values")
        sys_value_id = items[0]['id']
        resp2 = api_client.delete(
            f'{ENUM_URL}/enum-values/{sys_value_id}',
            headers=admin_headers,
        )
        if resp2.status_code == 410:
            resp2 = api_client.delete(
                f'/api/v2/bo/enum_value/{sys_value_id}',
                headers=admin_headers,
            )
        assert resp2.status_code == 400
        body = resp2.get_json()
        assert body.get('error_code') == 'SYSTEM_VALUE_IMMUTABLE' or '系统预置' in body.get('message', '')

    # ── FR-012: ui_actions_resolved 字段 ──

    def test_fr012_get_enum_type_includes_ui_actions_resolved(self, api_client, admin_headers):
        """FR-012: GET /enum-types/<id> 应返回 ui_actions_resolved 字段"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr012_{int(_t.time()*1000)}',
        )
        try:
            resp = api_client.get(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)
            assert resp.status_code == 200
            data = resp.get_json()['data']
            assert 'ui_actions_resolved' in data, f"缺少 ui_actions_resolved 字段: {list(data.keys())}"
            actions = data['ui_actions_resolved']
            # 验证 6 个 action 都在
            for key in ('create_value', 'update_value', 'delete_value', 'toggle_active', 'update_type', 'delete_type'):
                assert key in actions, f"ui_actions_resolved 缺少 '{key}': {list(actions.keys())}"
                assert isinstance(actions[key], bool), f"{key} 应是 bool, 实际 {type(actions[key])}"
        finally:
            self._cleanup(api_client, admin_headers, enum_id)

    def test_fr012_locked_enum_value_actions_blocked(self, api_client, admin_headers):
        """FR-012: locked 枚举的 value_actions 全部 False"""
        import time as _t
        enum_id = self._create_business_enum(
            api_client, admin_headers,
            suffix=f'fr012l_{int(_t.time()*1000)}',
            mutability='locked',
        )
        try:
            resp = api_client.get(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)
            actions = resp.get_json()['data']['ui_actions_resolved']
            assert actions['create_value'] is False
            assert actions['update_value'] is False
            assert actions['delete_value'] is False
            assert actions['toggle_active'] is False
            # update_type 仍可 (业务枚举可改)
            assert actions['update_type'] is True
            # delete_type: 0 values → 可删
            assert actions['delete_type'] is True
        finally:
            self._cleanup(api_client, admin_headers, enum_id)
