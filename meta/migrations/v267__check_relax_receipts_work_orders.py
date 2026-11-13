# -*- coding: utf-8 -*-
"""v267 —— 放宽 receipts / work_orders 的枚举 CHECK（补齐 YAML 既有取值）。

背景:
  `sync_schema --check` 有 2 处已有 CHECK 的漂移：
    - receipts.source_doc_type 缺 'unordered'（无单收货，v230 业务语义）
    - work_orders.source_demand_type 缺 'manual'（手工需求）
  `schema_generator.rebuild_table_with_checks` 只给「缺 CHECK」的列补 CHECK，
  对已有 CHECK 一律跳过，因此 sync_schema --apply / v257 都无法修复。

范围:
  仅重建这两张表的对应列级 CHECK；不动 vendor_invoice*（另一分支在途）。

做法（SQLite 无 ALTER ... DROP CONSTRAINT）:
  读取 sqlite_master 的 CREATE TABLE 原文 → 替换目标列 CHECK 子句 →
  建 `__new` 表 → INSERT SELECT 复制 → DROP 旧表 → RENAME →
  按 sqlite_master 重建索引 / 触发器 / 引用本表的视图。全程单事务。

幂等:
  CHECK 已包含全部目标取值时打印 [SKIP]，不改任何行。

回滚:
  若已有行使用新增取值则拒绝回滚；否则重建为历史 CHECK。
"""

import re
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v267__check_relax_receipts_work_orders'

#: 表 → {列: 目标取值}
TARGET_CHECKS = {
    'receipts': {
        'source_doc_type': ('purchase_order', 'transfer_order', 'work_order',
                            'sales_return', 'intercompany', 'unordered'),
    },
    'work_orders': {
        'source_demand_type': ('sales_order_schedule', 'sales_order_line',
                               'project_task', 'manual'),
    },
}

#: 回滚时的历史取值
LEGACY_CHECKS = {
    'receipts': {
        'source_doc_type': ('purchase_order', 'transfer_order', 'work_order',
                            'sales_return', 'intercompany'),
    },
    'work_orders': {
        'source_demand_type': ('sales_order_schedule', 'sales_order_line',
                               'project_task'),
    },
}


def _check_re(column):
    return re.compile(
        r'CHECK\s*\(\s*["`\[]?' + re.escape(column)
        + r'["`\]]?\s+IN\s*\(([^)]*)\)\s*\)', re.IGNORECASE)


def _table_sql(conn, table):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _check_values(conn, table, column):
    sql = _table_sql(conn, table)
    if not sql:
        return None
    match = _check_re(column).search(sql)
    if not match:
        return []
    return [item.strip().strip("'\"") for item in match.group(1).split(',')]


def _quote(values):
    return ', '.join("'" + value.replace("'", "''") + "'" for value in values)


def _replace_checks(sql, table, columns):
    new_sql = sql
    for column, values in columns.items():
        match = _check_re(column).search(new_sql)
        if not match:
            raise RuntimeError(
                '{0}.{1} 缺少 CHECK 子句，请人工确认'.format(table, column))
        new_sql = (new_sql[:match.start()]
                   + 'CHECK ({0} IN ({1}))'.format(column, _quote(values))
                   + new_sql[match.end():])
    return new_sql


def _rebuild_table(conn, table, columns):
    """按给定列 CHECK 重建表；返回是否发生重建。"""
    sql = _table_sql(conn, table)
    if not sql:
        return False

    new_sql = _replace_checks(sql, table, columns)
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
    backup = '{0}_pre_v267_backup'.format(table)
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (backup,)
    ).fetchone()
    if exists:
        conn.execute('DROP TABLE "{0}"'.format(backup))
    conn.execute('CREATE TABLE "{0}" AS SELECT * FROM "{1}"'.format(backup, table))
    return backup


def _apply(conn, target):
    changed = []
    for table, columns in target.items():
        if not _table_sql(conn, table):
            print('[v267] [WARN] 表 {0} 不存在，跳过'.format(table))
            continue
        todo = {}
        for column, values in columns.items():
            current = _check_values(conn, table, column)
            missing = [value for value in values if value not in (current or [])]
            if not missing:
                print('[v267] [SKIP] {0}.{1} 已含 {2}'.format(
                    table, column, list(values)))
                continue
            print('[v267] {0}.{1} 当前 {2}，补 {3}'.format(
                table, column, current, missing))
            todo[column] = list(values)
        if not todo:
            continue
        backup = _backup_table(conn, table)
        print('[v267] 已备份 {0} → {1}'.format(table, backup))
        _rebuild_table(conn, table, todo)
        changed.append(table)
    return changed


def migrate(db_path, skip_backup=False):
    # skip_backup: MigrationRunner 已统一备份，迁移内部不再重复整库备份
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.isolation_level = None
    try:
        print('[v267] 开始: 放宽 receipts / work_orders 枚举 CHECK')
        changed = _apply(conn, TARGET_CHECKS)
        if changed:
            print('[v267] 重建完成: {0}'.format(', '.join(changed)))
        else:
            print('[v267] [SKIP] 无需重建')
        return True
    except Exception as exc:  # noqa: BLE001
        print('[v267] migrate 失败: {0}'.format(exc))
        raise
    finally:
        conn.close()


upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v267 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        for table, columns in TARGET_CHECKS.items():
            if not _table_sql(conn, table):
                print('[v267 verify] FAIL: 表 {0} 不存在'.format(table))
                return False
            for column, values in columns.items():
                current = _check_values(conn, table, column)
                missing = [value for value in values if value not in (current or [])]
                if missing:
                    print('[v267 verify] FAIL: {0}.{1} 缺值 {2}（实际 {3}）'.format(
                        table, column, missing, current))
                    return False
        print('[v267 verify] OK')
        return True
    finally:
        conn.close()


def rollback(db_path):
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.isolation_level = None
    try:
        for table, columns in LEGACY_CHECKS.items():
            if not _table_sql(conn, table):
                continue
            for column, legacy in columns.items():
                extra = [value for value in TARGET_CHECKS[table][column]
                         if value not in legacy]
                placeholders = ', '.join(['?'] * len(extra))
                used = conn.execute(
                    'SELECT COUNT(*) FROM "{0}" WHERE {1} IN ({2})'.format(
                        table, column, placeholders), extra).fetchone()[0]
                if used:
                    print('[v267 rollback] [FAIL] {0}.{1} 仍有 {2} 行使用新取值 {3}'.format(
                        table, column, used, extra))
                    return False
                _rebuild_table(conn, table, {column: list(legacy)})
                print('[v267 rollback] {0}.{1} 回退为 {2}'.format(
                    table, column, list(legacy)))
        return True
    finally:
        conn.close()