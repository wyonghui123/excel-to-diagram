# -*- coding: utf-8 -*-
"""[v200 2026-11-03] G4 工程 BOM 消费方（engineering_changes + engineering_change_lines）

依据:
  docs/specs/spec-project-g4-engineering-bom-2026-11-03.md §5 / §6 / §9

设计:
  · 新建 `engineering_changes`：工程变更单头（编号 / 类型 / 项目标签 / 生效日 / 状态）。
    头表**不含** item_id / source_structure_id / target_structure_id，结构维度全部
    下沉到明细行，表结构天然支持一单多物料（P1 服务层限制同一 target_structure_id）。
  · 新建 `engineering_change_lines`：一条 = 一个差异动作（add / modify / remove）。
    target_structure_id 必填；source_structure_id / source_structure_line_id 在
    add / modify 必填；structure_line_id 在 modify / remove 必填。
    `target_revision` / `source_revision` 是创建时的结构 revision 快照，
    仅用于 apply / approve 的并发改版拒绝（spec §6.4 前置校验 2）。
  · 枚举：`engineering_change_status` / `engineering_change_type` /
    `engineering_change_line_type`。
  · 权限：engineering_change:view / create / approve / apply（4 个），授予 admin / default。
  · 菜单：`engineering-change` 挂 master-data（sort_order=105，v196 批次占 104）。

幂等:
  表 / 索引 / 枚举 / 权限 / 授权 / 菜单先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单与 menu_permissions → 删权限与授权行 → 删索引 → 先删明细表再删头表；
  枚举种子保留（避免删值破坏历史）。
"""
import json
import sqlite3
import sys
from pathlib import Path

HEADER_TABLE = 'engineering_changes'
LINE_TABLE = 'engineering_change_lines'

TABLES = (
    (HEADER_TABLE, """
CREATE TABLE IF NOT EXISTS engineering_changes (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change_no VARCHAR(40) NOT NULL,
    title VARCHAR(120) NOT NULL,
    change_type VARCHAR(20) NOT NULL DEFAULT 'revise',
    project_id INTEGER,
    reason TEXT,
    effective_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    applied_at DATETIME,
    applied_by VARCHAR(40),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (change_type IN ('new', 'revise', 'obsolete')),
    CHECK (status IN ('draft', 'in_review', 'approved', 'applied',
                      'rejected', 'cancelled')),
    FOREIGN KEY (project_id) REFERENCES projects(id)
)
"""),
    (LINE_TABLE, """
CREATE TABLE IF NOT EXISTS engineering_change_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    line_type VARCHAR(20) NOT NULL,
    target_structure_id INTEGER NOT NULL,
    source_structure_id INTEGER,
    source_structure_line_id INTEGER,
    structure_line_id INTEGER,
    component_item_id INTEGER NOT NULL,
    match_key VARCHAR(120),
    target_revision VARCHAR(200),
    source_revision VARCHAR(200),
    old_qty_per REAL,
    new_qty_per REAL,
    old_valid_to DATE,
    new_valid_to DATE,
    note TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (line_type IN ('add', 'modify', 'remove')),
    FOREIGN KEY (change_id) REFERENCES engineering_changes(id) ON DELETE CASCADE,
    FOREIGN KEY (component_item_id) REFERENCES items(id)
)
"""),
)

INDEXES = (
    (HEADER_TABLE, 'uq_ec_change_no',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_ec_change_no '
     'ON engineering_changes(change_no)'),
    (HEADER_TABLE, 'idx_ec_status',
     'CREATE INDEX IF NOT EXISTS idx_ec_status ON engineering_changes(status)'),
    (HEADER_TABLE, 'idx_ec_project',
     'CREATE INDEX IF NOT EXISTS idx_ec_project ON engineering_changes(project_id)'),
    (LINE_TABLE, 'uq_ecl_change_line',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_ecl_change_line '
     'ON engineering_change_lines(change_id, line_no)'),
    (LINE_TABLE, 'idx_ecl_change',
     'CREATE INDEX IF NOT EXISTS idx_ecl_change ON engineering_change_lines(change_id)'),
    (LINE_TABLE, 'idx_ecl_component',
     'CREATE INDEX IF NOT EXISTS idx_ecl_component '
     'ON engineering_change_lines(component_item_id)'),
    (LINE_TABLE, 'idx_ecl_target',
     'CREATE INDEX IF NOT EXISTS idx_ecl_target '
     'ON engineering_change_lines(target_structure_id)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('engineering_change_status', '工程变更单状态',
     '工程变更单状态取值（草稿 / 评审中 / 已批准 / 已应用 / 驳回 / 取消）',
     (('draft', '草稿', 'Draft'),
      ('in_review', '评审中', 'In Review'),
      ('approved', '已批准', 'Approved'),
      ('applied', '已应用', 'Applied'),
      ('rejected', '已驳回', 'Rejected'),
      ('cancelled', '已取消', 'Cancelled'))),
    ('engineering_change_type', '工程变更类型',
     '工程变更类型取值（首次工程 BOM / 改版 / 停用）',
     (('new', '首次工程 BOM', 'New'),
      ('revise', '改版', 'Revise'),
      ('obsolete', '停用', 'Obsolete'))),
    ('engineering_change_line_type', '工程变更明细类型',
     '工程变更明细动作（新增 / 修改 / 移除）',
     (('add', '新增', 'Add'),
      ('modify', '修改', 'Modify'),
      ('remove', '移除', 'Remove'))),
)

ACTION_LABEL = {
    'view': '查看', 'create': '新建', 'approve': '批准', 'apply': '应用',
}
PERMISSIONS = tuple(
    ('engineering_change:%s' % action,
     '工程变更单%s' % ACTION_LABEL[action], 'engineering_change', action)
    for action in ('view', 'create', 'approve', 'apply')
)

GRANT_TO_SETS = ('admin', 'default')

PARENT_MENU = 'master-data'
MENUS = (
    {'menu_code': 'engineering-change', 'menu_name': '工程变更',
     'menu_path': '/master-data/engineering-change',
     'primary_object_type': 'engineering_change',
     'icon': 'GitPullRequest', 'color': '#f59e0b', 'sort_order': 105,
     'description': '工程变更单——工程 BOM 与生产 BOM 差异评审与生效'},
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


# 后端启动会按 YAML 自动建表；若先于迁移发生，CREATE TABLE IF NOT EXISTS 会
# 跳过整表，留下缺审计列的半成品。这里按列补齐（仅审计列，均为可空）。
AUDIT_COLUMNS = (
    ('created_by', 'VARCHAR(200)'),
    ('updated_by', 'VARCHAR(200)'),
    ('created_at', 'DATETIME'),
    ('updated_at', 'DATETIME'),
)


def _ensure_audit_columns(conn: sqlite3.Connection) -> None:
    for table, _ddl in TABLES:
        existing = _columns(conn, table)
        if not existing:
            continue
        for name, col_type in AUDIT_COLUMNS:
            if name in existing:
                continue
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {col_type}')
            print(f'  - [ALTER] {table}.{name} 补齐审计列')


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
        required = [code for code, _name, _rtype, _action in PERMISSIONS]
        bo_binding = [{
            'bo_id': menu['primary_object_type'],
            'role': 'primary',
            'include_actions': ['view', 'create', 'approve', 'apply'],
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
        print(f'[v200] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v200] 开始: G4 工程变更单（engineering_changes + engineering_change_lines）')
        _do_tables(conn)
        _ensure_audit_columns(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        conn.commit()
        print('[v200] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v200] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v200 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        expected_columns = {
            HEADER_TABLE: ('change_no', 'title', 'change_type', 'project_id',
                           'reason', 'effective_date', 'status', 'applied_at',
                           'applied_by', 'created_at', 'updated_at'),
            LINE_TABLE: ('change_id', 'line_no', 'line_type', 'target_structure_id',
                         'source_structure_id', 'source_structure_line_id',
                         'structure_line_id', 'component_item_id', 'match_key',
                         'target_revision', 'source_revision', 'old_qty_per',
                         'new_qty_per', 'old_valid_to', 'new_valid_to', 'note'),
        }
        for table, cols in expected_columns.items():
            if not _table_exists(conn, table):
                print(f'[v200 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v200 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for _table, name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v200 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute(
                    'SELECT 1 FROM enum_types WHERE id=?', (type_id,)
                ).fetchone():
                    print(f'[v200 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        (type_id, code),
                    ).fetchone():
                        print(f'[v200 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v200 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                if not conn.execute(
                    'SELECT 1 FROM menus WHERE menu_code=?', (menu['menu_code'],)
                ).fetchone():
                    print(f"[v200 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False

        print('[v200 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v200 rollback] DB 不存在: {db_path}')
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
            print(f'  - [DROP] {len(codes)} 条工程变更权限（含权限集授权行）')

        for _table, name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for name, _ddl in reversed(TABLES):
            if _table_exists(conn, name):
                conn.execute(f'DROP TABLE IF EXISTS {name}')
                print(f'  - [DROP] 表 {name}')

        conn.commit()
        print('[v200 rollback] 完成（枚举种子保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v200 rollback] 失败: {e}')
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

