# -*- coding: utf-8 -*-
"""区域守卫 —— 区域树成环与销售员区域分配的写入不变量。

依据: meta/schemas/territory.yaml 头注释
      meta/schemas/salesperson_territory_assignment.yaml 头注释
      docs/superpowers/specs/2026-10-25-sales-order-wave2-detailed-plan.md §7.4

落点划分:
  R-TER-1  parent_id 不得成环 —— `validate_territory_write`（沿 parent_id 逐级上溯，
           命中自身即判环；祖先链深度超过 yaml 声明的 max_depth 同样拒绝）
  R-TER-2  同一销售员同一 effective_from 至多一条主区域
           —— 唯一索引 `uq_sta_primary`（部分唯一）兜底，写时不做查询
  R-TER-3  停用区域不影响既有分配，但不再被新的分配引用
           —— `validate_assignment_write`（只在新建或改区域时调用，见拦截器）
  R-TER-4  level 由父链派生（根为 1），不接受手工值；父节点变更时
           由 `plan_descendant_levels` / `apply_levels` 级联重算整棵子树
  R-TER-6  停用区域不影响既有客户分配，但不再被新的客户分配引用
           —— 与 R-TER-3 同一实现，客户侧分配复用 `validate_assignment_write`

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

    # ── R-TER-1 + R-TER-4 ──────────────────────────────────────────────────
    def validate_territory_write(self, data: dict,
                                 exclude_id: Any = None) -> Any:
        """校验 parent_id 不成环，并返回按父链派生的 level（R-TER-4）。

        返回 None 表示读侧异常 fail-open：调用方不应写入 level。
        """
        parent_id = data.get('parent_id')
        if _is_blank(parent_id):
            return 1
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
            return depth + 1
        except TerritoryGuardError:
            raise
        except Exception as e:  # 读侧异常 → fail-open
            logger.warning('[territory] 校验上级区域链失败: %s', e)
            return None

    # ── R-TER-4 子树级联重算 ────────────────────────────────────────────────
    def plan_descendant_levels(self, territory_id: Any,
                               base_level: int) -> list:
        """BFS 计算子树各节点的新 level，返回 [(id, new_level)]（不写库）。

        只返回 level 实际变化的节点；父节点被移动时由拦截器调用。
        子树任一节点超过层级上限即整体拒绝，避免写一半。
        """
        plan = []
        frontier = {int(territory_id): int(base_level)}
        seen = {int(territory_id)}
        try:
            while frontier:
                ids = list(frontier.keys())
                placeholders = ','.join('?' * len(ids))
                rows = self.ds.query(
                    'SELECT id, parent_id, level FROM %s WHERE parent_id IN (%s)'
                    % (_TERRITORY_TABLE, placeholders), tuple(ids))
                nxt = {}
                for row in rows or []:
                    child_id = row.get('id')
                    if child_id is None:
                        continue
                    try:
                        child_id = int(child_id)
                    except (TypeError, ValueError):
                        continue
                    if child_id in seen:  # 防环
                        continue
                    seen.add(child_id)
                    new_level = frontier[int(row.get('parent_id'))] + 1
                    if new_level > _MAX_DEPTH + 1:
                        raise TerritoryGuardError(
                            '区域层级超过 %s 层，请调整层级' % _MAX_DEPTH,
                            rule='territory_parent_depth', field_name='parent_id')
                    if row.get('level') != new_level:
                        plan.append((child_id, new_level))
                    nxt[child_id] = new_level
                frontier = nxt
        except TerritoryGuardError:
            raise
        except Exception as e:  # 读侧异常 → fail-open（保留旧 level）
            logger.warning('[territory] 重算子树层级失败: %s', e)
            return []
        return plan

    def apply_levels(self, plan: list) -> None:
        """把 plan_descendant_levels 的结果落库；失败只告警，不阻断写入。"""
        for territory_id, level in plan or []:
            try:
                self.ds.execute(
                    'UPDATE %s SET level = ? WHERE id = ?' % _TERRITORY_TABLE,
                    (level, territory_id))
            except Exception as e:  # 展示字段，失败不阻断主写入
                logger.warning('[territory] 更新子树层级失败 id=%s: %s',
                               territory_id, e)

    # ── R-TER-3 / R-TER-6 + 分配有效期 ─────────────────────────────────────
    def validate_assignment_write(self, data: dict, exclude_id: Any = None,
                                  assignee_label: str = '销售员') -> None:
        """校验分配有效期与区域启用状态（R-TER-3 / R-TER-6）。

        `assignee_label` 只影响提示文案：销售员侧与客户侧复用同一校验。
        """
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
                '区域已停用，不能再分配给%s' % assignee_label,
                rule='territory_inactive', field_name='territory_id')
