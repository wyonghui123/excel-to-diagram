# -*- coding: utf-8 -*-
"""单据编号取号（INV-4：ADJ / CNT）—— 与 InventoryPostingService 同口径。

· 序列配置来自 number_sequences，流水状态落在 _sequences。
· 取号不单独提交：随调用方事务一起回滚。
"""

import re
from datetime import date, datetime
from typing import Any

from meta.services.inventory_guard_service import InventoryError

SEQUENCE_TABLE = '_sequences'

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


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if _blank(value):
        return date.today()
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except ValueError:
        return date.today()


def next_document_no(ds, code: str, doc_date: Any = None,
                     default_pattern: str = None) -> str:
    """按序列配置生成单据号；缺配置时使用 default_pattern 兜底。"""
    ds.execute(
        'CREATE TABLE IF NOT EXISTS %s (sequence_name TEXT PRIMARY KEY, '
        'current_value INTEGER NOT NULL DEFAULT 0, '
        'last_reset_at TEXT DEFAULT NULL)' % SEQUENCE_TABLE)
    rows = ds.query('SELECT * FROM number_sequences WHERE code = ?', [code])
    rows = [row for row in rows
            if 'status' not in row or row.get('status') == 'active']
    if not rows:
        if not default_pattern:
            raise InventoryError('INV_SEQUENCE_MISSING',
                                 '缺少单据编号序列 %s' % code)
        config = {'pattern': default_pattern, 'start_value': 1,
                  'on_exhaust': 'error'}
    else:
        config = rows[0]
    pattern = config.get('pattern') or default_pattern
    start_value = int(config.get('start_value') or 1)
    on_exhaust = config.get('on_exhaust') or 'error'
    txn_date = _as_date(doc_date)

    def _date_repl(match):
        fmt = _DATE_FMT.get(match.group(1))
        if not fmt:
            raise InventoryError('INV_SEQUENCE_MISSING',
                                 '编号日期格式不支持: %s' % match.group(1))
        return txn_date.strftime(fmt)

    rendered = _DATE_TOKEN_RE.sub(_date_repl, pattern)
    seq_match = _SEQ_TOKEN_RE.search(rendered)
    if not seq_match:
        raise InventoryError('INV_SEQUENCE_MISSING',
                             '编号序列缺少 SEQ 段: %s' % pattern)
    padding = int(seq_match.group(1))
    period = txn_date.strftime('%Y%m')
    sequence_key = '%s:default:%s' % (code, period)
    baseline = start_value - 1
    if ds.execute('SELECT 1 FROM %s WHERE sequence_name = ?' % SEQUENCE_TABLE,
                  [sequence_key]).fetchone() is None:
        ds.execute(
            'INSERT OR IGNORE INTO %s (sequence_name, current_value) '
            'VALUES (?, ?)' % SEQUENCE_TABLE, [sequence_key, baseline])
    ds.execute(
        'UPDATE %s SET current_value = ? WHERE sequence_name = ? '
        'AND current_value < ?' % SEQUENCE_TABLE,
        [baseline, sequence_key, baseline])
    ds.execute(
        'UPDATE %s SET current_value = current_value + 1 '
        'WHERE sequence_name = ?' % SEQUENCE_TABLE, [sequence_key])
    row = ds.execute(
        'SELECT current_value FROM %s WHERE sequence_name = ?'
        % SEQUENCE_TABLE, [sequence_key]).fetchone()
    if row is None:
        raise InventoryError('INV_SEQUENCE_MISSING',
                             '编号状态行写入失败: %s' % sequence_key)
    value = int(row[0] if not isinstance(row, dict) else row['current_value'])
    if len(str(value)) > padding and on_exhaust == 'error':
        raise InventoryError('INV_SEQUENCE_EXHAUSTED',
                             '单据编号流水超出 %d 位' % padding)
    return rendered.replace(seq_match.group(0), str(value).zfill(padding))
