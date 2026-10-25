# -*- coding: utf-8 -*-
"""[v110 2026-10-25] 单据类型 / 行类型统一为 type_definition

依据: docs/superpowers/specs/2026-10-25-type-definition-generalization-spec.md

本迁移做五件事（幂等）:
  1. CREATE TABLE IF NOT EXISTS type_definitions（DDL 由
     meta/schemas/type_definition.yaml 经 SchemaGenerator('sqlite') 冻结于此）
     + 复合唯一索引 idx_type_definition_scope_code (scope_bo, level, code)
  2. 数据搬迁:
       sales_document_types 2 行 → type_definitions，id 保持，level='header'
       sales_line_types 5 行 → type_definitions，新 id = 原 id + 100，level='line'
       单据类型 default_line_type_id 重映射: 1→101、3→103（统一 old_id + 100）
  3. DROP TABLE sales_document_types / sales_line_types
     —— 必须先删表：同名视图由服务启动时的 sync_schema_from_meta 以
        CREATE VIEW IF NOT EXISTS 重建；表名占位会导致视图创建失败
  4. 子表外键改指 type_definitions:
       control_parameter_values / sales_line_type_assignments 的物理外键原先指向
       旧表名；旧表降级为视图后，SQLite 会拒绝写入（foreign key mismatch）。
       SQLite 不支持 ALTER FOREIGN KEY，故按"建新表 → 拷行 → 换名 → 重建索引"
       重建这两张子表，并把存量行的 sales_line_type_id 同步 +100。
  5. 幂等: 按 (scope_bo, level, code) 判重，重复执行不产生重复行；
     子表重建仅在仍引用旧表名时才做，行重映射仅在旧表仍为表时做。

回滚:
  rollback() 重建两张旧表并把 type_definitions 中的 sales_order 切片写回，
  再删除 type_definitions。旧名视图需先 DROP VIEW。
"""
import re
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v110__type_definitions.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

SCOPE = 'sales_order'

DOC_TABLE = 'sales_document_types'
LINE_TABLE = 'sales_line_types'
NEW_TABLE = 'type_definitions'

# ---- 冻结 DDL（由 type_definition.yaml 经 SchemaGenerator('sqlite') 生成）----
NEW_DDL = """CREATE TABLE IF NOT EXISTS type_definitions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    scope_bo VARCHAR(200) NOT NULL,
    level VARCHAR(200) NOT NULL,
    document_category VARCHAR(200) DEFAULT 'standard',
    default_type_id INTEGER,
    number_sequence_id INTEGER,
    line_category VARCHAR(200) DEFAULT 'material',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (default_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (number_sequence_id) REFERENCES number_sequences(id)
)"""

NEW_INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_type_definition_scope_code "
    "ON type_definitions (scope_bo, level, code)"
)
NEW_STATUS_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_type_definition_scope_status "
    "ON type_definitions (scope_bo, level, status)"
)

# 回滚用：旧表 DDL（迁移前形态，仅保留业务列，够读回即可）
OLD_DOC_DDL = """CREATE TABLE IF NOT EXISTS sales_document_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(200) NOT NULL DEFAULT 'standard',
    default_line_type_id INTEGER,
    number_sequence_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME
)"""

OLD_LINE_DDL = """CREATE TABLE IF NOT EXISTS sales_line_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(200) NOT NULL DEFAULT 'material',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME
)"""


def _object_type(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    return row[0] if row else None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return _object_type(conn, name) == 'table'


def _view_exists(conn: sqlite3.Connection, name: str) -> bool:
    return _object_type(conn, name) == 'view'


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table).fetchall()}


def _upsert_type(conn: sqlite3.Connection, row: dict) -> str:
    """按 (scope_bo, level, code) 判重；存在则只刷新业务属性，不覆盖 status。"""
    existing = conn.execute(
        "SELECT id FROM type_definitions WHERE scope_bo = ? AND level = ? AND code = ?",
        (row['scope_bo'], row['level'], row['code']),
    ).fetchone()
    if existing:
        sets = ['name = ?']
        params = [row['name']]
        for col in ('document_category', 'line_category', 'default_type_id',
                    'number_sequence_id', 'description'):
            if col in row:
                sets.append('%s = ?' % col)
                params.append(row[col])
        params.append(existing[0])
        conn.execute(
            "UPDATE type_definitions SET %s WHERE id = ?" % ', '.join(sets), params
        )
        return 'updated'

    cols = ['code', 'name', 'scope_bo', 'level', 'status', 'created_at']
    vals = [row['code'], row['name'], row['scope_bo'], row['level'],
            row.get('status') or 'active', row.get('created_at')]
    for col in ('document_category', 'line_category', 'default_type_id',
                'number_sequence_id', 'description'):
        if col in row:
            cols.append(col)
            vals.append(row[col])

    if row.get('id') is not None:
        cols.insert(0, 'id')
        vals.insert(0, row['id'])
    conn.execute(
        "INSERT INTO type_definitions (%s) VALUES (%s)" % (
            ', '.join(cols), ', '.join('?' * len(cols))),
        vals,
    )
    return 'inserted'


def _migrate_doc_types(conn: sqlite3.Connection) -> tuple:
    """header: id 保持、scope_bo=SCOPE、level='header'、document_category=category。"""
    if not _table_exists(conn, DOC_TABLE):
        print('  - [SKIP] %s 不存在或已是视图' % DOC_TABLE)
        return (0, 0)

    cols = _columns(conn, DOC_TABLE)
    fallback_line = 'default_line_type_id' if 'default_line_type_id' in cols \
        else 'default_type_id'
    rows = conn.execute(
        "SELECT id, code, name, category, %s, number_sequence_id, status, "
        "description, created_at FROM %s ORDER BY id" % (fallback_line, DOC_TABLE)
    ).fetchall()

    inserted = updated = 0
    for (rid, code, name, category, default_line_type_id,
         number_sequence_id, status, description, created_at) in rows:
        # default_line_type_id 指向旧行类型 id，新 id = old + 100
        new_default = (default_line_type_id + 100) \
            if default_line_type_id is not None else None
        result = _upsert_type(conn, {
            'id': rid,
            'code': code,
            'name': name,
            'scope_bo': SCOPE,
            'level': 'header',
            'document_category': category,
            'default_type_id': new_default,
            'number_sequence_id': number_sequence_id,
            'status': status,
            'description': description,
            'created_at': created_at,
        })
        inserted += result == 'inserted'
        updated += result == 'updated'
    print('  - [MOVE] %s → type_definitions(header): %d inserted, %d updated'
          % (DOC_TABLE, inserted, updated))
    return (inserted, updated)


def _migrate_line_types(conn: sqlite3.Connection) -> tuple:
    """line: 新 id = 原 id + 100、level='line'、line_category=category。"""
    if not _table_exists(conn, LINE_TABLE):
        print('  - [SKIP] %s 不存在或已是视图' % LINE_TABLE)
        return (0, 0)

    rows = conn.execute(
        "SELECT id, code, name, category, status, description, created_at "
        "FROM %s ORDER BY id" % LINE_TABLE
    ).fetchall()

    inserted = updated = 0
    for (rid, code, name, category, status, description, created_at) in rows:
        result = _upsert_type(conn, {
            'id': rid + 100,
            'code': code,
            'name': name,
            'scope_bo': SCOPE,
            'level': 'line',
            'line_category': category,
            'status': status,
            'description': description,
            'created_at': created_at,
        })
        inserted += result == 'inserted'
        updated += result == 'updated'
    print('  - [MOVE] %s → type_definitions(line): %d inserted, %d updated'
          % (LINE_TABLE, inserted, updated))
    return (inserted, updated)


def _drop_old_tables(conn: sqlite3.Connection) -> None:
    for table in (DOC_TABLE, LINE_TABLE):
        if _table_exists(conn, table):
            conn.execute("DROP TABLE %s" % table)
            print('  - [DROP] TABLE %s（视图由下次启动重建）' % table)
        elif _view_exists(conn, table):
            print('  - [SKIP] %s 已是视图' % table)
        else:
            print('  - [SKIP] %s 不存在' % table)


# ---- 子表外键改指 ----
# 旧表降级为视图后，物理外键仍指向表名会让 SQLite 直接报
# `foreign key mismatch`（视图不能做 FK 父表）。SQLite 不支持
# ALTER FOREIGN KEY，只能重建表。

REF_TABLES = ('control_parameter_values', 'sales_line_type_assignments')

_FK_RE = re.compile(
    r'(FOREIGN\s+KEY\s*\(\s*(?P<col>\w+)\s*\)\s*REFERENCES\s+)(?P<ref>\w+)',
    re.IGNORECASE,
)


def _retarget_fks(sql: str, mapping: dict) -> str:
    """按列名改写 REFERENCES 目标；mapping: {列名(小写): 目标表}。"""
    def _repl(m):
        target = mapping.get(m.group('col').lower())
        if not target or target.lower() == m.group('ref').lower():
            return m.group(0)
        return m.group(1) + target
    return _FK_RE.sub(_repl, sql)


def _rename_create_target(sql: str, table: str) -> str:
    return re.sub(
        r'^(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)[^\s(]+',
        r'\1%s' % table, sql, count=1, flags=re.IGNORECASE,
    )


def _remap_child_refs(conn: sqlite3.Connection) -> None:
    """存量子表行: 行类型 id 已整体 +100，同步改引用（仅首次执行调用）。"""
    for table in REF_TABLES:
        if not _table_exists(conn, table):
            continue
        conn.execute(
            'UPDATE %s SET sales_line_type_id = sales_line_type_id + 100 '
            'WHERE sales_line_type_id IS NOT NULL' % table)
        print('  - [REMAP] %s.sales_line_type_id += 100' % table)


def _retarget_referencing_tables(conn: sqlite3.Connection,
                                 mapping: dict) -> None:
    """重建子表以改外键目标（幂等：已指向目标则跳过）。"""
    for table in REF_TABLES:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = ? AND type = 'table'",
            (table,)).fetchone()
        if not row or not row[0]:
            continue
        new_sql = _retarget_fks(row[0], mapping)
        if new_sql == row[0]:
            continue

        tmp = '%s__fk_rebuild' % table
        cols = [r[1] for r in conn.execute(
            'PRAGMA table_info(%s)' % table).fetchall()]
        idx_sqls = [r[0] for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = 'index' "
            "AND sql IS NOT NULL", (table,)).fetchall()]

        conn.execute('DROP TABLE IF EXISTS %s' % tmp)
        conn.execute(_rename_create_target(new_sql, tmp))
        col_list = ', '.join(cols)
        conn.execute('INSERT INTO %s (%s) SELECT %s FROM %s'
                     % (tmp, col_list, col_list, table))
        conn.execute('DROP TABLE %s' % table)
        conn.execute('ALTER TABLE %s RENAME TO %s' % (tmp, table))
        for isql in idx_sqls:
            conn.execute(isql)
        print('  - [FK] %s 外键改指（重建表，%d 个索引）' % (table, len(idx_sqls)))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v110] DB 不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print('[v110] 开始: 单据类型 / 行类型 → type_definitions')
        conn.execute('PRAGMA foreign_keys = OFF')
        conn.execute(NEW_DDL)
        conn.execute(NEW_INDEX_DDL)
        conn.execute(NEW_STATUS_INDEX_DDL)
        print('  - [DDL] type_definitions + 2 个索引就绪')

        _migrate_line_types(conn)   # 先搬 line，header 的 default_type_id 才有落点
        _migrate_doc_types(conn)

        # 旧表仍为物理表 ⇒ 首次执行：子表存量行同步重映射（重复执行会二次 +100）
        if _table_exists(conn, LINE_TABLE):
            _remap_child_refs(conn)

        _drop_old_tables(conn)
        _retarget_referencing_tables(conn, {
            'sales_document_type_id': NEW_TABLE,
            'sales_line_type_id': NEW_TABLE,
        })

        conn.commit()
        print('  - [DONE] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v110] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, NEW_TABLE):
            print('[v110 verify] FAIL: type_definitions 不存在')
            return False

        total = conn.execute('SELECT count(1) FROM type_definitions').fetchone()[0]
        headers = conn.execute(
            "SELECT count(1) FROM type_definitions WHERE scope_bo = ? AND level = 'header'",
            (SCOPE,)).fetchone()[0]
        lines = conn.execute(
            "SELECT count(1) FROM type_definitions WHERE scope_bo = ? AND level = 'line'",
            (SCOPE,)).fetchone()[0]
        print('[v110 verify] 行数: total=%d header=%d line=%d' % (total, headers, lines))

        if headers != 2 or lines != 5:
            print('[v110 verify] FAIL: 期望 2 header + 5 line')
            return False

        for code, expect in (('TA', 101), ('RE', 103)):
            row = conn.execute(
                "SELECT default_type_id FROM type_definitions "
                "WHERE scope_bo = ? AND level = 'header' AND code = ?",
                (SCOPE, code)).fetchone()
            if not row or row[0] != expect:
                print('[v110 verify] FAIL: %s.default_type_id=%s, 期望 %d'
                      % (code, row[0] if row else None, expect))
                return False

        for name in (DOC_TABLE, LINE_TABLE):
            if not _view_exists(conn, name):
                # 视图由服务启动时 sync_schema_from_meta 重建，迁移时缺失属正常
                print('[v110 verify] WARN: %s 尚未重建为视图（重启服务后由 YAML 生成）'
                      % name)

        for table in REF_TABLES:
            if not _table_exists(conn, table):
                continue
            refs = {r[2] for r in conn.execute(
                'PRAGMA foreign_key_list(%s)' % table).fetchall()}
            bad = refs & {DOC_TABLE, LINE_TABLE}
            if bad:
                print('[v110 verify] FAIL: %s 的外键仍指向旧表 %s'
                      % (table, sorted(bad)))
                return False

        idx = conn.execute(
            "SELECT count(1) FROM sqlite_master WHERE type='index' "
            "AND name='idx_type_definition_scope_code'").fetchone()[0]
        if not idx:
            print('[v110 verify] FAIL: 缺少唯一索引 idx_type_definition_scope_code')
            return False

        print('[v110 verify] OK: 7 行（2 header + 5 line）、复合唯一索引存在、子表外键已改指')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    """回滚：重建旧表并写回 sales_order 切片，再删除 type_definitions。"""
    if not db_path.exists():
        print('[v110] DB 不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print('[v110] rollback: type_definitions → 旧表')
        conn.execute('PRAGMA foreign_keys = OFF')
        for name in (DOC_TABLE, LINE_TABLE):
            if _view_exists(conn, name):
                conn.execute('DROP VIEW %s' % name)
                print('  - [DROP] VIEW %s' % name)

        conn.execute(OLD_LINE_DDL)
        conn.execute(OLD_DOC_DDL)

        if _table_exists(conn, NEW_TABLE):
            for (rid, code, name, category, status, description, created_at) in \
                conn.execute(
                    "SELECT id, code, name, line_category, status, description, "
                    "created_at FROM type_definitions "
                    "WHERE scope_bo = ? AND level = 'line' ORDER BY id", (SCOPE,)
                ).fetchall():
                conn.execute(
                    "INSERT OR IGNORE INTO sales_line_types "
                    "(id, code, name, category, status, description, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (rid - 100, code, name, category, status, description, created_at))

            for (rid, code, name, category, default_type_id, number_sequence_id,
                 status, description, created_at) in conn.execute(
                    "SELECT id, code, name, document_category, default_type_id, "
                    "number_sequence_id, status, description, created_at "
                    "FROM type_definitions "
                    "WHERE scope_bo = ? AND level = 'header' ORDER BY id", (SCOPE,)
                ).fetchall():
                old_default = (default_type_id - 100) \
                    if default_type_id is not None else None
                conn.execute(
                    "INSERT OR IGNORE INTO sales_document_types "
                    "(id, code, name, category, default_line_type_id, "
                    " number_sequence_id, status, description, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rid, code, name, category, old_default, number_sequence_id,
                     status, description, created_at))

            conn.execute('DROP TABLE %s' % NEW_TABLE)
            print('  - [DROP] TABLE type_definitions')

        # 子表外键改回旧表，并把行类型引用回退 100（与升级路径对称）
        _retarget_referencing_tables(conn, {
            'sales_document_type_id': DOC_TABLE,
            'sales_line_type_id': LINE_TABLE,
        })
        for table in REF_TABLES:
            if table in (DOC_TABLE, LINE_TABLE):
                continue
            if not _table_exists(conn, table):
                continue
            conn.execute(
                'UPDATE %s SET sales_line_type_id = sales_line_type_id - 100 '
                'WHERE sales_line_type_id >= 100' % table)
            print('  - [REMAP] %s.sales_line_type_id -= 100' % table)

        conn.commit()
        print('  - [DONE] 回滚提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v110] rollback 失败: %s' % e)
        return False
    finally:
        conn.close()


# 兼容 migration_runner 的旧命名
downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print('[v110] migrate: %s' % ('OK' if _ok else 'FAIL'))
    _v = verify(_db)
    print('[v110] verify: %s' % ('PASS' if _v else 'FAIL'))
