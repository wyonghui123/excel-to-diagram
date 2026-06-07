# -*- coding: utf-8 -*-
"""
元数据验证器测试

合并以下测试文件:
- test_metadata_validator.py (元数据验证器)
- test_phase3_verification.py (Phase 3 验证)

测试范围:
- MetadataValidator 核心功能
- ValidationLevel 枚举
- Phase 3 组件导入验证
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.unit


# ==================== 元数据验证器测试 ====================

class TestMetadataValidator:
    """元数据验证器测试"""

    def test_validator_has_required_methods(self):
        """测试元数据验证器核心功能"""
        from meta.core.metadata_validator import MetadataValidator
        validator = MetadataValidator()

        assert hasattr(validator, 'validate_all')
        assert hasattr(validator, 'log_results')
        assert hasattr(validator, 'get_validation_summary')

        report = validator.validate_all()
        assert hasattr(report, 'errors')
        assert hasattr(report, 'warnings')
        assert hasattr(report, 'tech_debts')
        assert hasattr(report, 'has_errors')

    def test_validation_levels_enum(self):
        """测试验证级别枚举"""
        from meta.core.metadata_validator import ValidationLevel

        assert hasattr(ValidationLevel, 'ERROR')
        assert hasattr(ValidationLevel, 'WARNING')
        assert hasattr(ValidationLevel, 'TECH_DEBT')
        assert hasattr(ValidationLevel, 'INFO')

    def test_validation_result_data_class(self):
        """测试验证结果数据类"""
        from meta.core.metadata_validator import ValidationResult, ValidationLevel

        result = ValidationResult(
            level=ValidationLevel.ERROR,
            object_id='user_group',
            field_id='created_by',
            message='Test error'
        )

        assert result.level == ValidationLevel.ERROR
        assert result.object_id == 'user_group'
        assert result.field_id == 'created_by'
        assert result.message == 'Test error'

        if hasattr(result, 'to_dict'):
            result_dict = result.to_dict()
            assert isinstance(result_dict, dict)

    def test_validation_report_data_class(self):
        """测试验证报告数据类"""
        from meta.core.metadata_validator import ValidationReport

        report = ValidationReport()

        assert hasattr(report, 'errors')
        assert hasattr(report, 'warnings')
        assert hasattr(report, 'tech_debts')
        assert hasattr(report, 'has_errors')
        assert hasattr(report, 'to_dict')

        report_dict = report.to_dict()
        assert isinstance(report_dict, dict)
        assert 'errors' in report_dict
        assert 'warnings' in report_dict
        assert 'tech_debts' in report_dict


# ==================== Phase 3 组件验证测试 ====================

class TestPhase3Components:
    """Phase 3 组件验证测试"""

    def test_enum_type_dto(self):
        """测试 EnumTypeDTO"""
        from meta.core.enums.dto import EnumTypeDTO
        
        type_dto = EnumTypeDTO(id='test', name='Test Type')
        assert type_dto.id == 'test'
        assert type_dto.name == 'Test Type'

    def test_enum_value_dto(self):
        """测试 EnumValueDTO"""
        from meta.core.enums.dto import EnumValueDTO
        
        value_dto = EnumValueDTO(id=1, enum_type_id='test', code='ACTIVE', name='Active')
        assert value_dto.code == 'ACTIVE'
        assert value_dto.name == 'Active'

    def test_enum_select_option(self):
        """测试 EnumSelectOption"""
        from meta.core.enums.dto import EnumSelectOption
        
        option = EnumSelectOption(value='ACTIVE', label='Active')
        assert option.value == 'ACTIVE'
        assert option.label == 'Active'

    def test_user_context(self):
        """测试 UserContext"""
        from meta.core.enums.interfaces import UserContext
        
        user = UserContext(user_id='1', username='admin', roles=['admin'])
        assert user.username == 'admin'
        assert user.has_role('admin')

    def test_factory_functions(self):
        """测试工厂函数"""
        from meta.core.enums.factory import create_enum_provider, create_enum_admin
        
        provider = create_enum_provider()
        admin = create_enum_admin()
        
        assert provider is not None
        assert admin is not None

    def test_adapter_pair(self):
        """测试适配器对创建"""
        from meta.core.enums.factory import create_enum_adapter_pair
        
        provider, admin = create_enum_adapter_pair()
        assert provider is not None
        assert admin is not None
