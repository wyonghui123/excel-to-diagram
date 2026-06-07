# -*- coding: utf-8 -*-
import logging
import os
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'true').lower() in ('true', '1', 'yes')


class OwnerAutoPermissionInterceptor(Interceptor):
    """
    所有者自动权限拦截器

    before_action: 创建层级对象时自动注入 owner_id
    after_action: 创建成功后自动添加 admin 级数据权限

    通过 YAML authorization 配置驱动:
      authorization:
        auto_owner: true
        auto_permission: admin
        inherit_to_children: true
    """

    @property
    def name(self) -> str:
        return "owner_permission"

    @property
    def priority(self) -> int:
        return 96

    def before_action(self, context: 'ActionContext') -> None:
        if not context.is_create_action:
            return
        if not AUTH_ENABLED:
            return

        auth_config = self._get_auth_config(context)
        if not auth_config:
            return

        auto_owner = False
        if isinstance(auth_config, dict):
            auto_owner = auth_config.get('auto_owner', False)
        elif hasattr(auth_config, 'auto_owner'):
            auto_owner = auth_config.auto_owner

        if auto_owner and context.user_id:
            context.params['owner_id'] = context.user_id

    def after_action(self, context: 'ActionContext') -> None:
        if not context.is_create_action:
            return
        if not AUTH_ENABLED:
            return
        if context.result is None or not context.result.success:
            return

        auth_config = self._get_auth_config(context)
        if not auth_config:
            return

        auto_perm = ''
        inherit = True
        if isinstance(auth_config, dict):
            auto_perm = auth_config.get('auto_permission', '')
            inherit = auth_config.get('inherit_to_children', True)
        elif hasattr(auth_config, 'auto_permission'):
            auto_perm = auth_config.auto_permission
            inherit = getattr(auth_config, 'inherit_to_children', True)

        if not auto_perm:
            return

        created_id = None
        if context.result.data:
            if isinstance(context.result.data, dict):
                created_id = context.result.data.get('id')

        if not created_id or not context.user_id:
            return

        try:
            from meta.services.data_permission_service import DataPermissionService
            perm_service = DataPermissionService(context.data_source)
            perm_service.add_data_permission(
                user_id=context.user_id,
                resource_type=context.object_type,
                resource_id=created_id,
                permission_level=auto_perm,
                inherit_to_children=inherit,
            )
            logger.debug(f"[OwnerPermInterceptor] Auto permission added: user={context.user_id}, {context.object_type}:{created_id}, level={auto_perm}")
        except Exception as e:
            logger.warning(f"[OwnerPermInterceptor] Failed to add auto permission: {e}")

    def _get_auth_config(self, context: 'ActionContext'):
        meta_obj = context.meta_object
        if meta_obj is None:
            return None
        return getattr(meta_obj, 'authorization', None)
