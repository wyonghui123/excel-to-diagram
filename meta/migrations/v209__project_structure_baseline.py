# -*- coding: utf-8 -*-
"""v209] 项目结构基线指针表（G15 ETO P2-2）

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.2（P2-2 项目结构基线指针表）

范围:
  1. 新表 project_structure_baselines：只存「指针 + 哈希」，不存 BOM 行。
       project_id / item_id / usage / alternative_no 构成业务键；
       structure_id = 0 表示「时点 active 版本」，非 0 表示钉住某版本；
       baseline_hash 是头 + 行按固定口径算出的 sha256 hex。
  2. 唯一索引 uq_project_structure_baseline（同键一条，upsert 语义）与
       查询索引 idx_project_structure_baseline_item（按物料反查）。
  3. 权限 6 条 + 授权 admin / default；不建独立菜单
     （项目从属表，按 menu-retirement 判据不该有平级菜单）。

口径:
  · baseline 不进成本、不参与 MRP，只是结构版本的事实快照指针。
  · 无子表，禁止行级维护（note 不承载 BOM 行）。
  · structure_id 的 0 哨兵是避免 SQLite 唯一索引对 NULL 去重失效。

幂等:
  表 / 索引 / 权限 / 授权先查后写；重复执行打印 [SKIP]。

回滚:
  [ALLOW_DESTRUCTIVE] 删授权 → 删权限 → 删索引 → 删表（仅回滚路径）。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v209__project_structure_baseline'

TABLE = 'project_structure_baselines'
UNIQUE_INDEX = 'uq_project_structure_baseline'
ITEM_INDEX = 'idx_project_structure_baseline_item'

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS %s (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    usage TEXT NOT NULL DEFAULT 'production',
    alternative_no INTEGER NOT NULL DEFAULT 1,
    structure_id INTEGER NOT NULL DEFAULT 0,
    baseline_hash TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    note TEXT
)""" % TABLE

INDEX_SQL = (
    (
        UNIQUE_INDEX,
        "CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s"
        "(project_id, item_id, usage, alternative_no)" % (UNIQUE_INDEX, TABLE),
    ),
    (
        ITEM_INDEX,
        "CREATE INDEX IF NOT EXISTS %s ON %s(item_id)" % (ITEM_INDEX, TABLE),
    ),
)

PERMISSIONS = (
    ('project_structure_baseline:project_structure_baseline_read',
     '项目结构基线查看', 'project_structure_baseline', 'project_structure_baseline_read'),
    ('project_structure_baseline:project_structure_baseline_list',
     '项目结构基线查询', 'project_structure_baseline', 'project_structure_baseline_list'),
    ('project_structure_baseline:project_structure_baseline_create',
     '项目结构基线新建', 'project_structure_baseline', 'project_structure_baseline_create'),
    ('project_structure_baseline:project_structure_baseline_update',
     '项目结构基线修改', 'project_structure_baseline', 'project_structure_baseline_update'),
    # action 权限码与 bo_action_registrations 的 permission_required 逐字一致
    ('project_structure_baseline:check_drift',
     '项目结构基线漂移检查', 'project_structure_baseline', 'check_drift'),
    ('project_structure_baseline:refresh',
     '项目结构基线刷新', 'project_structure_baseline', 'refresh'),
)

GRANT_TO_SETS = ('admin', 'default')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        return {row[1] for row in conn.execute(
            'PRAGMA table_info(%s)' % table).fetchall()}
    except sqlite3.Error:
        return set()


def _do_table(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, TABLE):
        print('  - [SKIP] 表 %s 已存在' % TABLE)
        return
    conn.execute(TABLE_SQL)
    print('  - [NEW] 表 %s' % TABLE)


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, sql in INDEX_SQL:
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
            continue
        conn.execute(sql)
        print('  - [NEW] 索引 %s' % name)


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
            'VALUES (?, ?, ?, ?)', (code, name, resource_type, action))
        if cur.rowcount:
            created += 1
            print('  - [NEW] 权限 %s (%s)' % (code, name))
    print('  - [SUMMARY] permissions: +%s' % created)


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
        return
    has_code_col = 'permission_code' in cols
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            (set_code,)).fetchone()
        if not row:
            continue
        permission_set_id = row[0]
        for code, _name, _rtype, _action in PERMISSIONS:
            prow = conn.execute(
                'SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
            if not prow:
                continue
            if conn.execute(
                    'SELECT 1 FROM permission_set_permissions WHERE '
                    '%s = ? AND permission_id = ?' % id_col,
                    (permission_set_id, prow[0])).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_code, permission_id, granted, created_at) '
                    "VALUES (?, ?, ?, 1, datetime('now'))" % id_col,
                    (permission_set_id, code, prow[0]))
            else:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_id, granted, created_at) '
                    "VALUES (?, ?, 1, datetime('now'))" % id_col,
                    (permission_set_id, prow[0]))
            granted += 1
    print('  - [SUMMARY] permission_set_permissions: +%s' % granted)


def _do_upgrade(conn: sqlite3.Connection) -> None:
    _do_table(conn)
    _do_indexes(conn)
    _do_permissions(conn)
    _do_grants(conn)


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if (_table_exists(conn, 'permissions')
            and _table_exists(conn, 'permission_set_permissions')):
        cols = _columns(conn, 'permission_set_permissions')
        if 'permission_set_id' in cols or 'role_id' in cols:
            id_col = 'permission_set_id' if 'permission_set_id' in cols \
                else 'role_id'
            codes = [code for code, _n, _r, _a in PERMISSIONS]
            for code in codes:
                prow = conn.execute(
                    'SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
                if not prow:
                    continue
                conn.execute(
                    'DELETE FROM permission_set_permissions WHERE %s '
                    'IS NOT NULL AND permission_id = ?' % id_col, (prow[0],))
            print('  - [DEL] 权限授权 %s 条' % len(codes))
    if _table_exists(conn, 'permissions'):
        for code, _name, _rtype, _action in PERMISSIONS:
            conn.execute('DELETE FROM permissions WHERE code=?', (code,))
        print('  - [DEL] 权限 %s 条' % len(PERMISSIONS))
    for name, _sql in reversed(INDEX_SQL):
        if _index_exists(conn, name):
            conn.execute('DROP INDEX IF EXISTS %s' % name)
            print('  - [DEL] 索引 %s' % name)
    if _table_exists(conn, TABLE):
        conn.execute('DROP TABLE IF EXISTS %s' % TABLE)
        print('  - [DEL] 表 %s' % TABLE)


def migrate(db_path: Path, skip_backup: bool = True) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v209] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v209] 开始: 项目结构基线指针表（G15 ETO P2-2）')
        _do_upgrade(conn)
        conn.commit()
        print('[v209] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v209] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v209 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, TABLE):
            print('[v209 verify] FAIL: 缺表 %s' % TABLE)
            return False
        expected = {'id', 'project_id', 'item_id', 'usage', 'alternative_no',
                    'structure_id', 'baseline_hash', 'captured_at', 'note'}
        missing = expected - _columns(conn, TABLE)
        if missing:
            print('[v209 verify] FAIL: 缺列 %s' % sorted(missing))
            return False
        for name, _sql in INDEX_SQL:
            if not _index_exists(conn, name):
                print('[v209 verify] FAIL: 缺索引 %s' % name)
                return False
        print('[v209 verify] PASS')
        return True
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print(migrate(Path(sys.argv[1]), skip_backup=True))
        print(verify(Path(sys.argv[1])))
