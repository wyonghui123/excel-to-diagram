# -*- coding: utf-8 -*-
"""
SVC-002: log_filter_service 单元测试 (6 用例)

[NEW] 2026-06-07 批次: 补齐 LogFilterService 测试
- mask_sensitive_value: 密码/Token/Key 字段识别
- filter_dict: 嵌套 dict 屏蔽
- filter_log_message: 正则替换
  - Bearer Token
  - JWT (eyJ...)
  - 15/18 位身份证
  - 手机号
- SensitiveDataFilter (logging.Filter)
"""
import logging
import pytest

pytestmark = pytest.mark.unit


class TestLogFilterService:
    """log_filter_service 单元测试 (SVC-002)"""

    def test_mask_sensitive_value_password(self):
        """password 字段值被屏蔽"""
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('password', 'secret123') == '[REDACTED]'
        assert mask_sensitive_value('new_password', 'old_pwd') == '[REDACTED]'
        assert mask_sensitive_value('PASSWORD_HASH', 'hash') == '[REDACTED]'

    def test_mask_sensitive_value_token(self):
        """token/api_key 字段值被屏蔽"""
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('token', 'abc') == '[REDACTED]'
        assert mask_sensitive_value('auth_token', 'xyz') == '[REDACTED]'
        assert mask_sensitive_value('api_key', 'k') == '[REDACTED]'
        # 非敏感字段保留
        assert mask_sensitive_value('username', 'admin') == 'admin'

    def test_filter_dict_nested_redaction(self):
        """filter_dict 嵌套 dict 全部敏感字段屏蔽"""
        from meta.services.log_filter_service import filter_dict
        data = {
            'username': 'admin',
            'credentials': {
                'password': 'secret',
                'token': 'tk_123',
            },
            'profile': {
                'name': 'Alice',
                'api_key': 'k_secret',
            },
            'items': [
                {'password': 'p1', 'value': 'v1'},
                {'value': 'v2'},
            ],
        }
        result = filter_dict(data)
        assert result['username'] == 'admin'
        assert result['credentials']['password'] == '[REDACTED]'
        assert result['credentials']['token'] == '[REDACTED]'
        assert result['profile']['name'] == 'Alice'
        assert result['profile']['api_key'] == '[REDACTED]'
        assert result['items'][0]['password'] == '[REDACTED]'
        assert result['items'][0]['value'] == 'v1'

    def test_filter_log_message_bearer_token(self):
        """filter_log_message 屏蔽 Bearer token"""
        from meta.services.log_filter_service import filter_log_message
        msg = "Authorization: Bearer abcDEF12345_-."
        result = filter_log_message(msg)
        assert '[TOKEN]' in result
        assert 'abcDEF12345' not in result

    def test_filter_log_message_id_card_and_phone(self):
        """filter_log_message 屏蔽身份证/手机号"""
        from meta.services.log_filter_service import filter_log_message
        # 15 位身份证
        assert '[ID_NUMBER]' in filter_log_message("用户身份证: 123456789012345")
        # 18 位身份证
        assert '[ID_NUMBER]' in filter_log_message("ID: 123456789012345678")
        # 11 位手机号 (1[3-9] 开头)
        assert '[PHONE]' in filter_log_message("联系手机: 13800138000")

    def test_sensitive_data_filter_on_log_record(self):
        """SensitiveDataFilter 处理 log record.msg (dict + str)"""
        from meta.services.log_filter_service import SensitiveDataFilter
        f = SensitiveDataFilter()

        # 1. dict message
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg={'username': 'admin', 'password': 'secret'}, args=None, exc_info=None
        )
        result = f.filter(record)
        assert result is True
        assert record.msg['username'] == 'admin'
        assert record.msg['password'] == '[REDACTED]'

        # 2. str message with Bearer
        record2 = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='Log entry: Bearer secret_token_xyz', args=None, exc_info=None
        )
        f.filter(record2)
        assert '[TOKEN]' in record2.msg
