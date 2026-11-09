# -*- coding: utf-8 -*-
"""[v176 2026-11-01] 统一资源模型 P2b（作业定义 / 班次 / 产能 / 分配）

依据:
  docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
    §FR-014 / §9.2 目标架构 / §9.3 数据模型表 / §9.5 实施顺序

设计:
  · 8 张表由 `meta/schemas/{shift,calendar_shift,work_definition,
    work_definition_operation,operation_resource_requirement,resource_capacity,
    resource_assignment,resource_territory_assignment}.yaml` 声明，
    sync_schema 生成；本迁移做「兜底 CREATE + 补索引 + 枚举种子 + 权限 + 菜单」。
  · 8 组枚举（29 个取值）种入 `enum_types` / `enum_values`，type id 与
    schema 里的 `value_help.source.enum_type_id` 一字不差。
  · 8 条菜单挂在现有「主数据」父菜单（menu_code='master-data'），
    sort_order 93–100 接在 v175 的 87–92 之后；父节点不存在时退回顶层并打印说明。
  · 权限码为双段式 `{bo}:{bo}_{action}`，授予 admin / default 权限集。

幂等:
  表 / 索引 / 枚举 / 菜单 / 权限 / 授权先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单 + menu_permissions + 本迁移写入的 permissions / permission_set_permissions
  + 8 张表；枚举种子保留（可能已被其他对象引用）。
"""
import json
import sqlite3
import sys
from pathlib import Path

SHIFT_TABLE = 'shifts'
CALENDAR_SHIFT_TABLE = 'calendar_shifts'
DEFINITION_TABLE = 'work_definitions'
DEFINITION_OP_TABLE = 'work_definition_operations'
REQUIREMENT_TABLE = 'operation_resource_requirements'
CAPACITY_TABLE = 'resource_capacities'
ASSIGNMENT_TABLE = 'resource_assignments'
TERRITORY_ASSIGNMENT_TABLE = 'resource_territory_assignments'

PARENT_MENU = 'master-data'

TABLES = (
    (SHIFT_TABLE, """
CREATE TABLE IF NOT EXISTS shifts (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    start_time VARCHAR(200) NOT NULL,
    end_time VARCHAR(200) NOT NULL,
    crosses_midnight INTEGER NOT NULL DEFAULT 0,
    break_minutes INTEGER NOT NULL DEFAULT 0,
    shift_type VARCHAR(200) NOT NULL DEFAULT 'regular',
    org_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    valid_from DATETIME,
    valid_to DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (org_id) REFERENCES orgs(id)
)
"""),
    (CALENDAR_SHIFT_TABLE, """
CREATE TABLE IF NOT EXISTS calendar_shifts (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id INTEGER NOT NULL,
    shift_id INTEGER NOT NULL,
    day_mask_mon INTEGER NOT NULL DEFAULT 1,
    day_mask_tue INTEGER NOT NULL DEFAULT 1,
    day_mask_wed INTEGER NOT NULL DEFAULT 1,
    day_mask_thu INTEGER NOT NULL DEFAULT 1,
    day_mask_fri INTEGER NOT NULL DEFAULT 1,
    day_mask_sat INTEGER NOT NULL DEFAULT 1,
    day_mask_sun INTEGER NOT NULL DEFAULT 1,
    seq INTEGER NOT NULL DEFAULT 1,
    capacity_factor REAL NOT NULL DEFAULT 1.0,
    valid_from DATETIME,
    valid_to DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (calendar_id) REFERENCES calendars(id),
    FOREIGN KEY (shift_id) REFERENCES shifts(id)
)
"""),
    (DEFINITION_TABLE, """
CREATE TABLE IF NOT EXISTS work_definitions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    definition_kind VARCHAR(200) NOT NULL DEFAULT 'routing',
    item_id INTEGER,
    revision VARCHAR(200) NOT NULL DEFAULT 'A',
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    org_id INTEGER,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id)
)
"""),
    (DEFINITION_OP_TABLE, """
CREATE TABLE IF NOT EXISTS work_definition_operations (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    definition_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    operation_name VARCHAR(200) NOT NULL,
    resource_group_id INTEGER,
    setup_minutes INTEGER NOT NULL DEFAULT 0,
    teardown_minutes INTEGER NOT NULL DEFAULT 0,
    run_minutes INTEGER NOT NULL DEFAULT 0,
    queue_minutes INTEGER NOT NULL DEFAULT 0,
    move_minutes INTEGER NOT NULL DEFAULT 0,
    travel_minutes INTEGER NOT NULL DEFAULT 0,
    qty_per REAL NOT NULL DEFAULT 1,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (definition_id) REFERENCES work_definitions(id),
    FOREIGN KEY (resource_group_id) REFERENCES resource_groups(id)
)
"""),
    (REQUIREMENT_TABLE, """
CREATE TABLE IF NOT EXISTS operation_resource_requirements (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL,
    resource_group_id INTEGER,
    resource_id INTEGER,
    role VARCHAR(200) NOT NULL DEFAULT 'labor',
    qty REAL NOT NULL DEFAULT 1,
    required_skill_id INTEGER,
    min_level INTEGER,
    is_primary INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 1,
    lead_time_days INTEGER,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (operation_id) REFERENCES work_definition_operations(id),
    FOREIGN KEY (resource_group_id) REFERENCES resource_groups(id),
    FOREIGN KEY (resource_id) REFERENCES resources(id),
    FOREIGN KEY (required_skill_id) REFERENCES skills(id)
)
"""),
    (CAPACITY_TABLE, """
CREATE TABLE IF NOT EXISTS resource_capacities (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER,
    resource_group_id INTEGER,
    capacity_category VARCHAR(200) NOT NULL DEFAULT 'labor_hours',
    capacity_uom_id INTEGER,
    capacity_per_day REAL,
    capacity_units REAL NOT NULL DEFAULT 1,
    utilization_pct REAL NOT NULL DEFAULT 100,
    valid_from DATETIME,
    valid_to DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (resource_id) REFERENCES resources(id),
    FOREIGN KEY (resource_group_id) REFERENCES resource_groups(id),
    FOREIGN KEY (capacity_uom_id) REFERENCES uoms(id)
)
"""),
    (ASSIGNMENT_TABLE, """
CREATE TABLE IF NOT EXISTS resource_assignments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_operation_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    planned_start DATETIME,
    planned_end DATETIME,
    planned_qty REAL,
    status VARCHAR(200) NOT NULL DEFAULT 'planned',
    source VARCHAR(200) NOT NULL DEFAULT 'manual',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (work_order_operation_id) REFERENCES work_order_operations(id),
    FOREIGN KEY (resource_id) REFERENCES resources(id)
)
"""),
    (TERRITORY_ASSIGNMENT_TABLE, """
CREATE TABLE IF NOT EXISTS resource_territory_assignments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER,
    resource_group_id INTEGER,
    territory_id INTEGER NOT NULL,
    coverage_level VARCHAR(200) NOT NULL DEFAULT 'primary',
    effective_from DATETIME,
    effective_to DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (resource_id) REFERENCES resources(id),
    FOREIGN KEY (resource_group_id) REFERENCES resource_groups(id),
    FOREIGN KEY (territory_id) REFERENCES territories(id)
)
"""),
)

INDEXES = (
    ('uq_shift_code', SHIFT_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_shift_code ON shifts(code)'),
    ('idx_shift_org', SHIFT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_shift_org ON shifts(org_id)'),
    ('idx_shift_validity', SHIFT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_shift_validity ON shifts(valid_from)'),

    ('idx_calendar_shift_calendar', CALENDAR_SHIFT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_calendar_shift_calendar '
     'ON calendar_shifts(calendar_id)'),
    ('idx_calendar_shift_shift', CALENDAR_SHIFT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_calendar_shift_shift '
     'ON calendar_shifts(shift_id)'),
    ('idx_calendar_shift_validity', CALENDAR_SHIFT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_calendar_shift_validity '
     'ON calendar_shifts(valid_from)'),
    ('uq_calendar_shift', CALENDAR_SHIFT_TABLE,
     "CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_shift "
     "ON calendar_shifts(calendar_id, shift_id, seq, IFNULL(valid_from, ''))"),

    ('uq_work_definition_code_revision', DEFINITION_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_work_definition_code_revision '
     'ON work_definitions(code, revision)'),
    ('idx_work_definition_item', DEFINITION_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_work_definition_item '
     'ON work_definitions(item_id)'),
    ('idx_work_definition_org', DEFINITION_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_work_definition_org '
     'ON work_definitions(org_id)'),
    ('idx_work_definition_status', DEFINITION_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_work_definition_status '
     'ON work_definitions(status)'),

    ('uq_work_definition_operation_seq', DEFINITION_OP_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_work_definition_operation_seq '
     'ON work_definition_operations(definition_id, seq)'),
    ('idx_work_definition_operation_group', DEFINITION_OP_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_work_definition_operation_group '
     'ON work_definition_operations(resource_group_id)'),
    ('idx_work_definition_operation_status', DEFINITION_OP_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_work_definition_operation_status '
     'ON work_definition_operations(status)'),

    ('idx_operation_resource_requirement_operation', REQUIREMENT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_operation_resource_requirement_operation '
     'ON operation_resource_requirements(operation_id)'),
    ('idx_operation_resource_requirement_group', REQUIREMENT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_operation_resource_requirement_group '
     'ON operation_resource_requirements(resource_group_id)'),
    ('idx_operation_resource_requirement_resource', REQUIREMENT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_operation_resource_requirement_resource '
     'ON operation_resource_requirements(resource_id)'),
    ('idx_operation_resource_requirement_skill', REQUIREMENT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_operation_resource_requirement_skill '
     'ON operation_resource_requirements(required_skill_id)'),

    ('uq_resource_capacity', CAPACITY_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_capacity '
     'ON resource_capacities(resource_id, resource_group_id, capacity_category, '
     'valid_from)'),
    ('idx_resource_capacity_group', CAPACITY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_capacity_group '
     'ON resource_capacities(resource_group_id)'),
    ('idx_resource_capacity_uom', CAPACITY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_capacity_uom '
     'ON resource_capacities(capacity_uom_id)'),
    ('idx_resource_capacity_validity', CAPACITY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_capacity_validity '
     'ON resource_capacities(valid_from)'),

    ('uq_resource_assignment', ASSIGNMENT_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_assignment '
     'ON resource_assignments(work_order_operation_id, resource_id, planned_start)'),
    ('idx_resource_assignment_resource', ASSIGNMENT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_assignment_resource '
     'ON resource_assignments(resource_id)'),
    ('idx_resource_assignment_operation', ASSIGNMENT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_assignment_operation '
     'ON resource_assignments(work_order_operation_id)'),

    ('uq_resource_territory_assignment', TERRITORY_ASSIGNMENT_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_territory_assignment '
     'ON resource_territory_assignments(resource_id, resource_group_id, '
     'territory_id, effective_from)'),
    ('idx_resource_territory_assignment_group', TERRITORY_ASSIGNMENT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_territory_assignment_group '
     'ON resource_territory_assignments(resource_group_id)'),
    ('idx_resource_territory_assignment_territory', TERRITORY_ASSIGNMENT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_resource_territory_assignment_territory '
     'ON resource_territory_assignments(territory_id)'),
)

# 唯一键（7 条）—— 与 schema 的 `indexes[*].unique` 一一对应
UNIQUE_KEYS = (
    'uq_shift_code',
    'uq_calendar_shift',
    'uq_work_definition_code_revision',
    'uq_work_definition_operation_seq',
    'uq_resource_capacity',
    'uq_resource_assignment',
    'uq_resource_territory_assignment',
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('shift_type', '班次类型', '班次时段的类型取值',
     (('regular', '常规', 'Regular'),
      ('overtime', '加班', 'Overtime'),
      ('standby', '待命', 'Standby'))),
    ('capacity_category', '产能口径', '资源产能的计量口径（多口径产能 TBD-4）',
     (('labor_hours', '人工工时', 'Labor Hours'),
      ('machine_hours', '设备工时', 'Machine Hours'),
      ('tool_count', '工装位', 'Tool Count'),
      ('vehicle_weight', '载重', 'Vehicle Weight'),
      ('vehicle_volume', '体积', 'Vehicle Volume'),
      ('facility_capacity', '场地容量', 'Facility Capacity'))),
    ('definition_kind', '作业定义类型', '作业定义的场景类型',
     (('routing', '工艺路线', 'Routing'),
      ('recipe', '配方', 'Recipe'),
      ('service_template', '服务模板', 'Service Template'))),
    ('work_definition_status', '作业定义状态', '作业定义与其工序的状态取值',
     (('draft', '草稿', 'Draft'),
      ('active', '生效', 'Active'),
      ('obsolete', '作废', 'Obsolete'))),
    ('requirement_role', '资源要求角色', '工序需要资源承担的角色',
     (('machine', '设备', 'Machine'),
      ('labor', '人工', 'Labor'),
      ('tool', '工装', 'Tool'),
      ('vehicle', '车辆', 'Vehicle'),
      ('external', '外协', 'External'))),
    ('assignment_status', '资源分配状态', '资源分配的生命周期状态',
     (('planned', '计划', 'Planned'),
      ('confirmed', '已确认', 'Confirmed'),
      ('in_progress', '执行中', 'In Progress'),
      ('completed', '已完成', 'Completed'),
      ('canceled', '已取消', 'Canceled'))),
    ('assignment_source', '分配来源', '资源分配的产生方式',
     (('manual', '手工', 'Manual'),
      ('auto', '自动排程', 'Auto'))),
    ('coverage_level', '区域覆盖级别', '资源对服务区域的覆盖级别',
     (('primary', '主覆盖', 'Primary'),
      ('backup', '备选覆盖', 'Backup'))),
)

ACTIONS = ('read', 'create', 'update', 'delete')
_ACTION_LABEL = {
    'read': '查看', 'create': '新建', 'update': '修改', 'delete': '删除',
}
OBJECTS = (
    ('shift', '班次'),
    ('calendar_shift', '日历班次'),
    ('work_definition', '作业定义'),
    ('work_definition_operation', '作业定义工序'),
    ('operation_resource_requirement', '工序资源要求'),
    ('resource_capacity', '资源产能'),
    ('resource_assignment', '资源分配'),
    ('resource_territory_assignment', '资源区域分配'),
)

PERMISSIONS = tuple(
    ('{0}:{0}_{1}'.format(bo, action),
     '{0}{1}'.format(label, _ACTION_LABEL[action]), bo, action)
    for bo, label in OBJECTS
    for action in ACTIONS
)

GRANT_TO_SETS = ('admin', 'default')

MENUS = (
    {'menu_code': 'shift-list', 'menu_name': '班次', 'menu_path': '/shifts',
     'primary_object_type': 'shift', 'icon': 'CalendarClock', 'color': '#0ea5e9',
     'sort_order': 93, 'description': '班次时段模板（开始/结束/跨天/休息扣减/类型）'},
    {'menu_code': 'calendar-shift-list', 'menu_name': '日历班次',
     'menu_path': '/calendar-shifts',
     'primary_object_type': 'calendar_shift',
     'icon': 'CalendarRange', 'color': '#6366f1', 'sort_order': 94,
     'description': '日历 × 星期掩码 × 班次（产能系数 / 同日多班排序）'},
    {'menu_code': 'work-definition-list', 'menu_name': '作业定义',
     'menu_path': '/work-definitions',
     'primary_object_type': 'work_definition',
     'icon': 'ClipboardList', 'color': '#10b981', 'sort_order': 95,
     'description': '标准作业定义：工艺路线 / 服务模板（编码 + 版本唯一）'},
    {'menu_code': 'work-definition-operation-list', 'menu_name': '作业定义工序',
     'menu_path': '/work-definition-operations',
     'primary_object_type': 'work_definition_operation',
     'icon': 'ListOrdered', 'color': '#f59e0b', 'sort_order': 96,
     'description': '作业定义下的工序（顺序 / 六类工时 / 产量倍数）'},
    {'menu_code': 'operation-resource-requirement-list', 'menu_name': '工序资源要求',
     'menu_path': '/operation-resource-requirements',
     'primary_object_type': 'operation_resource_requirement',
     'icon': 'Users', 'color': '#8b5cf6', 'sort_order': 97,
     'description': '工序需要的资源组/资源、角色、数量与技能等级'},
    {'menu_code': 'resource-capacity-list', 'menu_name': '资源产能',
     'menu_path': '/resource-capacities',
     'primary_object_type': 'resource_capacity',
     'icon': 'Gauge', 'color': '#06b6d4', 'sort_order': 98,
     'description': '资源 / 资源组的多口径产能（口径 + 单位 + 日产能 + 有效性）'},
    {'menu_code': 'resource-assignment-list', 'menu_name': '资源分配',
     'menu_path': '/resource-assignments',
     'primary_object_type': 'resource_assignment',
     'icon': 'CalendarCheck', 'color': '#ef4444', 'sort_order': 99,
     'description': '工单工序的资源分配（资源 + 计划时间窗 + 计划量 + 状态）'},
    {'menu_code': 'resource-territory-assignment-list', 'menu_name': '资源区域分配',
     'menu_path': '/resource-territory-assignments',
     'primary_object_type': 'resource_territory_assignment',
     'icon': 'MapPin', 'color': '#22c55e', 'sort_order': 100,
     'description': '资源/资源组的服务区域覆盖（区域 + 覆盖级别 + 生效区间）'},
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
    print(f'  - [WARN] 父菜单 {PARENT_MENU} 不存在，8 条菜单挂顶层（parent_menu=""）')
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


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v176] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v176] 开始: 统一资源模型 P2b（作业定义 / 班次 / 产能 / 分配）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        conn.commit()
        print('[v176] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v176] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v176 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            SHIFT_TABLE: ('code', 'name', 'start_time', 'end_time',
                          'crosses_midnight', 'break_minutes', 'shift_type',
                          'org_id', 'is_active', 'valid_from', 'valid_to'),
            CALENDAR_SHIFT_TABLE: ('calendar_id', 'shift_id', 'day_mask_mon',
                                   'day_mask_tue', 'day_mask_wed', 'day_mask_thu',
                                   'day_mask_fri', 'day_mask_sat', 'day_mask_sun',
                                   'seq', 'capacity_factor', 'valid_from', 'valid_to'),
            DEFINITION_TABLE: ('code', 'name', 'definition_kind', 'item_id',
                               'revision', 'status', 'org_id', 'description'),
            DEFINITION_OP_TABLE: ('definition_id', 'seq', 'operation_name',
                                  'resource_group_id', 'setup_minutes',
                                  'teardown_minutes', 'run_minutes',
                                  'queue_minutes', 'move_minutes',
                                  'travel_minutes', 'qty_per', 'status'),
            REQUIREMENT_TABLE: ('operation_id', 'resource_group_id', 'resource_id',
                                'role', 'qty', 'required_skill_id', 'min_level',
                                'is_primary', 'priority', 'lead_time_days'),
            CAPACITY_TABLE: ('resource_id', 'resource_group_id', 'capacity_category',
                             'capacity_uom_id', 'capacity_per_day', 'capacity_units',
                             'utilization_pct', 'valid_from', 'valid_to'),
            ASSIGNMENT_TABLE: ('work_order_operation_id', 'resource_id',
                               'planned_start', 'planned_end', 'planned_qty',
                               'status', 'source'),
            TERRITORY_ASSIGNMENT_TABLE: ('resource_id', 'resource_group_id',
                                         'territory_id', 'coverage_level',
                                         'effective_from', 'effective_to'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v176 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v176 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v176 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute(
                    'SELECT 1 FROM enum_types WHERE id=?', (type_id,)
                ).fetchone():
                    print(f'[v176 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        (type_id, code),
                    ).fetchone():
                        print(f'[v176 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v176 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            has_parent = conn.execute(
                'SELECT 1 FROM menus WHERE menu_code=?', (PARENT_MENU,)
            ).fetchone()
            for menu in MENUS:
                row = conn.execute(
                    'SELECT is_active, parent_menu, primary_object_type, '
                    'show_in_sidebar, sort_order FROM menus WHERE menu_code=?',
                    (menu['menu_code'],)
                ).fetchone()
                if not row:
                    print(f"[v176 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False
                    continue
                if row[0] != 1:
                    print(f"[v176 verify] FAIL: 菜单 {menu['menu_code']} 未启用")
                    ok = False
                if row[2] != menu['primary_object_type']:
                    print(f"[v176 verify] FAIL: 菜单 {menu['menu_code']} primary_object_type")
                    ok = False
                if row[3] != 0:
                    print(f"[v176 verify] FAIL: 菜单 {menu['menu_code']} show_in_sidebar")
                    ok = False
                if row[4] != menu['sort_order']:
                    print(f"[v176 verify] FAIL: 菜单 {menu['menu_code']} sort_order")
                    ok = False
                if has_parent and row[1] != PARENT_MENU:
                    print(f"[v176 verify] FAIL: 菜单 {menu['menu_code']} 未挂 {PARENT_MENU}")
                    ok = False

        print('[v176 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v176 rollback] DB 不存在: {db_path}')
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
        print('  - [DROP] 8 条资源域 P2b 菜单')

        codes = [code for code, _name, _rtype, _action in PERMISSIONS]
        if _table_exists(conn, 'permissions'):
            ids = [row[0] for row in conn.execute(
                'SELECT id FROM permissions WHERE code IN (%s)'
                % ','.join('?' * len(codes)), codes).fetchall()]
            if ids and _table_exists(conn, 'permission_set_permissions'):
                conn.execute(
                    'DELETE FROM permission_set_permissions WHERE permission_id IN (%s)'
                    % ','.join('?' * len(ids)), ids,
                )
            conn.execute(
                'DELETE FROM permissions WHERE code IN (%s)'
                % ','.join('?' * len(codes)), codes,
            )
            print(f'  - [DROP] {len(codes)} 条 P2b 权限（含权限集授权行）')

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for table in (TERRITORY_ASSIGNMENT_TABLE, ASSIGNMENT_TABLE,
                      CAPACITY_TABLE, REQUIREMENT_TABLE, DEFINITION_OP_TABLE,
                      DEFINITION_TABLE, CALENDAR_SHIFT_TABLE, SHIFT_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')

        conn.commit()
        print('[v176 rollback] 完成（枚举种子保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v176 rollback] 失败: {e}')
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
