# -*- coding: utf-8 -*-
"""外部价源取数接口占位（桩）。

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md
      §4 D9（外部价格源：手工覆盖桩 + 适配器接口占位）
      §10.11「不做外部承运商 / 服务商 API 对接」

定位：这是**取数接口占位**，不是定价链的一部分。
      · 本期**不接入** `pricing_determination_service` / `pricing_service`，
        定价判定仍走既有链路，一行都不改。
      · 唯一可用实现是 `ManualOverrideAdapter`（读 `external_rate_sources`
        的手工覆盖字段），保证「外部取价」在真实集成缺席时有确定的占位行为。
      · 真实外部集成（Platts / LME / ICE / 通用指数）到来时，
        新增 `ExternalRateAdapter` 子类并注册进 `ADAPTERS` 即可替换，
        调用方无需改动。

取值口径（手工覆盖）：
  1) 按 `source_code`（为空则按 `sku`）精确匹配 `external_rate_sources.code`；
  2) 无记录 或 `override_rate` 为 NULL → 无报价（返回 None）；
  3) `on_date` 早于 `override_valid_from` / 晚于 `override_valid_to` → 无报价；
  4) 命中 → {'rate': override_rate, 'currency': currency,
             'on_date': on_date, 'source': code}。

桩的「静默降级」：查询异常不外抛，一律按「无报价」处理（返回 None）——
占位期不应该因为一次查询失败把上层取价流程打死；真实集成再按需收紧。
"""

from typing import Any, Dict, Optional

EXTERNAL_SOURCE_UNSUPPORTED = 'EXTERNAL_SOURCE_UNSUPPORTED'


class ExternalRateSourceError(Exception):
    """外部价源错误；code 为稳定错误码，供上层映射。"""

    def __init__(self, message: str, code: str = EXTERNAL_SOURCE_UNSUPPORTED):
        super().__init__(message)
        self.code = code


class ExternalRateAdapter:
    """外部价源适配器接口桩。子类实现 fetch_quote。"""

    name = ''

    def fetch_quote(self, sku, qty, currency, on_date):
        """返回 {'rate': float, 'currency': str, 'on_date': str, 'source': str} 或 None（无报价）。"""
        raise NotImplementedError


class ManualOverrideAdapter(ExternalRateAdapter):
    """手工覆盖适配器 —— 读 `external_rate_sources` 的可空覆盖字段组。"""

    name = 'manual_override'

    TABLE = 'external_rate_sources'
    COLUMNS = [
        'code',
        'override_rate',
        'override_valid_from',
        'override_valid_to',
        'override_reason',
    ]

    def __init__(self, data_source, source_code: Optional[str] = None):
        self.ds = data_source
        self.source_code = source_code

    def fetch_quote(self, sku, qty, currency, on_date):
        """见模块 docstring 的 4 步口径；任何异常都按「无报价」处理，不外抛。"""
        try:
            code = self.source_code or sku
            if not code:
                return None
            rows = self.ds.query(
                "SELECT {cols} FROM {table} WHERE code = ?".format(
                    cols=', '.join(self.COLUMNS), table=self.TABLE),
                [code])
            if not rows:
                return None
            # 内存库测试表由用例自建，列可能不全 —— 一律 row.get 容错
            row = rows[0]
            rate = row.get('override_rate')
            if rate is None:
                return None
            on_date_str = str(on_date)[:10]
            valid_from = row.get('override_valid_from')
            valid_to = row.get('override_valid_to')
            if valid_from is not None and on_date_str < str(valid_from)[:10]:
                return None
            if valid_to is not None and on_date_str > str(valid_to)[:10]:
                return None
            return {
                'rate': float(rate),
                'currency': currency,
                'on_date': on_date,
                'source': row.get('code') or code,
            }
        except Exception:
            return None


ADAPTERS = {'manual_override': ManualOverrideAdapter}


def get_adapter(name, data_source=None):
    """按适配器名取实例；未实现的适配器 → ExternalRateSourceError。"""
    adapter_cls = ADAPTERS.get(name)
    if adapter_cls is None:
        raise ExternalRateSourceError(
            "外部价源适配器未实现：{0}（本期仅有手工覆盖桩，真实外部集成未接入）".format(name))
    return adapter_cls(data_source)
