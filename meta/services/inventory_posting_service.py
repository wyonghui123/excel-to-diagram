# -*- coding: utf-8 -*-
"""库存过账服务 —— INV-1 事务账 + 余额投影的唯一写入口。

依据:
  .trae/specs/excel-to-diagram/define-inventory-model/spec.md
    FR-001 事务账 / FR-003 余额投影 / FR-008 幂等与反冲
    FR-012 重建与对账 / FR-007 在途派生

口径:
  ① inventory_transactions 只 INSERT；纠错走 REVERSAL 反冲，原分录不动。
  ② inventory_balances 是投影：同一键 UPSERT，qty_on_hand 按 base_qty 累加。
  ③ 单据动作与库存分录同事务（调用方已有的 transaction 内执行，嵌套 savepoint）。
  ④ 幂等键 = (source_event_key, source_line_id)；重复过账返回既有分录。
  ⑤ 一条原分录最多反冲一次（uq_inv_tx_reversal 部分唯一）。
  ⑥ 开关 inventory_posting_enabled=0 时 post() 不写账（过渡期行为）。
  ⑦ 在途不落表：由调拨行 qty_shipped - qty_received 派生。
"""

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from meta.services.inventory_guard_service import (
    INV_COUNT_BLOCKED, INV_POSTING_DISABLED, InventoryError,
    InventoryGuardService,
)

logger = logging.getLogger(__name__)

TYPES_TABLE = 'inventory_transaction_types'
TX_TABLE = 'inventory_transactions'
BAL_TABLE = 'inventory_balances'
SEQUENCE_CODE = 'INV'
SEQUENCE_TABLE = '_sequences'

TYPE_REVERSAL = 'REVERSAL'

_DATE_FMT = {
    'yyyy': '%Y',
    'yy': '%y',
    'yyyymm': '%Y%m',
    'yyyymmdd': '%Y%m%d',
    'mm': '%m',
}
_DATE_TOKEN_RE = re.compile(r'\{DATE:([a-z]+)\}')
_SEQ_TOKEN_RE = re.compile(r'\{SEQ:(\d+)\}')


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _day(value: Any) -> str:
    if _blank(value):
        return date.today().strftime('%Y-%m-%d')
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return str(value)[:10]


def _as_date(value: Any) -> date:
    text = _day(value)
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return date.today()


class InventoryPostingService:
    """库存过账。构造函数可注入 data_source 与守卫（单测替身）。"""

    def __init__(self, data_source, guard: Optional[InventoryGuardService] = None):
        self.ds = data_source
        self.guard = guard or InventoryGuardService(data_source)

    # ------------------------------------------------------------------
    # 过账
    # ------------------------------------------------------------------
    def post(self, entries: List[Dict[str, Any]],
             source: Dict[str, Any],
             allow_non_unrestricted: bool = False,
             ignore_switch: bool = False,
             allow_blocked_batch: bool = False,
             bypass_posting_block: bool = False) -> Dict[str, Any]:
        """写库存分录并更新余额。返回 created / existing / skipped。

        INV-4 扩展：
          · allow_blocked_batch：非可用桶出库豁免批次冻结（INV-4 服务显式开启）。
          · bypass_posting_block：盘点差异自身豁免盘点冻结。
        """
        if not entries:
            return {'created': 0, 'existing': [], 'transactions': [],
                    'skipped': False}
        if not ignore_switch and not self.guard.posting_enabled():
            logger.info('[inventory] 过账开关关闭，跳过 source=%s/%s',
                        source.get('source_doc_type'),
                        source.get('source_doc_id'))
            return {'created': 0, 'existing': [], 'transactions': [],
                    'skipped': True, 'reason': INV_POSTING_DISABLED}

        source_event_key = source.get('source_event_key')
        if _blank(source_event_key):
            raise InventoryError('INV_SOURCE_REQUIRED', '库存过账缺少来源事件键')
        doc_type = source.get('source_doc_type')
        doc_id = source.get('source_doc_id')
        if _blank(doc_type) or _blank(doc_id):
            raise InventoryError('INV_SOURCE_REQUIRED',
                                 '库存过账缺少来源单据类型或 ID')

        txn_date = _day(source.get('transaction_date'))
        created: List[Dict[str, Any]] = []
        existing: List[Dict[str, Any]] = []
        batch_group = source.get('transfer_group_id')

        for entry in entries:
            payload = dict(entry)
            payload.setdefault('source_event_key', source_event_key)
            payload.setdefault('transfer_group_id', batch_group)
            if _blank(payload.get('transaction_date')):
                payload['transaction_date'] = txn_date
            payload.setdefault('created_by', source.get('created_by'))
            if _blank(payload.get('source_line_id')):
                raise InventoryError(
                    'INV_SOURCE_REQUIRED', '库存过账缺少来源行 ID',
                    {'source_event_key': source_event_key, 'entry': entry})
            normalized = self.guard.normalize_entry(
                payload, allow_non_unrestricted=allow_non_unrestricted,
                allow_blocked_batch=allow_blocked_batch)
            if not bypass_posting_block and self._posting_block_active(
                    normalized.get('org_id'),
                    normalized.get('location_id')):
                raise InventoryError(
                    INV_COUNT_BLOCKED,
                    '库存组织 %s 库位 %s 正在盘点冻结，禁止过账'
                    % (normalized.get('org_id'),
                       normalized.get('location_id')),
                    {'org_id': normalized.get('org_id'),
                     'location_id': normalized.get('location_id')})

            hit = self._find_existing(source_event_key,
                                      normalized['source_line_id'])
            if hit:
                existing.append(hit)
                continue

            current = self._current_qty(normalized)
            self.guard.check_negative(normalized, current)

            txn = self._insert_transaction(
                normalized, doc_type, doc_id, source_event_key,
                payload.get('remark') or source.get('remark'))
            self._apply_balance(normalized)
            created.append(txn)

        logger.info(
            '[inventory] post source=%s:%s event=%s created=%s existing=%s',
            doc_type, doc_id, source_event_key, len(created), len(existing))
        return {'created': len(created), 'existing': existing,
                'transactions': created, 'skipped': False}

    # ------------------------------------------------------------------
    # 反冲
    # ------------------------------------------------------------------
    def reverse_by_source(self, original_event_key: str,
                          source: Dict[str, Any],
                          transaction_date: Any = None) -> Dict[str, Any]:
        """按原过账事件键反冲其全部未反冲分录。

        库存表未建（迁移未执行）时视为没有库存分录，直接空返回：保证
        `inventory_posting_enabled=0` 期间的历史单据红冲不被库存模型阻断。
        """
        if not self._tx_table_ready():
            logger.warning('[inventory] %s 不存在，反冲 %s 跳过',
                           TX_TABLE, original_event_key)
            return {'created': 0, 'existing': [], 'transactions': []}
        rows = self.ds.query(
            'SELECT id FROM %s WHERE source_event_key = ?' % TX_TABLE,
            [original_event_key])
        ids = [row['id'] for row in rows]
        if not ids:
            return {'created': 0, 'existing': [], 'transactions': []}
        return self.reverse(ids, source, transaction_date=transaction_date)

    def _tx_table_ready(self) -> bool:
        try:
            rows = self.ds.query(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                'AND name = ?', [TX_TABLE])
        except Exception:
            return False
        return bool(rows)

    def _posting_block_active(self, org_id: Any, location_id: Any) -> bool:
        """盘点冻结检查：同组织 +（盘点单库位为空 或 与分录库位相同）。"""
        if _blank(org_id):
            return False
        try:
            rows = self.ds.query(
                'SELECT id FROM inventory_counts WHERE org_id = ? '
                'AND posting_block = 1 '
                "AND status IN ('counting', 'submitted', 'approved') "
                'AND (location_id IS NULL OR location_id = ?) LIMIT 1',
                [org_id, location_id])
        except Exception:
            return False
        return bool(rows)

    def reverse(self, transaction_ids: Iterable[Any],
                source: Dict[str, Any],
                transaction_date: Any = None,
                allow_blocked_batch: bool = False,
                bypass_posting_block: bool = False) -> Dict[str, Any]:
        """对原分录生成 REVERSAL 分录；已反冲的跳过（幂等）。"""
        source_event_key = source.get('source_event_key')
        if _blank(source_event_key):
            raise InventoryError('INV_SOURCE_REQUIRED', '反冲缺少来源事件键')
        doc_type = source.get('source_doc_type')
        doc_id = source.get('source_doc_id')
        if _blank(doc_type) or _blank(doc_id):
            raise InventoryError('INV_SOURCE_REQUIRED',
                                 '反冲缺少来源单据类型或 ID')

        txn_date = _day(transaction_date or source.get('transaction_date'))
        reversal_type = self.guard.resolve_type(TYPE_REVERSAL)
        created: List[Dict[str, Any]] = []
        existing: List[Dict[str, Any]] = []

        for tx_id in transaction_ids:
            original = self._load_transaction(tx_id)
            if original is None:
                raise InventoryError('INV_TX_NOT_FOUND',
                                     '原库存分录 %s 不存在' % tx_id,
                                     {'transaction_id': tx_id})
            if original.get('reversal_of_transaction_id') not in (None, 0, ''):
                raise InventoryError('INV_REVERSAL_INVALID',
                                     '反冲分录不能再被反冲',
                                     {'transaction_id': tx_id})
            hit = self.ds.query(
                'SELECT id, transaction_no FROM %s '
                'WHERE reversal_of_transaction_id = ?' % TX_TABLE,
                [original['id']])
            if hit:
                existing.append(hit[0])
                continue

            direction = 'out' if original.get('direction') == 'in' else 'in'
            payload = {
                'transaction_type': TYPE_REVERSAL,
                'transaction_type_id': reversal_type['id'],
                'transaction_date': txn_date,
                'org_id': original.get('org_id'),
                'location_id': original.get('location_id'),
                'item_id': original.get('item_id'),
                'uom_id': original.get('uom_id'),
                'qty': original.get('qty'),
                'direction': direction,
                'batch_id': original.get('batch_id'),
                'stock_status': original.get('stock_status'),
                'source_line_id': original.get('source_line_id'),
                'source_event_key': source_event_key,
                'transfer_group_id': original.get('transfer_group_id'),
                'created_by': source.get('created_by'),
            }
            normalized = self.guard.normalize_entry(
                payload, allow_non_unrestricted=True,
                allow_blocked_batch=allow_blocked_batch)
            if not bypass_posting_block and self._posting_block_active(
                    normalized.get('org_id'),
                    normalized.get('location_id')):
                raise InventoryError(
                    INV_COUNT_BLOCKED,
                    '库存组织 %s 库位 %s 正在盘点冻结，禁止红冲'
                    % (normalized.get('org_id'),
                       normalized.get('location_id')),
                    {'org_id': normalized.get('org_id'),
                     'location_id': normalized.get('location_id')})
            normalized['base_qty'] = float(original.get('base_qty') or 0)
            if normalized['base_qty'] <= 0:
                raise InventoryError('INV_QTY_INVALID',
                                     '原分录 base_qty 非法',
                                     {'transaction_id': tx_id})

            self.guard.check_negative(normalized,
                                      self._current_qty(normalized))
            txn = self._insert_transaction(
                normalized, doc_type, doc_id, source_event_key,
                source.get('remark'), reversal_of=original['id'])
            self._apply_balance(normalized)
            created.append(txn)

        logger.info('[inventory] reverse event=%s created=%s existing=%s',
                    source_event_key, len(created), len(existing))
        return {'created': len(created), 'existing': existing,
                'transactions': created}

    # ------------------------------------------------------------------
    # 余额查询
    # ------------------------------------------------------------------
    def on_hand(self, org_id: Any, location_id: Any, item_id: Any,
                batch_id: Any = None,
                stock_status: str = 'unrestricted') -> float:
        rows = self.ds.query(
            'SELECT qty_on_hand FROM %s WHERE org_id = ? AND location_id = ? '
            'AND item_id = ? AND batch_id = ? AND stock_status = ?' % BAL_TABLE,
            [org_id, location_id, item_id,
             int(batch_id) if not _blank(batch_id) else 0, stock_status])
        return float(rows[0].get('qty_on_hand') or 0) if rows else 0.0

    def available_qty(self, org_id: Any, location_id: Any, item_id: Any,
                      batch_id: Any = None) -> float:
        rows = self.ds.query(
            'SELECT qty_on_hand, qty_reserved FROM %s WHERE org_id = ? '
            'AND location_id = ? AND item_id = ? AND batch_id = ? '
            "AND stock_status = 'unrestricted'" % BAL_TABLE,
            [org_id, location_id, item_id,
             int(batch_id) if not _blank(batch_id) else 0])
        if not rows:
            return 0.0
        return float(rows[0].get('qty_on_hand') or 0) - \
            float(rows[0].get('qty_reserved') or 0)

    def in_transit(self, org_id: Any = None,
                   item_id: Any = None) -> List[Dict[str, Any]]:
        """在途派生：按调出/调入组织与物料汇总 TO 行未收量。"""
        sql = (
            'SELECT h.from_org_id AS from_org_id, '
            '       h.to_org_id   AS to_org_id, '
            '       l.item_id     AS item_id, '
            '       COALESCE(SUM(CASE WHEN '
            '           COALESCE(l.qty_shipped, 0) - COALESCE(l.qty_received, 0) > 0 '
            '           THEN COALESCE(l.qty_shipped, 0) - COALESCE(l.qty_received, 0) '
            '           ELSE 0 END), 0) AS qty '
            'FROM transfer_order_lines l '
            'JOIN transfer_orders h ON h.id = l.transfer_order_id '
            "WHERE h.status NOT IN ('draft', 'cancelled') "
        )
        params: List[Any] = []
        if org_id is not None:
            sql += 'AND (h.from_org_id = ? OR h.to_org_id = ?) '
            params.extend([org_id, org_id])
        if item_id is not None:
            sql += 'AND l.item_id = ? '
            params.append(item_id)
        sql += 'GROUP BY h.from_org_id, h.to_org_id, l.item_id'
        rows = self.ds.query(sql, params)

        grouped: Dict[Any, Dict[str, Any]] = {}
        for row in rows:
            item = row.get('item_id')
            qty = float(row.get('qty') or 0)
            if qty <= 0:
                continue
            bucket = grouped.setdefault(item, {
                'item_id': item,
                'outbound': [], 'inbound': [],
            })
            if org_id is not None and row.get('from_org_id') == org_id:
                bucket['outbound'].append(
                    {'org_id': org_id, 'qty': qty})
            elif org_id is not None and row.get('to_org_id') == org_id:
                bucket['inbound'].append(
                    {'org_id': org_id, 'qty': qty})
            else:
                bucket['outbound'].append(
                    {'org_id': row.get('from_org_id'), 'qty': qty})
                bucket['inbound'].append(
                    {'org_id': row.get('to_org_id'), 'qty': qty})
        result = []
        for item, bucket in grouped.items():
            outbound = sum(x['qty'] for x in bucket['outbound'])
            inbound = sum(x['qty'] for x in bucket['inbound'])
            result.append({'item_id': item, 'outbound': outbound,
                           'inbound': inbound})
        return result

    # ------------------------------------------------------------------
    # 重建与对账
    # ------------------------------------------------------------------
    def _computed_totals(self, org_id: Any = None) -> Dict[tuple, float]:
        sql = (
            'SELECT org_id, location_id, item_id, '
            '       COALESCE(batch_id, 0) AS batch_id, stock_status, '
            "       SUM(CASE WHEN direction = 'in' THEN base_qty "
            '               ELSE -base_qty END) AS qty '
            'FROM %s ' % TX_TABLE
        )
        params: List[Any] = []
        if org_id is not None:
            sql += 'WHERE org_id = ? '
            params.append(org_id)
        sql += 'GROUP BY org_id, location_id, item_id, COALESCE(batch_id, 0), stock_status'
        totals: Dict[tuple, float] = {}
        for row in self.ds.query(sql, params):
            key = (row['org_id'], row['location_id'], row['item_id'],
                   row['batch_id'], row['stock_status'])
            totals[key] = float(row.get('qty') or 0)
        return totals

    def _current_totals(self, org_id: Any = None) -> Dict[tuple, float]:
        sql = 'SELECT org_id, location_id, item_id, batch_id, stock_status, qty_on_hand FROM %s' % BAL_TABLE
        params: List[Any] = []
        if org_id is not None:
            sql += ' WHERE org_id = ?'
            params.append(org_id)
        totals: Dict[tuple, float] = {}
        for row in self.ds.query(sql, params):
            key = (row['org_id'], row['location_id'], row['item_id'],
                   int(row.get('batch_id') or 0), row['stock_status'])
            totals[key] = float(row.get('qty_on_hand') or 0)
        return totals

    def diff_report(self, org_id: Any = None,
                    include_zero: bool = False) -> Dict[str, Any]:
        """账（分录合计）vs 余额差异报告；不修改任何数据。"""
        computed = self._computed_totals(org_id)
        current = self._current_totals(org_id)
        keys = set(computed) | set(current)
        rows: List[Dict[str, Any]] = []
        for key in sorted(keys):
            org, location, item, batch, status = key
            account_qty = computed.get(key, 0.0)
            balance_qty = current.get(key, 0.0)
            diff = account_qty - balance_qty
            if not include_zero and abs(diff) < 1e-9:
                continue
            rows.append({
                'org_id': org, 'location_id': location, 'item_id': item,
                'batch_id': batch, 'stock_status': status,
                'account_qty': round(account_qty, 6),
                'balance_qty': round(balance_qty, 6),
                'diff': round(diff, 6),
                'missing_balance': key not in current,
                'orphan_balance': key not in computed,
            })
        return {
            'ok': len(rows) == 0,
            'org_id': org_id,
            'diff_count': len(rows),
            'rows': rows,
        }

    def rebuild_balances(self, org_id: Any = None) -> Dict[str, Any]:
        """按分录重算余额：删除范围内余额后重建（投影允许重建）。"""
        computed = self._computed_totals(org_id)
        with self.ds.transaction():
            if org_id is not None:
                self.ds.execute('DELETE FROM %s WHERE org_id = ?' % BAL_TABLE,
                                [org_id])
            else:
                self.ds.execute('DELETE FROM %s' % BAL_TABLE)
            now = _now()
            for (org, location, item, batch, status), qty in computed.items():
                self.ds.execute(
                    'INSERT INTO %s (org_id, location_id, item_id, batch_id, '
                    'stock_status, qty_on_hand, qty_reserved, updated_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, 0, ?)' % BAL_TABLE,
                    [org, location, item, batch, status, qty, now])
        logger.info('[inventory] rebuild org=%s rows=%s', org_id, len(computed))
        return {'org_id': org_id, 'rows': len(computed),
                'total_qty': round(sum(computed.values()), 6)}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _find_existing(self, event_key: str,
                       source_line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, transaction_no, direction, base_qty, org_id, '
            'location_id, item_id, batch_id, stock_status FROM %s '
            'WHERE source_event_key = ? AND source_line_id = ?' % TX_TABLE,
            [event_key, source_line_id])
        return rows[0] if rows else None

    def _load_transaction(self, tx_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, transaction_no, transaction_type_id, '
            'transaction_date, org_id, location_id, item_id, uom_id, qty, '
            'base_qty, direction, batch_id, stock_status, source_line_id, '
            'transfer_group_id, reversal_of_transaction_id '
            'FROM %s WHERE id = ?' % TX_TABLE, [tx_id])
        return rows[0] if rows else None

    def _current_qty(self, entry: Dict[str, Any]) -> float:
        batch_id = entry.get('batch_id')
        return self.on_hand(
            entry.get('org_id'), entry.get('location_id'),
            entry.get('item_id'), batch_id,
            entry.get('stock_status') or 'unrestricted')

    def _insert_transaction(self, entry: Dict[str, Any], doc_type: str,
                            doc_id: Any, event_key: str, remark: Any,
                            reversal_of: Any = None) -> Dict[str, Any]:
        transaction_no = self._next_transaction_no(
            entry.get('transaction_date'))
        now = _now()
        cursor = self.ds.execute(
            'INSERT INTO %s (transaction_no, transaction_type_id, '
            'transaction_date, org_id, location_id, item_id, uom_id, qty, '
            'base_qty, direction, batch_id, stock_status, source_doc_type, '
            'source_doc_id, source_line_id, source_event_key, '
            'transfer_group_id, reversal_of_transaction_id, remark, '
            'created_by, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            % TX_TABLE,
            [transaction_no, entry['transaction_type_id'],
             entry.get('transaction_date'), entry['org_id'],
             entry['location_id'], entry['item_id'], entry['uom_id'],
             entry['qty'], entry['base_qty'], entry['direction'],
             entry.get('batch_id'), entry['stock_status'], doc_type,
             doc_id, entry['source_line_id'], event_key,
             entry.get('transfer_group_id'), reversal_of,
             remark, entry.get('created_by'), now])
        return {
            'id': cursor.lastrowid,
            'transaction_no': transaction_no,
            'direction': entry['direction'],
            'base_qty': entry['base_qty'],
            'org_id': entry['org_id'],
            'location_id': entry['location_id'],
            'item_id': entry['item_id'],
            'batch_id': entry.get('batch_id'),
            'stock_status': entry['stock_status'],
            'reversal_of_transaction_id': reversal_of,
        }

    def _apply_balance(self, entry: Dict[str, Any]) -> None:
        batch_id = int(entry['batch_id']) if not _blank(entry.get('batch_id')) else 0
        delta = float(entry['base_qty'])
        if entry.get('direction') == 'out':
            delta = -delta
        now = _now()
        self.ds.execute(
            'INSERT INTO %s (org_id, location_id, item_id, batch_id, '
            'stock_status, qty_on_hand, qty_reserved, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, 0, ?) '
            'ON CONFLICT(org_id, location_id, item_id, batch_id, stock_status) '
            'DO UPDATE SET qty_on_hand = qty_on_hand + excluded.qty_on_hand, '
            'updated_at = excluded.updated_at' % BAL_TABLE,
            [entry['org_id'], entry['location_id'], entry['item_id'],
             batch_id, entry['stock_status'], delta, now])

    def _next_transaction_no(self, transaction_date: Any) -> str:
        """在当前事务内取 INV 号（不单独提交，单据回滚时号一并回滚）。"""
        self.ds.execute(
            'CREATE TABLE IF NOT EXISTS %s (sequence_name TEXT PRIMARY KEY, '
            'current_value INTEGER NOT NULL DEFAULT 0, '
            'last_reset_at TEXT DEFAULT NULL)' % SEQUENCE_TABLE)
        rows = self.ds.query(
            'SELECT * FROM number_sequences WHERE code = ?', [SEQUENCE_CODE])
        # 部分测试替身无 status 列：视为 active，保持与真实库一致口径
        rows = [row for row in rows
                if 'status' not in row or row.get('status') == 'active']
        if not rows:
            raise InventoryError('INV_SEQUENCE_MISSING',
                                 '缺少库存事务编号序列 INV')
        config = rows[0]
        pattern = config.get('pattern') or 'INV-{DATE:yyyymm}-{SEQ:6}'
        start_value = int(config.get('start_value') or 1)
        on_exhaust = config.get('on_exhaust') or 'error'
        txn_date = _as_date(transaction_date)

        def _date_repl(match):
            fmt = match.group(1)
            fmt = _DATE_FMT.get(fmt)
            if not fmt:
                raise InventoryError('INV_SEQUENCE_MISSING',
                                     '库存编号日期格式不支持: %s' % match.group(1))
            return txn_date.strftime(fmt)

        rendered = _DATE_TOKEN_RE.sub(_date_repl, pattern)
        seq_match = _SEQ_TOKEN_RE.search(rendered)
        if not seq_match:
            raise InventoryError('INV_SEQUENCE_MISSING',
                                 '库存编号序列缺少 SEQ 段: %s' % pattern)
        padding = int(seq_match.group(1))
        period = txn_date.strftime('%Y%m')
        sequence_key = '%s:default:%s' % (SEQUENCE_CODE, period)
        baseline = start_value - 1
        if self.ds.execute(
                'SELECT 1 FROM %s WHERE sequence_name = ?' % SEQUENCE_TABLE,
                [sequence_key]).fetchone() is None:
            self.ds.execute(
                'INSERT OR IGNORE INTO %s (sequence_name, current_value) '
                'VALUES (?, ?)' % SEQUENCE_TABLE, [sequence_key, baseline])
        self.ds.execute(
            'UPDATE %s SET current_value = ? WHERE sequence_name = ? '
            'AND current_value < ?' % SEQUENCE_TABLE,
            [baseline, sequence_key, baseline])
        self.ds.execute(
            'UPDATE %s SET current_value = current_value + 1 '
            'WHERE sequence_name = ?' % SEQUENCE_TABLE, [sequence_key])
        row = self.ds.execute(
            'SELECT current_value FROM %s WHERE sequence_name = ?'
            % SEQUENCE_TABLE, [sequence_key]).fetchone()
        if row is None:
            raise InventoryError('INV_SEQUENCE_MISSING',
                                 '库存编号状态行写入失败: %s' % sequence_key)
        value = int(row[0] if not isinstance(row, dict) else row['current_value'])
        if len(str(value)) > padding and on_exhaust == 'error':
            raise InventoryError('INV_SEQUENCE_EXHAUSTED',
                                 '库存编号流水超出 %d 位' % padding)
        rendered = rendered.replace(
            seq_match.group(0), str(value).zfill(padding))
        return rendered
