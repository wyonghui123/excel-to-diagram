# -*- coding: utf-8 -*-
"""v232 - 属性提升表（attribute_promotion）

依据: docs/superpowers/specs/2026-11-09-rule-model-scenario-and-extended-attributes-spec.md
      §9.3.6 数据模型 / TBD-003 一次性切换（cutover）

口径:
  1. 一条记录 = 一个字典层属性（object_type + attribute_code）提升到业务表物理列；
     (object_type, attribute_code) 唯一。
  2. 状态机 pending → column_created → backfilled → verified → active，
     只允许单向前进；回滚靠停用 / 新建记录，不做原地倒退。
  3. verified 之前 AttributeProvider 仍读值表；active 之后物理列成为唯一 owner，
     值表只读（AttributeValueService 拒写）。
  4. 运营计数（backfilled_count / mismatch_count / last_checked_at）供每日一致性
     校验与告警使用，不参与规则求值。
"""

import os
import sqlite3

MIGRATION_NAME = 'v232__attribute_promotion'

PROMOTION_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS attribute_promotion (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type VARCHAR(200) NOT NULL,
    attribute_code VARCHAR(200) NOT NULL,
    target_table VARCHAR(200) NOT NULL,
    target_column VARCHAR(200) NOT NULL,
    data_type VARCHAR(200) NOT NULL DEFAULT 'string',
    sync_mode VARCHAR(200) NOT NULL DEFAULT 'cutover',
    status VARCHAR(200) NOT NULL DEFAULT 'pending',
    backfilled_count INTEGER NOT NULL DEFAULT 0,
    mismatch_count INTEGER NOT NULL DEFAULT 0,
    last_checked_at DATETIME,
    activated_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    UNIQUE (object_type, attribute_code)
)
"""

PROMOTION_INDEXES = (
    ("idx_attribute_promotion_status",
     "CREATE INDEX IF NOT EXISTS idx_attribute_promotion_status "
     "ON attribute_promotion(status)"),
    ("idx_attribute_promotion_target",
     "CREATE INDEX IF NOT EXISTS idx_attribute_promotion_target "
     "ON attribute_promotion(object_type, target_table, target_column)"),
)


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _index_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _do_upgrade(conn):
    if _table_exists(conn, 'attribute_promotion'):
        print('  - [SKIP] 表 attribute_promotion 已存在')
    else:
        conn.execute(PROMOTION_TABLE_DDL)
        print('  - [OK] 建表 attribute_promotion')

    for name, ddl in PROMOTION_INDEXES:
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
        else:
            conn.execute(ddl)
            print('  - [OK] 建索引 %s' % name)


def migrate(db_path, skip_backup=False):
    print('[v232] 属性提升表 attribute_promotion')
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return
    conn = sqlite3.connect(db_path)
    try:
        _do_upgrade(conn)
        conn.commit()
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
        checks = {
            'table': _table_exists(conn, 'attribute_promotion'),
            'status_index': _index_exists(conn, 'idx_attribute_promotion_status'),
            'target_index': _index_exists(conn, 'idx_attribute_promotion_target'),
        }
        if checks['table']:
            columns = {row[1] for row in conn.execute(
                'PRAGMA table_info(attribute_promotion)').fetchall()}
            checks['required_columns'] = {
                'object_type', 'attribute_code', 'target_table',
                'target_column', 'sync_mode', 'status',
            }.issubset(columns)
        else:
            checks['required_columns'] = False
        return {'ok': all(checks.values()), 'checks': checks}
    finally:
        conn.close()


def rollback(db_path):
    """回滚：仅当表内没有已切换（active）记录时才允许删表。"""
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    try:
        if _table_exists(conn, 'attribute_promotion'):
            active = conn.execute(
                "SELECT COUNT(*) FROM attribute_promotion "
                "WHERE status = 'active'").fetchone()[0]
            if active:
                raise RuntimeError(
                    'attribute_promotion 存在 %s 条 active 记录，'
                    '物理列已成为唯一 owner，禁止直接删表；'
                    '请先停用并迁回值表。' % active)
            conn.execute('DROP TABLE attribute_promotion')
        conn.commit()
    finally:
        conn.close()
