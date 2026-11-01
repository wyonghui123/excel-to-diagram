# -*- coding: utf-8 -*-
"""[v172 2026-11-01] 项目对象地基（项目侧 P1）

依据:
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §0.1 P1
  docs/specs/spec-project-type-object-model-research-2026-10-31.md
    §2.1 商务层 / §5 Phase 1 / §6 AC-01~AC-03

设计:
  · `project` 表由 `meta/schemas/project.yaml` 声明、sync_schema 生成；
    本迁移只做「断言 + 兜底 CREATE + 补索引 + 权限 + 菜单」
  · 三处可空挂载（sales_orders / sales_order_lines / sales_order_schedules 的
    project_id）同样由 YAML 声明，本迁移对存量库补 ALTER COLUMN
  · 项目类型不建新枚举列，走 type_definitions(scope_bo='project' + level='header')（D2）
  · 菜单挂在 `sales` 分组下；同时需在 meta/scripts/init_menu_permissions.py 声明，
    否则步骤 7.6 会把该手工菜单当冗余删除

幂等:
  表 / 列 / 索引 / 菜单先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删菜单行 + 删索引 + 删表；**保留** permissions 行（可能已被角色授予），
  三处 project_id 列保留（SQLite 删列不可逆，且空值不影响旧链路）。
"""
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_TABLE = 'projects'
SALES_ORDER_TABLE = 'sales_orders'
SALES_ORDER_LINE_TABLE = 'sales_order_lines'
SALES_ORDER_SCHEDULE_TABLE = 'sales_order_schedules'

MOUNT_TABLES = (
    SALES_ORDER_TABLE,
    SALES_ORDER_LINE_TABLE,
    SALES_ORDER_SCHEDULE_TABLE,
)

PROJECT_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    created_by              VARCHAR(200),
    updated_by              VARCHAR(200),
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_no              VARCHAR(200) NOT NULL,
    name                    VARCHAR(200) NOT NULL,
    project_type_id         INTEGER NOT NULL,
    status                  VARCHAR(200) NOT NULL DEFAULT 'draft',
    org_id                  INTEGER NOT NULL,
    customer_account_id     INTEGER,
    manager_user_id         INTEGER,
    start_date              DATETIME,
    end_date                DATETIME,
    budget_amount           REAL,
    currency_id             INTEGER,
    description             TEXT,
    created_at              DATETIME,
    updated_at              DATETIME,
    FOREIGN KEY (project_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id),
    FOREIGN KEY (manager_user_id) REFERENCES users(id),
    FOREIGN KEY (currency_id) REFERENCES currencies(id)
)
"""

INDEXES = (
    ('uidx_project_no', PROJECT_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_project_no ON projects(project_no)'),
    ('idx_project_type', PROJECT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_project_type ON projects(project_type_id)'),
    ('idx_project_org_status', PROJECT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_project_org_status ON projects(org_id, status)'),
    ('idx_project_customer', PROJECT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_project_customer ON projects(customer_account_id)'),
    ('idx_project_manager', PROJECT_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_project_manager ON projects(manager_user_id)'),
    ('idx_sales_order_project', SALES_ORDER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_sales_order_project ON sales_orders(project_id)'),
    ('idx_sales_order_line_project', SALES_ORDER_LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_sales_order_line_project '
     'ON sales_order_lines(project_id)'),
    ('idx_schedule_project', SALES_ORDER_SCHEDULE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_schedule_project '
     'ON sales_order_schedules(project_id)'),
)

ACTIONS = ('create', 'read', 'update', 'delete', 'list')
_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

PERMISSIONS = tuple(
    (f'project:project_{a}', f'{_ACTION_LABEL[a]}项目', 'project', a)
    for a in ACTIONS
)

PROJECT_MENU = {
    'menu_code': 'project-management',
    'menu_name': '项目',
    'menu_path': '/projects',
    'page_type': 'object_list',
    'primary_object_type': 'project',
    'object_types': ['project'],
    'bo_bindings': [
        {'bo_id': 'project', 'role': 'primary', 'include_actions': list(ACTIONS)},
    ],
    'required_permissions': [p[0] for p in PERMISSIONS],
    'parent_menu': 'sales',
    'icon': 'Folder',
    'color': '#8b5cf6',
    'description': '项目：商务层归集对象，挂载销售订单 / 订单行 / 计划行',
    'sort_order': 2,
    'is_active': 1,
    'show_in_sidebar': 0,
    'auto_generated': 0,
    'data_permission_hint': {
        'resource_types': ['project'],
        'message': '项目暂不进入权限维度链（D8），沿用业务实体（org）维度',
    },
}


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


def _do_table(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, PROJECT_TABLE):
        print(f'  - [SKIP] 表 {PROJECT_TABLE} 已存在')
    else:
        conn.execute(PROJECT_DDL)
        print(f'  - [CREATE] 表 {PROJECT_TABLE}')


def _do_mount_columns(conn: sqlite3.Connection) -> None:
    for table in MOUNT_TABLES:
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 表 {table} 不存在（由各自波次迁移负责）')
            continue
        if 'project_id' in _columns(conn, table):
            print(f'  - [SKIP] 列 {table}.project_id 已存在')
        else:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN project_id INTEGER NULL')
            print(f'  - [ALTER] 列 {table}.project_id')


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


def _do_menu(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return
    exists = conn.execute(
        'SELECT 1 FROM menus WHERE menu_code=?', (PROJECT_MENU['menu_code'],)
    ).fetchone()
    if exists:
        print(f"  - [SKIP] 菜单 {PROJECT_MENU['menu_code']} 已存在")
    else:
        conn.execute(
            "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
            "object_types, primary_object_type, bo_bindings, required_permissions, "
            "parent_menu, icon, color, description, sort_order, is_active, "
            "show_in_sidebar, auto_generated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                PROJECT_MENU['menu_code'], PROJECT_MENU['menu_name'],
                PROJECT_MENU['menu_path'], PROJECT_MENU['page_type'],
                json.dumps(PROJECT_MENU['object_types'], ensure_ascii=False),
                PROJECT_MENU['primary_object_type'],
                json.dumps(PROJECT_MENU['bo_bindings'], ensure_ascii=False),
                json.dumps(PROJECT_MENU['required_permissions'], ensure_ascii=False),
                PROJECT_MENU['parent_menu'], PROJECT_MENU['icon'],
                PROJECT_MENU['color'], PROJECT_MENU['description'],
                PROJECT_MENU['sort_order'], PROJECT_MENU['is_active'],
                PROJECT_MENU['show_in_sidebar'], PROJECT_MENU['auto_generated'],
            ),
        )
        print(f"  - [NEW] 菜单 {PROJECT_MENU['menu_code']}")

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, menu_path, "
            "required_permissions, required_any_permission, parent_menu, icon, "
            "sort_order, is_active, data_permission_hint) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (
                PROJECT_MENU['menu_code'], PROJECT_MENU['menu_name'],
                PROJECT_MENU['menu_path'],
                json.dumps(PROJECT_MENU['required_permissions'], ensure_ascii=False),
                PROJECT_MENU['parent_menu'], PROJECT_MENU['icon'],
                PROJECT_MENU['sort_order'], PROJECT_MENU['is_active'],
                json.dumps(PROJECT_MENU['data_permission_hint'], ensure_ascii=False),
            ),
        )
        if cur.rowcount:
            print(f"  - [NEW] menu_permissions: {PROJECT_MENU['menu_code']}")
        else:
            print(f"  - [SKIP] menu_permissions: {PROJECT_MENU['menu_code']} 已存在")


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v172] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v172] 开始: 项目对象地基（P1）')
        _do_table(conn)
        _do_mount_columns(conn)
        _do_indexes(conn)
        _do_permissions(conn)
        _do_menu(conn)
        conn.commit()
        print('[v172] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v172] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v172 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            PROJECT_TABLE: ('project_no', 'name', 'project_type_id', 'status',
                            'org_id', 'customer_account_id', 'manager_user_id',
                            'start_date', 'end_date', 'budget_amount',
                            'currency_id'),
            SALES_ORDER_TABLE: ('project_id',),
            SALES_ORDER_LINE_TABLE: ('project_id',),
            SALES_ORDER_SCHEDULE_TABLE: ('project_id',),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v172 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v172 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v172 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                        'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v172 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            row = conn.execute(
                'SELECT is_active FROM menus WHERE menu_code=?',
                (PROJECT_MENU['menu_code'],)
            ).fetchone()
            if not row:
                print(f"[v172 verify] FAIL: 缺菜单 {PROJECT_MENU['menu_code']}")
                ok = False
            elif row[0] != 1:
                print(f"[v172 verify] FAIL: 菜单 {PROJECT_MENU['menu_code']} 未启用")
                ok = False

        print('[v172 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v172 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _table_exists(conn, 'menu_permissions'):
            conn.execute(
                'DELETE FROM menu_permissions WHERE menu_code=?',
                (PROJECT_MENU['menu_code'],),
            )
        if _table_exists(conn, 'menus'):
            conn.execute(
                'DELETE FROM menus WHERE menu_code=?', (PROJECT_MENU['menu_code'],)
            )
            print(f"  - [DROP] 菜单 {PROJECT_MENU['menu_code']}")

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        if _table_exists(conn, PROJECT_TABLE):
            conn.execute(f'DROP TABLE IF EXISTS {PROJECT_TABLE}')
            print(f'  - [DROP] 表 {PROJECT_TABLE}')

        conn.commit()
        print('[v172 rollback] 完成（permissions 行与 project_id 列保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v172 rollback] 失败: %s' % e)
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
