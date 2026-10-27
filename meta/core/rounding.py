# -*- coding: utf-8 -*-
"""舍入方式（rounding）—— 平台级单一映射源

依据:
  D 项（SO 域扩展 · 舍入字段统一）
  docs/superpowers/specs/2026-10-27-sales-order-business-type-and-rounding-spec.md
    FR-003 / FR-004 / FR-009 / FR-010 / NFR-001

【为什么要这个模块】
  平台内 5 处业务对象各自带一个舍入字段（allocation_rule.rounding /
  allocation_result.rounding / rate_type.rounding / pricing_period.rounding /
  tax_code.rounding），本模块提供**唯一**的「取值域 → 具体算法」映射，
  避免每处各写一份 if/elif 导致口径漂移。

【精度 vs 方向】
  - 精度（保留几位小数）：唯一真源 = `currency.decimal_places`，**不在本模块**。
  - 方向（怎么舍）：唯一真源 = 平台字典 `rounding_mode`（4 值），本模块是它的
    代码侧映射。

【取值域】
  none / round / ceil / floor —— 与平台字典 `rounding_mode` 逐值一致。
  字典是动态真源；本模块的 ROUNDING_MODES 是代码侧的**静态镜像**，由
  `meta/tests/test_rounding_unification.py` 断言两者一致（防止字典改了代码没改）。
"""
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
)

#: 舍入方式取值域（与平台字典 rounding_mode 一致）
ROUNDING_MODES = frozenset({'none', 'round', 'ceil', 'floor'})

#: 取值 → decimal rounding 常量。
#: none / round 均映射为 ROUND_HALF_UP —— 这是历史行为（allocation_service.plan()
#: 中 `none` 与 `round` 等价，见其 L145-149 注释），本模块保持不变以确保零回归。
#: `none` 与 `round` 的语义差异（是否显式声明）体现在配置层，不体现在算法层。
ROUNDING_TO_DECIMAL = {
    'none': ROUND_HALF_UP,
    'round': ROUND_HALF_UP,
    'ceil': ROUND_CEILING,
    'floor': ROUND_FLOOR,
}


def resolve_rounding_mode(value, default='round'):
    """把配置里的舍入方式解析为 decimal rounding 常量。

    非法值处理：返回 `default` 对应的常量，**不抛错** —— 运行侧容错口径统一为
    「回落默认 + 由调用方记 WARNING」（Spec FR-009 / NFR-003）。
    本函数**不记日志**（core 层无 logger 依赖），日志由调用方补。

    Args:
        value: 配置值（none/round/ceil/floor）；None / '' 视为未配置
        default: 非法值 / 未配置时的回落目标（默认 'round'）

    Returns:
        decimal 的 rounding 常量（ROUND_HALF_UP / ROUND_CEILING / ROUND_FLOOR）
    """
    if value in (None, ''):
        value = default
    key = str(value).strip().lower()
    return ROUNDING_TO_DECIMAL.get(key, ROUNDING_TO_DECIMAL.get(default, ROUND_HALF_UP))


def is_valid_rounding_mode(value) -> bool:
    """取值是否在四值域内（用于「非法值必须报错」的严格场景，如定价取整）。"""
    return str(value or '').strip().lower() in ROUNDING_MODES


def round_by_mode(value, decimals: int, mode) -> Decimal:
    """按指定舍入方向把数值舍入到 `decimals` 位。

    Args:
        value: 待舍入的数值（Decimal / int / str）
        decimals: 保留位数（精度来源 = currency.decimal_places）
        mode: 舍入方式（none/round/ceil/floor）

    Returns:
        舍入后的 Decimal
    """
    if isinstance(value, Decimal):
        dec = value
    else:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError):
            dec = Decimal('0')
    q = Decimal(1).scaleb(-int(decimals))
    return dec.quantize(q, rounding=resolve_rounding_mode(mode))
