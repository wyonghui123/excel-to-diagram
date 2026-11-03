# -*- coding: utf-8 -*-
"""序列号服务 —— 建档、录号校验、状态流转、过账登记与按号查历史（P6a）。

依据: docs/specs/p6-serial-number-model/spec.md §5 / §6
口径:
  · serial_numbers 是当前态投影；serial_transactions 是事件真相（D4）。
  · 唯一键 (item_id, org_id, serial_no)；跨组织同号允许（D2）。
  · 状态流转只走本服务的白名单，禁止任意跳转（D11）。
  · 数量账不加 serial_id；桥接放 serial_transactions.inventory_transaction_id（D5）。
  · 反冲只写反向事件并回退状态，不删除 document_serial_links（D13）。
  · 单据行 serial_no 只承载 qty=1 快捷录入；qty>1 必须已有等量 link（D7）。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SERIAL_TABLE = 'serial_numbers'
SERIAL_TX_TABLE = 'serial_transactions'
LINK_TABLE = 'document_serial_links'
ITEM_TABLE = 'items'
ORG_TABLE = 'orgs'
LOCATION_TABLE = 'locations'
RECEIPT_TABLE = 'receipts'
RECEIPT_LINE_TABLE = 'receipt_lines'
SHIPMENT_TABLE = 'shipments'
SHIPMENT_LINE_TABLE = 'shipment_lines'
INV_TX_TABLE = 'inventory_transactions'

DOC_RECEIPT = 'receipt'
DOC_SHIPMENT = 'shipment'

STATUS_DEFINED = 'defined'
STATUS_IN_STORES = 'in_stores'
STATUS_IN_TRANSIT = 'in_transit'
STATUS_ISSUED = 'issued'
STATUS_SHIPPED = 'shipped'
STATUS_CONSUMED = 'consumed'
STATUS_RETURNED = 'returned'
STATUS_SCRAPPED = 'scrapped'

USAGE_STATUSES = (STATUS_DEFINED, STATUS_IN_STORES, STATUS_IN_TRANSIT,
                  STATUS_ISSUED, STATUS_SHIPPED, STATUS_CONSUMED,
                  STATUS_RETURNED, STATUS_SCRAPPED)
QUALITY_STATUSES = ('unrestricted', 'inspection', 'blocked')
SOURCE_TYPES = ('received', 'produced', 'opening', 'issue_created')
RELATION_TYPES = ('assembly', 'packaging')

TXN_CREATE = 'create'
TXN_RECEIVE = 'receive'
TXN_SHIP = 'ship'
TXN_ADJUST = 'adjust'
TXN_STATUS_CHANGE = 'status_change'
TXN_TYPES = (TXN_CREATE, TXN_RECEIVE, 'issue', 'transfer_out', 'transfer_in',
             TXN_SHIP, 'return', TXN_ADJUST, TXN_STATUS_CHANGE, 'scrap')

#: 状态流转白名单（§3.5）。scrapped 为终态，不可再流转。
TRANSITIONS = {
    STATUS_DEFINED: (STATUS_IN_STORES, STATUS_SCRAPPED),
    STATUS_IN_STORES: (STATUS_ISSUED, STATUS_IN_TRANSIT, STATUS_SCRAPPED),
    STATUS_IN_TRANSIT: (STATUS_IN_STORES, STATUS_SCRAPPED),
    STATUS_ISSUED: (STATUS_SHIPPED, STATUS_CONSUMED, STATUS_RETURNED,
                    STATUS_SCRAPPED),
    STATUS_SHIPPED: (STATUS_SCRAPPED,),
    STATUS_CONSUMED: (STATUS_SCRAPPED,),
    STATUS_RETURNED: (STATUS_IN_STORES, STATUS_SCRAPPED),
    STATUS_SCRAPPED: (),
}

#: 可发运 / 可领用的在库状态（§5 validate_line_serials）
OUTBOUND_ALLOWED = (STATUS_IN_STORES, STATUS_ISSUED)


class SerialNumberError(Exception):
    """序列号业务校验错误（拦截器转为 ValidationFailedError）。"""

    def __init__(self, message: str, field_name: Optional[str] = None,
                 rule: str = ''):
        super().__init__(message)
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


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class SerialNumberService:
    """序列号主档 / 事件账 / 单据关系的唯一写入口。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 建档
    # ------------------------------------------------------------------
    def create_serial(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """手工建档：初始 usage_status=defined，并写 create 事件。"""
        data = dict(payload or {})
        item_id = data.get('item_id')
        org_id = data.get('org_id')
        serial_no = str(data.get('serial_no') or '').strip()
        if _blank(item_id):
            raise SerialNumberError('物料不能为空', field_name='item_id',
                                    rule='SERIAL_ITEM_REQUIRED')
        if _blank(org_id):
            raise SerialNumberError('库存组织不能为空', field_name='org_id',
                                    rule='SERIAL_ORG_REQUIRED')
        if not serial_no:
            raise SerialNumberError('序列号不能为空', field_name='serial_no',
                                    rule='SERIAL_NO_REQUIRED')
        if len(serial_no) > 64:
            raise SerialNumberError('序列号不能超过 64 个字符',
                                    field_name='serial_no',
                                    rule='SERIAL_NO_TOO_LONG')
        item = self._require_item(item_id)
        if not bool(item.get('serial_tracked')):
            raise SerialNumberError('该物料未启用序列号管理',
                                    field_name='item_id',
                                    rule='SERIAL_ITEM_NOT_TRACKED')
        self._require_row(ORG_TABLE, org_id, '库存组织', 'SERIAL_ORG_NOT_FOUND')
        source_type = str(data.get('source_type') or 'received')
        self._assert_source_type(source_type)
        quality_status = str(data.get('quality_status') or 'unrestricted')
        self._assert_quality_status(quality_status)
        if self._find_serial(item_id, org_id, serial_no):
            raise SerialNumberError(
                '同一物料同一组织下序列号已存在',
                field_name='serial_no', rule='SERIAL_DUPLICATE')

        now = _now()
        with self.ds.transaction():
            cursor = self.ds.execute(
                'INSERT INTO %s (item_id, org_id, serial_no, uii, batch_id, '
                ' revision, usage_status, quality_status, current_location_id, '
                ' parent_serial_id, relation_type, parent_item_id, source_type, '
                ' source_doc_type, source_doc_id, received_at, produced_at, '
                ' remark, created_at, updated_at) '
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                % SERIAL_TABLE,
                [item_id, org_id, serial_no, data.get('uii'),
                 data.get('batch_id'), data.get('revision'), STATUS_DEFINED,
                 quality_status, data.get('current_location_id'),
                 data.get('parent_serial_id'), data.get('relation_type'),
                 data.get('parent_item_id'), source_type,
                 data.get('source_doc_type'), data.get('source_doc_id'),
                 data.get('received_at'), data.get('produced_at'),
                 data.get('remark'), now, now])
            serial_id = cursor.lastrowid
            self._insert_txn(
                serial_id, TXN_CREATE, now, org_to_id=org_id,
                usage_to=STATUS_DEFINED, quality_to=quality_status,
                doc_type=data.get('source_doc_type'),
                doc_id=data.get('source_doc_id'),
                remark=data.get('remark') or '建档')
        logger.info('[serial] created id=%s no=%s item=%s org=%s',
                    serial_id, serial_no, item_id, org_id)
        return {'id': serial_id, 'item_id': item_id, 'org_id': org_id,
                'serial_no': serial_no, 'usage_status': STATUS_DEFINED}

    # ------------------------------------------------------------------
    # 行级录号校验
    # ------------------------------------------------------------------
    def validate_line_serials(self, item_id: Any, org_id: Any, qty: Any,
                              serials: Optional[List[Any]], direction: str,
                              doc: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """校验一行单据的序列号集合，返回主档行。

        · serial_tracked=0 时 serials 必须为空；
        · 数量必须等于 qty；同批不得重复；
        · out 方向所有号必须 in_stores / issued。
        """
        item = self._require_item(item_id)
        refs = list(serials or [])
        if not bool(item.get('serial_tracked')):
            if refs:
                raise SerialNumberError('该物料未启用序列号管理，不能录入序列号',
                                        field_name='serial_no',
                                        rule='SERIAL_ITEM_NOT_TRACKED')
            return []
        expected = int(_as_float(qty))
        if expected <= 0:
            raise SerialNumberError('数量必须大于 0', field_name='qty',
                                    rule='SERIAL_COUNT_MISMATCH')
        if len(refs) != expected:
            raise SerialNumberError(
                '序列号数量必须等于单据数量 %s，实际 %s' % (expected, len(refs)),
                field_name='serial_no', rule='SERIAL_COUNT_MISMATCH')

        seen = set()
        rows: List[Dict[str, Any]] = []
        for ref in refs:
            serial_no = self._serial_ref(ref)
            if serial_no in seen:
                raise SerialNumberError('同一行内序列号重复：%s' % serial_no,
                                        field_name='serial_no',
                                        rule='SERIAL_DUPLICATE_IN_LINE')
            seen.add(serial_no)
            row = self._find_serial(item_id, org_id, serial_no)
            if row is None:
                raise SerialNumberError('序列号不存在：%s' % serial_no,
                                        field_name='serial_no',
                                        rule='SERIAL_NOT_FOUND')
            self._assert_org(row, org_id)
            if direction == 'out' \
                    and row.get('usage_status') not in OUTBOUND_ALLOWED:
                raise SerialNumberError(
                    '序列号 %s 当前状态 %s 不可出库' % (
                        serial_no, row.get('usage_status')),
                    field_name='serial_no', rule='SERIAL_NOT_AVAILABLE')
            rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # 过账前置校验（§6.1）
    # ------------------------------------------------------------------
    def precheck_receipt(self, receipt_id: Any) -> None:
        """收货过账前置：逐行校验快捷录入与 require_on_receipt 数量。"""
        lines = self.ds.query(
            'SELECT * FROM %s WHERE receipt_id = ? AND status <> ?'
            % RECEIPT_LINE_TABLE, [receipt_id, 'cancelled'])
        for line in lines:
            net = _as_float(line.get('qty_received')) \
                - _as_float(line.get('qty_rejected'))
            self._precheck_line(line, net, DOC_RECEIPT, 'require_on_receipt',
                                'SERIAL_RECEIPT_COUNT_MISMATCH')

    def precheck_shipment(self, shipment_id: Any) -> None:
        """发运过账前置：逐行校验快捷录入与 require_on_issue 数量。"""
        lines = self.ds.query(
            'SELECT * FROM %s WHERE delivery_id = ? AND status <> ?'
            % SHIPMENT_LINE_TABLE, [shipment_id, 'cancelled'])
        for line in lines:
            self._precheck_line(line, _as_float(line.get('qty')), DOC_SHIPMENT,
                                'require_on_issue',
                                'SERIAL_ISSUE_COUNT_MISMATCH')

    def _precheck_line(self, line: Dict[str, Any], qty: float,
                       doc_type: str, require_field: str,
                       count_rule: str) -> None:
        if qty <= 0:
            return
        item = self._require_item(line.get('item_id'))
        line_serial = str(line.get('serial_no') or '').strip()
        if not bool(item.get('serial_tracked')):
            if line_serial:
                raise SerialNumberError(
                    '物料未启用序列号管理，行内不能填写序列号',
                    field_name='serial_no', rule='SERIAL_ITEM_NOT_TRACKED')
            return
        links = self.line_link_count(doc_type, line.get('id'))
        if line_serial and qty > 1 and not links:
            raise SerialNumberError(
                '数量大于 1 时不能用单值序列号快捷录入，请走序列号子表',
                field_name='serial_no',
                rule='SERIAL_SINGLE_VALUE_WITH_MULTI_QTY')
        if bool(item.get(require_field)):
            expected = int(round(qty))
            actual = links if links else (1 if line_serial else 0)
            if actual != expected:
                raise SerialNumberError(
                    '序列号数量必须等于单据数量 %s，实际 %s' % (expected, actual),
                    field_name='serial_no', rule=count_rule)

    # ------------------------------------------------------------------
    # 过账登记
    # ------------------------------------------------------------------
    def register_receipt(self, receipt_id: Any) -> Dict[str, Any]:
        """收货过账后登记：建号或复用、写 receive 事件与 link、置 in_stores。"""
        header = self._require_row(RECEIPT_TABLE, receipt_id, '收货单',
                                   'SERIAL_RECEIPT_NOT_FOUND')
        org_id = header.get('inventory_org_id') or header.get('org_id')
        location_id = header.get('deliver_to_location_id')
        lines = self.ds.query(
            'SELECT * FROM %s WHERE receipt_id = ? AND status <> ?'
            % RECEIPT_LINE_TABLE, [receipt_id, 'cancelled'])
        registered = 0
        for line in lines:
            registered += self._register_receipt_line(
                header, line, org_id, location_id)
        logger.info('[serial] receipt=%s registered=%s', receipt_id, registered)
        return {'receipt_id': receipt_id, 'registered': registered}

    def _register_receipt_line(self, header: Dict[str, Any],
                               line: Dict[str, Any], org_id: Any,
                               location_id: Any) -> int:
        net = _as_float(line.get('qty_received')) \
            - _as_float(line.get('qty_rejected'))
        if net <= 0:
            return 0
        item = self._require_item(line.get('item_id'))
        line_serial = str(line.get('serial_no') or '').strip()
        if not bool(item.get('serial_tracked')):
            if line_serial:
                raise SerialNumberError(
                    '物料未启用序列号管理，行内不能填写序列号',
                    field_name='serial_no', rule='SERIAL_ITEM_NOT_TRACKED')
            return 0

        links = self._links(DOC_RECEIPT, line.get('id'))
        require = bool(item.get('require_on_receipt'))
        if not links and line_serial:
            if net > 1:
                raise SerialNumberError(
                    '数量大于 1 时不能用单值序列号快捷录入，请走序列号子表',
                    field_name='serial_no',
                    rule='SERIAL_SINGLE_VALUE_WITH_MULTI_QTY')
            serial = self._ensure_serial(
                item, org_id, line_serial, header, line,
                source_type='received')
            self._ensure_link(DOC_RECEIPT, header.get('id'), line.get('id'),
                              serial['id'], 'in')
            links = self._links(DOC_RECEIPT, line.get('id'))
        if require and int(round(net)) != len(links):
            raise SerialNumberError(
                '收货行序列号数量必须等于净收数量 %s，实际 %s' % (
                    int(round(net)), len(links)),
                field_name='serial_no', rule='SERIAL_RECEIPT_COUNT_MISMATCH')

        batch_id = self._resolve_batch_id(
            org_id, line.get('item_id'), line.get('lot_no'))
        event_key = 'receipt:%s:post' % header.get('id')
        inv_tx_id = self._find_inv_tx(event_key, line.get('id'))
        usage_location = line.get('putaway_location_id') or location_id
        txn_date = header.get('actual_arrival_date') or _now()
        count = 0
        for link in links:
            self._receive_one(
                link.get('serial_id'), org_id, usage_location, batch_id,
                header, line, inv_tx_id, txn_date)
            count += 1
        return count

    def _receive_one(self, serial_id: Any, org_id: Any, location_id: Any,
                     batch_id: Any, header: Dict[str, Any],
                     line: Dict[str, Any], inv_tx_id: Any,
                     txn_date: str) -> None:
        serial = self._require_row(SERIAL_TABLE, serial_id, '序列号',
                                   'SERIAL_NOT_FOUND')
        if serial.get('usage_status') == STATUS_SCRAPPED:
            raise SerialNumberError('已报废序列号不能再收货',
                                    field_name='serial_no',
                                    rule='SERIAL_STATUS_TRANSITION_INVALID')
        self._assert_org(serial, org_id)
        existing = self.ds.query(
            'SELECT id FROM %s WHERE serial_id = ? AND txn_type = ? '
            'AND doc_type = ? AND doc_id = ? AND line_id = ?' % SERIAL_TX_TABLE,
            [serial_id, TXN_RECEIVE, DOC_RECEIPT, header.get('id'),
             line.get('id')])
        now = _now()
        if not existing:
            usage_from = serial.get('usage_status')
            if usage_from not in (STATUS_DEFINED, STATUS_RETURNED,
                                  STATUS_IN_STORES):
                raise SerialNumberError(
                    '序列号 %s 当前状态 %s 不可收货' % (
                        serial.get('serial_no'), usage_from),
                    field_name='serial_no',
                    rule='SERIAL_STATUS_TRANSITION_INVALID')
            self._insert_txn(
                serial_id, TXN_RECEIVE, txn_date or now,
                inventory_transaction_id=inv_tx_id, org_to_id=org_id,
                location_to_id=location_id, batch_to_id=batch_id,
                usage_from=usage_from, usage_to=STATUS_IN_STORES,
                doc_type=DOC_RECEIPT, doc_id=header.get('id'),
                line_id=line.get('id'), remark='收货单 %s' % header.get('receipt_no'))
        self.ds.execute(
            'UPDATE %s SET usage_status = ?, current_location_id = ?, '
            'batch_id = COALESCE(?, batch_id), received_at = COALESCE(received_at, ?), '
            'updated_at = ? WHERE id = ?' % SERIAL_TABLE,
            [STATUS_IN_STORES, location_id, batch_id, now, now, serial_id])

    def register_shipment(self, shipment_id: Any) -> Dict[str, Any]:
        """发运过账后登记：校验在库、写 ship 事件与 link、置 shipped。"""
        header = self._require_row(SHIPMENT_TABLE, shipment_id, '交货单',
                                   'SERIAL_SHIPMENT_NOT_FOUND')
        org_id = self._shipment_org_id(header)
        location_id = header.get('ship_from_location_id')
        lines = self.ds.query(
            'SELECT * FROM %s WHERE delivery_id = ? AND status <> ?'
            % SHIPMENT_LINE_TABLE, [shipment_id, 'cancelled'])
        registered = 0
        for line in lines:
            registered += self._register_shipment_line(
                header, line, org_id, location_id)
        logger.info('[serial] shipment=%s registered=%s', shipment_id, registered)
        return {'shipment_id': shipment_id, 'registered': registered}

    def _register_shipment_line(self, header: Dict[str, Any],
                                line: Dict[str, Any], org_id: Any,
                                location_id: Any) -> int:
        qty = _as_float(line.get('qty'))
        if qty <= 0:
            return 0
        item = self._require_item(line.get('item_id'))
        line_serial = str(line.get('serial_no') or '').strip()
        if not bool(item.get('serial_tracked')):
            if line_serial:
                raise SerialNumberError(
                    '物料未启用序列号管理，行内不能填写序列号',
                    field_name='serial_no', rule='SERIAL_ITEM_NOT_TRACKED')
            return 0

        links = self._links(DOC_SHIPMENT, line.get('id'))
        require = bool(item.get('require_on_issue'))
        if not links and line_serial:
            if qty > 1:
                raise SerialNumberError(
                    '数量大于 1 时不能用单值序列号快捷录入，请走序列号子表',
                    field_name='serial_no',
                    rule='SERIAL_SINGLE_VALUE_WITH_MULTI_QTY')
            serial = self._find_serial(item.get('id'), org_id, line_serial)
            if serial is None:
                raise SerialNumberError('序列号不存在：%s' % line_serial,
                                        field_name='serial_no',
                                        rule='SERIAL_NOT_FOUND')
            self._ensure_link(DOC_SHIPMENT, header.get('id'), line.get('id'),
                              serial['id'], 'out')
            links = self._links(DOC_SHIPMENT, line.get('id'))
        if require and int(round(qty)) != len(links):
            raise SerialNumberError(
                '发运行序列号数量必须等于发运数量 %s，实际 %s' % (
                    int(round(qty)), len(links)),
                field_name='serial_no', rule='SERIAL_ISSUE_COUNT_MISMATCH')

        txn_date = header.get('actual_ship_date') or _now()
        count = 0
        for link in links:
            serial = self._require_row(
                SERIAL_TABLE, link.get('serial_id'), '序列号', 'SERIAL_NOT_FOUND')
            self._assert_org(serial, org_id)
            if serial.get('usage_status') not in OUTBOUND_ALLOWED:
                raise SerialNumberError(
                    '序列号 %s 当前状态 %s 不可发运' % (
                        serial.get('serial_no'), serial.get('usage_status')),
                    field_name='serial_no', rule='SERIAL_NOT_AVAILABLE')
            existing = self.ds.query(
                'SELECT id FROM %s WHERE serial_id = ? AND txn_type = ? '
                'AND doc_type = ? AND doc_id = ? AND line_id = ?'
                % SERIAL_TX_TABLE,
                [serial['id'], TXN_SHIP, DOC_SHIPMENT, header.get('id'),
                 line.get('id')])
            now = _now()
            if not existing:
                self._insert_txn(
                    serial['id'], TXN_SHIP, txn_date or now,
                    inventory_transaction_id=None, org_from_id=org_id,
                    location_from_id=serial.get('current_location_id'),
                    batch_from_id=serial.get('batch_id'),
                    usage_from=serial.get('usage_status'),
                    usage_to=STATUS_SHIPPED, doc_type=DOC_SHIPMENT,
                    doc_id=header.get('id'), line_id=line.get('id'),
                    remark='交货单 %s' % header.get('delivery_no'))
            self.ds.execute(
                'UPDATE %s SET usage_status = ?, current_location_id = NULL, '
                'shipped_at = COALESCE(shipped_at, ?), updated_at = ? WHERE id = ?'
                % SERIAL_TABLE, [STATUS_SHIPPED, now, now, serial['id']])
            count += 1
        return count

    # ------------------------------------------------------------------
    # 状态流转 / 反冲 / 追溯
    # ------------------------------------------------------------------
    def change_status(self, serial_id: Any, to_status: str,
                      reason: str = '',
                      doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """按 §3.5 白名单流转；非法跳转抛 SERIAL_STATUS_TRANSITION_INVALID。"""
        serial = self._require_row(SERIAL_TABLE, serial_id, '序列号',
                                   'SERIAL_NOT_FOUND')
        if to_status not in USAGE_STATUSES:
            raise SerialNumberError('未知用途状态：%s' % to_status,
                                    field_name='usage_status',
                                    rule='SERIAL_STATUS_INVALID')
        current = serial.get('usage_status')
        if current == STATUS_SCRAPPED:
            raise SerialNumberError('已报废序列号为终态，不可再流转',
                                    field_name='usage_status',
                                    rule='SERIAL_STATUS_TRANSITION_INVALID')
        if to_status not in TRANSITIONS.get(current, ()):
            raise SerialNumberError(
                '不允许从 %s 流转到 %s' % (current, to_status),
                field_name='usage_status',
                rule='SERIAL_STATUS_TRANSITION_INVALID')
        doc = dict(doc or {})
        now = _now()
        with self.ds.transaction():
            self._insert_txn(
                serial_id, TXN_STATUS_CHANGE, now,
                org_from_id=serial.get('org_id'),
                org_to_id=serial.get('org_id'),
                location_from_id=serial.get('current_location_id'),
                location_to_id=(None if to_status == STATUS_SHIPPED
                                else serial.get('current_location_id')),
                usage_from=current, usage_to=to_status,
                doc_type=doc.get('doc_type'), doc_id=doc.get('doc_id'),
                line_id=doc.get('line_id'), remark=reason or '状态变更')
            updates = ['usage_status = ?', 'updated_at = ?']
            params: List[Any] = [to_status, now]
            if to_status == STATUS_SHIPPED:
                updates.append('current_location_id = NULL')
                updates.append('shipped_at = COALESCE(shipped_at, ?)')
                params.append(now)
            if to_status == STATUS_SCRAPPED:
                updates.append('scrapped_at = COALESCE(scrapped_at, ?)')
                params.append(now)
            params.append(serial_id)
            self.ds.execute(
                'UPDATE %s SET %s WHERE id = ?' % (SERIAL_TABLE,
                                                   ', '.join(updates)), params)
        return {'id': serial_id, 'from_status': current, 'to_status': to_status}

    def reverse_serial_event(self, inventory_transaction_id: Any) -> Dict[str, Any]:
        """库存反冲：写反向事件并回退主档状态，不删除原 link（D13）。"""
        rows = self.ds.query(
            'SELECT * FROM %s WHERE inventory_transaction_id = ? ORDER BY id'
            % SERIAL_TX_TABLE, [inventory_transaction_id])
        now = _now()
        reversed_count = 0
        with self.ds.transaction():
            for row in rows:
                if not row.get('usage_to') or not row.get('usage_from'):
                    continue
                serial = self._require_row(
                    SERIAL_TABLE, row.get('serial_id'), '序列号',
                    'SERIAL_NOT_FOUND')
                if serial.get('usage_status') != row.get('usage_to'):
                    continue
                back = row.get('usage_from')
                self._insert_txn(
                    row.get('serial_id'), TXN_ADJUST, now,
                    inventory_transaction_id=inventory_transaction_id,
                    org_from_id=row.get('org_to_id'),
                    org_to_id=row.get('org_from_id'),
                    location_from_id=row.get('location_to_id'),
                    location_to_id=row.get('location_from_id'),
                    batch_from_id=row.get('batch_to_id'),
                    batch_to_id=row.get('batch_from_id'),
                    usage_from=row.get('usage_to'), usage_to=back,
                    doc_type=row.get('doc_type'), doc_id=row.get('doc_id'),
                    line_id=row.get('line_id'),
                    remark='库存反冲 #%s' % inventory_transaction_id)
                updates = ['usage_status = ?', 'updated_at = ?']
                params: List[Any] = [back, now]
                if back == STATUS_IN_STORES:
                    updates.append('current_location_id = ?')
                    params.append(row.get('location_from_id'))
                if back == STATUS_DEFINED:
                    updates.append('current_location_id = NULL')
                if row.get('usage_to') == STATUS_SHIPPED:
                    updates.append('shipped_at = NULL')
                params.append(row.get('serial_id'))
                self.ds.execute(
                    'UPDATE %s SET %s WHERE id = ?'
                    % (SERIAL_TABLE, ', '.join(updates)), params)
                reversed_count += 1
        return {'inventory_transaction_id': inventory_transaction_id,
                'reversed': reversed_count}

    def trace_serial(self, serial_no: Any,
                     org_id: Optional[Any] = None) -> Dict[str, Any]:
        """按号查历史：主档 + 事件时间线 + 关联单据；跨组织按 org 分组。"""
        serial_no = str(serial_no or '').strip()
        if not serial_no:
            raise SerialNumberError('序列号不能为空', field_name='serial_no',
                                    rule='SERIAL_NO_REQUIRED')
        sql = 'SELECT * FROM %s WHERE serial_no = ?' % SERIAL_TABLE
        params: List[Any] = [serial_no]
        if not _blank(org_id):
            sql += ' AND org_id = ?'
            params.append(org_id)
        rows = self.ds.query(sql + ' ORDER BY org_id, id', params)
        if not rows:
            raise SerialNumberError('序列号不存在：%s' % serial_no,
                                    field_name='serial_no',
                                    rule='SERIAL_NOT_FOUND')
        matches = []
        for serial in rows:
            transactions = self.ds.query(
                'SELECT * FROM %s WHERE serial_id = ? ORDER BY txn_date, id'
                % SERIAL_TX_TABLE, [serial['id']])
            documents = self.ds.query(
                'SELECT * FROM %s WHERE serial_id = ? ORDER BY id'
                % LINK_TABLE, [serial['id']])
            matches.append({
                'org_id': serial.get('org_id'),
                'serial': serial,
                'transactions': transactions,
                'documents': documents,
            })
        return {'serial_no': serial_no, 'matches': matches}

    # ------------------------------------------------------------------
    # 供过账钩子 / 拦截器使用的小工具
    # ------------------------------------------------------------------
    def validate_item_switches(self, payload: Dict[str, Any],
                               existing: Optional[Dict[str, Any]] = None) -> None:
        """require_on_receipt / require_on_issue 为 1 时 serial_tracked 必须为 1。"""
        merged = dict(existing or {})
        merged.update(payload or {})
        tracked = bool(merged.get('serial_tracked'))
        if not tracked and (merged.get('require_on_receipt')
                            or merged.get('require_on_issue')):
            raise SerialNumberError(
                '启用收货 / 发货强制录号前必须先启用序列号管理',
                field_name='serial_tracked',
                rule='SERIAL_ITEM_SWITCH_INVALID')

    def line_link_count(self, doc_type: str, line_id: Any) -> int:
        rows = self.ds.query(
            'SELECT COUNT(*) AS cnt FROM %s WHERE doc_type = ? AND line_id = ?'
            % LINK_TABLE, [doc_type, line_id])
        return int(rows[0]['cnt']) if rows else 0

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _require_item(self, item_id: Any) -> Dict[str, Any]:
        return self._require_row(ITEM_TABLE, item_id, '物料',
                                 'SERIAL_ITEM_NOT_FOUND')

    def _require_row(self, table: str, row_id: Any, label: str,
                     rule: str) -> Dict[str, Any]:
        if _blank(row_id):
            raise SerialNumberError('%s不能为空' % label,
                                    field_name='%s_id' % table.rstrip('s'),
                                    rule=rule)
        rows = self.ds.query('SELECT * FROM %s WHERE id = ?' % table, [row_id])
        if not rows:
            raise SerialNumberError('%s不存在：%s' % (label, row_id),
                                    field_name='%s_id' % table.rstrip('s'),
                                    rule=rule)
        return rows[0]

    def _find_serial(self, item_id: Any, org_id: Any,
                     serial_no: str) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE item_id = ? AND org_id = ? AND serial_no = ?'
            % SERIAL_TABLE, [item_id, org_id, serial_no])
        return rows[0] if rows else None

    def _ensure_serial(self, item: Dict[str, Any], org_id: Any, serial_no: str,
                       header: Dict[str, Any], line: Dict[str, Any],
                       source_type: str) -> Dict[str, Any]:
        row = self._find_serial(item.get('id'), org_id, serial_no)
        if row:
            return row
        now = _now()
        cursor = self.ds.execute(
            'INSERT INTO %s (item_id, org_id, serial_no, usage_status, '
            ' quality_status, source_type, source_doc_type, source_doc_id, '
            ' received_at, created_at, updated_at) '
            "VALUES (?, ?, ?, ?, 'unrestricted', ?, ?, ?, ?, ?, ?)"
            % SERIAL_TABLE,
            [item.get('id'), org_id, serial_no, STATUS_DEFINED, source_type,
             'receipt' if header.get('receipt_no') else 'shipment',
             header.get('id'), now, now, now])
        serial_id = cursor.lastrowid
        self._insert_txn(
            serial_id, TXN_CREATE, now, org_to_id=org_id,
            usage_to=STATUS_DEFINED, remark='过账快捷录入建档')
        return self._require_row(SERIAL_TABLE, serial_id, '序列号',
                                 'SERIAL_NOT_FOUND')

    def _ensure_link(self, doc_type: str, doc_id: Any, line_id: Any,
                     serial_id: Any, direction: str) -> None:
        if self.ds.query(
                'SELECT id FROM %s WHERE doc_type = ? AND line_id = ? '
                'AND serial_id = ?' % LINK_TABLE,
                [doc_type, line_id, serial_id]):
            return
        self.ds.execute(
            'INSERT INTO %s (doc_type, doc_id, line_id, serial_id, direction, '
            "created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))" % LINK_TABLE,
            [doc_type, doc_id, line_id, serial_id, direction])

    def _links(self, doc_type: str, line_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE doc_type = ? AND line_id = ? ORDER BY id'
            % LINK_TABLE, [doc_type, line_id])

    def _find_inv_tx(self, event_key: str, line_id: Any) -> Optional[Any]:
        rows = self.ds.query(
            'SELECT id FROM %s WHERE source_event_key = ? AND source_line_id = ?'
            % INV_TX_TABLE, [event_key, line_id])
        return rows[0]['id'] if rows else None

    def _resolve_batch_id(self, org_id: Any, item_id: Any,
                          lot_no: Any) -> Optional[Any]:
        if _blank(org_id) or _blank(item_id) or _blank(lot_no):
            return None
        rows = self.ds.query(
            'SELECT id FROM batches WHERE item_id = ? AND org_id = ? '
            'AND batch_no = ?', [item_id, org_id, str(lot_no).strip()])
        return rows[0]['id'] if rows else None

    def _shipment_org_id(self, header: Dict[str, Any]) -> Optional[Any]:
        location_id = header.get('ship_from_location_id')
        if not _blank(location_id):
            rows = self.ds.query(
                'SELECT org_id FROM %s WHERE id = ?' % LOCATION_TABLE,
                [location_id])
            if rows:
                return rows[0].get('org_id')
        return header.get('org_id')

    def _insert_txn(self, serial_id: Any, txn_type: str, txn_date: Any,
                    **fields: Any) -> int:
        if txn_type not in TXN_TYPES:
            raise SerialNumberError('未知事件类型：%s' % txn_type,
                                    field_name='txn_type',
                                    rule='SERIAL_TXN_TYPE_INVALID')
        columns = ['serial_id', 'txn_type', 'txn_date']
        values = [serial_id, txn_type, txn_date]
        for key in ('inventory_transaction_id', 'org_from_id', 'org_to_id',
                    'location_from_id', 'location_to_id', 'batch_from_id',
                    'batch_to_id', 'usage_from', 'usage_to', 'quality_from',
                    'quality_to', 'doc_type', 'doc_id', 'line_id', 'remark'):
            columns.append(key)
            values.append(fields.get(key))
        columns.append('created_at')
        values.append(_now())
        cursor = self.ds.execute(
            'INSERT INTO %s (%s) VALUES (%s)' % (
                SERIAL_TX_TABLE, ', '.join(columns),
                ', '.join(['?'] * len(columns))), values)
        return cursor.lastrowid

    def _serial_ref(self, ref: Any) -> str:
        if isinstance(ref, dict):
            return str(ref.get('serial_no') or ref.get('id') or '').strip()
        return str(ref or '').strip()

    def _assert_org(self, serial: Dict[str, Any], org_id: Any) -> None:
        if not _blank(org_id) and serial.get('org_id') != org_id:
            raise SerialNumberError(
                '序列号 %s 不属于当前库存组织' % serial.get('serial_no'),
                field_name='serial_no', rule='SERIAL_ORG_MISMATCH')

    def _assert_source_type(self, source_type: str) -> None:
        if source_type not in SOURCE_TYPES:
            raise SerialNumberError('未知来源类型：%s' % source_type,
                                    field_name='source_type',
                                    rule='SERIAL_SOURCE_TYPE_INVALID')

    def _assert_quality_status(self, quality_status: str) -> None:
        if quality_status not in QUALITY_STATUSES:
            raise SerialNumberError('未知质量状态：%s' % quality_status,
                                    field_name='quality_status',
                                    rule='SERIAL_QUALITY_STATUS_INVALID')
