# -*- coding: utf-8 -*-
"""[v188 2026-11-01] 统一资源模型 P4a（生产版本 + 作业定义序列）

依据:
  docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
    §TBD-15（备选/并行工艺路线）/ §TBD-16（物料↔BOM↔路线版本绑定）/ 附 B
  docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md §5.2

设计:
  · `production_versions` = "某物料在某工厂、某批量区间、某有效期内走哪套 BOM +
    哪条路线"的唯一真源（对标 SAP Production Version）。
    物料 = 存量 `items`（target_bo: item）；工厂首期用 `orgs`。
  · `work_definition_sequences` = 工艺主数据内的路线序列（std / alternative）；
    与 `workflow_task` / `project_task` **不复用**（静态主数据 vs 运行态）。
    首期只实现整条替代路线，branch/return 与 parallel 放 P5，不提前建字段。
  · `work_definition_operations.sequence_id` 追加为**可空**列：存量行 NULL 视为
    标准序列。SQLite 的 `ALTER TABLE ADD COLUMN` 不接受 REFERENCES 子句，
    故存量库只加裸列（与平台 `SchemaMigrator` 行为一致）；全新建库由
    `meta/schemas/work_definition_operation.yaml` 的 relation 生成真外键。
  · 2 组枚举（5 个取值）种入 `enum_types` / `enum_values`。
  · 1 条菜单（生产版本）挂「主数据」父菜单，sort_order=103 接 v185 的 102；
    `work_definition_sequence` 是从表 ⇒ 不建独立菜单。
  · 权限码双段式 `{bo}:{bo}_{action}`，授予 admin / default 权限集。

幂等:
  表 / 列 / 索引 / 枚举 / 菜单 / 权限 / 授权先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单 + menu_permissions + 本迁移写入的 permissions / permission_set_permissions
  + 索引 + 两张表 + 尝试删除 sequence_id 列（SQLite ≥3.35，失败则保留并告警）；
  枚举种子保留（可能已被其他对象引用）。
"""
import json
import sqlite3
import sys
from pathlib import Path

PRODUCTION_VERSION_TABLE = 'production_versions'
SEQUENCE_TABLE = 'work_definition_sequences'
DEFINITION_OP_TABLE = 'work_definition_operations'
SEQUENCE_COLUMN = 'sequence_id'

PARENT_MENU = 'master-data'

TABLES = (
    (SEQUENCE_TABLE, """
CREATE TABLE IF NOT EXISTS work_definition_sequences (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    definition_id INTEGER NOT NULL,
    seq_no INTEGER NOT NULL,
    seq_type VARCHAR(200) NOT NULL DEFAULT 'std',
    description VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (definition_id) REFERENCES work_definitions(id)
)
"""),
    (PRODUCTION_VERSION_TABLE, """
CREATE TABLE IF NOT EXISTS production_versions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL,
    item_id INTEGER NOT NULL,
    org_id INTEGER NOT NULL,
    bom_id INTEGER,
    work_definition_id INTEGER NOT NULL,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME,
    lot_min REAL NOT NULL DEFAULT 0,
    lot_max REAL,
    priority INTEGER NOT NULL DEFAULT 1,
    locked INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    description VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (bom_id) REFERENCES item_structures(id),
    FOREIGN KEY (work_definition_id) REFERENCES work_definitions(id)
)
"""),
)

# 追加列（表, 列, DDL 片段）
ADDED_COLUMNS = (
    (DEFINITION_OP_TABLE, SEQUENCE_COLUMN, 'sequence_id INTEGER'),
)

INDEXES = (
    (SEQUENCE_TABLE, 'uq_work_definition_sequence_no',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_work_definition_sequence_no '
     'ON work_definition_sequences(definition_id, seq_no)'),
    (SEQUENCE_TABLE, 'idx_work_definition_sequence_type',
     'CREATE INDEX IF NOT EXISTS idx_work_definition_sequence_type '
     'ON work_definition_sequences(seq_type)'),
    (PRODUCTION_VERSION_TABLE, 'uq_production_version_code',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_production_version_code '
     'ON production_versions(code)'),
    (PRODUCTION_VERSION_TABLE, 'idx_production_version_item_org',
     'CREATE INDEX IF NOT EXISTS idx_production_version_item_org '
     'ON production_versions(item_id, org_id)'),
    (PRODUCTION_VERSION_TABLE, 'idx_production_version_work_definition',
     'CREATE INDEX IF NOT EXISTS idx_production_version_work_definition '
     'ON production_versions(work_definition_id)'),
    (PRODUCTION_VERSION_TABLE, 'idx_production_version_bom',
     'CREATE INDEX IF NOT EXISTS idx_production_version_bom '
     'ON production_versions(bom_id)'),
    (PRODUCTION_VERSION_TABLE, 'idx_production_version_status',
     'CREATE INDEX IF NOT EXISTS idx_production_version_status '
     'ON production_versions(status)'),
    (DEFINITION_OP_TABLE, 'idx_work_definition_operation_sequence',
     'CREATE INDEX IF NOT EXISTS idx_work_definition_operation_sequence '
     'ON work_definition_operations(sequence_id)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('sequence_type', '路线序列类型', '作业定义序列类型取值（首期仅标准/整条替代）',
     (('std', '标准', 'Standard'),
      ('alternative', '替代', 'Alternative'))),
    ('production_version_status', '生产版本状态', '生产版本状态取值',
     (('draft', '草稿', 'Draft'),
      ('active', '生效', 'Active'),
      ('obsolete', '作废', 'Obsolete'))),
)

ACTIONS = ('read', 'create', 'update', 'delete')
_ACTION_LABEL = {
    'read': '查看', 'create': '新建', 'update': '修改', 'delete': '删除',
}
OBJECTS = (
    ('production_version', '生产版本'),
    ('work_definition_sequence', '作业定义序列'),
)

PERMISSIONS = tuple(
    ('{0}:{0}_{1}'.format(bo, action),
     '{0}{1}'.format(label, _ACTION_LABEL[action]), bo, action)
    for bo, label in OBJECTS
    for action in ACTIONS
)

GRANT_TO_SETS = ('admin', 'default')

MENUS = (
    {'menu_code': 'production-version-list', 'menu_name': '生产版本',
     'menu_path': '/master-data/production-version',
     'primary_object_type': 'production_version',
     'icon': 'Layers', 'color': '#6366f1', 'sort_order': 103,
     'description': '生产版本——物料+工厂 ↔ BOM + 工艺路线（有效期 / 批量区间 / 优先级）'},
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


def _do_columns(conn: sqlite3.Connection) -> None:
    for table, column, ddl in ADDED_COLUMNS:
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 表 {table} 不存在, 跳过加列 {column}')
            continue
        if column in _columns(conn, table):
            print(f'  - [SKIP] 列 {table}.{column} 已存在')
            continue
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')
        print(f'  - [ADD] 列 {table}.{column}')


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
        print(f'[v188] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v188] 开始: 统一资源模型 P4a（生产版本 + 作业定义序列）')
        _do_tables(conn)
        _do_columns(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        conn.commit()
        print('[v188] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v188] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v188 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            SEQUENCE_TABLE: ('definition_id', 'seq_no', 'seq_type', 'description'),
            PRODUCTION_VERSION_TABLE: (
                'code', 'item_id', 'org_id', 'bom_id', 'work_definition_id',
                'valid_from', 'valid_to', 'lot_min', 'lot_max', 'priority',
                'locked', 'status', 'description'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v188 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v188 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        if SEQUENCE_COLUMN not in _columns(conn, DEFINITION_OP_TABLE):
            print(f'[v188 verify] FAIL: 缺列 {DEFINITION_OP_TABLE}.{SEQUENCE_COLUMN}')
            ok = False

        for _table, name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v188 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute(
                    'SELECT 1 FROM enum_types WHERE id=?', (type_id,)
                ).fetchone():
                    print(f'[v188 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        (type_id, code),
                    ).fetchone():
                        print(f'[v188 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v188 verify] FAIL: 缺权限 {code}')
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
                    print(f"[v188 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False
                    continue
                if row[0] != 1:
                    print(f"[v188 verify] FAIL: 菜单 {menu['menu_code']} 未启用")
                    ok = False
                if row[2] != menu['primary_object_type']:
                    print(f"[v188 verify] FAIL: 菜单 {menu['menu_code']} primary_object_type")
                    ok = False
                if row[3] != 0:
                    print(f"[v188 verify] FAIL: 菜单 {menu['menu_code']} show_in_sidebar")
                    ok = False
                if row[4] != menu['sort_order']:
                    print(f"[v188 verify] FAIL: 菜单 {menu['menu_code']} sort_order")
                    ok = False
                if has_parent and row[1] != PARENT_MENU:
                    print(f"[v188 verify] FAIL: 菜单 {menu['menu_code']} 未挂 {PARENT_MENU}")
                    ok = False

        print('[v188 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v188 rollback] DB 不存在: {db_path}')
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
        print('  - [DROP] 生产版本菜单')

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
            print(f'  - [DROP] {len(codes)} 条 P4a 权限（含权限集授权行）')

        for _table, name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for table, column, _ddl in ADDED_COLUMNS:
            if column in _columns(conn, table):
                try:
                    conn.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
                    print(f'  - [DROP] 列 {table}.{column}')
                except sqlite3.OperationalError as e:
                    print(f'  - [WARN] {table}.{column} 列保留（{e}）')

        for name, _ddl in reversed(TABLES):
            if _table_exists(conn, name):
                conn.execute(f'DROP TABLE IF EXISTS {name}')
                print(f'  - [DROP] 表 {name}')

        conn.commit()
        print('[v188 rollback] 完成（枚举种子保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v188 rollback] 失败: {e}')
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
