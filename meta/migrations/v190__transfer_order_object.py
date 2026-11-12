# -*- coding: utf-8 -*-
"""[v190 2026-11-02] 调拨单对象模型（M4 内部供应）

依据:
  docs/specs/spec-transfer-order-object-model-2026-11-02.md
    §3.1 头字段 / §3.2 行字段 / §3.3 索引
    §4 类型与编号 / §9 权限与菜单 / §10 服务层不变量

范围:
  1. 建 2 张表：transfer_orders / transfer_order_lines
     （表由 meta/schemas/{transfer_order,transfer_order_line}.yaml 声明，
     本迁移做兜底 CREATE + 显式索引，防止仅 sync_schema 漏建）
  2. type_definitions 种子：
       头类型 TRF_STD（standard）；行类型 TRF_GOODS（material，delivery_relevant=1）
  3. number_sequences 种子 TRF + 回填头类型的 number_sequence_id /
     default_type_id（行类型不带序列）
  4. permissions 双段式 {bo}:{bo}_{action}（transfer_order 10 动作），
     授予 admin / default 权限集
  5. 菜单：顶层容器 procurement（若缺则补建）+ transfer-order-management → /transfer-orders
  6. 清理自动生成器可能留下的 *-list 孤儿菜单

幂等:
  表 / 索引 / 类型 / 序列 / 权限 / 菜单先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单 + 丢索引 + 删表；解除类型序列 / 默认行类型绑定后删序列；
  type_definitions 与 permissions 行保留（可能已被单据 / 角色引用）。
"""
import json
import sqlite3
import sys
from pathlib import Path

TO_TABLE = 'transfer_orders'
TOL_TABLE = 'transfer_order_lines'

SCOPE_BO = 'transfer_order'

#: 头类型 (code, name, document_category, description)
HEADER_TYPE = (
    'TRF_STD', '标准调拨单', 'standard',
    '同法人不同库存组织之间的内部调拨单据类型',
)

#: 行类型 (code, name, line_category, delivery_relevant, description)
LINE_TYPE = (
    'TRF_GOODS', '标准物料行', 'material', 1,
    '可发货、可收货的实物物料行',
)

#: (code, name, pattern, date_field, start_value, on_exhaust, description)
NUMBER_SEQUENCE = (
    'TRF', '调拨单编号', 'TRF-{DATE:yyyymm}-{SEQ:6}', 'transfer_date', 1,
    'error', '调拨单取号：TRF-年月-6 位流水，按年度重置',
)

TABLES = (
    (TO_TABLE, """
CREATE TABLE IF NOT EXISTS transfer_orders (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_order_no VARCHAR(30) NOT NULL UNIQUE,
    document_type_id INTEGER,
    transfer_date DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    fulfillment_status VARCHAR(30),
    from_org_id INTEGER NOT NULL,
    to_org_id INTEGER NOT NULL,
    legal_entity_id INTEGER NOT NULL,
    from_location_id INTEGER,
    to_location_id INTEGER,
    project_id INTEGER,
    actual_ship_date DATETIME,
    carrier_name VARCHAR(100),
    waybill_no VARCHAR(50),
    remark TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (document_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (from_org_id) REFERENCES orgs(id),
    FOREIGN KEY (to_org_id) REFERENCES orgs(id),
    FOREIGN KEY (legal_entity_id) REFERENCES orgs(id),
    FOREIGN KEY (from_location_id) REFERENCES locations(id),
    FOREIGN KEY (to_location_id) REFERENCES locations(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    CHECK (status IN ('draft', 'released', 'closed', 'cancelled')),
    CHECK (fulfillment_status IS NULL OR fulfillment_status IN
           ('open', 'partially_shipped', 'shipped', 'partially_received', 'received'))
)
"""),
    (TOL_TABLE, """
CREATE TABLE IF NOT EXISTS transfer_order_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_order_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    line_type_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    uom_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    qty_shipped REAL NOT NULL DEFAULT 0,
    qty_received REAL NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    fulfillment_status VARCHAR(30),
    remark TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (transfer_order_id) REFERENCES transfer_orders(id),
    FOREIGN KEY (line_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id),
    UNIQUE (transfer_order_id, line_no),
    CHECK (qty > 0),
    CHECK (status IN ('open', 'closed', 'cancelled')),
    CHECK (fulfillment_status IS NULL OR fulfillment_status IN
           ('open', 'partially_shipped', 'shipped', 'partially_received', 'received'))
)
"""),
)

#: 索引名按 spec §3.3 逐字声明（唯一约束由表级 UNIQUE 承担）
INDEXES = (
    # ---- transfer_orders ----
    ('idx_transfer_order_type', TO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_type '
     'ON transfer_orders(document_type_id)'),
    ('idx_transfer_order_date', TO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_date '
     'ON transfer_orders(transfer_date)'),
    ('idx_transfer_order_from_org', TO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_from_org '
     'ON transfer_orders(from_org_id)'),
    ('idx_transfer_order_to_org', TO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_to_org '
     'ON transfer_orders(to_org_id)'),
    ('idx_transfer_order_project', TO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_project '
     'ON transfer_orders(project_id)'),
    ('idx_transfer_order_status', TO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_status '
     'ON transfer_orders(status)'),

    # ---- transfer_order_lines ----
    ('idx_transfer_order_line_order', TOL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_line_order '
     'ON transfer_order_lines(transfer_order_id)'),
    ('idx_transfer_order_line_item', TOL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_line_item '
     'ON transfer_order_lines(item_id)'),
    ('idx_transfer_order_line_type', TOL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_transfer_order_line_type '
     'ON transfer_order_lines(line_type_id)'),
)

ACTIONS = ('create', 'read', 'update', 'delete', 'list')
_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

#: 单据动作权限（spec §9.1：下达 / 发货 / 收货 / 取消 / 关闭，双段式）
DOC_PERMISSIONS = (
    ('transfer_order:transfer_order_release', '调拨单下达',
     'transfer_order', 'release'),
    ('transfer_order:transfer_order_ship', '调拨单发货',
     'transfer_order', 'ship'),
    ('transfer_order:transfer_order_receive', '调拨单收货',
     'transfer_order', 'receive'),
    ('transfer_order:transfer_order_cancel', '调拨单取消',
     'transfer_order', 'cancel'),
    ('transfer_order:transfer_order_close', '调拨单关闭',
     'transfer_order', 'close'),
)

PERMISSIONS = tuple(
    ('transfer_order:transfer_order_{0}'.format(action),
     '调拨单{0}'.format(_ACTION_LABEL[action]), 'transfer_order', action)
    for action in ACTIONS
) + DOC_PERMISSIONS

GRANT_TO_SETS = ('admin', 'default')

ROOT_MENU_CODE = 'procurement'
TRANSFER_MENU_CODE = 'transfer-order-management'

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
        'menu_code': TRANSFER_MENU_CODE,
        'menu_name': '调拨单',
        'menu_path': '/transfer-orders',
        'page_type': 'object_list',
        'primary_object_type': 'transfer_order',
        'object_types': ['transfer_order'],
        'bo_bindings': [
            {'bo_id': 'transfer_order', 'role': 'primary',
             'include_actions': list(ACTIONS)},
        ],
        'required_permissions': [
            'transfer_order:transfer_order_{0}'.format(a) for a in ACTIONS],
        'parent_menu': ROOT_MENU_CODE,
        'icon': 'Truck',
        'color': '#0ea5e9',
        'description': '调拨单：抬头 + 调拨行子表，按调出组织做数据范围',
        'sort_order': 3,
        'show_in_sidebar': 0,
        'data_permission_hint': {
            'resource_types': ['transfer_order'],
            'message': '建议分配调拨单数据权限（按调出组织，调入组织作附加过滤）',
        },
    },
)

_ORPHAN_MENU_CODES = (
    'transfer_order-list',
    'transfer_order_line-list',
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


def _ensure_type(conn: sqlite3.Connection, code: str, name: str, level: str,
                 document_category, line_category, delivery_relevant,
                 description: str) -> int:
    existing = _type_id(conn, code, level)
    if existing:
        print(f'  - [SKIP] 类型 {SCOPE_BO}/{level}/{code} 已存在 (id={existing})')
        return int(existing)

    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    if level == 'header':
        cur = conn.execute(
            'INSERT INTO type_definitions '
            '(code, name, scope_bo, level, document_category, status, description, '
            ' created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (code, name, SCOPE_BO, level, document_category, 'active', description, now))
    else:
        cur = conn.execute(
            'INSERT INTO type_definitions '
            '(code, name, scope_bo, level, line_category, delivery_relevant, '
            ' status, description, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (code, name, SCOPE_BO, level, line_category, delivery_relevant,
             'active', description, now))
    new_id = int(cur.lastrowid)
    print(f'  - [NEW] 类型 {SCOPE_BO}/{level}/{code} (id={new_id})')
    return new_id


def _do_types(conn: sqlite3.Connection) -> dict:
    if not _table_exists(conn, 'type_definitions'):
        print('  - type_definitions 表不存在, 跳过类型种子')
        return {}
    ids = {'header': _ensure_type(
        conn, HEADER_TYPE[0], HEADER_TYPE[1], 'header', HEADER_TYPE[2],
        None, 1, HEADER_TYPE[3])}
    code, name, line_category, delivery_relevant, desc = LINE_TYPE
    ids[code] = _ensure_type(
        conn, code, name, 'line', None, line_category, delivery_relevant, desc)
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


def _do_type_bindings(conn: sqlite3.Connection, type_ids: dict,
                      sequence_id) -> None:
    if not _table_exists(conn, 'type_definitions'):
        return
    header_id = type_ids.get('header')
    goods_id = type_ids.get('TRF_GOODS')

    if header_id and sequence_id:
        row = conn.execute(
            'SELECT number_sequence_id FROM type_definitions WHERE id=?',
            (header_id,)).fetchone()
        if row and row[0]:
            print(f'  - [SKIP] 头类型 number_sequence_id 已绑定 (id={row[0]})')
        else:
            conn.execute(
                'UPDATE type_definitions SET number_sequence_id=? WHERE id=?',
                (sequence_id, header_id))
            print(f'  - [BIND] 头类型 → 编号序列 id={sequence_id}')

    if header_id and goods_id:
        row = conn.execute(
            'SELECT default_type_id FROM type_definitions WHERE id=?',
            (header_id,)).fetchone()
        if row and row[0]:
            print(f'  - [SKIP] 头类型 default_type_id 已绑定 (id={row[0]})')
        else:
            conn.execute(
                'UPDATE type_definitions SET default_type_id=? WHERE id=?',
                (goods_id, header_id))
            print(f'  - [BIND] 头类型 → 默认行类型 id={goods_id}')


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
        print(f'[v190] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v190] 开始: 调拨单对象模型（M4 内部供应）')
        _do_tables(conn)
        _do_indexes(conn)
        type_ids = _do_types(conn)
        sequence_id = _do_number_sequence(conn)
        _do_type_bindings(conn, type_ids, sequence_id)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        _do_cleanup_auto_menu(conn)
        conn.commit()
        print('[v190] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v190] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v190 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            TO_TABLE: ('transfer_order_no', 'document_type_id', 'transfer_date',
                       'status', 'fulfillment_status', 'from_org_id', 'to_org_id',
                       'legal_entity_id', 'from_location_id', 'to_location_id',
                       'project_id', 'actual_ship_date', 'carrier_name',
                       'waybill_no', 'remark'),
            TOL_TABLE: ('transfer_order_id', 'line_no', 'line_type_id', 'item_id',
                        'uom_id', 'qty', 'qty_shipped', 'qty_received', 'status',
                        'fulfillment_status', 'remark'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v190 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v190 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v190 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'type_definitions'):
            header_id = _type_id(conn, HEADER_TYPE[0], 'header')
            if not header_id:
                print(f'[v190 verify] FAIL: 缺头类型 {HEADER_TYPE[0]}')
                ok = False
            else:
                row = conn.execute(
                    'SELECT number_sequence_id, default_type_id, document_category, '
                    'status FROM type_definitions WHERE id=?', (header_id,)).fetchone()
                if not row[0]:
                    print('[v190 verify] FAIL: 头类型未绑定编号序列')
                    ok = False
                if not row[1]:
                    print('[v190 verify] FAIL: 头类型未绑定默认行类型')
                    ok = False
                if (row[2] or '') != HEADER_TYPE[2]:
                    print('[v190 verify] FAIL: 头类型 document_category 不符')
                    ok = False
                if (row[3] or '') != 'active':
                    print('[v190 verify] FAIL: 头类型未启用')
                    ok = False

            line_code = LINE_TYPE[0]
            line_id = _type_id(conn, line_code, 'line')
            if not line_id:
                print(f'[v190 verify] FAIL: 缺行类型 {line_code}')
                ok = False
            else:
                row = conn.execute(
                    'SELECT line_category, delivery_relevant, status '
                    'FROM type_definitions WHERE id=?', (line_id,)).fetchone()
                if (row[0] or '') != LINE_TYPE[2]:
                    print(f'[v190 verify] FAIL: 行类型 {line_code} line_category 不符')
                    ok = False
                if int(row[1] or 0) != LINE_TYPE[3]:
                    print(
                        f'[v190 verify] FAIL: 行类型 {line_code} delivery_relevant 不符')
                    ok = False
                if (row[2] or '') != 'active':
                    print(f'[v190 verify] FAIL: 行类型 {line_code} 未启用')
                    ok = False

        if _table_exists(conn, 'number_sequences'):
            row = conn.execute(
                'SELECT pattern, date_field, on_exhaust, status '
                'FROM number_sequences WHERE code=?', (NUMBER_SEQUENCE[0],)
            ).fetchone()
            if not row:
                print(f'[v190 verify] FAIL: 缺编号序列 {NUMBER_SEQUENCE[0]}')
                ok = False
            else:
                if (row[0] or '') != NUMBER_SEQUENCE[2]:
                    print('[v190 verify] FAIL: 编号序列 pattern 不符')
                    ok = False
                if (row[1] or '') != NUMBER_SEQUENCE[3]:
                    print('[v190 verify] FAIL: 编号序列 date_field 不符')
                    ok = False
                if (row[2] or '') != NUMBER_SEQUENCE[5]:
                    print('[v190 verify] FAIL: 编号序列 on_exhaust 不符')
                    ok = False
                if (row[3] or '') != 'active':
                    print('[v190 verify] FAIL: 编号序列未启用')
                    ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v190 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            root = conn.execute(
                'SELECT is_active FROM menus WHERE menu_code=?', (ROOT_MENU_CODE,)
            ).fetchone()
            if not root or root[0] != 1:
                print(f'[v190 verify] FAIL: 顶层菜单 {ROOT_MENU_CODE} 缺失或未启用')
                ok = False
            for menu in MENUS:
                row = conn.execute(
                    'SELECT is_active, parent_menu, primary_object_type, page_type, '
                    'sort_order, bo_bindings FROM menus WHERE menu_code=?',
                    (menu['menu_code'],)
                ).fetchone()
                if not row:
                    print(f"[v190 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False
                    continue
                if row[0] != 1:
                    print(f"[v190 verify] FAIL: 菜单 {menu['menu_code']} 未启用")
                    ok = False
                if (row[1] or '') != menu['parent_menu']:
                    print(f"[v190 verify] FAIL: 菜单 {menu['menu_code']} 父菜单不符")
                    ok = False
                if (row[2] or '') != menu['primary_object_type']:
                    print(f"[v190 verify] FAIL: 菜单 {menu['menu_code']} primary_object_type")
                    ok = False
                if (row[3] or '') != menu['page_type']:
                    print(f"[v190 verify] FAIL: 菜单 {menu['menu_code']} page_type")
                    ok = False
                if int(row[4] or 0) != menu['sort_order']:
                    print(f"[v190 verify] FAIL: 菜单 {menu['menu_code']} sort_order")
                    ok = False
                try:
                    bindings = json.loads(row[5] or '[]')
                except (TypeError, ValueError):
                    bindings = []
                actions = set()
                for binding in bindings:
                    if binding.get('bo_id') == 'transfer_order':
                        actions = set(binding.get('include_actions') or [])
                if set(ACTIONS) - actions:
                    print(f"[v190 verify] FAIL: 菜单 {menu['menu_code']} bo_bindings 缺 CRUD")
                    ok = False
            if _table_exists(conn, 'menu_permissions'):
                for menu in MENUS:
                    if not conn.execute(
                        'SELECT 1 FROM menu_permissions WHERE menu_code=?',
                        (menu['menu_code'],)
                    ).fetchone():
                        print(f"[v190 verify] FAIL: 缺 menu_permissions {menu['menu_code']}")
                        ok = False

        print('[v190 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v190 rollback] DB 不存在: {db_path}')
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
        print('  - [DROP] 1 条调拨菜单（procurement 容器保留）')

        if _table_exists(conn, 'type_definitions'):
            conn.execute(
                'UPDATE type_definitions SET number_sequence_id=NULL, '
                'default_type_id=NULL WHERE scope_bo=? AND level=?',
                (SCOPE_BO, 'header'))
            print('  - [UNBIND] 头类型序列 / 默认行类型')

        if _table_exists(conn, 'number_sequences'):
            conn.execute(
                'DELETE FROM number_sequences WHERE code=?', (NUMBER_SEQUENCE[0],))

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for table in (TOL_TABLE, TO_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')

        conn.commit()
        print('[v190 rollback] 完成（type_definitions / permissions 保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v190 rollback] 失败: {e}')
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
