# -*- coding: utf-8 -*-
"""库存调整服务 —— INV-4 调整单 / 报废 / 状态变更 / 期初导入。

依据:
  .trae/specs/excel-to-diagram/define-inventory-adjustment/spec.md
    FR-001 调整单 / FR-002 数量调整与报废 / FR-003 状态变更
    FR-008 生命周期与红冲 / FR-009 批次冻结边界 / FR-010 幂等与追溯
    FR-013 期初导入入口

口径:
  ① 一张调整单只允许一个 adjustment_type；混合类型拆单。
  ② 数量变化只经 inventory_transactions 落账，余额由 InventoryPostingService 投影。
  ③ status_transfer 生成成对分录（OUT/IN），同一 transfer_group_id，总在手量不变。
  ④ count_difference 只能由盘点服务生成，手工创建返回 INV_ADJ_TYPE_FORBIDDEN。
  ⑤ opening 仅对持有 inventory_adjustment:inventory_adjustment_opening 的用户开放。
  ⑥ 红冲不修改原事务，只追加 REVERSAL 分录并回写原单 reversed。
  ⑦ 幂等键：adjustment:{adjustment_no} + {line_id}:{leg}；红冲 reversal:{原单号}。
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from meta.core.interceptors.permission_interceptor import PermissionDenied
from meta.services.control_parameter_service import ControlParameterResolver
from meta.services.inventory_document_sequence import next_document_no
from meta.services.inventory_guard_service import (
    ALL_STATUSES, INV_POSTING_DISABLED, INV_QTY_INVALID, InventoryError,
    InventoryGuardService,
)
from meta.services.inventory_posting_service import InventoryPostingService

logger = logging.getLogger(__name__)

ADJ_TABLE = 'inventory_adjustments'
ADJ_LINE_TABLE = 'inventory_adjustment_lines'
TX_TABLE = 'inventory_transactions'
CNT_TABLE = 'inventory_counts'

TYPE_QTY_INCREASE = 'qty_increase'
TYPE_QTY_DECREASE = 'qty_decrease'
TYPE_SCRAP = 'scrap'
TYPE_STATUS_TRANSFER = 'status_transfer'
TYPE_COUNT_DIFFERENCE = 'count_difference'
TYPE_OPENING = 'opening'

MANUAL_TYPES = (TYPE_QTY_INCREASE, TYPE_QTY_DECREASE, TYPE_SCRAP,
                TYPE_STATUS_TRANSFER, TYPE_OPENING)
ALL_TYPES = MANUAL_TYPES + (TYPE_COUNT_DIFFERENCE,)

STATUS_DRAFT = 'draft'
STATUS_RELEASED = 'released'
STATUS_POSTED = 'posted'
STATUS_REVERSED = 'reversed'
STATUS_CANCELLED = 'cancelled'

STATUS_LABELS = {
    STATUS_DRAFT: '草稿',
    STATUS_RELEASED: '已下达',
    STATUS_POSTED: '已过账',
    STATUS_REVERSED: '已红冲',
    STATUS_CANCELLED: '已取消',
}

PARAM_RELEASE_REQUIRED = 'inventory_adjustment_release_required'
OPENING_PERMISSION = 'inventory_adjustment:opening'

INV_ADJ_NOT_FOUND = 'INV_ADJ_NOT_FOUND'
INV_ADJ_TYPE_INVALID = 'INV_ADJ_TYPE_INVALID'
INV_ADJ_TYPE_FORBIDDEN = 'INV_ADJ_TYPE_FORBIDDEN'
INV_ADJ_NO_LINES = 'INV_ADJ_NO_LINES'
INV_ADJ_STATE_INVALID = 'INV_ADJ_STATE_INVALID'
INV_ADJ_RELEASE_REQUIRED = 'INV_ADJ_RELEASE_REQUIRED'
INV_ADJ_LINE_INVALID = 'INV_ADJ_LINE_INVALID'
INV_ADJ_STATUS_PAIR_INVALID = 'INV_ADJ_STATUS_PAIR_INVALID'
INV_ADJ_NO_TRANSACTIONS = 'INV_ADJ_NO_TRANSACTIONS'
INV_DOC_POSTED_LOCKED = 'INV_DOC_POSTED_LOCKED'
INV_REASON_REQUIRED = 'INV_REASON_REQUIRED'
INV_ALREADY_REVERSED = 'INV_ALREADY_REVERSED'
INV_PERMISSION_DENIED = 'INV_PERMISSION_DENIED'


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _today() -> str:
    return date.today().strftime('%Y-%m-%d')


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if _blank(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class InventoryAdjustmentService:
    """调整单动作服务：release / post / reverse / cancel + 创建归一。"""

    def __init__(self, data_source, guard: Optional[InventoryGuardService] = None,
                 posting: Optional[InventoryPostingService] = None):
        self.ds = data_source
        self.guard = guard or InventoryGuardService(data_source)
        self.posting = posting or InventoryPostingService(data_source,
                                                          guard=self.guard)
        self.params = ControlParameterResolver(data_source)

    # ------------------------------------------------------------------
    # 创建归一（守卫拦截器调用）
    # ------------------------------------------------------------------
    def prepare_create(self, payload: Dict[str, Any],
                       user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = dict(payload or {})
        adj_type = data.get('adjustment_type')
        if _blank(adj_type):
            raise InventoryError(INV_ADJ_TYPE_INVALID, '调整类型不能为空')
        if adj_type not in ALL_TYPES:
            raise InventoryError(INV_ADJ_TYPE_INVALID,
                                 '未知的调整类型: %s' % adj_type,
                                 {'adjustment_type': adj_type})
        if adj_type == TYPE_COUNT_DIFFERENCE:
            raise InventoryError(
                INV_ADJ_TYPE_FORBIDDEN,
                '盘点差异只能由盘点单过账生成，不能手工创建',
                {'adjustment_type': adj_type})
        if adj_type == TYPE_OPENING:
            _require_opening_permission(user_info)
        if adj_type == TYPE_SCRAP and _blank(data.get('reason_code')):
            raise InventoryError(INV_REASON_REQUIRED,
                                 '报废调整必须填写原因',
                                 {'adjustment_type': adj_type})

        data['status'] = STATUS_DRAFT
        data['posting_date'] = data.get('posting_date') or _today()
        data['adjustment_no'] = next_document_no(
            self.ds, 'ADJ', data['posting_date'], 'ADJ-{DATE:yyyymm}-{SEQ:6}')
        data.setdefault('created_at', _now())
        data['updated_at'] = _now()
        if _blank(data.get('created_by')):
            data['created_by'] = _user_name(user_info)
        return data

    # ------------------------------------------------------------------
    # 状态动作
    # ------------------------------------------------------------------
    def release(self, adjustment_id: Any,
                user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        header = self._load(adjustment_id)
        if header['status'] != STATUS_DRAFT:
            raise InventoryError(
                INV_ADJ_STATE_INVALID,
                '仅草稿调整单可下达，当前状态: %s'
                % STATUS_LABELS.get(header['status'], header['status']),
                {'adjustment_id': adjustment_id, 'status': header['status']})
        lines = self._load_lines(adjustment_id)
        self._validate_lines(header, lines)

        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % ADJ_TABLE,
                [STATUS_RELEASED, _now(), header['id']])
        logger.info('[inventory-adjustment] release id=%s no=%s',
                    header['id'], header['adjustment_no'])
        return {'adjustment_id': header['id'],
                'adjustment_no': header['adjustment_no'],
                'status': STATUS_RELEASED, 'lines': len(lines)}

    def post(self, adjustment_id: Any,
             bypass_posting_block: bool = False,
             user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        header = self._load(adjustment_id)
        status = header['status']
        if status == STATUS_POSTED:
            # FR-010：同一调整单重复 post 幂等返回 created=0，余额不变
            existing = self.ds.query(
                'SELECT id FROM %s WHERE source_event_key = ?' % TX_TABLE,
                ['adjustment:%s' % header['adjustment_no']])
            return {'adjustment_id': header['id'],
                    'adjustment_no': header['adjustment_no'],
                    'status': STATUS_POSTED,
                    'created': 0,
                    'existing': len(existing),
                    'transactions': [row['id'] for row in existing]}
        if status in (STATUS_REVERSED, STATUS_CANCELLED):
            raise InventoryError(
                INV_DOC_POSTED_LOCKED,
                '单据已红冲/取消，不可过账',
                {'adjustment_id': adjustment_id, 'status': status})
        require_release = self._param_bool(PARAM_RELEASE_REQUIRED, True,
                                           header.get('org_id'))
        if status == STATUS_DRAFT and require_release:
            raise InventoryError(
                INV_ADJ_RELEASE_REQUIRED,
                '调整单需先下达（release）才能过账',
                {'adjustment_id': adjustment_id})
        if status not in (STATUS_DRAFT, STATUS_RELEASED):
            raise InventoryError(
                INV_ADJ_STATE_INVALID, '当前状态不可过账: %s' % status,
                {'adjustment_id': adjustment_id, 'status': status})
        if not self.guard.posting_enabled():
            raise InventoryError(INV_POSTING_DISABLED,
                                 '库存过账开关已关闭，禁止过账')

        lines = self._load_lines(adjustment_id)
        self._validate_lines(header, lines)
        serial_ready = self._serial_ready()
        if serial_ready:
            self._precheck_serials(header['id'])
        entries = self._build_entries(header, lines, user_info)
        source = {
            'source_doc_type': 'inventory_adjustment',
            'source_doc_id': header['id'],
            'source_doc_no': header['adjustment_no'],
            'source_event_key': 'adjustment:%s' % header['adjustment_no'],
            'transaction_date': header.get('posting_date') or _today(),
            'created_by': _user_name(user_info),
            'remark': header.get('reason_text'),
        }

        with self.ds.transaction():
            result = self.posting.post(
                entries, source, allow_non_unrestricted=True,
                allow_blocked_batch=True,
                bypass_posting_block=bypass_posting_block)
            self.ds.execute(
                'UPDATE %s SET status = ?, posted_by = ?, posted_at = ?, '
                'updated_at = ? WHERE id = ?' % ADJ_TABLE,
                [STATUS_POSTED, _user_name(user_info), _now(), _now(),
                 header['id']])
            if serial_ready:
                self._register_serials(header['id'])

        logger.info(
            '[inventory-adjustment] post id=%s no=%s created=%s existing=%s',
            header['id'], header['adjustment_no'], result.get('created'),
            len(result.get('existing') or []))
        return {'adjustment_id': header['id'],
                'adjustment_no': header['adjustment_no'],
                'status': STATUS_POSTED,
                'created': result.get('created', 0),
                'existing': len(result.get('existing') or []),
                'transactions': result.get('transactions') or []}

    def reverse(self, adjustment_id: Any,
                user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """红冲：委托 ReversalOrchestrator（红字单由声明的创建器生成）。"""
        from meta.core.reversal_orchestrator import ReversalError, execute

        header = self._load(adjustment_id)
        if header['status'] == STATUS_REVERSED:
            raise InventoryError(INV_ALREADY_REVERSED, '调整单已红冲',
                                 {'adjustment_id': adjustment_id})
        if header['status'] != STATUS_POSTED:
            raise InventoryError(
                INV_ADJ_STATE_INVALID, '仅已过账调整单可红冲，当前状态: %s'
                % header['status'],
                {'adjustment_id': adjustment_id,
                 'status': header['status']})

        try:
            outcome = execute(
                self.ds, schema_id='inventory_adjustment',
                doc_id=header['id'],
                reason='红冲 %s' % header['adjustment_no'],
                user_info=user_info)
        except ReversalError as error:
            raise self._map_reversal_error(error, header) from error

        document = outcome.document or {}
        inventory = outcome.faces.get('inventory') or {}
        logger.info('[inventory-adjustment] reverse id=%s -> %s created=%s',
                    header['id'], document.get('no'),
                    inventory.get('created'))
        return {'adjustment_id': header['id'],
                'adjustment_no': header['adjustment_no'],
                'status': STATUS_REVERSED,
                'created': int(inventory.get('created') or 0),
                'reversal_adjustment_id': document.get('id'),
                'reversal_adjustment_no': document.get('no')}

    @staticmethod
    def _map_reversal_error(error, header: Dict[str, Any]) -> 'InventoryError':
        """平台错误码 → 调整单既有错误码（前端契约不变）。"""
        details = {'adjustment_id': header['id'], 'status': header['status']}
        if error.code == 'REVERSAL_STATE_INVALID':
            return InventoryError(INV_ADJ_STATE_INVALID, error.message, details)
        if error.code == 'REVERSAL_FACT_MISSING':
            return InventoryError(INV_ADJ_NO_TRANSACTIONS, error.message,
                                  details)
        return InventoryError(error.code, error.message, details)

    def create_reversal_document(self, adjustment_id: Any,
                                 user_info: Optional[Dict[str, Any]] = None
                                 ) -> Dict[str, Any]:
        """创建红字镜像调整单（幂等：已有 REVERSAL 事实则 replay）。

        供 ReversalOrchestrator 的 ``reversal.create_document`` 声明调用；
        必须在编排器事务内执行（行复制与单据头同事务）。
        """
        header = self._load(adjustment_id)
        result = {
            'id': None, 'no': None, 'replay': False,
            'event_key': self._original_event_key(header),
            'reversal_event_key': 'reversal:%s' % header['adjustment_no'],
            'created_by': _user_name(user_info),
        }
        if self._reversal_exists(header['adjustment_no']):
            result['replay'] = True
            return result

        lines = self._load_lines(adjustment_id)
        reversal_no = next_document_no(
            self.ds, 'ADJ', _today(), 'ADJ-{DATE:yyyymm}-{SEQ:6}')
        now = _now()
        cur = self.ds.execute(
            'INSERT INTO %s (adjustment_no, adjustment_type, status, '
            'org_id, location_id, reason_code, reason_text, '
            'posting_date, source_count_id, reversal_of_adjustment_id, '
            'created_by, created_at, posted_by, posted_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            % ADJ_TABLE,
            [reversal_no, header['adjustment_type'], STATUS_POSTED,
             header['org_id'], header.get('location_id'),
             header.get('reason_code'), '红冲 %s' % header['adjustment_no'],
             _today(), header.get('source_count_id'), header['id'],
             _user_name(user_info), now, _user_name(user_info), now, now])
        reversal_id = cur.lastrowid
        swap_status = header['adjustment_type'] == TYPE_STATUS_TRANSFER
        for line in lines:
            self._insert_line_from(reversal_id, line, swap_status=swap_status)
        result.update({'id': reversal_id, 'no': reversal_no})
        return result

    def cancel(self, adjustment_id: Any,
               user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        header = self._load(adjustment_id)
        if header['status'] not in (STATUS_DRAFT, STATUS_RELEASED):
            raise InventoryError(
                INV_DOC_POSTED_LOCKED,
                '仅草稿/已下达调整单可取消，当前状态: %s'
                % STATUS_LABELS.get(header['status'], header['status']),
                {'adjustment_id': adjustment_id,
                 'status': header['status']})
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % ADJ_TABLE,
                [STATUS_CANCELLED, _now(), header['id']])
        return {'adjustment_id': header['id'],
                'adjustment_no': header['adjustment_no'],
                'status': STATUS_CANCELLED}

    # ------------------------------------------------------------------
    # 守卫拦截器辅助
    # ------------------------------------------------------------------
    def assert_deletable(self, adjustment_id: Any) -> Dict[str, Any]:
        header = self._load(adjustment_id)
        if header['status'] != STATUS_DRAFT:
            raise InventoryError(
                INV_DOC_POSTED_LOCKED, '仅草稿调整单可删除',
                {'adjustment_id': adjustment_id,
                 'status': header['status']})
        return header

    def prepare_line_create(self, parent_id: Any,
                            payload: Dict[str, Any]) -> Dict[str, Any]:
        header = self._load(parent_id)
        if header['status'] != STATUS_DRAFT:
            raise InventoryError(
                INV_DOC_POSTED_LOCKED, '仅草稿调整单可新增行',
                {'adjustment_id': parent_id, 'status': header['status']})
        data = dict(payload or {})
        data['adjustment_id'] = header['id']
        data.setdefault('line_no', self._next_line_no(parent_id))
        data.setdefault('uom_id', self._item_base_uom(data.get('item_id')))
        self._normalize_line_statuses(header['adjustment_type'], data)
        data.setdefault('created_at', _now())
        data['updated_at'] = _now()
        return data

    def prepare_line_update(self, parent_id: Any, line_id: Any,
                            payload: Dict[str, Any]) -> Dict[str, Any]:
        header = self._load(parent_id)
        if header['status'] != STATUS_DRAFT:
            raise InventoryError(
                INV_DOC_POSTED_LOCKED, '仅草稿调整单可编辑行',
                {'adjustment_id': parent_id, 'status': header['status']})
        data = dict(payload or {})
        data['adjustment_id'] = header['id']
        row = self.ds.query(
            'SELECT * FROM %s WHERE id = ? AND adjustment_id = ?' % ADJ_LINE_TABLE,
            [line_id, parent_id])
        if not row:
            raise InventoryError(INV_ADJ_LINE_INVALID, '调整行不存在',
                                 {'line_id': line_id})
        merged = dict(row[0])
        merged.update(data)
        if _blank(merged.get('uom_id')):
            merged['uom_id'] = self._item_base_uom(merged.get('item_id'))
        self._normalize_line_statuses(header['adjustment_type'], merged)
        for key in ('line_no', 'adjustment_id', 'source_count_line_id'):
            data.pop(key, None)
        data['to_stock_status'] = merged.get('to_stock_status')
        data['from_stock_status'] = merged.get('from_stock_status')
        data['uom_id'] = merged.get('uom_id')
        data['updated_at'] = _now()
        return data

    def assert_line_deletable(self, parent_id: Any, line_id: Any) -> Dict[str, Any]:
        header = self._load(parent_id)
        if header['status'] != STATUS_DRAFT:
            raise InventoryError(INV_DOC_POSTED_LOCKED, '仅草稿调整单可删除行',
                                 {'adjustment_id': parent_id,
                                  'status': header['status']})
        return header

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _load(self, adjustment_id: Any) -> Dict[str, Any]:
        rows = self.ds.query('SELECT * FROM %s WHERE id = ?' % ADJ_TABLE,
                             [adjustment_id])
        if not rows:
            raise InventoryError(INV_ADJ_NOT_FOUND, '库存调整单 %s 不存在'
                                 % adjustment_id, {'adjustment_id': adjustment_id})
        return rows[0]

    def _load_lines(self, adjustment_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE adjustment_id = ? ORDER BY line_no'
            % ADJ_LINE_TABLE, [adjustment_id])

    def _validate_lines(self, header: Dict[str, Any],
                        lines: List[Dict[str, Any]]) -> None:
        if not lines:
            raise InventoryError(INV_ADJ_NO_LINES, '调整单没有行，不能下达/过账',
                                 {'adjustment_id': header.get('id')})
        adj_type = header.get('adjustment_type')
        if adj_type == TYPE_SCRAP and _blank(header.get('reason_code')):
            raise InventoryError(INV_REASON_REQUIRED, '报废调整必须填写原因',
                                 {'adjustment_id': header.get('id')})
        for line in lines:
            qty = _float(line.get('qty'))
            if qty <= 0:
                raise InventoryError(INV_QTY_INVALID, '调整行数量必须大于 0',
                                     {'line_id': line.get('id'), 'qty': qty})
            if _blank(line.get('item_id')) or _blank(line.get('uom_id')):
                raise InventoryError(
                    INV_ADJ_LINE_INVALID, '调整行缺少物料或单位',
                    {'line_id': line.get('id')})
            from_status = line.get('from_stock_status')
            to_status = line.get('to_stock_status')
            if adj_type in (TYPE_QTY_INCREASE, TYPE_OPENING):
                if not _blank(from_status) or _blank(to_status):
                    raise InventoryError(
                        INV_ADJ_STATUS_PAIR_INVALID,
                        '增加类调整行只允许 to_stock_status',
                        {'line_id': line.get('id')})
            elif adj_type in (TYPE_QTY_DECREASE, TYPE_SCRAP):
                if _blank(from_status) or not _blank(to_status):
                    raise InventoryError(
                        INV_ADJ_STATUS_PAIR_INVALID,
                        '减少类调整行只允许 from_stock_status',
                        {'line_id': line.get('id')})
            elif adj_type == TYPE_STATUS_TRANSFER:
                if _blank(from_status) or _blank(to_status):
                    raise InventoryError(
                        INV_ADJ_STATUS_PAIR_INVALID,
                        '状态变更行必须同时填写转出/转入状态',
                        {'line_id': line.get('id')})
                if from_status == to_status:
                    raise InventoryError(
                        INV_ADJ_STATUS_PAIR_INVALID,
                        '状态变更的转出与转入状态不能相同',
                        {'line_id': line.get('id')})
                if from_status not in ALL_STATUSES or to_status not in ALL_STATUSES:
                    raise InventoryError(
                        INV_ADJ_STATUS_PAIR_INVALID,
                        '库存状态取值非法', {'line_id': line.get('id')})
            elif adj_type == TYPE_COUNT_DIFFERENCE:
                if _blank(from_status) == _blank(to_status):
                    raise InventoryError(
                        INV_ADJ_STATUS_PAIR_INVALID,
                        '盘点差异行必须有且只有一个方向状态',
                        {'line_id': line.get('id')})
            if from_status and from_status not in ALL_STATUSES:
                raise InventoryError(INV_ADJ_STATUS_PAIR_INVALID,
                                     '库存状态取值非法',
                                     {'line_id': line.get('id')})
            if to_status and to_status not in ALL_STATUSES:
                raise InventoryError(INV_ADJ_STATUS_PAIR_INVALID,
                                     '库存状态取值非法',
                                     {'line_id': line.get('id')})

    def _normalize_line_statuses(self, adj_type: str,
                                 data: Dict[str, Any]) -> None:
        if _blank(data.get('item_id')):
            raise InventoryError(INV_ADJ_LINE_INVALID, '调整行缺少物料')
        if _float(data.get('qty')) <= 0:
            raise InventoryError(INV_QTY_INVALID, '调整行数量必须大于 0')
        if adj_type in (TYPE_QTY_INCREASE, TYPE_OPENING):
            data['from_stock_status'] = None
            data['to_stock_status'] = data.get('to_stock_status') or 'unrestricted'
        elif adj_type in (TYPE_QTY_DECREASE, TYPE_SCRAP):
            data['to_stock_status'] = None
            data['from_stock_status'] = data.get('from_stock_status') or 'unrestricted'
        elif adj_type == TYPE_STATUS_TRANSFER:
            if (_blank(data.get('from_stock_status'))
                    or _blank(data.get('to_stock_status'))):
                raise InventoryError(
                    INV_ADJ_STATUS_PAIR_INVALID,
                    '状态变更行必须同时填写转出/转入状态')
            if data['from_stock_status'] == data['to_stock_status']:
                raise InventoryError(
                    INV_ADJ_STATUS_PAIR_INVALID, '转出与转入状态不能相同')
        self._shared_status_check(data)

    def _shared_status_check(self, data: Dict[str, Any]) -> None:
        for key in ('from_stock_status', 'to_stock_status'):
            value = data.get(key)
            if value and value not in ALL_STATUSES:
                raise InventoryError(INV_ADJ_STATUS_PAIR_INVALID,
                                     '库存状态取值非法: %s' % value,
                                     {'field': key, 'value': value})

    def _serial_ready(self) -> bool:
        from meta.services.serial_number_service import serial_schema_ready
        return serial_schema_ready(self.ds)

    def _precheck_serials(self, adjustment_id: Any) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService)
        try:
            SerialNumberService(self.ds).precheck_adjustment(adjustment_id)
        except SerialNumberError as error:
            raise InventoryError(
                error.rule or 'SERIAL_ADJUST_COUNT_MISMATCH', str(error),
                {'field_name': error.field_name or 'serial_no'})

    def _register_serials(self, adjustment_id: Any) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService)
        try:
            SerialNumberService(self.ds).register_adjustment(adjustment_id)
        except SerialNumberError as error:
            raise InventoryError(
                error.rule or 'SERIAL_ADJUST_REGISTER_FAILED', str(error),
                {'field_name': error.field_name or 'serial_no'})

    def _build_entries(self, header: Dict[str, Any],
                       lines: List[Dict[str, Any]],
                       user_info: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        adj_type = header['adjustment_type']
        entries: List[Dict[str, Any]] = []
        for line in lines:
            base = self._line_entry(header, line, user_info)
            if adj_type == TYPE_QTY_INCREASE:
                base.update(transaction_type='ADJ_INCREASE', direction='in',
                            stock_status=line.get('to_stock_status')
                            or 'unrestricted',
                            source_line_id=str(line['id']))
            elif adj_type == TYPE_QTY_DECREASE:
                base.update(transaction_type='ADJ_DECREASE', direction='out',
                            stock_status=line.get('from_stock_status')
                            or 'unrestricted',
                            source_line_id=str(line['id']))
            elif adj_type == TYPE_SCRAP:
                base.update(transaction_type='SCRAP', direction='out',
                            stock_status=line.get('from_stock_status')
                            or 'unrestricted',
                            source_line_id=str(line['id']))
            elif adj_type == TYPE_OPENING:
                base.update(transaction_type='OPENING', direction='in',
                            stock_status=line.get('to_stock_status')
                            or 'unrestricted',
                            source_line_id=str(line['id']))
            elif adj_type == TYPE_COUNT_DIFFERENCE:
                if line.get('to_stock_status'):
                    base.update(transaction_type='COUNT_INCREASE',
                                direction='in',
                                stock_status=line['to_stock_status'],
                                source_line_id=str(line['id']))
                else:
                    base.update(transaction_type='COUNT_DECREASE',
                                direction='out',
                                stock_status=line['from_stock_status'],
                                source_line_id=str(line['id']))
            elif adj_type == TYPE_STATUS_TRANSFER:
                group = 'adj-%s-%s' % (header['adjustment_no'], line['id'])
                out_entry = dict(base)
                out_entry.update(
                    transaction_type='STATUS_TRANSFER_OUT', direction='out',
                    stock_status=line['from_stock_status'],
                    transfer_group_id=group,
                    source_line_id='%s:out' % line['id'])
                in_entry = dict(base)
                in_entry.update(
                    transaction_type='STATUS_TRANSFER_IN', direction='in',
                    stock_status=line['to_stock_status'],
                    transfer_group_id=group,
                    source_line_id='%s:in' % line['id'])
                entries.append(out_entry)
                entries.append(in_entry)
                continue
            else:
                raise InventoryError(INV_ADJ_TYPE_INVALID,
                                     '未知的调整类型: %s' % adj_type)
            entries.append(base)
        return entries

    def _line_entry(self, header: Dict[str, Any], line: Dict[str, Any],
                    user_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        location_id = line.get('location_id') or header.get('location_id')
        batch_id = line.get('batch_id')
        if _blank(batch_id) or int(batch_id) == 0:
            batch_id = None
        return {
            'transaction_date': header.get('posting_date') or _today(),
            'org_id': header['org_id'],
            'location_id': location_id,
            'item_id': line['item_id'],
            'uom_id': line['uom_id'],
            'qty': _float(line['qty']),
            'batch_id': batch_id,
            'created_by': _user_name(user_info),
            'remark': line.get('remark') or header.get('reason_text'),
        }

    def _original_event_key(self, header: Dict[str, Any]) -> str:
        count_id = header.get('source_count_id')
        if not _blank(count_id):
            rows = self.ds.query(
                'SELECT count_no FROM %s WHERE id = ?' % CNT_TABLE, [count_id])
            if rows:
                return 'count:%s' % rows[0]['count_no']
        return 'adjustment:%s' % header['adjustment_no']

    def _reversal_exists(self, adjustment_no: str) -> bool:
        try:
            rows = self.ds.query(
                'SELECT 1 FROM %s WHERE source_event_key = ? LIMIT 1' % TX_TABLE,
                ['reversal:%s' % adjustment_no])
        except Exception:
            return False
        return bool(rows)

    def _insert_line_from(self, adjustment_id: Any, line: Dict[str, Any],
                          swap_status: bool = False) -> None:
        from_status = line.get('from_stock_status')
        to_status = line.get('to_stock_status')
        # 红冲镜像：状态变更互换 from/to；数量方向由 REVERSAL 分录表达
        if swap_status:
            from_status, to_status = to_status, from_status
        self.ds.execute(
            'INSERT INTO %s (adjustment_id, line_no, item_id, location_id, '
            'batch_id, uom_id, qty, from_stock_status, to_stock_status, '
            'source_count_line_id, remark, created_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)' % ADJ_LINE_TABLE,
            [adjustment_id, line['line_no'], line['item_id'],
             line.get('location_id'), line.get('batch_id'), line['uom_id'],
             line['qty'], from_status, to_status,
             line.get('source_count_line_id'), line.get('remark'),
             _now(), _now()])

    def _next_line_no(self, adjustment_id: Any) -> int:
        rows = self.ds.query(
            'SELECT MAX(line_no) AS m FROM %s WHERE adjustment_id = ?'
            % ADJ_LINE_TABLE, [adjustment_id])
        current = int(rows[0].get('m') or 0) if rows else 0
        return current + 1

    def _item_base_uom(self, item_id: Any) -> Any:
        rows = self.ds.query('SELECT base_uom FROM items WHERE id = ?',
                             [item_id])
        if not rows:
            raise InventoryError(INV_ADJ_LINE_INVALID, '物料 %s 不存在' % item_id,
                                 {'item_id': item_id})
        return rows[0].get('base_uom')

    def _param_bool(self, code: str, default: bool, org_id: Any) -> bool:
        value = self.params.resolve(code, {'org_id': org_id})
        if value is None:
            return default
        return bool(value)


def _user_name(user_info: Optional[Dict[str, Any]]) -> Optional[str]:
    if not user_info:
        return None
    return (user_info.get('display_name') or user_info.get('username')
            or user_info.get('name'))


def _require_opening_permission(user_info: Optional[Dict[str, Any]]) -> None:
    if not user_info:
        raise PermissionDenied('缺少权限: %s' % OPENING_PERMISSION)
    if user_info.get('is_superuser') or user_info.get('is_admin'):
        return
    permissions = set(user_info.get('permissions') or [])
    if '*' in permissions or OPENING_PERMISSION in permissions:
        return
    roles = set(user_info.get('roles') or [])
    if 'admin' in roles or 'super_admin' in roles:
        return
    raise PermissionDenied('缺少权限: %s' % OPENING_PERMISSION)
