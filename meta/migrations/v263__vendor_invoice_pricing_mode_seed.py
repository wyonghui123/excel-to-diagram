# -*- coding: utf-8 -*-
"""[v263 2026-11-13] 采购发票定价模式控制参数种子（W5 遗留①）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §22.10
  docs/superpowers/plans/2026-11-12-vendor-invoice-amount-w2-execution-plan.md §9.1

内容:
  1. control_parameter_defs 新增 1 条:
       code='vi_match_pricing_mode'  name='采购发票定价模式'
       domain='procurement'  value_type='enum'  default_value='po_price'
       target_bo='vendor_invoice'  status='active'
       枚举: po_price=按采购订单价 / manual=人工定价（需 override）
  2. 本迁移只写定义，不建表；服务侧解析见 VendorInvoiceMatchService。

幂等:
  按 code 先查后插；已存在则对齐定义字段，重复执行打印 [SKIP]。

回滚:
  按 code 删除。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v263__vendor_invoice_pricing_mode_seed'

PARAM_TABLE = 'control_parameter_defs'

SCOPE_BO = 'vendor_invoice'

PARAM = {
    'code': 'vi_match_pricing_mode',
    'name': '采购发票定价模式',
    'domain': 'procurement',
    'value_type': 'enum',
    'default_value': 'po_price',
    'description': 'po_price=按采购订单价 / manual=人工定价（需 override）',
}

PARAM_CODE = PARAM['code']


# --------------------------------------------------------------------- helpers

def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _param_row(conn, code):
    return conn.execute(
        'SELECT id, domain, status, default_value FROM %s WHERE code = ?'
        % PARAM_TABLE, [code]).fetchone()


# ----------------------------------------------------------------------- seed

def _do_param(conn):
    if not _table_exists(conn, PARAM_TABLE):
        print('[v263] SKIP: %s 表不存在（未建参数）' % PARAM_TABLE)
        return 0
    existing = _param_row(conn, PARAM_CODE)
    if existing:
        conn.execute(
            'UPDATE %s SET name = ?, domain = ?, value_type = ?, '
            'target_bo = ?, default_value = ?, status = \'active\', '
            'description = ? WHERE id = ?' % PARAM_TABLE,
            [PARAM['name'], PARAM['domain'], PARAM['value_type'], SCOPE_BO,
             PARAM['default_value'], PARAM['description'], int(existing[0])])
        print('[v263] SKIP: 参数 %s 已存在（已对齐定义）' % PARAM_CODE)
        return 0
    conn.execute(
        'INSERT INTO %s (code, name, domain, value_type, target_bo, '
        'default_value, status, description, created_at) '
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'))" % PARAM_TABLE,
        [PARAM['code'], PARAM['name'], PARAM['domain'], PARAM['value_type'],
         SCOPE_BO, PARAM['default_value'], PARAM['description']])
    print('[v263] CREATE: 参数 %s' % PARAM_CODE)
    return 1


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v263] 开始: 采购发票定价模式参数种子')
    conn = _connect(db_path)
    try:
        _do_param(conn)
        conn.commit()
        print('[v263] 完成: 采购发票定价模式参数种子')
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
        if not _table_exists(conn, PARAM_TABLE):
            problems.append('缺少表 %s' % PARAM_TABLE)
        else:
            row = _param_row(conn, PARAM_CODE)
            if not row:
                problems.append('缺少参数 %s' % PARAM_CODE)
            else:
                if row[1] != PARAM['domain']:
                    problems.append('参数 %s domain=%r（期望 %r）'
                                    % (PARAM_CODE, row[1], PARAM['domain']))
                if row[2] != 'active':
                    problems.append('参数 %s status=%r' % (PARAM_CODE, row[2]))
                if str(row[3]) != PARAM['default_value']:
                    problems.append('参数 %s default_value=%r（期望 %r）'
                                    % (PARAM_CODE, row[3],
                                       PARAM['default_value']))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v263] FAIL: %s' % problem)
        return False
    print('[v263] PASS: 参数 vi_match_pricing_mode 齐备（default=po_price）')
    return True


# ------------------------------------------------------------------ rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v263] 开始: 回滚采购发票定价模式参数')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, PARAM_TABLE):
            conn.execute('DELETE FROM %s WHERE code = ?' % PARAM_TABLE,
                         [PARAM_CODE])
        conn.commit()
        print('[v263] 完成: 参数 vi_match_pricing_mode 已删除')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()