# -*- coding: utf-8 -*-
"""
定价编排服务（Pricing Service）— 定价引擎 T1-4
================================================

把 T2 内核（`lookup_resolver` + `calc_procedure_executor`）与 T1 配置链
（10 张表）串成**一条完整链路**：

    读配置 → 查表(FR-004) → 算过程(FR-005/006/007) → 落结果(FR-010/011) + 记明细

[分层 · 依赖方向]
    本模块是 **services 层**，向下依赖 core（两个纯函数内核）+ 读配置表，
    **不依赖 api 层**。api 层只做参数校验与响应包装（见 pricing_api.py）。

[现状：行级受阻于 order_line]
    本仓 `bo_sub_category: document` 仅 `sales_order_enhanced.yaml` 一个，
    且**单头无行**（`order_line` 对象缺失）。故本期按 §8.2.0 两步法：
    **先挂头级**（`document_line_id = NULL` / `level = header`），
    待 `order_line` 补齐后**仅填该字段**，本模块与三表结构零改动。
    为此本模块的 `document_line_id` 参数是**可选**的，且不做存在性校验。

[可回放 · FR-010]
    每步都落 `calc_detail`：命中哪些候选（hit_ids）、剔除了谁及原因
    （skipped_candidates）、当时的因子取值（factor_snapshot）、
    算完累计多少（running_net_amount）。**只存结果不存因子 = 无法复现**。
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.lookup_resolver import (
    Candidate,
    ResolutionError,
    lookup,
    RESOLUTION_PRECEDENCE,
)
from meta.core.calc_procedure_executor import (
    CalculationError,
    execute,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 结果写回映射（TBD-9 ②：本期不建 pricing_output_map 对象）
# ----------------------------------------------------------------------
# 拍板结论：「按 result_semantic 约定写回字段」——`price`→`unit_price`/`amount`、
# `cost`→`cost_amount`、`emission`→`emission_amount`，余者落 `result_amount`。
# 理由见 §10 TBD-9：`calc_result` 已泛化挂任意 document 型 BO，但下游单据行
# 字段名不同即断链；多过程 / 多结果结构时再补对象，本约定即默认映射。
#
# 值为 (单价字段 or None, 金额字段)。`None` 表示该语义不产出单价。
WRITEBACK_MAP: Dict[str, Dict[str, Optional[str]]] = {
    "price":     {"unit": "unit_price",  "amount": "amount"},
    "cost":      {"unit": None,           "amount": "cost_amount"},
    "emission":  {"unit": None,           "amount": "emission_amount"},
    "tax":       {"unit": None,           "amount": "result_amount"},
    "hours":     {"unit": "unit_price",   "amount": "result_amount"},
    "quantity":  {"unit": "unit_price",   "amount": "result_amount"},
}

# 候选字段名（不同单据可能命名不同，按优先级取第一个存在的）
_UNIT_CANDIDATES = ("unit_price", "price", "unit_cost")
_AMOUNT_CANDIDATES = ("amount", "total_amount", "net_amount", "line_amount")


def _to_num(v: Any) -> Optional[float]:
    """数值列归一：sqlite 可能读回 str / bytes / None，统一成 float 或 None。"""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class PricingError(Exception):
    """定价失败。

    与内核的 `ResolutionError` / `CalculationError` **并列不兜底**——
    内核错是"配置/候选矛盾"，本异常是"编排层无法完成"（如过程不存在）。
    """


def _to_bool_or_none(v: Any) -> Optional[bool]:
    """布尔列归一：sqlite 读回 0/1/None（或文本）统一成真正的 bool 或 None。

    【为何必须归一】执行器判"跳过本步"用 `condition is False`（**严格身份**），
    而 sqlite 的 0 不是 Python 的 False —— 不归一会让「显式 false 的条件行」
    静默不跳过。拆表前 json.loads 给出的本就是真正的 False，此处保持等价。
    """
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().lower() in ("1", "true", "yes", "y")


def _loads(v: Any, default):
    """json 列可能是 str（sqlite 存文本）或已解析对象。"""
    if v is None or v == "":
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


class PricingService:
    """定价编排。构造注入数据源，便于测试用内存 SQLite。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 配置读取
    # ------------------------------------------------------------------
    def _query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        cur = self.ds.execute(sql, list(params))
        rows = cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_rate_tables(self, status: str = "approved") -> List[Dict[str, Any]]:
        """取参与取价的价目表。**仅 `approved`**（C-T0-11 草稿发布分离）。"""
        return self._query(
            "SELECT * FROM rate_tables WHERE status = ? ORDER BY code", (status,)
        )

    def get_procedure(self, code: str) -> Optional[Dict[str, Any]]:
        """取定价过程定义（步骤在子表，见 get_procedure_steps）。"""
        rows = self._query("SELECT * FROM calc_procedures WHERE code = ?", (code,))
        return rows[0] if rows else None

    def get_procedure_steps(self, procedure_id: int) -> List[Dict[str, Any]]:
        """按 seq 升序装配过程的计算步骤 —— 方案① 后 steps 已由 json 列拆为子表。

        返回结构即 `calc_procedure_executor.execute(steps=...)` 的入参：
        [{seq, element_type, rate_type_id, condition, params, rolling,
          base_step, subtotal_key}, ...]

        【W2-C】一并带出该步费率类型的 `code`（`rate_type`）与 `rate_class`：
        编排层据此判定「价格类沿用确定规则序列、折扣/附加费类按自身序列独立查找」，
        明细落库也能记下步骤的费率类型编码。

        【布尔口径】见 `_to_bool_or_none` —— condition 必须归一成真正的
        bool/None，才能与执行器的 `is False` 判断对齐。
        """
        rows = self._query(
            "SELECT s.*, rt.code AS rt_code, rt.rate_class AS rt_class"
            "  FROM calc_procedure_steps s"
            "  LEFT JOIN rate_types rt ON rt.id = s.rate_type_id"
            " WHERE s.calc_procedure_id = ? ORDER BY s.seq ASC",
            (procedure_id,),
        )
        return [
            {
                "seq": r.get("seq"),
                "element_type": r.get("element_type"),
                "rate_type_id": r.get("rate_type_id"),
                "rate_type": r.get("rt_code"),
                "rate_type_class": r.get("rt_class"),
                "condition": _to_bool_or_none(r.get("condition")),
                "params": _loads(r.get("params"), {}),
                "rolling": bool(r.get("rolling")),
                "base_step": r.get("base_step"),
                "subtotal_key": r.get("subtotal_key"),
            }
            for r in rows
        ]

    def get_sequence(self, code: str) -> Optional[Dict[str, Any]]:
        rows = self._query("SELECT * FROM lookup_sequences WHERE code = ?", (code,))
        return rows[0] if rows else None

    def get_rate_type(self, code: str) -> Optional[Dict[str, Any]]:
        """取费率类型。**当前编排未用**——`calc_result.rate_type_code` 取自
        计算步骤声明（rate_type_id → code），而非独立查表。
        保留供后续「按费率类型分组统计 / 分摊」等场景使用。
        """
        rows = self._query("SELECT * FROM rate_types WHERE code = ?", (code,))
        return rows[0] if rows else None

    def load_candidates(
        self,
        rate_table_id: int,
        key_schema_id: Optional[int] = None,
        valid_on: Optional[str] = None,
        rate_type_id: Optional[int] = None,
    ) -> List[Candidate]:
        """装载候选费率记录。

        【T0-7 遗留 · 已知代价】`keys{}` 是 json，**不可索引**，
        故这里只能先按 `rate_table_id`（+ `key_schema_id`）**收窄**，
        走 `idx_rate_record_lookup`，再由 lookup 引擎在结果集内比对键值。
        这是 C-T0-12「结构冻结」的既定代价。

        【W2-C · `rate_type_id` 过滤】同一价目表可同时存价格、折扣、附加费记录，
        且它们的 `keys{}` 完全相同（都按物料 / 客户匹配）。若不按费率类型过滤，
        价格步骤会命中折扣记录（费率 5 被当成单价），反之亦然。故编排层必须
        **按步骤声明的费率类型分别装载**，本参数即该收窄手段。

        【FR-016 条件更新】装载阶段即剔除**累计用量已触顶**的费率记录
        （对标 SAP Condition Update `KOUPD`：条件记录跨单累计，用满即失效）。
        在此剔除而非在引擎里判，是为了让"用满"与"停用"走**同一条**回放路径
        （`inactive` → `SKIP_DISABLED`），不新增第三种跳过原因。
        """
        sql = "SELECT * FROM rate_records WHERE rate_table_id = ? AND status = 'active'"
        params: List[Any] = [rate_table_id]
        if key_schema_id is not None:
            sql += " AND key_schema_id = ?"
            params.append(key_schema_id)
        if rate_type_id is not None:
            sql += " AND rate_type_id = ?"
            params.append(rate_type_id)
        if valid_on:
            # 有效期过滤：区间含下不含上，空值表示无限
            sql += (" AND (valid_from IS NULL OR valid_from <= ?)"
                    " AND (valid_to IS NULL OR valid_to > ?)")
            params.extend([valid_on, valid_on])
        sql += " ORDER BY priority ASC, id ASC"
        cands = [Candidate.from_dict(r) for r in self._query(sql, tuple(params))]
        return self._apply_usage_exhaustion(cands)

    # ------------------------------------------------------------------
    # FR-016 条件更新（累计用量）
    # ------------------------------------------------------------------
    def _apply_usage_exhaustion(self, cands: List[Candidate]) -> List[Candidate]:
        """把**累计用量已触顶**的候选标记为 inactive（不删除、不报错）。

        【为什么"触顶"复用 `inactive` 语义】`cumulative_usage` 上限由
        `usage_group` 给（金额 / 数量 / 单据数三选），任一触顶即失效
        （FR-016 AC「超限自动失效」）。失效是**配置状态**而非异常，
        故走既有 `inactive` 通道，回放记 `record_inactive`。

        【缺表容错】`cumulative_usages` / `usage_groups` 属 P2 对象，
        早期库可能未建表；查不到即视为"无上限"，不阻断取价。
        """
        if not cands:
            return cands
        ids = [c.id for c in cands]
        try:
            rows = self._query(
                "SELECT cu.rate_record_id, cu.used_amount, cu.used_quantity,"
                "       cu.used_documents, ug.max_amount, ug.max_quantity,"
                "       ug.max_documents"
                "  FROM cumulative_usages cu"
                "  JOIN usage_groups ug ON ug.id = cu.usage_group_id"
                " WHERE cu.rate_record_id IN ({0})".format(
                    ", ".join("?" * len(ids))),
                tuple(ids),
            )
        except Exception as exc:      # 表未建 / 无该组 —— 视为无上限
            logger.debug("累计用量检查跳过（表不可用）：%s", exc)
            return cands

        exhausted = set()
        for r in rows:
            for used_col, max_col in (("used_amount", "max_amount"),
                                      ("used_quantity", "max_quantity"),
                                      ("used_documents", "max_documents")):
                cap = _to_num(r.get(max_col))
                if cap is None:
                    continue        # 该维度不设上限
                used = _to_num(r.get(used_col)) or 0.0
                if used >= cap:
                    exhausted.add(r["rate_record_id"])
                    break
        for c in cands:
            if c.id in exhausted:
                c.inactive = True
        return cands

    def _accumulate_usage(self, lk, *, base: float, net: float) -> None:
        """把本次用量累加进 `cumulative_usages`（FR-016 写侧）。

        **只在落库路径调用**（dry-run 不累计），且与结果落库**同事务** ——
        累计值与结果行必须同生共死，否则会出现"结果已生效但用量没计"，
        下次取价仍判未触顶 = 超发。

        【累加口径】金额累加本次 `net`，数量累加计算基 `base`，
        单据数 +1（**按命中候选逐条计**，多候选取优时各条各计一次——
        对标 SAP：每条条件记录各自维护自己的累计值）。

        【缺表容错】与读侧同口径：`cumulative_usages` 未建表时跳过累计，
        不阻断取价（P2 对象晚于 T0 交付，早期库无此表）。
        """
        if lk is None or not lk.hit_ids:
            return
        now = datetime.now().isoformat(timespec="seconds")
        for cid in lk.hit_ids:
            try:
                self.ds.execute(
                    "UPDATE cumulative_usages"
                    "   SET used_amount = COALESCE(used_amount, 0) + ?,"
                    "       used_quantity = COALESCE(used_quantity, 0) + ?,"
                    "       used_documents = COALESCE(used_documents, 0) + 1,"
                    "       last_used_at = ?, updated_at = ?"
                    " WHERE rate_record_id = ?",
                    [float(net or 0.0), float(base or 0.0), now, now, cid],
                )
            except Exception as exc:
                logger.debug("累计用量写入跳过（表不可用）：%s", exc)
                return

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def price_line(
        self,
        process_code: str,
        rate_table_id: int,
        slot_keys: List[Dict[str, Any]],
        base: float,
        *,
        sequence_code: Optional[str] = None,
        document_type: Optional[str] = None,
        document_id: Optional[int] = None,
        document_line_id: Optional[int] = None,
        level: str = "header",
        resolution: str = RESOLUTION_PRECEDENCE,
        measure: Optional[str] = None,
        valid_on: Optional[str] = None,
        persist: bool = True,
        result_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """对一行执行定价：查表 → 算过程 → （可选）落结果与明细。

        Args:
            process_code:   定价过程编码（calc_procedures.code）
            rate_table_id:  价目表 ID
            slot_keys:      与**查找序列**槽位等长的键值，如 [{"customer": 1001}]
            base:           计算基数（由 FR-006 的 base_level/base_source 决定）。
                            **同时用作 FR-009 阶梯基数**（命中带 `scale` 的费率记录时按此定档）
            sequence_code:  查找序列编码。**留空则跳过 FR-004 查表**，
                            直接由 calc_procedure 的计算步骤出结果
            document_*:     泛化宿主（FR-011）；本期只挂头级故 line 可空
            resolution:     候选消解范式（FR-008）
            measure:        `best` 范式的度量（如 min_amount）。**best 必填**，
                            否则内核报「绝不隐式默认」——不透传则 best 永不可达
            valid_on:       有效期（含下不含上）
            persist:        False = 只算不落库（dry-run / 预览）
            result_code:    调用方指定的结果编码（幂等键）；留空自动生成

        Returns:
            {"net_amount", "subtotals", "step_results", "traces", "result_id"}

        Raises:
            PricingError:     过程不存在 / 价目表不存在
            ResolutionError:  权重和不归一等（FR-008：拒绝计算，不静默缩放）
            CalculationError: 算子未注册 / rolling 与 base_step 互斥等
        """
        proc = self.get_procedure(process_code)
        if not proc:
            raise PricingError(f"定价过程不存在：{process_code}")

        tables = self.get_rate_tables(status="approved")
        table_ids = {t["id"] for t in tables}
        if rate_table_id not in table_ids:
            # C-T0-11：未发布的价目表不参与取价（对标金蝶"仅审核态参与取价"）
            raise PricingError(
                f"价目表 {rate_table_id} 不存在或未发布（仅 approved 参与取价）"
            )

        steps = self.get_procedure_steps(proc["id"])
        if not steps:
            raise PricingError(f"定价过程未定义步骤：{process_code}")

        # ---- 阶段一：查表（FR-004 / T2-1）----
        # 【实施纠正 2026-10-06】查找序列是**独立配置**，与计算步骤不同源：
        #   lookup_sequence.steps[]      = 查找槽位 {seq, key_schema_id}
        #   calc_procedure_step 行        = 计算步骤 {seq, element_type, ...}
        #     （方案① 2026-10-13 前是本表的 steps json 列）
        # 早期实现把计算步骤直接喂给 lookup，报 KeyError: key_schema_id。
        lk = None
        lk_traces: List[Dict[str, Any]] = []
        hit_ids: List[int] = []
        initial_state: Dict[str, Any] = {}
        step_lookups: Dict[int, Any] = {}

        if sequence_code:
            lk_seq = self.get_sequence(sequence_code)
            if not lk_seq:
                raise PricingError(f"查找序列不存在：{sequence_code}")
            slots = _loads(lk_seq.get("steps"), [])
            if not slots:
                raise PricingError(f"查找序列未定义槽位：{sequence_code}")
            # 【W2-C】主查表只装**价格类**候选：同表内的折扣/附加费记录
            # 键值相同，混装会让价格步骤命中折扣费率（5 被当单价）。
            price_rate_type_id = self._price_rate_type_id(steps)
            candidates = self.load_candidates(
                rate_table_id, valid_on=valid_on,
                rate_type_id=price_rate_type_id,
            )
            lk = lookup(
                candidates=candidates,
                steps=slots,                     # ← 查找槽位（非计算步骤）
                slot_keys=slot_keys,             # ← 与槽位等长
                resolution=resolution,
                measure=measure,
                # 【FR-009 2026-10-06】阶梯基数 = 计算基（数量）。
                # `rate_record.scale_divisor`（分档基数字段）**本期不消费**：它要求读
                # 单据行字段，与"零 order_line / 零主数据"前提冲突，待行对象补齐后接。
                scale_qty=base,
            )
            lk_traces = [t.to_dict() for t in lk.traces]
            hit_ids = list(lk.hit_ids)
            # 把查表命中喂给计算过程作为初始 state（IF-001 逐行调用的接缝）
            initial_state = {
                "lookup_amount": lk.amount,
                "lookup_hit_ids": list(lk.hit_ids),
            }
            for c in lk.candidates:
                # 【FR-009】分档记录的 `c.value` 是无意义占位，须用**定档后费率**。
                # 【FR-009 · 2026-10-07 补】`lk.rates` 的费率已由
                # `resolve_scale` 折算成**每 1 个**的单价（含 `rate_qty`
                # 折算），此处**不得再除第二次**；fallback 的 `c.value` 是
                # 未折算的毛额，故走 `per_unit_rate()` 补齐——两条路径口径一致。
                initial_state[f"rate_{c.id}"] = lk.rates.get(
                    c.id, c.per_unit_rate())

        # 【W2-C】折扣/附加费各自按费率类型的查找序列**独立查表**，并把命中
        # 值按步注入（不共用价格查表结果）。价格类与未声明费率类型的步骤
        # 仍走主查表，保持波次 1 的既有口径。
        steps = self._bind_step_lookups(
            steps, rate_table_id=rate_table_id, slot_keys=slot_keys,
            base=base, valid_on=valid_on, resolution=resolution,
            measure=measure, primary=lk, primary_rate_type_id=(
                self._price_rate_type_id(steps) if sequence_code else None),
            out=step_lookups,
        )

        # ---- 阶段二：算过程（FR-005/006/007 / T2-2）----
        calc = execute(steps=steps, base=base, initial_state=initial_state)
        net = float(calc["amount"])

        # ---- 阶段三：落结果与明细（FR-010 / FR-011）----
        result_id = None
        if persist and document_type and document_id is not None:
            result_id = self._persist_with_invalidate(
                process=proc,
                level=level,
                document_type=document_type,
                document_id=document_id,
                document_line_id=document_line_id,
                net=net,
                base=base,
                calc=calc,
                lk=lk,
                step_lookups=step_lookups,
                valid_on=valid_on,
                result_code=result_code,
            )

        return {
            "amount": net,
            "net_amount": net,
            "subtotals": calc["subtotals"],
            "step_results": calc["step_results"],
            "state": calc.get("state", {}),
            "traces": lk_traces,
            "hit_ids": hit_ids,
            "result_id": result_id,
        }

    # ------------------------------------------------------------------
    # 多费率类型查找（W2-C）
    # ------------------------------------------------------------------
    def _price_rate_type_id(self, steps: List[Dict[str, Any]]) -> Optional[int]:
        """过程里「价格类」步骤的费率类型 ID（主查表用）。

        价格类（`rate_class='price'`）沿用确定规则给的查找序列；没有价格类步骤
        （如纯公式过程）时返回 None，主查表不按费率类型收窄，保持旧口径。
        """
        for s in steps:
            if s.get("rate_type_id") is not None \
                    and s.get("rate_type_class") == "price":
                return s["rate_type_id"]
        return None

    def _bind_step_lookups(
        self,
        steps: List[Dict[str, Any]],
        *,
        rate_table_id: int,
        slot_keys: List[Dict[str, Any]],
        base: float,
        valid_on: Optional[str],
        resolution: str,
        measure: Optional[str],
        primary,
        primary_rate_type_id: Optional[int],
        out: Dict[int, Any],
    ) -> List[Dict[str, Any]]:
        """为声明了费率类型的步骤绑定该步的查表结果，并注入 `lookup_amount`。

        - 价格类 / 未声明费率类型 → 复用主查表结果（`primary`）
        - 其余类型（折扣、附加费…） → 按其 `rate_type.lookup_sequence_id`
          在同一价目表内**独立查找**，且只装该费率类型的候选
        - 非价格类但未配查找序列 → 显式注入 0，**杜绝**拿价格命中值当百分比
        """
        values = self._factor_values(slot_keys)
        bound: List[Dict[str, Any]] = []
        for s in steps:
            rid = s.get("rate_type_id")
            step = dict(s)
            if rid is None or rid == primary_rate_type_id:
                if primary is not None:
                    out[step["seq"]] = primary
                    step["lookup_amount"] = float(primary.amount)
            else:
                slk = self._lookup_for_rate_type(
                    rate_type_id=rid, rate_table_id=rate_table_id,
                    values=values, base=base, valid_on=valid_on,
                    resolution=resolution, measure=measure,
                )
                out[step["seq"]] = slk
                step["lookup_amount"] = (
                    float(slk.amount) if slk is not None else 0.0)
            bound.append(step)
        return bound

    def _lookup_for_rate_type(
        self,
        *,
        rate_type_id: int,
        rate_table_id: int,
        values: Dict[str, Any],
        base: float,
        valid_on: Optional[str],
        resolution: str,
        measure: Optional[str],
    ):
        """按单个费率类型的查找序列查一次，返回 LookupResult；无序列返回 None。"""
        rt = self._one(
            "SELECT lookup_sequence_id FROM rate_types WHERE id = ?",
            (rate_type_id,))
        seq_id = (rt or {}).get("lookup_sequence_id")
        if seq_id is None:
            return None
        seq = self._one(
            "SELECT steps FROM lookup_sequences WHERE id = ?", (seq_id,))
        slots = _loads((seq or {}).get("steps"), [])
        if not slots:
            return None
        return lookup(
            candidates=self.load_candidates(
                rate_table_id, valid_on=valid_on, rate_type_id=rate_type_id),
            steps=slots,
            slot_keys=self._slot_keys_for(slots, values),
            resolution=resolution,
            measure=measure,
            scale_qty=base,
        )

    @staticmethod
    def _factor_values(slot_keys: List[Dict[str, Any]]) -> Dict[str, Any]:
        """把各槽位的键值合并成因子取值表，供其他查找序列重新组槽。"""
        values: Dict[str, Any] = {}
        for keys in slot_keys or []:
            if isinstance(keys, dict):
                values.update(keys)
        return values

    def _slot_keys_for(
        self,
        slots: List[Dict[str, Any]],
        values: Dict[str, Any],
    ) -> List[Optional[Dict[str, Any]]]:
        """按给定查找序列的槽位与 `key_schemas.key_fields` 逐槽组键。

        任一因子取不到值即该槽位置 `None`（引擎跳过该槽，顺序不变）。
        """
        out: List[Optional[Dict[str, Any]]] = []
        for step in sorted(slots, key=lambda s: (s or {}).get("seq") or 0):
            schema = self._one(
                "SELECT key_fields FROM key_schemas WHERE id = ?",
                ((step or {}).get("key_schema_id"),))
            fields = _loads((schema or {}).get("key_fields"), [])
            keys: Optional[Dict[str, Any]] = {}
            for field in fields:
                value = values.get(field)
                if value is None or value == "":
                    keys = None
                    break
                keys[field] = value
            out.append(keys or None)
        return out

    def _one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # 落库
    # ------------------------------------------------------------------
    def _persist_with_invalidate(
        self,
        *,
        process: Dict[str, Any],
        level: str,
        document_type: str,
        document_id: int,
        document_line_id: Optional[int],
        net: float,
        base: float,
        calc: Dict[str, Any],
        lk,
        step_lookups: Optional[Dict[int, Any]] = None,
        valid_on: Optional[str] = None,
        result_code: Optional[str] = None,
    ) -> int:
        """作废旧结果 + 落新结果 + 落明细 + 累计用量（FR-016），**整体一个事务**。

        【补 2026-10-06 二次审查】
        ① **重算须作废旧结果**：否则同一单据调两次会留下 2 条 active 结果，
           `explain` 只查 active，回放无法判断哪条有效。`status` 枚举里
           `invalid` 的语义正是「已被重算取代，保留以便审计」。
        ② **作废与新写必须同事务**：否则作废成功而新写失败 = 该单据**无有效结果**，
           比留 2 条 active 更糟。
        ③ **累计用量与结果同事务**（FR-016）：分开写会出现"结果已生效但用量没计"，
           下次取价仍判未触顶 = 超发。**重算同理**——重算会作废旧结果，
           故累计只增不减会重复计数，这是 FR-016 已知代价（对标 SAP 亦需
           手工冲销累计值），本期不做自动冲销。
        """
        tx = getattr(self.ds, "transaction", None)
        if callable(tx):
            with tx():
                rid = self._invalidate_and_persist_inner(
                    process, level, document_type, document_id,
                    document_line_id, net, base, calc, lk,
                    step_lookups, valid_on, result_code,
                )
                self._accumulate_usage(lk, base=base, net=net)
                return rid
        sp = f"sp_pricing_{uuid.uuid4().hex[:8]}"
        # 裸 sqlite 连接（测试用）无 transaction()，用 SAVEPOINT 包裹。
        # 【注意】不能用 BEGIN —— python sqlite3 默认 autocommit=False，
        # 已在隐式事务中，显式 BEGIN 会报 "cannot start a transaction
        # within a transaction"。SAVEPOINT 可嵌套，故两者皆宜。
        self.ds.execute(f"SAVEPOINT {sp}")
        try:
            rid = self._invalidate_and_persist_inner(
                process, level, document_type, document_id,
                document_line_id, net, base, calc, lk,
                step_lookups, valid_on, result_code,
            )
            self._accumulate_usage(lk, base=base, net=net)
            self.ds.execute(f"RELEASE SAVEPOINT {sp}")
            return rid
        except Exception:
            self.ds.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            self.ds.execute(f"RELEASE SAVEPOINT {sp}")
            raise

    def _invalidate_and_persist_inner(
        self,
        process: Dict[str, Any],
        level: str,
        document_type: str,
        document_id: int,
        document_line_id: Optional[int],
        net: float,
        base: float,
        calc: Dict[str, Any],
        lk,
        step_lookups: Optional[Dict[int, Any]] = None,
        valid_on: Optional[str] = None,
        result_code: Optional[str] = None,
    ) -> int:
        # 【2026-10-07 拆表 · TBD-18】此处曾加过
        #   `AND allocation_rule_id IS NULL` 以防误伤分摊留痕，现已**移除**。
        #
        #   起因：分摊留痕原写 `calc_results`（共表），而作废条件只按宿主
        #   三字段过滤，于是同单据跑一次定价就把分摊留痕置 invalid
        #   （实测 active 由 1 变 0，FR-013 AC「可回放」静默失效）。
        #   终解：分摊留痕迁至独立表 `allocation_results`，**物理隔离**。
        #
        #   为何保留「按宿主、不按 process_code」的原有范围：Spec L973 定的
        #   作废语义是「同一宿主重复定价 → 旧行 invalid」，刻意**不**按
        #   过程区分——同一宿主换过程重算同样应作废旧结果。
        self.ds.execute(
            "UPDATE calc_results SET status = 'invalid', updated_at = ?"
            " WHERE document_type = ? AND document_id = ?"
            "   AND status = 'active'"
            "   AND ((document_line_id IS NULL AND ? IS NULL)"
            "        OR document_line_id = ?)",
            [datetime.now().isoformat(timespec="seconds"),
             document_type, document_id, document_line_id, document_line_id],
        )
        return self._persist_inner(
            process, level, document_type, document_id,
            document_line_id, net, base, calc, lk,
            step_lookups, valid_on, result_code,
        )

    def _persist_inner(
        self,
        process: Dict[str, Any],
        level: str,
        document_type: str,
        document_id: int,
        document_line_id: Optional[int],
        net: float,
        base: float,
        calc: Dict[str, Any],
        lk,
        step_lookups: Optional[Dict[int, Any]] = None,
        valid_on: Optional[str] = None,
        result_code: Optional[str] = None,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        code = result_code or f"CR_{uuid.uuid4().hex[:16]}"

        # 逐槽位的回放信息并入明细（LookupTrace 与 StepResult 序号不对齐，
        # 故按 slot_seq 建索引，明细行用其所在槽位的 trace）
        # lk 为 None 时表示未走查表（无查找序列），此时无候选可回放。
        trace_by_seq = ({t.slot_seq: t for t in lk.traces} if lk else {})

        # 【修 2026-10-06】rate 落**查表命中的费率**，原先硬编码 0。
        # 写回单据单价时优先取 rate（加权场景下 amount/base 才是均价，
        # 直接落 rate 会在多候选取优时给出错误单价）。
        # 取法：首个命中的候选费率；无查表时由 amount/base 派生。
        hit_rate: Optional[float] = None
        if lk and lk.candidates:
            # 【FR-009 2026-10-06】分档记录的 `c.value` 是占位，须取**定档后费率**
            #（否则会把 0 当单价写回单据）
            hit_rate = _to_num(lk.rates.get(lk.candidates[0].id))
            if hit_rate is None:
                hit_rate = _to_num(lk.candidates[0].value)
        if hit_rate is None:
            hit_rate = (net / base) if base not in (None, 0) else None

        cur = self.ds.execute(
            """INSERT INTO calc_results
               (code, document_type, document_id, document_line_id, level,
                process_code, result_semantic, base_level, base_source,
                rolling, rate, base, amount, net_amount, currency, sign,
                sequence, origin, rate_source, price_mode, status,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                code, document_type, document_id, document_line_id, level,
                process["code"], process.get("result_semantic") or "price",
                "header" if level == "header" else "line",
                "pricing_quantity", False,
                hit_rate, base, net, net,
                # 币种取**过程声明的币种**，不取任意价目表的
                # （原实现取 get_rate_tables()[0]，多表时币种是错的）
                process.get("currency") or "CNY",
                "+", 0, "planned", "rate_record", "carry", "active",
                now, now,
            ],
        )
        result_id = cur.lastrowid

        # 明细：逐步骤落一条。
        # running_net_amount 取执行器逐步的累计值（不是恒 0）——
        # 需重放一遍以拿到每步的净额快照。
        running = 0.0
        step_meta = {sr["seq"]: sr for sr in calc["step_results"]}
        by_step = step_lookups or {}
        for sr in calc["step_results"]:
            seq_no = sr["seq"]
            meta = step_meta[seq_no]
            running = float(meta.get("running_net_amount", running))
            # 【W2-C】优先用「按步绑定」的查表结果（折扣/附加费各有独立查找），
            # 无绑定时退回旧的按槽位序号匹配（波次 1 口径）。
            step_lk = by_step.get(seq_no)
            if step_lk is not None:
                hit_json = json.dumps(list(step_lk.hit_ids))
                skip_json = json.dumps(
                    [{"candidate_id": c, "reason": r}
                     for t in step_lk.traces for c, r in t.skipped])
                scales = [s for t in step_lk.traces for s in t.scales]
                lookup_amount = float(step_lk.amount)
            else:
                trace = trace_by_seq.get(seq_no)
                hit_json = json.dumps(trace.hit_ids) if trace else None
                skip_json = json.dumps(
                    [{"candidate_id": c, "reason": r}
                     for c, r in trace.skipped]) if trace else None
                scales = list(trace.scales) if trace else []
                lookup_amount = None
            self.ds.execute(
                """INSERT INTO calc_details
                   (result_id, seq, element_type, rate_type_code, label,
                    unit_price, extended_amount, running_net_amount,
                    rollup_flag, skip_running_price, subtotal_key,
                    base_level, base_source, rolling, base_value,
                    skipped, skip_reason, hit_ids, skipped_candidates,
                    factor_snapshot, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    result_id, seq_no, sr["element_type"],
                    sr.get("rate_type"),
                    f"{seq_no}.{sr['element_type']}",
                    None, sr["amount"], running,
                    bool(meta.get("subtotal_key")), bool(meta.get("skip_running_price")),
                    meta.get("subtotal_key"),
                    "line", "pricing_quantity", False, base,
                    bool(sr.get("skipped")), sr.get("skip_reason"),
                    hit_json, skip_json,
                    json.dumps(
                        {"valid_on": valid_on, "base": base,
                         # 【W2-C】该步查表命中值（折扣/附加费的百分比、价格的费率），
                         # 是"为什么是这个值"的直接依据。
                         "lookup_amount": lookup_amount,
                         # 【FR-009】定档留痕（落到哪一档 / 定出什么费率）。FR-010 要求
                         # 能回答"为什么是这个值"，分档记录的"为什么"含"哪一档"。
                         # 复用既有 json 列承载，**零 schema 改动**。
                         "scales": scales},
                        ensure_ascii=False),
                    now, now,
                ],
            )
        return result_id

    # 结果写回（TBD-9 ②）
    # ------------------------------------------------------------------
    def write_back(
        self,
        document_type: str,
        document_id: int,
        document_line_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """把 active 的定价结果**写回业务单据字段**（TBD-9 ②）。

        映射按 `result_semantic` 约定（`WRITEBACK_MAP`）；字段名在候选集中
        取该单据**实际存在**的第一个，故同一套代码可服务不同命名的单据。

        头级结果（`document_line_id` 为空）只写**金额**字段，不写单价——
        单价是行级概念，无行可挂。

        Args:
            document_type / document_id: 宿主单据
            document_line_id: 行级写回时传入；None = 头级

        Returns:
            {"written": {字段: 值}, "skipped": [原因], "result_ids": [...]}

        Raises:
            PricingError: 单据对象未注册 / 找不到可写字段
        """
        from meta.core.models import registry

        mo = registry.get(document_type)
        if not mo:
            raise PricingError(f"单据对象未注册：{document_type}")

        cols = {f.db_column for f in mo.fields}
        # 【2026-10-07 拆表】原曾按 `allocation_rule_id IS NULL` 排除分摊留痕，
        #   现已移除——分摊留痕迁至独立表 `allocation_results`，本表只属定价，
        #   无需再靠 WHERE 条件区分来源（物理隔离比WHERE 过滤更可靠：
        #   后者漏写一个条件就串数据）。
        results = self._query(
            "SELECT * FROM calc_results WHERE document_type = ?"
            " AND document_id = ? AND status = 'active'",
            (document_type, document_id),
        )
        if document_line_id is not None:
            results = [r for r in results
                       if r.get("document_line_id") == document_line_id]
        if not results:
            return {"written": {}, "skipped": ["无 active 定价结果"],
                    "result_ids": []}

        written: Dict[str, Any] = {}
        skipped: List[str] = []
        upd = getattr(self.ds, "update", None)

        for r in results:
            sem = r.get("result_semantic") or "price"
            rule = WRITEBACK_MAP.get(sem)
            if not rule:
                # 未知语义不猜：落 result_amount，若该单据没有则跳过
                rule = {"unit": None, "amount": "result_amount"}
                skipped.append(f"语义 {sem} 无约定映射，按 result_amount 兜底")

            data: Dict[str, Any] = {}
            amt = _to_num(r.get("amount"))
            if amt is not None:
                tgt = rule["amount"]
                if tgt in cols:
                    data[tgt] = amt
                else:
                    alt = next((c for c in _AMOUNT_CANDIDATES if c in cols),
                               None)
                    if alt:
                        data[alt] = amt
                    else:
                        skipped.append(f"单据无金额字段可写（{sem}）")

            # 单价仅行级写；头级无行可挂
            if document_line_id is not None and rule["unit"]:
                unit_name = rule["unit"]
                if unit_name not in cols:
                    unit_name = next((c for c in _UNIT_CANDIDATES
                                      if c in cols), None)
                if unit_name:
                    u = _to_num(r.get("rate"))
                    if u is None:
                        base = _to_num(r.get("base"))
                        if base not in (None, 0) and amt is not None:
                            u = amt / base
                    if u is not None:
                        data[unit_name] = u

            if not data:
                skipped.append(f"无可写字段（语义 {sem}）")
                continue

            if not callable(upd):
                # 裸 sqlite 连接：直接 UPDATE（列名取自 meta 声明，不接受外部输入）
                sets = ", ".join(f"{k} = ?" for k in data)
                self.ds.execute(
                    f"UPDATE {mo.table_name} SET {sets} WHERE id = ?",
                    list(data.values()) + [document_id],
                )
            else:
                upd(mo.table_name, document_id, data)
            written.update(data)

        return {
            "written": written,
            "skipped": skipped,
            "result_ids": [r["id"] for r in results],
        }

    # ------------------------------------------------------------------
    # 回放查询（IF-002 / FR-010）
    # ------------------------------------------------------------------
    def explain(
        self,
        document_type: str,
        document_id: int,
        document_line_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """回放查询：结果行 + 步骤明细 + 逐层小计 + 计算基四维度。

        对标 IF-002「按document_type + document_id（+ 可选 document_line_id）
        查询 calc_result + calc_detail」。

        【2026-10-07 拆表 · TBD-18】**本方法不再返回分摊留痕**。
        拆分曾短暂提供 `include_allocation=True` 在本方法内联查
        `allocation_results`，等于把共表时的跨域耦合原样搬到服务层——
        表边界建了、查询边界没建。现由 `AllocationService.query_results`
        负责留痕回放（HTTP 出口 `GET /api/v1/allocation/result/...`）。
        """
        sql = "SELECT * FROM calc_results WHERE document_type = ? AND document_id = ?"
        params: List[Any] = [document_type, document_id]
        if document_line_id is not None:
            sql += " AND document_line_id = ?"
            params.append(document_line_id)
        sql += " AND status = 'active' ORDER BY sequence ASC, id ASC"

        results = self._query(sql, tuple(params))
        for r in results:
            details = self._query(
                "SELECT * FROM calc_details WHERE result_id = ? ORDER BY seq ASC",
                (r["id"],),
            )
            for d in details:
                d["hit_ids"] = _loads(d.get("hit_ids"), [])
                d["skipped_candidates"] = _loads(d.get("skipped_candidates"), [])
                d["factor_snapshot"] = _loads(d.get("factor_snapshot"), {})
                # sqlite 的 REAL/INTEGER 在部分驱动下读回为 str/bytes
                # （如 DECIMAL 亲和性），回放接口须归一为数值，
                # 否则前端拿到 "100.0" 字符串做不了算术。
                # 【修 2026-10-06】明细的金额列名是 `extended_amount`（不是
                # `amount`）—— 原归一列表写的是 `amount`，导致明细金额
                # 从未被归一，回放接口返回 None。
                for k in ("extended_amount", "running_net_amount",
                          "base_value", "unit_price"):
                    d[k] = _to_num(d.get(k))
                # boolean 列同样可能被读回 0/1 或 "0"/"1"
                for k in ("rollup_flag", "skip_running_price", "rolling",
                          "skipped"):
                    d[k] = bool(_to_num(d.get(k)) or 0)
            for k in ("amount", "net_amount", "rate", "base"):
                r[k] = _to_num(r.get(k))
            r["details"] = details
            # 逐层小计（rollup_flag 或有 subtotal_key 的行）
            r["subtotals"] = [
                {"seq": d["seq"], "running_net_amount": d["running_net_amount"],
                 "subtotal_key": d.get("subtotal_key")}
                for d in details
                if d.get("subtotal_key") or d.get("rollup_flag")
            ]
        return {
            "document_type": document_type,
            "document_id": document_id,
            "document_line_id": document_line_id,
            "results": results,
        }
