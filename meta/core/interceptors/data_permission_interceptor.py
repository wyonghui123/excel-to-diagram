# -*- coding: utf-8 -*-
import logging
import os
import re
from typing import TYPE_CHECKING, List, Dict, Optional

from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext


def _has_top_level_or(expr: str) -> bool:
    """检测表达式中是否有顶级 OR (不在括号内的 OR)"""
    depth = 0
    i = 0
    while i < len(expr):
        c = expr[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif depth == 0 and expr[i:i+4].upper() == ' OR ' and (i == 0 or expr[i-1] != 'A'):
            # 确保是独立的 OR 关键词 (不是 AND 中的 O 或其他)
            if re.match(r'\s+OR\s+', expr[i:i+4], re.IGNORECASE):
                return True
        i += 1
    return False


def _is_balanced_parens(expr: str) -> bool:
    """检查表达式中的括号是否平衡（所有左括号都有对应的右括号）"""
    depth = 0
    for c in expr:
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _split_top_level_or(expr: str) -> List[str]:
    """按顶级 OR 拆分表达式 (忽略括号内的 OR)"""
    depth = 0
    parts = []
    start = 0
    i = 0
    while i < len(expr):
        c = expr[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif depth == 0:
            # 检测顶级 OR
            m = re.match(r'\s+OR\s+', expr[i:], re.IGNORECASE)
            if m:
                parts.append(expr[start:i])
                i += m.end()
                start = i
                continue
        i += 1
    parts.append(expr[start:])
    return parts


def _parse_in_subquery(expr: str) -> Optional[Dict]:
    """解析 'field IN (SELECT ...)' 形式的子查询条件"""
    expr = expr.strip()
    m = re.match(r'^(\w+)\s+IN\s*\((SELECT\s+.+)\)\s*$', expr, re.IGNORECASE | re.DOTALL)
    if m:
        field = m.group(1)
        subquery = m.group(2).strip()
        return {'field': field, 'operator': 'in_subquery', 'value': subquery}
    return None

logger = logging.getLogger(__name__)

AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'true').lower() in ('true', '1', 'yes')


def _write_debug(tag, msg):
    """调试日志辅助函数"""
    logger.debug(f'[{tag}] {msg}')


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

    # [V1.2.9 2026-06-17] 关联型 BO (relationship) 的权限过滤策略:
    # 不再"跳过所有过滤"，而是:
    #   1. 应用 dim scope OR 派生: source_bo_id IN (...) OR target_bo_id IN (...)
    #      语义: 关系可见 ⟺ source BO 在权限范围 OR target BO 在权限范围
    #            = 权限域内 + 跨权限域 (排除权限域外)
    #   2. 跳过 visibility scope 和 owner 例外 (relationship 没有这些字段)
    #
    # V1.2.3/V1.2.4 的"跳过所有过滤"导致权限域外的关系也被返回:
    #   TEST888 (dim scope=采购管理) 看到全部 33 条关系, 实际只应看到 12 条
    #
    # DimensionScopeEngine (V1.1.9) 已正确生成 OR 条件:
    #   source_bo_id IN (SELECT ... WHERE domain_id IN (703))
    #   OR target_bo_id IN (SELECT ... WHERE domain_id IN (703))
    # 之前 V1.2.4 跳过了整个拦截器, 这些条件没被使用
    ASSOCIATION_BOS_SKIP_VISIBILITY = {'relationship'}

    def before_action(self, context: 'ActionContext') -> None:
        if not context.is_query_action:
            return

        if not AUTH_ENABLED:
            return

        if self._is_admin(context):
            return

        # [V1.2.9 2026-06-17] relationship 不再跳过 dim scope 过滤
        # 走正常的 _apply_dimension_scope_filter (OR 派生: source OR target)
        # 但跳过 visibility scope + owner 例外 (relationship 无这些字段)
        # 见 _apply_scope_filter_after_dimension 中的 ASSOCIATION_BOS_SKIP_VISIBILITY 处理

        # [FIX v1.0.2 + v1.0.5 2026-06-10] 优先应用 role_dimension_scopes 派生条件
        # 当角色声明了 dimension scope (例: TEST60 version=[2,11,12]) 时,
        # DimensionScopeEngine 自动向上展开到 parent BO (例: product={1,17}),
        # 然后注入到 query_conditions。
        #
        # v1.0.5 修复 (TESET68 bug):
        #   旧逻辑 dimension scope 应用后直接 return, 完全跳过 visibility/owner scope
        #   → 用户能看到 product 范围内所有人的 draft 版本 (违反最小权限)
        #   新逻辑 dimension scope 应用后, 继续调用 _apply_scope_filter,
        #   visibility/owner scope 条件 AND 叠加到 dimension scope 内部。
        #
        # SQL 结构 (修复后):
        #   WHERE (
        #     (dimension_scope 派生条件)              -- 维度范围
        #     AND                                     -- AND 叠加
        #     (visibility='public' OR owner_id=$user) -- visibility/owner
        #   )
        #   OR (owner_id = $user_id)                  -- 自己 owner 始终可见
        dimension_applied = self._apply_dimension_scope_filter(context)

        if dimension_applied:
            # Dimension scope 已应用, 继续叠加 visibility/owner scope (AND 关系)
            # 不再 return, 让 _apply_scope_filter 把 BO.yaml 中的 visibility scope
            # 作为 AND 子条件注入到 dimension scope 条件组内
            self._apply_scope_filter_after_dimension(context)
        else:
            # 没 dimension scope, 走原 scope filter
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

        # 5. [FIX v1.0.5 2026-06-10] 多 role → OR 关系; 单 role → 直接 append 各 AND 段
        #   v1.0.5 移除 v1.0.4 的 owner OR 短路逻辑（修复 TESET68 bug）
        #   owner 例外改由 _apply_scope_filter_after_dimension + _add_owner_exception 处理
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

        logger.info(
            f'[_apply_dimension_scope_filter] user={context.user_id} object_type={object_type} '
            f'roles_with_scope={len(per_role_conditions)} '
            f'(v1.0.5: AND visibility/owner overlay applied in next step)'
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
          - "field IN (SELECT ...) OR field2 IN (SELECT ...)" → OR 关系 (v1.2.1)

        Returns:
            list of {'field': str, 'operator': str, 'value' or 'values': ...}
            OR 关系时返回 [{'type': 'or', 'conditions': [...]}]
        """
        import re
        expr = expr.strip()
        if not expr:
            return []

        # [V1.2.2 2026-06-16] 去除最外层冗余括号
        # DimensionScopeEngine 可能生成 "(A OR B)" 形式, 外层括号会导致
        # _has_top_level_or 误判 OR 在括号内, 从而走 AND 分支解析失败
        while (expr.startswith('(') and expr.endswith(')')
               and _is_balanced_parens(expr[1:-1])):
            expr = expr[1:-1].strip()

        # [V1.2.1 2026-06-16] 先检测是否包含顶级 OR (不在括号内的 OR)
        # relationship 的 dim scope 条件: source_bo_id IN (SELECT ...) OR target_bo_id IN (SELECT ...)
        if _has_top_level_or(expr):
            or_parts = _split_top_level_or(expr)
            or_conditions = []
            for part in or_parts:
                part = part.strip()
                if not part:
                    continue
                # 每个 OR 段可能自身是 AND 复合
                and_parts = re.split(r'\s+AND\s+', part, flags=re.IGNORECASE)
                and_conds = []
                for ap in and_parts:
                    ap = ap.strip()
                    if not ap:
                        continue
                    parsed = DataPermissionInterceptor._parse_single_in_or_eq(ap)
                    if parsed is None:
                        # 尝试 in_subquery 解析
                        parsed = _parse_in_subquery(ap)
                    if parsed is None:
                        # 解析失败: 整条 cond 失效
                        return []
                    and_conds.append(parsed)
                if len(and_conds) == 1:
                    or_conditions.append(and_conds[0])
                else:
                    or_conditions.append({'type': 'and', 'conditions': and_conds})
            if or_conditions:
                return [{'type': 'or', 'conditions': or_conditions}]
            return []

        # 原有 AND 逻辑
        parts = re.split(r'\s+AND\s+', expr, flags=re.IGNORECASE)
        results = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            parsed = DataPermissionInterceptor._parse_single_in_or_eq(part)
            if parsed is None:
                # 尝试 in_subquery 解析
                parsed = _parse_in_subquery(part)
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

        # [FIX] 按顶层 OR 分割，忽略括号内的 OR（避免拆分子查询内部的 OR）
        or_parts = DataPermissionInterceptor._split_top_level_or(expr)
        if len(or_parts) > 1:
            or_group = []
            for part in or_parts:
                or_group.append(DataPermissionInterceptor._parse_simple_condition(part.strip()))
            return [or_group]

        return [DataPermissionInterceptor._parse_simple_condition(expr.strip())]

    @staticmethod
    def _split_top_level_or(expr: str) -> List[str]:
        """按顶层 OR 分割表达式，忽略括号内的 OR

        示例:
          "a = 1 OR b = 2" → ["a = 1", "b = 2"]
          "x IN (SELECT ... WHERE a OR b)" → ["x IN (SELECT ... WHERE a OR b)"]
        """
        parts = []
        depth = 0
        current = []
        i = 0
        upper = expr.upper()
        while i < len(expr):
            if expr[i] == '(':
                depth += 1
                current.append(expr[i])
                i += 1
            elif expr[i] == ')':
                depth -= 1
                current.append(expr[i])
                i += 1
            elif depth == 0 and upper[i:i+4] == ' OR ' and (i == 0 or not upper[i-1].isalnum()):
                # 顶层 OR
                parts.append(''.join(current).strip())
                current = []
                i += 4  # skip ' OR '
            else:
                current.append(expr[i])
                i += 1
        remainder = ''.join(current).strip()
        if remainder:
            parts.append(remainder)
        return parts

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

    # ────────────────────────────────────────
    # [FIX v1.0.5 + v1.0.8 2026-06-10] Dimension scope 命中后的 visibility 叠加
    # 修复 TESET68 bug: dimension scope 命中不再跳过 visibility/owner scope
    #
    # [FIX v1.0.8 2026-06-10] 只对含 visibility 字段的 BO 应用 visibility scope
    #   - version 有 visibility 字段 → 应用 visibility scope（保护 draft）
    #   - product 没有 visibility 字段 → 跳过 visibility scope（避免过严）
    #   - 两种情况都加 owner 例外（自己 owner 的永远可见）
    # ────────────────────────────────────────
    def _apply_scope_filter_after_dimension(self, context: 'ActionContext') -> None:
        """dimension scope 已应用后, 叠加 visibility scope（仅当 BO 有 visibility 字段）

        [FIX v1.0.8] 分情况处理:
        - BO 有 visibility 字段（如 version）→ AND 叠加 visibility scope
        - BO 无 visibility 字段（如 product）→ 跳过 visibility scope（避免过严）
        - 两种情况都加 owner 例外

        [V1.2.9] 关联型 BO (relationship) 跳过 visibility scope 和 owner 例外:
        - relationship 没有 visibility/owner_id 字段
        - dim scope OR 派生 (source_bo_id IN ... OR target_bo_id IN ...) 已足够

        修复后 SQL（version 有 visibility）:
          WHERE (product_id = 1) AND (visibility='public' OR owner_id=$user)
              OR (owner_id = $user_id)

        修复后 SQL（product 无 visibility）:
          WHERE (id IN (1, 17))   -- dimension scope 直接授权
              OR (owner_id = $user_id)  -- owner 例外
        """
        meta_obj = context.meta_object
        if meta_obj is None:
            return

        # [V1.2.9] 关联型 BO (relationship) 跳过 visibility scope 和 owner 例外
        # relationship 没有 visibility/owner_id 字段, dim scope OR 派生已足够
        if context.object_type in self.ASSOCIATION_BOS_SKIP_VISIBILITY:
            logger.info(
                f'[_apply_scope_filter_after_dimension] Skipping visibility+owner for '
                f'{context.object_type} (association BO, dim scope OR-derived is sufficient)'
            )
            return

        # [FIX v1.0.8] 检查 BO 是否有 visibility 字段
        if not self._bo_has_visibility_field(context):
            # 没有 visibility 字段, 跳过 visibility scope
            # 直接加 owner 例外（dimension scope 已经表达了"被授权"）
            self._add_owner_exception(context)
            return

        authorization = getattr(meta_obj, 'authorization', None)

        # 解析 visibility scope（如果有）
        visibility_conditions = []
        if authorization:
            scope_expr = None
            if isinstance(authorization, dict):
                scope_expr = authorization.get('scope')
            elif hasattr(authorization, 'scope'):
                scope_expr = authorization.scope

            if scope_expr:
                resolved = scope_expr
                if context.user_id:
                    resolved = resolved.replace('$user.id', str(context.user_id))
                if context.user_name:
                    resolved = resolved.replace('$user.username', str(context.user_name))

                try:
                    parsed = self._parse_scope_expression(resolved)
                    for cond_item in parsed:
                        if isinstance(cond_item, list):
                            or_conditions = [
                                {'field': c['field'], 'operator': c['operator'], 'value': c['value']}
                                for c in cond_item
                            ]
                            visibility_conditions.append({
                                'type': 'or',
                                'conditions': or_conditions,
                                'source': 'visibility_scope',
                            })
                        else:
                            visibility_conditions.append({
                                'field': cond_item['field'],
                                'operator': cond_item['operator'],
                                'value': cond_item['value'],
                                'source': 'visibility_scope',
                            })
                except Exception as e:
                    logger.warning(f'[_apply_scope_filter_after_dimension] parse scope failed: {e}')

        # 把 visibility 条件平铺到 query_conditions
        existing = context.extra.get('query_conditions', [])
        new_conditions = list(existing) + visibility_conditions
        context.extra['query_conditions'] = new_conditions

        logger.info(
            f'[_apply_scope_filter_after_dimension] user={context.user_id} '
            f'object_type={context.object_type} '
            f'visibility scope AND-overlaid ({len(visibility_conditions)} conds)'
        )

        # owner 例外
        self._add_owner_exception(context)

    def _bo_has_visibility_field(self, context: 'ActionContext') -> bool:
        """[FIX v1.0.8] 检查当前 BO 是否有 visibility 字段

        用于判断是否需要应用 visibility scope 过滤:
        - version 有 visibility 字段 → True (应用 visibility scope 保护 draft)
        - product 没有 visibility 字段 → False (跳过 visibility scope, 避免过严)

        委托给 BoSchemaLoader.has_visibility_field (复用现有缓存机制)
        """
        try:
            from meta.core.bo_schema_loader import get_bo_schema_loader
            loader = get_bo_schema_loader()
            return loader.has_visibility_field(context.object_type)
        except Exception as e:
            logger.debug(f'[_bo_has_visibility_field] error: {e}')
            return False

    def _add_owner_exception(self, context: 'ActionContext') -> None:
        """[FIX v1.0.5 + v1.0.7] owner 例外: 用户对自己 owner 的资源始终可见

        即使 dimension scope 命中且 visibility=draft, 只要 owner=自己, 仍然可见。

        [FIX v1.0.7 2026-06-10]
        persistence_interceptor._build_scope_conditions 支持嵌套 AND/OR group,
        我们用以下嵌套结构表达:

        最终 SQL 结构:
          WHERE (product_id = ? AND (visibility = ? OR owner_id = ?))
              OR (owner_id = ?)

        实现:
          query_conditions = [
              {'type': 'and', 'conditions': [dim_cond, visibility_or_group]},
              owner_cond
          ]
        然后把整个列表用顶层 type='or' 包住, 表达 OR 关系:
          query_conditions = [
              {'type': 'or', 'conditions': [
                  {'type': 'and', 'conditions': [dim_cond, visibility_or_group]},
                  owner_cond,
              ]}
          ]
        """
        if not context.user_id:
            return
        if not self._bo_has_owner_id(context):
            return

        owner_cond = {
            'field': 'owner_id',
            'operator': 'eq',
            'value': context.user_id,
            'source': 'owner_exception',
        }
        existing = list(context.extra.get('query_conditions', []))
        if not existing:
            context.extra['query_conditions'] = [owner_cond]
            return

        # 把 existing 包成 and_group, 然后 OR 上 owner_cond
        # 用顶层 type='or' 包住 (dim+visibility AND group) 和 owner_cond
        and_group = {
            'type': 'and',
            'conditions': existing,
        }
        context.extra['query_conditions'] = [{
            'type': 'or',
            'conditions': [and_group, owner_cond],
        }]
        logger.info(
            f'[_add_owner_exception] user={context.user_id} '
            f'object_type={context.object_type} '
            f'wrapped {len(existing)} existing into AND group, '
            f'OR with owner_exception (top-level OR group)'
        )
