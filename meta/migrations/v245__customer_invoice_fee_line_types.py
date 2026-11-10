# -*- coding: utf-8 -*-
"""v245 —— 销售发票费用行类型（运费 / 杂费）与费用行权限。

依据:
  docs/specs/sales-invoice-pricing-spec-2026-11-10.md
    §3 FR-006（费用行双层模型：计算层条件 → 落库层 FRT/MSC 行）
    §9.3.4 v245（行类型种子 + 权限 + 回滚）

内容:
  1. `type_definitions` 种子：`FRT`（运费行）/ `MSC`（杂费行），
     `scope_bo=customer_invoice`、`level=line`、`status=active`
  2. 权限 `customer_invoice:customer_invoice_fee_line`，授予 admin / default，
     并挂到 `customer_invoice-list` 菜单（required_permissions 与
     bo_bindings.include_actions 按值合并）

幂等：类型先查后插；权限 INSERT OR IGNORE；授权与菜单按值合并。
回滚：删权限与授权 → 清菜单引用 → 行类型无业务引用时删除，否则置 inactive。
"""

import json
import sqlite3
from pathlib import Path

from meta.migrations import v239__customer_invoice_permissions_menu as v239

MIGRATION_NAME = 'v245__customer_invoice_fee_line_types'

TYPE_TABLE = 'type_definitions'
LINE_TABLE = 'customer_invoice_lines'
PERMISSION_TABLE = 'permissions'
PERMISSION_SET_TABLE = 'permission_sets'
GRANT_TABLE = 'permission_set_permissions'
MENU_TABLE = 'menus'
MENU_PERMISSION_TABLE = 'menu_permissions'

SCOPE_BO = 'customer_invoice'
LEVEL = 'line'
MENU_CODE = 'customer_invoice-list'

#: 费用行类型种子：(code, name, line_category, delivery_relevant, description)
LINE_TYPE_SEEDS = (
    ('FRT', '运费行', 'freight', 0,
     '由运费条件生成的费用行，必带 source_rate_record_id / calc_result_id'),
    ('MSC', '杂费行', 'misc', 0,
     '由杂费条件生成的费用行，item_id 可为空，税率独立'),
)

FEE_ACTION = 'fee_line'
FEE_PERMISSION = 'customer_invoice:customer_invoice_fee_line'
PERMISSION = (FEE_PERMISSION, '销售发票费用行', 'customer_invoice', FEE_ACTION)
GRANT_TO_SETS = ('admin', 'default')


# --------------------------------------------------------------------- helpers

def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone() is not None


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


# ------------------------------------------------------------------- upgrade

def _do_line_types(conn):
    cols = _columns(conn, TYPE_TABLE)
    if not {'line_category', 'delivery_relevant'} <= cols:
        print('[v245] SKIP: type_definitions 缺 line 相关列（未播种行类型）')
        return
    for code, name, line_category, delivery_relevant, description in \
            LINE_TYPE_SEEDS:
        row = conn.execute(
            'SELECT id, line_category FROM %s WHERE scope_bo = ? AND level = ? '
            'AND code = ?' % TYPE_TABLE, [SCOPE_BO, LEVEL, code]).fetchone()
        if row:
            if not (row[1] or '').strip():
                conn.execute(
                    'UPDATE %s SET line_category = ? WHERE id = ?' % TYPE_TABLE,
                    [line_category, row[0]])
                print('[v245] ~ 行类型 %s line_category=%s' % (code, line_category))
            else:
                print('[v245] SKIP: 行类型 %s 已存在 (id=%s)' % (code, row[0]))
            continue
        conn.execute(
            'INSERT INTO %s (code, name, scope_bo, level, line_category, '
            'delivery_relevant, status, description, created_at) '
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'))"
            % TYPE_TABLE,
            (code, name, SCOPE_BO, LEVEL, line_category, delivery_relevant,
             description))
        print('[v245] + 行类型 %s（%s）' % (code, line_category))


def _do_permission(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        print('[v245] SKIP: permissions 表缺失（未建权限）')
        return
    code, name, resource_type, action = PERMISSION
    if conn.execute('SELECT 1 FROM permissions WHERE code = ?', [code]).fetchone():
        print('[v245] SKIP: 权限 %s 已存在' % code)
        return
    conn.execute(
        'INSERT INTO permissions (code, name, resource_type, action) '
        'VALUES (?, ?, ?, ?)', (code, name, resource_type, action))
    print('[v245] + 权限 %s' % code)


def _do_grants(conn):
    if not (_table_exists(conn, PERMISSION_TABLE)
            and _table_exists(conn, PERMISSION_SET_TABLE)
            and _table_exists(conn, GRANT_TABLE)):
        print('[v245] SKIP: 权限集相关表缺失（未授权）')
        return
    cols = _columns(conn, GRANT_TABLE)
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('[v245] SKIP: %s 无 permission_set_id/role_id' % GRANT_TABLE)
        return
    has_code_col = 'permission_code' in cols
    has_granted = 'granted' in cols

    prow = conn.execute('SELECT id FROM permissions WHERE code = ?',
                        [FEE_PERMISSION]).fetchone()
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
            params.append(FEE_PERMISSION)
        if conn.execute('SELECT 1 FROM %s WHERE %s' % (GRANT_TABLE, where),
                        params).fetchone():
            continue
        if has_code_col:
            conn.execute(
                'INSERT INTO %s (%s, permission_code, permission_id, granted, '
                "created_at) VALUES (?, ?, ?, 1, datetime('now'))"
                % (GRANT_TABLE, id_col),
                (row[0], FEE_PERMISSION, prow[0]))
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
        print('[v245] 授权 %s → %s' % (FEE_PERMISSION, set_code))


def _merge_menu_value(conn, table, column, value):
    if not (_table_exists(conn, table) and column in _columns(conn, table)):
        return
    row = conn.execute(
        'SELECT %s FROM %s WHERE menu_code = ?' % (column, table),
        [MENU_CODE]).fetchone()
    if row is None:
        return
    values = _load_json_list(row[0])
    if value in values:
        return
    values.append(value)
    conn.execute('UPDATE %s SET %s = ? WHERE menu_code = ?' % (table, column),
                 [_dump(values), MENU_CODE])
    print('[v245] 菜单 %s.%s += %s' % (table, column, value))


def _do_menu(conn):
    if not _table_exists(conn, MENU_TABLE):
        print('[v245] SKIP: menus 表缺失（菜单未同步）')
        return
    v239._insert_menu_if_missing(conn)
    _merge_menu_value(conn, MENU_TABLE, 'required_permissions', FEE_PERMISSION)
    _merge_menu_value(conn, MENU_PERMISSION_TABLE, 'required_permissions',
                      FEE_PERMISSION)

    if 'bo_bindings' not in _columns(conn, MENU_TABLE):
        return
    row = conn.execute('SELECT bo_bindings FROM menus WHERE menu_code = ?',
                       [MENU_CODE]).fetchone()
    bindings = _load_json_list(row[0] if row else None)
    changed = False
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        actions = binding.get('include_actions')
        if isinstance(actions, list) and FEE_ACTION not in actions:
            actions.append(FEE_ACTION)
            changed = True
    if changed:
        conn.execute('UPDATE menus SET bo_bindings = ? WHERE menu_code = ?',
                     [_dump(bindings), MENU_CODE])
        print('[v245] 菜单 bo_bindings 追加 %s' % FEE_ACTION)


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v245] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, TYPE_TABLE):
            print('[v245] SKIP: type_definitions 表不存在')
            return False
        _do_line_types(conn)
        _do_permission(conn)
        _do_grants(conn)
        _do_menu(conn)
        conn.commit()
        print('[v245] 完成')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _verify_line_types(conn):
    for code, _name, line_category, _rel, _desc in LINE_TYPE_SEEDS:
        row = conn.execute(
            'SELECT line_category, status FROM %s WHERE scope_bo = ? '
            'AND level = ? AND code = ?' % TYPE_TABLE,
            [SCOPE_BO, LEVEL, code]).fetchone()
        if not row:
            print('[v245 verify] FAIL: 缺行类型 %s' % code)
            return False
        if (row[0] or '') != line_category:
            print('[v245 verify] FAIL: 行类型 %s line_category 不符（%s）'
                  % (code, row[0]))
            return False
        if (row[1] or '') != 'active':
            print('[v245 verify] FAIL: 行类型 %s 非 active' % code)
            return False
    return True


def verify(db_path):
    path = Path(db_path)
    if not path.exists():
        return False
    conn = _connect(path)
    try:
        if not _table_exists(conn, TYPE_TABLE):
            return False
        if not _verify_line_types(conn):
            return False
        if not _table_exists(conn, PERMISSION_TABLE):
            print('[v245 verify] FAIL: permissions 表缺失')
            return False
        if not conn.execute('SELECT 1 FROM permissions WHERE code = ?',
                            [FEE_PERMISSION]).fetchone():
            print('[v245 verify] FAIL: 缺权限 %s' % FEE_PERMISSION)
            return False
        return True
    finally:
        conn.close()


# ------------------------------------------------------------------ rollback

def _delete_grants(conn):
    if not _table_exists(conn, GRANT_TABLE):
        return
    cols = _columns(conn, GRANT_TABLE)
    prow = conn.execute('SELECT id FROM permissions WHERE code = ?',
                        [FEE_PERMISSION]).fetchone() \
        if _table_exists(conn, PERMISSION_TABLE) else None
    if 'permission_code' in cols:
        conn.execute('DELETE FROM %s WHERE permission_code = ?' % GRANT_TABLE,
                     [FEE_PERMISSION])
    if prow and 'permission_id' in cols:
        conn.execute('DELETE FROM %s WHERE permission_id = ?' % GRANT_TABLE,
                     [prow[0]])
    print('[v245] - 权限授权 %s' % FEE_PERMISSION)


def _remove_menu_value(conn, table, column, value):
    if not (_table_exists(conn, table) and column in _columns(conn, table)):
        return
    row = conn.execute(
        'SELECT %s FROM %s WHERE menu_code = ?' % (column, table),
        [MENU_CODE]).fetchone()
    if row is None:
        return
    values = _load_json_list(row[0])
    if value not in values:
        return
    values = [item for item in values if item != value]
    conn.execute('UPDATE %s SET %s = ? WHERE menu_code = ?' % (table, column),
                 [_dump(values), MENU_CODE])


def _remove_menu(conn):
    _remove_menu_value(conn, MENU_TABLE, 'required_permissions', FEE_PERMISSION)
    _remove_menu_value(conn, MENU_PERMISSION_TABLE, 'required_permissions',
                       FEE_PERMISSION)
    if 'bo_bindings' not in _columns(conn, MENU_TABLE):
        return
    row = conn.execute('SELECT bo_bindings FROM menus WHERE menu_code = ?',
                       [MENU_CODE]).fetchone()
    if row is None:
        return
    bindings = _load_json_list(row[0])
    changed = False
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        actions = binding.get('include_actions')
        if isinstance(actions, list) and FEE_ACTION in actions:
            binding['include_actions'] = [
                item for item in actions if item != FEE_ACTION]
            changed = True
    if changed:
        conn.execute('UPDATE menus SET bo_bindings = ? WHERE menu_code = ?',
                     [_dump(bindings), MENU_CODE])
        print('[v245] - 菜单动作 %s' % FEE_ACTION)


def _remove_line_types(conn):
    for code, _name, _category, _rel, _desc in LINE_TYPE_SEEDS:
        row = conn.execute(
            'SELECT id FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
            % TYPE_TABLE, [SCOPE_BO, LEVEL, code]).fetchone()
        if not row:
            continue
        used = conn.execute(
            'SELECT 1 FROM %s WHERE line_type_id = ? LIMIT 1' % LINE_TABLE,
            [row[0]]).fetchone() if _table_exists(conn, LINE_TABLE) else None
        if used:
            conn.execute(
                "UPDATE %s SET status = 'inactive' WHERE id = ?" % TYPE_TABLE,
                [row[0]])
            print('[v245] ~ 行类型 %s 有业务引用，置 inactive' % code)
        else:
            conn.execute('DELETE FROM %s WHERE id = ?' % TYPE_TABLE, [row[0]])
            print('[v245] - 行类型 %s' % code)


def rollback(db_path):
    path = Path(db_path)
    if not path.exists():
        return False
    conn = _connect(path)
    try:
        _remove_menu(conn)
        _delete_grants(conn)
        if _table_exists(conn, PERMISSION_TABLE):
            conn.execute('DELETE FROM permissions WHERE code = ?',
                         [FEE_PERMISSION])
            print('[v245] - 权限 %s' % FEE_PERMISSION)
        if _table_exists(conn, TYPE_TABLE):
            _remove_line_types(conn)
        conn.commit()
        print('[v245] 回滚完成')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


migrate = upgrade