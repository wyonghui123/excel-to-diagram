# -*- coding: utf-8 -*-
"""[v170 2026-11-01] 业务单据类型规范 —— 其余业务单据头补 document_type_id

依据:
  docs/specs/spec-procurement-task-object-model-2026-10-31.md T-D20（单据类型规范）

规范:
  所有业务单据头必备「单据类型」，统一引用 type_definitions 的 header 行
  （scope_bo=<BO YAML id> + level='header'）。字段与 value_help 由平台切面
  `document_type_aspect`（meta/schemas/aspects.yaml）提供。

本迁移对 4 张既有单据做同一组动作（幂等）:
  ① 补列 document_type_id（库列可空：SQLite ALTER 不能加 NOT NULL）
  ② 种子默认类型（scope_bo=<BO>, level='header', code='STD'）
  ③ 存量行回填默认类型
  ④ 补索引

「创建时必填」由 DocumentTypeGuardInterceptor / DocumentTypeGuardService 承担，
不在库层做 NOT NULL（与 v169 同口径）。

回滚:
  列由 YAML 声明，保留；仅删本迁移补的索引。默认类型行保留（可能已被引用）。
"""
import sqlite3
import sys
from pathlib import Path

COLUMN = 'document_type_id'
TYPE_TABLE = 'type_definitions'
TYPE_LEVEL = 'header'
TYPE_CODE = 'STD'

#: (表名, 归属对象 id, 索引名, 默认类型名, 中文说明)
BOXES = (
    ('fulfillment_orders', 'fulfillment_order',
     'idx_fulfillment_order_document_type', '标准履约单', '履约单'),
    ('service_requests', 'service_request',
     'idx_service_request_document_type', '标准服务请求', '服务请求'),
    ('shipments', 'shipment',
     'idx_shipment_document_type', '标准交货单', '交货单'),
    ('work_orders', 'work_order',
     'idx_work_order_document_type', '标准工单', '服务工单'),
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


def _ensure_column(conn: sqlite3.Connection, table: str) -> None:
    if COLUMN in _columns(conn, table):
        print(f'  - [SKIP] {table}.{COLUMN} 已存在')
        return
    conn.execute(f'ALTER TABLE {table} ADD COLUMN {COLUMN} INTEGER')
    print(f'  - [ADD] {table}.{COLUMN}')


def _seed_default_type(conn: sqlite3.Connection, scope: str, name: str,
                       label: str) -> int:
    """按 (scope_bo, level, code) 判重；返回类型 id。"""
    row = conn.execute(
        'SELECT id FROM type_definitions WHERE scope_bo=? AND level=? AND code=?',
        (scope, TYPE_LEVEL, TYPE_CODE)).fetchone()
    if row:
        print(f'  - [SKIP] 默认类型 {scope}/{TYPE_LEVEL}/{TYPE_CODE} 已存在 (id={row[0]})')
        return int(row[0])

    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    cur = conn.execute(
        'INSERT INTO type_definitions '
        '(code, name, scope_bo, level, document_category, status, description, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (TYPE_CODE, name, scope, TYPE_LEVEL, 'standard', 'active',
         f'{label}默认单据类型（T-D20 种子；编号 / 审批 / 打印等治理语义的挂载点）', now))
    print(f'  - [NEW] 默认类型 {scope}/{TYPE_LEVEL}/{TYPE_CODE} (id={cur.lastrowid})')
    return int(cur.lastrowid)


def _backfill(conn: sqlite3.Connection, table: str, type_id: int) -> int:
    cur = conn.execute(
        f'UPDATE {table} SET {COLUMN} = ? WHERE {COLUMN} IS NULL', (type_id,))
    print(f'  - [BACKFILL] {table}.{COLUMN}: {cur.rowcount} 行')
    return cur.rowcount


def _ensure_index(conn: sqlite3.Connection, table: str, index_name: str) -> None:
    if _index_exists(conn, index_name):
        print(f'  - [SKIP] 索引 {index_name} 已存在')
        return
    conn.execute(
        f'CREATE INDEX IF NOT EXISTS {index_name} ON {table}({COLUMN})')
    print(f'  - [ADD] 索引 {index_name}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v170] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v170] 开始: 单据类型规范 · 业务单据头 document_type_id')
        if not _table_exists(conn, TYPE_TABLE):
            print(f'[v170] FAIL: 缺表 {TYPE_TABLE}（请先应用 v110）')
            return False

        for table, scope, index_name, type_name, label in BOXES:
            print(f'  · {label} ({table})')
            if not _table_exists(conn, table):
                print(f'  - [SKIP] 缺表 {table}（该单据尚未建表）')
                continue
            _ensure_column(conn, table)
            type_id = _seed_default_type(conn, scope, type_name, label)
            _backfill(conn, table, type_id)
            _ensure_index(conn, table, index_name)

        conn.commit()
        print('[v170] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v170] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v170 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table, scope, index_name, _type_name, label in BOXES:
            if not _table_exists(conn, table):
                print(f'[v170 verify] SKIP: 缺表 {table}')
                continue
            if COLUMN not in _columns(conn, table):
                print(f'[v170 verify] FAIL: 缺列 {table}.{COLUMN}')
                ok = False
                continue

            row = conn.execute(
                'SELECT id, status FROM type_definitions '
                'WHERE scope_bo=? AND level=? AND code=?',
                (scope, TYPE_LEVEL, TYPE_CODE)).fetchone()
            if not row:
                print(f'[v170 verify] FAIL: 缺默认类型 {scope}/{TYPE_CODE}')
                ok = False
            elif row[1] != 'active':
                print(f'[v170 verify] FAIL: {scope} STD 状态为 {row[1]}，期望 active')
                ok = False

            nulls = conn.execute(
                f'SELECT COUNT(*) FROM {table} WHERE {COLUMN} IS NULL').fetchone()[0]
            total = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            print(f'[v170 verify] {table}: {total} 行，NULL {COLUMN} {nulls} 条')
            if nulls:
                print(f'[v170 verify] FAIL: {table} 存在 {COLUMN} 为 NULL 的存量行')
                ok = False

            if not _index_exists(conn, index_name):
                print(f'[v170 verify] FAIL: 缺索引 {index_name}')
                ok = False

        print('[v170 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v170 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for table, _scope, index_name, _type_name, _label in BOXES:
            if _index_exists(conn, index_name):
                conn.execute(f'DROP INDEX IF EXISTS {index_name}')
                print(f'  - [DROP] 索引 {index_name}')
        conn.commit()
        print('[v170 rollback] 完成（列与默认类型保留：由 YAML 声明 / 可能已被引用）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v170 rollback] 失败: %s' % e)
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
