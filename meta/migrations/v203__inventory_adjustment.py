# -*- coding: utf-8 -*-
"""[v203 2026-11-03] 库存调整 / 盘点（INV-4）

依据:
  .trae/specs/excel-to-diagram/define-inventory-adjustment/spec.md
  .trae/specs/excel-to-diagram/define-inventory-adjustment/tasks.md

范围:
  1. 建 4 张表：
       inventory_adjustments / inventory_adjustment_lines
       inventory_counts / inventory_count_lines
  2. 唯一索引与查询索引（单据号、状态、来源盘点单、行号）
  3. 移动类型种子 7 个：
       ADJ_INCREASE / ADJ_DECREASE / SCRAP /
       STATUS_TRANSFER_OUT / STATUS_TRANSFER_IN /
       COUNT_INCREASE / COUNT_DECREASE
  4. 编号序列：ADJ / CNT（均按月重置）
  5. 权限 18 条（双段码）：调整单 9 条、盘点单 9 条
  6. 菜单 2 个（父 procurement）：
       inventory-adjustment-management / inventory-count-management
  7. 控制参数 4 个（调整复核 / 盘点容差 / 盘点冻结默认值）

口径:
  · 盘点移动类型 category 归入 'adjustment'（v201 表上的 CHECK 约束只允许
    receipt/issue/transfer/adjustment，不新增 category 取值）。
  · 本迁移只建 INV-4 自有对象，不改 v201 三表结构。

幂等:
  表 / 索引 / 类型 / 序列 / 权限 / 菜单 / 参数先查后用；重复执行打印 [SKIP]。

回滚:
  [ALLOW_DESTRUCTIVE] rollback() 物理删除本迁移自建的 4 张表（仅回滚路径）；
  删菜单 + 序列 + 权限 + 参数定义 + 本迁移索引与表；
  已授予的 permission_set_permissions 行一并清理。
"""
import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v203__inventory_adjustment'

ADJ_TABLE = 'inventory_adjustments'
ADJ_LINE_TABLE = 'inventory_adjustment_lines'
CNT_TABLE = 'inventory_counts'
CNT_LINE_TABLE = 'inventory_count_lines'
TYPES_TABLE = 'inventory_transaction_types'

ADJ_TYPES = ('qty_increase', 'qty_decrease', 'scrap', 'status_transfer',
             'count_difference', 'opening')
ADJ_STATUSES = ('draft', 'released', 'posted', 'reversed', 'cancelled')
CNT_TYPES = ('physical', 'cycle')
CNT_STATUSES = ('draft', 'counting', 'submitted', 'approved', 'posted',
                'cancelled')
STOCK_STATUSES = ('unrestricted', 'inspection', 'blocked')

#: (code, name, category, direction, affects_on_hand, sort_order, description)
TRANSACTION_TYPES = (
    ('ADJ_INCREASE', '调整增加', 'adjustment', 'in', 1, 60,
     '手工盘盈 / 入库纠错形成的增加'),
    ('ADJ_DECREASE', '调整减少', 'adjustment', 'out', 1, 70,
     '手工盘亏 / 出库纠错形成的减少'),
    ('SCRAP', '报废', 'issue', 'out', 1, 80,
     '报废出库（需报废原因）'),
    ('STATUS_TRANSFER_OUT', '状态转出', 'adjustment', 'out', 1, 90,
     '库存状态变更的转出腿（不改变组织总在手量）'),
    ('STATUS_TRANSFER_IN', '状态转入', 'adjustment', 'in', 1, 100,
     '库存状态变更的转入腿（不改变组织总在手量）'),
    ('COUNT_INCREASE', '盘点盘盈', 'adjustment', 'in', 1, 110,
     '盘点差异为正时形成的增加'),
    ('COUNT_DECREASE', '盘点盘亏', 'adjustment', 'out', 1, 120,
     '盘点差异为负时形成的减少'),
)

#: (code, name, pattern, date_field, start_value, on_exhaust, description)
NUMBER_SEQUENCES = (
    ('ADJ', '库存调整单编号', 'ADJ-{DATE:yyyymm}-{SEQ:6}', 'posting_date', 1,
     'error', '库存调整单取号：ADJ-年月-6 位流水，按月度重置'),
    ('CNT', '库存盘点单编号', 'CNT-{DATE:yyyymm}-{SEQ:6}', 'snapshot_at', 1,
     'error', '库存盘点单取号：CNT-年月-6 位流水，按月度重置'),
)

TABLES = (
    (ADJ_TABLE, """
CREATE TABLE IF NOT EXISTS inventory_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    adjustment_no VARCHAR(50) NOT NULL UNIQUE,
    adjustment_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    org_id INTEGER NOT NULL,
    location_id INTEGER,
    reason_code VARCHAR(30),
    reason_text VARCHAR(200),
    posting_date DATE NOT NULL,
    source_count_id INTEGER,
    reversal_of_adjustment_id INTEGER,
    created_by VARCHAR(200),
    created_at DATETIME,
    posted_by VARCHAR(200),
    posted_at DATETIME,
    updated_at DATETIME,
    CHECK (adjustment_type IN ('qty_increase', 'qty_decrease', 'scrap',
                               'status_transfer', 'count_difference',
                               'opening')),
    CHECK (status IN ('draft', 'released', 'posted', 'reversed',
                      'cancelled'))
)
"""),
    (ADJ_LINE_TABLE, """
CREATE TABLE IF NOT EXISTS inventory_adjustment_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    adjustment_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    location_id INTEGER,
    batch_id INTEGER,
    uom_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    from_stock_status VARCHAR(20),
    to_stock_status VARCHAR(20),
    source_count_line_id INTEGER,
    remark VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (qty > 0)
)
"""),
    (CNT_TABLE, """
CREATE TABLE IF NOT EXISTS inventory_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    count_no VARCHAR(50) NOT NULL UNIQUE,
    count_type VARCHAR(20) NOT NULL DEFAULT 'physical',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    org_id INTEGER NOT NULL,
    location_id INTEGER,
    snapshot_at DATETIME,
    posting_block INTEGER NOT NULL DEFAULT 0,
    tolerance_qty_pct REAL NOT NULL DEFAULT 0,
    tolerance_qty_abs REAL NOT NULL DEFAULT 0,
    generated_adjustment_id INTEGER,
    approved_by VARCHAR(200),
    approved_at DATETIME,
    posted_at DATETIME,
    remark VARCHAR(200),
    created_by VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (count_type IN ('physical', 'cycle')),
    CHECK (status IN ('draft', 'counting', 'submitted', 'approved',
                      'posted', 'cancelled'))
)
"""),
    (CNT_LINE_TABLE, """
CREATE TABLE IF NOT EXISTS inventory_count_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    count_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    batch_id INTEGER,
    uom_id INTEGER NOT NULL,
    stock_status VARCHAR(20) NOT NULL DEFAULT 'unrestricted',
    snapshot_qty REAL NOT NULL DEFAULT 0,
    counted_qty REAL,
    variance_qty REAL,
    variance_reason VARCHAR(200),
    source_balance_id INTEGER,
    remark VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (stock_status IN ('unrestricted', 'inspection', 'blocked')),
    CHECK (snapshot_qty >= 0),
    CHECK (counted_qty IS NULL OR counted_qty >= 0)
)
"""),
)

#: (索引名, 表, DDL)
INDEXES = (
    ('uq_inv_adj_no', ADJ_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_adj_no '
     'ON inventory_adjustments(adjustment_no)'),
    ('idx_inv_adj_org_status', ADJ_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_adj_org_status '
     'ON inventory_adjustments(org_id, status)'),
    ('idx_inv_adj_source_count', ADJ_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_adj_source_count '
     'ON inventory_adjustments(source_count_id)'),
    ('uq_inv_adj_line', ADJ_LINE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_adj_line '
     'ON inventory_adjustment_lines(adjustment_id, line_no)'),
    ('idx_inv_adj_line_item', ADJ_LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_adj_line_item '
     'ON inventory_adjustment_lines(item_id)'),

    ('uq_inv_count_no', CNT_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_count_no '
     'ON inventory_counts(count_no)'),
    ('idx_inv_count_org_status', CNT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_count_org_status '
     'ON inventory_counts(org_id, status)'),
    ('idx_inv_count_block', CNT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_count_block '
     'ON inventory_counts(org_id, location_id, status, posting_block)'),
    ('uq_inv_count_line', CNT_LINE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_count_line '
     'ON inventory_count_lines(count_id, line_no)'),
    ('idx_inv_count_line_item', CNT_LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_count_line_item '
     'ON inventory_count_lines(item_id)'),
)

PERMISSIONS = (
    ('inventory_adjustment:inventory_adjustment_read', '库存调整单查看',
     'inventory_adjustment', 'read'),
    ('inventory_adjustment:inventory_adjustment_list', '库存调整单查询',
     'inventory_adjustment', 'list'),
    ('inventory_adjustment:inventory_adjustment_create', '库存调整单创建',
     'inventory_adjustment', 'create'),
    ('inventory_adjustment:inventory_adjustment_update', '库存调整单编辑',
     'inventory_adjustment', 'update'),
    ('inventory_adjustment:inventory_adjustment_release', '库存调整单下达',
     'inventory_adjustment', 'release'),
    ('inventory_adjustment:inventory_adjustment_post', '库存调整单过账',
     'inventory_adjustment', 'post'),
    ('inventory_adjustment:inventory_adjustment_reverse', '库存调整单红冲',
     'inventory_adjustment', 'reverse'),
    ('inventory_adjustment:inventory_adjustment_cancel', '库存调整单取消',
     'inventory_adjustment', 'cancel'),
    ('inventory_adjustment:inventory_adjustment_opening', '库存期初导入',
     'inventory_adjustment', 'opening'),

    ('inventory_count:inventory_count_read', '库存盘点单查看',
     'inventory_count', 'read'),
    ('inventory_count:inventory_count_list', '库存盘点单查询',
     'inventory_count', 'list'),
    ('inventory_count:inventory_count_create', '库存盘点单创建',
     'inventory_count', 'create'),
    ('inventory_count:inventory_count_update', '库存盘点单编辑',
     'inventory_count', 'update'),
    ('inventory_count:inventory_count_start', '库存盘点开始',
     'inventory_count', 'start'),
    ('inventory_count:inventory_count_submit', '库存盘点提交',
     'inventory_count', 'submit'),
    ('inventory_count:inventory_count_approve', '库存盘点审批',
     'inventory_count', 'approve'),
    ('inventory_count:inventory_count_post', '库存盘点过账',
     'inventory_count', 'post'),
    ('inventory_count:inventory_count_cancel', '库存盘点取消',
     'inventory_count', 'cancel'),
)

GRANT_TO_SETS = ('admin', 'default')

ROOT_MENU_CODE = 'procurement'
ADJ_MENU_CODE = 'inventory-adjustment-management'
CNT_MENU_CODE = 'inventory-count-management'

MENUS = (
    {
        'menu_code': ADJ_MENU_CODE,
        'menu_name': '库存调整',
        'menu_path': '/inventory-adjustments',
        'page_type': 'object_list',
        'primary_object_type': 'inventory_adjustment',
        'object_types': ['inventory_adjustment', 'inventory_adjustment_line'],
        'bo_bindings': [
            {'bo_id': 'inventory_adjustment', 'role': 'primary',
             'include_actions': ['read', 'list', 'create', 'update',
                                 'release', 'post', 'reverse', 'cancel']},
            {'bo_id': 'inventory_adjustment_line', 'role': 'secondary',
             'include_actions': ['read', 'list', 'create', 'update']},
        ],
        'required_permissions': [
            'inventory_adjustment:inventory_adjustment_read',
            'inventory_adjustment:inventory_adjustment_list',
        ],
        'parent_menu': ROOT_MENU_CODE,
        'icon': 'SlidersHorizontal',
        'color': '#6366f1',
        'description': '手工数量调整、报废与库存状态变更',
        'sort_order': 7,
        'show_in_sidebar': 1,
        'data_permission_hint': {
            'resource_types': ['inventory_adjustment'],
            'message': '建议按库存组织分配库存调整单数据权限',
        },
    },
    {
        'menu_code': CNT_MENU_CODE,
        'menu_name': '库存盘点',
        'menu_path': '/inventory-counts',
        'page_type': 'object_list',
        'primary_object_type': 'inventory_count',
        'object_types': ['inventory_count', 'inventory_count_line'],
        'bo_bindings': [
            {'bo_id': 'inventory_count', 'role': 'primary',
             'include_actions': ['read', 'list', 'create', 'update',
                                 'start', 'submit', 'approve', 'post',
                                 'cancel']},
            {'bo_id': 'inventory_count_line', 'role': 'secondary',
             'include_actions': ['read', 'list', 'create', 'update']},
        ],
        'required_permissions': [
            'inventory_count:inventory_count_read',
            'inventory_count:inventory_count_list',
        ],
        'parent_menu': ROOT_MENU_CODE,
        'icon': 'ClipboardCheck',
        'color': '#0ea5e9',
        'description': '库存盘点快照、实盘录入与差异过账',
        'sort_order': 8,
        'show_in_sidebar': 1,
        'data_permission_hint': {
            'resource_types': ['inventory_count'],
            'message': '建议按库存组织分配库存盘点单数据权限',
        },
    },
)

_ORPHAN_MENU_CODES = (
    'inventory_adjustment-list',
    'inventory_adjustment_line-list',
    'inventory_count-list',
    'inventory_count_line-list',
)

#: (code, name, value_type, default_value, target_bo, description)
PARAM_DEFS = (
    ('inventory_adjustment_release_required', '库存调整是否要求下达', 'bool',
     '1', 'inventory_adjustment',
     '默认 1：调整单需 release 后才允许 post（制单/复核分离）'),
    ('inventory_count_auto_approve_in_tolerance', '盘点容差内自动审批', 'bool',
     '1', 'inventory_count',
     '默认 1：全部行在容差内时 submit 直接进入 approved'),
    ('inventory_count_default_tolerance_qty_pct', '盘点默认数量容差比例',
     'number', '0', 'inventory_count',
     '默认 0：新建盘点单的数量容差比例（0.05 表示 5%）'),
    ('inventory_count_posting_block_default', '盘点默认冻结库存过账', 'bool',
     '0', 'inventory_count',
     '默认 0：新建盘点单不冻结库存过账，可按组织灰度开启'),
)
PARAM_DOMAIN = 'procurement'


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
        print('  - inventory_transaction_types 表不存在, 跳过移动类型种子')
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


def _do_number_sequences(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'number_sequences'):
        print('  - number_sequences 表不存在, 跳过编号序列种子')
        return
    for code, name, pattern, date_field, start_value, on_exhaust, desc in \
            NUMBER_SEQUENCES:
        if conn.execute(
                'SELECT id FROM number_sequences WHERE code=?',
                (code,)).fetchone():
            print(f'  - [SKIP] 编号序列 {code} 已存在')
            continue
        conn.execute(
            'INSERT INTO number_sequences '
            '(code, name, pattern, scope_fields, date_field, start_value, '
            ' on_exhaust, preview, status, description, created_at) '
            "VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, 'active', ?, datetime('now'))",
            (code, name, pattern, date_field, start_value, on_exhaust, desc),
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
                f'{id_col} = ? AND permission_id = ?',
                (permission_set_id, prow[0]),
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
    for code, name, value_type, default_value, target_bo, desc in PARAM_DEFS:
        row = conn.execute(
            'SELECT id FROM control_parameter_defs WHERE code=?', (code,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE control_parameter_defs SET name=?, domain=?, '
                'value_type=?, target_bo=?, default_value=?, description=?, '
                'status=? WHERE code=?',
                (name, PARAM_DOMAIN, value_type, target_bo,
                 default_value, desc, 'active', code),
            )
            print(f'  - [SKIP] 参数定义 {code} 已存在（刷新元数据）')
            continue
        conn.execute(
            'INSERT INTO control_parameter_defs '
            '(code, name, domain, value_type, target_bo, default_value, '
            ' status, description, created_at) '
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'))",
            (code, name, PARAM_DOMAIN, value_type, target_bo,
             default_value, desc),
        )
        print(f'  - [NEW] 参数定义 {code}={default_value}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v202] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v202] 开始: 库存调整 / 盘点（INV-4）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_types(conn)
        _do_number_sequences(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        _do_cleanup_auto_menu(conn)
        _do_params(conn)
        conn.commit()
        print('[v202] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v202] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v202 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table, _sql in TABLES:
            if not _table_exists(conn, table):
                print(f'[v202 verify] FAIL: 缺表 {table}')
                ok = False

        required_cols = {
            ADJ_TABLE: {'adjustment_no', 'adjustment_type', 'status', 'org_id',
                        'location_id', 'reason_code', 'reason_text',
                        'posting_date', 'source_count_id',
                        'reversal_of_adjustment_id', 'posted_by', 'posted_at'},
            ADJ_LINE_TABLE: {'adjustment_id', 'line_no', 'item_id',
                             'location_id', 'batch_id', 'uom_id', 'qty',
                             'from_stock_status', 'to_stock_status',
                             'source_count_line_id'},
            CNT_TABLE: {'count_no', 'count_type', 'status', 'org_id',
                        'location_id', 'snapshot_at', 'posting_block',
                        'tolerance_qty_pct', 'tolerance_qty_abs',
                        'generated_adjustment_id', 'approved_by',
                        'approved_at', 'posted_at'},
            CNT_LINE_TABLE: {'count_id', 'line_no', 'item_id', 'location_id',
                             'batch_id', 'uom_id', 'stock_status',
                             'snapshot_qty', 'counted_qty', 'variance_qty',
                             'variance_reason', 'source_balance_id'},
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                continue
            missing = cols - _columns(conn, table)
            if missing:
                print(f'[v202 verify] FAIL: {table} 缺列 {sorted(missing)}')
                ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v202 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, TYPES_TABLE):
            codes = {
                row[0] for row in conn.execute(
                    'SELECT code FROM inventory_transaction_types').fetchall()
            }
            missing = [t[0] for t in TRANSACTION_TYPES if t[0] not in codes]
            if missing:
                print(f'[v202 verify] FAIL: 缺移动类型 {missing}')
                ok = False

        if _table_exists(conn, 'number_sequences'):
            for code, _name, pattern, date_field, *_ in NUMBER_SEQUENCES:
                row = conn.execute(
                    'SELECT pattern, date_field, status FROM number_sequences '
                    'WHERE code=?', (code,)).fetchone()
                if not row:
                    print(f'[v202 verify] FAIL: 缺编号序列 {code}')
                    ok = False
                else:
                    if (row[0] or '') != pattern:
                        print(f'[v202 verify] FAIL: {code} pattern 不符')
                        ok = False
                    if (row[1] or '') != date_field:
                        print(f'[v202 verify] FAIL: {code} date_field 不符')
                        ok = False
        else:
            print('[v202 verify] FAIL: 缺 number_sequences 表')
            ok = False

        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if not conn.execute(
                        'SELECT 1 FROM permissions WHERE code=?',
                        (code,)).fetchone():
                    print(f'[v202 verify] FAIL: 缺权限 {code}')
                    ok = False
        else:
            print('[v202 verify] FAIL: 缺 permissions 表')
            ok = False

        if _table_exists(conn, 'menus'):
            for code in (ADJ_MENU_CODE, CNT_MENU_CODE):
                if not conn.execute(
                        'SELECT 1 FROM menus WHERE menu_code=?',
                        (code,)).fetchone():
                    print(f'[v202 verify] FAIL: 缺菜单 {code}')
                    ok = False
        else:
            print('[v202 verify] FAIL: 缺 menus 表')
            ok = False

        if _table_exists(conn, 'control_parameter_defs'):
            for code, *_ in PARAM_DEFS:
                if not conn.execute(
                        'SELECT 1 FROM control_parameter_defs WHERE code=?',
                        (code,)).fetchone():
                    print(f'[v202 verify] FAIL: 缺参数定义 {code}')
                    ok = False
        else:
            print('[v202 verify] FAIL: 缺 control_parameter_defs 表')
            ok = False

        if ok:
            print('[v202 verify] PASS')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v202] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v202] 回滚: 库存调整 / 盘点')
        if _table_exists(conn, 'menu_permissions'):
            for code in (ADJ_MENU_CODE, CNT_MENU_CODE):
                conn.execute('DELETE FROM menu_permissions WHERE menu_code=?',
                             (code,))
        if _table_exists(conn, 'menus'):
            for code in (ADJ_MENU_CODE, CNT_MENU_CODE):
                conn.execute('DELETE FROM menus WHERE menu_code=?', (code,))

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
            for code, *_ in NUMBER_SEQUENCES:
                conn.execute('DELETE FROM number_sequences WHERE code=?',
                             (code,))

        if _table_exists(conn, TYPES_TABLE):
            for code, *_ in TRANSACTION_TYPES:
                conn.execute(
                    'DELETE FROM %s WHERE code=?' % TYPES_TABLE, (code,))

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')

        for table in (CNT_LINE_TABLE, CNT_TABLE, ADJ_LINE_TABLE, ADJ_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')

        conn.commit()
        print('[v202] 回滚完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v202] 回滚失败: {e}')
        raise
    finally:
        conn.close()
