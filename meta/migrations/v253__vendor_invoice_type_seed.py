# -*- coding: utf-8 -*-
"""[v253 2026-11-11] 采购发票对象模型（W2：类型 / 序列 / 控制参数种子）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §3.1 单据类型与方向 / §5.1 匹配模式 / §6.1 容差参数 / §13 实施波次 W2

范围:
  1. type_definitions 4 个 header 类型（scope_bo='vendor_invoice'）:
       VENDOR_INVOICE        采购发票       invoice      +1  is_default=1  VI   → 反转 VENDOR_CREDIT_MEMO
       VENDOR_CREDIT_MEMO    采购贷项凭证   credit_memo  -1               VCM  → 反转 VENDOR_DEBIT_MEMO
       VENDOR_DEBIT_MEMO     采购借项通知单 debit_memo   +1               VDM  → 反转 VENDOR_CREDIT_MEMO
       VENDOR_INVOICE_CANCEL 采购发票取消单 cancellation -1               VIC  → 反转 VENDOR_INVOICE
     不变量: 反转类型 direction 与原类型相反。
     说明: 默认类型 VENDOR_INVOICE 的 reversal_type_id 指向 VENDOR_CREDIT_MEMO，
           红冲引擎据此定位红字单据类型（方向必须为 -1）。
  2. number_sequences 4 条（VI / VCM / VDM / VIC）
  3. control_parameter_defs 6 条:
       vi_match_mode（domain=procurement，enum，默认 gr_based）
       5 个容差（domain=tolerance，decimal）
  4. 本迁移只写定义与种子，不建表（表由 v252 + schema yaml 负责）

幂等:
  类型 / 序列按 (scope_bo, level, code) / code 先查后插；
  参数按 code 先查后插；重复执行打印 [SKIP]。

回滚:
  删 6 参数 → 4 序列 → 4 类型（先解除 reversal 引用）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v253__vendor_invoice_type_seed'

TYPE_TABLE = 'type_definitions'
SEQUENCE_TABLE = 'number_sequences'
PARAM_TABLE = 'control_parameter_defs'

SCOPE_BO = 'vendor_invoice'
LEVEL = 'header'

#: 4 个采购发票头类型
VENDOR_TYPES = (
    {
        'code': 'VENDOR_INVOICE',
        'name': '采购发票',
        'document_category': 'invoice',
        'document_role': 'invoice',
        'direction': 1,
        'is_default': 1,
        'sequence': 'VI',
        'reversal_of': 'VENDOR_CREDIT_MEMO',
        'description': '标准采购发票：正向入账，采购发票默认类型；红冲生成采购贷项凭证',
    },
    {
        'code': 'VENDOR_CREDIT_MEMO',
        'name': '采购贷项凭证',
        'document_category': 'credit_memo',
        'document_role': 'credit_memo',
        'direction': -1,
        'is_default': 0,
        'sequence': 'VCM',
        'reversal_of': 'VENDOR_DEBIT_MEMO',
        'description': '供应商贷项：冲减应付，direction=-1，红冲对应借项通知单',
    },
    {
        'code': 'VENDOR_DEBIT_MEMO',
        'name': '采购借项通知单',
        'document_category': 'debit_memo',
        'document_role': 'debit_memo',
        'direction': 1,
        'is_default': 0,
        'sequence': 'VDM',
        'reversal_of': 'VENDOR_CREDIT_MEMO',
        'description': '采购借项：追加应付/费用，direction=1，红冲对应贷项凭证',
    },
    {
        'code': 'VENDOR_INVOICE_CANCEL',
        'name': '采购发票取消单',
        'document_category': 'cancellation',
        'document_role': 'cancellation',
        'direction': -1,
        'is_default': 0,
        'sequence': 'VIC',
        'reversal_of': 'VENDOR_INVOICE',
        'description': '发票取消：红冲已过账采购发票，direction=-1',
    },
)

#: (code, name, pattern) —— date_field 统一 invoice_date
SEQUENCES = (
    ('VI', '采购发票编号', 'VI-{DATE:yyyymm}-{SEQ:5}'),
    ('VCM', '采购贷项凭证编号', 'VCM-{DATE:yyyymm}-{SEQ:5}'),
    ('VDM', '采购借项通知单编号', 'VDM-{DATE:yyyymm}-{SEQ:5}'),
    ('VIC', '采购发票取消单编号', 'VIC-{DATE:yyyymm}-{SEQ:5}'),
)

SEQUENCE_DATE_FIELD = 'invoice_date'

#: (code, name, domain, value_type, default_value, tolerance_direction, tolerance_basis, description)
PARAMS = (
    (
        'vi_match_mode', '采购发票匹配模式', 'procurement', 'enum', 'gr_based',
        None, None,
        'po_based=按采购订单行匹配 / gr_based=按收货行匹配',
    ),
    (
        'vi_price_tolerance', '采购发票价格容差', 'tolerance', 'decimal', '0.00',
        'over', 'percent',
        '单价高于订单价的允许上限（百分比）；超出则匹配异常',
    ),
    (
        'vi_qty_tolerance_receipt', '采购发票收货数量容差', 'tolerance', 'decimal', '0.00',
        'over', 'percent',
        '开票数量高于可开票收货量的允许上限（百分比）',
    ),
    (
        'vi_qty_tolerance_order', '采购发票订单数量容差', 'tolerance', 'decimal', '0.00',
        'over', 'percent',
        'po_based 模式下开票数量高于订单量的允许上限（百分比）',
    ),
    (
        'vi_amount_tolerance_abs', '采购发票金额绝对容差', 'tolerance', 'decimal', '0.00',
        'both', 'absolute',
        '行金额净额差异的绝对允许值（正负双向）',
    ),
    (
        'vi_rounding_tolerance_abs', '采购发票舍入容差', 'tolerance', 'decimal', '0.01',
        'both', 'absolute',
        '头级金额舍入差异的绝对允许值（正负双向）',
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


def _index_exists(conn, index):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
        [index]).fetchone()
    return row is not None


def _type_row(conn, code):
    return conn.execute(
        'SELECT id, document_role, direction, is_default, reversal_type_id '
        'FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
        % TYPE_TABLE, [SCOPE_BO, LEVEL, code]).fetchone()


def _sequence_id(conn, code):
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % SEQUENCE_TABLE, [code]).fetchone()
    return int(row[0]) if row else None


def _param_id(conn, code):
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % PARAM_TABLE, [code]).fetchone()
    return int(row[0]) if row else None


# ------------------------------------------------------------------- sequences

def _do_sequences(conn):
    """4 条编号序列；返回 {code: id}。"""
    if not _table_exists(conn, SEQUENCE_TABLE):
        print('[v253] SKIP: %s 表不存在（未建序列）' % SEQUENCE_TABLE)
        return {}
    ids = {}
    for code, name, pattern in SEQUENCES:
        existing = _sequence_id(conn, code)
        if existing:
            conn.execute(
                'UPDATE %s SET name = ?, pattern = ?, date_field = ?, '
                "status = 'active' WHERE id = ?" % SEQUENCE_TABLE,
                [name, pattern, SEQUENCE_DATE_FIELD, existing])
            ids[code] = existing
            print('[v253] SKIP: 序列 %s 已存在（已对齐 pattern）' % code)
            continue
        cur = conn.execute(
            'INSERT INTO %s (code, name, pattern, date_field, start_value, '
            "on_exhaust, status) VALUES (?, ?, ?, ?, 1, 'error', 'active')"
            % SEQUENCE_TABLE,
            [code, name, pattern, SEQUENCE_DATE_FIELD])
        ids[code] = int(cur.lastrowid)
        print('[v253] CREATE: 序列 %s' % code)
    return ids


# ----------------------------------------------------------------------- types

def _do_types(conn, sequence_ids):
    """4 个头类型；先插（不写反转引用），再统一回填 reversal_type_id。"""
    if not _table_exists(conn, TYPE_TABLE):
        print('[v253] SKIP: %s 表不存在（未建类型）' % TYPE_TABLE)
        return {}
    ids = {}
    for spec in VENDOR_TYPES:
        sequence_id = sequence_ids.get(spec['sequence'])
        existing = _type_row(conn, spec['code'])
        if existing:
            type_id = int(existing[0])
            conn.execute(
                'UPDATE %s SET name = ?, document_category = ?, '
                'document_role = ?, direction = ?, is_default = ?, '
                'number_sequence_id = ?, status = ?, description = ? '
                'WHERE id = ?' % TYPE_TABLE,
                [spec['name'], spec['document_category'], spec['document_role'],
                 spec['direction'], spec['is_default'], sequence_id, 'active',
                 spec['description'], type_id])
            ids[spec['code']] = type_id
            print('[v253] SKIP: 类型 %s 已存在（已对齐身份值）' % spec['code'])
            continue
        cur = conn.execute(
            'INSERT INTO %s (code, name, scope_bo, level, document_category, '
            'document_role, direction, is_default, number_sequence_id, status, '
            'description, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime(\'now\'))'
            % TYPE_TABLE,
            [spec['code'], spec['name'], SCOPE_BO, LEVEL,
             spec['document_category'], spec['document_role'], spec['direction'],
             spec['is_default'], sequence_id, 'active', spec['description']])
        ids[spec['code']] = int(cur.lastrowid)
        print('[v253] CREATE: 类型 %s' % spec['code'])
    for spec in VENDOR_TYPES:
        source_id = ids.get(spec['code'])
        target_id = ids.get(spec['reversal_of']) if spec['reversal_of'] else None
        if source_id is None:
            continue
        conn.execute('UPDATE %s SET reversal_type_id = ? WHERE id = ?'
                     % TYPE_TABLE, [target_id, source_id])
    print('[v253] 反转链已回填（invoice→credit / credit↔debit / cancel→invoice）')
    return ids


# ---------------------------------------------------------------------- params

def _do_params(conn):
    if not _table_exists(conn, PARAM_TABLE):
        print('[v253] SKIP: %s 表不存在（未建参数）' % PARAM_TABLE)
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
            print('[v253] SKIP: 参数 %s 已存在（已对齐定义）' % code)
            continue
        conn.execute(
            'INSERT INTO %s (code, name, domain, value_type, target_bo, '
            'default_value, tolerance_direction, tolerance_basis, status, '
            "description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, "
            "datetime('now'))" % PARAM_TABLE,
            [code, name, domain, value_type, SCOPE_BO, default_value,
             tolerance_direction, tolerance_basis, description])
        written += 1
        print('[v253] CREATE: 参数 %s' % code)
    return written


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v253] 开始: 采购发票类型 / 序列 / 控制参数种子')
    conn = _connect(db_path)
    try:
        sequence_ids = _do_sequences(conn)
        _do_types(conn, sequence_ids)
        _do_params(conn)
        conn.commit()
        print('[v253] 完成: 采购发票类型 / 序列 / 控制参数种子')
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
        for table in (TYPE_TABLE, SEQUENCE_TABLE, PARAM_TABLE):
            if not _table_exists(conn, table):
                problems.append('缺少表 %s' % table)
        if _table_exists(conn, TYPE_TABLE):
            rows = {}
            for spec in VENDOR_TYPES:
                row = _type_row(conn, spec['code'])
                if not row:
                    problems.append('缺少类型 %s' % spec['code'])
                    continue
                rows[spec['code']] = row
                if row[1] != spec['document_role']:
                    problems.append('类型 %s document_role=%r（期望 %r）'
                                    % (spec['code'], row[1], spec['document_role']))
                if int(row[2] or 0) != spec['direction']:
                    problems.append('类型 %s direction=%r（期望 %d）'
                                    % (spec['code'], row[2], spec['direction']))
                if int(row[3] or 0) != spec['is_default']:
                    problems.append('类型 %s is_default=%r（期望 %d）'
                                    % (spec['code'], row[3], spec['is_default']))
            for spec in VENDOR_TYPES:
                source = rows.get(spec['code'])
                if spec['reversal_of']:
                    target = rows.get(spec['reversal_of'])
                    if source and target:
                        if int(source[4] or 0) != int(target[0]):
                            problems.append('类型 %s reversal_type_id 未指向 %s'
                                            % (spec['code'], spec['reversal_of']))
                        if int(source[2] or 0) == int(target[2] or 0):
                            problems.append('反转链 %s↔%s direction 未相反'
                                            % (spec['code'], spec['reversal_of']))
            # 默认类型唯一：同一 (scope_bo, level, document_role) 最多 1 条
            conflicts = conn.execute(
                'SELECT document_role, COUNT(*) FROM %s '
                "WHERE scope_bo = ? AND level = ? AND is_default = 1 "
                'GROUP BY document_role HAVING COUNT(*) > 1' % TYPE_TABLE,
                [SCOPE_BO, LEVEL]).fetchall()
            for role, count in conflicts:
                problems.append('默认类型冲突: %s/%s 有 %d 条 is_default=1'
                                % (SCOPE_BO, role, count))
        if _table_exists(conn, SEQUENCE_TABLE):
            for code, _name, pattern in SEQUENCES:
                row = conn.execute(
                    'SELECT pattern, status FROM %s WHERE code = ?'
                    % SEQUENCE_TABLE, [code]).fetchone()
                if not row:
                    problems.append('缺少序列 %s' % code)
                elif row[0] != pattern or row[1] != 'active':
                    problems.append('序列 %s 配置漂移 (pattern=%r status=%r)'
                                    % (code, row[0], row[1]))
        if _table_exists(conn, PARAM_TABLE):
            for code in PARAM_CODES:
                row = conn.execute(
                    'SELECT domain, status FROM %s WHERE code = ?'
                    % PARAM_TABLE, [code]).fetchone()
                if not row:
                    problems.append('缺少参数 %s' % code)
                elif row[1] != 'active':
                    problems.append('参数 %s status=%r' % (code, row[1]))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v253] FAIL: %s' % problem)
        return False
    print('[v253] PASS: 4 类型 / 4 序列 / 6 参数齐备且反转链方向正确')
    return True


# ------------------------------------------------------------------ rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v253] 开始: 回滚采购发票类型 / 序列 / 控制参数种子')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, PARAM_TABLE):
            placeholders = ', '.join('?' for _ in PARAM_CODES)
            conn.execute('DELETE FROM %s WHERE code IN (%s)'
                         % (PARAM_TABLE, placeholders), list(PARAM_CODES))
        if _table_exists(conn, TYPE_TABLE):
            # 先断开反转指针（指向本批类型的所有引用），再按 code 删除
            conn.execute(
                'UPDATE %s SET reversal_type_id = NULL WHERE scope_bo = ? '
                'AND level = ? AND reversal_type_id IN '
                '(SELECT id FROM %s WHERE scope_bo = ? AND level = ?)'
                % (TYPE_TABLE, TYPE_TABLE), [SCOPE_BO, LEVEL, SCOPE_BO, LEVEL])
            for spec in VENDOR_TYPES:
                conn.execute(
                    'DELETE FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
                    % TYPE_TABLE, [SCOPE_BO, LEVEL, spec['code']])
        if _table_exists(conn, SEQUENCE_TABLE):
            for code, _name, _pattern in SEQUENCES:
                conn.execute('DELETE FROM %s WHERE code = ?'
                             % SEQUENCE_TABLE, [code])
        conn.commit()
        print('[v253] 完成: 已删除采购发票种子（参数 / 类型 / 序列）')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()