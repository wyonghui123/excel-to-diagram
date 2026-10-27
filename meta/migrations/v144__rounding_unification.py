# -*- coding: utf-8 -*-
"""[v144] 舍入字段统一：tax_code.rounding_mode → rounding（列改名 + 存量核查）

依据:
  D 项（SO 域扩展 · 舍入字段统一）
  docs/superpowers/specs/2026-10-27-sales-order-business-type-and-rounding-spec.md
    FR-004 / TR-001 / TR-002 / TR-004

背景:
  平台内 5 处舍入字段（allocation_rule.rounding / allocation_result.rounding /
  rate_type.rounding / pricing_period.rounding / tax_code.rounding_mode）
  存在三类不一致：
    1. 命名不统一 —— 4 处叫 `rounding`，tax_code 一处叫 `rounding_mode`；
    2. 取值域不统一 —— tax_code 只有 3 值（round/ceil/floor），缺 `none`；
    3. 3 处为死字段 —— tax_code.rounding_mode / rate_type.rounding /
       pricing_period.rounding 配了不生效且静默失效。
  本迁移只做**结构层**（列改名 + 存量核查）；取值域统一与消费方接线由
  YAML（SSOT）与业务代码完成。

本迁移内容:
  1. 断言 tax_codes 表存在（不存在提示先跑 sync_schema）
  2. 列改名：tax_codes.rounding_mode → tax_codes.rounding（SQLite 3.25+；
     幂等 —— 已是 `rounding` 则 SKIP）
  3. 存量核查：5 张表的舍入列值是否落在四值域
     {none, round, ceil, floor} 内 —— 超域值**只报告、不改写**
     （避免静默篡改业务数据；脏值由人工处置）
  4. 重复执行输出 SKIP

不做的:
  - 不改写任何业务数据（舍入方式属业务配置，不擅自变更）
  - 不建 rounding_profile 对象（平台既定分工：精度=currency.decimal_places，
    方向=rounding_mode 字典）
  - 不删列（列由 YAML 声明，删列会丢数据）

幂等:
  列先查后用；核查只读，不修改业务数据。

回滚:
  列名改回 rounding_mode（改名为元数据操作，数据不丢）。
"""
import sqlite3
from pathlib import Path

# 舍入方式唯一取值域（与平台字典 rounding_mode 一致）
ROUNDING_MODES = ('none', 'round', 'ceil', 'floor')

# 需核查的舍入列：(表名, 列名)
# 注意表名是**复数**（DB 实际表名，与 YAML 的 id 单数不同）
ROUNDING_COLUMNS = [
    ('allocation_rules', 'rounding'),
    ('allocation_results', 'rounding'),
    ('rate_types', 'rounding'),
    ('pricing_periods', 'rounding'),
    ('tax_codes', 'rounding'),
]

# tax_code 列改名：(表名, 旧列名, 新列名)
RENAME_COLUMNS = [
    ('tax_codes', 'rounding_mode', 'rounding'),
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> dict:
    if not _table_exists(conn, table):
        return {}
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _query(conn: sqlite3.Connection, sql: str, params: list = None) -> list:
    try:
        if params:
            return conn.execute(sql, params).fetchall()
        return conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []


def _report_out_of_domain(conn: sqlite3.Connection, table: str, column: str) -> int:
    """报告落在四值域外的存量值（只报告，不改写、不阻断）。"""
    if not _table_exists(conn, table):
        print(f'  - [SKIP] 表 {table} 不存在，跳过核查')
        return 0
    cols = _columns(conn, table)
    if column not in cols:
        print(f'  - [SKIP] {table}.{column} 不存在，跳过核查')
        return 0
    placeholders = ','.join('?' * len(ROUNDING_MODES))
    rows = _query(
        conn,
        f'SELECT id, {column} FROM {table} '
        f'WHERE {column} IS NOT NULL AND {column} NOT IN ({placeholders}) '
        f'ORDER BY id',
        list(ROUNDING_MODES),
    )
    if not rows:
        print(f'  - [CHECK] {table}.{column} 存量值全部落在四值域内：0 条越界')
        return 0
    print(f'  - [CHECK] {table}.{column} 越界值：{len(rows)} 条（只报告，不改写）')
    for row_id, value in rows:
        print(f'      id={row_id} {column}={value!r}')
    return len(rows)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v144] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v144] 开始: 舍入字段统一（列改名 + 存量核查）')
        if not _table_exists(conn, 'tax_codes'):
            print('[v144] 表 tax_codes 不存在：请先执行 '
                  '`python -m meta.tools.sync_schema --source sqlite '
                  '--local {db_path} --execute` 建表'.format(db_path=db_path))
            return False

        # 1. 列改名
        for table, old_col, new_col in RENAME_COLUMNS:
            cols = _columns(conn, table)
            if old_col in cols and new_col not in cols:
                conn.execute(f'ALTER TABLE {table} RENAME COLUMN {old_col} TO {new_col}')
                print(f'  - [RENAME] {table}.{old_col} → {table}.{new_col}')
            elif new_col in cols and old_col not in cols:
                print(f'  - [SKIP] {table}.{new_col} 已存在（改名已完成）')
            elif old_col in cols and new_col in cols:
                print(f'  - [WARN] {table} 同时存在 {old_col} 与 {new_col}，跳过改名（需人工处理）')
            else:
                print(f'  - [SKIP] {table}.{old_col} 不存在，跳过改名')

        # 2. 存量核查（只读）
        print('  - 存量核查（超域值只报告，不改写）:')
        total_dirty = 0
        for table, column in ROUNDING_COLUMNS:
            total_dirty += _report_out_of_domain(conn, table, column)

        conn.commit()
        if total_dirty:
            print(f'[v144] 迁移完成，但存在 {total_dirty} 条越界存量值，'
                  f'请人工处置（未自动改写）')
        else:
            print('[v144] 迁移完成：0 条越界存量值')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v144] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言改名已完成 + 5 处舍入列存在 + 无越界存量值。"""
    if not db_path.exists():
        print('[v144 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        ok = True

        # 1. 改名断言
        for table, old_col, new_col in RENAME_COLUMNS:
            if not _table_exists(conn, table):
                print(f'[v144 verify] FAIL: 表 {table} 不存在')
                ok = False
                continue
            cols = _columns(conn, table)
            if new_col not in cols:
                print(f'[v144 verify] FAIL: {table}.{new_col} 不存在（改名未完成）')
                ok = False
            elif old_col in cols:
                print(f'[v144 verify] FAIL: {table}.{old_col} 与 {new_col} 并存')
                ok = False

        # 2. 5 处舍入列存在
        for table, column in ROUNDING_COLUMNS:
            if not _table_exists(conn, table):
                continue
            cols = _columns(conn, table)
            if column not in cols:
                print(f'[v144 verify] FAIL: 缺列 {table}.{column}')
                ok = False

        # 3. 无越界存量值
        placeholders = ','.join('?' * len(ROUNDING_MODES))
        for table, column in ROUNDING_COLUMNS:
            if not _table_exists(conn, table):
                continue
            if column not in _columns(conn, table):
                continue
            dirty = _query(
                conn,
                f'SELECT COUNT(*) FROM {table} '
                f'WHERE {column} IS NOT NULL AND {column} NOT IN ({placeholders})',
                list(ROUNDING_MODES),
            )
            if dirty and dirty[0][0]:
                print(f'[v144 verify] FAIL: {table}.{column} 有 {dirty[0][0]} 条越界存量值')
                ok = False

        if ok:
            print('[v144 verify] PASS: tax_codes.rounding 改名完成；'
                  '5 处舍入列存在且存量值全部在四值域内')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """列名改回 rounding_mode（数据不丢）。"""
    if not db_path.exists():
        print(f'[v144] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for table, old_col, new_col in RENAME_COLUMNS:
            if not _table_exists(conn, table):
                print(f'  - [SKIP] 表 {table} 不存在')
                continue
            cols = _columns(conn, table)
            if new_col in cols and old_col not in cols:
                conn.execute(f'ALTER TABLE {table} RENAME COLUMN {new_col} TO {old_col}')
                print(f'  - [RENAME] {table}.{new_col} → {table}.{old_col}')
            else:
                print(f'  - [SKIP] {table}.{new_col} 不存在或 {old_col} 已存在，跳过')
        conn.commit()
        print('[v144] rollback 完成：列名已还原，业务数据未改动')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v144] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _argv = sys.argv[1:]
    _args = [a for a in _argv if not a.startswith('--')]
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in _argv:
        _ok = rollback(_db)
        print(f'[v144] rollback: {"OK" if _ok else "FAIL"}')
    elif '--verify' in _argv:
        _v = verify(_db)
        print(f'[v144] verify: {"PASS" if _v else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v144] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v144] verify: {"PASS" if _v else "FAIL"}')
