"""
UserGroupMemberFactory (P1-5d 新建)
====================================

用户组成员工厂: 用于用户组成员关系测试

yaml: meta/schemas/user_group_member.yaml
表名: user_group_members
required 字段:
- user_id
- group_id
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class UserGroupMemberFactory(BaseFactory):
    """用户组成员工厂"""

    _OBJECT_TYPE = 'user_group_member'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        return {
            'user_id': None,
            'group_id': None,
            'is_manager': False,
            'joined_at': None,
            'role_in_group': 'member',
            'note': None,
        }

    @classmethod
    def create_for_user_group(
        cls, user_id: int, group_id: int, cookie=None, **overrides
    ):
        """为指定 user + group 创建成员关系"""
        return cls.create(
            cookie=cookie, user_id=user_id, group_id=group_id, **overrides
        )

    @classmethod
    def create_manager(cls, user_id: int, group_id: int, cookie=None, **overrides):
        """创建组管理员"""
        return cls.create_for_user_group(
            user_id, group_id,
            cookie=cookie, is_manager=True, role_in_group='manager', **overrides
        )

    @classmethod
    def create_member(cls, user_id: int, group_id: int, cookie=None, **overrides):
        """创建普通成员"""
        return cls.create_for_user_group(
            user_id, group_id,
            cookie=cookie, is_manager=False, role_in_group='member', **overrides
        )

    @classmethod
    def create_owner(cls, user_id: int, group_id: int, cookie=None, **overrides):
        """创建组所有者"""
        return cls.create_for_user_group(
            user_id, group_id,
            cookie=cookie, is_manager=True, role_in_group='owner', **overrides
        )