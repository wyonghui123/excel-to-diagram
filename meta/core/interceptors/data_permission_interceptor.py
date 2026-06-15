# -*- coding: utf-8 -*-
import logging
import os
from typing import TYPE_CHECKING, List

from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


def _write_debug(tag, msg):
    """[v1.1.5 DEBUG] 写调试信息到文件 (因 service_manager 不捕获 stdout)"""
    try:
        debug_file = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'logs', 'permission_debug.log')
        debug_file = os.path.abspath(debug_file)
        os.makedirs(os.path.dirname(debug_file), exist_ok=True)
        with open(debug_file, 'a', encoding='utf-8') as f:
            f.write(f'[{tag}] {msg}\n')
    except Exception as e:
        logger.debug(f'write_debug failed: {e}')

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
            logger.warning(f'[DPI-DEBUG] AUTH_ENABLED=False, skipping all permission checks')
            return

        if self._is_admin(context):
            logger.info(f'[DPI-DEBUG] user={context.user_id} is_admin=True, skipping dim scope')
            return

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
        logger.info(f'[DPI-DEBUG] user={context.user_id} object_type={context.object_type} dimension_applied={dimension_applied} query_conditions={context.extra.get("query_conditions", [])}')

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
                    # [FIX v1.0.7 2026-06-15] 角色无 dim scope 派生 = 跳过 (不进 OR-of-AND)
                    # 业界标准 (SAP/Salesforce/Oracle): 多 role data scope 取并集, 但
                    #   "无 dim scope" 不等于 "always_true 永真" (那是过度宽松).
                    # 正确语义: 该 role 不参与 dim scope 组合, 让其他有 dim scope 的 role
                    #   决定可见范围. 例: TEST333 (5434 公司可读 + 5970 采购管理) →
                    #   5970 单独生效 → domain=703 范围内 8 条 (而非全部 29).
                    # 之前 v1.0.6 加 always_true 占位: 5970 限制被吞 → 29 条 (违反隔离).
                    logger.info(
                        f'[_apply_dimension_scope_filter] user={context.user_id} role={role_id} '
                        f'object_type={object_type} -> NO dim scope, SKIP (v1.0.7)'
                    )
                    continue

                # 4. 解析单段表达式 (支持 AND 复合)
                conds = self._parse_compound_expr(cond_expr)
                if not conds:
                    # [FIX v1.0.7] 解析失败也跳过, 不阻断也不占位
                    logger.info(
                        f'[_apply_dimension_scope_filter] user={context.user_id} role={role_id} '
                        f'object_type={object_type} -> parse empty, SKIP (v1.0.7)'
                    )
                    continue
                per_role_conditions.append(conds)
                logger.info(
                    f'[_apply_dimension_scope_filter] user={context.user_id} role={role_id} '
                    f'object_type={object_type} -> conds={conds}'
                )
            except Exception as e:
                # [FIX v1.0.7] 异常时跳过, 不阻断也不占位
                logger.warning(f'[_apply_dimension_scope_filter] derive role_id={role_id} failed: {e}')
                continue

        if not per_role_conditions:
            return False  # 没有 role 派生该 object_type, 走原 scope filter

        if 'query_conditions' not in context.extra:
            context.extra['query_conditions'] = []

        # 5. [FIX v1.0.5 2026-06-10] 多 role → OR 关系; 单 role → 直接 append 各 AND 段
        #   v1.0.5 移除 v1.0.4 的 owner OR 短路逻辑（修复 TESET68 bug）
        #   owner 例外改由 _apply_scope_filter_after_dimension + _add_owner_exception 处理
        if len(per_role_conditions) == 1:
            for c in per_role_conditions[0]:
                c['source'] = 'dimension_scope'  # [FIX 2026-06-16] 标记来源
                context.extra['query_conditions'].append(c)
        else:
            # 多 role: OR-of-AND
            or_group_conditions = []
            for conds in per_role_conditions:
                for c in conds:
                    c['source'] = 'dimension_scope'  # [FIX 2026-06-16] 标记来源
                or_group_conditions.extend(conds)
            context.extra['query_conditions'].append({
                'type': 'or',
                'conditions': or_group_conditions,
                'source': 'dimension_scope',  # [FIX 2026-06-16] 标记来源
            })

        logger.info(
            f'[_apply_dimension_scope_filter] user={context.user_id} object_type={object_type} '
            f'roles_with_scope={len(per_role_conditions)} '
            f'per_role_conditions={per_role_conditions} '
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
          - [FIX v1.1.9] "(A IN (...) OR B IN (...))" → 单条 OR 段 (跨域 association 推导)
              关系: source_bo_id / target_bo_id 任一端在 dim scope 内
              → 嵌套 {'type': 'or', 'conditions': [A, B]}

        Returns:
            list of {'field', 'operator', 'value'/'values'}
            或 list 中含 {'type': 'or', 'conditions': [...]}
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
            # [FIX v1.1.9] 段内含 OR: (A OR B) 形式 → 解析为 OR 嵌套 dict
            if ' OR ' in part.upper():
                or_match = re.match(r'^\((.*)\)$', part, re.IGNORECASE | re.DOTALL)
                if or_match:
                    inner = or_match.group(1)
                    or_parts = re.split(r'\s+OR\s+', inner, flags=re.IGNORECASE)
                    or_conds = []
                    for op in or_parts:
                        op = op.strip()
                        if not op:
                            continue
                        parsed = DataPermissionInterceptor._parse_single_in_or_eq(op)
                        if parsed is None:
                            return []  # 解析失败: 整条 cond 失效
                        or_conds.append(parsed)
                    if or_conds:
                        results.append({'type': 'or', 'conditions': or_conds})
                    continue
            # 单段: 直接解析
            parsed = DataPermissionInterceptor._parse_single_in_or_eq(part)
            if parsed is None:
                # [FIX 2026-06-16] 解析失败不丢弃已成功解析的部分
                # 例如 domain 条件 "id = 703 AND version_id IN (SELECT ...)"
                # "id = 703" 能解析成功，但子查询部分不能 → 只跳过失败部分
                logger.debug(f'[_parse_compound_expr] Skipping unparseable part: {part}')
                continue
            results.append(parsed)
        return results

    @staticmethod
    def _parse_single_in_or_eq(expr: str):
        """解析单段表达式

        支持:
          - 'id IN (1, 2, 3)' → 字面量列表
          - 'id = 1' → 等值
          - [FIX 2026-06-14] 'id IN (SELECT ...)' → in_subquery (DimensionScopeEngine 派生)
        """
        import re
        expr = expr.strip()

        # [FIX 2026-06-14] 优先处理 'field IN (SELECT ...)' 子查询形式
        # 解析思路: 找到 'IN' 之后首个 '(', 用括号深度跟踪提取完整子查询
        m = re.match(r'^(\w+)\s+IN\s*\(', expr, re.IGNORECASE)
        if m:
            field = m.group(1)
            open_idx = m.end() - 1  # 指向 '('
            # 括号深度跟踪, 提取完整 SELECT 子查询
            depth = 0
            close_idx = -1
            for i in range(open_idx, len(expr)):
                c = expr[i]
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        close_idx = i
                        break
            if close_idx == -1:
                return None  # 括号不闭合, 解析失败
            inner = expr[open_idx + 1:close_idx].strip()
            trailing = expr[close_idx + 1:].strip()
            if trailing:
                return None  # IN (...) 之后不应有别的内容 (允许的 AND 在 _parse_compound_expr 处理)

            # [FIX 2026-06-14] 子查询形式: field IN (SELECT ...)
            if re.match(r'^SELECT\b', inner, re.IGNORECASE):
                # 替换 SELECT 内的 ? 占位符为 $user.id (如果 scope 表达式里有)
                inner_resolved = inner.replace('?', str(0))  # 占位符在执行时由 SQL 渲染层替换
                return {'field': field, 'operator': 'in_subquery', 'value': inner_resolved}

            # 字面量列表: field IN (1, 2, 3)
            try:
                values = [int(x.strip()) for x in inner.split(',') if x.strip()]
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
        """
        括号感知的 OR 拆分。

        修复 v1.x: 之前用 re.split(r'\\s+OR\\s+', ...) 会把 IN (SELECT ... WHERE ... OR ...)
        子查询里的 OR 也拆开, 产生 ``product_id IN (SELECT ... visibility = 'public'`` 这种
        未闭合的左括号碎片, 下游 SQL 拼接后报 'incomplete input'。

        新实现是手写状态机, 跟踪括号深度和字符串字面量, 只在 depth==0 且不在字符串内
        时才识别顶层 OR 关键字。
        """
        or_parts = []
        depth = 0
        in_string = False
        string_char = None
        current = []
        i = 0
        n = len(expr)
        while i < n:
            c = expr[i]

            # 字符串字面量内 (跳过 OR 关键字检测)
            if in_string:
                current.append(c)
                if c == '\\' and i + 1 < n:
                    current.append(expr[i + 1])
                    i += 2
                    continue
                if c == string_char:
                    in_string = False
                i += 1
                continue
            if c in ("'", '"'):
                in_string = True
                string_char = c
                current.append(c)
                i += 1
                continue

            # 括号深度跟踪
            if c == '(':
                depth += 1
            elif c == ')':
                depth = max(depth - 1, 0)

            # 仅在 depth=0 时把 OR 当顶层关键字
            if depth == 0 and not in_string:
                if (i + 2) <= n and expr[i:i + 2].upper() == 'OR' \
                        and (i == 0 or expr[i - 1].isspace()) \
                        and (i + 2 == n or expr[i + 2].isspace()):
                    or_parts.append(''.join(current).strip())
                    current = []
                    i += 2
                    continue

            current.append(c)
            i += 1

        if current:
            tail = ''.join(current).strip()
            if tail:
                or_parts.append(tail)

        if len(or_parts) > 1:
            or_group = []
            for part in or_parts:
                or_group.append(DataPermissionInterceptor._parse_simple_condition(part))
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
                    op_val = c.operator.value if hasattr(c.operator, 'value') else str(c.operator)
                    cond_dict = {'field': c.field, 'operator': op_val}
                    if op_val == 'in':
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

        # [FIX v1.0.8] 检查 BO 是否有 visibility 字段
        if not self._bo_has_visibility_field(context):
            # [FIX 2026-06-16] 没有 visibility 字段时, dim scope 已表达被授权范围
            # 不加 owner 例外, 否则会绕过 dim scope 限制
            # 例: TEST888 有 domain=703 dim scope → product id=475
            # 但 owner_id=3371 的 product 有 108 个 → owner 例外让 dim scope 失效
            logger.info(
                f'[_apply_scope_filter_after_dimension] user={context.user_id} '
                f'object_type={context.object_type} '
                f'no visibility field, dim scope only (no owner exception)'
            )
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
        """[FIX v1.0.5 + v1.0.7 + v1.1.5] owner 例外: 用户对自己 owner 的资源始终可见

        即使 dimension scope 命中且 visibility=draft, 只要 owner=自己, 仍然可见。

        [FIX v1.0.7 2026-06-10]
        persistence_interceptor._build_scope_conditions 支持嵌套 AND/OR group,
        我们用以下嵌套结构表达:

        最终 SQL 结构 (无 dim scope):
          WHERE (visibility = ? OR owner_id = ?)

        最终 SQL 结构 (有 dim scope):
          WHERE (dim_scope_cond AND (visibility = ? OR owner_id = ?))

        [FIX 2026-06-16] 当 dim scope 已应用时, owner 例外不绕过 dim scope
        旧逻辑: (dim_scope AND visibility) OR owner_id → owner_id 绕过 dim scope
        新逻辑: dim_scope AND (visibility OR owner_id) → owner_id 在 dim scope 内

        [FIX v1.1.5 2026-06-15] HIERARCHY_CHAIN 化: version/domain/sub_domain
        顶层没有 owner_id 字段, 但顶层 owner 在 product. 之前 _bo_has_owner_id
        返回 False 导致 owner 例外失效 (e.g. TEST333 创建了 product 476 + V10,
        看不到 V10).

        修复: 即使 BO 无 owner_id 字段, 也尝试沿 HIERARCHY_CHAIN 向上查
        product.owner_id. 用 build_owner_exception_subquery 生成链式 SQL 子查询
        (e.g. version: 'id IN (SELECT id FROM versions WHERE product_id IN
        (SELECT id FROM products WHERE owner_id = $user))').

        降级: chain 上找不到 (BO 不在 chain) → 不加 owner 例外
        """
        if not context.user_id:
            return

        # [v1.1.5] 决定 owner 例外 SQL 表达式
        owner_cond = self._build_owner_exception_cond(context)
        if owner_cond is None:
            # 既无 owner_id 字段, 又不在 HIERARCHY_CHAIN
            return

        existing = list(context.extra.get('query_conditions', []))
        if not existing:
            context.extra['query_conditions'] = [owner_cond]
            return

        # [FIX 2026-06-16] 检查是否有 dim scope 条件
        # 如果有 dim scope, owner 例外必须在 dim scope 范围内
        # 即: dim_scope AND (visibility OR owner_id), 而不是 (dim_scope AND visibility) OR owner_id
        has_dim_scope = any(
            c.get('source') == 'dimension_scope' or
            (c.get('type') == 'and' and any(
                sc.get('source') == 'dimension_scope'
                for sc in c.get('conditions', [])
            ))
            for c in existing
        )

        if has_dim_scope:
            # [FIX 2026-06-16] owner 例外在 dim scope 范围内
            # 把 owner_cond 合并到 visibility OR 组内（如果有的话）
            # 否则作为独立 AND 条件（但仍在 dim scope 范围内）
            #
            # 目标 SQL: dim_scope AND (visibility = 'public' OR owner_id = ?)
            # 而不是: dim_scope AND visibility = 'public' AND owner_id = ?
            merged = False
            for i, cond in enumerate(existing):
                if isinstance(cond, dict) and cond.get('type') == 'or':
                    # 找到 visibility OR 组，把 owner_cond 加入
                    existing[i]['conditions'].append(owner_cond)
                    merged = True
                    break
            if not merged:
                # 没有 OR 组，创建一个: (owner_id = ?)
                # 但这会变成 dim_scope AND owner_id = ?，可能过严
                # 更好的做法是创建 OR 组: (visibility OR owner_id)
                # 但如果没有 visibility 条件，就直接 append
                existing.append(owner_cond)
            context.extra['query_conditions'] = existing
            logger.info(
                f'[_add_owner_exception] user={context.user_id} '
                f'object_type={context.object_type} '
                f'dim scope active, owner exception within dim scope (merged={merged})'
            )
        else:
            # 无 dim scope: 把 existing 包成 and_group, 然后 OR 上 owner_cond
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
                f'no dim scope, owner exception as top-level OR'
            )

    def _build_owner_exception_cond(self, context: 'ActionContext') -> Optional[Dict]:
        """[v1.1.5] 构造 owner 例外 condition (含 chain 追溯)

        决策树:
        1. BO 有 owner_id 字段 (e.g. product) → owner_id = $user 直接
        2. BO 在 HIERARCHY_CHAIN (e.g. version/domain/sub_domain) →
           用 build_owner_exception_subquery 生成链式 SQL 子查询
        3. 都不满足 (e.g. relationship) → None (caller 不加 owner 例外)

        Returns:
            QueryCondition dict 或 None
        """
        if not context.user_id:
            return None

        # 路径 1: BO 直接有 owner_id 字段 (跟之前行为一致)
        if self._bo_has_owner_id(context):
            return {
                'field': 'owner_id',
                'operator': 'eq',
                'value': context.user_id,
                'source': 'owner_exception',
            }

        # 路径 2: [v1.1.5] BO 在 HIERARCHY_CHAIN, 沿 chain 查 product.owner
        try:
            from meta.services.chain_owner_resolver import (
                is_in_chain,
                build_owner_exception_subquery,
            )
            if not is_in_chain(context.object_type):
                return None

            subquery_expr = build_owner_exception_subquery(
                context.data_source, context.object_type, context.user_id
            )
            if not subquery_expr:
                return None

            # 表达为 in_subquery 条件
            return {
                'field': 'id',
                'operator': 'in_subquery',
                'value': subquery_expr,
                'source': 'owner_exception_chain',
            }
        except Exception as e:
            logger.debug(f'[_build_owner_exception_cond] chain resolve failed: {e}')
            return None
