# -*- coding: utf-8 -*-
"""[v268 2026-11-13] 采购发票费用分摊（W8-P1）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §22.6.1.4 数据与参数 / §22.6.1.5 硬约束 / §22.6.2.2 变更矩阵

范围:
  1. vendor_invoice_lines 增列:
       allocated_charge_amount NUMERIC(18,4) NOT NULL DEFAULT 0
     只读派生列，事实源为 allocation_results（S-2：派生列是投影，不是事实）。
     幂等: PRAGMA 判列，缺失才 ALTER。
  2. control_parameter_defs 2 条（target_bo='vendor_invoice'）:
       vi_charge_allocation_enabled    bool    false
       vi_charge_allocation_rule_code  string  ''（留空 = 自动取 basis=value 的规则）
  3. 本迁移只加列 + 写参数，不建表、不写任何分摊数据。

回滚:
  删 2 参数；列保留（SQLite 老版本不支持 DROP COLUMN）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v268__vendor_invoice_charge_allocation'

LINE_TABLE = 'vendor_invoice_lines'
PARAM_TABLE = 'control_parameter_defs'

SCOPE_BO = 'vendor_invoice'

LINE_COLUMNS = (
    ('allocated_charge_amount', 'NUMERIC(18,4) NOT NULL DEFAULT 0'),
)

PARAMS = (
    (
        'vi_charge_allocation_enabled', '采购发票费用分摊开关', 'procurement',
        'bool', 'false', None, None,
        'true=提交采购发票时把本票费用行金额摊到本票物料行；'
        'false=不执行分摊（默认）',
    ),
    (
        'vi_charge_allocation_rule_code', '采购发票费用分摊规则', 'procurement',
        'string', '', None, None,
        '指向 allocation_rules.code；留空时自动取 basis=value 的首条规则',
    ),
)

PARAM_CODES = tuple(param[0] for param in PARAMS)


# --------------------------------------------------------------------- helpers

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


def _param_id(conn, code):
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % PARAM_TABLE, [code]).fetchone()
    return None if not row else int(row[0])


# ------------------------------------------------------------------- columns

def _do_columns(conn):
    if not _table_exists(conn, LINE_TABLE):
        print('[v268] SKIP: %s 表不存在（未加列）' % LINE_TABLE)
        return 0
    existing = _columns(conn, LINE_TABLE)
    added = 0
    for column, column_type in LINE_COLUMNS:
        if column in existing:
            print('[v268] SKIP: %s.%s 已存在' % (LINE_TABLE, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (LINE_TABLE, column, column_type))
        added += 1
        print('[v268] ALTER: %s 新增 %s' % (LINE_TABLE, column))
    return added


# -------------------------------------------------------------------- params

def _do_params(conn):
    if not _table_exists(conn, PARAM_TABLE):
        print('[v268] SKIP: %s 表不存在（未建参数）' % PARAM_TABLE)
        return 0
    written = 0
    for (code, name, domain, value_type, default_value,
         tolerance_direction, tolerance_basis, description) in PARAMS:
        existing = _param_id(conn, code)
        if existing:
            conn.execute(
                'UPDATE %s SET name = ?, domain = ?, value_type = ?, '
                'target_bo = ?, default_value = ?, tolerance_direction = ?, '
                "tolerance_basis = ?, status = 'active', description = ? "
                'WHERE id = ?' % PARAM_TABLE,
                [name, domain, value_type, SCOPE_BO, default_value,
                 tolerance_direction, tolerance_basis, description, existing])
            print('[v268] SKIP: 参数 %s 已存在（已对齐定义）' % code)
            continue
        conn.execute(
            'INSERT INTO %s (code, name, domain, value_type, target_bo, '
            'default_value, tolerance_direction, tolerance_basis, status, '
            "description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, "
            "datetime('now'))" % PARAM_TABLE,
            [code, name, domain, value_type, SCOPE_BO, default_value,
             tolerance_direction, tolerance_basis, description])
        written += 1
        print('[v268] CREATE: 参数 %s' % code)
    return written


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v268] 开始: 采购发票费用分摊（列 + 参数）')
    conn = _connect(db_path)
    try:
        _do_columns(conn)
        _do_params(conn)
        conn.commit()
        print('[v268] 完成: vendor_invoice_lines.allocated_charge_amount / 2 参数')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    problems = []
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, LINE_TABLE):
            problems.append('缺少表 %s' % LINE_TABLE)
        else:
            existing = _columns(conn, LINE_TABLE)
            for column, _type in LINE_COLUMNS:
                if column not in existing:
                    problems.append('缺少列 %s.%s' % (LINE_TABLE, column))
        if not _table_exists(conn, PARAM_TABLE):
            problems.append('缺少表 %s' % PARAM_TABLE)
        else:
            for (code, name, domain, value_type, default_value,
                 tolerance_direction, tolerance_basis, description) in PARAMS:
                row = conn.execute(
                    'SELECT status, default_value, target_bo FROM %s '
                    'WHERE code = ?' % PARAM_TABLE, [code]).fetchone()
                if not row:
                    problems.append('缺少参数 %s' % code)
                    continue
                if row[0] != 'active':
                    problems.append('参数 %s status=%r' % (code, row[0]))
                if (row[1] or '') != (default_value if default_value is not None
                                      else ''):
                    problems.append('参数 %s default_value=%r（期望 %r）'
                                    % (code, row[1], default_value))
                if row[2] != SCOPE_BO:
                    problems.append('参数 %s target_bo=%r（期望 %r）'
                                    % (code, row[2], SCOPE_BO))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v268] FAIL: %s' % problem)
        return False
    print('[v268] PASS: vendor_invoice_lines.allocated_charge_amount / '
          '2 参数齐备')
    return True


# ------------------------------------------------------------------- rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v268] 开始回滚: 删除 2 参数（列保留）')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, PARAM_TABLE):
            for code in PARAM_CODES:
                conn.execute('DELETE FROM %s WHERE code = ?' % PARAM_TABLE,
                             [code])
                print('[v268] DROP: 参数 %s' % code)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    migrate(Path(target))
    verify(Path(target))