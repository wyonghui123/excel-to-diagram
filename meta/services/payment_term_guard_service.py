# -*- coding: utf-8 -*-
"""付款条件守卫 —— 分期行写入的跨行 / 跨字段校验（G1 上半 / G3 / G4）。

依据: meta/schemas/payment_term_line.yaml 头注释「到期日计算口径」与「跨行不变量」

落点划分:
  G1  Σ percentage = 100
      —— 写时只硬拦「合计 > 100」（超过必然错误，且不会因逐行录入而误伤）；
         「合计 = 100」是完整性条件，由 `assert_term_complete(term_id)` 在使用前校验。
         原因：子表是逐行 crud_create 保存，若每次写都要求合计=100，两期各 50% 的第二行
         永远无法落库（与 sourcing rank 分摊的逐行校验口径不同 —— 那里允许一次性整组写入）。
  G2  (payment_term_id, seq) 唯一 —— 唯一索引 `idx_payment_term_line_seq` +
      `MetadataDrivenValidator._check_unique_indexes`，不在本服务重复。
  G3  discount_percent 与 discount_days 同时为空或同时有值 —— `validate_line_write`。
  G4  discount_days 必须早于该行到期天数 —— `validate_line_write`；
      仅在该行 fixed_day_of_month 为空时可比（有固定日时到期日依赖具体月份，写时不可判定）。
  G5  percentage 全为正 —— 字段级 `constraints: numeric_range gt 0` 已覆盖。

查询失败一律 fail-open + WARNING（沿用 currency_rate_guard / uom_conversion_guard 口径）：
读侧守卫不应因一次瞬时查询异常把整条写入路径打死。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与其他守卫同一限制）。
"""

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HUNDRED = Decimal('100')
_PCT_TOLERANCE = Decimal('0.0001')
_LINE_TABLE = 'payment_term_lines'


class PaymentTermGuardError(ValueError):
    """付款条件守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _to_decimal(value: Any) -> Decimal:
    if _is_blank(value):
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        logger.warning('[payment_term_guard] 占比无法解析，按 0 计: %r', value)
        return Decimal('0')


class PaymentTermGuardService:
    """付款条件分期行写入前的校验。

    覆写 `_sum_percentage` 即可注入测试数据（不依赖真实库）。
    """

    LINE_TABLE = _LINE_TABLE

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def validate_line_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """分期行创建 / 更新前校验 G3 / G4 / G1（上限）。

        `exclude_id`：更新场景传入当前行 id，避免把自己重复计入合计。
        """
        discount_percent = data.get('discount_percent')
        discount_days = data.get('discount_days')

        # G3：折扣率与折扣天数必须成对
        has_percent = not _is_blank(discount_percent)
        has_days = not _is_blank(discount_days)
        if has_percent != has_days:
            raise PaymentTermGuardError(
                '折扣率与折扣天数必须同时填写或同时留空',
                field_name='discount_days' if has_percent else 'discount_percent',
                rule='discount_pair_mismatch')

        # G4：折扣天数必须早于该行到期天数（仅无固定日时可比）
        if has_percent and _is_blank(data.get('fixed_day_of_month')):
            maturity_days = (
                _to_decimal(data.get('offset_months')) * Decimal('30')
                + _to_decimal(data.get('offset_days'))
            )
            if _to_decimal(discount_days) >= maturity_days:
                raise PaymentTermGuardError(
                    f'折扣天数 {discount_days} 必须早于到期天数 {maturity_days}',
                    field_name='discount_days',
                    rule='discount_not_before_maturity')

        # G1（上半）：合计不得超过 100
        term_id = data.get('payment_term_id')
        if _is_blank(term_id):
            return  # 缺父键交给必填校验兜底
        total = self._sum_percentage(term_id, exclude_id) + _to_decimal(data.get('percentage'))
        total_q = total.quantize(_PCT_TOLERANCE, rounding=ROUND_HALF_UP)
        if total_q > _HUNDRED + _PCT_TOLERANCE:
            raise PaymentTermGuardError(
                f'分期占比合计为 {total_q}，不能超过 100',
                field_name='percentage',
                rule='percentage_over_100')

    def assert_term_complete(self, term_id: Any) -> None:
        """G1（下半）：使用前校验合计 = 100（消费方接线时调用）。"""
        total = self._sum_percentage(term_id)
        total_q = total.quantize(_PCT_TOLERANCE, rounding=ROUND_HALF_UP)
        if abs(total_q - _HUNDRED) > _PCT_TOLERANCE:
            raise PaymentTermGuardError(
                f'付款条件分期占比合计为 {total_q}，应等于 100',
                field_name='percentage',
                rule='percentage_not_100')

    # ---------- 查询（可覆写，便于单测注入）----------

    def _sum_percentage(self, term_id: Any, exclude_id: Any = None) -> Decimal:
        sql = f"SELECT percentage FROM {self.LINE_TABLE} WHERE payment_term_id = ?"
        params = [term_id]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open（不阻断正常写入）
            logger.warning(f'[payment_term_guard] 查询失败: {e}')
            return Decimal('0')
        return sum((_to_decimal(row.get('percentage')) for row in rows or []), Decimal('0'))
