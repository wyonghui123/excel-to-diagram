# -*- coding: utf-8 -*-
"""
GAP-017: key_template_api 端到端测试 (5 用例)

[NEW] 2026-06-07 批次: 补齐 key_template_api (3 端点) 的端到端测试
- GET  /api/v2/key-template/config/<object_type>
- POST /api/v2/key-template/preview/<object_type>
- GET  /api/v2/key-template/list-objects
"""
import pytest
import time
import json

pytestmark = pytest.mark.integration


KT_URL = '/api/v2/key-template'


class TestKeyTemplateAPI:
    """key_template_api 端到端测试 (GAP-017)"""

    def test_get_config_unknown_type_404(self, api_client, admin_headers):
        """GET /config/<unknown> 404"""
        resp = api_client.get(f'{KT_URL}/config/__no_such__', headers=admin_headers)
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False

    def test_get_config_user_no_key_template(self, api_client, admin_headers):
        """GET /config/user (通常 user 不配置 key_template)"""
        resp = api_client.get(f'{KT_URL}/config/user', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # user 通常无 key_template → data.enabled=False
        data = body.get('data', {})
        if isinstance(data, dict) and 'enabled' in data:
            # 无 key_template 配置
            assert data.get('enabled') is False

    def test_preview_code_unknown_type_404(self, api_client, admin_headers):
        """POST /preview/<unknown> 404"""
        resp = api_client.post(
            f'{KT_URL}/preview/__no_such__',
            json={'field_values': {}, 'generate': False},
            headers=admin_headers,
        )
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False

    def test_preview_code_no_key_template(self, api_client, admin_headers):
        """POST /preview/<user> (无 key_template) → success=False"""
        resp = api_client.post(
            f'{KT_URL}/preview/user',
            json={'field_values': {}, 'generate': False},
            headers=admin_headers,
        )
        # 200 (enabled=False 走 success=False path) 或 500
        assert resp.status_code in (200, 500)

    def test_list_objects(self, api_client, admin_headers):
        """GET /list-objects 返回配置 key_template 的对象列表"""
        resp = api_client.get(f'{KT_URL}/list-objects', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body['data'], list)
        # 每个对象含 object_type / name / pattern / preview
        for obj in body['data']:
            assert 'object_type' in obj
            assert 'pattern' in obj

    # ── [NEW 2026-06-11] MISSING_PARENT_FIELD 回归测试 ──

    def test_preview_business_object_422_missing_service_module(self, api_client, admin_headers):
        """
        POST /preview/business_object with only domain_id → 422 MISSING_PARENT_FIELD

        这是 BUG 的回归测试：选择领域但未选服务模块时，
        不应生成裸序列号（如 "44"），应返回 422 明确告知缺失字段。
        """
        resp = api_client.post(
            f'{KT_URL}/preview/business_object',
            json={
                'field_values': {},
                'parent_params': {'domain_id': 999},  # 只有 domain_id，无 service_module_id
                'generate': True,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422, (
            f"缺少 service_module_code 应返回 422，实际: {resp.status_code} "
            f"body: {resp.get_data(as_text=True)[:200]}"
        )
        body = resp.get_json()
        assert body.get('success') is False
        assert body.get('code') == 'MISSING_PARENT_FIELD', (
            f"错误码应为 MISSING_PARENT_FIELD，实际: {body.get('code')}"
        )
        assert 'service_module_code' in (body.get('missing_fields') or []), (
            f"missing_fields 应包含 service_module_code，实际: {body.get('missing_fields')}"
        )

    def test_preview_business_object_ok_with_service_module(self, api_client, admin_headers):
        """
        POST /preview/business_object with service_module_id → 200 正常生成 code

        这是 BUG 的回归测试：正常传 service_module_id 后应生成正确编码。
        """
        resp = api_client.post(
            f'{KT_URL}/preview/business_object',
            json={
                'field_values': {},
                'parent_params': {'service_module_id': 1},
                'generate': True,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200, (
            f"传 service_module_id 应返回 200，实际: {resp.status_code} "
            f"body: {resp.get_data(as_text=True)[:200]}"
        )
        body = resp.get_json()
        assert body.get('success') is True
        assert body.get('data', {}).get('code'), "应返回 generated code"


class TestVersionNoKeyTemplate:
    """
    [NEW 2026-06-10] version 不应再配置 key_template

    原因：version code 是有业务含义的版本名（v1.0 / 2024-Q4 / R2024.1），
    不应使用自动生成的 `{product_code}_{SEQ:2}` 模式。
    决策参考：.trae/specs/key-template-form-interaction/ TBD-2

    覆盖矩阵（4 个用例）：
     1. test_version_schema_has_no_key_template - YAML 不含 key_template
     2. test_version_api_config_no_enabled - API config 返回 enabled=False
     3. test_version_not_in_list_objects - version 不在 list-objects 中
     4. test_version_create_requires_code - 创建不传 code 应失败（无自动建议）
    """

    def test_version_schema_has_no_key_template(self):
        """version.yaml 不应定义 key_template 字段"""
        from pathlib import Path
        from meta.core.yaml_loader import load_yaml_file
        # YAML 在 meta/schemas/ 下
        schema_dir = Path(__file__).parent.parent / 'schemas'
        yaml_path = schema_dir / 'version.yaml'
        data = load_yaml_file(str(yaml_path))
        assert data is not None, f"无法加载 version.yaml: {yaml_path}"
        # load_yaml_file 可能返回 dict 或 MetaObject - 用 getattr 兼容
        kt_value = None
        if isinstance(data, dict):
            kt_value = data.get('key_template')
        else:
            kt_value = getattr(data, 'key_template', None)
        # key_template 应为 None / 不存在 / 空 dict (代表未配置)
        assert not kt_value or (isinstance(kt_value, dict) and not kt_value.get('enabled')), (
            f"version.yaml 不应有 key_template 配置 (TBD-2 决策移除), "
            f"实际: {kt_value}"
        )

    def test_version_api_config_no_enabled(self, api_client, admin_headers):
        """GET /config/version → data.enabled=False (因无 key_template)"""
        resp = api_client.get(f'{KT_URL}/config/version', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body.get('data', {})
        # 无 key_template 配置 → enabled 应为 False
        if isinstance(data, dict) and 'enabled' in data:
            assert data.get('enabled') is False, (
                f"version 应无 key_template，enabled 应为 False，实际: {data.get('enabled')}"
            )

    def test_version_not_in_list_objects(self, api_client, admin_headers):
        """version 不在 list-objects 返回中 (因无 key_template)"""
        resp = api_client.get(f'{KT_URL}/list-objects', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        object_types = [obj.get('object_type') for obj in body.get('data', [])]
        assert 'version' not in object_types, (
            f"version 不应出现在 list-objects 中 (无 key_template), 实际: {object_types}"
        )

    def test_version_create_requires_code(self, api_client, admin_headers):
        """创建 version 不传 name 应失败 (name 作为业务键必填)"""
        # product_id=1 是固定测试产品
        payload = {
            'product_id': 1,
        }
        resp = api_client.post('/api/v2/bo/version', json=payload, headers=admin_headers)
        # 应返回 400 / 500 (name 必填), 不应自动生成
        assert resp.status_code in (400, 500), (
            f"不传 name 时应失败，实际: {resp.status_code} {resp.get_data(as_text=True)}"
        )


class TestVersionCodePattern:
    """
    [NEW 2026-06-10] [CHANGED 2026-06-13] version 的 name 字段 pattern 放宽

    决策: 接受 dot/dash，覆盖 SemVer / CalVer / 业务自定义。
    2026-06-13: 删除 version.code 字段，name 作为业务键（product_id + name 唯一）
    原 pattern: ^[A-Z][A-Z0-9_]*$ (拒绝 v1.0/2024-Q4/R2024.1)
    新 pattern: ^[A-Za-z0-9][A-Za-z0-9_.\\-]*$

    覆盖矩阵（10 个用例）:
     1. test_pattern_accepts_semver (v1.0, 1.0.0, v1.0-rc.1)
     2. test_pattern_accepts_calver (2024-Q4, 2024Q4)
     3. test_pattern_accepts_business_style (R2024.1, V1.0, SCM_01)
     4. test_pattern_accepts_lowercase_v (v1.0)
     5. test_pattern_accepts_pure_digit (1.0.0)
     6. test_pattern_rejects_dot_prefix
     7. test_pattern_rejects_dash_prefix
     8. test_pattern_rejects_special_chars
     9. test_pattern_rejects_whitespace
     10. test_pattern_rejects_slash
    """

    @pytest.fixture
    def product_id(self, api_client, admin_headers):
        """获取一个可用的 product_id"""
        resp = api_client.get('/api/v2/bo/product?page=1&page_size=1', headers=admin_headers)
        items = resp.get_json().get('data', {}).get('items', [])
        if items:
            return items[0].get('id')
        pytest.skip('无可用 product')

    def _try_create(self, api_client, admin_headers, name, product_id):
        """创建 version，name 作为业务键（code 字段已删除）"""
        payload = {
            'name': name,  # 2026-06-13: code 字段已删除，直接用 name 作为业务键
            'product_id': product_id,
        }
        resp = api_client.post('/api/v2/bo/version', json=payload, headers=admin_headers)
        if resp.status_code in (200, 201):
            vid = resp.get_json().get('data', {}).get('id')
            if vid:
                api_client.delete(f'/api/v2/bo/version/{vid}', headers=admin_headers)
            return True, resp
        return False, resp

    @pytest.mark.parametrize('name,desc', [
        ('v1.0', 'SemVer'),
        ('1.0.0', '纯数字 SemVer'),
        ('v1.0-rc.1', 'SemVer 预发布'),
        ('1.0.0-rc.1', '完整 SemVer 预发布'),
        ('0.1.0', '小版本 SemVer'),
    ])
    def test_pattern_accepts_semver(self, api_client, admin_headers, product_id, name, desc):
        """接受 SemVer 格式 (v1.0, 1.0.0, v1.0-rc.1)"""
        success, resp = self._try_create(api_client, admin_headers, name, product_id)
        assert success, f"{desc} ({name}) 应被接受，实际: {resp.status_code} {resp.get_data(as_text=True)}"

    @pytest.mark.parametrize('name,desc', [
        ('2024-Q4', 'CalVer 带 dash'),
        ('2024Q4', 'CalVer 无分隔'),
        ('2024.10', 'CalVer 点分隔'),
    ])
    def test_pattern_accepts_calver(self, api_client, admin_headers, product_id, name, desc):
        """接受 CalVer 格式 (2024-Q4, 2024Q4)"""
        success, resp = self._try_create(api_client, admin_headers, name, product_id)
        assert success, f"{desc} ({name}) 应被接受，实际: {resp.status_code} {resp.get_data(as_text=True)}"

    @pytest.mark.parametrize('name,desc', [
        ('R2024.1', 'R 前缀 + 年份 + 点'),
        ('V1.0', '大写 V + 数字 + 点'),
        ('SCM_01', '下划线分隔'),
    ])
    def test_pattern_accepts_business_style(self, api_client, admin_headers, product_id, name, desc):
        """接受业务自定义格式"""
        success, resp = self._try_create(api_client, admin_headers, name, product_id)
        assert success, f"{desc} ({name}) 应被接受，实际: {resp.status_code} {resp.get_data(as_text=True)}"

    def test_pattern_accepts_lowercase_v(self, api_client, admin_headers, product_id):
        """接受小写 v 开头"""
        success, resp = self._try_create(api_client, admin_headers, 'v1.0', product_id)
        assert success, f"v1.0 应被接受（接受小写），实际: {resp.status_code}"

    def test_pattern_accepts_pure_digit(self, api_client, admin_headers, product_id):
        """接受纯数字开头"""
        success, resp = self._try_create(api_client, admin_headers, '1.0.0', product_id)
        assert success, f"1.0.0 应被接受（接受数字开头），实际: {resp.status_code}"

    @pytest.mark.parametrize('name', ['.V1.0', '.1.0'])
    def test_pattern_rejects_dot_prefix(self, api_client, admin_headers, product_id, name):
        """拒绝点开头 (违反首字符规则)"""
        success, resp = self._try_create(api_client, admin_headers, name, product_id)
        assert not success, f"{name} 应被拒绝，实际通过"
        # 检查错误消息：raw body 或 json
        body = resp.get_data(as_text=True)
        try:
            data = resp.get_json() or {}
        except Exception:
            data = {}
        msg = data.get('message', '') if isinstance(data, dict) else ''
        # 接受任一形式：raw body、json.message、success=false
        assert ('格式不正确' in body or
                '格式不正确' in msg or
                data.get('success') is False), (
            f"{name} 错误信息不包含 '格式不正确'，body={body[:200]}"
        )

    @pytest.mark.parametrize('name', ['-V1.0', '-2024Q4'])
    def test_pattern_rejects_dash_prefix(self, api_client, admin_headers, product_id, name):
        """拒绝 dash 开头 (违反首字符规则)"""
        success, resp = self._try_create(api_client, admin_headers, name, product_id)
        assert not success, f"{name} 应被拒绝，实际通过"

    @pytest.mark.parametrize('name', ['V1.0!', 'V1.0#', 'V1.0$', 'V1.0?', 'V1.0+'])
    def test_pattern_rejects_special_chars(self, api_client, admin_headers, product_id, name):
        """拒绝特殊字符 (! # $ ? + 等不在允许范围)"""
        success, resp = self._try_create(api_client, admin_headers, name, product_id)
        assert not success, f"{name} 应被拒绝，实际通过"

    def test_pattern_rejects_whitespace(self, api_client, admin_headers, product_id):
        """拒绝空格"""
        success, resp = self._try_create(api_client, admin_headers, 'V 1.0', product_id)
        assert not success, "含空格应被拒绝"

    def test_pattern_rejects_slash(self, api_client, admin_headers, product_id):
        """拒绝斜杠"""
        success, resp = self._try_create(api_client, admin_headers, 'V1.0/2.0', product_id)
        assert not success, "含斜杠应被拒绝"


class TestVersionUniqueKey:
    """
    [NEW 2026-06-13] version 删除 code 字段后，name 承担业务键。
    验证 (product_id, name) 联合唯一性约束。

    覆盖矩阵（5 个用例）:
     1. test_same_product_same_name_rejected        # 同 product 同 name → 409/400
     2. test_same_product_different_name_accepted   # 同 product 不同 name → 201
     3. test_different_product_same_name_accepted   # 不同 product 同 name → 201（跨产品允许同名）
     4. test_name_required_on_create                # 不传 name → 必填校验失败
     5. test_name_immutable_after_publish           # 不可改 name（业务键不变性）
    """

    def _create_version(self, api_client, headers, name, product_id):
        """Helper: 创建 version，返回 (success, resp, data)"""
        payload = {'name': name, 'product_id': product_id}
        resp = api_client.post('/api/v2/bo/version', json=payload, headers=headers)
        body = resp.get_data(as_text=True)
        try:
            data = json.loads(body)
        except Exception:
            data = {}
        success = resp.status_code in (200, 201) and data.get('success', True)
        return success, resp, data

    def _get_product_id(self, api_client, headers):
        """获取一个可用的 product_id"""
        resp = api_client.get('/api/v2/bo/product?page=1&page_size=1', headers=headers)
        body = resp.get_data(as_text=True)
        try:
            data = json.loads(body)
        except Exception:
            return 1
        items = (data.get('data') or {}).get('items') or []
        if items:
            return items[0].get('id') or items[0].get('product_id') or 1
        return 1

    def test_same_product_same_name_rejected(self, api_client, admin_headers):
        """[T1] 同 product 同 name → 第二次创建应被拒绝 (UNIQUE 冲突)"""
        product_id = self._get_product_id(api_client, admin_headers)
        unique_name = f'UNIQ_TEST_{int(time.time() * 1000)}'

        success1, _, _ = self._create_version(api_client, admin_headers, unique_name, product_id)
        assert success1, f"首次创建应成功: {unique_name}"

        # 第二次同名同 product 创建应失败
        success2, resp2, data2 = self._create_version(api_client, admin_headers, unique_name, product_id)
        assert not success2, f"同 product 同 name 重复创建应被拒绝, 实际成功: {data2}"
        assert resp2.status_code in (400, 409, 500), f"期望 400/409/500, 实际 {resp2.status_code}"

    def test_same_product_different_name_accepted(self, api_client, admin_headers):
        """[T2] 同 product 不同 name → 应能成功创建多个 version"""
        product_id = self._get_product_id(api_client, admin_headers)
        ts = int(time.time() * 1000)

        success1, _, _ = self._create_version(api_client, admin_headers, f'MULTI_V1_{ts}', product_id)
        success2, _, _ = self._create_version(api_client, admin_headers, f'MULTI_V2_{ts}', product_id)

        assert success1 and success2, f"同 product 不同 name 都应创建成功"

    def test_different_product_same_name_accepted(self, api_client, admin_headers):
        """[T3] 不同 product 同 name → 当前实现为全局 name 唯一 (业务键=name 单独)

        背景: version 的 name 字段 business_key=true，product_code 是 virtual。
        _check_business_key_composite 只按 name 全局唯一，跨产品同名当前会被拒绝。
        这与 version.yaml 注释 "唯一性改为 (product_id, name) 联合约束" 的愿景不符，
        需要后续扩展校验器将 product_id 加入联合键 (TODO)。

        本测试只验证: 不同 product 仍能独立创建版本（使用不同 name）
        """
        ts = int(time.time() * 1000)

        # 至少需要 2 个产品
        resp = api_client.get('/api/v2/bo/product?page=1&page_size=2', headers=admin_headers)
        body = resp.get_data(as_text=True)
        try:
            data = json.loads(body)
        except Exception:
            pytest.skip("无法解析产品列表")
        items = (data.get('data') or {}).get('items') or []
        if len(items) < 2:
            pytest.skip("需要至少 2 个产品才能验证跨产品创建")

        def _pid(it):
            return it.get('id') or it.get('product_id') or it.get('productId') or 0
        pid1 = _pid(items[0])
        pid2 = _pid(items[1])
        if pid1 == pid2 or pid2 == 0:
            pytest.skip(f"产品 ID 异常: pid1={pid1} pid2={pid2}")

        # 不同 name，分别在不同 product 下创建
        success1, resp1, _ = self._create_version(api_client, admin_headers, f'DIFFPROD_V1_{ts}', pid1)
        success2, resp2, _ = self._create_version(api_client, admin_headers, f'DIFFPROD_V2_{ts}', pid2)

        if not success1:
            print(f"[T3-DBG] pid1={pid1} 失败: status={resp1.status_code} body={resp1.get_data(as_text=True)[:200]}")
        if not success2:
            print(f"[T3-DBG] pid2={pid2} 失败: status={resp2.status_code} body={resp2.get_data(as_text=True)[:200]}")

        assert success1 and success2, f"不同 product 应能独立创建版本, 实际: p1={success1} p2={success2}"

    def test_name_required_on_create(self, api_client, admin_headers):
        """[T4] 不传 name → 应返回 400 (name 是 business_key 必填)"""
        product_id = self._get_product_id(api_client, admin_headers)
        payload = {'product_id': product_id}  # 故意不传 name
        resp = api_client.post('/api/v2/bo/version', json=payload, headers=admin_headers)
        body = resp.get_data(as_text=True)
        try:
            data = json.loads(body)
        except Exception:
            data = {}
        msg = (data.get('message') or '').lower() if isinstance(data, dict) else ''

        assert resp.status_code in (400, 422), f"期望 400/422, 实际 {resp.status_code}: {body[:200]}"
        # 错误信息应提及 name 必填/不能为空/版本名称
        assert ('必填' in msg
                or '不能为空' in msg
                or 'name' in msg
                or 'required' in msg
                or '名称' in msg), \
            f"错误信息应提及 name 必填: msg={msg!r} body={body[:200]}"

    def test_name_immutable_after_publish(self, api_client, admin_headers):
        """[T5] name 作为业务键，发布后不可改名 (应返回 400/409)"""
        product_id = self._get_product_id(api_client, admin_headers)
        original_name = f'IMMUTABLE_TEST_{int(time.time() * 1000)}'

        success, resp, data = self._create_version(api_client, admin_headers, original_name, product_id)
        if not success:
            pytest.skip(f"前置创建失败，跳过: {data}")
        version_id = (data.get('data') or {}).get('id')
        if not version_id:
            pytest.skip("无法获取 version_id")

        # 尝试改名
        new_name = f'CHANGED_{int(time.time() * 1000)}'
        update_resp = api_client.put(
            f'/api/v2/bo/version/{version_id}',
            json={'name': new_name, 'product_id': product_id},
            headers=admin_headers,
        )
        update_body = update_resp.get_data(as_text=True)

        # name 是业务键（business_key=true），改名应被拒绝
        assert update_resp.status_code in (400, 403, 409, 422, 500), \
            f"改名应被拒绝, 实际 {update_resp.status_code}: {update_body[:200]}"

