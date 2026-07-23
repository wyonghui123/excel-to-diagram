# -*- coding: utf-8 -*-
"""
[MODULE] permission_migration — 数据权限规则迁移 (Phase 3 P3-T2/P3-T3)
[DESCRIPTION] 将 role_dimension_scopes / permission_rules 数据迁移到
              data_permission_rules 统一表, 通过 rule_type 区分.
[SPEC] spec-permission-system-unification-2026-07-19 §8.3 P3-T2/P3-T3

[P3-T2] role_dimension_scopes → data_permission_rules (rule_type='dimension')
[P3-T3] permission_rules → data_permission_rules (rule_type='condition')

[设计原则]
  - 单向迁移 (旧表 → 新表), 旧表保留 (P3-T7 废弃前可回滚)
  - source_table + source_id 记录原表来源, 便于审计/回滚
  - 幂等: 重复执行不会插入重复数据
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def migrate_role_dimension_scopes(ds) -> int:
    """[P3-T2] 将 role_dimension_scopes 数据迁移到 data_permission_rules

    Args:
        ds: DB 数据源 (有 .execute() 方法)

    Returns:
        迁移行数 (int)
    """
    # 1. 检查目标表是否存在
    if not _table_exists(ds, 'data_permission_rules'):
        raise RuntimeError(
            '[P3-T2] data_permission_rules table does not exist. '
            'Run P3-T1 (DDL) first.'
        )

    # 2. 幂等: 检查是否已迁移 (按 source_table + source_id 唯一)
    already_migrated = _count_migrated(ds, 'role_dimension_scopes')
    if already_migrated > 0:
        logger.info(
            f'[P3-T2] Already migrated {already_migrated} rows from '
            f'role_dimension_scopes. Skip.'
        )
        return 0

    # 3. 读取源数据
    if not _table_exists(ds, 'role_dimension_scopes'):
        logger.warning('[P3-T2] role_dimension_scopes table does not exist. Skip.')
        return 0

    src_rows = ds.execute(
        "SELECT id, role_id, dimension_code, dimension_values, "
        "inherit_children, scope_mode FROM role_dimension_scopes"
    ).fetchall()

    if not src_rows:
        logger.info('[P3-T2] No data in role_dimension_scopes. Skip.')
        return 0

    # 4. 批量插入
    migrated = 0
    for row in src_rows:
        src_id, role_id, dim_code, dim_values, inherit_children, scope_mode = row
        ds.execute(
            "INSERT INTO data_permission_rules "
            "(role_id, rule_type, dimension_code, condition, scope_mode, "
            " permission_level, inherit_to_children, propagate_to_parents, "
            " source_table, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                role_id, 'dimension', dim_code, dim_values, scope_mode or 'include',
                'read', inherit_children if inherit_children is not None else 1,
                0, 'role_dimension_scopes', src_id,
            ]
        )
        migrated += 1

    logger.info(f'[P3-T2] Migrated {migrated} rows from role_dimension_scopes')
    return migrated


def migrate_permission_rules(ds) -> int:
    """[P3-T3] 将 permission_rules 数据迁移到 data_permission_rules

    Args:
        ds: DB 数据源

    Returns:
        迁移行数 (int)
    """
    if not _table_exists(ds, 'data_permission_rules'):
        raise RuntimeError(
            '[P3-T3] data_permission_rules table does not exist. '
            'Run P3-T1 (DDL) first.'
        )

    already_migrated = _count_migrated(ds, 'permission_rules')
    if already_migrated > 0:
        logger.info(
            f'[P3-T3] Already migrated {already_migrated} rows from '
            f'permission_rules. Skip.'
        )
        return 0

    if not _table_exists(ds, 'permission_rules'):
        logger.warning('[P3-T3] permission_rules table does not exist. Skip.')
        return 0

    src_rows = ds.execute(
        "SELECT role_id, resource_type, condition, permission_level, "
        "is_denied, inherit_to_children, propagate_to_parents "
        "FROM permission_rules"
    ).fetchall()

    if not src_rows:
        logger.info('[P3-T3] No data in permission_rules. Skip.')
        return 0

    migrated = 0
    for idx, row in enumerate(src_rows):
        role_id, resource_type, condition, permission_level, is_denied, \
            inherit_to_children, propagate_to_parents = row
        # permission_rules 没有 id 主键, 用 idx+1 作为 source_id
        src_id = idx + 1
        ds.execute(
            "INSERT INTO data_permission_rules "
            "(role_id, rule_type, resource_type, condition, "
            " permission_level, is_denied, inherit_to_children, propagate_to_parents, "
            " source_table, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                role_id, 'condition', resource_type, condition,
                permission_level or 'read', is_denied or 0,
                inherit_to_children if inherit_to_children is not None else 1,
                propagate_to_parents if propagate_to_parents is not None else 0,
                'permission_rules', src_id,
            ]
        )
        migrated += 1

    logger.info(f'[P3-T3] Migrated {migrated} rows from permission_rules')
    return migrated


def migrate_all(ds) -> Dict[str, int]:
    """[P3] 完整迁移入口: 依次执行 P3-T2 + P3-T3

    Returns:
        {'dimension': N, 'condition': M, 'total': N+M}
    """
    dim_count = migrate_role_dimension_scopes(ds)
    cond_count = migrate_permission_rules(ds)
    return {
        'dimension': dim_count,
        'condition': cond_count,
        'total': dim_count + cond_count,
    }


def _table_exists(ds, table_name: str) -> bool:
    """检查表是否存在"""
    try:
        row = ds.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            [table_name]
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _count_migrated(ds, source_table: str) -> int:
    """统计已从 source_table 迁移的记录数"""
    try:
        row = ds.execute(
            "SELECT COUNT(*) FROM data_permission_rules WHERE source_table = ?",
            [source_table]
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


# ============================================================================
# [P3-T4 2026-07-19] 迁移 Visibility 配置
# ============================================================================

def migrate_visibility_config(ds, bo_metadata: dict = None) -> int:
    """[P3-T4] 将 BO 的 visibility 字段值迁移到 data_permission_rules (rule_type='visibility')

    数据来源:
      1. 优先: bo_metadata 参数 (从 BO.yaml 加载的 visibility 默认值)
      2. 次选: 扫描数据库各 BO 表的 visibility 列

    Args:
        ds: DB 数据源
        bo_metadata: 可选, 形如 {'product': 'public', 'business_object': 'private', ...}
                     若为 None, 跳过 metadata 路径

    Returns:
        迁移行数 (int)
    """
    if not _table_exists(ds, 'data_permission_rules'):
        raise RuntimeError(
            '[P3-T4] data_permission_rules table does not exist. '
            'Run P3-T1 (DDL) first.'
        )

    already_migrated = _count_migrated(ds, 'visibility_config')
    if already_migrated > 0:
        logger.info(
            f'[P3-T4] Already migrated {already_migrated} visibility rules. Skip.'
        )
        return 0

    migrated = 0

    # 1. 从 bo_metadata 加载 visibility 默认值 (来自 BO.yaml)
    if bo_metadata:
        for resource_type, visibility_value in bo_metadata.items():
            if not visibility_value:
                continue
            # 生成 visibility rule (为所有 role_id 通配, 用 0 表示通配)
            ds.execute(
                "INSERT INTO data_permission_rules "
                "(role_id, rule_type, resource_type, condition, scope_mode, "
                " permission_level, source_table, source_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    0,  # role_id=0 表示对所有角色生效 (visibility 是 BO 级配置)
                    'visibility',
                    resource_type,
                    str(visibility_value),
                    'include',
                    'read',
                    'visibility_config',
                    migrated + 1,
                ]
            )
            migrated += 1

    # 2. Fallback: 扫描数据库各 BO 表的 visibility 列
    #    (如果 bo_metadata 未提供, 尝试从 db 读取 visibility 列默认值)
    if not bo_metadata:
        bo_tables = _discover_bo_tables_with_visibility(ds)
        for table_name in bo_tables:
            # 获取该表所有不同的 visibility 值
            try:
                rows = ds.execute(
                    f"SELECT DISTINCT visibility FROM {table_name} "
                    f"WHERE visibility IS NOT NULL AND visibility != ''"
                ).fetchall()
                for (vis_val,) in rows:
                    ds.execute(
                        "INSERT INTO data_permission_rules "
                        "(role_id, rule_type, resource_type, condition, "
                        " permission_level, source_table, source_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [
                            0, 'visibility', table_name.rstrip('s'),
                            str(vis_val), 'read',
                            'visibility_config', migrated + 1,
                        ]
                    )
                    migrated += 1
            except Exception as e:
                logger.debug(f'[P3-T4] scan {table_name}.visibility failed: {e}')

    logger.info(f'[P3-T4] Migrated {migrated} visibility rules')
    return migrated


def _discover_bo_tables_with_visibility(ds) -> list:
    """扫描所有含 visibility 列的 BO 表"""
    tables = []
    try:
        rows = ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '_deprecated_%'"
        ).fetchall()
        for (table_name,) in rows:
            if table_name in ('sqlite_sequence', 'data_permission_rules',
                              'role_dimension_scopes', 'permission_rules'):
                continue
            try:
                cols = ds.execute(f"PRAGMA table_info({table_name})").fetchall()
                col_names = {c[1] for c in cols}
                if 'visibility' in col_names:
                    tables.append(table_name)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f'[_discover_bo_tables_with_visibility] failed: {e}')
    return tables


# ============================================================================
# [P3-T7 2026-07-19] 废弃旧表 (RENAME TO _deprecated_*)
# ============================================================================

_LEGACY_TABLES_TO_DEPRECATE = [
    'role_dimension_scopes',
    'permission_rules',
]


def deprecate_legacy_tables(ds) -> dict:
    """[P3-T7] 将旧权限表重命名为 _deprecated_* 前缀

    安全设计:
      - 仅在 data_permission_rules 已有数据时执行 (避免数据丢失)
      - 旧表已 _deprecated_ 前缀时跳过 (幂等)
      - 保留原表数据, 仅重命名 (可回滚)

    Returns:
        {'renamed': [...], 'skipped': [...]}
    """
    result = {'renamed': [], 'skipped': []}

    # 前置检查: data_permission_rules 必须有数据
    new_count = 0
    try:
        row = ds.execute(
            "SELECT COUNT(*) FROM data_permission_rules"
        ).fetchone()
        new_count = int(row[0]) if row else 0
    except Exception:
        pass

    if new_count == 0:
        raise RuntimeError(
            '[P3-T7] data_permission_rules is empty. '
            'Run P3-T2/T3/T4 migration first before deprecating legacy tables.'
        )

    for table in _LEGACY_TABLES_TO_DEPRECATE:
        deprecated_name = f'_deprecated_{table}'

        # 检查旧表是否还存在
        old_exists = _table_exists(ds, table)
        if not old_exists:
            result['skipped'].append(f'{table} (not exists)')
            continue

        # 检查 _deprecated_ 表是否已存在 (幂等)
        if _table_exists(ds, deprecated_name):
            result['skipped'].append(f'{table} (already deprecated)')
            continue

        # 重命名
        try:
            ds.execute(
                f"ALTER TABLE {table} RENAME TO {deprecated_name}"
            )
            result['renamed'].append(f'{table} → {deprecated_name}')
            logger.info(f'[P3-T7] Renamed {table} → {deprecated_name}')
        except Exception as e:
            logger.warning(f'[P3-T7] Rename {table} failed: {e}')
            result['skipped'].append(f'{table} (rename failed: {e})')

    return result


def rollback_deprecation(ds) -> dict:
    """[P3-T7] 回滚: 将 _deprecated_* 表恢复原名

    Returns:
        {'restored': [...], 'skipped': [...]}
    """
    result = {'restored': [], 'skipped': []}

    for table in _LEGACY_TABLES_TO_DEPRECATE:
        deprecated_name = f'_deprecated_{table}'
        if not _table_exists(ds, deprecated_name):
            result['skipped'].append(f'{table} (no deprecated version)')
            continue
        if _table_exists(ds, table):
            result['skipped'].append(f'{table} (original exists, cannot restore)')
            continue
        try:
            ds.execute(
                f"ALTER TABLE {deprecated_name} RENAME TO {table}"
            )
            result['restored'].append(f'{deprecated_name} → {table}')
            logger.info(f'[P3-T7 rollback] Restored {deprecated_name} → {table}')
        except Exception as e:
            logger.warning(f'[P3-T7 rollback] Restore {deprecated_name} failed: {e}')
            result['skipped'].append(f'{table} (restore failed: {e})')

    return result


# ============================================================================
# [P3 完整入口] 包含 visibility 迁移的完整流程
# ============================================================================

def migrate_all_with_visibility(ds, bo_metadata: dict = None) -> Dict[str, int]:
    """[P3] 完整迁移入口: P3-T2 + P3-T3 + P3-T4

    Args:
        ds: DB 数据源
        bo_metadata: 可选, BO.yaml 的 visibility 默认值字典

    Returns:
        {'dimension': N, 'condition': M, 'visibility': K, 'total': N+M+K}
    """
    dim_count = migrate_role_dimension_scopes(ds)
    cond_count = migrate_permission_rules(ds)
    vis_count = migrate_visibility_config(ds, bo_metadata)
    return {
        'dimension': dim_count,
        'condition': cond_count,
        'visibility': vis_count,
        'total': dim_count + cond_count + vis_count,
    }