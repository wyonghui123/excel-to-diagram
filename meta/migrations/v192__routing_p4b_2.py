# -*- coding: utf-8 -*-
"""[v192 2026-11-01] 统一资源模型 P4b-2（过程指令，单表双形态）

依据:
  docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md §10.5 / §10.8
  docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md 附 C.1

设计:
  · 新建 `process_instructions`：`instruction_kind` 判别文本指令 / 操作参数，
    避免为两类数据各建一张薄表（Oracle Instructions / Operational Parameters、
    SAP Process Instruction Category + Characteristics 的同一语义）。
  · 唯一 `(operation_id, seq)`；`(operation_id, parameter_code)` 在 parameter_code
    非空时唯一（部分唯一索引）。
  · `target_value` / `min_value` / `max_value` 用 TEXT 存储（numeric 存规范十进制
    字符串）；P5 若需强类型报表再拆表或加 typed 列。
  · 3 组枚举：`instruction_kind` / `parameter_data_type` / `parameter_direction`。
  · 权限码双段式 `{bo}:{bo}_{action}`，授予 admin / default 权限集。
  · 无菜单（从表）。

幂等:
  表 / 索引 / 枚举 / 权限 / 授权先查后用；重复执行打印 [SKIP]。

回滚:
  删权限与授权行 → 删索引 → 删表；枚举保留（可能被其他对象引用）。
"""
import sqlite3
import sys
from pathlib import Path

INSTRUCTION_TABLE = 'process_instructions'
OPERATION_TABLE = 'work_definition_operations'

TABLES = (
    (INSTRUCTION_TABLE, """
CREATE TABLE IF NOT EXISTS process_instructions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    instruction_kind VARCHAR(200) NOT NULL DEFAULT 'text',
    title VARCHAR(200),
    content TEXT,
    parameter_code VARCHAR(200),
    parameter_name VARCHAR(200),
    data_type VARCHAR(200),
    uom_id INTEGER,
    target_value TEXT,
    min_value TEXT,
    max_value TEXT,
    direction VARCHAR(200),
    resource_id INTEGER,
    is_required INTEGER NOT NULL DEFAULT 0,
    description VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (operation_id) REFERENCES work_definition_operations(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id),
    FOREIGN KEY (resource_id) REFERENCES resources(id)
)
"""),
)

INDEXES = (
    (INSTRUCTION_TABLE, 'uq_process_instruction_seq',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_process_instruction_seq '
     'ON process_instructions(operation_id, seq)'),
    (INSTRUCTION_TABLE, 'uq_process_instruction_parameter',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_process_instruction_parameter '
     'ON process_instructions(operation_id, parameter_code) '
     'WHERE parameter_code IS NOT NULL'),
    (INSTRUCTION_TABLE, 'idx_process_instruction_operation',
     'CREATE INDEX IF NOT EXISTS idx_process_instruction_operation '
     'ON process_instructions(operation_id)'),
    (INSTRUCTION_TABLE, 'idx_process_instruction_kind',
     'CREATE INDEX IF NOT EXISTS idx_process_instruction_kind '
     'ON process_instructions(instruction_kind)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('instruction_kind', '指令形态', '过程指令形态取值（文本指令 / 操作参数）',
     (('text', '文本指令', 'Text'),
      ('parameter', '操作参数', 'Parameter'))),
    ('parameter_data_type', '参数数据类型', '操作参数数据类型取值',
     (('numeric', '数值', 'Numeric'),
      ('text', '文本', 'Text'),
      ('boolean', '布尔', 'Boolean'),
      ('date', '日期', 'Date'))),
    ('parameter_direction', '参数方向', '操作参数方向取值（下发 / 采集）',
     (('set', '下发', 'Set'),
      ('collect', '采集', 'Collect'))),
)

ACTIONS = ('read', 'create', 'update', 'delete')
_ACTION_LABEL = {
    'read': '查看', 'create': '新建', 'update': '修改', 'delete': '删除',
}
OBJECTS = (
    ('process_instruction', '过程指令'),
)

PERMISSIONS = tuple(
    ('{0}:{0}_{1}'.format(bo, action),
     '{0}{1}'.format(label, _ACTION_LABEL[action]), bo, action)
    for bo, label in OBJECTS
    for action in ACTIONS
)

GRANT_TO_SETS = ('admin', 'default')


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


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v192] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v192] 开始: 统一资源模型 P4b-2（过程指令）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        conn.commit()
        print('[v192] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v192] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v192 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        expected_columns = (
            'operation_id', 'seq', 'instruction_kind', 'title', 'content',
            'parameter_code', 'parameter_name', 'data_type', 'uom_id',
            'target_value', 'min_value', 'max_value', 'direction', 'resource_id',
            'is_required', 'description',
        )
        if not _table_exists(conn, INSTRUCTION_TABLE):
            print(f'[v192 verify] FAIL: 缺表 {INSTRUCTION_TABLE}')
            ok = False
        else:
            have = _columns(conn, INSTRUCTION_TABLE)
            for col in expected_columns:
                if col not in have:
                    print(f'[v192 verify] FAIL: 缺列 {INSTRUCTION_TABLE}.{col}')
                    ok = False

        for _table, name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v192 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute(
                    'SELECT 1 FROM enum_types WHERE id=?', (type_id,)
                ).fetchone():
                    print(f'[v192 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        (type_id, code),
                    ).fetchone():
                        print(f'[v192 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v192 verify] FAIL: 缺权限 {code}')
                    ok = False

        print('[v192 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v192 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
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
            print(f'  - [DROP] {len(codes)} 条 P4b 权限（含权限集授权行）')

        for _table, name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for name, _ddl in reversed(TABLES):
            if _table_exists(conn, name):
                conn.execute(f'DROP TABLE IF EXISTS {name}')
                print(f'  - [DROP] 表 {name}')

        conn.commit()
        print('[v192 rollback] 完成（枚举种子保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v192 rollback] 失败: {e}')
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
