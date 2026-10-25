# -*- coding: utf-8 -*-
"""定价确定服务 —— 规则解析 + 行级取价编排

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
      §3.6 解析算法、§3.6 失败原因码、§3.7 写回规则、§3.8 不变量

职责边界:
  本服务只回答两个问题，不做业务写入（不碰 sales_order / sales_order_line）：
    1) `resolve`   —— 哪个「定价确定规则」命中，用哪张价目表 / 哪个过程 / 哪个序列
    2) `determine_line` —— 对一行（物料 + 数量）取价，产出 `unit_price` 与回放留痕

  订单侧的字段写回与变更触发（W1-R1~R9）由接线层承担（见 sales_order 定价接线），
  本服务不依赖订单对象，便于单测直接注入内存 SQLite。

失败一律不抛异常（W1-R3）：返回 `pricing_status='failed'` + `reason`，
由调用方决定是否降级保存。
"""
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from meta.core.calc_procedure_executor import CalculationError
from meta.core.lookup_resolver import ResolutionError
from meta.services.pricing_service import PricingError, PricingService

logger = logging.getLogger(__name__)

# 失败原因码（§3.6）。一律写入 price_trace.reason，不抛异常。
REASON_NO_DETERMINATION = 'NO_DETERMINATION'
REASON_NO_RATE_TABLE = 'NO_RATE_TABLE'
REASON_CURRENCY_MISMATCH = 'CURRENCY_MISMATCH'
REASON_NO_CANDIDATE = 'NO_CANDIDATE'
REASON_ZERO_QTY = 'ZERO_QTY'

#: 单价保留位数（本期只做 CNY / USD，两者均为 2 位）
PRICE_SCALE = Decimal('0.01')


def _date_key(value: Any) -> Optional[str]:
    """date / datetime / 字符串统一成 'YYYY-MM-DD'，与库内 date 存储口径一致。"""
    if value is None or value == '':
        return None
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    text = str(value).strip()
    return text[:10] if text else None


def _num(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class PricingDeterminationService:
    """按「销售组织 + 单据类型 + 基准日 + 币种」解析价目表与过程，并对行取价。"""

    def __init__(self, data_source, pricing_service: Optional[PricingService] = None):
        self.ds = data_source
        self.pricing = pricing_service or PricingService(data_source)

    # ------------------------------------------------------------------
    # 1) 规则解析
    # ------------------------------------------------------------------
    def resolve(
        self,
        *,
        sales_org_id: Optional[int] = None,
        order_type_id: Optional[int] = None,
        price_date: Any = None,
        currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """返回命中规则与价目表/过程/序列；未命中时给 `reason`。

        Returns:
            {"matched": bool, "reason": str|None, "rule": dict|None,
             "rate_table": dict|None, "procedure_code": str|None,
             "sequence_code": str|None}
        """
        on_date = _date_key(price_date) or date.today().isoformat()

        rows = self._query(
            "SELECT * FROM pricing_determinations"
            " WHERE status = 'active'"
            "   AND (valid_from IS NULL OR valid_from = '' OR valid_from <= ?)"
            "   AND (valid_to   IS NULL OR valid_to   = '' OR valid_to   >  ?)"
            "   AND (sales_org_id  IS NULL OR sales_org_id  = ?)"
            "   AND (order_type_id IS NULL OR order_type_id = ?)",
            [on_date, on_date, sales_org_id, order_type_id],
        )
        if not rows:
            return self._miss(REASON_NO_DETERMINATION)

        # 打分：组织精确 / 类型精确优于通配；同分按 seq、id 升序（§3.6 第 2 步）
        def _score(rule: Dict[str, Any]):
            return (
                (1 if rule.get('sales_org_id') is None else 0)
                + (1 if rule.get('order_type_id') is None else 0),
                self._int(rule.get('seq'), 10 ** 9),
                self._int(rule.get('id'), 10 ** 9),
            )

        rule = sorted(rows, key=_score)[0]

        # 规则级币种为空 = 跟随订单币种
        rule_currency = (rule.get('currency') or '').strip().upper()
        order_currency = (currency or '').strip().upper()
        if rule_currency and order_currency and rule_currency != order_currency:
            return self._miss(REASON_CURRENCY_MISMATCH, rule=rule)

        procedure = self._one(
            'SELECT code FROM calc_procedures WHERE id = ?',
            [rule.get('calc_procedure_id')])
        if not procedure:
            return self._miss(REASON_NO_DETERMINATION, rule=rule)

        sequence_code = None
        if rule.get('lookup_sequence_id') is not None:
            sequence = self._one(
                'SELECT code FROM lookup_sequences WHERE id = ?',
                [rule.get('lookup_sequence_id')])
            sequence_code = sequence.get('code') if sequence else None

        table, reason = self._resolve_rate_table(rule, sales_org_id, order_currency)
        if table is None:
            return self._miss(reason, rule=rule)

        return {
            'matched': True,
            'reason': None,
            'rule': rule,
            'rate_table': table,
            'procedure_code': procedure['code'],
            'sequence_code': sequence_code,
        }

    def _resolve_rate_table(
        self,
        rule: Dict[str, Any],
        sales_org_id: Optional[int],
        order_currency: str,
    ):
        """定表（§3.6 第 3 步）。返回 (rate_table|None, reason|None)。"""
        pinned_id = rule.get('rate_table_id')
        if pinned_id is not None:
            table = self._one(
                'SELECT * FROM rate_tables WHERE id = ?', [pinned_id])
            if not table or table.get('status') != 'approved':
                return None, REASON_NO_RATE_TABLE
            table_currency = (table.get('currency') or '').strip().upper()
            if order_currency and table_currency and table_currency != order_currency:
                return None, REASON_CURRENCY_MISMATCH
            if not self._table_in_scope(table, sales_org_id):
                return None, REASON_NO_RATE_TABLE
            return table, None

        if not order_currency:
            return None, REASON_NO_RATE_TABLE

        rows = self._query(
            "SELECT * FROM rate_tables"
            " WHERE status = 'approved' AND currency = ?"
            "   AND (owner_org_id IS NULL OR owner_org_id = ?)"
            " ORDER BY (owner_org_id IS NULL) ASC, id DESC LIMIT 1",
            [order_currency, sales_org_id],
        )
        if not rows:
            return None, REASON_NO_RATE_TABLE
        return rows[0], None

    @staticmethod
    def _table_in_scope(table: Dict[str, Any], sales_org_id: Optional[int]) -> bool:
        owner = table.get('owner_org_id')
        if owner is None:
            return True
        if sales_org_id is None:
            return False
        return str(owner) == str(sales_org_id)

    # ------------------------------------------------------------------
    # 2) 行级取价
    # ------------------------------------------------------------------
    def determine_line(
        self,
        *,
        item_id: Any,
        qty: Any,
        price_date: Any = None,
        currency: Optional[str] = None,
        sales_org_id: Optional[int] = None,
        order_type_id: Optional[int] = None,
        document_id: Optional[int] = None,
        document_line_id: Optional[int] = None,
        persist: bool = False,
    ) -> Dict[str, Any]:
        """对一行取价，返回单价与回放留痕（不抛异常）。

        Returns:
            {"pricing_status": "determined"|"failed",
             "reason": str|None,
             "unit_price": float|None,
             "amount": float|None,
             "trace": {...}}
        """
        qty_num = _num(qty)
        if qty_num is None or qty_num <= 0:
            return self._failed(REASON_ZERO_QTY)
        if item_id is None:
            return self._failed(REASON_NO_CANDIDATE)

        resolved = self.resolve(
            sales_org_id=sales_org_id,
            order_type_id=order_type_id,
            price_date=price_date,
            currency=currency,
        )
        if not resolved['matched']:
            return self._failed(resolved['reason'], rule=resolved.get('rule'))

        table = resolved['rate_table']
        on_date = _date_key(price_date) or date.today().isoformat()
        trace = {
            'matched_rule_code': (resolved['rule'] or {}).get('code'),
            'rate_table_code': table.get('code'),
            'procedure_code': resolved['procedure_code'],
            'candidates': 0,
            'hit_ids': [],
            'result_id': None,
            'reason': None,
        }

        candidates = self.pricing.load_candidates(table['id'], valid_on=on_date)
        trace['candidates'] = len(candidates)
        if not candidates:
            return self._failed(REASON_NO_CANDIDATE, rule=resolved['rule'],
                                trace=trace)

        common = dict(
            process_code=resolved['procedure_code'],
            rate_table_id=table['id'],
            slot_keys=[{'item_id': item_id}],
            base=qty_num,
            sequence_code=resolved['sequence_code'],
            document_type='sales_order',
            document_id=document_id,
            document_line_id=document_line_id,
            valid_on=on_date,
        )
        try:
            # 先干跑：无命中（键不匹配）时不留下 0 元结果行，只写失败原因
            dry = self.pricing.price_line(persist=False, **common)
            if not dry['hit_ids']:
                trace['reason'] = REASON_NO_CANDIDATE
                return self._failed(REASON_NO_CANDIDATE, rule=resolved['rule'],
                                    trace=trace)

            result = dry
            if persist and document_id is not None:
                result = self.pricing.price_line(persist=True, **common)
        except (PricingError, ResolutionError, CalculationError) as exc:
            logger.info('[pricing_determination] 取价不可完成：%s', exc)
            trace['reason'] = REASON_NO_CANDIDATE
            return self._failed(REASON_NO_CANDIDATE, rule=resolved['rule'],
                                trace=trace)

        amount = float(result['net_amount'])
        trace['hit_ids'] = list(result['hit_ids'])
        trace['result_id'] = result['result_id']

        unit_price = float(
            (Decimal(str(amount)) / Decimal(str(qty_num))).quantize(
                PRICE_SCALE, rounding=ROUND_HALF_UP)
        )
        return {
            'pricing_status': 'determined',
            'reason': None,
            'unit_price': unit_price,
            'amount': amount,
            'trace': trace,
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    @staticmethod
    def _int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _miss(reason: str, rule: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            'matched': False,
            'reason': reason,
            'rule': rule,
            'rate_table': None,
            'procedure_code': None,
            'sequence_code': None,
        }

    @staticmethod
    def _failed(reason: str, rule: Optional[Dict[str, Any]] = None,
                trace: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        out_trace = trace or {}
        out_trace.setdefault('matched_rule_code', (rule or {}).get('code'))
        out_trace.setdefault('rate_table_code', None)
        out_trace.setdefault('procedure_code', None)
        out_trace.setdefault('candidates', 0)
        out_trace.setdefault('hit_ids', [])
        out_trace.setdefault('result_id', None)
        out_trace['reason'] = reason
        return {
            'pricing_status': 'failed',
            'reason': reason,
            'unit_price': None,
            'amount': None,
            'trace': out_trace,
        }

    def _query(self, sql: str, params: List[Any]) -> List[Dict[str, Any]]:
        return self.ds.query(sql, params)

    def _one(self, sql: str, params: List[Any]) -> Optional[Dict[str, Any]]:
        rows = self._query(sql, params)
        return rows[0] if rows else None
