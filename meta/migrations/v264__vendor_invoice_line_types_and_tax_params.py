# -*- coding: utf-8 -*-
"""[v264 2026-11-13] 采购发票对象模型（W6：5 条行类型 + 税/费用参数）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §22.6 行类型 / §22.10 控制参数与类型种子 / §22.2 直录税额校验

范围:
  1. type_definitions 5 个 line 类型（scope_bo='vendor_invoice', level='line'）:
       VI_LINE_GOODS      物料行   material  delivery_relevant=1  is_default=1
       VI_LINE_SERVICE    服务行   service   delivery_relevant=0
       VI_LINE_FREIGHT    运费行   freight   delivery_relevant=0  （费用行）
       VI_LINE_SURCHARGE  附加费行 misc      delivery_relevant=0  （费用行）
       VI_LINE_DISCOUNT   折扣行   misc      delivery_relevant=0  （费用行）
     费用行（freight / surcharge / discount）不写 doc_flow 边、不参与数量匹配。
  2. control_parameter_defs 4 条:
       vi_tax_mode              enum    line_direct
       vi_tax_tolerance_abs     decimal 0.01  both/absolute
       vi_freight_tolerance_abs decimal 0.00  both/absolute
       vi_po_tax_compare        bool    false（预留）

幂等:
  类型按 (scope_bo, level, code) 先查后插；参数按 code 先查后插；重复执行打印 [SKIP]。

回滚:
  删 4 参数 → 5 行类型（不涉及反转链）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v264__vendor_invoice_line_types_and_tax_params'

TYPE_TABLE = 'type_definitions'
PARAM_TABLE = 'control_parameter_defs'

SCOPE_BO = 'vendor_invoice'
LEVEL = 'line'

LINE_TYPES = (
    {
        'code': 'VI_LINE_GOODS',
        'name': '物料行',
        'line_category': 'material',
        'delivery_relevant': 1,
        'is_default': 1,
        'description': '按采购订单 / 收货匹配的物料或服务明细行（采购发票默认行类型）',
    },
    {
        'code': 'VI_LINE_SERVICE',
        'name': '服务行',
        'line_category': 'service',
        'delivery_relevant': 0,
        'is_default': 0,
        'description': '无收货锚点的服务类明细行，按订单行匹配',
    },
    {
        'code': 'VI_LINE_FREIGHT',
        'name': '运费行',
        'line_category': 'freight',
        'delivery_relevant': 0,
        'is_default': 0,
        'description': '费用行：不挂收货/订单锚点，不写 doc_flow 边，不参与数量匹配',
    },
    {
        'code': 'VI_LINE_SURCHARGE',
        'name': '附加费行',
        'line_category': 'misc',
        'delivery_relevant': 0,
        'is_default': 0,
        'description': '费用行：与采购订单 header_surcharge_amount 按容差对账',
    },
    {
        'code': 'VI_LINE_DISCOUNT',
        'name': '折扣行',
        'line_category': 'misc',
        'delivery_relevant': 0,
        'is_default': 0,
        'description': '费用行：净额为负的折扣，与采购订单 header_discount_amount 按容差对账',
    },
)

PARAMS = (
    (
        'vi_tax_mode', '采购发票税模式', 'procurement', 'enum', 'line_direct',
        None, None,
        'line_direct=直录税额并按容差校验 / rate_calc=按税率计算税额',
    ),
    (
        'vi_tax_tolerance_abs', '采购发票税额绝对容差', 'tolerance', 'decimal', '0.01',
        'both', 'absolute',
        '直录税额与按税率计算税额的绝对允许差额（正负双向）',
    ),
    (
        'vi_freight_tolerance_abs', '采购发票费用行绝对容差', 'tolerance', 'decimal', '0.00',
        'both', 'absolute',
        '费用行合计与采购订单附加费/折扣的绝对允许差额（正负双向）',
    ),
    (
        'vi_po_tax_compare', '采购发票与订单税额比对', 'procurement', 'bool', 'false',
        None, None,
        '启用后在匹配阶段比对订单税额与发票税额（预留开关）',
    ),
)

LINE_TYPE_CODES = tuple(spec['code'] for spec in LINE_TYPES)
PARAM_CODES = tuple(param[0] for param in PARAMS)


# --------------------------------------------------------------------- helpers

def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return bool(row)


def _columns(conn, table):
    return {row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)}


def _type_row(conn, code):
    return conn.execute(
        'SELECT id, is_default, status FROM %s '
        'WHERE scope_bo = ? AND level = ? AND code = ?'
        % TYPE_TABLE, [SCOPE_BO, LEVEL, code]).fetchone()


def _param_id(conn, code):
    row = conn.execute('SELECT id FROM %s WHERE code = ?' % PARAM_TABLE,
                       [code]).fetchone()
    return int(row[0]) if row else None


# -------------------------------------------------------------------- migrate

def _do_types(conn):
    if not _table_exists(conn, TYPE_TABLE):
        print('[v264] SKIP: %s 表不存在（未建类型）' % TYPE_TABLE)
        return 0
    columns = _columns(conn, TYPE_TABLE)
    written = 0
    for spec in LINE_TYPES:
        existing = _type_row(conn, spec['code'])
        fields = ['code', 'name', 'scope_bo', 'level', 'is_default', 'status']
        values = [spec['code'], spec['name'], SCOPE_BO, LEVEL,
                  spec['is_default'], 'active']
        if 'line_category' in columns:
            fields.append('line_category')
            values.append(spec['line_category'])
        if 'delivery_relevant' in columns:
            fields.append('delivery_relevant')
            values.append(spec['delivery_relevant'])
        if 'description' in columns:
            fields.append('description')
            values.append(spec['description'])
        if existing:
            assignments = ', '.join('%s = ?' % field
                                     for field in fields if field not in ('code',))
            conn.execute(
                'UPDATE %s SET %s WHERE id = ?' % (TYPE_TABLE, assignments),
                values[1:] + [int(existing[0])])
            print('[v264] SKIP: 行类型 %s 已存在（已对齐定义）' % spec['code'])
            continue
        placeholders = ', '.join('?' for _ in fields)
        if 'created_at' in columns:
            fields.append('created_at')
            placeholders += ", datetime('now')"
        conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (TYPE_TABLE, ', '.join(fields), placeholders), values)
        written += 1
        print('[v264] CREATE: 行类型 %s' % spec['code'])
    return written


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


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v264] 开始: 采购发票行类型 / 税与费用参数种子')
    conn = _connect(db_path)
    try:
        _do_types(conn)
        _do_params(conn)
        conn.commit()
        print('[v264] 完成: 采购发票行类型 / 税与费用参数种子')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------- verify

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
                row = _type_row(conn, spec['code'])
                if not row:
                    problems.append('缺少行类型 %s' % spec['code'])
                elif int(row[1] or 0) != spec['is_default']:
                    problems.append('行类型 %s is_default=%r（期望 %d）'
                                    % (spec['code'], row[1], spec['is_default']))
                elif row[2] != 'active':
                    problems.append('行类型 %s status=%r' % (spec['code'], row[2]))
            conflicts = conn.execute(
                'SELECT COUNT(*) FROM %s WHERE scope_bo = ? AND level = ? '
                'AND is_default = 1' % TYPE_TABLE, [SCOPE_BO, LEVEL]).fetchone()
            if conflicts and int(conflicts[0] or 0) > 1:
                problems.append('默认行类型冲突: %s/%s 有 %s 条 is_default=1'
                                % (SCOPE_BO, LEVEL, conflicts[0]))
        if _table_exists(conn, PARAM_TABLE):
            for code, _name, _domain, _value_type, default_value, _d, _b, _desc in PARAMS:
                row = conn.execute(
                    'SELECT default_value, status FROM %s WHERE code = ?'
                    % PARAM_TABLE, [code]).fetchone()
                if not row:
                    problems.append('缺少参数 %s' % code)
                elif row[1] != 'active':
                    problems.append('参数 %s status=%r' % (code, row[1]))
                elif str(row[0]) != default_value:
                    problems.append('参数 %s default_value=%r（期望 %r）'
                                    % (code, row[0], default_value))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v264] FAIL: %s' % problem)
        return False
    print('[v264] PASS: 5 行类型 / 4 参数齐备')
    return True


# ------------------------------------------------------------------- rollback

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
            for code in LINE_TYPE_CODES:
                conn.execute(
                    'DELETE FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
                    % TYPE_TABLE, [SCOPE_BO, LEVEL, code])
        conn.commit()
        print('[v264] 完成: 已删除采购发票行类型 / 税与费用参数种子')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()