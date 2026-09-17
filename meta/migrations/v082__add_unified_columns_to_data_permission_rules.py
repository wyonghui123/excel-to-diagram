# -*- coding: utf-8 -*-
"""
[v082 2026-09-04] data_permission_rules 补齐统一权限规则(P3)列

背景:
  org/user「权限预览」页在 staging 上 500:
    GET /api/v1/orgs/{id}/permission-config
      -> org_service.get_permission_preview / _build_ps_data_scope
      -> SELECT resource_type, condition, condition_display, permission_level,
                inherit_to_children FROM data_permission_rules
             WHERE permission_set_id = ? AND (is_denied IS NULL OR is_denied = 0)
      -> sqlite3.OperationalError: no such column: condition

根因:
  staging 的 data_permission_rules 仍是 Spec15 时代的窄 schema
  (只有 created_by/updated_by/id/resource_type/resource_id/rule_type/created_at/
   updated_at/role_id + v074 加的 permission_set_id + v076 加的 permission_level
   + 运行时 _ensure_unified_table 幂等补的 condition_display)。
  代码权威 schema 在 meta/services/condition_permission_service.py
  _ensure_unified_table 的 CREATE TABLE(IF NOT EXISTS) 与
  meta/schemas/generated_schema.sql §P3-T1, 含 condition / is_denied /
  inherit_to_children / dimension_code / scope_mode 等列。
  但 CREATE TABLE IF NOT EXISTS 对已存在的窄表是 no-op, 只有
  condition_display 有运行时幂等 ALTER -> 其余列永远缺失。

修复 (expand, 安全, 幂等):
  对 data_permission_rules 逐列检查 PRAGMA table_info, 缺列才 ALTER ADD COLUMN
  (全 nullable / 带默认值, 不触碰现有行; 该表在受影响环境为 0 行)。
  补齐列对齐代码侧 DDL:
    permission_set_id / permission_level / condition_display (防御, 已存在则跳过)
    dimension_code / condition / scope_mode / is_denied / inherit_to_children /
    propagate_to_parents / source_table / source_id
  不回填数据, 不 DROP 遗留列 (role_id/resource_id/rule_type 保留)。

幂等性:
  - PRAGMA table_info 检查列是否已存在; 已存在 -> 跳过 (可重复执行)
  - verify(): 检查预览读路径必需列 condition / condition_display / permission_level /
    inherit_to_children / is_denied / permission_set_id 全齐

回滚:
  - SQLite 不支持 DROP COLUMN (3.35 之前) -> downgrade 仅打印警告, 不真删列
"""
import sqlite3
from pathlib import Path

# 需要补齐的列: (列名, 建表声明) —— 对齐 _ensure_unified_table / generated_schema.sql
MISSING_OK_COLUMNS = [
    ('permission_set_id', 'INTEGER'),
    ('permission_level', 'VARCHAR(50)'),
    ('condition_display', 'TEXT'),
    ('dimension_code', 'VARCHAR(200)'),
    ('condition', 'TEXT'),
    ('scope_mode', "VARCHAR(50) DEFAULT 'include'"),
    ('is_denied', 'INTEGER DEFAULT 0'),
    ('inherit_to_children', 'INTEGER DEFAULT 1'),
    ('propagate_to_parents', 'INTEGER DEFAULT 0'),
    ('source_table', 'VARCHAR(100)'),
    ('source_id', 'INTEGER'),
]

# verify 必需列 (预览读路径 / 写入路径的实际依赖)
REQUIRED = [
    ('data_permission_rules', 'permission_set_id'),
    ('data_permission_rules', 'permission_level'),
    ('data_permission_rules', 'condition'),
    ('data_permission_rules', 'condition_display'),
    ('data_permission_rules', 'is_denied'),
    ('data_permission_rules', 'inherit_to_children'),
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, decl: str) -> bool:
    """缺列才 ADD, 返回是否实际做了修改."""
    if not _table_exists(conn, table):
        print(f'  - 表 {table} 不存在, 跳过 ADD COLUMN {column}')
        return False
    if _column_exists(conn, table, column):
        print(f'  - {table}.{column} 已存在, 跳过')
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    print(f'  [ADD COLUMN] {table}.{column} {decl}')
    return True


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'data_permission_rules'):
        print('  - data_permission_rules 表不存在, 跳过 (该表由代码 lazy create)')
        return
    for col, decl in MISSING_OK_COLUMNS:
        _add_column_if_missing(conn, 'data_permission_rules', col, decl)


def _do_downgrade(conn: sqlite3.Connection) -> None:
    print('  [WARN] SQLite 不支持安全 DROP COLUMN, 不真回滚加列 (避免数据丢失)')
    print('  [WARN] 如必须回滚, 请用 SQLite 3.35+ 手动 DROP COLUMN 或从备份恢复')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v082] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v082] 开始: data_permission_rules 补齐统一权限规则列')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v082] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证: data_permission_rules 预览读路径必需列全齐"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for table, col in REQUIRED:
            if not _column_exists(conn, table, col):
                print(f'  [FAIL] {table}.{col} 缺失')
                return False
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v082] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v082] 回滚: 不真删列 (避免数据丢失)')
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v082] downgrade 失败: {e}')
        raise
    finally:
        conn.close()
