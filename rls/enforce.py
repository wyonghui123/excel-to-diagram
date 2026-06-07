"""
rls/enforce.py - RLS 高层执行 API

设计哲学（基于实际代码）：
- 0 改 18 现有拦截器
- 提供"可选集成"的高层 API
- 现有拦截器可以选择调用（保持 0 风险）
- 业务代码 0 改动

3 个高层 API：
1. check_action(user_role, entity, action, rules_dir) -> bool
   替代 PermissionInterceptor 的 resource:action 检查
2. apply_row_filter(user_role, entity, conditions, rules_dir) -> Optional[condition]
   替代 DataPermissionInterceptor 的 scope 表达式
3. apply_field_masks(user_role, entity, data, rules_dir) -> masked_data
   替代 FieldPolicyInterceptor 的 mask 规则

所有函数：
- 纯函数（不修改入参）
- 优雅降级（YAML 错误时返回原值）
- 0 依赖（仅依赖 rls.loader）
"""
import logging
import re
from typing import List, Optional, Dict, Any

from .loader import get_loader, get_allowed_actions, get_field_masks, get_row_filters

logger = logging.getLogger(__name__)


# ==================== 操作权限 ====================

def check_action(
    user_role: str,
    entity: str,
    action: str,
    rules_dir: Optional[str] = None,
) -> bool:
    """检查 user_role 是否有权对 entity 执行 action

    Args:
        user_role: 角色字符串（'role:user' / 'role:admin' / 'ai-agent' / 'admin'）
        entity: 实体名（'order' / 'user' / ...）
        action: 操作（'create' / 'read' / 'update' / 'delete' / 'export' / 'list'）
        rules_dir: rls_rules 目录（None = 默认）

    Returns:
        bool: 允许执行 → True / 拒绝 → False

    兼容性：
        - 自动补全 'role:' 前缀
        - YAML 中无规则时 → 默认拒绝（fail-closed）
        - YAML 错误时 → 默认拒绝（fail-closed）

    用法（PermissionInterceptor 集成示例）：
        from rls import check_action
        if not check_action(user.role, 'order', 'create'):
            raise PermissionDenied("no permission to create order")
    """
    # 自动补全 'role:' 前缀
    if not user_role.startswith('role:'):
        user_role = f'role:{user_role}'

    try:
        allowed = get_allowed_actions(entity, user_role, rules_dir)
    except Exception as e:
        logger.warning(f"[RLS] check_action failed: {e}, defaulting to deny")
        return False  # fail-closed

    if not allowed:
        # YAML 中无规则 → 默认拒绝
        return False

    return action in allowed


# ==================== 行级过滤 ====================

def get_active_row_filter(
    user_role: str,
    entity: str,
    rules_dir: Optional[str] = None,
) -> Optional[str]:
    """获取行级过滤的 condition 字符串

    Args:
        user_role: 角色
        entity: 实体
        rules_dir: rls_rules 目录

    Returns:
        Optional[str]: 第一个匹配的 condition，无则 None

    用法（DataPermissionInterceptor 集成示例）：
        from rls import get_active_row_filter

        class DataPermissionInterceptor(Interceptor):
            def before_action(self, context):
                cond = get_active_row_filter(user.role, context.object_type)
                if cond:
                    # 用 cond 替换现有的 scope_expr
                    resolved = cond.replace('$user.id', str(context.user_id))
                    # 注入到 context.query_filters
                    context.query_filters = context.query_filters or {}
                    # 注意：实际需要 DSL 解析器，这里仅返回 condition 字符串
                    logger.debug(f"[RLS] row filter: {resolved}")
    """
    if not user_role.startswith('role:'):
        user_role = f'role:{user_role}'

    try:
        filters = get_row_filters(entity, user_role, rules_dir)
    except Exception as e:
        logger.warning(f"[RLS] get_active_row_filter failed: {e}")
        return None

    if not filters:
        return None

    # 取第一个匹配（业务可按优先级扩展）
    return filters[0].get('condition')


# ==================== 字段脱敏 ====================

# mask 格式：{} 占位符替换为字段值的后 N 位
_MASK_FORMAT_RE = re.compile(r'\{\}')

def _apply_single_mask(value: Any, mask: str) -> str:
    """应用单个 mask 规则"""
    if value is None:
        return None
    s = str(value)
    if '{}' in mask:
        # mask 格式 "***-****-{}" → 取 s 后 4 位
        return _MASK_FORMAT_RE.sub(s[-4:] if len(s) >= 4 else s, mask)
    # 普通 mask 替换
    return mask


def apply_field_masks(
    user_role: str,
    entity: str,
    data: Dict[str, Any],
    rules_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """应用字段脱敏规则到 data

    Args:
        user_role: 角色
        entity: 实体
        data: 原始数据 dict（不修改）
        rules_dir: rls_rules 目录

    Returns:
        Dict[str, Any]: 脱敏后的新 dict（原 dict 不修改）

    用法（FieldPolicyInterceptor 集成示例）：
        from rls import apply_field_masks

        class FieldPolicyInterceptor(Interceptor):
            def after_action(self, context):
                if context.result and isinstance(context.result, dict):
                    context.result = apply_field_masks(
                        user.role, context.object_type, context.result
                    )
    """
    if not isinstance(data, dict):
        return data

    if not user_role.startswith('role:'):
        user_role = f'role:{user_role}'

    try:
        masks = get_field_masks(entity, user_role, rules_dir)
    except Exception as e:
        logger.warning(f"[RLS] apply_field_masks failed: {e}")
        return data  # 失败返回原 data

    if not masks:
        return data

    # 复制 data（不修改入参）
    masked = dict(data)
    for m in masks:
        field = m.get('field')
        mask = m.get('mask')
        if field and mask and field in masked:
            masked[field] = _apply_single_mask(masked[field], mask)
    return masked


def apply_field_masks_to_list(
    user_role: str,
    entity: str,
    data_list: List[Dict[str, Any]],
    rules_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """批量应用字段脱敏（list 场景）"""
    if not isinstance(data_list, list):
        return data_list
    return [apply_field_masks(user_role, entity, item, rules_dir) for item in data_list]
