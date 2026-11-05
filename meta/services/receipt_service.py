# -*- coding: utf-8 -*-
"""收货单服务 —— 草稿创建、过账、取消、整单红冲。

依据: docs/specs/spec-receipt-object-model-2026-11-01.md
      §3 / §4 对象模型 · §5.3 不变量 R-RC-0~18 · §6 过账 6 步 · §6.1 分配拆分
      · §7 整单红冲

口径:
  · 唯一写入口：计划行 `received_qty`（净收）/ `rejected_qty`（拒收）只由本服务
    过账与红冲回写；PO `fulfillment_status` **只调用**
    `PurchaseOrderFulfillmentService.recompute_order` 派生（INV-1），本服务禁止直写。
  · `received_qty` = 净收（≈ Oracle ACCEPTED），`rejected_qty` 独立累加，两者不混算
    （R-RC-18）。
  · 超收用「条件 UPDATE 原子累加」判定，`rowcount = 0` 即拒绝（R-RC-5 禁止先查后写）；
    容差来自控制参数 `receipt_over_tolerance_percent`（百分数，0 = 不允许超收）。
  · 需求分配：标准单按「PO 分配剩余量占比」拆分（§6.1）；红字单按原单分配逐行取负
    （§7）。PO 分配与收货分配分段计数，不相加（§6.2）。
  · 整单红冲 = 新建红字单（`document_category='return'`）并自动过账，红字行数量
    保持正数、净量贡献为负；原单全部冲销后置 `reversed`（§7）。
  · 取号必须在事务之外（R-RC-8 / 编号引擎硬约束）。事务边界由调用方控制：
    BO Action 用 `framework.transaction()` 包住 `post` / `cancel`，本服务不自行提交。
  · 来源分两支：`purchase_order`（计划行 / 分配 / PO 履约）与 `transfer_order`
    （调拨行发运余量 / TO 收货回写）；TO 来源不写 `purchase_order_schedules`、
    不调 PO 履约服务。

覆写 `_load_*` / `_insert_*` 即可注入测试数据。
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HEADER_TABLE = 'receipts'
LINE_TABLE = 'receipt_lines'
SCHEDULE_TABLE = 'purchase_order_schedules'
ORDER_TABLE = 'purchase_orders'
ORDER_LINE_TABLE = 'purchase_order_lines'
ALLOCATION_TABLE = 'demand_allocations'
TYPE_TABLE = 'type_definitions'
LOCATION_TABLE = 'locations'
PARTY_RELATION_TABLE = 'party_relations'
PARAM_TABLE = 'control_parameter_defs'
PARAM_VALUE_TABLE = 'control_parameter_values'
ORG_TABLE = 'orgs'
ORG_FUNCTION_TABLE = 'org_functions'
FUNCTION_INVENTORY = 'inventory'

SOURCE_PURCHASE_ORDER = 'purchase_order'
SOURCE_TRANSFER_ORDER = 'transfer_order'
SOURCE_WORK_ORDER = 'work_order'
SOURCE_SUPPORTED = (SOURCE_PURCHASE_ORDER, SOURCE_TRANSFER_ORDER)

DOC_CATEGORY_STANDARD = 'standard'
DOC_CATEGORY_RETURN = 'return'
DOC_CATEGORIES = (DOC_CATEGORY_STANDARD, DOC_CATEGORY_RETURN)

STATUS_DRAFT = 'draft'
STATUS_POSTED = 'posted'
STATUS_REVERSED = 'reversed'
STATUS_CANCELLED = 'cancelled'

SCHEDULE_KIND_ALLOWED = ('delivery', 'service')
SCHEDULE_PENDING_STATUSES = ('planned', 'confirmed')
SCHEDULE_STATUS_COMPLETED = 'completed'
COMPLETION_SOURCE_RECEIPT = 'receipt'
COMPLETION_SOURCE_SHORT_CLOSE = 'short_close'

REJECTION_DISPOSITIONS = ('return_to_supplier', 'concession', 'scrap', 'rework')

TOLERANCE_PARAM = 'receipt_over_tolerance_percent'

#: 已过账后不可删除的抬头状态（R-RC-13）
UNDELETABLE_STATUSES = (STATUS_POSTED, STATUS_REVERSED)

_Q4 = Decimal('0.0001')


class ReceiptError(ValueError):
    """收货守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.message = message
        self.field_name = field_name
        self.rule = rule


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _dec(value: Any, field_name: str = 'qty') -> Decimal:
    """数量统一走 Decimal，避免浮点比较把 0.1+0.2 判成超收。"""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ReceiptError('数量必须是数字', field_name=field_name,
                           rule='RC_QTY_INVALID')


def _q4(value: Decimal) -> Decimal:
    return value.quantize(_Q4)


class ReceiptService:
    """收货单创建、过账、取消与整单红冲。"""

    def __init__(self, data_source=None, platform_data_source=None):
        self._ds = data_source
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
        """平台库（doc_flow_rule）；未配置时回落应用库（单库部署）。"""
        if self._platform_ds is None:
            try:
                from meta.core.datasource import get_platform_data_source
                self._platform_ds = get_platform_data_source() or self.ds
            except Exception:  # noqa: BLE001 - 未配置平台库
                self._platform_ds = self.ds
        return self._platform_ds

    # ------------------------------------------------------------------ 取号
    def allocate_receipt_no(self, document_type_id: Any,
                            receipt_date: Any) -> Optional[str]:
        """按单据类型指向的序列取号（R-RC-8：必须在开事务前调用）。"""
        if _blank(document_type_id) or _blank(receipt_date):
            return None
        rows = self.ds.query(
            'SELECT number_sequence_id FROM %s WHERE id = ?' % TYPE_TABLE,
            [document_type_id])
        sequence_id = rows[0].get('number_sequence_id') if rows else None
        if _blank(sequence_id):
            return None
        configs = self.ds.query(
            'SELECT code, pattern, scope_fields, date_field, start_value, '
            'on_exhaust FROM number_sequences WHERE id = ?', [sequence_id])
        if not configs:
            return None
        from meta.core.number_sequence_engine import (
            NumberSequenceEngine, NumberSequenceError)
        try:
            return NumberSequenceEngine(self.ds).allocate(
                dict(configs[0]), {}, {'receipt_date': receipt_date})
        except NumberSequenceError as e:
            raise ReceiptError(str(e), field_name='receipt_no',
                               rule='RC_NUMBER_REQUIRED')

    # ------------------------------------------------------------------ 创建
    def prepare_header(self, header: Dict[str, Any]):
        """创建前归一化抬头：来源 / 日期 / 单据类型 / 默认值 / 取号。

        返回 `(header, order, doc_type)`。R-RC-8：取号在本方法内、
        调用方开事务之前完成。BO crud_create 与 action 建单共用本方法，
        避免「默认值 + 取号」在两侧各写一遍。
        """
        header = dict(header or {})
        source_type = header.get('source_doc_type') or SOURCE_PURCHASE_ORDER
        if source_type == SOURCE_TRANSFER_ORDER:
            return self.prepare_transfer_header(header)
        if source_type == SOURCE_WORK_ORDER:
            return self.prepare_work_order_header(header)
        if source_type not in SOURCE_SUPPORTED:
            raise ReceiptError(
                '来源单据类型 %s 暂不支持收货' % source_type,
                field_name='source_doc_type', rule='RC_SOURCE_UNSUPPORTED')

        receipt_date = header.get('receipt_date')
        if _blank(receipt_date):
            raise ReceiptError('收货日期必填', field_name='receipt_date',
                               rule='RC_DATE_REQUIRED')

        order = self._load_order(header.get('source_doc_id'))
        if order is None:
            raise ReceiptError('来源采购订单不存在', field_name='source_doc_id',
                               rule='RC_ORDER_NOT_FOUND')

        doc_type = self._require_document_type(header.get('document_type_id'))
        if doc_type['document_category'] == DOC_CATEGORY_RETURN \
                and _blank(header.get('reversal_of_receipt_id')):
            raise ReceiptError('红字收货单必须引用原单',
                               field_name='reversal_of_receipt_id',
                               rule='RC_DOC_TYPE_INVALID')

        header = self._apply_header_defaults(header, order)
        receipt_no = header.get('receipt_no') or self.allocate_receipt_no(
            doc_type['id'], receipt_date)
        if _blank(receipt_no):
            raise ReceiptError('单据类型未绑定编号序列，无法生成收货单号',
                               field_name='receipt_no', rule='RC_NUMBER_REQUIRED')
        header['receipt_no'] = receipt_no
        return header, order, doc_type

    def prepare_transfer_header(self, header: Dict[str, Any]):
        """调拨单来源抬头归一化（spec §7.2 字段映射）。

        返回 `(header, transfer_order, doc_type)`；来源机构 / 收货库位等只读字段
        由调拨单推导，采购专属字段（`purchase_org_id` / `supplier_party_id`）置空。
        """
        header = dict(header or {})
        receipt_date = header.get('receipt_date')
        if _blank(receipt_date):
            raise ReceiptError('收货日期必填', field_name='receipt_date',
                               rule='RC_DATE_REQUIRED')

        transfer_order = self._load_transfer_order(header.get('source_doc_id'))
        if transfer_order is None:
            raise ReceiptError('来源调拨单不存在', field_name='source_doc_id',
                               rule='RC_TRANSFER_NOT_FOUND')

        doc_type = self._require_document_type(header.get('document_type_id'))
        if doc_type['document_category'] == DOC_CATEGORY_RETURN \
                and _blank(header.get('reversal_of_receipt_id')):
            raise ReceiptError('红字收货单必须引用原单',
                               field_name='reversal_of_receipt_id',
                               rule='RC_DOC_TYPE_INVALID')

        header['source_doc_type'] = SOURCE_TRANSFER_ORDER
        header['source_doc_id'] = transfer_order['id']
        header['source_doc_no'] = transfer_order.get('transfer_order_no')
        header['org_id'] = transfer_order.get('legal_entity_id')
        header['purchase_org_id'] = None
        header['supplier_party_id'] = None
        header['deliver_to_location_id'] = transfer_order.get('to_location_id')
        # TBD-6：收货库存组织 = 调拨单收货组织（与法人 org_id 正交）
        header['inventory_org_id'] = transfer_order.get('to_org_id')
        self._validate_inventory_org(header)
        # TBD-7：收货库位所属组织（org_id 非空时）须等于收货库存组织
        self._validate_location_org(header)
        receipt_no = header.get('receipt_no') or self.allocate_receipt_no(
            doc_type['id'], receipt_date)
        if _blank(receipt_no):
            raise ReceiptError('单据类型未绑定编号序列，无法生成收货单号',
                               field_name='receipt_no', rule='RC_NUMBER_REQUIRED')
        header['receipt_no'] = receipt_no
        return header, transfer_order, doc_type

    def prepare_work_order_header(self, header: Dict[str, Any]):
        """生产工单来源抬头归一化（P6c D1/D2）。

        工单无库存组织 / 收货库位字段，必须由收货单表头显式提供；
        采购专属字段置空。返回 `(header, work_order, doc_type)`。
        """
        header = dict(header or {})
        receipt_date = header.get('receipt_date')
        if _blank(receipt_date):
            raise ReceiptError('收货日期必填', field_name='receipt_date',
                               rule='RC_DATE_REQUIRED')

        work_order = self._load_work_order(header.get('source_doc_id'))
        if work_order is None:
            raise ReceiptError('来源生产工单不存在', field_name='source_doc_id',
                               rule='RC_WORK_ORDER_INVALID')
        if str(work_order.get('order_type') or '').strip().lower() != 'production':
            raise ReceiptError('来源工单不是生产工单', field_name='source_doc_id',
                               rule='RC_WORK_ORDER_INVALID')
        status = str(work_order.get('status') or '').strip().lower()
        if status not in ('new', 'in progress'):
            raise ReceiptError(
                '工单状态 %s 不允许完工收货' % work_order.get('status'),
                field_name='source_doc_id', rule='RC_WORK_ORDER_INVALID')

        doc_type = self._require_document_type(header.get('document_type_id'))
        if doc_type['document_category'] == DOC_CATEGORY_RETURN \
                and _blank(header.get('reversal_of_receipt_id')):
            raise ReceiptError('红字收货单必须引用原单',
                               field_name='reversal_of_receipt_id',
                               rule='RC_DOC_TYPE_INVALID')

        header['source_doc_type'] = SOURCE_WORK_ORDER
        header['source_doc_id'] = work_order['id']
        header['source_doc_no'] = work_order.get('work_order_no')
        header['purchase_org_id'] = None
        header['supplier_party_id'] = None
        if _blank(header.get('inventory_org_id')):
            raise ReceiptError('完工收货单必须指定库存组织',
                               field_name='inventory_org_id',
                               rule='RC_WORK_ORDER_ORG_REQUIRED')
        if _blank(header.get('deliver_to_location_id')):
            raise ReceiptError('完工收货单必须指定收货库位',
                               field_name='deliver_to_location_id',
                               rule='RC_WORK_ORDER_LOCATION_REQUIRED')
        self._validate_inventory_org(header)
        self._validate_location_org(header)
        receipt_no = header.get('receipt_no') or self.allocate_receipt_no(
            doc_type['id'], receipt_date)
        if _blank(receipt_no):
            raise ReceiptError('单据类型未绑定编号序列，无法生成收货单号',
                               field_name='receipt_no', rule='RC_NUMBER_REQUIRED')
        header['receipt_no'] = receipt_no
        return header, work_order, doc_type

    # ------------------------------------------------------------------ 创建
    def create_receipt(self, header: Dict[str, Any],
                       lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """创建收货单草稿（头 + 行）；返回 `{'id','receipt_no','status'}`。

        结构校验（R-RC-0 ~ R-RC-4）在此完成；超收与完工判定留到过账
        （条件 UPDATE 原子累加，禁止先查后写）。
        """
        header, order, doc_type = self.prepare_header(header)
        is_transfer = header['source_doc_type'] == SOURCE_TRANSFER_ORDER
        is_work_order = header['source_doc_type'] == SOURCE_WORK_ORDER
        if is_work_order:
            validator = self._validate_work_order_line
        elif is_transfer:
            validator = self._validate_transfer_line
        else:
            validator = self._validate_line
        normalized = [validator(line, order, doc_type)
                      for line in (lines or [])]

        now = _now()
        row = {
            'receipt_no': header['receipt_no'],
            'document_type_id': doc_type['id'],
            'receipt_date': header['receipt_date'],
            'actual_arrival_date': header.get('actual_arrival_date'),
            'source_doc_type': header['source_doc_type'],
            'source_doc_id': order['id'],
            'source_doc_no': header.get('source_doc_no') or order.get('order_no')
                             or order.get('transfer_order_no'),
            'supplier_party_id': header.get('supplier_party_id'),
            'supplier_delivery_no': header.get('supplier_delivery_no'),
            'org_id': header.get('org_id'),
            'purchase_org_id': header.get('purchase_org_id'),
            'inventory_org_id': header.get('inventory_org_id'),
            'deliver_to_location_id': header.get('deliver_to_location_id'),
            'project_id': header.get('project_id'),
            'received_by': header.get('received_by'),
            'status': STATUS_DRAFT,
            'reversal_of_receipt_id': header.get('reversal_of_receipt_id'),
            'remark': header.get('remark'),
            'created_at': now,
            'updated_at': now,
        }
        receipt_id = self._insert_header(row)
        for seq, item in enumerate(normalized, start=1):
            if is_work_order:
                payload = self._normalized_work_order_payload(item)
            elif is_transfer:
                payload = self._normalized_transfer_payload(item)
            else:
                payload = self._normalized_payload(item)
            payload['line_no'] = str(seq)
            self._insert_line(receipt_id, payload, now)

        logger.info('[receipt] created id=%s no=%s lines=%s',
                    receipt_id, header['receipt_no'], len(normalized))
        return {'id': receipt_id, 'receipt_no': header['receipt_no'],
                'status': STATUS_DRAFT, 'source_doc_id': order['id'],
                'line_count': len(normalized)}

    def create_from_transfer_order(
            self, transfer_order_id: Any,
            line_ids: Optional[List[Any]] = None) -> Dict[str, Any]:
        """由调拨单发运余量生成草稿收货单（spec §7.2）。

        只取 `qty_shipped - qty_received > 0` 的行，`qty_received` 取余量；
        来源字段按固定映射推导，不直接过账，不写计划行、不调 PO 履约服务。
        取号在事务之外（R-RC-8），随后在同一事务内插入头 / 行。
        """
        transfer_order = self._load_transfer_order(transfer_order_id)
        if transfer_order is None:
            raise ReceiptError('来源调拨单不存在', field_name='source_doc_id',
                               rule='RC_TRANSFER_NOT_FOUND')

        source_lines = self._transfer_open_lines(transfer_order_id, line_ids)
        if not source_lines:
            raise ReceiptError(
                '调拨单没有发运余量 > 0 的行，无法生成收货单',
                field_name='lines', rule='RC_TRANSFER_NO_BALANCE')

        header = {
            'source_doc_type': SOURCE_TRANSFER_ORDER,
            'source_doc_id': transfer_order['id'],
            'receipt_date': _now()[:10],
            'document_type_id': self.standard_header_type()['id'],
            'remark': '调拨单 %s 收货' % (
                transfer_order.get('transfer_order_no') or ''),
        }
        lines = [{'source_line_id': row['id'],
                  'qty_received': float(balance)}
                 for row, balance in source_lines]
        # R-RC-8：先取号（prepare_transfer_header），再开事务插入
        prepared, _order, _doc_type = self.prepare_transfer_header(header)
        with self.ds.transaction():
            return self.create_receipt(prepared, lines)

    def create_from_work_order(
            self, work_order_id: Any, location_id: Any,
            lines: List[Dict[str, Any]],
            inventory_org_id: Any = None, receipt_date: Any = None,
            document_type_id: Any = None,
            remark: Any = None, org_id: Any = None) -> Dict[str, Any]:
        """由生产工单生成完工收货单草稿（P6c D1/D2）。

        工单无成品数量字段，行内容（成品物料 / 数量 / 序列号）由调用方显式给；
        组织与库位由表头显式提供。取号在事务之外（R-RC-8）。
        """
        header = {
            'source_doc_type': SOURCE_WORK_ORDER,
            'source_doc_id': work_order_id,
            'receipt_date': receipt_date or _now()[:10],
            'document_type_id': document_type_id
            or self.standard_header_type()['id'],
            'org_id': org_id,
            'inventory_org_id': inventory_org_id,
            'deliver_to_location_id': location_id,
            'remark': remark or '生产工单 %s 完工收货' % work_order_id,
        }
        prepared, _order, _doc_type = self.prepare_work_order_header(header)
        with self.ds.transaction():
            return self.create_receipt(prepared, lines)

    # ------------------------------------------------------------------ 过账
    def post(self, receipt_id: Any,
             actual_arrival_date: Optional[str] = None) -> Dict[str, Any]:
        """draft → posted：§6 六步（校验 → 分配 → 计划行 → 履约 → 状态 → 审计）。"""
        header = self._require_header(receipt_id)
        if header['status'] == STATUS_POSTED:
            return {'id': header['id'], 'status': STATUS_POSTED,
                    'idempotent': True, 'order_ids': []}
        if header['status'] != STATUS_DRAFT:
            raise ReceiptError('仅草稿收货单可过账', field_name='status',
                               rule='RC_STATE_INVALID')

        if header.get('source_doc_type') == SOURCE_TRANSFER_ORDER:
            return self._post_transfer_order(header, actual_arrival_date)
        if header.get('source_doc_type') == SOURCE_WORK_ORDER:
            return self._post_work_order(header, actual_arrival_date)

        doc_type = self._require_document_type(header.get('document_type_id'))
        is_return = doc_type['document_category'] == DOC_CATEGORY_RETURN
        lines = self._load_lines(receipt_id)
        if not lines:
            raise ReceiptError('收货单没有任何行，禁止过账',
                               field_name='lines', rule='RC_EMPTY')

        now = actual_arrival_date or _now()
        tol = self._tolerance_ratio()
        order = self._load_order(header.get('source_doc_id'))
        if order is None:
            raise ReceiptError('来源采购订单不存在', field_name='source_doc_id',
                               rule='RC_ORDER_NOT_FOUND')
        self._require_vendor(header)

        # 1. 行校验（R-RC-1 ~ R-RC-4 / R-RC-15 / R-RC-17）
        checked = [self._validate_line(line, order, doc_type, for_post=True)
                   for line in lines]

        # P6a §6.1：序列号录号前置校验（最后一步做写副作用前必须通过）
        if not is_return:
            self._validate_serial_tracking(header, checked)

        order_ids = set()
        for item in checked:
            line = item['line']
            net = item['net']
            schedule = item['schedule']
            order_ids.add(schedule['order_id'])

            # 2. 需求分配（红字单取负，标准单按剩余占比拆）
            if net > 0:
                if is_return:
                    self._write_reversal_allocations(
                        line, header['id'], schedule, tol, now)
                else:
                    self._write_allocations(line, header['id'], schedule, net,
                                            tol, now)
            # 3. 计划行条件 UPDATE 原子累加（R-RC-5 唯一判定点）
            self._apply_schedule_receipt(schedule, net, item['rejected'], tol, now)

        # 4. 履约状态派生（唯一写入口）
        from meta.services.purchase_order_fulfillment_service import (
            PurchaseOrderFulfillmentService)
        fulfillment = PurchaseOrderFulfillmentService(self.ds)
        for order_id in sorted(order_ids):
            fulfillment.recompute_order(order_id)

        # 5. 状态置位
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_POSTED, now, header['id'], STATUS_DRAFT])
        self.ds.execute(
            'UPDATE %s SET status = ?, actual_arrival_date = COALESCE(?, '
            'actual_arrival_date, receipt_date), updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_POSTED, actual_arrival_date, now, header['id']])

        # 6. 库存入账（同事务；开关关闭时 post() 内部自动跳过）
        #    红字单由 reverse 流程生成并直接置为已过账，不经过此处；若手工
        #    过账红字单则拒绝，避免与 REVERSAL 反冲重复记账。
        if is_return:
            from meta.services.inventory_guard_service import (
                InventoryError, InventoryGuardService, INV_STATUS_INVALID)
            if InventoryGuardService(self.ds).posting_enabled():
                e = InventoryError(
                    INV_STATUS_INVALID, '红字收货单不支持库存入库，请走红冲')
                raise ReceiptError(e.message, field_name='inventory', rule=e.code)
        else:
            txns = self._post_receipt_inventory(header, checked, 'RCV_PO')
            # DOC_FLOW 阶段 2：收货行 → 入库事务（attach 既有事务）
            self._write_receipt_inbound_edges(checked, txns)
            # P6a §5 register_receipt：建号 / 复用、写 receive 事件与 link、
            # 主档置 in_stores。只处理标准收货；红字 / TO 不走本支路。
            self._register_receipt_serials(header, checked)
            # P6a-2 §11.5：按行 hu_no 建箱 / 装箱（表缺失时自动 no-op）
            self._register_receipt_hus(header)

        logger.info('[receipt] posted id=%s return=%s lines=%s',
                    header['id'], is_return, len(checked))
        return {'id': header['id'], 'status': STATUS_POSTED,
                'idempotent': False, 'order_ids': sorted(order_ids)}

    def _post_transfer_order(self, header: Dict[str, Any],
                             actual_arrival_date: Optional[str] = None,
                             ) -> Dict[str, Any]:
        """TO 来源过账：净收回写 TO 行（R-TO-9），不写计划行 / 不调 PO 履约。"""
        doc_type = self._require_document_type(header.get('document_type_id'))
        lines = self._load_lines(header['id'])
        if not lines:
            raise ReceiptError('收货单没有任何行，禁止过账',
                               field_name='lines', rule='RC_EMPTY')
        transfer_order = self._load_transfer_order(header.get('source_doc_id'))
        if transfer_order is None:
            raise ReceiptError('来源调拨单不存在', field_name='source_doc_id',
                               rule='RC_TRANSFER_NOT_FOUND')

        checked = [self._validate_transfer_line(line, transfer_order, doc_type,
                                                for_post=True)
                   for line in lines]
        updates = [{'line_id': item['line'].get('source_line_id'),
                    'qty_received': float(item['net']),
                    'qty_rejected': float(item['rejected'])}
                   for item in checked if item['net'] > 0]
        serial_ready = self._serial_ready()
        if serial_ready:
            self._precheck_transfer_receipt_serials(
                transfer_order['id'], header['id'])
        if updates:
            from meta.services.transfer_order_service import (
                TransferOrderError, TransferOrderService)
            try:
                TransferOrderService(self.ds).apply_receipt(
                    transfer_order['id'], updates)
            except TransferOrderError as e:
                raise ReceiptError(e.message, field_name=e.field_name,
                                   rule=e.rule or 'RC_TRANSFER_RECEIVE_FAILED')

        now = actual_arrival_date or _now()
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_POSTED, now, header['id'], STATUS_DRAFT])
        self.ds.execute(
            'UPDATE %s SET status = ?, actual_arrival_date = COALESCE(?, '
            'actual_arrival_date, receipt_date), updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_POSTED, actual_arrival_date, now, header['id']])

        # 库存入账：TO 来源收货写 RCV_TO（org=inventory_org_id）
        txns = self._post_receipt_inventory(header, checked, 'RCV_TO')
        self._write_receipt_inbound_edges(checked, txns)
        if serial_ready:
            self._register_transfer_receipt_serials(
                transfer_order['id'], header['id'])
        # P6a-2 §11.5：目标组织侧按行 hu_no 建箱 / 装箱（跨组织=复制结构）
        self._register_receipt_hus(header)

        logger.info('[receipt] posted to id=%s transfer_order=%s lines=%s',
                    header['id'], transfer_order['id'], len(checked))
        return {'id': header['id'], 'status': STATUS_POSTED,
                'idempotent': False, 'order_ids': [],
                'transfer_order_id': transfer_order['id']}

    def _post_work_order(self, header: Dict[str, Any],
                         actual_arrival_date: Optional[str] = None,
                         ) -> Dict[str, Any]:
        """生产工单来源过账：成品入库 + 组件号爆用 + 单父谱系（P6c）。

        不自动关闭工单（D5）；组件只写一条 issue（D4）。
        """
        doc_type = self._require_document_type(header.get('document_type_id'))
        lines = self._load_lines(header['id'])
        if not lines:
            raise ReceiptError('收货单没有任何行，禁止过账',
                               field_name='lines', rule='RC_EMPTY')
        work_order = self._load_work_order(header.get('source_doc_id'))
        if work_order is None:
            raise ReceiptError('来源生产工单不存在', field_name='source_doc_id',
                               rule='RC_WORK_ORDER_INVALID')

        checked = [self._validate_work_order_line(line, work_order, doc_type,
                                                  for_post=True)
                   for line in lines]
        serial_ready = self._serial_ready()
        if serial_ready:
            self._precheck_work_order_serials(work_order['id'], header['id'])

        now = actual_arrival_date or _now()
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_POSTED, now, header['id'], STATUS_DRAFT])
        self.ds.execute(
            'UPDATE %s SET status = ?, actual_arrival_date = COALESCE(?, '
            'actual_arrival_date, receipt_date), updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_POSTED, actual_arrival_date, now, header['id']])

        txns = self._post_receipt_inventory(header, checked, 'RCV_WO')
        self._write_receipt_inbound_edges(checked, txns)
        if serial_ready:
            self._register_completion_serials(
                work_order['id'], header['id'],
                event_key='receipt:%s:post' % header['id'])
        # P6a-2 §11.5：成品按行 hu_no 装箱（仅成品行，组件在工单侧）
        self._register_receipt_hus(header)
        # INV-2：完工收货是 P6c 唯一的组件消耗事件，按累计完工量核销组件承诺
        self._fulfill_component_reservations(work_order['id'])

        logger.info('[receipt] posted work order id=%s work_order=%s lines=%s',
                    header['id'], work_order['id'], len(checked))
        return {'id': header['id'], 'status': STATUS_POSTED,
                'idempotent': False, 'order_ids': [],
                'work_order_id': work_order['id']}

    def _fulfill_component_reservations(self, work_order_id: Any) -> None:
        """按累计完工量核销工单组件软预留；预留层失败不阻断过账。"""
        try:
            from meta.services.inventory_reservation_service import (
                InventoryReservationService,
            )
            completed = self._work_order_completed_qty(work_order_id)
            InventoryReservationService(
                self.ds).fulfill_work_order_components(
                    work_order_id, completed_qty=completed)
        except Exception as error:  # noqa: BLE001 - 承诺核销失败不阻断完工
            logger.warning('[receipt] 工单 %s 组件承诺核销失败（跳过）: %s',
                           work_order_id, error)

    def _work_order_completed_qty(self, work_order_id: Any) -> float:
        """累计净完工量：只计已过账且未被红冲的完工收货单。"""
        try:
            rows = self.ds.query(
                'SELECT COALESCE(SUM(COALESCE(l.qty_received, 0) '
                '- COALESCE(l.qty_rejected, 0)), 0) AS qty '
                'FROM %s l JOIN %s r ON r.id = l.receipt_id '
                'WHERE r.source_doc_type = ? AND r.source_doc_id = ? '
                'AND r.status = ? AND r.reversal_of_receipt_id IS NULL'
                % (LINE_TABLE, HEADER_TABLE),
                [SOURCE_WORK_ORDER, work_order_id, STATUS_POSTED])
        except Exception as error:  # noqa: BLE001 - 旧库缺列按 0 处理
            logger.warning('[receipt] 汇总工单 %s 完工量失败: %s',
                           work_order_id, error)
            return 0.0
        return float(rows[0].get('qty') or 0) if rows else 0.0

    # ------------------------------------------------------------------ 取消
    def cancel(self, receipt_id: Any) -> Dict[str, Any]:
        """draft → cancelled，行一并取消（R-RC-13 草稿才可删 / 可废）。"""
        header = self._require_header(receipt_id)
        if header['status'] == STATUS_CANCELLED:
            return {'id': header['id'], 'status': STATUS_CANCELLED,
                    'idempotent': True}
        if header['status'] != STATUS_DRAFT:
            raise ReceiptError('仅草稿收货单可取消', field_name='status',
                               rule='RC_STATE_INVALID')
        now = _now()
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?' % HEADER_TABLE,
            [STATUS_CANCELLED, now, header['id']])
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ?' % LINE_TABLE,
            [STATUS_CANCELLED, now, header['id']])
        return {'id': header['id'], 'status': STATUS_CANCELLED}

    # ------------------------------------------------------------------ 红冲
    def reverse(self, receipt_id: Any, receipt_date: Optional[str] = None,
                receipt_no: Optional[str] = None,
                remark: Optional[str] = None) -> Dict[str, Any]:
        """整单红冲：新建红字单并自动过账（§7）。

        调用前须确保不在事务中（取号 R-RC-8）；红字单过账与原单置位在同一事务内
        由调用方提交。净量为 0 的行（全部拒收）不产生红字行：拒收是独立事实，
        不属于净收冲销范围。
        """
        header = self._require_header(receipt_id)
        if header['status'] != STATUS_POSTED:
            raise ReceiptError('仅已过账收货单可冲销', field_name='status',
                               rule='RC_STATE_INVALID')
        if header.get('source_doc_type') == SOURCE_TRANSFER_ORDER:
            return self._reverse_transfer_order(
                header, receipt_date, receipt_no, remark)
        if header.get('source_doc_type') == SOURCE_WORK_ORDER:
            return self._reverse_work_order(
                header, receipt_date, receipt_no, remark)
        original_type = self._require_document_type(header.get('document_type_id'))
        if original_type['document_category'] == DOC_CATEGORY_RETURN:
            raise ReceiptError('红字收货单不可再冲销', field_name='status',
                               rule='RC_REVERSAL_INVALID')
        if self._reversal_exists(header['id']):
            raise ReceiptError('该收货单已存在红字单，禁止重复冲销',
                               field_name='status', rule='RC_REVERSAL_EXISTS')

        return_type = self._return_header_type()
        date = receipt_date or header.get('receipt_date') or _now()
        red_no = receipt_no or self.allocate_receipt_no(return_type['id'], date)
        if _blank(red_no):
            raise ReceiptError('缺少红字收货单类型或编号序列',
                               field_name='receipt_no', rule='RC_NUMBER_REQUIRED')

        original_lines = self._load_lines(header['id'], status=STATUS_POSTED)
        source_items = [self._load_schedule_context(line)
                       for line in original_lines]
        source_items = [item for item in source_items
                        if item['schedule'] is not None and item['net'] > 0]
        if not source_items:
            raise ReceiptError('原单没有可冲销的净收行', field_name='lines',
                               rule='RC_REVERSAL_INVALID')

        now = _now()
        tol = self._tolerance_ratio()
        red_row = {
            'receipt_no': red_no,
            'document_type_id': return_type['id'],
            'receipt_date': date,
            'actual_arrival_date': header.get('actual_arrival_date'),
            'source_doc_type': header.get('source_doc_type'),
            'source_doc_id': header.get('source_doc_id'),
            'source_doc_no': header.get('source_doc_no'),
            'supplier_party_id': header.get('supplier_party_id'),
            'supplier_delivery_no': header.get('supplier_delivery_no'),
            'org_id': header.get('org_id'),
            'purchase_org_id': header.get('purchase_org_id'),
            'inventory_org_id': header.get('inventory_org_id'),
            'deliver_to_location_id': header.get('deliver_to_location_id'),
            'project_id': header.get('project_id'),
            'received_by': header.get('received_by'),
            'status': STATUS_DRAFT,
            'reversal_of_receipt_id': header['id'],
            'remark': remark or ('红冲 %s' % header.get('receipt_no')),
            'created_at': now,
            'updated_at': now,
        }
        red_id = self._insert_header(red_row)

        order_ids = set()
        for seq, item in enumerate(source_items, start=1):
            line = item['line']
            schedule = item['schedule']
            net = item['net']
            red_line = {
                'line_no': line['line_no'],
                'schedule_id': line['schedule_id'],
                'source_line_id': line.get('source_line_id'),
                'order_id': line.get('order_id'),
                'order_line_id': line.get('order_line_id'),
                'item_id': line['item_id'],
                'uom_id': line['uom_id'],
                'qty_received': _q4(net),
                'qty_rejected': 0,
                'rejection_reason_code': None,
                'rejection_disposition': None,
                'lot_no': line.get('lot_no'),
                'serial_no': line.get('serial_no'),
                'putaway_location_id': line.get('putaway_location_id'),
                'status': STATUS_DRAFT,
                'reversal_of_line_id': line['id'],
            }
            red_line_id = self._insert_line(red_id, red_line, now)
            red_line['id'] = red_line_id

            self._write_reversal_allocations(red_line, red_id, schedule, tol, now)
            self._apply_schedule_reversal(schedule, net, now)
            order_ids.add(schedule['order_id'])

        from meta.services.purchase_order_fulfillment_service import (
            PurchaseOrderFulfillmentService)
        fulfillment = PurchaseOrderFulfillmentService(self.ds)
        for order_id in sorted(order_ids):
            fulfillment.recompute_order(order_id)

        # 红字单过账
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_POSTED, now, red_id, STATUS_DRAFT])
        self.ds.execute(
            'UPDATE %s SET status = ?, actual_arrival_date = COALESCE(?, '
            'actual_arrival_date, receipt_date), updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_POSTED, red_row['actual_arrival_date'], now, red_id])

        # 原单置 reversed（全部行冲销）
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_REVERSED, now, header['id'], STATUS_POSTED])
        self.ds.execute(
            'UPDATE %s SET status = ?, reversed_at = ?, updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_REVERSED, now, now, header['id']])

        # 库存红冲：按原过账事件键生成 REVERSAL（同事务）
        self._reverse_receipt_inventory(header, date)
        # DOC_FLOW 阶段 3：收货行 → 入库事务边整体冲销（红字边 + 原边 reversed）
        self._reverse_receipt_inbound_edges(
            [item['line']['id'] for item in source_items], red_id)
        # P6a-2 §11.5：倒序回退该单据产生的容器事件（装箱 / 发运 / 移库）
        self._reverse_receipt_hus(header)

        logger.info('[receipt] reversed original=%s red=%s lines=%s',
                    header['id'], red_id, len(source_items))
        return {'id': header['id'], 'status': STATUS_REVERSED,
                'reversal_receipt_id': red_id, 'reversal_receipt_no': red_no,
                'order_ids': sorted(order_ids)}

    def _reverse_transfer_order(self, header: Dict[str, Any],
                                receipt_date: Optional[str] = None,
                                receipt_no: Optional[str] = None,
                                remark: Optional[str] = None) -> Dict[str, Any]:
        """TO 来源整单红冲：新建红字单并反向扣减 TO 行 `qty_received`。"""
        if self._reversal_exists(header['id']):
            raise ReceiptError('该收货单已存在红字单，禁止重复冲销',
                               field_name='status', rule='RC_REVERSAL_EXISTS')

        return_type = self._return_header_type()
        date = receipt_date or header.get('receipt_date') or _now()
        red_no = receipt_no or self.allocate_receipt_no(return_type['id'], date)
        if _blank(red_no):
            raise ReceiptError('缺少红字收货单类型或编号序列',
                               field_name='receipt_no', rule='RC_NUMBER_REQUIRED')

        original_lines = self._load_lines(header['id'], status=STATUS_POSTED)
        source_items = []
        for line in original_lines:
            if _blank(line.get('source_line_id')):
                continue
            net = _q4(_dec(line.get('qty_received') or 0)
                      - _dec(line.get('qty_rejected') or 0))
            if net > 0:
                source_items.append((line, net))
        if not source_items:
            raise ReceiptError('原单没有可冲销的净收行', field_name='lines',
                               rule='RC_REVERSAL_INVALID')

        now = _now()
        red_row = {
            'receipt_no': red_no,
            'document_type_id': return_type['id'],
            'receipt_date': date,
            'actual_arrival_date': header.get('actual_arrival_date'),
            'source_doc_type': SOURCE_TRANSFER_ORDER,
            'source_doc_id': header.get('source_doc_id'),
            'source_doc_no': header.get('source_doc_no'),
            'supplier_party_id': None,
            'supplier_delivery_no': header.get('supplier_delivery_no'),
            'org_id': header.get('org_id'),
            'purchase_org_id': None,
            'inventory_org_id': header.get('inventory_org_id'),
            'deliver_to_location_id': header.get('deliver_to_location_id'),
            'project_id': header.get('project_id'),
            'received_by': header.get('received_by'),
            'status': STATUS_DRAFT,
            'reversal_of_receipt_id': header['id'],
            'remark': remark or ('红冲 %s' % header.get('receipt_no')),
            'created_at': now,
            'updated_at': now,
        }
        red_id = self._insert_header(red_row)

        for seq, (line, net) in enumerate(source_items, start=1):
            red_line = {
                'line_no': line.get('line_no') or str(seq),
                'schedule_id': None,
                'source_line_id': line.get('source_line_id'),
                'order_id': None,
                'order_line_id': None,
                'item_id': line['item_id'],
                'uom_id': line['uom_id'],
                'qty_received': _q4(net),
                'qty_rejected': 0,
                'lot_no': line.get('lot_no'),
                'serial_no': line.get('serial_no'),
                'putaway_location_id': line.get('putaway_location_id'),
                'status': STATUS_DRAFT,
                'reversal_of_line_id': line['id'],
            }
            self._insert_line(red_id, red_line, now)

        updates = [{'line_id': line.get('source_line_id'),
                    'qty_received': float(net)}
                   for line, net in source_items]
        from meta.services.transfer_order_service import (
            TransferOrderError, TransferOrderService)
        try:
            TransferOrderService(self.ds).reverse_receipt(
                header.get('source_doc_id'), updates)
        except TransferOrderError as e:
            raise ReceiptError(e.message, field_name=e.field_name,
                               rule=e.rule or 'RC_TRANSFER_REVERSE_FAILED')

        # 红字单过账 + 原单置 reversed
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_POSTED, now, red_id, STATUS_DRAFT])
        self.ds.execute(
            'UPDATE %s SET status = ?, actual_arrival_date = COALESCE(?, '
            'actual_arrival_date, receipt_date), updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_POSTED, red_row['actual_arrival_date'], now, red_id])
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_REVERSED, now, header['id'], STATUS_POSTED])
        self.ds.execute(
            'UPDATE %s SET status = ?, reversed_at = ?, updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_REVERSED, now, now, header['id']])

        # 库存红冲：TO 收货原分录生成 REVERSAL（同事务）
        self._reverse_receipt_inventory(header, date)
        # DOC_FLOW 阶段 3：收货行 → 入库事务边整体冲销（红字边 + 原边 reversed）
        self._reverse_receipt_inbound_edges(
            [line['id'] for line, _ in source_items], red_id)
        # P6a-2 §11.5：倒序回退该单据产生的容器事件（装箱 / 发运 / 移库）
        self._reverse_receipt_hus(header)

        logger.info('[receipt] reversed to original=%s red=%s lines=%s',
                    header['id'], red_id, len(source_items))
        return {'id': header['id'], 'status': STATUS_REVERSED,
                'reversal_receipt_id': red_id, 'reversal_receipt_no': red_no,
                'order_ids': [], 'transfer_order_id': header.get('source_doc_id')}

    def _reverse_work_order(self, header: Dict[str, Any],
                            receipt_date: Optional[str] = None,
                            receipt_no: Optional[str] = None,
                            remark: Optional[str] = None) -> Dict[str, Any]:
        """生产工单来源整单红冲：新建红字单 + 序列号状态回退（P6c §5.3）。

        谱系与 document_serial_links 不解除（与 P6a D13 一致）。
        """
        if self._reversal_exists(header['id']):
            raise ReceiptError('该收货单已存在红字单，禁止重复冲销',
                               field_name='status', rule='RC_REVERSAL_EXISTS')

        return_type = self._return_header_type()
        date = receipt_date or header.get('receipt_date') or _now()
        red_no = receipt_no or self.allocate_receipt_no(return_type['id'], date)
        if _blank(red_no):
            raise ReceiptError('缺少红字收货单类型或编号序列',
                               field_name='receipt_no', rule='RC_NUMBER_REQUIRED')

        original_lines = self._load_lines(header['id'], status=STATUS_POSTED)
        source_items = []
        for line in original_lines:
            net = _q4(_dec(line.get('qty_received') or 0)
                      - _dec(line.get('qty_rejected') or 0))
            if net > 0:
                source_items.append((line, net))
        if not source_items:
            raise ReceiptError('原单没有可冲销的净收行', field_name='lines',
                               rule='RC_REVERSAL_INVALID')

        now = _now()
        red_row = {
            'receipt_no': red_no,
            'document_type_id': return_type['id'],
            'receipt_date': date,
            'actual_arrival_date': header.get('actual_arrival_date'),
            'source_doc_type': SOURCE_WORK_ORDER,
            'source_doc_id': header.get('source_doc_id'),
            'source_doc_no': header.get('source_doc_no'),
            'supplier_party_id': None,
            'supplier_delivery_no': header.get('supplier_delivery_no'),
            'org_id': header.get('org_id'),
            'purchase_org_id': None,
            'inventory_org_id': header.get('inventory_org_id'),
            'deliver_to_location_id': header.get('deliver_to_location_id'),
            'project_id': header.get('project_id'),
            'received_by': header.get('received_by'),
            'status': STATUS_DRAFT,
            'reversal_of_receipt_id': header['id'],
            'remark': remark or ('红冲 %s' % header.get('receipt_no')),
            'created_at': now,
            'updated_at': now,
        }
        red_id = self._insert_header(red_row)

        for seq, (line, net) in enumerate(source_items, start=1):
            red_line = {
                'line_no': line.get('line_no') or str(seq),
                'schedule_id': None,
                'source_line_id': None,
                'order_id': None,
                'order_line_id': None,
                'item_id': line['item_id'],
                'uom_id': line['uom_id'],
                'qty_received': _q4(net),
                'qty_rejected': 0,
                'lot_no': line.get('lot_no'),
                'serial_no': line.get('serial_no'),
                'putaway_location_id': line.get('putaway_location_id'),
                'status': STATUS_DRAFT,
                'reversal_of_line_id': line['id'],
            }
            self._insert_line(red_id, red_line, now)

        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_POSTED, now, red_id, STATUS_DRAFT])
        self.ds.execute(
            'UPDATE %s SET status = ?, actual_arrival_date = COALESCE(?, '
            'actual_arrival_date, receipt_date), updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_POSTED, red_row['actual_arrival_date'], now, red_id])
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE receipt_id = ? '
            'AND status = ?' % LINE_TABLE,
            [STATUS_REVERSED, now, header['id'], STATUS_POSTED])
        self.ds.execute(
            'UPDATE %s SET status = ?, reversed_at = ?, updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [STATUS_REVERSED, now, now, header['id']])

        self._reverse_receipt_inventory(header, date)
        # DOC_FLOW 阶段 3：收货行 → 入库事务边整体冲销（红字边 + 原边 reversed）
        self._reverse_receipt_inbound_edges(
            [line['id'] for line, _ in source_items], red_id)
        # P6a-2 §11.5：倒序回退该单据产生的容器事件（装箱 / 发运 / 移库）
        self._reverse_receipt_hus(header)
        self._reverse_completion_serials(header.get('source_doc_id'), header['id'])

        logger.info('[receipt] reversed work order original=%s red=%s lines=%s',
                    header['id'], red_id, len(source_items))
        return {'id': header['id'], 'status': STATUS_REVERSED,
                'reversal_receipt_id': red_id, 'reversal_receipt_no': red_no,
                'order_ids': [], 'work_order_id': header.get('source_doc_id')}

    # ------------------------------------------------------------- 库存过账
    def _post_receipt_inventory(self, header: Dict[str, Any],
                                checked: List[Dict[str, Any]],
                                transaction_type: str) -> Dict[int, Any]:
        """按收货行写库存入账分录（RCV_PO / RCV_TO / RCV_WO）。

        净收（qty_received - qty_rejected）为库存入账数量；净收为 0 的行跳过。
        库存组织取 receipt.inventory_org_id，库位取 deliver_to_location_id。
        返回 ``{收货行 id: 库存事务 id}``，供 DOC_FLOW attach 边定位目标行；
        开关关闭 / 无分录时返回空映射。
        """
        from meta.services.inventory_guard_service import (
            InventoryError, InventoryGuardService)
        from meta.services.inventory_posting_service import (
            InventoryPostingService,
        )
        from meta.services.stock_segment_service import StockSegmentService

        if not InventoryGuardService(self.ds).posting_enabled():
            return {}

        org_id = header.get('inventory_org_id')
        location_id = header.get('deliver_to_location_id')
        segments = StockSegmentService(self.ds)
        supplier_id = header.get('supplier_party_id')
        entries = []
        for item in checked:
            line = item.get('line') or {}
            net = float(item.get('net') or 0)
            if net <= 0:
                continue
            context = {
                'item_id': line.get('item_id'),
                'org_id': org_id,
            }
            # G7：项目字段只能来自该行的需求分配（收货桥复制），禁止手填不同值
            project_id, project_task_id = self._line_project_scope(line)
            if project_id:
                context['project_id'] = project_id
            if project_task_id:
                context['project_task_id'] = project_task_id
            # G1：寄售物料收货时所有权仍归供应商；普通物料走 owned。
            if supplier_id and segments.item_flags(
                    line.get('item_id'))['consignment_enabled']:
                context['owner_party_id'] = supplier_id
            segment = segments.resolve_segment(context)
            entry = {
                'transaction_type': transaction_type,
                'transaction_date': header.get('receipt_date'),
                'org_id': org_id,
                'location_id': location_id,
                'item_id': line.get('item_id'),
                'uom_id': line.get('uom_id'),
                'qty': net,
                'batch_id': self._resolve_batch_id(
                    org_id, line.get('item_id'), line.get('lot_no')),
                'stock_status': 'unrestricted',
                'source_line_id': line.get('id'),
                'remark': '收货单 %s' % header.get('receipt_no'),
            }
            entry.update(segment)
            entries.append(entry)
        if not entries:
            return {}

        source = {
            'source_doc_type': 'receipt',
            'source_doc_id': header.get('id'),
            'source_event_key': 'receipt:%s:post' % header.get('id'),
            'transaction_date': header.get('receipt_date'),
            'remark': '收货单 %s 过账' % header.get('receipt_no'),
        }
        try:
            InventoryPostingService(self.ds).post(entries, source)
        except InventoryError as e:
            raise ReceiptError(e.message, field_name='inventory', rule=e.code)

        rows = self.ds.query(
            'SELECT id, source_line_id FROM inventory_transactions '
            'WHERE source_event_key = ?', [source['source_event_key']])
        return {int(row['source_line_id']): row['id']
                for row in rows if row.get('source_line_id') is not None}

    def _write_receipt_inbound_edges(self, checked: List[Dict[str, Any]],
                                     txns: Dict[int, Any]) -> None:
        """把「收货行 → 入库事务」写成 DOC_FLOW 边（attach 模式）。

        未启用 DOC_FLOW（规则 / 边表缺失）或当日无入库事务时降级为告警，
        不阻断收货过账。
        """
        if not txns:
            return
        from meta.core.doc_flow_attach import attach_edge
        for item in checked:
            line = item.get('line') or {}
            net = float(item.get('net') or 0)
            if net <= 0:
                continue
            txn_id = txns.get(int(line.get('id') or 0))
            if not txn_id:
                continue
            attach_edge(
                self.ds, self.platform_ds, 'receipt_line_to_inventory_txn',
                line.get('id'), txn_id, net,
                target_item=str(line.get('id') or ''),
                unit=str(line.get('uom_id') or ''),
                derived_by='receipt_service')

    def _reverse_receipt_inbound_edges(self, line_ids: List[Any],
                                       red_receipt_id: Any) -> None:
        """红冲时整体冲销「收货行 → 入库事务」边（红字边 + 原边 reversed）。

        DOC_FLOW 未启用 / 边表缺失时降级为告警，不阻断收货红冲。
        """
        if not line_ids or _blank(red_receipt_id):
            return
        try:
            from meta.core.doc_flow_attach import reverse_edges_by_source
        except Exception:  # pragma: no cover - 核心模块缺失时保持红冲可用
            logger.warning('[receipt] DOC_FLOW 模块不可用，跳过红字边')
            return
        for line_id in line_ids:
            if _blank(line_id):
                continue
            reverse_edges_by_source(
                self.ds, 'receipt_line_to_inventory_txn', 'receipt_line',
                line_id, ref_id=red_receipt_id, derived_by='receipt_service')

    def _line_project_scope(self, line: Dict[str, Any]) -> tuple:
        """G7：收货行的项目 / 任务归属以该行 active 需求分配为唯一真源。

        · 无分配：回退到收货行自身的 project_task_id（来源单据口径）。
        · 分配不唯一 / 与行上手填值冲突：400，禁止调用方自造项目归属。
        """
        rows = self.ds.query(
            "SELECT project_id, project_task_id FROM %s "
            "WHERE target_bo = 'receipt' AND target_line_id = ? "
            "AND status = 'active'" % ALLOCATION_TABLE,
            [line.get('id')])
        pairs = {(int(row.get('project_id') or 0),
                  int(row.get('project_task_id') or 0)) for row in rows}
        line_task = int(line.get('project_task_id') or 0)
        if len(pairs) > 1:
            raise ReceiptError(
                '收货行 %s 的项目分配不唯一（%s 组），无法确定库存归属'
                % (line.get('id'), len(pairs)),
                field_name='project_task_id',
                rule='RC_PROJECT_SOURCE_AMBIGUOUS')
        if not pairs:
            return int(line.get('project_id') or 0), line_task
        project_id, task_id = pairs.pop()
        if line_task and line_task != task_id:
            raise ReceiptError(
                '收货行 %s 的项目任务 %s 与需求分配 %s 不一致（禁止手填）'
                % (line.get('id'), line_task, task_id or '空'),
                field_name='project_task_id',
                rule='RC_PROJECT_SOURCE_MISMATCH')
        return project_id, task_id

    def _resolve_batch_id(self, org_id: Any, item_id: Any,
                          lot_no: Any) -> Optional[int]:
        """收货行 lot_no → 批次 id（无匹配则返回 None，不阻断过账）。"""
        if not lot_no or _blank(org_id) or _blank(item_id):
            return None
        rows = self.ds.query(
            'SELECT id FROM batches WHERE item_id = ? AND org_id = ? '
            'AND batch_no = ?', [item_id, org_id, lot_no])
        return rows[0]['id'] if rows else None

    # ------------------------------------------------------------------ 序列号（P6a）
    def _item_serial_flags(self, item_id: Any) -> Dict[str, Any]:
        if _blank(item_id):
            return {}
        rows = self.ds.query(
            'SELECT serial_tracked, require_on_receipt FROM items WHERE id = ?',
            [item_id])
        return rows[0] if rows else {}

    def _has_serial_tracked(self, checked: Any) -> bool:
        from meta.services.serial_number_service import serial_schema_ready
        if not serial_schema_ready(self.ds):
            return False
        for item in checked or []:
            line = item.get('line') or {}
            if str(line.get('serial_no') or '').strip():
                return True
            if self._item_serial_flags(line.get('item_id')).get('serial_tracked'):
                return True
        return False

    def _validate_serial_tracking(self, header: Dict[str, Any],
                                  checked: Any) -> None:
        """§6.1 收货前置：require_on_receipt 时 link 数必须等于净收数量。"""
        if not self._has_serial_tracked(checked):
            return
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService,
        )
        try:
            SerialNumberService(self.ds).precheck_receipt(header['id'])
        except SerialNumberError as error:
            raise ReceiptError(str(error), field_name=error.field_name or 'serial_no',
                               rule=error.rule or 'SERIAL_RECEIPT_COUNT_MISMATCH')

    def _register_receipt_serials(self, header: Dict[str, Any],
                                  checked: Any) -> None:
        if not self._has_serial_tracked(checked):
            return
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService,
        )
        try:
            SerialNumberService(self.ds).register_receipt(header['id'])
        except SerialNumberError as error:
            raise ReceiptError(str(error), field_name=error.field_name or 'serial_no',
                               rule=error.rule or 'SERIAL_RECEIPT_REGISTER_FAILED')

    def _serial_ready(self) -> bool:
        from meta.services.serial_number_service import serial_schema_ready
        return serial_schema_ready(self.ds)

    def _hu_ready(self) -> bool:
        from meta.services.handling_unit_service import hu_schema_ready
        return hu_schema_ready(self.ds)

    def _register_receipt_hus(self, header: Dict[str, Any]) -> None:
        """P6a-2 §11.5：过账后按行 hu_no 建箱 / 装箱；表缺失时 no-op。"""
        if not self._hu_ready():
            return
        from meta.services.handling_unit_service import (
            HandlingUnitError, HandlingUnitService,
        )
        try:
            HandlingUnitService(self.ds).pack_receipt(header['id'])
        except HandlingUnitError as error:
            raise ReceiptError(
                str(error), field_name=error.field_name or 'hu_no',
                rule=error.rule or 'HU_PACK_FAILED')

    def _reverse_receipt_hus(self, header: Dict[str, Any]) -> None:
        """红冲：倒序回退该收货单产生的容器事件（不删历史事件）。"""
        if not self._hu_ready():
            return
        from meta.services.handling_unit_service import (
            HandlingUnitError, HandlingUnitService,
        )
        try:
            HandlingUnitService(self.ds).reverse_document('receipt', header['id'])
        except HandlingUnitError as error:
            raise ReceiptError(
                str(error), field_name=error.field_name or 'hu_no',
                rule=error.rule or 'HU_REVERSE_FAILED')

    def _precheck_transfer_receipt_serials(self, transfer_order_id: Any,
                                           receipt_id: Any) -> None:
        """TO 来源收货前置：在途号数量必须等于净收数量。"""
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService,
        )
        try:
            SerialNumberService(self.ds).precheck_transfer_receipt(
                transfer_order_id, receipt_id)
        except SerialNumberError as error:
            raise ReceiptError(
                str(error), field_name=error.field_name or 'serial_no',
                rule=error.rule or 'SERIAL_TRANSFER_COUNT_MISMATCH')

    def _register_transfer_receipt_serials(self, transfer_order_id: Any,
                                           receipt_id: Any) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService,
        )
        try:
            SerialNumberService(self.ds).register_transfer_receipt(
                transfer_order_id, receipt_id)
        except SerialNumberError as error:
            raise ReceiptError(
                str(error), field_name=error.field_name or 'serial_no',
                rule=error.rule or 'SERIAL_TRANSFER_REGISTER_FAILED')

    def _precheck_work_order_serials(self, work_order_id: Any,
                                     receipt_id: Any) -> None:
        """完工前置：成品录号完整性 + 组件号合法性（D7）。"""
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService,
        )
        try:
            SerialNumberService(self.ds).precheck_completion(
                work_order_id, receipt_id)
        except SerialNumberError as error:
            raise ReceiptError(
                str(error), field_name=error.field_name or 'serial_no',
                rule=error.rule or 'SERIAL_COMPLETION_INVALID')

    def _register_completion_serials(self, work_order_id: Any,
                                     receipt_id: Any,
                                     event_key: Any = None) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService,
        )
        try:
            SerialNumberService(self.ds).register_completion(
                work_order_id, receipt_id, event_key)
        except SerialNumberError as error:
            raise ReceiptError(
                str(error), field_name=error.field_name or 'serial_no',
                rule=error.rule or 'SERIAL_COMPLETION_REGISTER_FAILED')

    def _reverse_completion_serials(self, work_order_id: Any,
                                    receipt_id: Any) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService,
        )
        try:
            SerialNumberService(self.ds).reverse_completion(
                work_order_id, receipt_id)
        except SerialNumberError as error:
            raise ReceiptError(
                str(error), field_name=error.field_name or 'serial_no',
                rule=error.rule or 'SERIAL_COMPLETION_REVERSE_FAILED')

    def _reverse_receipt_inventory(self, header: Dict[str, Any],
                                   transaction_date: Any = None) -> None:
        """按原过账事件键写 REVERSAL 反冲分录。"""
        from meta.services.inventory_guard_service import InventoryError
        from meta.services.inventory_posting_service import (
            InventoryPostingService,
        )

        receipt_id = header.get('id')
        source = {
            'source_doc_type': 'receipt',
            'source_doc_id': receipt_id,
            'source_event_key': 'receipt:%s:reverse' % receipt_id,
            'transaction_date': transaction_date,
            'remark': '收货单 %s 红冲' % header.get('receipt_no'),
        }
        try:
            InventoryPostingService(self.ds).reverse_by_source(
                'receipt:%s:post' % receipt_id, source,
                transaction_date=transaction_date or header.get('receipt_date'))
        except InventoryError as e:
            raise ReceiptError(e.message, field_name='inventory', rule=e.code)

    # ------------------------------------------------------------------ 行校验
    def validate_new_line(self, payload: Dict[str, Any],
                          receipt_id: Any = None) -> Dict[str, Any]:
        """校验新建收货行并返回归一化冗余列（供守卫回填）。"""
        header = self._require_header(receipt_id or payload.get('receipt_id'))
        if header['status'] in UNDELETABLE_STATUSES:
            raise ReceiptError('已过账 / 已冲销的收货单禁止新增行',
                               field_name='status',
                               rule='RC_POSTED_IMMUTABLE')
        doc_type = self._require_document_type(header.get('document_type_id'))
        if header.get('source_doc_type') == SOURCE_WORK_ORDER:
            order = self._load_work_order(header.get('source_doc_id'))
            if order is None:
                raise ReceiptError('来源生产工单不存在',
                                   field_name='source_doc_id',
                                   rule='RC_WORK_ORDER_INVALID')
            return self._normalized_work_order_payload(
                self._validate_work_order_line(payload, order, doc_type))
        if header.get('source_doc_type') == SOURCE_TRANSFER_ORDER:
            order = self._load_transfer_order(header.get('source_doc_id'))
            if order is None:
                raise ReceiptError('来源调拨单不存在',
                                   field_name='source_doc_id',
                                   rule='RC_TRANSFER_NOT_FOUND')
            return self._normalized_transfer_payload(
                self._validate_transfer_line(payload, order, doc_type))
        order = self._load_order(header.get('source_doc_id'))
        if order is None:
            raise ReceiptError('来源采购订单不存在', field_name='source_doc_id',
                               rule='RC_ORDER_NOT_FOUND')
        return self._normalized_payload(self._validate_line(payload, order, doc_type))

    def update_line(self, line_id: Any, patch: Dict[str, Any]) -> Dict[str, Any]:
        """校验行编辑并返回归一化冗余列（供守卫回填到写入口径）。

        仅草稿抬头可编辑；已过账行禁止改数量 / 计划行（R-RC-6）。
        """
        line = self._require_line(line_id)
        header = self._require_header(line['receipt_id'])
        patch = dict(patch or {})
        if line['status'] != STATUS_DRAFT \
                or header['status'] != STATUS_DRAFT:
            raise ReceiptError('已过账 / 已冲销的行禁止修改',
                               field_name='qty_received',
                               rule='RC_POSTED_IMMUTABLE')
        merged = dict(line)
        merged.update({k: v for k, v in patch.items()
                       if k in ('schedule_id', 'source_line_id', 'qty_received',
                                'qty_rejected', 'rejection_reason_code',
                                'rejection_disposition', 'lot_no', 'serial_no',
                                'putaway_location_id')})
        doc_type = self._require_document_type(header.get('document_type_id'))
        if header.get('source_doc_type') == SOURCE_TRANSFER_ORDER:
            order = self._load_transfer_order(header.get('source_doc_id'))
            if order is None:
                raise ReceiptError('来源调拨单不存在',
                                   field_name='source_doc_id',
                                   rule='RC_TRANSFER_NOT_FOUND')
            normalized = self._validate_transfer_line(merged, order, doc_type)
            return self._normalized_transfer_payload(normalized)
        order = self._load_order(header.get('source_doc_id'))
        normalized = self._validate_line(merged, order, doc_type)
        return self._normalized_payload(normalized, for_update=True)

    def assert_deletable(self, receipt_id: Any) -> None:
        header = self._require_header(receipt_id)
        if header['status'] in UNDELETABLE_STATUSES:
            raise ReceiptError('已过账 / 已冲销的收货单禁止删除',
                               field_name='status', rule='RC_POSTED_IMMUTABLE')

    def assert_line_deletable(self, line_id: Any) -> None:
        """R-RC-6：已过账 / 已冲销的行禁止删除。"""
        line = self._require_line(line_id)
        header = self._require_header(line['receipt_id'])
        if header['status'] in UNDELETABLE_STATUSES \
                or line['status'] != STATUS_DRAFT:
            raise ReceiptError('已过账 / 已冲销的行禁止删除',
                               field_name='status', rule='RC_POSTED_IMMUTABLE')

    # ------------------------------------------------------------------ 计划行回写
    def _apply_schedule_receipt(self, schedule: Dict[str, Any], net: Decimal,
                                rejected: Decimal, tol: Decimal,
                                now: str) -> None:
        """标准单：条件 UPDATE 原子累加（R-RC-5）；`rowcount=0` 即拒绝。"""
        cursor = self.ds.execute(
            'UPDATE %s SET received_qty = COALESCE(received_qty, 0) + ?, '
            'rejected_qty = COALESCE(rejected_qty, 0) + ?, updated_at = ? '
            'WHERE id = ? '
            "AND COALESCE(completion_source, '') <> '%s' "
            'AND (promised_qty IS NULL '
            '     OR COALESCE(received_qty, 0) + ? <= promised_qty * (1 + ?))'
            % (SCHEDULE_TABLE, COMPLETION_SOURCE_SHORT_CLOSE),
            [float(net), float(rejected), now, schedule['id'],
             float(net), float(tol)])
        if not getattr(cursor, 'rowcount', 0):
            fresh = self._load_schedule(schedule['id']) or {}
            if fresh.get('completion_source') == COMPLETION_SOURCE_SHORT_CLOSE:
                raise ReceiptError('计划行已短收结案，禁止再收货',
                                   field_name='schedule_id',
                                   rule='RC_SCHEDULE_CLOSED')
            raise ReceiptError(
                '收货数量超过计划行承诺量（promised_qty=%s，容差 %s%%）'
                % (schedule.get('promised_qty'), tol * 100),
                field_name='qty_received', rule='RC_OVER_RECEIPT')

        # R-RC-10：净收累计达标且原状态 pending 时才自动完成，并留存来源与前一状态
        if schedule.get('status') in SCHEDULE_PENDING_STATUSES:
            promised = schedule.get('promised_qty')
            if not _blank(promised) and net > 0:
                self.ds.execute(
                    'UPDATE %s SET status = ?, completion_source = ?, '
                    'completion_prev_status = ?, updated_at = ? '
                    'WHERE id = ? AND status = ? '
                    'AND promised_qty IS NOT NULL '
                    'AND COALESCE(received_qty, 0) >= promised_qty'
                    % SCHEDULE_TABLE,
                    [SCHEDULE_STATUS_COMPLETED, COMPLETION_SOURCE_RECEIPT,
                     schedule['status'], now, schedule['id'],
                     schedule['status']])

    def _apply_schedule_reversal(self, schedule: Dict[str, Any], net: Decimal,
                                 now: str) -> None:
        """红字单：净收减回；仅回退由收货置位的完成（R-RC-10）。"""
        self.ds.execute(
            'UPDATE %s SET received_qty = COALESCE(received_qty, 0) - ?, '
            'updated_at = ? WHERE id = ?' % SCHEDULE_TABLE,
            [float(net), now, schedule['id']])
        row = self._load_schedule(schedule['id']) or {}
        promised = row.get('promised_qty')
        if row.get('completion_source') == COMPLETION_SOURCE_RECEIPT \
                and (_blank(promised)
                     or _dec(row.get('received_qty') or 0) < _dec(promised)):
            self.ds.execute(
                'UPDATE %s SET status = COALESCE(completion_prev_status, ?), '
                'completion_source = NULL, completion_prev_status = NULL, '
                'updated_at = ? WHERE id = ? '
                "AND completion_source = '%s'"
                % (SCHEDULE_TABLE, COMPLETION_SOURCE_RECEIPT),
                ['confirmed', now, schedule['id']])

    # ------------------------------------------------------------------ 需求分配
    def _write_allocations(self, line: Dict[str, Any], receipt_id: Any,
                           schedule: Dict[str, Any], net: Decimal,
                           tol: Decimal, now: str) -> None:
        """标准单：按 PO 分配剩余量占比拆分（§6.1）。"""
        planned = self._po_allocations(schedule['id'])
        if not planned:
            # 计划行未挂需求分配（如人工建单）⇒ 无需求可追溯，跳过而不拦截
            return
        received = self._received_net_by_demand(schedule['id'])
        remaining = []
        total = Decimal('0')
        for row in planned:
            left = _dec(row.get('qty') or 0) - received.get(row['demand_line_id'], Decimal('0'))
            if left <= 0:
                continue
            remaining.append((row, left))
            total += left
        if total <= 0:
            raise ReceiptError('计划行的需求分配剩余量为 0，无法继续分配',
                               field_name='schedule_id', rule='RC_ALLOC_EXHAUSTED')
        cap = total + _dec(schedule.get('promised_qty') or 0) * tol
        if net > cap:
            raise ReceiptError('收货分配超过 PO 分配剩余量（可分配 %s）' % total,
                               field_name='qty_received', rule='RC_ALLOC_OVER')

        allocated = Decimal('0')
        for idx, (row, left) in enumerate(remaining):
            if idx == len(remaining) - 1:
                part = _q4(net - allocated)
            else:
                part = _q4(net * left / total)
                allocated += part
            self._insert_allocation(row, receipt_id, line, schedule, part, now)

    def _write_reversal_allocations(self, line: Dict[str, Any], red_receipt_id: Any,
                                    schedule: Dict[str, Any], tol: Decimal,
                                    now: str) -> None:
        """红字单：按原行分配逐行取负（§7）。"""
        if not line.get('reversal_of_line_id'):
            return
        source_rows = self.ds.query(
            "SELECT * FROM %s WHERE target_bo = 'receipt' "
            'AND target_line_id = ? ORDER BY id' % ALLOCATION_TABLE,
            [line['reversal_of_line_id']])
        for row in source_rows:
            self._insert_allocation(row, red_receipt_id, line, schedule,
                                    -_q4(_dec(row.get('qty') or 0)), now)

    def _po_allocations(self, schedule_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            "SELECT * FROM %s WHERE target_bo = 'purchase_order' "
            "AND target_schedule_id = ? AND status = 'active' ORDER BY id"
            % ALLOCATION_TABLE, [schedule_id])

    def _received_net_by_demand(self, schedule_id: Any) -> Dict[Any, Decimal]:
        rows = self.ds.query(
            "SELECT demand_line_id, COALESCE(SUM(qty), 0) AS total FROM %s "
            "WHERE target_bo = 'receipt' AND target_schedule_id = ? "
            'GROUP BY demand_line_id' % ALLOCATION_TABLE, [schedule_id])
        return {row['demand_line_id']: _dec(row.get('total') or 0) for row in rows}

    def _insert_allocation(self, source: Dict[str, Any], receipt_id: Any,
                           line: Dict[str, Any], schedule: Dict[str, Any],
                           qty: Decimal, now: str) -> None:
        """整行复制 PO 分配的需求 / 成本字段，只换 target_* 与 qty。"""
        self.ds.execute(
            'INSERT INTO %s (demand_bo, demand_id, demand_line_id, demand_line_no, '
            'demand_need_date, project_id, project_task_id, target_bo, target_id, '
            'target_line_id, target_schedule_id, qty, uom_id, allocated_amount, '
            'cost_center_id, expense_account_code, asset_category_code, '
            'charge_basis, status, created_at, updated_at) '
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'receipt', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "'active', ?, ?)" % ALLOCATION_TABLE,
            [source.get('demand_bo'), source.get('demand_id'),
             source.get('demand_line_id'), source.get('demand_line_no'),
             source.get('demand_need_date'), source.get('project_id'),
             source.get('project_task_id'), receipt_id, line.get('id'),
             schedule['id'], float(qty), source.get('uom_id'),
             source.get('allocated_amount'), source.get('cost_center_id'),
             source.get('expense_account_code'),
             source.get('asset_category_code'),
             source.get('charge_basis') or 'inventory', now, now])

    # ------------------------------------------------------------------ 校验
    def _require_document_type(self, type_id: Any) -> Dict[str, Any]:
        if _blank(type_id):
            raise ReceiptError('单据类型必填', field_name='document_type_id',
                               rule='RC_DOC_TYPE_INVALID')
        rows = self.ds.query(
            'SELECT id, code, scope_bo, level, document_category FROM %s '
            'WHERE id = ?' % TYPE_TABLE, [type_id])
        if not rows:
            raise ReceiptError('单据类型不存在', field_name='document_type_id',
                               rule='RC_DOC_TYPE_INVALID')
        row = rows[0]
        if row.get('scope_bo') != 'receipt' or row.get('level') != 'header':
            raise ReceiptError('单据类型必须是收货单抬头类型',
                               field_name='document_type_id',
                               rule='RC_DOC_TYPE_INVALID')
        if row.get('document_category') not in DOC_CATEGORIES:
            raise ReceiptError('收货单类型的方向必须是 standard / return',
                               field_name='document_type_id',
                               rule='RC_DOC_TYPE_INVALID')
        return row

    def _header_type(self, category: str) -> Dict[str, Any]:
        rows = self.ds.query(
            "SELECT id, code, document_category FROM %s WHERE scope_bo = 'receipt' "
            "AND level = 'header' AND document_category = ? ORDER BY id LIMIT 1"
            % TYPE_TABLE, [category])
        if not rows:
            raise ReceiptError(
                '缺少收货单类型（document_category=%s）' % category,
                field_name='document_type_id', rule='RC_DOC_TYPE_INVALID')
        return rows[0]

    def standard_header_type(self) -> Dict[str, Any]:
        return self._header_type(DOC_CATEGORY_STANDARD)

    def _return_header_type(self) -> Dict[str, Any]:
        return self._header_type(DOC_CATEGORY_RETURN)

    def allocate_reversal_no(self, receipt_id: Any,
                             receipt_date: Optional[str] = None) -> str:
        """红字单取号（R-RC-8：必须在开事务前调用，供 BO Action 用）。"""
        header = self._require_header(receipt_id)
        date = receipt_date or header.get('receipt_date')
        red_no = self.allocate_receipt_no(self._return_header_type()['id'], date)
        if _blank(red_no):
            raise ReceiptError('缺少红字收货单类型或编号序列',
                               field_name='receipt_no', rule='RC_NUMBER_REQUIRED')
        return red_no

    def _validate_line(self, line: Dict[str, Any], order: Dict[str, Any],
                       doc_type: Dict[str, Any],
                       for_post: bool = False) -> Dict[str, Any]:
        """R-RC-1 ~ R-RC-4 / R-RC-15 / R-RC-17 + 冗余列一致性。"""
        line = dict(line or {})
        source_type = 'purchase_order'
        schedule_id = line.get('schedule_id')
        if _blank(schedule_id):
            raise ReceiptError(
                'PO 来源的收货行必须挂到货计划行',
                field_name='schedule_id', rule='RC_SCHEDULE_INVALID')
        schedule = self._load_schedule(schedule_id)
        if schedule is None:
            raise ReceiptError('计划行不存在', field_name='schedule_id',
                               rule='RC_SCHEDULE_INVALID')
        if schedule.get('schedule_kind') not in SCHEDULE_KIND_ALLOWED:
            raise ReceiptError('收货行只能挂到货 / 服务计划行',
                               field_name='schedule_id', rule='RC_SCHEDULE_INVALID')
        if for_post and schedule.get('status') not in SCHEDULE_PENDING_STATUSES:
            raise ReceiptError('计划行状态不可收货（需 planned / confirmed）',
                               field_name='schedule_id', rule='RC_SCHEDULE_INVALID')
        if schedule.get('completion_source') == COMPLETION_SOURCE_SHORT_CLOSE:
            raise ReceiptError('计划行已短收结案，禁止再收货',
                               field_name='schedule_id', rule='RC_SCHEDULE_CLOSED')
        if schedule.get('order_id') != order['id']:
            raise ReceiptError('计划行不属于该收货单的来源订单',
                               field_name='schedule_id', rule='RC_SCHEDULE_INVALID')

        order_line = self._load_order_line(schedule.get('line_id'))
        if order_line is None:
            raise ReceiptError('计划行对应的订单行不存在',
                               field_name='schedule_id', rule='RC_SCHEDULE_INVALID')
        for field, expected in (('order_line_id', order_line['id']),
                                ('order_id', order['id']),
                                ('item_id', order_line.get('item_id')),
                                ('uom_id', order_line.get('uom_id'))):
            if _blank(line.get(field)) or _blank(expected):
                continue
            if int(line[field]) != int(expected):
                raise ReceiptError(
                    '收货行 %s 与计划行反查结果不一致' % field,
                    field_name=field, rule='RC_LINE_MISMATCH')

        received = _dec(line.get('qty_received'), 'qty_received')
        if received <= 0:
            raise ReceiptError('收货数量必须大于 0', field_name='qty_received',
                               rule='RC_QTY_INVALID')
        rejected = _dec(line.get('qty_rejected') or 0, 'qty_rejected')
        if rejected < 0 or rejected > received:
            raise ReceiptError('拒收数量须在 0 ~ 收货数量之间',
                               field_name='qty_rejected', rule='RC_QTY_INVALID')
        if rejected > 0:
            if _blank(line.get('rejection_reason_code')):
                raise ReceiptError('存在拒收时必须填拒收原因',
                                   field_name='rejection_reason_code',
                                   rule='RC_REJECTION_INCOMPLETE')
            if _blank(line.get('rejection_disposition')):
                raise ReceiptError('存在拒收时必须填拒收处置',
                                   field_name='rejection_disposition',
                                   rule='RC_REJECTION_INCOMPLETE')
            if line['rejection_disposition'] not in REJECTION_DISPOSITIONS:
                raise ReceiptError('拒收处置取值非法',
                                   field_name='rejection_disposition',
                                   rule='RC_REJECTION_INCOMPLETE')
        self._assert_location_active(line.get('putaway_location_id'))

        return {
            'line': line,
            'schedule': schedule,
            'order_line': order_line,
            'net': _q4(received - rejected),
            'rejected': _q4(rejected),
        }

    def _validate_transfer_line(self, line: Dict[str, Any],
                                transfer_order: Dict[str, Any],
                                doc_type: Dict[str, Any],
                                for_post: bool = False) -> Dict[str, Any]:
        """TO 来源行校验（spec §7.2）：`source_line_id` 反查 + 通用数量校验。

        不要求 `schedule_id` / `order_id`；不校验供应商、超收容差等 PO 专属口径。
        """
        line = dict(line or {})
        source_line_id = line.get('source_line_id')
        if _blank(source_line_id):
            raise ReceiptError(
                '调拨单来源的收货行必须挂调拨行（source_line_id）',
                field_name='source_line_id', rule='RC_TRANSFER_LINE_INVALID')
        source_line = self._load_transfer_line(source_line_id)
        if source_line is None:
            raise ReceiptError('调拨行不存在', field_name='source_line_id',
                               rule='RC_TRANSFER_LINE_INVALID')
        if str(source_line.get('transfer_order_id')) != str(transfer_order['id']):
            raise ReceiptError('调拨行不属于该收货单的来源调拨单',
                               field_name='source_line_id',
                               rule='RC_TRANSFER_LINE_INVALID')
        if str(source_line.get('status') or '').strip().lower() != 'open':
            raise ReceiptError('调拨行已关闭 / 已取消，禁止收货',
                               field_name='source_line_id',
                               rule='RC_TRANSFER_LINE_CLOSED')

        for field, expected in (('item_id', source_line.get('item_id')),
                                ('uom_id', source_line.get('uom_id'))):
            if _blank(line.get(field)) or _blank(expected):
                continue
            if str(line[field]) != str(expected):
                raise ReceiptError(
                    '收货行 %s 与调拨行反查结果不一致' % field,
                    field_name=field, rule='RC_LINE_MISMATCH')

        received = _dec(line.get('qty_received'), 'qty_received')
        if received <= 0:
            raise ReceiptError('收货数量必须大于 0', field_name='qty_received',
                               rule='RC_QTY_INVALID')
        rejected = _dec(line.get('qty_rejected') or 0, 'qty_rejected')
        if rejected < 0 or rejected > received:
            raise ReceiptError('拒收数量须在 0 ~ 收货数量之间',
                               field_name='qty_rejected', rule='RC_QTY_INVALID')
        if rejected > 0:
            if _blank(line.get('rejection_reason_code')):
                raise ReceiptError('存在拒收时必须填拒收原因',
                                   field_name='rejection_reason_code',
                                   rule='RC_REJECTION_INCOMPLETE')
            if _blank(line.get('rejection_disposition')):
                raise ReceiptError('存在拒收时必须填拒收处置',
                                   field_name='rejection_disposition',
                                   rule='RC_REJECTION_INCOMPLETE')
            if line['rejection_disposition'] not in REJECTION_DISPOSITIONS:
                raise ReceiptError('拒收处置取值非法',
                                   field_name='rejection_disposition',
                                   rule='RC_REJECTION_INCOMPLETE')
        self._assert_location_active(line.get('putaway_location_id'))

        return {
            'line': line,
            'transfer_line': source_line,
            'order_line': source_line,
            'schedule': None,
            'net': _q4(received - rejected),
            'rejected': _q4(rejected),
        }

    def _validate_work_order_line(self, line: Dict[str, Any],
                                  work_order: Dict[str, Any],
                                  doc_type: Dict[str, Any],
                                  for_post: bool = False) -> Dict[str, Any]:
        """生产工单来源行校验（P6c）：成品物料与数量由调用方显式给出。"""
        line = dict(line or {})
        if _blank(line.get('item_id')):
            raise ReceiptError('完工收货行必须指定成品物料',
                               field_name='item_id',
                               rule='RC_WORK_ORDER_LINE_INVALID')
        received = _dec(line.get('qty_received'), 'qty_received')
        if received <= 0:
            raise ReceiptError('收货数量必须大于 0', field_name='qty_received',
                               rule='RC_QTY_INVALID')
        rejected = _dec(line.get('qty_rejected') or 0, 'qty_rejected')
        if rejected < 0 or rejected > received:
            raise ReceiptError('拒收数量须在 0 ~ 收货数量之间',
                               field_name='qty_rejected', rule='RC_QTY_INVALID')
        if rejected > 0:
            if _blank(line.get('rejection_reason_code')):
                raise ReceiptError('存在拒收时必须填拒收原因',
                                   field_name='rejection_reason_code',
                                   rule='RC_REJECTION_INCOMPLETE')
            if _blank(line.get('rejection_disposition')):
                raise ReceiptError('存在拒收时必须填拒收处置',
                                   field_name='rejection_disposition',
                                   rule='RC_REJECTION_INCOMPLETE')
            if line['rejection_disposition'] not in REJECTION_DISPOSITIONS:
                raise ReceiptError('拒收处置取值非法',
                                   field_name='rejection_disposition',
                                   rule='RC_REJECTION_INCOMPLETE')
        self._assert_location_active(line.get('putaway_location_id'))
        return {
            'line': line,
            'work_order': work_order,
            'order_line': None,
            'schedule': None,
            'net': _q4(received - rejected),
            'rejected': _q4(rejected),
        }

    def _assert_location_active(self, location_id: Any) -> None:
        """R-RC-15：指定入库库位必须启用；库表缺失时 fail-open。"""
        if _blank(location_id):
            return
        try:
            rows = self.ds.query(
                'SELECT status FROM %s WHERE id = ?' % LOCATION_TABLE,
                [location_id])
        except Exception as e:  # noqa: BLE001 - 旧环境无 locations 表
            logger.warning('[receipt] 读取库位失败（跳过校验）: %s', e)
            return
        if rows and rows[0].get('status') != 'active':
            raise ReceiptError('入库库位未启用', field_name='putaway_location_id',
                               rule='RC_LOCATION_INVALID')

    def _require_vendor(self, header: Dict[str, Any]) -> None:
        """PO 来源过账校验供应商 vendor 关系（同 R-PO-8）。"""
        party_id = header.get('supplier_party_id')
        if _blank(party_id):
            raise ReceiptError('采购收货必须指定供应商',
                               field_name='supplier_party_id',
                               rule='RC_SUPPLIER_REQUIRED')
        try:
            rows = self.ds.query(
                "SELECT 1 FROM %s WHERE role = 'vendor' "
                "AND COALESCE(status, 'active') = 'active' "
                'AND (party1_id = ? OR party2_id = ?) LIMIT 1'
                % PARTY_RELATION_TABLE, [party_id, party_id])
        except Exception as e:  # noqa: BLE001 - 无关系表时 fail-open
            logger.warning('[receipt] 读取 vendor 关系失败（跳过校验）: %s', e)
            return
        if not rows:
            raise ReceiptError(
                '供应商 %s 无有效的 vendor 关系' % party_id,
                field_name='supplier_party_id',
                rule='RC_SUPPLIER_RELATION_MISSING')

    # ------------------------------------------------------------------ 容差
    def _tolerance_ratio(self) -> Decimal:
        """`receipt_over_tolerance_percent`（百分数）→ 倍数（5 → 0.05）。"""
        percent = None
        try:
            rows = self.ds.query(
                'SELECT id, default_value FROM %s WHERE code = ? AND status = ?'
                % PARAM_TABLE, [TOLERANCE_PARAM, 'active'])
            if rows:
                percent = rows[0].get('default_value')
                values = self.ds.query(
                    'SELECT value FROM %s WHERE control_parameter_id = ? '
                    "AND status = 'active' ORDER BY id DESC LIMIT 1"
                    % PARAM_VALUE_TABLE, [rows[0]['id']])
                if values and not _blank(values[0].get('value')):
                    percent = values[0]['value']
        except Exception as e:  # noqa: BLE001 - 单测库无参数表
            logger.debug('[receipt] 读取超收容差失败，按 0 处理: %s', e)
        try:
            return _dec(percent or 0) / Decimal('100')
        except ReceiptError:
            return Decimal('0')

    # ------------------------------------------------------------------ 默认值
    def _apply_header_defaults(self, header: Dict[str, Any],
                               order: Dict[str, Any]) -> Dict[str, Any]:
        header = dict(header)
        header['source_doc_type'] = SOURCE_PURCHASE_ORDER
        for key, source in (('org_id', 'org_id'),
                            ('purchase_org_id', 'purchase_org_id'),
                            ('supplier_party_id', 'supplier_party_id'),
                            ('project_id', 'project_id'),
                            ('deliver_to_location_id', 'deliver_to_location_id')):
            if _blank(header.get(key)) and not _blank(order.get(source)):
                header[key] = order[source]
        if _blank(header.get('org_id')):
            raise ReceiptError('无法推导收货方法人（org_id）',
                               field_name='org_id', rule='RC_ORG_REQUIRED')
        # TBD-10：PO 法人快照非空时，收货组织必须与之一致；快照为空跳过校验
        purchase_legal_entity_id = order.get('purchase_legal_entity_id')
        if not _blank(purchase_legal_entity_id) \
                and str(header['org_id']) != str(purchase_legal_entity_id):
            raise ReceiptError(
                '收货组织 %s 与采购订单法人 %s 不一致'
                % (header['org_id'], purchase_legal_entity_id),
                field_name='org_id', rule='RC_LEGAL_ENTITY_MISMATCH')
        # TBD-6：PO 来源收货库存组织 = 采购组织（须具备 inventory 职能），否则留空
        if _blank(header.get('inventory_org_id')):
            header['inventory_org_id'] = self._inventory_org_from_purchase(order)
        self._validate_inventory_org(header)
        # TBD-7：收货库位所属组织（org_id 非空时）须等于收货库存组织
        self._validate_location_org(header)
        return header

    def _inventory_org_from_purchase(self, order: Dict[str, Any]) -> Optional[Any]:
        """采购订单来源的收货库存组织：`purchase_org_id` 具 inventory 职能才取。"""
        purchase_org_id = order.get('purchase_org_id')
        if _blank(purchase_org_id):
            return None
        try:
            if self._inventory_guard()._org_has_function(
                    purchase_org_id, FUNCTION_INVENTORY):
                return purchase_org_id
        except Exception as e:  # noqa: BLE001 - 旧环境 / 替身缺职能表
            logger.debug('[receipt] 读取采购组织 %s 职能失败，留空库存组织: %s',
                         purchase_org_id, e)
        return None

    def _inventory_guard(self):
        """复用调拨守卫的组织读取 / 上溯口径（不重写法人与职能解析）。"""
        from meta.services.transfer_order_guard_service import (
            TransferOrderGuardService)
        return TransferOrderGuardService(self.ds)

    def _validate_inventory_org(self, header: Dict[str, Any]) -> None:
        """TBD-6：收货库存组织非空时校验（存在且启用 / 库存职能 / 法人一致）。"""
        inventory_org_id = header.get('inventory_org_id')
        if _blank(inventory_org_id):
            return
        guard = self._inventory_guard()
        try:
            org = guard._load_org(inventory_org_id)
        except Exception as e:  # noqa: BLE001 - 旧环境 / 替身缺组织表
            logger.debug('[receipt] 读取组织 %s 失败，跳过库存组织校验: %s',
                         inventory_org_id, e)
            return
        status = str((org or {}).get('status') or '').strip().lower()
        if org is None or (status and status != 'active'):
            raise ReceiptError(
                '收货库存组织 %s 不存在或未启用' % inventory_org_id,
                field_name='inventory_org_id', rule='RC_INVENTORY_ORG_INVALID')
        if not guard._org_has_function(inventory_org_id, FUNCTION_INVENTORY):
            raise ReceiptError(
                '收货库存组织 %s 不具备库存职能' % inventory_org_id,
                field_name='inventory_org_id',
                rule='RC_INVENTORY_ORG_NOT_INVENTORY')
        legal_entity_id = guard._resolve_org_legal_entity(inventory_org_id)
        if _blank(legal_entity_id) \
                or str(legal_entity_id) != str(header.get('org_id')):
            raise ReceiptError(
                '收货库存组织 %s 所属法人 %s 与收货单法人 %s 不一致'
                % (inventory_org_id, legal_entity_id, header.get('org_id')),
                field_name='inventory_org_id',
                rule='RC_INVENTORY_ORG_LEGAL_MISMATCH')

    def _validate_location_org(self, header: Dict[str, Any]) -> None:
        """TBD-7：收货库位 `locations.org_id` 非空时须等于收货库存组织。

        库存组织为空时回退收货法人 `org_id`；库位未归属（NULL）或旧库缺列放行。
        """
        location_id = header.get('deliver_to_location_id')
        if _blank(location_id):
            return
        inventory_org_id = header.get('inventory_org_id')
        if _blank(inventory_org_id):
            inventory_org_id = header.get('org_id')
        if _blank(inventory_org_id):
            return
        try:
            rows = self.ds.query(
                'SELECT id, org_id FROM locations WHERE id = ?', [location_id])
        except Exception as e:  # noqa: BLE001 - 旧库缺 org_id 列不阻断
            logger.debug('[receipt] 读取库位 %s 归属失败，跳过校验: %s',
                         location_id, e)
            return
        if not rows:
            return
        location_org = rows[0].get('org_id')
        if _blank(location_org):
            return
        if str(location_org) != str(inventory_org_id):
            raise ReceiptError(
                '收货库位 %s 所属组织 %s 与收货库存组织 %s 不一致'
                % (location_id, location_org, inventory_org_id),
                field_name='deliver_to_location_id',
                rule='RC_LOCATION_ORG_MISMATCH')

    # ------------------------------------------------------------------ 持久化
    def _insert_header(self, row: Dict[str, Any]) -> int:
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            HEADER_TABLE, ', '.join(columns), ', '.join(['?'] * len(columns)))
        cursor = self.ds.execute(sql, [row[c] for c in columns])
        return int(getattr(cursor, 'lastrowid', 0) or 0)

    def _insert_line(self, receipt_id: Any, item: Dict[str, Any], now: str) -> int:
        cursor = self.ds.execute(
            'INSERT INTO %s (receipt_id, line_no, schedule_id, source_line_id, '
            'order_id, order_line_id, item_id, uom_id, qty_received, qty_rejected, '
            'rejection_reason_code, rejection_disposition, lot_no, serial_no, '
            'putaway_location_id, status, reversal_of_line_id, created_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            % LINE_TABLE,
            [receipt_id, item.get('line_no'), item.get('schedule_id'),
             item.get('source_line_id'), item.get('order_id'),
             item.get('order_line_id'), item.get('item_id'), item.get('uom_id'),
             float(item.get('qty_received') or 0),
             float(item.get('qty_rejected') or 0),
             item.get('rejection_reason_code'), item.get('rejection_disposition'),
             item.get('lot_no'), item.get('serial_no'),
             item.get('putaway_location_id'), item.get('status') or STATUS_DRAFT,
             item.get('reversal_of_line_id'), now, now])
        return int(getattr(cursor, 'lastrowid', 0) or 0)

    def _normalized_payload(self, checked: Dict[str, Any],
                            for_update: bool = False) -> Dict[str, Any]:
        line = checked['line']
        order_line = checked['order_line']
        values = {
            'schedule_id': checked['schedule']['id'],
            'order_id': checked['schedule']['order_id'],
            'order_line_id': order_line['id'],
            'item_id': order_line.get('item_id'),
            'uom_id': order_line.get('uom_id'),
            'qty_received': float(line.get('qty_received')),
            'qty_rejected': float(line.get('qty_rejected') or 0),
            'rejection_reason_code': line.get('rejection_reason_code'),
            'rejection_disposition': line.get('rejection_disposition'),
            'lot_no': line.get('lot_no'),
            'serial_no': line.get('serial_no'),
            'putaway_location_id': line.get('putaway_location_id'),
        }
        return values

    def _normalized_transfer_payload(self, checked: Dict[str, Any],
                                     for_update: bool = False) -> Dict[str, Any]:
        """TO 来源行归一化（spec §7.2：schedule_id / order_id 置空）。"""
        line = checked['line']
        source_line = checked['transfer_line']
        return {
            'schedule_id': None,
            'source_line_id': source_line['id'],
            'order_id': None,
            'order_line_id': None,
            'item_id': source_line.get('item_id'),
            'uom_id': source_line.get('uom_id'),
            'qty_received': float(line.get('qty_received')),
            'qty_rejected': float(line.get('qty_rejected') or 0),
            'rejection_reason_code': line.get('rejection_reason_code'),
            'rejection_disposition': line.get('rejection_disposition'),
            'lot_no': line.get('lot_no'),
            'serial_no': line.get('serial_no'),
            'putaway_location_id': line.get('putaway_location_id'),
        }

    def _normalized_work_order_payload(self, checked: Dict[str, Any]) -> Dict[str, Any]:
        """完工行归一化：schedule / order 字段置空，成品与数量取行内值。"""
        line = checked['line']
        return {
            'schedule_id': None,
            'source_line_id': None,
            'order_id': None,
            'order_line_id': None,
            'item_id': line.get('item_id'),
            'uom_id': line.get('uom_id'),
            'qty_received': float(line.get('qty_received')),
            'qty_rejected': float(line.get('qty_rejected') or 0),
            'rejection_reason_code': line.get('rejection_reason_code'),
            'rejection_disposition': line.get('rejection_disposition'),
            'lot_no': line.get('lot_no'),
            'serial_no': line.get('serial_no'),
            'putaway_location_id': line.get('putaway_location_id'),
        }

    # ------------------------------------------------------------------ 读取
    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(order_id):
            return None
        rows = self.ds.query(
            'SELECT id, order_no, org_id, purchase_org_id, '
            'purchase_legal_entity_id, supplier_party_id, '
            'project_id, deliver_to_location_id FROM %s WHERE id = ?' % ORDER_TABLE,
            [order_id])
        return rows[0] if rows else None

    def _load_order_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(line_id):
            return None
        rows = self.ds.query(
            'SELECT id, order_id, item_id, uom_id FROM %s WHERE id = ?'
            % ORDER_LINE_TABLE, [line_id])
        return rows[0] if rows else None

    def _load_transfer_order(self, transfer_order_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(transfer_order_id):
            return None
        rows = self.ds.query(
            'SELECT id, transfer_order_no, status, legal_entity_id, '
            'from_org_id, to_org_id, to_location_id '
            'FROM transfer_orders WHERE id = ?', [transfer_order_id])
        return rows[0] if rows else None

    def _load_work_order(self, work_order_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(work_order_id):
            return None
        rows = self.ds.query(
            'SELECT id, work_order_no, order_type, status '
            'FROM work_orders WHERE id = ?', [work_order_id])
        return rows[0] if rows else None

    def _load_transfer_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(line_id):
            return None
        rows = self.ds.query(
            'SELECT id, transfer_order_id, line_no, item_id, uom_id, qty, '
            'qty_shipped, qty_received, status '
            'FROM transfer_order_lines WHERE id = ?', [line_id])
        return rows[0] if rows else None

    def _transfer_open_lines(self, transfer_order_id: Any,
                             line_ids: Optional[List[Any]] = None,
                             ) -> List[Any]:
        """发运余量 > 0 的调拨行（可限定 line_ids），返回 [(row, balance)]。"""
        rows = self.ds.query(
            'SELECT id, line_no, item_id, uom_id, qty, qty_shipped, '
            'qty_received, status FROM transfer_order_lines '
            'WHERE transfer_order_id = ? ORDER BY line_no, id',
            [transfer_order_id])
        wanted = {str(x) for x in line_ids} if line_ids else None
        result = []
        for row in rows:
            if str(row.get('status') or '').strip().lower() != 'open':
                continue
            if wanted is not None and str(row['id']) not in wanted:
                continue
            balance = _q4(_dec(row.get('qty_shipped') or 0)
                          - _dec(row.get('qty_received') or 0))
            if balance > 0:
                result.append((row, balance))
        return result

    def _load_schedule(self, schedule_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(schedule_id):
            return None
        rows = self.ds.query(
            'SELECT id, order_id, line_id, schedule_kind, promised_qty, status, '
            'completion_source, completion_prev_status, '
            'COALESCE(received_qty, 0) AS received_qty, '
            'COALESCE(rejected_qty, 0) AS rejected_qty '
            'FROM %s WHERE id = ?' % SCHEDULE_TABLE, [schedule_id])
        return rows[0] if rows else None

    def _load_schedule_context(self, line: Dict[str, Any]) -> Dict[str, Any]:
        schedule = self._load_schedule(line.get('schedule_id'))
        net = _q4(_dec(line.get('qty_received') or 0)
                  - _dec(line.get('qty_rejected') or 0))
        return {'line': line, 'schedule': schedule, 'net': net}

    def _require_header(self, receipt_id: Any) -> Dict[str, Any]:
        if _blank(receipt_id):
            raise ReceiptError('收货单 ID 不能为空', field_name='id',
                               rule='RC_NOT_FOUND')
        rows = self.ds.query(
            'SELECT id, receipt_no, document_type_id, receipt_date, '
            'actual_arrival_date, source_doc_type, source_doc_id, source_doc_no, '
            'supplier_party_id, supplier_delivery_no, org_id, purchase_org_id, '
            'inventory_org_id, deliver_to_location_id, project_id, received_by, '
            'status, reversal_of_receipt_id FROM %s WHERE id = ?' % HEADER_TABLE,
            [receipt_id])
        if not rows:
            raise ReceiptError('收货单不存在', field_name='id',
                               rule='RC_NOT_FOUND')
        return rows[0]

    def _load_lines(self, receipt_id: Any,
                    status: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = ('SELECT id, receipt_id, line_no, schedule_id, source_line_id, '
               'order_id, order_line_id, item_id, uom_id, qty_received, '
               'qty_rejected, rejection_reason_code, rejection_disposition, '
               'lot_no, serial_no, putaway_location_id, status, '
               'reversal_of_line_id FROM %s WHERE receipt_id = ?'
               % LINE_TABLE)
        params: List[Any] = [receipt_id]
        if status:
            sql += ' AND status = ?'
            params.append(status)
        return self.ds.query(sql + ' ORDER BY line_no, id', params)

    def _require_line(self, line_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT id, receipt_id, line_no, schedule_id, source_line_id, '
            'order_id, order_line_id, item_id, uom_id, qty_received, qty_rejected, '
            'rejection_reason_code, rejection_disposition, lot_no, serial_no, '
            'putaway_location_id, status, reversal_of_line_id FROM %s WHERE id = ?'
            % LINE_TABLE, [line_id])
        if not rows:
            raise ReceiptError('收货行不存在', field_name='id', rule='RC_NOT_FOUND')
        return rows[0]

    def _reversal_exists(self, receipt_id: Any) -> bool:
        rows = self.ds.query(
            'SELECT 1 FROM %s WHERE reversal_of_receipt_id = ? '
            'AND status <> ? LIMIT 1' % HEADER_TABLE,
            [receipt_id, STATUS_CANCELLED])
        return bool(rows)
