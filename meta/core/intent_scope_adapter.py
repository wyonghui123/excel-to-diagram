# -*- coding: utf-8 -*-
"""
IntentScopeAdapter — 桥接 role_effective_intents (Layer 1) 到现有拦截器

[背景]
  Phase 2 需要让 DataPermissionInterceptor / WriteScopeInterceptor 切换到读取
  role_effective_intents 表。但现有拦截器已有 ~2000+ 行复杂逻辑 (owner chain,
  dim scope, visibility, FK scope policies...)。

[策略]
  最小侵入: 创建一个 adapter, 把 effective_intents.data_scope (JSON) 转换为
  现有拦截器期望的 SQL WHERE 片段, 然后在拦截器入口加 Feature flag 切换。

[Feature Flag]
  effective_intents_enabled = True 时启用 adapter
  = False 时回退到原 role_dimension_scopes + data_permission_rules 路径

[输出格式]
  现有 DataPermissionInterceptor 期望的格式:
    - cond_expr: SQL WHERE 表达式字符串 (无外层 WHERE)
    - params: 参数列表

  示例:
    data_scope = {
      "include": [{"field":"domain_id","op":"IN","value":[1,2]}],
      "exclude": [{"field":"status","op":"=","value":"archived"}]
    }
    → cond_expr: "domain_id IN (?, ?) AND status != ?"
    → params: [1, 2, 'archived']
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from meta.core.condition_parser import ConditionExpressionParser
from meta.core.effective_intent_dao import EffectiveIntentDAO


class IntentScopeAdapter:
    """桥接 effective_intents → 现有拦截器 SQL 条件"""

    def __init__(
        self,
        db_path: str,
        dao: Optional[EffectiveIntentDAO] = None,
        parser: Optional[ConditionExpressionParser] = None,
    ):
        self._db_path = db_path
        self._dao = dao or EffectiveIntentDAO(db_path)
        self._parser = parser or ConditionExpressionParser()

    def get_filter_for_roles(
        self,
        role_ids: List[int],
        bo_id: str,
        action_name: str = 'read',
        user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取多个角色的合并过滤条件

        [P0-A1 修复 2026-07-26] 重构: exclude 全局生效 (跨 role Deny 优先)

        Args:
            role_ids: 角色 ID 列表
            bo_id: 业务对象 ID
            action_name: 操作名称 (默认 'read')
            user_id: 当前用户 ID (用于解析 ${user.id} 运行时变量)

        Returns:
            {
                'cond_expr': str,  # SQL WHERE 片段
                'params': List[Any],
                'sources': List[str],
            }
            或 None (无任何 Intent = 未配置 = 允许所有)

        [语义] (跨 role Deny 优先 - 与 check_record_allowed 一致)
          - 所有 role 都无 Intent → None (默认允许所有, 未配置=不加过滤)
          - 任一 role 有 Intent:
              include: 所有 role 的 include 用 OR 合并 (任一允许即允许)
              exclude: 所有 role 的 exclude 用 OR 合并, 整体 NOT (任一拒绝即拒绝)
              最终 SQL: (include_A OR include_B OR ...) AND NOT (exclude_A OR exclude_B OR ...)

        [修复前问题]
          旧实现: 每个 role 独立生成 (include AND NOT exclude), 然后 OR 合并
          SQL: (inc_A AND NOT exc_A) OR (inc_B AND NOT exc_B)
          问题: role A exclude [339] + role B include [339] → 339 仍可见
                (role B 的 include 绕过了 role A 的 exclude)
          修复后: (inc_A OR inc_B) AND NOT (exc_A OR exc_B)
                → 339 被 role A exclude 拒绝, role B 的 include 无效
        """
        if not role_ids:
            return None

        # 构建 runtime_vars (用于解析 ${user.id} 等变量)
        runtime_vars = {'user.id': user_id} if user_id is not None else {}

        include_clauses = []  # 所有 role 的 include 子句 (OR 合并)
        include_params = []
        exclude_clauses = []  # 所有 role 的 exclude 子句 (OR 合并, 整体 NOT)
        exclude_params = []
        sources = []

        has_any_intent = False
        has_any_include = False  # 是否有 role 配了 include (空 include = all, 也算)
        has_any_exclude = False

        for role_id in role_ids:
            intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)
            if not intents:
                sources.append('default_deny')
                continue

            has_any_intent = True
            intent = intents[0]
            data_scope = json.loads(intent['data_scope']) if intent['data_scope'] else {}

            include = data_scope.get('include', [])
            exclude = data_scope.get('exclude', [])

            # 收集 include 条件 (OR 合并)
            if include:
                inc_sql, inc_params = self._parser.to_sql(include, runtime_vars)
                if inc_sql:
                    include_clauses.append(f'({inc_sql})')
                    include_params.extend(inc_params)
                    has_any_include = True
                    sources.append('include')
            else:
                # 空 include = all (该 role 允许所有, OR 合并中加 1=1)
                include_clauses.append('(1=1)')
                has_any_include = True
                sources.append('include_all')

            # 收集 exclude 条件 (OR 合并)
            if exclude:
                exc_sql, exc_p = self._parser.to_sql(exclude, runtime_vars)
                if exc_sql:
                    exclude_clauses.append(f'({exc_sql})')
                    exclude_params.extend(exc_p)
                    has_any_exclude = True

        # 所有 role 都无 Intent = 未配置 = 允许所有 (返回 None 表示不加过滤)
        if not has_any_intent:
            return None

        # 构建 include 部分 (OR 合并)
        # 如果没有任何 include 子句 (理论上不会, 因为空 include 会加 1=1), 默认 1=0 (拒绝)
        if include_clauses:
            include_expr = ' OR '.join(include_clauses)
        else:
            include_expr = '1=0'  # 无 include = 拒绝

        # 构建 exclude 部分 (NOT (OR 合并))
        if has_any_exclude and exclude_clauses:
            exclude_expr = ' OR '.join(exclude_clauses)
            cond_expr = f'({include_expr}) AND NOT ({exclude_expr})'
            all_params = include_params + exclude_params
        else:
            cond_expr = include_expr
            all_params = include_params

        return {
            'cond_expr': cond_expr,
            'params': all_params,
            'sources': sources,
        }

    def _get_filter_for_single_role(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        runtime_vars: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取单个角色的过滤条件

        Returns:
            {'cond_expr': str, 'params': List, 'source': str}
            或 None (无 Intent → 默认拒绝)
        """
        intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)
        if not intents:
            return None

        # 取第一个 Intent (upsert 保证唯一)
        intent = intents[0]
        data_scope = json.loads(intent['data_scope']) if intent['data_scope'] else {}

        include = data_scope.get('include', [])
        exclude = data_scope.get('exclude', [])

        clauses = []
        params = []

        # include 条件 (AND 关系)
        # 空 include = 全部允许 (无 WHERE 限制)
        if include:
            inc_sql, inc_params = self._parser.to_sql(include, runtime_vars)
            if inc_sql:
                clauses.append(inc_sql)
                params.extend(inc_params)
        else:
            # 空 include = 允许所有, 添加 1=1 占位
            clauses.append('1=1')

        # exclude 条件 (AND NOT 关系)
        if exclude:
            exc_sql, exc_params = self._parser.to_sql(exclude, runtime_vars)
            if exc_sql:
                clauses.append(f'NOT ({exc_sql})')
                params.extend(exc_params)

        if not clauses:
            return None

        cond_expr = ' AND '.join(clauses)
        return {
            'cond_expr': cond_expr,
            'params': params,
            'source': 'include' if include else 'all',
        }

    def check_record_allowed(
        self,
        role_ids: List[int],
        bo_id: str,
        action_name: str,
        record_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """检查单条记录是否被允许 (用于写拦截器)

        Args:
            role_ids: 角色 ID 列表
            bo_id: 业务对象 ID
            action_name: 操作名称
            record_id: 记录 ID
            user_id: 当前用户 ID

        Returns:
            {'allowed': bool, 'source': str, 'reason': str}

        [source 语义]
          - 'owner': owner 命中 (允许)
          - 'no_intent_allows_all': 无 Intent 配置 (调用方应回退到 legacy 5 步检查)
          - 'exclude': 命中 exclude 条件 (拒绝)
          - 'include': 命中 include 条件 (允许)
          - 'include_all': 空 include = 全允许
          - 'record_not_found': 记录不存在 (调用方应回退到 legacy 处理)
          - 'default_deny': 默认拒绝

        [P1-A4 2026-07-26] no_intent 行为设计意图 (read/write 路径差异)
          - read 路径 (get_filter_for_roles): 无 Intent → 返回 None = 不加 WHERE = 允许所有
            (与旧 DataPermissionInterceptor 一致: 无 dim scope = 不加过滤)
          - write 路径 (check_record_allowed): 无 Intent → 返回 allowed=False + source='no_intent_allows_all'
            → 调用方 (WriteScopeInterceptor._apply_effective_intents_write_check) 回退到 legacy 5 步检查
            (legacy 包含 owner chain + dim scope + visibility 完整链路, 更严格)
          - EffectiveIntentChecker.check (Layer 1): 无 Intent → 返回 allowed=True
            (该 checker 是独立的 Layer 1 求值, 不回退 legacy)

          [设计理由]
            1. read 路径宽松: 未配置 = 不加过滤 = 允许所有 (与旧系统一致, 避免锁定未配置角色)
            2. write 路径严格: 未配置 → 回退 legacy (legacy 包含完整 5 步检查, 更安全)
            3. EffectiveIntentChecker 是独立 Layer 1 checker, 用于内部求值 (不涉及写路径),
               默认允许是为了与旧系统行为对齐

          [一致性保证]
            - 已配置 Intent 时: read 和 write 行为一致 (Owner > Exclude > Include > Default deny)
            - 未配置 Intent 时: read 允许所有, write 回退 legacy (设计意图, 非缺陷)
        """
        if not role_ids:
            return {
                'allowed': False,
                'source': 'no_role',
                'reason': 'User has no roles',
            }

        # [P5 补充 2026-07-26] Step 0a: 记录存在性检查
        # 用于 PUT 不存在 ID 的场景 (B2 测试)
        # 返回 'record_not_found' 让调用方回退到 legacy 处理 (legacy 会抛 WriteScopeDenied)
        if user_id is not None:
            record = self._get_record(bo_id, record_id)
            if record is None:
                return {
                    'allowed': False,
                    'source': 'record_not_found',
                    'reason': f'Record {bo_id}#{record_id} not found',
                }
            # [P4 补充] Step 0b: Owner 检查 (最高优先级, 不受 exclude 限制)
            # 与 EffectiveIntentChecker.check 保持一致
            # 修复 WriteScope owner 链失效问题
            if self._is_owner(record, user_id):
                return {
                    'allowed': True,
                    'source': 'owner',
                    'reason': f'User {user_id} is owner of {bo_id}#{record_id}',
                }

        # [P4 补充] 检查是否所有角色都无 Intent (未配置 = 允许所有)
        has_any_intent = False
        for role_id in role_ids:
            intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)
            if intents:
                has_any_intent = True
                break

        if not has_any_intent:
            # 所有角色都无 Intent = 未配置
            # [P5 修复 2026-07-26] 对于写操作, 返回 'no_intent_allows_all'
            # 让调用方 (_apply_effective_intents_write_check) 回退到 legacy 5 步检查
            # (legacy 包含 owner chain + dim scope + visibility 完整链路)
            # 之前直接返回 allowed=True 会导致 C1/D2 测试失败 (越权写通过)
            return {
                'allowed': False,
                'source': 'no_intent_allows_all',
                'reason': f'No intent for any role (需回退到 legacy 写权限检查)',
            }

        # [Deny 优先语义] (跟 EffectiveIntentChecker.check_multi_role 一致)
        # 1. 先检查所有 role 的 exclude (任一命中即拒绝)
        # 2. 再检查 include (任一匹配即允许)
        # 3. 默认拒绝

        # Pass 1: exclude 检查 (Deny 优先)
        for role_id in role_ids:
            intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)
            if not intents:
                continue

            intent = intents[0]
            data_scope = json.loads(intent['data_scope']) if intent['data_scope'] else {}

            exclude = data_scope.get('exclude', [])
            if exclude and self._matches_any(record_id, bo_id, exclude, user_id):
                return {
                    'allowed': False,
                    'source': 'exclude',
                    'reason': f'Record matched exclude condition (role={role_id})',
                }

        # Pass 2: include 检查 (任一 role 允许即允许)
        for role_id in role_ids:
            intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)
            if not intents:
                continue

            intent = intents[0]
            data_scope = json.loads(intent['data_scope']) if intent['data_scope'] else {}

            include = data_scope.get('include', [])

            # 空 include = 全部允许
            if not include:
                return {
                    'allowed': True,
                    'source': 'include_all',
                    'reason': f'Empty include = all allowed (role={role_id})',
                }
            if self._matches_any(record_id, bo_id, include, user_id):
                return {
                    'allowed': True,
                    'source': 'include',
                    'reason': f'Record matches include condition (role={role_id})',
                }

        return {
            'allowed': False,
            'source': 'default_deny',
            'reason': 'No matching intent',
        }

    def _matches_any(
        self,
        record_id: int,
        bo_id: str,
        conditions: List[Dict[str, Any]],
        user_id: int,
    ) -> bool:
        """检查记录是否匹配任一条件 (运行时变量替换后)

        [实现]
          用 ConditionExpressionParser 将 conditions 转为 SQL WHERE,
          然后用 SELECT COUNT(*) 验证记录是否匹配。
          支持字面值 + ${user.id} 运行时变量。
        """
        if not conditions:
            return False

        # 构建 runtime_vars
        runtime_vars = {'user.id': user_id} if user_id is not None else {}

        # 用 parser 生成 SQL
        try:
            where_sql, params = self._parser.to_sql(conditions, runtime_vars)
        except Exception:
            return False

        if not where_sql:
            return False

        # 表名映射
        table_map = {
            'product': 'products',
            'version': 'versions',
            'domain': 'domains',
            'sub_domain': 'sub_domains',
            'service_module': 'service_modules',
            'business_object': 'business_objects',
        }
        table = table_map.get(bo_id, f'{bo_id}s')

        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    f'SELECT COUNT(*) FROM {table} WHERE id = ? AND ({where_sql})',
                    [record_id] + params,
                ).fetchone()
                return row[0] > 0
        except sqlite3.Error:
            return False

    # [P4 补充] Owner 检查辅助方法 (与 EffectiveIntentChecker 一致)
    _TABLE_MAP = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
    }

    def _get_record(self, bo_id: str, record_id: int) -> Optional[Dict[str, Any]]:
        """获取记录数据 (用于 owner 检查)"""
        table = self._TABLE_MAP.get(bo_id, f'{bo_id}s')
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    f'SELECT * FROM {table} WHERE id = ?',
                    [record_id],
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.OperationalError:
            return None

    def _is_owner(self, record: Dict[str, Any], user_id: int) -> bool:
        """检查用户是否是记录的 Owner

        只检查 owner_id 字段 (Spec 10: Owner = owner_id = ${user.id})。
        created_by 是普通字段, 可用于 include 条件但不触发 Owner 优先级。
        """
        owner_id = record.get('owner_id')
        if owner_id is not None and owner_id == user_id:
            return True
        return False
