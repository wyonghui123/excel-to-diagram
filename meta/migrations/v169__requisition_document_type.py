# -*- coding: utf-8 -*-
"""[v169 2026-11-01] 业务单据类型规范 —— requisition.document_type_id

依据:
  docs/specs/spec-procurement-task-object-model-2026-10-31.md §3.2 / T-D13a（收窄释义）
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §1 M0 A4 / §2 M1

规范:
  所有业务单据头必备「单据类型」，统一引用 type_definitions 的 header 行
  （scope_bo=<BO YAML id> + level='header'）。单据类型只承载编号 / 审批 /
  打印 / 权限等治理语义；不承载 purchase / internal —— 内外仍由 sourcing
  派生（T-D13a 只禁止它编码载体方向）。

本迁移做四件事（幂等）:
  ① requisitions 补列 document_type_id（库列可空：SQLite ALTER 不能加 NOT NULL）
  ② 种子一条默认类型（scope_bo='requisition', level='header', code='STD'）
  ③ 存量行回填默认类型（避免 NULL 行）
  ④ 补索引 idx_requisition_document_type

「创建时必填」由 DemandEntryService.validate_document_type / 需求入口守卫承担，
不在库层做 NOT NULL（与业务键 request_no 的「列可空、写入时校验」同口径）。

回滚:
  列由 YAML 声明，保留（与 v147 同口径）；仅删本迁移补的索引。
  默认类型行保留 —— 可能已被存量单据引用。
"""
import sqlite3
import sys
from pathlib import Path

TABLE = 'requisitions'
COLUMN = 'document_type_id'
INDEX_NAME = 'idx_requisition_document_type'

TYPE_TABLE = 'type_definitions'
TYPE_SCOPE = 'requisition'
TYPE_LEVEL = 'header'
TYPE_CODE = 'STD'


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


def _ensure_column(conn: sqlite3.Connection) -> None:
    if COLUMN in _columns(conn, TABLE):
        print(f'  - [SKIP] {TABLE}.{COLUMN} 已存在')
        return
    conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} INTEGER')
    print(f'  - [ADD] {TABLE}.{COLUMN}')


def _seed_default_type(conn: sqlite3.Connection) -> int:
    """按 (scope_bo, level, code) 判重；返回类型 id。"""
    row = conn.execute(
        'SELECT id FROM type_definitions WHERE scope_bo=? AND level=? AND code=?',
        (TYPE_SCOPE, TYPE_LEVEL, TYPE_CODE)).fetchone()
    if row:
        print(f'  - [SKIP] 默认类型 {TYPE_SCOPE}/{TYPE_LEVEL}/{TYPE_CODE} 已存在 (id={row[0]})')
        return int(row[0])

    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    cur = conn.execute(
        'INSERT INTO type_definitions '
        '(code, name, scope_bo, level, document_category, status, description, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (TYPE_CODE, '标准采购申请', TYPE_SCOPE, TYPE_LEVEL, 'standard', 'active',
         '采购申请默认单据类型（M1 种子；编号 / 审批 / 打印等治理语义的挂载点）', now))
    print(f'  - [NEW] 默认类型 {TYPE_SCOPE}/{TYPE_LEVEL}/{TYPE_CODE} (id={cur.lastrowid})')
    return int(cur.lastrowid)


def _backfill(conn: sqlite3.Connection, type_id: int) -> int:
    cur = conn.execute(
        f'UPDATE {TABLE} SET {COLUMN} = ? WHERE {COLUMN} IS NULL', (type_id,))
    print(f'  - [BACKFILL] {TABLE}.{COLUMN}: {cur.rowcount} 行')
    return cur.rowcount


def _ensure_index(conn: sqlite3.Connection) -> None:
    if _index_exists(conn, INDEX_NAME):
        print(f'  - [SKIP] 索引 {INDEX_NAME} 已存在')
        return
    conn.execute(
        f'CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON {TABLE}({COLUMN})')
    print(f'  - [ADD] 索引 {INDEX_NAME}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v169] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v169] 开始: 单据类型规范 · requisition.document_type_id')
        if not _table_exists(conn, TABLE):
            print(f'[v169] FAIL: 缺表 {TABLE}（请先应用 v168）')
            return False
        if not _table_exists(conn, TYPE_TABLE):
            print(f'[v169] FAIL: 缺表 {TYPE_TABLE}（请先应用 v110）')
            return False

        _ensure_column(conn)
        type_id = _seed_default_type(conn)
        _backfill(conn, type_id)
        _ensure_index(conn)
        conn.commit()
        print('[v169] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v169] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v169 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if COLUMN not in _columns(conn, TABLE):
            print(f'[v169 verify] FAIL: 缺列 {TABLE}.{COLUMN}')
            ok = False

        row = conn.execute(
            'SELECT id, scope_bo, level, status FROM type_definitions '
            'WHERE scope_bo=? AND level=? AND code=?',
            (TYPE_SCOPE, TYPE_LEVEL, TYPE_CODE)).fetchone()
        if not row:
            print('[v169 verify] FAIL: 缺默认类型 STD')
            ok = False
        elif row[3] != 'active':
            print(f'[v169 verify] FAIL: STD 状态为 {row[3]}，期望 active')
            ok = False

        if COLUMN in _columns(conn, TABLE):
            nulls = conn.execute(
                f'SELECT COUNT(*) FROM {TABLE} WHERE {COLUMN} IS NULL').fetchone()[0]
            total = conn.execute(f'SELECT COUNT(*) FROM {TABLE}').fetchone()[0]
            print(f'[v169 verify] {TABLE}: {total} 行，NULL {COLUMN} {nulls} 条')
            if nulls:
                print(f'[v169 verify] FAIL: 存在 {COLUMN} 为 NULL 的存量行')
                ok = False

        if not _index_exists(conn, INDEX_NAME):
            print(f'[v169 verify] FAIL: 缺索引 {INDEX_NAME}')
            ok = False

        print('[v169 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v169 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _index_exists(conn, INDEX_NAME):
            conn.execute(f'DROP INDEX IF EXISTS {INDEX_NAME}')
            print(f'  - [DROP] 索引 {INDEX_NAME}')
        conn.commit()
        print('[v169 rollback] 完成（列与默认类型保留：由 YAML 声明 / 可能已被引用）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v169 rollback] 失败: %s' % e)
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
