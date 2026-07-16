# -*- coding: utf-8 -*-
"""
版本上下文拦截器

当对象配置了 context.field: version_id 时，
自动在查询操作中注入 version_id 过滤条件，
确保用户只能看到当前版本上下文中的数据。
"""

import logging
from flask import g, request

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


class VersionContextInterceptor(Interceptor):
    """
    版本上下文拦截器

    基于 YAML 中 context 配置，自动注入版本上下文过滤条件。
    当对象的 context.field 为 version_id 时，在 list/query 操作中
    自动添加 version_id 过滤，确保数据隔离。

    优先级：15（在 ContextInterceptor 之后，权限检查之前）
    """

    @property
    def priority(self) -> int:
        return 15

    def should_execute(self, context: ActionContext) -> bool:
        obj = context.meta_object
        if not obj or not obj.context:
            return False
        action = context.action or ''
        return action.startswith('crud_list') or action.startswith('crud_read')

    def before_action(self, context: ActionContext) -> None:
        obj = context.meta_object
        if not obj or not obj.context:
            return

        context_field = obj.context.get('field')
        if not context_field:
            return

        params = context.params
        if context_field in params and params[context_field] is not None:
            return

        version_id = self._resolve_version_id()
        if version_id is not None:
            params[context_field] = version_id
            logger.debug(
                f"[VersionContextInterceptor] Auto-injected {context_field}={version_id} "
                f"for {obj.id}.{context.action}"
            )

    def after_action(self, context: ActionContext) -> None:
        pass

    def _resolve_version_id(self):
        version_id = getattr(g, 'version_id', None)
        if version_id is not None:
            return version_id

        try:
            if request:
                version_id = request.args.get('version_id')
                if not version_id and request.is_json:
                    try:
                        body = request.get_json(silent=True) or {}
                        version_id = body.get('version_id')
                    except Exception:
                        pass
                if version_id:
                    return int(version_id)
        except (ValueError, TypeError, RuntimeError):
            pass

        return None
