# -*- coding: utf-8 -*-
"""
FieldValueProvider Registry (QE-2026-06-v2)

可插拔的"字段值提供器"注册表。

设计目标：
- 允许在不改 Facade / QueryBuilder 的情况下，扩展新的字段处理逻辑
- 用于 computed count / virtual field / rule chain 派生字段

v3 SSOT 复用：
- ComputedCountFieldProvider  → RedundancyRegistry 解析 *_count 字段
- AuditVirtualFieldProvider   → VirtualFieldTransform 解析审计虚拟字段
- RedundancyVirtualFieldProvider → RedundancyRegistry 解析 redundancy/enum_type_ref
- RuleChainFieldProvider      → SafeExpressionEvaluator 执行规则链

约束：
- 不重新实现 SQL 构造（FR-006）
- 不与 v3 EnrichmentEngine 重复（TC-7）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class FieldValueProvider(Protocol):
    """字段值提供器接口。

    实现类必须提供 matches() 和 postprocess() 两个方法。
    """

    def matches(self, meta: Any, field_name: str) -> bool:
        """是否处理该字段。"""
        ...

    def postprocess(self, records: List[Dict[str, Any]], field_name: str, data_source: Any) -> None:
        """对记录列表进行原地后处理（如批量填充计算字段）。"""
        ...


class FieldValueProviderRegistry:
    """FieldValueProvider 注册表（按注册顺序匹配）。"""

    def __init__(self):
        self._providers: List[FieldValueProvider] = []

    def register(self, provider: FieldValueProvider) -> 'FieldValueProviderRegistry':
        """注册 provider。返回 self 便于链式调用。"""
        self._providers.append(provider)
        return self

    def for_field(self, meta: Any, field_name: str) -> Optional[FieldValueProvider]:
        """返回第一个匹配该字段的 provider。"""
        for p in self._providers:
            try:
                if p.matches(meta, field_name):
                    return p
            except Exception as e:
                logger.warning(f"[FieldValueProvider] {type(p).__name__}.matches() failed: {e}")
        return None

    def run_postprocess(
        self,
        meta: Any,
        records: List[Dict[str, Any]],
        data_source: Any,
        field_names: Optional[List[str]] = None,
    ) -> None:
        """对记录列表运行所有匹配的 postprocess。

        Args:
            meta: 元数据对象
            records: 记录列表（原地修改）
            data_source: 数据源
            field_names: 要处理的字段名列表（None = 所有记录中的字段）
        """
        if not records:
            return
        # 收集要处理的字段名
        if field_names is None:
            field_names = set()
            for rec in records:
                field_names.update(rec.keys())
        for fname in field_names:
            provider = self.for_field(meta, fname)
            if provider is None:
                continue
            try:
                provider.postprocess(records, fname, data_source)
            except Exception as e:
                logger.warning(
                    f"[FieldValueProvider] {type(provider).__name__}.postprocess("
                    f"field={fname}) failed: {e}"
                )


# ============================================================
# v3 SSOT Provider 实现
# ============================================================

class ComputedCountFieldProvider:
    """`*_count` 计算字段 → 用 RedundancyRegistry 解析 through 表。"""

    def __init__(self, registry: Any):
        self.reg = registry

    def matches(self, meta: Any, field_name: str) -> bool:
        # 任何以 `_count` 结尾的字段都可能是 computed count
        return field_name.endswith('_count')

    def postprocess(self, records: List[Dict[str, Any]], field_name: str, data_source: Any) -> None:
        """批量填充 *_count 字段（依赖 v3 EnrichmentEngine）。"""
        # 注：v3 EnrichmentEngine.enrich_batch 已经处理了 *_count 字段
        # 这里作为钩子，预留给需要独立 Provider 的场景
        # 留空 → EnrichmentEngine 在 Facade 流程中处理


class AuditVirtualFieldProvider:
    """updated_at / created_at / created_by / updated_by 虚拟字段。"""

    AUDIT_FIELDS = {'updated_at', 'created_at', 'created_by', 'updated_by'}

    def __init__(self, transform_engine: Any = None):
        self.tx = transform_engine

    def matches(self, meta: Any, field_name: str) -> bool:
        return field_name in self.AUDIT_FIELDS

    def postprocess(self, records: List[Dict[str, Any]], field_name: str, data_source: Any) -> None:
        # v3 已经通过 audit_aspect 注入 created_at/updated_at 物理列
        # 留空 → 无需额外处理
        pass


class RedundancyVirtualFieldProvider:
    """semantics.redundancy / semantics.enum_type_ref 冗余字段。"""

    def __init__(self, registry: Any):
        self.reg = registry

    def matches(self, meta: Any, field_name: str) -> bool:
        if not meta or not hasattr(meta, 'fields_map'):
            return False
        field_def = meta.fields_map.get(field_name)
        if not field_def:
            return False
        semantics = getattr(field_def, 'semantics', None)
        if not semantics:
            return False
        return bool(getattr(semantics, 'redundancy', None) or
                    getattr(semantics, 'enum_type_ref', None))

    def postprocess(self, records: List[Dict[str, Any]], field_name: str, data_source: Any) -> None:
        # v3 EnrichmentEngine.enrich_batch 已经处理
        pass


class RuleChainFieldProvider:
    """规则链派生字段（计算字段 + 规则链扩展点）。"""

    def __init__(self, evaluator: Any = None):
        self.ev = evaluator

    def matches(self, meta: Any, field_name: str) -> bool:
        if not meta or not hasattr(meta, 'fields_map'):
            return False
        field_def = meta.fields_map.get(field_name)
        if not field_def:
            return False
        semantics = getattr(field_def, 'semantics', None)
        if not semantics:
            return False
        # 规则链字段在 semantics.rule_chain 或 semantics.formula 中声明
        return bool(getattr(semantics, 'rule_chain', None) or
                    getattr(semantics, 'formula', None))

    def postprocess(self, records: List[Dict[str, Any]], field_name: str, data_source: Any) -> None:
        """用 SafeExpressionEvaluator 批量计算规则链字段。

        v3 已有 SafeExpressionEvaluator / ComputationExecutor
        这里委托给它们，不重新实现。
        """
        if not self.ev:
            return
        # 简化实现：从 records 上下文计算
        # 实际场景下，由 ComputationExecutor 接管
        # 留作扩展点
        pass


# ============================================================
# 默认注册表
# ============================================================

def build_default_registry(
    redundancy_reg: Any = None,
    transform_engine: Any = None,
    evaluator: Any = None,
) -> FieldValueProviderRegistry:
    """构造默认 FieldValueProvider 注册表。"""
    reg = FieldValueProviderRegistry()
    if redundancy_reg:
        reg.register(ComputedCountFieldProvider(redundancy_reg))
        reg.register(RedundancyVirtualFieldProvider(redundancy_reg))
    reg.register(AuditVirtualFieldProvider(transform_engine))
    if evaluator:
        reg.register(RuleChainFieldProvider(evaluator))
    return reg
