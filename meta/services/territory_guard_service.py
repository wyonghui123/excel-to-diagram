# -*- coding: utf-8 -*-
"""区域守卫 —— 区域树成环与销售员区域分配的写入不变量。

依据: meta/schemas/territory.yaml 头注释
      meta/schemas/salesperson_territory_assignment.yaml 头注释
      docs/superpowers/specs/2026-10-25-sales-order-wave2-detailed-plan.md §7.4

落点划分:
  R-TER-1  parent_id 不得成环 —— `validate_territory_write`（沿 parent_id 逐级上溯，
           命中自身即判环；深度超过 yaml 声明的 max_depth 同样拒绝）
  R-TER-2  同一销售员同一 effective_from 至多一条主区域
           —— 唯一索引 `uq_sta_primary`（部分唯一）兜底，写时不做查询
  R-TER-3  停用区域不影响既有分配，但不再被新的分配引用
           —— `validate_assignment_write`（只在新建或改区域时调用，见拦截器）

另校验分配有效期：`effective_to` 不含端点，填了就必须晚于 `effective_from`。

查询失败一律 fail-open + WARNING（沿用 payment_term_guard / currency_rate_guard 口径）：
读侧守卫不应因一次瞬时查询异常把整条写入路径打死。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与其他守卫同一限制）。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_TERRITORY_TABLE = 'territories'

# 与 territory.yaml hierarchy_level.max_depth 对齐
_MAX_DEPTH = 10


def _is_blank(value: Any) -> bool:
    return value is None or value == ''


class TerritoryGuardError(Exception):
    """区域写入被拒。`rule` 供前端定位提示，`field_name` 指向出错的列。"""

    def __init__(self, message: str, rule: str = '', field_name: str = ''):
        super().__init__(message)
        self.message = message
        self.rule = rule
        self.field_name = field_name


class TerritoryGuardService:
    """区域树与销售员区域分配的服务层校验。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ── R-TER-1 ────────────────────────────────────────────────────────────
    def validate_territory_write(self, data: dict, exclude_id: Any = None) -> None:
        """校验 parent_id 不成环（`exclude_id` 为被更新记录的 id）。"""
        parent_id = data.get('parent_id')
        if _is_blank(parent_id):
            return
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            raise TerritoryGuardError(
                '上级区域必须是有效的区域记录', rule='territory_parent_invalid',
                field_name='parent_id')

        if exclude_id is not None and str(parent_id) == str(exclude_id):
            raise TerritoryGuardError(
                '上级区域不能是自己', rule='territory_parent_cycle',
                field_name='parent_id')

        # 上溯链里出现自身即说明新增的父边闭合了环
        chain = {str(exclude_id)} if exclude_id is not None else set()
        cursor = parent_id
        depth = 0
        try:
            while not _is_blank(cursor):
                if str(cursor) in chain:
                    raise TerritoryGuardError(
                        '上级区域形成环，请调整层级', rule='territory_parent_cycle',
                        field_name='parent_id')
                chain.add(str(cursor))
                depth += 1
                if depth > _MAX_DEPTH:
                    raise TerritoryGuardError(
                        '区域层级超过 %s 层，请调整层级' % _MAX_DEPTH,
                        rule='territory_parent_depth', field_name='parent_id')
                rows = self.ds.query(
                    'SELECT parent_id FROM %s WHERE id = ?' % _TERRITORY_TABLE,
                    (cursor,))
                # 上层不存在时交给真外键拦截，此处不再上溯
                cursor = rows[0].get('parent_id') if rows else None
        except TerritoryGuardError:
            raise
        except Exception as e:  # 读侧异常 → fail-open
            logger.warning('[territory] 校验上级区域链失败: %s', e)

    # ── R-TER-3 + 分配有效期 ───────────────────────────────────────────────
    def validate_assignment_write(self, data: dict, exclude_id: Any = None) -> None:
        """校验分配有效期与区域启用状态（R-TER-3）。"""
        effective_from = data.get('effective_from')
        effective_to = data.get('effective_to')
        if (not _is_blank(effective_from) and not _is_blank(effective_to)
                and str(effective_to) <= str(effective_from)):
            raise TerritoryGuardError(
                '失效日必须晚于生效日', rule='assignment_date_range',
                field_name='effective_to')

        territory_id = data.get('territory_id')
        if _is_blank(territory_id):
            return

        try:
            rows = self.ds.query(
                'SELECT status FROM %s WHERE id = ?' % _TERRITORY_TABLE,
                (territory_id,))
        except Exception as e:  # 读侧异常 → fail-open
            logger.warning('[territory] 校验区域状态失败: %s', e)
            return

        if not rows:
            return  # 悬空引用交给真外键

        if rows[0].get('status') != 'active':
            raise TerritoryGuardError(
                '区域已停用，不能再分配给销售员', rule='territory_inactive',
                field_name='territory_id')
