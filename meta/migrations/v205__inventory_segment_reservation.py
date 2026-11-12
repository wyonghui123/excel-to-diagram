# -*- coding: utf-8 -*-
"""[v205 2026-11-04] 库存段、预留与 ATP（INV-2 S1/S2 铺底）

依据:
  docs/specs/inv2-reservation-atp/spec.md
  docs/specs/inv2-reservation-atp/tasks.md

范围:
  1. inventory_transactions / inventory_balances 各加 5 个段列（0 哨兵）：
       stock_segment_type / project_id / project_task_id /
       sales_order_line_id / owner_party_id
  2. 余额唯一键重建为 10 列（uq_inv_balance_segment），旧键 uq_inv_balance_key 删除
  3. 建 inventory_reservations / demand_trace_links 两张表与索引
  4. items 加 4 个开关列（so_segment_enabled / consignment_enabled /
     hard_peg_default / valuation_relevant）
  5. 枚举 5 类、权限 5 条、菜单 2 个、控制参数 5 个、预留号序列 RSV
  6. 存量事务/余额回填 owned + 0 哨兵

幂等:
  列/表/索引/枚举/权限/菜单/参数/序列先查后写；重复执行打印 [SKIP]。

回滚:
  [ALLOW_DESTRUCTIVE] rollback() 物理删除本迁移自建表/索引/枚举/权限/菜单/参数，
  并恢复旧余额索引；仅当不存在非 owned 段数据时执行，否则拒绝并保留结构。
  段列不删除（SQLite 无安全 DROP COLUMN）。
"""
import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v205__inventory_segment_reservation'

TX_TABLE = 'inventory_transactions'
BAL_TABLE = 'inventory_balances'
ITEM_TABLE = 'items'
RESERVATION_TABLE = 'inventory_reservations'
TRACE_TABLE = 'demand_trace_links'
SEQUENCE_TABLE = '_sequences'

NEW_BALANCE_INDEX = 'uq_inv_balance_segment'
OLD_BALANCE_INDEX = 'uq_inv_balance_key'

#: (列名, ALTER 片段)；自有段 = 'owned' + 伙伴列 0
SEGMENT_COLUMNS = (
    ('stock_segment_type',
     "stock_segment_type VARCHAR(20) NOT NULL DEFAULT 'owned'"),
    ('project_id', 'project_id INTEGER NOT NULL DEFAULT 0'),
    ('project_task_id', 'project_task_id INTEGER NOT NULL DEFAULT 0'),
    ('sales_order_line_id', 'sales_order_line_id INTEGER NOT NULL DEFAULT 0'),
    ('owner_party_id', 'owner_party_id INTEGER NOT NULL DEFAULT 0'),
)

SEGMENT_COL_NAMES = tuple(name for name, _ddl in SEGMENT_COLUMNS)

BALANCE_KEY_COLUMNS = (
    'org_id', 'location_id', 'item_id', 'batch_id', 'stock_status',
    'stock_segment_type', 'project_id', 'project_task_id',
    'sales_order_line_id', 'owner_party_id',
)

ITEM_COLUMNS = (
    ('so_segment_enabled', 'INTEGER NOT NULL DEFAULT 0'),
    ('consignment_enabled', 'INTEGER NOT NULL DEFAULT 0'),
    ('hard_peg_default', 'INTEGER NOT NULL DEFAULT 0'),
    ('valuation_relevant', 'INTEGER NOT NULL DEFAULT 1'),
)

TABLES = (
    (RESERVATION_TABLE, """
CREATE TABLE IF NOT EXISTS inventory_reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_no VARCHAR(32) NOT NULL UNIQUE,
    org_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    uom_id INTEGER NOT NULL,
    demand_object_type VARCHAR(30) NOT NULL,
    demand_object_id INTEGER NOT NULL,
    demand_line_id INTEGER NOT NULL DEFAULT 0,
    location_id INTEGER,
    batch_id INTEGER,
    stock_segment_type VARCHAR(20) NOT NULL DEFAULT 'owned',
    project_id INTEGER NOT NULL DEFAULT 0,
    project_task_id INTEGER NOT NULL DEFAULT 0,
    sales_order_line_id INTEGER NOT NULL DEFAULT 0,
    owner_party_id INTEGER NOT NULL DEFAULT 0,
    qty_reserved REAL NOT NULL DEFAULT 0,
    qty_fulfilled REAL NOT NULL DEFAULT 0,
    peg_type VARCHAR(10) NOT NULL DEFAULT 'soft',
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    valid_from DATETIME,
    valid_to DATETIME,
    source_doc_type VARCHAR(50),
    source_doc_id INTEGER,
    source_line_id INTEGER,
    reservation_key VARCHAR(200) NOT NULL,
    remark TEXT,
    created_by VARCHAR(200),
    created_at DATETIME,
    updated_by VARCHAR(200),
    updated_at DATETIME,
    CHECK (qty_reserved > 0),
    CHECK (qty_fulfilled >= 0),
    CHECK (qty_fulfilled <= qty_reserved),
    CHECK (peg_type IN ('hard', 'soft')),
    CHECK (status IN ('open', 'partially_fulfilled', 'fulfilled',
                      'cancelled', 'expired'))
)
"""),
    (TRACE_TABLE, """
CREATE TABLE IF NOT EXISTS demand_trace_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supply_object_type VARCHAR(30) NOT NULL,
    supply_object_id INTEGER NOT NULL,
    supply_line_id INTEGER NOT NULL DEFAULT 0,
    demand_object_type VARCHAR(30) NOT NULL,
    demand_object_id INTEGER NOT NULL,
    demand_line_id INTEGER NOT NULL DEFAULT 0,
    trace_type VARCHAR(20) NOT NULL DEFAULT 'allocation',
    peg_type VARCHAR(10) NOT NULL DEFAULT 'soft',
    allocated_qty REAL NOT NULL DEFAULT 0,
    plan_version VARCHAR(40),
    valid_from DATETIME,
    valid_to DATETIME,
    source_doc_type VARCHAR(50),
    source_doc_id INTEGER,
    source_line_id INTEGER,
    remark TEXT,
    computed_at DATETIME,
    created_at DATETIME,
    CHECK (allocated_qty >= 0),
    CHECK (trace_type IN ('reservation', 'pegging', 'allocation')),
    CHECK (peg_type IN ('hard', 'soft'))
)
"""),
)

INDEXES = (
    ('idx_inv_tx_segment', TX_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_inv_tx_segment '
     'ON inventory_transactions(org_id, item_id, stock_segment_type, '
     'project_task_id, sales_order_line_id, owner_party_id)'),
    ('uq_reservation_key', RESERVATION_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_reservation_key '
     'ON inventory_reservations(reservation_key)'),
    ('idx_reservation_demand', RESERVATION_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_reservation_demand '
     'ON inventory_reservations(demand_object_type, demand_object_id, '
     'demand_line_id)'),
    ('idx_reservation_segment', RESERVATION_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_reservation_segment '
     'ON inventory_reservations(org_id, item_id, stock_segment_type, '
     'project_task_id, sales_order_line_id, owner_party_id, status)'),

    ('uq_trace_link', TRACE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_trace_link '
     'ON demand_trace_links(supply_object_type, supply_object_id, '
     'supply_line_id, demand_object_type, demand_object_id, '
     'demand_line_id, trace_type) WHERE valid_to IS NULL'),
    ('idx_trace_supply', TRACE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_trace_supply '
     'ON demand_trace_links(supply_object_type, supply_object_id, '
     'supply_line_id)'),
    ('idx_trace_demand', TRACE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_trace_demand '
     'ON demand_trace_links(demand_object_type, demand_object_id, '
     'demand_line_id)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('stock_segment_type', '库存段类型',
     '库存段类型（自有 / 项目任务 / 销售订单行 / 供应商寄售 / 客户所有）',
     (('owned', '自有', 'Owned'),
      ('project_task', '项目任务', 'Project Task'),
      ('sales_order_line', '销售订单行', 'Sales Order Line'),
      ('supplier_consignment', '供应商寄售', 'Supplier Consignment'),
      ('customer_owned', '客户所有', 'Customer Owned'))),
    ('inventory_reservation_status', '库存预留状态',
     '库存预留状态（开放 / 部分核销 / 已核销 / 已取消 / 已过期）',
     (('open', '开放', 'Open'),
      ('partially_fulfilled', '部分核销', 'Partially Fulfilled'),
      ('fulfilled', '已核销', 'Fulfilled'),
      ('cancelled', '已取消', 'Cancelled'),
      ('expired', '已过期', 'Expired'))),
    ('inventory_peg_type', '库存钉类型',
     '库存与需求的钉定强度（硬钉 / 软钉）',
     (('hard', '硬钉', 'Hard'),
      ('soft', '软钉', 'Soft'))),
    ('demand_object_type', '需求对象类型',
     '需求节点对象类型（销售订单行 / 项目任务 / 工单 / 服务单 / 预测）',
     (('sales_order_line', '销售订单行', 'Sales Order Line'),
      ('project_task', '项目任务', 'Project Task'),
      ('work_order', '工单', 'Work Order'),
      ('service_order', '服务单', 'Service Order'),
      ('forecast', '预测', 'Forecast'))),
    ('demand_trace_type', '需求线索类型',
     '供应与需求之间线索类型（预留 / 钉住 / 分配）',
     (('reservation', '预留', 'Reservation'),
      ('pegging', '钉住', 'Pegging'),
      ('allocation', '分配', 'Allocation'))),
)

PERMISSIONS = (
    ('inventory_reservation:inventory_reservation_read',
     '库存预留查看', 'inventory_reservation', 'read'),
    ('inventory_reservation:inventory_reservation_create',
     '库存预留新建', 'inventory_reservation', 'create'),
    ('inventory_reservation:inventory_reservation_update',
     '库存预留修改', 'inventory_reservation', 'update'),
    ('inventory_reservation:inventory_reservation_delete',
     '库存预留删除', 'inventory_reservation', 'delete'),
    ('demand_trace_link:demand_trace_link_read',
     '需求线索查看', 'demand_trace_link', 'read'),
)

GRANT_TO_SETS = ('admin', 'default')

MENUS = (
    {
        'menu_code': 'inventory-reservation-list',
        'menu_name': '库存预留',
        'menu_path': '/inventory-reservations',
        'primary_object_type': 'inventory_reservation',
        'required_permissions': ['inventory_reservation:inventory_reservation_read'],
        'include_actions': ['read'],
        'parent_menu': 'procurement',
        'icon': 'Lock',
        'color': '#f59e0b',
        'description': '库存预留只读列表（释放动作走服务层）',
        'sort_order': 7,
    },
    {
        'menu_code': 'demand-trace-link-list',
        'menu_name': '需求线索',
        'menu_path': '/demand-trace-links',
        'primary_object_type': 'demand_trace_link',
        'required_permissions': ['demand_trace_link:demand_trace_link_read'],
        'include_actions': ['read'],
        'parent_menu': 'procurement',
        'icon': 'GitBranch',
        'color': '#8b5cf6',
        'description': '供应—需求线索只读列表',
        'sort_order': 8,
    },
)

#: 段转移专用移动类型（成对出/入；禁止用普通收发模拟段变更）
TRANSACTION_TYPES = (
    ('SEG_TRANSFER_OUT', '库存段转出', 'adjustment', 'out', 1, 60,
     '段转移：从原段转出数量'),
    ('SEG_TRANSFER_IN', '库存段转入', 'adjustment', 'in', 1, 61,
     '段转移：向目标段转入数量'),
)

_ORPHAN_MENU_CODES = (
    'inventory_reservation-list',
    'demand_trace_link-list',
)

#: (code, name, value_type, default_value, target_bo, description)
PARAM_DEFS = (
    ('inventory.so_segment_default', 'SO 专用段默认开关', 'bool', '0',
     'inventory_balance', '默认 0：仅按物料 so_segment_enabled 开启 SO 段'),
    ('inventory.allow_cross_project_issue', '跨项目发料开关', 'bool', '0',
     'inventory_transaction', '默认 0：禁止跨项目/跨任务发料'),
    ('inventory.consignment_enabled', '供应商寄售总开关', 'bool', '0',
     'inventory_balance', '默认 0：关闭寄售收货与消耗'),
    ('inventory.hard_peg_default', '硬钉默认开关', 'bool', '0',
     'inventory_reservation', '默认 0：MTO 标准预留为软钉，物料可覆盖'),
    ('inventory.segment_valuation_enabled', '段级估值开关', 'bool', '0',
     'inventory_balance', '默认 0：段级估值由 INV-5 开启'),
)
PARAM_DOMAIN = 'procurement'

#: (code, name, pattern, date_field, start_value, on_exhaust, description)
NUMBER_SEQUENCE = (
    'RSV', '库存预留编号', 'RSV-{DATE:yyyymm}-{SEQ:6}', 'created_at', 1,
    'error', '库存预留取号：RSV-年月-6 位流水，按月度重置',
)


# ----------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------
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


def _do_segment_columns(conn: sqlite3.Connection, table: str) -> None:
    if not _table_exists(conn, table):
        print(f'  - {table} 不存在, 跳过段列')
        return
    have = _columns(conn, table)
    for name, ddl in SEGMENT_COLUMNS:
        if name in have:
            print(f'  - [SKIP] {table}.{name} 已存在')
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s' % (table, ddl))
        print(f'  - [NEW] {table}.{name}')


def _do_tables(conn: sqlite3.Connection) -> None:
    for table, sql in TABLES:
        if _table_exists(conn, table):
            print(f'  - [SKIP] 表 {table} 已存在')
            continue
        conn.execute(sql)
        print(f'  - [NEW] 表 {table}')


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, table, sql in INDEXES:
        if not _table_exists(conn, table):
            print(f'  - {table} 不存在, 跳过索引 {name}')
            continue
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
            continue
        conn.execute(sql)
        print(f'  - [NEW] 索引 {name}')


def _do_balance_key(conn: sqlite3.Connection) -> None:
    """新键先建、旧键后删；新键为旧键超集，存量行天然满足唯一性。"""
    if not _table_exists(conn, BAL_TABLE):
        print(f'  - {BAL_TABLE} 不存在, 跳过余额唯一键重建')
        return
    if _index_exists(conn, NEW_BALANCE_INDEX):
        print(f'  - [SKIP] 索引 {NEW_BALANCE_INDEX} 已存在')
    else:
        conn.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s(%s)'
            % (NEW_BALANCE_INDEX, BAL_TABLE, ', '.join(BALANCE_KEY_COLUMNS)))
        print(f'  - [NEW] 索引 {NEW_BALANCE_INDEX}')
    if _index_exists(conn, OLD_BALANCE_INDEX):
        conn.execute('DROP INDEX %s' % OLD_BALANCE_INDEX)
        print(f'  - [DROP] 旧索引 {OLD_BALANCE_INDEX}')


def _do_backfill(conn: sqlite3.Connection) -> None:
    for table in (TX_TABLE, BAL_TABLE):
        if not _table_exists(conn, table):
            continue
        cur = conn.execute(
            "UPDATE %s SET stock_segment_type = 'owned' "
            'WHERE stock_segment_type IS NULL OR stock_segment_type = %s'
            % (table, "''"))
        if cur.rowcount:
            print(f'  - [FIX] {table} 段类型空值回填 owned: {cur.rowcount}')
        for col in SEGMENT_COL_NAMES[1:]:
            cur = conn.execute(
                'UPDATE %s SET %s = 0 WHERE %s IS NULL' % (table, col, col))
            if cur.rowcount:
                print(f'  - [FIX] {table}.{col} 空值回填 0: {cur.rowcount}')


def _do_item_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, ITEM_TABLE):
        print('  - items 表不存在, 跳过库存段开关列')
        return
    have = _columns(conn, ITEM_TABLE)
    for column, ddl in ITEM_COLUMNS:
        if column in have:
            print(f'  - [SKIP] items.{column} 已存在')
            continue
        conn.execute('ALTER TABLE items ADD COLUMN %s %s' % (column, ddl))
        print(f'  - [NEW] items.{column}')


def _do_enums(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'enum_types')
            and _table_exists(conn, 'enum_values')):
        print('  - enum_types / enum_values 不存在, 跳过枚举种子')
        return
    for type_id, type_name, description, values in ENUM_SEEDS:
        if conn.execute('SELECT 1 FROM enum_types WHERE id=?',
                        (type_id,)).fetchone():
            print(f'  - [SKIP] 枚举类型 {type_id} 已存在')
        else:
            conn.execute(
                "INSERT INTO enum_types (id, name, category, mutability, "
                "dimension_schema, description, created_at) "
                "VALUES (?, ?, 'business', 'extensible', NULL, ?, datetime('now'))",
                (type_id, type_name, description),
            )
            print(f'  - [NEW] 枚举类型 {type_id} ({type_name})')
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
            print(f'    - [NEW] 枚举值 {type_id}.{code}')


def _do_transaction_types(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'inventory_transaction_types'):
        print('  - inventory_transaction_types 不存在, 跳过段转移移动类型')
        return
    for code, name, category, direction, affects, sort_order, desc in \
            TRANSACTION_TYPES:
        if conn.execute('SELECT 1 FROM inventory_transaction_types WHERE code=?',
                        (code,)).fetchone():
            print(f'  - [SKIP] 移动类型 {code} 已存在')
            continue
        conn.execute(
            'INSERT INTO inventory_transaction_types '
            '(code, name, category, direction, affects_on_hand, status, '
            ' sort_order, description, created_at) '
            "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, datetime('now'))",
            (code, name, category, direction, affects, sort_order, desc),
        )
        print(f'  - [NEW] 移动类型 {code}')


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


def _resolve_parent_menu(conn: sqlite3.Connection, preferred: str) -> str:
    if not _table_exists(conn, 'menus'):
        return ''
    if conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                    (preferred,)).fetchone():
        return preferred
    print(f'  - [WARN] 父菜单 {preferred} 不存在，菜单挂顶层')
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
    required = list(menu['required_permissions'])
    bo_binding = [{
        'bo_id': menu['primary_object_type'],
        'role': 'primary',
        'include_actions': list(menu['include_actions']),
    }]
    if conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                    (menu['menu_code'],)).fetchone():
        print(f"  - [SKIP] 菜单 {menu['menu_code']} 已存在")
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
            ),
        )
        print(f"  - [NEW] 菜单 {menu['menu_code']} (sort={sort_order})")

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            'INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, '
            'menu_path, required_permissions, required_any_permission, '
            'parent_menu, icon, sort_order, is_active, data_permission_hint) '
            'VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, NULL)',
            (menu['menu_code'], menu['menu_name'], menu['menu_path'],
             json.dumps(required, ensure_ascii=False), parent, menu['icon'],
             sort_order),
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


def _do_number_sequence(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'number_sequences'):
        print('  - number_sequences 表不存在, 跳过预留编号序列')
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


# ----------------------------------------------------------------------
# 公开：供测试替身复用的结构应用
# ----------------------------------------------------------------------
def apply_segment_schema(conn: sqlite3.Connection) -> None:
    """在给定连接上应用段结构（列/新表/索引/items 列/回填）。

    迁移与内存测试替身共用，保证 DDL 单一来源。
    """
    _do_segment_columns(conn, TX_TABLE)
    _do_segment_columns(conn, BAL_TABLE)
    _do_tables(conn)
    _do_indexes(conn)
    _do_balance_key(conn)
    _do_item_columns(conn)
    _do_backfill(conn)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v205] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v205] 开始: 库存段、预留与 ATP 铺底（INV-2）')
        apply_segment_schema(conn)
        _do_transaction_types(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        _do_cleanup_auto_menu(conn)
        _do_params(conn)
        _do_number_sequence(conn)
        conn.commit()
        print('[v205] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v205] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v205 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table, _sql in TABLES:
            if not _table_exists(conn, table):
                print(f'[v205 verify] FAIL: 缺表 {table}')
                ok = False

        for table in (TX_TABLE, BAL_TABLE):
            if not _table_exists(conn, table):
                print(f'[v205 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            missing = set(SEGMENT_COL_NAMES) - _columns(conn, table)
            if missing:
                print(f'[v205 verify] FAIL: {table} 缺列 {sorted(missing)}')
                ok = False

        for name, table, _sql in INDEXES:
            if _table_exists(conn, table) and not _index_exists(conn, name):
                print(f'[v205 verify] FAIL: 缺索引 {name}')
                ok = False
        if _table_exists(conn, BAL_TABLE):
            if not _index_exists(conn, NEW_BALANCE_INDEX):
                print(f'[v205 verify] FAIL: 缺索引 {NEW_BALANCE_INDEX}')
                ok = False
            if _index_exists(conn, OLD_BALANCE_INDEX):
                print(f'[v205 verify] FAIL: 旧索引 {OLD_BALANCE_INDEX} 仍存在')
                ok = False

        if _table_exists(conn, ITEM_TABLE):
            missing = {c for c, _d in ITEM_COLUMNS} - _columns(conn, ITEM_TABLE)
            if missing:
                print(f'[v205 verify] FAIL: items 缺列 {sorted(missing)}')
                ok = False
        else:
            print('[v205 verify] FAIL: 缺 items 表')
            ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute('SELECT 1 FROM enum_types WHERE id=?',
                                    (type_id,)).fetchone():
                    print(f'[v205 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                            'SELECT 1 FROM enum_values WHERE enum_type_id=? '
                            'AND code=?', (type_id, code)).fetchone():
                        print(f'[v205 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if not conn.execute('SELECT 1 FROM permissions WHERE code=?',
                                    (code,)).fetchone():
                    print(f'[v205 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                if not conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                                    (menu['menu_code'],)).fetchone():
                    print(f"[v205 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False

        if _table_exists(conn, 'control_parameter_defs'):
            for code, *_rest in PARAM_DEFS:
                if not conn.execute(
                        'SELECT 1 FROM control_parameter_defs WHERE code=?',
                        (code,)).fetchone():
                    print(f'[v205 verify] FAIL: 缺参数 {code}')
                    ok = False

        if _table_exists(conn, 'number_sequences'):
            if not conn.execute('SELECT 1 FROM number_sequences WHERE code=?',
                                (NUMBER_SEQUENCE[0],)).fetchone():
                print('[v205 verify] FAIL: 缺编号序列 RSV')
                ok = False

        for table in (TX_TABLE, BAL_TABLE):
            if not _table_exists(conn, table):
                continue
            count = conn.execute(
                'SELECT COUNT(*) FROM %s' % table).fetchone()[0]
            bad = conn.execute(
                "SELECT COUNT(*) FROM %s WHERE stock_segment_type IS NULL "
                "OR stock_segment_type = ''" % table).fetchone()[0]
            print(f'[v205 verify] {table} 行数: {count} 待清洗: {bad}')
            if bad:
                print(f'[v205 verify] FAIL: {table} 存在空段类型 {bad}')
                ok = False

        if ok:
            print('[v205 verify] PASS')
        return ok
    finally:
        conn.close()


def _non_owned_segment_count(conn: sqlite3.Connection) -> int:
    total = 0
    for table in (TX_TABLE, BAL_TABLE, RESERVATION_TABLE):
        if not _table_exists(conn, table):
            continue
        if 'stock_segment_type' not in _columns(conn, table):
            continue
        total += conn.execute(
            "SELECT COUNT(*) FROM %s WHERE stock_segment_type != 'owned'"
            % table).fetchone()[0]
    return total


def rollback(db_path: Path) -> bool:
    """降级：有非 owned 段数据时拒绝（保留结构），否则清理本迁移对象。"""
    if not db_path.exists():
        print(f'[v205 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        non_owned = _non_owned_segment_count(conn)
        if non_owned:
            print(f'[v205 rollback] REFUSE: 存在 {non_owned} 条非 owned 段数据，'
                  '请先清洗后再回滚')
            return False

        for table, _sql in TABLES:
            if _table_exists(conn, table):
                conn.execute('DROP TABLE %s' % table)
                print(f'  - [DROP] 表 {table}')
        if _table_exists(conn, BAL_TABLE):
            if _index_exists(conn, NEW_BALANCE_INDEX):
                conn.execute('DROP INDEX %s' % NEW_BALANCE_INDEX)
                print(f'  - [DROP] 索引 {NEW_BALANCE_INDEX}')
            if not _index_exists(conn, OLD_BALANCE_INDEX):
                conn.execute(
                    'CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s'
                    '(org_id, location_id, item_id, batch_id, stock_status)'
                    % (OLD_BALANCE_INDEX, BAL_TABLE))
                print(f'  - [RESTORE] 索引 {OLD_BALANCE_INDEX}')

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                conn.execute('DELETE FROM menus WHERE menu_code=?',
                             (menu['menu_code'],))
            print('  - [DROP] 菜单 2 个')
        if _table_exists(conn, 'menu_permissions'):
            for menu in MENUS:
                conn.execute('DELETE FROM menu_permissions WHERE menu_code=?',
                             (menu['menu_code'],))
        if _table_exists(conn, 'control_parameter_defs'):
            for code, *_rest in PARAM_DEFS:
                conn.execute(
                    'DELETE FROM control_parameter_defs WHERE code=?', (code,))
        if _table_exists(conn, 'permissions'):
            codes = [p[0] for p in PERMISSIONS]
            ids = [row[0] for row in conn.execute(
                'SELECT id FROM permissions WHERE code IN (%s)'
                % ', '.join('?' * len(codes)), codes).fetchall()]
            if ids and _table_exists(conn, 'permission_set_permissions'):
                conn.execute(
                    'DELETE FROM permission_set_permissions WHERE permission_id '
                    'IN (%s)' % ', '.join('?' * len(ids)), ids)
            conn.execute(
                'DELETE FROM permissions WHERE code IN (%s)'
                % ', '.join('?' * len(codes)), codes)
            print('  - [DROP] 权限 5 条（含已授权行）')
        if _table_exists(conn, 'enum_values'):
            for type_id, *_rest in ENUM_SEEDS:
                conn.execute('DELETE FROM enum_values WHERE enum_type_id=?',
                             (type_id,))
            print('  - [DROP] 枚举值 5 类')
        if _table_exists(conn, 'enum_types'):
            for type_id, *_rest in ENUM_SEEDS:
                conn.execute('DELETE FROM enum_types WHERE id=?', (type_id,))
            print('  - [DROP] 枚举类型 5 个')
        if _table_exists(conn, 'number_sequences'):
            conn.execute('DELETE FROM number_sequences WHERE code=?',
                         (NUMBER_SEQUENCE[0],))
            print('  - [DROP] 编号序列 RSV')
        conn.commit()
        print('[v205 rollback] 完成（段列保留，SQLite 无安全 DROP COLUMN）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v205 rollback] 失败: {e}')
        raise
    finally:
        conn.close()
