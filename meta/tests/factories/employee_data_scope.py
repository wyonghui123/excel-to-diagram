"""
EmployeeDataScopeFactory (Phase 5 新建)
========================================

员工数据范围工厂: 用于数据权限范围配置测试

yaml: meta/schemas/employee_data_scope.yaml
required 字段 (排除审计自动生成):
- code (unique, self/department/department_tree/organization)
- name
- condition_template
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class EmployeeDataScopeFactory(BaseFactory):
    """员工数据范围工厂"""

    _OBJECT_TYPE = 'employee_data_scope'

    # 标准 scope code (来自 schema description)
    SCOPE_SELF = 'self'
    SCOPE_DEPARTMENT = 'department'
    SCOPE_DEPARTMENT_TREE = 'department_tree'
    SCOPE_ORGANIZATION = 'organization'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            # [FIX 2026-07-17 P1] 覆盖 yaml 必填字段
            'code': f'self_{n}_{suffix}',  # unique 约束
            'name': f'Test Scope {n}',
            'condition_template': 'user_id = :user_id',
            # 业务字段
            'description': f'Test employee data scope #{n}',
        }

    @classmethod
    def create_self(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """本人范围"""
        return cls.create(
            cookie=cookie,
            code=cls.SCOPE_SELF,
            name='本人',
            condition_template='user_id = :user_id',
            **overrides
        )

    @classmethod
    def create_department(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """本部门范围"""
        return cls.create(
            cookie=cookie,
            code=cls.SCOPE_DEPARTMENT,
            name='本部门',
            condition_template='user_department_id = :user_department_id',
            **overrides
        )

    @classmethod
    def create_department_tree(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """本部门及下级范围"""
        return cls.create(
            cookie=cookie,
            code=cls.SCOPE_DEPARTMENT_TREE,
            name='本部门及下级',
            condition_template='user_department_id IN (:user_department_tree)',
            **overrides
        )

    @classmethod
    def create_organization(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """本组织范围"""
        return cls.create(
            cookie=cookie,
            code=cls.SCOPE_ORGANIZATION,
            name='本组织',
            condition_template='user_organization_id = :user_organization_id',
            **overrides
        )