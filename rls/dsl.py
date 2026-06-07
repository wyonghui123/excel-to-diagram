"""
rls/dsl.py - M11 v1.4.0 DSL 解析器

基于 DataPermissionInterceptor 现有 _parse_scope_expression 扩展：
- 变量替换：$user.id / $user.company_id / $user.role
- 嵌套属性：$user.company_id 替换为 context.user_context['company_id']
- 公开 API：业务可独立调用（不依赖 DataPermissionInterceptor）
- 完整 SQL where dict 输出

用法：
    from rls.dsl import parse_condition

    # 简单替换
    parsed = parse_condition(
        "order.company_id == $user.company_id",
        user_context={'company_id': 'A'}
    )
    # 输出: [{'field': 'order.company_id', 'operator': 'eq', 'value': 'A'}]

    # 复杂条件
    parsed = parse_condition(
        "order.status == 'active' AND order.user_id == $user.id",
        user_context={'id': 5}
    )
    # 输出: [
    #   {'field': 'order.status', 'operator': 'eq', 'value': 'active'},
    #   {'field': 'order.user_id', 'operator': 'eq', 'value': '5'},
    # ]
"""
import logging
import re
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# 变量正则：$user.attr_name（attr_name 可含字母数字下划线）
_VAR_PATTERN = re.compile(r'\$user\.([a-zA-Z_][a-zA-Z0-9_]*)')


# ==================== 变量替换 ====================

def _replace_user_vars(condition: str, user_context: Optional[dict]) -> str:
    """替换 $user.* 变量

    Args:
        condition: YAML condition 字符串
        user_context: dict（如 {'id': 5, 'company_id': 'A', 'role': 'admin'}）

    Returns:
        替换后的字符串

    行为：
    1. user_context 为 None → 不替换
    2. $user.attr 在 user_context 中 → 替换为对应值的 str
    3. $user.attr 不在 user_context → 保持原样（后续解析可能抛错）
    """
    if not user_context or not isinstance(user_context, dict):
        return condition

    def _replace(match):
        attr = match.group(1)
        if attr in user_context:
            value = user_context[attr]
            return f"'{value}'" if isinstance(value, str) else str(value)
        # 缺失：保持原样
        return match.group(0)

    return _VAR_PATTERN.sub(_replace, condition)


# ==================== DSL 解析（委托给 DataPermissionInterceptor） ====================

def _do_parse_scope_expression(expr: str) -> List[dict]:
    """委托给 DataPermissionInterceptor._parse_scope_expression

    行为：
    1. 表达式包含 'OR'（不区分大小写）→ 返回 OR group（list of list）
    2. 否则返回 simple condition（list of dict）

    Returns:
        List of dict: 单条件或 OR group

    Raises:
        ImportError: DataPermissionInterceptor 不可用
        ValueError: 表达式无法解析
    """
    from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
    return DataPermissionInterceptor._parse_scope_expression(expr)


# ==================== 高层 API ====================

def _clean_parsed_value(parsed: List[dict]) -> List[dict]:
    """后处理：清理 DataPermissionInterceptor 解析器的异常输出

    修复：
    - value 带 "= " 前缀（"order.id == 5" → value="= 5"）→ 去除
    - value 带 "=" 前缀 → 去除
    """
    for item in parsed:
        if not isinstance(item, dict):
            continue
        value = item.get('value')
        if not isinstance(value, str):
            continue
        if value.startswith('= '):
            item['value'] = value[2:]
        elif value.startswith('='):
            item['value'] = value[1:].lstrip()
        # 去除外层引号（如果 value 是 "'active'" → "active"）
        if (value.startswith("'") and value.endswith("'")
                and value.count("'") == 2 and len(value) > 2):
            inner = value[1:-1]
            # 仍带 '=' 前缀的情况（如 "'= active'"）也处理
            if inner.startswith('= '):
                inner = inner[2:]
            item['value'] = inner
    return parsed


def parse_condition(
    condition: str,
    user_context: Optional[dict] = None,
) -> List[dict]:
    """解析 YAML condition 字符串 → SQL where 条件 dict list

    Args:
        condition: YAML condition（如 "user.company_id == order.company_id"）
        user_context: 用户上下文（用于 $user.* 变量替换）

    Returns:
        List[dict]: SQL where 条件
        - 单条件：[{'field': ..., 'operator': ..., 'value': ...}]
        - OR 条件：[{...}, [{...}, {...}]

    Examples:
        >>> parse_condition("order.id == 5", None)
        [{'field': 'order.id', 'operator': 'eq', 'value': '5'}]

        >>> parse_condition("order.user_id == $user.id", {'id': 5})
        [{'field': 'order.user_id', 'operator': 'eq', 'value': '5'}]

        >>> parse_condition("true", None)
        [{'field': '__rls_always_true__', 'operator': 'always', 'value': True}]
    """
    if not condition or not isinstance(condition, str):
        return []

    # 特殊值 'true'（admin/manager 角色无过滤）
    stripped = condition.strip()
    if stripped.lower() == 'true':
        return [{'field': '__rls_always_true__', 'operator': 'always', 'value': True}]
    if stripped.lower() == 'false':
        return [{'field': '__rls_always_false__', 'operator': 'always', 'value': False}]

    # Step 1: 变量替换
    resolved = _replace_user_vars(condition, user_context)

    # Step 2: 标准化 == → =（DataPermissionInterceptor 解析器不识别 ==）
    normalized = resolved.replace('==', '=')

    # Step 3: 委托解析
    try:
        result = _do_parse_scope_expression(normalized)
    except Exception as e:
        logger.warning(f"[RLS DSL] parse error: {e}（condition: {condition}）")
        return []

    # Step 4: 后处理清理
    return _clean_parsed_value(result)


def get_row_filter_parsed(
    user_role: str,
    entity: str,
    user_context: Optional[dict] = None,
    rules_dir: Optional[str] = None,
) -> List[dict]:
    """获取行级过滤规则（已解析为 SQL where 条件）

    Args:
        user_role: 角色
        entity: 实体
        user_context: 用户上下文（id / company_id / role 等）
        rules_dir: rls_rules 目录

    Returns:
        List[dict]: SQL where 条件（空 list 表示无规则）

    流程：
    1. 从 rls_rules/{entity}.yaml 读 row_filters
    2. 匹配 applies_to 含 user_role 的规则
    3. 取第一个匹配的 condition
    4. parse_condition(condition, user_context) 解析
    """
    from .loader import get_row_filters
    if not user_role.startswith('role:'):
        user_role = f'role:{user_role}'
    try:
        filters = get_row_filters(entity, user_role, rules_dir)
    except Exception as e:
        logger.warning(f"[RLS DSL] get_row_filters error: {e}")
        return []
    if not filters:
        return []
    condition = filters[0].get('condition')
    if not condition:
        return []
    return parse_condition(condition, user_context)


def is_field_reference(value: str) -> bool:
    """判断 value 是否为字段引用（如 'order.company_id'）

    字段引用特征：
    - 含 '.' 字符
    - 不以 ' 开头（字符串字面量）
    - 不是数字

    用法：
        >>> is_field_reference('order.company_id')
        True
        >>> is_field_reference('5')
        False
        >>> is_field_reference("'active'")
        False
    """
    if not isinstance(value, str):
        return False
    if value.startswith("'") or value.startswith('"'):
        return False
    if value.isdigit():
        return False
    return '.' in value
