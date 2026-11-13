# -*- coding: utf-8 -*-
"""v266 —— control_parameter_defs.domain CHECK 放宽至 billing。

背景:
  v244（销售发票价格与金额）需要写入 3 条 domain='billing' 的控制参数，
  但真实库 `control_parameter_defs.domain` 的列级 CHECK 只有
  sales/procurement/inventory/tolerance/platform/demand（YAML 枚举历史遗漏
  `billing`），INSERT 直接 IntegrityError：CHECK constraint failed。
  `schema_generator.rebuild_table_with_checks` 只给「缺 CHECK」的列补 CHECK，
  对已有 CHECK 一律跳过，因此 `sync_schema --apply` 无法修复该漂移。

范围:
  1. `control_parameter_defs.domain` 的 CHECK 重建为 7 值（追加 billing）。
  2. 同步 `meta/schemas/control_parameter_def.yaml` 的 domain 枚举（DDL 单源），
     `generated_schema.sql` 由 `sync_schema --generate` 重新产出。

做法（SQLite 无 ALTER ... ADD/DROP CONSTRAINT）:
  读取 sqlite_master 的 CREATE TABLE 原文 → 仅替换 domain CHECK 子句 →
  建 `__new` 表 → INSERT SELECT 复制 → DROP 旧表 → RENAME → 按
  sqlite_master 重建索引 / 触发器 / 引用本表的视图。全程单事务。

幂等:
  CHECK 已包含 billing 时打印 [SKIP]，不改任何行。
回滚:
  先删 domain='billing' 行（避免 CHECK 收窄后校验失败），再重建为 6 值 CHECK。
"""

import re
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v266__control_parameter_domain_billing'

TABLE = 'control_parameter_defs'

DOMAIN_VALUES = ('sales', 'procurement', 'inventory', 'tolerance',
                 'platform', 'demand', 'billing')
DOMAIN_VALUES_LEGACY = DOMAIN_VALUES[:-1]

_DOMAIN_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*[\"`\[]?domain[\"`\]]?\s+IN\s*\(([^)]*)\)\s*\)", re.IGNORECASE)


def _table_sql(conn, table):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _check_values(conn, table):
    sql = _table_sql(conn, table)
    if not sql:
        return None
    match = _DOMAIN_CHECK_RE.search(sql)
    if not match:
        return []
    return [item.strip().strip("'\"") for item in match.group(1).split(',')]


def _rebuild_domain_check(conn, table, values):
    """把 domain 列 CHECK 替换为给定取值集合；返回是否发生重建。"""
    sql = _table_sql(conn, table)
    if not sql:
        return False
    match = _DOMAIN_CHECK_RE.search(sql)
    if not match:
        raise RuntimeError(
            '{0}.domain 缺少 CHECK 子句，请用 sync_schema --check 人工确认'.format(table))

    quoted = ', '.join("'" + value.replace("'", "''") + "'" for value in values)
    new_sql = (sql[:match.start()]
               + 'CHECK (domain IN ({0}))'.format(quoted)
               + sql[match.end():])

    new_table = table + '__new'
    create_new, replaced = re.subn(
        r'^(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)["`\[]?'
        + re.escape(table) + r'["`\]]?',
        lambda mo: mo.group(1) + new_table,
        new_sql, count=1, flags=re.IGNORECASE)
    if not replaced:
        raise RuntimeError('无法改写 CREATE TABLE 语句: {0}'.format(table))

    index_sqls = [row[0] for row in conn.execute(
        "SELECT sql FROM sqlite_master WHERE type IN ('index','trigger') "
        "AND tbl_name=? AND sql IS NOT NULL", (table,))]
    view_sqls = [
        (row[0], row[1]) for row in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='view' AND sql IS NOT NULL")
        if re.search(r'\b{0}\b'.format(re.escape(table)), row[1], re.IGNORECASE)
    ]

    conn.execute('PRAGMA foreign_keys=OFF')
    try:
        conn.execute('BEGIN')
        for name, _sql in view_sqls:
            conn.execute('DROP VIEW IF EXISTS "{0}"'.format(name))
        conn.execute(create_new)
        conn.execute('INSERT INTO "{0}" SELECT * FROM "{1}"'.format(new_table, table))
        conn.execute('DROP TABLE "{0}"'.format(table))
        conn.execute('ALTER TABLE "{0}" RENAME TO "{1}"'.format(new_table, table))
        for sql_text in index_sqls:
            conn.execute(sql_text)
        for _name, sql_text in view_sqls:
            conn.execute(sql_text)
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    finally:
        conn.execute('PRAGMA foreign_keys=ON')
    return True


def _backup_table(conn, table):
    backup = '{0}_pre_v266_backup'.format(table)
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (backup,)
    ).fetchone()
    if exists:
        conn.execute('DROP TABLE "{0}"'.format(backup))
    conn.execute('CREATE TABLE "{0}" AS SELECT * FROM "{1}"'.format(backup, table))
    return backup


def migrate(db_path, skip_backup=False):
    # skip_backup: MigrationRunner 已统一备份，迁移内部不再重复整库备份
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.isolation_level = None
    try:
        print('[v266] 开始: {0}.domain CHECK 追加 billing'.format(TABLE))
        if not _table_sql(conn, TABLE):
            print('[v266] [WARN] 表 {0} 不存在，跳过'.format(TABLE))
            return True

        current = _check_values(conn, TABLE)
        if 'billing' in (current or []):
            print('[v266] [SKIP] domain CHECK 已含 billing: {0}'.format(current))
            return True

        print('[v266] 当前 domain CHECK: {0}'.format(current))
        backup = _backup_table(conn, TABLE)
        print('[v266] 已备份到 {0}'.format(backup))
        rebuilt = _rebuild_domain_check(conn, TABLE, DOMAIN_VALUES)
        print('[v266] 重建完成: {0}'.format(_check_values(conn, TABLE))
              if rebuilt else '[v266] [SKIP] 无需重建')
        return True
    except Exception as exc:  # noqa: BLE001
        print('[v266] migrate 失败: {0}'.format(exc))
        raise
    finally:
        conn.close()


upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v266 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        current = _check_values(conn, TABLE)
        if current is None:
            print('[v266 verify] FAIL: 表 {0} 不存在'.format(TABLE))
            return False
        missing = [value for value in DOMAIN_VALUES if value not in current]
        if missing:
            print('[v266 verify] FAIL: domain CHECK 缺值 {0}（实际 {1}）'.format(
                missing, current))
            return False
        print('[v266 verify] OK: domain CHECK = {0}'.format(current))
        return True
    finally:
        conn.close()


def rollback(db_path):
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.isolation_level = None
    try:
        if not _table_sql(conn, TABLE):
            print('[v266 rollback] [SKIP] 表不存在')
            return True
        cur = conn.execute(
            "DELETE FROM \"{0}\" WHERE domain='billing'".format(TABLE))
        print('[v266 rollback] 删除 billing 行: {0}'.format(cur.rowcount))
        _rebuild_domain_check(conn, TABLE, DOMAIN_VALUES_LEGACY)
        print('[v266 rollback] domain CHECK 回退为 {0}'.format(list(DOMAIN_VALUES_LEGACY)))
        return True
    finally:
        conn.close()