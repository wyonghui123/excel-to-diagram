# -*- coding: utf-8 -*-
"""[v182 2026-11-01] 工时记录 `time_entry` + 工时回聚派生视图（项目侧 G14）

依据:
  docs/specs/tasks-project-g14-labor-view-2026-11-01.md §3 Phase 1 / Phase 2
  docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md FR-004 / FR-008

设计:
  · Phase 1：`time_entries` 表由 `meta/schemas/time_entry.yaml` 声明，
    sync_schema 生成 DDL；本迁移对存量库做「兜底 CREATE + 5 索引 + 权限 + 手工菜单」
  · Phase 2：三张只读派生视图（D11 / D15，不落汇总表）
      - v_project_task_labor   任务级（JOIN project_tasks）
      - v_project_labor        项目级（COALESCE(任务.project_id, 工单.project_id)）
      - v_resource_labor_daily 资源 × 日（纯实际，不塞产能；利用率由服务层算）
  · 工时桥只落 time_entries 行；`work_order_operation` 不加 project_task_id（D14）
  · 成本字段（rate_id / cost_amount）留阶段二（D17）

幂等:
  表 / 索引 / 权限 / 菜单先查后用；视图每次 DROP + CREATE。
  重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删视图 → 删索引 → 删表 → 删菜单（menu_permissions / menus）；
  **保留** permissions 行（可能已被角色授予）。
"""
import json
import sqlite3
import sys
from pathlib import Path

TIME_ENTRY_TABLE = 'time_entries'

# 列序与 sync_schema 生成 DDL 一致（audit_aspect 注入 created_by/updated_by 置首）
TIME_ENTRY_DDL = """
CREATE TABLE IF NOT EXISTS time_entries (
    created_by              VARCHAR(200),
    updated_by              VARCHAR(200),
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    work_date               DATETIME NOT NULL,
    resource_id             INTEGER NOT NULL,
    minutes                 INTEGER NOT NULL,
    project_task_id         INTEGER,
    work_order_id           INTEGER,
    work_order_operation_id INTEGER,
    resource_assignment_id  INTEGER,
    entry_type              VARCHAR(200) NOT NULL DEFAULT 'manual',
    billable                INTEGER NOT NULL DEFAULT 1,
    note                    VARCHAR(200),
    created_at              DATETIME,
    updated_at              DATETIME,
    FOREIGN KEY (resource_id) REFERENCES resources(id),
    FOREIGN KEY (project_task_id) REFERENCES project_tasks(id),
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id),
    FOREIGN KEY (work_order_operation_id) REFERENCES work_order_operations(id),
    FOREIGN KEY (resource_assignment_id) REFERENCES resource_assignments(id)
)
"""

INDEXES = (
    ('idx_time_entry_task_date', TIME_ENTRY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_time_entry_task_date '
     'ON time_entries(project_task_id, work_date)'),
    ('idx_time_entry_resource_date', TIME_ENTRY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_time_entry_resource_date '
     'ON time_entries(resource_id, work_date)'),
    ('idx_time_entry_wo', TIME_ENTRY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_time_entry_wo '
     'ON time_entries(work_order_id)'),
    ('idx_time_entry_operation', TIME_ENTRY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_time_entry_operation '
     'ON time_entries(work_order_operation_id)'),
    ('idx_time_entry_assignment', TIME_ENTRY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_time_entry_assignment '
     'ON time_entries(resource_assignment_id)'),
)

REQUIRED_COLUMNS = {
    TIME_ENTRY_TABLE: ('work_date', 'resource_id', 'minutes', 'project_task_id',
                       'work_order_id', 'work_order_operation_id',
                       'resource_assignment_id', 'entry_type', 'billable',
                       'note', 'created_at', 'updated_at'),
}

ACTIONS = ('create', 'read', 'update', 'delete', 'list')
_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

PERMISSIONS = tuple(
    (f'project:time_entry_{a}', f'{_ACTION_LABEL[a]}工时记录', 'project', a)
    for a in ACTIONS
)

TIME_ENTRY_MENU = {
    'menu_code': 'time-entry',
    'menu_name': '工时记录',
    'menu_path': '/time-entries',
    'page_type': 'object_list',
    'primary_object_type': 'time_entry',
    'object_types': ['time_entry'],
    'bo_bindings': [
        {'bo_id': 'time_entry', 'role': 'primary', 'include_actions': list(ACTIONS)},
    ],
    'required_permissions': [p[0] for p in PERMISSIONS],
    'parent_menu': 'sales',
    'icon': 'Clock',
    'color': '#14b8a6',
    'description': '工时记录：资源 × 日期 × 分钟，挂项目任务 / 工单工序',
    'sort_order': 4,
    'is_active': 1,
    'show_in_sidebar': 1,
    'auto_generated': 0,
    'data_permission_hint': {
        'resource_types': ['project'],
        'message': '工时记录沿用项目的业务实体（org）数据权限口径',
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 派生视图（SELECT 中不复制金额，只 SUM / COUNT / MIN / MAX）
# ─────────────────────────────────────────────────────────────────────────────

VIEW_DEFINITIONS = (
    ('v_project_task_labor', """
SELECT pt.project_id,
       pt.id AS project_task_id,
       pt.task_no,
       pt.name AS task_name,
       pt.status,
       SUM(te.minutes) AS actual_minutes,
       ROUND(SUM(te.minutes) / 60.0, 2) AS actual_hours,
       SUM(CASE WHEN te.billable = 1 THEN te.minutes ELSE 0 END) AS billable_minutes,
       COUNT(te.id) AS entry_count,
       COUNT(DISTINCT te.resource_id) AS resource_count,
       MIN(te.work_date) AS first_work_date,
       MAX(te.work_date) AS last_work_date
FROM time_entries te
JOIN project_tasks pt ON pt.id = te.project_task_id
GROUP BY pt.project_id, pt.id
"""),
    ('v_project_labor', """
WITH resolved AS (
    SELECT te.id,
           te.minutes,
           te.billable,
           te.resource_id,
           te.work_date,
           te.project_task_id,
           COALESCE(pt.project_id, wo.project_id) AS project_id
    FROM time_entries te
    LEFT JOIN project_tasks pt ON pt.id = te.project_task_id
    LEFT JOIN work_orders wo ON wo.id = te.work_order_id
)
SELECT r.project_id,
       p.project_no,
       p.name AS project_name,
       SUM(r.minutes) AS actual_minutes,
       ROUND(SUM(r.minutes) / 60.0, 2) AS actual_hours,
       SUM(CASE WHEN r.billable = 1 THEN r.minutes ELSE 0 END) AS billable_minutes,
       COUNT(DISTINCT r.project_task_id) AS task_count,
       COUNT(DISTINCT r.resource_id) AS resource_count,
       COUNT(r.id) AS entry_count,
       MAX(r.work_date) AS last_work_date
FROM resolved r
JOIN projects p ON p.id = r.project_id
WHERE r.project_id IS NOT NULL
GROUP BY r.project_id
"""),
    ('v_resource_labor_daily', """
SELECT te.resource_id,
       te.work_date,
       SUM(te.minutes) AS actual_minutes,
       SUM(CASE WHEN te.billable = 1 THEN te.minutes ELSE 0 END) AS billable_minutes,
       COUNT(te.id) AS entry_count,
       COUNT(DISTINCT COALESCE(pt.project_id, wo.project_id)) AS project_count
FROM time_entries te
LEFT JOIN project_tasks pt ON pt.id = te.project_task_id
LEFT JOIN work_orders wo ON wo.id = te.work_order_id
GROUP BY te.resource_id, te.work_date
"""),
)


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


def _view_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name=?", (name,)
    ).fetchone() is not None


def create_views(conn: sqlite3.Connection) -> None:
    """先 DROP VIEW IF EXISTS 再 CREATE VIEW，保证重复执行收敛到同一份 SQL。"""
    for name, sql in VIEW_DEFINITIONS:
        conn.execute('DROP VIEW IF EXISTS {0}'.format(name))
        conn.execute('CREATE VIEW {0} AS {1}'.format(name, sql))
        print('  - [VIEW] {0}'.format(name))


def _do_table(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, TIME_ENTRY_TABLE):
        print('  - [SKIP] 表 {0} 已存在'.format(TIME_ENTRY_TABLE))
        return
    conn.execute(TIME_ENTRY_DDL)
    print('  - [CREATE] 表 {0}'.format(TIME_ENTRY_TABLE))


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
        'SELECT 1 FROM menus WHERE menu_code=?', (TIME_ENTRY_MENU['menu_code'],)
    ).fetchone()
    if exists:
        print("  - [SKIP] 菜单 {0} 已存在".format(TIME_ENTRY_MENU['menu_code']))
    else:
        conn.execute(
            "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
            "object_types, primary_object_type, bo_bindings, required_permissions, "
            "parent_menu, icon, color, description, sort_order, is_active, "
            "show_in_sidebar, auto_generated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                TIME_ENTRY_MENU['menu_code'], TIME_ENTRY_MENU['menu_name'],
                TIME_ENTRY_MENU['menu_path'], TIME_ENTRY_MENU['page_type'],
                json.dumps(TIME_ENTRY_MENU['object_types'], ensure_ascii=False),
                TIME_ENTRY_MENU['primary_object_type'],
                json.dumps(TIME_ENTRY_MENU['bo_bindings'], ensure_ascii=False),
                json.dumps(TIME_ENTRY_MENU['required_permissions'], ensure_ascii=False),
                TIME_ENTRY_MENU['parent_menu'], TIME_ENTRY_MENU['icon'],
                TIME_ENTRY_MENU['color'], TIME_ENTRY_MENU['description'],
                TIME_ENTRY_MENU['sort_order'], TIME_ENTRY_MENU['is_active'],
                TIME_ENTRY_MENU['show_in_sidebar'], TIME_ENTRY_MENU['auto_generated'],
            ),
        )
        print("  - [NEW] 菜单 {0}".format(TIME_ENTRY_MENU['menu_code']))

    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, menu_path, "
            "required_permissions, required_any_permission, parent_menu, icon, "
            "sort_order, is_active, data_permission_hint) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (
                TIME_ENTRY_MENU['menu_code'], TIME_ENTRY_MENU['menu_name'],
                TIME_ENTRY_MENU['menu_path'],
                json.dumps(TIME_ENTRY_MENU['required_permissions'], ensure_ascii=False),
                TIME_ENTRY_MENU['parent_menu'], TIME_ENTRY_MENU['icon'],
                TIME_ENTRY_MENU['sort_order'], TIME_ENTRY_MENU['is_active'],
                json.dumps(TIME_ENTRY_MENU['data_permission_hint'], ensure_ascii=False),
            ),
        )
        if cur.rowcount:
            print("  - [NEW] menu_permissions: {0}".format(TIME_ENTRY_MENU['menu_code']))
        else:
            print("  - [SKIP] menu_permissions: {0} 已存在".format(
                TIME_ENTRY_MENU['menu_code']))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v182] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v182] 开始: 工时记录 time_entry + 工时回聚视图（G14）')
        _do_table(conn)
        _do_indexes(conn)
        _do_permissions(conn)
        _do_menu(conn)
        create_views(conn)
        conn.commit()
        print('[v182] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v182] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v182 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table, cols in REQUIRED_COLUMNS.items():
            if not _table_exists(conn, table):
                print('[v182 verify] FAIL: 缺表 {0}'.format(table))
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print('[v182 verify] FAIL: 缺列 {0}.{1}'.format(table, col))
                    ok = False
        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v182 verify] FAIL: 缺索引 {0}'.format(name))
                ok = False
        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                        'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print('[v182 verify] FAIL: 缺权限 {0}'.format(code))
                    ok = False
        if _table_exists(conn, 'menus'):
            row = conn.execute(
                'SELECT is_active FROM menus WHERE menu_code=?',
                (TIME_ENTRY_MENU['menu_code'],)
            ).fetchone()
            if not row:
                print('[v182 verify] FAIL: 缺菜单 {0}'.format(
                    TIME_ENTRY_MENU['menu_code']))
                ok = False
            elif row[0] != 1:
                print('[v182 verify] FAIL: 菜单 {0} 未启用'.format(
                    TIME_ENTRY_MENU['menu_code']))
                ok = False
        # SQLite 视图延迟解析：不 SELECT 等于没建
        for name, _sql in VIEW_DEFINITIONS:
            if not _view_exists(conn, name):
                print('[v182 verify] FAIL: 缺视图 {0}'.format(name))
                ok = False
                continue
            try:
                conn.execute('SELECT * FROM {0} LIMIT 1'.format(name)).fetchone()
            except sqlite3.Error as e:
                print('[v182 verify] FAIL: 视图 {0} 无法查询: {1}'.format(name, e))
                ok = False
        print('[v182 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v182 rollback] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _sql in VIEW_DEFINITIONS:
            if _view_exists(conn, name):
                conn.execute('DROP VIEW IF EXISTS {0}'.format(name))
                print('  - [DROP] 视图 {0}'.format(name))

        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute('DROP INDEX IF EXISTS {0}'.format(name))
                print('  - [DROP] 索引 {0}'.format(name))

        if _table_exists(conn, TIME_ENTRY_TABLE):
            conn.execute('DROP TABLE IF EXISTS {0}'.format(TIME_ENTRY_TABLE))
            print('  - [DROP] 表 {0}'.format(TIME_ENTRY_TABLE))

        if _table_exists(conn, 'menu_permissions'):
            conn.execute(
                'DELETE FROM menu_permissions WHERE menu_code=?',
                (TIME_ENTRY_MENU['menu_code'],),
            )
        if _table_exists(conn, 'menus'):
            conn.execute(
                'DELETE FROM menus WHERE menu_code=?', (TIME_ENTRY_MENU['menu_code'],)
            )
            print('  - [DROP] 菜单 {0}'.format(TIME_ENTRY_MENU['menu_code']))

        conn.commit()
        print('[v182 rollback] 完成（permissions 行保留）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v182 rollback] 失败: %s' % e)
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
