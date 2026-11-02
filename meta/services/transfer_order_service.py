# -*- coding: utf-8 -*-
"""调拨单服务 —— 下达、发货、取消、关闭、履约派生与收货回写。

依据: `.trae/specs/excel-to-diagram/define-transfer-order-object-model/spec.md`
      §3 对象模型 / §6 状态机 / §7 发货与收货桥接 / §10 不变量 R-TO-0 ~ R-TO-13

口径:
  · 头状态 `draft / released / closed / cancelled`；行状态 `open / closed / cancelled`；
    履约状态为只读派生 `open / partially_shipped / shipped / partially_received / received`。
  · `ship` 只累加行 `qty_shipped`，不建 shipment、不校验库存可用量、不写库存事务。
  · `qty_received` 只由 `apply_receipt`（收货过账）与 `reverse=True`（红冲）回写，
    累计不得超过 `qty_shipped`；全部行收满时自动置头 `closed` + `received`。
  · 红冲后若头此前因收满而 `closed`，回退为 `released` 并重算履约状态。
  · 不写金额 / 成本 / 币种 / 税率；不写 `purchase_order_schedules`；不调用 PO 履约服务。
  · 所有写操作均在 `ds.transaction()` 内完成（嵌套事务由 DataSource 守卫处理）。

覆写 `_load_header` / `_load_lines` / `_load_line` 即可注入测试数据。
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HEADER_TABLE = 'transfer_orders'
LINE_TABLE = 'transfer_order_lines'

STATUS_DRAFT = 'draft'
STATUS_RELEASED = 'released'
STATUS_CLOSED = 'closed'
STATUS_CANCELLED = 'cancelled'

LINE_STATUS_OPEN = 'open'
LINE_STATUS_CLOSED = 'closed'
LINE_STATUS_CANCELLED = 'cancelled'

FULFILL_OPEN = 'open'
FULFILL_PARTIALLY_SHIPPED = 'partially_shipped'
FULFILL_SHIPPED = 'shipped'
FULFILL_PARTIALLY_RECEIVED = 'partially_received'
FULFILL_RECEIVED = 'received'

#: 终态：禁止 ship / receive / update（R-TO-13）
TERMINAL_STATUSES = (STATUS_CLOSED, STATUS_CANCELLED)

#: 无时间戳时要落库的最小列集
_HEADER_COLUMNS = (
    'id, transfer_order_no, document_type_id, transfer_date, status, '
    'fulfillment_status, from_org_id, to_org_id, legal_entity_id, '
    'from_location_id, to_location_id, project_id, actual_ship_date, '
    'carrier_name, waybill_no')
_LINE_COLUMNS = (
    'id, transfer_order_id, line_no, line_type_id, item_id, uom_id, qty, '
    'qty_shipped, qty_received, status, fulfillment_status')


class TransferOrderError(ValueError):
    """调拨单业务拒绝。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.message = message
        self.field_name = field_name
        self.rule = rule


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _status(value: Any) -> str:
    return str(value or '').strip().lower()


def _dec(value: Any, field_name: str = 'qty') -> Decimal:
    """数量统一走 Decimal，避免浮点把 0.1 + 0.2 判成超发。"""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise TransferOrderError('数量必须是数字', field_name=field_name,
                                 rule='TO_QTY_INVALID')


def _num(value: Any) -> Decimal:
    """读库值的宽松数值口径：空值 / 脏值按 0 处理。"""
    if _blank(value):
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def _rowcount(cursor: Any) -> int:
    return int(getattr(cursor, 'rowcount', 0) or 0)


class TransferOrderService:
    """调拨单生命周期动作与履约派生。"""

    def __init__(self, data_source=None):
        self._ds = data_source

    @property
    def ds(self):
        if self._ds is None:
            from meta.core.datasource import get_data_source
            from meta.core.db_path import get_meta_db_path
            self._ds = get_data_source('sqlite', database=get_meta_db_path())
        return self._ds

    # ------------------------------------------------------------------
    # 下达
    # ------------------------------------------------------------------
    def release(self, transfer_order_id: Any) -> Dict[str, Any]:
        """draft → released（R-TO-3 至少 1 行；R-TO-5 冻结由守卫承接）。"""
        with self.ds.transaction():
            header = self._require_header(transfer_order_id)
            current = _status(header.get('status'))
            if current in TERMINAL_STATUSES:
                raise TransferOrderError(
                    '调拨单已处于终态 %s，禁止下达' % current,
                    field_name='status', rule='TO_TERMINAL_IMMUTABLE')
            if current == STATUS_RELEASED:
                return {'id': header['id'], 'status': STATUS_RELEASED,
                        'idempotent': True}
            if current != STATUS_DRAFT:
                raise TransferOrderError(
                    '仅草稿态调拨单可下达', field_name='status',
                    rule='TO_STATE_INVALID')

            lines = self._load_lines(header['id'])
            if not lines:
                raise TransferOrderError(
                    '调拨单没有任何行，禁止下达', field_name='lines',
                    rule='TO_NO_LINES')

            now = _now()
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % HEADER_TABLE, [STATUS_RELEASED, now, header['id']])
            self.recompute_fulfillment(header['id'])
            logger.info('[transfer_order] released id=%s lines=%s',
                        header['id'], len(lines))
            return {'id': header['id'], 'status': STATUS_RELEASED,
                    'idempotent': False, 'line_count': len(lines)}

    # ------------------------------------------------------------------
    # 发货
    # ------------------------------------------------------------------
    def ship(self, transfer_order_id: Any,
             lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """released 状态下原子累加行 `qty_shipped`（R-TO-7）。

        `lines` 项: `line_id` 必填、`qty` 必填且 > 0；
        `carrier_name` / `waybill_no` / `ship_date` 选填（首次发货写
        `actual_ship_date`）。重复 `line_id` 按合计处理。
        """
        items = self._normalize_ship_lines(lines)
        with self.ds.transaction():
            header = self._require_header(transfer_order_id)
            status = _status(header.get('status'))
            if status in TERMINAL_STATUSES:
                raise TransferOrderError(
                    '调拨单已处于终态 %s，禁止发货' % status,
                    field_name='status', rule='TO_TERMINAL_IMMUTABLE')
            if status != STATUS_RELEASED:
                raise TransferOrderError(
                    '仅已下达的调拨单可发货', field_name='status',
                    rule='TO_STATE_INVALID')

            now = _now()
            for line_id, qty in items.items():
                line = self._load_line(line_id)
                if line is None or line.get('transfer_order_id') != header['id']:
                    raise TransferOrderError(
                        '调拨行 %s 不属于该调拨单' % line_id,
                        field_name='line_id', rule='TO_LINE_NOT_FOUND')
                if _status(line.get('status')) != LINE_STATUS_OPEN:
                    raise TransferOrderError(
                        '调拨行 %s 已关闭 / 已取消，禁止发货' % line_id,
                        field_name='line_id', rule='TO_LINE_NOT_OPEN')
                # R-TO-7 唯一判定点：条件 UPDATE 原子累加，rowcount=0 即超发
                cursor = self.ds.execute(
                    'UPDATE %s SET qty_shipped = COALESCE(qty_shipped, 0) + ?, '
                    'updated_at = ? WHERE id = ? AND transfer_order_id = ? '
                    'AND status = ? AND COALESCE(qty_shipped, 0) + ? <= qty'
                    % LINE_TABLE,
                    [float(qty), now, line_id, header['id'],
                     LINE_STATUS_OPEN, float(qty)])
                if not _rowcount(cursor):
                    raise TransferOrderError(
                        '调拨行 %s 发货量超过计划量（本次 %s，已发 %s）'
                        % (line_id, qty, line.get('qty_shipped') or 0),
                        field_name='qty', rule='TO_SHIP_QTY_EXCEEDED')

            ship_date = self._first_ship_date(lines)
            carrier = self._first_text(lines, 'carrier_name')
            waybill = self._first_text(lines, 'waybill_no')
            self.ds.execute(
                'UPDATE %s SET actual_ship_date = COALESCE(actual_ship_date, ?), '
                'carrier_name = COALESCE(?, carrier_name), '
                'waybill_no = COALESCE(?, waybill_no), updated_at = ? '
                'WHERE id = ?' % HEADER_TABLE,
                [ship_date, carrier, waybill, now, header['id']])

            self.recompute_fulfillment(header['id'])
            fresh = self._require_header(header['id'])
            logger.info('[transfer_order] shipped id=%s lines=%s',
                        header['id'], len(items))
            return {'id': fresh['id'], 'status': fresh.get('status'),
                    'fulfillment_status': fresh.get('fulfillment_status'),
                    'actual_ship_date': fresh.get('actual_ship_date'),
                    'line_ids': sorted(items.keys())}

    # ------------------------------------------------------------------
    # 取消 / 关闭
    # ------------------------------------------------------------------
    def cancel(self, transfer_order_id: Any) -> Dict[str, Any]:
        """draft / released → cancelled；总发货量必须为 0（R-TO-6）。"""
        with self.ds.transaction():
            header = self._require_header(transfer_order_id)
            status = _status(header.get('status'))
            if status == STATUS_CANCELLED:
                return {'id': header['id'], 'status': STATUS_CANCELLED,
                        'idempotent': True}
            if status in TERMINAL_STATUSES:
                raise TransferOrderError(
                    '调拨单已处于终态 %s，禁止取消' % status,
                    field_name='status', rule='TO_TERMINAL_IMMUTABLE')
            if self._total_shipped(header['id']) > 0:
                raise TransferOrderError(
                    '调拨单已发货，禁止取消；请改走反向调拨',
                    field_name='status', rule='TO_SHIPPED_CANNOT_CANCEL')

            now = _now()
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % HEADER_TABLE, [STATUS_CANCELLED, now, header['id']])
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE transfer_order_id = ?'
                % LINE_TABLE, [LINE_STATUS_CANCELLED, now, header['id']])
            return {'id': header['id'], 'status': STATUS_CANCELLED}

    def close(self, transfer_order_id: Any) -> Dict[str, Any]:
        """released → closed：在途量 = 0 且总收货量 > 0（短收结案）。"""
        with self.ds.transaction():
            header = self._require_header(transfer_order_id)
            status = _status(header.get('status'))
            if status == STATUS_CLOSED:
                return {'id': header['id'], 'status': STATUS_CLOSED,
                        'idempotent': True}
            if status in TERMINAL_STATUSES:
                raise TransferOrderError(
                    '调拨单已处于终态 %s，禁止关闭' % status,
                    field_name='status', rule='TO_TERMINAL_IMMUTABLE')
            if status != STATUS_RELEASED:
                raise TransferOrderError(
                    '仅已下达的调拨单可关闭', field_name='status',
                    rule='TO_STATE_INVALID')

            lines = self._load_lines(header['id'])
            in_transit = sum((_num(x.get('qty_shipped'))
                              - _num(x.get('qty_received')) for x in lines),
                             Decimal('0'))
            if in_transit != 0:
                raise TransferOrderError(
                    '调拨单仍有在途量 %s，禁止关闭' % in_transit,
                    field_name='status', rule='TO_IN_TRANSIT_NOT_EMPTY')
            if sum((_num(x.get('qty_received')) for x in lines), Decimal('0')) <= 0:
                raise TransferOrderError(
                    '调拨单尚未收货，禁止关闭', field_name='status',
                    rule='TO_NOTHING_RECEIVED')

            now = _now()
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % HEADER_TABLE, [STATUS_CLOSED, now, header['id']])
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? '
                'WHERE transfer_order_id = ? AND status = ?'
                % LINE_TABLE,
                [LINE_STATUS_CLOSED, now, header['id'], LINE_STATUS_OPEN])
            self.recompute_fulfillment(header['id'])
            return {'id': header['id'], 'status': STATUS_CLOSED}

    # ------------------------------------------------------------------
    # 履约状态派生
    # ------------------------------------------------------------------
    def recompute_fulfillment(self, transfer_order_id: Any) -> Optional[str]:
        """头与行的 `fulfillment_status` 按 spec §6.1 公式派生；返回头状态。"""
        with self.ds.transaction():
            header = self._load_header(transfer_order_id)
            if not header:
                return None
            lines = self._load_lines(header['id'])
            now = _now()
            for line in lines:
                derived = self._line_fulfillment(line)
                if line.get('fulfillment_status') == derived:
                    continue
                self.ds.execute(
                    'UPDATE %s SET fulfillment_status = ?, updated_at = ? '
                    'WHERE id = ?' % LINE_TABLE, [derived, now, line['id']])
            derived = self._header_fulfillment(lines)
            if header.get('fulfillment_status') != derived:
                self.ds.execute(
                    'UPDATE %s SET fulfillment_status = ?, updated_at = ? '
                    'WHERE id = ?' % HEADER_TABLE,
                    [derived, now, header['id']])
            return derived

    # ------------------------------------------------------------------
    # 收货回写（由收货过账 / 红冲调用）
    # ------------------------------------------------------------------
    def apply_receipt(self, transfer_order_id: Any,
                      lines: List[Dict[str, Any]],
                      reverse: bool = False) -> Dict[str, Any]:
        """按净收回写 TO 行 `qty_received`（R-TO-9）。

        `lines` 项支持两种口径（二者其一）：
          · `line_id` + `qty_received`（+ `qty_rejected`）—— 直接来自收货行；
          · `line_id` + `qty` —— 已算好的净收量。
        正向：净收 > 0，累加后不得超过 `qty_shipped`；全部行收满自动关闭头。
        反向（`reverse=True`）：扣减 `qty_received`，若头因收满而 `closed`
        则回退 `released` 并重算履约状态。
        """
        items = self._normalize_receipt_lines(lines)
        with self.ds.transaction():
            header = self._require_header(transfer_order_id)
            status = _status(header.get('status'))
            if status == STATUS_CANCELLED:
                raise TransferOrderError(
                    '调拨单已取消，禁止收货回写', field_name='status',
                    rule='TO_TERMINAL_IMMUTABLE')
            if not reverse and status != STATUS_RELEASED:
                raise TransferOrderError(
                    '仅已下达的调拨单可收货回写', field_name='status',
                    rule='TO_STATE_INVALID')
            if reverse and status not in (STATUS_RELEASED, STATUS_CLOSED):
                raise TransferOrderError(
                    '当前状态 %s 禁止收货红冲' % status, field_name='status',
                    rule='TO_STATE_INVALID')
            if not items:
                raise TransferOrderError(
                    '收货回写没有任何行', field_name='lines', rule='TO_NO_LINES')

            now = _now()
            for line_id, net in items.items():
                line = self._load_line(line_id)
                if line is None or line.get('transfer_order_id') != header['id']:
                    raise TransferOrderError(
                        '调拨行 %s 不属于该调拨单' % line_id,
                        field_name='line_id', rule='TO_LINE_NOT_FOUND')
                if reverse:
                    cursor = self.ds.execute(
                        'UPDATE %s SET qty_received = COALESCE(qty_received, 0) - ?, '
                        'updated_at = ? WHERE id = ? AND transfer_order_id = ? '
                        'AND COALESCE(qty_received, 0) - ? >= 0' % LINE_TABLE,
                        [float(net), now, line_id, header['id'], float(net)])
                    if not _rowcount(cursor):
                        raise TransferOrderError(
                            '调拨行 %s 红冲量超过已收量' % line_id,
                            field_name='qty_received', rule='TO_RECEIVE_REVERSE_EXCEEDED')
                else:
                    # 条件 UPDATE 原子累加：不得超过已发货量（R-TO-9）
                    cursor = self.ds.execute(
                        'UPDATE %s SET qty_received = COALESCE(qty_received, 0) + ?, '
                        'updated_at = ? WHERE id = ? AND transfer_order_id = ? '
                        'AND COALESCE(qty_received, 0) + ? <= COALESCE(qty_shipped, 0)'
                        % LINE_TABLE,
                        [float(net), now, line_id, header['id'], float(net)])
                    if not _rowcount(cursor):
                        raise TransferOrderError(
                            '调拨行 %s 收货量超过已发货量' % line_id,
                            field_name='qty_received', rule='TO_RECEIVE_EXCEEDED')

            fresh_lines = self._load_lines(header['id'])
            all_received = self._all_received(fresh_lines)
            if reverse:
                # 仅回退「因收满而自动关闭」的头：closed + fulfillment=received；
                # 手工 close（短收结案）保持 closed，避免红冲误重开。
                auto_closed = (
                    _status(header.get('status')) == STATUS_CLOSED
                    and _status(header.get('fulfillment_status')) == FULFILL_RECEIVED)
                if auto_closed and not all_received:
                    # 红冲回退：头从 closed 回到 released，行由 closed 回到 open
                    self.ds.execute(
                        'UPDATE %s SET status = ?, updated_at = ? '
                        'WHERE transfer_order_id = ? AND status = ?'
                        % LINE_TABLE,
                        [LINE_STATUS_OPEN, now, header['id'], LINE_STATUS_CLOSED])
                    self.ds.execute(
                        'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                        % HEADER_TABLE, [STATUS_RELEASED, now, header['id']])
            elif all_received:
                # 全部收满：头自动关闭并置 received（行一并关闭）
                self.ds.execute(
                    'UPDATE %s SET status = ?, updated_at = ? '
                    'WHERE transfer_order_id = ? AND status = ?'
                    % LINE_TABLE,
                    [LINE_STATUS_CLOSED, now, header['id'], LINE_STATUS_OPEN])
                self.ds.execute(
                    'UPDATE %s SET status = ?, fulfillment_status = ?, updated_at = ? '
                    'WHERE id = ?' % HEADER_TABLE,
                    [STATUS_CLOSED, FULFILL_RECEIVED, now, header['id']])

            self.recompute_fulfillment(header['id'])
            fresh = self._require_header(header['id'])
            logger.info('[transfer_order] receipt applied id=%s reverse=%s lines=%s',
                        header['id'], reverse, len(items))
            return {'id': fresh['id'], 'status': fresh.get('status'),
                    'fulfillment_status': fresh.get('fulfillment_status'),
                    'reversed': bool(reverse), 'line_ids': sorted(items.keys())}

    def reverse_receipt(self, transfer_order_id: Any,
                        lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """收货红冲入口（Tasks SubTask 3.2 / 6.1），等价 `apply_receipt(reverse=True)`。"""
        return self.apply_receipt(transfer_order_id, lines, reverse=True)

    # ------------------------------------------------------------------
    # 派生规则
    # ------------------------------------------------------------------
    @staticmethod
    def _line_fulfillment(line: Dict[str, Any]) -> str:
        qty = _num(line.get('qty'))
        shipped = _num(line.get('qty_shipped'))
        received = _num(line.get('qty_received'))
        if qty > 0 and received >= qty:
            return FULFILL_RECEIVED
        if received > 0:
            return FULFILL_PARTIALLY_RECEIVED
        if shipped <= 0:
            return FULFILL_OPEN
        if shipped >= qty:
            return FULFILL_SHIPPED
        return FULFILL_PARTIALLY_SHIPPED

    @staticmethod
    def _header_fulfillment(lines: List[Dict[str, Any]]) -> str:
        if not lines:
            return FULFILL_OPEN
        total = sum((_num(x.get('qty')) for x in lines), Decimal('0'))
        shipped = sum((_num(x.get('qty_shipped')) for x in lines), Decimal('0'))
        received = sum((_num(x.get('qty_received')) for x in lines), Decimal('0'))
        if TransferOrderService._all_received(lines):
            return FULFILL_RECEIVED
        if received > 0:
            return FULFILL_PARTIALLY_RECEIVED
        if shipped <= 0:
            return FULFILL_OPEN
        if total > 0 and shipped >= total:
            return FULFILL_SHIPPED
        return FULFILL_PARTIALLY_SHIPPED

    @staticmethod
    def _all_received(lines: List[Dict[str, Any]]) -> bool:
        active = [x for x in lines if _status(x.get('status'))
                  != LINE_STATUS_CANCELLED]
        if not active:
            return False
        return all(_num(x.get('qty_received')) >= _num(x.get('qty'))
                   for x in active)

    # ------------------------------------------------------------------
    # 入参归一
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_ship_lines(lines: Optional[List[Dict[str, Any]]]) -> Dict[Any, Decimal]:
        items: Dict[Any, Decimal] = {}
        for item in (lines or []):
            item = dict(item or {})
            line_id = item.get('line_id') or item.get('id')
            if _blank(line_id):
                raise TransferOrderError(
                    '发货行缺少 line_id', field_name='line_id',
                    rule='TO_LINE_REQUIRED')
            qty = _dec(item.get('qty'), 'qty')
            if qty <= 0:
                raise TransferOrderError(
                    '发货数量必须大于 0', field_name='qty',
                    rule='TO_SHIP_QTY_POSITIVE')
            items[line_id] = items.get(line_id, Decimal('0')) + qty
        if not items:
            raise TransferOrderError(
                '发货至少需要一行', field_name='lines', rule='TO_NO_LINES')
        return items

    @staticmethod
    def _normalize_receipt_lines(lines: Optional[List[Dict[str, Any]]]) -> Dict[Any, Decimal]:
        items: Dict[Any, Decimal] = {}
        for item in (lines or []):
            item = dict(item or {})
            line_id = (item.get('line_id') or item.get('transfer_order_line_id')
                       or item.get('source_line_id'))
            if _blank(line_id):
                raise TransferOrderError(
                    '收货回写行缺少 line_id', field_name='line_id',
                    rule='TO_LINE_REQUIRED')
            if item.get('qty_received') is None and item.get('qty') is not None:
                net = _dec(item.get('qty'), 'qty')
            else:
                received = _dec(item.get('qty_received') or 0, 'qty_received')
                rejected = _dec(item.get('qty_rejected') or 0, 'qty_rejected')
                net = received - rejected
            if net == 0:
                continue
            if net < 0:
                raise TransferOrderError(
                    '收货净收量不能为负', field_name='qty_received',
                    rule='TO_QTY_INVALID')
            items[line_id] = items.get(line_id, Decimal('0')) + net
        return items

    @staticmethod
    def _first_ship_date(lines: Optional[List[Dict[str, Any]]]) -> str:
        """首次发货日期：优先取入参 `ship_date`，否则取当天（日期口径）。"""
        for item in (lines or []):
            value = dict(item or {}).get('ship_date')
            if not _blank(value):
                return str(value).strip()
        return datetime.now().strftime('%Y-%m-%d')

    @staticmethod
    def _first_text(lines: Optional[List[Dict[str, Any]]], field: str) -> Optional[str]:
        for item in (lines or []):
            value = dict(item or {}).get(field)
            if not _blank(value):
                return str(value).strip()
        return None

    # ------------------------------------------------------------------
    # 读取 / 校验（可覆写，便于单测注入）
    # ------------------------------------------------------------------
    def _load_header(self, transfer_order_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(transfer_order_id):
            return None
        rows = self.ds.query(
            'SELECT %s FROM %s WHERE id = ?' % (_HEADER_COLUMNS, HEADER_TABLE),
            [transfer_order_id])
        return rows[0] if rows else None

    def _require_header(self, transfer_order_id: Any) -> Dict[str, Any]:
        header = self._load_header(transfer_order_id)
        if header is None:
            raise TransferOrderError('调拨单不存在', field_name='id',
                                     rule='TO_NOT_FOUND')
        return header

    def _load_lines(self, transfer_order_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT %s FROM %s WHERE transfer_order_id = ? ORDER BY line_no, id'
            % (_LINE_COLUMNS, LINE_TABLE), [transfer_order_id])

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(line_id):
            return None
        rows = self.ds.query(
            'SELECT %s FROM %s WHERE id = ?' % (_LINE_COLUMNS, LINE_TABLE),
            [line_id])
        return rows[0] if rows else None

    def _total_shipped(self, transfer_order_id: Any) -> Decimal:
        rows = self.ds.query(
            'SELECT COALESCE(SUM(qty_shipped), 0) AS total FROM %s '
            'WHERE transfer_order_id = ? AND status <> ?'
            % LINE_TABLE, [transfer_order_id, LINE_STATUS_CANCELLED])
        return _num(rows[0].get('total')) if rows else Decimal('0')
