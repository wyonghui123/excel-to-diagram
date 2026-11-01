# -*- coding: utf-8 -*-
"""[v186 2026-11-01] 采购收货对象模型（M3 第二阶段）

依据:
  docs/specs/spec-receipt-object-model-2026-11-01.md
    §3 头字段 / §4 行字段 / §5 状态机与不变量 / §12 页面菜单权限
    §13 实施清单步骤 3

范围:
  1. 建 2 张表：receipts / receipt_lines
     （表由 meta/schemas/{receipt,receipt_line}.yaml 声明，
     本迁移做兜底 CREATE + 显式索引，防止仅 sync_schema 漏建）
  2. purchase_order_schedules 补三列：
       rejected_qty / completion_source / completion_prev_status（先查后用，幂等）
  3. type_definitions 种子：头类型 RCV_STD（standard）/ RCV_RETURN（return）
  4. number_sequences 种子 RCV + 回填两个头类型的 number_sequence_id
  5. control_parameter_defs 种子 receipt_over_tolerance_percent（默认 0）
  6. permissions 双段式 {bo}:{bo}_{action}（receipt 8 动作 / receipt_line 5 动作），
     授予 admin / default 权限集
  7. 菜单：顶层容器 procurement（若缺则补建）+ goods-receipt-management → /receipts
  8. 清理自动生成器可能留下的 *-list 孤儿菜单

幂等:
  表 / 列 / 索引 / 类型 / 序列 / 参数 / 权限 / 菜单先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单 + 丢索引 + 删表；解除类型序列绑定后删序列；删参数定义；删三列新增列；
  type_definitions 与 permissions 行保留（可能已被单据 / 角色引用）。
"""
import json
import sqlite3
import sys
from pathlib import Path

RECEIPT_TABLE = 'receipts'
RECEIPT_LINE_TABLE = 'receipt_lines'
POS_TABLE = 'purchase_order_schedules'

SCOPE_BO = 'receipt'

#: 新增到 purchase_order_schedules 的列（列名 → DDL 片段）
POS_COLUMNS = (
    ('rejected_qty', 'REAL NULL'),
    ('completion_source', 'VARCHAR(20) NULL'),
    ('completion_prev_status', 'VARCHAR(20) NULL'),
)

#: 头类型 (code, name, document_category, description)
HEADER_TYPES = (
    ('RCV_STD', '标准收货单', 'standard',
     '采购收货默认单据类型（编号 / 打印 / 权限等治理语义的挂载点）'),
    ('RCV_RETURN', '红字收货单', 'return',
     '整单红冲生成的负向收货单类型（必须引用原收货单）'),
)

#: (code, name, pattern, date_field, start_value, on_exhaust, description)
NUMBER_SEQUENCE = (
    'RCV', '收货单编号', 'RCV-{DATE:yyyymm}-{SEQ:6}', 'receipt_date', 1,
    'error', '收货单取号：RCV-年月-6 位流水，按月复位（标准单与红字单共用）',
)

#: (code, name, value_type, default_value, description)
PARAM_DEF = (
    'receipt_over_tolerance_percent', '收货超收容差（%）', 'number', '0',
    '计划行净收累计允许超出承诺量的百分比；0 = 不允许超收（R-RC-5 / R-RC-9 共用）',
)

TABLES = (
    (RECEIPT_TABLE, """
CREATE TABLE IF NOT EXISTS receipts (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no VARCHAR(200) NOT NULL,
    document_type_id INTEGER,
    receipt_date DATETIME NOT NULL,
    actual_arrival_date DATETIME,
    source_doc_type VARCHAR(200) NOT NULL,
    source_doc_id INTEGER NOT NULL,
    source_doc_no VARCHAR(200),
    supplier_party_id INTEGER,
    supplier_delivery_no VARCHAR(200),
    org_id INTEGER NOT NULL,
    purchase_org_id INTEGER,
    deliver_to_location_id INTEGER,
    project_id INTEGER,
    received_by VARCHAR(200),
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    reversal_of_receipt_id INTEGER,
    reversed_at DATETIME,
    remark TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (document_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (supplier_party_id) REFERENCES parties(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (purchase_org_id) REFERENCES orgs(id),
    FOREIGN KEY (deliver_to_location_id) REFERENCES locations(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (reversal_of_receipt_id) REFERENCES receipts(id)
)
"""),
    (RECEIPT_LINE_TABLE, """
CREATE TABLE IF NOT EXISTS receipt_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL,
    line_no VARCHAR(200) NOT NULL,
    schedule_id INTEGER,
    source_line_id INTEGER,
    order_id INTEGER,
    order_line_id INTEGER,
    item_id INTEGER NOT NULL,
    uom_id INTEGER NOT NULL,
    qty_received REAL NOT NULL,
    qty_rejected REAL DEFAULT 0,
    rejection_reason_code VARCHAR(200),
    rejection_disposition VARCHAR(200),
    lot_no VARCHAR(200),
    serial_no VARCHAR(200),
    putaway_location_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    reversal_of_line_id INTEGER,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (receipt_id) REFERENCES receipts(id),
    FOREIGN KEY (schedule_id) REFERENCES purchase_order_schedules(id),
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY (order_line_id) REFERENCES purchase_order_lines(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id),
    FOREIGN KEY (putaway_location_id) REFERENCES locations(id),
    FOREIGN KEY (reversal_of_line_id) REFERENCES receipt_lines(id)
)
"""),
)

INDEXES = (
    # ---- receipts ----
    # 索引名按 spec §3.1 逐字声明
    ('uq_receipt_no', RECEIPT_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_receipt_no ON receipts(receipt_no)'),
    ('idx_receipt_source', RECEIPT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_source '
     'ON receipts(source_doc_type, source_doc_id)'),
    ('idx_receipt_status_date', RECEIPT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_status_date '
     'ON receipts(status, receipt_date)'),
    ('idx_receipt_supplier', RECEIPT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_supplier ON receipts(supplier_party_id)'),
    ('idx_receipt_reversal', RECEIPT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_reversal '
     'ON receipts(reversal_of_receipt_id)'),
    ('idx_receipt_project', RECEIPT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_project ON receipts(project_id)'),

    # ---- receipt_lines ----
    ('uq_receipt_line_no', RECEIPT_LINE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_receipt_line_no '
     'ON receipt_lines(receipt_id, line_no)'),
    # 同一计划行可分多次收货，schedule_id 不唯一（spec §4.1）
    ('idx_receipt_line_schedule', RECEIPT_LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_line_schedule '
     'ON receipt_lines(schedule_id)'),
    ('idx_receipt_line_order_line', RECEIPT_LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_line_order_line '
     'ON receipt_lines(order_line_id)'),
    ('idx_receipt_line_item', RECEIPT_LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_line_item ON receipt_lines(item_id)'),
    ('idx_receipt_line_lot', RECEIPT_LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_receipt_line_lot ON receipt_lines(lot_no)'),
)

ACTIONS = ('create', 'read', 'update', 'delete', 'list')
_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}
OBJECTS = (
    ('receipt', '收货单'),
    ('receipt_line', '收货行'),
)

#: 单据动作权限（spec §12：过账 / 冲销 / 取消，双段式）
DOC_PERMISSIONS = (
    ('receipt:receipt_post', '收货单过账', 'receipt', 'post'),
    ('receipt:receipt_reverse', '收货单冲销', 'receipt', 'reverse'),
    ('receipt:receipt_cancel', '收货单取消', 'receipt', 'cancel'),
)

PERMISSIONS = tuple(
    ('{0}:{0}_{1}'.format(bo, action),
     '{0}{1}'.format(label, _ACTION_LABEL[action]), bo, action)
    for bo, label in OBJECTS
    for action in ACTIONS
) + DOC_PERMISSIONS

GRANT_TO_SETS = ('admin', 'default')

ROOT_MENU_CODE = 'procurement'
RECEIPT_MENU_CODE = 'goods-receipt-management'

ROOT_MENU = {
    'menu_code': ROOT_MENU_CODE,
    'menu_name': '采购',
    'menu_path': '',
    'page_type': '',
    'primary_object_type': '',
    'object_types': [],
    'bo_bindings': [],
    'required_permissions': [],
    'parent_menu': '',
    'icon': 'ShoppingCart',
    'color': '#0ea5e9',
    'description': '采购域：采购订单、需求分配与到货计划',
    'sort_order': 40,
    'show_in_sidebar': 1,
    'data_permission_hint': {},
}

MENUS = (
    {
        'menu_code': RECEIPT_MENU_CODE,
        'menu_name': '收货单',
        'menu_path': '/receipts',
        'page_type': 'object_list',
        'primary_object_type': 'receipt',
        'object_types': ['receipt'],
        'bo_bindings': [
            {'bo_id': 'receipt', 'role': 'primary', 'include_actions': list(ACTIONS)},
        ],
        'required_permissions': [
            'receipt:receipt_{0}'.format(a) for a in ACTIONS],
        'parent_menu': ROOT_MENU_CODE,
        'icon': 'Inbox',
        'color': '#0ea5e9',
        'description': '收货单：抬头 + 收货行子表，按收货组织做数据范围（已过账 ≠ 已入库）',
        'sort_order': 2,
        'show_in_sidebar': 0,
        'data_permission_hint': {
            'resource_types': ['receipt'],
            'message': '建议分配收货单数据权限（按收货组织）',
        },
    },
)

_ORPHAN_MENU_CODES = (
    'receipt-list',
    'receipt_line-list',
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _do_tables(conn: sqlite3.Connection) -> None:
    for name, ddl in TABLES:
        if _table_exists(conn, name):
            print(f'  - [SKIP] 表 {name} 已存在')
        else:
            conn.execute(ddl)
            print(f'  - [CREATE] 表 {name}')


def _do_pos_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, POS_TABLE):
        print(f'  - [SKIP] 表 {POS_TABLE} 不存在（由 v177 创建）')
        return
    have = _columns(conn, POS_TABLE)
    for name, ddl in POS_COLUMNS:
        if name in have:
            print(f'  - [SKIP] 列 {POS_TABLE}.{name} 已存在')
            continue
        conn.execute(f'ALTER TABLE {POS_TABLE} ADD COLUMN {name} {ddl}')
        print(f'  - [ALTER] 列 {POS_TABLE}.{name}')


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, table, sql in INDEXES:
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
            continue
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 索引 {name} 依赖表 {table} 不存在')
            continue
        conn.execute(sql)
        print(f'  - [ADD] 索引 {name}')


def _type_id(conn: sqlite3.Connection, code: str, level: str):
    row = conn.execute(
        'SELECT id FROM type_definitions WHERE scope_bo=? AND level=? AND code=?',
        (SCOPE_BO, level, code)).fetchone()
    return row[0] if row else None


def _ensure_type(conn: sqlite3.Connection, code: str, name: str,
                 document_category: str, description: str) -> int:
    existing = _type_id(conn, code, 'header')
    if existing:
        print(f'  - [SKIP] 类型 {SCOPE_BO}/header/{code} 已存在 (id={existing})')
        return int(existing)

    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    cur = conn.execute(
        'INSERT INTO type_definitions '
        '(code, name, scope_bo, level, document_category, status, description, '
        ' created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (code, name, SCOPE_BO, 'header', document_category, 'active', description, now))
    new_id = int(cur.lastrowid)
    print(f'  - [NEW] 类型 {SCOPE_BO}/header/{code} (id={new_id})')
    return new_id


def _do_types(conn: sqlite3.Connection) -> dict:
    if not _table_exists(conn, 'type_definitions'):
        print('  - type_definitions 表不存在, 跳过类型种子')
        return {}
    ids = {}
    for code, name, category, desc in HEADER_TYPES:
        ids[code] = _ensure_type(conn, code, name, category, desc)
    return ids


def _do_number_sequence(conn: sqlite3.Connection):
    if not _table_exists(conn, 'number_sequences'):
        print('  - number_sequences 表不存在, 跳过编号序列种子')
        return None
    code = NUMBER_SEQUENCE[0]
    row = conn.execute(
        'SELECT id FROM number_sequences WHERE code=?', (code,)).fetchone()
    if row:
        print(f'  - [SKIP] 编号序列 {code} 已存在 (id={row[0]})')
        return int(row[0])
    cur = conn.execute(
        'INSERT INTO number_sequences '
        '(code, name, pattern, scope_fields, date_field, start_value, '
        ' on_exhaust, preview, status, description, created_at) '
        "VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, 'active', ?, datetime('now'))",
        (code, NUMBER_SEQUENCE[1], NUMBER_SEQUENCE[2], NUMBER_SEQUENCE[3],
         NUMBER_SEQUENCE[4], NUMBER_SEQUENCE[5], NUMBER_SEQUENCE[6]))
    print(f'  - [NEW] 编号序列 {code} (id={cur.lastrowid})')
    return int(cur.lastrowid)


def _do_type_bindings(conn: sqlite3.Connection, type_ids: dict, sequence_id) -> None:
    if not _table_exists(conn, 'type_definitions') or not sequence_id:
        return
    for code in type_ids:
        type_id = type_ids[code]
        row = conn.execute(
            'SELECT number_sequence_id FROM type_definitions WHERE id=?',
            (type_id,)).fetchone()
        if row and row[0]:
            print(f'  - [SKIP] 头类型 {code} number_sequence_id 已绑定 (id={row[0]})')
            continue
        conn.execute(
            'UPDATE type_definitions SET number_sequence_id=? WHERE id=?',
            (sequence_id, type_id))
        print(f'  - [BIND] 头类型 {code} → 编号序列 id={sequence_id}')


def _do_param(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'control_parameter_defs'):
        print('  - control_parameter_defs 不存在, 跳过参数种子')
        return
    code, name, value_type, default_value, desc = PARAM_DEF
    row = conn.execute(
        'SELECT id FROM control_parameter_defs WHERE code=?', (code,)).fetchone()
    if row:
        conn.execute(
            'UPDATE control_parameter_defs SET name=?, domain=?, value_type=?, '
            'target_bo=?, default_value=?, description=?, status=? WHERE id=?',
            (name, 'procurement', value_type, 'receipt', default_value,
             desc, 'active', row[0]))
        print(f'  - [SKIP] 参数 {code} 已存在 (id={row[0]})')
        return
    conn.execute(
        'INSERT INTO control_parameter_defs '
        '(code, name, domain, value_type, target_bo, default_value, status, '
        ' description, created_at) '
        "VALUES (?, ?, 'procurement', ?, 'receipt', ?, 'active', ?, "
        "datetime('now'))",
        (code, name, value_type, default_value, desc))
    print(f'  - [NEW] 参数 {code}')


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
    print(f'  - [SUMMARY] permissions: +{created} 新增')


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
        print('  - permission_set_permissions 无 permission_set_id/role_id, 跳过授权')
        return
    has_code_col = 'permission_code' in cols
    has_granted = 'granted' in cols
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1', (set_code,)
        ).fetchone()
        if not row:
            continue
        permission_set_id = row[0]
        for code, _name, _rtype, _action in PERMISSIONS:
            prow = conn.execute(
                'SELECT id FROM permissions WHERE code=?', (code,)
            ).fetchone()
            if not prow:
                continue
            params = [permission_set_id, prow[0]]
            where = f'{id_col} = ? AND permission_id = ?'
            if has_code_col:
                where += ' AND permission_code = ?'
                params.append(code)
            if conn.execute(
                'SELECT 1 FROM permission_set_permissions WHERE ' + where, params
            ).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    f"INSERT INTO permission_set_permissions "
                    f"({id_col}, permission_code, permission_id, granted, "
                    f"created_at) VALUES (?, ?, ?, ?, datetime('now'))",
                    (permission_set_id, code, prow[0], 1),
                )
            elif has_granted:
                conn.execute(
                    f"INSERT INTO permission_set_permissions "
                    f"({id_col}, permission_id, granted, created_at) "
                    f"VALUES (?, ?, 1, datetime('now'))",
                    (permission_set_id, prow[0]),
                )
            else:
                conn.execute(
                    f"INSERT INTO permission_set_permissions "
                    f"({id_col}, permission_id, created_at) "
                    f"VALUES (?, ?, datetime('now'))",
                    (permission_set_id, prow[0]),
                )
            granted += 1
    print(f'  - [SUMMARY] permission_set_permissions: +{granted} 授权')


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
        else:
            print(f"  - [SKIP] menu_permissions: {menu['menu_code']} 已存在")


def _do_menus(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return
    # 顶层容器若已被 v177 / init 脚本建立则跳过，否则补建（保证孤儿菜单不出现）
    _insert_menu(conn, ROOT_MENU)
    for menu in MENUS:
        _insert_menu(conn, menu)


def _do_cleanup_auto_menu(conn: sqlite3.Connection) -> None:
    """清掉自动生成器可能产出的孤儿菜单（* -list）。"""
    if not _table_exists(conn, 'menus'):
        return
    for code in _ORPHAN_MENU_CODES:
        cur = conn.execute(
            'DELETE FROM menus WHERE menu_code=? AND auto_generated=1', (code,))
        if cur.rowcount:
            print(f'  - [DROP] 孤儿自动菜单 {code}')
        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                'DELETE FROM menu_permissions WHERE menu_code=?', (code,))
            if cur.rowcount:
                print(f'  - [DROP] menu_permissions: {code}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v186] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v186] 开始: 采购收货对象模型（M3 第二阶段）')
        _do_tables(conn)
        _do_pos_columns(conn)
        _do_indexes(conn)
        type_ids = _do_types(conn)
        sequence_id = _do_number_sequence(conn)
        _do_type_bindings(conn, type_ids, sequence_id)
        _do_param(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        _do_cleanup_auto_menu(conn)
        conn.commit()
        print('[v186] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v186] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v186 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            RECEIPT_TABLE: ('receipt_no', 'document_type_id', 'receipt_date',
                            'actual_arrival_date', 'source_doc_type', 'source_doc_id',
                            'source_doc_no', 'supplier_party_id',
                            'supplier_delivery_no', 'org_id', 'purchase_org_id',
                            'deliver_to_location_id', 'project_id', 'received_by',
                            'status', 'reversal_of_receipt_id', 'reversed_at',
                            'remark'),
            RECEIPT_LINE_TABLE: ('receipt_id', 'line_no', 'schedule_id',
                                 'source_line_id', 'order_id', 'order_line_id',
                                 'item_id', 'uom_id', 'qty_received',
                                 'qty_rejected', 'rejection_reason_code',
                                 'rejection_disposition', 'lot_no', 'serial_no',
                                 'putaway_location_id', 'status',
                                 'reversal_of_line_id'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v186 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v186 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        if _table_exists(conn, POS_TABLE):
            have = _columns(conn, POS_TABLE)
            for name, _ddl in POS_COLUMNS:
                if name not in have:
                    print(f'[v186 verify] FAIL: 缺列 {POS_TABLE}.{name}')
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v186 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'type_definitions'):
            for code, _name, category, _desc in HEADER_TYPES:
                header_id = _type_id(conn, code, 'header')
                if not header_id:
                    print(f'[v186 verify] FAIL: 缺头类型 {code}')
                    ok = False
                    continue
                row = conn.execute(
                    'SELECT number_sequence_id, document_category '
                    'FROM type_definitions WHERE id=?', (header_id,)).fetchone()
                if not row[0]:
                    print(f'[v186 verify] FAIL: 头类型 {code} 未绑定编号序列')
                    ok = False
                if (row[1] or '') != category:
                    print(f'[v186 verify] FAIL: 头类型 {code} document_category 不符')
                    ok = False

        if _table_exists(conn, 'number_sequences'):
            if not conn.execute(
                'SELECT 1 FROM number_sequences WHERE code=?',
                (NUMBER_SEQUENCE[0],)
            ).fetchone():
                print(f'[v186 verify] FAIL: 缺编号序列 {NUMBER_SEQUENCE[0]}')
                ok = False

        if _table_exists(conn, 'control_parameter_defs'):
            row = conn.execute(
                'SELECT default_value, status FROM control_parameter_defs '
                'WHERE code=?', (PARAM_DEF[0],)).fetchone()
            if not row:
                print(f'[v186 verify] FAIL: 缺控制参数 {PARAM_DEF[0]}')
                ok = False
            elif (row[1] or '') != 'active':
                print(f'[v186 verify] FAIL: 控制参数 {PARAM_DEF[0]} 未启用')
                ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v186 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            root = conn.execute(
                'SELECT is_active FROM menus WHERE menu_code=?', (ROOT_MENU_CODE,)
            ).fetchone()
            if not root or root[0] != 1:
                print(f'[v186 verify] FAIL: 顶层菜单 {ROOT_MENU_CODE} 缺失或未启用')
                ok = False
            for menu in MENUS:
                row = conn.execute(
                    'SELECT is_active, parent_menu, primary_object_type, page_type '
                    'FROM menus WHERE menu_code=?', (menu['menu_code'],)
                ).fetchone()
                if not row:
                    print(f"[v186 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False
                    continue
                if row[0] != 1:
                    print(f"[v186 verify] FAIL: 菜单 {menu['menu_code']} 未启用")
                    ok = False
                if (row[1] or '') != menu['parent_menu']:
                    print(f"[v186 verify] FAIL: 菜单 {menu['menu_code']} 父菜单不符")
                    ok = False
                if (row[2] or '') != menu['primary_object_type']:
                    print(f"[v186 verify] FAIL: 菜单 {menu['menu_code']} primary_object_type")
                    ok = False
                if (row[3] or '') != menu['page_type']:
                    print(f"[v186 verify] FAIL: 菜单 {menu['menu_code']} page_type")
                    ok = False
            if _table_exists(conn, 'menu_permissions'):
                for menu in MENUS:
                    if not conn.execute(
                        'SELECT 1 FROM menu_permissions WHERE menu_code=?',
                        (menu['menu_code'],)
                    ).fetchone():
                        print(f"[v186 verify] FAIL: 缺 menu_permissions {menu['menu_code']}")
                        ok = False

        print('[v186 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v186 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for menu in MENUS:
            if _table_exists(conn, 'menu_permissions'):
                conn.execute(
                    'DELETE FROM menu_permissions WHERE menu_code=?',
                    (menu['menu_code'],))
            if _table_exists(conn, 'menus'):
                conn.execute(
                    'DELETE FROM menus WHERE menu_code=?', (menu['menu_code'],))
        print('  - [DROP] 1 条收货菜单（procurement 容器保留）')

        if _table_exists(conn, 'control_parameter_defs'):
            conn.execute(
                'DELETE FROM control_parameter_defs WHERE code=?', (PARAM_DEF[0],))

        if _table_exists(conn, 'type_definitions'):
            conn.execute(
                'UPDATE type_definitions SET number_sequence_id=NULL '
                'WHERE scope_bo=? AND level=?',
                (SCOPE_BO, 'header'))
            print('  - [UNBIND] 头类型序列')

        if _table_exists(conn, 'number_sequences'):
            conn.execute(
                'DELETE FROM number_sequences WHERE code=?', (NUMBER_SEQUENCE[0],))

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for table in (RECEIPT_LINE_TABLE, RECEIPT_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')

        if _table_exists(conn, POS_TABLE):
            have = _columns(conn, POS_TABLE)
            for name, _ddl in POS_COLUMNS:
                if name not in have:
                    continue
                try:
                    conn.execute(f'ALTER TABLE {POS_TABLE} DROP COLUMN {name}')
                    print(f'  - [DROP] 列 {POS_TABLE}.{name}')
                except sqlite3.OperationalError as e:
                    print(f'  - [WARN] 未删除列 {POS_TABLE}.{name}: {e}')

        conn.commit()
        print('[v186 rollback] 完成（type_definitions / permissions 保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v186 rollback] 失败: {e}')
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
