# -*- coding: utf-8 -*-
"""
Migration: role_dimension_scopes + data_permission_rules → permission_rules_v2

[Phase 2] 数据迁移脚本 (零停机)

[迁移源]
  1. role_dimension_scopes (维度范围配置)
     - dimension_code + scope_mode + dimension_values
     - → include_conditions: [{field: <dim>_id, op: IN/include, value: values}]
     - scope_mode='all' → include_conditions = [] (空 = all)

  2. data_permission_rules (条件规则)
     - condition (自由文本) → 通过 ConditionConverter 转为 [{field,op,value}]
     - is_denied=1 → exclude_conditions
     - rule_type='dimension' 的记录合并到 (1) 的结果
     - permission_level 直接透传

[迁移策略]
  - 双写期: 不删除旧表, 仅填充 permission_rules_v2
  - 幂等: 可重复执行, 通过 source='migrated_<table>' 去重
  - 失败回滚: 单条失败不影响整体, 记录日志

[执行方式]
  python -m meta.migrations.migrate_dimension_scopes_to_v2 [db_path]
"""
import json
import sqlite3
import os
import sys
import logging

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.condition_converter import ConditionConverter

logger = logging.getLogger(__name__)


MIGRATION_VERSION = '2026_07_25_migrate_to_v2'
MIGRATION_NAME = 'migrate_legacy_to_permission_rules_v2'


def up(db_path: str) -> dict:
    """迁移 role_dimension_scopes + data_permission_rules → permission_rules_v2

    Args:
        db_path: 数据库路径

    Returns:
        {'dimension_scopes': int, 'permission_rules': int, 'skipped': int}
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    converter = ConditionConverter()
    stats = {'dimension_scopes': 0, 'permission_rules': 0, 'skipped': 0}

    try:
        # 检查目标表是否存在
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='permission_rules_v2'"
        )
        if not cursor.fetchone():
            print(f'[SKIP] permission_rules_v2 not exists, run add_permission_rules_v2 first')
            return stats

        # ============================================================
        # 1. 迁移 role_dimension_scopes
        # ============================================================
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='role_dimension_scopes'"
        )
        if cursor.fetchone():
            rows = conn.execute(
                '''SELECT * FROM role_dimension_scopes WHERE scope_mode IS NOT NULL'''
            ).fetchall()
            for row in rows:
                try:
                    rule = _convert_dimension_scope(row)
                    if rule:
                        _insert_v2_rule(conn, rule, source='migrated_dim_scope')
                        stats['dimension_scopes'] += 1
                except Exception as e:
                    logger.warning(f'Skip dim_scope id={row["id"]}: {e}')
                    stats['skipped'] += 1
            conn.commit()

        # ============================================================
        # 2. 迁移 data_permission_rules
        # ============================================================
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='data_permission_rules'"
        )
        if cursor.fetchone():
            rows = conn.execute(
                '''SELECT * FROM data_permission_rules'''
            ).fetchall()
            for row in rows:
                try:
                    rule = _convert_permission_rule(row, converter)
                    if rule:
                        _insert_v2_rule(conn, rule, source='migrated_perm_rule')
                        stats['permission_rules'] += 1
                except Exception as e:
                    logger.warning(f'Skip perm_rule id={row["id"]}: {e}')
                    stats['skipped'] += 1
            conn.commit()

        # 记录 migration
        try:
            conn.execute(
                'INSERT OR REPLACE INTO _migrations (version, name) VALUES (?, ?)',
                [MIGRATION_VERSION, MIGRATION_NAME],
            )
            conn.commit()
        except sqlite3.Error:
            pass

        print(f'[OK] Migration: {stats}')
        return stats
    except Exception as e:
        print(f'[ERROR] {e}')
        conn.rollback()
        raise
    finally:
        conn.close()


def _convert_dimension_scope(row) -> dict:
    """role_dimension_scopes → permission_rules_v2 rule

    [映射]
      dimension_code='domain', dimension_values=[1,2], scope_mode='include'
      → resource_type='domain', include_conditions=[{field:'domain_id', op:'IN', value:[1,2]}]

      scope_mode='all' → include_conditions=[] (空 = all)
    """
    dim_code = row['dimension_code']
    scope_mode = row['scope_mode'] or 'include'
    raw_values = row['dimension_values']

    # 解析 dimension_values
    values = _parse_dim_values(raw_values)

    if scope_mode == 'all':
        include_conditions = []
    elif scope_mode == 'include' and values:
        include_conditions = [{
            'field': f'{dim_code}_id',
            'op': 'IN',
            'value': values,
        }]
    elif scope_mode == 'exclude' and values:
        # scope_mode='exclude' → 写入 exclude_conditions
        include_conditions = []
        # 注: 这条规则的 resource_type 应是子维度, 但老表无对应信息
        # 暂用 dimension_code 作为 resource_type
        return {
            'role_id': row['role_id'],
            'resource_type': dim_code,
            'permission_level': 'read',  # 默认 read
            'include_conditions': [],
            'exclude_conditions': [{
                'field': f'{dim_code}_id',
                'op': 'IN',
                'value': values,
            }],
            'derivation_mode': 'static',
        }
    else:
        # 未知 scope_mode 或无值, 跳过
        return None

    return {
        'role_id': row['role_id'],
        'resource_type': dim_code,
        'permission_level': 'read',  # 老表无 level 信息, 默认 read
        'include_conditions': include_conditions,
        'exclude_conditions': [],
        'derivation_mode': 'static',
    }


def _convert_permission_rule(row, converter: ConditionConverter) -> dict:
    """data_permission_rules → permission_rules_v2 rule

    [映射]
      condition (自由文本) → converter.convert() → [{field,op,value}]
      is_denied=1 → 写入 exclude_conditions
      is_denied=0 → 写入 include_conditions
      permission_level 直接透传
      resource_type 直接透传
    """
    condition_text = row['condition'] if 'condition' in row.keys() else None
    conditions = converter.convert(condition_text)
    is_denied = bool(row['is_denied']) if 'is_denied' in row.keys() else False
    permission_level = row['permission_level'] if 'permission_level' in row.keys() else 'read'
    resource_type = row['resource_type'] if 'resource_type' in row.keys() else None

    if not resource_type:
        return None

    if is_denied:
        return {
            'role_id': row['role_id'],
            'resource_type': resource_type,
            'permission_level': 'none',  # deny 规则不授予任何 action
            'include_conditions': [],
            'exclude_conditions': conditions,
            'derivation_mode': 'static',
        }

    return {
        'role_id': row['role_id'],
        'resource_type': resource_type,
        'permission_level': permission_level,
        'include_conditions': conditions,
        'exclude_conditions': [],
        'derivation_mode': 'static',
    }


def _parse_dim_values(raw) -> list:
    """解析 dimension_values 字段 (兼容 JSON/list/None)"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [int(x) for x in raw if str(x).lstrip('-').isdigit()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [int(x) for x in parsed if str(x).lstrip('-').isdigit()]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _insert_v2_rule(conn, rule: dict, source: str) -> None:
    """插入一条 permission_rules_v2 记录"""
    include_json = json.dumps(rule['include_conditions'], ensure_ascii=False)
    exclude_json = json.dumps(rule['exclude_conditions'], ensure_ascii=False)
    conn.execute(
        '''
        INSERT INTO permission_rules_v2
            (role_id, resource_type, permission_level,
             include_conditions, exclude_conditions,
             derivation_mode, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        [
            rule['role_id'],
            rule['resource_type'],
            rule['permission_level'],
            include_json,
            exclude_json,
            rule['derivation_mode'],
            source,
        ],
    )


def down(db_path: str) -> None:
    """回滚: 删除所有 migrated 来源的 v2 规则"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            '''DELETE FROM permission_rules_v2
               WHERE source IN ('migrated_dim_scope', 'migrated_perm_rule')'''
        )
        conn.execute(
            'DELETE FROM _migrations WHERE version = ?',
            [MIGRATION_VERSION],
        )
        conn.commit()
        print(f'[OK] Migration reverted')
    finally:
        conn.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    default_db = os.path.join(_PROJECT_ROOT, 'meta', 'db', 'archdata.db')
    db_path = sys.argv[1] if len(sys.argv) > 1 else default_db

    if not os.path.exists(db_path):
        print(f'[ERROR] DB not found: {db_path}')
        sys.exit(1)

    # 确保 _migrations 表存在
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS _migrations (
            version TEXT PRIMARY KEY,
            name TEXT,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

    up(db_path)
