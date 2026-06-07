import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
测试 LogEntry 数据类

测试日志条目的创建、验证和序列化功能。
"""

import pytest
from datetime import datetime
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from enums import LogCategory, LogLevel

# 直接导入模块文件，避免循环导入
import importlib.util
spec = importlib.util.spec_from_file_location(
    "structured_logger", 
    project_root / "services" / "structured_logger.py"
)
structured_logger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(structured_logger)
LogEntry = structured_logger.LogEntry


class TestLogEntryCreation:
    """测试 LogEntry 创建"""
    
    def test_create_minimal_entry(self):
        """测试创建最小日志条目"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE"
        )
        
        assert entry.category == LogCategory.BUSINESS
        assert entry.level == LogLevel.INFO
        assert entry.action == "CREATE"
        assert entry.created_at is not None
    
    def test_create_full_entry(self):
        """测试创建完整日志条目"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="UPDATE",
            object_type="user",
            object_id=123,
            user_id=1,
            user_name="admin",
            ip_address="192.168.1.100",
            old_data={"email": "old@example.com"},
            new_data={"email": "new@example.com"},
            field_name="email",
            trace_id="trace-123",
            transaction_id="txn-456"
        )
        
        assert entry.category == LogCategory.BUSINESS
        assert entry.object_type == "user"
        assert entry.object_id == 123
        assert entry.old_data["email"] == "old@example.com"
        assert entry.new_data["email"] == "new@example.com"
    
    def test_create_with_string_category(self):
        """测试使用字符串创建 category"""
        entry = LogEntry(
            category="business",
            level=LogLevel.INFO,
            action="CREATE"
        )
        
        assert entry.category == LogCategory.BUSINESS
    
    def test_create_with_string_level(self):
        """测试使用字符串创建 level"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level="INFO",
            action="CREATE"
        )
        
        assert entry.level == LogLevel.INFO
    
    def test_create_without_action_raises_error(self):
        """测试缺少 action 抛出错误"""
        with pytest.raises(ValueError):
            LogEntry(
                category=LogCategory.BUSINESS,
                level=LogLevel.INFO,
                action=""
            )


class TestLogEntryValidation:
    """测试 LogEntry 验证"""
    
    def test_validate_valid_entry(self):
        """测试验证有效条目"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE",
            object_type="user",
            object_id=123
        )
        
        assert entry.is_valid()
        assert len(entry.validate()) == 0
    
    def test_validate_business_log_without_object(self):
        """测试业务日志缺少对象信息"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE"
        )
        
        errors = entry.validate()
        assert len(errors) == 2
        assert "object_type is required for business logs" in errors
        assert "object_id is required for business logs" in errors
    
    def test_validate_update_without_data(self):
        """测试 UPDATE 操作缺少变更数据"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="UPDATE",
            object_type="user",
            object_id=123
        )
        
        errors = entry.validate()
        assert "old_data or new_data is required for UPDATE action" in errors
    
    def test_validate_security_log(self):
        """测试安全日志验证"""
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel.WARNING,
            action="LOGIN_FAILED"
        )
        
        # 安全日志不需要 object_type 和 object_id
        assert entry.is_valid()


class TestLogEntrySerialization:
    """测试 LogEntry 序列化"""
    
    def test_to_dict(self):
        """测试转换为字典"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="UPDATE",
            object_type="user",
            object_id=123,
            user_name="admin"
        )
        
        data = entry.to_dict()
        
        assert data['category'] == "business"
        assert data['level'] == "INFO"
        assert data['action'] == "UPDATE"
        assert data['object_type'] == "user"
        assert data['object_id'] == 123
        assert data['user_name'] == "admin"
        assert 'created_at' in data
    
    def test_to_dict_removes_none(self):
        """测试字典移除 None 值"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE"
        )
        
        data = entry.to_dict()
        
        assert 'object_type' not in data
        assert 'object_id' not in data
        assert 'user_id' not in data
    
    def test_to_json(self):
        """测试转换为 JSON"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE",
            object_type="user",
            object_id=123
        )
        
        json_str = entry.to_json()
        
        assert '"category": "business"' in json_str
        assert '"action": "CREATE"' in json_str
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            'category': 'business',
            'level': 'INFO',
            'action': 'UPDATE',
            'object_type': 'user',
            'object_id': 123,
            'user_name': 'admin'
        }
        
        entry = LogEntry.from_dict(data)
        
        assert entry.category == LogCategory.BUSINESS
        assert entry.level == LogLevel.INFO
        assert entry.action == "UPDATE"
        assert entry.object_type == "user"
        assert entry.object_id == 123
    
    def test_round_trip(self):
        """测试序列化和反序列化往返"""
        original = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="UPDATE",
            object_type="user",
            object_id=123,
            user_name="admin",
            old_data={"email": "old@example.com"},
            new_data={"email": "new@example.com"}
        )
        
        # 转换为字典再转回来
        data = original.to_dict()
        restored = LogEntry.from_dict(data)
        
        assert restored.category == original.category
        assert restored.level == original.level
        assert restored.action == original.action
        assert restored.object_type == original.object_type
        assert restored.object_id == original.object_id


class TestLogEntryBusinessKey:
    """测试 LogEntry 业务键"""
    
    def test_get_business_key_with_object(self):
        """测试获取对象业务键"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="UPDATE",
            object_type="user",
            object_id=123
        )
        
        assert entry.get_business_key() == "user:123"
    
    def test_get_business_key_with_user(self):
        """测试获取用户业务键"""
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel.INFO,
            action="LOGIN",
            user_id=1,
            user_name="admin"
        )
        
        assert entry.get_business_key() == "admin(1)"
    
    def test_get_business_key_none(self):
        """测试无业务键"""
        entry = LogEntry(
            category=LogCategory.SYSTEM,
            level=LogLevel.INFO,
            action="STARTUP"
        )
        
        assert entry.get_business_key() is None


class TestLogEntryStringRepresentation:
    """测试 LogEntry 字符串表示"""
    
    def test_str(self):
        """测试字符串表示"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="UPDATE",
            object_type="user",
            object_id=123
        )
        
        str_repr = str(entry)
        
        assert "LogEntry" in str_repr
        assert "category=business" in str_repr
        assert "action=UPDATE" in str_repr
        assert "object_type=user" in str_repr
