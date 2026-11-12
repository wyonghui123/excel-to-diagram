# -*- coding: utf-8 -*-
"""调拨发货单服务 —— 取号、建单、过账、取消（TBD-3 独立发货单）。

依据: `.trae/specs/excel-to-diagram/define-transfer-order-object-model/spec.md`
      TBD-3 / §7 发货与收货桥接

口径:
  · 发货单只承载「本次发货的调拨行 + 数量」这一事实，不写库存台账 /
    可用量 / 在途表，不存金额 / 币种 / 税率。
  · 取号在开事务之前完成（R-RC-8 同口径），允许跳号。
  · 建单只做校验 + 落草稿；调拨行 `qty_shipped` 只在 `post` 时由
    `TransferOrderService.ship` 累加，超发由 ship / 容差拒绝后整体回滚。
  · 状态机 draft → posted / cancelled；cancel 仅对 draft 生效。
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from meta.services.transfer_order_service import (
    STATUS_RELEASED,
    TOLERANCE_SHIP_PARAM,
    TransferOrderError,
    TransferOrderService,
    resolve_tolerance_ratio,
)

from meta.core.doc_flow_reversal import release_target_edges

logger = logging.getLogger(__name__)

HEADER_TABLE = 'transfer_shipments'
LINE_TABLE = 'transfer_shipment_lines'
TO_TABLE = 'transfer_orders'
TOL_TABLE = 'transfer_order_lines'

STATUS_DRAFT = 'draft'
STATUS_POSTED = 'posted'
STATUS_CANCELLED = 'cancelled'

#: 行号递增步长（与调拨行 10 / 20 / 30 同口径）
LINE_NO_STEP = 10

_HEADER_COLUMNS = (
    'id, shipment_no, transfer_order_id, ship_date, carrier_name, '
    'waybill_no, status, remark')
_LINE_COLUMNS = (
    'id, transfer_shipment_id, line_no, transfer_order_line_id, qty, remark')


class TransferShipmentError(ValueError):
    """调拨发货单业务拒绝。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.message = message
        self.field_name = field_name
        self.rule = rule


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _status(value: Any) -> str:
    return str(value or '').strip().lower()


def _dec(value: Any, field_name: str = 'qty') -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise TransferShipmentError('数量必须是数字', field_name=field_name,
                                    rule='TRS_QTY_INVALID')


def _num(value: Any) -> Decimal:
    if _blank(value):
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def _rowcount(cursor: Any) -> int:
    return int(getattr(cursor, 'rowcount', 0) or 0)


class TransferShipmentService:
    """调拨发货单生命周期动作。"""

    def __init__(self, data_source=None, order_service=None,
                 platform_data_source=None):
        self._ds = data_source
        self._order_service = order_service
        # 平台库（doc_flow_rule）；单库部署时与 self.ds 相同
        self._platform_ds = platform_data_source

    @property
    def ds(self):
        if self._ds is None:
            from meta.core.datasource import get_data_source
            from meta.core.db_path import get_meta_db_path
            self._ds = get_data_source('sqlite', database=get_meta_db_path())
        return self._ds

    @property
    def platform_ds(self):
        """平台库（doc_flow_rule）；未注入时回退平台库单例，再回退应用库。"""
        if self._platform_ds is None:
            try:
                from meta.core.datasource import get_platform_data_source
                self._platform_ds = get_platform_data_source() or self.ds
            except Exception:  # noqa: BLE001 - 平台库不可用按单库处理
                self._platform_ds = self.ds
        return self._platform_ds

    @property
    def order_service(self) -> TransferOrderService:
        if self._order_service is None:
            self._order_service = TransferOrderService(self.ds)
        return self._order_service

    # ------------------------------------------------------------------
    # 取号
    # ------------------------------------------------------------------
    def allocate_shipment_no(self, ship_date: Any) -> str:
        """按发货单头类型指向的序列取号（必须在开事务前调用，允许跳号）。"""
        date = str(ship_date or '').strip()
        if _blank(date):
            raise TransferShipmentError(
                '发货日期缺失，无法取号', field_name='ship_date',
                rule='TRS_DATE_REQUIRED')

        from meta.services.document_number_service import (
            DocumentNumberError, DocumentNumberService)
        try:
            return DocumentNumberService(self.ds).allocate_for(
                'transfer_shipment', {'ship_date': date}, required=True)
        except DocumentNumberError as error:
            raise TransferShipmentError(
                str(error), field_name='shipment_no',
                rule='TRS_NUMBER_REQUIRED') from error

    # ------------------------------------------------------------------
    # 建单
    # ------------------------------------------------------------------
    def create(self, transfer_order_id: Any, ship_date: Any,
               lines: List[Dict[str, Any]], carrier_name: Any = None,
               waybill_no: Any = None, remark: Any = None) -> Dict[str, Any]:
        """创建草稿发货单；只校验并落头 / 行，不动调拨行已发量。"""
        if _blank(transfer_order_id):
            raise TransferShipmentError(
                '缺少 transfer_order_id', field_name='transfer_order_id',
                rule='TRS_ORDER_REQUIRED')
        date = str(ship_date or '').strip()
        if _blank(date):
            raise TransferShipmentError(
                '发货日期必填', field_name='ship_date',
                rule='TRS_DATE_REQUIRED')
        items = self._normalize_lines(lines)

        # 取号必须在事务外完成（号段独立提交，回滚不吞号）
        number = self.allocate_shipment_no(date)

        with self.ds.transaction():
            order = self._require_order(transfer_order_id)
            if _status(order.get('status')) != STATUS_RELEASED:
                raise TransferShipmentError(
                    '仅已下达的调拨单可发货', field_name='transfer_order_id',
                    rule='TRS_ORDER_NOT_RELEASED')

            order_lines = self._load_order_lines(order['id'])
            ratio = resolve_tolerance_ratio(self.ds, TOLERANCE_SHIP_PARAM, order)
            for order_line_id, qty in items.items():
                line = order_lines.get(order_line_id)
                if line is None:
                    raise TransferShipmentError(
                        '调拨行 %s 不属于该调拨单' % order_line_id,
                        field_name='transfer_order_line_id',
                        rule='TRS_LINE_NOT_FOUND')
                if _status(line.get('status')) != 'open':
                    raise TransferShipmentError(
                        '调拨行 %s 已关闭 / 已取消，禁止发货' % order_line_id,
                        field_name='transfer_order_line_id',
                        rule='TRS_LINE_NOT_OPEN')
                remain = (_num(line.get('qty')) * (Decimal('1') + ratio)
                          - _num(line.get('qty_shipped')))
                if qty > remain:
                    raise TransferShipmentError(
                        '调拨行 %s 本次发货量 %s 超过可发上限 %s（已发 %s）'
                        % (order_line_id, qty, remain,
                           line.get('qty_shipped') or 0),
                        field_name='qty', rule='TRS_SHIP_QTY_EXCEEDED')

            now = _now()
            cursor = self.ds.execute(
                'INSERT INTO %s (shipment_no, transfer_order_id, ship_date, '
                'carrier_name, waybill_no, status, remark, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)' % HEADER_TABLE,
                [number, order['id'], date, carrier_name, waybill_no,
                 STATUS_DRAFT, remark, now, now])
            shipment_id = int(getattr(cursor, 'lastrowid', 0) or 0)

            created_lines = []
            for index, (order_line_id, qty) in enumerate(items.items(), start=1):
                cursor = self.ds.execute(
                    'INSERT INTO %s (transfer_shipment_id, line_no, '
                    'transfer_order_line_id, qty, remark, created_at, updated_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)' % LINE_TABLE,
                    [shipment_id, index * LINE_NO_STEP, order_line_id,
                     float(qty), None, now, now])
                created_lines.append(
                    (order_line_id, qty,
                     int(getattr(cursor, 'lastrowid', 0) or 0)))
            self._write_order_edges(created_lines)

        logger.info('[transfer_shipment] created id=%s order=%s lines=%s',
                    shipment_id, order['id'], len(items))
        return {'id': shipment_id, 'shipment_no': number,
                'status': STATUS_DRAFT, 'transfer_order_id': order['id'],
                'line_count': len(items)}

    def _write_order_edges(self, created_lines) -> None:
        """调拨行 → 调拨发货行（attach 模式，失败降级不阻断建单）。"""
        from meta.core.doc_flow_attach import attach_edge
        for order_line_id, qty, line_id in created_lines:
            if not line_id:
                continue
            attach_edge(
                self.ds, self.platform_ds,
                'transfer_order_line_to_transfer_shipment_line',
                order_line_id, line_id, float(qty),
                target_item=str(line_id), unit='',
                derived_by='transfer_shipment_service')

    # ------------------------------------------------------------------
    # 过账 / 取消
    # ------------------------------------------------------------------
    def post(self, shipment_id: Any) -> Dict[str, Any]:
        """draft → posted：调 ship 累加调拨行已发量，成功后置 posted。"""
        with self.ds.transaction():
            header = self._require_header(shipment_id)
            if _status(header.get('status')) != STATUS_DRAFT:
                raise TransferShipmentError(
                    '仅草稿态发货单可过账', field_name='status',
                    rule='TRS_STATE_INVALID')

            lines = self._load_lines(header['id'])
            if not lines:
                raise TransferShipmentError(
                    '发货单没有任何行，禁止过账', field_name='lines',
                    rule='TRS_NO_LINES')

            payload = [{
                'line_id': line.get('transfer_order_line_id'),
                'qty': line.get('qty'),
                'ship_date': header.get('ship_date'),
                'carrier_name': header.get('carrier_name'),
                'waybill_no': header.get('waybill_no'),
            } for line in lines]

            # ship 自带事务与超发守卫；抛错时外层整体回滚，发货单保持 draft
            order_result = self.order_service.ship(
                header.get('transfer_order_id'), payload)

            now = _now()
            cursor = self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? '
                'WHERE id = ? AND status = ?' % HEADER_TABLE,
                [STATUS_POSTED, now, header['id'], STATUS_DRAFT])
            if not _rowcount(cursor):
                raise TransferShipmentError(
                    '发货单状态已变更，过账失败', field_name='status',
                    rule='TRS_STATE_INVALID')

        logger.info('[transfer_shipment] posted id=%s order=%s lines=%s',
                    header['id'], header.get('transfer_order_id'), len(lines))
        return {'id': header['id'], 'shipment_no': header.get('shipment_no'),
                'status': STATUS_POSTED,
                'transfer_order_id': header.get('transfer_order_id'),
                'fulfillment_status': order_result.get('fulfillment_status'),
                'line_count': len(lines)}

    def cancel(self, shipment_id: Any) -> Dict[str, Any]:
        """draft → cancelled；仅草稿可取消，不触碰调拨单数量。"""
        with self.ds.transaction():
            header = self._require_header(shipment_id)
            if _status(header.get('status')) != STATUS_DRAFT:
                raise TransferShipmentError(
                    '仅草稿态发货单可取消', field_name='status',
                    rule='TRS_STATE_INVALID')

            now = _now()
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % HEADER_TABLE, [STATUS_CANCELLED, now, header['id']])
            # 取消 → 释放调拨行被本发货行占用的量（边保留，视图不计）
            line_ids = [row['id'] for row in self.ds.query(
                'SELECT id FROM %s WHERE transfer_shipment_id = ?' % LINE_TABLE,
                [header['id']])]
            release_target_edges(
                self.ds, 'transfer_shipment_line', line_ids,
                reversed_by='transfer_shipment_service.cancel')

        logger.info('[transfer_shipment] cancelled id=%s', header['id'])
        return {'id': header['id'], 'shipment_no': header.get('shipment_no'),
                'status': STATUS_CANCELLED}

    # ------------------------------------------------------------------
    # 入参归一
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_lines(lines: Optional[List[Dict[str, Any]]
                                    ]) -> Dict[Any, Decimal]:
        """同一调拨行多次出现时按合计处理（与 TO ship 同口径）。"""
        items: Dict[Any, Decimal] = {}
        for item in (lines or []):
            item = dict(item or {})
            line_id = (item.get('transfer_order_line_id')
                       or item.get('line_id'))
            if _blank(line_id):
                raise TransferShipmentError(
                    '发货行缺少 transfer_order_line_id',
                    field_name='transfer_order_line_id',
                    rule='TRS_LINE_REQUIRED')
            qty = _dec(item.get('qty'))
            if qty <= 0:
                raise TransferShipmentError(
                    '发货数量必须大于 0', field_name='qty',
                    rule='TRS_QTY_POSITIVE')
            items[line_id] = items.get(line_id, Decimal('0')) + qty
        if not items:
            raise TransferShipmentError(
                '发货单至少需要一行', field_name='lines',
                rule='TRS_NO_LINES')
        return items

    # ------------------------------------------------------------------
    # 读取 / 校验（可覆写，便于单测注入）
    # ------------------------------------------------------------------
    def _load_header(self, shipment_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(shipment_id):
            return None
        rows = self.ds.query(
            'SELECT %s FROM %s WHERE id = ?' % (_HEADER_COLUMNS, HEADER_TABLE),
            [shipment_id])
        return rows[0] if rows else None

    def _require_header(self, shipment_id: Any) -> Dict[str, Any]:
        header = self._load_header(shipment_id)
        if header is None:
            raise TransferShipmentError('发货单不存在', field_name='id',
                                        rule='TRS_NOT_FOUND')
        return header

    def _load_lines(self, shipment_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT %s FROM %s WHERE transfer_shipment_id = ? '
            'ORDER BY line_no, id' % (_LINE_COLUMNS, LINE_TABLE),
            [shipment_id])

    def _require_order(self, transfer_order_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT id, transfer_order_no, document_type_id, status, '
            'from_org_id, to_org_id FROM %s WHERE id = ?' % TO_TABLE,
            [transfer_order_id])
        if not rows:
            raise TransferShipmentError('调拨单不存在',
                                        field_name='transfer_order_id',
                                        rule='TRS_ORDER_NOT_FOUND')
        return rows[0]

    def _load_order_lines(self, transfer_order_id: Any) -> Dict[Any, Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, transfer_order_id, item_id, qty, qty_shipped, status '
            'FROM %s WHERE transfer_order_id = ?' % TOL_TABLE,
            [transfer_order_id])
        return {row.get('id'): row for row in rows}


__all__ = ['TransferShipmentError', 'TransferShipmentService',
           'TransferOrderError']
