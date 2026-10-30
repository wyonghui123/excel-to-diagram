# -*- coding: utf-8 -*-
"""交货单服务 —— B1：交货单头/行状态机与销售订单计划行接线。

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.2 / §10.3 / §10.4 / §10.10

口径:
  · 状态机 draft → released → staged → shipped → delivered → closed，
    旁支 cancelled（仅 shipped 之前）。
  · 交货行只挂 delivery 计划行（`schedule_kind='delivery'`，R-DN-0），
    行级冗余 order_line_id / item_id / uom_id 由计划行反查，不一致拒绝。
  · 超交判定 = `qty` > `promised_qty − delivered_qty`（R-DN-1）；
    计划行 `promised_qty` 为空视为不限量（历史数据兜底）。
  · ship confirm 是 `delivered_qty` 的唯一写入口，且**不写** fulfillment_status
    （INV-1：履约派生仍由 sales_order_fulfillment_service 唯一写入）。
  · ship confirm 幂等（R-DN-3）：已 shipped 及之后状态再次调用直接返回，不重复累加。
  · 事务边界由调用方控制（与 SalesOrderFulfillmentService 同构，本服务不自行开事务）。

覆写 `_load_*` / `_write_*` 即可注入测试数据。
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HEADER_TABLE = 'shipments'
LINE_TABLE = 'shipment_lines'
SCHEDULE_TABLE = 'sales_order_schedules'
ORDER_TABLE = 'sales_orders'
ORDER_LINE_TABLE = 'sales_order_lines'
ORG_TABLE = 'orgs'

SCHEDULE_KIND_DELIVERY = 'delivery'
SCHEDULE_PENDING_STATUSES = ('planned', 'confirmed')
SCHEDULE_STATUS_COMPLETED = 'completed'

STATUS_DRAFT = 'draft'
STATUS_RELEASED = 'released'
STATUS_STAGED = 'staged'
STATUS_SHIPPED = 'shipped'
STATUS_DELIVERED = 'delivered'
STATUS_CLOSED = 'closed'
STATUS_CANCELLED = 'cancelled'

#: 可编辑 / 可取消 / 可发运确认的抬头状态集合
EDITABLE_HEADER_STATUSES = (STATUS_DRAFT, STATUS_RELEASED)
CANCELLABLE_HEADER_STATUSES = (STATUS_DRAFT, STATUS_RELEASED)
SHIP_IDEMPOTENT_STATUSES = (STATUS_SHIPPED, STATUS_DELIVERED, STATUS_CLOSED)

#: 行级锁定状态（R-DN-7：禁止改 qty / schedule_id）
LOCKED_LINE_STATUSES = (STATUS_SHIPPED, STATUS_DELIVERED, STATUS_CANCELLED)

#: 发运后不可删除的抬头状态（R-DN-8）
UNDELETABLE_HEADER_STATUSES = (STATUS_SHIPPED, STATUS_DELIVERED, STATUS_CLOSED)


class ShipmentError(ValueError):
    """交货单守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _to_decimal(value: Any, field_name: str = 'qty') -> Decimal:
    """数值统一走 Decimal，避免浮点比较把 0.1+0.2 判成超交。"""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ShipmentError('数量必须是数字', field_name=field_name,
                            rule='DN_QTY_EXCEED')


def _blank(value: Any) -> bool:
    return value is None or value == ''


class ShipmentService:
    """交货单创建、状态流转与计划行交付量回写。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------ 创建

    def create_shipment(self, header: Dict[str, Any], lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """创建交货单头 + 行；返回 `{'id', 'delivery_no', 'status'}`。

        行可以为空（草稿允许后补行）；但一旦给行，逐行执行 R-DN-0 / R-DN-1。
        """
        header = dict(header or {})
        order = self._load_order(header.get('order_id'))
        if order is None:
            raise ShipmentError('来源销售订单不存在', field_name='order_id',
                                rule='DN_ORDER_NOT_FOUND')

        normalized = [self._validate_line(line, order) for line in (lines or [])]
        header = self._apply_header_defaults(header, order, normalized)

        now = _now()
        delivery_no = header.get('delivery_no') or self._next_delivery_no(order)
        row = {
            'delivery_no': delivery_no,
            'order_id': order['id'],
            'ship_from_location_id': header['ship_from_location_id'],
            'ship_to_party_id': header.get('ship_to_party_id'),
            'ship_to_address_text': header['ship_to_address_text'],
            'carrier_name': header.get('carrier_name'),
            'tracking_no': header.get('tracking_no'),
            'waybill_no': header.get('waybill_no'),
            'planned_ship_date': header.get('planned_ship_date'),
            'actual_ship_date': header.get('actual_ship_date'),
            'actual_arrival_date': header.get('actual_arrival_date'),
            'signature_ref': header.get('signature_ref'),
            'status': header.get('status') or STATUS_DRAFT,
            'source': header.get('source') or 'manual',
            'remark': header.get('remark'),
            'created_at': now,
            'updated_at': now,
        }
        delivery_id = self._insert_header(row)

        for item in normalized:
            self._insert_line(delivery_id, item, now)

        logger.info('[shipment] created id=%s no=%s lines=%s',
                    delivery_id, delivery_no, len(normalized))
        return {'id': delivery_id, 'delivery_no': delivery_no,
                'status': row['status'], 'order_id': order['id'],
                'line_ids': [item['order_line']['id'] for item in normalized]}

    # ------------------------------------------------------------------ 状态流转

    def release(self, delivery_id: Any) -> Dict[str, Any]:
        """draft → released（拣货释放）。"""
        header = self._require_header(delivery_id)
        if header['status'] != STATUS_DRAFT:
            raise ShipmentError('仅草稿交货单可释放', field_name='status',
                                rule='DN_STATE_INVALID')
        return self._transition_header(delivery_id, STATUS_RELEASED)

    def stage(self, delivery_id: Any) -> Dict[str, Any]:
        """released → staged（拣货确认 / 装箱）。"""
        header = self._require_header(delivery_id)
        if header['status'] != STATUS_RELEASED:
            raise ShipmentError('仅已释放交货单可拣货确认', field_name='status',
                                rule='DN_STATE_INVALID')
        return self._transition_header(delivery_id, STATUS_STAGED)

    def ship_confirm(self, delivery_id: Any,
                     actual_ship_date: Optional[str] = None) -> Dict[str, Any]:
        """staged → shipped：回写计划行 `delivered_qty` + 计划行状态（R-DN-1/3/4）。

        返回 `{'id', 'status', 'order_id', 'line_ids'}`，调用方据此触发
        `SalesOrderFulfillmentService.recompute_order(order_id)`（INV-1）。
        """
        header = self._require_header(delivery_id)
        if header['status'] in SHIP_IDEMPOTENT_STATUSES:
            return {'id': header['id'], 'status': header['status'],
                    'order_id': header['order_id'], 'line_ids': [],
                    'idempotent': True}
        if header['status'] != STATUS_STAGED:
            raise ShipmentError('仅拣货确认后的交货单可发运确认', field_name='status',
                                rule='DN_STATE_INVALID')

        lines = self._load_lines(delivery_id)
        if not lines:
            raise ShipmentError('交货单没有任何行，禁止发运确认',
                                field_name='lines', rule='DN_EMPTY')

        grouped: Dict[Any, Decimal] = {}
        for line in lines:
            if line['status'] == STATUS_CANCELLED:
                continue
            grouped[line['schedule_id']] = grouped.get(line['schedule_id'], Decimal('0')) \
                + _to_decimal(line['qty'])

        schedules: Dict[Any, Dict[str, Any]] = {}
        for schedule_id, qty in grouped.items():
            schedule = self._load_schedule(schedule_id)
            if schedule is None or schedule['schedule_kind'] != SCHEDULE_KIND_DELIVERY:
                raise ShipmentError('交货行指向的计划行无效或已删除',
                                    field_name='schedule_id',
                                    rule='DN_SCHEDULE_INVALID')
            self._assert_not_exceed(schedule, qty)
            schedules[schedule_id] = schedule

        now = actual_ship_date or _now()
        for schedule_id, qty in grouped.items():
            self._apply_schedule_delivery(schedule_id, qty, delivery_id, now)

        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE delivery_id = ? '
            'AND status <> ?' % LINE_TABLE,
            [STATUS_SHIPPED, now, delivery_id, STATUS_CANCELLED])
        self.ds.execute(
            'UPDATE %s SET status = ?, actual_ship_date = ?, updated_at = ? '
            'WHERE id = ?' % HEADER_TABLE,
            [STATUS_SHIPPED, now, now, delivery_id])

        order_line_ids = sorted({int(line['order_line_id']) for line in lines})
        logger.info('[shipment] ship_confirm id=%s schedules=%s', delivery_id,
                    list(grouped.keys()))
        return {'id': header['id'], 'status': STATUS_SHIPPED,
                'order_id': header['order_id'], 'line_ids': order_line_ids,
                'idempotent': False}

    def receive(self, delivery_id: Any, signature_ref: Optional[str] = None,
                actual_arrival_date: Optional[str] = None) -> Dict[str, Any]:
        """shipped → delivered（签收，可选环节）。"""
        header = self._require_header(delivery_id)
        if header['status'] == STATUS_DELIVERED:
            return {'id': header['id'], 'status': STATUS_DELIVERED,
                    'idempotent': True}
        if header['status'] != STATUS_SHIPPED:
            raise ShipmentError('仅已发运交货单可签收', field_name='status',
                                rule='DN_STATE_INVALID')
        now = actual_arrival_date or _now()
        self.ds.execute(
            'UPDATE %s SET status = ?, actual_arrival_date = ?, signature_ref = ?, '
            'updated_at = ? WHERE id = ?' % HEADER_TABLE,
            [STATUS_DELIVERED, now, signature_ref, now, delivery_id])
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE delivery_id = ? '
            'AND status <> ?' % LINE_TABLE,
            [STATUS_DELIVERED, now, delivery_id, STATUS_CANCELLED])
        return {'id': header['id'], 'status': STATUS_DELIVERED,
                'idempotent': False}

    def cancel(self, delivery_id: Any) -> Dict[str, Any]:
        """draft / released → cancelled（R-DN-2：shipped 之后不可取消）。"""
        header = self._require_header(delivery_id)
        if header['status'] not in CANCELLABLE_HEADER_STATUSES:
            raise ShipmentError('仅草稿或已释放的交货单可取消',
                                field_name='status', rule='DN_STATE_INVALID')
        now = _now()
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?' % HEADER_TABLE,
            [STATUS_CANCELLED, now, delivery_id])
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE delivery_id = ?' % LINE_TABLE,
            [STATUS_CANCELLED, now, delivery_id])
        return {'id': header['id'], 'status': STATUS_CANCELLED}

    # ------------------------------------------------------------------ 行编辑 / 删除

    def update_line(self, line_id: Any, patch: Dict[str, Any]) -> Dict[str, Any]:
        """编辑交货行（仅 draft / released 抬头；R-DN-7 行锁）。"""
        line = self._require_line(line_id)
        header = self._require_header(line['delivery_id'])

        patch = dict(patch or {})
        # R-DN-7 优先于抬头可编辑判定：已发运行改 qty / schedule_id 报 DN_LINE_LOCKED
        touches_locked = any(key in patch for key in ('qty', 'schedule_id'))
        if touches_locked and line['status'] in LOCKED_LINE_STATUSES:
            raise ShipmentError('已发运 / 已签收的行禁止修改数量或计划行',
                                field_name='qty', rule='DN_LINE_LOCKED')
        if header['status'] not in EDITABLE_HEADER_STATUSES:
            raise ShipmentError('仅草稿或已释放的交货单可编辑行',
                                field_name='status', rule='DN_STATE_INVALID')

        order = self._load_order(header['order_id'])
        merged = dict(line)
        merged.update({k: v for k, v in patch.items()
                       if k in ('schedule_id', 'qty', 'lot_no', 'serial_no')})
        if 'schedule_id' in patch and patch['schedule_id'] != line['schedule_id']:
            # 换计划行时冗余列由新计划行重算，旧值不得参与一致性校验
            merged.pop('order_line_id', None)
        normalized = self._validate_line(merged, order)

        values = {
            'schedule_id': normalized['schedule']['id'],
            'order_line_id': normalized['order_line']['id'],
            'item_id': normalized['order_line'].get('item_id'),
            'uom_id': normalized['order_line'].get('uom_id'),
            'qty': float(normalized['qty']),
            'lot_no': merged.get('lot_no'),
            'serial_no': merged.get('serial_no'),
            'updated_at': _now(),
        }
        self.ds.execute(
            'UPDATE %s SET schedule_id = ?, order_line_id = ?, item_id = ?, '
            'uom_id = ?, qty = ?, lot_no = ?, serial_no = ?, updated_at = ? '
            'WHERE id = ?' % LINE_TABLE,
            [values['schedule_id'], values['order_line_id'], values['item_id'],
             values['uom_id'], values['qty'], values['lot_no'],
             values['serial_no'], values['updated_at'], line['id']])
        result = dict(line)
        result.update(values)
        return result

    def validate_new_line(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """校验新建交货行并返回归一化冗余列（供守卫回填）。

        payload 需含 `delivery_id` 与 `schedule_id`；抬头须处于可编辑状态。
        """
        payload = dict(payload or {})
        header = self._require_header(payload.get('delivery_id'))
        if header['status'] not in EDITABLE_HEADER_STATUSES:
            raise ShipmentError('仅草稿或已释放的交货单可新增行',
                                field_name='status', rule='DN_STATE_INVALID')
        order = self._load_order(header['order_id'])
        if order is None:
            raise ShipmentError('来源销售订单不存在', field_name='order_id',
                                rule='DN_ORDER_NOT_FOUND')
        normalized = self._validate_line(payload, order)
        return {
            'schedule_id': normalized['schedule']['id'],
            'order_line_id': normalized['order_line']['id'],
            'item_id': normalized['order_line'].get('item_id'),
            'uom_id': normalized['order_line'].get('uom_id'),
            'qty': float(normalized['qty']),
        }

    def assert_deletable(self, delivery_id: Any) -> None:
        """R-DN-8：已发运 / 已签收单据不可删除（作废走批次 4 反向交货单）。"""
        header = self._require_header(delivery_id)
        if header['status'] in UNDELETABLE_HEADER_STATUSES:
            raise ShipmentError('已发运的交货单不可删除，请用反向交货单冲销',
                                field_name='status', rule='DN_DELETE_FORBIDDEN')

    # ------------------------------------------------------------------ 编号

    def _next_delivery_no(self, order: Dict[str, Any]) -> str:
        """`<ORG>-DN-<yyyyMM>-<seq>`；无独立编号服务，故在服务内自增。"""
        prefix = '%s-DN-%s-' % (self._org_code(order.get('org_id')),
                                self._period(order.get('order_date')))
        rows = self.ds.query(
            'SELECT delivery_no FROM %s WHERE delivery_no LIKE ? '
            'ORDER BY delivery_no DESC LIMIT 1' % HEADER_TABLE,
            [prefix + '%'])
        seq = 1
        if rows:
            tail = str(rows[0].get('delivery_no') or '').rsplit('-', 1)[-1]
            try:
                seq = int(tail) + 1
            except ValueError:
                seq = 1
        return '%s%04d' % (prefix, seq)

    @staticmethod
    def _period(order_date: Any) -> str:
        text = str(order_date or '')[:10]
        if len(text) >= 7 and text[4] == '-':
            return text[:4] + text[5:7]
        return datetime.now().strftime('%Y%m')

    def _org_code(self, org_id: Any) -> str:
        if _blank(org_id):
            return 'ORG'
        rows = self.ds.query('SELECT code FROM %s WHERE id = ?' % ORG_TABLE,
                             [org_id])
        code = rows[0].get('code') if rows else None
        return str(code) if not _blank(code) else 'ORG'

    # ------------------------------------------------------------------ 校验

    def _validate_line(self, line: Dict[str, Any],
                       order: Dict[str, Any]) -> Dict[str, Any]:
        """R-DN-0 / R-DN-1 + 冗余列一致性；返回归一化行。"""
        schedule_id = (line or {}).get('schedule_id')
        if _blank(schedule_id):
            raise ShipmentError('交货行必须挂 delivery 计划行',
                                field_name='schedule_id',
                                rule='DN_SCHEDULE_INVALID')
        schedule = self._load_schedule(schedule_id)
        if schedule is None:
            raise ShipmentError('计划行不存在', field_name='schedule_id',
                                rule='DN_SCHEDULE_INVALID')
        if schedule['schedule_kind'] != SCHEDULE_KIND_DELIVERY:
            raise ShipmentError('交货行只能挂 delivery 类计划行',
                                field_name='schedule_id',
                                rule='DN_SCHEDULE_INVALID')
        if schedule['status'] not in SCHEDULE_PENDING_STATUSES:
            raise ShipmentError('计划行状态不可交付（需 planned / confirmed）',
                                field_name='schedule_id',
                                rule='DN_SCHEDULE_INVALID')
        if schedule.get('order_id') != order['id']:
            raise ShipmentError('计划行不属于该交货单的来源订单',
                                field_name='schedule_id',
                                rule='DN_SCHEDULE_INVALID')

        order_line = self._load_order_line(schedule['line_id'])
        if order_line is None:
            raise ShipmentError('计划行对应的订单行不存在',
                                field_name='schedule_id',
                                rule='DN_SCHEDULE_INVALID')
        if not _blank(line.get('order_line_id')) \
                and int(line['order_line_id']) != int(order_line['id']):
            raise ShipmentError('交货行 order_line_id 与计划行反查结果不一致',
                                field_name='order_line_id',
                                rule='DN_SCHEDULE_INVALID')

        qty = _to_decimal(line.get('qty'))
        if qty <= 0:
            raise ShipmentError('交货数量必须大于 0', field_name='qty',
                                rule='DN_QTY_EXCEED')
        self._assert_not_exceed(schedule, qty)

        return {'schedule': schedule, 'order_line': order_line, 'qty': qty,
                'lot_no': line.get('lot_no'), 'serial_no': line.get('serial_no')}

    @staticmethod
    def _assert_not_exceed(schedule: Dict[str, Any], qty: Decimal) -> None:
        promised = schedule.get('promised_qty')
        if _blank(promised):
            return
        remaining = _to_decimal(promised) - _to_decimal(schedule.get('delivered_qty') or 0)
        if qty > remaining:
            raise ShipmentError(
                '交货数量超过计划行剩余可交付量（剩余 %s）' % remaining,
                field_name='qty', rule='DN_QTY_EXCEED')

    # ------------------------------------------------------------------ 默认值

    def _apply_header_defaults(self, header: Dict[str, Any],
                               order: Dict[str, Any],
                               lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        header = dict(header)
        if 'ship_to_party_id' not in header:
            header['ship_to_party_id'] = order.get('ship_to_party_id')
        if _blank(header.get('ship_to_address_text')):
            header['ship_to_address_text'] = order.get('ship_to_address_text')
        if _blank(header.get('ship_to_address_text')):
            raise ShipmentError('缺少收货地址快照', field_name='ship_to_address_text',
                                rule='DN_ADDRESS_REQUIRED')

        if _blank(header.get('ship_from_location_id')) and lines:
            header['ship_from_location_id'] = lines[0]['schedule'].get('plant_location_id')
        if _blank(header.get('ship_from_location_id')):
            raise ShipmentError('缺少发货库位', field_name='ship_from_location_id',
                                rule='DN_LOCATION_REQUIRED')

        if _blank(header.get('planned_ship_date')):
            dates = [item['schedule'].get('promised_date') for item in lines
                     if not _blank(item['schedule'].get('promised_date'))]
            if dates:
                header['planned_ship_date'] = min(dates)
        return header

    # ------------------------------------------------------------------ 持久化

    def _insert_header(self, row: Dict[str, Any]) -> int:
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            HEADER_TABLE, ', '.join(columns), ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [row[c] for c in columns])
        return int(getattr(cursor, 'lastrowid', 0) or 0)

    def _insert_line(self, delivery_id: int, item: Dict[str, Any], now: str) -> None:
        self.ds.execute(
            'INSERT INTO %s (delivery_id, schedule_id, order_line_id, item_id, '
            'uom_id, qty, lot_no, serial_no, status, created_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)' % LINE_TABLE,
            [delivery_id, item['schedule']['id'], item['order_line']['id'],
             item['order_line'].get('item_id'), item['order_line'].get('uom_id'),
             float(item['qty']), item.get('lot_no'), item.get('serial_no'),
             STATUS_DRAFT, now, now])

    def _transition_header(self, delivery_id: Any, status: str) -> Dict[str, Any]:
        now = _now()
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?' % HEADER_TABLE,
            [status, now, delivery_id])
        return {'id': int(delivery_id), 'status': status}

    def _apply_schedule_delivery(self, schedule_id: Any, qty: Decimal,
                                 delivery_id: Any, now: str) -> None:
        """ship confirm 唯一写计划行交付量（R-DN-1 满足则置 completed）。"""
        self.ds.execute(
            'UPDATE %s SET delivered_qty = COALESCE(delivered_qty, 0) + ?, '
            'status = CASE WHEN promised_qty IS NOT NULL '
            '              AND COALESCE(delivered_qty, 0) + ? >= promised_qty '
            '         THEN ? ELSE ? END, '
            'delivery_id = ?, updated_at = ? WHERE id = ?' % SCHEDULE_TABLE,
            [float(qty), float(qty), SCHEDULE_STATUS_COMPLETED, 'confirmed',
             delivery_id, now, schedule_id])

    # ------------------------------------------------------------------ 读取

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(order_id):
            return None
        rows = self.ds.query(
            'SELECT id, order_no, org_id, order_date, status, '
            'ship_to_party_id, ship_to_address_text FROM %s WHERE id = ?' % ORDER_TABLE,
            [order_id])
        return rows[0] if rows else None

    def _load_schedule(self, schedule_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(schedule_id):
            return None
        rows = self.ds.query(
            'SELECT id, order_id, line_id, schedule_kind, plant_location_id, '
            'promised_date, promised_qty, status, '
            'COALESCE(delivered_qty, 0) AS delivered_qty '
            'FROM %s WHERE id = ?' % SCHEDULE_TABLE, [schedule_id])
        return rows[0] if rows else None

    def _load_order_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(line_id):
            return None
        rows = self.ds.query(
            'SELECT id, order_id, item_id, uom_id, status FROM %s WHERE id = ?'
            % ORDER_LINE_TABLE, [line_id])
        return rows[0] if rows else None

    def _require_header(self, delivery_id: Any) -> Dict[str, Any]:
        if _blank(delivery_id):
            raise ShipmentError('交货单 ID 不能为空', field_name='id',
                                rule='DN_NOT_FOUND')
        rows = self.ds.query(
            'SELECT id, delivery_no, order_id, status FROM %s WHERE id = ?'
            % HEADER_TABLE, [delivery_id])
        if not rows:
            raise ShipmentError('交货单不存在', field_name='id',
                                rule='DN_NOT_FOUND')
        return rows[0]

    def _load_lines(self, delivery_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT id, delivery_id, schedule_id, order_line_id, item_id, uom_id, '
            'qty, lot_no, serial_no, status FROM %s WHERE delivery_id = ? '
            'ORDER BY id' % LINE_TABLE, [delivery_id])

    def _require_line(self, line_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT id, delivery_id, schedule_id, order_line_id, item_id, uom_id, '
            'qty, lot_no, serial_no, status FROM %s WHERE id = ?' % LINE_TABLE,
            [line_id])
        if not rows:
            raise ShipmentError('交货行不存在', field_name='id', rule='DN_NOT_FOUND')
        return rows[0]
