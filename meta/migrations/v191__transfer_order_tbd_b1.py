# -*- coding: utf-8 -*-
"""[v191 2026-11-02] 调拨单 TBD 收口 B1（迁移 + 类型 / 参数 / 视图）

依据:
  docs/specs/tasks-transfer-order-object-model-2026-11-02.md §12 B1

范围:
  1. transfer_orders 增列 reversal_of_transfer_id（可空）+ 索引
     idx_transfer_order_reversal；
  2. type_definitions 行类型种子：TRF_SERVICE / TRF_ASSET / TRF_TEXT
     （delivery_relevant=0，不参与发货 / 收货）；
     不改 TRF_STD.default_type_id（仍为 TRF_GOODS）；
  3. line_type_assignments 种子：TRF_STD + 通配物料组 → TRF_GOODS（rank 900）；
     表不存在则 SKIP；
  4. 控制参数 transfer_over_ship_percent / transfer_over_receive_percent
     （number，默认 0，domain=procurement，target_bo=transfer_order）；
  5. 重建 document_types / line_types 视图，末尾追加 scope_bo（TBD-11）。

幂等:
  列 / 索引 / 类型 / assignment / 参数先查后用；视图每次 DROP + CREATE
  （定义收敛到同一份 SQL）。重复执行打印 [SKIP]。

回滚:
  删索引 / 行类型 / assignment 种子 / 参数，恢复旧视图（无 scope_bo）。
  SQLite 不支持 DROP COLUMN，列 reversal_of_transfer_id 保留（仅不再被使用）。
"""
import sqlite3
import sys
from pathlib import Path

TO_TABLE = 'transfer_orders'
TYPE_TABLE = 'type_definitions'
ASSIGNMENT_TABLE = 'line_type_assignments'
PARAM_TABLE = 'control_parameter_defs'

REVERSAL_COLUMN = 'reversal_of_transfer_id'
REVERSAL_INDEX = 'idx_transfer_order_reversal'
REVERSAL_INDEX_SQL = (
    'CREATE INDEX IF NOT EXISTS idx_transfer_order_reversal '
    'ON transfer_orders(reversal_of_transfer_id)')

SCOPE_BO = 'transfer_order'
HEADER_TYPE_CODE = 'TRF_STD'
GOODS_TYPE_CODE = 'TRF_GOODS'

#: 非交付行类型 (code, name, line_category, delivery_relevant, description)
LINE_TYPES = (
    ('TRF_SERVICE', '服务行', 'service', 0,
     '不发货、不分期确认的调拨服务行；release 时自动关闭'),
    ('TRF_ASSET', '资产行', 'asset', 0,
     '资产 / 设备类调拨行，不参与发货收货；release 时自动关闭'),
    ('TRF_TEXT', '文本行', 'text', 0,
     '仅承载说明文字的文本行，不参与发货收货；release 时自动关闭'),
)

ASSIGNMENT_RANK = 900

#: (code, name, value_type, default_value, description)
PARAMS = (
    ('transfer_over_ship_percent', '调拨超发容差（%）', 'number', '0',
     '调拨行累计发货量允许超出计划量的百分比；0 = 不允许超发'),
    ('transfer_over_receive_percent', '调拨超收容差（%）', 'number', '0',
     '调拨行累计收货量允许超出已发货量的百分比；0 = 不允许超收'),
)

#: 视图定义（与 meta/schemas/{document_type,line_type}.yaml 逐字一致）
VIEWS = (
    ('document_types', """CREATE VIEW document_types AS
SELECT id, code, name,
       document_category AS category,
       default_type_id AS default_line_type_id,
       number_sequence_id,
       status, description, created_at, scope_bo
FROM type_definitions
WHERE level = 'header'"""),
    ('line_types', """CREATE VIEW line_types AS
SELECT id, code, name,
       line_category AS category,
       COALESCE(delivery_relevant, 1) AS delivery_relevant,
       status, description, created_at, scope_bo
FROM type_definitions
WHERE level = 'line'"""),
)

#: 回滚用旧视图定义（无 scope_bo）
OLD_VIEWS = (
    ('document_types', """CREATE VIEW document_types AS
SELECT id, code, name,
       document_category AS category,
       default_type_id AS default_line_type_id,
       number_sequence_id,
       status, description, created_at
FROM type_definitions
WHERE level = 'header'"""),
    ('line_types', """CREATE VIEW line_types AS
SELECT id, code, name,
       line_category AS category,
       COALESCE(delivery_relevant, 1) AS delivery_relevant,
       status, description, created_at
FROM type_definitions
WHERE level = 'line'"""),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _object_type(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _type_id(conn: sqlite3.Connection, code: str, level: str):
    row = conn.execute(
        'SELECT id FROM type_definitions WHERE scope_bo=? AND level=? AND code=?',
        (SCOPE_BO, level, code)).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# 列 / 索引
# ---------------------------------------------------------------------------
def _do_column(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TO_TABLE):
        print(f'  - [SKIP] 表 {TO_TABLE} 不存在')
        return
    if REVERSAL_COLUMN in _columns(conn, TO_TABLE):
        print(f'  - [SKIP] 列 {TO_TABLE}.{REVERSAL_COLUMN} 已存在')
        return
    conn.execute(
        'ALTER TABLE %s ADD COLUMN %s INTEGER' % (TO_TABLE, REVERSAL_COLUMN))
    print(f'  - [CREATE] 列 {TO_TABLE}.{REVERSAL_COLUMN}')


def _do_index(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TO_TABLE):
        print(f'  - [SKIP] 索引 {REVERSAL_INDEX} 依赖表 {TO_TABLE} 不存在')
        return
    if _index_exists(conn, REVERSAL_INDEX):
        print(f'  - [SKIP] 索引 {REVERSAL_INDEX} 已存在')
        return
    conn.execute(REVERSAL_INDEX_SQL)
    print(f'  - [CREATE] 索引 {REVERSAL_INDEX}')


# ---------------------------------------------------------------------------
# 行类型
# ---------------------------------------------------------------------------
def _ensure_line_type(conn: sqlite3.Connection, code: str, name: str,
                      line_category: str, delivery_relevant: int,
                      description: str) -> int:
    existing = _type_id(conn, code, 'line')
    if existing:
        print(f'  - [SKIP] 行类型 {SCOPE_BO}/line/{code} 已存在 (id={existing})')
        return int(existing)
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    cur = conn.execute(
        'INSERT INTO type_definitions '
        '(code, name, scope_bo, level, line_category, delivery_relevant, '
        ' status, description, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (code, name, SCOPE_BO, 'line', line_category, delivery_relevant,
         'active', description, now))
    new_id = int(cur.lastrowid)
    print(f'  - [CREATE] 行类型 {SCOPE_BO}/line/{code} (id={new_id})')
    return new_id


def _do_line_types(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TYPE_TABLE):
        print(f'  - [SKIP] 表 {TYPE_TABLE} 不存在')
        return
    for code, name, line_category, delivery_relevant, desc in LINE_TYPES:
        _ensure_line_type(conn, code, name, line_category, delivery_relevant, desc)


# ---------------------------------------------------------------------------
# 行类型确定种子
# ---------------------------------------------------------------------------
def _do_assignment(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, ASSIGNMENT_TABLE):
        print(f'  - [SKIP] 表 {ASSIGNMENT_TABLE} 不存在')
        return
    header_id = _type_id(conn, HEADER_TYPE_CODE, 'header')
    goods_id = _type_id(conn, GOODS_TYPE_CODE, 'line')
    if not header_id or not goods_id:
        print(f'  - [SKIP] 缺 {HEADER_TYPE_CODE} / {GOODS_TYPE_CODE}，跳过 assignment')
        return
    row = conn.execute(
        'SELECT id FROM line_type_assignments WHERE document_type_id=? '
        'AND item_group_id IS NULL AND line_type_id=?',
        (header_id, goods_id)).fetchone()
    if row:
        print(f'  - [SKIP] assignment {HEADER_TYPE_CODE}→{GOODS_TYPE_CODE} 已存在 (id={row[0]})')
        return
    conn.execute(
        'INSERT INTO line_type_assignments '
        '(document_type_id, item_group_id, specificity_rank, line_type_id, '
        ' status, created_at) '
        "VALUES (?, NULL, ?, ?, 'active', datetime('now'))",
        (header_id, ASSIGNMENT_RANK, goods_id))
    print(f'  - [CREATE] assignment {HEADER_TYPE_CODE}→{GOODS_TYPE_CODE} (rank={ASSIGNMENT_RANK})')


# ---------------------------------------------------------------------------
# 控制参数
# ---------------------------------------------------------------------------
def _do_params(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, PARAM_TABLE):
        print(f'  - [SKIP] 表 {PARAM_TABLE} 不存在')
        return
    for code, name, value_type, default_value, desc in PARAMS:
        row = conn.execute(
            'SELECT id FROM control_parameter_defs WHERE code=?', (code,)).fetchone()
        if row:
            conn.execute(
                'UPDATE control_parameter_defs SET name=?, domain=?, value_type=?, '
                'target_bo=?, default_value=?, description=?, status=? WHERE id=?',
                (name, 'procurement', value_type, 'transfer_order',
                 default_value, desc, 'active', row[0]))
            print(f'  - [SKIP] 参数 {code} 已存在 (id={row[0]})')
            continue
        conn.execute(
            'INSERT INTO control_parameter_defs '
            '(code, name, domain, value_type, target_bo, default_value, status, '
            ' description, created_at) '
            "VALUES (?, ?, 'procurement', ?, 'transfer_order', ?, 'active', ?, "
            "datetime('now'))",
            (code, name, value_type, default_value, desc))
        print(f'  - [CREATE] 参数 {code}')


# ---------------------------------------------------------------------------
# 视图
# ---------------------------------------------------------------------------
def _rebuild_view(conn: sqlite3.Connection, name: str, sql: str) -> None:
    obj_type = _object_type(conn, name)
    if obj_type == 'table':
        raise RuntimeError('%s 是表不是视图，需人工处理' % name)
    if obj_type == 'view':
        conn.execute('DROP VIEW IF EXISTS %s' % name)
        print(f'  - [REBUILD] 视图 {name}')
    else:
        print(f'  - [CREATE] 视图 {name}')
    conn.execute(sql)


def _do_views(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TYPE_TABLE):
        print(f'  - [SKIP] 表 {TYPE_TABLE} 不存在')
        return
    if 'scope_bo' not in _columns(conn, TYPE_TABLE):
        raise RuntimeError('type_definitions 缺列 scope_bo')
    for name, sql in VIEWS:
        _rebuild_view(conn, name, sql)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v191] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v191] 开始: 调拨单 TBD 收口 B1')
        _do_column(conn)
        _do_index(conn)
        _do_line_types(conn)
        _do_assignment(conn)
        _do_params(conn)
        _do_views(conn)
        conn.commit()
        print('[v191] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v191] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v191 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True

        if REVERSAL_COLUMN not in _columns(conn, TO_TABLE):
            print(f'[v191 verify] FAIL: 缺列 {TO_TABLE}.{REVERSAL_COLUMN}')
            ok = False

        if not _index_exists(conn, REVERSAL_INDEX):
            print(f'[v191 verify] FAIL: 缺索引 {REVERSAL_INDEX}')
            ok = False

        if _table_exists(conn, TYPE_TABLE):
            for code, _name, line_category, delivery_relevant, _desc in LINE_TYPES:
                type_id = _type_id(conn, code, 'line')
                if not type_id:
                    print(f'[v191 verify] FAIL: 缺行类型 {code}')
                    ok = False
                    continue
                row = conn.execute(
                    'SELECT line_category, delivery_relevant, status '
                    'FROM type_definitions WHERE id=?', (type_id,)).fetchone()
                if (row[0] or '') != line_category:
                    print(f'[v191 verify] FAIL: 行类型 {code} line_category 不符')
                    ok = False
                if int(row[1] or 0) != delivery_relevant:
                    print(f'[v191 verify] FAIL: 行类型 {code} delivery_relevant 不符')
                    ok = False
                if (row[2] or '') != 'active':
                    print(f'[v191 verify] FAIL: 行类型 {code} 未启用')
                    ok = False

            header_id = _type_id(conn, HEADER_TYPE_CODE, 'header')
            goods_id = _type_id(conn, GOODS_TYPE_CODE, 'line')
            if not header_id or not goods_id:
                print('[v191 verify] FAIL: 缺 TRF_STD / TRF_GOODS')
                ok = False
            else:
                row = conn.execute(
                    'SELECT default_type_id FROM type_definitions WHERE id=?',
                    (header_id,)).fetchone()
                if row and int(row[0] or 0) != int(goods_id):
                    print('[v191 verify] FAIL: TRF_STD.default_type_id 未指向 TRF_GOODS')
                    ok = False

            if _table_exists(conn, ASSIGNMENT_TABLE):
                if not header_id or not goods_id:
                    ok = False
                elif not conn.execute(
                        'SELECT 1 FROM line_type_assignments WHERE document_type_id=? '
                        'AND item_group_id IS NULL AND line_type_id=?',
                        (header_id, goods_id)).fetchone():
                    print('[v191 verify] FAIL: 缺 assignment TRF_STD→TRF_GOODS')
                    ok = False

        if _table_exists(conn, PARAM_TABLE):
            for code, _name, value_type, default_value, _desc in PARAMS:
                row = conn.execute(
                    'SELECT domain, value_type, target_bo, default_value, status '
                    'FROM control_parameter_defs WHERE code=?', (code,)).fetchone()
                if not row:
                    print(f'[v191 verify] FAIL: 缺参数 {code}')
                    ok = False
                    continue
                if (row[0] or '') != 'procurement':
                    print(f'[v191 verify] FAIL: 参数 {code} domain 不符')
                    ok = False
                if (row[1] or '') != value_type:
                    print(f'[v191 verify] FAIL: 参数 {code} value_type 不符')
                    ok = False
                if (row[2] or '') != 'transfer_order':
                    print(f'[v191 verify] FAIL: 参数 {code} target_bo 不符')
                    ok = False
                if str(row[3] or '') != default_value:
                    print(f'[v191 verify] FAIL: 参数 {code} default_value 不符')
                    ok = False
                if (row[4] or '') != 'active':
                    print(f'[v191 verify] FAIL: 参数 {code} 未启用')
                    ok = False

        for name, _sql in VIEWS:
            if _object_type(conn, name) != 'view':
                print(f'[v191 verify] FAIL: {name} 不是视图')
                ok = False
                continue
            cols = [r[1] for r in conn.execute('PRAGMA table_info(%s)' % name)]
            if not cols or cols[-1] != 'scope_bo':
                print(f'[v191 verify] FAIL: 视图 {name} 未在末尾暴露 scope_bo')
                ok = False

        print('[v191 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v191 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _index_exists(conn, REVERSAL_INDEX):
            conn.execute('DROP INDEX IF EXISTS %s' % REVERSAL_INDEX)
            print(f'  - [DROP] 索引 {REVERSAL_INDEX}')

        if _table_exists(conn, TYPE_TABLE):
            for code, _name, _category, _relevant, _desc in LINE_TYPES:
                cur = conn.execute(
                    'DELETE FROM type_definitions WHERE scope_bo=? AND level=? '
                    'AND code=?', (SCOPE_BO, 'line', code))
                if cur.rowcount:
                    print(f'  - [DROP] 行类型 {code}')

        if _table_exists(conn, ASSIGNMENT_TABLE):
            cur = conn.execute(
                'DELETE FROM line_type_assignments WHERE document_type_id IN '
                '(SELECT id FROM type_definitions WHERE scope_bo=? AND level=? '
                'AND code=?) AND item_group_id IS NULL AND line_type_id IN '
                '(SELECT id FROM type_definitions WHERE scope_bo=? AND level=? '
                'AND code=?)',
                (SCOPE_BO, 'header', HEADER_TYPE_CODE,
                 SCOPE_BO, 'line', GOODS_TYPE_CODE))
            if cur.rowcount:
                print('  - [DROP] assignment TRF_STD→TRF_GOODS')

        if _table_exists(conn, PARAM_TABLE):
            for code, _name, _value_type, _default, _desc in PARAMS:
                cur = conn.execute(
                    'DELETE FROM control_parameter_defs WHERE code=?', (code,))
                if cur.rowcount:
                    print(f'  - [DROP] 参数 {code}')

        if _table_exists(conn, TYPE_TABLE):
            for name, sql in OLD_VIEWS:
                _rebuild_view(conn, name, sql)

        if _table_exists(conn, TO_TABLE):
            print(f'  - [KEEP] 列 {TO_TABLE}.{REVERSAL_COLUMN}（SQLite 不支持 DROP COLUMN）')

        conn.commit()
        print('[v191 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v191 rollback] 失败: {e}')
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
