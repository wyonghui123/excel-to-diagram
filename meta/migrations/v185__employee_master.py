# -*- coding: utf-8 -*-
"""[v185 2026-11-01] 统一资源模型 P3（员工薄主数据 + 员工排班）

依据:
  docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
    §FR-015 员工主数据（薄）/ §9.3 数据模型表 / §9.5 实施顺序

设计:
  · `employees` 是 `person_profiles` 之上的**雇佣关系**（薄 assignment），
    不含 `resource_id`；资源与员工都指向 person，按 person 求交
    （`resource.person_ref = employees.person_profile_id AND status='active'`）。
  · `employee_shift_assignments` 承载「谁上哪个班」，复用 FR-014 的 `shifts`
    时段模板，不复制时段定义。
  · 表由 `meta/schemas/employee.yaml` / `employee_shift_assignment.yaml` 声明，
    sync_schema 生成；本迁移做「兜底 CREATE + 补索引 + 枚举种子 + 权限 + 菜单」。
  · 2 组枚举（8 个取值）种入 `enum_types` / `enum_values`，type id 与 schema 里
    的 `value_help.source.enum_type_id` 一字不差。
  · 2 条**部分唯一索引**：工号仅在职唯一（再入职沿用原号）、自然人仅在职唯一。
  · 1 条菜单挂在现有「主数据」父菜单（menu_code='master-data'），
    sort_order=102 接在 v180 的 101 之后；父节点不存在时退回顶层并打印说明。
    `employee_shift_assignment` 是关系对象 ⇒ 不做独立菜单。
  · 权限码为双段式 `{bo}:{bo}_{action}`，授予 admin / default 权限集。

幂等:
  表 / 索引 / 枚举 / 菜单 / 权限 / 授权先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单 + menu_permissions + 本迁移写入的 permissions / permission_set_permissions
  + 索引 + 表；枚举种子保留（可能已被其他对象引用）。
"""
import json
import sqlite3
import sys
from pathlib import Path

EMPLOYEES_TABLE = 'employees'
ASSIGNMENTS_TABLE = 'employee_shift_assignments'

PARENT_MENU = 'master-data'

TABLES = (
    (EMPLOYEES_TABLE, """
CREATE TABLE IF NOT EXISTS employees (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_no VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    person_profile_id INTEGER NOT NULL,
    user_id INTEGER,
    org_id INTEGER NOT NULL,
    location_id INTEGER,
    position VARCHAR(200),
    job_grade VARCHAR(200),
    employment_type VARCHAR(200) NOT NULL DEFAULT 'full_time',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    hire_date DATETIME NOT NULL,
    termination_date DATETIME,
    manager_employee_id INTEGER,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (person_profile_id) REFERENCES person_profiles(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (manager_employee_id) REFERENCES employees(id)
)
"""),
    (ASSIGNMENTS_TABLE, """
CREATE TABLE IF NOT EXISTS employee_shift_assignments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    shift_id INTEGER NOT NULL,
    day_mask_mon INTEGER NOT NULL DEFAULT 1,
    day_mask_tue INTEGER NOT NULL DEFAULT 1,
    day_mask_wed INTEGER NOT NULL DEFAULT 1,
    day_mask_thu INTEGER NOT NULL DEFAULT 1,
    day_mask_fri INTEGER NOT NULL DEFAULT 1,
    day_mask_sat INTEGER NOT NULL DEFAULT 1,
    day_mask_sun INTEGER NOT NULL DEFAULT 1,
    seq INTEGER NOT NULL DEFAULT 1,
    effective_from DATETIME NOT NULL,
    effective_to DATETIME,
    work_center_id INTEGER,
    note VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (shift_id) REFERENCES shifts(id),
    FOREIGN KEY (work_center_id) REFERENCES resource_groups(id)
)
"""),
)

INDEXES = (
    ('idx_employee_org', EMPLOYEES_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_employee_org ON employees(org_id)'),
    ('idx_employee_person', EMPLOYEES_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_employee_person '
     'ON employees(person_profile_id)'),
    ('idx_employee_status', EMPLOYEES_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_employee_status ON employees(status)'),
    ('uq_employee_shift_assignment', ASSIGNMENTS_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_shift_assignment '
     'ON employee_shift_assignments(employee_id, shift_id, seq, effective_from)'),
    ('idx_employee_shift_assignment_employee', ASSIGNMENTS_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_employee_shift_assignment_employee '
     'ON employee_shift_assignments(employee_id)'),
    ('idx_employee_shift_assignment_shift', ASSIGNMENTS_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_employee_shift_assignment_shift '
     'ON employee_shift_assignments(shift_id)'),
)

# 部分唯一索引（仅约束 status='active' 的行）
UNIQUE_KEYS = (
    ('uq_employee_active_no', EMPLOYEES_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_active_no '
     "ON employees(employee_no) WHERE status='active'"),
    ('uq_employee_active_person', EMPLOYEES_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_active_person '
     "ON employees(person_profile_id) WHERE status='active'"),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('employment_type', '用工类型', '员工用工类型取值',
     (('full_time', '全职', 'Full Time'),
      ('part_time', '兼职', 'Part Time'),
      ('contractor', '外包', 'Contractor'),
      ('intern', '实习', 'Intern'),
      ('dispatched', '派遣', 'Dispatched'))),
    ('employment_status', '在职状态', '员工在职状态取值',
     (('active', '在职', 'Active'),
      ('inactive', '停职', 'Inactive'),
      ('terminated', '离职', 'Terminated'))),
)

ACTIONS = ('read', 'create', 'update', 'delete')
_ACTION_LABEL = {
    'read': '查看', 'create': '新建', 'update': '修改', 'delete': '删除',
}
OBJECTS = (
    ('employee', '员工'),
    ('employee_shift_assignment', '员工排班'),
)

PERMISSIONS = tuple(
    ('{0}:{0}_{1}'.format(bo, action),
     '{0}{1}'.format(label, _ACTION_LABEL[action]), bo, action)
    for bo, label in OBJECTS
    for action in ACTIONS
)

GRANT_TO_SETS = ('admin', 'default')

MENUS = (
    {'menu_code': 'employee-list', 'menu_name': '员工',
     'menu_path': '/master-data/employee',
     'primary_object_type': 'employee',
     'icon': 'User', 'color': '#0ea5e9', 'sort_order': 102,
     'description': '员工薄主数据（雇佣组织 / 地点 / 岗位 / 在职区间）'},
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


def _create_index(conn: sqlite3.Connection, name: str, table: str, sql: str) -> None:
    if _index_exists(conn, name):
        print(f'  - [SKIP] 索引 {name} 已存在')
        return
    if not _table_exists(conn, table):
        print(f'  - [SKIP] 索引 {name} 依赖表 {table} 不存在')
        return
    try:
        conn.execute(sql)
        print(f'  - [ADD] 索引 {name}')
    except sqlite3.IntegrityError as e:
        print(f'  - [FAIL] 索引 {name}: {e}')
        raise


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, table, sql in INDEXES:
        _create_index(conn, name, table, sql)
    for name, table, sql in UNIQUE_KEYS:
        _create_index(conn, name, table, sql)


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
    print(f'  - [WARN] 父菜单 {PARENT_MENU} 不存在，菜单挂顶层（parent_menu=""）')
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
        print(f'[v185] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v185] 开始: 统一资源模型 P3（员工薄主数据 + 员工排班）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        conn.commit()
        print('[v185] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v185] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v185 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            EMPLOYEES_TABLE: ('employee_no', 'name', 'person_profile_id', 'user_id',
                              'org_id', 'location_id', 'position', 'job_grade',
                              'employment_type', 'status', 'hire_date',
                              'termination_date', 'manager_employee_id'),
            ASSIGNMENTS_TABLE: ('employee_id', 'shift_id', 'day_mask_mon',
                                'day_mask_tue', 'day_mask_wed', 'day_mask_thu',
                                'day_mask_fri', 'day_mask_sat', 'day_mask_sun',
                                'seq', 'effective_from', 'effective_to',
                                'work_center_id', 'note'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v185 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v185 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _table, _sql in INDEXES + UNIQUE_KEYS:
            if not _index_exists(conn, name):
                print(f'[v185 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute(
                    'SELECT 1 FROM enum_types WHERE id=?', (type_id,)
                ).fetchone():
                    print(f'[v185 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        (type_id, code),
                    ).fetchone():
                        print(f'[v185 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v185 verify] FAIL: 缺权限 {code}')
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
                    print(f"[v185 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False
                    continue
                if row[0] != 1:
                    print(f"[v185 verify] FAIL: 菜单 {menu['menu_code']} 未启用")
                    ok = False
                if row[2] != menu['primary_object_type']:
                    print(f"[v185 verify] FAIL: 菜单 {menu['menu_code']} primary_object_type")
                    ok = False
                if row[3] != 0:
                    print(f"[v185 verify] FAIL: 菜单 {menu['menu_code']} show_in_sidebar")
                    ok = False
                if row[4] != menu['sort_order']:
                    print(f"[v185 verify] FAIL: 菜单 {menu['menu_code']} sort_order")
                    ok = False
                if has_parent and row[1] != PARENT_MENU:
                    print(f"[v185 verify] FAIL: 菜单 {menu['menu_code']} 未挂 {PARENT_MENU}")
                    ok = False

        print('[v185 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v185 rollback] DB 不存在: {db_path}')
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
        print('  - [DROP] 员工菜单')

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
            print(f'  - [DROP] {len(codes)} 条 P3 权限（含权限集授权行）')

        for name, _table, _sql in tuple(INDEXES) + tuple(UNIQUE_KEYS):
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for name, _ddl in TABLES:
            if _table_exists(conn, name):
                conn.execute(f'DROP TABLE IF EXISTS {name}')
                print(f'  - [DROP] 表 {name}')

        conn.commit()
        print('[v185 rollback] 完成（枚举种子保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v185 rollback] 失败: {e}')
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
