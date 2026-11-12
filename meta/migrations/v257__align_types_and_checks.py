# -*- coding: utf-8 -*-
"""v257 —— 类型亲和性对齐 + 全量枚举 CHECK 补齐（DDL 单源 E2）。

背景:
  v256 只覆盖 status 列；历史库其余枚举列仍只有类型声明、没有 CHECK。
  另有若干表的列类型亲和性与 YAML 不一致（多为历史 TEXT/VARCHAR）。
  纯 VARCHAR 长度差异不算漂移：SQLite 不强制长度，长度由应用层
  `metadata_driven_validator` 的 max_length 约束。

范围:
  仅按 `meta/migrations/data/v257_type_alignments.json` 冻结映射执行
  （生成方式见 v257 提交说明）；排除 `vendor_invoice*`（另一分支在途）。
  映射生成后不随 YAML 演化，保证迁移语义稳定。

做法:
  1) `menus.page_type` 空串 → `object_list`（否则新 CHECK 会拒绝存量行）；
  2) 逐表 `rebuild_table_with_checks(types=..., checks=...)`，类型与 CHECK
     在同一次重建中完成；单表事务，失败即抛；缺表跳过。

幂等:
  亲和性已一致且 CHECK 已相同 → `[SKIP]`，不重建。
"""
import json
import sqlite3
from pathlib import Path

from meta.core.schema_generator import (
    parse_schema_text, rebuild_table_with_checks, sqlite_type_affinity)

MIGRATION_NAME = 'v257__align_types_and_checks'
MAPPING_PATH = Path(__file__).resolve().parent / 'data' / 'v257_type_alignments.json'


def load_mapping(path=None):
    with open(path or MAPPING_PATH, encoding='utf-8') as handle:
        return json.load(handle)


def _has_table(conn, table):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [table]).fetchone())


def _columns(conn, table):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if not row or not row[0]:
        return {}
    for name, info in parse_schema_text(row[0]).items():
        if name.lower() == table.lower():
            return info['columns']
    return {}


def _fix_menus_page_type(conn, spec):
    if not spec or not _has_table(conn, spec['table']):
        return 0
    cursor = conn.execute(
        "UPDATE {0} SET {1}=? WHERE TRIM(COALESCE({1}, ''))=?".format(
            spec['table'], spec['column']),
        (spec['to'], spec.get('from', '')))
    return cursor.rowcount


def _plan_table(conn, table, spec):
    """按冻结映射算出本表仍需变更的类型 / CHECK；无需变更返回 (None, None)。"""
    columns = _columns(conn, table)
    types, checks = {}, {}
    for column, target in spec.get('types', {}).items():
        have = columns.get(column)
        if have and sqlite_type_affinity(have.get('type')) != sqlite_type_affinity(target):
            types[column] = target
    for column, values in spec.get('checks', {}).items():
        have = columns.get(column)
        if not have:
            continue
        have_check = have.get('check')
        if not have_check or set(have_check) != set(values):
            checks[column] = values
    if not types and not checks:
        return None, None
    return types, checks


def _apply_mapping(conn, db_path, mapping):
    spec = mapping.get('menus_page_type_fix')
    fixed = _fix_menus_page_type(conn, spec)
    if fixed:
        print('[v257] menus.page_type 空串 → %s: %d 行'
              % (spec['to'], fixed))

    rebuilt, type_count, check_count, skipped = [], 0, 0, 0
    for table in sorted(mapping.get('tables', {})):
        table_spec = mapping['tables'][table]
        if not _has_table(conn, table):
            skipped += 1
            continue
        types, checks = _plan_table(conn, table, table_spec)
        if not types and not checks:
            skipped += 1
            continue
        if rebuild_table_with_checks(
                str(db_path), table, checks, types=types, conn=conn):
            rebuilt.append(table)
            type_count += len(types)
            check_count += len(checks)
    return rebuilt, type_count, check_count, skipped, fixed


def migrate(db_path, skip_backup=False, mapping=None):
    # skip_backup: MigrationRunner 已统一备份，迁移内部不再重复备份
    path = Path(db_path)
    payload = mapping or load_mapping()
    conn = sqlite3.connect(str(path), timeout=30)
    conn.isolation_level = None
    try:
        print('[v257] 开始: 类型 + CHECK 对齐（%d 张表）'
              % len(payload.get('tables', {})))
        rebuilt, type_count, check_count, skipped, fixed = _apply_mapping(
            conn, path, payload)
        print('[v257] 完成: 重建 %d 张表 / 改类型 %d 列 / 补 CHECK %d 列 / 跳过 %d 表'
              % (len(rebuilt), type_count, check_count, skipped))
        if not rebuilt and not fixed:
            print('[v257] [SKIP] 类型与 CHECK 已对齐')
        elif len(rebuilt) <= 10:
            print('[v257] 重建表: %s' % ', '.join(rebuilt))
        return True
    finally:
        conn.close()


upgrade = migrate


def verify(db_path, mapping=None) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v257 verify] FAIL: DB 不存在')
        return False
    payload = mapping or load_mapping()
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        problems = []
        spec = payload.get('menus_page_type_fix')
        if spec and _has_table(conn, spec['table']):
            blank = conn.execute(
                "SELECT COUNT(*) FROM {0} WHERE TRIM(COALESCE({1}, ''))=?".format(
                    spec['table'], spec['column']),
                (spec.get('from', ''),)).fetchone()[0]
            if blank:
                problems.append('menus.page_type 仍有 %d 行空串' % blank)

        for table, table_spec in sorted(payload.get('tables', {}).items()):
            if not _has_table(conn, table):
                problems.append('缺表 %s' % table)
                continue
            columns = _columns(conn, table)
            for column, target in table_spec.get('types', {}).items():
                have = columns.get(column)
                if not have:
                    problems.append('%s.%s 缺列' % (table, column))
                elif sqlite_type_affinity(have.get('type')) != sqlite_type_affinity(target):
                    problems.append('%s.%s 类型 %s≠%s'
                                    % (table, column, have.get('type'), target))
            for column, values in table_spec.get('checks', {}).items():
                have = columns.get(column)
                if not have:
                    problems.append('%s.%s 缺列' % (table, column))
                elif not have.get('check') or set(have['check']) != set(values):
                    problems.append('%s.%s CHECK 不一致' % (table, column))
        if problems:
            print('[v257 verify] FAIL: %d 项' % len(problems))
            for item in problems[:10]:
                print('  -', item)
            return False
        print('[v257 verify] OK: 类型亲和性与 CHECK 已对齐')
        return True
    finally:
        conn.close()