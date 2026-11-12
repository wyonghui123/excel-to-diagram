# -*- coding: utf-8 -*-
"""[v259 2026-11-12] 采购发票正向调整单（W7 / Phase 2）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §21

内容:
  1. vendor_invoices 增列:
       adjustment_of_invoice_id INTEGER  回指原票 / 原调整单
       adjustment_direction     VARCHAR(10) increase / decrease
       adjustment_reason        VARCHAR(256) 调整原因
     幂等: PRAGMA 判列，缺失才 ALTER。
  2. 播种单据类型 VENDOR_INVOICE_ADJUSTMENT（scope_bo='vendor_invoice', level='header'）:
       document_category='adjustment' / document_role='adjustment' /
       direction=1 / is_default=0 / reversal_type_id=NULL
     reversal_type_id 为 NULL 是设计意图：调整单不进红冲引擎（§21.4）。
  3. 播种编号序列 VIA（VIA-{DATE:yyyymm}-{SEQ:5}, date_field=invoice_date）。
  4. 建回指索引 idx_vendor_invoice_adjustment_of（partial）:
     旧库升级不会执行 generated_schema.sql，索引只能在迁移内建，否则与
     YAML indexes 声明漂移。

回滚:
  删索引 → 删序列 → 删类型 → 清三列值（SQLite 老版本不支持 DROP COLUMN，列保留）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v259__vendor_invoice_adjustment'

HEADER_TABLE = 'vendor_invoices'
TYPE_TABLE = 'type_definitions'
SEQUENCE_TABLE = 'number_sequences'

SCOPE_BO = 'vendor_invoice'
LEVEL = 'header'

TYPE_CODE = 'VENDOR_INVOICE_ADJUSTMENT'
TYPE_NAME = '采购发票调整单'
TYPE_DESCRIPTION = '正向调整单：增加/冲减已过账发票数量与金额，不修改原票'
SEQUENCE_CODE = 'VIA'
SEQUENCE_NAME = '采购发票调整单编号'
SEQUENCE_PATTERN = 'VIA-{DATE:yyyymm}-{SEQ:5}'
SEQUENCE_DATE_FIELD = 'invoice_date'

COLUMNS = (
    ('adjustment_of_invoice_id', 'INTEGER'),
    ('adjustment_direction', 'VARCHAR(10)'),
    ('adjustment_reason', 'VARCHAR(256)'),
)

# 与 meta/schemas/vendor_invoice.yaml indexes 声明保持同一 DDL
INDEX_NAME = 'idx_vendor_invoice_adjustment_of'
INDEX_DDL = (
    'CREATE INDEX IF NOT EXISTS %s ON %s(adjustment_of_invoice_id) '
    "WHERE adjustment_of_invoice_id IS NOT NULL" % (INDEX_NAME, HEADER_TABLE)
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

def _do_columns(conn):
    if not _table_exists(conn, HEADER_TABLE):
        print('[v259] SKIP: %s 表不存在（未加列）' % HEADER_TABLE)
        return 0
    existing = _columns(conn, HEADER_TABLE)
    added = 0
    for column, column_type in COLUMNS:
        if column in existing:
            print('[v259] SKIP: %s.%s 已存在' % (HEADER_TABLE, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (HEADER_TABLE, column, column_type))
        added += 1
        print('[v259] ALTER: %s 新增 %s' % (HEADER_TABLE, column))
    return added


def _do_index(conn):
    if not _table_exists(conn, HEADER_TABLE):
        print('[v259] SKIP: %s 表不存在（未建索引）' % HEADER_TABLE)
        return
    conn.execute(INDEX_DDL)
    print('[v259] ENSURE: 索引 %s' % INDEX_NAME)


def _do_sequence(conn):
    if not _table_exists(conn, SEQUENCE_TABLE):
        print('[v259] SKIP: %s 表不存在（未建序列）' % SEQUENCE_TABLE)
        return None
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % SEQUENCE_TABLE,
        [SEQUENCE_CODE]).fetchone()
    if row:
        conn.execute(
            'UPDATE %s SET name = ?, pattern = ?, date_field = ?, '
            "status = 'active' WHERE id = ?" % SEQUENCE_TABLE,
            [SEQUENCE_NAME, SEQUENCE_PATTERN, SEQUENCE_DATE_FIELD, row[0]])
        print('[v259] SKIP: 序列 %s 已存在（已对齐 pattern）' % SEQUENCE_CODE)
        return int(row[0])
    cur = conn.execute(
        'INSERT INTO %s (code, name, pattern, date_field, start_value, '
        "on_exhaust, status) VALUES (?, ?, ?, ?, 1, 'error', 'active')"
        % SEQUENCE_TABLE,
        [SEQUENCE_CODE, SEQUENCE_NAME, SEQUENCE_PATTERN, SEQUENCE_DATE_FIELD])
    print('[v259] CREATE: 序列 %s' % SEQUENCE_CODE)
    return int(cur.lastrowid)


def _do_type(conn, sequence_id):
    if not _table_exists(conn, TYPE_TABLE):
        print('[v259] SKIP: %s 表不存在（未建类型）' % TYPE_TABLE)
        return None
    row = conn.execute(
        'SELECT id FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
        % TYPE_TABLE, [SCOPE_BO, LEVEL, TYPE_CODE]).fetchone()
    if row:
        conn.execute(
            'UPDATE %s SET name = ?, document_category = ?, document_role = ?, '
            'direction = 1, is_default = 0, number_sequence_id = ?, '
            'reversal_type_id = NULL, status = ?, description = ? WHERE id = ?'
            % TYPE_TABLE,
            [TYPE_NAME, 'adjustment', 'adjustment', sequence_id, 'active',
             TYPE_DESCRIPTION, row[0]])
        print('[v259] SKIP: 类型 %s 已存在（已对齐定义）' % TYPE_CODE)
        return int(row[0])
    cur = conn.execute(
        'INSERT INTO %s (code, name, scope_bo, level, document_category, '
        'document_role, direction, is_default, number_sequence_id, '
        "reversal_type_id, status, description, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, NULL, 'active', ?, datetime('now'))"
        % TYPE_TABLE,
        [TYPE_CODE, TYPE_NAME, SCOPE_BO, LEVEL, 'adjustment', 'adjustment',
         sequence_id, TYPE_DESCRIPTION])
    print('[v259] CREATE: 类型 %s' % TYPE_CODE)
    return int(cur.lastrowid)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v259] 开始: 采购发票正向调整单')
    conn = _connect(db_path)
    try:
        _do_columns(conn)
        _do_index(conn)
        sequence_id = _do_sequence(conn)
        _do_type(conn, sequence_id)
        conn.commit()
        print('[v259] 完成: 采购发票正向调整单')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v259 verify] FAIL: DB 不存在')
        return False
    conn = _connect(db_path)
    problems = []
    try:
        if not _table_exists(conn, HEADER_TABLE):
            problems.append('缺少表 %s' % HEADER_TABLE)
        else:
            existing = _columns(conn, HEADER_TABLE)
            for column, _ in COLUMNS:
                if column not in existing:
                    problems.append('%s 缺少列 %s' % (HEADER_TABLE, column))
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
                [INDEX_NAME]).fetchone()
            if not row:
                problems.append('缺少索引 %s' % INDEX_NAME)
        if _table_exists(conn, TYPE_TABLE):
            row = conn.execute(
                'SELECT id, document_category, document_role, direction, '
                'is_default, number_sequence_id, reversal_type_id '
                'FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
                % TYPE_TABLE, [SCOPE_BO, LEVEL, TYPE_CODE]).fetchone()
            if not row:
                problems.append('缺少类型 %s' % TYPE_CODE)
            else:
                if row[1] != 'adjustment':
                    problems.append('%s.document_category 应为 adjustment（实际 %s）'
                                    % (TYPE_CODE, row[1]))
                if row[2] != 'adjustment':
                    problems.append('%s.document_role 应为 adjustment（实际 %s）'
                                    % (TYPE_CODE, row[2]))
                if int(row[3] or 0) != 1:
                    problems.append('%s.direction 应为 1（实际 %s）' % (TYPE_CODE, row[3]))
                if int(row[4] or 0) != 0:
                    problems.append('%s.is_default 应为 0' % TYPE_CODE)
                if not row[5]:
                    problems.append('%s.number_sequence_id 为空' % TYPE_CODE)
                if row[6]:
                    problems.append('%s.reversal_type_id 必须为空（调整单不可红冲）' % TYPE_CODE)
        if _table_exists(conn, SEQUENCE_TABLE):
            row = conn.execute(
                'SELECT pattern, date_field FROM %s WHERE code = ?'
                % SEQUENCE_TABLE, [SEQUENCE_CODE]).fetchone()
            if not row:
                problems.append('缺少序列 %s' % SEQUENCE_CODE)
            elif row[0] != SEQUENCE_PATTERN:
                problems.append('序列 %s.pattern 不符（实际 %s）'
                                % (SEQUENCE_CODE, row[0]))
            elif row[1] != SEQUENCE_DATE_FIELD:
                problems.append('序列 %s.date_field 不符（实际 %s）'
                                % (SEQUENCE_CODE, row[1]))
    finally:
        conn.close()
    if problems:
        print('[v259 verify] FAIL: %d 项' % len(problems))
        for item in problems:
            print('  - %s' % item)
        return False
    print('[v259 verify] OK: 采购发票正向调整单（列 / 类型 / 序列）')
    return True


def rollback(db_path: Path, force_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v259 rollback] 开始: 撤销采购发票正向调整单')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, HEADER_TABLE):
            conn.execute('DROP INDEX IF EXISTS %s' % INDEX_NAME)
        if _table_exists(conn, TYPE_TABLE):
            conn.execute(
                'DELETE FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
                % TYPE_TABLE, [SCOPE_BO, LEVEL, TYPE_CODE])
        if _table_exists(conn, SEQUENCE_TABLE):
            conn.execute('DELETE FROM %s WHERE code = ?' % SEQUENCE_TABLE,
                         [SEQUENCE_CODE])
        if _table_exists(conn, HEADER_TABLE):
            existing = _columns(conn, HEADER_TABLE)
            for column, _ in COLUMNS:
                if column in existing:
                    conn.execute('UPDATE %s SET %s = NULL'
                                 % (HEADER_TABLE, column))
        conn.commit()
        print('[v259 rollback] 完成: 类型 / 序列已删，三列已清空（列保留）')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()