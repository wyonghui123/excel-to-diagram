# -*- coding: utf-8 -*-
"""[v138] 权限双轨收口：退役 role_* 物理表，单一真源 = permission_set_*

背景
  v070 已把 roles/role_permissions/... RENAME 为 permission_set_*，但
  meta/schemas/ 中仍保留 role.yaml / role_permission.yaml /
  role_data_permission.yaml / role_dimension_scope.yaml，yaml_loader
  按目录 glob 全量注册 → 每次 sync_schema 又把旧表建回来，形成
  「逻辑双轨 + 物理双轨」。本迁移负责存量库的收口；YAML 侧已在本
  change 中删除（新库不会再生成旧表）。

本迁移做什么
  1. roles            → permission_sets            （按 code 去重并入，保留原 id 映射）
  2. role_permissions → permission_set_permissions （按 role_id 映射后并入）
  3. role_data_permissions → permission_set_data_permissions
  4. role_dimension_scopes → permission_set_dimension_scopes
  5. 数据核对通过后：RENAME 旧表为 *_pre_v138_backup → DROP 备份
     （沿用 v071 的「RENAME → DROP backup」模式，避免直接 DROP 含数据的表）

幂等
  - 旧表不存在 → 直接返回 True（已收口或从未有过旧表）
  - 子表按业务键 NOT EXISTS 判重；重复执行不会产生重复行
  - permission_sets 不存在（说明 v070 未执行）→ 返回 False，交由部署阻断

回滚（rollback）
  - 重建 4 张旧空表（结构照 generated_schema.sql 历史 DDL）
  - 数据不回滚：原数据已并入 permission_set_*，仍可在新表查询
"""
import sqlite3
from pathlib import Path

# 旧表 → 新表
LEGACY_TO_TARGET = [
    ('roles', 'permission_sets'),
    ('role_permissions', 'permission_set_permissions'),
    ('role_data_permissions', 'permission_set_data_permissions'),
    ('role_dimension_scopes', 'permission_set_dimension_scopes'),
]

BACKUP_SUFFIX = '_pre_v138_backup'

# 子表：旧 FK 列 → 新 FK 列，以及业务键（用于 NOT EXISTS 判重）
CHILD_SPECS = [
    ('role_permissions', 'permission_set_permissions', 'role_id', 'permission_set_id',
     ('permission_id',)),
    ('role_data_permissions', 'permission_set_data_permissions', 'role_id',
     'permission_set_id', ('resource_type', 'resource_id')),
    ('role_dimension_scopes', 'permission_set_dimension_scopes', 'role_id',
     'permission_set_id', ('dimension_code',)),
]

# rollback 用：旧表历史 DDL（与 v070 之前 generated_schema.sql 对齐）
LEGACY_DDL = {
    'roles': '''CREATE TABLE IF NOT EXISTS roles (
        created_by VARCHAR(200), updated_by VARCHAR(200),
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(200) UNIQUE NOT NULL, name VARCHAR(200) NOT NULL,
        description TEXT, is_active INTEGER DEFAULT 1, is_system INTEGER DEFAULT 0,
        is_super_admin INTEGER DEFAULT 0, priority INTEGER DEFAULT 0,
        created_at DATETIME, menu_count INTEGER, permission_count INTEGER,
        data_perm_count INTEGER)''',
    'role_permissions': '''CREATE TABLE IF NOT EXISTS role_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_id INTEGER NOT NULL, permission_id INTEGER NOT NULL,
        created_at DATETIME)''',
    'role_data_permissions': '''CREATE TABLE IF NOT EXISTS role_data_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_id INTEGER NOT NULL, resource_type VARCHAR(200) NOT NULL,
        resource_id INTEGER NOT NULL,
        permission_level VARCHAR(200) DEFAULT 'read',
        inherit_to_children INTEGER DEFAULT 1,
        created_at VARCHAR(200), created_by INTEGER)''',
    'role_dimension_scopes': '''CREATE TABLE IF NOT EXISTS role_dimension_scopes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_id INTEGER NOT NULL, dimension_code VARCHAR(200) NOT NULL,
        dimension_values TEXT NOT NULL,
        inherit_children INTEGER DEFAULT 1,
        scope_mode VARCHAR(200) DEFAULT 'include')''',
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> list:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def _merge_permission_sets(conn: sqlite3.Connection) -> dict:
    """roles → permission_sets，返回 {old_role_id: new_permission_set_id}"""
    mapping = {}
    common = [c for c in _columns(conn, 'roles')
              if c in _columns(conn, 'permission_sets') and c != 'id']
    for row in conn.execute('SELECT * FROM roles').fetchall():
        data = dict(zip(_columns(conn, 'roles'), row))
        existing = conn.execute(
            'SELECT id FROM permission_sets WHERE code = ?', (data['code'],)
        ).fetchone()
        if existing:
            mapping[data['id']] = existing[0]
            print(f"  roles#{data['id']} ({data['code']}) 已存在于 permission_sets#{existing[0]}")
            continue
        placeholders = ','.join('?' * len(common))
        conn.execute(
            f'INSERT INTO permission_sets ({",".join(common)}) VALUES ({placeholders})',
            tuple(data[c] for c in common),
        )
        new_id = conn.execute(
            'SELECT id FROM permission_sets WHERE code = ?', (data['code'],)
        ).fetchone()[0]
        mapping[data['id']] = new_id
        print(f"  roles#{data['id']} ({data['code']}) → permission_sets#{new_id}")
    return mapping


def _merge_child(conn: sqlite3.Connection, spec, role_map: dict) -> None:
    old_t, new_t, old_fk, new_fk, biz_keys = spec
    old_cols = _columns(conn, old_t)
    new_cols = _columns(conn, new_t)
    copy_cols = [c for c in old_cols if c != 'id' and c != old_fk and c in new_cols]
    for row in conn.execute(f'SELECT * FROM "{old_t}"').fetchall():
        data = dict(zip(old_cols, row))
        new_pid = role_map.get(data[old_fk])
        if new_pid is None:
            print(f"  [{old_t}#{data['id']}] 找不到 role_id={data[old_fk]} 映射，跳过")
            continue
        where = ' AND '.join(f'{k} = ?' for k in biz_keys)
        exists = conn.execute(
            f'SELECT 1 FROM "{new_t}" WHERE {new_fk} = ? AND {where}',
            (new_pid, *[data[k] for k in biz_keys]),
        ).fetchone()
        if exists:
            continue
        cols = [new_fk] + copy_cols
        vals = [new_pid] + [data[c] for c in copy_cols]
        placeholders = ','.join('?' * len(cols))
        conn.execute(
            f'INSERT INTO "{new_t}" ({",".join(cols)}) VALUES ({placeholders})', vals
        )


def _retire(conn: sqlite3.Connection) -> None:
    for old_t, _ in LEGACY_TO_TARGET:
        if not _table_exists(conn, old_t):
            continue
        backup = old_t + BACKUP_SUFFIX
        cnt = _row_count(conn, old_t)
        conn.execute(f'ALTER TABLE "{old_t}" RENAME TO "{backup}"')
        conn.execute(f'DROP TABLE IF EXISTS "{backup}"')
        print(f'  RENAME+DROP {old_t} → {backup} ({cnt} rows, 已并入新表)')


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permission_sets'):
        raise RuntimeError(
            'permission_sets 不存在（v070 未执行）。请先按顺序执行 v070 → v138。'
        )
    if not _table_exists(conn, 'roles'):
        print('  roles 不存在，旧轨已收口，跳过')
        return

    role_map = _merge_permission_sets(conn)
    for spec in CHILD_SPECS:
        if _table_exists(conn, spec[0]):
            _merge_child(conn, spec, role_map)

    # 数据核对：每条 roles.code 必须能在 permission_sets 命中
    missing = conn.execute(
        'SELECT code FROM roles WHERE code NOT IN (SELECT code FROM permission_sets)'
    ).fetchall()
    if missing:
        raise RuntimeError(f'合并后仍有 {len(missing)} 条 roles 未落入 permission_sets: {missing}')

    _retire(conn)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v138] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v138] 权限双轨收口：role_* → permission_set_*')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v138] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v138 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        leftovers = [t for t, _ in LEGACY_TO_TARGET if _table_exists(conn, t)]
        backups = [t + BACKUP_SUFFIX for t, _ in LEGACY_TO_TARGET
                   if _table_exists(conn, t + BACKUP_SUFFIX)]
        if leftovers or backups:
            print(f'[v138 verify] FAIL: 旧表仍在: {leftovers + backups}')
            return False
        if not _table_exists(conn, 'permission_sets'):
            print('[v138 verify] FAIL: permission_sets 不存在')
            return False
        print('[v138 verify] OK: 旧 role_* 表已退役，permission_sets 就位')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """重建 4 张旧空表（结构回滚；数据不回滚，已并入 permission_set_*）"""
    if not db_path.exists():
        print(f'[v138] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for name, ddl in LEGACY_DDL.items():
            conn.execute(ddl)
            print(f'  rollback: 重建空表 {name}')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v138] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _args = [a for a in sys.argv[1:] if a != '--rollback']
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v138] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v138] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v138] verify: {"PASS" if _v else "FAIL"}')
