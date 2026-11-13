# -*- coding: utf-8 -*-
"""[v264 2026-11-13] 采购发票 W6：行类型 5 条 + 税与费用参数 4 条

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §22.2 规则 2/3（line_direct 税额容差）/ §22.6（费用行）/ §22.10（种子与参数）

范围:
  1. type_definitions 5 个 line 类型（scope_bo='vendor_invoice', level='line'）:
       VI_LINE_GOODS      物料行  material  is_default=1
       VI_LINE_SERVICE    服务行  service
       VI_LINE_FREIGHT    运费行  freight   ← 费用行
       VI_LINE_SURCHARGE  杂费行  misc      ← 费用行
       VI_LINE_DISCOUNT   折扣行  misc      ← 费用行
     费用行（freight/surcharge/discount）不写 doc_flow 边，见 match service。
  2. control_parameter_defs 4 条（target_bo='vendor_invoice'）:
       vi_tax_mode             enum    line_direct
       vi_tax_tolerance_abs    decimal 0.01
       vi_freight_tolerance_abs decimal 0.00
       vi_po_tax_compare       bool    false
  3. 本迁移只写种子，不建表。

幂等:
  类型按 (scope_bo, level, code) 先查后插；参数按 code 先查后插；
  重复执行将定义对齐到本迁移口径并打印 [SKIP]。

回滚:
  删 4 参数 → 5 类型。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v264__vendor_invoice_charge_line_seed'

TYPE_TABLE = 'type_definitions'
PARAM_TABLE = 'control_parameter_defs'

SCOPE_BO = 'vendor_invoice'
LEVEL = 'line'

#: 5 个采购发票行类型（费用行 3 个：freight / surcharge / discount）
LINE_TYPES = (
    {
        'code': 'VI_LINE_GOODS',
        'name': '物料行',
        'line_category': 'material',
        'delivery_relevant': 1,
        'is_default': 1,
        'description': '采购发票默认行类型：可挂采购订单 / 收货行锚点并参与三单匹配',
    },
    {
        'code': 'VI_LINE_SERVICE',
        'name': '服务行',
        'line_category': 'service',
        'delivery_relevant': 0,
        'is_default': 0,
        'description': '服务类采购行：参与匹配，但不产生收货履约',
    },
    {
        'code': 'VI_LINE_FREIGHT',
        'name': '运费行',
        'line_category': 'freight',
        'delivery_relevant': 0,
        'is_default': 0,
        'description': '费用行：不挂锚点、不参与数量/价格匹配、不写 doc_flow 边',
    },
    {
        'code': 'VI_LINE_SURCHARGE',
        'name': '杂费行',
        'line_category': 'misc',
        'delivery_relevant': 0,
        'is_default': 0,
        'description': '费用行：附加费/杂费，与 PO 头附加费按绝对容差核对',
    },
    {
        'code': 'VI_LINE_DISCOUNT',
        'name': '折扣行',
        'line_category': 'misc',
        'delivery_relevant': 0,
        'is_default': 0,
        'description': '费用行：负数金额的折扣/让价，不写 doc_flow 边',
    },
)

PARAMS = (
    (
        'vi_tax_mode', '采购发票税额模式', 'tax', 'enum', 'line_direct',
        None, None,
        'line_direct=税额直录并按 vi_tax_tolerance_abs 校验 / rate_calc=按税率计算覆盖',
    ),
    (
        'vi_tax_tolerance_abs', '采购发票税额绝对容差', 'tolerance', 'decimal', '0.01',
        'both', 'absolute',
        '直录税额与按税率计算值的绝对允许差额（正负双向）',
    ),
    (
        'vi_freight_tolerance_abs', '采购发票费用行绝对容差', 'tolerance', 'decimal', '0.00',
        'both', 'absolute',
        '费用行合计与采购订单头附加费/折扣的绝对允许差额',
    ),
    (
        'vi_po_tax_compare', '采购发票与订单税额比对', 'tax', 'bool', 'false',
        None, None,
        'true=发票行税额与采购订单行税额差异纳入匹配异常（默认关闭）',
    ),
)

PARAM_CODES = tuple(param[0] for param in PARAMS)


# --------------------------------------------------------------------- helpers

def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        [table]).fetchone()
    return bool(row)


def _line_type_row(conn, code):
    cols = [row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % TYPE_TABLE).fetchall()]
    select = ['id', 'is_default', 'status']
    if 'line_category' in cols:
        select.append('line_category')
    else:
        select.append("''")
    if 'delivery_relevant' in cols:
        select.append('delivery_relevant')
    else:
        select.append('NULL')
    return conn.execute(
        'SELECT %s FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
        % (', '.join(select), TYPE_TABLE),
        [SCOPE_BO, LEVEL, code]).fetchone()


def _param_id(conn, code):
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % PARAM_TABLE, [code]).fetchone()
    return None if not row else int(row[0])


# ---------------------------------------------------------------------- types

def _do_line_types(conn):
    if not _table_exists(conn, TYPE_TABLE):
        print('[v264] SKIP: %s 表不存在（未建类型）' % TYPE_TABLE)
        return 0
    cols = [row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % TYPE_TABLE).fetchall()]
    written = 0
    for spec in LINE_TYPES:
        existing = _line_type_row(conn, spec['code'])
        if existing:
            assignments = ['name = ?', 'is_default = ?', "status = 'active'",
                           'description = ?']
            values = [spec['name'], spec['is_default'], spec['description']]
            if 'line_category' in cols:
                assignments.insert(1, 'line_category = ?')
                values.insert(1, spec['line_category'])
            if 'delivery_relevant' in cols:
                assignments.append('delivery_relevant = ?')
                values.append(spec['delivery_relevant'])
            conn.execute(
                'UPDATE %s SET %s WHERE id = ?'
                % (TYPE_TABLE, ', '.join(assignments)),
                values + [int(existing[0])])
            print('[v264] SKIP: 行类型 %s 已存在（已对齐定义）' % spec['code'])
            continue
        columns = ['code', 'name', 'scope_bo', 'level', 'is_default', 'status',
                   'description']
        values = [spec['code'], spec['name'], SCOPE_BO, LEVEL, spec['is_default'],
                  'active', spec['description']]
        if 'line_category' in cols:
            columns.append('line_category')
            values.append(spec['line_category'])
        if 'delivery_relevant' in cols:
            columns.append('delivery_relevant')
            values.append(spec['delivery_relevant'])
        columns.append('created_at')
        conn.execute(
            'INSERT INTO %s (%s) VALUES (%s, datetime(\'now\'))'
            % (TYPE_TABLE, ', '.join(columns),
               ', '.join('?' for _ in values)),
            values)
        written += 1
        print('[v264] CREATE: 行类型 %s' % spec['code'])
    return written


# --------------------------------------------------------------------- params

def _do_params(conn):
    if not _table_exists(conn, PARAM_TABLE):
        print('[v264] SKIP: %s 表不存在（未建参数）' % PARAM_TABLE)
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
            print('[v264] SKIP: 参数 %s 已存在（已对齐定义）' % code)
            continue
        conn.execute(
            'INSERT INTO %s (code, name, domain, value_type, target_bo, '
            'default_value, tolerance_direction, tolerance_basis, status, '
            "description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, "
            "datetime('now'))" % PARAM_TABLE,
            [code, name, domain, value_type, SCOPE_BO, default_value,
             tolerance_direction, tolerance_basis, description])
        written += 1
        print('[v264] CREATE: 参数 %s' % code)
    return written


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v264] 开始: 采购发票行类型 / 税与费用参数种子')
    conn = _connect(db_path)
    try:
        _do_line_types(conn)
        _do_params(conn)
        conn.commit()
        print('[v264] 完成: 5 行类型 / 4 参数')
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
        for table in (TYPE_TABLE, PARAM_TABLE):
            if not _table_exists(conn, table):
                problems.append('缺少表 %s' % table)
        if _table_exists(conn, TYPE_TABLE):
            for spec in LINE_TYPES:
                row = _line_type_row(conn, spec['code'])
                if not row:
                    problems.append('缺少行类型 %s' % spec['code'])
                    continue
                if int(row[1] or 0) != spec['is_default']:
                    problems.append('行类型 %s is_default=%r（期望 %d）'
                                    % (spec['code'], row[1], spec['is_default']))
                if row[2] != 'active':
                    problems.append('行类型 %s status=%r' % (spec['code'], row[2]))
                if row[3] != spec['line_category']:
                    problems.append('行类型 %s line_category=%r（期望 %r）'
                                    % (spec['code'], row[3], spec['line_category']))
            conflicts = conn.execute(
                'SELECT COUNT(id) FROM %s WHERE scope_bo = ? AND level = ? '
                'AND is_default = 1' % TYPE_TABLE, [SCOPE_BO, LEVEL]).fetchone()
            if int(conflicts[0] or 0) != 1:
                problems.append('采购发票行类型 is_default=1 应唯一，实际 %d 条'
                                % int(conflicts[0] or 0))
        if _table_exists(conn, PARAM_TABLE):
            for code in PARAM_CODES:
                row = conn.execute(
                    'SELECT status, default_value FROM %s WHERE code = ?'
                    % PARAM_TABLE, [code]).fetchone()
                if not row:
                    problems.append('缺少参数 %s' % code)
                elif row[0] != 'active':
                    problems.append('参数 %s status=%r' % (code, row[0]))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v264] FAIL: %s' % problem)
        return False
    print('[v264] PASS: 5 行类型 / 4 参数齐备且默认行类型唯一')
    return True


# ------------------------------------------------------------------ rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v264] 开始: 回滚采购发票行类型 / 税与费用参数种子')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, PARAM_TABLE):
            placeholders = ', '.join('?' for _ in PARAM_CODES)
            conn.execute('DELETE FROM %s WHERE code IN (%s)'
                         % (PARAM_TABLE, placeholders), list(PARAM_CODES))
        if _table_exists(conn, TYPE_TABLE):
            for spec in LINE_TYPES:
                conn.execute(
                    'DELETE FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
                    % TYPE_TABLE, [SCOPE_BO, LEVEL, spec['code']])
        conn.commit()
        print('[v264] 完成: 已删除采购发票行类型 / 税与费用参数种子')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()