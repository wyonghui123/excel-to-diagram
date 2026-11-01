# -*- coding: utf-8 -*-
"""[v179 2026-11-01] 计划层 `project_task` + 依赖边（项目侧 P1.5 / G11）

依据:
  docs/specs/spec-project-type-object-model-research-2026-10-31.md
    §2.5 计划层 / §5 Phase 1.5 / §6 AC-09 / §8.2 红线
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §0.1 P1.5

设计:
  · `project_task` / `project_task_dependency` 由 `meta/schemas/*.yaml` 声明、
    sync_schema 生成 DDL；本迁移对存量库做「断言 + 兜底 CREATE + 索引 + 权限 + 菜单」
  · 计划只产需求不产动作：两张表不生成 `tasks`、不写 `work_order_operation`
  · 需求入口由 `work_order.source_demand_type` 扩 `project_task`（G11，服务层校验同项目）
  · 工时回聚派生视图依赖 G7（Gen2 任务六表进元模型），本迁移不做

幂等:
  表 / 索引 / 权限 / 菜单先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删菜单行 + 删索引 + 删两张表；**保留** permissions 行（可能已被角色授予）。
"""
import json
import sqlite3
import sys
from pathlib import Path

TASK_TABLE = 'project_tasks'
DEPENDENCY_TABLE = 'project_task_dependencies'

TASK_DDL = """
CREATE TABLE IF NOT EXISTS project_tasks (
    created_by              VARCHAR(200),
    updated_by              VARCHAR(200),
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id              INTEGER NOT NULL,
    parent_task_id          INTEGER,
    task_no                 VARCHAR(200) NOT NULL,
    name                    VARCHAR(200) NOT NULL,
    task_type               VARCHAR(200) NOT NULL DEFAULT 'activity',
    status                  VARCHAR(200) NOT NULL DEFAULT 'draft',
    planned_start           DATETIME,
    planned_end             DATETIME,
    percent_complete        REAL DEFAULT 0,
    owner_user_id           INTEGER,
    description             TEXT,
    created_at              DATETIME,
    updated_at              DATETIME,
    FOREIGN KEY (project_id) REFERENCES projects(id)
)
"""

DEPENDENCY_DDL = """
CREATE TABLE IF NOT EXISTS project_task_dependencies (
    created_by              VARCHAR(200),
    updated_by              VARCHAR(200),
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    predecessor_task_id     INTEGER NOT NULL,
    successor_task_id       INTEGER NOT NULL,
    dependency_type         VARCHAR(200) NOT NULL DEFAULT 'FS',
    lag_minutes             INTEGER NOT NULL DEFAULT 0,
    created_at              DATETIME,
    updated_at              DATETIME,
    FOREIGN KEY (predecessor_task_id) REFERENCES project_tasks(id),
    FOREIGN KEY (successor_task_id) REFERENCES project_tasks(id)
)
"""

INDEXES = (
    ('uidx_project_task_no', TASK_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_project_task_no '
     'ON project_tasks(project_id, task_no)'),
    ('idx_project_task_project_status', TASK_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_project_task_project_status '
     'ON project_tasks(project_id, status)'),
    ('idx_project_task_parent', TASK_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_project_task_parent '
     'ON project_tasks(parent_task_id)'),
    ('idx_project_task_owner', TASK_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_project_task_owner '
     'ON project_tasks(owner_user_id)'),
    ('uidx_ptd_edge', DEPENDENCY_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_ptd_edge '
     'ON project_task_dependencies(predecessor_task_id, successor_task_id, '
     'dependency_type)'),
    ('idx_ptd_successor', DEPENDENCY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_ptd_successor '
     'ON project_task_dependencies(successor_task_id)'),
)

REQUIRED_COLUMNS = {
    TASK_TABLE: ('project_id', 'parent_task_id', 'task_no', 'name', 'task_type',
                 'status', 'planned_start', 'planned_end', 'percent_complete',
                 'owner_user_id', 'description'),
    DEPENDENCY_TABLE: ('predecessor_task_id', 'successor_task_id',
                       'dependency_type', 'lag_minutes'),
}

ACTIONS = ('create', 'read', 'update', 'delete', 'list')
_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

PERMISSIONS = tuple(
    (f'project:project_task_{a}', f'{_ACTION_LABEL[a]}项目活动', 'project', a)
    for a in ACTIONS
)

TASK_MENU = {
    'menu_code': 'project-task',
    'menu_name': '项目活动',
    'menu_path': '/project-tasks',
    'page_type': 'object_list',
    'primary_object_type': 'project_task',
    'object_types': ['project_task'],
    'bo_bindings': [
        {'bo_id': 'project_task', 'role': 'primary', 'include_actions': list(ACTIONS)},
    ],
    'required_permissions': [p[0] for p in PERMISSIONS],
    'parent_menu': 'sales',
    'icon': 'ListChecks',
    'color': '#8b5cf6',
    'description': '项目活动：计划层 WBS 节点（阶段 / 工作包 / 活动），只产需求不产动作',
    'sort_order': 3,
    'is_active': 1,
    'show_in_sidebar': 1,
    'auto_generated': 0,
    'data_permission_hint': {
        'resource_types': ['project'],
        'message': '项目活动沿用项目的业务实体（org）数据权限口径',
    },
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute('PRAGMA table_info({0})'.format(table))}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _do_table(conn: sqlite3.Connection, table: str, ddl: str) -> None:
    if _table_exists(conn, table):
        print('  - [SKIP] 表 {0} 已存在'.format(table))
        return
    conn.execute(ddl)
    print('  - [CREATE] 表 {0}'.format(table))


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, table, sql in INDEXES:
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 {0} 已存在'.format(name))
            continue
        if not _table_exists(conn, table):
            print('  - [SKIP] 索引 {0} 依赖表 {1} 不存在'.format(name, table))
            continue
        conn.execute(sql)
        print('  - [ADD] 索引 {0}'.format(name))


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
            print('  - [NEW] 权限 {0} ({1})'.format(code, name))
    print('  - [SUMMARY] permissions: +{0} 新增'.format(created))


def _do_menu(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return
    exists = conn.execute(
        'SELECT 1 FROM menus WHERE menu_code=?', (TASK_MENU['menu_code'],)
    ).fetchone()
    if exists:
        print("  - [SKIP] 菜单 {0} 已存在".format(TASK_MENU['menu_code']))
    else:
        conn.execute(
            "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
            "object_types, primary_object_type, bo_bindings, required_permissions, "
            "parent_menu, icon, color, description, sort_order, is_active, "
            "show_in_sidebar, auto_generated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                TASK_MENU['menu_code'], TASK_MENU['menu_name'],
                TASK_MENU['menu_path'], TASK_MENU['page_type'],
                json.dumps(TASK_MENU['object_types'], ensure_ascii=False),
                TASK_MENU['primary_object_type'],
                json.dumps(TASK_MENU['bo_bindings'], ensure_ascii=False),
                json.dumps(TASK_MENU['required_permissions'], ensure_ascii=False),
                TASK_MENU['parent_menu'], TASK_MENU['icon'],
                TASK_MENU['color'], TASK_MENU['description'],
                TASK_MENU['sort_order'], TASK_MENU['is_active'],
                TASK_MENU['show_in_sidebar'], TASK_MENU['auto_generated'],
            ),
        )
        print("  - [NEW] 菜单 {0}".format(TASK_MENU['menu_code']))

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, menu_path, "
            "required_permissions, required_any_permission, parent_menu, icon, "
            "sort_order, is_active, data_permission_hint) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (
                TASK_MENU['menu_code'], TASK_MENU['menu_name'],
                TASK_MENU['menu_path'],
                json.dumps(TASK_MENU['required_permissions'], ensure_ascii=False),
                TASK_MENU['parent_menu'], TASK_MENU['icon'],
                TASK_MENU['sort_order'], TASK_MENU['is_active'],
                json.dumps(TASK_MENU['data_permission_hint'], ensure_ascii=False),
            ),
        )
        if cur.rowcount:
            print("  - [NEW] menu_permissions: {0}".format(TASK_MENU['menu_code']))
        else:
            print("  - [SKIP] menu_permissions: {0} 已存在".format(
                TASK_MENU['menu_code']))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v179] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v179] 开始: 计划层 project_task + 依赖边（P1.5 / G11）')
        _do_table(conn, TASK_TABLE, TASK_DDL)
        _do_table(conn, DEPENDENCY_TABLE, DEPENDENCY_DDL)
        _do_indexes(conn)
        _do_permissions(conn)
        _do_menu(conn)
        conn.commit()
        print('[v179] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v179] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v179 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table, cols in REQUIRED_COLUMNS.items():
            if not _table_exists(conn, table):
                print('[v179 verify] FAIL: 缺表 {0}'.format(table))
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print('[v179 verify] FAIL: 缺列 {0}.{1}'.format(table, col))
                    ok = False
        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v179 verify] FAIL: 缺索引 {0}'.format(name))
                ok = False
        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                        'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print('[v179 verify] FAIL: 缺权限 {0}'.format(code))
                    ok = False
        if _table_exists(conn, 'menus'):
            row = conn.execute(
                'SELECT is_active FROM menus WHERE menu_code=?',
                (TASK_MENU['menu_code'],)
            ).fetchone()
            if not row:
                print('[v179 verify] FAIL: 缺菜单 {0}'.format(
                    TASK_MENU['menu_code']))
                ok = False
            elif row[0] != 1:
                print('[v179 verify] FAIL: 菜单 {0} 未启用'.format(
                    TASK_MENU['menu_code']))
                ok = False
        print('[v179 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v179 rollback] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _table_exists(conn, 'menu_permissions'):
            conn.execute(
                'DELETE FROM menu_permissions WHERE menu_code=?',
                (TASK_MENU['menu_code'],),
            )
        if _table_exists(conn, 'menus'):
            conn.execute(
                'DELETE FROM menus WHERE menu_code=?', (TASK_MENU['menu_code'],)
            )
            print('  - [DROP] 菜单 {0}'.format(TASK_MENU['menu_code']))

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute('DROP INDEX IF EXISTS {0}'.format(name))
                print('  - [DROP] 索引 {0}'.format(name))

        for table in (DEPENDENCY_TABLE, TASK_TABLE):
            if _table_exists(conn, table):
                conn.execute('DROP TABLE IF EXISTS {0}'.format(table))
                print('  - [DROP] 表 {0}'.format(table))

        conn.commit()
        print('[v179 rollback] 完成（permissions 行保留）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v179 rollback] 失败: %s' % e)
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
