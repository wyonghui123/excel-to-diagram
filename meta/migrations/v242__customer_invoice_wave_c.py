# -*- coding: utf-8 -*-
"""v242 —— 开票完备性补齐（S8 Wave C）。

内容：
  1. `sales_order_lines` 加 5 个开票计划字段（期数 / 间隔月 / 锚点日 / 提前滞后天 / 尾差口径）。
  2. 权限 `customer_invoice:customer_invoice_submit`，授予 admin / default，并挂到
     `customer_invoice-list` 菜单（复用 v239 的菜单补插与同步逻辑）。
  3. doc_flow 规则 `return_shipment_line_to_credit_memo`
     （shipment_line → customer_invoice_line，pool=billing）。
  4. 索引 idx_sol_billing_plan / idx_cil_original_line（先查后建）。

幂等：列先查后加；权限 INSERT OR IGNORE；规则 ON CONFLICT DO UPDATE；
      索引 CREATE INDEX IF NOT EXISTS；菜单 JSON 按值合并。

回滚：删规则 / 索引 / 授权 / 权限；菜单 JSON 移除 submit；尽力删除 5 列。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from meta.migrations import v239__customer_invoice_permissions_menu as v239

MIGRATION_NAME = 'v242__customer_invoice_wave_c'

ORDER_LINE_TABLE = 'sales_order_lines'
LINE_TABLE = 'customer_invoice_lines'

PERMISSION_TABLE = 'permissions'
PERMISSION_SET_TABLE = 'permission_sets'
GRANT_TABLE = 'permission_set_permissions'
MENU_TABLE = 'menus'
MENU_PERMISSION_TABLE = 'menu_permissions'
RULE_TABLE = 'doc_flow_rule'

MENU_CODE = 'customer_invoice-list'
SUBMIT_ACTION = 'submit'
SUBMIT_PERMISSION = 'customer_invoice:customer_invoice_submit'
PERMISSION = (SUBMIT_PERMISSION, '销售发票提交', 'customer_invoice', SUBMIT_ACTION)
GRANT_TO_SETS = ('admin', 'default')

#: 5 个计划字段（列名, DDL 片段）
NEW_COLUMNS = (
    ('billing_period_count', 'INTEGER NULL'),
    ('billing_interval_months', 'INTEGER NULL DEFAULT 1'),
    ('billing_anchor_date', 'DATE NULL'),
    ('billing_lead_days', 'INTEGER NULL DEFAULT 0'),
    ('billing_proration', "VARCHAR(8) NULL DEFAULT 'none'"),
)

PRORATION_VALUES = ('none', 'daily')

RULE_ID = 'return_shipment_line_to_credit_memo'
RULE = {
    'rule_id': RULE_ID,
    'source_bo': 'shipment_line',
    'target_bo': 'customer_invoice_line',
    'source_qty_field': 'qty',
    'pool': 'billing',
}

INDEXES = (
    ('idx_sol_billing_plan', ORDER_LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_sol_billing_plan '
     'ON sales_order_lines (billing_relevance, billing_method)'),
    ('idx_cil_original_line', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_cil_original_line '
     'ON customer_invoice_lines (original_invoice_line_id)'),
)


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


def _index_covers(conn, table, column):
    """是否存在任意索引覆盖该列（接受等价索引，不强制名字）。"""
    if not _table_exists(conn, table):
        return False
    for row in conn.execute('PRAGMA index_list(%s)' % table):
        info = conn.execute('PRAGMA index_info("%s")' % row[1]).fetchall()
        if any(item[2] == column for item in info):
            return True
    return False


def _load_json_list(raw):
    try:
        values = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return []
    return values if isinstance(values, list) else []


def _dump(values):
    return json.dumps(values, ensure_ascii=False)


# ------------------------------------------------------------------- upgrade

def _do_columns(conn):
    if not _table_exists(conn, ORDER_LINE_TABLE):
        print('[v242] SKIP: %s 表不存在（未加列）' % ORDER_LINE_TABLE)
        return 0
    have = _columns(conn, ORDER_LINE_TABLE)
    added = 0
    for column, ddl in NEW_COLUMNS:
        if column in have:
            print('[v242] SKIP: 列 %s.%s 已存在' % (ORDER_LINE_TABLE, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (ORDER_LINE_TABLE, column, ddl))
        added += 1
        print('[v242] ALTER: 列 %s.%s' % (ORDER_LINE_TABLE, column))
    return added


def _do_permission(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        print('[v242] SKIP: %s 表不存在（未写权限）' % PERMISSION_TABLE)
        return False
    cur = conn.execute(
        'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
        'VALUES (?, ?, ?, ?)', PERMISSION)
    print('[v242] 权限 %s %s' % (SUBMIT_PERMISSION,
                                 '已新增' if cur.rowcount else '已存在'))
    return True


def _do_grants(conn):
    if not (_table_exists(conn, PERMISSION_TABLE)
            and _table_exists(conn, PERMISSION_SET_TABLE)
            and _table_exists(conn, GRANT_TABLE)):
        print('[v242] SKIP: 权限集相关表缺失（未授权）')
        return
    cols = _columns(conn, GRANT_TABLE)
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('[v242] SKIP: %s 无 permission_set_id/role_id' % GRANT_TABLE)
        return
    has_code_col = 'permission_code' in cols
    has_granted = 'granted' in cols

    prow = conn.execute('SELECT id FROM permissions WHERE code = ?',
                        [SUBMIT_PERMISSION]).fetchone()
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
            params.append(SUBMIT_PERMISSION)
        if conn.execute('SELECT 1 FROM %s WHERE %s' % (GRANT_TABLE, where),
                        params).fetchone():
            continue
        if has_code_col:
            conn.execute(
                'INSERT INTO %s (%s, permission_code, permission_id, granted, '
                "created_at) VALUES (?, ?, ?, ?, datetime('now'))"
                % (GRANT_TABLE, id_col),
                (row[0], SUBMIT_PERMISSION, prow[0], 1))
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
        print('[v242] 授权 %s → %s' % (SUBMIT_PERMISSION, set_code))


def _do_menu(conn):
    if not _table_exists(conn, MENU_TABLE):
        print('[v242] SKIP: %s 表不存在（菜单未同步）' % MENU_TABLE)
        return
    v239._insert_menu_if_missing(conn)

    cols = _columns(conn, MENU_TABLE)
    if 'required_permissions' in cols:
        row = conn.execute(
            'SELECT required_permissions FROM %s WHERE menu_code = ?'
            % MENU_TABLE, [MENU_CODE]).fetchone()
        values = _load_json_list(row[0] if row else None)
        if SUBMIT_PERMISSION not in values:
            values.append(SUBMIT_PERMISSION)
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
            if isinstance(actions, list) and SUBMIT_ACTION not in actions:
                actions.append(SUBMIT_ACTION)
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
                if SUBMIT_PERMISSION not in values:
                    values.append(SUBMIT_PERMISSION)
                conn.execute(
                    'UPDATE %s SET required_permissions = ? WHERE menu_code = ?'
                    % MENU_PERMISSION_TABLE, [_dump(values), MENU_CODE])
    print('[v242] 菜单 %s 权限同步完成' % MENU_CODE)


def _do_rule(conn):
    if not _table_exists(conn, RULE_TABLE):
        print('[v242] SKIP: %s 表不存在（未写规则）' % RULE_TABLE)
        return
    now = datetime.now().isoformat(timespec='seconds')
    conn.execute(
        """
        INSERT INTO doc_flow_rule
            (rule_id, source_bo, target_bo, source_qty_field, pool, status,
             field_map, split_key, target_line_bo, head_fk_field,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', '{}', '[]', '', '', ?, ?)
        ON CONFLICT(rule_id) DO UPDATE SET
            source_bo=excluded.source_bo,
            target_bo=excluded.target_bo,
            source_qty_field=excluded.source_qty_field,
            pool=excluded.pool,
            status='active',
            updated_at=excluded.updated_at
        """,
        (RULE['rule_id'], RULE['source_bo'], RULE['target_bo'],
         RULE['source_qty_field'], RULE['pool'], now, now))
    print('[v242] doc_flow 规则 %s 已写入（pool=%s）'
          % (RULE_ID, RULE['pool']))


def _do_indexes(conn):
    for name, table, sql in INDEXES:
        if _index_exists(conn, name):
            print('[v242] SKIP: 索引 %s 已存在' % name)
            continue
        if not _table_exists(conn, table):
            print('[v242] SKIP: 索引 %s 依赖表 %s 不存在' % (name, table))
            continue
        conn.execute(sql)
        print('[v242] 索引 %s 已建立' % name)


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v242] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, ORDER_LINE_TABLE):
            print('[v242] SKIP: %s 表不存在' % ORDER_LINE_TABLE)
            return False
        _do_columns(conn)
        _do_permission(conn)
        _do_grants(conn)
        _do_menu(conn)
        _do_rule(conn)
        _do_indexes(conn)
        conn.commit()
        return True
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def _verify_columns(conn):
    if not _table_exists(conn, ORDER_LINE_TABLE):
        print('[v242] verify: 缺表 %s' % ORDER_LINE_TABLE)
        return False
    have = _columns(conn, ORDER_LINE_TABLE)
    ok = True
    for column, _ddl in NEW_COLUMNS:
        if column not in have:
            print('[v242] verify: 缺列 %s.%s' % (ORDER_LINE_TABLE, column))
            ok = False
    return ok


def _verify_permission(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        print('[v242] verify: 缺表 %s' % PERMISSION_TABLE)
        return False
    if not conn.execute('SELECT 1 FROM permissions WHERE code = ?',
                        [SUBMIT_PERMISSION]).fetchone():
        print('[v242] verify: 缺权限 %s' % SUBMIT_PERMISSION)
        return False
    if not (_table_exists(conn, PERMISSION_SET_TABLE)
            and _table_exists(conn, GRANT_TABLE)):
        return True
    cols = _columns(conn, GRANT_TABLE)
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code = ? AND is_active = 1',
            [set_code]).fetchone()
        if not row:
            continue
        if 'permission_code' in cols:
            found = conn.execute(
                'SELECT 1 FROM %s WHERE permission_set_id = ? AND '
                'permission_code = ?' % GRANT_TABLE,
                [row[0], SUBMIT_PERMISSION]).fetchone()
        else:
            prow = conn.execute('SELECT id FROM permissions WHERE code = ?',
                                [SUBMIT_PERMISSION]).fetchone()
            found = conn.execute(
                'SELECT 1 FROM %s WHERE permission_set_id = ? AND '
                'permission_id = ?' % GRANT_TABLE,
                [row[0], prow[0] if prow else None]).fetchone()
        if not found:
            print('[v242] verify: 权限 %s 未授予 %s'
                  % (SUBMIT_PERMISSION, set_code))
            return False
    return True


def _verify_menu(conn):
    if not _table_exists(conn, MENU_TABLE):
        return True
    row = conn.execute(
        'SELECT 1 FROM %s WHERE menu_code = ?' % MENU_TABLE,
        [MENU_CODE]).fetchone()
    if not row:
        print('[v242] verify: 缺菜单 %s' % MENU_CODE)
        return False
    if 'required_permissions' in _columns(conn, MENU_TABLE):
        raw = conn.execute(
            'SELECT required_permissions FROM %s WHERE menu_code = ?'
            % MENU_TABLE, [MENU_CODE]).fetchone()[0]
        if SUBMIT_PERMISSION not in _load_json_list(raw):
            print('[v242] verify: 菜单 %s 未包含 submit 权限' % MENU_CODE)
            return False
    return True


def _verify_rule(conn):
    if not _table_exists(conn, RULE_TABLE):
        print('[v242] verify: 缺表 %s' % RULE_TABLE)
        return False
    row = conn.execute(
        'SELECT source_bo, target_bo, source_qty_field, pool, status '
        'FROM %s WHERE rule_id = ?' % RULE_TABLE, [RULE_ID]).fetchone()
    if not row:
        print('[v242] verify: 缺规则 %s' % RULE_ID)
        return False
    expected = (RULE['source_bo'], RULE['target_bo'],
                RULE['source_qty_field'], RULE['pool'], 'active')
    if tuple(row) != expected:
        print('[v242] verify: 规则 %s 字段不符 %s' % (RULE_ID, tuple(row)))
        return False
    return True


def _verify_indexes(conn):
    ok = True
    for name, table, _sql in INDEXES:
        if not _table_exists(conn, table):
            continue
        column = 'original_invoice_line_id' if name == 'idx_cil_original_line' \
            else 'billing_relevance'
        if not (_index_exists(conn, name) or _index_covers(conn, table, column)):
            print('[v242] verify: 缺索引 %s（或等价索引）' % name)
            ok = False
    return ok


def _verify_values(conn):
    if not _table_exists(conn, ORDER_LINE_TABLE):
        return False
    have = _columns(conn, ORDER_LINE_TABLE)
    if any(column not in have for column, _ddl in NEW_COLUMNS):
        return False
    ok = True
    bad = conn.execute(
        "SELECT COUNT(*) FROM %s WHERE billing_proration IS NOT NULL "
        "AND billing_proration NOT IN ('none', 'daily')" % ORDER_LINE_TABLE
    ).fetchone()[0]
    if bad:
        print('[v242] verify: billing_proration 非法值 %s 行' % bad)
        ok = False
    bad = conn.execute(
        'SELECT COUNT(*) FROM %s WHERE billing_period_count IS NOT NULL '
        'AND (billing_period_count < 1 OR billing_period_count > 60)'
        % ORDER_LINE_TABLE).fetchone()[0]
    if bad:
        print('[v242] verify: billing_period_count 越界 %s 行' % bad)
        ok = False
    bad = conn.execute(
        'SELECT COUNT(*) FROM %s WHERE billing_interval_months IS NOT NULL '
        'AND (billing_interval_months < 1 OR billing_interval_months > 12)'
        % ORDER_LINE_TABLE).fetchone()[0]
    if bad:
        print('[v242] verify: billing_interval_months 越界 %s 行' % bad)
        ok = False
    bad = conn.execute(
        "SELECT COUNT(*) FROM %s WHERE billing_relevance = 'plan' "
        "AND billing_method = 'time_and_material' "
        'AND billing_period_count IS NULL' % ORDER_LINE_TABLE).fetchone()[0]
    if bad:
        print('[v242] verify: time_and_material plan 行缺期数 %s 行' % bad)
        ok = False
    return ok


def verify(db_path):
    path = Path(db_path)
    if not path.exists():
        return False

    conn = _connect(path)
    try:
        checks = (
            _verify_columns(conn),
            _verify_permission(conn),
            _verify_menu(conn),
            _verify_rule(conn),
            _verify_indexes(conn),
            _verify_values(conn),
        )
        ok = all(checks)
        print('[v242] verify: %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


# ------------------------------------------------------------------ rollback

def _remove_from_menu(conn):
    for table in (MENU_TABLE, MENU_PERMISSION_TABLE):
        if not _table_exists(conn, table):
            continue
        if 'required_permissions' not in _columns(conn, table):
            continue
        row = conn.execute(
            'SELECT required_permissions FROM %s WHERE menu_code = ?' % table,
            [MENU_CODE]).fetchone()
        if row is None:
            continue
        values = [item for item in _load_json_list(row[0])
                  if item != SUBMIT_PERMISSION]
        conn.execute(
            'UPDATE %s SET required_permissions = ? WHERE menu_code = ?' % table,
            [_dump(values), MENU_CODE])


def _remove_grant_and_permission(conn):
    if _table_exists(conn, GRANT_TABLE):
        cols = _columns(conn, GRANT_TABLE)
        if 'permission_code' in cols:
            conn.execute('DELETE FROM %s WHERE permission_code = ?' % GRANT_TABLE,
                         [SUBMIT_PERMISSION])
        if 'permission_id' in cols and _table_exists(conn, PERMISSION_TABLE):
            row = conn.execute('SELECT id FROM permissions WHERE code = ?',
                               [SUBMIT_PERMISSION]).fetchone()
            if row:
                conn.execute(
                    'DELETE FROM %s WHERE permission_id = ?' % GRANT_TABLE,
                    [row[0]])
    if _table_exists(conn, PERMISSION_TABLE):
        conn.execute('DELETE FROM permissions WHERE code = ?', [SUBMIT_PERMISSION])


def _drop_columns(conn):
    if not _table_exists(conn, ORDER_LINE_TABLE):
        return
    for column, _ddl in NEW_COLUMNS:
        if column not in _columns(conn, ORDER_LINE_TABLE):
            continue
        try:
            conn.execute('ALTER TABLE %s DROP COLUMN %s'
                         % (ORDER_LINE_TABLE, column))
            print('[v242] rollback: 删除列 %s.%s'
                  % (ORDER_LINE_TABLE, column))
        except sqlite3.OperationalError as exc:
            print('[v242] rollback: 列 %s.%s 无法删除（%s），保留'
                  % (ORDER_LINE_TABLE, column, exc))


def rollback(db_path):
    path = Path(db_path)
    if not path.exists():
        return False

    conn = _connect(path)
    try:
        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute('DROP INDEX %s' % name)
        if _table_exists(conn, RULE_TABLE):
            conn.execute('DELETE FROM %s WHERE rule_id = ?' % RULE_TABLE,
                         [RULE_ID])
        _remove_from_menu(conn)
        _remove_grant_and_permission(conn)
        _drop_columns(conn)
        conn.commit()
        print('[v242] rollback: 已删除规则 %s / 索引 / submit 权限 / 5 列'
              % RULE_ID)
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)