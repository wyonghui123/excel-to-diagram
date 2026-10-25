# -*- coding: utf-8 -*-
"""计量单位数量换算 —— 两层模型（物料级例外 + 组内标准）。

依据:
  docs/superpowers/specs/2026-10-24-uom-conversion-model-design.md
  meta/services/uom_conversion_guard_service.py（同两张换算表）

读法:
  item_uom_conversions —— 1 个 uom_id = factor 个 items.base_uom（物料级例外，允许跨组）
  uom_conversions      —— 1 个 uom_id = factor 个 uom_groups.base_uom_id（组内标准）

优先级:
  1) 物料级：两个端点都能折到该物料的基本单位时生效；
  2) 组内：两个端点同组，且都能折到组基本单位。
  换算一律经基本单位中转，不做单位间直连。

无法判定（缺数据 / 查询失败）返回 None，由调用方决定 fail-open 还是报错。
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ITEM_TABLE = 'items'
UOM_TABLE = 'uoms'
GROUP_TABLE = 'uom_groups'
ITEM_CONV_TABLE = 'item_uom_conversions'
GROUP_CONV_TABLE = 'uom_conversions'


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _to_decimal(value: Any) -> Optional[Decimal]:
    if _is_blank(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class UomQuantityService:
    """单位间数量换算。查询方法可覆写，便于单测注入。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def convert(self, item_id: Any, qty: Any,
                from_uom_id: Any, to_uom_id: Any) -> Optional[Decimal]:
        """把 `qty` 从 `from_uom_id` 换算为 `to_uom_id`；无法换算返回 None。"""
        amount = _to_decimal(qty)
        if amount is None or _is_blank(from_uom_id) or _is_blank(to_uom_id):
            return None
        if str(from_uom_id) == str(to_uom_id):
            return amount
        factor, _ = self.resolve(item_id, from_uom_id, to_uom_id)
        if factor is None:
            return None
        return amount * factor

    def is_compatible(self, item_id: Any, uom_a: Any,
                      uom_b: Any) -> Optional[bool]:
        """两个单位能否换算。True / False 为确定结论，None 为数据不足。"""
        if _is_blank(uom_a) or _is_blank(uom_b):
            return None
        if str(uom_a) == str(uom_b):
            return True
        factor, determinable = self.resolve(item_id, uom_a, uom_b)
        if factor is not None:
            return True
        return False if determinable else None

    def resolve(self, item_id: Any, from_uom_id: Any,
                to_uom_id: Any) -> Tuple[Optional[Decimal], bool]:
        """返回 (换算率, 是否可确定)。缺数据 / 查询失败 → (None, False)。"""
        item = self._one(
            f"SELECT id, base_uom FROM {ITEM_TABLE} WHERE id = ?", [item_id])
        item_base = item.get('base_uom') if item else None

        # 1) 物料级例外
        from_item = self._item_factor(item_id, from_uom_id, item_base)
        to_item = self._item_factor(item_id, to_uom_id, item_base)
        if from_item is not None and to_item is not None:
            return self._ratio(from_item, to_item), True

        # 2) 组内标准换算
        uoms = self._fetch_uoms([from_uom_id, to_uom_id])
        if uoms is None or str(from_uom_id) not in uoms \
                or str(to_uom_id) not in uoms:
            return None, False
        from_group = uoms[str(from_uom_id)].get('uom_group_id')
        to_group = uoms[str(to_uom_id)].get('uom_group_id')
        if _is_blank(from_group) or _is_blank(to_group) \
                or str(from_group) != str(to_group):
            return None, True

        group = self._one(
            f"SELECT id, base_uom_id FROM {GROUP_TABLE} WHERE id = ?",
            [from_group])
        if group is None:
            return None, False
        group_base = group.get('base_uom_id')
        if _is_blank(group_base):
            return None, True

        from_group_factor = self._group_factor(
            from_group, from_uom_id, group_base)
        to_group_factor = self._group_factor(from_group, to_uom_id, group_base)
        if from_group_factor is None or to_group_factor is None:
            return None, True
        return self._ratio(from_group_factor, to_group_factor), True

    # ---------- 折算因子 ----------

    def _item_factor(self, item_id: Any, uom_id: Any,
                     item_base: Any) -> Optional[Decimal]:
        """`uom_id` 折合多少个物料基本单位；无物料级换算行时返回 None。"""
        if not _is_blank(item_base) and str(uom_id) == str(item_base):
            return Decimal(1)
        row = self._one(
            f"SELECT factor FROM {ITEM_CONV_TABLE} "
            "WHERE item_id = ? AND uom_id = ?", [item_id, uom_id])
        return _to_decimal(row.get('factor')) if row else None

    def _group_factor(self, group_id: Any, uom_id: Any,
                      group_base: Any) -> Optional[Decimal]:
        """`uom_id` 折合多少个组基本单位；无组内换算行时返回 None。"""
        if str(uom_id) == str(group_base):
            return Decimal(1)
        row = self._one(
            f"SELECT factor FROM {GROUP_CONV_TABLE} "
            "WHERE uom_group_id = ? AND uom_id = ?", [group_id, uom_id])
        return _to_decimal(row.get('factor')) if row else None

    @staticmethod
    def _ratio(from_factor: Decimal, to_factor: Decimal) -> Optional[Decimal]:
        if to_factor == 0:
            return None
        return from_factor / to_factor

    # ---------- 查询（可覆写，便于单测注入）----------

    def _fetch_uoms(self, ids: List[Any]) -> Optional[Dict[str, Dict[str, Any]]]:
        placeholders = ', '.join('?' * len(ids))
        rows = self._query(
            f"SELECT id, uom_group_id FROM {UOM_TABLE} "
            f"WHERE id IN ({placeholders})", ids)
        if rows is None:
            return None
        return {str(row.get('id')): row for row in rows}

    def _one(self, sql: str, params: list) -> Optional[Dict[str, Any]]:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _query(self, sql: str, params: list) -> Optional[List[Dict[str, Any]]]:
        try:
            return self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → 交由调用方决定 fail-open / 报错
            logger.warning(f'[uom_quantity] 查询失败: {e}')
            return None
