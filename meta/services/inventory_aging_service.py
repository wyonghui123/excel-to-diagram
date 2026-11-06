# -*- coding: utf-8 -*-
"""库存库龄（入库日期投影）读模型。

依据: docs/specs/p8-inventory-aging-model/spec.md §5.3 / §5.4 / §5.5 / §7.1

口径:
  ① 库龄起算日 = 余额行 first_received_date（最早未清零入库过账日）。
  ② 报表只读 inventory_balances（O(余额行)），禁止现场扫事务做 FIFO。
  ③ 明细钻取才按单个余额键重放 receipt/outbound CTE，用于补偿余额法误差。
  ④ 分桶闭区间：0-30 / 31-60 / 61-90 / 91-180 / >180。
  ⑤ 负数库存与空日期落 UNASSIGNED；合计必须与 rows.qty_on_hand 相等。
  ⑥ group_by=item/batch 先按余额行分桶，再对桶内数量求和；展示日期取 MIN。
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from meta.services.inventory_guard_service import InventoryError

logger = logging.getLogger(__name__)

BAL_TABLE = 'inventory_balances'
TX_TABLE = 'inventory_transactions'

ERROR_ORG_REQUIRED = 'INV_AGING_ORG_REQUIRED'
ERROR_DATE_INVALID = 'INV_AGING_DATE_INVALID'

BUCKET_LABEL_UNASSIGNED = 'UNASSIGNED'

KEY_COLUMNS = (
    'org_id', 'location_id', 'item_id', 'batch_id', 'stock_status',
    'stock_segment_type', 'project_id', 'project_task_id',
    'sales_order_line_id', 'owner_party_id',
)

#: 参与 FIFO 匹配的键（batch_id 已 COALESCE 为 0，不含 org_id）
MATCH_COLUMNS = (
    'location_id', 'item_id', 'batch_id', 'stock_status',
    'stock_segment_type', 'project_id', 'project_task_id',
    'sales_order_line_id', 'owner_party_id',
)


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _int_or_zero(value: Any) -> int:
    return 0 if _blank(value) else int(value)


def _day_text(value: Any) -> Optional[str]:
    """把余额行的日期列统一截到 YYYY-MM-DD；空值返回 None。"""
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    text = str(value).strip()
    return text[:10] if text else None


def _parse_date(value: Any) -> date:
    if _blank(value):
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        raise InventoryError(
            ERROR_DATE_INVALID,
            '库龄日期格式非法，应为 YYYY-MM-DD',
            {'as_of': value})


class InventoryAgingService:
    """库龄报表与明细钻取；构造函数可注入 data_source（单测替身）。"""

    BUCKETS: Sequence[int] = (30, 60, 90, 180)

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 共用 SQL：FIFO 首个未清层日期
    # ------------------------------------------------------------------
    @staticmethod
    def first_received_date_sql(org_filter: bool = True) -> str:
        """返回“最早未清入库层日期”的 CTE SQL（§5.3）。

        org_filter=True  : SQL 含两处 `WHERE org_id = ?`（receipt / outbound），
                          调用方需传 2 个相同参数。
        org_filter=False : 不按组织过滤，结果多一列 org_id（按组织分组）。
        """
        where = 'WHERE org_id = ? AND ' if org_filter else 'WHERE '
        select_prefix = '' if org_filter else 'org_id,\n         '
        partition_prefix = 'org_id, ' if not org_filter else ''
        group_prefix = 'org_id, ' if not org_filter else ''
        final_prefix = '' if org_filter else 'r.org_id,\n       '
        match_join = '\n  AND '.join(
            'o.%s = r.%s' % (col, col) for col in MATCH_COLUMNS)
        select_keys = ',\n         '.join(
            'COALESCE(batch_id, 0) AS batch_id' if col == 'batch_id' else col
            for col in MATCH_COLUMNS)
        group_keys = ',\n           '.join(
            'COALESCE(batch_id, 0)' if col == 'batch_id' else col
            for col in MATCH_COLUMNS)
        final_keys = ',\n       '.join('r.%s' % col for col in MATCH_COLUMNS)
        return (
            'WITH receipt AS (\n'
            '  SELECT %(sp)s%(keys)s,\n'
            '         date(transaction_date) AS transaction_date, id,\n'
            '         SUM(base_qty) OVER (\n'
            '           PARTITION BY %(pp)s%(group_keys)s\n'
            '           ORDER BY date(transaction_date), id\n'
            '           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n'
            '         ) AS cum_in\n'
            '  FROM %(tx)s\n'
            "  %(where)s""direction = 'in'\n"
            '    AND reversal_of_transaction_id IS NULL\n'
            '),\n'
            'outbound AS (\n'
            '  SELECT %(sp)s%(keys)s,\n'
            "         SUM(CASE WHEN direction = 'out' THEN base_qty\n"
            '                   ELSE -base_qty END) AS net_out\n'
            '  FROM %(tx)s\n'
            "  %(where)s""(direction = 'out'\n"
            "         OR (direction = 'in'\n"
            '             AND reversal_of_transaction_id IS NOT NULL))\n'
            '  GROUP BY %(gp)s%(group_keys)s\n'
            ')\n'
            'SELECT %(fp)s%(final_keys)s,\n'
            '       MIN(r.transaction_date) AS first_received_date\n'
            'FROM receipt r\n'
            'LEFT JOIN outbound o\n'
            '  ON  %(match_join)s\n'
            'WHERE r.cum_in > COALESCE(o.net_out, 0)\n'
            'GROUP BY %(pg)s%(final_group)s'
        ) % {
            'sp': select_prefix, 'keys': select_keys,
            'pp': partition_prefix, 'group_keys': group_keys,
            'gp': group_prefix, 'pg': 'r.' + group_prefix if not org_filter
            else '',
            'tx': TX_TABLE, 'where': where,
            'fp': final_prefix, 'final_keys': final_keys,
            'match_join': match_join,
            'final_group': ',\n         '.join(
                'r.%s' % col for col in MATCH_COLUMNS),
        }

    # ------------------------------------------------------------------
    # 报表
    # ------------------------------------------------------------------
    def report(self, *, org_id: Any = None, as_of: Any = None,
               location_id: Any = None, item_id: Any = None,
               batch_id: Any = None, stock_status: Optional[str] = None,
               group_by: str = 'balance',
               bucket_edges: Optional[Sequence[int]] = None,
               include_zero: bool = False) -> Dict[str, Any]:
        """按余额行输出库龄分布；summary 合计恒等于 rows.qty_on_hand 合计。"""
        if _blank(org_id):
            raise InventoryError(
                ERROR_ORG_REQUIRED, '库龄报表必须指定库存组织',
                {'org_id': org_id})
        if group_by not in ('balance', 'item', 'batch'):
            raise InventoryError(
                'INV_AGING_GROUP_INVALID', '库龄分组方式不支持',
                {'group_by': group_by})

        as_of_date = _parse_date(as_of)
        edges = self._normalize_edges(bucket_edges)

        sql = ('SELECT org_id, location_id, item_id, batch_id, stock_status, '
               'stock_segment_type, project_id, project_task_id, '
               'sales_order_line_id, owner_party_id, qty_on_hand, '
               'first_received_date FROM %s WHERE org_id = ?' % BAL_TABLE)
        params: List[Any] = [int(org_id)]
        if location_id not in (None, ''):
            sql += ' AND location_id = ?'
            params.append(int(location_id))
        if item_id not in (None, ''):
            sql += ' AND item_id = ?'
            params.append(int(item_id))
        if batch_id not in (None, ''):
            sql += ' AND batch_id = ?'
            params.append(int(batch_id))
        if not _blank(stock_status):
            sql += ' AND stock_status = ?'
            params.append(stock_status)
        if not include_zero:
            sql += ' AND qty_on_hand <> 0'
        rows = self.ds.query(sql, params)

        balance_rows: List[Dict[str, Any]] = []
        for raw in rows:
            qty = float(raw.get('qty_on_hand') or 0)
            received = _day_text(raw.get('first_received_date'))
            days = None
            anomaly = False
            if received:
                days = (as_of_date - _parse_date(received)).days
                if days < 0:
                    days = 0
                    anomaly = True
            bucket = self._bucket_for(qty, days, edges)
            row = {col: raw.get(col) for col in KEY_COLUMNS}
            row.update({
                'qty_on_hand': qty,
                'first_received_date': received,
                'days_in_stock': days,
                'age_bucket': bucket,
                'date_anomaly': anomaly,
            })
            balance_rows.append(row)

        summary = self._summarize(balance_rows, edges)
        output_rows = balance_rows
        if group_by != 'balance':
            output_rows = self._group_rows(balance_rows, group_by, as_of_date)

        total_qty = round(sum(r['qty_on_hand'] for r in balance_rows), 6)
        unassigned_qty = round(sum(
            r['qty_on_hand'] for r in balance_rows
            if r['age_bucket'] == BUCKET_LABEL_UNASSIGNED), 6)
        return {
            'as_of': as_of_date.strftime('%Y-%m-%d'),
            'bucket_edges': list(edges),
            'group_by': group_by,
            'rows': output_rows,
            'summary': summary,
            'total_qty': total_qty,
            'unassigned_qty': unassigned_qty,
        }

    # ------------------------------------------------------------------
    # 明细钻取（精确重建，补偿余额法误差）
    # ------------------------------------------------------------------
    def detail(self, *, org_id: Any = None, location_id: Any = None,
               item_id: Any = None, batch_id: Any = 0,
               stock_status: str = 'unrestricted',
               stock_segment_type: str = 'owned',
               project_id: Any = 0, project_task_id: Any = 0,
               sales_order_line_id: Any = 0, owner_party_id: Any = 0,
               as_of: Any = None) -> Dict[str, Any]:
        """按单个余额键逐层重放 FIFO；Σremaining 与 qty_on_hand 对账。"""
        if _blank(org_id):
            raise InventoryError(
                ERROR_ORG_REQUIRED, '库龄明细必须指定库存组织',
                {'org_id': org_id})
        as_of_date = _parse_date(as_of)
        key = {
            'org_id': int(org_id),
            'location_id': _int_or_zero(location_id),
            'item_id': _int_or_zero(item_id),
            'batch_id': _int_or_zero(batch_id),
            'stock_status': stock_status or 'unrestricted',
            'stock_segment_type': stock_segment_type or 'owned',
            'project_id': _int_or_zero(project_id),
            'project_task_id': _int_or_zero(project_task_id),
            'sales_order_line_id': _int_or_zero(sales_order_line_id),
            'owner_party_id': _int_or_zero(owner_party_id),
        }
        match_sql = ' AND '.join(
            'COALESCE(batch_id, 0) = ?' if col == 'batch_id' else '%s = ?' % col
            for col in KEY_COLUMNS)
        match_params = [key[col] for col in KEY_COLUMNS]

        layers_sql = (
            'WITH receipt AS (\n'
            '  SELECT date(transaction_date) AS transaction_date, id, base_qty,\n'
            '         SUM(base_qty) OVER (\n'
            '           ORDER BY date(transaction_date), id\n'
            '           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n'
            '         ) AS cum_in\n'
            '  FROM %s\n'
            '  WHERE %s\n'
            "    AND direction = 'in'\n"
            '    AND reversal_of_transaction_id IS NULL\n'
            '), net AS (\n'
            '  SELECT COALESCE(SUM(CASE WHEN direction = \'out\' THEN base_qty\n'
            '                             ELSE -base_qty END), 0) AS net_out\n'
            '  FROM %s\n'
            '  WHERE %s\n'
            "    AND (direction = 'out'\n"
            "         OR (direction = 'in'\n"
            '             AND reversal_of_transaction_id IS NOT NULL))\n'
            ')\n'
            'SELECT receipt.transaction_date AS receipt_date,\n'
            '       receipt.base_qty AS layer_qty,\n'
            '       MAX(0, MIN(receipt.base_qty,\n'
            '                  receipt.cum_in - net.net_out)) AS remaining_qty,\n'
            '       CAST(julianday(?) - julianday(receipt.transaction_date) '
            'AS INTEGER) AS days_in_stock\n'
            'FROM receipt, net\n'
            'WHERE receipt.cum_in > net.net_out\n'
            'ORDER BY receipt.transaction_date, receipt.id'
            % (TX_TABLE, match_sql, TX_TABLE, match_sql))
        layers = self.ds.query(
            layers_sql,
            match_params * 2 + [as_of_date.strftime('%Y-%m-%d')])
        for layer in layers:
            layer['receipt_date'] = _day_text(layer.get('receipt_date'))
            layer['layer_qty'] = float(layer.get('layer_qty') or 0)
            layer['remaining_qty'] = float(layer.get('remaining_qty') or 0)
            days = layer.get('days_in_stock')
            layer['days_in_stock'] = int(days) if days is not None else None

        balance = self.ds.query(
            'SELECT qty_on_hand, first_received_date FROM %s WHERE %s'
            % (BAL_TABLE, match_sql), match_params)
        qty_on_hand = float(balance[0].get('qty_on_hand') or 0) \
            if balance else 0.0
        layers_total = round(sum(l['remaining_qty'] for l in layers), 6)
        reconciled = abs(layers_total - qty_on_hand) < 1e-6
        if not reconciled:
            logger.warning(
                '[inventory-aging] detail 对账不平 key=%s layers=%s qty=%s',
                key, layers_total, qty_on_hand)
        return {
            'as_of': as_of_date.strftime('%Y-%m-%d'),
            'key': key,
            'qty_on_hand': qty_on_hand,
            'first_received_date': _day_text(
                balance[0].get('first_received_date')) if balance else None,
            'layers': layers,
            'layers_total': layers_total,
            'reconciled': reconciled,
        }

    # ------------------------------------------------------------------
    # 内部分桶
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_edges(bucket_edges: Optional[Sequence[int]]) -> List[int]:
        edges = list(bucket_edges or InventoryAgingService.BUCKETS)
        try:
            edges = [int(edge) for edge in edges]
        except (TypeError, ValueError):
            raise InventoryError(
                ERROR_DATE_INVALID, '库龄分桶边界必须为整数',
                {'bucket_edges': bucket_edges})
        if not edges or any(edge <= 0 for edge in edges) \
                or edges != sorted(edges) or len(set(edges)) != len(edges):
            raise InventoryError(
                ERROR_DATE_INVALID, '库龄分桶边界必须为正整数且严格递增',
                {'bucket_edges': bucket_edges})
        return edges

    @staticmethod
    def _bucket_for(qty: float, days: Optional[int],
                    edges: Sequence[int]) -> str:
        if qty <= 0 or days is None:
            return BUCKET_LABEL_UNASSIGNED
        previous = 0
        for edge in edges:
            if days <= edge:
                return '%d-%d' % (previous, edge)
            previous = edge + 1
        return '>%d' % edges[-1]

    @staticmethod
    def _summarize(rows: List[Dict[str, Any]],
                   edges: Sequence[int]) -> List[Dict[str, Any]]:
        labels: List[str] = []
        previous = 0
        for edge in edges:
            labels.append('%d-%d' % (previous, edge))
            previous = edge + 1
        labels.append('>%d' % edges[-1])
        labels.append(BUCKET_LABEL_UNASSIGNED)
        totals = {label: 0.0 for label in labels}
        for row in rows:
            totals[row['age_bucket']] += row['qty_on_hand']
        return [{'bucket': label, 'qty': round(totals[label], 6)}
                for label in labels]

    def _group_rows(self, rows: List[Dict[str, Any]], group_by: str,
                    as_of_date: date) -> List[Dict[str, Any]]:
        """先分桶再求和：summary 已由余额行算出，这里只影响展示行。"""
        grouped: Dict[tuple, Dict[str, Any]] = {}
        for row in rows:
            if group_by == 'item':
                key = (row.get('org_id'), row.get('item_id'))
            else:
                key = (row.get('org_id'), row.get('item_id'),
                       row.get('batch_id'))
            bucket = grouped.get(key)
            if bucket is None:
                bucket = {
                    'org_id': row.get('org_id'),
                    'item_id': row.get('item_id'),
                    'qty_on_hand': 0.0,
                    'first_received_date': None,
                    'date_anomaly': False,
                }
                if group_by == 'batch':
                    bucket['batch_id'] = row.get('batch_id')
                grouped[key] = bucket
            bucket['qty_on_hand'] += row['qty_on_hand']
            bucket['date_anomaly'] = (bucket['date_anomaly']
                                      or row['date_anomaly'])
            received = row.get('first_received_date')
            if received and (bucket['first_received_date'] is None
                             or received < bucket['first_received_date']):
                bucket['first_received_date'] = received

        output: List[Dict[str, Any]] = []
        for bucket in grouped.values():
            received = bucket['first_received_date']
            days = None
            if received:
                days = (as_of_date - _parse_date(received)).days
                if days < 0:
                    days = 0
                    bucket['date_anomaly'] = True
            bucket.update({
                'qty_on_hand': round(bucket['qty_on_hand'], 6),
                'days_in_stock': days,
                # 聚合行不展示单桶归属：桶必须按余额行分别判定（§7.1）
                'age_bucket': None,
            })
            output.append(bucket)
        return output
