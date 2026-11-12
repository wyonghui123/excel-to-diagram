# -*- coding: utf-8 -*-
"""v233 - 控制参数：容差方向 / 基准（M6a-1）

依据: docs/specs/spec-rule-model-2026-11-10.md §11.2.1（M6a-1）

背景:
- 容差限值只以参数存在（`domain='tolerance'`），限值身份 = 参数 code；
- 「方向（over/under/both）× 基准（percent/absolute）」原先靠 code 前缀与
  description 文本表达，构成第二套事实源；本迁移把它收敛为
  `control_parameter_defs` 的两列，元数据侧同批声明于
  `meta/schemas/control_parameter_def.yaml`。

动作:
  1. PRAGMA 判列；缺则 ALTER TABLE ADD COLUMN tolerance_direction / tolerance_basis
  2. 存量容差参数回填方向与基准（只回填缺失值，幂等）
  3. 存量容差参数所属域由 procurement 迁到 tolerance（与 schema 枚举一致）

回滚:
  不回滚列（SQLite 删列需重建表）；恢复 4 个参数的 domain 并清空两列。
"""
from __future__ import annotations

import os
import sqlite3

MIGRATION_NAME = 'v233__control_parameter_tolerance_fields'

TABLE = 'control_parameter_defs'
#: 与 meta/core/schema_generator.py 的字符串列宽对齐（VARCHAR(200)）
COLUMNS = {
    'tolerance_direction': 'VARCHAR(200) NULL',
    'tolerance_basis': 'VARCHAR(200) NULL',
}

#: 存量容差参数：(code, 方向, 基准)
BACKFILL = (
    ('receipt_over_tolerance_percent', 'over', 'percent'),
    ('transfer_over_ship_percent', 'over', 'percent'),
    ('transfer_over_receive_percent', 'over', 'percent'),
    ('inventory_count_default_tolerance_qty_pct', 'both', 'percent'),
)

#: 回滚时恢复的域（这 4 个参数迁入 tolerance 前的值）
ROLLBACK_DOMAIN = 'procurement'


def _table_exists(conn, name):
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name]
    ).fetchone())


def _column_info(conn, table):
    return {row[1]: row for row in conn.execute(
        'PRAGMA table_info(%s)' % table).fetchall()}


def _do_column(conn):
    if not _table_exists(conn, TABLE):
        print('  - [SKIP] 缺表 %s，跳过补列' % TABLE)
        return False
    info = _column_info(conn, TABLE)
    for name, ddl in COLUMNS.items():
        if name in info:
            print('  - [SKIP] 列 %s.%s 已存在' % (TABLE, name))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (TABLE, name, ddl))
        print('  - [ALTER] 列 %s.%s' % (TABLE, name))
    return True


def _backfill(conn):
    if not _table_exists(conn, TABLE):
        print('  - [SKIP] 缺表 %s，跳过回填' % TABLE)
        return 0
    info = _column_info(conn, TABLE)
    if any(name not in info for name in COLUMNS):
        print('  - [SKIP] 容差列缺失，跳过回填')
        return 0
    updated = 0
    for code, direction, basis in BACKFILL:
        cursor = conn.execute(
            "UPDATE %s SET tolerance_direction = ?, tolerance_basis = ?, "
            "domain = 'tolerance' "
            "WHERE code = ? AND (tolerance_direction IS NULL "
            "OR tolerance_basis IS NULL OR domain <> 'tolerance')" % TABLE,
            [direction, basis, code],
        )
        updated += cursor.rowcount or 0
    print('  - [UPDATE] 容差参数回填 %s 行' % updated)
    return updated


def _do_upgrade(conn):
    _do_column(conn)
    _backfill(conn)
    print('  - [VERIFY] domain=tolerance 且方向/基准缺失的行: %s'
          % _incomplete_count(conn))
    return True


def _incomplete_count(conn):
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM %s WHERE domain = 'tolerance' AND "
            "(tolerance_direction IS NULL OR tolerance_basis IS NULL)" % TABLE
        ).fetchone()[0]
    except sqlite3.Error:
        return -1


def migrate(db_path, skip_backup=False):
    print('[v233] 控制参数：容差方向 / 基准')
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(db_path)
    try:
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path):
    if not os.path.exists(db_path):
        return {'ok': False, 'error': 'db not found'}
    conn = sqlite3.connect(db_path)
    try:
        info = _column_info(conn, TABLE)
        checks = {name: name in info for name in COLUMNS}
        incomplete = _incomplete_count(conn)
        return {'ok': all(checks.values()) and incomplete == 0,
                'checks': checks,
                'incomplete_tolerance_rows': incomplete}
    finally:
        conn.close()


def rollback(db_path):
    print('[v233 rollback] 列保留；恢复 domain 并清空容差语义列')
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(db_path)
    try:
        info = _column_info(conn, TABLE)
        if any(name not in info for name in COLUMNS):
            print('  - [SKIP] 容差列不存在，无需回滚')
            return True
        for code, _direction, _basis in BACKFILL:
            conn.execute(
                "UPDATE %s SET domain = ?, tolerance_direction = NULL, "
                "tolerance_basis = NULL WHERE code = ?" % TABLE,
                [ROLLBACK_DOMAIN, code],
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


downgrade = rollback