import pytest

pytestmark = pytest.mark.integration

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BO 分类体系单元测试

验证 BusinessObjectCategory、BoSubCategory、BoCategoryConfig
以及 MetaObject 扩展的正确性和向后兼容性。
"""

import pytest

from meta.core.models import (
    BusinessObjectCategory,
    BoSubCategory,
    BoCategoryConfig,
    BO_CATEGORY_TEMPLATES,
    MetaObject
)


class TestBusinessObjectCategory:
    """测试 BusinessObjectCategory 枚举"""

    def test_enum_has_4_types(self):
        """应该包含4种BO类型"""
        assert len(BusinessObjectCategory) == 4
        assert BusinessObjectCategory.TRANSACTIONAL in BusinessObjectCategory
        assert BusinessObjectCategory.MASTER_DATA in BusinessObjectCategory
        assert BusinessObjectCategory.ANALYTICAL in BusinessObjectCategory
        assert BusinessObjectCategory.CONFIGURATION in BusinessObjectCategory

    def test_enum_values(self):
        """枚举值应该正确"""
        assert BusinessObjectCategory.TRANSACTIONAL.value == "transactional"
        assert BusinessObjectCategory.MASTER_DATA.value == "master_data"
        assert BusinessObjectCategory.ANALYTICAL.value == "analytical"
        assert BusinessObjectCategory.CONFIGURATION.value == "configuration"


class TestBoSubCategory:
    """测试 BoSubCategory 枚举"""

    def test_enum_has_16_subcategories(self):
        """应该包含16种子类别"""
        assert len(BoSubCategory) == 16

    def test_transactional_subcategories(self):
        """事务型子类别应该包含 document, process_instance 等"""
        assert BoSubCategory.DOCUMENT in BoSubCategory
        assert BoSubCategory.PROCESS_INSTANCE in BoSubCategory
        assert BoSubCategory.EVENT_LOG in BoSubCategory
        assert BoSubCategory.TEMPORARY in BoSubCategory

    def test_master_data_subcategories(self):
        """主数据型子类别应该包含 party, product 等"""
        assert BoSubCategory.PARTY in BoSubCategory
        assert BoSubCategory.PRODUCT in BoSubCategory
        assert BoSubCategory.ORGANIZATION in BoSubCategory
        assert BoSubCategory.ASSET in BoSubCategory


class TestBoCategoryConfig:
    """测试 BoCategoryConfig 数据类"""

    def test_default_values(self):
        """默认值应该合理"""
        config = BoCategoryConfig(category=BusinessObjectCategory.MASTER_DATA)

        assert config.default_lifecycle == "active"
        assert config.default_audit_level == "standard"
        assert config.default_soft_delete is False
        assert config.default_versioning is False
        assert config.change_frequency == "medium"
        assert config.default_list_page_size == 20

    def test_custom_values(self):
        """自定义值应该被保留"""
        config = BoCategoryConfig(
            category=BusinessObjectCategory.TRANSACTIONAL,
            default_audit_level="detailed",
            default_state_machine=True,
            default_soft_delete=True
        )

        assert config.default_audit_level == "detailed"
        assert config.default_state_machine is True
        assert config.default_soft_delete is True


class TestBOCategoryTemplates:
    """测试 BO_CATEGORY_TEMPLATES 预置字典"""

    def test_templates_have_4_entries(self):
        """应该包含4种类型的模板"""
        assert len(BO_CATEGORY_TEMPLATES) == 4
        assert BusinessObjectCategory.TRANSACTIONAL in BO_CATEGORY_TEMPLATES
        assert BusinessObjectCategory.MASTER_DATA in BO_CATEGORY_TEMPLATES
        assert BusinessObjectCategory.ANALYTICAL in BO_CATEGORY_TEMPLATES
        assert BusinessObjectCategory.CONFIGURATION in BO_CATEGORY_TEMPLATES

    def test_transactional_template_config(self):
        """事务型模板配置应该正确"""
        template = BO_CATEGORY_TEMPLATES[BusinessObjectCategory.TRANSACTIONAL]

        assert template.default_audit_level == "detailed"
        assert template.default_state_machine is True
        assert template.default_soft_delete is True
        assert template.is_analytical_source is True
        assert template.supports_aggregation is True
        assert template.change_frequency == "high"

    def test_master_data_template_config(self):
        """主数据型模板配置应该正确"""
        template = BO_CATEGORY_TEMPLATES[BusinessObjectCategory.MASTER_DATA]

        assert template.default_audit_level == "standard"
        assert template.default_versioning is True
        assert template.default_soft_delete is False
        assert template.sharing_scope == "global"
        assert template.supports_hierarchy_display is True

    def test_analytical_template_config(self):
        """分析型模板配置应该正确"""
        template = BO_CATEGORY_TEMPLATES[BusinessObjectCategory.ANALYTICAL]

        assert template.default_audit_level == "none"
        assert template.default_import_export is False
        assert template.change_frequency == "realtime"
        assert template.time_dimension_required is True

    def test_configuration_template_config(self):
        """配置型模板配置应该正确"""
        template = BO_CATEGORY_TEMPLATES[BusinessObjectCategory.CONFIGURATION]

        assert template.default_audit_level == "light"
        assert template.default_versioning is True
        assert template.change_frequency == "low"
        assert template.supports_hierarchy_display is True


class TestMetaObjectBackwardCompatibility:
    """测试 MetaObject 向后兼容性"""

    def test_create_without_bo_fields(self):
        """不指定 BO 字段时应该能正常创建（向后兼容）"""
        obj = MetaObject(
            id="test_obj",
            name="测试对象",
            table_name="t_test"
        )

        assert obj.bo_category == BusinessObjectCategory.MASTER_DATA
        assert obj.bo_sub_category is None
        assert obj.category_config is not None

    def test_category_config_auto_filled(self):
        """category_config 应该根据 bo_category 自动填充"""
        obj = MetaObject(
            id="order",
            name="订单",
            table_name="t_order",
            bo_category=BusinessObjectCategory.TRANSACTIONAL
        )

        assert obj.category_config is not None
        assert obj.category_config.category == BusinessObjectCategory.TRANSACTIONAL
        assert obj.category_config.default_audit_level == "detailed"
        assert obj.category_config.default_state_machine is True

    def test_explicit_bo_category(self):
        """显式指定 BO 分类应该生效"""
        obj = MetaObject(
            id="report",
            name="销售报表",
            table_name="t_report",
            bo_category=BusinessObjectCategory.ANALYTICAL,
            bo_sub_category=BoSubCategory.KPI_DASHBOARD
        )

        assert obj.bo_category == BusinessObjectCategory.ANALYTICAL
        assert obj.bo_sub_category == BoSubCategory.KPI_DASHBOARD


class TestMetaObjectHelperMethods:
    """测试 MetaObject 辅助方法"""

    @pytest.fixture
    def transactional_obj(self):
        """创建事务型测试对象"""
        return MetaObject(
            id="order",
            name="销售订单",
            table_name="t_sales_order",
            bo_category=BusinessObjectCategory.TRANSACTIONAL
        )

    @pytest.fixture
    def master_data_obj(self):
        """创建主数据类型测试对象"""
        return MetaObject(
            id="customer",
            name="客户",
            table_name="t_customer",
            bo_category=BusinessObjectCategory.MASTER_DATA
        )

    @pytest.fixture
    def analytical_obj(self):
        """创建分析型测试对象"""
        return MetaObject(
            id="monthly_report",
            name="月度报表",
            table_name="t_monthly_report",
            bo_category=BusinessObjectCategory.ANALYTICAL
        )

    @pytest.fixture
    def config_obj(self):
        """创建配置型测试对象"""
        return MetaObject(
            id="order_status",
            name="订单状态",
            table_name="t_order_status",
            bo_category=BusinessObjectCategory.CONFIGURATION
        )

    def test_is_transactional(self, transactional_obj, master_data_obj, analytical_obj, config_obj):
        """is_transactional 方法应该正确判断"""
        assert transactional_obj.is_transactional() is True
        assert master_data_obj.is_transactional() is False
        assert analytical_obj.is_transactional() is False
        assert config_obj.is_transactional() is False

    def test_is_master_data(self, transactional_obj, master_data_obj, analytical_obj, config_obj):
        """is_master_data 方法应该正确判断"""
        assert transactional_obj.is_master_data() is False
        assert master_data_obj.is_master_data() is True
        assert analytical_obj.is_master_data() is False
        assert config_obj.is_master_data() is False

    def test_is_analytical(self, transactional_obj, master_data_obj, analytical_obj, config_obj):
        """is_analytical 方法应该正确判断"""
        assert transactional_obj.is_analytical() is False
        assert master_data_obj.is_analytical() is False
        assert analytical_obj.is_analytical() is True
        assert config_obj.is_analytical() is False

    def test_is_configuration(self, transactional_obj, master_data_obj, analytical_obj, config_obj):
        """is_configuration 方法应该正确判断"""
        assert transactional_obj.is_configuration() is False
        assert master_data_obj.is_configuration() is False
        assert analytical_obj.is_configuration() is False
        assert config_obj.is_configuration() is True
