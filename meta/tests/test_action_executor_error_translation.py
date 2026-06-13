# -*- coding: utf-8 -*-
"""
测试 translate_error_message 在 4 种 SQL 错误类型下的行为
修复 FR-001：确保 import re 在 L59 之前，调用不再 NameError
"""
import pytest
from unittest.mock import MagicMock
from meta.core.action_executor import translate_error_message


@pytest.fixture
def mock_meta_object():
    """构造一个最小化的 mock MetaObject"""
    mock = MagicMock()
    field = MagicMock()
    field.semantics.meaning = "用户"
    field.name = "user_name"
    mock.get_field.return_value = field
    return mock


class TestTranslateErrorMessage:
    """测试 SQL 错误消息翻译功能"""

    def test_not_null_constraint(self, mock_meta_object):
        """NOT NULL 约束：必须返回业务消息，不抛 NameError"""
        # 注意：错误消息必须包含 .code/.id/.name 才能匹配正则
        result = translate_error_message(
            "NOT NULL constraint failed: user.name", mock_meta_object
        )
        assert "用户" in result
        assert "NOT NULL" not in result  # 业务消息替换技术消息

    def test_unique_constraint(self, mock_meta_object):
        """UNIQUE 约束：返回唯一性消息"""
        result = translate_error_message(
            "UNIQUE constraint failed: user.code", mock_meta_object
        )
        assert "用户" in result  # 业务字段名
        assert "唯一" in result or "值" in result

    def test_foreign_key_constraint(self, mock_meta_object):
        """FOREIGN KEY 约束：返回外键消息"""
        result = translate_error_message(
            "FOREIGN KEY constraint failed: order.id", mock_meta_object
        )
        assert "用户" in result or "关联" in result or "外键" in result

    def test_check_constraint(self, mock_meta_object):
        """CHECK 约束：返回校验消息（无字段名匹配场景）"""
        result = translate_error_message(
            "CHECK constraint failed: age", mock_meta_object
        )
        assert "校验" in result or "不满足" in result

    def test_empty_error_string(self, mock_meta_object):
        """空字符串：返回通用消息"""
        result = translate_error_message("", mock_meta_object)
        assert result == "操作失败"

    def test_unmapped_error(self, mock_meta_object):
        """未映射的错误：返回原字符串"""
        result = translate_error_message("Unknown error XYZ", mock_meta_object)
        assert result == "Unknown error XYZ"

    def test_no_name_error_after_fix(self, mock_meta_object):
        """回归测试：调用后不应残留 NameError 状态"""
        # FR-001 修复前会抛 NameError: name 're' is not defined
        # 修复后应正常返回
        try:
            translate_error_message("NOT NULL constraint failed: x.y", mock_meta_object)
        except NameError as e:
            pytest.fail(f"NameError 未修复：{e}")
