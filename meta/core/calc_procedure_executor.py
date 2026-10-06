# -*- coding: utf-8 -*-
"""
计算过程执行器（Calculation Procedure Executor）— 定价引擎 T2-2
================================================================

实现 Spec FR-005（可配置计算序列 + 可插拔算子）与 FR-006（计算基一等对象）。

[C5 硬约束 · 步骤须带类型]
  `element_type` 决定用哪个算子，**禁止 if-else 硬编码分支**（D7 / FR-005 AC）。
  故本模块用**注册表**（registry）而非条件链：新增算子 = 注册一个函数，
  **不改引擎**。这是"可插拔"的落地形式，也是 C5 的唯一合规实现。

[职责边界]
  本模块负责：按 seq 逐步执行、每步有条件地更新内存中间结果、记录小计、算基四字段。
  本模块**不管**：费率怎么查（FR-004 → `meta/core/lookup_resolver.py`）、
  结果落哪张单据（FR-011，受阻于 order_line）。

[T2 前提 · 纯函数]
  零外部依赖：不查库、不读 BO、不依赖 order_line、不依赖主数据。
  输入 = 过程定义（list[dict]）+ 单据行上下文（dict）+ 基数（float）。
  输出 = 内存结果对象（可回放，供 FR-010 落 calc_detail）。

[FR-006 互斥校验]
  `rolling = true` 与 `base_step` **互斥**——滚动时不指定具体前序步骤
  （对标 Oracle Running Net Price 是单一累加器对象）。
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 计算基来源（FR-006 轴① · 通用化轴①）
BASE_PRICING_QUANTITY = "pricing_quantity"   # 定价数量（默认）
BASE_ACTIVITY_QUANTITY = "activity_quantity"  # 活动量：燃料/电量/工时（碳与作业成本）
BASE_VALUE = "value"
BASE_WEIGHT = "weight"
BASE_VOLUME = "volume"
BASE_ENERGY = "energy"
BASE_HOURS = "hours"
BASE_ATTRIBUTE = "attribute"
BASE_FORMULA = "formula"

# 结果语义（FR-005 · 通用化轴③）
RESULT_PRICE = "price"
RESULT_COST = "cost"
RESULT_EMISSION = "emission"
RESULT_TAX = "tax"
RESULT_HOURS = "hours"
RESULT_QUANTITY = "quantity"


class CalculationError(Exception):
    """计算过程失败（FR-006 互斥校验等结构性错误）。

    与 `ResolutionError`（FR-008 消解失败）**并列且不互相兜底**——
    两者语义不同：前者是"配置本身矛盾"，后者是"候选消解失败"。
    """


# ---------------------------------------------------------------------------
# 算子上下文 / 结果
# ---------------------------------------------------------------------------
@dataclass
class StepContext:
    """单个步骤的执行上下文（内存态）。

    `state` 是**跨步骤共享的中间结果**（对标 Oracle Pricing Algorithm
    逐步更新的内存 SDO）。算子只能通过它读写，不碰外部。
    """

    state: Dict[str, Any] = field(default_factory=dict)
    base: float = 0.0
    running_net_amount: float = 0.0
    trace: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StepResult:
    """单步结果（可回放一条，对标 calc_detail 的一行）。"""

    seq: int
    element_type: str
    rate_type: Optional[str]
    amount: float = 0.0
    skipped: bool = False
    skip_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "element_type": self.element_type,
            "rate_type": self.rate_type,
            "amount": self.amount,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


# ---------------------------------------------------------------------------
# 算子注册表（C5 的落地形式：新增算子 = 注册，不改引擎）
# ---------------------------------------------------------------------------
Operator = Callable[[StepContext, Dict[str, Any]], float]
OPERATORS: Dict[str, Operator] = {}

# 只读算子：只读 state / 净额，**不改金额**（返回 0.0）。
# 它们在累加之后补跑一次，以便读到"含本步"的 running_net_amount。
_READONLY_OPS = {"round", "aggregate", "derived", "track"}


def register_operator(element_type: str):
    """算子注册装饰器。`element_type` 重复注册会报错（防静默覆盖）。"""

    def deco(fn: Operator) -> Operator:
        if element_type in OPERATORS:
            raise CalculationError(f"算子已注册，不可覆盖：{element_type}")
        OPERATORS[element_type] = fn
        return fn

    return deco


def registered_operators() -> List[str]:
    return sorted(OPERATORS)


# ---------------------------------------------------------------------------
# 算子实现
# ---------------------------------------------------------------------------
@register_operator("list_price")
def _op_list_price(ctx: StepContext, params: Dict[str, Any]) -> float:
    """取价：直接用给定费率（由 FR-004 查表结果喂入 params['rate']）。"""
    rate = float(params.get("rate", 0.0) or 0.0)
    amount = rate * ctx.base
    ctx.state["list_price"] = amount
    return amount


@register_operator("tier")
def _op_tier(ctx: StepContext, params: Dict[str, Any]) -> float:
    """阶梯：按 params['tiers']（[{from,to,rate}]）选档。

    两语义（FR-005 / T0-7 `scale_semantic`）：
      total       = 整单取档（总量落在哪档取哪档的费率）
      incremental = 逐档累进（分段计算后累加）
    """
    tiers = params.get("tiers") or []
    qty = float(params.get("quantity", ctx.base) or 0.0)
    semantic = params.get("semantic", "total")

    if not tiers:
        return 0.0

    if semantic == "incremental":
        total = 0.0
        for t in tiers:
            lo, hi = float(t.get("from", 0)), float(t.get("to", float("inf")))
            seg = max(0.0, min(qty, hi) - lo)      # 区间含下不含上
            total += seg * float(t.get("rate", 0.0) or 0.0)
        amount = total
    else:
        hit = None
        for t in tiers:
            lo, hi = float(t.get("from", 0)), float(t.get("to", float("inf")))
            if lo <= qty < hi:
                hit = float(t.get("rate", 0.0) or 0.0)
                break
        amount = (hit or 0.0) * qty

    ctx.state["tier"] = amount
    return amount


@register_operator("attribute")
def _op_attribute(ctx: StepContext, params: Dict[str, Any]) -> float:
    """属性：按基数比例取属性值（如按重量的每吨属性费率）。"""
    attr = float(params.get("value", 0.0) or 0.0)
    divisor = float(params.get("divisor", 1.0) or 1.0)
    amount = attr * (ctx.base / divisor) if divisor else 0.0
    ctx.state["attribute"] = amount
    return amount


@register_operator("formula")
def _op_formula(ctx: StepContext, params: Dict[str, Any]) -> float:
    """公式：仅允许白名单算子（FR-005 安全要求，对标 NFR-002 AST 白名单）。

    本期只支持四则 + 括号 + 变量引用，**不用 eval**——
    变量名限定在 state 白名单内，杜绝任意代码执行。
    """
    expr = params.get("expr")
    if not expr:
        raise CalculationError("formula 算子缺少 expr")
    amount = _safe_eval(expr, {**ctx.state, "base": ctx.base,
                              "running_net_amount": ctx.running_net_amount})
    ctx.state["formula"] = amount
    return amount


@register_operator("round")
def _op_round(ctx: StepContext, params: Dict[str, Any]) -> float:
    """取整：按 rate_type.rounding 对当前累计值取整。

    [设计要点] 取整算子返回 **0.0** —— 它只**改 state['rounded']**（展示/入账值），
    **不参与累加**。否则会双重计入：净额已经含未取整值，再加一次取整差。
    对标 Oracle：取整发生在结果呈现层，不是累加器层。
    """
    mode = params.get("mode", "none")
    value = float(params.get("value", ctx.running_net_amount) or 0.0)
    digits = int(params.get("digits", 0) or 0)
    if mode == "round":
        import decimal
        q = decimal.Decimal(1).scaleb(-digits)
        out = float(decimal.Decimal(str(value)).quantize(
            q, rounding=decimal.ROUND_HALF_UP))
    elif mode == "ceil":
        out = float(__import__("math").ceil(value * 10 ** digits) / 10 ** digits)
    elif mode == "floor":
        out = float(__import__("math").floor(value * 10 ** digits) / 10 ** digits)
    else:
        out = value
    ctx.state["rounded"] = out
    return 0.0        # 不累加


@register_operator("aggregate")
def _op_aggregate(ctx: StepContext, params: Dict[str, Any]) -> float:
    """聚合：对已有中间结果做 sum / avg / min / max。

    `source` 可为 "running_net_amount"（对已累加净额做聚合）或 state 中的
    **列表**字段（需显式列出多个来源名，如 ["a","b","c"]）。
    """
    op = params.get("op", "sum")
    source = params.get("source")
    sources = params.get("sources")

    if sources:
        vals = []
        for s in sources:
            if s not in ctx.state:
                raise CalculationError(f"aggregate 源不存在：{s}")
            vals.append(ctx.state[s])
    elif source == "running_net_amount":
        # 注意：此刻 running_net_amount **尚未含本步 amount**（累加在算子返回之后）。
        # 故对净额做聚合时必须用「当前净额 + 本步产出」。
        vals = [ctx.running_net_amount]
    elif source and source in ctx.state:
        v = ctx.state[source]
        vals = v if isinstance(v, (list, tuple)) else [v]
    else:
        raise CalculationError(f"aggregate 源不存在：{source}")

    if not vals:
        raise CalculationError("aggregate 无可用值")

    if op == "sum":
        out = float(sum(vals))
    elif op == "avg":
        out = float(sum(vals)) / len(vals)
    elif op == "min":
        out = float(min(vals))
    elif op == "max":
        out = float(max(vals))
    else:
        raise CalculationError(f"未知聚合方式：{op}")

    key = f"aggregate_{source or 'multi'}"
    ctx.state[key] = out
    ctx.state["aggregate"] = out
    return 0.0        # 聚合是只读操作，不累加


@register_operator("derived")
def _op_derived(ctx: StepContext, params: Dict[str, Any]) -> float:
    """派生：引用前序步骤结果（base_step），**只读不累加**。"""
    source = params.get("source")
    if not source or source not in ctx.state:
        raise CalculationError(f"derived 源不存在：{source}")
    out = float(ctx.state[source])
    ctx.state["derived"] = out
    return 0.0


@register_operator("manual")
def _op_manual(ctx: StepContext, params: Dict[str, Any]) -> float:
    """手工：取单据上手工填入的值（对标 rate_type.manual_allowed）。"""
    out = float(params.get("value", 0.0) or 0.0)
    ctx.state["manual"] = out
    return out


@register_operator("track")
def _op_track(ctx: StepContext, params: Dict[str, Any]) -> float:
    """跟踪：只记录，不改金额（对标 SAP 把中间值写入统计字段）。

    返回 0.0 —— **不改净额**。可跟 `label` 记录多个跟踪值，供 aggregate 汇总。
    """
    value = params.get("value", 0.0)
    label = params.get("label")
    if label:
        tracked = ctx.state.setdefault("tracked_values", [])
        tracked.append(value)
        ctx.state[label] = value
    else:
        ctx.state["tracked"] = value
    return 0.0


@register_operator("quality_premium")
def _op_quality_premium(ctx: StepContext, params: Dict[str, Any]) -> float:
    """质量溢价（FR-015 预留）：按 quality_level 映射溢价率。

    本期仅落骨架 + 可复现的线性映射，**不接质检取数**
    （质检是主数据模块职责，见 TR-002 责任方划分）。
    """
    level = float(params.get("quality_level", 0.0) or 0.0)
    rate = float(params.get("premium_rate", 0.0) or 0.0)
    out = level * rate * ctx.base
    ctx.state["quality_premium"] = out
    return out


_SAFE_CHARS = set("0123456789.+-*/() \t")


def _safe_eval(expr: str, variables: Dict[str, Any]) -> float:
    """受限表达式求值 —— **不使用 eval**（NFR-002 禁止 eval）。

    做法：白名单字符过滤 + 用 ast.parse 以 BinOp/Num/Name 白名单解析，
    变量名只能取自传入的 state 白名单。
    """
    import ast

    bad = set(expr) - _SAFE_CHARS - set("abcdefghijklmnopqrstuvwxyz_")
    if bad:
        raise CalculationError(f"表达式含非法字符：{sorted(bad)}")
    tree = ast.parse(expr, mode="eval")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise CalculationError("只支持数值常量")
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise CalculationError(f"变量不在白名单：{node.id}")
            v = variables[node.id]
            if not isinstance(v, (int, float)):
                raise CalculationError(f"变量非数值：{node.id}")
            return float(v)
        if isinstance(node, ast.BinOp):
            l, r = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return l + r
            if isinstance(node.op, ast.Sub):
                return l - r
            if isinstance(node.op, ast.Mult):
                return l * r
            if isinstance(node.op, ast.Div):
                if r == 0:
                    raise CalculationError("除零")
                return l / r
            raise CalculationError("仅支持四则运算")
        raise CalculationError(f"不支持的语法节点：{type(node).__name__}")

    return ev(tree)


# ---------------------------------------------------------------------------
# 执行器
# ---------------------------------------------------------------------------
def execute(
    steps: List[Dict[str, Any]],
    base: float = 0.0,
    initial_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """执行计算过程 —— FR-005 / FR-007。

    Args:
        steps:       有序步骤 [{seq, element_type, rate_type?, condition?, params{}}]
        base:        计算基数（由 FR-006 的 base_level/base_source 决定后传入）
        initial_state: 初始中间结果（如查表得到的候选费率）

    Returns:
        {"amount", "running_net_amount", "subtotals", "step_results"}

    Raises:
        CalculationError: 未知 element_type / rolling 与 base_step 互斥 / 公式非法
    """
    ctx = StepContext(state=dict(initial_state or {}), base=float(base or 0.0))
    step_results: List[StepResult] = []
    subtotals: Dict[str, float] = {}

    ordered = sorted(steps, key=lambda s: s["seq"])   # 步骤按 seq 升序

    for st in ordered:
        et = st.get("element_type")
        seq = st.get("seq")
        rate_type = st.get("rate_type")
        params = st.get("params") or {}

        # element_type 必须在注册表中 —— 未知类型即报错，不静默跳过
        # （C5：步骤须带类型，未注册的类型说明配置漏了算子实现）
        if et not in OPERATORS:
            raise CalculationError(
                f"未注册的 element_type：{et}（seq={seq}）"
                f"；已注册：{registered_operators()}"
            )

        # 【修 2026-10-06】控制项从**步骤顶层**读，不从 params 读。
        # rolling / base_step / subtotal_key 是"步骤怎么参与累加"的控制项，
        # 不是算子的业务参数；混在 params 里会被算子误读，也让校验易漏。
        # 为兼容两种写法，两处都接受，但顶层优先。
        rolling = st.get("rolling", params.get("rolling", False))
        base_step = st.get("base_step", params.get("base_step"))
        subtotal_key = st.get("subtotal_key", params.get("subtotal_key"))

        # FR-006 互斥校验：rolling 与 base_step 不可共存
        if rolling and base_step:
            raise CalculationError(
                f"rolling=true 与 base_step 互斥（FR-006 AC，seq={seq}）"
            )

        # 条件执行：condition 为假则跳过（FR-005「每步有条件地更新」）
        cond = st.get("condition", params.get("condition"))
        if cond is False:
            step_results.append(StepResult(
                seq=seq, element_type=et, rate_type=rate_type,
                skipped=True, skip_reason="condition_false",
            ))
            continue

        amount = OPERATORS[et](ctx, params)

        # 步骤间 additive（FR-007「不累加就算不出净价」）
        if rolling:
            ctx.running_net_amount = amount          # 滚动：直接覆盖为当前值
        else:
            ctx.running_net_amount += amount         # 累加

        if subtotal_key:
            subtotals[subtotal_key] = ctx.running_net_amount

        # 【修 2026-10-06】只读算子（round / aggregate / derived / track）在
        # **累加之后**补跑一次，使其能读到"含本步"的 running_net_amount。
        # 否则 aggregate(source="running_net_amount") 取到的是本步之前的净额
        # （实测 max 拿到 80 而非 100 —— 因最后一步是 -20 的 list_price）。
        # 这类算子返回 0.0，补跑不会重复计入金额。
        if et in _READONLY_OPS:
            OPERATORS[et](ctx, params)

        step_results.append(StepResult(
            seq=seq, element_type=et, rate_type=rate_type, amount=amount,
        ))

    return {
        "amount": ctx.running_net_amount,
        "running_net_amount": ctx.running_net_amount,
        "subtotals": subtotals,
        "step_results": [r.to_dict() for r in step_results],
        "state": ctx.state,
    }
