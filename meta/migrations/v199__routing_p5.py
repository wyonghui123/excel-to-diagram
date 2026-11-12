# -*- coding: utf-8 -*-
"""[v199 2026-11-03] 路线分支/并行 + 批次等级 + 批次选择策略（P5）

依据:
  docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md §12
  docs/specs/p5-routing-branch-parallel-batch-selection/spec.md

设计:
  · `work_definition_sequences` 追加 branch_operation_seq / return_operation_seq /
    lot_min / lot_max / priority（裸列无 FK，服务层校验引用）。
  · `sequence_type` 补 `parallel`；新增 enum `batch_selection_scope` /
    `batch_selection_policy_status`。
  · 新建 `batch_selection_policies`：scope_type + scope_ref（业务编码）+ rule_json v1
    + priority + status；同范围 active priority 由部分唯一索引兜底。
  · `batches.grade_code`（VARCHAR(20)，可空）+ `idx_batches_grade(item_id, grade_code)`。
  · 权限 batch_selection_policy 4 条双段式，授予 admin / default。
  · 菜单 `batch-selection-policy-list` 挂 master-data，sort_order=106
    （104 已被 v196 批次、105 已被 v198 工程变更占用）。

幂等:
  列 / 表 / 索引 / 枚举 / 权限 / 授权 / 菜单先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单与 menu_permissions → 删权限与授权行 → 删索引 → 删策略表 → DROP COLUMN；
  枚举种子保留（避免删值破坏历史行）。
"""
import json
import sqlite3
import sys
from pathlib import Path

SEQUENCE_TABLE = 'work_definition_sequences'
BATCH_TABLE = 'batches'
POLICY_TABLE = 'batch_selection_policies'

ADDED_COLUMNS = (
    (SEQUENCE_TABLE, 'branch_operation_seq', 'INTEGER'),
    (SEQUENCE_TABLE, 'return_operation_seq', 'INTEGER'),
    (SEQUENCE_TABLE, 'lot_min', 'REAL'),
    (SEQUENCE_TABLE, 'lot_max', 'REAL'),
    (SEQUENCE_TABLE, 'priority', 'INTEGER NOT NULL DEFAULT 1'),
    (BATCH_TABLE, 'grade_code', 'VARCHAR(20)'),
)

TABLES = (
    (POLICY_TABLE, """
CREATE TABLE IF NOT EXISTS batch_selection_policies (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(128) NOT NULL,
    scope_type VARCHAR(20) NOT NULL,
    scope_ref VARCHAR(60) NOT NULL,
    rule_json TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    description VARCHAR(255),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (scope_type IN ('item', 'item_group', 'org')),
    CHECK (status IN ('active', 'inactive')),
    CHECK (priority >= 1)
)
"""),
)

INDEXES = (
    (SEQUENCE_TABLE, 'uq_work_definition_sequence_branch_priority',
     'CREATE UNIQUE INDEX IF NOT EXISTS '
     'uq_work_definition_sequence_branch_priority '
     'ON work_definition_sequences(definition_id, branch_operation_seq, priority) '
     "WHERE seq_type = 'alternative' AND branch_operation_seq IS NOT NULL"),
    (SEQUENCE_TABLE, 'idx_work_definition_sequence_branch',
     'CREATE INDEX IF NOT EXISTS idx_work_definition_sequence_branch '
     'ON work_definition_sequences(definition_id, branch_operation_seq)'),
    (POLICY_TABLE, 'uq_batch_selection_policy_code',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_selection_policy_code '
     'ON batch_selection_policies(code)'),
    (POLICY_TABLE, 'uq_batch_selection_policy_scope_priority',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_selection_policy_scope_priority '
     'ON batch_selection_policies(scope_type, scope_ref, priority) '
     "WHERE status = 'active'"),
    (POLICY_TABLE, 'idx_batch_selection_policy_scope',
     'CREATE INDEX IF NOT EXISTS idx_batch_selection_policy_scope '
     'ON batch_selection_policies(scope_type, scope_ref)'),
    (BATCH_TABLE, 'idx_batches_grade',
     'CREATE INDEX IF NOT EXISTS idx_batches_grade '
     'ON batches(item_id, grade_code)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('sequence_type', '序列类型', '路线序列类型（标准 / 并行 / 替代）',
     (('std', '标准', 'Standard'),
      ('alternative', '替代', 'Alternative'),
      ('parallel', '并行', 'Parallel'))),
    ('batch_selection_scope', '批次选择范围', '批次选择策略的适用范围层级',
     (('item', '物料', 'Item'),
      ('item_group', '物料分类', 'Item Group'),
      ('org', '组织', 'Organization'))),
    ('batch_selection_policy_status', '批次选择策略状态', '策略启用 / 停用',
     (('active', '启用', 'Active'),
      ('inactive', '停用', 'Inactive'))),
)

ACTIONS = ('read', 'create', 'update', 'delete')
_ACTION_LABEL = {
    'read': '查看', 'create': '新建', 'update': '修改', 'delete': '删除',
}
OBJECTS = (
    ('batch_selection_policy', '批次选择策略'),
)

PERMISSIONS = tuple(
    ('{0}:{0}_{1}'.format(bo, action),
     '{0}{1}'.format(label, _ACTION_LABEL[action]), bo, action)
    for bo, label in OBJECTS
    for action in ACTIONS
)

GRANT_TO_SETS = ('admin', 'default')

PARENT_MENU = 'master-data'
MENUS = (
    {'menu_code': 'batch-selection-policy-list', 'menu_name': '批次选择策略',
     'menu_path': '/master-data/batch-selection-policy',
     'primary_object_type': 'batch_selection_policy',
     'icon': 'SlidersHorizontal', 'color': '#8b5cf6', 'sort_order': 106,
     'description': '批次选择策略——按范围与优先级声明批次挑选规则'},
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


def _do_columns(conn: sqlite3.Connection) -> None:
    for table, name, ddl in ADDED_COLUMNS:
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 表 {table} 不存在，跳过列 {name}')
            continue
        if name in _columns(conn, table):
            print(f'  - [SKIP] 列 {table}.{name} 已存在')
            continue
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')
        print(f'  - [ADD] 列 {table}.{name}')


def _do_tables(conn: sqlite3.Connection) -> None:
    for name, ddl in TABLES:
        if _table_exists(conn, name):
            print(f'  - [SKIP] 表 {name} 已存在')
        else:
            conn.execute(ddl)
            print(f'  - [CREATE] 表 {name}')


def _create_index(conn: sqlite3.Connection, table: str, name: str, sql: str) -> None:
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
    for table, name, sql in INDEXES:
        _create_index(conn, table, name, sql)


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
        print(f'[v199] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v199] 开始: 路线分支/并行 + 批次等级 + 批次选择策略（P5）')
        _do_columns(conn)
        _do_tables(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        conn.commit()
        print('[v199] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v199] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v199 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, SEQUENCE_TABLE):
            print(f'[v199 verify] FAIL: 缺表 {SEQUENCE_TABLE}')
            ok = False
        else:
            have = _columns(conn, SEQUENCE_TABLE)
            for col in ('branch_operation_seq', 'return_operation_seq',
                        'lot_min', 'lot_max', 'priority'):
                if col not in have:
                    print(f'[v199 verify] FAIL: 缺列 {SEQUENCE_TABLE}.{col}')
                    ok = False
            info = {row[1]: row for row in conn.execute(
                f'PRAGMA table_info({SEQUENCE_TABLE})').fetchall()}
            priority = info.get('priority')
            if priority and (priority[3] != 1 or str(priority[4]) != '1'):
                print('[v199 verify] FAIL: priority 需 NOT NULL DEFAULT 1')
                ok = False

        if not _table_exists(conn, BATCH_TABLE):
            print(f'[v199 verify] FAIL: 缺表 {BATCH_TABLE}')
            ok = False
        elif 'grade_code' not in _columns(conn, BATCH_TABLE):
            print(f'[v199 verify] FAIL: 缺列 {BATCH_TABLE}.grade_code')
            ok = False

        if not _table_exists(conn, POLICY_TABLE):
            print(f'[v199 verify] FAIL: 缺表 {POLICY_TABLE}')
            ok = False

        for _table, name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v199 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute(
                    'SELECT 1 FROM enum_types WHERE id=?', (type_id,)
                ).fetchone():
                    print(f'[v199 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        (type_id, code),
                    ).fetchone():
                        print(f'[v199 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v199 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                if not conn.execute(
                    'SELECT 1 FROM menus WHERE menu_code=?', (menu['menu_code'],)
                ).fetchone():
                    print(f"[v199 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False

        print('[v199 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v199 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for menu in MENUS:
            if _table_exists(conn, 'menu_permissions'):
                conn.execute('DELETE FROM menu_permissions WHERE menu_code=?',
                             (menu['menu_code'],))
            if _table_exists(conn, 'menus'):
                conn.execute('DELETE FROM menus WHERE menu_code=?',
                             (menu['menu_code'],))
            print(f"  - [DROP] 菜单 {menu['menu_code']}")

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
            print(f'  - [DROP] {len(codes)} 条 P5 权限（含权限集授权行）')

        for _table, name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        if _table_exists(conn, POLICY_TABLE):
            conn.execute(f'DROP TABLE IF EXISTS {POLICY_TABLE}')
            print(f'  - [DROP] 表 {POLICY_TABLE}')

        for table, name, _ddl in reversed(ADDED_COLUMNS):
            if not _table_exists(conn, table):
                continue
            if name not in _columns(conn, table):
                continue
            conn.execute(f'ALTER TABLE {table} DROP COLUMN {name}')
            print(f'  - [DROP] 列 {table}.{name}')

        conn.commit()
        print('[v199 rollback] 完成（枚举种子保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v199 rollback] 失败: {e}')
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
