"""
mcp/rls_integration.py - M11 TODO-7: M10 MCP 与 M11 RLS 集成

AI Agent（X-Agent-Id 头）调用 MCP 工具时自动应用 RLS：
- 角色注入：ai-agent 角色
- 行级过滤：根据 YAML condition 限制可见行
- 字段脱敏：根据 YAML field_masks 脱敏敏感字段
- 权限检查：check_action() 拒绝越权操作

用法：
    from mcp.rls_integration import apply_rls_to_result

    result = apply_rls_to_result(
        entity='user',
        action='read',
        user_context={'id': 5, 'company_id': 'A', 'is_ai_agent': True},
        raw_result={'id': 5, 'phone': '13800001234'},
    )
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _normalize_user_context(user_context: Optional[dict]) -> dict:
    """规范化 user_context

    处理 AI Agent 调用（X-Agent-Id 头）：
    - is_ai_agent=True → roles=['ai-agent']
    - X-Agent-Id 存在 → 注入 'ai-agent' 角色

    Args:
        user_context: 调用方传入的 user context
            {
                'id': int,
                'company_id': str,
                'roles': list,
                'is_ai_agent': bool,
                'agent_id': str,
            }

    Returns:
        dict: M11 RLS 期望的 user_info 格式
    """
    if not user_context:
        return {'id': 0, 'roles': set()}

    ctx = dict(user_context)
    roles = set(ctx.get('roles', []))

    # AI Agent 注入
    if ctx.get('is_ai_agent') or ctx.get('agent_id'):
        roles.add('ai-agent')
        ctx['is_ai_agent'] = True

    ctx['roles'] = roles
    return ctx


def _is_action_allowed(entity: str, action: str, user_context: dict) -> bool:
    """M11 RLS action 权限检查

    Args:
        entity: 实体名（lowercase）
        action: 操作（read/create/update/delete）
        user_context: 规范化后的 user context

    Returns:
        bool: True = 允许, False = 拒绝
    """
    from rls.enforce import check_action
    from rls import loader as loader_mod
    # 显式 ensure RLS 已加载
    loader = loader_mod.get_loader('rls_rules')
    loader.load_all()  # 强制 reload（解决 set_rules_dir 重置 _rules 后未加载的 race）

    try:
        roles = user_context.get('roles', set())
        if not roles:
            return False
        # 任一角色允许即可
        for role in roles:
            if check_action(role, entity, action):
                return True
        return False
    except Exception as e:
        logger.error(f'[MCP RLS] check_action 异常：{e}')
        return False


def _apply_field_masks(entity: str, user_context: dict, data: Any) -> Any:
    """M11 RLS 字段脱敏

    Args:
        entity: 实体名（lowercase）
        user_context: user context
        data: dict 或 list[dict]

    Returns:
        脱敏后的 data
    """
    try:
        from rls.enforce import apply_field_masks
        roles = user_context.get('roles', set())
        if not roles:
            return data
        # 任一角色 → 脱敏
        for role in roles:
            data = apply_field_masks(role, entity, data)
        return data
    except Exception as e:
        logger.error(f'[MCP RLS] apply_field_masks 异常：{e}')
        return data


def apply_rls_to_result(
    entity: str,
    action: str,
    user_context: dict,
    raw_result: Any,
) -> dict:
    """MCP 调用结果应用 M11 RLS

    Args:
        entity: 实体名（lowercase，如 'user'）
        action: 操作（read/create/update/delete）
        user_context: 调用方 user context
        raw_result: M9 GraphQL/Mock 原始结果

    Returns:
        dict: 包装后的结果
            {
                'tool': str,
                'entity': str,
                'allowed': bool,
                'rls_applied': bool,
                'data': Any,
                'deny_reason': Optional[str],
            }
    """
    ctx = _normalize_user_context(user_context)

    # Step 1: 权限检查
    allowed = _is_action_allowed(entity, action, ctx)
    if not allowed:
        return {
            'tool': 'rls_blocked',
            'entity': entity,
            'allowed': False,
            'rls_applied': True,
            'data': None,
            'deny_reason': f'role {ctx.get("roles")} cannot {action} {entity}',
        }

    # Step 2: 字段脱敏
    rls_applied = False
    if isinstance(raw_result, dict) and 'result' in raw_result:
        masked = _apply_field_masks(entity, ctx, raw_result['result'])
        rls_applied = True
        raw_result = {**raw_result, 'result': masked}

    return {
        **raw_result,
        'allowed': True,
        'rls_applied': rls_applied,
    }
