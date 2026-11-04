# -*- coding: utf-8 -*-
"""[v201 2026-11-03] 库存模型基础（INV-1 数量账与余额投影）

依据:
  .trae/specs/excel-to-diagram/define-inventory-model/spec.md
  .trae/specs/excel-to-diagram/define-inventory-model/tasks.md

范围:
  1. 建 3 张表：
       inventory_transaction_types（移动类型字典）
       inventory_transactions（追加式数量事件账）
       inventory_balances（余额投影）
  2. 唯一索引：
       inventory_transactions(source_event_key, source_line_id)
       inventory_transactions(reversal_of_transaction_id) 部分唯一
       inventory_balances(org_id, location_id, item_id, batch_id, stock_status)
  3. 移动类型种子：RCV_PO / RCV_TO / ISSUE_TO_SHIP / OPENING / REVERSAL
  4. 编号序列 INV：INV-{DATE:yyyymm}-{SEQ:6}，date_field=transaction_date
  5. 权限 4 条（只读）：inventory_transaction / inventory_balance 各 read、list
  6. 菜单 inventory-balance-management（父 procurement，primary=inventory_balance）
  7. 控制参数：inventory_allow_negative=0、inventory_posting_enabled=0
  8. orgs.default_inventory_location_id 列（可空）

幂等:
  表 / 索引 / 类型 / 序列 / 权限 / 菜单 / 参数先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单 + 序列 + 权限 + 参数定义 + 本迁移索引与表；
  已授予的 permission_set_permissions 行一并清理；org 列保留（仅清空取值）。
"""
import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v201__inventory_foundation'

TYPES_TABLE = 'inventory_transaction_types'
TX_TABLE = 'inventory_transactions'
BAL_TABLE = 'inventory_balances'

STOCK_STATUSES = ('unrestricted', 'inspection', 'blocked')

#: (code, name, category, direction, affects_on_hand, sort_order, description)
TRANSACTION_TYPES = (
    ('RCV_PO', '采购收货入库', 'receipt', 'in', 1, 10,
     '采购订单来源收货过账形成的入库'),
    ('RCV_TO', '调拨收货入库', 'receipt', 'in', 1, 20,
     '调拨单来源收货过账形成的入库'),
    ('ISSUE_TO_SHIP', '调拨发货出库', 'issue', 'out', 1, 30,
     '调拨单发货形成的出库'),
    ('OPENING', '期初库存导入', 'adjustment', 'in', 1, 40,
     '上线期初余额初始化'),
    ('REVERSAL', '反冲', 'adjustment', 'out', 1, 50,
     '对原库存事务的反向冲销'),
)

#: (code, name, pattern, date_field, start_value, on_exhaust, description)
NUMBER_SEQUENCE = (
    'INV', '库存事务编号', 'INV-{DATE:yyyymm}-{SEQ:6}', 'transaction_date', 1,
    'error', '库存事务取号：INV-年月-6 位流水，按月度重置',
)

TABLES = (
    (TYPES_TABLE, """
CREATE TABLE IF NOT EXISTS inventory_transaction_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(20) NOT NULL DEFAULT 'receipt',
    direction VARCHAR(10) NOT NULL DEFAULT 'in',
    affects_on_hand INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    sort_order INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    created_at DATETIME,
    CHECK (category IN ('receipt', 'issue', 'transfer', 'adjustment')),
    CHECK (direction IN ('in', 'out')),
    CHECK (status IN ('active', 'inactive'))
)
"""),
    (TX_TABLE, """
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_no VARCHAR(30) NOT NULL UNIQUE,
    transaction_type_id INTEGER NOT NULL,
    transaction_date DATETIME NOT NULL,
    org_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    uom_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    base_qty REAL NOT NULL,
    direction VARCHAR(10) NOT NULL DEFAULT 'in',
    batch_id INTEGER,
    stock_status VARCHAR(20) NOT NULL DEFAULT 'unrestricted',
    source_doc_type VARCHAR(50) NOT NULL,
    source_doc_id INTEGER NOT NULL,
    source_line_id INTEGER NOT NULL,
    source_event_key VARCHAR(200) NOT NULL,
    transfer_group_id VARCHAR(64),
    reversal_of_transaction_id INTEGER,
    remark TEXT,
    created_by VARCHAR(200),
    created_at DATETIME,
    FOREIGN KEY (transaction_type_id) REFERENCES inventory_transaction_types(id),
    CHECK (qty > 0),
    CHECK (base_qty > 0),
    CHECK (direction IN ('in', 'out')),
    CHECK (stock_status IN ('unrestricted', 'inspection', 'blocked'))
)
"""),
    (BAL_TABLE, """
CREATE TABLE IF NOT EXISTS inventory_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL DEFAULT 0,
    stock_status VARCHAR(20) NOT NULL DEFAULT 'unrestricted',
    qty_on_hand REAL NOT NULL DEFAULT 0,
    qty_reserved REAL NOT NULL DEFAULT 0,
    updated_at DATETIME,
    CHECK (stock_status IN ('unrestricted', 'inspection', 'blocked'))
)
"""),
)

#: (索引名, 表, DDL)
INDEXES = (
    ('idx_inv_type_status', TYPES_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_type_status '
     'ON inventory_transaction_types(status, sort_order)'),

    ('idx_inv_tx_org_item_date', TX_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_tx_org_item_date '
     'ON inventory_transactions(org_id, item_id, transaction_date)'),
    ('idx_inv_tx_source_doc', TX_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_tx_source_doc '
     'ON inventory_transactions(source_doc_type, source_doc_id)'),
    ('idx_inv_tx_location', TX_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_tx_location '
     'ON inventory_transactions(org_id, location_id, item_id)'),
    ('uq_inv_tx_source_line', TX_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_tx_source_line '
     'ON inventory_transactions(source_event_key, source_line_id)'),
    ('uq_inv_tx_reversal', TX_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_tx_reversal '
     'ON inventory_transactions(reversal_of_transaction_id) '
     'WHERE reversal_of_transaction_id IS NOT NULL'),

    ('uq_inv_balance_key', BAL_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_balance_key '
     'ON inventory_balances(org_id, location_id, item_id, batch_id, stock_status)'),
    ('idx_inv_balance_org_item', BAL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_balance_org_item '
     'ON inventory_balances(org_id, item_id, stock_status)'),
)

PERMISSIONS = (
    ('inventory_transaction:inventory_transaction_read',
     '库存事务查看', 'inventory_transaction', 'read'),
    ('inventory_transaction:inventory_transaction_list',
     '库存事务查询', 'inventory_transaction', 'list'),
    ('inventory_balance:inventory_balance_read',
     '库存余额查看', 'inventory_balance', 'read'),
    ('inventory_balance:inventory_balance_list',
     '库存余额查询', 'inventory_balance', 'list'),
)

GRANT_TO_SETS = ('admin', 'default')

ROOT_MENU_CODE = 'procurement'
INVENTORY_MENU_CODE = 'inventory-balance-management'

MENUS = (
    {
        'menu_code': INVENTORY_MENU_CODE,
        'menu_name': '库存余额',
        'menu_path': '/inventory-balances',
        'page_type': 'object_list',
        'primary_object_type': 'inventory_balance',
        'object_types': ['inventory_balance', 'inventory_transaction'],
        'bo_bindings': [
            {'bo_id': 'inventory_balance', 'role': 'primary',
             'include_actions': ['read', 'list']},
            {'bo_id': 'inventory_transaction', 'role': 'secondary',
             'include_actions': ['read', 'list']},
        ],
        'required_permissions': [
            'inventory_balance:inventory_balance_read',
            'inventory_balance:inventory_balance_list',
        ],
        'parent_menu': ROOT_MENU_CODE,
        'icon': 'Boxes',
        'color': '#22c55e',
        'description': '库存余额与库存事务只读查询（数量账为唯一真相）',
        'sort_order': 6,
        'show_in_sidebar': 0,
        'data_permission_hint': {
            'resource_types': ['inventory_balance', 'inventory_transaction'],
            'message': '建议按库存组织分配库存余额/事务数据权限',
        },
    },
)

_ORPHAN_MENU_CODES = (
    'inventory_balance-list',
    'inventory_balance_line-list',
    'inventory_transaction-list',
)

PARAM_DEFS = (
    ('inventory_allow_negative', '库存是否允许负库存', 'bool', '0',
     '默认 0：出账导致余额为负时拒绝；按库存组织可覆盖'),
    ('inventory_posting_enabled', '库存过账总开关', 'bool', '0',
     '默认 0：关闭新过账（期初导入完成并核对后再开启）'),
)
PARAM_DOMAIN = 'procurement'
PARAM_TARGET_BO = 'inventory_balance'


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


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _do_tables(conn: sqlite3.Connection) -> None:
    for table, sql in TABLES:
        if _table_exists(conn, table):
            print(f'  - [SKIP] 表 {table} 已存在')
            continue
        conn.execute(sql)
        print(f'  - [NEW] 表 {table}')


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, _table, sql in INDEXES:
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
            continue
        conn.execute(sql)
        print(f'  - [NEW] 索引 {name}')


def _do_types(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TYPES_TABLE):
        return
    for code, name, category, direction, affects, sort_order, desc in \
            TRANSACTION_TYPES:
        row = conn.execute(
            'SELECT id FROM inventory_transaction_types WHERE code=?',
            (code,),
        ).fetchone()
        if row:
            print(f'  - [SKIP] 移动类型 {code} 已存在')
            continue
        conn.execute(
            'INSERT INTO inventory_transaction_types '
            '(code, name, category, direction, affects_on_hand, status, '
            ' sort_order, description, created_at) '
            "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, datetime('now'))",
            (code, name, category, direction, affects, sort_order, desc),
        )
        print(f'  - [NEW] 移动类型 {code} ({name})')


def _do_number_sequence(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'number_sequences'):
        print('  - number_sequences 表不存在, 跳过编号序列种子')
        return
    code = NUMBER_SEQUENCE[0]
    if conn.execute(
            'SELECT id FROM number_sequences WHERE code=?', (code,)).fetchone():
        print(f'  - [SKIP] 编号序列 {code} 已存在')
        return
    conn.execute(
        'INSERT INTO number_sequences '
        '(code, name, pattern, scope_fields, date_field, start_value, '
        ' on_exhaust, preview, status, description, created_at) '
        "VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, 'active', ?, datetime('now'))",
        (code, NUMBER_SEQUENCE[1], NUMBER_SEQUENCE[2], NUMBER_SEQUENCE[3],
         NUMBER_SEQUENCE[4], NUMBER_SEQUENCE[5], NUMBER_SEQUENCE[6]),
    )
    print(f'  - [NEW] 编号序列 {code}')


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            (code, name, resource_type, action),
        )
        if cur.rowcount:
            created += 1
            print(f'  - [NEW] 权限 {code} ({name})')
    print(f'  - [SUMMARY] permissions: +{created}')


def _do_grants(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'permissions')
            and _table_exists(conn, 'permission_sets')
            and _table_exists(conn, 'permission_set_permissions')):
        print('  - 权限集相关表缺失, 跳过授权')
        return
    cols = _columns(conn, 'permission_set_permissions')
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        return
    has_code_col = 'permission_code' in cols
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            (set_code,),
        ).fetchone()
        if not row:
            continue
        permission_set_id = row[0]
        for code, _name, _rtype, _action in PERMISSIONS:
            prow = conn.execute(
                'SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
            if not prow:
                continue
            if conn.execute(
                'SELECT 1 FROM permission_set_permissions WHERE '
                f'{id_col} = ? AND permission_id = ?', (permission_set_id, prow[0])
            ).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    f'({id_col}, permission_code, permission_id, granted, '
                    "created_at) VALUES (?, ?, ?, 1, datetime('now'))",
                    (permission_set_id, code, prow[0]),
                )
            else:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    f'({id_col}, permission_id, granted, created_at) '
                    "VALUES (?, ?, 1, datetime('now'))",
                    (permission_set_id, prow[0]),
                )
            granted += 1
    print(f'  - [SUMMARY] permission_set_permissions: +{granted}')


def _insert_menu(conn: sqlite3.Connection, menu: dict) -> None:
    if conn.execute(
        'SELECT 1 FROM menus WHERE menu_code=?', (menu['menu_code'],)
    ).fetchone():
        print(f"  - [SKIP] 菜单 {menu['menu_code']} 已存在")
    else:
        conn.execute(
            "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
            "object_types, primary_object_type, bo_bindings, "
            "required_permissions, parent_menu, icon, color, description, "
            "sort_order, is_active, show_in_sidebar, auto_generated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 0)",
            (
                menu['menu_code'], menu['menu_name'], menu['menu_path'],
                menu['page_type'],
                json.dumps(menu['object_types'], ensure_ascii=False),
                menu['primary_object_type'],
                json.dumps(menu['bo_bindings'], ensure_ascii=False),
                json.dumps(menu['required_permissions'], ensure_ascii=False),
                menu['parent_menu'], menu['icon'], menu['color'],
                menu['description'], menu['sort_order'],
                menu['show_in_sidebar'],
            ),
        )
        print(f"  - [NEW] 菜单 {menu['menu_code']} ({menu['menu_name']})")

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, "
            "menu_path, required_permissions, required_any_permission, "
            "parent_menu, icon, sort_order, is_active, data_permission_hint) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, ?)",
            (
                menu['menu_code'], menu['menu_name'], menu['menu_path'],
                json.dumps(menu['required_permissions'], ensure_ascii=False),
                menu['parent_menu'], menu['icon'], menu['sort_order'],
                json.dumps(menu['data_permission_hint'], ensure_ascii=False),
            ),
        )
        if cur.rowcount:
            print(f"  - [NEW] menu_permissions: {menu['menu_code']}")


def _do_menus(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return
    for menu in MENUS:
        _insert_menu(conn, menu)


def _do_cleanup_auto_menu(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    for code in _ORPHAN_MENU_CODES:
        cur = conn.execute(
            'DELETE FROM menus WHERE menu_code=? AND auto_generated=1', (code,))
        if cur.rowcount:
            print(f'  - [DROP] 孤儿菜单 {code}')


def _do_params(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'control_parameter_defs'):
        print('  - control_parameter_defs 不存在, 跳过参数种子')
        return
    for code, name, value_type, default_value, desc in PARAM_DEFS:
        row = conn.execute(
            'SELECT id FROM control_parameter_defs WHERE code=?', (code,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE control_parameter_defs SET name=?, domain=?, '
                'value_type=?, target_bo=?, default_value=?, description=?, '
                'status=? WHERE code=?',
                (name, PARAM_DOMAIN, value_type, PARAM_TARGET_BO,
                 default_value, desc, 'active', code),
            )
            print(f'  - [SKIP] 参数定义 {code} 已存在（刷新元数据）')
            continue
        conn.execute(
            'INSERT INTO control_parameter_defs '
            '(code, name, domain, value_type, target_bo, default_value, '
            ' status, description, created_at) '
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'))",
            (code, name, PARAM_DOMAIN, value_type, PARAM_TARGET_BO,
             default_value, desc),
        )
        print(f'  - [NEW] 参数定义 {code}={default_value}')


def _do_org_column(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'orgs'):
        print('  - orgs 表不存在, 跳过默认库位列')
        return
    if 'default_inventory_location_id' in _columns(conn, 'orgs'):
        print('  - [SKIP] orgs.default_inventory_location_id 已存在')
        return
    conn.execute(
        'ALTER TABLE orgs ADD COLUMN default_inventory_location_id INTEGER'
    )
    print('  - [NEW] orgs.default_inventory_location_id')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v201] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v201] 开始: 库存模型基础（INV-1）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_types(conn)
        _do_number_sequence(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        _do_cleanup_auto_menu(conn)
        _do_params(conn)
        _do_org_column(conn)
        conn.commit()
        print('[v201] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v201] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v201 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table, _sql in TABLES:
            if not _table_exists(conn, table):
                print(f'[v201 verify] FAIL: 缺表 {table}')
                ok = False

        required_cols = {
            TX_TABLE: {'transaction_no', 'transaction_type_id', 'transaction_date',
                       'org_id', 'location_id', 'item_id', 'uom_id', 'qty',
                       'base_qty', 'direction', 'batch_id', 'stock_status',
                       'source_doc_type', 'source_doc_id', 'source_line_id',
                       'source_event_key', 'transfer_group_id',
                       'reversal_of_transaction_id'},
            BAL_TABLE: {'org_id', 'location_id', 'item_id', 'batch_id',
                        'stock_status', 'qty_on_hand', 'qty_reserved'},
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                continue
            missing = cols - _columns(conn, table)
            if missing:
                print(f'[v201 verify] FAIL: {table} 缺列 {sorted(missing)}')
                ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v201 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, TYPES_TABLE):
            codes = {
                row[0] for row in conn.execute(
                    'SELECT code FROM inventory_transaction_types').fetchall()
            }
            missing = [t[0] for t in TRANSACTION_TYPES if t[0] not in codes]
            if missing:
                print(f'[v201 verify] FAIL: 缺移动类型 {missing}')
                ok = False

        if _table_exists(conn, 'number_sequences'):
            row = conn.execute(
                'SELECT pattern, date_field, on_exhaust, status '
                'FROM number_sequences WHERE code=?', (NUMBER_SEQUENCE[0],)
            ).fetchone()
            if not row:
                print('[v201 verify] FAIL: 缺编号序列 INV')
                ok = False
            else:
                if (row[0] or '') != NUMBER_SEQUENCE[2]:
                    print('[v201 verify] FAIL: INV pattern 不符')
                    ok = False
                if (row[1] or '') != NUMBER_SEQUENCE[3]:
                    print('[v201 verify] FAIL: INV date_field 不符')
                    ok = False
        else:
            print('[v201 verify] FAIL: 缺 number_sequences 表')
            ok = False

        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if not conn.execute(
                        'SELECT 1 FROM permissions WHERE code=?', (code,)).fetchone():
                    print(f'[v201 verify] FAIL: 缺权限 {code}')
                    ok = False
        else:
            print('[v201 verify] FAIL: 缺 permissions 表')
            ok = False

        if _table_exists(conn, 'menus'):
            if not conn.execute(
                    'SELECT 1 FROM menus WHERE menu_code=?',
                    (INVENTORY_MENU_CODE,)).fetchone():
                print('[v201 verify] FAIL: 缺菜单 inventory-balance-management')
                ok = False
        else:
            print('[v201 verify] FAIL: 缺 menus 表')
            ok = False

        if _table_exists(conn, 'control_parameter_defs'):
            for code, *_ in PARAM_DEFS:
                if not conn.execute(
                        'SELECT 1 FROM control_parameter_defs WHERE code=?',
                        (code,)).fetchone():
                    print(f'[v201 verify] FAIL: 缺参数定义 {code}')
                    ok = False
        else:
            print('[v201 verify] FAIL: 缺 control_parameter_defs 表')
            ok = False

        if _table_exists(conn, 'orgs'):
            if 'default_inventory_location_id' not in _columns(conn, 'orgs'):
                print('[v201 verify] FAIL: orgs 缺默认库位列')
                ok = False

        if ok:
            print('[v201 verify] PASS')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v201] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v201] 回滚: 库存模型基础')
        if _table_exists(conn, 'menu_permissions'):
            conn.execute('DELETE FROM menu_permissions WHERE menu_code=?',
                         (INVENTORY_MENU_CODE,))
        if _table_exists(conn, 'menus'):
            conn.execute('DELETE FROM menus WHERE menu_code=?',
                         (INVENTORY_MENU_CODE,))

        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if _table_exists(conn, 'permission_set_permissions'):
                    conn.execute(
                        'DELETE FROM permission_set_permissions WHERE permission_id '
                        'IN (SELECT id FROM permissions WHERE code=?)', (code,))
                conn.execute('DELETE FROM permissions WHERE code=?', (code,))

        if _table_exists(conn, 'control_parameter_defs'):
            for code, *_ in PARAM_DEFS:
                row = conn.execute(
                    'SELECT id FROM control_parameter_defs WHERE code=?', (code,)
                ).fetchone()
                if not row:
                    continue
                if _table_exists(conn, 'control_parameter_values'):
                    remain = conn.execute(
                        'SELECT COUNT(*) FROM control_parameter_values '
                        'WHERE control_parameter_id=?', (row[0],)).fetchone()[0]
                    if remain:
                        print(f'  - [KEEP] 参数 {code} 仍有 {remain} 条取值')
                        continue
                conn.execute(
                    'DELETE FROM control_parameter_defs WHERE id=?', (row[0],))

        if _table_exists(conn, 'number_sequences'):
            conn.execute('DELETE FROM number_sequences WHERE code=?',
                         (NUMBER_SEQUENCE[0],))

        if _table_exists(conn, 'orgs') and \
                'default_inventory_location_id' in _columns(conn, 'orgs'):
            conn.execute(
                'UPDATE orgs SET default_inventory_location_id=NULL')

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')

        for table in (BAL_TABLE, TX_TABLE, TYPES_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')

        conn.commit()
        print('[v201] 回滚完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v201] 回滚失败: {e}')
        raise
    finally:
        conn.close()
