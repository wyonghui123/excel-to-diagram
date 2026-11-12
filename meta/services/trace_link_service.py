# -*- coding: utf-8 -*-
"""追溯链接（单据 ↔ 序列号 / 容器）写入唯一入口。

只收敛两张关系桥表的**写入**，不动 doc_flow 边（那是单据流转的另一层）：

  · document_serial_links：幂等键 (doc_type, line_id, serial_id)，已存在即跳过；
  · document_hu_links：幂等键 (doc_type, doc_id, line_id, hu_id, direction)，
    已存在时 link_type 只前进不回退（planned → packed → shipped），
    qty 覆盖为最新数量。

调用方仍保留各自的前置判断（表是否就绪、必填是否齐全）。
"""

from datetime import datetime

SERIAL_LINK_TABLE = 'document_serial_links'
HU_LINK_TABLE = 'document_hu_links'
HU_LINK_RANK = {'planned': 0, 'packed': 1, 'shipped': 2}


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def link_serial(ds, doc_type, doc_id, line_id, serial_id, direction) -> bool:
    """建单据行 ↔ 序列号链接；已存在返回 False（幂等）。"""
    if ds.query(
            'SELECT id FROM %s WHERE doc_type = ? AND line_id = ? '
            'AND serial_id = ?' % SERIAL_LINK_TABLE,
            [doc_type, line_id, serial_id]):
        return False
    ds.execute(
        'INSERT INTO %s (doc_type, doc_id, line_id, serial_id, direction, '
        "created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))"
        % SERIAL_LINK_TABLE,
        [doc_type, doc_id, line_id, serial_id, direction])
    return True


def link_hu(ds, doc_type, doc_id, line_id, hu_id, direction,
            link_type='packed', qty=None, tentative=0, org_id=None) -> str:
    """建/推进单据行 ↔ 容器链接；返回 'inserted' / 'promoted' / 'qty' / 'kept'。"""
    rows = ds.query(
        'SELECT id, link_type FROM %s WHERE doc_type = ? AND doc_id = ? '
        'AND COALESCE(line_id, 0) = ? AND hu_id = ? AND direction = ?'
        % HU_LINK_TABLE,
        [doc_type, doc_id, line_id or 0, hu_id, direction])
    if rows:
        row = rows[0]
        current = row.get('link_type') or 'planned'
        if HU_LINK_RANK.get(link_type, 0) > HU_LINK_RANK.get(current, 0):
            ds.execute(
                'UPDATE %s SET link_type = ?, qty = COALESCE(?, qty), '
                'updated_at = ? WHERE id = ?' % HU_LINK_TABLE,
                [link_type, qty, _now(), row['id']])
            return 'promoted'
        if not _blank(qty):
            ds.execute(
                'UPDATE %s SET qty = ?, updated_at = ? WHERE id = ?'
                % HU_LINK_TABLE, [qty, _now(), row['id']])
            return 'qty'
        return 'kept'
    now = _now()
    ds.execute(
        'INSERT INTO %s (doc_type, doc_id, line_id, hu_id, direction, '
        'link_type, tentative, qty, org_id, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)' % HU_LINK_TABLE,
        [doc_type, doc_id, line_id, hu_id, direction, link_type,
         tentative, qty, org_id, now, now])
    return 'inserted'
