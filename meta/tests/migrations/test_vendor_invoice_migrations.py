# -*- coding: utf-8 -*-
"""W1–W6 采购发票迁移断言（v252–v255 / v258 / v259）。

覆盖：
  v252 表 / 列 / 禁止列 / 索引
  v253 4 类型 + 反转链 / 4 序列 / 6 控制参数
  v254 3 条流转规则（含 target_qty_field）+ 金额视图（既有数量视图 5 列不被改写）
  v255 17 权限 + 菜单挂载 + 旧自动菜单退役 + 无孤儿授权行
  v258 红冲字段 / 类型反指针回填 / 死权限清理（幂等）
  v259 调整单三列 / 调整单类型（reversal_type_id 为空）/ VIA 序列 / 幂等 / 回滚

迁移函数以「裸 sqlite3 连接」写入，因此本测试用最小平台底座表 + 临时库执行真实 migrate/verify。
底座建表与初始数据在 `meta/tests/factories/_vendor_invoice_migration_helpers.py`。

ALLOW_RAW_SQL: v258 需模拟「v255 尚未退役死权限」的存量库，直接 INSERT 两行权限与授权。
"""

import sqlite3

import pytest

from meta.core.doc_flow_rule_store import ensure_doc_flow_rule_table
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.sql_adapters import SQLiteAdapter
from meta.migrations import (
    v252__vendor_invoice_object as v252,
    v253__vendor_invoice_type_seed as v253,
    v254__vendor_invoice_doc_flow as v254,
    v255__vendor_invoice_actions as v255,
    v258__vendor_invoice_reversal as v258,
    v259__vendor_invoice_adjustment as v259,
    v260__vendor_invoice_amount_columns as v260,
    v261__vendor_invoice_match_mode_default as v261,
    v262__vendor_invoice_line_price_trace as v262,
    v263__vendor_invoice_pricing_mode_seed as v263,
    v264__vendor_invoice_charge_line_seed as v264,
)
from meta.tests.factories import _vendor_invoice_migration_helpers as MH


def _connect(path):
    return sqlite3.connect(str(path))


def _columns(conn, table):
    return {row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)}


def _index_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
        [name]).fetchone()
    return row is not None


@pytest.fixture()
def db_path(tmp_path):
    """最小平台底座 + doc_flow 依赖表。"""
    path = tmp_path / 'vendor_invoice_migrations.db'
    MH.make_base_db(path)

    ds = SQLiteAdapter()
    ds.connect(path=str(path))
    ensure_doc_flow_edge_tables(ds)
    ensure_doc_flow_rule_table(ds)
    ds.commit()
    return path


def test_v252_tables_columns_indexes(db_path):
    assert v252.migrate(db_path, skip_backup=True) is True
    assert v252.verify(db_path) is True

    conn = _connect(db_path)
    try:
        header_cols = _columns(conn, v252.HEADER_TABLE)
        assert v252.HEADER_COLUMNS <= header_cols
        assert not (v252.FORBIDDEN_HEADER_COLUMNS & header_cols)
        line_cols = _columns(conn, v252.LINE_TABLE)
        assert {'invoice_id', 'line_no', 'qty', 'unit_price',
                'match_status'} <= line_cols
        for index, _table, _ddl in v252.INDEXES:
            assert _index_exists(conn, index), '缺少索引 %s' % index
    finally:
        conn.close()


def test_v253_types_sequences_params(db_path):
    assert v253.migrate(db_path, skip_backup=True) is True
    assert v253.verify(db_path) is True

    conn = _connect(db_path)
    try:
        types = {row[0]: row for row in conn.execute(
            'SELECT code, direction, is_default, reversal_type_id '
            "FROM type_definitions WHERE scope_bo = 'vendor_invoice'")}
        assert set(types) == {'VENDOR_INVOICE', 'VENDOR_CREDIT_MEMO',
                              'VENDOR_DEBIT_MEMO', 'VENDOR_INVOICE_CANCEL'}
        assert types['VENDOR_INVOICE'][1] == 1          # direction
        assert types['VENDOR_INVOICE'][2] == 1          # is_default
        assert types['VENDOR_CREDIT_MEMO'][1] == -1
        assert types['VENDOR_INVOICE_CANCEL'][1] == -1
        assert types['VENDOR_DEBIT_MEMO'][3] is not None   # reversal -> credit
        assert types['VENDOR_INVOICE_CANCEL'][3] is not None

        seqs = {row[0] for row in conn.execute(
            "SELECT code FROM number_sequences "
            "WHERE code IN ('VI','VCM','VDM','VIC')")}
        assert seqs == {'VI', 'VCM', 'VDM', 'VIC'}

        params = {row[0]: (row[1], row[2]) for row in conn.execute(
            'SELECT code, domain, default_value FROM control_parameter_defs '
            "WHERE target_bo = 'vendor_invoice'")}
        assert params['vi_match_mode'] == ('procurement', 'gr_based')
        for code in ('vi_price_tolerance', 'vi_qty_tolerance_receipt',
                     'vi_qty_tolerance_order', 'vi_amount_tolerance_abs',
                     'vi_rounding_tolerance_abs'):
            assert code in params
    finally:
        conn.close()


def test_v254_rules_and_amount_view(db_path):
    assert v254.migrate(db_path, skip_backup=True) is True
    assert v254.verify(db_path) is True

    conn = _connect(db_path)
    try:
        rows = {row[0]: row for row in conn.execute(
            'SELECT rule_id, source_bo, target_bo, source_qty_field, '
            'target_qty_field, pool, status FROM doc_flow_rule')}
        assert set(rows) == set(v254.RULE_IDS)
        assert all(row[4] == 'qty' for row in rows.values())
        assert rows['receipt_line_to_vendor_invoice_line'][5] == 'ap_match'
        assert rows['po_schedule_to_vendor_invoice_line'][5] == 'billing'

        view = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = ?",
            [v254.AMOUNT_VIEW]).fetchone()
        assert view is not None
        qty_cols = [row[1] for row in conn.execute(
            'PRAGMA table_info(v_doc_flow_consumed_qty)')]
        assert len(qty_cols) == 5
    finally:
        conn.close()


def test_v255_permissions_menu_retirement(db_path):
    assert v255.migrate(db_path, skip_backup=True) is True
    assert v255.verify(db_path) is True

    conn = _connect(db_path)
    try:
        codes = {row[0] for row in conn.execute('SELECT code FROM permissions')}
        assert set(v255.PERMISSION_CODES) <= codes
        assert len(v255.PERMISSION_CODES) == 17

        row = conn.execute(
            'SELECT parent_menu, is_active FROM menus WHERE menu_code = ?',
            [v255.MENU_CODE]).fetchone()
        assert row == (v255.ROOT_MENU_CODE, 1)

        for code in MH.RETIRED_MENU_CODES:
            retired = conn.execute(
                'SELECT is_active FROM menus WHERE menu_code = ?',
                [code]).fetchone()
            assert retired is not None and int(retired[0] or 0) == 0
            # 退役菜单仍保留在 menus（只是停用），因此不应产生孤儿行
            orphan = conn.execute(
                'SELECT COUNT(*) FROM menu_permissions '
                'WHERE menu_code = ? AND menu_code NOT IN '
                '(SELECT menu_code FROM menus)',
                [code]).fetchone()
            assert int(orphan[0]) == 0

        granted = conn.execute(
            'SELECT COUNT(*) FROM permission_set_permissions '
            'WHERE permission_id IN (SELECT id FROM permissions WHERE code LIKE ?)',
            ['vendor_invoice%']).fetchone()
        assert int(granted[0]) == 2 * len(v255.PERMISSION_CODES)
    finally:
        conn.close()


def test_v258_reversal_column_pointer_and_dead_permissions(db_path):
    assert v252.migrate(db_path, skip_backup=True) is True
    assert v253.migrate(db_path, skip_backup=True) is True
    assert v255.migrate(db_path, skip_backup=True) is True

    conn = _connect(db_path)
    try:
        # 模拟 v255 尚未退役死权限的存量库（v255 现版本已不再播种）
        def _clone_row(table, source_where, overrides):
            cols = [r[1] for r in conn.execute('PRAGMA table_info(%s)' % table)]
            row = conn.execute(
                'SELECT * FROM %s WHERE %s' % (table, source_where)).fetchone()
            assert row is not None
            data = dict(zip(cols, row))
            data.update(overrides)
            data.pop('id', None)
            keys = [k for k in cols if k != 'id']
            conn.execute(
                'INSERT INTO %s (%s) VALUES (%s)'
                % (table, ','.join(keys), ','.join('?' for _ in keys)),
                [data.get(k) for k in keys])

        for code in v258.DEAD_PERMISSION_CODES:
            _clone_row('permissions', "code = 'vendor_invoice:cancel'", {'code': code})
        _clone_row(
            'permission_set_permissions',
            "permission_code = 'vendor_invoice:cancel'",
            {'permission_code': v258.DEAD_PERMISSION_CODES[0]})
        conn.commit()
        codes = {row[0] for row in conn.execute('SELECT code FROM permissions')}
        assert set(v258.DEAD_PERMISSION_CODES) <= codes
    finally:
        conn.close()

    assert v258.migrate(db_path, skip_backup=True) is True
    assert v258.verify(db_path) is True
    # 幂等：重复执行不报错、不重复加列
    assert v258.migrate(db_path, skip_backup=True) is True
    assert v258.verify(db_path) is True

    conn = _connect(db_path)
    try:
        assert v258.REASON_COLUMN in _columns(conn, v258.HEADER_TABLE)
        row = conn.execute(
            'SELECT r.code FROM type_definitions t '
            'JOIN type_definitions r ON r.id = t.reversal_type_id '
            "WHERE t.code = 'VENDOR_INVOICE' AND t.scope_bo = 'vendor_invoice'"
        ).fetchone()
        assert row == ('VENDOR_CREDIT_MEMO',)
        placeholders = ','.join('?' for _ in v258.DEAD_PERMISSION_CODES)
        left = conn.execute(
            'SELECT COUNT(*) FROM permissions WHERE code IN (%s)' % placeholders,
            list(v258.DEAD_PERMISSION_CODES)).fetchone()[0]
        assert int(left) == 0
        grants = conn.execute(
            'SELECT COUNT(*) FROM permission_set_permissions '
            'WHERE permission_code IN (%s)' % placeholders,
            list(v258.DEAD_PERMISSION_CODES)).fetchone()[0]
        assert int(grants) == 0
    finally:
        conn.close()


def test_v259_adjustment_columns_phase2(db_path):
    """调整单三列 / 类型（不可红冲）/ VIA 序列 / 幂等 / 回滚。"""
    assert v252.migrate(db_path, skip_backup=True) is True
    assert v253.migrate(db_path, skip_backup=True) is True
    assert v259.migrate(db_path, skip_backup=True) is True
    assert v259.verify(db_path) is True

    # 幂等：二次执行不重复建类型 / 序列
    assert v259.migrate(db_path, skip_backup=True) is True
    assert v259.verify(db_path) is True

    conn = _connect(db_path)
    try:
        columns = _columns(conn, v259.HEADER_TABLE)
        for column, _ in v259.COLUMNS:
            assert column in columns
        assert _index_exists(conn, v259.INDEX_NAME), '缺少索引 %s' % v259.INDEX_NAME
        rows = conn.execute(
            'SELECT document_category, document_role, direction, is_default, '
            'number_sequence_id, reversal_type_id, status '
            'FROM type_definitions WHERE scope_bo = ? AND level = ? AND code = ?',
            [v259.SCOPE_BO, v259.LEVEL, v259.TYPE_CODE]).fetchall()
        assert len(rows) == 1
        category, role, direction, is_default, sequence_id, reversal_id, status = rows[0]
        assert category == 'adjustment'
        assert role == 'adjustment'
        assert int(direction) == 1
        assert int(is_default) == 0
        assert sequence_id
        assert reversal_id is None, '调整单不进红冲引擎'
        assert status == 'active'
        sequence = conn.execute(
            'SELECT pattern, date_field FROM number_sequences WHERE code = ?',
            [v259.SEQUENCE_CODE]).fetchone()
        assert sequence == (v259.SEQUENCE_PATTERN, v259.SEQUENCE_DATE_FIELD)
    finally:
        conn.close()

    assert v259.rollback(db_path) is True
    conn = _connect(db_path)
    try:
        assert conn.execute(
            'SELECT COUNT(*) FROM type_definitions WHERE code = ?',
            [v259.TYPE_CODE]).fetchone()[0] == 0
        assert conn.execute(
            'SELECT COUNT(*) FROM number_sequences WHERE code = ?',
            [v259.SEQUENCE_CODE]).fetchone()[0] == 0
        # 列保留（SQLite 老版本不支持 DROP COLUMN），值已清空
        columns = _columns(conn, v259.HEADER_TABLE)
        for column, _ in v259.COLUMNS:
            assert column in columns
        assert conn.execute(
            'SELECT COUNT(*) FROM %s WHERE %s IS NOT NULL'
            % (v259.HEADER_TABLE, v259.COLUMNS[0][0])).fetchone()[0] == 0
        assert not _index_exists(conn, v259.INDEX_NAME), '回滚应删除索引'
    finally:
        conn.close()


def test_v260_amount_columns(db_path):
    """金额链路两列 / 幂等 / 回滚清值（列保留）。"""
    assert v252.migrate(db_path, skip_backup=True) is True
    assert v260.migrate(db_path, skip_backup=True) is True
    assert v260.verify(db_path) is True

    # 幂等：二次执行不报错
    assert v260.migrate(db_path, skip_backup=True) is True
    assert v260.verify(db_path) is True

    conn = _connect(db_path)
    try:
        for table, columns in ((v260.HEADER_TABLE, v260.HEADER_COLUMNS),
                               (v260.LINE_TABLE, v260.LINE_COLUMNS)):
            existing = _columns(conn, table)
            for column, _ in columns:
                assert column in existing, '缺少列 %s.%s' % (table, column)
    finally:
        conn.close()

    assert v260.rollback(db_path) is True
    conn = _connect(db_path)
    try:
        assert conn.execute(
            'SELECT COUNT(*) FROM %s WHERE supplier_gross_amount IS NOT NULL'
            % v260.HEADER_TABLE).fetchone()[0] == 0
        assert conn.execute(
            'SELECT COUNT(*) FROM %s WHERE tax_rate_percent IS NOT NULL'
            % v260.LINE_TABLE).fetchone()[0] == 0
        # 列保留（SQLite 老版本不支持 DROP COLUMN）
        assert 'supplier_gross_amount' in _columns(conn, v260.HEADER_TABLE)
        assert 'tax_rate_percent' in _columns(conn, v260.LINE_TABLE)
    finally:
        conn.close()


def test_v261_match_mode_default_po_based(db_path):
    """vi_match_mode 默认值 gr_based → po_based / 幂等 / 回滚。"""
    assert v252.migrate(db_path, skip_backup=True) is True
    assert v253.migrate(db_path, skip_backup=True) is True
    assert v261.migrate(db_path, skip_backup=True) is True
    assert v261.verify(db_path) is True

    conn = _connect(db_path)
    try:
        value = conn.execute(
            'SELECT default_value FROM control_parameter_defs WHERE code = ?',
            [v261.PARAM_CODE]).fetchone()[0]
        assert value == v261.DEFAULT_NEW
    finally:
        conn.close()

    assert v261.rollback(db_path) is True
    conn = _connect(db_path)
    try:
        value = conn.execute(
            'SELECT default_value FROM control_parameter_defs WHERE code = ?',
            [v261.PARAM_CODE]).fetchone()[0]
        assert value == v261.DEFAULT_OLD
    finally:
        conn.close()


def test_v262_line_price_trace_backfill_and_rollback(db_path):
    """price_source / price_trace 两列 / 历史回填口径 / 幂等 / 回滚清值。"""
    assert v252.migrate(db_path, skip_backup=True) is True

    conn = _connect(db_path)
    try:
        header_cols = (
            'invoice_no, document_type_id, document_category, invoice_date, '
            'supplier_account_id, supplier_party_id, currency_id, org_id')
        conn.execute(
            'INSERT INTO vendor_invoices (%s) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
            % header_cols,
            ['VI-V262', 1, 'invoice', '2026-11-13', 1, 1, 1, 1])
        conn.execute(
            'INSERT INTO vendor_invoices (%s) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
            % header_cols,
            ['VIA-V262', 1, 'adjustment', '2026-11-13', 1, 1, 1, 1])
        line_sql = (
            'INSERT INTO vendor_invoice_lines '
            '(invoice_id, line_no, order_line_id) VALUES (?, ?, ?)')
        conn.execute(line_sql, [1, 1, 7101])   # PO 锚
        conn.execute(line_sql, [1, 2, None])   # 无锚
        conn.execute(line_sql, [2, 1, None])   # 调整单
        conn.commit()
    finally:
        conn.close()

    assert v262.migrate(db_path, skip_backup=True) is True
    assert v262.verify(db_path) is True
    # 幂等：二次执行不报错、不重复加列
    assert v262.migrate(db_path, skip_backup=True) is True
    assert v262.verify(db_path) is True

    conn = _connect(db_path)
    try:
        assert {'price_source', 'price_trace'} <= _columns(
            conn, v262.LINE_TABLE)
        rows = dict(conn.execute(
            'SELECT line_no, price_source FROM %s WHERE invoice_id = 1'
            % v262.LINE_TABLE).fetchall())
        assert rows[1] == 'po'
        assert rows[2] == 'manual'
        adjustment = conn.execute(
            'SELECT price_source FROM %s WHERE invoice_id = 2'
            % v262.LINE_TABLE).fetchone()[0]
        assert adjustment == 'adjustment'
    finally:
        conn.close()

    assert v262.rollback(db_path) is True
    conn = _connect(db_path)
    try:
        # 列保留（SQLite 老版本不支持 DROP COLUMN），值已清空
        assert 'price_source' in _columns(conn, v262.LINE_TABLE)
        assert conn.execute(
            'SELECT COUNT(*) FROM %s WHERE price_source IS NOT NULL'
            % v262.LINE_TABLE).fetchone()[0] == 0
    finally:
        conn.close()


def test_v263_pricing_mode_param_seed_and_rollback(db_path):
    """vi_match_pricing_mode 定义 / 幂等 / 回滚删除。"""
    assert v263.migrate(db_path, skip_backup=True) is True
    assert v263.verify(db_path) is True
    # 幂等：二次执行不重复插入
    assert v263.migrate(db_path, skip_backup=True) is True
    assert v263.verify(db_path) is True

    conn = _connect(db_path)
    try:
        count = conn.execute(
            'SELECT COUNT(*) FROM control_parameter_defs WHERE code = ?',
            [v263.PARAM_CODE]).fetchone()[0]
        assert count == 1
        row = conn.execute(
            'SELECT domain, value_type, target_bo, default_value, status '
            'FROM control_parameter_defs WHERE code = ?',
            [v263.PARAM_CODE]).fetchone()
        assert row == ('procurement', 'enum', 'vendor_invoice', 'po_price', 'active')
    finally:
        conn.close()

    assert v263.rollback(db_path) is True
    conn = _connect(db_path)
    try:
        assert conn.execute(
            'SELECT COUNT(*) FROM control_parameter_defs WHERE code = ?',
            [v263.PARAM_CODE]).fetchone()[0] == 0
    finally:
        conn.close()


def test_v264_charge_line_types_and_tax_params_seed(db_path):
    """5 个行类型（含 3 费用行）/ 4 个税与费用参数 / 幂等 / 回滚。"""
    assert v264.migrate(db_path, skip_backup=True) is True
    assert v264.verify(db_path) is True

    expected_types = {spec['code']: spec for spec in v264.LINE_TYPES}
    conn = _connect(db_path)
    try:
        rows = {row[0]: row for row in conn.execute(
            'SELECT code, is_default, line_category, delivery_relevant, status '
            "FROM type_definitions WHERE scope_bo = 'vendor_invoice' "
            "AND level = 'line'")}
        assert set(rows) == set(expected_types)
        for code, spec in expected_types.items():
            assert rows[code][1] == spec['is_default'], code
            assert rows[code][2] == spec['line_category'], code
            assert rows[code][3] == spec['delivery_relevant'], code
            assert rows[code][4] == 'active', code
        assert [code for code, row in rows.items() if int(row[1] or 0) == 1] \
            == ['VI_LINE_GOODS']

        params = {row[0]: row[1:] for row in conn.execute(
            'SELECT code, domain, value_type, target_bo, default_value, status '
            'FROM control_parameter_defs WHERE target_bo = ?',
            [v264.SCOPE_BO])}
        assert set(v264.PARAM_CODES) <= set(params)
        assert params['vi_tax_mode'][3] == 'line_direct'
        assert params['vi_tax_tolerance_abs'][3] == '0.01'
        assert params['vi_freight_tolerance_abs'][3] == '0.00'
        assert params['vi_po_tax_compare'][3] == 'false'
        for code in v264.PARAM_CODES:
            assert params[code][2] == v264.SCOPE_BO, code
            assert params[code][4] == 'active', code
    finally:
        conn.close()

    # 幂等：二次执行不重复插入
    assert v264.migrate(db_path, skip_backup=True) is True
    assert v264.verify(db_path) is True

    conn = _connect(db_path)
    try:
        assert conn.execute(
            'SELECT COUNT(*) FROM type_definitions '
            "WHERE scope_bo = 'vendor_invoice' AND level = 'line'"
        ).fetchone()[0] == len(v264.LINE_TYPES)
        placeholders = ','.join('?' for _ in v264.PARAM_CODES)
        assert conn.execute(
            'SELECT COUNT(*) FROM control_parameter_defs WHERE code IN (%s)'
            % placeholders, list(v264.PARAM_CODES)).fetchone()[0] \
            == len(v264.PARAM_CODES)
    finally:
        conn.close()

    assert v264.rollback(db_path) is True
    conn = _connect(db_path)
    try:
        assert conn.execute(
            'SELECT COUNT(*) FROM type_definitions '
            "WHERE scope_bo = 'vendor_invoice' AND level = 'line'"
        ).fetchone()[0] == 0
        placeholders = ','.join('?' for _ in v264.PARAM_CODES)
        assert conn.execute(
            'SELECT COUNT(*) FROM control_parameter_defs WHERE code IN (%s)'
            % placeholders, list(v264.PARAM_CODES)).fetchone()[0] == 0
    finally:
        conn.close()