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
import json
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
#: 折扣后金额为负（W2-C · R-DSC-1）；为负即失败并降级保存
REASON_NEGATIVE_AMOUNT = 'NEGATIVE_AMOUNT'

#: 折扣 / 附加费的费率类型编码（W2-C），用于在回放里汇总调整金额
RATE_TYPE_DISCOUNT = 'RT_DISC_LINE'
RATE_TYPE_SURCHARGE = 'RT_SURCHARGE_LINE'

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
        preferred_rate_table_id: Optional[int] = None,
        allow_currency_conversion: bool = False,
    ) -> Dict[str, Any]:
        """返回命中规则与价目表/过程/序列；未命中时给 `reason`。

        `preferred_rate_table_id` 为客户档案/销售组织指定的价目表：仅当
        approved、币种相符且在组织作用域内时优先采用；否则静默回退既有定表
        规则（客户配置错误不阻断取价，零回归）。

        `allow_currency_conversion=True` 时，规则币种 / 价目表币种与订单币种
        不符不再返回 CURRENCY_MISMATCH，照常返回价目表，由上层按汇率折算（C2）。

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
        if (not allow_currency_conversion
                and rule_currency and order_currency
                and rule_currency != order_currency):
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

        table, reason = self._resolve_rate_table(
            rule, sales_org_id, order_currency, preferred_rate_table_id,
            allow_currency_conversion)
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
        preferred_rate_table_id: Optional[int] = None,
        allow_currency_conversion: bool = False,
    ):
        """定表（§3.6 第 3 步）。返回 (rate_table|None, reason|None)。

        客户价目表只作「优选」：approved / 币种相符 / 组织作用域内三者
        全部满足才采用，任一不满足即静默回退既有规则（零回归）。
        `allow_currency_conversion=True` 时跳过币种相符校验（C2 折算场景）。
        """
        preferred = self._load_preferred_table(
            preferred_rate_table_id, sales_org_id, order_currency,
            allow_currency_conversion)
        if preferred is not None:
            return preferred, None

        pinned_id = rule.get('rate_table_id')
        if pinned_id is not None:
            table = self._one(
                'SELECT * FROM rate_tables WHERE id = ?', [pinned_id])
            if not table or table.get('status') != 'approved':
                return None, REASON_NO_RATE_TABLE
            table_currency = (table.get('currency') or '').strip().upper()
            if (not allow_currency_conversion
                    and order_currency and table_currency
                    and table_currency != order_currency):
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

    def _load_preferred_table(
        self,
        table_id: Optional[int],
        sales_org_id: Optional[int],
        order_currency: str,
        allow_currency_conversion: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """客户指定价目表：仅返回合法表，非法一律视为未指定（回退既有规则）。"""
        if table_id in (None, ''):
            return None
        table = self._one('SELECT * FROM rate_tables WHERE id = ?', [table_id])
        if not table or table.get('status') != 'approved':
            return None
        table_currency = (table.get('currency') or '').strip().upper()
        if (not allow_currency_conversion
                and order_currency and table_currency
                and table_currency != order_currency):
            return None
        if not self._table_in_scope(table, sales_org_id):
            return None
        return table

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
        customer_account_id: Any = None,
        price_date: Any = None,
        currency: Optional[str] = None,
        preferred_rate_table_id: Optional[int] = None,
        sales_org_id: Optional[int] = None,
        order_type_id: Optional[int] = None,
        document_id: Optional[int] = None,
        document_line_id: Optional[int] = None,
        persist: bool = False,
        exchange_rate: Optional[float] = None,
        exchange_rate_type: Optional[str] = None,
        exchange_rate_date: Any = None,
    ) -> Dict[str, Any]:
        """对一行取价，返回单价与回放留痕（不抛异常）。

        槽位键值按命中的查找序列逐槽构造（W2-F）：序列若含「客户 × 物料」
        首槽、本行又带客户时，先按客户价查，未命中自然落「物料」次槽；
        客户为空时**跳过**首槽（不构造 `None` 键值），不影响物料兜底。

        【C2 多币种】价目表币种 ≠ 订单币种时，`exchange_rate`（1 订单币种 =
        exchange_rate 价目表币种）用于把价目表金额折算成订单币种：
        `amount_order = amount_table / exchange_rate`（2 位 ROUND_HALF_UP），
        `unit_price` 由折算后金额重算。汇率缺失则返回 CURRENCY_MISMATCH，
        绝不按 1:1 静默折算。`exchange_rate_type` / `exchange_rate_date` 仅供
        回放留痕（不参与计算）。

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
            preferred_rate_table_id=preferred_rate_table_id,
        )
        if (not resolved['matched']
                and resolved['reason'] == REASON_CURRENCY_MISMATCH
                and _num(exchange_rate) is not None):
            # 币种不符但有可折算汇率：按「允许折算」重解析，照常拿到价目表
            resolved = self.resolve(
                sales_org_id=sales_org_id,
                order_type_id=order_type_id,
                price_date=price_date,
                currency=currency,
                preferred_rate_table_id=preferred_rate_table_id,
                allow_currency_conversion=True,
            )
        if not resolved['matched']:
            return self._failed(resolved['reason'], rule=resolved.get('rule'))

        table = resolved['rate_table']
        on_date = _date_key(price_date) or date.today().isoformat()
        table_currency = (table.get('currency') or '').strip().upper()
        order_currency = (currency or '').strip().upper()
        cross_currency = bool(
            table_currency and order_currency
            and table_currency != order_currency)
        rate = _num(exchange_rate)
        if cross_currency and (rate is None or rate <= 0):
            # 汇率缺失：不得按 1:1 静默折算（W1-R3 降级保存）
            return self._failed(REASON_CURRENCY_MISMATCH,
                                rule=resolved['rule'], trace={
                                    'rate_table_code': table.get('code'),
                                    'procedure_code': resolved['procedure_code'],
                                    'price_currency': table_currency,
                                   })
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
            slot_keys=self._slot_keys(
                resolved['sequence_code'], item_id, customer_account_id,
                sales_org_id),
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
            # 【W2-C · R-DSC-1】折扣/附加费算完为负即失败，不落结果行
            if float(dry['net_amount']) < 0:
                trace['reason'] = REASON_NEGATIVE_AMOUNT
                return self._failed(REASON_NEGATIVE_AMOUNT,
                                    rule=resolved['rule'], trace=trace)

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
        # 【W2-C】行级折扣/附加费汇总（json 内新增两个键，不改表结构）
        trace.update(self._adjustment_amounts(result.get('step_results') or []))
        # 【SO Wave3 · B3】把查表留痕的分档信息汇总进 trace（只补传参，不改算法）
        trace['scales'] = [s for t in (result.get('traces') or [])
                           for s in (t.get('scales') or [])]

        if cross_currency:
            # 【C2】价目表金额 → 订单币种金额；保留 2 位 ROUND_HALF_UP
            table_amount = amount
            amount = float(
                (Decimal(str(table_amount)) / Decimal(str(rate))).quantize(
                    PRICE_SCALE, rounding=ROUND_HALF_UP))
            trace.update({
                'exchange_rate': rate,
                'exchange_rate_type': exchange_rate_type,
                'exchange_rate_date': _date_key(exchange_rate_date),
                'currency_converted': True,
                'price_currency': table_currency,
                'table_amount': table_amount,
            })
        else:
            trace['exchange_rate'] = None

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
    def _slot_keys(self, sequence_code: Optional[str], item_id: Any,
                   customer_account_id: Any,
                   sales_org_id: Any = None) -> List[Optional[Dict[str, Any]]]:
        """按查找序列逐槽构造键值（W2-F · R-KEY-1~3；v152 增组织维度）。

        每槽按其 `key_schema.key_fields` 填因子值；任一因子在本行无值时该槽位置
        `None`（查找引擎跳过该槽，顺序不变）。无法解析序列/键表时退回单槽物料键，
        与波次 1 的既有权口径一致（R-KEY-3）。

        【v152】`sales_org_id` 以因子名 `org_id` 注入 —— 序列首槽若声明了
        `org_id`（KS_ORG_ITEM / KS_ORG_CUST_ITEM），按组织精确匹配；本行无
        销售组织时该槽为 `None` 被跳过，落回物料/客户槽（零回归）。

        【v153 / B4】`customer_group_id` 以同名字段注入 —— 组槽（KS_GROUP_ITEM）
        声明了 `customer_group_id`；客户不属于任何组时该槽为 `None` 被跳过，
        落回客户 / 物料槽（零回归）。
        """
        fallback: List[Optional[Dict[str, Any]]] = [{'item_id': item_id}]
        if not sequence_code:
            return fallback
        row = self._one(
            'SELECT steps FROM lookup_sequences WHERE code = ?', [sequence_code])
        steps = self._json_list((row or {}).get('steps'))
        if not steps:
            return fallback

        values = {'item_id': item_id, 'customer_account_id': customer_account_id,
                  'org_id': sales_org_id,
                  'customer_group_id': self._customer_group_id(
                      customer_account_id)}
        slots: List[Optional[Dict[str, Any]]] = []
        for step in sorted(steps, key=lambda s: self._int(
                (s or {}).get('seq'), 10 ** 9)):
            schema = self._one(
                'SELECT key_fields FROM key_schemas WHERE id = ?',
                [(step or {}).get('key_schema_id')])
            fields = self._json_list((schema or {}).get('key_fields'))
            keys: Optional[Dict[str, Any]] = {}
            for field in fields:
                value = values.get(field)
                if value is None or value == '':
                    keys = None
                    break
                keys[field] = value
            # 空键表或未知因子 → 该槽无从比对，与"无值"同处理
            slots.append(keys or None)
        return slots or fallback

    def _customer_group_id(self, customer_account_id: Any) -> Optional[int]:
        """客户账户 → 业务伙伴组（T2.3 / B4）。

        组的唯一挂载点是关系层（`party_relations.group_id`），账户经
        `relation_id` 指向关系行。无账户 / 无关系 / 无组 / 查询失败
        （如表未建）一律返回 `None` —— 该槽位被跳过，不阻断取价。
        """
        if customer_account_id is None or customer_account_id == '':
            return None
        try:
            row = self._one(
                'SELECT pr.group_id FROM customer_accounts ca'
                ' JOIN party_relations pr ON pr.id = ca.relation_id'
                ' WHERE ca.id = ?', [customer_account_id])
        except Exception:       # 表未建 / 查询失败 → 该槽跳过（不阻断取价）
            return None
        group_id = (row or {}).get('group_id')
        if group_id is None or group_id == '':
            return None
        return group_id

    @staticmethod
    def _adjustment_amounts(step_results: List[Dict[str, Any]]) -> Dict[str, float]:
        """按步骤的净额变化汇总折扣 / 附加费金额（W2-C）。

        折扣/附加费步骤用 `rolling=true`，其 `running_net_amount` 已是**应用后**
        的净额，故调整额 = 与上一步净额的差；符号由步骤落在哪一侧决定。
        """
        discount = surcharge = 0.0
        prev = 0.0
        for sr in step_results:
            if sr.get('skipped'):
                continue
            net = float(sr.get('running_net_amount') or 0.0)
            rate_type = sr.get('rate_type')
            if rate_type == RATE_TYPE_DISCOUNT:
                discount += prev - net
            elif rate_type == RATE_TYPE_SURCHARGE:
                surcharge += net - prev
            prev = net
        return {
            'discount_amount': round(discount, 2),
            'surcharge_amount': round(surcharge, 2),
        }

    @staticmethod
    def _json_list(raw: Any) -> List[Any]:
        if isinstance(raw, list):
            return raw
        if not raw:
            return []
        try:
            loaded = json.loads(raw)
        except (TypeError, ValueError):
            return []
        return loaded if isinstance(loaded, list) else []

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
        out_trace.setdefault('scales', [])
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
