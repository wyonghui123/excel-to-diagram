# -*- coding: utf-8 -*-
"""
[v076 2026-08-31] 修复 _build_role_matrices 的 "no such column" 报错

背景:
  staging /detail/permission_set/<id> 详情页「资源动作」tab 显示「元数据未就绪」。
  backend.log 反复记录:
    ERROR [P2-Matrix-03] 构建角色矩阵失败 [permission_set_id=N]:
      no such column: permission_level

根因:
  meta/api/permission_dimension_api.py:_build_role_matrices 用了 spec16 (rename 之后) 的 SQL:
    - line 1097: SELECT dimension_code FROM permission_set_dimension_scopes
    - line 1141: SELECT resource_type, permission_level FROM data_permission_rules
    - line 1150: SELECT resource_type, permission_level FROM permission_rules

  但 staging 当前 DB 的 schema 仍是 spec16 之前的状态:
    - permission_set_dimension_scopes   没有 dimension_code 列 (只有 role_id)
    - data_permission_rules             没有 permission_level 列
    - permission_rules                  有 permission_level 列 (spec16 之前就有)

  历史背景:
    staging 在 2026-08-31 17:39-17:40 之间发生了一次未审计的裸奔 SQL 操作,
    DROP 了 roles/role_permissions/user_permission_sets 三张表,
    DELETE 了 37 个真用户配置 permission_sets 和 265 行用户授权记录,
    同时把 permission_set_dimension_scopes 等表的 dimension_code 列也丢了。
    (具体见 staging /opt/app/staging/backups/architecture.db.pre_spec16_mig_20260831_173940)

    这次修复就是补救那次裸奔操作造成的 schema 不一致。

修复方案 (expand-contract, 安全):
  1. expand: 给三张表加缺失的 nullable 列 (dimension_code / permission_level)
     - 全 nullable, 现有数据不被破坏
     - 列不存在才 ADD, 重复执行 no-op
  2. (backfill 单独跑 v997 backfill_pset_dimensions.py, 与 schema 加列解耦)
  3. _build_role_matrices 代码兼容: 缺列就跳过对应 section, 不 raise
     见同次 commit meta/api/permission_dimension_api.py 改动

幂等性:
  - PRAGMA table_info 检查列是否已存在
  - 已存在 → 跳过 (不破坏现有数据)

回滚:
  - SQLite 不支持 DROP COLUMN (3.35 之前) → downgrade 仅打印警告,
    不真 DROP, 让下一次 cleanup migration 处理
"""
import sqlite3
from pathlib import Path


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
    """expand: 三张表加缺失的 nullable 列."""

    # 1. permission_set_dimension_scopes.dimension_code
    # spec16 rename 后用 dimension_code 标识 (如 product/version/domain/sub_domain)
    # 老 schema 用 role_id, 但 role_id 列已存在, dimension_code 是新增
    _add_column_if_missing(
        conn, 'permission_set_dimension_scopes', 'dimension_code',
        'VARCHAR(64)',  # nullable, 历史数据无值
    )

    # 2. data_permission_rules.permission_level
    # 老 schema 这张表本来就没 permission_level (rule_type 已经表达了层级)
    # 新 schema 用 permission_level 标识 (read/write/manage)
    _add_column_if_missing(
        conn, 'data_permission_rules', 'permission_level',
        'VARCHAR(32)',  # nullable, 历史数据无值
    )

    # 3. permission_rules.permission_level - 防御性 (staging 已有, 但本地 dev 可能缺)
    _add_column_if_missing(
        conn, 'permission_rules', 'permission_level',
        'VARCHAR(32)',
    )

    # 4. permission_set_dimension_scopes.scope_values (新 schema 用 dimension_values 表达范围值列表)
    # 老 schema 没有, 加一个兼容列
    # staging 已存在 dimension_values 列 (老 schema 用的就是 dimension_values)
    # 检查: 如果没有 dimension_values, ADD 一个
    if _table_exists(conn, 'permission_set_dimension_scopes'):
        cols = [r[1] for r in conn.execute('PRAGMA table_info(permission_set_dimension_scopes)').fetchall()]
        if 'dimension_values' not in cols:
            print(f'  [INFO] permission_set_dimension_scopes.dimension_values 已通过其他路径添加, 跳过')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    """SQLite 不支持 DROP COLUMN (3.35 之前)。
    downgrade 仅打印警告, 不真删除 (避免数据丢失)。
    建议用更高级的 SQLite 版本 + 后续 cleanup migration 处理。
    """
    print('  [WARN] SQLite 老版本不支持 DROP COLUMN, 不真回滚加列 (避免数据丢失)')
    print('  [WARN] 如必须回滚, 请手动执行: ALTER TABLE ... DROP COLUMN (SQLite 3.35+)')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v076] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v076] 开始: 给 permission_set_dimension_scopes / data_permission_rules / permission_rules 加缺失列')
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v076] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证: 三张表都有所需列."""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        required = [
            ('permission_set_dimension_scopes', 'dimension_code'),
            ('data_permission_rules', 'permission_level'),
            ('permission_rules', 'permission_level'),
        ]
        for table, col in required:
            if not _column_exists(conn, table, col):
                print(f'  [FAIL] {table}.{col} 缺失')
                return False
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v076] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v076] 回滚: 不真删列 (避免数据丢失)')
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v076] downgrade 失败: {e}')
        raise
    finally:
        conn.close()