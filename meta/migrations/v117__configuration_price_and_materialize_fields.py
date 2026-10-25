# -*- coding: utf-8 -*-
"""[v117 2026-10-25] 配置定价门面 字段与权限交付

背景:
  P4.1 落地 `price` 门面（`none` 来源 + 幂等缓存），需要两处支撑:

  1. 结构字段
     - items.config_materialize_policy：物化开关（off / manual / auto），
       与 config_match_policy 正交，默认 off。
     - configurations.variant_item_id：变式物料外键，P4 只留位置不取值。
     两列均为「只留位置」，不改变 solve 行为。

  2. 权限
     定价门面不新增对象，`price` 挂 configuration 的 read 权限
     （见 P4 任务清单 §6）。本迁移确保 5 条 configuration 双段式权限码就位；
     若 v114 已执行，重复写入只输出 [SKIP]。

幂等:
  - 列已存在则跳过（PRAGMA table_info 探测）。
  - 权限 INSERT OR IGNORE；重复执行只输出 [SKIP]。

回滚:
  **保留** 新增列与 permissions 行。列删改在 SQLite 需重建表，风险大于收益；
  permissions 可能已被角色授予。
"""
import sqlite3
from pathlib import Path

# (表, 列, 列定义)
COLUMNS = (
    ('items', 'config_materialize_policy',
     "VARCHAR(20) NOT NULL DEFAULT 'off'"),
    ('configurations', 'variant_item_id',
     'INTEGER REFERENCES items(id)'),
)

_RANK = ('create', 'read', 'update', 'delete', 'list')

_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

OBJECT_ID = 'configuration'
OBJECT_LABEL = '配置实例'

PERMISSIONS = tuple(
    (f'{OBJECT_ID}:{OBJECT_ID}_{action}',
     f'{_ACTION_LABEL[action]}{OBJECT_LABEL}',
     OBJECT_ID,
     action)
    for action in _RANK
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> dict:
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _do_columns(conn: sqlite3.Connection) -> None:
    added = 0
    for table, column, definition in COLUMNS:
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 表 {table} 不存在, 跳过 {column}')
            continue
        if column in _columns(conn, table):
            print(f'  - [SKIP] {table}.{column} 已存在')
            continue
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        added += 1
        print(f'  - [NEW] {table}.{column}')

    print(f'  - [SUMMARY] columns: +{added} 新增')


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

    if created:
        print(f'  - [SUMMARY] permissions: +{created} 新增')
    else:
        print(f'  - [SKIP] {len(PERMISSIONS)} 条权限码均已存在, 无新增')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v117] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v117] 开始: 配置定价门面 字段与权限')
        _do_columns(conn)
        _do_permissions(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v117] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言两列就位（含默认值/可空性）与 5 条 configuration 权限码齐备。"""
    if not db_path.exists():
        print('[v117 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for table, column, _definition in COLUMNS:
            if not _table_exists(conn, table):
                print(f'[v117 verify] FAIL: 表 {table} 不存在')
                return False
            info = _columns(conn, table)
            if column not in info:
                print(f'[v117 verify] FAIL: 缺列 {table}.{column}')
                return False

        materialize = _columns(conn, 'items')['config_materialize_policy']
        if materialize[3] != 1 or str(materialize[4]).strip("'\"") != 'off':
            print(f'[v117 verify] FAIL: items.config_materialize_policy '
                  f'默认值异常 {materialize[4]!r} / notnull={materialize[3]}')
            return False

        variant = _columns(conn, 'configurations')['variant_item_id']
        if variant[3] != 0:
            print('[v117 verify] FAIL: configurations.variant_item_id 应为可空')
            return False

        if not _table_exists(conn, 'permissions'):
            print('[v117 verify] FAIL: permissions 表不存在')
            return False
        missing = [
            code for code, _name, _rt, _action in PERMISSIONS
            if not conn.execute(
                "SELECT 1 FROM permissions WHERE code = ?", (code,)).fetchone()
        ]
        if missing:
            print(f'[v117 verify] FAIL: 缺权限码 {missing}')
            return False

        if not conn.execute(
                "SELECT 1 FROM permissions WHERE code = ?",
                ('configuration:configuration_read',)).fetchone():
            print('[v117 verify] FAIL: 缺 configuration 读权限 (price 依赖)')
            return False

        print('[v117 verify] OK: 字段 2 列 + configuration 权限 5 条齐备')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """新增列与 permissions 行保留（列删改需重建表；权限可能已授予角色）。"""
    print('[v117] downgrade: 列与 permissions 行保留，无删除动作')
    return True


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v117] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v117] verify: {"PASS" if _v else "FAIL"}')
