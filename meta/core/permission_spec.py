# -*- coding: utf-8 -*-
"""
PermissionSpec（QE-M6-2026-06-v2）

[M6.5 2026-06-05] 集中式权限规则。

解决问题：
- 当前权限规则散落各 BO metadata（_apply_data_permission / FieldPolicy）
- 列级权限靠 UI hide（API 层无防护）
- 多端（API + GraphQL + BI）需要重复实现

设计：
- PermissionSpec 表达"谁能看哪些行/列"
- 跨端复用：API、GraphQL、报表、批量导出走同一规则
- 审计友好：权限决策可 trace_id 回放
- 运行时热更新：注册后立即生效（无需重启）
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FieldPolicy:
    """列级策略。"""
    visible: bool = True
    readonly: bool = False
    hidden_in_api: bool = False  # API 响应中隐藏
    mask: Optional[str] = None  # 脱敏：'last4' / 'email' / 'phone'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'visible': self.visible,
            'readonly': self.readonly,
            'hidden_in_api': self.hidden_in_api,
            'mask': self.mask,
        }


@dataclass
class PermissionSpec:
    """单个实体的权限规则。

    Attributes:
        entity_type: 实体类型
        row_filter: 行级过滤（返回 SQL WHERE 子句 + params）
        field_visibility: 字段级策略 {field_name: FieldPolicy}
        trace_decision: 是否 trace 权限决策（DRE 上报）
    """

    entity_type: str
    row_filter: Optional[Callable[[Any], tuple]] = None  # (where_sql, params)
    field_visibility: Dict[str, FieldPolicy] = field(default_factory=dict)
    trace_decision: bool = True

    def apply_row_filter(
        self,
        base_where_sql: str,
        base_params: List[Any],
        context: Any = None,
    ) -> tuple:
        """应用行级过滤。

        Returns:
            (new_where_sql, new_params)
        """
        if not self.row_filter or not context:
            return base_where_sql, base_params
        try:
            extra_where, extra_params = self.row_filter(context)
            if extra_where:
                if base_where_sql:
                    new_where = f"{base_where_sql} AND ({extra_where})"
                else:
                    new_where = extra_where
                return new_where, base_params + list(extra_params)
        except Exception as e:
            logger.error(
                f"[PermissionSpec.M6.5] row_filter failed for {self.entity_type}: {e}"
            )
        return base_where_sql, base_params

    def apply_field_visibility(
        self,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """应用列级策略（hidden / mask）。

        Returns:
            处理后的 items（in-place modify + return）
        """
        if not self.field_visibility or not items:
            return items
        for item in items:
            for field_name, policy in self.field_visibility.items():
                if field_name not in item:
                    continue
                if policy.hidden_in_api:
                    # API 响应中隐藏
                    item.pop(field_name, None)
                elif policy.mask:
                    item[field_name] = self._apply_mask(
                        item[field_name], policy.mask
                    )
        return items

    def _apply_mask(self, value: Any, mask_type: str) -> Any:
        """脱敏。"""
        if value is None or not isinstance(value, str):
            return value
        if mask_type == 'last4':
            return f'****{value[-4:]}' if len(value) > 4 else '****'
        if mask_type == 'email':
            if '@' in value:
                local, domain = value.split('@', 1)
                return f'{local[0]}***@{domain}' if local else f'***@{domain}'
        if mask_type == 'phone':
            return f'{value[:3]}****{value[-4:]}' if len(value) > 7 else '****'
        return value

    def trace(self, context: Any, decision: Dict[str, Any]) -> None:
        """DRE 上报权限决策。"""
        if not self.trace_decision:
            return
        logger.info(
            f"[PermissionSpec.M6.5] entity={self.entity_type} "
            f"user={getattr(context, 'user_id', '?')} "
            f"decision={decision}"
        )


class PermissionRegistry:
    """全局权限规则注册中心。"""

    def __init__(self):
        self._specs: Dict[str, PermissionSpec] = {}

    def register(self, spec: PermissionSpec) -> None:
        self._specs[spec.entity_type] = spec
        logger.info(
            f"[PermissionRegistry.M6.5] registered {spec.entity_type}: "
            f"row_filter={'yes' if spec.row_filter else 'no'}, "
            f"fields={len(spec.field_visibility)}"
        )

    def unregister(self, entity_type: str) -> None:
        self._specs.pop(entity_type, None)

    def get(self, entity_type: str) -> Optional[PermissionSpec]:
        return self._specs.get(entity_type)

    def stats(self) -> Dict[str, Any]:
        return {
            'registered_entities': len(self._specs),
        }


_default_registry: Optional[PermissionRegistry] = None


def get_permission_registry() -> PermissionRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = PermissionRegistry()
    return _default_registry
