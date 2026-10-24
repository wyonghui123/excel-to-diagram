# -*- coding: utf-8 -*-
"""币种汇率守卫 —— 单向存储与币对一致性校验（R1 / R2 / R3）。

依据: docs/superpowers/specs/2026-10-24-currency-rate-domain/spec.md
      §3 FR-005 ~ FR-007、§9.3 守卫规则表

落点：
  R1 自反禁止        —— `validate_rate_write`（currency_id ≠ to_currency_id）
  R2 同日镜像行禁止  —— `validate_rate_write`（同 rate_type + valid_from，无序币对只能一行）
  R3 双币种须启用    —— `validate_rate_write`（源 / 目标币种均须 active）
  R4 rate > 0 且 ≤12 位小数 —— 字段级 `constraints: numeric_range`，
      由 `MetadataDrivenValidator._check_numeric_range` 执行，不在本服务内重复；
  有向四元组唯一     —— 唯一索引 `idx_currency_rate_key`。

R2 必须放在应用层的原因：DB 唯一索引只能表达
`(rate_type, currency_id, to_currency_id, valid_from)` 的**有向**组合，
无法表达「无序币对 {A,B} 同一生效日只允许一行」；反向行若不拦，同一事实会被表达两次，
读侧（直接 vs 取倒数）将出现两个可能的答案。

查询失败一律 fail-open + WARNING（沿用 uom_conversion 守卫口径）：
读侧守卫不应因一次瞬时查询异常把整条写入路径打死。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CurrencyRateGuardError(ValueError):
    """汇率守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


class CurrencyRateGuardService:
    """汇率行写入前的跨对象校验。

    覆写 `_fetch_currency` / `_count_same_pair` 即可注入测试数据（不依赖真实库）。
    """

    CURRENCY_TABLE = 'currencies'
    RATE_TABLE = 'currency_rates'

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def validate_rate_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """汇率行创建 / 更新前校验 R1 / R3 / R2。

        `exclude_id`：更新场景传入当前行 id，避免把自己算成重复行。
        """
        currency_id = data.get('currency_id')
        to_currency_id = data.get('to_currency_id')

        # 缺字段交给必填校验兜底，不在此处报错
        if currency_id is None or to_currency_id is None:
            return

        # R1：禁止自反
        if str(currency_id) == str(to_currency_id):
            raise CurrencyRateGuardError(
                '源币种与目标币种不能相同（同币种换算率恒为 1，无需定义）',
                field_name='目标币种', rule='self_pair')

        # R3：两个币种都必须处于启用态
        self._ensure_currency_active(currency_id, '源币种', 'currency_id')
        self._ensure_currency_active(to_currency_id, '目标币种', 'to_currency_id')

        # R2：同一 (类型, 生效日) 下无序币对只能有一行（双向查重）
        rate_type = data.get('rate_type') or 'spot'
        valid_from = _date_key(data.get('valid_from'))
        if valid_from is None:
            return  # 缺生效日交给必填校验
        dup = self._count_same_pair(rate_type, currency_id, to_currency_id,
                                    valid_from, exclude_id)
        if dup:
            raise CurrencyRateGuardError(
                '该币对在该汇率类型与生效日期下已存在汇率（含反向行）；'
                '同一天只维护一个方向，反向汇率由系统取倒数',
                field_name='目标币种', rule='mirror_pair')

    # ---------- 查询（可覆写，便于单测注入）----------

    def _one(self, sql: str, params: list) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open（不阻断正常写入）
            logger.warning(f'[currency_rate_guard] 查询失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_currency(self, currency_id: Any) -> Optional[Dict[str, Any]]:
        return self._one(
            f"SELECT id, code, status FROM {self.CURRENCY_TABLE} WHERE id = ?",
            [currency_id])

    def _count_same_pair(self, rate_type: str, currency_id: Any, to_currency_id: Any,
                         valid_from: str, exclude_id: Any) -> int:
        sql = (
            f"SELECT COUNT(*) AS cnt FROM {self.RATE_TABLE} "
            "WHERE rate_type = ? AND valid_from = ? "
            "AND ((currency_id = ? AND to_currency_id = ?) "
            "  OR (currency_id = ? AND to_currency_id = ?))"
        )
        params = [rate_type, valid_from,
                  currency_id, to_currency_id,
                  to_currency_id, currency_id]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        row = self._one(sql, params)
        if not row:
            return 0
        try:
            return int(row.get('cnt') or 0)
        except (TypeError, ValueError):
            return 0

    # ---------- 内部 ----------

    def _ensure_currency_active(self, currency_id: Any, label: str, field: str) -> None:
        currency = self._fetch_currency(currency_id)
        if currency is None:
            return  # 币种不存在时交给 FK 存在性校验兜底
        if currency.get('status') != 'active':
            code = currency.get('code') or currency_id
            raise CurrencyRateGuardError(
                f'{label}「{code}」已停用，不能维护汇率',
                field_name=label, rule='currency_inactive')


def _date_key(value: Any) -> Optional[str]:
    """把 date / datetime / 字符串统一成 'YYYY-MM-DD'，与库内 date 字段存储口径一致。"""
    if value is None:
        return None
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    text = str(value).strip()
    return text[:10] if text else None
