# -*- coding: utf-8 -*-
"""[v211 2026-11-04] 包装容器（HU / LPN）—— P6a-2

依据:
  docs/specs/p6-serial-number-model/spec.md §11

范围:
  1. 建 3 张表：
       handling_units（容器抬头 / 当前态）
       handling_unit_items（容器内容投影）
       hu_transactions（容器事件账）
  2. 索引：uq_hu_no / idx_hu_parent / idx_hu_root / idx_hu_location /
     idx_hu_status / uq_hu_serial / uq_serial_in_hu / uq_hu_child /
     idx_hu_item_serial / idx_hu_item_item；事件账 3 条。
  3. 注册 4 个枚举：hu_type / hu_status / hu_content_type / hu_txn_type。
  4. 权限 8 条 + 授权 admin / default；2 个菜单
     （handling-unit-list / hu-transaction-list）。
  5. 单据行可选装箱字段：receipt_lines / shipment_lines 加
     hu_no VARCHAR(40) / hu_type VARCHAR(20)（§11.5）。
  6. 不回填历史数据：存量无容器信息，不做猜测。

幂等:
  表 / 索引 / 枚举 / 权限 / 授权 / 菜单 / 列 先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单与 menu_permissions → 删权限与授权 → 删索引 → 删三表；
  单据行两列保留（SQLite 旧版本无法安全 DROP COLUMN，仅清零取值）。
"""
import json
import sqlite3
import sys
from pathlib import Path

MIGRATION_NAME = 'v211__handling_unit'

HU_TABLE = 'handling_units'
ITEM_TABLE = 'handling_unit_items'
TX_TABLE = 'hu_transactions'
RECEIPT_LINE_TABLE = 'receipt_lines'
SHIPMENT_LINE_TABLE = 'shipment_lines'

HU_TYPES = ('pallet', 'carton', 'bin', 'container', 'other')
HU_STATUSES = ('open', 'sealed', 'shipped', 'void')
CONTENT_TYPES = ('material', 'packaging', 'hu')
TXN_TYPES = ('create', 'pack', 'unpack', 'move', 'consolidate', 'split',
             'seal', 'unseal', 'ship', 'reverse', 'reuse', 'void')

TABLES = (
    (HU_TABLE, """
CREATE TABLE IF NOT EXISTS handling_units (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hu_no VARCHAR(40) NOT NULL,
    hu_type VARCHAR(20) NOT NULL DEFAULT 'carton',
    packaging_item_id INTEGER,
    org_id INTEGER NOT NULL,
    location_id INTEGER,
    parent_hu_id INTEGER,
    root_hu_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    is_reusable INTEGER NOT NULL DEFAULT 0,
    cycle_no INTEGER NOT NULL DEFAULT 1,
    gross_weight DECIMAL(18,4),
    tare_weight DECIMAL(18,4),
    net_weight DECIMAL(18,4),
    volume DECIMAL(18,6),
    uom_id INTEGER,
    source_doc_type VARCHAR(50),
    source_doc_id INTEGER,
    sealed_at DATETIME,
    shipped_at DATETIME,
    voided_at DATETIME,
    remark VARCHAR(255),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (hu_type IN ('pallet', 'carton', 'bin', 'container', 'other')),
    CHECK (status IN ('open', 'sealed', 'shipped', 'void')),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (packaging_item_id) REFERENCES items(id),
    FOREIGN KEY (parent_hu_id) REFERENCES handling_units(id),
    FOREIGN KEY (root_hu_id) REFERENCES handling_units(id)
)
"""),
    (ITEM_TABLE, """
CREATE TABLE IF NOT EXISTS handling_unit_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hu_id INTEGER NOT NULL,
    content_type VARCHAR(20) NOT NULL DEFAULT 'material',
    item_id INTEGER,
    batch_id INTEGER,
    serial_id INTEGER,
    child_hu_id INTEGER,
    qty DECIMAL(18,4) NOT NULL DEFAULT 0,
    uom_id INTEGER,
    created_at DATETIME,
    CHECK (content_type IN ('material', 'packaging', 'hu')),
    CHECK (
        (content_type = 'material' AND item_id IS NOT NULL
         AND child_hu_id IS NULL)
        OR (content_type = 'packaging' AND item_id IS NOT NULL
            AND serial_id IS NULL AND batch_id IS NULL
            AND child_hu_id IS NULL)
        OR (content_type = 'hu' AND child_hu_id IS NOT NULL
            AND qty = 0 AND item_id IS NULL AND batch_id IS NULL
            AND serial_id IS NULL)
    ),
    CHECK (serial_id IS NULL OR content_type = 'material'),
    CHECK (serial_id IS NULL OR qty = 1),
    FOREIGN KEY (hu_id) REFERENCES handling_units(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    FOREIGN KEY (serial_id) REFERENCES serial_numbers(id),
    FOREIGN KEY (child_hu_id) REFERENCES handling_units(id)
)
"""),
    (TX_TABLE, """
CREATE TABLE IF NOT EXISTS hu_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hu_id INTEGER NOT NULL,
    serial_id INTEGER,
    child_hu_id INTEGER,
    txn_type VARCHAR(20) NOT NULL,
    from_hu_id INTEGER,
    to_hu_id INTEGER,
    from_location_id INTEGER,
    to_location_id INTEGER,
    doc_type VARCHAR(30),
    doc_id INTEGER,
    line_id INTEGER,
    txn_at DATETIME NOT NULL,
    remark VARCHAR(255),
    created_by VARCHAR(200),
    created_at DATETIME,
    CHECK (txn_type IN ('create', 'pack', 'unpack', 'move', 'consolidate',
                        'split', 'seal', 'unseal', 'ship', 'reverse',
                        'reuse', 'void')),
    FOREIGN KEY (hu_id) REFERENCES handling_units(id),
    FOREIGN KEY (serial_id) REFERENCES serial_numbers(id),
    FOREIGN KEY (child_hu_id) REFERENCES handling_units(id)
)
"""),
)

INDEXES = (
    (HU_TABLE, 'uq_hu_no',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_hu_no '
     'ON handling_units(org_id, hu_no)'),
    (HU_TABLE, 'idx_hu_parent',
     'CREATE INDEX IF NOT EXISTS idx_hu_parent ON handling_units(parent_hu_id)'),
    (HU_TABLE, 'idx_hu_root',
     'CREATE INDEX IF NOT EXISTS idx_hu_root ON handling_units(root_hu_id)'),
    (HU_TABLE, 'idx_hu_location',
     'CREATE INDEX IF NOT EXISTS idx_hu_location ON handling_units(location_id)'),
    (HU_TABLE, 'idx_hu_status',
     'CREATE INDEX IF NOT EXISTS idx_hu_status ON handling_units(status)'),

    (ITEM_TABLE, 'uq_hu_serial',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_hu_serial '
     'ON handling_unit_items(hu_id, serial_id) WHERE serial_id IS NOT NULL'),
    (ITEM_TABLE, 'uq_serial_in_hu',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_serial_in_hu '
     'ON handling_unit_items(serial_id) WHERE serial_id IS NOT NULL'),
    (ITEM_TABLE, 'uq_hu_child',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_hu_child '
     'ON handling_unit_items(hu_id, child_hu_id) WHERE child_hu_id IS NOT NULL'),
    (ITEM_TABLE, 'idx_hu_item_serial',
     'CREATE INDEX IF NOT EXISTS idx_hu_item_serial '
     'ON handling_unit_items(serial_id)'),
    (ITEM_TABLE, 'idx_hu_item_item',
     'CREATE INDEX IF NOT EXISTS idx_hu_item_item '
     'ON handling_unit_items(item_id, batch_id)'),

    (TX_TABLE, 'idx_hu_tx_hu_at',
     'CREATE INDEX IF NOT EXISTS idx_hu_tx_hu_at '
     'ON hu_transactions(hu_id, txn_at)'),
    (TX_TABLE, 'idx_hu_tx_serial_at',
     'CREATE INDEX IF NOT EXISTS idx_hu_tx_serial_at '
     'ON hu_transactions(serial_id, txn_at)'),
    (TX_TABLE, 'idx_hu_tx_doc',
     'CREATE INDEX IF NOT EXISTS idx_hu_tx_doc '
     'ON hu_transactions(doc_type, doc_id)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('hu_type', '包装容器类型',
     '容器类型（托盘 / 纸箱 / 料箱 / 集装箱 / 其他）',
     (('pallet', '托盘', 'Pallet'),
      ('carton', '纸箱', 'Carton'),
      ('bin', '料箱', 'Bin'),
      ('container', '集装箱', 'Container'),
      ('other', '其他', 'Other'))),
    ('hu_status', '包装容器状态',
     '容器状态（打开 / 已密封 / 已发运 / 已作废）',
     (('open', '打开', 'Open'),
      ('sealed', '已密封', 'Sealed'),
      ('shipped', '已发运', 'Shipped'),
      ('void', '已作废', 'Void'))),
    ('hu_content_type', '包装容器内容类型',
     '容器内容行类型（物料 / 包装物 / 子容器）',
     (('material', '物料', 'Material'),
      ('packaging', '包装物', 'Packaging'),
      ('hu', '子容器', 'Handling Unit'))),
    ('hu_txn_type', '包装容器事件类型',
     '容器事件账类型（建箱 / 装箱 / 拆箱 / 移库 / 合并 / 拆分 / 密封 / 开封 / 发运 / 反冲 / 复用 / 作废）',
     (('create', '建箱', 'Create'),
      ('pack', '装箱', 'Pack'),
      ('unpack', '拆箱', 'Unpack'),
      ('move', '移库', 'Move'),
      ('consolidate', '合并', 'Consolidate'),
      ('split', '拆分', 'Split'),
      ('seal', '密封', 'Seal'),
      ('unseal', '开封', 'Unseal'),
      ('ship', '发运', 'Ship'),
      ('reverse', '反冲', 'Reverse'),
      ('reuse', '复用', 'Reuse'),
      ('void', '作废', 'Void'))),
)

PERMISSIONS = (
    ('handling_unit:handling_unit_read', '包装容器查看', 'handling_unit', 'read'),
    ('handling_unit:handling_unit_create', '包装容器新建', 'handling_unit', 'create'),
    ('handling_unit:handling_unit_update', '包装容器修改', 'handling_unit', 'update'),
    ('handling_unit:handling_unit_delete', '包装容器删除', 'handling_unit', 'delete'),
    ('handling_unit_item:handling_unit_item_read', '包装容器内容查看',
     'handling_unit_item', 'read'),
    ('handling_unit_item:handling_unit_item_list', '包装容器内容查询',
     'handling_unit_item', 'list'),
    ('hu_transaction:hu_transaction_read', '包装容器事件查看',
     'hu_transaction', 'read'),
    ('hu_transaction:hu_transaction_list', '包装容器事件查询',
     'hu_transaction', 'list'),
)

GRANT_TO_SETS = ('admin', 'default')

MENUS = (
    {
        'menu_code': 'handling-unit-list',
        'menu_name': '包装容器',
        'menu_path': '/inventory/handling-units',
        'parent_menu': 'inventory',
        'primary_object_type': 'handling_unit',
        'include_actions': ['read', 'create', 'update', 'delete'],
        'icon': 'Box',
        'color': '#0ea5e9',
        'sort_order': 9,
        'description': '包装容器（HU/LPN）——托盘、箱、料箱的当前状态与内容',
    },
    {
        'menu_code': 'hu-transaction-list',
        'menu_name': '包装容器事件',
        'menu_path': '/inventory/hu-transactions',
        'parent_menu': 'inventory',
        'primary_object_type': 'hu_transaction',
        'include_actions': ['read', 'list'],
        'icon': 'List',
        'color': '#64748b',
        'sort_order': 10,
        'description': '容器事件账只读查询（建箱 / 装箱 / 移库 / 密封 / 发运）',
    },
)

LINE_COLUMNS = (
    (RECEIPT_LINE_TABLE, 'hu_no', 'VARCHAR(40)'),
    (RECEIPT_LINE_TABLE, 'hu_type', 'VARCHAR(20)'),
    (SHIPMENT_LINE_TABLE, 'hu_no', 'VARCHAR(40)'),
    (SHIPMENT_LINE_TABLE, 'hu_type', 'VARCHAR(20)'),
)

_ORPHAN_MENU_CODES = ('handling-unit-list', 'hu_transaction-list')


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
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone() is not None


def _do_tables(conn: sqlite3.Connection) -> None:
    for table, sql in TABLES:
        if _table_exists(conn, table):
            print('  - [SKIP] 表 %s 已存在' % table)
            continue
        conn.execute(sql)
        print('  - [NEW] 表 %s' % table)


def _create_index(conn: sqlite3.Connection, name: str, sql: str) -> None:
    if _index_exists(conn, name):
        print('  - [SKIP] 索引 %s 已存在' % name)
        return
    conn.execute(sql)
    print('  - [NEW] 索引 %s' % name)


def _do_indexes(conn: sqlite3.Connection) -> None:
    for _table, name, sql in INDEXES:
        _create_index(conn, name, sql)


def _do_line_columns(conn: sqlite3.Connection) -> None:
    for table, column, ddl_type in LINE_COLUMNS:
        if not _table_exists(conn, table):
            print('  - %s 表不存在, 跳过 %s 列' % (table, column))
            continue
        if column in _columns(conn, table):
            print('  - [SKIP] %s.%s 已存在' % (table, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, ddl_type))
        print('  - [NEW] %s.%s' % (table, column))


def _do_enums(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'enum_types')
            and _table_exists(conn, 'enum_values')):
        print('  - enum_types / enum_values 不存在, 跳过枚举种子')
        return
    for type_id, type_name, description, values in ENUM_SEEDS:
        if conn.execute('SELECT 1 FROM enum_types WHERE id=?',
                        (type_id,)).fetchone():
            print('  - [SKIP] 枚举类型 %s 已存在' % type_id)
        else:
            conn.execute(
                "INSERT INTO enum_types (id, name, category, mutability, "
                "dimension_schema, description, created_at) "
                "VALUES (?, ?, 'business', 'extensible', NULL, ?, datetime('now'))",
                (type_id, type_name, description),
            )
            print('  - [NEW] 枚举类型 %s (%s)' % (type_id, type_name))
        for sort_order, (code, value_name, name_en) in enumerate(values, start=1):
            if conn.execute(
                    'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                    (type_id, code)).fetchone():
                continue
            conn.execute(
                "INSERT INTO enum_values (enum_type_id, code, name, name_en, "
                "sort_order, is_active, is_system, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, 0, datetime('now'))",
                (type_id, code, value_name, name_en, sort_order),
            )
            print('    - [NEW] 枚举值 %s.%s' % (type_id, code))


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
            'VALUES (?, ?, ?, ?)', (code, name, resource_type, action))
        if cur.rowcount:
            created += 1
            print('  - [NEW] 权限 %s (%s)' % (code, name))
    print('  - [SUMMARY] permissions: +%s' % created)


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
            (set_code,)).fetchone()
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
                    '%s = ? AND permission_id = ?' % id_col,
                    (permission_set_id, prow[0])).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_code, permission_id, granted, created_at) '
                    "VALUES (?, ?, ?, 1, datetime('now'))" % id_col,
                    (permission_set_id, code, prow[0]))
            else:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_id, granted, created_at) '
                    "VALUES (?, ?, 1, datetime('now'))" % id_col,
                    (permission_set_id, prow[0]))
            granted += 1
    print('  - [SUMMARY] permission_set_permissions: +%s' % granted)


def _resolve_parent_menu(conn: sqlite3.Connection, preferred: str) -> str:
    if not _table_exists(conn, 'menus'):
        return ''
    if conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                    (preferred,)).fetchone():
        return preferred
    if preferred == 'inventory' and conn.execute(
            "SELECT 1 FROM menus WHERE menu_code='procurement'").fetchone():
        print('  - [WARN] 父菜单 inventory 不存在，挂到 procurement')
        return 'procurement'
    print('  - [WARN] 父菜单 %s 不存在，菜单挂顶层' % preferred)
    return ''


def _next_sort_order(conn: sqlite3.Connection, parent: str,
                     preferred: int) -> int:
    row = conn.execute(
        "SELECT MAX(sort_order) FROM menus WHERE COALESCE(parent_menu, '') = ?",
        (parent,)).fetchone()
    current = int(row[0] or 0) if row else 0
    return max(int(preferred), current + 1)


def _insert_menu(conn: sqlite3.Connection, menu: dict) -> None:
    parent = _resolve_parent_menu(conn, menu['parent_menu'])
    sort_order = _next_sort_order(conn, parent, menu['sort_order'])
    required = ['{0}:{0}_{1}'.format(menu['primary_object_type'], action)
                for action in menu['include_actions']]
    bo_binding = [{
        'bo_id': menu['primary_object_type'],
        'role': 'primary',
        'include_actions': list(menu['include_actions']),
    }]
    if conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                    (menu['menu_code'],)).fetchone():
        print("  - [SKIP] 菜单 %s 已存在" % menu['menu_code'])
    else:
        conn.execute(
            'INSERT INTO menus (menu_code, menu_name, menu_path, page_type, '
            'object_types, primary_object_type, bo_bindings, '
            'required_permissions, parent_menu, icon, color, description, '
            'sort_order, is_active, show_in_sidebar, auto_generated) '
            "VALUES (?, ?, ?, 'object_list', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 0)",
            (
                menu['menu_code'], menu['menu_name'], menu['menu_path'],
                json.dumps([menu['primary_object_type']], ensure_ascii=False),
                menu['primary_object_type'],
                json.dumps(bo_binding, ensure_ascii=False),
                json.dumps(required, ensure_ascii=False),
                parent, menu['icon'], menu['color'], menu['description'],
                sort_order,
            ))
        print("  - [NEW] 菜单 %s (sort=%s)" % (menu['menu_code'], sort_order))

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            'INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, '
            'menu_path, required_permissions, required_any_permission, '
            'parent_menu, icon, sort_order, is_active, data_permission_hint) '
            'VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, NULL)',
            (menu['menu_code'], menu['menu_name'], menu['menu_path'],
             json.dumps(required, ensure_ascii=False), parent, menu['icon'],
             sort_order))
        if cur.rowcount:
            print("  - [NEW] menu_permissions: %s" % menu['menu_code'])


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
            print('  - [DROP] 孤儿菜单 %s' % code)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v211] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v211] 开始: 包装容器（HU/LPN）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_line_columns(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        _do_cleanup_auto_menu(conn)
        conn.commit()
        print('[v211] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v211] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v211 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table, _sql in TABLES:
            if not _table_exists(conn, table):
                print('[v211 verify] FAIL: 缺表 %s' % table)
                ok = False

        required_cols = {
            HU_TABLE: {'hu_no', 'hu_type', 'packaging_item_id', 'org_id',
                       'location_id', 'parent_hu_id', 'root_hu_id', 'status',
                       'is_reusable', 'cycle_no', 'gross_weight', 'tare_weight',
                       'net_weight', 'volume', 'uom_id', 'source_doc_type',
                       'source_doc_id', 'sealed_at', 'shipped_at', 'voided_at'},
            ITEM_TABLE: {'hu_id', 'content_type', 'item_id', 'batch_id',
                         'serial_id', 'child_hu_id', 'qty', 'uom_id'},
            TX_TABLE: {'hu_id', 'serial_id', 'child_hu_id', 'txn_type',
                       'from_hu_id', 'to_hu_id', 'from_location_id',
                       'to_location_id', 'doc_type', 'doc_id', 'line_id',
                       'txn_at'},
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                continue
            missing = cols - _columns(conn, table)
            if missing:
                print('[v211 verify] FAIL: %s 缺列 %s' % (table, sorted(missing)))
                ok = False

        for _table, name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v211 verify] FAIL: 缺索引 %s' % name)
                ok = False

        for table, column, _ddl in LINE_COLUMNS:
            if _table_exists(conn, table) and column not in _columns(conn, table):
                print('[v211 verify] FAIL: %s 缺列 %s' % (table, column))
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute('SELECT 1 FROM enum_types WHERE id=?',
                                    (type_id,)).fetchone():
                    print('[v211 verify] FAIL: 缺枚举类型 %s' % type_id)
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                            'SELECT 1 FROM enum_values WHERE enum_type_id=? '
                            'AND code=?', (type_id, code)).fetchone():
                        print('[v211 verify] FAIL: 缺枚举值 %s.%s' % (type_id, code))
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if not conn.execute('SELECT 1 FROM permissions WHERE code=?',
                                    (code,)).fetchone():
                    print('[v211 verify] FAIL: 缺权限 %s' % code)
                    ok = False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                if not conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                                    (menu['menu_code'],)).fetchone():
                    print('[v211 verify] FAIL: 缺菜单 %s' % menu['menu_code'])
                    ok = False

        if ok:
            print('[v211 verify] PASS')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v211] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v211] 回滚: 包装容器')
        if _table_exists(conn, 'menu_permissions'):
            for menu in MENUS:
                conn.execute('DELETE FROM menu_permissions WHERE menu_code=?',
                             (menu['menu_code'],))
        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                conn.execute('DELETE FROM menus WHERE menu_code=?',
                             (menu['menu_code'],))

        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if _table_exists(conn, 'permission_set_permissions'):
                    conn.execute(
                        'DELETE FROM permission_set_permissions WHERE permission_id '
                        'IN (SELECT id FROM permissions WHERE code=?)', (code,))
                conn.execute('DELETE FROM permissions WHERE code=?', (code,))

        for _table, name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute('DROP INDEX IF EXISTS %s' % name)

        for table, _sql in TABLES:
            if _table_exists(conn, table):
                conn.execute('DROP TABLE IF EXISTS %s' % table)

        conn.commit()
        print('[v211 rollback] 完成（单据行 hu_no/hu_type 列保留）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v211 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)
