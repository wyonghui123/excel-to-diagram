# -*- coding: utf-8 -*-
"""批次服务 —— 批次主数据的写前校验与必填特性检查。

依据: docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md
      §11.2（表结构）/ §11.3（约束与校验）/ §11.7（特性接入四项）

口径:
  · 身份 `(item_id, org_id, batch_no)`；批次属库存组织，不含 location。
  · `qty > 0`；`qty_uom_id` 必须与物料基本单位同 `uom_group`。
  · 生命周期 `status` 与质量状态 `quality_status` 是两套语义，不合并。
  · `quality_status='blocked'` 时不允许 `status='closed'`（先解冻）。
  · `expiry_date >= date(produced_at)`；`produced_at` 为空时不校验。
  · `potency_pct` 为 0–100 的物理列，不参与 EAV。
  · 父批次单父；禁自指 / 成环（深度 > 10 拒绝）。
  · 批次保存时按 `attribute_scopes(scope_ref='batch')` 与物料分类解析必填特性；
    更新时缺值拒绝。创建时尚无 `batch_id`，不校验（首编辑时补值）。
  · 本服务只读校验，不写业务字段；写路径仍走通用 BO API。

覆写 `_load_item` / `_load_uom` / `_load_batch` / `_item_group_code` 可注入测试数据。
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BATCH_TABLE = 'batches'
ITEM_TABLE = 'items'
UOM_TABLE = 'uoms'
ITEM_GROUP_TABLE = 'item_groups'
VALUE_TABLE = 'batch_attribute_values'
DEFINITION_TABLE = 'attribute_definitions'

STATUS_PLANNED = 'planned'
STATUS_IN_PROCESS = 'in_process'
STATUS_CLOSED = 'closed'
STATUSES = (STATUS_PLANNED, STATUS_IN_PROCESS, STATUS_CLOSED)

QUALITY_UNRESTRICTED = 'unrestricted'
QUALITY_INSPECTION = 'inspection'
QUALITY_BLOCKED = 'blocked'
QUALITY_STATUSES = (QUALITY_UNRESTRICTED, QUALITY_INSPECTION, QUALITY_BLOCKED)

SOURCE_PRODUCTION = 'production'
SOURCE_PURCHASE = 'purchase'
SOURCE_MANUAL = 'manual'
SOURCE_ADJUSTMENT = 'adjustment'
SOURCES = (SOURCE_PRODUCTION, SOURCE_PURCHASE, SOURCE_MANUAL, SOURCE_ADJUSTMENT)

#: 父链最大深度（超过视为成环 / 数据异常）
MAX_PARENT_DEPTH = 10

BATCH_NO_MAX_LENGTH = 60


class BatchError(Exception):
    """批次业务校验错误（拦截器转为 ValidationFailedError）。"""

    def __init__(self, message: str, field_name: Optional[str] = None,
                 rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _text(value: Any) -> str:
    return '' if value is None else str(value).strip()


def _as_int(value: Any) -> Optional[int]:
    if _blank(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any, field_name: str, rule: str) -> Optional[Decimal]:
    if _blank(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise BatchError('%s 必须是数字' % field_name,
                         field_name=field_name, rule=rule)


def _as_date(value: Any, field_name: str) -> Optional[date]:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        raise BatchError('%s 必须是日期' % field_name,
                         field_name=field_name, rule='BATCH_DATE_INVALID')


class BatchService:
    """批次主数据校验（创建 / 更新前的只读检查）。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 批次主校验
    # ------------------------------------------------------------------
    def validate_batch(self, payload: Dict[str, Any],
                       existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """校验批次创建 / 更新，返回归一化后的合并值。"""
        patch = dict(payload or {})
        old = dict(existing or {})
        merged = dict(old)
        merged.update(patch)
        batch_id = _as_int(old.get('id'))

        self._validate_identity(merged)
        self._validate_quantity(merged)
        self._validate_enums(merged)
        self._validate_dates(merged)
        self._validate_potency(merged)
        self._validate_parent(merged, batch_id)

        merged['status'] = _text(merged.get('status') or STATUS_PLANNED).lower()
        merged['quality_status'] = (
            _text(merged.get('quality_status') or QUALITY_UNRESTRICTED).lower())
        merged['source'] = _text(merged.get('source') or SOURCE_MANUAL).lower()

        if (merged['quality_status'] == QUALITY_BLOCKED
                and merged['status'] == STATUS_CLOSED):
            raise BatchError(
                '质量状态为冻结的批次不能关闭，请先解冻。',
                field_name='quality_status', rule='BATCH_BLOCKED_CANNOT_CLOSE')

        if batch_id is not None:
            item_group_code = self._item_group_code(merged.get('item_id'))
            self.validate_required_attributes(
                _as_int(merged.get('tenant_id')) or 0, batch_id, item_group_code)

        return merged

    # ------------------------------------------------------------------
    # 必填特性
    # ------------------------------------------------------------------
    def validate_required_attributes(self, tenant_id: int, batch_id: int,
                                     item_group_code: Optional[str] = None) -> None:
        """校验批次是否已填齐该范围内的必填特性；缺失则拒绝保存。"""
        from meta.services.attribute_scope_service import AttributeScopeService

        required_ids = AttributeScopeService(self.ds).required_attribute_ids(
            tenant_id, 'batch', item_group_code)
        if not required_ids:
            return

        present = self._present_attribute_ids(batch_id, required_ids)
        missing = [aid for aid in required_ids if aid not in present]
        if not missing:
            return

        codes = self._attribute_codes(missing)
        raise BatchError(
            '缺少必填批次特性：%s' % '、'.join(codes or [str(i) for i in missing]),
            field_name='attribute_id',
            rule='BATCH_REQUIRED_ATTRIBUTE_MISSING')

    # ------------------------------------------------------------------
    # 规则
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_identity(merged: Dict[str, Any]) -> None:
        batch_no = _text(merged.get('batch_no'))
        if not batch_no:
            raise BatchError('批次号不能为空。',
                             field_name='batch_no', rule='BATCH_NO_REQUIRED')
        if len(batch_no) > BATCH_NO_MAX_LENGTH:
            raise BatchError('批次号长度不能超过 %d。' % BATCH_NO_MAX_LENGTH,
                             field_name='batch_no', rule='BATCH_NO_REQUIRED')
        if _as_int(merged.get('item_id')) is None:
            raise BatchError('批次必须指定物料。',
                             field_name='item_id', rule='BATCH_ITEM_REQUIRED')
        if _as_int(merged.get('org_id')) is None:
            raise BatchError('批次必须指定库存组织。',
                             field_name='org_id', rule='BATCH_ORG_REQUIRED')

    def _validate_quantity(self, merged: Dict[str, Any]) -> None:
        qty = _decimal(merged.get('qty'), 'qty', 'BATCH_QTY_INVALID')
        if qty is None or qty <= 0:
            raise BatchError('批次数量必须大于 0。',
                             field_name='qty', rule='BATCH_QTY_INVALID')

        uom_id = _as_int(merged.get('qty_uom_id'))
        if uom_id is None:
            raise BatchError('批次必须指定数量单位。',
                             field_name='qty_uom_id', rule='BATCH_UOM_REQUIRED')

        item = self._load_item(_as_int(merged.get('item_id')))
        if not item:
            return
        item_uom_group = self._uom_group(item.get('base_uom'))
        row_uom_group = self._uom_group(uom_id)
        if item_uom_group is None or row_uom_group is None:
            return  # 缺数据时 fail-open，不阻断主数据维护
        if item_uom_group != row_uom_group:
            raise BatchError(
                '数量单位与物料基本单位不在同一单位组。',
                field_name='qty_uom_id', rule='BATCH_UOM_GROUP')

    @staticmethod
    def _validate_enums(merged: Dict[str, Any]) -> None:
        status = _text(merged.get('status') or STATUS_PLANNED).lower()
        if status not in STATUSES:
            raise BatchError(
                '未知的批次生命周期状态 %s；只允许 %s。' % (status, '/'.join(STATUSES)),
                field_name='status', rule='BATCH_STATUS_INVALID')

        quality = _text(
            merged.get('quality_status') or QUALITY_UNRESTRICTED).lower()
        if quality not in QUALITY_STATUSES:
            raise BatchError(
                '未知的质量状态 %s；只允许 %s。' % (quality, '/'.join(QUALITY_STATUSES)),
                field_name='quality_status', rule='BATCH_QUALITY_STATUS_INVALID')

        source = _text(merged.get('source') or SOURCE_MANUAL).lower()
        if source not in SOURCES:
            raise BatchError(
                '未知的批次来源 %s；只允许 %s。' % (source, '/'.join(SOURCES)),
                field_name='source', rule='BATCH_SOURCE_INVALID')

    @staticmethod
    def _validate_dates(merged: Dict[str, Any]) -> None:
        produced = _as_date(merged.get('produced_at'), 'produced_at')
        expiry = _as_date(merged.get('expiry_date'), 'expiry_date')
        if produced and expiry and expiry < produced:
            raise BatchError(
                '有效期不能早于产出时间。',
                field_name='expiry_date', rule='BATCH_EXPIRY_INVALID')

    @staticmethod
    def _validate_potency(merged: Dict[str, Any]) -> None:
        potency = _decimal(merged.get('potency_pct'), 'potency_pct',
                           'BATCH_POTENCY_INVALID')
        if potency is None:
            return
        if potency < 0 or potency > 100:
            raise BatchError(
                '效价必须在 0–100 之间。',
                field_name='potency_pct', rule='BATCH_POTENCY_INVALID')

    def _validate_parent(self, merged: Dict[str, Any],
                         batch_id: Optional[int]) -> None:
        parent_id = _as_int(merged.get('parent_batch_id'))
        if parent_id is None:
            return
        if batch_id is not None and parent_id == batch_id:
            raise BatchError('父批次不能指向自身。',
                             field_name='parent_batch_id',
                             rule='BATCH_PARENT_SELF')

        visited = {batch_id} if batch_id is not None else set()
        current = parent_id
        depth = 0
        while current is not None:
            if current in visited:
                raise BatchError('父批次链存在成环。',
                                 field_name='parent_batch_id',
                                 rule='BATCH_PARENT_CYCLE')
            parent = self._load_batch(current)
            if parent is None:
                raise BatchError(
                    '父批次 %s 不存在。' % current,
                    field_name='parent_batch_id', rule='BATCH_PARENT_MISSING')
            visited.add(current)
            depth += 1
            if depth > MAX_PARENT_DEPTH:
                raise BatchError(
                    '父批次链深度超过 %d。' % MAX_PARENT_DEPTH,
                    field_name='parent_batch_id', rule='BATCH_PARENT_CYCLE')
            current = _as_int(parent.get('parent_batch_id'))

    # ------------------------------------------------------------------
    # 查询辅助（可覆写注入）
    # ------------------------------------------------------------------
    def _load_item(self, item_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if item_id is None:
            return None
        return self._row(f'SELECT id, code, base_uom, item_group_id '
                         f'FROM {ITEM_TABLE} WHERE id = ? LIMIT 1', [item_id])

    def _load_uom(self, uom_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if uom_id is None:
            return None
        return self._row(f'SELECT id, code, uom_group_id '
                         f'FROM {UOM_TABLE} WHERE id = ? LIMIT 1', [uom_id])

    def _load_batch(self, batch_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if batch_id is None:
            return None
        return self._row(f'SELECT id, parent_batch_id, item_id, org_id '
                         f'FROM {BATCH_TABLE} WHERE id = ? LIMIT 1', [batch_id])

    def _item_group_code(self, item_id: Any) -> Optional[str]:
        item = self._load_item(_as_int(item_id))
        if not item:
            return None
        group_id = _as_int(item.get('item_group_id'))
        if group_id is None:
            return None
        row = self._row(f'SELECT code FROM {ITEM_GROUP_TABLE} '
                        'WHERE id = ? LIMIT 1', [group_id])
        return (row or {}).get('code')

    def _uom_group(self, uom_id: Any) -> Optional[int]:
        uom = self._load_uom(_as_int(uom_id))
        if not uom:
            return None
        return _as_int(uom.get('uom_group_id'))

    def _present_attribute_ids(self, batch_id: Any,
                               attribute_ids: List[int]) -> set:
        if not attribute_ids:
            return set()
        placeholders = ','.join('?' * len(attribute_ids))
        rows = self._query(
            f'SELECT DISTINCT attribute_id FROM {VALUE_TABLE} '
            f'WHERE batch_id = ? AND attribute_id IN ({placeholders})',
            [batch_id, *attribute_ids]) or []
        return {_as_int(row.get('attribute_id')) for row in rows}

    def _attribute_codes(self, attribute_ids: List[int]) -> List[str]:
        if not attribute_ids:
            return []
        placeholders = ','.join('?' * len(attribute_ids))
        rows = self._query(
            f'SELECT id, code FROM {DEFINITION_TABLE} '
            f'WHERE id IN ({placeholders})', list(attribute_ids)) or []
        codes = {_as_int(row.get('id')): row.get('code') for row in rows}
        return [codes.get(aid) or str(aid) for aid in attribute_ids]

    def _row(self, sql: str, params) -> Optional[Dict[str, Any]]:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _query(self, sql: str, params) -> List[Dict[str, Any]]:
        if self.ds is None:
            return []
        try:
            return self.ds.query(sql, list(params)) or []
        except Exception as e:  # 查询失败 → fail-open，不阻断主数据维护
            logger.warning(f'[batch] 查询失败，跳过该项检查: {e}')
            return []
