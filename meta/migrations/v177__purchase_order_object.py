# -*- coding: utf-8 -*-
"""[v177 2026-11-01] 采购订单对象模型（M3 第一阶段）

依据:
  docs/specs/spec-purchase-order-object-model-2026-11-01.md
    §3 头字段 / §4 行字段 / §5 业务类型 / §9 demand_allocation / §10 计划行
    §14 实施清单步骤 5

范围:
  1. 建 4 张表：
       purchase_orders / purchase_order_lines /
       purchase_order_schedules / demand_allocations
     （表由 meta/schemas/{purchase_order,purchase_order_line,
       purchase_order_schedule,demand_allocation}.yaml 声明，
     本迁移做兜底 CREATE + 显式索引，防止仅 sync_schema 漏建）
  2. requisition_lines 补 cost_center_id + 索引（§9.2.1 前置小改）
  3. type_definitions 种子：
       头 PO_STD；行 PO_GOODS / PO_SUBCONTRACT / PO_ASSET /
       PO_SERVICE / PO_EXPENSE / PO_TEXT
  4. number_sequences 种子 PO_STD + 回填头类型的 number_sequence_id /
     default_type_id（行类型不带序列，与销售订单一致）
  5. permissions 双段式 {bo}:{bo}_{action}（4 对象 × 5 动作），
     授予 admin / default 权限集
  6. 菜单：顶层容器 procurement + purchase-order-management
  7. 清理自动生成器可能留下的 *_ -list 孤儿菜单

幂等:
  表 / 列 / 索引 / 类型 / 序列 / 权限 / 菜单先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单 + 丢索引 + 删表；解除类型上的序列绑定后删序列；
  type_definitions 与 permissions 行保留（可能已被单据 / 角色引用）。
"""
import json
import sqlite3
import sys
from pathlib import Path

PO_TABLE = 'purchase_orders'
POL_TABLE = 'purchase_order_lines'
POS_TABLE = 'purchase_order_schedules'
DA_TABLE = 'demand_allocations'

REQ_LINE_TABLE = 'requisition_lines'
REQ_LINE_COLUMN = 'cost_center_id'
REQ_LINE_INDEX = 'idx_requisition_line_cost_center'

SCOPE_BO = 'purchase_order'

#: 头类型 (code, name, document_category, description)
HEADER_TYPE = (
    'PO_STD', '标准采购订单', 'standard',
    '采购订单默认单据类型（编号 / 审批 / 打印等治理语义的挂载点）',
)

#: 行类型 (code, name, line_category, delivery_relevant, description)
LINE_TYPES = (
    ('PO_GOODS', '标准物料行', 'material', 1, '常规物料采购行'),
    ('PO_SUBCONTRACT', '委外加工行', 'subcontract', 1,
     '委外加工费行（组件发料由 component_issue_required 表达）'),
    ('PO_ASSET', '资产采购行', 'asset', 1,
     '固定资产采购行（收货后按 asset_category_code 转固）'),
    ('PO_SERVICE', '服务采购行', 'service', 0,
     '服务采购行（结算由服务验收 / 发票驱动）'),
    ('PO_EXPENSE', '费用采购行', 'expense', 0,
     '费用采购行（直接计入费用科目 / 成本中心）'),
    ('PO_TEXT', '文本行', 'text', 0, '仅说明用途的文本行，无量价'),
)

#: (code, name, pattern, date_field, start_value, on_exhaust, description)
NUMBER_SEQUENCE = (
    'PO_STD', '标准采购订单编号', 'PO-{DATE:yyyymm}-{SEQ:6}', 'order_date', 1,
    'error', '采购订单取号：PO-年月-6 位流水，按月复位',
)

TABLES = (
    (PO_TABLE, """
CREATE TABLE IF NOT EXISTS purchase_orders (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no VARCHAR(200) NOT NULL,
    document_type_id INTEGER,
    order_date DATETIME NOT NULL,
    project_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    supplier_party_id INTEGER NOT NULL,
    supplier_account_id INTEGER,
    supplier_reference_no VARCHAR(200),
    contact_party_id INTEGER,
    contact_name_text VARCHAR(200),
    contact_phone_text VARCHAR(200),
    org_id INTEGER NOT NULL,
    purchase_org_id INTEGER NOT NULL,
    division_code VARCHAR(200),
    deliver_to_location_id INTEGER,
    currency_id INTEGER NOT NULL,
    exchange_rate REAL NOT NULL DEFAULT 1,
    exchange_rate_type VARCHAR(200) NOT NULL DEFAULT 'spot',
    exchange_rate_date DATETIME,
    payment_term_id INTEGER,
    incoterm_code VARCHAR(200),
    requested_date DATETIME,
    confirmed_date DATETIME,
    price_date DATETIME,
    header_discount_percent REAL NOT NULL DEFAULT 0,
    header_surcharge_percent REAL NOT NULL DEFAULT 0,
    header_discount_amount REAL NOT NULL DEFAULT 0,
    header_surcharge_amount REAL NOT NULL DEFAULT 0,
    price_list_id INTEGER,
    pricing_procedure_id INTEGER,
    net_amount REAL NOT NULL DEFAULT 0,
    tax_amount REAL NOT NULL DEFAULT 0,
    gross_amount REAL NOT NULL DEFAULT 0,
    approval_status VARCHAR(200) NOT NULL DEFAULT 'not_required',
    fulfillment_status VARCHAR(200),
    fulfillment_derived_at DATETIME,
    description TEXT,
    revision_no INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (document_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (supplier_party_id) REFERENCES parties(id),
    FOREIGN KEY (supplier_account_id) REFERENCES vendor_accounts(id),
    FOREIGN KEY (contact_party_id) REFERENCES parties(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (purchase_org_id) REFERENCES orgs(id),
    FOREIGN KEY (deliver_to_location_id) REFERENCES locations(id),
    FOREIGN KEY (currency_id) REFERENCES currencies(id),
    FOREIGN KEY (payment_term_id) REFERENCES payment_terms(id),
    FOREIGN KEY (price_list_id) REFERENCES rate_tables(id),
    FOREIGN KEY (pricing_procedure_id) REFERENCES calc_procedures(id)
)
"""),
    (POL_TABLE, """
CREATE TABLE IF NOT EXISTS purchase_order_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    line_no VARCHAR(200) NOT NULL,
    line_type_id INTEGER NOT NULL,
    item_id INTEGER,
    supplier_item_code VARCHAR(200),
    description VARCHAR(200),
    qty REAL NOT NULL,
    uom_id INTEGER,
    unit_price REAL,
    net_amount REAL NOT NULL DEFAULT 0,
    header_discount_amount REAL NOT NULL DEFAULT 0,
    header_surcharge_amount REAL NOT NULL DEFAULT 0,
    tax_code_id INTEGER,
    tax_base_amount REAL NOT NULL DEFAULT 0,
    tax_rate_percent REAL,
    tax_amount REAL NOT NULL DEFAULT 0,
    tax_recoverable INTEGER NOT NULL DEFAULT 1,
    non_recoverable_tax_amount REAL NOT NULL DEFAULT 0,
    gross_amount REAL NOT NULL DEFAULT 0,
    requested_date DATETIME,
    deliver_to_location_id INTEGER,
    service_start_date DATETIME,
    service_end_date DATETIME,
    subcontract_fee_basis VARCHAR(200),
    component_issue_required INTEGER NOT NULL DEFAULT 0,
    asset_category_code VARCHAR(200),
    capitalization_flag INTEGER,
    capitalization_date DATETIME,
    service_acceptance_required INTEGER NOT NULL DEFAULT 1,
    expense_account_code VARCHAR(200),
    cost_center_id INTEGER,
    price_source VARCHAR(200),
    price_trace TEXT,
    sourcing_rule_line_id INTEGER,
    pricing_mode VARCHAR(200) NOT NULL DEFAULT 'standalone',
    parent_line_id INTEGER,
    component_no VARCHAR(200),
    configuration_id INTEGER,
    source_structure_id INTEGER,
    source_structure_line_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'open',
    fulfillment_status VARCHAR(200),
    fulfillment_derived_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY (line_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id),
    FOREIGN KEY (tax_code_id) REFERENCES tax_codes(id),
    FOREIGN KEY (deliver_to_location_id) REFERENCES locations(id),
    FOREIGN KEY (parent_line_id) REFERENCES purchase_order_lines(id),
    FOREIGN KEY (configuration_id) REFERENCES configurations(id),
    FOREIGN KEY (source_structure_id) REFERENCES item_structures(id),
    FOREIGN KEY (source_structure_line_id) REFERENCES item_structure_lines(id)
)
"""),
    (POS_TABLE, """
CREATE TABLE IF NOT EXISTS purchase_order_schedules (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    line_id INTEGER NOT NULL,
    schedule_no INTEGER NOT NULL,
    schedule_kind VARCHAR(200) NOT NULL DEFAULT 'delivery',
    deliver_to_location_id INTEGER,
    promised_date DATETIME NOT NULL,
    promised_qty REAL NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'planned',
    received_qty REAL,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY (line_id) REFERENCES purchase_order_lines(id),
    FOREIGN KEY (deliver_to_location_id) REFERENCES locations(id)
)
"""),
    (DA_TABLE, """
CREATE TABLE IF NOT EXISTS demand_allocations (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demand_bo VARCHAR(200) NOT NULL,
    demand_id INTEGER NOT NULL,
    demand_line_id INTEGER NOT NULL,
    demand_line_no VARCHAR(200),
    demand_need_date DATETIME,
    project_id INTEGER,
    project_task_id INTEGER,
    target_bo VARCHAR(200) NOT NULL,
    target_id INTEGER NOT NULL,
    target_line_id INTEGER NOT NULL,
    target_schedule_id INTEGER,
    qty REAL NOT NULL,
    uom_id INTEGER,
    allocated_amount REAL,
    cost_center_id INTEGER,
    expense_account_code VARCHAR(200),
    asset_category_code VARCHAR(200),
    charge_basis VARCHAR(200) NOT NULL DEFAULT 'inventory',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    reversed_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (uom_id) REFERENCES uoms(id)
)
"""),
)

INDEXES = (
    # ---- purchase_orders ----
    ('uidx_purchase_order_no', PO_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_purchase_order_no '
     'ON purchase_orders(order_no)'),
    ('idx_purchase_order_supplier_date', PO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_supplier_date '
     'ON purchase_orders(supplier_party_id, order_date)'),
    ('idx_purchase_order_purchase_org_date', PO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_purchase_org_date '
     'ON purchase_orders(purchase_org_id, order_date)'),
    ('idx_purchase_order_status', PO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_status '
     'ON purchase_orders(status)'),
    ('idx_purchase_order_approval_status', PO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_approval_status '
     'ON purchase_orders(approval_status)'),
    ('idx_purchase_order_document_type', PO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_document_type '
     'ON purchase_orders(document_type_id)'),
    ('idx_purchase_order_project', PO_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_project '
     'ON purchase_orders(project_id)'),

    # ---- purchase_order_lines ----
    ('uidx_purchase_order_line_no', POL_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_purchase_order_line_no '
     'ON purchase_order_lines(order_id, line_no)'),
    ('idx_purchase_order_line_item', POL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_line_item '
     'ON purchase_order_lines(item_id)'),
    ('idx_purchase_order_line_order_status', POL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_line_order_status '
     'ON purchase_order_lines(order_id, status)'),
    ('idx_purchase_order_line_sourcing', POL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_line_sourcing '
     'ON purchase_order_lines(sourcing_rule_line_id)'),
    ('idx_purchase_order_line_parent', POL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_line_parent '
     'ON purchase_order_lines(parent_line_id)'),
    # 同一父行内组件号唯一；未成套行不参与
    ('uidx_purchase_order_line_component', POL_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_purchase_order_line_component '
     'ON purchase_order_lines(parent_line_id, component_no) '
     'WHERE parent_line_id IS NOT NULL AND component_no IS NOT NULL'),
    ('idx_purchase_order_line_source_structure', POL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_order_line_source_structure '
     'ON purchase_order_lines(source_structure_line_id)'),

    # ---- purchase_order_schedules ----
    ('uidx_po_schedule_line_kind_no', POS_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_po_schedule_line_kind_no '
     'ON purchase_order_schedules(line_id, schedule_kind, schedule_no)'),
    ('idx_po_schedule_order', POS_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_po_schedule_order '
     'ON purchase_order_schedules(order_id)'),
    ('idx_po_schedule_line', POS_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_po_schedule_line '
     'ON purchase_order_schedules(line_id)'),
    ('idx_po_schedule_promised_date', POS_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_po_schedule_promised_date '
     'ON purchase_order_schedules(promised_date)'),
    ('idx_po_schedule_location', POS_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_po_schedule_location '
     'ON purchase_order_schedules(deliver_to_location_id)'),

    # ---- demand_allocations ----
    # SQLite 唯一索引对 NULL 不去重，按 target_schedule_id 是否为空拆两条
    # partial unique（等价 spec 的「无计划层按 0」口径）
    ('uidx_demand_alloc_target', DA_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_demand_alloc_target '
     'ON demand_allocations(demand_bo, demand_line_id, target_bo, target_line_id) '
     'WHERE target_schedule_id IS NULL'),
    ('uidx_demand_alloc_target_schedule', DA_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_demand_alloc_target_schedule '
     'ON demand_allocations'
     '(demand_bo, demand_line_id, target_bo, target_line_id, target_schedule_id) '
     'WHERE target_schedule_id IS NOT NULL'),
    ('idx_demand_alloc_target_line', DA_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_demand_alloc_target_line '
     'ON demand_allocations(target_bo, target_line_id)'),
    ('idx_demand_alloc_target_schedule', DA_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_demand_alloc_target_schedule '
     'ON demand_allocations(target_bo, target_schedule_id)'),
    ('idx_demand_alloc_demand', DA_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_demand_alloc_demand '
     'ON demand_allocations(demand_bo, demand_id)'),
    ('idx_demand_alloc_project', DA_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_demand_alloc_project '
     'ON demand_allocations(project_id, project_task_id)'),
    ('idx_demand_alloc_cost', DA_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_demand_alloc_cost '
     'ON demand_allocations(cost_center_id, expense_account_code)'),
)

ACTIONS = ('create', 'read', 'update', 'delete', 'list')
_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}
OBJECTS = (
    ('purchase_order', '采购订单'),
    ('purchase_order_line', '采购订单行'),
    ('purchase_order_schedule', '采购订单计划行'),
    ('demand_allocation', '需求分配'),
)

#: 审批决策动作权限（spec §6.3 / §14 步骤 13；双段式与列表动作一致）
APPROVAL_PERMISSIONS = (
    ('purchase_order:purchase_order_approve', '采购订单审批',
     'purchase_order', 'approve'),
    ('purchase_order:purchase_order_reject', '采购订单驳回',
     'purchase_order', 'reject'),
)

PERMISSIONS = tuple(
    ('{0}:{0}_{1}'.format(bo, action),
     '{0}{1}'.format(label, _ACTION_LABEL[action]), bo, action)
    for bo, label in OBJECTS
    for action in ACTIONS
) + APPROVAL_PERMISSIONS

GRANT_TO_SETS = ('admin', 'default')

ROOT_MENU_CODE = 'procurement'
ORDER_MENU_CODE = 'purchase-order-management'

MENUS = (
    {
        # 顶层分组容器：无页面、无路径，仅承载子菜单
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
    },
    {
        'menu_code': ORDER_MENU_CODE,
        'menu_name': '采购订单',
        'menu_path': '/purchase-orders',
        'page_type': 'object_list',
        'primary_object_type': 'purchase_order',
        'object_types': ['purchase_order'],
        'bo_bindings': [
            {'bo_id': 'purchase_order', 'role': 'primary', 'include_actions': list(ACTIONS)},
        ],
        'required_permissions': [
            'purchase_order:purchase_order_{0}'.format(a) for a in ACTIONS],
        'parent_menu': ROOT_MENU_CODE,
        'icon': 'List',
        'color': '#0ea5e9',
        'description': '采购订单：抬头 + 行 / 计划行子表，按采购组织做数据范围',
        'sort_order': 1,
        'show_in_sidebar': 0,
        'data_permission_hint': {
            'resource_types': ['purchase_order'],
            'message': '建议分配采购订单数据权限（按采购组织）',
        },
    },
)

_ORPHAN_MENU_CODES = (
    'purchase_order-list',
    'purchase_order_line-list',
    'purchase_order_schedule-list',
    'demand_allocation-list',
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


def _do_requisition_line_column(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, REQ_LINE_TABLE):
        print(f'  - [SKIP] 表 {REQ_LINE_TABLE} 不存在（由 v168 / sync_schema 创建）')
        return
    if REQ_LINE_COLUMN in _columns(conn, REQ_LINE_TABLE):
        print(f'  - [SKIP] 列 {REQ_LINE_TABLE}.{REQ_LINE_COLUMN} 已存在')
    else:
        conn.execute(
            f'ALTER TABLE {REQ_LINE_TABLE} ADD COLUMN {REQ_LINE_COLUMN} INTEGER NULL')
        print(f'  - [ALTER] 列 {REQ_LINE_TABLE}.{REQ_LINE_COLUMN}')


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, table, sql in INDEXES:
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
            continue
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 索引 {name} 依赖表 {table} 不存在')
            continue
        try:
            conn.execute(sql)
            print(f'  - [ADD] 索引 {name}')
        except sqlite3.IntegrityError as e:
            print(f'  - [FAIL] 索引 {name}: {e}')
            raise

    if _index_exists(conn, REQ_LINE_INDEX):
        print(f'  - [SKIP] 索引 {REQ_LINE_INDEX} 已存在')
    elif not _table_exists(conn, REQ_LINE_TABLE) \
            or REQ_LINE_COLUMN not in _columns(conn, REQ_LINE_TABLE):
        print(f'  - [SKIP] 索引 {REQ_LINE_INDEX} 依赖列缺失')
    else:
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS {REQ_LINE_INDEX} '
            f'ON {REQ_LINE_TABLE}({REQ_LINE_COLUMN})')
        print(f'  - [ADD] 索引 {REQ_LINE_INDEX}')


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
    for code, name, line_category, delivery_relevant, desc in LINE_TYPES:
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
    goods_id = type_ids.get('PO_GOODS')

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


def _do_menus(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return
    for menu in MENUS:
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
        print(f'[v177] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v177] 开始: 采购订单对象模型（M3 第一阶段）')
        _do_tables(conn)
        _do_requisition_line_column(conn)
        _do_indexes(conn)
        type_ids = _do_types(conn)
        sequence_id = _do_number_sequence(conn)
        _do_type_bindings(conn, type_ids, sequence_id)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        _do_cleanup_auto_menu(conn)
        conn.commit()
        print('[v177] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v177] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v177 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            PO_TABLE: ('order_no', 'document_type_id', 'order_date', 'status',
                       'supplier_party_id', 'supplier_account_id', 'org_id',
                       'purchase_org_id', 'currency_id', 'exchange_rate',
                       'net_amount', 'tax_amount', 'gross_amount',
                       'approval_status', 'fulfillment_status', 'revision_no'),
            POL_TABLE: ('order_id', 'line_no', 'line_type_id', 'item_id', 'qty',
                        'uom_id', 'unit_price', 'net_amount', 'tax_code_id',
                        'tax_amount', 'gross_amount', 'pricing_mode',
                        'parent_line_id', 'component_no', 'status'),
            POS_TABLE: ('order_id', 'line_id', 'schedule_no', 'schedule_kind',
                        'promised_date', 'promised_qty', 'status', 'received_qty'),
            DA_TABLE: ('demand_bo', 'demand_id', 'demand_line_id', 'project_id',
                       'project_task_id', 'target_bo', 'target_id',
                       'target_line_id', 'target_schedule_id', 'qty', 'uom_id',
                       'allocated_amount', 'cost_center_id', 'charge_basis',
                       'status', 'reversed_at'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v177 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v177 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v177 verify] FAIL: 缺索引 {name}')
                ok = False

        if not _index_exists(conn, REQ_LINE_INDEX):
            print(f'[v177 verify] FAIL: 缺索引 {REQ_LINE_INDEX}')
            ok = False
        if _table_exists(conn, REQ_LINE_TABLE):
            if REQ_LINE_COLUMN not in _columns(conn, REQ_LINE_TABLE):
                print(f'[v177 verify] FAIL: 缺列 {REQ_LINE_TABLE}.{REQ_LINE_COLUMN}')
                ok = False

        if _table_exists(conn, 'type_definitions'):
            header_id = _type_id(conn, HEADER_TYPE[0], 'header')
            if not header_id:
                print(f'[v177 verify] FAIL: 缺头类型 {HEADER_TYPE[0]}')
                ok = False
            else:
                row = conn.execute(
                    'SELECT number_sequence_id, default_type_id, document_category '
                    'FROM type_definitions WHERE id=?', (header_id,)).fetchone()
                if not row[0]:
                    print('[v177 verify] FAIL: 头类型未绑定编号序列')
                    ok = False
                if not row[1]:
                    print('[v177 verify] FAIL: 头类型未绑定默认行类型')
                    ok = False
                if (row[2] or '') != HEADER_TYPE[2]:
                    print('[v177 verify] FAIL: 头类型 document_category 不符')
                    ok = False
            for code, _name, line_category, _rel, _desc in LINE_TYPES:
                if not _type_id(conn, code, 'line'):
                    print(f'[v177 verify] FAIL: 缺行类型 {code}')
                    ok = False
                    continue
                row = conn.execute(
                    'SELECT line_category FROM type_definitions '
                    'WHERE scope_bo=? AND level=? AND code=?',
                    (SCOPE_BO, 'line', code)).fetchone()
                if (row[0] or '') != line_category:
                    print(f'[v177 verify] FAIL: 行类型 {code} line_category 不符')
                    ok = False

        if _table_exists(conn, 'number_sequences'):
            if not conn.execute(
                'SELECT 1 FROM number_sequences WHERE code=?',
                (NUMBER_SEQUENCE[0],)
            ).fetchone():
                print(f'[v177 verify] FAIL: 缺编号序列 {NUMBER_SEQUENCE[0]}')
                ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v177 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                row = conn.execute(
                    'SELECT is_active, parent_menu, primary_object_type, page_type '
                    'FROM menus WHERE menu_code=?', (menu['menu_code'],)
                ).fetchone()
                if not row:
                    print(f"[v177 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False
                    continue
                if row[0] != 1:
                    print(f"[v177 verify] FAIL: 菜单 {menu['menu_code']} 未启用")
                    ok = False
                if (row[1] or '') != menu['parent_menu']:
                    print(f"[v177 verify] FAIL: 菜单 {menu['menu_code']} 父菜单不符")
                    ok = False
                if (row[2] or '') != menu['primary_object_type']:
                    print(f"[v177 verify] FAIL: 菜单 {menu['menu_code']} primary_object_type")
                    ok = False
                if (row[3] or '') != menu['page_type']:
                    print(f"[v177 verify] FAIL: 菜单 {menu['menu_code']} page_type")
                    ok = False

        print('[v177 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v177 rollback] DB 不存在: {db_path}')
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
        print('  - [DROP] 2 条采购域菜单')

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
        if _index_exists(conn, REQ_LINE_INDEX):
            conn.execute(f'DROP INDEX IF EXISTS {REQ_LINE_INDEX}')

        for table in (DA_TABLE, POS_TABLE, POL_TABLE, PO_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')

        if _table_exists(conn, REQ_LINE_TABLE):
            cols = _columns(conn, REQ_LINE_TABLE)
            if REQ_LINE_COLUMN in cols:
                # SQLite 不支持 DROP COLUMN 之前的旧版本会失败；失败即保留列
                try:
                    conn.execute(
                        f'ALTER TABLE {REQ_LINE_TABLE} DROP COLUMN {REQ_LINE_COLUMN}')
                    print(f'  - [DROP] 列 {REQ_LINE_TABLE}.{REQ_LINE_COLUMN}')
                except sqlite3.OperationalError as e:
                    print(f'  - [WARN] 未删除列 {REQ_LINE_TABLE}.{REQ_LINE_COLUMN}: {e}')

        conn.commit()
        print('[v177 rollback] 完成（type_definitions / permissions 保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v177 rollback] 失败: {e}')
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
