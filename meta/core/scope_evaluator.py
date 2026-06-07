# -*- coding: utf-8 -*-
r"""
Scope 表达式求值器（FR-009/010 真正应用）

【背景 2026-06-04】
解析 aspects.yaml 的 authorization.scope 表达式
例："visibility = 'public' OR owner_id = $user.id"

支持的语法（简化版）：
- field = value         # 字段等于 value
- field = $user.id      # 字段等于当前用户 ID
- OR, AND               # 逻辑连接符
- =, !=, <, >, <=, >=  # 比较操作符

不支持（v1.5+）：
- 函数调用（如 LENGTH()）
- 子查询
- 复杂表达式
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ScopeEvaluator:
    """Scope 表达式求值器

    用法：
        evaluator = ScopeEvaluator()
        result = evaluator.evaluate(
            scope="visibility = 'public' OR owner_id = $user.id",
            user_id=123,
            record={'visibility': 'draft', 'owner_id': 123},
        )
        # → True
    """

    def evaluate(
        self,
        scope: str,
        user_id: int,
        record: Dict[str, Any],
    ) -> bool:
        """求值 scope 表达式

        Args:
            scope: 表达式字符串
            user_id: 当前用户 ID（$user.id 替换）
            record: 记录上下文（字段值字典）

        Returns:
            bool: 表达式是否为 true
        """
        if not scope:
            return True
        try:
            # 1. 替换 $user.id 为实际用户 ID
            substituted = scope.replace('$user.id', str(user_id))
            substituted = substituted.replace('$user.name', '"current_user"')
            # 2. 解析为 AST（OR 顶层分隔）
            or_parts = self._split_top_level(substituted, ' OR ')
            for part in or_parts:
                if self._evaluate_and_expression(part.strip(), record):
                    return True
            return False
        except Exception as e:  # noqa: BLE001
            logger.error(f"Scope evaluation failed: {scope!r}, error: {e}")
            return False

    def _split_top_level(
        self, expr: str, separator: str,
    ) -> List[str]:
        """按顶层 separator 分割（不分割嵌套在引号内的）"""
        parts = []
        current = []
        in_quote = False
        quote_char = None
        i = 0
        while i < len(expr):
            ch = expr[i]
            if ch in ('"', "'") and (i == 0 or expr[i-1] != '\\'):
                if not in_quote:
                    in_quote = True
                    quote_char = ch
                elif ch == quote_char:
                    in_quote = False
                    quote_char = None
            if not in_quote and expr[i:i+len(separator)] == separator:
                parts.append(''.join(current))
                current = []
                i += len(separator)
                continue
            current.append(ch)
            i += 1
        if current:
            parts.append(''.join(current))
        return parts

    def _evaluate_and_expression(
        self, expr: str, record: Dict[str, Any],
    ) -> bool:
        """求值 AND 表达式（顶层无 OR）"""
        # 拆分 AND
        and_parts = self._split_top_level(expr, ' AND ')
        for part in and_parts:
            if not self._evaluate_single_condition(part.strip(), record):
                return False
        return True

    def _evaluate_single_condition(
        self, expr: str, record: Dict[str, Any],
    ) -> bool:
        """求值单个条件：field op value"""
        # 简化：只支持 =, !=
        for op in ('!=', '>=', '<=', '=', '>', '<'):
            # 优先匹配更长的 op
            if op in expr:
                # 找第一个 op（不在引号内）
                idx = self._find_operator(expr, op)
                if idx is None:
                    continue
                field = expr[:idx].strip()
                value_str = expr[idx+len(op):].strip()
                # 去除引号
                if (
                    (value_str.startswith('"') and value_str.endswith('"'))
                    or (value_str.startswith("'") and value_str.endswith("'"))
                ):
                    value = value_str[1:-1]
                else:
                    # 尝试转 int
                    try:
                        value = int(value_str)
                    except ValueError:
                        value = value_str
                record_value = record.get(field)
                if op == '=':
                    return record_value == value
                if op == '!=':
                    return record_value != value
                if op == '>':
                    return record_value is not None and record_value > value
                if op == '<':
                    return record_value is not None and record_value < value
                if op == '>=':
                    return record_value is not None and record_value >= value
                if op == '<=':
                    return record_value is not None and record_value <= value
        return False

    def _find_operator(
        self, expr: str, op: str,
    ) -> Optional[int]:
        """找 expr 中第一个不在引号内的 op 位置"""
        in_quote = False
        quote_char = None
        for i, ch in enumerate(expr):
            if ch in ('"', "'") and (i == 0 or expr[i-1] != '\\'):
                if not in_quote:
                    in_quote = True
                    quote_char = ch
                elif ch == quote_char:
                    in_quote = False
                    quote_char = None
            if not in_quote and expr[i:i+len(op)] == op:
                return i
        return None


_scope_evaluator_instance: Optional[ScopeEvaluator] = None


def get_scope_evaluator() -> ScopeEvaluator:
    """获取全局单例"""
    global _scope_evaluator_instance
    if _scope_evaluator_instance is None:
        _scope_evaluator_instance = ScopeEvaluator()
    return _scope_evaluator_instance
