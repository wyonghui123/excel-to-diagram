# -*- coding: utf-8 -*-
"""v244 —— 销售发票价格与金额：净额基数 / 分摊明细 / 溯源 / 定价模式。

依据:
  docs/specs/sales-invoice-pricing-spec-2026-11-10.md
    §3 FR-001（净额基数）/ FR-002（分摊明细）/ FR-003（舍入差）
    FR-004（价格溯源）/ FR-005（定价模式）/ FR-006（distribution_basis）
    §9.3.2（枚举与控制参数）/ §9.3.4（迁移设计）

内容:
  1. `customer_invoice_lines` 增 6 列:
       header_discount_amount / header_surcharge_amount / calc_result_id /
       source_rate_record_id / price_trace / price_override_reason_code
  2. `customer_invoices` 增 5 列:
       billing_pricing_mode / pricing_date / rounding_diff /
       header_discount_amount / header_surcharge_amount
  3. `rate_records` 增 `distribution_basis`（默认 none，语义见 FR-006，
     与 `allocation_weight` 严格区分）
  4. 枚举种子：billing_pricing_mode / price_override_reason（先查后插）
  5. 控制参数种子：billing_pricing_mode / price_override_tolerance_pct /
     invoice_amount_tolerance（先查后插）
  6. 存量回填：billing_pricing_mode='legacy'、pricing_date=invoice_date、
     rounding_diff=0（仅回填空值，幂等）
  7. 定价模式按发票类型（SINV / SCR / SDN / SRV）落一条类型级取值
  8. 权限 `customer_invoice:customer_invoice_override_price`，授予
     admin / default，并挂到 `customer_invoice-list` 菜单

幂等：列先查后加；枚举 / 参数先查后插；UPDATE 只覆盖空值；权限
      INSERT OR IGNORE；菜单 JSON 按值合并；重复执行打印 [SKIP]。

回滚：删权限与授权；清理菜单中的权限码与动作；无引用时删控制参数 /
      枚举；尽力 DROP 新增列（SQLite 3.35+）。不删业务数据。
"""

import json
import sqlite3
from pathlib import Path

from meta.migrations import v239__customer_invoice_permissions_menu as v239

MIGRATION_NAME = 'v244__customer_invoice_pricing_trace'

HEADER_TABLE = 'customer_invoices'
LINE_TABLE = 'customer_invoice_lines'
RATE_RECORD_TABLE = 'rate_records'
TYPE_TABLE = 'type_definitions'
ENUM_TYPE_TABLE = 'enum_types'
ENUM_VALUE_TABLE = 'enum_values'
PARAM_DEF_TABLE = 'control_parameter_defs'
PARAM_VALUE_TABLE = 'control_parameter_values'
PERMISSION_TABLE = 'permissions'
PERMISSION_SET_TABLE = 'permission_sets'
GRANT_TABLE = 'permission_set_permissions'
MENU_TABLE = 'menus'
MENU_PERMISSION_TABLE = 'menu_permissions'

SCOPE_BO = 'customer_invoice'
MENU_CODE = 'customer_invoice-list'

#: 发票行新增列（列名, DDL 片段）
NEW_LINE_COLUMNS = (
    ('header_discount_amount', 'REAL NOT NULL DEFAULT 0'),
    ('header_surcharge_amount', 'REAL NOT NULL DEFAULT 0'),
    ('calc_result_id', 'INTEGER'),
    ('source_rate_record_id', 'INTEGER'),
    ('price_trace', 'TEXT'),
    ('price_override_reason_code', 'VARCHAR(64)'),
)

#: 发票头新增列
NEW_HEADER_COLUMNS = (
    ('billing_pricing_mode', "VARCHAR(48) NOT NULL DEFAULT 'legacy'"),
    ('pricing_date', 'VARCHAR(32)'),
    ('rounding_diff', 'REAL NOT NULL DEFAULT 0'),
    ('header_discount_amount', 'REAL NOT NULL DEFAULT 0'),
    ('header_surcharge_amount', 'REAL NOT NULL DEFAULT 0'),
)

#: 价目表条件新增列
NEW_RATE_RECORD_COLUMNS = (
    ('distribution_basis', "VARCHAR(32) NOT NULL DEFAULT 'none'"),
)

#: 枚举种子：type_id → (显示名, 描述, [(code, 显示名, name_en, is_system)])
ENUM_SEEDS = (
    ('billing_pricing_mode', '开票定价模式',
     '发票生成时价格与税的复制/重算策略（对标 SAP 复制控制 A/B/C/D/G）',
     (('copy_frozen', '复制冻结价', 'Copy Frozen', 0),
      ('copy_scale_update', '复制并按阶梯更新', 'Copy & Scale Update', 0),
      ('copy_reprice_all', '全部重新取价', 'Copy & Reprice All', 0),
      ('copy_manual_reprice_rest', '手工价冻结其余重算', 'Copy Manual, Reprice Rest', 0),
      ('copy_frozen_redetermine_tax', '冻结价 + 重算税', 'Copy Frozen, Redetermine Tax', 0),
      ('legacy', '历史口径', 'Legacy', 1))),
    ('price_override_reason', '改价原因',
     '发票行价格覆盖的原因码（替代自由文本）',
     (('promotion', '促销', 'Promotion', 0),
      ('contract', '合同价', 'Contract Price', 0),
      ('compensation', '补偿', 'Compensation', 0),
      ('freight_adjust', '运费调整', 'Freight Adjustment', 0),
      ('other', '其他', 'Other', 0))),
)

#: 控制参数定义：(code, 显示名, domain, value_type, enum_type_id,
#:               default_value, description)
PARAM_DEFS = (
    ('billing_pricing_mode', '开票定价模式', 'billing', 'enum', 'billing_pricing_mode',
     'copy_frozen_redetermine_tax',
     '发票生成时的价格复制/重算策略；按发票类型取值，组织级可覆盖'),
    ('price_override_tolerance_pct', '改价容差(%)', 'billing', 'number', None, '0',
     '行价偏离基准价的容忍百分比，超出需 override_price 权限'),
    ('invoice_amount_tolerance', '开票金额容差', 'billing', 'number', None, '0.01',
     '发票净额与订单行净额之差的容忍值（单据币种）'),
)

#: 定价模式默认取值的发票类型（类型级配置）
PRICING_MODE_TYPE_CODES = ('SINV', 'SCR', 'SDN', 'SRV')

#: 价格覆盖权限
OVERRIDE_ACTION = 'override_price'
OVERRIDE_PERMISSION = 'customer_invoice:customer_invoice_override_price'
PERMISSION = (OVERRIDE_PERMISSION, '销售发票改价', 'customer_invoice', OVERRIDE_ACTION)
GRANT_TO_SETS = ('admin', 'default')


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


def _load_json_list(raw):
    try:
        values = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return []
    return values if isinstance(values, list) else []


def _dump(values):
    return json.dumps(values, ensure_ascii=False)


def _add_columns(conn, table, columns):
    if not _table_exists(conn, table):
        print('[v244] SKIP: %s 表不存在（未加列）' % table)
        return 0
    have = _columns(conn, table)
    added = 0
    for column, ddl in columns:
        if column in have:
            print('[v244] SKIP: %s.%s 已存在' % (table, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, ddl))
        print('[v244] + %s.%s' % (table, column))
        added += 1
    return added


def _drop_column(conn, table, column):
    if not _table_exists(conn, table) or column not in _columns(conn, table):
        return
    try:
        conn.execute('ALTER TABLE %s DROP COLUMN %s' % (table, column))
        print('[v244] - %s.%s' % (table, column))
    except sqlite3.OperationalError as exc:
        print('[v244] WARN: 无法删除 %s.%s（%s）' % (table, column, exc))


# ------------------------------------------------------------------- upgrade

def _do_enums(conn):
    if not (_table_exists(conn, ENUM_TYPE_TABLE)
            and _table_exists(conn, ENUM_VALUE_TABLE)):
        print('[v244] SKIP: enum_types / enum_values 缺失（未播种枚举）')
        return
    for type_id, type_name, description, values in ENUM_SEEDS:
        if conn.execute('SELECT 1 FROM %s WHERE id = ?' % ENUM_TYPE_TABLE,
                        [type_id]).fetchone():
            print('[v244] SKIP: 枚举类型 %s 已存在' % type_id)
        else:
            conn.execute(
                "INSERT INTO %s (id, name, category, mutability, "
                "dimension_schema, description, created_at) "
                "VALUES (?, ?, 'business', 'extensible', NULL, ?, datetime('now'))"
                % ENUM_TYPE_TABLE,
                (type_id, type_name, description))
            print('[v244] + 枚举类型 %s' % type_id)

        for sort_order, (code, value_name, name_en, is_system) in enumerate(
                values, start=1):
            if conn.execute(
                    'SELECT 1 FROM %s WHERE enum_type_id = ? AND code = ?'
                    % ENUM_VALUE_TABLE, (type_id, code)).fetchone():
                continue
            conn.execute(
                "INSERT INTO %s (enum_type_id, code, name, name_en, sort_order, "
                "is_active, is_system, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, datetime('now'))" % ENUM_VALUE_TABLE,
                (type_id, code, value_name, name_en, sort_order, is_system))
            print('[v244]   + 枚举值 %s.%s' % (type_id, code))


def _do_params(conn):
    if not _table_exists(conn, PARAM_DEF_TABLE):
        print('[v244] SKIP: control_parameter_defs 缺失（未播种控制参数）')
        return
    columns = _columns(conn, PARAM_DEF_TABLE)
    has_enum_col = 'enum_type_id' in columns
    for code, name, domain, value_type, enum_type_id, default_value, desc in PARAM_DEFS:
        row = conn.execute('SELECT id FROM %s WHERE code = ?' % PARAM_DEF_TABLE,
                           [code]).fetchone()
        if row:
            if has_enum_col:
                conn.execute(
                    'UPDATE %s SET name = ?, domain = ?, value_type = ?, '
                    'enum_type_id = ?, default_value = ?, description = ?, '
                    "status = 'active' WHERE code = ?" % PARAM_DEF_TABLE,
                    (name, domain, value_type, enum_type_id, default_value, desc, code))
            else:
                conn.execute(
                    'UPDATE %s SET name = ?, domain = ?, value_type = ?, '
                    'default_value = ?, description = ?, status = ? '
                    'WHERE code = ?' % PARAM_DEF_TABLE,
                    (name, domain, value_type, default_value, desc, 'active', code))
            print('[v244] ~ 控制参数 %s' % code)
            continue
        if has_enum_col:
            conn.execute(
                'INSERT INTO %s (code, name, domain, value_type, enum_type_id, '
                'target_bo, default_value, status, description, created_at) '
                "VALUES (?, ?, ?, ?, ?, NULL, ?, 'active', ?, datetime('now'))"
                % PARAM_DEF_TABLE,
                (code, name, domain, value_type, enum_type_id, default_value, desc))
        else:
            conn.execute(
                'INSERT INTO %s (code, name, domain, value_type, target_bo, '
                'default_value, status, description, created_at) '
                "VALUES (?, ?, ?, ?, NULL, ?, 'active', ?, datetime('now'))"
                % PARAM_DEF_TABLE,
                (code, name, domain, value_type, default_value, desc))
        print('[v244] + 控制参数 %s' % code)


def _do_type_values(conn):
    """为发票类型落一条类型级定价模式取值（specificity_rank=1）。"""
    if not (_table_exists(conn, PARAM_DEF_TABLE)
            and _table_exists(conn, PARAM_VALUE_TABLE)
            and _table_exists(conn, TYPE_TABLE)):
        print('[v244] SKIP: 控制参数取值表或类型表缺失（未写类型级取值）')
        return
    prow = conn.execute(
        'SELECT id, default_value FROM %s WHERE code = ?' % PARAM_DEF_TABLE,
        ['billing_pricing_mode']).fetchone()
    if not prow:
        print('[v244] SKIP: 控制参数 billing_pricing_mode 缺失')
        return
    param_id, default_value = prow[0], prow[1]
    cols = _columns(conn, PARAM_VALUE_TABLE)
    has_type_col = 'document_type_id' in cols
    if not has_type_col:
        print('[v244] SKIP: control_parameter_values 无 document_type_id')
        return
    for code in PRICING_MODE_TYPE_CODES:
        trow = conn.execute(
            'SELECT id FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
            % TYPE_TABLE, [SCOPE_BO, 'header', code]).fetchone()
        if not trow:
            print('[v244] SKIP: 发票类型 %s 不存在' % code)
            continue
        existing = conn.execute(
            'SELECT id FROM %s WHERE control_parameter_id = ? '
            'AND document_type_id = ? AND org_id IS NULL AND line_type_id IS NULL '
            'AND item_group_id IS NULL' % PARAM_VALUE_TABLE,
            (param_id, int(trow[0]))).fetchone()
        if existing:
            conn.execute(
                'UPDATE %s SET value = ?, status = ? WHERE id = ?'
                % PARAM_VALUE_TABLE, (default_value, 'active', existing[0]))
            print('[v244] ~ 类型级定价模式 %s' % code)
            continue
        conn.execute(
            'INSERT INTO %s (control_parameter_id, org_id, document_type_id, '
            'line_type_id, item_group_id, specificity_rank, value, status, '
            "created_at) VALUES (?, NULL, ?, NULL, NULL, 1, ?, 'active', "
            "datetime('now'))" % PARAM_VALUE_TABLE,
            (param_id, int(trow[0]), default_value))
        print('[v244] + 类型级定价模式 %s' % code)


def _do_backfill(conn):
    if not _table_exists(conn, HEADER_TABLE):
        print('[v244] SKIP: %s 表不存在（未回填）' % HEADER_TABLE)
        return
    cols = _columns(conn, HEADER_TABLE)
    filled = 0
    if 'billing_pricing_mode' in cols:
        cur = conn.execute(
            "UPDATE %s SET billing_pricing_mode = 'legacy' "
            "WHERE billing_pricing_mode IS NULL OR billing_pricing_mode = ''"
            % HEADER_TABLE)
        filled += cur.rowcount or 0
    if 'pricing_date' in cols and 'invoice_date' in cols:
        cur = conn.execute(
            'UPDATE %s SET pricing_date = invoice_date '
            'WHERE (pricing_date IS NULL OR pricing_date = ?) '
            'AND invoice_date IS NOT NULL' % HEADER_TABLE, [''])
        filled += cur.rowcount or 0
    if 'rounding_diff' in cols:
        cur = conn.execute(
            'UPDATE %s SET rounding_diff = 0 WHERE rounding_diff IS NULL'
            % HEADER_TABLE)
        filled += cur.rowcount or 0
    print('[v244] 存量回填 %d 处' % filled)


def _do_permission(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        print('[v244] SKIP: permissions 表缺失（未写权限）')
        return False
    cur = conn.execute(
        'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
        'VALUES (?, ?, ?, ?)', PERMISSION)
    print('[v244] 权限 %s %s'
          % (OVERRIDE_PERMISSION, '已新增' if cur.rowcount else '已存在'))
    return True


def _do_grants(conn):
    if not (_table_exists(conn, PERMISSION_TABLE)
            and _table_exists(conn, PERMISSION_SET_TABLE)
            and _table_exists(conn, GRANT_TABLE)):
        print('[v244] SKIP: 权限集相关表缺失（未授权）')
        return
    cols = _columns(conn, GRANT_TABLE)
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('[v244] SKIP: %s 无 permission_set_id/role_id' % GRANT_TABLE)
        return
    has_code_col = 'permission_code' in cols
    has_granted = 'granted' in cols

    prow = conn.execute('SELECT id FROM permissions WHERE code = ?',
                        [OVERRIDE_PERMISSION]).fetchone()
    if not prow:
        return
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code = ? AND is_active = 1',
            [set_code]).fetchone()
        if not row:
            continue
        params = [row[0], prow[0]]
        where = '%s = ? AND permission_id = ?' % id_col
        if has_code_col:
            where += ' AND permission_code = ?'
            params.append(OVERRIDE_PERMISSION)
        if conn.execute('SELECT 1 FROM %s WHERE %s' % (GRANT_TABLE, where),
                        params).fetchone():
            continue
        if has_code_col:
            conn.execute(
                'INSERT INTO %s (%s, permission_code, permission_id, granted, '
                "created_at) VALUES (?, ?, ?, 1, datetime('now'))"
                % (GRANT_TABLE, id_col),
                (row[0], OVERRIDE_PERMISSION, prow[0]))
        elif has_granted:
            conn.execute(
                'INSERT INTO %s (%s, permission_id, granted, created_at) '
                "VALUES (?, ?, 1, datetime('now'))" % (GRANT_TABLE, id_col),
                (row[0], prow[0]))
        else:
            conn.execute(
                'INSERT INTO %s (%s, permission_id, created_at) '
                "VALUES (?, ?, datetime('now'))" % (GRANT_TABLE, id_col),
                (row[0], prow[0]))
        print('[v244] 授权 %s → %s' % (OVERRIDE_PERMISSION, set_code))


def _do_menu(conn):
    if not _table_exists(conn, MENU_TABLE):
        print('[v244] SKIP: %s 表缺失（菜单未同步）' % MENU_TABLE)
        return
    v239._insert_menu_if_missing(conn)

    cols = _columns(conn, MENU_TABLE)
    if 'required_permissions' in cols:
        row = conn.execute(
            'SELECT required_permissions FROM %s WHERE menu_code = ?'
            % MENU_TABLE, [MENU_CODE]).fetchone()
        values = _load_json_list(row[0] if row else None)
        if OVERRIDE_PERMISSION not in values:
            values.append(OVERRIDE_PERMISSION)
            conn.execute(
                'UPDATE %s SET required_permissions = ? WHERE menu_code = ?'
                % MENU_TABLE, [_dump(values), MENU_CODE])
            print('[v244] 菜单 required_permissions += %s' % OVERRIDE_PERMISSION)

    if 'bo_bindings' in cols:
        row = conn.execute(
            'SELECT bo_bindings FROM %s WHERE menu_code = ?' % MENU_TABLE,
            [MENU_CODE]).fetchone()
        bindings = _load_json_list(row[0] if row else None)
        changed = False
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            actions = binding.get('include_actions')
            if isinstance(actions, list) and OVERRIDE_ACTION not in actions:
                actions.append(OVERRIDE_ACTION)
                changed = True
        if changed:
            conn.execute(
                'UPDATE %s SET bo_bindings = ? WHERE menu_code = ?' % MENU_TABLE,
                [_dump(bindings), MENU_CODE])
            print('[v244] 菜单 bo_bindings 追加 %s' % OVERRIDE_ACTION)

    if _table_exists(conn, MENU_PERMISSION_TABLE):
        mp_cols = _columns(conn, MENU_PERMISSION_TABLE)
        if 'required_permissions' in mp_cols:
            row = conn.execute(
                'SELECT required_permissions FROM %s WHERE menu_code = ?'
                % MENU_PERMISSION_TABLE, [MENU_CODE]).fetchone()
            if row is not None:
                values = _load_json_list(row[0])
                if OVERRIDE_PERMISSION not in values:
                    values.append(OVERRIDE_PERMISSION)
                    conn.execute(
                        'UPDATE %s SET required_permissions = ? WHERE menu_code = ?'
                        % MENU_PERMISSION_TABLE, [_dump(values), MENU_CODE])
    print('[v244] 菜单 %s 权限同步完成' % MENU_CODE)


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v244] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, HEADER_TABLE):
            print('[v244] SKIP: %s 表不存在' % HEADER_TABLE)
            return False
        _add_columns(conn, LINE_TABLE, NEW_LINE_COLUMNS)
        _add_columns(conn, HEADER_TABLE, NEW_HEADER_COLUMNS)
        _add_columns(conn, RATE_RECORD_TABLE, NEW_RATE_RECORD_COLUMNS)
        _do_enums(conn)
        _do_params(conn)
        _do_type_values(conn)
        _do_backfill(conn)
        _do_permission(conn)
        _do_grants(conn)
        _do_menu(conn)
        conn.commit()
        return True
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def _verify_columns(conn):
    ok = True
    for table, columns in ((LINE_TABLE, NEW_LINE_COLUMNS),
                           (HEADER_TABLE, NEW_HEADER_COLUMNS),
                           (RATE_RECORD_TABLE, NEW_RATE_RECORD_COLUMNS)):
        if not _table_exists(conn, table):
            print('[v244] verify: 缺表 %s' % table)
            ok = False
            continue
        have = _columns(conn, table)
        for column, _ddl in columns:
            if column not in have:
                print('[v244] verify: 缺列 %s.%s' % (table, column))
                ok = False
    return ok


def _verify_seeds(conn):
    ok = True
    for type_id, _name, _desc, values in ENUM_SEEDS:
        if not conn.execute('SELECT 1 FROM %s WHERE id = ?' % ENUM_TYPE_TABLE,
                            [type_id]).fetchone():
            print('[v244] verify: 缺枚举类型 %s' % type_id)
            ok = False
            continue
        for code, _vn, _en, _sys in values:
            if not conn.execute(
                    'SELECT 1 FROM %s WHERE enum_type_id = ? AND code = ?'
                    % ENUM_VALUE_TABLE, (type_id, code)).fetchone():
                print('[v244] verify: 缺枚举值 %s.%s' % (type_id, code))
                ok = False
    for code, *_rest in PARAM_DEFS:
        if not conn.execute('SELECT 1 FROM %s WHERE code = ?' % PARAM_DEF_TABLE,
                            [code]).fetchone():
            print('[v244] verify: 缺控制参数 %s' % code)
            ok = False
    return ok


def _verify_backfill(conn):
    if not _table_exists(conn, HEADER_TABLE):
        return False
    if 'billing_pricing_mode' not in _columns(conn, HEADER_TABLE):
        # 已回滚：列缺失由 _verify_columns 报告，此处不再重复
        return False
    row = conn.execute(
        'SELECT COUNT(1) FROM %s WHERE billing_pricing_mode IS NULL '
        "OR billing_pricing_mode = ''" % HEADER_TABLE).fetchone()
    if row and int(row[0]):
        print('[v244] verify: %d 张发票的定价模式未回填' % int(row[0]))
        return False
    return True


def _verify_permission(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        return False
    if not conn.execute('SELECT 1 FROM permissions WHERE code = ?',
                        [OVERRIDE_PERMISSION]).fetchone():
        print('[v244] verify: 缺权限 %s' % OVERRIDE_PERMISSION)
        return False
    return True


def verify(db_path):
    path = Path(db_path)
    if not path.exists():
        print('[v244] verify: database not found: %s' % path)
        return False
    conn = _connect(path)
    try:
        checks = (
            _verify_columns(conn),
            _verify_seeds(conn),
            _verify_backfill(conn),
            _verify_permission(conn),
        )
    finally:
        conn.close()
    if all(checks):
        print('[v244] verify: OK')
        return True
    print('[v244] verify: FAILED')
    return False


# ------------------------------------------------------------------ rollback

def _remove_menu_refs(conn):
    if _table_exists(conn, MENU_TABLE):
        cols = _columns(conn, MENU_TABLE)
        if 'required_permissions' in cols:
            row = conn.execute(
                'SELECT required_permissions FROM %s WHERE menu_code = ?'
                % MENU_TABLE, [MENU_CODE]).fetchone()
            if row is not None:
                values = [v for v in _load_json_list(row[0])
                          if v != OVERRIDE_PERMISSION]
                conn.execute(
                    'UPDATE %s SET required_permissions = ? WHERE menu_code = ?'
                    % MENU_TABLE, [_dump(values), MENU_CODE])
        if 'bo_bindings' in cols:
            row = conn.execute(
                'SELECT bo_bindings FROM %s WHERE menu_code = ?' % MENU_TABLE,
                [MENU_CODE]).fetchone()
            bindings = _load_json_list(row[0] if row else None)
            changed = False
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                actions = binding.get('include_actions')
                if isinstance(actions, list) and OVERRIDE_ACTION in actions:
                    binding['include_actions'] = [
                        a for a in actions if a != OVERRIDE_ACTION]
                    changed = True
            if changed:
                conn.execute(
                    'UPDATE %s SET bo_bindings = ? WHERE menu_code = ?'
                    % MENU_TABLE, [_dump(bindings), MENU_CODE])
    if _table_exists(conn, MENU_PERMISSION_TABLE):
        cols = _columns(conn, MENU_PERMISSION_TABLE)
        if 'required_permissions' in cols:
            row = conn.execute(
                'SELECT required_permissions FROM %s WHERE menu_code = ?'
                % MENU_PERMISSION_TABLE, [MENU_CODE]).fetchone()
            if row is not None:
                values = [v for v in _load_json_list(row[0])
                          if v != OVERRIDE_PERMISSION]
                conn.execute(
                    'UPDATE %s SET required_permissions = ? WHERE menu_code = ?'
                    % MENU_PERMISSION_TABLE, [_dump(values), MENU_CODE])


def _remove_permission(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        return
    ids = [row[0] for row in conn.execute(
        'SELECT id FROM permissions WHERE code = ?', [OVERRIDE_PERMISSION])]
    if _table_exists(conn, GRANT_TABLE):
        cols = _columns(conn, GRANT_TABLE)
        if 'permission_code' in cols:
            conn.execute('DELETE FROM %s WHERE permission_code = ?' % GRANT_TABLE,
                         [OVERRIDE_PERMISSION])
        elif ids:
            conn.execute(
                'DELETE FROM %s WHERE permission_id IN (%s)'
                % (GRANT_TABLE, ','.join('?' for _ in ids)), ids)
    conn.execute('DELETE FROM permissions WHERE code = ?', [OVERRIDE_PERMISSION])


def _remove_seeds(conn):
    if _table_exists(conn, PARAM_VALUE_TABLE) and _table_exists(conn, PARAM_DEF_TABLE):
        for code, *_rest in PARAM_DEFS:
            row = conn.execute('SELECT id FROM %s WHERE code = ?' % PARAM_DEF_TABLE,
                               [code]).fetchone()
            if not row:
                continue
            conn.execute(
                'DELETE FROM %s WHERE control_parameter_id = ?' % PARAM_VALUE_TABLE,
                [row[0]])
            conn.execute('DELETE FROM %s WHERE id = ?' % PARAM_DEF_TABLE, [row[0]])
            print('[v244] - 控制参数 %s' % code)
    if _table_exists(conn, ENUM_VALUE_TABLE) and _table_exists(conn, ENUM_TYPE_TABLE):
        for type_id, _name, _desc, _values in ENUM_SEEDS:
            used = False
            if _table_exists(conn, PARAM_DEF_TABLE) and 'enum_type_id' in _columns(
                    conn, PARAM_DEF_TABLE):
                used = conn.execute(
                    'SELECT 1 FROM %s WHERE enum_type_id = ? LIMIT 1' % PARAM_DEF_TABLE,
                    [type_id]).fetchone() is not None
            if used:
                print('[v244] SKIP: 枚举 %s 仍被控制参数引用' % type_id)
                continue
            conn.execute('DELETE FROM %s WHERE enum_type_id = ?' % ENUM_VALUE_TABLE,
                         [type_id])
            conn.execute('DELETE FROM %s WHERE id = ?' % ENUM_TYPE_TABLE, [type_id])
            print('[v244] - 枚举 %s' % type_id)


def rollback(db_path):
    path = Path(db_path)
    if not path.exists():
        return False
    conn = _connect(path)
    try:
        _remove_menu_refs(conn)
        _remove_permission(conn)
        _remove_seeds(conn)
        for column, _ddl in NEW_LINE_COLUMNS:
            _drop_column(conn, LINE_TABLE, column)
        for column, _ddl in NEW_HEADER_COLUMNS:
            _drop_column(conn, HEADER_TABLE, column)
        for column, _ddl in NEW_RATE_RECORD_COLUMNS:
            _drop_column(conn, RATE_RECORD_TABLE, column)
        conn.commit()
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)