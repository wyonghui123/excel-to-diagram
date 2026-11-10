# -*- coding: utf-8 -*-
"""v243 —— 单据身份元数据平台化（S8 Wave D）。

依据:
  docs/specs/s8-customer-invoice-wave-d/spec.md §5.2 / §6.1 / FR-1 / FR-2 / FR-5

内容:
  1. `type_definitions` 增 4 个平台级列（对全部 scope_bo 生效）:
       document_role / direction / reversal_type_id / is_default
  2. `customer_invoices` 增 `direction`（单据层冗余快照，默认 1）。
  3. 平台回填：`level='header'` 的行按 `document_category` 推导
       document_role（standard→invoice，其余同名）
       direction（credit_memo / return / cancellation → -1，其余 1）
  4. 发票类型种子补齐（FR-1 / FR-5）:
       SINV  invoice      +1  is_default=1  reversal_type_id→SRV
       SCR   credit_memo  -1               （显示名改「销售贷项凭证」）
       SDN   debit_memo   +1  is_default=1
       SRV   invoice      -1  （新增类型 + 号段 SRV-{DATE:yyyymm}-{SEQ:5}）
     存量发票的 `direction` 按 `document_type_id` 回填。
  5. 唯一索引 `uq_type_default_role`：
       (scope_bo, level, document_role) WHERE is_default = 1。
  6. 权限 `customer_invoice:customer_invoice_debit_memo`，授予 admin / default，
     并挂到 `customer_invoice-list` 菜单（bo_bindings / required_permissions）。

幂等：列先查后加；类型 / 序列先查后插；UPDATE 幂等覆盖；索引 IF NOT EXISTS；
      权限 INSERT OR IGNORE；菜单 JSON 按值合并；重复执行打印 [SKIP]。

回滚：删索引；删权限与授权；解除 SINV→SRV 引用后尽力删除 SRV 类型与号段；
      尽力删除 5 个新增列（SQLite 3.35+ DROP COLUMN）。重建前的业务数据不删。
"""

import json
import sqlite3
from pathlib import Path

from meta.migrations import v239__customer_invoice_permissions_menu as v239

MIGRATION_NAME = 'v243__customer_invoice_document_role'

TYPE_TABLE = 'type_definitions'
HEADER_TABLE = 'customer_invoices'
SEQUENCE_TABLE = 'number_sequences'
PERMISSION_TABLE = 'permissions'
PERMISSION_SET_TABLE = 'permission_sets'
GRANT_TABLE = 'permission_set_permissions'
MENU_TABLE = 'menus'
MENU_PERMISSION_TABLE = 'menu_permissions'

SCOPE_BO = 'customer_invoice'
MENU_CODE = 'customer_invoice-list'

#: type_definitions 平台级身份列（列名, DDL 片段）
NEW_TYPE_COLUMNS = (
    ('document_role', 'VARCHAR(32)'),
    ('direction', 'INTEGER NOT NULL DEFAULT 1'),
    ('reversal_type_id', 'INTEGER'),
    ('is_default', 'INTEGER NOT NULL DEFAULT 0'),
)

#: customer_invoices 单据层方向快照
NEW_HEADER_COLUMNS = (
    ('direction', 'INTEGER NOT NULL DEFAULT 1'),
)

DEFAULT_INDEX = 'uq_type_default_role'
DEFAULT_INDEX_SQL = (
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_type_default_role '
    'ON type_definitions (scope_bo, level, document_role) '
    'WHERE is_default = 1'
)

#: document_category → document_role（平台通用口径；standard 归一到 invoice）
ROLE_BY_CATEGORY = {
    'standard': 'invoice',
    'invoice': 'invoice',
    'credit_memo': 'credit_memo',
    'debit_memo': 'debit_memo',
    'cancellation': 'cancellation',
    'return': 'return',
}

#: 负向单据类别（direction = -1）
NEGATIVE_CATEGORIES = ('credit_memo', 'return', 'cancellation')

#: 发票头类型目标值：code → (document_role, direction, is_default)
INVOICE_TYPE_ROLES = {
    'SINV': ('invoice', 1, 1),
    'SCR': ('credit_memo', -1, 0),
    'SDN': ('debit_memo', 1, 1),
    'SRV': ('invoice', -1, 0),
}

#: FR-5：SCR 显示名从「红字销售发票」改为「销售贷项凭证」
SCR_NAME = '销售贷项凭证'

#: 新增红字发票类型（负向 invoice：同角色不同方向）
SRV_TYPE = {
    'code': 'SRV',
    'name': '销售红字发票',
    # 沿用 SINV 的 legacy 类型类别口径（v237 的 CASE 将 standard 映射为 invoice）
    'document_category': 'standard',
}

SRV_SEQUENCE = {
    'code': 'SRV',
    'name': '销售红字发票编号',
    'pattern': 'SRV-{DATE:yyyymm}-{SEQ:5}',
    'date_field': 'invoice_date',
}

#: 借项通知单权限（T52 预留）
DEBIT_ACTION = 'debit_memo'
DEBIT_PERMISSION = 'customer_invoice:customer_invoice_debit_memo'
PERMISSION = (DEBIT_PERMISSION, '销售发票创建借项', 'customer_invoice', DEBIT_ACTION)
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


def _index_exists(conn, index):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
        [index]).fetchone()
    return row is not None


def _load_json_list(raw):
    try:
        values = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return []
    return values if isinstance(values, list) else []


def _dump(values):
    return json.dumps(values, ensure_ascii=False)


def _type_row(conn, code):
    return conn.execute(
        'SELECT id FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
        % TYPE_TABLE, [SCOPE_BO, 'header', code]).fetchone()


# ------------------------------------------------------------------- upgrade

def _do_type_columns(conn):
    if not _table_exists(conn, TYPE_TABLE):
        print('[v243] SKIP: %s 表不存在（未加列）' % TYPE_TABLE)
        return 0
    have = _columns(conn, TYPE_TABLE)
    added = 0
    for column, ddl in NEW_TYPE_COLUMNS:
        if column in have:
            print('[v243] SKIP: 列 %s.%s 已存在' % (TYPE_TABLE, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (TYPE_TABLE, column, ddl))
        added += 1
        print('[v243] ALTER: 列 %s.%s' % (TYPE_TABLE, column))
    return added


def _do_header_columns(conn):
    if not _table_exists(conn, HEADER_TABLE):
        print('[v243] SKIP: %s 表不存在（未加列）' % HEADER_TABLE)
        return 0
    have = _columns(conn, HEADER_TABLE)
    added = 0
    for column, ddl in NEW_HEADER_COLUMNS:
        if column in have:
            print('[v243] SKIP: 列 %s.%s 已存在' % (HEADER_TABLE, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (HEADER_TABLE, column, ddl))
        added += 1
        print('[v243] ALTER: 列 %s.%s' % (HEADER_TABLE, column))
    return added


def _do_platform_backfill(conn):
    """所有 scope_bo 的头类型按 document_category 推导角色与方向。"""
    if not _table_exists(conn, TYPE_TABLE):
        return
    placeholders = ', '.join('?' for _ in ROLE_BY_CATEGORY)
    categories = list(ROLE_BY_CATEGORY)
    case_sql = 'CASE document_category %s ELSE document_category END' % (
        ' '.join('WHEN ? THEN ?' for _ in ROLE_BY_CATEGORY))
    params = []
    for category, role in ROLE_BY_CATEGORY.items():
        params.extend([category, role])
    conn.execute(
        'UPDATE %s SET document_role = %s '
        "WHERE level = 'header' AND document_category IN (%s)"
        % (TYPE_TABLE, case_sql, placeholders),
        params + categories)
    negative = ', '.join('?' for _ in NEGATIVE_CATEGORIES)
    conn.execute(
        'UPDATE %s SET direction = CASE WHEN document_category IN (%s) '
        "THEN -1 ELSE 1 END WHERE level = 'header' "
        'AND document_category IS NOT NULL' % (TYPE_TABLE, negative),
        list(NEGATIVE_CATEGORIES))
    print('[v243] 平台回填: 头类型 document_role / direction')


def _do_srv_sequence(conn):
    if not _table_exists(conn, SEQUENCE_TABLE):
        print('[v243] SKIP: %s 表不存在（未建 SRV 号段）' % SEQUENCE_TABLE)
        return None
    row = conn.execute('SELECT id FROM %s WHERE code = ?' % SEQUENCE_TABLE,
                       [SRV_SEQUENCE['code']]).fetchone()
    if row:
        print('[v243] SKIP: 号段 %s 已存在' % SRV_SEQUENCE['code'])
        return int(row[0])
    cur = conn.execute(
        'INSERT INTO %s (code, name, pattern, date_field, start_value, '
        "on_exhaust, status) VALUES (?, ?, ?, ?, 1, 'error', 'active')"
        % SEQUENCE_TABLE,
        [SRV_SEQUENCE['code'], SRV_SEQUENCE['name'],
         SRV_SEQUENCE['pattern'], SRV_SEQUENCE['date_field']])
    print('[v243] 号段 %s 已新增' % SRV_SEQUENCE['code'])
    return int(cur.lastrowid)


def _do_srv_type(conn, sequence_id):
    if not _table_exists(conn, TYPE_TABLE):
        return None
    row = _type_row(conn, SRV_TYPE['code'])
    if row:
        print('[v243] SKIP: 类型 %s 已存在' % SRV_TYPE['code'])
        type_id = int(row[0])
        if sequence_id:
            conn.execute(
                'UPDATE %s SET number_sequence_id = ? WHERE id = ?'
                % TYPE_TABLE, [sequence_id, type_id])
        return type_id
    cur = conn.execute(
        'INSERT INTO %s (code, name, scope_bo, level, document_category, '
        'delivery_relevant, number_sequence_id, status, description) '
        "VALUES (?, ?, ?, 'header', ?, 1, ?, 'active', ?)" % TYPE_TABLE,
        [SRV_TYPE['code'], SRV_TYPE['name'], SCOPE_BO,
         SRV_TYPE['document_category'], sequence_id,
         '红字发票：红冲生成，direction=-1，回指原发票'])
    print('[v243] 类型 %s 已新增' % SRV_TYPE['code'])
    return int(cur.lastrowid)


def _do_invoice_type_roles(conn, srv_id):
    """发票四类型的目标身份值 + SINV→SRV 红冲类型绑定。"""
    if not _table_exists(conn, TYPE_TABLE):
        return
    for code, (role, direction, is_default) in INVOICE_TYPE_ROLES.items():
        row = _type_row(conn, code)
        if not row:
            print('[v243] SKIP: 缺类型 %s（未回填）' % code)
            continue
        conn.execute(
            'UPDATE %s SET document_role = ?, direction = ?, is_default = ? '
            'WHERE id = ?' % TYPE_TABLE,
            [role, direction, is_default, int(row[0])])
    if srv_id:
        row = _type_row(conn, 'SINV')
        if row:
            conn.execute(
                'UPDATE %s SET reversal_type_id = ? WHERE id = ?' % TYPE_TABLE,
                [srv_id, int(row[0])])
    conn.execute(
        'UPDATE %s SET name = ? WHERE scope_bo = ? AND level = ? AND code = ?'
        % TYPE_TABLE, [SCR_NAME, SCOPE_BO, 'header', 'SCR'])
    print('[v243] 发票类型身份值已回填（SINV/SCR/SDN/SRV）')


def _do_invoice_backfill(conn):
    """存量发票按类型回填 direction 快照。"""
    if not (_table_exists(conn, HEADER_TABLE)
            and _table_exists(conn, TYPE_TABLE)):
        return
    conn.execute(
        'UPDATE %s SET direction = COALESCE('
        '(SELECT t.direction FROM %s t WHERE t.id = %s.document_type_id), 1)'
        % (HEADER_TABLE, TYPE_TABLE, HEADER_TABLE))
    print('[v243] 存量发票 direction 已回填')


def _do_default_index(conn):
    if not _table_exists(conn, TYPE_TABLE):
        print('[v243] SKIP: %s 表不存在（未建索引）' % TYPE_TABLE)
        return
    if _index_exists(conn, DEFAULT_INDEX):
        print('[v243] SKIP: 索引 %s 已存在' % DEFAULT_INDEX)
        return
    conn.execute(DEFAULT_INDEX_SQL)
    print('[v243] 索引 %s 已建立' % DEFAULT_INDEX)


def _do_permission(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        print('[v243] SKIP: %s 表不存在（未写权限）' % PERMISSION_TABLE)
        return False
    cur = conn.execute(
        'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
        'VALUES (?, ?, ?, ?)', PERMISSION)
    print('[v243] 权限 %s %s'
          % (DEBIT_PERMISSION, '已新增' if cur.rowcount else '已存在'))
    return True


def _do_grants(conn):
    if not (_table_exists(conn, PERMISSION_TABLE)
            and _table_exists(conn, PERMISSION_SET_TABLE)
            and _table_exists(conn, GRANT_TABLE)):
        print('[v243] SKIP: 权限集相关表缺失（未授权）')
        return
    cols = _columns(conn, GRANT_TABLE)
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('[v243] SKIP: %s 无 permission_set_id/role_id' % GRANT_TABLE)
        return
    has_code_col = 'permission_code' in cols
    has_granted = 'granted' in cols

    prow = conn.execute('SELECT id FROM permissions WHERE code = ?',
                        [DEBIT_PERMISSION]).fetchone()
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
            params.append(DEBIT_PERMISSION)
        if conn.execute('SELECT 1 FROM %s WHERE %s' % (GRANT_TABLE, where),
                        params).fetchone():
            continue
        if has_code_col:
            conn.execute(
                'INSERT INTO %s (%s, permission_code, permission_id, granted, '
                "created_at) VALUES (?, ?, ?, ?, datetime('now'))"
                % (GRANT_TABLE, id_col),
                (row[0], DEBIT_PERMISSION, prow[0], 1))
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
        print('[v243] 授权 %s → %s' % (DEBIT_PERMISSION, set_code))


def _do_menu(conn):
    if not _table_exists(conn, MENU_TABLE):
        print('[v243] SKIP: %s 表不存在（菜单未同步）' % MENU_TABLE)
        return
    v239._insert_menu_if_missing(conn)

    cols = _columns(conn, MENU_TABLE)
    if 'required_permissions' in cols:
        row = conn.execute(
            'SELECT required_permissions FROM %s WHERE menu_code = ?'
            % MENU_TABLE, [MENU_CODE]).fetchone()
        values = _load_json_list(row[0] if row else None)
        if DEBIT_PERMISSION not in values:
            values.append(DEBIT_PERMISSION)
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
            if isinstance(actions, list) and DEBIT_ACTION not in actions:
                actions.append(DEBIT_ACTION)
                changed = True
        if changed:
            conn.execute(
                'UPDATE %s SET bo_bindings = ? WHERE menu_code = ?' % MENU_TABLE,
                [_dump(bindings), MENU_CODE])

    if _table_exists(conn, MENU_PERMISSION_TABLE):
        mp_cols = _columns(conn, MENU_PERMISSION_TABLE)
        if 'required_permissions' in mp_cols:
            row = conn.execute(
                'SELECT required_permissions FROM %s WHERE menu_code = ?'
                % MENU_PERMISSION_TABLE, [MENU_CODE]).fetchone()
            if row is not None:
                values = _load_json_list(row[0])
                if DEBIT_PERMISSION not in values:
                    values.append(DEBIT_PERMISSION)
                conn.execute(
                    'UPDATE %s SET required_permissions = ? WHERE menu_code = ?'
                    % MENU_PERMISSION_TABLE, [_dump(values), MENU_CODE])
    print('[v243] 菜单 %s 权限同步完成' % MENU_CODE)


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v243] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, TYPE_TABLE):
            print('[v243] SKIP: %s 表不存在' % TYPE_TABLE)
            return False
        _do_type_columns(conn)
        _do_header_columns(conn)
        _do_platform_backfill(conn)
        sequence_id = _do_srv_sequence(conn)
        srv_id = _do_srv_type(conn, sequence_id)
        _do_invoice_type_roles(conn, srv_id)
        _do_invoice_backfill(conn)
        _do_default_index(conn)
        _do_permission(conn)
        _do_grants(conn)
        _do_menu(conn)
        conn.commit()
        return True
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def _verify_columns(conn):
    if not _table_exists(conn, TYPE_TABLE):
        print('[v243] verify: 缺表 %s' % TYPE_TABLE)
        return False
    ok = True
    have = _columns(conn, TYPE_TABLE)
    for column, _ddl in NEW_TYPE_COLUMNS:
        if column not in have:
            print('[v243] verify: 缺列 %s.%s' % (TYPE_TABLE, column))
            ok = False
    if not _table_exists(conn, HEADER_TABLE):
        print('[v243] verify: 缺表 %s' % HEADER_TABLE)
        return False
    header_have = _columns(conn, HEADER_TABLE)
    for column, _ddl in NEW_HEADER_COLUMNS:
        if column not in header_have:
            print('[v243] verify: 缺列 %s.%s' % (HEADER_TABLE, column))
            ok = False
    return ok


def _verify_invoice_types(conn):
    ok = True
    srv = _type_row(conn, 'SRV')
    if not srv:
        print('[v243] verify: 缺类型 SRV')
        return False
    srv_id = int(srv[0])
    for code, (role, direction, is_default) in INVOICE_TYPE_ROLES.items():
        row = conn.execute(
            'SELECT document_role, direction, is_default FROM %s '
            'WHERE scope_bo = ? AND level = ? AND code = ?'
            % TYPE_TABLE, [SCOPE_BO, 'header', code]).fetchone()
        if not row:
            print('[v243] verify: 缺类型 %s' % code)
            ok = False
            continue
        if (row[0], row[1], row[2]) != (role, direction, is_default):
            print('[v243] verify: 类型 %s 身份值不符 %s'
                  % (code, tuple(row)))
            ok = False
    row = conn.execute(
        'SELECT reversal_type_id FROM %s WHERE scope_bo = ? AND level = ? '
        'AND code = ?' % TYPE_TABLE, [SCOPE_BO, 'header', 'SINV']).fetchone()
    if not row or row[0] != srv_id:
        print('[v243] verify: SINV.reversal_type_id 未指向 SRV')
        ok = False
    row = conn.execute(
        'SELECT number_sequence_id FROM %s WHERE id = ?' % TYPE_TABLE,
        [srv_id]).fetchone()
    if not row or row[0] is None:
        print('[v243] verify: SRV 未绑定号段')
        ok = False
    return ok


def _verify_platform_roles(conn):
    """"非发票 scope_bo 的头类型也应有 role / direction（缺失即回填失败）。"""
    ok = True
    rows = conn.execute(
        'SELECT code, scope_bo, document_category, document_role, direction '
        "FROM %s WHERE level = 'header' AND document_category IS NOT NULL "
        'AND scope_bo != ?' % TYPE_TABLE, [SCOPE_BO]).fetchall()
    for code, scope_bo, category, role, direction in rows:
        expected_role = ROLE_BY_CATEGORY.get(category)
        expected_direction = -1 if category in NEGATIVE_CATEGORIES else 1
        if role != expected_role or direction != expected_direction:
            print('[v243] verify: 类型 %s(%s) 回填不符 role=%s direction=%s'
                  % (code, scope_bo, role, direction))
            ok = False
    return ok


def _verify_header_direction(conn):
    row = conn.execute(
        'SELECT COUNT(*) FROM %s WHERE direction IS NULL '
        'OR direction NOT IN (-1, 1)' % HEADER_TABLE).fetchone()
    if row[0]:
        print('[v243] verify: %s.direction 非法 %s 行' % (HEADER_TABLE, row[0]))
        return False
    return True


def _verify_index(conn):
    if not _index_exists(conn, DEFAULT_INDEX):
        print('[v243] verify: 缺索引 %s' % DEFAULT_INDEX)
        return False
    return True


def _verify_permission(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        print('[v243] verify: 缺表 %s' % PERMISSION_TABLE)
        return False
    if not conn.execute('SELECT 1 FROM permissions WHERE code = ?',
                        [DEBIT_PERMISSION]).fetchone():
        print('[v243] verify: 缺权限 %s' % DEBIT_PERMISSION)
        return False
    if not (_table_exists(conn, PERMISSION_SET_TABLE)
            and _table_exists(conn, GRANT_TABLE)):
        return True
    cols = _columns(conn, GRANT_TABLE)
    id_col = 'permission_set_id' if 'permission_set_id' in cols else 'role_id'
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code = ? AND is_active = 1',
            [set_code]).fetchone()
        if not row:
            continue
        if 'permission_code' in cols:
            found = conn.execute(
                'SELECT 1 FROM %s WHERE %s = ? AND permission_code = ?'
                % (GRANT_TABLE, id_col),
                [row[0], DEBIT_PERMISSION]).fetchone()
        else:
            prow = conn.execute(
                'SELECT id FROM permissions WHERE code = ?',
                [DEBIT_PERMISSION]).fetchone()
            found = conn.execute(
                'SELECT 1 FROM %s WHERE %s = ? AND permission_id = ?'
                % (GRANT_TABLE, id_col),
                [row[0], prow[0] if prow else None]).fetchone()
        if not found:
            print('[v243] verify: 权限 %s 未授予 %s'
                  % (DEBIT_PERMISSION, set_code))
            return False
    return True


def verify(db_path):
    path = Path(db_path)
    if not path.exists():
        return False

    conn = _connect(path)
    try:
        if not _verify_columns(conn):
            return False
        checks = (
            _verify_invoice_types(conn),
            _verify_platform_roles(conn),
            _verify_header_direction(conn),
            _verify_index(conn),
            _verify_permission(conn),
        )
        return all(checks)
    finally:
        conn.close()


# ------------------------------------------------------------------ rollback

def _drop_column(conn, table, column):
    if not _table_exists(conn, table):
        return
    if column not in _columns(conn, table):
        return
    try:
        conn.execute('ALTER TABLE %s DROP COLUMN %s' % (table, column))
    except sqlite3.OperationalError as exc:
        print('[v243] WARN: 无法删除 %s.%s（%s）' % (table, column, exc))


def rollback(db_path):
    path = Path(db_path)
    if not path.exists():
        return False

    conn = _connect(path)
    try:
        if _table_exists(conn, TYPE_TABLE):
            if _index_exists(conn, DEFAULT_INDEX):
                conn.execute('DROP INDEX %s' % DEFAULT_INDEX)

        # 权限与授权
        if _table_exists(conn, PERMISSION_TABLE):
            ids = [row[0] for row in conn.execute(
                'SELECT id FROM permissions WHERE code = ?',
                [DEBIT_PERMISSION])]
            if _table_exists(conn, GRANT_TABLE):
                cols = _columns(conn, GRANT_TABLE)
                if 'permission_code' in cols:
                    conn.execute(
                        'DELETE FROM %s WHERE permission_code = ?' % GRANT_TABLE,
                        [DEBIT_PERMISSION])
                elif ids:
                    conn.execute(
                        'DELETE FROM %s WHERE permission_id IN (%s)'
                        % (GRANT_TABLE, ','.join('?' for _ in ids)), ids)
            conn.execute('DELETE FROM permissions WHERE code = ?',
                         [DEBIT_PERMISSION])

        # 解除 SINV→SRV 引用后删除 SRV（无单据引用时）
        if _table_exists(conn, TYPE_TABLE):
            srv = _type_row(conn, SRV_TYPE['code'])
            if srv:
                conn.execute(
                    'UPDATE %s SET reversal_type_id = NULL '
                    'WHERE reversal_type_id = ?' % TYPE_TABLE, [int(srv[0])])
                used = False
                if _table_exists(conn, HEADER_TABLE):
                    used = conn.execute(
                        'SELECT 1 FROM %s WHERE document_type_id = ? LIMIT 1'
                        % HEADER_TABLE, [int(srv[0])]).fetchone() is not None
                if not used:
                    conn.execute('DELETE FROM %s WHERE id = ?' % TYPE_TABLE,
                                 [int(srv[0])])
                    if _table_exists(conn, SEQUENCE_TABLE):
                        seq = conn.execute(
                            'SELECT id FROM %s WHERE code = ?' % SEQUENCE_TABLE,
                            [SRV_SEQUENCE['code']]).fetchone()
                        if seq:
                            conn.execute(
                                'DELETE FROM %s WHERE id = ?' % SEQUENCE_TABLE,
                                [int(seq[0])])
                else:
                    print('[v243] SKIP: 已有单据引用 SRV，保留类型与号段')

        # 尽力回退列
        for column, _ddl in NEW_TYPE_COLUMNS:
            _drop_column(conn, TYPE_TABLE, column)
        for column, _ddl in NEW_HEADER_COLUMNS:
            _drop_column(conn, HEADER_TABLE, column)
        conn.commit()
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)