# -*- coding: utf-8 -*-
"""
查找序列引擎（Lookup Resolver）— 定价引擎 T2-1
==================================================

实现 Spec FR-004（查找序列与取数范式）与 FR-008（候选消解四范式）的**纯函数内核**。

[设计前提 · T2 批次]
  本模块**零外部依赖**：不查库、不读 BO、不依赖 order_line、不依赖主数据。
  输入是内存中的 list[dict]，输出是内存中的结果对象。
  理由：Spec §8.2 T2 的定位是"六家骨架里最难的部分，且完全不依赖 order_line"，
        且 FR-004/FR-008 的 AC 全部可用内存夹具验证（TR-006 验收矩阵即三候选夹具）。

[职责边界 · FR-004]
  本模块**只管"第几个槽位、用哪把键、命中哪一行"**：
    - 槽位次序     = lookup_sequence.steps[{seq, key_schema_id}]
    - 命中即停/累加 = rate_record.hit_policy（**下沉**，v1.6 · C-T0-4）
  本模块**不管**"怎么算"（FR-005 计算过程）、"按什么基准算"（FR-006 计算基）。

[确定性保证 · FR-004 AC]
  同 priority 候选必须有**确定 tie-break**：`priority` asc → `id` asc，
  **禁止依赖 dict/DB 的隐式返回顺序**（否则同数据两次取价结果可能不同，
  违反 Spec C4「可解释 = 可回放」）。

[回放骨架 · FR-004 AC 末条]
  每次查找都返回 `LookupTrace`，可回答"命中哪一行 / 为什么其它行被跳过"，
  供 FR-010（可解释 = 可回放）消费。本期只出结构，不落 calc_detail 表。

[阶梯 · FR-009]
  费率记录可自带档位表（`rate_record.scale`）与语义（`scale_semantic`）：
  `total` 整单取档 / `incremental` 逐档累进。
  **定档发生在"记录选定之后"**（对标 SAP：先由存取序列选中条件记录，再按数量
  落到 Staffel 的某一档），故消解范式（FR-008）只在**记录层**比较 `value`，
  不比较"定档后的金额"。若要按定档后金额比优，须把阶梯上移到比较函数——本期不做。
  **本模块产出的是费率**（与未分档记录的 `value` 同量纲），金额 = 费率 × 数量，
  由计算过程（FR-005）完成；若此处返金额，同一个 `lookup_amount` 变量会时而费率
  时而金额，配置无法统一书写。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import json

# 消解范式（FR-008 · Spec §9.3.1 B2 四范式）
RESOLUTION_PRECEDENCE = "precedence"   # 逐级覆盖，首个命中获胜（默认）
RESOLUTION_BEST = "best"               # 按度量取最优（须显式开启）
RESOLUTION_EXCLUSIVE = "exclusive"     # 排斥组内只保留获胜者
RESOLUTION_WEIGHTED = "weighted"       # 全部参与，加权累加

# 命中策略（FR-004 · C-T0-4 · 缺省 exclusive 与 v1.5 行为一致）
HIT_POLICY_EXCLUSIVE = "exclusive"     # 命中即止
HIT_POLICY_ADDITIVE = "additive"       # 继续向后查并累加

# 阶梯语义（FR-009 · rate_record.scale_semantic · 空 = 不启用）
SCALE_TOTAL = "total"                  # 整单取档（按总量落在哪档取哪档费率）
SCALE_INCREMENTAL = "incremental"      # 逐档累进（分段计算后累加）
SCALE_SEMANTICS = frozenset({SCALE_TOTAL, SCALE_INCREMENTAL})

# 跳过原因（回放用；命名与 DefaultExecutor.SKIP_REASONS 风格一致）
SKIP_HIT_BY_EARLIER = "hit_by_earlier_slot"   # 被更小 seq 的槽位抢先命中
SKIP_NOT_IN_GROUP = "not_in_slot_key"          # 键值不匹配本槽位
SKIP_DISABLED = "record_inactive"              # 记录已停用
SKIP_INVALID_WEIGHT = "weight_sum_not_normalized"  # 权重和 ≠ 1（拒绝计算）


class ResolutionError(Exception):
    """消解失败。用于「拒绝计算并报错」而非静默降级（FR-008 AC）。

    当前唯一触发场景：weighted 范式下同组权重和 != 1（TR-006 明确要求报错，
    禁止静默按比例缩放 —— 可预测性优先于"宽容"）。
    """


@dataclass
class Candidate:
    """一条候选费率记录（内存态，非 BO 记录）。

    对应 `rate_record` 表的取数字段。刻意不引入 BO 依赖（T2 前提）。
    """

    id: int
    priority: int = 100
    hit_policy: str = HIT_POLICY_EXCLUSIVE
    allocation_weight: Optional[float] = None
    value: float = 0.0
    inactive: bool = False
    key_schema_id: Optional[int] = None
    keys: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)
    # 阶梯（FR-009）：档位表 + 语义 + 分档基数字段。空 scale = 不分档
    scale: List[Dict[str, Any]] = field(default_factory=list)
    scale_semantic: Optional[str] = None
    scale_divisor: Optional[str] = None
    # 【补 2026-10-07 FR-009 收口】定价数量（如"每 10 个"填 10）。空/非正 = 1。
    # `rate` 是「每 rate_qty 个」的单价，喂给计算过程前须折算成**每 1 个**的单价
    # （见 `per_unit_rate`）。此前本字段全仓零消费 → "每 10 个收 100"被当成
    # "每个收 100" 直接 × base，**静默 10 倍超收**（实测 10000 vs 期望 1000）。
    rate_qty: float = 1.0

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Candidate":
        """从费率记录 dict 构造，缺省值对齐 T0 表声明（rate_record.yaml）。

        【修 2026-10-06】`keys` / `hit_policy` 等字段从 sqlite 读出来可能是
        **json 文本**（`keys` 是 json 列，`hit_policy` 若被当 json 存亦然），
        故此处统一做一次反序列化——否则 `keys` 会是 str，
        下游 `ck[k]` 报 "string indices must be integers"。
        """
        keys = d.get("keys")
        if isinstance(keys, str):
            try:
                keys = json.loads(keys) if keys else {}
            except (TypeError, ValueError):
                keys = {}

        # 【FR-009 2026-10-06】`scale` 同样是 json 列，须反序列化。
        # **与 keys 不同：解析失败必须报错，不能静默当"不分档"** ——
        #   keys 解析失败 → 该候选匹配不上（保守，不会算错价）；
        #   scale 解析失败 → 静默按不分档取 `value`（对分档记录 value 多半是 0），
        #   **会静默算出错误价格**。故此处抛配置矛盾（HTTP 层映射 422）。
        # 【二次审查补】"解析失败"不止 json 畸形，还含**形状不对**
        #   （对象而非数组 / 元素非 dict）——原实现只查 `isinstance(scale, list)`
        #   然后再赋 `[]`，把形状错误也静默降级为"不分档"，与畸形 json 同样危险。
        scale = d.get("scale")
        if scale in (None, ""):
            scale = []                       # 未声明阶梯 → 不分档（合法）
        elif isinstance(scale, str):
            try:
                scale = json.loads(scale)
            except (TypeError, ValueError) as exc:
                raise ResolutionError(
                    f"费率记录 {d.get('id')} 的 scale 不是合法 json：{exc}"
                ) from exc
        # 走到这里 = 已声明的值（str 已解析，或本就已解析）。形状须为 [{from,to,rate}]
        if not isinstance(scale, list) or any(not isinstance(t, dict) for t in scale):
            raise ResolutionError(
                f"费率记录 {d.get('id')} 的 scale 须为档位对象数组"
                "（形如 [{\"from\":0,\"to\":10,\"rate\":100}]）"
            )

        def _num(key, default=0.0):
            """sqlite 的 NULL / 文本数字统一成 float。
            【修 2026-10-06】`rate` / `priority` 列若为 NULL，原实现直接透传
            None，下游 `int + None` 抛 TypeError。"""
            v = d.get(key)
            if v is None or v == "":
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        return cls(
            id=d["id"],
            priority=int(_num("priority", 100)),
            hit_policy=d.get("hit_policy") or HIT_POLICY_EXCLUSIVE,
            allocation_weight=(
                None if d.get("allocation_weight") in (None, "")
                else _num("allocation_weight")
            ),
            value=_num("value", None) if d.get("value") is not None
            else _num("rate", 0.0),
            inactive=d.get("inactive", False) or d.get("status") == "inactive",
            key_schema_id=d.get("key_schema_id"),
            keys=keys or {},
            raw=d,
            scale=scale,
            scale_semantic=(d.get("scale_semantic") or None),
            scale_divisor=(d.get("scale_divisor") or None),
            rate_qty=_num("rate_qty", 1.0),
        )

    def per_unit_rate(self, rate: Optional[float] = None) -> float:
        """把「每 `rate_qty` 个」的单价折算成「每 1 个」的单价。

        【FR-009 · 2026-10-07 补】`rate_record.rate_qty` 声明「如"每 10 个"填 10」，
        而引擎契约是「金额 = **每单位**费率 × 数量」，故折算必须发生在喂给
        `rate_<id>` / `LookupResult.rates` 之前。

        【为何 `rate_qty <= 0` 兜底为 1 而非报错】存量与配置语义都是「空 = 1」
        （rate_record.yaml 声明）；负数/0 属配置矛盾，但本期**不引入新的拒绝
        路径**——若在此抛错，等于让存量脏数据把整张价目表的取价全阻断，
        比"按 1 处理"风险更大。已登记为待确认项。
        """
        r = self.value if rate is None else rate
        return float(r or 0.0) / (self.rate_qty if self.rate_qty > 0 else 1.0)


@dataclass
class LookupTrace:
    """查找回放骨架（FR-004 AC「可回答命中哪一行 / 为什么其它行被跳过」）。"""

    slot_seq: int
    key_schema_id: int
    hit_ids: List[int] = field(default_factory=list)
    skipped: List[Tuple[int, str]] = field(default_factory=list)  # (candidate_id, reason)
    weighted: bool = False
    # 阶梯定档留痕（FR-009 / FR-010）：每条获胜候选一条，记"落到哪一档、定出什么费率"
    scales: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_seq": self.slot_seq,
            "key_schema_id": self.key_schema_id,
            "hit_ids": list(self.hit_ids),
            "skipped": [{"candidate_id": c, "reason": r} for c, r in self.skipped],
            "weighted": self.weighted,
            "scales": [dict(s) for s in self.scales],
        }


@dataclass
class LookupResult:
    """查找结果。

    [语义]  `amount` 是"本槽位贡献的金额"（加权时 = Σ(rateᵢ×weightᵢ)，
            否则 = 命中行的 value 之和）。
            步骤间如何累加由 FR-005 计算过程负责，本模块**不越界**。
    """

    amount: float = 0.0
    hit_ids: List[int] = field(default_factory=list)
    candidates: List[Candidate] = field(default_factory=list)
    traces: List[LookupTrace] = field(default_factory=list)
    # 【FR-009】每条获胜候选**本槽位实际采用的费率**（分档记录 = 定档后费率，
    # 非分档 = `Candidate.value`）。存在的理由：分档记录的 `c.value` 是**无意义**的
    # 占位（额度类费率分档后 value 多半为 0），下游若继续读 `c.value`
    # 会把 0 当单价写回单据。故一律改读本表——单一真相源。
    rates: Dict[int, float] = field(default_factory=dict)

    @property
    def hit(self) -> bool:
        return bool(self.hit_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount": self.amount,
            "hit_ids": list(self.hit_ids),
            "traces": [t.to_dict() for t in self.traces],
            "rates": dict(self.rates),
        }


def _sort_key(c: Candidate) -> Tuple[int, int]:
    """确定性排序：priority asc → id asc（FR-004 AC「同 priority 须有确定 tie-break」）。

    **不依赖** dict/DB 隐式顺序 —— 这是"同数据两次取价结果相同"的唯一保证。
    """
    return (c.priority, c.id)


def _matches(cand: Candidate, wanted: Dict[str, Any], strict: bool) -> bool:
    """键值匹配。

    `wanted` 槽位键值（如 {"customer": 1001, "material": "M001"}）。
    `strict=True` 时要求 wanted 的每个键都在候选 keys 中命中（防串键）；
    `strict=False` 时只要候选覆盖了 wanted 的**全部**键即算命中（允许候选带额外键，
    对应更细的键在更粗的槽位下也能命中）。
    """
    if not wanted:
        return True
    ck = cand.keys
    for k, v in wanted.items():
        if k not in ck:
            if strict:
                return False
            return False
        if ck[k] != v:
            return False
    return True


def _num_or(v: Any, default: float) -> float:
    """档位边界 / 费率可能是 sqlite 读回的文本或 NULL，统一成 float。"""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _tier_bounds(t: Dict[str, Any]) -> Tuple[float, float]:
    """档位区间 **含下不含上**（与 `calc_procedure_executor._op_tier` 同口径）。

    `to` 缺省 = 无穷（顶档不封口）。
    """
    return _num_or(t.get("from"), 0.0), _num_or(t.get("to"), float("inf"))


def resolve_scale(cand: Candidate, qty: Optional[float]) -> Dict[str, Any]:
    """按量定档 —— FR-009。返回 `{semantic, qty, rate, tier}`。

    **产出的是费率**（见模块头 [阶梯]）：金额 = 费率 × 数量，由计算过程完成。

    - `total`（整单取档）：费率 = 命中档位的 `rate`
      —— 金额 = `rate × qty`
    - `incremental`（逐档累进）：费率 = 分段金额 ÷ `qty`（等效均价）
      —— 金额 = Σ `段长 × 段费率`

    与 `calc_procedure_executor._op_tier` 的两种语义**同义**（后者直接返金额），
    两者一致性由 `test_lookup_resolver.py::TestScaleParity` 逐例守护。

    【FR-009 · 2026-10-07 补】返回的 `rate` 一律经 `per_unit_rate()` 折算成
    **每 1 个**的单价。本函数是所有费率出口的**唯一收口**（不分档 / total /
    incremental 三条返回路径、以及 `LookupResult.rates` 与 `lookup_amount`
    累加都经此），故折算只做一次——服务层 `initial_state["rate_<id>"]` 直接
    取 `lk.rates` 即已是每单位费率，**不得再除第二次**。

    【边界】定档发生在**记录选定之后**，故消解范式（FR-008）仍按 `value` 比较——
    与 SAP「先存取序列选中条件记录、再落 Staffel 档位」一致。

    Raises:
        ResolutionError: 语义非法 / 声明了阶梯但未给数量 / 数量不落在任何档位内。
    """
    tiers = cand.scale or []
    semantic = cand.scale_semantic
    if not tiers or not semantic:
        # 空 scale = 不分档；空 scale_semantic = 阶梯不启用（rate_record.yaml 声明）
        return {"semantic": None, "qty": qty,
                "rate": cand.per_unit_rate(),
                "tier": None}
    if semantic not in SCALE_SEMANTICS:
        raise ResolutionError(
            f"未知的阶梯语义：{semantic!r}（可选 {sorted(SCALE_SEMANTICS)}）"
        )
    if qty is None:
        raise ResolutionError(
            f"费率记录 {cand.id} 声明了阶梯（scale_semantic={semantic}），"
            "但未提供阶梯基数（数量）"
        )

    q = float(qty)
    if q <= 0:
        # 非正数量 → 金额必为 0，与档位无关。不因"档位未覆盖负值/0"误报配置错误
        #（头级调用给 base=0 是常见情形）。
        # 【二次审查 2026-10-06】原写 `q == 0`，负数量会落入下方档位匹配：
        # `total` 找不到覆盖负值的档位 → **抛 ResolutionError**，而 `_op_tier`
        # 对同一输入**静默返 0**，两条路径分叉（`TestScaleParity` 原来只测非负值，
        # 故未暴露）。现统一为"非正数量 → 费率 0"，与 `_op_tier` 同口径。
        # 退货/红字场景应由 `calc_result.sign` 表达，不在阶梯算子内取负。
        return {"semantic": semantic, "qty": q, "rate": 0.0, "tier": None}

    if semantic == SCALE_INCREMENTAL:
        total = 0.0
        for t in tiers:
            lo, hi = _tier_bounds(t)
            seg = max(0.0, min(q, hi) - lo)
            total += seg * _num_or(t.get("rate"), 0.0)
        return {"semantic": semantic, "qty": q,
                "rate": cand.per_unit_rate(total / q), "tier": None}

    # SCALE_TOTAL：按声明顺序取首个覆盖 q 的档位
    for t in tiers:
        lo, hi = _tier_bounds(t)
        if lo <= q < hi:
            # 档位 rate 同样是「每 rate_qty 个」口径，须一并折算；
            # `tier.rate` 记**折算后**的值，使「费率 × 数量 = 金额」在留痕里
            # 也自洽（factor_snapshot 回放 FR-010 时直接用它复算）。
            rate = cand.per_unit_rate(_num_or(t.get("rate"), 0.0))
            return {
                "semantic": semantic, "qty": q, "rate": rate,
                "tier": {"from": lo,
                         "to": (None if hi == float("inf") else hi),
                         "rate": rate},
            }
    covered = ", ".join(f"[{_tier_bounds(t)[0]}, {_tier_bounds(t)[1]})" for t in tiers)
    raise ResolutionError(
        f"数量 {q} 不落在费率记录 {cand.id} 的任何阶梯档位内（已声明 {covered}）"
    )


def resolve_candidates(
    candidates: List[Candidate],
    resolution: str = RESOLUTION_PRECEDENCE,
    measure: Optional[str] = None,
) -> List[Candidate]:
    """候选消解 —— FR-008 四范式。

    Args:
        candidates: 同粒度候选（调用方保证已按槽位筛好）
        resolution: 四范式之一。默认 precedence（Spec FR-008 AC「默认 Precedence」）
        measure:   best 范式的度量（如 "min_amount" / "max_discount"）。
                   **best 绝不隐式默认**（FR-008 AC）——未给度量直接报错。

    Returns:
        消解后的候选列表。

        **取一语义**（`precedence` / `exclusive` / `best`）返回**至多 1 条**。
        **多候选语义**（`weighted`）返回**全部**（加权累加，见 `apply_weighted`）。

        **权重优先于 resolution**（FR-008 AC 第 3 条「若组内存在非空
        `allocation_weight`，该组按加权累加执行，`resolution` 对其不生效」）：
        若组内候选**全部**带 `allocation_weight`，则**无论传入哪个范式**
        （含 `best`，其 `measure` 会被**静默忽略**）一律返回全部候选。
        部分带、部分不带 → 抛 `ResolutionError`（不静默取一）。
        判定发生在读取 `resolution` **之前**，故下方的范式分支仅在
        「全组无权重」时才可能到达。

        **`exclusive` 当前与 `precedence` 实现等价**（均取 `live[:1]`）：
        排斥组边界须由 `exclusion_group` 圈定，但两个调用方
        （`PricingService.calculate_line` / `pricing_api`）**只传 `resolution`
        字符串、不传组边界** → 组边界无人承载，AC 第 3 条的这一半尚未实现。
        见 Spec §10.1 的排斥组缺口登记。

    Raises:
        ResolutionError: best 范式未定义度量 / 未知范式或度量 /
            权重和 ≠ 1 / 权重部分缺失 / `best` 用于分档记录。
    """
    live = [c for c in candidates if not c.inactive]
    if not live:
        return []

    # 【修 2026-10-06】加权分支的判定须区分"全空"与"部分空"：
    #   全空      → 普通取一（precedence/best/exclusive 语义）
    #   部分有值  → **报错**（FR-008 AC「不可混用」），由 _resolve_weighted 抛出
    #   全有值    → 加权累加
    # 原实现用 `any(... is not None)`，导致"全空"也走进加权分支，
    # 随后 int + None 报 TypeError 而非按语义处理。
    has_weight = [c.allocation_weight is not None for c in live]
    if all(has_weight):
        return _resolve_weighted(live)
    if any(has_weight):
        raise ResolutionError(
            "weighted 范式下同组候选不可混用：部分候选缺 allocation_weight"
        )

    live.sort(key=_sort_key)

    if resolution == RESOLUTION_WEIGHTED:
        return _resolve_weighted(live)

    if resolution == RESOLUTION_PRECEDENCE:
        # 首个命中获胜（默认；合同价应压过促销价 —— 靠 priority 表达）
        return live[:1]

    if resolution == RESOLUTION_EXCLUSIVE:
        # 排斥组内只保留获胜者 —— 语义上"获胜者"= 排序最前（同 precedence）。
        # 与 precedence 的区别在于**归属**：precedence 是通用取一，
        # exclusive 是"组内排斥"，须由 exclusion_group 显式圈定组边界。
        return live[:1]

    if resolution == RESOLUTION_BEST:
        if not measure:
            # 「Best Price 绝不隐式默认」——开启时须显式定义度量（FR-008 AC）
            raise ResolutionError("best 范式必须显式定义度量（measure），绝不隐式默认")
        # 【FR-009 · 二次审查 2026-10-06】分档记录的 `value` 是**无意义占位**
        #（真实费率由 `resolve_scale` 定档决定），拿它比优 = 比一串占位值 →
        # **静默选出错误记录**，是又一条"不报错但算错价"的路径。
        # 正确的比优须按**定档后费率**（需数量），本期未实现，故显式拒绝，
        # 让配置者改用 precedence（或去掉 scale）。
        tiered = [c.id for c in live if c.scale and c.scale_semantic]
        if tiered:
            raise ResolutionError(
                f"best 范式不可用于分档费率记录（id={tiered}）：其 value 为占位值，"
                "比优须按定档后费率，本期未实现——请改用 precedence"
            )
        if measure == "min_amount":
            return [min(live, key=lambda c: c.value)]
        if measure == "max_amount":
            return [max(live, key=lambda c: c.value)]
        raise ResolutionError(f"未知的度量：{measure}")

    raise ResolutionError(f"未知的消解范式：{resolution}")


def _resolve_weighted(cands: List[Candidate]) -> List[Candidate]:
    """加权累加分支：校验权重和 = 1，不满足则**拒绝计算并报错**。

    FR-008 AC / TR-006「权重和不归一 → 拒绝计算并报错（不静默缩放）」。
    """
    total = 0.0
    for c in cands:
        if c.allocation_weight is None:
            raise ResolutionError(
                "weighted 范式下同组候选不可混用：存在 allocation_weight 为空的候选"
            )
        total += c.allocation_weight
    if abs(total - 1.0) > 1e-9:
        raise ResolutionError(
            f"权重和须归一：Σallocation_weight = {total} ≠ 1（拒绝计算，不静默缩放）"
        )
    return list(cands)


def apply_weighted(
    cands: List[Candidate],
    base: float,
    rates: Optional[Dict[int, float]] = None,
) -> float:
    """加权累加：`Σ(rateᵢ × base × weightᵢ)`（FR-008 AC）。

    TR-006 验收：权重 0.5 / 0.3 / 0.2 → 100×.5 + 200×.3 + 300×.2 = 170
    （50+60+60=170）。base 传 1.0 即"单件加权费率"。
    [算术修正 2026-10-06] Spec 原文写 140 是错的，已同步修正。

    Args:
        rates: 可选 `{candidate_id: 实际采用费率}` —— **FR-009 分档记录须传**
               （其 `value` 是无意义占位）。不给则退回 `Candidate.value`。
    """
    if not cands:
        return 0.0
    _resolve_weighted(cands)  # 复用校验，不通过直接抛
    rate_of = (lambda c: rates.get(c.id, c.value)) if rates else (lambda c: c.value)
    return sum(rate_of(c) * base * (c.allocation_weight or 0.0) for c in cands)

def lookup(
    candidates: List[Candidate],
    steps: List[Dict[str, Any]],
    slot_keys: List[Dict[str, Any]],
    resolution: str = RESOLUTION_PRECEDENCE,
    measure: Optional[str] = None,
    scale_qty: Optional[float] = None,
) -> LookupResult:
    """查找序列主入口 —— FR-004。

    按 `steps` 的次序逐槽位取数，每槽独立执行消解；槽位之间 additive
    （D2「分层默认：槽位内 exclusive / 步骤间 additive」——不累加就算不出净价）。

    Args:
        candidates: 全部候选（引擎内部按 steps 筛）
        steps:      有序槽位 [{"seq": 1, "key_schema_id": 1}, ...]
        slot_keys:  与 steps 等长的槽位键值 [{"customer": 1001}, ...]；
                    某项为 `None` 表示该槽位无可用因子值，**跳过此槽**
                    （顺序不变，不会错位到下一槽）
        resolution: FR-008 消解范式
        measure:    best 范式度量
        scale_qty:  **阶梯基数（数量）** —— FR-009。命中带 `scale` 的记录时按此定档；
                    未提供而命中分档记录则报错（额度类记录无法知道落在哪档）。

    Returns:
        LookupResult（amount = 各槽位贡献之和；rates = 各获胜候选实际采用费率；
                      traces = 逐槽回放骨架）
    """
    result = LookupResult()
    # 【修 2026-10-06】槽位与键值必须成对排序。原实现只对 steps 排序、slot_keys
    # 保持原序 → 键值与槽位错配（steps 顺序变了，slot_keys 没跟着变）。
    # 正确做法：把 (step, keys) 打成对一起按 seq 排序。
    #
    # 【W2-F】`slot_keys` 中为 `None` 的项 = 该槽位无可用因子值（如订单无客户），
    # 直接剔除该对。**不可**把后面的键值往前挪：`zip` 是按位置配对的，
    # 少一项就会让第 2 槽用上第 1 槽的键值。
    pairs = sorted(
        ((step, wanted) for step, wanted in zip(steps, slot_keys)
         if wanted is not None),
        key=lambda p: p[0]["seq"],
    )  # 槽位按 seq 升序，忽略调用方顺序

    for step, wanted in pairs:
        ks = step["key_schema_id"]
        trace = LookupTrace(slot_seq=step["seq"], key_schema_id=ks)

        in_slot = []
        for c in candidates:
            if c.inactive:
                trace.skipped.append((c.id, SKIP_DISABLED))
                continue
            # 先按 key_schema_id 粗筛（走 idx_rate_record_lookup 索引），
            # 再在结果集内比对 keys{}（json 不可索引，C-T0-12 的既定代价）
            if c.key_schema_id is not None and c.key_schema_id != ks:
                trace.skipped.append((c.id, SKIP_NOT_IN_GROUP))
                continue
            if not _matches(c, wanted, strict=False):
                trace.skipped.append((c.id, SKIP_NOT_IN_GROUP))
                continue
            in_slot.append(c)

        if not in_slot:
            result.traces.append(trace)
            continue

        winners = resolve_candidates(in_slot, resolution, measure)
        trace.hit_ids = [c.id for c in winners]

        # 【FR-009 2026-10-06】定档：算出"本槽位实际采用的费率"并留痕。
        # 分档记录的 `c.value` 是**无意义占位**，故此后累加一律走 `slot_rates`，
        # 不再读 `c.value`（否则分档记录会被当 0 费率算，静默算错价）。
        slot_rates: Dict[int, float] = {}
        for c in winners:
            sc = resolve_scale(c, scale_qty)
            slot_rates[c.id] = sc["rate"]
            if sc["semantic"]:
                trace.scales.append({"candidate_id": c.id, **sc})

        # 加权判定与 resolve_candidates 保持一致：全有值才加权
        winners_have_weight = all(
            c.allocation_weight is not None for c in winners
        )
        if resolution == RESOLUTION_WEIGHTED or winners_have_weight:
            trace.weighted = True
            result.amount += apply_weighted(winners, 1.0, slot_rates)
        else:
            result.amount += sum(slot_rates.values())

        result.rates.update(slot_rates)
        result.hit_ids.extend(trace.hit_ids)
        result.candidates.extend(winners)
        result.traces.append(trace)

        # 【修 2026-10-06】命中即停：整段 break，**不再累加后续槽位**。
        # 原实现在 stop 后仍继续遍历并累加金额，导致 exclusive 语义被破坏
        #（实测 exclusive 场景把 100 + 50 = 150 全加上了）。
        if any(c.hit_policy == HIT_POLICY_EXCLUSIVE for c in winners):
            hit_index = pairs.index((step, wanted))
            for later_step, _later_keys in pairs[hit_index + 1:]:
                ltrace = LookupTrace(
                    slot_seq=later_step["seq"], key_schema_id=later_step["key_schema_id"]
                )
                for c in candidates:
                    ltrace.skipped.append((c.id, SKIP_HIT_BY_EARLIER))
                result.traces.append(ltrace)
            break

    return result
