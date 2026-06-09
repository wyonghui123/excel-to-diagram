# -*- coding: utf-8 -*-
"""
SVC-013: validation_messages (6 测试) - 校验消息 i18n 注册表

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] ValidationMessageRegistry.get / register_messages / set_locale
"""
import pytest
from meta.core.validation_messages import (
    ValidationDetail,
    ValidationMessageRegistry,
)

pytestmark = [pytest.mark.unit]


class TestValidationDetail:
    """ValidationDetail dataclass 测试 (2 用例)"""

    def test_to_dict(self):
        """to_dict 包含全部字段"""
        detail = ValidationDetail(
            field_id='fld_001',
            field_name='姓名',
            rule='required',
            message='姓名 不能为空',
            i18n_key='validation.field.required',
            params={},
        )
        d = detail.to_dict()
        assert d['field_id'] == 'fld_001'
        assert d['field_name'] == '姓名'
        assert d['rule'] == 'required'
        assert d['i18n_key'] == 'validation.field.required'
        assert d['params'] == {}

    def test_params_default_empty_dict(self):
        """params 缺省 → {} (非 None)"""
        detail = ValidationDetail(field_name='X')
        assert detail.params == {}


class TestValidationMessageRegistry:
    """ValidationMessageRegistry 测试 (4 用例)"""

    def setup_method(self):
        """每个测试前重置 locale"""
        ValidationMessageRegistry.set_locale('zh_CN')

    def test_get_zh_cn(self):
        """zh_CN locale: 默认中文消息"""
        msg = ValidationMessageRegistry.get(
            'validation.field.required', field_name='姓名'
        )
        assert msg == '姓名 不能为空'

    def test_get_with_missing_param(self):
        """模板缺参数 → 返回原模板 (不抛异常)"""
        # template 用 {field_name}, 但不传
        msg = ValidationMessageRegistry.get('validation.field.required')
        # KeyError 触发 fallback → 返回原 template
        assert '{field_name}' in msg

    def test_register_messages_new_locale(self):
        """注册新 locale (en_US) + 切换 + 获取"""
        ValidationMessageRegistry.register_messages('en_US', {
            'validation.field.required': '{field_name} is required',
        })
        ValidationMessageRegistry.set_locale('en_US')
        msg = ValidationMessageRegistry.get(
            'validation.field.required', field_name='Name'
        )
        assert msg == 'Name is required'

    # ---------- 不同 message key 合并 (3 → 1, 3 cases) ----------
    @pytest.mark.parametrize('key,params,expected', [
        pytest.param('validation.field.unique', {'field_name': 'Email'},
                    'Email 已存在', id='unique'),
        pytest.param('validation.field.max_length_exceeded',
                    {'field_name': 'Name', 'max_length': 10},
                    'Name 长度不能超过 10 个字符', id='max_length'),
        pytest.param('validation.field.enum_value_invalid',
                    {'field_name': 'Status', 'value': 'X',
                     'valid_values': 'A, B, C'},
                    "Status 的值 'X' 不在有效选项中，有效值为：A, B, C", id='enum_invalid'),
    ])
    def test_message_keys(self, key, params, expected):
        """不同 i18n key 渲染"""
        msg = ValidationMessageRegistry.get(key, **params)
        assert msg == expected
