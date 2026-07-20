# -*- coding: utf-8 -*-
"""
[MODULE] visibility_condition_mapper — Visibility → 条件表达式自动映射
[DESCRIPTION] Phase 3 P3-T5: 将 BO 的 visibility 字段值自动映射为 condition_expr,
              使 visibility 配置可统一存储到 data_permission_rules.rule_type='visibility'.
[SPEC] spec-permission-system-unification-2026-07-19 §3.18.6 / §8.3 P3-T5
[FR] FR-034

[5 种 Visibility 级别] (Spec §3.18.4)
  - public     → 1=1                            所有人可见
  - private    → owner_id = {user_id}           仅 owner 可见
  - team       → team_id IN ({user_team_ids})   团队可见
  - department → department_id = {dep_id}       部门可见
  - parent     → parent.owner_id = {user_id}    Controlled by Parent (Salesforce 语义)

[安全设计]
  - user_id / department_id 强制 int 转换, 失败时 fallback 到 1=0 (deny all)
  - team_ids 强制 list of int, 非法元素过滤
  - 未知 visibility 值走 fallback: visibility = '{value}' (含 SQL 注入字符时拒绝)

[向后兼容]
  - 保留 visibility DB 列 (Spec §3.18.5: 性能 + UI 友好 + 向后兼容)
  - 本模块仅做"配置层"映射, 不改读路径 SQL (Phase 4 PDP/PEP 时统一)
"""
import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# ============================================================================
# 常量
# ============================================================================

# Spec §3.18.4 — 5 种 visibility 级别
SUPPORTED_VISIBILITY_LEVELS = frozenset({
    'public', 'private', 'team', 'department', 'parent'
})

# 模板 (Spec §3.18.6)
# 注意: 模板使用 {user_id} / {user_team_ids} / {user_department_id} 占位符
VISIBILITY_CONDITION_MAP: Dict[str, str] = {
    'public':     '1=1',
    'private':    'owner_id = {user_id}',
    'team':       'team_id IN ({user_team_ids})',
    'department': 'department_id = {user_department_id}',
    'parent':     'parent.owner_id = {user_id}',
}

# SQL 注入危险字符 (用于未知 visibility fallback 时校验)
_DANGEROUS_CHARS = {';', '--', "'", '"', '\\', '\x00', '\n', '\r'}


# ============================================================================
# 内部辅助: 从 user 提取字段 (兼容 dict + object)
# ============================================================================

def _get_user_attr(user: Any, key: str, default: Any = None) -> Any:
    """从 user 提取属性, 兼容 dict 和 object"""
    if user is None:
        return default
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """安全转换为 int, 失败返回 default

    拒绝字符串形式 (防 SQL 注入), 仅接受 int 或可解析为 int 的字符串.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        # bool 是 int 子类, 但不接受 (避免 True→1 误用)
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        # 字符串: 仅当全是数字时转换 (防 "1; DROP TABLE" 注入)
        s = value.strip()
        if s.isdigit() or (s.startswith('-') and s[1:].isdigit()):
            try:
                return int(s)
            except ValueError:
                return default
        return default
    return default


def _safe_int_list(values: Any) -> list:
    """安全转换为 list of int, 过滤非法元素"""
    if not values:
        return []
    if not isinstance(values, (list, tuple, set)):
        return []
    result = []
    for v in values:
        iv = _safe_int(v)
        if iv is not None:
            result.append(iv)
    return result


def _sanitize_visibility_value(value: Any) -> Optional[str]:
    """清洗未知 visibility 值, 防注入

    Returns:
        清洗后的字符串 (可安全拼入 SQL) 或 None (拒绝)
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # 检查危险字符
    for dangerous in _DANGEROUS_CHARS:
        if dangerous in s:
            return None
    # 限制长度 (避免超长输入)
    if len(s) > 50:
        return None
    # 仅允许字母数字下划线
    if not all(c.isalnum() or c == '_' for c in s):
        return None
    return s


# ============================================================================
# 主接口
# ============================================================================

def generate_visibility_condition(
    visibility_value: Any,
    user: Any,
) -> str:
    """[P3-T5] 将 visibility 字段值转化为条件表达式

    Spec §3.18.6 实现.

    Args:
        visibility_value: visibility 字段值 (e.g. 'public', 'private', 'team', ...)
                          接受 str / None
        user: 用户对象, 支持以下形式:
              - dict: {'id': int, 'team_ids': list[int], 'department_id': int}
              - object: 有 .id / .team_ids / .department_id 属性
              - None: 返回安全 fallback (deny all)

    Returns:
        合法的 condition_expr 字符串, 可被 ConditionEvaluator 解析.

    Behavior:
        - 5 种支持级别: 按模板填充 user 参数
        - 未知级别: fallback to `visibility = '{value}'` (Spec §3.18.6)
        - None/空值: 返回 `1=0` (deny all, 安全默认)
        - user 参数缺失: 返回安全 fallback (1=0 或空 IN)
        - 类型错误: 强制转换, 转换失败返回 1=0
    """
    # 1. None / 空值 → 安全 fallback
    if visibility_value is None:
        logger.debug('[P3-T5] visibility_value is None → 1=0 (deny all)')
        return '1=0'

    visibility_str = str(visibility_value).strip()
    if not visibility_str:
        logger.debug('[P3-T5] visibility_value is empty → 1=0 (deny all)')
        return '1=0'

    # 2. 已知级别: 按模板填充
    if visibility_str in VISIBILITY_CONDITION_MAP:
        return _render_known_visibility(visibility_str, user)

    # 3. 未知级别: fallback to visibility = '{value}'
    sanitized = _sanitize_visibility_value(visibility_str)
    if sanitized is None:
        # 含危险字符: deny all (不拼入 SQL)
        logger.warning(
            f'[P3-T5] visibility_value contains dangerous chars: {visibility_value!r} → 1=0'
        )
        return '1=0'
    return f"visibility = '{sanitized}'"


def _render_known_visibility(level: str, user: Any) -> str:
    """渲染已知 visibility 级别的条件表达式"""
    template = VISIBILITY_CONDITION_MAP[level]

    # public: 1=1, 无需 user 参数
    if level == 'public':
        return template

    # private / parent: 需要 user_id
    if level in ('private', 'parent'):
        user_id = _safe_int(_get_user_attr(user, 'id'))
        if user_id is None:
            logger.debug(f'[P3-T5] {level}: user_id missing or invalid → 1=0')
            return '1=0'
        return template.format(user_id=user_id)

    # team: 需要 team_ids (list of int)
    if level == 'team':
        team_ids = _safe_int_list(_get_user_attr(user, 'team_ids'))
        if not team_ids:
            # 无团队 → 永远不匹配 (deny all for team scope)
            logger.debug('[P3-T5] team: user has no team_ids → team_id IN ()')
            return 'team_id IN ()'
        ids_str = ','.join(str(t) for t in team_ids)
        return template.format(user_team_ids=ids_str)

    # department: 需要 department_id
    if level == 'department':
        dep_id = _safe_int(_get_user_attr(user, 'department_id'))
        if dep_id is None:
            logger.debug('[P3-T5] department: department_id missing → 1=0')
            return '1=0'
        return template.format(user_department_id=dep_id)

    # 不应到达
    return '1=0'


def map_all_visibility_levels(user: Any) -> Dict[str, str]:
    """[P3-T5] 批量映射所有 5 种 visibility 级别

    用途: 调试 / UI 预览 / 一次性生成所有条件表达式用于审计.

    Args:
        user: 同 generate_visibility_condition 的 user 参数

    Returns:
        {'public': '1=1', 'private': 'owner_id = N', ...}
    """
    return {
        level: generate_visibility_condition(level, user)
        for level in SUPPORTED_VISIBILITY_LEVELS
    }