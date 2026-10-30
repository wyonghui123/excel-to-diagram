# -*- coding: utf-8 -*-
"""v159 修正 calc_results.level 与 document_line_id 不一致的存量数据

背景
  `calc_results`（元模型 calc_result，见 meta/schemas/calc_result.yaml）同时承载
  表头级与单据行级定价结果，两者互斥：
    document_line_id IS NULL   ⇒ level='header'
    document_line_id IS NOT NULL ⇒ level='line'
  源码根因已在 `meta/services/pricing_service.py::determine` 修复（按
  document_line_id 推导 level），但存量数据仍有反例：实测 36 行中
  28 行 level='header' 却带 document_line_id，违反上述不变量。

本迁移做什么
  1. 建 `calc_result_level_backup (id INTEGER PRIMARY KEY, old_level TEXT)`
     记录被修正行的旧 level；
  2. `INSERT ... SELECT` 备份「待修正且尚未备份」的行；
  3. `UPDATE calc_results SET level='line'`
     `WHERE document_line_id IS NOT NULL AND level='header'`；
  4. 校验实际改变行数 == 待修正行数，不一致则 raise；
  5. 全过程单事务，异常 rollback + raise。

幂等
  - `CREATE TABLE IF NOT EXISTS` + `id NOT IN (SELECT id FROM backup)`：
    二次执行备份 0 行、UPDATE 0 行，不报错。

回滚（rollback = downgrade）
  - 按 backup 表 id 回填旧 level，成功后 DROP TABLE IF EXISTS
    calc_result_level_backup；事务 + 异常 rollback。
"""
import sqlite3
import sys
from pathlib import Path

SOURCE = 'calc_results'
BACKUP = 'calc_result_level_backup'

# 反例条件：单据行却标成 header
_BAD_SQL = "document_line_id IS NOT NULL AND level='header'"
# 修正后应有的行条件
_FIXED_SQL = "level='line' AND document_line_id IS NOT NULL"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


def migrate(db_path: Path, skip_backup: bool = True) -> bool:
    if not db_path.exists():
        print(f'[v159] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, SOURCE):
            print(f'[v159] {SOURCE} 不存在，跳过')
            return True

        print('[v159] 修正 calc_results.level / document_line_id 不一致')
        conn.execute('BEGIN')

        conn.execute(
            f'CREATE TABLE IF NOT EXISTS {BACKUP} '
            f'(id INTEGER PRIMARY KEY, old_level TEXT)'
        )

        expected = _count(conn, f'SELECT COUNT(*) FROM {SOURCE} WHERE {_BAD_SQL}')

        conn.execute(
            f'INSERT INTO {BACKUP} (id, old_level) '
            f'SELECT id, level FROM {SOURCE} WHERE {_BAD_SQL} '
            f'AND id NOT IN (SELECT id FROM {BACKUP})'
        )

        before_lines = _count(conn, f'SELECT COUNT(*) FROM {SOURCE} WHERE {_FIXED_SQL}')
        conn.execute(f"UPDATE {SOURCE} SET level='line' WHERE {_BAD_SQL}")
        after_lines = _count(conn, f'SELECT COUNT(*) FROM {SOURCE} WHERE {_FIXED_SQL}')
        changed = after_lines - before_lines
        if changed != expected:
            raise RuntimeError(
                f'修正行数不一致: changed={changed} expected={expected}'
            )

        residual = _count(conn, f'SELECT COUNT(*) FROM {SOURCE} WHERE {_BAD_SQL}')
        conn.commit()

        print(f'  修正行数: {changed}')
        print(f'  残留反例: {residual}')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v159] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v159 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, SOURCE):
            print(f'[v159 verify] OK: {SOURCE} 不存在，无需校验')
            return True

        residual = _count(conn, f'SELECT COUNT(*) FROM {SOURCE} WHERE {_BAD_SQL}')
        if residual:
            print(f'[v159 verify] FAIL: 仍有 {residual} 行 document_line_id 非空却 level=header')
            return False
        print('[v159 verify] OK: 反例 0 行')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """按 backup 表回填旧 level，然后 DROP backup。"""
    if not db_path.exists():
        print(f'[v159] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, BACKUP):
            print(f'[v159] rollback: {BACKUP} 不存在，无需回滚')
            return True
        if not _table_exists(conn, SOURCE):
            print(f'[v159] rollback FAIL: {SOURCE} 不存在，无法回填（{BACKUP} 保留）')
            return False

        print(f'[v159] rollback: {BACKUP} 回填 calc_results.level')
        conn.execute('BEGIN')
        conn.execute(
            f'UPDATE {SOURCE} '
            f'SET level=(SELECT b.old_level FROM {BACKUP} b WHERE b.id={SOURCE}.id) '
            f'WHERE id IN (SELECT id FROM {BACKUP}) '
            f'AND EXISTS (SELECT 1 FROM {BACKUP} b WHERE b.id={SOURCE}.id)'
        )
        restored = _count(conn, f'SELECT COUNT(*) FROM {SOURCE} WHERE {_BAD_SQL}')
        conn.execute(f'DROP TABLE IF EXISTS {BACKUP}')
        conn.commit()
        print(f'  回填后反例行数: {restored}，{BACKUP} 已删除')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v159] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v159] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v159] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v159] verify: {"PASS" if _v else "FAIL"}')
