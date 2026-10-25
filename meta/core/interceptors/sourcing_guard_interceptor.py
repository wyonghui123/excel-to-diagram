# -*- coding: utf-8 -*-
"""供应来源规则写前守卫拦截器 —— 4 张表写入入口的配置一致性校验。

覆盖范围:
  sourcing_rule_line       创建 / 更新  —— 类型—引用一致、组织职能 / vendor 关系、rank 分摊合计
  sourcing_rule_assignment 创建 / 更新  —— specificity_rank 派生、作用域合法、启用态作用域唯一
  sourcing_mode_policy     创建 / 更新  —— 启用态 (物料组, 物料, 组织) 唯一
  sourcing_rule            仅更新        —— 启用时规则下必须至少有一条来源行

优先级 43（紧随 ConstraintValidationInterceptor 42，先于 HierarchyValidationInterceptor 45）；
其余对象 / 动作零开销短路。

[边界] 守卫只做「写入前可判定的配置矛盾」，**不做求值** —— 候选集求解与资格过滤
归 `meta/services/sourcing_service.py` 的 SourcingResolver；此处重复实现必然漂移。
拦截器链只覆盖 bo_api 写路径，manage_api 与 Excel 导入绕过拦截器链（与
uom_conversion_guard / party_relation_guard 同一限制）。
"""

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from meta.core.interceptors.base import Interceptor
from meta.services.sourcing_service import (
    SOURCING_ALLOCATION_NOT_100,
    SOURCING_ALL_LINES_INELIGIBLE,
    SOURCING_ASSIGNMENT_CONFLICT,
    SOURCING_SOURCE_REF_MISMATCH,
    SOURCE_INTERNAL_LOCATION,
    SOURCE_INTERNAL_ORG,
    SOURCE_PRODUCTION,
    SOURCE_SUPPLIER,
    SourcingError,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

LINE_OBJECT = 'sourcing_rule_line'
ASSIGNMENT_OBJECT = 'sourcing_rule_assignment'
POLICY_OBJECT = 'sourcing_mode_policy'
RULE_OBJECT = 'sourcing_rule'

_WRITE_ACTIONS = ('crud_create', 'crud_update')

#: 来源类型 → 必填引用字段（与 SourcingResolver 的 missing_source_ref 同口径）
_SOURCE_REF_FIELD = {
    SOURCE_INTERNAL_ORG: 'source_org_id',
    SOURCE_PRODUCTION: 'source_org_id',
    SOURCE_INTERNAL_LOCATION: 'source_location_id',
    SOURCE_SUPPLIER: 'supplier_party_id',
}

#: 来源类型 → 组织必须具备的职能
_SOURCE_FUNCTION = {
    SOURCE_INTERNAL_ORG: 'inventory',
    SOURCE_PRODUCTION: 'manufacturing',
}

#: 分摊比例合计的允许误差（与 resolver.validate_rule 一致）
_PCT_TOLERANCE = Decimal('0.01')
_HUNDRED = Decimal('100')


# ---------------------------------------------------------------------------
# 模块私有辅助：空值 / 数值 / 查询
# ---------------------------------------------------------------------------

def _is_blank(value: Any) -> bool:
    """None 与纯空白字符串视为未设置。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _is_empty_ref(value: Any) -> bool:
    """作用域引用的空值口径：None、空串、0 都视为未设置。"""
    if _is_blank(value):
        return True
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    return False


def _same_id(left: Any, right: Any) -> bool:
    """id 比较：DB 整型与入参类型可能不同，统一按字符串比。"""
    return str(left) == str(right)


def _to_decimal(value: Any) -> Decimal:
    """数值转 Decimal；无法解析时按 0 计（合计校验不因此中断）。"""
    if _is_blank(value):
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        logger.warning('[sourcing-guard] 分摊比例无法解析，按 0 计: %r', value)
        return Decimal('0')


def _query_rows(ds, sql: str, params: Optional[list]) -> List[Dict[str, Any]]:
    """参数化查询 → dict 列表（datasource.execute 返回游标）。"""
    cursor = ds.execute(sql, list(params or []))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in rows]


def _count_rows(ds, sql: str, params: Optional[list]) -> int:
    rows = _query_rows(ds, sql, params)
    if not rows:
        return 0
    try:
        return int(rows[0].get('cnt') or 0)
    except (TypeError, ValueError):
        return 0


class SourcingGuardInterceptor(Interceptor):
    """供应来源配置写前守卫（4 张表 / 5 类判定）。"""

    @property
    def priority(self) -> int:
        return 43

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        action = context.action
        if object_id in (LINE_OBJECT, ASSIGNMENT_OBJECT, POLICY_OBJECT):
            return action in _WRITE_ACTIONS
        if object_id == RULE_OBJECT:
            return action == 'crud_update'
        return False

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        params = dict(context.params or {})
        # 更新可能是部分字段：与旧行合并还原「更新后的有效行」
        merged = dict(context.old_data or {})
        merged.update(params)
        ds = context.data_source

        try:
            if object_id == LINE_OBJECT:
                self._guard_line(ds, context, merged)
            elif object_id == ASSIGNMENT_OBJECT:
                self._guard_assignment(ds, context, merged)
            elif object_id == POLICY_OBJECT:
                self._guard_policy(ds, context, merged)
            elif object_id == RULE_OBJECT:
                self._guard_rule(ds, context, merged)
        except SourcingError as exc:
            from meta.core.exceptions import ValidationFailedError

            raise ValidationFailedError(
                message=exc.message,
                details=[{
                    'field_name': self._error_field(object_id),
                    'rule': exc.code,
                    'message': exc.message,
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        pass

    @staticmethod
    def _error_field(object_id: Optional[str]) -> str:
        """报错定位字段：取该对象上与判定最相关的一列。"""
        return {
            LINE_OBJECT: 'source_type',
            ASSIGNMENT_OBJECT: 'scope_type',
            POLICY_OBJECT: 'status',
            RULE_OBJECT: 'status',
        }.get(object_id, 'status')

    # ------------------------------------------------------------------
    # 来源行
    # ------------------------------------------------------------------
    def _guard_line(self, ds, context: 'ActionContext',
                    data: Dict[str, Any]) -> None:
        source_type = str(data.get('source_type') or '').strip()

        # 1) 类型—引用一致
        ref_field = _SOURCE_REF_FIELD.get(source_type)
        if ref_field is not None and _is_blank(data.get(ref_field)):
            raise SourcingError(
                SOURCING_SOURCE_REF_MISMATCH,
                f'来源类型 {source_type} 必须填写 {ref_field}',
                hint='internal_org/production 填 source_org_id；'
                     'internal_location 填 source_location_id；'
                     'supplier 填 supplier_party_id',
            )

        # 2) 职能 / vendor 关系（写入时只看是否存在，有效期由求值阶段判定）
        if source_type in _SOURCE_FUNCTION:
            org_id = data.get('source_org_id')
            if not _is_blank(org_id):
                function_type = _SOURCE_FUNCTION[source_type]
                if _count_rows(
                    ds,
                    'SELECT COUNT(*) AS cnt FROM org_functions '
                    'WHERE org_id = ? AND function_type = ?',
                    [org_id, function_type],
                ) == 0:
                    raise SourcingError(
                        SOURCING_SOURCE_REF_MISMATCH,
                        f'来源组织 #{org_id} 缺少 {function_type} 职能，'
                        f'不能作为 {source_type} 来源',
                        hint=f'请先为该组织维护 {function_type} 职能',
                    )
        elif source_type == SOURCE_SUPPLIER:
            party_id = data.get('supplier_party_id')
            if not _is_blank(party_id):
                if _count_rows(
                    ds,
                    "SELECT COUNT(*) AS cnt FROM party_relations "
                    "WHERE role = 'vendor' AND COALESCE(status, 'active') = 'active' "
                    "AND (party1_id = ? OR party2_id = ?)",
                    [party_id, party_id],
                ) == 0:
                    raise SourcingError(
                        SOURCING_SOURCE_REF_MISMATCH,
                        f'供应商 #{party_id} 缺少有效的 vendor 关系',
                        hint='请先维护该往来方的 vendor 关系',
                    )

        # 3) rank 分摊合计：用「规则下全部持久化行」替换/追加当前待写行后分组累加
        rule_id = data.get('rule_id')
        if _is_blank(rule_id):
            return

        current_id = None
        if context.action == 'crud_update':
            current_id = context.object_id
            if _is_blank(current_id):
                current_id = data.get('id')

        persisted = _query_rows(
            ds,
            'SELECT id, rank, allocation_pct FROM sourcing_rule_lines '
            'WHERE rule_id = ?',
            [rule_id],
        )
        bucket_rows = [
            row for row in persisted
            if current_id is None or not _same_id(row.get('id'), current_id)
        ]
        bucket_rows.append(data)

        totals: Dict[Any, Decimal] = {}
        for row in bucket_rows:
            rank_key = row.get('rank')
            totals[rank_key] = (
                totals.get(rank_key, Decimal('0'))
                + _to_decimal(row.get('allocation_pct'))
            )

        for rank_key, total in totals.items():
            total_q = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if abs(total_q - _HUNDRED) > _PCT_TOLERANCE:
                raise SourcingError(
                    SOURCING_ALLOCATION_NOT_100,
                    f'rank {rank_key} 的分摊比例合计为 {total_q}，应等于 100',
                    hint='同一 rank 下所有来源行的 allocation_pct 必须合计 100',
                )

    # ------------------------------------------------------------------
    # 作用域分配
    # ------------------------------------------------------------------
    def _guard_assignment(self, ds, context: 'ActionContext',
                          data: Dict[str, Any]) -> None:
        scope_type = str(data.get('scope_type') or '').strip()
        ref_id = data.get('scope_ref_id')
        has_dest_org = not _is_empty_ref(data.get('dest_org_id'))

        # 1) 派生 specificity_rank 并写回参数 —— 前端不传、服务端唯一来源
        if context.params is not None:
            context.params['specificity_rank'] = self._derive_specificity_rank(
                scope_type, has_dest_org)

        # 2) 作用域合法
        if scope_type == 'global':
            if not _is_empty_ref(ref_id):
                raise SourcingError(
                    SOURCING_SOURCE_REF_MISMATCH,
                    f'global 作用域的 scope_ref_id 必须为空（当前 {ref_id!r}）',
                    hint='global 作用域不对具体对象限定',
                )
        elif scope_type == 'item':
            self._require_scope_ref(ds, scope_type, ref_id, 'items')
        elif scope_type == 'item_group':
            self._require_scope_ref(ds, scope_type, ref_id, 'item_groups')

        # 3) 启用态作用域唯一
        if not self._is_active_status(data.get('status')):
            return

        current_id = -1
        if context.action == 'crud_update':
            current_id = context.object_id
            if _is_blank(current_id):
                current_id = data.get('id')
            current_id = -1 if _is_blank(current_id) else int(current_id)

        if _count_rows(
            ds,
            "SELECT COUNT(*) AS cnt FROM sourcing_rule_assignments "
            "WHERE status = 'active' AND scope_type = ? "
            "  AND COALESCE(scope_ref_id, 0) = COALESCE(?, 0) "
            "  AND COALESCE(dest_org_id, 0) = COALESCE(?, 0) "
            "  AND COALESCE(dest_location_id, 0) = COALESCE(?, 0) "
            "  AND id <> ?",
            [
                scope_type,
                ref_id,
                data.get('dest_org_id'),
                data.get('dest_location_id'),
                current_id,
            ],
        ) > 0:
            raise SourcingError(
                SOURCING_ASSIGNMENT_CONFLICT,
                '同一作用域（作用域类型 / 引用 / 目标组织 / 目标位置）'
                '已有启用的分配，不能重复配置',
                hint='同一作用域键只能有一条 active 分配，请停用多余分配',
            )

    @staticmethod
    def _derive_specificity_rank(scope_type: str, has_dest_org: bool) -> int:
        """作用域由细到粗的匹配优先级。"""
        if scope_type == 'item':
            return 10 if has_dest_org else 30
        if scope_type == 'item_group':
            return 20 if has_dest_org else 40
        return 50 if has_dest_org else 60

    @staticmethod
    def _require_scope_ref(ds, scope_type: str, ref_id: Any,
                           table: str) -> None:
        """item / item_group 作用域：引用必填且目标对象必须存在。"""
        if _is_empty_ref(ref_id):
            raise SourcingError(
                SOURCING_SOURCE_REF_MISMATCH,
                f'{scope_type} 作用域必须填写 scope_ref_id',
                hint='scope_ref_id 指向物料或物料组 id',
            )
        if _count_rows(
            ds, f'SELECT COUNT(*) AS cnt FROM {table} WHERE id = ?', [ref_id]
        ) == 0:
            raise SourcingError(
                SOURCING_SOURCE_REF_MISMATCH,
                f'{scope_type} 作用域引用的 {table} #{ref_id} 不存在',
                hint=f'scope_ref_id 必须指向已存在的 {table} 记录',
            )

    # ------------------------------------------------------------------
    # 供应方式策略
    # ------------------------------------------------------------------
    def _guard_policy(self, ds, context: 'ActionContext',
                      data: Dict[str, Any]) -> None:
        if not self._is_active_status(data.get('status')):
            return

        current_id = -1
        if context.action == 'crud_update':
            current_id = context.object_id
            if _is_blank(current_id):
                current_id = data.get('id')
            current_id = -1 if _is_blank(current_id) else int(current_id)

        if _count_rows(
            ds,
            "SELECT COUNT(*) AS cnt FROM sourcing_mode_policies "
            "WHERE status = 'active' AND item_group_id = ? "
            "  AND COALESCE(item_id, 0) = COALESCE(?, 0) "
            "  AND org_id = ? AND id <> ?",
            [
                data.get('item_group_id'),
                data.get('item_id'),
                data.get('org_id'),
                current_id,
            ],
        ) > 0:
            raise SourcingError(
                SOURCING_ASSIGNMENT_CONFLICT,
                '同一物料/物料组在该组织已存在启用的供应方式策略',
                hint='同一 (物料组, 物料, 组织) 只能有一条 active 策略，请停用多余记录',
            )

    # ------------------------------------------------------------------
    # 规则头：启用时不能没有来源行
    # ------------------------------------------------------------------
    def _guard_rule(self, ds, context: 'ActionContext',
                    data: Dict[str, Any]) -> None:
        if not self._is_active_status(data.get('status')):
            return
        old_status = str((context.old_data or {}).get('status') or '').strip().lower()
        if old_status == 'active':
            return  # 已是启用态的其它字段更新，不重复校验

        rule_id = context.object_id
        if _is_blank(rule_id):
            rule_id = data.get('id')
        if _is_blank(rule_id):
            return

        if _count_rows(
            ds,
            'SELECT COUNT(*) AS cnt FROM sourcing_rule_lines WHERE rule_id = ?',
            [rule_id],
        ) == 0:
            raise SourcingError(
                SOURCING_ALL_LINES_INELIGIBLE,
                '规则下没有任何来源行，不能启用',
                hint='请先补充至少一条来源行再启用规则',
            )

    @staticmethod
    def _is_active_status(value: Any) -> bool:
        """空状态按 active 兜底（与表默认值一致）。"""
        if _is_blank(value):
            return True
        return str(value).strip().lower() == 'active'
