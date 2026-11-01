# -*- coding: utf-8 -*-
"""[v174 2026-11-01] 修正需求入口头表的外键目标（party_internal 视图 → parties 真表）

背景:
  `service_requests.requester_party_id` / `requisitions.requested_by_party_id` 的
  DDL 由 schema 生成器按 YAML `relations.target: party_internal` 输出
  `REFERENCES party_internal(id)`。而 `party_internal` 是 `parties` 上的只读视图
  （generated_schema.sql §party_internal），SQLite **不允许外键指向视图**：
  任何 INSERT 都报 `foreign key mismatch - "service_requests" referencing "party_internal"`，
  即 M1 两张头表在真实库上完全不可写。

修复:
  · YAML relations.target 改为真表 `party`（物理列存的即 parties.id，展示仍走
    party_internal 视图），generated_schema.sql 同步为 `REFERENCES parties(id)`
  · 本迁移对已存在的两张头表做「原 DDL 打补丁 → 建新表 → 拷数据 → 删旧表 → 改名 →
    重建索引」，保留全部行与列（含 created_by / updated_by / document_type_id 等
    后续迁移追加的列）。
  · 幂等：DDL 中已无 party_internal 时打印 [SKIP]；表不存在时留给 v168 / sync_schema。

回滚:
  反向重建（parties → party_internal）。注意回滚后该表重新不可写，仅用于结构回退。
"""
import re
import sqlite3
import sys
from pathlib import Path

REQUEST_TABLE = 'service_requests'
REQUISITION_TABLE = 'requisitions'
TABLES = (REQUEST_TABLE, REQUISITION_TABLE)

_OLD_FK = 'REFERENCES party_internal(id)'
_NEW_FK = 'REFERENCES parties(id)'

_CREATE_RE = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{table}\s*\('


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _table_ddl(conn: sqlite3.Connection, table: str):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row else None


def _indexes(conn: sqlite3.Connection, table: str):
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
        "AND sql IS NOT NULL", (table,)
    ).fetchall()
    return [r[1] for r in rows]


def _fk_targets(conn: sqlite3.Connection, table: str) -> list:
    """PRAGMA foreign_key_list → [(被引用表, 被引用列)]"""
    return [(row[2], row[3]) for row in
            conn.execute('PRAGMA foreign_key_list({0})'.format(table)).fetchall()]


def _rebuild(conn: sqlite3.Connection, table: str,
             old_fk: str, new_fk: str, tag: str) -> None:
    ddl = _table_ddl(conn, table)
    if not ddl:
        print('  - [SKIP] 表 {0} 不存在（由 v168 / sync_schema 创建）'.format(table))
        return
    if old_fk not in ddl:
        print('  - [SKIP] 表 {0} 无需重建（未引用 {1}）'.format(
            table, old_fk.split()[-1]))
        return
    if not _table_exists(conn, 'parties'):
        print('  - [SKIP] 表 {0}：parties 真表不存在，无法改指向'.format(table))
        return

    tmp = '_rebuild_{0}'.format(table)
    conn.execute('DROP TABLE IF EXISTS {0}'.format(tmp))
    idx_sqls = _indexes(conn, table)  # 必须在删旧表前抓取（DROP 会连带删索引）

    fixed = re.sub(_CREATE_RE.format(table=table),
                   'CREATE TABLE {0} ('.format(tmp), ddl, count=1)
    if tmp not in fixed:
        raise RuntimeError('无法改写建表语句: {0}'.format(table))
    fixed = fixed.replace(old_fk, new_fk)

    conn.execute(fixed)
    cols = [row[1] for row in conn.execute(
        'PRAGMA table_info({0})'.format(table)).fetchall()]
    col_list = ', '.join(cols)
    conn.execute('INSERT INTO {0} ({1}) SELECT {1} FROM {2}'.format(
        tmp, col_list, table))
    copied = conn.execute('SELECT COUNT(*) FROM {0}'.format(tmp)).fetchone()[0]

    conn.execute('DROP TABLE {0}'.format(table))
    conn.execute('ALTER TABLE {0} RENAME TO {1}'.format(tmp, table))
    for sql in idx_sqls:
        conn.execute(sql)
    print('  - [{0}] 表 {1} 重建完成（保留 {2} 行，FK → parties）'.format(
        tag, table, copied))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v174] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        # 重建期间必须关闭外键校验（子表 FK 指向被重建的头表）
        conn.execute('PRAGMA foreign_keys=OFF')
        print('[v174] 开始: 需求入口头表外键目标修正')
        for table in TABLES:
            _rebuild(conn, table, _OLD_FK, _NEW_FK, 'FIX')
        conn.commit()
        print('[v174] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v174] 失败: {0}'.format(e))
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v174 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table in TABLES:
            if not _table_exists(conn, table):
                print('[v174 verify] SKIP: 表 {0} 尚未创建'.format(table))
                continue
            targets = [t for t, _col in _fk_targets(conn, table)]
            if 'party_internal' in targets:
                print('[v174 verify] FAIL: {0} 仍引用 party_internal'.format(table))
                ok = False
            elif 'parties' not in targets:
                print('[v174 verify] FAIL: {0} 缺少 parties 外键'.format(table))
                ok = False
            else:
                print('[v174 verify] OK: {0} 外键指向 parties'.format(table))
        print('[v174 verify] {0}'.format('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    """结构回退：parties → party_internal（回退后该两张表重新不可写）。"""
    if not db_path.exists():
        print('[v174 rollback] DB 不存在: {0}'.format(db_path))
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        conn.execute('PRAGMA foreign_keys=OFF')
        for table in TABLES:
            _rebuild(conn, table, _NEW_FK, _OLD_FK, 'ROLLBACK')
        conn.commit()
        print('[v174 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v174 rollback] 失败: {0}'.format(e))
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
    print('DB: {0}'.format(db))

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)
