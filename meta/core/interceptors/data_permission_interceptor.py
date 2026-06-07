# -*- coding: utf-8 -*-
import logging
import os
from typing import TYPE_CHECKING, List

from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'true').lower() in ('true', '1', 'yes')


class DataPermissionInterceptor(Interceptor):
    """
    数据权限拦截器

    before_action 阶段对查询请求注入权限过滤条件：
    1. scope过滤 — 从元模型 authorization.scope 读取表达式，替换 $user 变量
    2. 数据权限过滤 — 非管理员自动应用 DataPermissionFilter

    仅对 crud_query 动作生效。
    """

    _perm_filter = None

    @property
    def name(self) -> str:
        return "data_permission"

    @property
    def priority(self) -> int:
        return 30

    def before_action(self, context: 'ActionContext') -> None:
        if not context.is_query_action:
            return

        if not AUTH_ENABLED:
            return

        if self._is_admin(context):
            return

        self._apply_scope_filter(context)
        self._apply_data_permission_filter(context)

    def after_action(self, context: 'ActionContext') -> None:
        pass

    def _is_admin(self, context: 'ActionContext') -> bool:
        try:
            from meta.services.auth_middleware import is_admin, get_current_user
            user = get_current_user()
            if user and is_admin(user):
                return True
            if context.extra.get('is_admin'):
                return True
            perms = context.extra.get('permissions', [])
            if '*' in perms or 'admin' in perms:
                return True
        except Exception:
            pass
        return False

    def _apply_scope_filter(self, context: 'ActionContext') -> None:
        meta_obj = context.meta_object
        if meta_obj is None:
            return

        authorization = getattr(meta_obj, 'authorization', None)
        if not authorization:
            return

        scope_expr = None
        if isinstance(authorization, dict):
            scope_expr = authorization.get('scope')
        elif hasattr(authorization, 'scope'):
            scope_expr = authorization.scope

        if not scope_expr:
            return

        perm_filter = self._get_perm_filter(context)
        if perm_filter:
            try:
                allowed_ids = perm_filter.perm_service.get_allowed_resource_ids(
                    context.user_id, context.object_type
                )
                if allowed_ids:
                    logger.debug(f"[DataPermInterceptor] User has explicit data permissions for {context.object_type}, skipping scope")
                    return
            except Exception:
                pass

        resolved = scope_expr

        # [DECORATIVE] M11 v1.2.0: YAML 集中化行级过滤（rls_rules/*.yaml 优先于 meta_object.authorization.scope）
        try:
            from flask import g
            user_info = g.get('current_user') if hasattr(g, 'current_user') else None
        except Exception:
            user_info = None
        if user_info:
            try:
                from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
                yaml_filter = _check_yaml_row_filter(
                    user_info, context.object_type,
                    current_scope_expr=resolved,
                    user_id=context.user_id,
                )
                if yaml_filter:
                    logger.debug(f"[DataPermInterceptor] Using YAML row filter for {context.object_type}: {yaml_filter[:100]}")
                    # YAML 规则：仅替换 $user.id 变量，其余原样（DSL 解析留给后续）
                    resolved = yaml_filter
            except Exception as e:
                logger.debug(f"[DataPermInterceptor] YAML row filter skipped: {e}")

        if context.user_id:
            resolved = resolved.replace('$user.id', str(context.user_id))
        if context.user_name:
            resolved = resolved.replace('$user.username', str(context.user_name))

        if 'query_conditions' not in context.extra:
            context.extra['query_conditions'] = []

        try:
            parsed = self._parse_scope_expression(resolved)
            for cond_item in parsed:
                if isinstance(cond_item, list):
                    or_group = cond_item
                    or_conditions = []
                    for c in or_group:
                        or_conditions.append({
                            'field': c['field'],
                            'operator': c['operator'],
                            'value': c['value'],
                        })
                    context.extra['query_conditions'].append({
                        'type': 'or',
                        'conditions': or_conditions,
                    })
                else:
                    context.extra['query_conditions'].append({
                        'field': cond_item['field'],
                        'operator': cond_item['operator'],
                        'value': cond_item['value'],
                    })
        except Exception:
            parts = resolved.split('=', 1)
            if len(parts) == 2:
                field = parts[0].strip()
                value = parts[1].strip()
                context.extra['query_conditions'].append({
                    'field': field,
                    'operator': 'eq',
                    'value': value,
                })

    @staticmethod
    def _parse_scope_expression(expr: str):
        import re

        or_parts = re.split(r'\s+OR\s+', expr, flags=re.IGNORECASE)
        if len(or_parts) > 1:
            or_group = []
            for part in or_parts:
                or_group.append(DataPermissionInterceptor._parse_simple_condition(part.strip()))
            return [or_group]

        return [DataPermissionInterceptor._parse_simple_condition(expr.strip())]

    @staticmethod
    def _parse_simple_condition(expr: str):
        import re
        expr = expr.strip()

        # [IN子查询] version_id IN (SELECT ...)
        in_match = re.match(
            r'^(.+?)\s+IN\s*\((.+)\)$', expr, re.IGNORECASE | re.DOTALL)
        if in_match:
            return {
                'field': in_match.group(1).strip(),
                'operator': 'in_subquery',
                'value': in_match.group(2).strip(),
            }

        for op_char, op_name in [('!=', 'ne'), ('>=', 'ge'), ('<=', 'le'), ('>', 'gt'), ('<', 'lt'), ('=', 'eq')]:
            if op_char in expr:
                parts = expr.split(op_char, 1)
                field = parts[0].strip()
                value = parts[1].strip()
                if (value.startswith("'") and value.endswith("'")) or \
                   (value.startswith('"') and value.endswith('"')):
                    value = value[1:-1]
                return {'field': field, 'operator': op_name, 'value': value}
        return {'field': expr, 'operator': 'eq', 'value': True}

    def _apply_data_permission_filter(self, context: 'ActionContext') -> None:
        if not context.user_id:
            return

        perm_filter = self._get_perm_filter(context)
        if perm_filter is None:
            return

        try:
            from meta.core.query_builder import QueryCondition
            existing = context.extra.get('query_conditions', [])
            conditions = []
            for c in existing:
                if isinstance(c, QueryCondition):
                    conditions.append(c)
                elif isinstance(c, dict):
                    if c.get('type') == 'or':
                        conditions.append(c)
                    else:
                        conditions.append(QueryCondition(
                            field=c.get('field', ''),
                            operator=c.get('operator', 'eq'),
                            value=c.get('value'),
                        ))

            filtered = perm_filter.apply_filter(context.object_type, context.user_id, conditions)
            dict_conditions = []
            for c in filtered:
                if isinstance(c, QueryCondition):
                    cond_dict = {'field': c.field, 'operator': c.operator.value if hasattr(c.operator, 'value') else str(c.operator)}
                    if c.operator.value if hasattr(c.operator, 'value') else str(c.operator) == 'in':
                        cond_dict['values'] = c.values
                    else:
                        cond_dict['value'] = c.value
                    dict_conditions.append(cond_dict)
                elif isinstance(c, dict):
                    dict_conditions.append(c)
            context.extra['query_conditions'] = dict_conditions
        except Exception as e:
            logger.warning(f"[DataPermInterceptor] data permission filter error: {e}")

    def _get_perm_filter(self, context: 'ActionContext'):
        if DataPermissionInterceptor._perm_filter is not None:
            return DataPermissionInterceptor._perm_filter
        try:
            from meta.services.data_permission_filter import DataPermissionFilter
            DataPermissionInterceptor._perm_filter = DataPermissionFilter(context.data_source)
            return DataPermissionInterceptor._perm_filter
        except Exception as e:
            logger.warning(f"[DataPermInterceptor] Failed to init DataPermissionFilter: {e}")
            return None
