# -*- coding: utf-8 -*-
"""库存过账守卫 —— INV-1 维度一致性、负库存与主数据解析。

依据:
  .trae/specs/excel-to-diagram/define-inventory-model/spec.md
    FR-009 维度一致性 / FR-010 负库存参数 / FR-013 期初导入

口径:
  ① 只做校验与归一，不写任何表；写入由 InventoryPostingService 负责。
  ② 所有错误带稳定错误码（INV_*），调用方（单据动作）据此整体回滚。
  ③ 缺库位时按 org.default_inventory_location_id 兜底，仍无则 INV_LOCATION_REQUIRED。
  ④ 日常过账 stock_status 只允许 unrestricted；期初导入由 allow_non_unrestricted=True 放开。
  ⑤ 批次 blocked 禁止 unrestricted 桶出库（INV_BATCH_BLOCKED）；
     INV-4 服务传 allow_blocked_batch=True 时，非可用桶出库放行。
  ⑥ 参数解析走 ControlParameterResolver，按 org_id 维度覆盖。
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: 错误码（与 spec 9.3 错误码表一致）
INV_ORG_REQUIRED = 'INV_ORG_REQUIRED'
INV_ORG_INVALID = 'INV_ORG_INVALID'
INV_LOCATION_REQUIRED = 'INV_LOCATION_REQUIRED'
INV_LOCATION_INVALID = 'INV_LOCATION_INVALID'
INV_LOCATION_ORG_MISMATCH = 'INV_LOCATION_ORG_MISMATCH'
INV_BATCH_MISMATCH = 'INV_BATCH_MISMATCH'
INV_BATCH_BLOCKED = 'INV_BATCH_BLOCKED'
INV_UOM_INVALID = 'INV_UOM_INVALID'
INV_STATUS_INVALID = 'INV_STATUS_INVALID'
INV_NEGATIVE_STOCK = 'INV_NEGATIVE_STOCK'
INV_QTY_INVALID = 'INV_QTY_INVALID'
INV_TYPE_INVALID = 'INV_TYPE_INVALID'
INV_DUPLICATE_SOURCE = 'INV_DUPLICATE_SOURCE'
INV_POSTING_DISABLED = 'INV_POSTING_DISABLED'
INV_COUNT_BLOCKED = 'INV_COUNT_BLOCKED'

DAILY_STATUSES = ('unrestricted',)
ALL_STATUSES = ('unrestricted', 'inspection', 'blocked')

PARAM_ALLOW_NEGATIVE = 'inventory_allow_negative'
PARAM_POSTING_ENABLED = 'inventory_posting_enabled'


class InventoryError(ValueError):
    """库存域业务错误；`code` 为稳定错误码，`details` 携带定位信息。"""

    def __init__(self, code: str, message: str,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__('[%s] %s' % (code, message))
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {'code': self.code, 'message': self.message,
                'details': self.details, 'success': False}


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'enabled')


def _decimal(value: Any) -> Optional[Decimal]:
    if _blank(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class InventoryGuardService:
    """库存维度守卫。构造函数只持有 data_source，可在单测中注入替身。"""

    def __init__(self, data_source, parameter_resolver=None):
        self.ds = data_source
        self._parameters = parameter_resolver

    # ------------------------------------------------------------------
    # 参数
    # ------------------------------------------------------------------
    @property
    def parameters(self):
        if self._parameters is None:
            from meta.services.control_parameter_service import (
                ControlParameterResolver,
            )
            self._parameters = ControlParameterResolver(self.ds)
        return self._parameters

    def posting_enabled(self) -> bool:
        return _as_bool(self.parameters.resolve(PARAM_POSTING_ENABLED, {}))

    def allow_negative(self, org_id: Any) -> bool:
        return _as_bool(self.parameters.resolve(PARAM_ALLOW_NEGATIVE,
                                                {'org_id': org_id}))

    # ------------------------------------------------------------------
    # 主数据解析
    # ------------------------------------------------------------------
    def resolve_org(self, org_id: Any, location_id: Any = None) -> Dict[str, Any]:
        if _blank(org_id):
            raise InventoryError(INV_ORG_REQUIRED, '库存组织不能为空')
        rows = self.ds.query(
            'SELECT id, status FROM orgs WHERE id = ?', [org_id])
        if not rows:
            raise InventoryError(INV_ORG_INVALID,
                                 '库存组织 %s 不存在' % org_id,
                                 {'org_id': org_id})
        org = rows[0]
        status = (org.get('status') or 'active')
        if str(status).lower() not in ('active', 'enabled', '1'):
            raise InventoryError(INV_ORG_INVALID,
                                 '库存组织 %s 未启用' % org_id,
                                 {'org_id': org_id, 'status': status})
        try:
            rows = self.ds.query(
                'SELECT 1 FROM org_functions WHERE org_id = ? '
                'AND function_type = ?', [org_id, 'inventory'])
        except Exception:
            rows = [{'1': 1}]
        if not rows:
            raise InventoryError(
                INV_ORG_INVALID, '组织 %s 不具备库存职能' % org_id,
                {'org_id': org_id, 'function': 'inventory'})
        return org

    def resolve_location(self, org_id: Any,
                         location_id: Any = None) -> Dict[str, Any]:
        if _blank(location_id):
            rows = self.ds.query(
                'SELECT default_inventory_location_id FROM orgs WHERE id = ?',
                [org_id])
            default_id = rows[0].get('default_inventory_location_id') if rows else None
            if _blank(default_id):
                raise InventoryError(
                    INV_LOCATION_REQUIRED,
                    '库存组织 %s 未指定库位，且未设置默认库存库位' % org_id,
                    {'org_id': org_id})
            location_id = default_id
        rows = self.ds.query(
            'SELECT id, org_id FROM locations WHERE id = ?',
            [location_id])
        if not rows:
            raise InventoryError(INV_LOCATION_INVALID,
                                 '库位 %s 不存在' % location_id,
                                 {'location_id': location_id})
        location = rows[0]
        if location.get('org_id') in (None, ''):
            raise InventoryError(
                INV_LOCATION_ORG_MISMATCH,
                '库位 %s 未归属任何组织，禁止过账' % location_id,
                {'location_id': location_id})
        if str(location.get('org_id')) != str(org_id):
            raise InventoryError(
                INV_LOCATION_ORG_MISMATCH,
                '库位 %s 归属组织 %s，与库存组织 %s 不一致'
                % (location_id, location.get('org_id'), org_id),
                {'location_id': location_id, 'org_id': org_id,
                 'location_org_id': location.get('org_id')})
        return location

    def resolve_batch(self, batch_id: Any, item_id: Any, org_id: Any,
                      direction: str, stock_status: str = 'unrestricted',
                      allow_blocked: bool = False) -> Optional[Dict[str, Any]]:
        if _blank(batch_id):
            return None
        rows = self.ds.query(
            'SELECT id, batch_no, item_id, org_id, quality_status '
            'FROM batches WHERE id = ?', [batch_id])
        if not rows:
            raise InventoryError(INV_BATCH_MISMATCH,
                                 '批次 %s 不存在' % batch_id,
                                 {'batch_id': batch_id})
        batch = rows[0]
        if str(batch.get('item_id')) != str(item_id) or \
                str(batch.get('org_id')) != str(org_id):
            raise InventoryError(
                INV_BATCH_MISMATCH,
                '批次 %s 的物料/组织与分录不一致' % batch_id,
                {'batch_id': batch_id, 'item_id': item_id, 'org_id': org_id,
                 'batch_item_id': batch.get('item_id'),
                 'batch_org_id': batch.get('org_id')})
        quality = (batch.get('quality_status') or 'unrestricted')
        # INV-4 FR-009：批次冻结只拦截 unrestricted 桶的日常出库；
        # 非可用桶（inspection / blocked）的报废、盘亏、状态转移允许执行。
        blocked_scope = (direction == 'out' and quality == 'blocked'
                         and (stock_status == 'unrestricted'
                              or not allow_blocked))
        if blocked_scope:
            raise InventoryError(
                INV_BATCH_BLOCKED,
                '批次 %s 已冻结，禁止出库' % batch['batch_no'],
                {'batch_id': batch_id, 'quality_status': quality})
        return batch

    def resolve_type(self, code_or_id: Any) -> Dict[str, Any]:
        if _blank(code_or_id):
            raise InventoryError(INV_TYPE_INVALID, '库存移动类型不能为空')
        rows = self.ds.query(
            'SELECT id, code, name, direction, status, affects_on_hand '
            'FROM inventory_transaction_types '
            'WHERE code = ? OR id = ?', [code_or_id, code_or_id])
        if not rows:
            raise InventoryError(INV_TYPE_INVALID,
                                 '库存移动类型 %s 不存在' % code_or_id)
        txn_type = rows[0]
        if (txn_type.get('status') or 'active') != 'active':
            raise InventoryError(INV_TYPE_INVALID,
                                 '库存移动类型 %s 已停用' % txn_type.get('code'),
                                 {'code': txn_type.get('code')})
        return txn_type

    def resolve_base_qty(self, item_id: Any, uom_id: Any,
                         qty: Any) -> Decimal:
        if _blank(item_id):
            raise InventoryError(INV_UOM_INVALID, '物料不能为空')
        rows = self.ds.query(
            'SELECT id, name, base_uom FROM items WHERE id = ?', [item_id])
        if not rows:
            raise InventoryError(INV_UOM_INVALID,
                                 '物料 %s 不存在' % item_id,
                                 {'item_id': item_id})
        base_uom = rows[0].get('base_uom')
        if _blank(base_uom):
            raise InventoryError(
                INV_UOM_INVALID, '物料 %s 未维护基本单位' % item_id,
                {'item_id': item_id})
        from meta.services.uom_quantity_service import UomQuantityService
        converted = UomQuantityService(self.ds).convert(
            item_id, qty, uom_id, base_uom)
        if converted is None:
            raise InventoryError(
                INV_UOM_INVALID,
                '单位 %s 无法换算为物料 %s 的基本单位' % (uom_id, item_id),
                {'item_id': item_id, 'uom_id': uom_id,
                 'base_uom': base_uom})
        return converted

    # ------------------------------------------------------------------
    # 分录归一
    # ------------------------------------------------------------------
    def normalize_entry(self, entry: Dict[str, Any],
                        allow_non_unrestricted: bool = False,
                        allow_blocked_batch: bool = False) -> Dict[str, Any]:
        """校验并归一一条分录；返回可直接落库的规范化字典。"""
        qty = _decimal(entry.get('qty'))
        if qty is None or qty <= 0:
            raise InventoryError(INV_QTY_INVALID,
                                 '库存分录数量必须大于 0',
                                 {'qty': entry.get('qty')})

        txn_type = self.resolve_type(
            entry.get('transaction_type') or entry.get('transaction_type_id'))
        direction = (entry.get('direction') or txn_type.get('direction') or 'in')
        if direction not in ('in', 'out'):
            raise InventoryError(INV_TYPE_INVALID,
                                 '库存方向必须是 in 或 out',
                                 {'direction': direction})
        # REVERSAL 是双向冲销类型：方向由原分录推导，不受类型默认方向限制。
        if txn_type.get('code') != 'REVERSAL' \
                and txn_type.get('direction') \
                and direction != txn_type.get('direction'):
            raise InventoryError(
                INV_TYPE_INVALID,
                '移动类型 %s 方向为 %s，与分录方向 %s 不一致'
                % (txn_type.get('code'), txn_type.get('direction'), direction),
                {'code': txn_type.get('code'),
                 'type_direction': txn_type.get('direction'),
                 'direction': direction})

        org = self.resolve_org(entry.get('org_id'), entry.get('location_id'))
        location = self.resolve_location(entry.get('org_id'),
                                         entry.get('location_id'))

        stock_status = (entry.get('stock_status') or 'unrestricted')
        allowed = ALL_STATUSES if allow_non_unrestricted else DAILY_STATUSES
        if stock_status not in allowed:
            raise InventoryError(
                INV_STATUS_INVALID,
                '库存状态 %s 不允许用于当前过账' % stock_status,
                {'stock_status': stock_status, 'allowed': list(allowed)})

        batch = self.resolve_batch(
            entry.get('batch_id'), entry.get('item_id'),
            entry.get('org_id'), direction, stock_status,
            allow_blocked=allow_blocked_batch)
        base_qty = self.resolve_base_qty(entry.get('item_id'),
                                         entry.get('uom_id'), qty)

        return {
            'transaction_type_id': txn_type['id'],
            'transaction_type_code': txn_type.get('code'),
            'affects_on_hand': txn_type.get('affects_on_hand', 1),
            'transaction_date': entry.get('transaction_date'),
            'org_id': org['id'],
            'location_id': location['id'],
            'item_id': entry.get('item_id'),
            'uom_id': entry.get('uom_id'),
            'qty': float(qty),
            'base_qty': float(base_qty),
            'direction': direction,
            'batch_id': batch['id'] if batch else None,
            'stock_status': stock_status,
            'source_line_id': entry.get('source_line_id'),
            'source_event_key': entry.get('source_event_key'),
            'transfer_group_id': entry.get('transfer_group_id'),
            'remark': entry.get('remark'),
            'created_by': entry.get('created_by'),
        }

    def check_negative(self, entry: Dict[str, Any],
                       current_qty: float) -> None:
        """负库存校验：只针对出账；参数允许时放行并记警告。"""
        if entry.get('direction') != 'out':
            return
        after = float(current_qty) - float(entry.get('base_qty') or 0)
        if after >= 0:
            return
        if self.allow_negative(entry.get('org_id')):
            logger.warning(
                '[inventory] 允许负库存 org=%s item=%s location=%s '
                'before=%s out=%s after=%s',
                entry.get('org_id'), entry.get('item_id'),
                entry.get('location_id'), current_qty,
                entry.get('base_qty'), after)
            return
        raise InventoryError(
            INV_NEGATIVE_STOCK,
            '出账后库存将为负（当前 %s，出账 %s）'
            % (current_qty, entry.get('base_qty')),
            {'org_id': entry.get('org_id'),
             'location_id': entry.get('location_id'),
             'item_id': entry.get('item_id'),
             'batch_id': entry.get('batch_id'),
             'stock_status': entry.get('stock_status'),
             'current_qty': current_qty,
             'out_qty': entry.get('base_qty'),
             'after_qty': after})
