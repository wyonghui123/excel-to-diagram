# -*- coding: utf-8 -*-
"""[v196 2026-11-03] 批次主数据 P4c（batches + batch_attribute_values）

依据:
  docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md §11.2 / §11.3 / §11.7
  docs/specs/p4c-batch-master-data/spec.md

设计:
  · 新建 `batches`：最小批次身份 `(item_id, org_id, batch_no)`、生命周期 status、
    质量状态 quality_status、来源 source、产出/有效期、效价 potency_pct（物理列）。
    父批次自引用，单父；深度与成环由 BatchService 校验。
  · 新建 `batch_attribute_values`：批次特性值表，严格照 _attribute_value_template，
    五值列互斥、多值用 seq；不建 characteristics_json / batch_characteristics。
  · 枚举：`batch_status` / `batch_quality_status` / `batch_source`。
  · 权限：batch 与 batch_attribute_value 各 4 条双段式，授予 admin / default。
  · 菜单：`batch-management` 挂 master-data（sort_order=104，v188 生产版本占 103）。
  · 表名 `batch_attribute_values` 是硬约束：AttributeImpactService 靠 `_attribute_values`
    后缀自动发现引用表，改名会绕过「被引用定义禁止删除」保护。

幂等:
  表 / 索引 / 枚举 / 权限 / 授权 / 菜单先查后用；重复执行打印 [SKIP]。

回滚:
  删菜单与 menu_permissions → 删权限与授权行 → 删索引 → 先删值表再删批次表；
  枚举种子保留（避免删值破坏历史行）。
"""
import json
import sqlite3
import sys
from pathlib import Path

BATCH_TABLE = 'batches'
VALUE_TABLE = 'batch_attribute_values'
ITEM_TABLE = 'items'
ORG_TABLE = 'orgs'
UOM_TABLE = 'uoms'
DEFINITION_TABLE = 'attribute_definitions'

TABLES = (
    (BATCH_TABLE, """
CREATE TABLE IF NOT EXISTS batches (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no VARCHAR(60) NOT NULL,
    item_id INTEGER NOT NULL,
    org_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    qty_uom_id INTEGER NOT NULL,
    parent_batch_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'planned',
    quality_status VARCHAR(20) NOT NULL DEFAULT 'unrestricted',
    source VARCHAR(20) NOT NULL DEFAULT 'manual',
    produced_at DATETIME,
    expiry_date DATE,
    potency_pct REAL,
    description VARCHAR(255),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (qty > 0),
    CHECK (status IN ('planned', 'in_process', 'closed')),
    CHECK (quality_status IN ('unrestricted', 'inspection', 'blocked')),
    CHECK (source IN ('production', 'purchase', 'manual', 'adjustment')),
    CHECK (potency_pct IS NULL OR (potency_pct >= 0 AND potency_pct <= 100)),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (qty_uom_id) REFERENCES uoms(id),
    FOREIGN KEY (parent_batch_id) REFERENCES batches(id)
)
"""),
    (VALUE_TABLE, """
CREATE TABLE IF NOT EXISTS batch_attribute_values (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL DEFAULT 0,
    batch_id INTEGER NOT NULL,
    attribute_id INTEGER NOT NULL,
    seq INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    value_text TEXT,
    value_number REAL,
    value_boolean INTEGER,
    value_date DATE,
    value_datetime DATETIME,
    created_at DATETIME,
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    FOREIGN KEY (attribute_id) REFERENCES attribute_definitions(id)
)
"""),
)

INDEXES = (
    (BATCH_TABLE, 'uq_batch_item_org_no',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_item_org_no '
     'ON batches(item_id, org_id, batch_no)'),
    (BATCH_TABLE, 'idx_batch_item',
     'CREATE INDEX IF NOT EXISTS idx_batch_item ON batches(item_id)'),
    (BATCH_TABLE, 'idx_batch_org',
     'CREATE INDEX IF NOT EXISTS idx_batch_org ON batches(org_id)'),
    (BATCH_TABLE, 'idx_batch_status',
     'CREATE INDEX IF NOT EXISTS idx_batch_status ON batches(status)'),
    (BATCH_TABLE, 'idx_batch_quality_status',
     'CREATE INDEX IF NOT EXISTS idx_batch_quality_status '
     'ON batches(quality_status)'),
    (BATCH_TABLE, 'idx_batch_parent',
     'CREATE INDEX IF NOT EXISTS idx_batch_parent ON batches(parent_batch_id)'),
    (BATCH_TABLE, 'idx_batch_produced_at',
     'CREATE INDEX IF NOT EXISTS idx_batch_produced_at ON batches(produced_at)'),
    (VALUE_TABLE, 'uidx_batch_attr_value',
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_batch_attr_value '
     'ON batch_attribute_values(tenant_id, batch_id, attribute_id, seq)'),
    (VALUE_TABLE, 'idx_batch_attr_value_attr',
     'CREATE INDEX IF NOT EXISTS idx_batch_attr_value_attr '
     'ON batch_attribute_values(attribute_id)'),
    (VALUE_TABLE, 'idx_batch_attr_value_batch',
     'CREATE INDEX IF NOT EXISTS idx_batch_attr_value_batch '
     'ON batch_attribute_values(tenant_id, batch_id)'),
)

# 枚举种子：(enum_type_id, 显示名, 描述, ((code, name, name_en), ...))
ENUM_SEEDS = (
    ('batch_status', '批次生命周期状态', '批次生命周期取值（计划 / 在制 / 关闭）',
     (('planned', '计划', 'Planned'),
      ('in_process', '在制', 'In Process'),
      ('closed', '关闭', 'Closed'))),
    ('batch_quality_status', '批次质量状态', '批次质量状态取值（可用 / 检验中 / 冻结）',
     (('unrestricted', '可用', 'Unrestricted'),
      ('inspection', '检验中', 'In Inspection'),
      ('blocked', '冻结', 'Blocked'))),
    ('batch_source', '批次来源', '批次来源取值（生产 / 采购 / 手工 / 调整）',
     (('production', '生产', 'Production'),
      ('purchase', '采购', 'Purchase'),
      ('manual', '手工', 'Manual'),
      ('adjustment', '调整', 'Adjustment'))),
)

ACTIONS = ('read', 'create', 'update', 'delete')
_ACTION_LABEL = {
    'read': '查看', 'create': '新建', 'update': '修改', 'delete': '删除',
}
OBJECTS = (
    ('batch', '批次'),
    ('batch_attribute_value', '批次特性值'),
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
    {'menu_code': 'batch-management', 'menu_name': '批次',
     'menu_path': '/master-data/batch',
     'primary_object_type': 'batch',
     'icon': 'Boxes', 'color': '#0ea5e9', 'sort_order': 104,
     'description': '批次——最小批次身份、生命周期、质量状态与批次特性'},
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
        print(f'[v196] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v196] 开始: 批次主数据 P4c（batches + batch_attribute_values）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_menus(conn)
        conn.commit()
        print('[v196] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v196] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v196 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        expected_columns = {
            BATCH_TABLE: ('batch_no', 'item_id', 'org_id', 'qty', 'qty_uom_id',
                          'parent_batch_id', 'status', 'quality_status', 'source',
                          'produced_at', 'expiry_date', 'potency_pct',
                          'description'),
            VALUE_TABLE: ('tenant_id', 'batch_id', 'attribute_id', 'seq',
                          'description', 'value_text', 'value_number',
                          'value_boolean', 'value_date', 'value_datetime'),
        }
        for table, cols in expected_columns.items():
            if not _table_exists(conn, table):
                print(f'[v196 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v196 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for _table, name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v196 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute(
                    'SELECT 1 FROM enum_types WHERE id=?', (type_id,)
                ).fetchone():
                    print(f'[v196 verify] FAIL: 缺枚举类型 {type_id}')
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        (type_id, code),
                    ).fetchone():
                        print(f'[v196 verify] FAIL: 缺枚举值 {type_id}.{code}')
                        ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v196 verify] FAIL: 缺权限 {code}')
                    ok = False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                if not conn.execute(
                    'SELECT 1 FROM menus WHERE menu_code=?', (menu['menu_code'],)
                ).fetchone():
                    print(f"[v196 verify] FAIL: 缺菜单 {menu['menu_code']}")
                    ok = False

        print('[v196 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v196 rollback] DB 不存在: {db_path}')
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
            print(f'  - [DROP] {len(codes)} 条 P4c 权限（含权限集授权行）')

        for _table, name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        for name, _ddl in reversed(TABLES):
            if _table_exists(conn, name):
                conn.execute(f'DROP TABLE IF EXISTS {name}')
                print(f'  - [DROP] 表 {name}')

        conn.commit()
        print('[v196 rollback] 完成（枚举种子保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v196 rollback] 失败: {e}')
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
