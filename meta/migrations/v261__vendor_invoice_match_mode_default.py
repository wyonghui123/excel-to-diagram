# -*- coding: utf-8 -*-
"""[v261 2026-11-12] 采购发票匹配模式默认值改为 po_based（W5）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §22.8.4 / §22.8.6

内容:
  1. control_parameter_defs: code='vi_match_mode' 的 default_value
     gr_based → po_based（四维均未命中时的回落值）。
  2. vendor_invoice.yaml 字段默认值同步改为 po_based（新单创建快照）。
  3. 已存在的 vendor_invoices.match_mode 是创建时快照，**不回写**历史单据。

回滚:
  default_value 改回 gr_based（同样不动历史单据快照）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v261__vendor_invoice_match_mode_default'

PARAM_CODE = 'vi_match_mode'
DEFAULT_OLD = 'gr_based'
DEFAULT_NEW = 'po_based'


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)}


def _apply(conn, expected_old, new_value, tag):
    if not _table_exists(conn, 'control_parameter_defs'):
        print('[v261] SKIP: control_parameter_defs 表不存在')
        return 0
    columns = _columns(conn, 'control_parameter_defs')
    sets = ['default_value = ?']
    params = [new_value]
    if 'updated_at' in columns:
        sets.append("updated_at = datetime('now')")
    cursor = conn.execute(
        'UPDATE control_parameter_defs SET %s WHERE code = ? AND default_value = ?'
        % ', '.join(sets),
        params + [PARAM_CODE, expected_old])
    print('[v261] %s: vi_match_mode default_value %s → %s（%d 行）'
          % (tag, expected_old, new_value, cursor.rowcount))
    return cursor.rowcount


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v261] 开始: 采购发票匹配模式默认值 po_based')
    conn = _connect(db_path)
    try:
        _apply(conn, DEFAULT_OLD, DEFAULT_NEW, 'UPDATE')
        conn.commit()
        print('[v261] 完成: vi_match_mode 默认 po_based')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, 'control_parameter_defs'):
            print('[v261] FAIL: control_parameter_defs 表不存在')
            return False
        row = conn.execute(
            'SELECT default_value FROM control_parameter_defs '
            'WHERE code = ? AND status = ?', [PARAM_CODE, 'active']).fetchone()
        if not row:
            print('[v261] FAIL: 缺少激活参数 vi_match_mode')
            return False
        if str(row[0]) != DEFAULT_NEW:
            print('[v261] FAIL: vi_match_mode default_value 仍为 %s' % row[0])
            return False
    finally:
        conn.close()
    print('[v261] PASS: vi_match_mode 默认 po_based')
    return True


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v261] 开始: 回滚采购发票匹配模式默认值 gr_based')
    conn = _connect(db_path)
    try:
        _apply(conn, DEFAULT_NEW, DEFAULT_OLD, 'ROLLBACK')
        conn.commit()
        print('[v261] 完成: vi_match_mode 默认 gr_based')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()