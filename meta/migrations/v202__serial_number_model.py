# -*- coding: utf-8 -*-
"""[v202 2026-11-03] 序列号对象模型（P6a）

依据:
  docs/specs/p6-serial-number-model/spec.md
  docs/specs/p6-serial-number-model/tasks.md

范围:
  1. 建 3 张表：
       serial_numbers（主档 + 当前态投影）
       serial_transactions（序列号事件账）
       document_serial_links（单据对象清单）
  2. 索引：uq_serial_number / uq_serial_uii（部分唯一）/ idx_serial_org_item /
     idx_serial_parent / idx_serial_status；事件账 3 条；对象清单 3 条。
  3. items 加三列 serial_tracked / require_on_receipt / require_on_issue。
  4. 注册 5 个枚举：serial_usage_status / serial_quality_status /
     serial_source_type / serial_relation_type / serial_txn_type。
  5. 权限 8 条 + 授权 admin / default；3 个菜单
     （serial-number-list / serial-transaction-list / document-serial-link-list）。
  6. 历史 serial_no 回填：qty=1 建主档 + link；qty>1 跳过并记
     SERIAL_BACKFILL_SKIPPED_MULTI_QTY；重复号保留最早并记
     SERIAL_BACKFILL_DUPLICATE；每行先查唯一键保证幂等。

幂等:
  表 / 索引 / 枚举 / 权限 / 授权 / 菜单先查后用；重复执行打印 [SKIP]。
  回填按 (item_id, org_id, serial_no) 与 (doc_type, line_id, serial_id) 查重。

回滚:
  删菜单与 menu_permissions → 删权限与授权 → 删索引 → 删三表；
  items 三列保留（SQLite 旧版本无法安全 DROP COLUMN，仅清零取值）。
"""
import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v202__serial_number_model'

SERIAL_TABLE = 'serial_numbers'
TX_TABLE = 'serial_transactions'
LINK_TABLE = 'document_serial_links'
ITEM_TABLE = 'items'
RECEIPT_TABLE = 'receipts'
RECEIPT_LINE_TABLE = 'receipt_lines'
SHIPMENT_TABLE = 'shipments'
SHIPMENT_LINE_TABLE = 'shipment_lines'
LOCATION_TABLE = 'locations'

USAGE_STATUSES = ('defined', 'in_stores', 'in_transit', 'issued', 'shipped',
                  'consumed', 'returned', 'scrapped')
QUALITY_STATUSES = ('unrestricted', 'inspection', 'blocked')
SOURCE_TYPES = ('received', 'produced', 'opening', 'issue_created')
RELATION_TYPES = ('assembly', 'packaging')
TXN_TYPES = ('create', 'receive', 'issue', 'transfer_out', 'transfer_in',
             'ship', 'return', 'adjust', 'status_change', 'scrap')

TABLES = (
    (SERIAL_TABLE, """
CREATE TABLE IF NOT EXISTS serial_numbers (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    org_id INTEGER NOT NULL,
    serial_no VARCHAR(64) NOT NULL,
    uii VARCHAR(64),
    batch_id INTEGER,
    revision VARCHAR(20),
    usage_status VARCHAR(20) NOT NULL DEFAULT 'defined',
    quality_status VARCHAR(20) NOT NULL DEFAULT 'unrestricted',
    current_location_id INTEGER,
    parent_serial_id INTEGER,
    relation_type VARCHAR(20),
    parent_item_id INTEGER,
    source_type VARCHAR(20) NOT NULL DEFAULT 'received',
    source_doc_type VARCHAR(50),
    source_doc_id INTEGER,
    received_at DATETIME,
    produced_at DATETIME,
    shipped_at DATETIME,
    scrapped_at DATETIME,
    remark VARCHAR(255),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (usage_status IN ('defined', 'in_stores', 'in_transit', 'issued',
                            'shipped', 'consumed', 'returned', 'scrapped')),
    CHECK (quality_status IN ('unrestricted', 'inspection', 'blocked')),
    CHECK (source_type IN ('received', 'produced', 'opening', 'issue_created')),
    CHECK (relation_type IS NULL OR relation_type IN ('assembly', 'packaging')),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    FOREIGN KEY (current_location_id) REFERENCES locations(id),
    FOREIGN KEY (parent_serial_id) REFERENCES serial_numbers(id)
)
"""),
    (TX_TABLE, """
CREATE TABLE IF NOT EXISTS serial_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_id INTEGER NOT NULL,
    inventory_transaction_id INTEGER,
    txn_type VARCHAR(20) NOT NULL,
    txn_date DATETIME NOT NULL,
    org_from_id INTEGER,
    org_to_id INTEGER,
    location_from_id INTEGER,
    location_to_id INTEGER,
    batch_from_id INTEGER,
    batch_to_id INTEGER,
    usage_from VARCHAR(20),
    usage_to VARCHAR(20),
    quality_from VARCHAR(20),
    quality_to VARCHAR(20),
    doc_type VARCHAR(30),
    doc_id INTEGER,
    line_id INTEGER,
    remark VARCHAR(255),
    created_by VARCHAR(200),
    created_at DATETIME,
    CHECK (txn_type IN ('create', 'receive', 'issue', 'transfer_out',
                        'transfer_in', 'ship', 'return', 'adjust',
                        'status_change', 'scrap')),
    FOREIGN KEY (serial_id) REFERENCES serial_numbers(id)
)
"""),
    (LINK_TABLE, """
CREATE TABLE IF NOT EXISTS document_serial_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type VARCHAR(30) NOT NULL,
    doc_id INTEGER NOT NULL,
    line_id INTEGER NOT NULL,
    serial_id INTEGER NOT NULL,
    direction VARCHAR(10) NOT NULL,
    created_at DATETIME,
    CHECK (direction IN ('in', 'out')),
    FOREIGN KEY (serial_id) REFERENCES serial_numbers(id)
)
"""),
)

INDEXES = (
    (SERIAL_TABLE, 'uq_serial_number',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_serial_number '
     'ON serial_numbers(item_id, org_id, serial_no)'),
    (SERIAL_TABLE, 'uq_serial_uii',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_serial_uii '
     "ON serial_numbers(uii) WHERE uii IS NOT NULL"),
    (SERIAL_TABLE, 'idx_serial_org_item',
     'CREATE INDEX IF NOT EXISTS idx_serial_org_item '
     'ON serial_numbers(org_id, item_id)'),
    (SERIAL_TABLE, 'idx_serial_parent',
     'CREATE INDEX IF NOT EXISTS idx_serial_parent '
     'ON serial_numbers(parent_serial_id)'),
    (SERIAL_TABLE, 'idx_serial_status',
     'CREATE INDEX IF NOT EXISTS idx_serial_status '
     'ON serial_numbers(usage_status)'),

    (TX_TABLE, 'idx_serial_tx_serial_date',
     'CREATE INDEX IF NOT EXISTS idx_serial_tx_serial_date '
     'ON serial_transactions(serial_id, txn_date)'),
    (TX_TABLE, 'idx_serial_tx_inv_tx',
     'CREATE INDEX IF NOT EXISTS idx_serial_tx_inv_tx '
     'ON serial_transactions(inventory_transaction_id)'),
    (TX_TABLE, 'idx_serial_tx_doc',
     'CREATE INDEX IF NOT EXISTS idx_serial_tx_doc '
     'ON serial_transactions(doc_type, doc_id)'),

    (LINK_TABLE, 'uq_document_serial_link',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_document_serial_link '
     'ON document_serial_links(doc_type, line_id, serial_id)'),
    (LINK_TABLE, 'idx_document_serial_doc',
     'CREATE INDEX IF NOT EXISTS idx_document_serial_doc '
     'ON document_serial_links(doc_type, doc_id)'),
    (LINK_TABLE, 'idx_document_serial_serial',
     'CREATE INDEX IF NOT EXISTS idx_document_serial_serial '
     'ON document_serial_links(serial_id)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('serial_usage_status', '序列号用途状态',
     '序列号用途状态取值（建档 / 在库 / 在途 / 待运 / 发运 / 耗用 / 退回 / 报废）',
     (('defined', '已建档', 'Defined'),
      ('in_stores', '在库', 'In Stores'),
      ('in_transit', '在途', 'In Transit'),
      ('issued', '已发出待运', 'Issued'),
      ('shipped', '已发运', 'Shipped'),
      ('consumed', '已耗用', 'Consumed'),
      ('returned', '已退回', 'Returned'),
      ('scrapped', '已报废', 'Scrapped'))),
    ('serial_quality_status', '序列号质量状态',
     '序列号质量状态取值（可用 / 检验中 / 冻结）',
     (('unrestricted', '可用', 'Unrestricted'),
      ('inspection', '检验中', 'Inspection'),
      ('blocked', '冻结', 'Blocked'))),
    ('serial_source_type', '序列号来源类型',
     '序列号建档来源（收货 / 完工 / 期初 / 发货时建档）',
     (('received', '收货', 'Received'),
      ('produced', '完工', 'Produced'),
      ('opening', '期初', 'Opening'),
      ('issue_created', '发货时建档', 'Issue Created'))),
    ('serial_relation_type', '序列号谱系关系',
     '父子谱系关系（装配 / 包装）',
     (('assembly', '装配', 'Assembly'),
      ('packaging', '包装', 'Packaging'))),
    ('serial_txn_type', '序列号事件类型',
     '序列号事件账类型（建档 / 收货 / 领用 / 调拨 / 发运 / 退回 / 调整 / 状态变更 / 报废）',
     (('create', '建档', 'Create'),
      ('receive', '收货', 'Receive'),
      ('issue', '领用', 'Issue'),
      ('transfer_out', '调出', 'Transfer Out'),
      ('transfer_in', '调入', 'Transfer In'),
      ('ship', '发运', 'Ship'),
      ('return', '退回', 'Return'),
      ('adjust', '调整', 'Adjust'),
      ('status_change', '状态变更', 'Status Change'),
      ('scrap', '报废', 'Scrap'))),
)

PERMISSIONS = (
    ('serial_number:serial_number_read', '序列号查看', 'serial_number', 'read'),
    ('serial_number:serial_number_create', '序列号新建', 'serial_number', 'create'),
    ('serial_number:serial_number_update', '序列号修改', 'serial_number', 'update'),
    ('serial_number:serial_number_delete', '序列号删除', 'serial_number', 'delete'),
    ('serial_transaction:serial_transaction_read', '序列号事件查看',
     'serial_transaction', 'read'),
    ('serial_transaction:serial_transaction_list', '序列号事件查询',
     'serial_transaction', 'list'),
    ('document_serial_link:document_serial_link_read', '单据序列号关系查看',
     'document_serial_link', 'read'),
    ('document_serial_link:document_serial_link_list', '单据序列号关系查询',
     'document_serial_link', 'list'),
)

GRANT_TO_SETS = ('admin', 'default')

MENUS = (
    {
        'menu_code': 'serial-number-list',
        'menu_name': '序列号',
        'menu_path': '/master-data/serial-number',
        'parent_menu': 'master-data',
        'primary_object_type': 'serial_number',
        'include_actions': ['read', 'create', 'update', 'delete'],
        'icon': 'Tickets',
        'color': '#0ea5e9',
        'sort_order': 107,
        'description': '序列号主档——按号识别的最小库存单位与当前状态',
    },
    {
        'menu_code': 'serial-transaction-list',
        'menu_name': '序列号事件',
        'menu_path': '/inventory/serial-transactions',
        'parent_menu': 'inventory',
        'primary_object_type': 'serial_transaction',
        'include_actions': ['read', 'list'],
        'icon': 'List',
        'color': '#64748b',
        'sort_order': 7,
        'description': '序列号事件账只读查询（建档 / 收货 / 发运 / 状态变更）',
    },
    {
        'menu_code': 'document-serial-link-list',
        'menu_name': '单据序列号关系',
        'menu_path': '/inventory/document-serial-links',
        'parent_menu': 'inventory',
        'primary_object_type': 'document_serial_link',
        'include_actions': ['read', 'list'],
        'icon': 'List',
        'color': '#64748b',
        'sort_order': 8,
        'description': '单据与序列号对象清单只读查询（收货 / 发运 / 调拨 / 工单）',
    },
)

_ORPHAN_MENU_CODES = ('serial_number-list', 'serial_transaction-list',
                      'document_serial_link-list')


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
            print(f'  - [SKIP] 表 {table} 已存在')
            continue
        conn.execute(sql)
        print(f'  - [NEW] 表 {table}')


def _create_index(conn: sqlite3.Connection, name: str, sql: str) -> None:
    if _index_exists(conn, name):
        print(f'  - [SKIP] 索引 {name} 已存在')
        return
    conn.execute(sql)
    print(f'  - [NEW] 索引 {name}')


def _do_indexes(conn: sqlite3.Connection) -> None:
    for _table, name, sql in INDEXES:
        _create_index(conn, name, sql)


def _do_item_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, ITEM_TABLE):
        print('  - items 表不存在, 跳过三开关列')
        return
    have = _columns(conn, ITEM_TABLE)
    for column in ('serial_tracked', 'require_on_receipt', 'require_on_issue'):
        if column in have:
            print(f'  - [SKIP] items.{column} 已存在')
            continue
        conn.execute(
            'ALTER TABLE items ADD COLUMN %s INTEGER NOT NULL DEFAULT 0' % column)
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
                    f'{id_col} = ? AND permission_id = ?',
                    (permission_set_id, prow[0])).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    f'({id_col}, permission_code, permission_id, granted, '
                    "created_at) VALUES (?, ?, ?, 1, datetime('now'))",
                    (permission_set_id, code, prow[0]))
            else:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    f'({id_col}, permission_id, granted, created_at) '
                    "VALUES (?, ?, 1, datetime('now'))",
                    (permission_set_id, prow[0]))
            granted += 1
    print(f'  - [SUMMARY] permission_set_permissions: +{granted}')


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
    required = ['{0}:{0}_{1}'.format(menu['primary_object_type'], action)
                for action in menu['include_actions']]
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
            ))
        print(f"  - [NEW] 菜单 {menu['menu_code']} (sort={sort_order})")

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


# ----------------------------------------------------------------------
# 回填（D14）：只处理 qty=1 的存量行；qty>1 / 拼接串 / 重复号只记日志
# ----------------------------------------------------------------------
def _is_concatenated(serial_no: str) -> bool:
    return any(ch in serial_no for ch in (',', ';', '，', '；', '\n'))


def _find_serial(conn: sqlite3.Connection, item_id, org_id, serial_no):
    return conn.execute(
        'SELECT id, usage_status FROM serial_numbers WHERE item_id=? AND org_id=? '
        'AND serial_no=?', (item_id, org_id, serial_no)).fetchone()


def _insert_serial(conn: sqlite3.Connection, item_id, org_id, serial_no,
                   usage_status: str, source_doc_type: str, source_doc_id,
                   location_id, batch_id, timestamp) -> int:
    cur = conn.execute(
        'INSERT INTO serial_numbers (item_id, org_id, serial_no, batch_id, '
        ' usage_status, quality_status, current_location_id, source_type, '
        ' source_doc_type, source_doc_id, received_at, shipped_at, '
        ' created_at, updated_at) '
        "VALUES (?, ?, ?, ?, ?, 'unrestricted', ?, 'received', ?, ?, ?, ?, "
        "datetime('now'), datetime('now'))",
        (item_id, org_id, serial_no, batch_id, usage_status, location_id,
         source_doc_type, source_doc_id, timestamp,
         timestamp if usage_status == 'shipped' else None))
    return cur.lastrowid


def _insert_event(conn: sqlite3.Connection, serial_id, txn_type: str,
                  txn_date, org_to_id, location_to_id, usage_from: str,
                  usage_to: str, doc_type: str, doc_id, line_id,
                  remark: str) -> None:
    if conn.execute(
            'SELECT 1 FROM serial_transactions WHERE serial_id=? AND txn_type=? '
            'AND doc_type=? AND doc_id=? AND line_id=?',
            (serial_id, txn_type, doc_type, doc_id, line_id)).fetchone():
        return
    conn.execute(
        'INSERT INTO serial_transactions (serial_id, txn_type, txn_date, '
        ' org_to_id, location_to_id, usage_from, usage_to, doc_type, doc_id, '
        ' line_id, remark, created_at) '
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (serial_id, txn_type, txn_date, org_to_id, location_to_id, usage_from,
         usage_to, doc_type, doc_id, line_id, remark))


def _ensure_link(conn: sqlite3.Connection, doc_type: str, doc_id, line_id,
                 serial_id, direction: str) -> None:
    if conn.execute(
            'SELECT 1 FROM document_serial_links WHERE doc_type=? AND line_id=? '
            'AND serial_id=?', (doc_type, line_id, serial_id)).fetchone():
        return
    conn.execute(
        'INSERT INTO document_serial_links (doc_type, doc_id, line_id, serial_id, '
        "direction, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (doc_type, doc_id, line_id, serial_id, direction))


def _resolve_batch(conn: sqlite3.Connection, item_id, org_id, lot_no):
    if not lot_no:
        return None
    row = conn.execute(
        'SELECT id FROM batches WHERE item_id=? AND org_id=? AND batch_no=?',
        (item_id, org_id, str(lot_no).strip())).fetchone()
    return row[0] if row else None


def _backfill_receipts(conn: sqlite3.Connection, stats: dict,
                       seen: set) -> None:
    required = (RECEIPT_TABLE, RECEIPT_LINE_TABLE, ITEM_TABLE)
    if not all(_table_exists(conn, t) for t in required):
        print('  - 收货表缺失, 跳过收货行回填')
        return
    rows = conn.execute(
        'SELECT rl.id AS line_id, rl.receipt_id, rl.item_id, rl.serial_no, '
        ' rl.qty_received, rl.qty_rejected, rl.lot_no, '
        ' COALESCE(r.inventory_org_id, r.org_id) AS org_id, '
        ' r.deliver_to_location_id AS location_id, r.actual_arrival_date '
        'FROM receipt_lines rl JOIN receipts r ON r.id = rl.receipt_id '
        "WHERE rl.serial_no IS NOT NULL AND TRIM(rl.serial_no) <> ''"
    ).fetchall()
    for row in rows:
        line_id = row[0]
        serial_no = str(row[3] or '').strip()
        received = float(row[4] or 0)
        qty_rejected = float(row[5] or 0)
        org_id = row[7]
        stats['receipts_total'] += 1
        if _is_concatenated(serial_no):
            stats['skipped_concat'] += 1
            print(f'  - [WARN] SERIAL_BACKFILL_SKIPPED_CONCATENATED '
                  f'receipt_line={line_id} serial={serial_no}')
            continue
        if received > 1 or qty_rejected > 0:
            stats['skipped_multi_qty'] += 1
            print(f'  - [WARN] SERIAL_BACKFILL_SKIPPED_MULTI_QTY '
                  f'receipt_line={line_id} qty={received}')
            continue
        if received != 1 or not org_id:
            if not org_id:
                stats['skipped_no_org'] += 1
                print(f'  - [WARN] SERIAL_BACKFILL_SKIPPED_NO_ORG '
                      f'receipt_line={line_id}')
            continue
        key = (row[2], org_id, serial_no)
        if key in seen:
            stats['duplicates'] += 1
            print(f'  - [WARN] SERIAL_BACKFILL_DUPLICATE '
                  f'receipt_line={line_id} serial={serial_no}')
            continue
        serial = _find_serial(conn, row[2], org_id, serial_no)
        if serial is None:
            batch_id = _resolve_batch(conn, row[2], org_id, row[6])
            serial_id = _insert_serial(
                conn, row[2], org_id, serial_no, 'in_stores', 'receipt',
                row[1], row[8], batch_id, row[9])
            _insert_event(conn, serial_id, 'receive', row[9], org_id, row[8],
                          'defined', 'in_stores', 'receipt', row[1], line_id,
                          'v202 回填收货行')
            stats['receipts_backfilled'] += 1
        else:
            serial_id = serial[0]
        seen.add(key)
        _ensure_link(conn, 'receipt', row[1], line_id, serial_id, 'in')


def _backfill_shipments(conn: sqlite3.Connection, stats: dict,
                        seen: set) -> None:
    required = (SHIPMENT_TABLE, SHIPMENT_LINE_TABLE, ITEM_TABLE,
                LOCATION_TABLE)
    if not all(_table_exists(conn, t) for t in required):
        print('  - 发运表缺失, 跳过发运行回填')
        return
    rows = conn.execute(
        'SELECT sl.id AS line_id, sl.delivery_id, sl.item_id, sl.serial_no, '
        ' sl.qty, s.ship_from_location_id, s.actual_ship_date, l.org_id '
        'FROM shipment_lines sl JOIN shipments s ON s.id = sl.delivery_id '
        'LEFT JOIN locations l ON l.id = s.ship_from_location_id '
        "WHERE sl.serial_no IS NOT NULL AND TRIM(sl.serial_no) <> ''"
    ).fetchall()
    for row in rows:
        line_id = row[0]
        serial_no = str(row[3] or '').strip()
        qty = float(row[4] or 0)
        org_id = row[7]
        stats['shipments_total'] += 1
        if _is_concatenated(serial_no):
            stats['skipped_concat'] += 1
            print(f'  - [WARN] SERIAL_BACKFILL_SKIPPED_CONCATENATED '
                  f'shipment_line={line_id} serial={serial_no}')
            continue
        if qty > 1:
            stats['skipped_multi_qty'] += 1
            print(f'  - [WARN] SERIAL_BACKFILL_SKIPPED_MULTI_QTY '
                  f'shipment_line={line_id} qty={qty}')
            continue
        if qty != 1 or not org_id:
            if not org_id:
                stats['skipped_no_org'] += 1
                print(f'  - [WARN] SERIAL_BACKFILL_SKIPPED_NO_ORG '
                      f'shipment_line={line_id}')
            continue
        key = (row[2], org_id, serial_no)
        if key in seen:
            stats['duplicates'] += 1
            print(f'  - [WARN] SERIAL_BACKFILL_DUPLICATE '
                  f'shipment_line={line_id} serial={serial_no}')
            continue
        serial = _find_serial(conn, row[2], org_id, serial_no)
        if serial is None:
            serial_id = _insert_serial(
                conn, row[2], org_id, serial_no, 'shipped', 'shipment',
                row[1], None, None, row[6])
            _insert_event(conn, serial_id, 'ship', row[6], org_id, None,
                          'defined', 'shipped', 'shipment', row[1], line_id,
                          'v202 回填发运行')
            stats['shipments_backfilled'] += 1
        else:
            serial_id = serial[0]
            conn.execute(
                'UPDATE serial_numbers SET usage_status=?, current_location_id=NULL, '
                ' shipped_at=COALESCE(shipped_at, ?), updated_at=datetime(\'now\') '
                'WHERE id=?', ('shipped', row[6], serial_id))
            _insert_event(conn, serial_id, 'ship', row[6], org_id, None,
                          serial[1] if serial[1] else 'in_stores', 'shipped',
                          'shipment', row[1], line_id, 'v202 回填发运行')
        seen.add(key)
        _ensure_link(conn, 'shipment', row[1], line_id, serial_id, 'out')


def _do_backfill(conn: sqlite3.Connection) -> dict:
    stats = {
        'receipts_total': 0, 'receipts_backfilled': 0,
        'shipments_total': 0, 'shipments_backfilled': 0,
        'skipped_multi_qty': 0, 'skipped_concat': 0, 'skipped_no_org': 0,
        'duplicates': 0,
    }
    if not _table_exists(conn, SERIAL_TABLE):
        print('  - serial_numbers 不存在, 跳过回填')
        return stats
    seen: set = set()
    _backfill_receipts(conn, stats, seen)
    _backfill_shipments(conn, stats, seen)
    print(f'  - [SUMMARY] backfill: receipts={stats["receipts_backfilled"]}/'
          f'{stats["receipts_total"]} shipments={stats["shipments_backfilled"]}/'
          f'{stats["shipments_total"]} skipped_multi_qty='
          f'{stats["skipped_multi_qty"]} duplicates={stats["duplicates"]} '
          f'skipped_concat={stats["skipped_concat"]}')
    return stats


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v202] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v202] 开始: 序列号对象模型（P6a）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_item_columns(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        _do_cleanup_auto_menu(conn)
        _do_backfill(conn)
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
            SERIAL_TABLE: {'item_id', 'org_id', 'serial_no', 'uii', 'batch_id',
                           'revision', 'usage_status', 'quality_status',
                           'current_location_id', 'parent_serial_id',
                           'relation_type', 'parent_item_id', 'source_type',
                           'source_doc_type', 'source_doc_id', 'received_at',
                           'produced_at', 'shipped_at', 'scrapped_at'},
            TX_TABLE: {'serial_id', 'inventory_transaction_id', 'txn_type',
                       'txn_date', 'org_from_id', 'org_to_id',
                       'location_from_id', 'location_to_id', 'batch_from_id',
                       'batch_to_id', 'usage_from', 'usage_to', 'quality_from',
                       'quality_to', 'doc_type', 'doc_id', 'line_id'},
            LINK_TABLE: {'doc_type', 'doc_id', 'line_id', 'serial_id',
                         'direction'},
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                continue
            missing = cols - _columns(conn, table)
            if missing:
                print(f'[v202 verify] FAIL: {table} 缺列 {sorted(missing)}')
                ok = False

        for _table, name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v202 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, ITEM_TABLE):
            missing = {'serial_tracked', 'require_on_receipt',
                       'require_on_issue'} - _columns(conn, ITEM_TABLE)
            if missing:
                print(f'[v202 verify] FAIL: items 缺列 {sorted(missing)}')
                ok = False
        else:
            print('[v202 verify] FAIL: 缺 items 表')
            ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute('SELECT 1 FROM enum_types WHERE id=?',
                                    (type_id,)).fetchone():
                    print(f'[v202 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                            'SELECT 1 FROM enum_values WHERE enum_type_id=? '
                            'AND code=?', (type_id, code)).fetchone():
                        print(f'[v202 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False
        else:
            print('[v202 verify] FAIL: 缺 enum_types / enum_values 表')
            ok = False

        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if not conn.execute('SELECT 1 FROM permissions WHERE code=?',
                                    (code,)).fetchone():
                    print(f'[v202 verify] FAIL: 缺权限 {code}')
                    ok = False
        else:
            print('[v202 verify] FAIL: 缺 permissions 表')
            ok = False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                if not conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                                    (menu['menu_code'],)).fetchone():
                    print(f"[v202 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False
        else:
            print('[v202 verify] FAIL: 缺 menus 表')
            ok = False

        if _table_exists(conn, SERIAL_TABLE):
            count = conn.execute('SELECT COUNT(*) FROM serial_numbers').fetchone()[0]
            print(f'[v202 verify] serial_numbers 行数: {count}')

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
        print('[v202] 回滚: 序列号对象模型')
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
                conn.execute(f'DROP INDEX IF EXISTS {name}')

        for table in (LINK_TABLE, TX_TABLE, SERIAL_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')

        if _table_exists(conn, ITEM_TABLE):
            have = _columns(conn, ITEM_TABLE)
            for column in ('serial_tracked', 'require_on_receipt',
                           'require_on_issue'):
                if column in have:
                    conn.execute('UPDATE items SET %s = 0' % column)
            print('  - [KEEP] items 三开关列保留（SQLite 不支持安全 DROP COLUMN，取值已清零）')

        conn.commit()
        print('[v202] 回滚完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v202] 回滚失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback
