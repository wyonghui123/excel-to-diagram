# -*- coding: utf-8 -*-
"""
状态转换 side_effects 执行器（单一实现，flat 与 chain 共用）

YAML 声明（change_event.yaml / audit_log.yaml）：

    side_effects:
      - type: set_field
        target: delivered_at
        value: "NOW()"

判据只来自 YAML 声明，本模块不写任何业务分支。支持的白名单表达式：

- ``NOW()``            → 执行时刻的 ``datetime.now()``
- ``<field> + <数字>``  → 当前值加数字（``-`` 同理；当前值为 None 时按 0 处理）
- 空字符串             → 字面量空串
- 其它不含 ``()+-*/`` 的字符串 → 字面量字符串
- 非字符串（YAML 已解析出的 int/float/bool/None）→ 原样字面量

**不使用 eval**；非法表达式在 reload 阶段即抛
``SideEffectDeclarationError``，避免脏数据静默写入。
"""

import ast
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# 当前唯一支持的副作用类型；新增类型须同时在执行器里实现语义
SUPPORTED_TYPES = ("set_field",)

_NOW_EXPR = "NOW()"
_ARITHMETIC = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*([+-])\s*(\d+(?:\.\d+)?)$")
_SIGNED_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

# 剩余字符串若含这些字符，视为「像表达式的非法写法」而不是字面量
_EXPR_CHARS = set("()+-*/")


class SideEffectDeclarationError(ValueError):
    """side_effects 声明非法（reload 阶段即失败）"""


def _attr(item: Any, name: str, default: Any = None) -> Any:
    """同时兼容 dataclass（StateTransitionSideEffect）与原始 dict"""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def compile_side_effect_value(value: Any, where: str = "") -> Callable[[Callable[[str], Any]], Any]:
    """把声明值编译成 ``fn(get_field) -> value``；非法表达式立即抛错"""
    if not isinstance(value, str):
        return lambda get_field: value

    expr = value.strip()
    if expr == "":
        return lambda get_field: ""
    if expr == _NOW_EXPR:
        return lambda get_field: datetime.now()

    m = _ARITHMETIC.match(expr)
    if m:
        field_name, op, number = m.group(1), m.group(2), m.group(3)
        delta = float(number) if "." in number else int(number)

        def _compute(get_field: Callable[[str], Any],
                     _field: str = field_name,
                     _op: str = op,
                     _delta: Any = delta) -> Any:
            base = get_field(_field)
            if base is None:
                base = 0
            if not isinstance(base, (int, float)) or isinstance(base, bool):
                raise SideEffectDeclarationError(
                    f"{where} 字段 '{_field}' 当前值 {base!r} 不是数字，无法做 {_op} 运算".strip()
                )
            return base + _delta if _op == "+" else base - _delta

        return _compute

    # 带符号的数字字面量（如 "-5"）
    if _SIGNED_NUMBER.match(expr):
        return lambda get_field, _v=ast.literal_eval(expr): _v

    # 纯字面量（数字 / True / False / None 等）；字符串字面量允许 YAML 内的
    # 裸文本（如 "已完成"），但含运算符或括号的写法一律视为非法表达式。
    if not (_EXPR_CHARS & set(expr)):
        try:
            literal = ast.literal_eval(expr)
        except (ValueError, SyntaxError):
            return lambda get_field, _v=expr: _v
        return lambda get_field, _v=literal: _v

    raise SideEffectDeclarationError(
        "{0} 非法副作用表达式: {1!r}（仅支持 NOW()、<field> +/- 数字、字面量）".format(where, value).strip()
    )


def evaluate_side_effect_value(value: Any, get_field: Callable[[str], Any]) -> Any:
    """单次求值（供测试/单点调用；批量用 apply_state_side_effects）"""
    return compile_side_effect_value(value)(get_field)


def validate_side_effects(side_effects: Optional[Iterable[Any]], where: str = "") -> int:
    """校验一组声明，返回声明条数；非法即抛 SideEffectDeclarationError"""
    count = 0
    for index, se in enumerate(side_effects or []):
        label = f"{where} side_effects[{index}]" if where else f"side_effects[{index}]"
        se_type = _attr(se, "type") or ""
        if se_type not in SUPPORTED_TYPES:
            raise SideEffectDeclarationError(
                f"{label}: 不支持的副作用类型 {se_type!r}（仅支持 {', '.join(SUPPORTED_TYPES)}）"
            )
        if not (_attr(se, "target") or ""):
            raise SideEffectDeclarationError(f"{label}: set_field 缺少 target")
        compile_side_effect_value(_attr(se, "value"), where=label)
        count += 1
    return count


def apply_state_side_effects(
    rule: Any,
    get_field: Callable[[str], Any],
    set_field: Callable[[str, Any], None],
    valid_fields: Optional[Set[str]] = None,
) -> List[Tuple[str, Any, Any]]:
    """
    在「状态字段落库的同一位置」应用 side_effects。

    返回 ``[(target, old_value, new_value), ...]``，供调用方登记变更（审计）。

    ``valid_fields`` 非空时，声明了对象不存在的字段会跳过并告警（避免写坏 SQL）。
    """
    applied: List[Tuple[str, Any, Any]] = []
    for index, se in enumerate(getattr(rule, "side_effects", None) or []):
        se_type = _attr(se, "type") or ""
        target = _attr(se, "target") or ""
        if se_type not in SUPPORTED_TYPES or not target:
            raise SideEffectDeclarationError(
                f"rule '{getattr(rule, 'id', '?')}' side_effects[{index}]: 非法声明"
            )
        if valid_fields is not None and target not in valid_fields:
            logger.warning(
                "[SideEffects] rule=%s target='%s' 不在对象字段中，已跳过",
                getattr(rule, "id", "?"), target,
            )
            continue
        old_value = get_field(target)
        new_value = compile_side_effect_value(_attr(se, "value"))(get_field)
        set_field(target, new_value)
        applied.append((target, old_value, new_value))
    return applied


def validate_schema_dir_side_effects(schema_dir: str, include_plain_text: bool = False) -> Dict[str, Any]:
    """
    reload 前置校验：扫描 schema 目录里所有声明了 side_effects 的 rules。

    返回 ``{"files": n, "declarations": m}``；发现非法声明即抛错，此时
    registry 尚未 reload，内存中的元模型保持旧状态。
    """
    files = 0
    declarations = 0
    for path in sorted(Path(schema_dir).glob("*.yaml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not include_plain_text and "side_effects" not in text:
            continue
        try:
            import yaml
            doc = yaml.safe_load(text) or {}
        except Exception as exc:  # YAML 语法错误交由 loader 报，不在此吞掉
            raise SideEffectDeclarationError(f"{path.name}: YAML 解析失败: {exc}")
        rules = doc.get("rules") if isinstance(doc, dict) else None
        if not isinstance(rules, list):
            continue
        files += 1
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            declarations += validate_side_effects(
                rule.get("side_effects"), where=f"{path.name}#{rule.get('id', '?')}"
            )
    return {"files": files, "declarations": declarations}
