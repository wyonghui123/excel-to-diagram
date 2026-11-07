# -*- coding: utf-8 -*-
"""[v230 2026-11-07] 无单收货（Oracle 双开关）

依据:
  docs/specs/bo-metadata-gap-2026-11-06（T8.3-b 后续：无上游创建范式）
  SAP 501/511（无采购订单收货）与 Oracle Fusion「Allow unordered receipts」
  （仓库接收参数）+「AllowUnorderedReceiptsFlag」（物料标志）双开口径。

范围:
  1. 加列（存在则 SKIP）：
       receipts.received_from_party_id INTEGER
       receipts.reason_code VARCHAR(200)
       items.allow_unordered_receipt INTEGER NOT NULL DEFAULT 0
       inventory_adjustment_lines.cost_center_id INTEGER
       inventory_adjustment_lines.expense_account_code VARCHAR(200)
  2. 种子移动类型 RCV_UNORDERED（category=receipt, direction=in）。
  3. 种子控制参数 allow_unordered_receipt（bool，默认 0 = 关闭）。
  4. 种子权限 receipt:receipt_unordered，并授予 admin / default 权限集。

幂等:
  列 / 类型 / 参数 / 权限均先查后用；重复执行打印 [SKIP]。

回滚:
  删除种子类型 / 参数定义 / 权限与授权；列保留（SQLite ALTER 无法安全回退）。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v230__unordered_receipt'

TYPES_TABLE = 'inventory_transaction_types'
TX_TABLE = 'inventory_transactions'

#: (表, 列, 列定义)
COLUMN_ADDS = (
    ('receipts', 'received_from_party_id', 'INTEGER'),
    ('receipts', 'reason_code', 'VARCHAR(30)'),
    ('items', 'allow_unordered_receipt', 'INTEGER NOT NULL DEFAULT 0'),
    ('inventory_adjustment_lines', 'cost_center_id', 'INTEGER'),
    ('inventory_adjustment_lines', 'expense_account_code', 'VARCHAR(40)'),
)

#: (code, name, category, direction, affects_on_hand, sort_order, description)
RCV_UNORDERED = (
    'RCV_UNORDERED', '无单收货入库', 'receipt', 'in', 1, 70,
    '无采购 / 调拨 / 工单来源的直接收货（需组织参数与物料开关双开）',
)

PARAM_DEF = ('allow_unordered_receipt', '允许无单收货', 'bool', '0')
PARAM_DOMAIN = 'procurement'
PARAM_TARGET_BO = 'receipt'
PARAM_DESC = '默认 0（关闭，对标 Oracle 默认 No）：需同时开启物料「允许无单收货」'

PERMISSION = ('receipt:receipt_unordered', '无单收货', 'receipt', 'unordered')
GRANT_TO_SETS = ('admin', 'default')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        return {row[1] for row in conn.execute(
            'PRAGMA table_info(%s)' % table).fetchall()}
    except sqlite3.Error:
        return set()


def _do_columns(conn: sqlite3.Connection) -> None:
    for table, column, ddl in COLUMN_ADDS:
        if not _table_exists(conn, table):
            print('  - [SKIP] 表 %s 不存在，跳过 %s' % (table, column))
            continue
        if column in _columns(conn, table):
            print('  - [SKIP] %s.%s 已存在' % (table, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, ddl))
        print('  - [NEW] %s.%s' % (table, column))


def _do_type(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TYPES_TABLE):
        print('  - [SKIP] %s 不存在，跳过移动类型' % TYPES_TABLE)
        return
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % TYPES_TABLE, (RCV_UNORDERED[0],)
    ).fetchone()
    if row:
        print('  - [SKIP] 移动类型 %s 已存在' % RCV_UNORDERED[0])
        return
    conn.execute(
        'INSERT INTO %s (code, name, category, direction, affects_on_hand, '
        'status, sort_order, description, created_at) '
        "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, datetime('now'))" % TYPES_TABLE,
        (RCV_UNORDERED[0], RCV_UNORDERED[1], RCV_UNORDERED[2],
         RCV_UNORDERED[3], RCV_UNORDERED[4], RCV_UNORDERED[5],
         RCV_UNORDERED[6]),
    )
    print('  - [NEW] 移动类型 %s（%s）' % (RCV_UNORDERED[0], RCV_UNORDERED[1]))


def _do_param(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'control_parameter_defs'):
        print('  - [SKIP] control_parameter_defs 不存在，跳过参数种子')
        return
    code, name, value_type, default_value = PARAM_DEF
    row = conn.execute(
        'SELECT id FROM control_parameter_defs WHERE code = ?', (code,)
    ).fetchone()
    if row:
        conn.execute(
            'UPDATE control_parameter_defs SET name=?, domain=?, value_type=?, '
            'target_bo=?, default_value=?, description=?, status=? WHERE code=?',
            (name, PARAM_DOMAIN, value_type, PARAM_TARGET_BO, default_value,
             PARAM_DESC, 'active', code),
        )
        print('  - [SKIP] 参数定义 %s 已存在（刷新元数据）' % code)
        return
    conn.execute(
        'INSERT INTO control_parameter_defs '
        '(code, name, domain, value_type, target_bo, default_value, '
        ' status, description, created_at) '
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'))",
        (code, name, PARAM_DOMAIN, value_type, PARAM_TARGET_BO, default_value,
         PARAM_DESC),
    )
    print('  - [NEW] 参数定义 %s=%s' % (code, default_value))


def _do_permission(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - [SKIP] permissions 不存在，跳过权限种子')
        return
    code, name, resource_type, action = PERMISSION
    cur = conn.execute(
        'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
        'VALUES (?, ?, ?, ?)',
        (code, name, resource_type, action),
    )
    if cur.rowcount:
        print('  - [NEW] 权限 %s（%s）' % (code, name))


def _do_grants(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'permissions')
            and _table_exists(conn, 'permission_sets')
            and _table_exists(conn, 'permission_set_permissions')):
        print('  - [SKIP] 权限集相关表缺失，跳过授权')
        return
    cols = _columns(conn, 'permission_set_permissions')
    id_col = 'permission_set_id' if 'permission_set_id' in cols else (
        'role_id' if 'role_id' in cols else None)
    if not id_col:
        print('  - [SKIP] permission_set_permissions 缺权限集列')
        return
    has_code_col = 'permission_code' in cols
    code = PERMISSION[0]
    prow = conn.execute(
        'SELECT id FROM permissions WHERE code = ?', (code,)).fetchone()
    if not prow:
        return
    for set_code in GRANT_TO_SETS:
        srow = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            (set_code,),
        ).fetchone()
        if not srow:
            continue
        if conn.execute(
            'SELECT 1 FROM permission_set_permissions WHERE %s = ? '
            'AND permission_id = ?' % id_col, (srow[0], prow[0])
        ).fetchone():
            continue
        if has_code_col:
            conn.execute(
                'INSERT INTO permission_set_permissions '
                '(%s, permission_code, permission_id, granted, created_at) '
                "VALUES (?, ?, ?, 1, datetime('now'))" % id_col,
                (srow[0], code, prow[0]),
            )
        else:
            conn.execute(
                'INSERT INTO permission_set_permissions '
                '(%s, permission_id, granted, created_at) '
                "VALUES (?, ?, 1, datetime('now'))" % id_col,
                (srow[0], prow[0]),
            )
        print('  - [NEW] 授权 %s → %s' % (code, set_code))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v230] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v230] 开始: 无单收货（Oracle 双开关）')
        _do_columns(conn)
        _do_type(conn)
        _do_param(conn)
        _do_permission(conn)
        _do_grants(conn)
        conn.commit()
        print('[v230] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v230] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> dict:
    db_path = Path(db_path)
    if not db_path.exists():
        return {'ok': False, 'error': 'DB 不存在: %s' % db_path}
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for table, column, _ddl in COLUMN_ADDS:
            if not _table_exists(conn, table):
                return {'ok': False, 'error': '缺表 %s' % table}
            if column not in _columns(conn, table):
                return {'ok': False, 'error': '缺列 %s.%s' % (table, column)}
        if _table_exists(conn, TYPES_TABLE):
            row = conn.execute(
                'SELECT category, direction, status FROM %s WHERE code = ?'
                % TYPES_TABLE, (RCV_UNORDERED[0],)).fetchone()
            if not row:
                return {'ok': False, 'error': '缺移动类型 %s' % RCV_UNORDERED[0]}
            if row[0] != 'receipt' or row[1] != 'in' or row[2] != 'active':
                return {'ok': False, 'error': '移动类型字段不符: %s' % (row,)}
        if _table_exists(conn, 'control_parameter_defs'):
            row = conn.execute(
                'SELECT default_value FROM control_parameter_defs WHERE code = ?',
                (PARAM_DEF[0],)).fetchone()
            if not row:
                return {'ok': False, 'error': '缺参数定义 %s' % PARAM_DEF[0]}
            if str(row[0]) != PARAM_DEF[3]:
                return {'ok': False, 'error': '参数默认值不符: %s' % (row[0],)}
        if _table_exists(conn, 'permissions'):
            row = conn.execute(
                'SELECT id FROM permissions WHERE code = ?',
                (PERMISSION[0],)).fetchone()
            if not row:
                return {'ok': False, 'error': '缺权限 %s' % PERMISSION[0]}
        return {'ok': True, 'error': None}
    finally:
        conn.close()


def rollback(db_path: Path) -> None:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _table_exists(conn, TYPES_TABLE):
            row = conn.execute(
                'SELECT id FROM %s WHERE code = ?' % TYPES_TABLE,
                (RCV_UNORDERED[0],)).fetchone()
            if row and _table_exists(conn, TX_TABLE):
                used = conn.execute(
                    'SELECT 1 FROM %s WHERE transaction_type_id = ? LIMIT 1'
                    % TX_TABLE, (row[0],)).fetchone()
                if used:
                    print('[v230] %s 已被库存事务引用，保留' % RCV_UNORDERED[0])
                else:
                    conn.execute(
                        'DELETE FROM %s WHERE id = ?' % TYPES_TABLE, (row[0],))
                    print('[v230] DEL 移动类型 %s' % RCV_UNORDERED[0])
        if _table_exists(conn, 'permission_set_permissions'):
            ids = [r[0] for r in conn.execute(
                'SELECT id FROM permissions WHERE code = ?',
                (PERMISSION[0],)).fetchall()]
            for pid in ids:
                conn.execute(
                    'DELETE FROM permission_set_permissions WHERE permission_id = ?',
                    (pid,))
            conn.execute(
                'DELETE FROM permissions WHERE code = ?', (PERMISSION[0],))
            print('[v230] DEL 权限 %s' % PERMISSION[0])
        if _table_exists(conn, 'control_parameter_values'):
            row = conn.execute(
                'SELECT id FROM control_parameter_defs WHERE code = ?',
                (PARAM_DEF[0],)).fetchone()
            if row:
                conn.execute(
                    'DELETE FROM control_parameter_values '
                    'WHERE control_parameter_id = ?', (row[0],))
        if _table_exists(conn, 'control_parameter_defs'):
            conn.execute(
                'DELETE FROM control_parameter_defs WHERE code = ?',
                (PARAM_DEF[0],))
            print('[v230] DEL 参数定义 %s' % PARAM_DEF[0])
        conn.commit()
        print('[v230] 加列保留（SQLite 限制）')
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('meta/architecture.db')
    migrate(target)
    print(verify(target))