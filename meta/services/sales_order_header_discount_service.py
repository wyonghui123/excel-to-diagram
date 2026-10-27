# -*- coding: utf-8 -*-
"""销售订单抬头折扣 / 附加费 —— 计算与按行分摊写回。

依据:
  docs/superpowers/specs/2026-10-26-sales-order-billing-and-header-discount-spec.md
    §4.1 不变量 / §4.2 过程 PRICE_STD_HDR_DISC / §4.3 抬头结果口径 /
    §4.5 分摊 / §4.6 幂等 / §4.7 留痕口径 / §4.10 验算

口径:
  行基额   base_i = net_amount_i − header_discount_amount_i − header_surcharge_amount_i
           （`SalesOrderAmountService.recompute_line` 写的 net 已叠加两调整列，
             回算即得未被抬头调整过的行基额。选「回算」而非「apply 前清零」：
             清零会破坏已落库净额，回算无副作用且 compute 可重复调用）
  抬头基额 base   = Σ base_i
  折扣    D = round(base × header_discount_percent  / 100, 币种精度)
  附加费  S = round(base × header_surcharge_percent / 100, 币种精度)
  分摊    同号基额（各行全正或全负）：
            d_i = plan(|D|, abs(base_i), scale=精度, rounding='round')
            s_i = plan(|S|, abs(base_i), scale=精度, rounding='round')
            （plan 只摊正量；方向在下一步按行还原）
          混合号基额（同时含正行与负行）：
            share_i = base_i × pct / 100（含符号，先不舍入）
            r_i = round(share_i, 精度)；尾差 D − Σ r_i 逐最小货币单位补到
                  abs(base_i) 最大（并列取 line id 最小）的行
            （同号口径按 |base_i| 摊绝对值会让负行的方向再翻一次，
              Σ 行调整额只等于两端绝对值之差，不再等于 −D）
  符号还原 同号：hdr_disc_adj_i = −sign(base_i) × d_i
                hdr_sur_adj_i  = +sign(base_i) × s_i
          混合：hdr_disc_adj_i = −r_i，hdr_sur_adj_i = +r_i
                （r_i 本身已带符号，正行的折扣为负、负行为正）
  净额     net_final_i = base_i + hdr_disc_adj_i + hdr_sur_adj_i
  抬头快照 header_discount_amount  = −D
          header_surcharge_amount = +S
          （§4.1「Σ hdr_disc_adj_i = −D」，故抬头快照与行调整额同号同值）

分工:
  compute 只计算 + 落 `calc_results`（4 步各一行，code 确定性），
          **不写** `sales_orders.header_discount_amount / header_surcharge_amount`；
  apply   才写业务字段（行两列 + 抬头两列）与 `allocation_results` 留痕。
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from meta.services.allocation_service import AllocationService, plan
from meta.services.sales_order_amount_service import SalesOrderAmountService

logger = logging.getLogger(__name__)

DOCUMENT_TYPE = 'sales_order'
PROCESS_CODE = 'PRICE_STD_HDR_DISC'
RULE_CODE = 'AR_HDR_DISC_BY_NET'
DEFAULT_CURRENCY = 'CNY'

_STEP_BASE = 10
_STEP_DISCOUNT = 15
_STEP_SURCHARGE = 18
_STEP_ROUND = 20

_RATE_DISCOUNT = 'RT_DISC_HEADER'
_RATE_SURCHARGE = 'RT_SURCHARGE_HEADER'

_ZERO = Decimal('0')
_HUNDRED = Decimal('100')


def _dec(value: Any) -> Decimal:
    if value is None or value == '':
        return _ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _ZERO


def _round(value: Decimal, decimals: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def _float_or_none(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _sign_of(value: Decimal) -> str:
    return '-' if value < 0 else '+'


def _direction(value: Decimal) -> Decimal:
    """基额方向：正 → +1，负 → -1（0 不参与分摊，恒取 +1）。"""
    return Decimal('-1') if value < 0 else Decimal('1')


class HeaderDiscountError(ValueError):
    """抬头折扣/附加费无法计算或分摊（如整单无可用基额）。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


class SalesOrderHeaderDiscountService:
    """抬头折扣/附加费的计算（compute）与写回（apply）。

    覆写 `_load_order` / `_lines_for_order` / `_write_order` / `_write_line` 等
    即可注入测试数据（不依赖真实库），与 `SalesOrderAmountService` 同风格。
    """

    def __init__(self, data_source, amount_service=None,
                 allocation_service=None):
        self.ds = data_source
        self.amount = amount_service or SalesOrderAmountService(data_source)
        self.alloc = allocation_service or AllocationService(data_source)

    # ------------------------------------------------------------------
    # compute：算 D / S + 落 4 步抬头结果（不写业务快照）
    # ------------------------------------------------------------------
    def compute(self, order_id: Any) -> Dict[str, Any]:
        """按抬头百分比算整单折扣/附加费，落 `calc_results` 并返回结果。

        【不写业务快照】`sales_orders.header_discount_amount /
        header_surcharge_amount` 只在 apply 里写：compute 可被反复调用
        （预览 / 校验），若顺手写快照，未 apply 的预览就会污染账面。
        """
        order = self._load_order(order_id)
        if not order:
            raise HeaderDiscountError(
                f'销售订单 #{order_id} 不存在',
                field_name='order_id', rule='ORDER_NOT_FOUND')

        decimals = self.amount._currency_decimals(order.get('currency_id'))
        currency = self._currency_code(order.get('currency_id'))

        base = _ZERO
        for line in self._lines_for_order(order_id):
            base += self._base_of(line)

        disc_pct = _dec(order.get('header_discount_percent'))
        sur_pct = _dec(order.get('header_surcharge_percent'))
        discount = _round(base * disc_pct / _HUNDRED, decimals)
        surcharge = _round(base * sur_pct / _HUNDRED, decimals)
        net_before_round = base - discount + surcharge
        net_final = _round(net_before_round, decimals)

        result_ids = self._write_header_results(
            order_id, currency, disc_pct, sur_pct,
            base, discount, surcharge, net_before_round, net_final,
        )
        return {
            'order_id': order_id,
            'base_amount': base,
            'discount_amount': discount,
            'surcharge_amount': surcharge,
            'currency': currency,
            'header_result_ids': result_ids,
        }

    def _write_header_results(self, order_id, currency, disc_pct, sur_pct,
                              base, discount, surcharge,
                              net_before_round, net_final) -> List[Any]:
        """按 `PRICE_STD_HDR_DISC` 4 步各落一行头级 `calc_results`。

        【code 确定性 + 就地 upsert】code 取 `CR_HD_{order_id}_{seq}`，
        已存在则 UPDATE、不存在则 INSERT——与 spec §4.3「可 upsert/替换而非
        堆叠」一致；主键得以稳定，留痕 `parent_id` 不再随重算漂移。
        """
        steps = [
            {'seq': _STEP_BASE, 'element_type': 'formula',
             'rate_type_code': None, 'rate': None,
             'base': base, 'amount': base, 'net_amount': base,
             'sign': '+', 'description': '抬头基价：Σ 行基额'},
            {'seq': _STEP_DISCOUNT, 'element_type': 'formula',
             'rate_type_code': _RATE_DISCOUNT, 'rate': disc_pct,
             'base': base, 'amount': -discount,
             'net_amount': base - discount, 'sign': '-',
             'description': '抬头折扣：按百分比整单下浮'},
            {'seq': _STEP_SURCHARGE, 'element_type': 'formula',
             'rate_type_code': _RATE_SURCHARGE, 'rate': sur_pct,
             'base': base - discount, 'amount': surcharge,
             'net_amount': base - discount + surcharge, 'sign': '+',
             'description': '抬头附加费：按百分比整单上浮'},
            {'seq': _STEP_ROUND, 'element_type': 'round',
             'rate_type_code': None, 'rate': None,
             'base': net_before_round,
             'amount': net_final - net_before_round, 'net_amount': net_final,
             'sign': _sign_of(net_final), 'description': '按币种精度四舍五入'},
        ]

        semantic = self._procedure_semantic()

        now = datetime.now().isoformat(timespec='seconds')
        result_ids = []
        for step in steps:
            code = f'CR_HD_{order_id}_{step["seq"]}'
            values = [
                DOCUMENT_TYPE, order_id, None, 'header',
                PROCESS_CODE, semantic,
                step['rate_type_code'], step['element_type'],
                'header', 'value', 1, _float_or_none(step['rate']),
                float(step['base']), float(step['amount']),
                float(step['net_amount']), currency, step['sign'],
                step['seq'], 'planned', 'active',
                step['description'],
            ]
            existing = self.ds.query(
                'SELECT id FROM calc_results WHERE code = ?', [code])
            if existing:
                # 就地更新：保留主键 → allocation_results.parent_id 不随重算漂移
                self.ds.execute(
                    """UPDATE calc_results SET
                       document_type=?, document_id=?, document_line_id=?, level=?,
                       process_code=?, result_semantic=?, rate_type_code=?,
                       element_type=?, base_level=?, base_source=?, rolling=?,
                       rate=?, base=?, amount=?, net_amount=?, currency=?,
                       sign=?, sequence=?, origin=?, status=?, description=?,
                       updated_at=?
                       WHERE id=?""",
                    values + [now, existing[0].get('id')],
                )
                result_ids.append(existing[0].get('id'))
            else:
                cur = self.ds.execute(
                    """INSERT INTO calc_results
                       (code, document_type, document_id, document_line_id, level,
                        process_code, result_semantic, rate_type_code, element_type,
                        base_level, base_source, rolling, rate, base, amount,
                        net_amount, currency, sign, sequence, origin, status,
                        description, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [code] + values + [now, now],
                )
                result_ids.append(cur.lastrowid)
        return result_ids

    def _procedure_semantic(self) -> str:
        try:
            rows = self.ds.query(
                'SELECT result_semantic FROM calc_procedures WHERE code = ?',
                [PROCESS_CODE])
        except Exception as exc:
            logger.debug('[header_discount] 读取过程语义失败: %s', exc)
            return 'price'
        return (rows[0].get('result_semantic') if rows else None) or 'price'

    # ------------------------------------------------------------------
    # apply：分摊写回行 + 抬头快照 + 分摊留痕
    # ------------------------------------------------------------------
    def apply(self, order_id: Any) -> Dict[str, Any]:
        """事务边界：compute（落 4 步结果）+ apply（行/抬头快照 + 留痕）原子提交。

        spec §4.6 要求「删除重建在同一事务内」——数据源为自动提交模式，
        故整段包事务；中途异常一律回滚，不留「留痕删了没重建」的半状态。
        嵌套调用时 `transaction()` 自动并入外层事务（datasource 的嵌套守卫）。
        """
        with self.ds.transaction():
            return self._apply(order_id)

    def _apply(self, order_id: Any) -> Dict[str, Any]:
        """把抬头折扣/附加费按行基额分摊到行，并写抬头快照与留痕。

        【零额短路】D == S == 0 时清零行/抬头调整列并重算，返回 applied=0：
        此时无钱可摊，仍须清掉上一次 apply 留下的行调整额，否则净额偏。
        【无基额】有 D/S 但所有 `abs(base_i) == 0` → 抛
        `HEADER_DISCOUNT_ZERO_BASE`，不写业务字段（§4.5）。
        """
        computed = self.compute(order_id)
        discount = computed['discount_amount']
        surcharge = computed['surcharge_amount']
        currency = computed['currency']
        header_ids = computed['header_result_ids']

        order = self._load_order(order_id)
        decimals = self.amount._currency_decimals(order.get('currency_id'))
        base_list = [(line, self._base_of(line))
                     for line in self._lines_for_order(order_id)]

        if discount == 0 and surcharge == 0:
            self._clear_adjustments(order_id, base_list)
            self._delete_traces(order_id)
            return {
                'order_id': order_id,
                'discount_amount': discount,
                'surcharge_amount': surcharge,
                'allocated_lines': 0,
                'applied': 0,
                'header_result_ids': header_ids,
                'line_result_ids': [],
            }

        weighted = [(line, base_i) for line, base_i in base_list
                    if abs(base_i) > 0]
        if not weighted:
            raise HeaderDiscountError(
                '整单行基额合计为 0，抬头折扣/附加费无法按行分摊',
                field_name='header_discount_percent',
                rule='HEADER_DISCOUNT_ZERO_BASE')

        # 基额同时含正行与负行时必须按「有符号份额」摊：plan 只摊正量，
        # 再按行符号还原会让负行的方向翻两次，Σ 行调整额只等于两端
        # 绝对值之差（如 +1000 / -500 折 10% 摊出 -16.67 而非 -50）。
        mixed = (any(base_i < 0 for _, base_i in weighted)
                 and any(base_i > 0 for _, base_i in weighted))
        if mixed:
            disc_share = self._split_mixed(
                weighted, _dec(order.get('header_discount_percent')),
                discount, decimals)
            sur_share = self._split_mixed(
                weighted, _dec(order.get('header_surcharge_percent')),
                surcharge, decimals)
            # 留痕只存绝对值（方向由组级 sign 表达，§4.7）；
            # 业务行调整额则由份额自身符号决定。
            disc_of = {line_id: abs(v) for line_id, v in disc_share.items()}
            sur_of = {line_id: abs(v) for line_id, v in sur_share.items()}
            disc_adj_of = {line_id: -v for line_id, v in disc_share.items()}
            sur_adj_of = dict(sur_share)
        else:
            weights = [abs(base_i) for _, base_i in weighted]
            disc_parts = plan(abs(discount), weights,
                              scale=decimals, rounding='round')
            sur_parts = plan(abs(surcharge), weights,
                             scale=decimals, rounding='round')
            disc_of = {line['id']: part
                       for (line, _), part in zip(weighted, disc_parts)}
            sur_of = {line['id']: part
                      for (line, _), part in zip(weighted, sur_parts)}
            disc_adj_of = {line['id']: -_direction(base_i) * disc_of[line['id']]
                           for line, base_i in weighted}
            sur_adj_of = {line['id']: _direction(base_i) * sur_of[line['id']]
                          for line, base_i in weighted}

        for line, base_i in base_list:
            if abs(base_i) > 0:
                disc_adj = disc_adj_of[line['id']]
                sur_adj = sur_adj_of[line['id']]
            else:
                disc_adj = _ZERO
                sur_adj = _ZERO
            self._write_line(line['id'], disc_adj, sur_adj)

        for line, _ in base_list:
            self.amount.recompute_line(line['id'])
        self.amount.recompute_order(order_id)
        self._write_order(order_id, -discount, surcharge)

        self._delete_traces(order_id)
        rule = self._load_rule()
        if not rule:
            raise HeaderDiscountError(
                f'分摊规则 {RULE_CODE} 未配置，无法留痕',
                field_name='allocation_rule_id',
                rule='HEADER_DISCOUNT_RULE_MISSING')

        step_ids = self._step_ids(order_id)
        line_result_ids: List[Any] = []
        if discount != 0:
            line_result_ids += self._record_group(
                order_id, currency, rule,
                step_ids.get(_STEP_DISCOUNT),
                abs(discount), disc_of, weighted, sign='-')
        if surcharge != 0:
            line_result_ids += self._record_group(
                order_id, currency, rule,
                step_ids.get(_STEP_SURCHARGE),
                abs(surcharge), sur_of, weighted, sign='+')

        return {
            'order_id': order_id,
            'discount_amount': discount,
            'surcharge_amount': surcharge,
            'allocated_lines': len(weighted),
            'applied': 1,
            'header_result_ids': header_ids,
            'line_result_ids': line_result_ids,
        }

    def _split_mixed(self, weighted, percent, total, decimals):
        """混合号基额的有符号份额分摊：Σ 份额精确等于 total。

        share_i = base_i × pct / 100 先不舍入，再按币种精度四舍五入；
        浮点/舍入产生的尾差 `total − Σ share_i` 逐最小货币单位补到
        abs(base_i) 最大（并列取 line id 最小）的行，保证守恒。
        """
        pct = _dec(percent)
        shares = [_round(base_i * pct / _HUNDRED, decimals)
                  for _, base_i in weighted]
        residual = total - sum(shares, _ZERO)
        if residual != 0:
            quantum = Decimal(1).scaleb(-decimals)
            units = int((residual / quantum).to_integral_value(
                rounding=ROUND_HALF_UP))
            target = sorted(
                range(len(weighted)),
                key=lambda i: (-abs(weighted[i][1]),
                               weighted[i][0].get('id') or 0),
            )[0]
            shares[target] += quantum * units
        return {line['id']: share
                for (line, _), share in zip(weighted, shares)}

    def _clear_adjustments(self, order_id: Any, base_list) -> None:
        for line, _ in base_list:
            self._write_line(line['id'], _ZERO, _ZERO)
        for line, _ in base_list:
            self.amount.recompute_line(line['id'])
        self._write_order(order_id, _ZERO, _ZERO)
        self.amount.recompute_order(order_id)

    def _record_group(self, order_id, currency, rule, calc_result_id,
                      total, parts_of, weighted, sign) -> List[Any]:
        """写一组留痕（1 头 + N 行），返回行级留痕 id。

        【amount 存绝对值】留痕的「方向」由 `sign` 表达（折扣 '-' / 附加费
        '+'），故 amount 只记量；行金额与头金额同用绝对值（§4.7）。
        【行行父记录】§4.7 要求行行 `parent_id` 挂「头行留痕 id」，而该 id
        只有插入头行后才有；故先按头级 calc_result.id 写入，再回填本组行行。
        """
        if calc_result_id is None:
            raise HeaderDiscountError(
                '抬头定价结果缺失，无法挂接分摊留痕',
                field_name='process_code', rule='HEADER_RESULT_MISSING')

        rows = [line for line, _ in weighted]
        values = [parts_of[line['id']] for line, _ in weighted]
        recorded = self.alloc.record_allocation_results(
            DOCUMENT_TYPE, order_id, values, rows, total, rule,
            charge_source=DOCUMENT_TYPE,
            source_document_type=DOCUMENT_TYPE,
            source_document_id=order_id,
            target=rule.get('target') or 'cost',
            currency=currency,
            parent_id=calc_result_id,
            basis_field='net_amount',
            rounding='round',
            origin='planned',
            line_sign=sign,
        )
        header_result_id = recorded['header_result_id']
        self.ds.execute(
            "UPDATE allocation_results SET parent_id = ?"
            " WHERE document_type = ? AND document_id = ? AND level = 'line'"
            "   AND parent_id = ? AND origin = 'planned'",
            [header_result_id, DOCUMENT_TYPE, order_id, calc_result_id])
        return recorded['line_result_ids']

    def _delete_traces(self, order_id: Any) -> None:
        """删本订单本规则的计划内留痕（幂等：重复 apply 不累积）。"""
        self.ds.execute(
            "DELETE FROM allocation_results"
            " WHERE document_type = ? AND document_id = ? AND origin = 'planned'"
            "   AND allocation_rule_id ="
            "       (SELECT id FROM allocation_rules WHERE code = ?)",
            [DOCUMENT_TYPE, order_id, RULE_CODE])

    def _step_ids(self, order_id: Any) -> Dict[int, Any]:
        rows = self.ds.query(
            "SELECT id, sequence FROM calc_results"
            " WHERE document_type = ? AND document_id = ?"
            "   AND level = 'header' AND process_code = ?",
            [DOCUMENT_TYPE, order_id, PROCESS_CODE])
        return {int(row['sequence']): row['id'] for row in rows}

    # ------------------------------------------------------------------
    # 读取 / 写入（可覆写，便于单测注入）
    # ------------------------------------------------------------------
    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, order_type_id, order_date, currency_id, '
            'header_discount_percent, header_surcharge_percent '
            'FROM sales_orders WHERE id = ?', [order_id])
        return rows[0] if rows else None

    def _lines_for_order(self, order_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT id, line_no, net_amount, header_discount_amount, '
            'header_surcharge_amount FROM sales_order_lines '
            'WHERE order_id = ? ORDER BY line_no, id', [order_id])

    def _load_rule(self) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, code, basis, rounding, target FROM allocation_rules '
            'WHERE code = ?', [RULE_CODE])
        return rows[0] if rows else None

    def _currency_code(self, currency_id: Any) -> str:
        if currency_id in (None, ''):
            return DEFAULT_CURRENCY
        try:
            rows = self.ds.query(
                'SELECT code FROM currencies WHERE id = ?', [currency_id])
        except Exception as exc:
            logger.warning('[header_discount] 读取币种失败: %s', exc)
            return DEFAULT_CURRENCY
        code = rows[0].get('code') if rows else None
        return str(code).upper() if code else DEFAULT_CURRENCY

    def _write_line(self, line_id: Any, discount_adj: Decimal,
                    surcharge_adj: Decimal) -> None:
        self.ds.execute(
            "UPDATE sales_order_lines SET header_discount_amount = ?, "
            "header_surcharge_amount = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            [float(discount_adj), float(surcharge_adj), line_id])

    def _write_order(self, order_id: Any, discount_amount: Decimal,
                     surcharge_amount: Decimal) -> None:
        self.ds.execute(
            "UPDATE sales_orders SET header_discount_amount = ?, "
            "header_surcharge_amount = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            [float(discount_amount), float(surcharge_amount), order_id])

    @staticmethod
    def _base_of(line: Dict[str, Any]) -> Decimal:
        return (_dec(line.get('net_amount'))
                - _dec(line.get('header_discount_amount'))
                - _dec(line.get('header_surcharge_amount')))
