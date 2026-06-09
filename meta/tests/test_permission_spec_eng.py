# -*- coding: utf-8 -*-
"""
SVC-015: permission_spec (8 测试) - v3 M6.5 集中式权限规则

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] FieldPolicy / PermissionSpec / apply_row_filter / apply_field_visibility / _apply_mask
"""
import pytest
from meta.core.permission_spec import (
    FieldPolicy,
    PermissionSpec,
    PermissionRegistry,
    get_permission_registry,
)

pytestmark = [pytest.mark.unit]


class TestFieldPolicy:
    """FieldPolicy dataclass 测试 (2 用例)"""

    def test_to_dict(self):
        """to_dict 完整序列化"""
        p = FieldPolicy(visible=True, readonly=False, hidden_in_api=False, mask=None)
        assert p.to_dict() == {
            'visible': True, 'readonly': False, 'hidden_in_api': False, 'mask': None,
        }

    def test_mask_field(self):
        """mask='last4' 字段正确序列化"""
        p = FieldPolicy(mask='last4')
        assert p.to_dict()['mask'] == 'last4'


class TestPermissionSpec:
    """PermissionSpec 测试 (5 用例)"""

    def test_apply_row_filter_no_filter_returns_base(self):
        """无 row_filter → 返回 base 不变"""
        spec = PermissionSpec(entity_type='user')
        sql, params = spec.apply_row_filter('id > 0', [1])
        assert sql == 'id > 0'
        assert params == [1]

    def test_apply_row_filter_no_context_returns_base(self):
        """有 row_filter 但无 context → 返回 base"""
        spec = PermissionSpec(
            entity_type='user',
            row_filter=lambda ctx: ("user_id = ?", [ctx.user_id]),
        )
        sql, params = spec.apply_row_filter('id > 0', [1], context=None)
        assert sql == 'id > 0'

    def test_apply_row_filter_concatenates(self):
        """有 row_filter + context → 追加 AND"""
        spec = PermissionSpec(
            entity_type='user',
            row_filter=lambda ctx: ("user_id = ?", [ctx['user_id']]),
        )
        ctx = {'user_id': 42}
        sql, params = spec.apply_row_filter('id > 0', [1], context=ctx)
        assert sql == 'id > 0 AND (user_id = ?)'
        assert params == [1, 42]

    def test_apply_field_visibility_hidden(self):
        """hidden_in_api=True → 字段从 items 中删除"""
        spec = PermissionSpec(
            entity_type='user',
            field_visibility={
                'password': FieldPolicy(hidden_in_api=True),
            },
        )
        items = [{'id': 1, 'name': 'Alice', 'password': 'secret'}]
        result = spec.apply_field_visibility(items)
        assert 'password' not in result[0]
        assert result[0]['name'] == 'Alice'

    def test_apply_field_visibility_mask(self):
        """mask='last4' → 字段脱敏"""
        spec = PermissionSpec(
            entity_type='user',
            field_visibility={
                'id_card': FieldPolicy(mask='last4'),
            },
        )
        items = [{'id_card': '123456789012345678'}]
        result = spec.apply_field_visibility(items)
        assert result[0]['id_card'] == '****5678'


class TestMask:
    """_apply_mask 脱敏测试 (3 cases, 1 函数)"""

    @pytest.mark.parametrize('value,mask_type,expected', [
        pytest.param('123456789012345678', 'last4', '****5678', id='last4_long'),
        pytest.param('1234', 'last4', '****', id='last4_short'),
        pytest.param('alice@example.com', 'email', 'a***@example.com', id='email'),
    ])
    def test_apply_mask(self, value, mask_type, expected):
        spec = PermissionSpec(entity_type='user')
        assert spec._apply_mask(value, mask_type) == expected


class TestPermissionRegistry:
    """PermissionRegistry 测试 (1 用例)"""

    def test_register_and_stats(self):
        """register 后 stats 反映注册数"""
        reg = PermissionRegistry()
        reg.register(PermissionSpec(entity_type='user'))
        reg.register(PermissionSpec(entity_type='product'))
        s = reg.stats()
        assert s['registered_entities'] == 2
