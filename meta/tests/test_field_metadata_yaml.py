# -*- coding: utf-8 -*-
"""
[P2-B6 2026-07-26] FieldMetadata YAML 自动加载测试

测试范围:
  1. FieldMetadataRegistry 注册/查询
  2. dimension_object_mapping.yaml 加载
  3. 默认注册表 (product/version/domain/sub_domain/service_module/business_object)
  4. is_dimension / is_owner 判断
  5. default_derivation_mode (static / dynamic)
  6. parent_field 笛卡尔积检测
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


class TestFieldMetadataRegistry:
    """FieldMetadataRegistry 注册/查询"""

    def test_register_and_get(self):
        """注册后能查询到"""
        from meta.core.field_metadata import FieldMetadata, FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        meta = FieldMetadata(
            field_name='domain_id',
            bo_id='product',
            is_dimension=True,
            dimension_chain='domain→sub_domain',
            default_derivation_mode='dynamic',
        )
        registry.register(meta)

        result = registry.get('domain_id', 'product')
        assert result is not None
        assert result.is_dimension is True
        assert result.dimension_chain == 'domain→sub_domain'
        assert result.default_derivation_mode == 'dynamic'

    def test_get_nonexistent_returns_none(self):
        """查询不存在的字段返回 None"""
        from meta.core.field_metadata import FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        assert registry.get('unknown_field', 'unknown_bo') is None

    def test_list_dimension_fields(self):
        """list_dimension_fields 列出指定 BO 的所有维度字段"""
        from meta.core.field_metadata import FieldMetadata, FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(field_name='domain_id', bo_id='product', is_dimension=True))
        registry.register(FieldMetadata(field_name='sub_domain_id', bo_id='product', is_dimension=True))
        registry.register(FieldMetadata(field_name='owner_id', bo_id='product', is_dimension=False))

        dim_fields = registry.list_dimension_fields('product')
        assert len(dim_fields) == 2
        field_names = {f.field_name for f in dim_fields}
        assert 'domain_id' in field_names
        assert 'sub_domain_id' in field_names
        assert 'owner_id' not in field_names

    def test_list_owner_fields(self):
        """list_owner_fields 列出指定 BO 的所有 Owner 字段"""
        from meta.core.field_metadata import FieldMetadata, FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(field_name='owner_id', bo_id='product', is_owner=True))
        registry.register(FieldMetadata(field_name='domain_id', bo_id='product', is_owner=False))

        owner_fields = registry.list_owner_fields('product')
        assert len(owner_fields) == 1
        assert owner_fields[0].field_name == 'owner_id'

    def test_is_dimension_quick_check(self):
        """is_dimension 快速判断"""
        from meta.core.field_metadata import FieldMetadata, FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(field_name='domain_id', bo_id='product', is_dimension=True))

        assert registry.is_dimension('domain_id', 'product') is True
        assert registry.is_dimension('owner_id', 'product') is False
        assert registry.is_dimension('unknown', 'unknown') is False

    def test_is_owner_quick_check(self):
        """is_owner 快速判断"""
        from meta.core.field_metadata import FieldMetadata, FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(field_name='owner_id', bo_id='product', is_owner=True))

        assert registry.is_owner('owner_id', 'product') is True
        assert registry.is_owner('domain_id', 'product') is False

    def test_get_default_derivation_mode_unknown_returns_static(self):
        """未知字段默认 static"""
        from meta.core.field_metadata import FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        assert registry.get_default_derivation_mode('unknown', 'unknown') == 'static'

    def test_all_fields_for_bo(self):
        """all_fields 列出指定 BO 的所有字段"""
        from meta.core.field_metadata import FieldMetadata, FieldMetadataRegistry

        registry = FieldMetadataRegistry()
        registry.register(FieldMetadata(field_name='domain_id', bo_id='product'))
        registry.register(FieldMetadata(field_name='owner_id', bo_id='product'))
        registry.register(FieldMetadata(field_name='domain_id', bo_id='version'))

        product_fields = registry.all_fields('product')
        assert len(product_fields) == 2


class TestDefaultRegistry:
    """默认注册表 (从 dimension_object_mapping.yaml 加载)"""

    def test_default_registry_singleton(self):
        """get_default_registry 是单例"""
        from meta.core.field_metadata import get_default_registry

        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2

    def test_default_registry_has_product_dimension(self):
        """默认注册表含 product 维度字段"""
        from meta.core.field_metadata import get_default_registry

        registry = get_default_registry()

        # product_id 应注册在 version BO 上
        meta = registry.get('product_id', 'version')
        assert meta is not None
        assert meta.is_dimension is True

    def test_default_registry_has_domain_chain(self):
        """默认注册表含 domain→sub_domain→service_module 链"""
        from meta.core.field_metadata import get_default_registry

        registry = get_default_registry()

        # domain_id 在 product BO 上, 是维度
        meta = registry.get('domain_id', 'product')
        assert meta is not None
        assert meta.is_dimension is True
        assert meta.dimension_chain is not None
        assert 'domain' in meta.dimension_chain

    def test_default_registry_has_owner_fields(self):
        """默认注册表含 owner_id 字段"""
        from meta.core.field_metadata import get_default_registry

        registry = get_default_registry()

        # owner_id 在 product BO 上
        meta = registry.get('owner_id', 'product')
        assert meta is not None
        assert meta.is_owner is True
        assert meta.runtime_variable == '${user.id}'

    def test_default_registry_dynamic_mode_for_domain(self):
        """domain 维度默认 dynamic"""
        from meta.core.field_metadata import get_default_registry

        registry = get_default_registry()
        meta = registry.get('domain_id', 'product')
        assert meta is not None
        assert meta.default_derivation_mode == 'dynamic'

    def test_default_registry_static_mode_for_product(self):
        """product 维度默认 static"""
        from meta.core.field_metadata import get_default_registry

        registry = get_default_registry()
        meta = registry.get('product_id', 'version')
        assert meta is not None
        assert meta.default_derivation_mode == 'static'

    def test_default_registry_parent_field_for_sub_domain(self):
        """sub_domain_id 的 parent_field 是 domain_id (笛卡尔积检测)"""
        from meta.core.field_metadata import get_default_registry

        registry = get_default_registry()
        meta = registry.get('sub_domain_id', 'product')
        assert meta is not None
        assert meta.parent_field == 'domain_id'

    def test_default_registry_triggers_menu_derivation(self):
        """维度字段 triggers_menu_derivation=True"""
        from meta.core.field_metadata import get_default_registry

        registry = get_default_registry()
        meta = registry.get('domain_id', 'product')
        assert meta is not None
        assert meta.triggers_menu_derivation is True


class TestDimensionObjectMappingYaml:
    """dimension_object_mapping.yaml 加载测试"""

    def test_yaml_file_exists(self):
        """dimension_object_mapping.yaml 文件存在"""
        yaml_path = os.path.join(
            _PROJECT_ROOT, 'meta', 'schemas', 'dimension_object_mapping.yaml'
        )
        assert os.path.isfile(yaml_path), f"YAML not found: {yaml_path}"

    def test_yaml_loads_successfully(self):
        """YAML 能成功加载"""
        import yaml

        yaml_path = os.path.join(
            _PROJECT_ROOT, 'meta', 'schemas', 'dimension_object_mapping.yaml'
        )
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        assert data is not None
        assert isinstance(data, dict)

    def test_yaml_contains_hierarchy_chain(self):
        """YAML 含 HIERARCHY_CHAIN 定义"""
        import yaml

        yaml_path = os.path.join(
            _PROJECT_ROOT, 'meta', 'schemas', 'dimension_object_mapping.yaml'
        )
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # 检查是否含层级链定义 (字段名可能不同)
        # 常见字段: hierarchy_chain, dimensions, dimension_chain
        has_chain = any(
            key in data
            for key in ('hierarchy_chain', 'dimensions', 'dimension_chain', 'HIERARCHY_CHAIN')
        )
        assert has_chain, f"YAML missing hierarchy definition, keys: {list(data.keys())}"
