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
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# 消解范式（FR-008 · Spec §9.3.1 B2 四范式）
RESOLUTION_PRECEDENCE = "precedence"   # 逐级覆盖，首个命中获胜（默认）
RESOLUTION_BEST = "best"               # 按度量取最优（须显式开启）
RESOLUTION_EXCLUSIVE = "exclusive"     # 排斥组内只保留获胜者
RESOLUTION_WEIGHTED = "weighted"       # 全部参与，加权累加

# 命中策略（FR-004 · C-T0-4 · 缺省 exclusive 与 v1.5 行为一致）
HIT_POLICY_EXCLUSIVE = "exclusive"     # 命中即止
HIT_POLICY_ADDITIVE = "additive"       # 继续向后查并累加

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

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Candidate":
        """从费率记录 dict 构造，缺省值对齐 T0 表声明（rate_record.yaml）。"""
        return cls(
            id=d["id"],
            priority=d.get("priority", 100),
            hit_policy=d.get("hit_policy") or HIT_POLICY_EXCLUSIVE,
            allocation_weight=d.get("allocation_weight"),
            value=d.get("value", 0.0),
            inactive=d.get("inactive", False) or d.get("status") == "inactive",
            key_schema_id=d.get("key_schema_id"),
            keys=d.get("keys") or {},
            raw=d,
        )


@dataclass
class LookupTrace:
    """查找回放骨架（FR-004 AC「可回答命中哪一行 / 为什么其它行被跳过」）。"""

    slot_seq: int
    key_schema_id: int
    hit_ids: List[int] = field(default_factory=list)
    skipped: List[Tuple[int, str]] = field(default_factory=list)  # (candidate_id, reason)
    weighted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_seq": self.slot_seq,
            "key_schema_id": self.key_schema_id,
            "hit_ids": list(self.hit_ids),
            "skipped": [{"candidate_id": c, "reason": r} for c, r in self.skipped],
            "weighted": self.weighted,
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

    @property
    def hit(self) -> bool:
        return bool(self.hit_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount": self.amount,
            "hit_ids": list(self.hit_ids),
            "traces": [t.to_dict() for t in self.traces],
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
        消解后的候选列表。precedence/best/exclusive 返回**至多 1 条**；
        weighted 返回**全部**（加权累加，见 apply_weighted）。

    Raises:
        ResolutionError: best 范式未定义度量。
    """
    live = [c for c in candidates if not c.inactive]
    if not live:
        return []

    # weighted：组内存在非空权重 → 整组按加权累加，优先级/排斥组对其不生效
    # （FR-008 AC「同组内非空 allocation_weight 与取一类候选不可混用」）
    if any(c.allocation_weight is not None for c in live):
        return _resolve_weighted(live)

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


def apply_weighted(cands: List[Candidate], base: float) -> float:
    """加权累加：`Σ(rateᵢ × base × weightᵢ)`（FR-008 AC）。

    TR-006 验收：权重 0.5 / 0.3 / 0.2 → 100×.5 + 200×.3 + 300×.2 = 140
    （base=1）。base 传 1.0 即"单件加权费率"。
    """
    if not cands:
        return 0.0
    _resolve_weighted(cands)  # 复用校验，不通过直接抛
    return sum(c.value * base * (c.allocation_weight or 0.0) for c in cands)


def lookup(
    candidates: List[Candidate],
    steps: List[Dict[str, Any]],
    slot_keys: List[Dict[str, Any]],
    resolution: str = RESOLUTION_PRECEDENCE,
    measure: Optional[str] = None,
) -> LookupResult:
    """查找序列主入口 —— FR-004。

    按 `steps` 的次序逐槽位取数，每槽独立执行消解；槽位之间 additive
    （D2「分层默认：槽位内 exclusive / 步骤间 additive」——不累加就算不出净价）。

    Args:
        candidates: 全部候选（引擎内部按 steps 筛）
        steps:      有序槽位 [{"seq": 1, "key_schema_id": 1}, ...]
        slot_keys:  与 steps 等长的槽位键值 [{"customer": 1001}, ...]
        resolution: FR-008 消解范式
        measure:    best 范式度量

    Returns:
        LookupResult（amount = 各槽位贡献之和；traces = 逐槽回放骨架）
    """
    result = LookupResult()
    # 【修 2026-10-06】槽位与键值必须成对排序。原实现只对 steps 排序、slot_keys
    # 保持原序 → 键值与槽位错配（steps 顺序变了，slot_keys 没跟着变）。
    # 正确做法：把 (step, keys) 打成对一起按 seq 排序。
    pairs = sorted(
        zip(steps, slot_keys),
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

        if resolution == RESOLUTION_WEIGHTED or any(
            c.allocation_weight is not None for c in winners
        ):
            trace.weighted = True
            result.amount += apply_weighted(winners, 1.0)
        else:
            result.amount += sum(c.value for c in winners)

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
