# -*- coding: utf-8 -*-
"""[v258 2026-11-11] 采购发票红冲链落地（W6：字段 + 类型反指针 + 死权限清理）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §3.2 / §6.2 / §12.2
  docs/specs/spec-reversal-platform-2026-11-06.md §3.1-§3.2 / §7

内容:
  1. vendor_invoices 增列 reversal_reason VARCHAR(256)（与 customer_invoices 同型），
     用于红字单回写原票冲销原因。幂等: PRAGMA 判列。
  2. 回填 type_definitions.VENDOR_INVOICE.reversal_type_id → VENDOR_CREDIT_MEMO.id，
     使红冲引擎能按“原类型 → 反转类型”定位红字单据类型（direction 必须相反）。
     v253 首次播种时该指针为空，本迁移补齐；v253 同步改为直接播种。
  3. 清理 v255 遗留的死权限 vendor_invoice:create_credit_memo / create_debit_memo
     （无 handler，手工创建贷项 / 借项已被守卫拒绝；调整单由正向流程承担），
     同时清 permission_set_permissions 授权。

幂等: ALTER 先判列；UPDATE 按 code 覆盖；DELETE 按 code（不存在时 0 行）。
回滚: 删权限无需复原（退役语义）；删除 reversal_type_id 指针；删除列需重建表，
      故 rollback 仅撤销指针与列值，不 DROP 列（SQLite 限制）。
"""

import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATION_NAME = 'v258__vendor_invoice_reversal'

HEADER_TABLE = 'vendor_invoices'
TYPE_TABLE = 'type_definitions'
PERMISSION_TABLE = 'permissions'
GRANT_TABLE = 'permission_set_permissions'

SCOPE_BO = 'vendor_invoice'
REASON_COLUMN = 'reversal_reason'
REASON_TYPE = 'VARCHAR(256)'

INVOICE_TYPE_CODE = 'VENDOR_INVOICE'
RED_TYPE_CODE = 'VENDOR_CREDIT_MEMO'

DEAD_PERMISSION_CODES = (
    'vendor_invoice:create_credit_memo',
    'vendor_invoice:create_debit_memo',
)


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


# ------------------------------------------------------------------ migration

def _do_reason_column(conn):
    if not _table_exists(conn, HEADER_TABLE):
        print('[v258] SKIP: %s 表不存在（未加列）' % HEADER_TABLE)
        return False
    if REASON_COLUMN in _columns(conn, HEADER_TABLE):
        print('[v258] SKIP: %s.%s 已存在' % (HEADER_TABLE, REASON_COLUMN))
        return False
    conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                 % (HEADER_TABLE, REASON_COLUMN, REASON_TYPE))
    print('[v258] ALTER: %s 新增 %s' % (HEADER_TABLE, REASON_COLUMN))
    return True


def _do_type_pointer(conn):
    if not _table_exists(conn, TYPE_TABLE):
        print('[v258] SKIP: %s 表不存在（未回填反指针）' % TYPE_TABLE)
        return 0
    red = conn.execute(
        'SELECT id FROM %s WHERE code = ? AND scope_bo = ?' % TYPE_TABLE,
        [RED_TYPE_CODE, SCOPE_BO]).fetchone()
    if not red:
        print('[v258] SKIP: 缺少红字类型 %s' % RED_TYPE_CODE)
        return 0
    cur = conn.execute(
        'UPDATE %s SET reversal_type_id = ? '
        'WHERE code = ? AND scope_bo = ?' % TYPE_TABLE,
        [red[0], INVOICE_TYPE_CODE, SCOPE_BO])
    print('[v258] UPDATE: %s.reversal_type_id → %s（%d 行）'
          % (INVOICE_TYPE_CODE, RED_TYPE_CODE, cur.rowcount))
    return cur.rowcount


def _do_dead_permissions(conn):
    removed = 0
    if _table_exists(conn, GRANT_TABLE):
        cols = _columns(conn, GRANT_TABLE)
        if 'permission_code' in cols:
            placeholders = ','.join('?' for _ in DEAD_PERMISSION_CODES)
            cur = conn.execute(
                'DELETE FROM %s WHERE permission_code IN (%s)'
                % (GRANT_TABLE, placeholders), list(DEAD_PERMISSION_CODES))
            removed += cur.rowcount or 0
    if _table_exists(conn, PERMISSION_TABLE):
        placeholders = ','.join('?' for _ in DEAD_PERMISSION_CODES)
        cur = conn.execute(
            'DELETE FROM %s WHERE code IN (%s)' % (PERMISSION_TABLE, placeholders),
            list(DEAD_PERMISSION_CODES))
        removed += cur.rowcount or 0
    print('[v258] CLEAN: 死权限 %s（%d 行）'
          % ('/'.join(DEAD_PERMISSION_CODES), removed))
    return removed


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v258] 开始: 采购发票红冲链（字段 + 类型反指针 + 死权限清理）')
    conn = _connect(db_path)
    try:
        _do_reason_column(conn)
        _do_type_pointer(conn)
        _do_dead_permissions(conn)
        conn.commit()
        print('[v258] 完成: 采购发票红冲链')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v258 verify] FAIL: DB 不存在')
        return False
    conn = _connect(db_path)
    problems = []
    try:
        if not _table_exists(conn, HEADER_TABLE):
            problems.append('缺少表 %s' % HEADER_TABLE)
        elif REASON_COLUMN not in _columns(conn, HEADER_TABLE):
            problems.append('%s 缺少列 %s' % (HEADER_TABLE, REASON_COLUMN))
        if _table_exists(conn, TYPE_TABLE):
            row = conn.execute(
                'SELECT t.reversal_type_id, r.code '
                'FROM %s t LEFT JOIN %s r ON r.id = t.reversal_type_id '
                'WHERE t.code = ? AND t.scope_bo = ?' % (TYPE_TABLE, TYPE_TABLE),
                [INVOICE_TYPE_CODE, SCOPE_BO]).fetchone()
            if not row:
                problems.append('缺少类型 %s' % INVOICE_TYPE_CODE)
            elif not row[0]:
                problems.append('%s.reversal_type_id 为空' % INVOICE_TYPE_CODE)
            elif row[1] != RED_TYPE_CODE:
                problems.append('%s.reversal_type_id 未指向 %s（实际 %s）'
                                % (INVOICE_TYPE_CODE, RED_TYPE_CODE, row[1]))
        if _table_exists(conn, PERMISSION_TABLE):
            placeholders = ','.join('?' for _ in DEAD_PERMISSION_CODES)
            left = conn.execute(
                'SELECT COUNT(*) FROM %s WHERE code IN (%s)'
                % (PERMISSION_TABLE, placeholders),
                list(DEAD_PERMISSION_CODES)).fetchone()[0]
            if left:
                problems.append('死权限未清理（%d 行）' % left)
    finally:
        conn.close()
    if problems:
        print('[v258 verify] FAIL: %d 项' % len(problems))
        for item in problems:
            print('  - %s' % item)
        return False
    print('[v258 verify] OK: 采购发票红冲链字段 / 类型反指针 / 死权限清理')
    return True


def rollback(db_path: Path, force_backup: bool = False) -> bool:
    """回滚：复原类型指针与列值；SQLite 不支持 DROP COLUMN（旧版本），
    列保留但清空，不影响业务（默认空值）。死权限不恢复（退役语义）。"""
    db_path = Path(db_path)
    print('[v258 rollback] 开始: 撤销采购发票红冲链')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, TYPE_TABLE):
            conn.execute(
                'UPDATE %s SET reversal_type_id = NULL '
                'WHERE code = ? AND scope_bo = ?' % TYPE_TABLE,
                [INVOICE_TYPE_CODE, SCOPE_BO])
        if _table_exists(conn, HEADER_TABLE) and \
                REASON_COLUMN in _columns(conn, HEADER_TABLE):
            conn.execute('UPDATE %s SET %s = NULL' % (HEADER_TABLE, REASON_COLUMN))
        conn.commit()
        print('[v258 rollback] 完成: 类型指针已置空，%s 已清空（列保留）'
              % REASON_COLUMN)
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()