# -*- coding: utf-8 -*-
"""
条件评估引擎

支持运行时评估业务条件表达式，用于：
- Deletability/Addability 动态 CRUD 控制
- Action Behavior 前置条件检查
- 业务规则条件判断

支持的操作符：
- 比较：==, !=, >, <, >=, <=
- 逻辑：and, or, not
- 成员：in, not in
- 字段访问：self.field, parent.field
"""

import re
from typing import Any, Dict, Optional
from meta.core.safe_expr_evaluator import safe_evaluate


class ConditionEvaluator:
    """条件评估引擎"""

    SAFE_NAMES = {
        "True": True,
        "False": False,
        "None": None,
        "true": True,
        "false": False,
        "null": None,
    }

    def __init__(self, context: Dict[str, Any] = None):
        self._context = context or {}

    def evaluate(self, condition: str, context: Dict[str, Any] = None) -> bool:
        if not condition or not condition.strip():
            return True

        ctx = dict(self._context)
        if context:
            ctx.update(context)

        try:
            eval_context = self._build_eval_context(ctx)
            result = safe_evaluate(condition, eval_context)
            return bool(result)
        except Exception:
            return False

    def evaluate_with_message(
        self,
        condition: str,
        message: str,
        context: Dict[str, Any] = None,
    ) -> tuple:
        result = self.evaluate(condition, context)
        if not result:
            return False, message
        return True, ""

    def _build_eval_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        eval_ctx = dict(self.SAFE_NAMES)

        self_obj = ctx.get("self", ctx)
        parent_obj = ctx.get("parent", {})

        if isinstance(self_obj, dict):
            accessor = _FieldAccessor(self_obj)
            eval_ctx["self"] = accessor
            for key, value in self_obj.items():
                if key not in eval_ctx:
                    if value is None and key in _FieldAccessor._NUMERIC_DEFAULTS:
                        eval_ctx[key] = _FieldAccessor._NUMERIC_DEFAULTS[key]
                    else:
                        eval_ctx[key] = value
        else:
            eval_ctx["self"] = _FieldAccessor(self_obj)

        if isinstance(parent_obj, dict):
            eval_ctx["parent"] = _FieldAccessor(parent_obj)
        else:
            eval_ctx["parent"] = _FieldAccessor(parent_obj)

        for key, value in ctx.items():
            if key not in ("self", "parent"):
                eval_ctx[key] = value

        return eval_ctx


class _FieldAccessor:
    """字段访问器，支持属性式访问字典字段"""

    _NUMERIC_DEFAULTS = {
        "count": 0,
        "relation_count": 0,
        "child_count": 0,
        "children_count": 0,
        "value_count": 0,
        "dimension_count": 0,
    }

    def __init__(self, data: Any):
        if isinstance(data, dict):
            self._data = data
        elif data is None:
            self._data = {}
        else:
            self._data = {"value": data}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        value = self._data.get(name)
        if value is None and name in self._NUMERIC_DEFAULTS:
            return self._NUMERIC_DEFAULTS[name]
        return value

    def __eq__(self, other):
        return self._data == other

    def __ne__(self, other):
        return self._data != other

    def __bool__(self):
        return bool(self._data)

    def __repr__(self):
        return repr(self._data)

    def __contains__(self, item):
        return item in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)
