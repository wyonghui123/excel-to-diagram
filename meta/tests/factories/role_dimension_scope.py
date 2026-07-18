"""
RoleDimensionScopeFactory (Phase 6 新建)
==========================================

角色维度范围工厂: 用于权限推导入口测试 (V027 权限域核心)

yaml: meta/schemas/role_dimension_scope.yaml
required 字段:
- role_id (关联角色)
- dimension_code (维度编码)
- dimension_values (维度值列表, JSON)
"""
from typing import Dict, Any, List
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class RoleDimensionScopeFactory(BaseFactory):
    """角色维度范围工厂"""

    _OBJECT_TYPE = 'role_dimension_scope'

    # 常见维度编码
    DIM_DOMAIN = 'domain'
    DIM_SUB_DOMAIN = 'sub_domain'
    DIM_SERVICE_MODULE = 'service_module'
    DIM_PRODUCT = 'product'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        return {
            # 真实调用必须用 create_for_role() 显式传入
            'role_id': None,  # 需配 RoleFactory
            'dimension_code': cls.DIM_DOMAIN,
            'dimension_values': [],  # 需配实际维度值
            'inherit_children': True,
            'scope_mode': 'include',
        }

    @classmethod
    def create_for_role(
        cls, role_id: int, dimension_code: str, dimension_values: List,
        scope_mode: str = 'include', cookie=None, **overrides
    ) -> Dict[str, Any]:
        """为指定角色创建维度范围"""
        return cls.create(
            cookie=cookie,
            role_id=role_id,
            dimension_code=dimension_code,
            dimension_values=dimension_values,
            scope_mode=scope_mode,
            **overrides
        )

    @classmethod
    def create_domain_scope(
        cls, role_id: int, domain_ids: List[int], cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建 domain 维度范围"""
        return cls.create_for_role(
            role_id, cls.DIM_DOMAIN, domain_ids, cookie=cookie, **overrides
        )

    @classmethod
    def create_exclude_scope(
        cls, role_id: int, dimension_code: str, dimension_values: List,
        cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建排除模式维度范围"""
        return cls.create_for_role(
            role_id, dimension_code, dimension_values, scope_mode='exclude',
            cookie=cookie, **overrides
        )
