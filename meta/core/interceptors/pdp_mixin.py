# -*- coding: utf-8 -*-
"""
[MODULE] pdp_mixin — PEP 拦截器的 PDP 委托 Mixin (P4-T4)
[DESCRIPTION] Phase 4 P4-T4: 为 9 个 PEP 拦截器提供统一的 PDP 调用入口,
              避免每个拦截器重复实现 _call_pdp.
[SPEC] spec-permission-system-unification-2026-07-19 §3.5 / §8.4 P4-T4

[设计原则]
  - Mixin 模式: 任何拦截器继承 PDPMixin 即可获得 _call_pdp 方法
  - 渐进式: PDP 不可用时返回 None, 拦截器 fallback 到原逻辑
  - 零破坏: 不修改拦截器现有方法签名
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PDPMixin:
    """[P4-T4] PEP 拦截器的 PDP 委托 Mixin

    用法:
        class MyInterceptor(Interceptor, PDPMixin):
            def before_action(self, context):
                # 调用 PDP 决策
                decision = self._call_pdp(context, 'read', 'product', resource_id=1)
                if decision is False:
                    raise PermissionDenied()
                # decision is None → fallback 到原逻辑
    """

    def _call_pdp(self, context, action: str, resource_type: str,
                  resource=None, resource_id=None) -> Optional[bool]:
        """[P4-T4] 调用 PermissionResolver.check() (PDP 入口)

        Args:
            context: ActionContext (或任何含 user/data_source 的对象)
            action: 'read' / 'write' / 'create' / 'delete' / ...
            resource_type: BO 名
            resource: 资源 dict (可选)
            resource_id: 资源 ID (可选)

        Returns:
            True=Allow, False=Deny, None=PDP 不可用 (fallback 到原逻辑)
        """
        try:
            from meta.services.permission_resolver import PermissionResolver
            ds = self._extract_data_source(context)
            if ds is None:
                return None
            user = self._extract_user(context)
            if user is None:
                return None
            resolver = PermissionResolver(ds)
            return resolver.check(
                user=user,
                action=action,
                resource_type=resource_type,
                resource=resource,
                resource_id=resource_id,
            )
        except Exception as e:
            logger.debug(f'[P4-T4 PDPMixin _call_pdp] fallback: {e}')
            return None

    def _extract_data_source(self, context) -> Any:
        """从 context 提取 data_source"""
        for attr in ('data_source', 'datasource', 'ds', '_ds'):
            ds = getattr(context, attr, None)
            if ds is not None:
                return ds
        return None

    def _extract_user(self, context) -> Any:
        """从 context 提取 user"""
        for attr in ('user', 'current_user', 'actor', '_user'):
            user = getattr(context, attr, None)
            if user is not None:
                return user
        return None

    def _build_pdp_context_dict(self, context) -> dict:
        """[P4-T4] 从 context 组装 PDP 决策上下文 (调试/审计用)

        Returns:
            dict: {user, action, resource_type, resource, resource_id}
        """
        return {
            'user': self._extract_user(context),
            'action': (
                getattr(context, 'action', None)
                or getattr(context, 'action_type', None)
            ),
            'resource_type': (
                getattr(context, 'resource_type', None)
                or getattr(context, 'bo_name', None)
            ),
            'resource': (
                getattr(context, 'resource', None)
                or getattr(context, 'record', None)
            ),
            'resource_id': (
                getattr(context, 'resource_id', None)
                or getattr(context, 'record_id', None)
            ),
        }


def attach_pdp_mixin(interceptor_class) -> type:
    """[P4-T4] 工具函数: 给现有拦截器类动态附加 PDPMixin

    用途: 不修改拦截器源码, 通过动态继承注入 PDP 能力.

    Usage:
        from meta.core.interceptors.pdp_mixin import attach_pdp_mixin
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        AuditInterceptorWithPDP = attach_pdp_mixin(AuditInterceptor)
    """
    if PDPMixin in interceptor_class.__mro__:
        return interceptor_class  # 已有 Mixin
    # 创建新子类, 多继承 PDPMixin
    new_class = type(
        interceptor_class.__name__,
        (interceptor_class, PDPMixin),
        {'_pdp_mixin_attached': True},
    )
    return new_class