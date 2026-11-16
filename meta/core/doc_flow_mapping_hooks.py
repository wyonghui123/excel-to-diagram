# -*- coding: utf-8 -*-
"""单据流映射三钩子（M4）：condition / transform / lookup_ref。

依据: docs/specs/spec-integration-module-2026-11-15.md §5.2
  · 三钩子插在既有映射优先级链上，不新建映射引擎：
    直拷白名单 → field_map → **transform** → **lookup_ref** → target_data → 数量派生
  · `condition` 是规则级前置判定：不成立 ⇒ 整条规则不生效（不写边、不消耗池）
  · 上下文只暴露 4 个名字：``source`` / ``head`` / ``now`` / ``user``
  · 表达式一律走 ``safe_evaluate``（禁 eval / import / 属性穿透）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from meta.core.condition_evaluator import _FieldAccessor
from meta.core.safe_expr_evaluator import safe_evaluate, validate_expression

logger = logging.getLogger(__name__)

#: 字段级错误码（与导入错误同一套结构：field / code / message）
ERROR_TRANSFORM = "TRANSFORM_ERROR"
ERROR_LOOKUP_NOT_FOUND = "LOOKUP_NOT_FOUND"


class DocFlowMappingHooks:
    """映射钩子执行器（一次派生复用一个实例，码表按需缓存）。"""

    def __init__(self, platform_ds=None):
        self._ds = platform_ds
        self._lookup_cache: Dict[str, Dict[str, str]] = {}

    # ---------------------------------------------------------------- 上下文
    @staticmethod
    def build_context(source_vals: Dict[str, Any],
                      head: Optional[Dict[str, Any]] = None,
                      user: str = "",
                      now: str = "") -> Dict[str, Any]:
        """构造钩子表达式上下文（仅 source / head / now / user）。"""
        return {
            "source": _FieldAccessor(source_vals or {}),
            "head": _FieldAccessor(head or {}),
            "now": now,
            "user": user,
        }

    # ---------------------------------------------------------------- condition
    def eval_condition(self, expression: Optional[str],
                       context: Dict[str, Any]) -> bool:
        """规则前置判定；空表达式 = 恒成立。

        表达式语法错误按「不成立」处理（规则声明期已由校验器拦截）。
        """
        if not expression or not str(expression).strip():
            return True
        try:
            return bool(safe_evaluate(str(expression), dict(context)))
        except Exception as exc:  # noqa: BLE001 - 声明期已校验，运行期降级
            logger.warning("[DocFlow] condition 求值失败（按不成立处理）: %s", exc)
            return False

    # ---------------------------------------------------------------- transform
    def eval_transform(self, target_field: str, expression: Optional[str],
                       context: Dict[str, Any]) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """单字段转换：返回 ``(值, 错误)``；失败不抛出，值返回 None。"""
        if expression is None or not str(expression).strip():
            return None, None
        invalid = validate_expression(str(expression))
        if invalid:
            return None, {
                "field": target_field,
                "code": ERROR_TRANSFORM,
                "message": invalid,
            }
        try:
            return safe_evaluate(str(expression), dict(context)), None
        except Exception as exc:  # noqa: BLE001 - 字段级错误，不中断整行
            return None, {
                "field": target_field,
                "code": ERROR_TRANSFORM,
                "message": str(exc) or "转换表达式求值失败",
            }

    # ---------------------------------------------------------------- lookup
    def lookup_map(self, lookup_code: str) -> Dict[str, str]:
        """载入整张码表（进程内按实例缓存；码表是小配置表）。"""
        if lookup_code in self._lookup_cache:
            return self._lookup_cache[lookup_code]
        mapping: Dict[str, str] = {}
        if self._ds is not None and lookup_code:
            try:
                from meta.core.doc_flow_lookup_store import load_lookup_map
                mapping = load_lookup_map(self._ds, lookup_code)
            except Exception as exc:  # noqa: BLE001 - 码表缺失不阻断派生
                logger.warning("[DocFlow] 码表载入失败 %s: %s", lookup_code, exc)
                mapping = {}
        self._lookup_cache[lookup_code] = mapping
        return mapping

    def resolve_lookup(self, lookup_code: str,
                       source_value: Any) -> "str | None":
        """按码表把值转成目标值；未命中返回 None（由调用方决定是否报错）。"""
        mapping = self.lookup_map(lookup_code)
        if not mapping:
            return None
        key = "" if source_value is None else str(source_value)
        return mapping.get(key)

    def apply_lookup(self, target_field: str, lookup_code: str,
                     source_value: Any) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """单字段码表转换：未命中返回 ``(None, 错误)``，命中返回 ``(目标值, None)``。"""
        resolved = self.resolve_lookup(lookup_code, source_value)
        if resolved is None:
            return None, {
                "field": target_field,
                "code": ERROR_LOOKUP_NOT_FOUND,
                "message": "码表 %s 未找到值 %r" % (lookup_code, source_value),
            }
        return resolved, None