# -*- coding: utf-8 -*-
"""[v120 2026-10-25] 销售订单波次 0：种子补齐（编号序列 / 付款条件 / 组织职能）

依据:
  docs/superpowers/specs/2026-10-24-sales-order-wave0-detailed-plan.md
    §2.3 number_sequence 只补种子（SO_STD / SO_RET）
    §4.1 波次 0 只补种子 NET30
    §0.4 org + org_functions 待补 sales 职能

范围:
  1. number_sequences 新增 2 条
       SO_STD  SO-{DATE:yyyymm}-{SEQ:6}   date_field=order_date
       SO_RET  SR-{DATE:yyyymm}-{SEQ:6}   date_field=order_date
  2. type_definitions 回填 number_sequence_id
       TA(header) → SO_STD
       RE(header) → SO_RET
     行类型（STD/SVC/RET/FOC/TXT）不挂序列（编号只取在抬头）
  3. payment_terms 新增 NET30（basis_date_rule=invoice_date）
     payment_term_lines 新增 1 行（seq=1 / percentage=100 / offset_days=30）
  4. org_functions 给「华东销售中心」(code=bu_east_sales) 增 sales 职能
     （W0-R10 校验 sales_org_id 必须具备 sales 职能）

边界:
  只补上述种子；不重跑 meta/scripts/init_sales_config_seed.py（含税务等超出波次 0 的内容）。

幂等:
  编号序列按 code 判存在；付款条件按 code 判存在；分期行按 (term_id, seq) 判存在；
  组织职能按 (org_id, function_type) 判存在。已存在则只刷新业务属性，不重置 status。

回滚:
  先清 type_definitions.number_sequence_id（解除外键），再删两条序列；
  删 NET30 的分期行与头；删 org 318 的 sales 职能行。
"""
import sqlite3
from pathlib import Path

SCOPE_BO = 'sales_order'

#: (code, name, pattern, date_field, start_value, on_exhaust, description)
SEQUENCES = (
    ('SO_STD', '标准销售订单编号', 'SO-{DATE:yyyymm}-{SEQ:6}', 'order_date', 1,
     'error', '标准销售订单取号：SO-年月-6 位流水，按月复位'),
    ('SO_RET', '退货订单编号', 'SR-{DATE:yyyymm}-{SEQ:6}', 'order_date', 1,
     'error', '退货订单取号：SR-年月-6 位流水，按月复位'),
)

#: (header code, sequence code)
TYPE_SEQUENCE_BINDINGS = (
    ('TA', 'SO_STD'),
    ('RE', 'SO_RET'),
)

PAYMENT_TERM = {
    'code': 'NET30',
    'name': '月结 30 天',
    'basis_date_rule': 'invoice_date',
    'cutoff_day': None,
    'description': '开票后 30 天全额付款（波次 0 标准账期）',
}

PAYMENT_TERM_LINE = {
    'seq': 1,
    'percentage': 100,
    'offset_months': 0,
    'fixed_day_of_month': None,
    'offset_days': 30,
    'discount_percent': None,
    'discount_days': None,
    'description': '全额到期',
}

SALES_ORG_CODE = 'bu_east_sales'
SALES_FUNCTION = 'sales'


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _sequence_id(conn, code):
    row = conn.execute(
        'SELECT id FROM number_sequences WHERE code = ?', (code,)
    ).fetchone()
    return row[0] if row else None


def _header_type_id(conn, code):
    row = conn.execute(
        "SELECT id FROM type_definitions "
        "WHERE scope_bo = ? AND level = 'header' AND code = ?", (SCOPE_BO, code)
    ).fetchone()
    return row[0] if row else None


def _payment_term_id(conn, code):
    row = conn.execute(
        'SELECT id FROM payment_terms WHERE code = ?', (code,)
    ).fetchone()
    return row[0] if row else None


def _payment_term_line_id(conn, term_id, seq):
    row = conn.execute(
        'SELECT id FROM payment_term_lines WHERE payment_term_id = ? AND seq = ?',
        (term_id, seq)
    ).fetchone()
    return row[0] if row else None


def _org_id_by_code(conn, code):
    row = conn.execute('SELECT id FROM orgs WHERE code = ?', (code,)).fetchone()
    return row[0] if row else None


def _org_function_id(conn, org_id, function_type):
    row = conn.execute(
        'SELECT id FROM org_functions WHERE org_id = ? AND function_type = ?',
        (org_id, function_type)
    ).fetchone()
    return row[0] if row else None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v120] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v120] 开始: 销售订单波次 0 种子')

        # 1) 编号序列
        if not _table_exists(conn, 'number_sequences'):
            print('[v120] 缺少 number_sequences，跳过')
            return False
        for code, name, pattern, date_field, start_value, on_exhaust, desc in SEQUENCES:
            if _sequence_id(conn, code):
                conn.execute(
                    'UPDATE number_sequences SET name = ?, pattern = ?, date_field = ?, '
                    'start_value = ?, on_exhaust = ?, status = ?, description = ? '
                    'WHERE code = ?',
                    (name, pattern, date_field, start_value, on_exhaust,
                     'active', desc, code))
                print('  ~ UPDATE sequence %s' % code)
            else:
                conn.execute(
                    'INSERT INTO number_sequences '
                    '(code, name, pattern, scope_fields, date_field, start_value, '
                    ' on_exhaust, preview, status, description, created_at) '
                    "VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, 'active', ?, datetime('now'))",
                    (code, name, pattern, date_field, start_value, on_exhaust, desc))
                print('  + INSERT sequence %s' % code)

        # 2) 单据类型挂序列
        for type_code, seq_code in TYPE_SEQUENCE_BINDINGS:
            type_id = _header_type_id(conn, type_code)
            seq_id = _sequence_id(conn, seq_code)
            if not type_id or not seq_id:
                print('  ! 跳过绑定 %s→%s：类型或序列缺失' % (type_code, seq_code))
                continue
            conn.execute(
                'UPDATE type_definitions SET number_sequence_id = ? WHERE id = ?',
                (seq_id, type_id))
            print('  ~ BIND type %s → %s' % (type_code, seq_code))

        # 3) 付款条件 NET30
        if not _table_exists(conn, 'payment_terms'):
            print('[v120] 缺少 payment_terms，跳过付款条件种子')
        else:
            term_id = _payment_term_id(conn, PAYMENT_TERM['code'])
            if term_id:
                conn.execute(
                    'UPDATE payment_terms SET name = ?, basis_date_rule = ?, '
                    'cutoff_day = ?, status = ?, description = ? WHERE id = ?',
                    (PAYMENT_TERM['name'], PAYMENT_TERM['basis_date_rule'],
                     PAYMENT_TERM['cutoff_day'], 'active',
                     PAYMENT_TERM['description'], term_id))
                print('  ~ UPDATE payment_term %s' % PAYMENT_TERM['code'])
            else:
                cur = conn.execute(
                    'INSERT INTO payment_terms '
                    '(code, name, basis_date_rule, cutoff_day, status, description, '
                    ' created_at) '
                    "VALUES (?, ?, ?, ?, 'active', ?, datetime('now'))",
                    (PAYMENT_TERM['code'], PAYMENT_TERM['name'],
                     PAYMENT_TERM['basis_date_rule'], PAYMENT_TERM['cutoff_day'],
                     PAYMENT_TERM['description']))
                term_id = cur.lastrowid
                print('  + INSERT payment_term %s' % PAYMENT_TERM['code'])

            line = PAYMENT_TERM_LINE
            line_id = _payment_term_line_id(conn, term_id, line['seq'])
            if line_id:
                conn.execute(
                    'UPDATE payment_term_lines SET percentage = ?, offset_months = ?, '
                    'fixed_day_of_month = ?, offset_days = ?, discount_percent = ?, '
                    'discount_days = ?, description = ? WHERE id = ?',
                    (line['percentage'], line['offset_months'],
                     line['fixed_day_of_month'], line['offset_days'],
                     line['discount_percent'], line['discount_days'],
                     line['description'], line_id))
                print('  ~ UPDATE payment_term_line %s/%s'
                      % (PAYMENT_TERM['code'], line['seq']))
            else:
                conn.execute(
                    'INSERT INTO payment_term_lines '
                    '(payment_term_id, seq, percentage, offset_months, '
                    ' fixed_day_of_month, offset_days, discount_percent, '
                    ' discount_days, description) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (term_id, line['seq'], line['percentage'], line['offset_months'],
                     line['fixed_day_of_month'], line['offset_days'],
                     line['discount_percent'], line['discount_days'],
                     line['description']))
                print('  + INSERT payment_term_line %s/%s'
                      % (PAYMENT_TERM['code'], line['seq']))

        # 4) 销售组织职能
        if not _table_exists(conn, 'org_functions'):
            print('[v120] 缺少 org_functions，跳过组织职能种子')
        else:
            org_id = _org_id_by_code(conn, SALES_ORG_CODE)
            if not org_id:
                print('  ! 跳过职能：组织 %s 不存在' % SALES_ORG_CODE)
            else:
                fn_id = _org_function_id(conn, org_id, SALES_FUNCTION)
                if fn_id:
                    conn.execute(
                        'UPDATE org_functions SET is_primary = 1 WHERE id = ?', (fn_id,))
                    print('  ~ UPDATE org_function %s/%s'
                          % (SALES_ORG_CODE, SALES_FUNCTION))
                else:
                    conn.execute(
                        'INSERT INTO org_functions '
                        '(org_id, function_type, is_primary, effective_from, '
                        ' effective_to, created_at) '
                        "VALUES (?, ?, 1, NULL, NULL, datetime('now'))",
                        (org_id, SALES_FUNCTION))
                    print('  + INSERT org_function %s/%s'
                          % (SALES_ORG_CODE, SALES_FUNCTION))

        conn.commit()
        print('[v120] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v120] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v120 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        missing = [c for c, *_ in SEQUENCES if not _sequence_id(conn, c)]
        if missing:
            print('[v120 verify] FAIL: 编号序列缺失 %s' % missing)
            return False

        bad_bindings = []
        for type_code, seq_code in TYPE_SEQUENCE_BINDINGS:
            type_id = _header_type_id(conn, type_code)
            seq_id = _sequence_id(conn, seq_code)
            if not type_id:
                bad_bindings.append('%s(类型缺失)' % type_code)
                continue
            row = conn.execute(
                'SELECT number_sequence_id FROM type_definitions WHERE id = ?',
                (type_id,)).fetchone()
            if not row or not seq_id or row[0] != seq_id:
                bad_bindings.append('%s→%s' % (type_code, seq_code))
        if bad_bindings:
            print('[v120 verify] FAIL: 类型未挂序列 %s' % bad_bindings)
            return False

        term_id = _payment_term_id(conn, PAYMENT_TERM['code'])
        if not term_id:
            print('[v120 verify] FAIL: 付款条件 %s 缺失' % PAYMENT_TERM['code'])
            return False
        if not _payment_term_line_id(conn, term_id, PAYMENT_TERM_LINE['seq']):
            print('[v120 verify] FAIL: %s 分期行缺失' % PAYMENT_TERM['code'])
            return False
        total = conn.execute(
            'SELECT COALESCE(SUM(percentage), 0) FROM payment_term_lines '
            'WHERE payment_term_id = ?', (term_id,)).fetchone()[0]
        if abs(float(total) - 100.0) > 0.01:
            print('[v120 verify] FAIL: %s 分期合计 %.4f ≠ 100'
                  % (PAYMENT_TERM['code'], float(total)))
            return False

        org_id = _org_id_by_code(conn, SALES_ORG_CODE)
        if not org_id or not _org_function_id(conn, org_id, SALES_FUNCTION):
            print('[v120 verify] FAIL: %s 缺少 %s 职能'
                  % (SALES_ORG_CODE, SALES_FUNCTION))
            return False

        print('[v120 verify] OK: 2 条序列 + TA/RE 已挂序列 + NET30(1 行 100%%) '
              '+ 销售组织 sales 职能')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v120 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        # 先解除类型挂接，避免删序列时被真外键拦住
        for type_code, seq_code in TYPE_SEQUENCE_BINDINGS:
            type_id = _header_type_id(conn, type_code)
            if type_id:
                conn.execute(
                    'UPDATE type_definitions SET number_sequence_id = NULL WHERE id = ?',
                    (type_id,))
                print('  ~ UNBIND type %s' % type_code)

        for code, *_ in SEQUENCES:
            seq_id = _sequence_id(conn, code)
            if seq_id:
                conn.execute('DELETE FROM number_sequences WHERE id = ?', (seq_id,))
                print('  - DELETE sequence %s' % code)

        term_id = _payment_term_id(conn, PAYMENT_TERM['code'])
        if term_id:
            line_id = _payment_term_line_id(conn, term_id, PAYMENT_TERM_LINE['seq'])
            if line_id:
                conn.execute(
                    'DELETE FROM payment_term_lines WHERE id = ?', (line_id,))
                print('  - DELETE payment_term_line %s' % PAYMENT_TERM['code'])
            remain = conn.execute(
                'SELECT COUNT(*) FROM payment_term_lines WHERE payment_term_id = ?',
                (term_id,)).fetchone()[0]
            if remain:
                print('  ! 付款条件 %s 仍有 %d 条分期行，保留头'
                      % (PAYMENT_TERM['code'], remain))
            else:
                conn.execute('DELETE FROM payment_terms WHERE id = ?', (term_id,))
                print('  - DELETE payment_term %s' % PAYMENT_TERM['code'])

        org_id = _org_id_by_code(conn, SALES_ORG_CODE)
        if org_id:
            fn_id = _org_function_id(conn, org_id, SALES_FUNCTION)
            if fn_id:
                conn.execute('DELETE FROM org_functions WHERE id = ?', (fn_id,))
                print('  - DELETE org_function %s/%s'
                      % (SALES_ORG_CODE, SALES_FUNCTION))

        conn.commit()
        print('[v120 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v120 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else get_meta_db_path()
    if '--rollback' in sys.argv:
        rollback(db)
    else:
        migrate(db)
        verify(db)
