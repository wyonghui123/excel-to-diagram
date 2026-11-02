# -*- coding: utf-8 -*-
"""调拨单守卫服务 —— 头 / 行 / 动作的写前校验。

依据: `.trae/specs/excel-to-diagram/define-transfer-order-object-model/spec.md`
      §3 对象模型 / §6 状态机 / §10 不变量 R-TO-0 ~ R-TO-13

口径:
  · 本服务只校验「能不能写 / 能不能迁」，不写任何业务字段；
    生命周期动作的实际写入由 `TransferOrderService` 承接。
  · 组织与法人：`from_org_id != to_org_id`、两组织存在且启用且具备 `inventory`
    职能；两组织沿 `parent_id` 上溯到的 `legal_entity` 职能组织必须是同一 id，
    解析失败或跨法人一律拒绝创建，不降级放行（R-TO-1 / R-TO-2）。
  · 数量：`qty > 0`；`0 <= qty_shipped <= qty`；`0 <= qty_received <= qty_shipped`
    （R-TO-4）。
  · 终态保护：`closed` / `cancelled` 禁止 ship / receive / update（R-TO-13）。

覆写 `_load_*` / `_org_has_function` 即可注入测试数据。
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from meta.services.transfer_order_service import (
    APPROVAL_NOT_REQUIRED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    LINE_STATUS_OPEN,
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_RELEASED,
    TOLERANCE_RECEIVE_PARAM,
    TOLERANCE_SHIP_PARAM,
    TERMINAL_STATUSES,
    TransferOrderError,
    resolve_tolerance_ratio,
)

logger = logging.getLogger(__name__)

HEADER_TABLE = 'transfer_orders'
LINE_TABLE = 'transfer_order_lines'
TYPE_TABLE = 'type_definitions'
ORG_TABLE = 'orgs'
ORG_FUNCTION_TABLE = 'org_functions'
ITEM_TABLE = 'items'
LOCATION_TABLE = 'locations'

SCOPE_BO = 'transfer_order'
FUNCTION_INVENTORY = 'inventory'
FUNCTION_LEGAL_ENTITY = 'legal_entity'
ITEM_TYPE_GOODS = 'goods'

#: 组织上溯找法人的最大层数（防 parent_id 成环）
_MAX_ORG_DEPTH = 50

#: 调拨单头类型 / 行类型归属（R-TO-0 / R-TO-3）
LEVEL_HEADER = 'header'
LEVEL_LINE = 'line'

#: released 后冻结的头字段（R-TO-5）
_FROZEN_HEADER_FIELDS = (
    'document_type_id', 'transfer_date', 'from_org_id', 'to_org_id',
    'legal_entity_id')

#: 行号递增步长（spec §3.2：10 / 20 / 30 …）
LINE_NO_STEP = 10


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _status(value: Any) -> str:
    return str(value or '').strip().lower()


def _is_active(value: Any) -> bool:
    """状态判定：空值按 active 兜底（存量组织 / 物料数据可能为空）。"""
    if _blank(value):
        return True
    return _status(value) == 'active'


def _dec(value: Any, field_name: str = 'qty') -> Optional[Decimal]:
    """宽松数值解析：空值返回 None，脏值抛业务错误。"""
    if _blank(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise TransferOrderError('数量必须是数字', field_name=field_name,
                                 rule='TO_QTY_INVALID')


class TransferOrderGuardService:
    """调拨单头 / 行 / 动作前置校验。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 头
    # ------------------------------------------------------------------
    def validate_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建草稿：头类型、日期、组织对、库存职能、同一法人（R-TO-0~2）。

        返回归一化后的头（含只读派生 `legal_entity_id`），供拦截器回填。
        """
        header = dict(data or {})
        self._validate_header_type(header.get('document_type_id'))
        if _blank(header.get('transfer_date')):
            raise TransferOrderError(
                '调拨日期必填', field_name='transfer_date',
                rule='TO_DATE_REQUIRED')
        for field in ('from_org_id', 'to_org_id'):
            if _blank(header.get(field)):
                raise TransferOrderError(
                    '调拨单缺少必填字段 %s' % field, field_name=field,
                    rule='TO_ORG_REQUIRED')

        from_org_id = header.get('from_org_id')
        to_org_id = header.get('to_org_id')
        if str(from_org_id) == str(to_org_id):
            raise TransferOrderError(
                '调出组织与调入组织不能相同', field_name='to_org_id',
                rule='TO_ORG_SAME')

        # 反向调拨：原单存在、非取消、组织与库位互换、原单尚无反向单
        reversal_of = header.get('reversal_of_transfer_id')
        if not _blank(reversal_of):
            original = self._load_header(reversal_of)
            if original is None:
                raise TransferOrderError(
                    '反向原单 %s 不存在' % reversal_of,
                    field_name='reversal_of_transfer_id',
                    rule='TO_REVERSAL_ORIGINAL_NOT_FOUND')
            if _status(original.get('status')) == STATUS_CANCELLED:
                raise TransferOrderError(
                    '反向原单 %s 已取消' % reversal_of,
                    field_name='reversal_of_transfer_id',
                    rule='TO_REVERSAL_ORIGINAL_CANCELLED')
            if (str(from_org_id) != str(original.get('to_org_id'))
                    or str(to_org_id) != str(original.get('from_org_id'))):
                raise TransferOrderError(
                    '反向调拨必须互换调出 / 调入组织',
                    field_name='to_org_id',
                    rule='TO_REVERSAL_ORG_NOT_SWAPPED')
            if (str(header.get('from_location_id'))
                    != str(original.get('to_location_id'))
                    or str(header.get('to_location_id'))
                    != str(original.get('from_location_id'))):
                raise TransferOrderError(
                    '反向调拨必须互换调出 / 调入库位',
                    field_name='to_location_id',
                    rule='TO_REVERSAL_LOCATION_NOT_SWAPPED')
            try:
                existing = self._query(
                    'SELECT id FROM %s WHERE reversal_of_transfer_id = ? LIMIT 1'
                    % HEADER_TABLE, [reversal_of])
            except Exception as error:  # noqa: BLE001 - 旧库列缺失不阻断
                logger.warning('[transfer_order_guard] 查询反向单失败: %s', error)
                existing = []
            if existing:
                raise TransferOrderError(
                    '反向原单 %s 已存在反向单 %s'
                    % (reversal_of, existing[0].get('id')),
                    field_name='reversal_of_transfer_id',
                    rule='TO_REVERSAL_EXISTS')

        self._require_inventory_org(from_org_id, 'from_org_id')
        self._require_inventory_org(to_org_id, 'to_org_id')
        header['legal_entity_id'] = self.resolve_legal_entity(
            from_org_id, to_org_id)

        # R-TO-11：库位可空；同时存在时必须不同
        from_location = header.get('from_location_id')
        to_location = header.get('to_location_id')
        if not _blank(from_location) and not _blank(to_location) \
                and str(from_location) == str(to_location):
            raise TransferOrderError(
                '调出库位与调入库位不能相同', field_name='to_location_id',
                rule='TO_LOCATION_SAME')
        return header

    def validate_update(self, data: Dict[str, Any],
                        old_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """更新头：仅 draft 可改；released 后冻结关键字段；终态拒绝（R-TO-5/13）。

        返回需要回填的派生字段（`legal_entity_id`）。
        """
        patch = dict(data or {})
        old = dict(old_data or {})
        old_status = _status(old.get('status')) or STATUS_DRAFT

        if old_status in TERMINAL_STATUSES:
            raise TransferOrderError(
                '调拨单已处于终态 %s，禁止修改' % old_status,
                field_name='status', rule='TO_TERMINAL_IMMUTABLE')
        if old_status != STATUS_DRAFT:
            for field in _FROZEN_HEADER_FIELDS:
                if field in patch and patch.get(field) != old.get(field):
                    raise TransferOrderError(
                        '调拨单已下达，字段 %s 不可修改' % field,
                        field_name=field, rule='TO_FIELD_IMMUTABLE')

        # 状态只能由 release / cancel / close 动作改变
        if 'status' in patch:
            target = _status(patch.get('status'))
            if target != old_status:
                raise TransferOrderError(
                    '调拨单状态不允许直接修改，请使用生命周期动作',
                    field_name='status', rule='TO_STATUS_ACTION_REQUIRED')

        if old_status != STATUS_DRAFT:
            return {}
        merged = dict(old)
        merged.update(patch)
        header = self.validate_create(merged)
        return {'legal_entity_id': header.get('legal_entity_id')}

    def validate_delete(self, transfer_order_id: Any) -> None:
        """仅 draft 可删除（R-TO-12）。"""
        header = self._load_header(transfer_order_id)
        if header is None:
            raise TransferOrderError('调拨单不存在', field_name='id',
                                     rule='TO_NOT_FOUND')
        if _status(header.get('status')) != STATUS_DRAFT:
            raise TransferOrderError(
                '仅草稿态调拨单允许删除', field_name='status',
                rule='TO_DELETE_ONLY_DRAFT')

    # ------------------------------------------------------------------
    # 行
    # ------------------------------------------------------------------
    def validate_line(self, data: Dict[str, Any],
                      transfer_order_id: Any = None) -> Dict[str, Any]:
        """行校验并返回可持久化的归一化字段（R-TO-3 / R-TO-4）。"""
        line = dict(data or {})
        to_id = transfer_order_id or line.get('transfer_order_id')
        if not _blank(to_id):
            header = self._load_header(to_id)
            if header is not None and _status(header.get('status')) \
                    in TERMINAL_STATUSES:
                raise TransferOrderError(
                    '调拨单已处于终态，禁止修改行', field_name='transfer_order_id',
                    rule='TO_TERMINAL_IMMUTABLE')
            if header is not None and _status(header.get('status')) \
                    != STATUS_DRAFT:
                raise TransferOrderError(
                    '仅草稿态调拨单允许新增 / 修改行', field_name='transfer_order_id',
                    rule='TO_LINE_ONLY_DRAFT')

        self._validate_line_type(line.get('line_type_id'))
        self._require_item(line.get('item_id'))
        self._require_uom(line.get('uom_id'))

        qty = _dec(line.get('qty'), 'qty')
        if qty is None or qty <= 0:
            raise TransferOrderError(
                '调拨数量必须大于 0', field_name='qty',
                rule='TO_LINE_QTY_POSITIVE')
        shipped = _dec(line.get('qty_shipped'), 'qty_shipped')
        shipped = shipped if shipped is not None else 0
        received = _dec(line.get('qty_received'), 'qty_received')
        received = received if received is not None else 0
        if shipped < 0 or shipped > qty:
            raise TransferOrderError(
                '已发货量必须在 0 与计划量之间', field_name='qty_shipped',
                rule='TO_LINE_SHIPPED_RANGE')
        if received < 0 or received > shipped:
            raise TransferOrderError(
                '已收货量必须在 0 与已发货量之间', field_name='qty_received',
                rule='TO_LINE_RECEIVED_RANGE')

        values = {
            'line_type_id': line.get('line_type_id'),
            'item_id': line.get('item_id'),
            'uom_id': line.get('uom_id'),
            'qty': float(qty),
            'qty_shipped': float(shipped),
            'qty_received': float(received),
        }
        # 行号：未传时按 10 / 20 / 30 递增生成（spec §3.2）
        line_no = line.get('line_no')
        if _blank(line_no) and not _blank(to_id):
            line_no = self._next_line_no(to_id)
        if not _blank(line_no):
            try:
                values['line_no'] = int(line_no)
            except (TypeError, ValueError):
                raise TransferOrderError(
                    '行号必须是整数', field_name='line_no',
                    rule='TO_LINE_NO_INVALID')
        return values

    # ------------------------------------------------------------------
    # 动作前置校验
    # ------------------------------------------------------------------
    def validate_release(self, transfer_order_id: Any) -> None:
        """下达：至少 1 行 + 头字段合法 + 行全部合法（R-TO-3）。"""
        header = self._load_header(transfer_order_id)
        if header is None:
            raise TransferOrderError('调拨单不存在', field_name='id',
                                     rule='TO_NOT_FOUND')
        status = _status(header.get('status'))
        if status in TERMINAL_STATUSES:
            raise TransferOrderError(
                '调拨单已处于终态 %s，禁止下达' % status,
                field_name='status', rule='TO_TERMINAL_IMMUTABLE')
        if status != STATUS_DRAFT:
            raise TransferOrderError(
                '仅草稿态调拨单可下达', field_name='status',
                rule='TO_STATE_INVALID')

        # 审批闸门：pending / rejected 拒绝下达；not_required / approved 放行
        approval = _status(header.get('approval_status')) or APPROVAL_NOT_REQUIRED
        if approval == APPROVAL_PENDING:
            raise TransferOrderError(
                '调拨单审批未完成，禁止下达', field_name='approval_status',
                rule='TO_APPROVAL_PENDING')
        if approval == APPROVAL_REJECTED:
            raise TransferOrderError(
                '调拨单审批已驳回，禁止下达', field_name='approval_status',
                rule='TO_APPROVAL_REJECTED')

        self.validate_create(header)
        lines = self._load_lines(header['id'])
        if not lines:
            raise TransferOrderError(
                '调拨单没有任何行，禁止下达', field_name='lines',
                rule='TO_NO_LINES')
        for line in lines:
            self.validate_line(line, header['id'])

    def validate_ship(self, transfer_order_id: Any,
                      lines: List[Dict[str, Any]]) -> None:
        """发货：released；每行本次发货量 > 0 且累加后不超过计划量（R-TO-7）。"""
        header = self._load_header(transfer_order_id)
        if header is None:
            raise TransferOrderError('调拨单不存在', field_name='id',
                                     rule='TO_NOT_FOUND')
        status = _status(header.get('status'))
        if status in TERMINAL_STATUSES:
            raise TransferOrderError(
                '调拨单已处于终态 %s，禁止发货' % status,
                field_name='status', rule='TO_TERMINAL_IMMUTABLE')
        if status != STATUS_RELEASED:
            raise TransferOrderError(
                '仅已下达的调拨单可发货', field_name='status',
                rule='TO_STATE_INVALID')

        pending = list(lines or [])
        if not pending:
            raise TransferOrderError(
                '发货至少需要一行', field_name='lines', rule='TO_NO_LINES')
        ratio = resolve_tolerance_ratio(self.ds, TOLERANCE_SHIP_PARAM, header)
        shipped_so_far: Dict[Any, Any] = {}
        for item in pending:
            item = dict(item or {})
            line_id = item.get('line_id') or item.get('id')
            if _blank(line_id):
                raise TransferOrderError(
                    '发货行缺少 line_id', field_name='line_id',
                    rule='TO_LINE_REQUIRED')
            line = self._load_line(line_id)
            if line is None or line.get('transfer_order_id') != header['id']:
                raise TransferOrderError(
                    '调拨行 %s 不属于该调拨单' % line_id,
                    field_name='line_id', rule='TO_LINE_NOT_FOUND')
            if _status(line.get('status')) != LINE_STATUS_OPEN:
                raise TransferOrderError(
                    '调拨行 %s 已关闭 / 已取消，禁止发货' % line_id,
                    field_name='line_id', rule='TO_LINE_NOT_OPEN')
            qty = _dec(item.get('qty'), 'qty')
            if qty is None or qty <= 0:
                raise TransferOrderError(
                    '发货数量必须大于 0', field_name='qty',
                    rule='TO_SHIP_QTY_POSITIVE')
            already = shipped_so_far.get(line_id)
            if already is None:
                already = _dec(line.get('qty_shipped'), 'qty_shipped') or 0
            total = already + qty
            shipped_so_far[line_id] = total
            plan = _dec(line.get('qty'), 'qty') or 0
            limit = plan * (Decimal('1') + ratio)
            if total > limit:
                raise TransferOrderError(
                    '调拨行 %s 累计发货量 %s 超过计划量 %s（含容差 %s%%）'
                    % (line_id, total, plan, ratio * 100),
                    field_name='qty', rule='TO_SHIP_QTY_EXCEEDED')

    def validate_receive(self, transfer_order_id: Any,
                         lines: Optional[List[Dict[str, Any]]] = None) -> None:
        """收货：released 且存在发运余量 > 0 的行（R-TO-8）。

        传入 `lines` 时额外校验净收累计不超过已发货量 × (1 + 超收容差)。
        """
        header = self._load_header(transfer_order_id)
        if header is None:
            raise TransferOrderError('调拨单不存在', field_name='id',
                                     rule='TO_NOT_FOUND')
        status = _status(header.get('status'))
        if status in TERMINAL_STATUSES:
            raise TransferOrderError(
                '调拨单已处于终态 %s，禁止收货' % status,
                field_name='status', rule='TO_TERMINAL_IMMUTABLE')
        if status != STATUS_RELEASED:
            raise TransferOrderError(
                '仅已下达的调拨单可收货', field_name='status',
                rule='TO_STATE_INVALID')
        if not self._lines_with_open_balance(header['id']):
            raise TransferOrderError(
                '调拨单没有发运余量 > 0 的行，禁止收货',
                field_name='status', rule='TO_NOTHING_TO_RECEIVE')
        if lines:
            self._validate_receive_lines(header, lines)

    def _validate_receive_lines(self, header: Dict[str, Any],
                                lines: List[Dict[str, Any]]) -> None:
        ratio = resolve_tolerance_ratio(
            self.ds, TOLERANCE_RECEIVE_PARAM, header)
        received_so_far: Dict[Any, Any] = {}
        for item in lines:
            item = dict(item or {})
            line_id = (item.get('line_id') or item.get('transfer_order_line_id')
                       or item.get('source_line_id'))
            if _blank(line_id):
                raise TransferOrderError(
                    '收货回写行缺少 line_id', field_name='line_id',
                    rule='TO_LINE_REQUIRED')
            line = self._load_line(line_id)
            if line is None or line.get('transfer_order_id') != header['id']:
                raise TransferOrderError(
                    '调拨行 %s 不属于该调拨单' % line_id,
                    field_name='line_id', rule='TO_LINE_NOT_FOUND')
            if item.get('qty_received') is None and item.get('qty') is not None:
                net = _dec(item.get('qty'), 'qty') or 0
            else:
                received = _dec(item.get('qty_received'), 'qty_received') or 0
                rejected = _dec(item.get('qty_rejected'), 'qty_rejected') or 0
                net = received - rejected
            if net == 0:
                continue
            if net < 0:
                raise TransferOrderError(
                    '收货净收量不能为负', field_name='qty_received',
                    rule='TO_QTY_INVALID')
            already = received_so_far.get(line_id)
            if already is None:
                already = _dec(line.get('qty_received'), 'qty_received') or 0
            total = already + net
            received_so_far[line_id] = total
            shipped = _dec(line.get('qty_shipped'), 'qty_shipped') or 0
            limit = shipped * (Decimal('1') + ratio)
            if total > limit:
                raise TransferOrderError(
                    '调拨行 %s 累计收货量 %s 超过已发货量 %s（含容差 %s%%）'
                    % (line_id, total, shipped, ratio * 100),
                    field_name='qty_received', rule='TO_RECEIVE_EXCEEDED')

    def validate_cancel(self, transfer_order_id: Any) -> None:
        """取消：仅 draft / released，且总发货量 = 0（R-TO-6）。"""
        header = self._load_header(transfer_order_id)
        if header is None:
            raise TransferOrderError('调拨单不存在', field_name='id',
                                     rule='TO_NOT_FOUND')
        status = _status(header.get('status'))
        if status in (STATUS_CLOSED, STATUS_CANCELLED):
            raise TransferOrderError(
                '调拨单已处于终态 %s，禁止取消' % status,
                field_name='status', rule='TO_TERMINAL_IMMUTABLE')
        if status not in (STATUS_DRAFT, STATUS_RELEASED):
            raise TransferOrderError(
                '仅草稿 / 已下达的调拨单可取消', field_name='status',
                rule='TO_STATE_INVALID')
        total = sum((_dec(x.get('qty_shipped'), 'qty_shipped') or 0
                     for x in self._load_lines(header['id'])
                     if _status(x.get('status')) != 'cancelled'),
                    Decimal('0'))
        if total > 0:
            raise TransferOrderError(
                '调拨单已发货，禁止取消；请改走反向调拨',
                field_name='status', rule='TO_SHIPPED_CANNOT_CANCEL')

    def validate_close(self, transfer_order_id: Any) -> None:
        """关闭：released；在途量 = 0 且总收货量 > 0（§6.3）。"""
        header = self._load_header(transfer_order_id)
        if header is None:
            raise TransferOrderError('调拨单不存在', field_name='id',
                                     rule='TO_NOT_FOUND')
        status = _status(header.get('status'))
        if status in TERMINAL_STATUSES:
            raise TransferOrderError(
                '调拨单已处于终态 %s，禁止关闭' % status,
                field_name='status', rule='TO_TERMINAL_IMMUTABLE')
        if status != STATUS_RELEASED:
            raise TransferOrderError(
                '仅已下达的调拨单可关闭', field_name='status',
                rule='TO_STATE_INVALID')
        lines = self._load_lines(header['id'])
        in_transit = sum(((_dec(x.get('qty_shipped'), 'qty_shipped') or 0)
                          - (_dec(x.get('qty_received'), 'qty_received') or 0)
                          for x in lines), Decimal('0'))
        if in_transit != 0:
            raise TransferOrderError(
                '调拨单仍有在途量 %s，禁止关闭' % in_transit,
                field_name='status', rule='TO_IN_TRANSIT_NOT_EMPTY')
        received = sum((_dec(x.get('qty_received'), 'qty_received') or 0
                        for x in lines), Decimal('0'))
        if received <= 0:
            raise TransferOrderError(
                '调拨单尚未收货，禁止关闭', field_name='status',
                rule='TO_NOTHING_RECEIVED')

    # ------------------------------------------------------------------
    # 法人解析
    # ------------------------------------------------------------------
    def resolve_legal_entity(self, from_org_id: Any, to_org_id: Any) -> Any:
        """两个组织沿 `parent_id` 上溯到 `legal_entity` 职能组织，必须是同一 id。

        任一解析失败抛 `TO_LEGAL_ENTITY_UNRESOLVED`，跨法人抛
        `TO_CROSS_LEGAL_ENTITY`；均不降级放行（R-TO-2）。
        """
        from_legal = self._resolve_org_legal_entity(from_org_id)
        if from_legal is None:
            raise TransferOrderError(
                '调出组织 %s 无法上溯到法人组织' % from_org_id,
                field_name='from_org_id', rule='TO_LEGAL_ENTITY_UNRESOLVED')
        to_legal = self._resolve_org_legal_entity(to_org_id)
        if to_legal is None:
            raise TransferOrderError(
                '调入组织 %s 无法上溯到法人组织' % to_org_id,
                field_name='to_org_id', rule='TO_LEGAL_ENTITY_UNRESOLVED')
        if str(from_legal) != str(to_legal):
            raise TransferOrderError(
                '调出 / 调入组织属于不同法人（%s vs %s），请改走 ISO'
                % (from_legal, to_legal),
                field_name='to_org_id', rule='TO_CROSS_LEGAL_ENTITY')
        return from_legal

    def _resolve_org_legal_entity(self, org_id: Any) -> Optional[Any]:
        """沿 parent_id 上溯，返回首个具 `legal_entity` 职能的组织 id。"""
        if _blank(org_id):
            return None
        visited = set()
        current = org_id
        depth = 0
        while current is not None and depth < _MAX_ORG_DEPTH:
            marker = str(current)
            if marker in visited:
                break
            visited.add(marker)
            org = self._load_org(current)
            if org is None:
                break
            if self._org_has_function(current, FUNCTION_LEGAL_ENTITY):
                return current
            current = org.get('parent_id')
            depth += 1
        return None

    # ------------------------------------------------------------------
    # 引用校验
    # ------------------------------------------------------------------
    def _validate_header_type(self, type_id: Any) -> Dict[str, Any]:
        if _blank(type_id):
            raise TransferOrderError(
                '调拨单必须选择单据类型', field_name='document_type_id',
                rule='TO_DOCUMENT_TYPE_REQUIRED')
        row = self._load_type(type_id)
        if row is None:
            raise TransferOrderError(
                '单据类型 %s 不存在' % type_id, field_name='document_type_id',
                rule='TO_DOCUMENT_TYPE_NOT_FOUND')
        self._assert_type_scope(row, LEVEL_HEADER, 'document_type_id',
                                'TO_HEADER_TYPE_INVALID')
        return row

    def _validate_line_type(self, type_id: Any) -> Dict[str, Any]:
        if _blank(type_id):
            raise TransferOrderError(
                '调拨行必须选择行类型', field_name='line_type_id',
                rule='TO_LINE_TYPE_REQUIRED')
        row = self._load_type(type_id)
        if row is None:
            raise TransferOrderError(
                '行类型 %s 不存在' % type_id, field_name='line_type_id',
                rule='TO_LINE_TYPE_NOT_FOUND')
        self._assert_type_scope(row, LEVEL_LINE, 'line_type_id',
                                'TO_LINE_TYPE_INVALID')
        return row

    def _assert_type_scope(self, row: Dict[str, Any], level: str,
                           field_name: str, rule: str) -> None:
        if str(row.get('scope_bo') or '') != SCOPE_BO:
            raise TransferOrderError(
                '类型 %s 不属于调拨单域' % row.get('code'),
                field_name=field_name, rule=rule)
        if str(row.get('level') or '') != level:
            raise TransferOrderError(
                '类型 %s 层级不是 %s' % (row.get('code'), level),
                field_name=field_name, rule=rule)
        if not _is_active(row.get('status')):
            raise TransferOrderError(
                '类型 %s 已停用' % row.get('code'),
                field_name=field_name, rule=rule)

    def _require_inventory_org(self, org_id: Any, field_name: str) -> None:
        """组织存在、启用且具备 `inventory` 职能（R-TO-1）。"""
        org = self._load_org(org_id)
        if org is None:
            raise TransferOrderError(
                '组织 %s 不存在' % org_id, field_name=field_name,
                rule='TO_ORG_NOT_FOUND')
        if not _is_active(org.get('status')):
            raise TransferOrderError(
                '组织 %s 已停用' % org_id, field_name=field_name,
                rule='TO_ORG_INACTIVE')
        if not self._org_has_function(org_id, FUNCTION_INVENTORY):
            raise TransferOrderError(
                '组织 %s 不具备 inventory 职能' % org_id,
                field_name=field_name, rule='TO_ORG_NOT_INVENTORY')

    def _require_item(self, item_id: Any) -> Dict[str, Any]:
        """物料存在、启用且 `item_type='goods'`（R-TO-3）。"""
        if _blank(item_id):
            raise TransferOrderError(
                '调拨行必须选择物料', field_name='item_id',
                rule='TO_ITEM_REQUIRED')
        item = self._load_item(item_id)
        if item is None:
            raise TransferOrderError(
                '物料 %s 不存在' % item_id, field_name='item_id',
                rule='TO_ITEM_NOT_FOUND')
        if not _is_active(item.get('status')):
            raise TransferOrderError(
                '物料 %s 已停用' % item_id, field_name='item_id',
                rule='TO_ITEM_INACTIVE')
        if str(item.get('item_type') or '').strip().lower() != ITEM_TYPE_GOODS:
            raise TransferOrderError(
                '物料 %s 不是实物物料（item_type 必须为 goods）' % item_id,
                field_name='item_id', rule='TO_ITEM_TYPE_INVALID')
        return item

    def _require_uom(self, uom_id: Any) -> None:
        if _blank(uom_id):
            raise TransferOrderError(
                '调拨行必须选择计量单位', field_name='uom_id',
                rule='TO_UOM_REQUIRED')
        if not self._load_uom(uom_id):
            raise TransferOrderError(
                '计量单位 %s 不存在' % uom_id, field_name='uom_id',
                rule='TO_UOM_NOT_FOUND')

    def _lines_with_open_balance(self, transfer_order_id: Any) -> List[Dict[str, Any]]:
        result = []
        for line in self._load_lines(transfer_order_id):
            if _status(line.get('status')) != LINE_STATUS_OPEN:
                continue
            shipped = _dec(line.get('qty_shipped'), 'qty_shipped') or 0
            received = _dec(line.get('qty_received'), 'qty_received') or 0
            if shipped - received > 0:
                result.append(line)
        return result

    # ------------------------------------------------------------------
    # 查询（可覆写，便于单测注入）
    # ------------------------------------------------------------------
    def _query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        return self.ds.query(sql, list(params or []))

    def _load_header(self, transfer_order_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(transfer_order_id):
            return None
        rows = self._query(
            'SELECT id, transfer_order_no, document_type_id, transfer_date, '
            'status, approval_status, fulfillment_status, from_org_id, '
            'to_org_id, legal_entity_id, from_location_id, to_location_id, '
            'reversal_of_transfer_id '
            'FROM %s WHERE id = ?' % HEADER_TABLE,
            [transfer_order_id])
        return rows[0] if rows else None

    def _load_lines(self, transfer_order_id: Any) -> List[Dict[str, Any]]:
        return self._query(
            'SELECT id, transfer_order_id, line_no, line_type_id, item_id, '
            'uom_id, qty, qty_shipped, qty_received, status '
            'FROM %s WHERE transfer_order_id = ? ORDER BY line_no, id'
            % LINE_TABLE, [transfer_order_id])

    def _next_line_no(self, transfer_order_id: Any) -> int:
        """行号按 10 / 20 / 30 递增；并发撞号由 `UNIQUE(transfer_order_id, line_no)` 兜底。"""
        rows = self._query(
            'SELECT MAX(CAST(line_no AS INTEGER)) AS mx FROM %s '
            "WHERE transfer_order_id = ? AND line_no NOT GLOB '*[^0-9]*'"
            % LINE_TABLE, [transfer_order_id])
        current = rows[0].get('mx') if rows else None
        return int(current or 0) + LINE_NO_STEP

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(line_id):
            return None
        rows = self._query(
            'SELECT id, transfer_order_id, line_no, line_type_id, item_id, '
            'uom_id, qty, qty_shipped, qty_received, status '
            'FROM %s WHERE id = ?' % LINE_TABLE, [line_id])
        return rows[0] if rows else None

    def _load_type(self, type_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(type_id):
            return None
        rows = self._query(
            'SELECT id, code, scope_bo, level, status FROM %s WHERE id = ?'
            % TYPE_TABLE, [type_id])
        return rows[0] if rows else None

    def _load_org(self, org_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(org_id):
            return None
        rows = self._query(
            'SELECT id, parent_id, status FROM %s WHERE id = ?' % ORG_TABLE,
            [org_id])
        return rows[0] if rows else None

    def _load_item(self, item_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(item_id):
            return None
        rows = self._query(
            'SELECT id, status, item_type FROM %s WHERE id = ?' % ITEM_TABLE,
            [item_id])
        return rows[0] if rows else None

    def _load_uom(self, uom_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(uom_id):
            return None
        rows = self._query(
            'SELECT id, status FROM uoms WHERE id = ?', [uom_id])
        return rows[0] if rows else None

    def _org_has_function(self, org_id: Any, function_type: str) -> bool:
        """组织是否具备某职能；职能表缺失时 fail-open（与 PO 守卫同口径）。"""
        try:
            rows = self._query(
                'SELECT 1 FROM %s WHERE org_id = ? AND function_type = ? LIMIT 1'
                % ORG_FUNCTION_TABLE, [org_id, function_type])
        except Exception as error:  # noqa: BLE001 - 旧环境 / 替身无职能表
            logger.warning('[transfer_order_guard] 读取组织职能 %s 失败: %s',
                           org_id, error)
            return True
        return bool(rows)
