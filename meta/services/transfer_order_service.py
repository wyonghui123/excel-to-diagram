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

#: 审批状态（与业务状态 status 正交；事实源 tasks(type=approval)）
APPROVAL_NOT_REQUIRED = 'not_required'
APPROVAL_PENDING = 'pending'
APPROVAL_APPROVED = 'approved'
APPROVAL_REJECTED = 'rejected'

#: 终态：禁止 ship / receive / update（R-TO-13）
TERMINAL_STATUSES = (STATUS_CLOSED, STATUS_CANCELLED)

#: 无时间戳时要落库的最小列集
_HEADER_COLUMNS = (
    'id, transfer_order_no, document_type_id, transfer_date, status, '
    'approval_status, fulfillment_status, from_org_id, to_org_id, '
    'legal_entity_id, from_location_id, to_location_id, project_id, '
    'actual_ship_date, carrier_name, waybill_no, reversal_of_transfer_id')
_LINE_COLUMNS = (
    'id, transfer_order_id, line_no, line_type_id, item_id, uom_id, qty, '
    'qty_shipped, qty_received, status, fulfillment_status')

#: 超发 / 超收容差控制参数（百分数）
TOLERANCE_SHIP_PARAM = 'transfer_over_ship_percent'
TOLERANCE_RECEIVE_PARAM = 'transfer_over_receive_percent'


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


def resolve_tolerance_ratio(ds: Any, code: str,
                            header: Optional[Dict[str, Any]]) -> Decimal:
    """读取调拨超发 / 超收容差（百分数）→ 小数倍数（10 → 0.1）。

    参数缺失、读取失败或值非法时按 0 处理（等价「不允许超发 / 超收」）。
    """
    if ds is None or not header:
        return Decimal('0')
    dims = {
        'org_id': header.get('from_org_id'),
        'document_type_id': header.get('document_type_id'),
    }
    try:
        from meta.services.control_parameter_service import (
            ControlParameterResolver)
        value = ControlParameterResolver(ds).resolve(code, dims)
    except Exception as error:  # noqa: BLE001 - 参数表缺失不阻断单据
        logger.warning('[transfer_order] 读取容差参数 %s 失败，按 0 处理: %s',
                       code, error)
        return Decimal('0')
    if _blank(value):
        return Decimal('0')
    try:
        percent = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')
    if percent <= 0:
        return Decimal('0')
    return percent / Decimal('100')


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
            self._close_non_delivery_lines(header['id'], now)
            self.recompute_fulfillment(header['id'])
            logger.info('[transfer_order] released id=%s lines=%s',
                        header['id'], len(lines))
            return {'id': header['id'], 'status': STATUS_RELEASED,
                    'idempotent': False, 'line_count': len(lines)}

    # ------------------------------------------------------------------
    # 审批（与业务状态 status 正交；TO 无 submitted 状态）
    # ------------------------------------------------------------------
    def submit(self, transfer_order_id: Any) -> Dict[str, Any]:
        """草稿态提交审批：命中策略 → pending + 建任务；否则 approved。"""
        with self.ds.transaction():
            header = self._require_header(transfer_order_id)
            status = _status(header.get('status'))
            if status in TERMINAL_STATUSES:
                raise TransferOrderError(
                    '调拨单已处于终态 %s，禁止提交审批' % status,
                    field_name='status', rule='TO_TERMINAL_IMMUTABLE')
            if status != STATUS_DRAFT:
                raise TransferOrderError(
                    '仅草稿态调拨单可提交审批', field_name='status',
                    rule='TO_STATE_INVALID')

            approval = (_status(header.get('approval_status'))
                        or APPROVAL_NOT_REQUIRED)
            if approval == APPROVAL_PENDING:
                raise TransferOrderError(
                    '调拨单已在审批中，禁止重复提交',
                    field_name='approval_status', rule='TO_APPROVAL_PENDING')
            if approval == APPROVAL_APPROVED:
                raise TransferOrderError(
                    '调拨单审批已通过，禁止重复提交',
                    field_name='approval_status',
                    rule='TO_APPROVAL_ALREADY_APPROVED')

            from meta.services.document_approval_service import (
                DocumentApprovalResolver)
            try:
                decision = DocumentApprovalResolver(self.ds).resolve(
                    'transfer_order', header['id'])
            except Exception as error:  # noqa: BLE001 - 策略表缺失 / 条件求值异常
                raise TransferOrderError(
                    '审批策略解析失败: %s' % error,
                    field_name='approval_status',
                    rule='TO_APPROVAL_RESOLVE_FAILED')

            required = bool(decision.get('required'))
            target = APPROVAL_PENDING if required else APPROVAL_APPROVED
            now = _now()
            self.ds.execute(
                'UPDATE %s SET approval_status = ?, updated_at = ? WHERE id = ?'
                % HEADER_TABLE, [target, now, header['id']])

            task_id = None
            if required:
                task_id = self._create_approval_task(
                    header['id'], decision.get('snapshot'))
            logger.info('[transfer_order] submitted approval id=%s target=%s task=%s',
                        header['id'], target, task_id)
            return {
                'id': header['id'],
                'status': header.get('status'),
                'approval_status': target,
                'required': required,
                'policy_code': decision.get('policy_code'),
                'task_id': task_id,
            }

    def withdraw(self, transfer_order_id: Any) -> Dict[str, Any]:
        """审批中 → 免审批（撤回审批），并尽量关闭在途审批任务。"""
        with self.ds.transaction():
            header = self._require_header(transfer_order_id)
            status = _status(header.get('status'))
            if status in TERMINAL_STATUSES:
                raise TransferOrderError(
                    '调拨单已处于终态 %s，禁止撤回审批' % status,
                    field_name='status', rule='TO_TERMINAL_IMMUTABLE')
            approval = (_status(header.get('approval_status'))
                        or APPROVAL_NOT_REQUIRED)
            if approval != APPROVAL_PENDING:
                raise TransferOrderError(
                    '调拨单当前审批状态 %s，无法撤回' % approval,
                    field_name='approval_status',
                    rule='TO_APPROVAL_NOT_PENDING')

            now = _now()
            self.ds.execute(
                'UPDATE %s SET approval_status = ?, updated_at = ? WHERE id = ?'
                % HEADER_TABLE, [APPROVAL_NOT_REQUIRED, now, header['id']])
            self._close_approval_tasks(header['id'], 'cancelled')
            logger.info('[transfer_order] withdrawn approval id=%s', header['id'])
            return {'id': header['id'], 'status': header.get('status'),
                    'approval_status': APPROVAL_NOT_REQUIRED}

    def _create_approval_task(self, transfer_order_id: Any,
                              snapshot: Optional[Dict[str, Any]]) -> Optional[str]:
        """建审批待办；失败只告警，不回滚已落的 approval_status（同 PO 口径）。"""
        try:
            from meta.services.approval_task_service import ApprovalTaskService
            return ApprovalTaskService(self.ds).create_task(
                'transfer_order', transfer_order_id,
                policy_snapshot=snapshot, actor='')
        except Exception as error:  # noqa: BLE001 - 任务表缺失不阻断提交
            logger.warning('[transfer_order] 建审批任务失败（跳过）: %s', error)
            return None

    def _close_approval_tasks(self, transfer_order_id: Any,
                              target_status: str) -> None:
        """把该单在途审批任务归位到 target_status（done / failed / cancelled）。"""
        try:
            self.ds.execute(
                'UPDATE tasks SET status = ? WHERE type = ? AND doc_ref = ? '
                'AND status NOT IN (?, ?, ?, ?, ?)',
                [target_status, 'approval', str(transfer_order_id),
                 'done', 'failed', 'cancelled', 'skipped', 'dead'])
        except Exception as error:  # noqa: BLE001 - 任务表缺失 / 旧库不阻断
            logger.warning('[transfer_order] 归位审批任务失败（跳过）: %s', error)

    # ------------------------------------------------------------------
    # 反向调拨
    # ------------------------------------------------------------------
    def allocate_transfer_order_no(self, document_type_id: Any,
                                   transfer_date: Any) -> str:
        """按单据类型指向的序列取号（必须在开事务前调用，允许跳号）。"""
        if _blank(document_type_id) or _blank(transfer_date):
            raise TransferOrderError(
                '调拨单类型或日期缺失，无法取号',
                field_name='transfer_order_no', rule='TO_NUMBER_REQUIRED')
        rows = self.ds.query(
            'SELECT number_sequence_id FROM type_definitions WHERE id = ?',
            [document_type_id])
        sequence_id = rows[0].get('number_sequence_id') if rows else None
        if _blank(sequence_id):
            raise TransferOrderError(
                '调拨单类型未绑定编号序列', field_name='transfer_order_no',
                rule='TO_NUMBER_REQUIRED')
        configs = self.ds.query(
            'SELECT code, pattern, scope_fields, date_field, start_value, '
            'on_exhaust FROM number_sequences WHERE id = ?', [sequence_id])
        if not configs:
            raise TransferOrderError(
                '编号序列 %s 不存在' % sequence_id,
                field_name='transfer_order_no', rule='TO_NUMBER_REQUIRED')
        from meta.core.number_sequence_engine import (
            NumberSequenceEngine, NumberSequenceError)
        try:
            return NumberSequenceEngine(self.ds).allocate(
                dict(configs[0]), {}, {'transfer_date': transfer_date})
        except NumberSequenceError as error:
            raise TransferOrderError(
                str(error), field_name='transfer_order_no',
                rule='TO_NUMBER_REQUIRED')

    def create_reversal(self, original_id: Any, transfer_date: Any = None,
                        user_context: Any = None) -> Dict[str, Any]:
        """由原单生成反向草稿调拨单（调出 / 调入组织与库位互换）。

        原单保持不动；反向单只做草稿，行号重排为 10 / 20 / 30，
        `qty_shipped` / `qty_received` 归零。非交付行照抄，release 时关闭。
        取消态原单或已存在反向单的原单拒绝。
        """
        original = self._require_header(original_id)
        self._assert_reversible(original)
        date = str(transfer_date or original.get('transfer_date') or '').strip()
        if _blank(date):
            raise TransferOrderError(
                '调拨日期必填', field_name='transfer_date',
                rule='TO_DATE_REQUIRED')

        # 取号必须在事务外完成（号段独立提交，回滚不吞号）
        number = self.allocate_transfer_order_no(
            original.get('document_type_id'), date)

        with self.ds.transaction():
            original = self._require_header(original_id)
            self._assert_reversible(original)
            now = _now()
            cursor = self.ds.execute(
                'INSERT INTO %s (transfer_order_no, document_type_id, '
                'transfer_date, status, from_org_id, to_org_id, legal_entity_id, '
                'from_location_id, to_location_id, project_id, '
                'reversal_of_transfer_id, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)' % HEADER_TABLE,
                [number, original.get('document_type_id'), date, STATUS_DRAFT,
                 original.get('to_org_id'), original.get('from_org_id'),
                 original.get('legal_entity_id'), original.get('to_location_id'),
                 original.get('from_location_id'), original.get('project_id'),
                 original.get('id'), now, now])
            new_id = int(getattr(cursor, 'lastrowid', 0) or 0)
            lines = self._load_lines(original['id'])
            for index, line in enumerate(lines, start=1):
                self.ds.execute(
                    'INSERT INTO %s (transfer_order_id, line_no, line_type_id, '
                    'item_id, uom_id, qty, qty_shipped, qty_received, status, '
                    'created_at, updated_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)' % LINE_TABLE,
                    [new_id, index * 10, line.get('line_type_id'),
                     line.get('item_id'), line.get('uom_id'),
                     float(_num(line.get('qty'))), LINE_STATUS_OPEN, now, now])

        logger.info('[transfer_order] reversal created id=%s original=%s lines=%s',
                    new_id, original['id'], len(lines))
        return {'id': new_id, 'transfer_order_no': number,
                'status': STATUS_DRAFT,
                'reversal_of_transfer_id': original['id'],
                'line_count': len(lines)}

    def _assert_reversible(self, original: Dict[str, Any]) -> None:
        if _status(original.get('status')) == STATUS_CANCELLED:
            raise TransferOrderError(
                '原调拨单已取消，不能生成反向调拨',
                field_name='reversal_of_transfer_id',
                rule='TO_REVERSAL_ORIGINAL_CANCELLED')
        existing = self._find_reversal(original['id'])
        if existing:
            raise TransferOrderError(
                '原调拨单 ID=%s 已存在反向单 ID=%s'
                % (original['id'], existing.get('id')),
                field_name='reversal_of_transfer_id',
                rule='TO_REVERSAL_EXISTS')

    def _find_reversal(self, transfer_order_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id FROM %s WHERE reversal_of_transfer_id = ? LIMIT 1'
                % HEADER_TABLE, [transfer_order_id])
        except Exception as error:  # noqa: BLE001 - 旧库列缺失不阻断
            logger.warning('[transfer_order] 查询反向单失败: %s', error)
            return None
        return rows[0] if rows else None

    def _close_non_delivery_lines(self, transfer_order_id: Any,
                                  now: str) -> None:
        """release 时关闭 `delivery_relevant=0` 的行（服务行 / 资产行 / 文本行）。"""
        try:
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? '
                'WHERE transfer_order_id = ? AND status = ? AND line_type_id IN '
                '(SELECT id FROM type_definitions '
                'WHERE COALESCE(delivery_relevant, 1) = 0)' % LINE_TABLE,
                [LINE_STATUS_CLOSED, now, transfer_order_id, LINE_STATUS_OPEN])
        except Exception as error:  # noqa: BLE001 - 旧库无类型表不阻断
            logger.warning('[transfer_order] 关闭非交付行失败（跳过）: %s', error)

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
            serial_ready = self._serial_ready()
            if serial_ready:
                self._precheck_transfer_serials(header['id'], items)
            ratio = resolve_tolerance_ratio(
                self.ds, TOLERANCE_SHIP_PARAM, header)
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
                # R-TO-7 唯一判定点：条件 UPDATE 原子累加，rowcount=0 即超发；
                # 上限 = 计划量 × (1 + 超发容差)
                limit = _num(line.get('qty')) * (Decimal('1') + ratio)
                cursor = self.ds.execute(
                    'UPDATE %s SET qty_shipped = COALESCE(qty_shipped, 0) + ?, '
                    'updated_at = ? WHERE id = ? AND transfer_order_id = ? '
                    'AND status = ? AND COALESCE(qty_shipped, 0) + ? <= ?'
                    % LINE_TABLE,
                    [float(qty), now, line_id, header['id'],
                     LINE_STATUS_OPEN, float(qty), float(limit)])
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

            # 库存出账：发货即转出（同事务；开关关闭时 post() 内部自动跳过）
            event_key = self._post_ship_inventory(header, items, ship_date)
            if serial_ready:
                self._register_transfer_serials(
                    header['id'], items, event_key, ship_date)

            self.recompute_fulfillment(header['id'])
            fresh = self._require_header(header['id'])
            logger.info('[transfer_order] shipped id=%s lines=%s',
                        header['id'], len(items))
            return {'id': fresh['id'], 'status': fresh.get('status'),
                    'fulfillment_status': fresh.get('fulfillment_status'),
                    'actual_ship_date': fresh.get('actual_ship_date'),
                    'line_ids': sorted(items.keys())}

    # ------------------------------------------------------------- 库存过账
    def _post_ship_inventory(self, header: Dict[str, Any],
                             items: Dict[Any, Any],
                             ship_date: Any = None) -> Optional[str]:
        """发货出账：按本次发货行写 ISSUE_TO_SHIP（org/location = 调出方）。

        返回本次库存事件键，供序列号事件桥接；开关关闭 / 无分录时返回 None。
        """
        from meta.services.inventory_guard_service import (
            InventoryError, InventoryGuardService)
        from meta.services.inventory_posting_service import (
            InventoryPostingService,
        )

        if not InventoryGuardService(self.ds).posting_enabled():
            return None

        event_seq = self.ds.query(
            'SELECT COUNT(DISTINCT source_event_key) AS c '
            'FROM inventory_transactions '
            "WHERE source_doc_type = 'transfer_order' AND source_doc_id = ? "
            "AND source_event_key LIKE 'transfer_order:%:ship:%'",
            [header['id']])
        seq = int((event_seq[0].get('c') if event_seq else 0) or 0) + 1
        event_key = 'transfer_order:%s:ship:%s' % (header['id'], seq)

        entries = []
        for line_id, qty in items.items():
            line = self._load_line(line_id) or {}
            entries.append({
                'transaction_type': 'ISSUE_TO_SHIP',
                'transaction_date': ship_date or header.get('actual_ship_date'),
                'org_id': header.get('from_org_id'),
                'location_id': header.get('from_location_id'),
                'item_id': line.get('item_id'),
                'uom_id': line.get('uom_id'),
                'qty': float(qty),
                'stock_status': 'unrestricted',
                'source_line_id': line_id,
                'remark': '调拨单 %s 发货' % header.get('order_no'),
            })
        if not entries:
            return None

        source = {
            'source_doc_type': 'transfer_order',
            'source_doc_id': header['id'],
            'source_event_key': event_key,
            'transaction_date': ship_date or header.get('actual_ship_date'),
            'remark': '调拨单 %s 发货' % header.get('order_no'),
        }
        try:
            InventoryPostingService(self.ds).post(entries, source)
        except InventoryError as e:
            raise TransferOrderError(
                e.message, field_name='inventory', rule=e.code)
        return event_key

    # ------------------------------------------------------------- 序列号钩子
    def _serial_ready(self) -> bool:
        from meta.services.serial_number_service import serial_schema_ready
        return serial_schema_ready(self.ds)

    def _precheck_transfer_serials(self, transfer_order_id: Any,
                                   items: Dict[Any, Any]) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService)
        try:
            SerialNumberService(self.ds).precheck_transfer_ship(
                transfer_order_id, items)
        except SerialNumberError as error:
            raise TransferOrderError(
                str(error), field_name=error.field_name or 'serial_no',
                rule=error.rule or 'SERIAL_ERROR')

    def _register_transfer_serials(self, transfer_order_id: Any,
                                   items: Dict[Any, Any],
                                   event_key: Any = None,
                                   ship_date: Any = None) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService)
        try:
            SerialNumberService(self.ds).register_transfer_ship(
                transfer_order_id, items, event_key=event_key,
                txn_date=ship_date)
        except SerialNumberError as error:
            raise TransferOrderError(
                str(error), field_name=error.field_name or 'serial_no',
                rule=error.rule or 'SERIAL_ERROR')

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
            ratio = resolve_tolerance_ratio(
                self.ds, TOLERANCE_RECEIVE_PARAM, header)
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
                    # 条件 UPDATE 原子累加：不得超过已发货量 × (1 + 超收容差)
                    limit = _num(line.get('qty_shipped')) * (
                        Decimal('1') + ratio)
                    cursor = self.ds.execute(
                        'UPDATE %s SET qty_received = COALESCE(qty_received, 0) + ?, '
                        'updated_at = ? WHERE id = ? AND transfer_order_id = ? '
                        'AND COALESCE(qty_received, 0) + ? <= ?'
                        % LINE_TABLE,
                        [float(net), now, line_id, header['id'],
                         float(net), float(limit)])
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
        # 取消行不参与；release 时关闭的非交付行（未收货）也不参与，
        # 但「收满后自动关闭」的行仍算已收（否则重算会把 received 打回
        # partially_received）。
        active = []
        for line in lines:
            status = _status(line.get('status'))
            if status == LINE_STATUS_CANCELLED:
                continue
            if (status == LINE_STATUS_CLOSED
                    and _num(line.get('qty_received')) < _num(line.get('qty'))):
                continue
            active.append(line)
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
