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

        # [FIX v1.0.2] 优先应用 role_dimension_scopes 派生条件
        # 当角色声明了 dimension scope (例: TEST60 version=[2,11,12]) 时,
        # DimensionScopeEngine 自动向上展开到 parent BO (例: product={1,17}),
        # 然后注入到 query_conditions。
        # 这覆盖了 product.yaml 的 owner_id scope 限制, 让用户能基于维度范围看到 product。
        if self._apply_dimension_scope_filter(context):
            return  # dimension scope 已应用, 跳过 data_permission 路径

        self._apply_scope_filter(context)
        self._apply_data_permission_filter(context)

    def _apply_dimension_scope_filter(self, context: 'ActionContext') -> bool:
        """[FIX v1.0.2 / v1.0.3] 应用 role_dimension_scopes 派生条件

        流程:
        1. 查 user → group → role 链路拿到所有 role_id
        2. 调 DimensionScopeEngine.derive_data_conditions(role_id) 拿所有 role 的派生条件
        3. 如果当前 object_type 在派生条件中, 注入到 query_conditions
        4. 任一 role 有 dimension scope 且 object_type 在其派生条件中 → 允许

        v1.0.3 修复:
          派生 cond_expr 可能是复合 AND 表达式, 例:
            "id IN (2,11,12) AND product_id IN (1,17)"
          旧逻辑 _parse_id_in_expr 只能解析单段 (整行 ^...$ 匹配),
          导致 AND 复合表达式被吞掉, fallback 到原 scope filter (visibility=public OR owner_id=...),
          完全绕开 dimension scope。
          新逻辑: 按 AND 拆开, 每段生成一条 query_condition (AND 关系);
          多 role 时各 role 的 condition 之间为 OR 关系。
        """
        if not context.user_id:
            return False

        try:
            from meta.services.dimension_scope_engine import DimensionScopeEngine
        except ImportError:
            return False

        # 1. 查 user 的所有 role_id (通过 group 链路)
        try:
            cursor = context.data_source.execute(
                """SELECT DISTINCT gr.role_id
                   FROM group_roles gr
                   JOIN user_group_members ugm ON gr.group_id = ugm.group_id
                   WHERE ugm.user_id = ?""",
                [context.user_id]
            )
            role_ids = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f'[_apply_dimension_scope_filter] query role_ids failed: {e}')
            return False

        if not role_ids:
            return False

        # 2. 查 role_dimension_scopes, 确认至少有一个 role 有 scope
        try:
            placeholders = ','.join('?' * len(role_ids))
            cursor = context.data_source.execute(
                f"SELECT COUNT(*) FROM role_dimension_scopes WHERE role_id IN ({placeholders})",
                role_ids
            )
            count = cursor.fetchone()[0]
            if not count:
                return False  # 角色没有 dimension scope, 走原 scope filter
        except Exception as e:
            logger.debug(f'[_apply_dimension_scope_filter] check role_dimension_scopes failed: {e}')
            return False

        # 3. 派生所有 role 的 data_conditions
        engine = DimensionScopeEngine(context.data_source)
        object_type = context.object_type
        # per_role_conditions: List[List[QueryCondition]]
        #   外层每个 role 一组 (role 之间 OR 关系, 实现为 type='or' group)
        #   内层每个 cond 是单段 IN/= 条件 (AND 关系)
        per_role_conditions: List[List[Dict]] = []

        for role_id in role_ids:
            try:
                data_conditions = engine.derive_data_conditions(role_id)
                cond_expr = data_conditions.get(object_type)
                if not cond_expr:
                    continue

                # 4. 解析单段表达式 (支持 AND 复合)
                conds = self._parse_compound_expr(cond_expr)
                if not conds:
                    continue
                per_role_conditions.append(conds)
                logger.info(
                    f'[_apply_dimension_scope_filter] user={context.user_id} role={role_id} '
                    f'object_type={object_type} -> conds={conds}'
                )
            except Exception as e:
                logger.warning(f'[_apply_dimension_scope_filter] derive role_id={role_id} failed: {e}')

        if not per_role_conditions:
            return False  # 没有 role 派生该 object_type, 走原 scope filter

        if 'query_conditions' not in context.extra:
            context.extra['query_conditions'] = []

        # 5. 多 role → OR 关系; 单 role → 直接 append 各 AND 段
        if len(per_role_conditions) == 1:
            for c in per_role_conditions[0]:
                context.extra['query_conditions'].append(c)
        else:
            # 多 role: OR-of-AND
            or_group_conditions = []
            for conds in per_role_conditions:
                or_group_conditions.extend(conds)
            context.extra['query_conditions'].append({
                'type': 'or',
                'conditions': or_group_conditions,
            })

        # 6. [FIX v1.0.4] Owner 过滤始终可见
        # 即使 dimension scope 配置存在, 用户对自己 owner 的资源也应该可见
        # (FR-009: 记录级可见性; auto_owner=true 自动设置 owner_id = 当前用户)
        # SQL: WHERE (id IN (1,2,11,12) AND product_id IN (1,17))  -- dimension scope
        #   OR (owner_id = $user_id)                                  -- owner 始终可见
        if context.user_id and self._bo_has_owner_id(context):
            owner_cond = {
                'field': 'owner_id',
                'operator': 'eq',
                'value': context.user_id,
                'source': 'owner',
            }
            # 把已注入的所有 dimension scope 条件 + owner 条件包成一个 OR group
            existing = list(context.extra['query_conditions'])
            context.extra['query_conditions'] = [{
                'type': 'or',
                'conditions': existing + [owner_cond],
            }]
            logger.info(
                f'[_apply_dimension_scope_filter] user={context.user_id} '
                f'object_type={object_type} added owner OR (owner_id={context.user_id})'
            )

        logger.info(
            f'[_apply_dimension_scope_filter] user={context.user_id} object_type={object_type} '
            f'roles_with_scope={len(per_role_conditions)}'
        )
        return True

    def _bo_has_owner_id(self, context: 'ActionContext') -> bool:
        """检查当前 BO 是否有 owner_id 字段"""
        try:
            from meta.core.bo_schema_loader import get_bo_schema_loader
            loader = get_bo_schema_loader()
            return loader.has_owner_id(context.object_type)
        except Exception as e:
            logger.debug(f'[_bo_has_owner_id] error: {e}')
            return False

    @staticmethod
    def _parse_compound_expr(expr: str) -> List[Dict]:
        """[FIX v1.0.3] 解析 dimension scope 派生的 cond_expr

        支持:
          - "id IN (1, 2, 3)"                       → 单条 IN
          - "id = 1"                                 → 单条 EQ
          - "id IN (2,11,12) AND product_id IN (1,17)" → 多条 (AND 关系)

        Returns:
            list of {'field': str, 'operator': str, 'value' or 'values': ...}
        """
        import re
        expr = expr.strip()
        if not expr:
            return []

        # 按 AND 拆开 (大写, 允许两端空白)
        parts = re.split(r'\s+AND\s+', expr, flags=re.IGNORECASE)
        results = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            parsed = DataPermissionInterceptor._parse_single_in_or_eq(part)
            if parsed is None:
                # 解析失败: 整条 cond 失效, 让外层 fallback
                return []
            results.append(parsed)
        return results

    @staticmethod
    def _parse_single_in_or_eq(expr: str):
        """解析单段 'field IN (a,b,c)' 或 'field = n'"""
        import re
        expr = expr.strip()

        # 'id IN (1, 2, 3)' 或 'product_id IN (1, 2)'
        m = re.match(r'^(\w+)\s+IN\s*\(([^)]+)\)\s*$', expr, re.IGNORECASE)
        if m:
            field = m.group(1)
            try:
                values = [int(x.strip()) for x in m.group(2).split(',') if x.strip()]
            except ValueError:
                return None
            if not values:
                return None
            if len(values) == 1:
                return {'field': field, 'operator': 'eq', 'value': values[0]}
            return {'field': field, 'operator': 'in', 'values': values}

        # 'id = 1'
        m = re.match(r'^(\w+)\s*=\s*(\d+)\s*$', expr)
        if m:
            return {'field': m.group(1), 'operator': 'eq', 'value': int(m.group(2))}

        return None

    @staticmethod
    def _parse_id_in_expr(expr: str) -> List[int]:
        """[DEPRECATED v1.0.3] 解析 'id IN (1,2,3)' 或 'id = 1' 或 'product_id IN (1,2)' 格式

        Returns: id 列表
        注意: 此函数无法处理 AND 复合表达式 (例 'id IN (..) AND product_id IN (..)'),
              dimension scope 派生条件是复合表达式时, 请用 _parse_compound_expr。
        """
        import re
        expr = expr.strip()

        # 'id IN (1, 2, 3)' 或 'product_id IN (1, 2)'
        m = re.match(r'^\w+\s+IN\s*\(([^)]+)\)\s*$', expr, re.IGNORECASE)
        if m:
            ids_str = m.group(1)
            try:
                return [int(x.strip()) for x in ids_str.split(',') if x.strip()]
            except ValueError:
                return []

        # 'id = 1' 或 'id = 1 AND product_id IN (...)' → 取第一个
        m = re.match(r'^\w+\s*=\s*(\d+)\s*', expr)
        if m:
            return [int(m.group(1))]

        return []

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
