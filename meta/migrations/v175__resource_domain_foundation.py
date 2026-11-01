# -*- coding: utf-8 -*-
"""[v175 2026-11-01] 统一资源模型地基（P2a）

依据:
  docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
    §FR-001 ~ FR-004 / §FR-007 / §FR-011 / §TR-001 / §9.3
  docs/specs/spec-resource-model-benchmark-oracle-sap-2026-11-01.md
    §6.2 对象清单 / §7 P2a

设计:
  · 6 张表由 `meta/schemas/{skill,resource,resource_group,
    resource_group_member,resource_capability,resource_rate}.yaml` 声明，
    sync_schema 生成；本迁移做「断言 + 兜底 CREATE + 补索引 + 枚举种子 +
    权限 + 菜单 + work_order_operations 列改名/加列」。
  · `work_order_operations.work_center_id → resource_group_id`（当前无数据，
    直接 RENAME）；新增 `required_skill_id`（skill 引用，可空）与
    `teardown_minutes`（默认 0）。旧列 `required_skill` 保留只读。
  · 6 条菜单挂在现有「主数据」父菜单（menu_code='master-data'）；
    父节点不存在时退回顶层（parent_menu=''）并打印说明。
  · 权限码为双段式 `{bo}:{bo}_{action}`，授予 admin / default 权限集。

幂等:
  表 / 列 / 索引 / 枚举 / 菜单 / 权限 / 授权先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单 + 丢索引 + 删表；列名改回 work_center_id（新增列保留）；
  permissions 与枚举种子保留（可能已被角色授予 / 被其他对象引用）。
"""
import json
import sqlite3
import sys
from pathlib import Path

SKILL_TABLE = 'skills'
RESOURCE_TABLE = 'resources'
GROUP_TABLE = 'resource_groups'
MEMBER_TABLE = 'resource_group_members'
CAPABILITY_TABLE = 'resource_capabilities'
RATE_TABLE = 'resource_rates'
OPERATIONS_TABLE = 'work_order_operations'

PARENT_MENU = 'master-data'

TABLES = (
    (SKILL_TABLE, """
CREATE TABLE IF NOT EXISTS skills (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(200) NOT NULL DEFAULT 'trade',
    parent_id INTEGER,
    requires_certification INTEGER NOT NULL DEFAULT 0,
    default_validity_months INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (parent_id) REFERENCES skills(id)
)
"""),
    (RESOURCE_TABLE, """
CREATE TABLE IF NOT EXISTS resources (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    resource_kind VARCHAR(200) NOT NULL DEFAULT 'person',
    resource_role VARCHAR(200),
    org_id INTEGER,
    location_id INTEGER,
    cost_center_id INTEGER,
    party_id INTEGER,
    person_ref INTEGER,
    capacity_uom_id INTEGER,
    capacity_per_day REAL,
    capacity_units REAL NOT NULL DEFAULT 1,
    utilization_pct REAL NOT NULL DEFAULT 100,
    calendar_id INTEGER,
    timezone VARCHAR(200),
    is_active INTEGER NOT NULL DEFAULT 1,
    valid_from DATETIME,
    valid_to DATETIME,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (party_id) REFERENCES parties(id),
    FOREIGN KEY (person_ref) REFERENCES person_profiles(id),
    FOREIGN KEY (capacity_uom_id) REFERENCES uoms(id),
    FOREIGN KEY (calendar_id) REFERENCES calendars(id)
)
"""),
    (GROUP_TABLE, """
CREATE TABLE IF NOT EXISTS resource_groups (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    group_kind VARCHAR(200) NOT NULL DEFAULT 'work_center',
    org_id INTEGER,
    org_unit_id INTEGER,
    location_id INTEGER,
    calendar_id INTEGER,
    cost_center_id INTEGER,
    capacity_aggregation VARCHAR(200) NOT NULL DEFAULT 'sum',
    membership_mode VARCHAR(200) NOT NULL DEFAULT 'members',
    parent_group_id INTEGER,
    is_bottleneck INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    valid_from DATETIME,
    valid_to DATETIME,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (parent_group_id) REFERENCES resource_groups(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (org_unit_id) REFERENCES orgs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (calendar_id) REFERENCES calendars(id)
)
"""),
    (MEMBER_TABLE, """
CREATE TABLE IF NOT EXISTS resource_group_members (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    role VARCHAR(200),
    priority INTEGER DEFAULT 0,
    allocation_pct REAL NOT NULL DEFAULT 100,
    quantity REAL NOT NULL DEFAULT 1,
    valid_from DATETIME,
    valid_to DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (group_id) REFERENCES resource_groups(id),
    FOREIGN KEY (resource_id) REFERENCES resources(id)
)
"""),
    (CAPABILITY_TABLE, """
CREATE TABLE IF NOT EXISTS resource_capabilities (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME,
    certification_ref VARCHAR(200),
    verified_by VARCHAR(200),
    verified_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (resource_id) REFERENCES resources(id),
    FOREIGN KEY (skill_id) REFERENCES skills(id)
)
"""),
    (RATE_TABLE, """
CREATE TABLE IF NOT EXISTS resource_rates (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER,
    resource_group_id INTEGER,
    rate_purpose VARCHAR(200) NOT NULL DEFAULT 'cost',
    rate_basis VARCHAR(200) NOT NULL DEFAULT 'per_hour',
    org_id INTEGER,
    location_id INTEGER,
    currency_id INTEGER,
    rate REAL NOT NULL,
    rate_uom_id INTEGER,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME,
    priority INTEGER NOT NULL DEFAULT 0,
    rate_source VARCHAR(200) NOT NULL DEFAULT 'internal',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (resource_id) REFERENCES resources(id),
    FOREIGN KEY (resource_group_id) REFERENCES resource_groups(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (currency_id) REFERENCES currencies(id),
    FOREIGN KEY (rate_uom_id) REFERENCES uoms(id)
)
"""),
)

INDEXES = (
    ('uq_skill_code', SKILL_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_code ON skills(code)'),
    ('idx_skill_parent', SKILL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_skill_parent ON skills(parent_id)'),
    ('idx_skill_category', SKILL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_skill_category ON skills(category)'),
    ('idx_skill_status', SKILL_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_skill_status ON skills(status)'),

    ('uq_resource_code', RESOURCE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_code ON resources(code)'),
    ('idx_resource_kind', RESOURCE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_kind ON resources(resource_kind)'),
    ('idx_resource_org', RESOURCE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_org ON resources(org_id)'),
    ('idx_resource_location', RESOURCE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_location ON resources(location_id)'),
    ('idx_resource_party', RESOURCE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_party ON resources(party_id)'),
    ('idx_resource_person', RESOURCE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_person ON resources(person_ref)'),
    ('idx_resource_active', RESOURCE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_active ON resources(is_active)'),

    ('uq_resource_group_code', GROUP_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_group_code '
     'ON resource_groups(code)'),
    ('idx_resource_group_parent', GROUP_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_group_parent '
     'ON resource_groups(parent_group_id)'),
    ('idx_resource_group_org', GROUP_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_group_org ON resource_groups(org_id)'),
    ('idx_resource_group_kind', GROUP_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_group_kind '
     'ON resource_groups(group_kind)'),
    ('idx_resource_group_active', GROUP_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_group_active '
     'ON resource_groups(is_active)'),

    ('uq_resource_group_member', MEMBER_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_group_member '
     'ON resource_group_members(group_id, resource_id)'),
    ('idx_resource_group_member_resource', MEMBER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_group_member_resource '
     'ON resource_group_members(resource_id)'),
    ('idx_resource_group_member_group', MEMBER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_group_member_group '
     'ON resource_group_members(group_id)'),

    ('uq_resource_capability', CAPABILITY_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_capability '
     'ON resource_capabilities(resource_id, skill_id, valid_from)'),
    ('idx_resource_capability_resource', CAPABILITY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_capability_resource '
     'ON resource_capabilities(resource_id)'),
    ('idx_resource_capability_skill', CAPABILITY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_capability_skill '
     'ON resource_capabilities(skill_id)'),

    ('uq_resource_rate_resource', RATE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_rate_resource '
     'ON resource_rates(resource_id, rate_purpose, valid_from)'),
    ('uq_resource_rate_group', RATE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_rate_group '
     'ON resource_rates(resource_group_id, rate_purpose, valid_from)'),
    ('idx_resource_rate_purpose', RATE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_rate_purpose '
     'ON resource_rates(rate_purpose)'),
    ('idx_resource_rate_org', RATE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_rate_org ON resource_rates(org_id)'),
    ('idx_resource_rate_validity', RATE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_rate_validity '
     'ON resource_rates(valid_from, valid_to)'),

    ('idx_work_order_operation_resource_group', OPERATIONS_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_work_order_operation_resource_group '
     'ON work_order_operations(resource_group_id)'),
    ('idx_work_order_operation_required_skill', OPERATIONS_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_work_order_operation_required_skill '
     'ON work_order_operations(required_skill_id)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('resource_kind', '资源类型', '资源主数据的类型取值',
     (('person', '人员', 'Person'),
      ('machine', '设备', 'Machine'),
      ('vehicle', '车辆', 'Vehicle'),
      ('tool', '工具', 'Tool'),
      ('facility', '场地', 'Facility'),
      ('site', '站点', 'Site'),
      ('external', '外协', 'External'))),
    ('resource_group_kind', '资源组类型', '资源组的类型取值（工作中心是其中一种）',
     (('work_center', '工作中心', 'Work Center'),
      ('crew', '班组', 'Crew'),
      ('pool', '资源池', 'Pool'),
      ('fleet', '车队', 'Fleet'),
      ('site_group', '场地组', 'Site Group'))),
    ('capacity_aggregation', '产能聚合方式', '资源组产能从直接下级聚合的口径',
     (('sum', '求和', 'Sum'),
      ('max', '取最大', 'Max'),
      ('bottleneck', '瓶颈', 'Bottleneck'))),
    ('membership_mode', '组成员模式', '节点挂成员还是子组（二者互斥）',
     (('members', '挂成员', 'Members'),
      ('children', '挂子组', 'Children'))),
    ('skill_category', '技能分类', '技能主数据的分类取值',
     (('trade', '工种', 'Trade'),
      ('certification', '认证', 'Certification'),
      ('language', '语言', 'Language'),
      ('soft', '通用素质', 'Soft Skill'))),
    ('rate_purpose', '费率用途', '资源费率的用途取值',
     (('cost', '成本', 'Cost'),
      ('billing', '计费', 'Billing'),
      ('overtime', '加班', 'Overtime'),
      ('setup', '准备', 'Setup'))),
    ('rate_basis', '费率基准', '资源费率的计量基准',
     (('per_hour', '按小时', 'Per Hour'),
      ('per_use', '按次', 'Per Use'),
      ('per_unit', '按单位', 'Per Unit'),
      ('per_km', '按里程', 'Per KM'),
      ('per_kg', '按重量', 'Per KG'))),
    ('resource_rate_source', '费率来源', '资源费率的来源取值',
     (('internal', '内部', 'Internal'),
      ('external_contract', '外协合同', 'External Contract'),
      ('standard', '标准', 'Standard'))),
)

ACTIONS = ('read', 'create', 'update', 'delete')
_ACTION_LABEL = {
    'read': '查看', 'create': '新建', 'update': '修改', 'delete': '删除',
}
OBJECTS = (
    ('skill', '技能'),
    ('resource', '资源'),
    ('resource_group', '资源组'),
    ('resource_group_member', '资源组成员'),
    ('resource_capability', '资源能力'),
    ('resource_rate', '资源费率'),
)

PERMISSIONS = tuple(
    ('{0}:{0}_{1}'.format(bo, action),
     '{0}{1}'.format(label, _ACTION_LABEL[action]), bo, action)
    for bo, label in OBJECTS
    for action in ACTIONS
)

GRANT_TO_SETS = ('admin', 'default')

MENUS = (
    {'menu_code': 'resource-list', 'menu_name': '资源', 'menu_path': '/resources',
     'primary_object_type': 'resource', 'icon': 'Boxes', 'color': '#0ea5e9',
     'sort_order': 87, 'description': '资源主数据：人 / 设备 / 车辆 / 工具 / 场地 / 站点 / 外协'},
    {'menu_code': 'resource-group-list', 'menu_name': '资源组',
     'menu_path': '/resource-groups', 'primary_object_type': 'resource_group',
     'icon': 'Network', 'color': '#6366f1', 'sort_order': 88,
     'description': '资源组：工作中心 / 班组 / 资源池 / 车队 / 场地组（多层级）'},
    {'menu_code': 'skill-list', 'menu_name': '技能', 'menu_path': '/skills',
     'primary_object_type': 'skill', 'icon': 'BadgeCheck', 'color': '#10b981',
     'sort_order': 89, 'description': '技能主数据：工种 / 认证 / 语言 / 通用素质'},
    {'menu_code': 'resource-group-member-list', 'menu_name': '资源组成员',
     'menu_path': '/resource-group-members',
     'primary_object_type': 'resource_group_member',
     'icon': 'Users', 'color': '#f59e0b', 'sort_order': 90,
     'description': '资源组成员关系（分配比例 / 数量 / 有效期）'},
    {'menu_code': 'resource-capability-list', 'menu_name': '资源能力',
     'menu_path': '/resource-capabilities',
     'primary_object_type': 'resource_capability',
     'icon': 'Award', 'color': '#8b5cf6', 'sort_order': 91,
     'description': '资源持有技能的能力记录（等级 / 有效期 / 认证）'},
    {'menu_code': 'resource-rate-list', 'menu_name': '资源费率',
     'menu_path': '/resource-rates', 'primary_object_type': 'resource_rate',
     'icon': 'CircleDollarSign', 'color': '#ef4444', 'sort_order': 92,
     'description': '资源 / 资源组费率（用途 / 基准 / 有效期 / 优先级）'},
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
        try:
            conn.execute(sql)
            print(f'  - [ADD] 索引 {name}')
        except sqlite3.IntegrityError as e:
            print(f'  - [FAIL] 索引 {name}: {e}')
            raise


def _do_enums(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values')):
        print('  - enum_types / enum_values 不存在, 跳过枚举种子')
        return
    for type_id, type_name, description, values in ENUM_SEEDS:
        if conn.execute('SELECT 1 FROM enum_types WHERE id=?', (type_id,)).fetchone():
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
                (type_id, code),
            ).fetchone():
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


def _resolve_parent_menu(conn: sqlite3.Connection) -> str:
    if not _table_exists(conn, 'menus'):
        return ''
    row = conn.execute(
        'SELECT 1 FROM menus WHERE menu_code=?', (PARENT_MENU,)
    ).fetchone()
    if row:
        return PARENT_MENU
    print(f'  - [WARN] 父菜单 {PARENT_MENU} 不存在，6 条菜单挂顶层（parent_menu=""）')
    return ''


def _do_menus(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return
    parent = _resolve_parent_menu(conn)
    for menu in MENUS:
        required = [
            '{0}:{0}_{1}'.format(menu['primary_object_type'], action)
            for action in ACTIONS
        ]
        bo_binding = [{
            'bo_id': menu['primary_object_type'],
            'role': 'primary',
            'include_actions': list(ACTIONS),
        }]
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
                "VALUES (?, ?, ?, 'object_list', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 0)",
                (
                    menu['menu_code'], menu['menu_name'], menu['menu_path'],
                    json.dumps([menu['primary_object_type']], ensure_ascii=False),
                    menu['primary_object_type'],
                    json.dumps(bo_binding, ensure_ascii=False),
                    json.dumps(required, ensure_ascii=False),
                    parent, menu['icon'], menu['color'], menu['description'],
                    menu['sort_order'],
                ),
            )
            print(f"  - [NEW] 菜单 {menu['menu_code']}")

        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, "
                "menu_path, required_permissions, required_any_permission, "
                "parent_menu, icon, sort_order, is_active, data_permission_hint) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, NULL)",
                (
                    menu['menu_code'], menu['menu_name'], menu['menu_path'],
                    json.dumps(required, ensure_ascii=False),
                    parent, menu['icon'], menu['sort_order'],
                ),
            )
            if cur.rowcount:
                print(f"  - [NEW] menu_permissions: {menu['menu_code']}")
            else:
                print(f"  - [SKIP] menu_permissions: {menu['menu_code']} 已存在")


def _do_operations_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, OPERATIONS_TABLE):
        print(f'  - [SKIP] 表 {OPERATIONS_TABLE} 不存在（由 v161 / sync_schema 创建）')
        return
    cols = _columns(conn, OPERATIONS_TABLE)

    if 'resource_group_id' in cols:
        print(f'  - [SKIP] 列 {OPERATIONS_TABLE}.resource_group_id 已存在')
    elif 'work_center_id' in cols:
        conn.execute(
            f'ALTER TABLE {OPERATIONS_TABLE} '
            'RENAME COLUMN work_center_id TO resource_group_id'
        )
        print(f'  - [RENAME] {OPERATIONS_TABLE}.work_center_id → resource_group_id')
    else:
        conn.execute(
            f'ALTER TABLE {OPERATIONS_TABLE} ADD COLUMN resource_group_id INTEGER NULL'
        )
        print(f'  - [ALTER] 列 {OPERATIONS_TABLE}.resource_group_id')

    if 'required_skill_id' in cols:
        print(f'  - [SKIP] 列 {OPERATIONS_TABLE}.required_skill_id 已存在')
    else:
        conn.execute(
            f'ALTER TABLE {OPERATIONS_TABLE} ADD COLUMN required_skill_id INTEGER NULL'
        )
        print(f'  - [ALTER] 列 {OPERATIONS_TABLE}.required_skill_id')

    if 'teardown_minutes' in cols:
        print(f'  - [SKIP] 列 {OPERATIONS_TABLE}.teardown_minutes 已存在')
    else:
        conn.execute(
            f'ALTER TABLE {OPERATIONS_TABLE} ADD COLUMN teardown_minutes INTEGER DEFAULT 0'
        )
        print(f'  - [ALTER] 列 {OPERATIONS_TABLE}.teardown_minutes')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v175] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v175] 开始: 统一资源模型地基（P2a）')
        _do_tables(conn)
        _do_operations_columns(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        conn.commit()
        print('[v175] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v175] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v175 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            SKILL_TABLE: ('code', 'name', 'category', 'parent_id',
                          'requires_certification', 'default_validity_months',
                          'status', 'description'),
            RESOURCE_TABLE: ('code', 'name', 'resource_kind', 'resource_role',
                             'org_id', 'location_id', 'cost_center_id', 'party_id',
                             'person_ref', 'capacity_uom_id', 'capacity_per_day',
                             'capacity_units', 'utilization_pct', 'calendar_id',
                             'timezone', 'is_active', 'valid_from', 'valid_to'),
            GROUP_TABLE: ('code', 'name', 'group_kind', 'org_id', 'org_unit_id',
                          'location_id', 'calendar_id', 'cost_center_id',
                          'capacity_aggregation', 'membership_mode',
                          'parent_group_id', 'is_bottleneck', 'is_active',
                          'valid_from', 'valid_to'),
            MEMBER_TABLE: ('group_id', 'resource_id', 'role', 'priority',
                           'allocation_pct', 'quantity', 'valid_from', 'valid_to'),
            CAPABILITY_TABLE: ('resource_id', 'skill_id', 'level', 'valid_from',
                               'valid_to', 'certification_ref', 'verified_by',
                               'verified_at'),
            RATE_TABLE: ('resource_id', 'resource_group_id', 'rate_purpose',
                         'rate_basis', 'org_id', 'location_id', 'currency_id',
                         'rate', 'rate_uom_id', 'valid_from', 'valid_to',
                         'priority', 'rate_source'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v175 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v175 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v175 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute(
                    'SELECT 1 FROM enum_types WHERE id=?', (type_id,)
                ).fetchone():
                    print(f'[v175 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        (type_id, code),
                    ).fetchone():
                        print(f'[v175 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v175 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                row = conn.execute(
                    'SELECT is_active, parent_menu, primary_object_type '
                    'FROM menus WHERE menu_code=?', (menu['menu_code'],)
                ).fetchone()
                if not row:
                    print(f"[v175 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False
                    continue
                if row[0] != 1:
                    print(f"[v175 verify] FAIL: 菜单 {menu['menu_code']} 未启用")
                    ok = False
                if row[2] != menu['primary_object_type']:
                    print(f"[v175 verify] FAIL: 菜单 {menu['menu_code']} primary_object_type")
                    ok = False
                if _table_exists(conn, 'menus') and \
                        conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                                     (PARENT_MENU,)).fetchone():
                    if row[1] != PARENT_MENU:
                        print(f"[v175 verify] FAIL: 菜单 {menu['menu_code']} 未挂 {PARENT_MENU}")
                        ok = False

        if _table_exists(conn, OPERATIONS_TABLE):
            have = _columns(conn, OPERATIONS_TABLE)
            for col in ('resource_group_id', 'required_skill_id', 'teardown_minutes'):
                if col not in have:
                    print(f'[v175 verify] FAIL: 缺列 {OPERATIONS_TABLE}.{col}')
                    ok = False

        print('[v175 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v175 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for menu in MENUS:
            if _table_exists(conn, 'menu_permissions'):
                conn.execute(
                    'DELETE FROM menu_permissions WHERE menu_code=?',
                    (menu['menu_code'],),
                )
            if _table_exists(conn, 'menus'):
                conn.execute(
                    'DELETE FROM menus WHERE menu_code=?', (menu['menu_code'],)
                )
        print('  - [DROP] 6 条资源域菜单')

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for table in (RATE_TABLE, CAPABILITY_TABLE, MEMBER_TABLE,
                      RESOURCE_TABLE, GROUP_TABLE, SKILL_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')

        if _table_exists(conn, OPERATIONS_TABLE):
            cols = _columns(conn, OPERATIONS_TABLE)
            if 'resource_group_id' in cols and 'work_center_id' not in cols:
                conn.execute(
                    f'ALTER TABLE {OPERATIONS_TABLE} '
                    'RENAME COLUMN resource_group_id TO work_center_id'
                )
                print(f'  - [RENAME] {OPERATIONS_TABLE}.resource_group_id → work_center_id')

        conn.commit()
        print('[v175 rollback] 完成（permissions / 枚举种子 / 新增列保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v175 rollback] 失败: {e}')
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
