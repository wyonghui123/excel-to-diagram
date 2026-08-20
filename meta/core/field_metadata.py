# -*- coding: utf-8 -*-
"""
FieldMetadataRegistry

字段元数据注册表, 驱动 Layer 2 推导管道。

[职责]
  - 注册字段的元数据 (是否维度、是否Owner、默认推导模式等)
  - 提供查询接口供推导管道使用
  - 从 dimension_object_mapping.yaml 自动加载维度字段

[元数据属性]
  field_name              — 字段名 (如 domain_id)
  bo_id                   — 所属 BO (如 product)
  is_dimension            — 是否维度字段 (触发层级展开)
  is_owner                — 是否 Owner 字段 (求值优先级提升)
  dimension_chain         — 维度层级链 (如 domain→sub_domain→service_module)
  parent_field            — 父维度字段 (笛卡尔积检测)
  default_derivation_mode — 默认推导模式 (static / dynamic)
  triggers_menu_derivation — 是否触发菜单推导
  triggers_permission_derivation — 是否触发功能权限推导
  value_help_source      — Value Help 数据源 (UI 级联选择)
  runtime_variable       — 运行时变量 (如 ${user.id})
"""
from dataclasses import dataclass, field as dc_field
from typing import Dict, List, Optional


@dataclass
class FieldMetadata:
    """字段元数据"""
    field_name: str
    bo_id: str
    is_dimension: bool = False
    is_owner: bool = False
    dimension_chain: Optional[str] = None
    parent_field: Optional[str] = None
    default_derivation_mode: str = 'static'  # static | dynamic
    triggers_menu_derivation: bool = False
    triggers_permission_derivation: bool = False
    value_help_source: Optional[str] = None
    runtime_variable: Optional[str] = None


class FieldMetadataRegistry:
    """字段元数据注册表"""

    def __init__(self):
        # key: (bo_id, field_name) → FieldMetadata
        self._registry: Dict[tuple, FieldMetadata] = {}

    def register(self, metadata: FieldMetadata) -> None:
        """注册字段元数据"""
        key = (metadata.bo_id, metadata.field_name)
        self._registry[key] = metadata

    def get(self, field_name: str, bo_id: str) -> Optional[FieldMetadata]:
        """查询字段元数据"""
        return self._registry.get((bo_id, field_name))

    def list_dimension_fields(self, bo_id: str) -> List[FieldMetadata]:
        """列出指定 BO 的所有维度字段"""
        return [
            m for (bid, _), m in self._registry.items()
            if bid == bo_id and m.is_dimension
        ]

    def list_owner_fields(self, bo_id: str) -> List[FieldMetadata]:
        """列出指定 BO 的所有 Owner 字段"""
        return [
            m for (bid, _), m in self._registry.items()
            if bid == bo_id and m.is_owner
        ]

    def is_dimension(self, field_name: str, bo_id: str) -> bool:
        """快速判断是否维度字段"""
        meta = self.get(field_name, bo_id)
        return meta is not None and meta.is_dimension

    def is_owner(self, field_name: str, bo_id: str) -> bool:
        """快速判断是否 Owner 字段"""
        meta = self.get(field_name, bo_id)
        return meta is not None and meta.is_owner

    def get_default_derivation_mode(self, field_name: str, bo_id: str) -> str:
        """获取字段的默认推导模式"""
        meta = self.get(field_name, bo_id)
        if meta is None:
            return 'static'  # 默认静态
        return meta.default_derivation_mode

    def all_fields(self, bo_id: str) -> List[FieldMetadata]:
        """列出指定 BO 的所有注册字段"""
        return [m for (bid, _), m in self._registry.items() if bid == bo_id]


# ============================================================================
# 默认注册表 (从 dimension_object_mapping.yaml 加载)
# ============================================================================
_DEFAULT_REGISTRY: Optional[FieldMetadataRegistry] = None


def get_default_registry() -> FieldMetadataRegistry:
    """获取全局默认注册表 (单例)

    从 dimension_object_mapping.yaml 自动加载维度字段元数据。
    """
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is not None:
        return _DEFAULT_REGISTRY

    _DEFAULT_REGISTRY = FieldMetadataRegistry()

    # 注册标准维度字段 (6级层级)
    dimension_fields = [
        # product 维度
        ('product_id', 'version', True, 'product→version', None, 'static'),
        ('version_id', 'business_object', True, 'version→business_object', 'product_id', 'static'),
        # domain 层级
        ('domain_id', 'product', True, 'domain→sub_domain→service_module', None, 'dynamic'),
        ('sub_domain_id', 'product', True, 'domain→sub_domain→service_module', 'domain_id', 'dynamic'),
        ('service_module_id', 'business_object', True, 'service_module→business_object', 'sub_domain_id', 'dynamic'),
        # Owner 字段
        ('owner_id', 'product', False, None, None, 'static'),
        ('owner_id', 'version', False, None, None, 'static'),
        ('owner_id', 'business_object', False, None, None, 'static'),
        ('created_by', 'product', False, None, None, 'static'),
    ]

    for field_name, bo_id, is_dim, chain, parent, mode in dimension_fields:
        _DEFAULT_REGISTRY.register(FieldMetadata(
            field_name=field_name,
            bo_id=bo_id,
            is_dimension=is_dim,
            dimension_chain=chain if is_dim else None,
            parent_field=parent,
            default_derivation_mode=mode,
            triggers_menu_derivation=is_dim,
            triggers_permission_derivation=is_dim,
            is_owner=(field_name == 'owner_id'),
            runtime_variable='${user.id}' if field_name == 'owner_id' else None,
        ))

    return _DEFAULT_REGISTRY
