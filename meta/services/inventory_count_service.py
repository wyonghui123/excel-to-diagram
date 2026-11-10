# -*- coding: utf-8 -*-
"""库存盘点服务 —— INV-4 盘点单快照 / 实盘录入 / 差异过账。

依据:
  .trae/specs/excel-to-diagram/define-inventory-adjustment/spec.md
    FR-004 盘点单与账面快照 / FR-005 盘点差异计算与过账
    FR-006 容差与审批 / FR-007 盘点冻结（posting block）
    FR-008 单据生命周期 / §9.3.3 服务设计

口径:
  ① 快照只由 start 生成：按 org_id（+ 可选 location_id）抓取 qty_on_hand <> 0
     的余额行冻结 snapshot_qty；已生成的快照行不得删除（只能录入实盘数）。
  ② submit 固化 variance_qty = counted_qty - snapshot_qty，超容差判定由 BO
     inventory_count_line 的 constraint 规则（combine_mode=all：率键 + 绝对值键
     同时超限）执行；单据头容差作为实例值经 overrides 传入。超容差行
     variance_reason 必填，全部容差内且参数开启时直接 approved。
  ③ post 在单事务内生成一张 count_difference 调整单 → 调用
     InventoryPostingService 落账 → 回写盘点单 posted；差异为 0 禁止过账。
  ④ 盘点差异分录 source_doc_type='inventory_count'，source_line_id 指向盘点行，
     bypass_posting_block=True 豁免自身冻结；非可用桶与冻结批次显式放行。
  ⑤ cancel 仅解除冻结，不删除快照行；posted 盘点单不可取消。
"""

import logging
from dataclasses import replace
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from meta.core.rule_constraint_evaluator import evaluate_constraint_rule
from meta.core.rule_metrics import MetricSession
from meta.services.control_parameter_service import ControlParameterResolver
from meta.services.inventory_adjustment_service import (
    ADJ_LINE_TABLE, ADJ_TABLE, TYPE_COUNT_DIFFERENCE,
)
from meta.services.inventory_document_sequence import next_document_no
from meta.services.inventory_guard_service import (
    INV_POSTING_DISABLED, InventoryError, InventoryGuardService,
)
from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.rule_hold_service import RuleHoldService

logger = logging.getLogger(__name__)

CNT_TABLE = 'inventory_counts'
CNT_LINE_TABLE = 'inventory_count_lines'
BAL_TABLE = 'inventory_balances'
ITEM_TABLE = 'items'

COUNT_TYPE_PHYSICAL = 'physical'
COUNT_TYPE_CYCLE = 'cycle'
COUNT_TYPES = (COUNT_TYPE_PHYSICAL, COUNT_TYPE_CYCLE)

STATUS_DRAFT = 'draft'
STATUS_COUNTING = 'counting'
STATUS_SUBMITTED = 'submitted'
STATUS_APPROVED = 'approved'
STATUS_POSTED = 'posted'
STATUS_CANCELLED = 'cancelled'

PARAM_AUTO_APPROVE_IN_TOLERANCE = 'inventory_count_auto_approve_in_tolerance'
PARAM_DEFAULT_TOLERANCE_QTY_PCT = 'inventory_count_default_tolerance_qty_pct'
PARAM_TOLERANCE_QTY_ABS = 'inventory_count_tolerance_qty_abs'
PARAM_POSTING_BLOCK_DEFAULT = 'inventory_count_posting_block_default'

#: 容差判定的事实源（BO yaml）；服务只消费，不在代码里重写口径
CNT_LINE_OBJECT = 'inventory_count_line'
TOLERANCE_RULE_ID = 'inventory_count_line_tolerance'
METRIC_DEVIATION_RATE = 'deviation_rate'

#: 超容差行挂起代码（holds.code）；holds 是挂起状态的唯一事实源
HOLD_CODE_OVER_TOLERANCE = 'INV_COUNT_TOLERANCE_EXCEEDED'

INV_COUNT_NOT_FOUND = 'INV_COUNT_NOT_FOUND'
INV_COUNT_TYPE_INVALID = 'INV_COUNT_TYPE_INVALID'
INV_COUNT_STATE_INVALID = 'INV_COUNT_STATE_INVALID'
INV_COUNT_INCOMPLETE = 'INV_COUNT_INCOMPLETE'
INV_COUNT_REASON_REQUIRED = 'INV_COUNT_REASON_REQUIRED'
INV_COUNT_NO_DIFF = 'INV_COUNT_NO_DIFF'
INV_COUNT_LINE_INVALID = 'INV_COUNT_LINE_INVALID'
INV_COUNT_LINE_LOCKED = 'INV_COUNT_LINE_LOCKED'
INV_DOC_POSTED_LOCKED = 'INV_DOC_POSTED_LOCKED'

_CNT_SEQ_PATTERN = 'CNT-{DATE:yyyymm}-{SEQ:6}'
_ADJ_SEQ_PATTERN = 'ADJ-{DATE:yyyymm}-{SEQ:6}'
_EPS = 1e-9


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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'y')


def _user_name(user_info: Optional[Dict[str, Any]]) -> Optional[str]:
    if not user_info:
        return None
    return (user_info.get('display_name') or user_info.get('username')
            or user_info.get('name'))


def _tolerance_rule() -> Any:
    """取盘点行容差规则；BO yaml 是唯一事实源，缺失即配置错误（不代码兜底）。"""
    from meta.core.models import registry
    meta_object = registry.get(CNT_LINE_OBJECT)
    for rule in (getattr(meta_object, 'rules', None) or []):
        if getattr(rule, 'id', '') == TOLERANCE_RULE_ID:
            return rule
    raise RuntimeError(
        'BO %s 缺少规则 %s，容差判定无事实源' % (CNT_LINE_OBJECT, TOLERANCE_RULE_ID))


def _line_tolerance_rule(rule: Any, snapshot: float) -> Any:
    """快照为 0 的行裁掉 ``deviation_rate`` 键（公式除零）。

    此时 ``snapshot_qty × tolerance_qty_pct = 0``，原 max 口径只剩绝对值容差，
    只按 ``deviation_qty`` 判定与之等价。
    """
    if _float(snapshot) != 0:
        return rule
    keys = [key for key in (getattr(rule, 'keys', None) or [])
            if str(key.get('metric') or '') != METRIC_DEVIATION_RATE]
    return replace(rule, keys=keys)


class InventoryCountService:
    """盘点单动作服务：创建归一 / start / submit / approve / post / cancel + 行守卫。"""

    def __init__(self, data_source, guard: Optional[InventoryGuardService] = None,
                 posting: Optional[InventoryPostingService] = None):
        self.ds = data_source
        self.guard = guard or InventoryGuardService(data_source)
        self.posting = posting or InventoryPostingService(data_source,
                                                          guard=self.guard)
        self.params = ControlParameterResolver(data_source)
        self.holds = RuleHoldService(data_source)

    # ------------------------------------------------------------------
    # 创建归一（守卫拦截器调用）
    # ------------------------------------------------------------------
    def prepare_create(self, payload: Dict[str, Any],
                       user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = dict(payload or {})
        count_type = data.get('count_type') or COUNT_TYPE_PHYSICAL
        if count_type not in COUNT_TYPES:
            raise InventoryError(INV_COUNT_TYPE_INVALID,
                                 '未知的盘点类型: %s' % count_type,
                                 {'count_type': count_type})
        data['count_type'] = count_type
        data['status'] = STATUS_DRAFT
        data['snapshot_at'] = None
        data['generated_adjustment_id'] = None

        if _blank(data.get('posting_block')):
            data['posting_block'] = (
                1 if self._param_bool(PARAM_POSTING_BLOCK_DEFAULT, False,
                                      data.get('org_id')) else 0)
        else:
            data['posting_block'] = 1 if _truthy(data.get('posting_block')) else 0

        tolerance = self.resolve_tolerance(
            data.get('org_id'), data.get('tolerance_qty_pct'),
            data.get('tolerance_qty_abs'))
        data['tolerance_qty_pct'] = tolerance['qty_pct']
        data['tolerance_qty_abs'] = tolerance['qty_abs']

        data['count_no'] = next_document_no(
            self.ds, 'CNT', _today(), _CNT_SEQ_PATTERN)
        data['created_at'] = data.get('created_at') or _now()
        data['updated_at'] = _now()
        if _blank(data.get('created_by')):
            data['created_by'] = _user_name(user_info)
        return data

    def resolve_tolerance(self, org_id: Any, header_pct: Any = None,
                          header_abs: Any = None) -> Dict[str, Any]:
        """按「单据头 > 参数行 specificity_rank > def.default_value」解析容差（M6a-2）。

        单据头是实例层：创建时把解析结果写入抬头即成为快照，submit 只读抬头，
        不随参数配置后续变化。绝对值容差不在参数池（spec §11.2.1 M6a-2），
        抬头未填时取 0.0。``source`` 透出命中来源（header / value / default /
        missing），便于排查「这个容差值从哪来」。
        """
        if _blank(header_pct):
            info = self.params.explain(
                PARAM_DEFAULT_TOLERANCE_QTY_PCT, {'org_id': org_id})
            qty_pct = _float(info.get('value'), 0.0)
            pct_source = str((info.get('source') or {}).get('type') or 'missing')
        else:
            qty_pct = _float(header_pct)
            pct_source = 'header'
        if _blank(header_abs):
            qty_abs, abs_source = 0.0, 'instance_default'
        else:
            qty_abs, abs_source = _float(header_abs), 'header'
        return {
            'qty_pct': qty_pct,
            'qty_abs': qty_abs,
            'source': {'qty_pct': pct_source, 'qty_abs': abs_source},
        }

    # ------------------------------------------------------------------
    # 状态动作
    # ------------------------------------------------------------------
    def start(self, count_id: Any,
              user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        header = self._load_header(count_id)
        if header['status'] != STATUS_DRAFT:
            raise InventoryError(
                INV_COUNT_STATE_INVALID,
                '仅草稿盘点单可开始盘点，当前状态: %s' % header['status'],
                {'count_id': count_id, 'status': header['status']})

        sql = (
            'SELECT b.id, b.org_id, b.location_id, b.item_id, b.batch_id, '
            '       b.stock_status, b.qty_on_hand, i.base_uom '
            'FROM %s b LEFT JOIN %s i ON i.id = b.item_id '
            'WHERE b.org_id = ? AND b.qty_on_hand <> 0 ' % (BAL_TABLE, ITEM_TABLE)
        )
        params: List[Any] = [header['org_id']]
        if not _blank(header.get('location_id')):
            sql += 'AND b.location_id = ? '
            params.append(header['location_id'])
        sql += ('ORDER BY b.location_id, b.item_id, b.batch_id, '
                'b.stock_status')
        balances = self.ds.query(sql, params)

        now = _now()
        inserted = 0
        with self.ds.transaction():
            for line_no, row in enumerate(balances, start=1):
                uom_id = row.get('base_uom')
                if _blank(uom_id):
                    raise InventoryError(
                        INV_COUNT_LINE_INVALID,
                        '物料 %s 未维护基本单位，无法生成盘点行'
                        % row.get('item_id'),
                        {'item_id': row.get('item_id')})
                batch_id = row.get('batch_id')
                if _blank(batch_id) or int(batch_id) == 0:
                    batch_id = None
                self.ds.execute(
                    'INSERT INTO %s (count_id, line_no, item_id, location_id, '
                    'batch_id, uom_id, stock_status, snapshot_qty, counted_qty, '
                    'variance_qty, variance_reason, source_balance_id, remark, '
                    'created_at, updated_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, '
                    '?, ?)' % CNT_LINE_TABLE,
                    [header['id'], line_no, row.get('item_id'),
                     row.get('location_id'), batch_id, uom_id,
                     row.get('stock_status') or 'unrestricted',
                     _float(row.get('qty_on_hand')), row.get('id'), now, now])
                inserted += 1
            self.ds.execute(
                'UPDATE %s SET status = ?, snapshot_at = ?, updated_at = ? '
                'WHERE id = ?' % CNT_TABLE,
                [STATUS_COUNTING, now, now, header['id']])

        logger.info('[inventory-count] start id=%s no=%s lines=%s',
                    header['id'], header.get('count_no'), inserted)
        return {'count_id': header['id'], 'count_no': header.get('count_no'),
                'status': STATUS_COUNTING, 'lines': inserted}

    def submit(self, count_id: Any,
               user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        header = self._load_header(count_id)
        if header['status'] != STATUS_COUNTING:
            raise InventoryError(
                INV_COUNT_STATE_INVALID,
                '仅盘点中单据可提交，当前状态: %s' % header['status'],
                {'count_id': count_id, 'status': header['status']})
        lines = self._load_lines(count_id)
        if not lines:
            raise InventoryError(INV_COUNT_INCOMPLETE, '盘点单没有行，不能提交',
                                 {'count_id': count_id})

        missing = [int(line['line_no']) for line in lines
                   if line.get('counted_qty') is None]
        if missing:
            raise InventoryError(
                INV_COUNT_INCOMPLETE, '存在未录入实盘数量的盘点行',
                {'count_id': count_id, 'lines': missing})

        tol_pct = _float(header.get('tolerance_qty_pct'))
        tol_abs = _float(header.get('tolerance_qty_abs'))
        # 单据头容差是实例值：比例走参数 key（快照覆盖），绝对值不在参数池
        overrides = {PARAM_DEFAULT_TOLERANCE_QTY_PCT: tol_pct,
                     PARAM_TOLERANCE_QTY_ABS: tol_abs}
        dims = {'org_id': header.get('org_id')}
        rule = _tolerance_rule()
        over: List[int] = []
        no_reason: List[int] = []
        variances: Dict[Any, float] = {}
        held: Dict[Any, Dict[str, Any]] = {}
        for line in lines:
            snapshot = _float(line.get('snapshot_qty'))
            counted = _float(line.get('counted_qty'))
            variance = counted - snapshot
            variances[line['id']] = variance
            metrics = MetricSession(
                CNT_LINE_OBJECT, line['id'],
                {'counted_qty': counted, 'snapshot_qty': snapshot})
            decision = evaluate_constraint_rule(
                _line_tolerance_rule(rule, snapshot), metrics=metrics,
                dims=dims, resolver=self.params, overrides=overrides)
            if decision.matched:
                over.append(int(line['line_no']))
                held[line['id']] = line
                if _blank(line.get('variance_reason')):
                    no_reason.append(int(line['line_no']))

        if no_reason:
            raise InventoryError(
                INV_COUNT_REASON_REQUIRED, '超容差盘点行必须填写差异原因',
                {'count_id': count_id, 'lines': no_reason})

        auto_approve = self._param_bool(PARAM_AUTO_APPROVE_IN_TOLERANCE, True,
                                        header.get('org_id'))
        target = (STATUS_APPROVED if (auto_approve and not over)
                  else STATUS_SUBMITTED)
        now = _now()
        operator = _user_name(user_info)
        approved_by = operator if target == STATUS_APPROVED else None
        approved_at = now if target == STATUS_APPROVED else None

        with self.ds.transaction():
            for line in lines:
                self.ds.execute(
                    'UPDATE %s SET variance_qty = ?, updated_at = ? WHERE id = ?'
                    % CNT_LINE_TABLE,
                    [variances[line['id']], now, line['id']])
            # 可存不可过：超容差行挂起（holds 唯一事实源），其余行释放旧挂起
            for line in lines:
                if line['id'] in held:
                    self.holds.apply(
                        CNT_LINE_OBJECT, line['id'], TOLERANCE_RULE_ID,
                        code=HOLD_CODE_OVER_TOLERANCE,
                        reason=str(line.get('variance_reason') or '').strip(),
                        applied_by=operator)
                else:
                    self.holds.release(
                        CNT_LINE_OBJECT, line['id'],
                        rule_key=TOLERANCE_RULE_ID, released_by=operator)
            self.ds.execute(
                'UPDATE %s SET status = ?, approved_by = ?, approved_at = ?, '
                'updated_at = ? WHERE id = ?' % CNT_TABLE,
                [target, approved_by, approved_at, now, header['id']])

        logger.info('[inventory-count] submit id=%s no=%s -> %s over=%s',
                    header['id'], header.get('count_no'), target, len(over))
        return {'count_id': header['id'], 'count_no': header.get('count_no'),
                'status': target, 'over_tolerance_lines': over,
                'in_tolerance': not over}

    def approve(self, count_id: Any,
                user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        header = self._load_header(count_id)
        if header['status'] != STATUS_SUBMITTED:
            raise InventoryError(
                INV_COUNT_STATE_INVALID,
                '仅已提交盘点单可审批，当前状态: %s' % header['status'],
                {'count_id': count_id, 'status': header['status']})
        now = _now()
        operator = _user_name(user_info)
        with self.ds.transaction():
            # 超容差行在此刻释放（规则声明 release_action=inventory_count.approve；
            # 首版由本动作直接释放，通用 release_action 执行器仍延后）
            for line in self._load_lines(count_id):
                self.holds.release(
                    CNT_LINE_OBJECT, line['id'],
                    rule_key=TOLERANCE_RULE_ID, released_by=operator)
            self.ds.execute(
                'UPDATE %s SET status = ?, approved_by = ?, approved_at = ?, '
                'updated_at = ? WHERE id = ?' % CNT_TABLE,
                [STATUS_APPROVED, operator, now, now, header['id']])
        logger.info('[inventory-count] approve id=%s no=%s',
                    header['id'], header.get('count_no'))
        return {'count_id': header['id'], 'count_no': header.get('count_no'),
                'status': STATUS_APPROVED}

    def post(self, count_id: Any,
             user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        header = self._load_header(count_id)
        if header['status'] != STATUS_APPROVED:
            raise InventoryError(
                INV_COUNT_STATE_INVALID,
                '仅已审批盘点单可过账，当前状态: %s' % header['status'],
                {'count_id': count_id, 'status': header['status']})
        if not self.guard.posting_enabled():
            raise InventoryError(INV_POSTING_DISABLED,
                                 '库存过账开关已关闭，禁止过账',
                                 {'count_id': count_id})

        lines = self._load_lines(count_id)
        missing = [int(line['line_no']) for line in lines
                   if line.get('counted_qty') is None]
        if missing:
            raise InventoryError(
                INV_COUNT_INCOMPLETE, '存在未录入实盘数量的盘点行',
                {'count_id': count_id, 'lines': missing})

        diffs = []
        for line in lines:
            variance = (_float(line.get('counted_qty'))
                        - _float(line.get('snapshot_qty')))
            if abs(variance) <= _EPS:
                continue
            diffs.append((line, variance))
        if not diffs:
            raise InventoryError(INV_COUNT_NO_DIFF, '盘点差异为 0，无需过账',
                                 {'count_id': count_id})

        count_no = header.get('count_no')
        serial_ready = self._serial_ready()
        if serial_ready:
            self._precheck_serials(header['id'])
        user_name = _user_name(user_info)
        today = _today()
        now = _now()
        entries: List[Dict[str, Any]] = []

        with self.ds.transaction():
            adjustment_no = next_document_no(self.ds, 'ADJ', today,
                                             _ADJ_SEQ_PATTERN)
            cursor = self.ds.execute(
                'INSERT INTO %s (adjustment_no, adjustment_type, status, '
                'org_id, location_id, reason_code, reason_text, posting_date, '
                'source_count_id, created_by, created_at, posted_by, posted_at, '
                'updated_at) '
                'VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)'
                % ADJ_TABLE,
                [adjustment_no, TYPE_COUNT_DIFFERENCE, STATUS_POSTED,
                 header['org_id'], header.get('location_id'),
                 '盘点单 %s 差异' % count_no, today, header['id'],
                 user_name, now, user_name, now, now])
            adjustment_id = cursor.lastrowid

            for line_no, (line, variance) in enumerate(diffs, start=1):
                batch_id = line.get('batch_id')
                if _blank(batch_id) or int(batch_id) == 0:
                    batch_id = None
                stock_status = line.get('stock_status') or 'unrestricted'
                qty = abs(variance)
                if variance > 0:
                    from_status, to_status = None, stock_status
                    transaction_type, direction = 'COUNT_INCREASE', 'in'
                else:
                    from_status, to_status = stock_status, None
                    transaction_type, direction = 'COUNT_DECREASE', 'out'
                self.ds.execute(
                    'INSERT INTO %s (adjustment_id, line_no, item_id, '
                    'location_id, batch_id, uom_id, qty, from_stock_status, '
                    'to_stock_status, source_count_line_id, remark, '
                    'created_at, updated_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)'
                    % ADJ_LINE_TABLE,
                    [adjustment_id, line_no, line['item_id'],
                     line.get('location_id'), batch_id, line['uom_id'], qty,
                     from_status, to_status, line['id'], now, now])
                entries.append({
                    'transaction_date': today,
                    'org_id': header['org_id'],
                    'location_id': line.get('location_id'),
                    'item_id': line['item_id'],
                    'uom_id': line['uom_id'],
                    'qty': qty,
                    'batch_id': batch_id,
                    'stock_status': stock_status,
                    'direction': direction,
                    'transaction_type': transaction_type,
                    'source_line_id': str(line['id']),
                    'created_by': user_name,
                })

            result = self.posting.post(
                entries,
                {
                    'source_doc_type': 'inventory_count',
                    'source_doc_id': header['id'],
                    'source_doc_no': count_no,
                    'source_event_key': 'count:%s' % count_no,
                    'transaction_date': today,
                    'created_by': user_name,
                },
                allow_non_unrestricted=True,
                allow_blocked_batch=True,
                bypass_posting_block=True)
            if serial_ready:
                self._register_serials(header['id'])
            self.ds.execute(
                'UPDATE %s SET status = ?, posted_at = ?, '
                'generated_adjustment_id = ?, updated_at = ? WHERE id = ?'
                % CNT_TABLE,
                [STATUS_POSTED, now, adjustment_id, now, header['id']])

        logger.info(
            '[inventory-count] post id=%s no=%s adjustment=%s created=%s',
            header['id'], count_no, adjustment_no, result.get('created'))
        return {'count_id': header['id'], 'count_no': count_no,
                'status': STATUS_POSTED, 'adjustment_id': adjustment_id,
                'adjustment_no': adjustment_no,
                'created': result.get('created', 0)}

    def cancel(self, count_id: Any,
               user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        header = self._load_header(count_id)
        if header['status'] == STATUS_POSTED:
            raise InventoryError(
                INV_DOC_POSTED_LOCKED, '已过账盘点单不可取消',
                {'count_id': count_id, 'status': header['status']})
        if header['status'] not in (STATUS_DRAFT, STATUS_COUNTING,
                                    STATUS_SUBMITTED, STATUS_APPROVED):
            raise InventoryError(
                INV_COUNT_STATE_INVALID,
                '当前状态不可取消: %s' % header['status'],
                {'count_id': count_id, 'status': header['status']})
        with self.ds.transaction():
            if self._serial_ready():
                self.ds.execute(
                    'DELETE FROM document_serial_links '
                    "WHERE doc_type = 'inventory_count' AND doc_id = ?",
                    [header['id']])
            # 取消后挂起失去意义：释放 active holds（不删行，保留历史）
            for line in self._load_lines(count_id):
                self.holds.release(
                    CNT_LINE_OBJECT, line['id'],
                    rule_key=TOLERANCE_RULE_ID,
                    released_by=_user_name(user_info))
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % CNT_TABLE,
                [STATUS_CANCELLED, _now(), header['id']])
        logger.info('[inventory-count] cancel id=%s no=%s',
                    header['id'], header.get('count_no'))
        return {'count_id': header['id'], 'count_no': header.get('count_no'),
                'status': STATUS_CANCELLED}

    # ------------------------------------------------------------------
    # 守卫拦截器辅助
    # ------------------------------------------------------------------
    def assert_deletable(self, count_id: Any) -> Dict[str, Any]:
        header = self._load_header(count_id)
        if header['status'] != STATUS_DRAFT:
            code = (INV_DOC_POSTED_LOCKED if header['status'] == STATUS_POSTED
                    else INV_COUNT_STATE_INVALID)
            raise InventoryError(
                code, '仅草稿盘点单可删除，当前状态: %s' % header['status'],
                {'count_id': count_id, 'status': header['status']})
        return header

    def prepare_line_create(self, parent_id: Any, payload: Dict[str, Any],
                            user_info: Optional[Dict[str, Any]] = None
                            ) -> Dict[str, Any]:
        header = self._load_header(parent_id)
        if header['status'] != STATUS_COUNTING:
            raise InventoryError(
                INV_COUNT_STATE_INVALID,
                '仅盘点中单据可新增行，当前状态: %s' % header['status'],
                {'count_id': parent_id, 'status': header['status']})
        data = dict(payload or {})
        if _blank(data.get('item_id')):
            raise InventoryError(INV_COUNT_LINE_INVALID, '盘点行缺少物料',
                                 {'count_id': parent_id})
        counted = data.get('counted_qty')
        if counted is not None and not _blank(counted) and _float(counted) < 0:
            raise InventoryError(
                INV_COUNT_LINE_INVALID, '实盘数量不能为负',
                {'counted_qty': counted})

        data['count_id'] = header['id']
        data['snapshot_qty'] = 0
        data['source_balance_id'] = None
        data['variance_qty'] = None
        if _blank(data.get('line_no')):
            data['line_no'] = self._next_line_no(header['id'])
        data['stock_status'] = data.get('stock_status') or 'unrestricted'
        if _blank(data.get('location_id')):
            data['location_id'] = header.get('location_id')
        if _blank(data.get('location_id')):
            raise InventoryError(
                INV_COUNT_LINE_INVALID, '新增盘点行必须指定库位',
                {'count_id': parent_id})
        if _blank(data.get('uom_id')):
            data['uom_id'] = self._item_base_uom(data.get('item_id'))
        data['created_at'] = data.get('created_at') or _now()
        data['updated_at'] = _now()
        return data

    def prepare_line_update(self, parent_id: Any, line_id: Any,
                            payload: Dict[str, Any],
                            user_info: Optional[Dict[str, Any]] = None
                            ) -> Dict[str, Any]:
        header = self._load_header(parent_id)
        if header['status'] != STATUS_COUNTING:
            raise InventoryError(
                INV_COUNT_STATE_INVALID,
                '仅盘点中单据可编辑行，当前状态: %s' % header['status'],
                {'count_id': parent_id, 'status': header['status']})
        line = self._load_line(parent_id, line_id)
        if not line:
            raise InventoryError(
                INV_COUNT_LINE_INVALID, '盘点行 %s 不属于盘点单 %s'
                % (line_id, parent_id),
                {'count_id': parent_id, 'line_id': line_id})

        source = dict(payload or {})
        data: Dict[str, Any] = {'count_id': header['id']}
        if 'counted_qty' in source:
            counted = source.get('counted_qty')
            if counted is not None and not _blank(counted) and _float(counted) < 0:
                raise InventoryError(
                    INV_COUNT_LINE_INVALID, '实盘数量不能为负',
                    {'line_id': line_id, 'counted_qty': counted})
            data['counted_qty'] = counted
        if 'variance_reason' in source:
            data['variance_reason'] = source.get('variance_reason')
        if 'remark' in source:
            data['remark'] = source.get('remark')
        data['updated_at'] = _now()
        return data

    def assert_line_deletable(self, parent_id: Any,
                              line_id: Any) -> Dict[str, Any]:
        header = self._load_header(parent_id)
        if header['status'] != STATUS_COUNTING:
            raise InventoryError(
                INV_COUNT_STATE_INVALID,
                '仅盘点中单据可删除行，当前状态: %s' % header['status'],
                {'count_id': parent_id, 'status': header['status']})
        line = self._load_line(parent_id, line_id)
        if not line:
            raise InventoryError(
                INV_COUNT_LINE_INVALID, '盘点行 %s 不存在' % line_id,
                {'count_id': parent_id, 'line_id': line_id})
        if not _blank(line.get('source_balance_id')):
            raise InventoryError(
                INV_COUNT_LINE_LOCKED, '快照行由 start 生成，不可删除',
                {'count_id': parent_id, 'line_id': line_id})
        return line

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _load_header(self, count_id: Any) -> Dict[str, Any]:
        rows = self.ds.query('SELECT * FROM %s WHERE id = ?' % CNT_TABLE,
                             [count_id])
        if not rows:
            raise InventoryError(INV_COUNT_NOT_FOUND,
                                 '库存盘点单 %s 不存在' % count_id,
                                 {'count_id': count_id})
        return rows[0]

    def _serial_ready(self) -> bool:
        from meta.services.serial_number_service import serial_schema_ready
        return serial_schema_ready(self.ds)

    def _precheck_serials(self, count_id: Any) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService)
        try:
            SerialNumberService(self.ds).precheck_count(count_id)
        except SerialNumberError as error:
            raise InventoryError(
                error.rule or 'SERIAL_COUNT_SERIAL_REQUIRED', str(error),
                {'field_name': error.field_name or 'serial_no'})

    def _register_serials(self, count_id: Any) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService)
        try:
            SerialNumberService(self.ds).register_count(count_id)
        except SerialNumberError as error:
            raise InventoryError(
                error.rule or 'SERIAL_COUNT_REGISTER_FAILED', str(error),
                {'field_name': error.field_name or 'serial_no'})

    def _load_lines(self, count_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE count_id = ? ORDER BY line_no'
            % CNT_LINE_TABLE, [count_id])

    def _load_line(self, count_id: Any,
                   line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ? AND count_id = ?' % CNT_LINE_TABLE,
            [line_id, count_id])
        return rows[0] if rows else None

    def _next_line_no(self, count_id: Any) -> int:
        rows = self.ds.query(
            'SELECT MAX(line_no) AS m FROM %s WHERE count_id = ?'
            % CNT_LINE_TABLE, [count_id])
        current = int(rows[0].get('m') or 0) if rows else 0
        return current + 1

    def _item_base_uom(self, item_id: Any) -> Any:
        rows = self.ds.query('SELECT base_uom FROM %s WHERE id = ?' % ITEM_TABLE,
                             [item_id])
        if not rows or _blank(rows[0].get('base_uom')):
            raise InventoryError(INV_COUNT_LINE_INVALID,
                                 '物料 %s 不存在或未维护基本单位' % item_id,
                                 {'item_id': item_id})
        return rows[0].get('base_uom')

    def _param_bool(self, code: str, default: bool, org_id: Any) -> bool:
        value = self.params.resolve(code, {'org_id': org_id})
        if value is None:
            return default
        return bool(value)

    def _param_float(self, code: str, default: float, org_id: Any) -> float:
        value = self.params.resolve(code, {'org_id': org_id})
        if value is None:
            return default
        return _float(value, default)
