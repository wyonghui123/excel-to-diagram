# -*- coding: utf-8 -*-
"""
Migration: permission_rules (legacy) → permission_rules_v2

[Phase 2 P4.4 补充] 迁移 permission_rules 表的 350 条规则到 permission_rules_v2

[迁移映射]
  permission_rules.condition (自由文本) → ConditionConverter → [{field,op,value}]
  permission_rules.is_denied=0 → include_conditions
  permission_rules.is_denied=1 → exclude_conditions
  permission_rules.permission_level → 直接透传
  permission_rules.resource_type → 直接透传
  permission_rules.inherit_to_children → derivation_mode ('static' / 'dynamic')

[执行方式]
  python -m meta.migrations.migrate_rules_to_v2 [db_path]
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

MIGRATION_VERSION = '2026_07_25_migrate_rules_to_v2'
MIGRATION_NAME = 'migrate_permission_rules_legacy_to_v2'


def up(db_path: str) -> dict:
    """迁移 permission_rules (legacy) → permission_rules_v2

    Args:
        db_path: 数据库路径

    Returns:
        {'migrated': int, 'skipped': int, 'failed': int}
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    converter = ConditionConverter()
    stats = {'migrated': 0, 'skipped': 0, 'failed': 0}

    try:
        # 检查目标表
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='permission_rules_v2'"
        )
        if not cursor.fetchone():
            print(f'[SKIP] permission_rules_v2 not exists, run add_permission_rules_v2 first')
            return stats

        # 检查源表
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='permission_rules'"
        )
        if not cursor.fetchone():
            print(f'[SKIP] permission_rules (legacy) not exists, nothing to migrate')
            return stats

        # 加载所有 legacy 规则
        rows = conn.execute(
            '''SELECT rowid as _rid, role_id, resource_type, condition,
                      permission_level, is_denied, inherit_to_children,
                      propagate_to_parents, analysis_mode
               FROM permission_rules'''
        ).fetchall()

        print(f'[INFO] Found {len(rows)} legacy permission_rules to migrate')

        for row in rows:
            try:
                rule = _convert_legacy_rule(row, converter)
                if rule is None:
                    stats['skipped'] += 1
                    continue
                _insert_v2_rule(conn, rule, source='migrated_perm_rule')
                stats['migrated'] += 1
            except Exception as e:
                logger.warning(
                    f'Skip perm_rule rowid={row["_rid"]}: {e}'
                )
                stats['failed'] += 1

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


def down(db_path: str) -> None:
    """回滚: 删除所有 migrated_perm_rule 来源的 v2 规则"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "DELETE FROM permission_rules_v2 WHERE source = 'migrated_perm_rule'"
        )
        conn.execute(
            "DELETE FROM _migrations WHERE version = ?",
            [MIGRATION_VERSION],
        )
        conn.commit()
        print('[OK] Rollback: removed migrated_perm_rule records')
    except Exception as e:
        print(f'[ERROR] Rollback failed: {e}')
        conn.rollback()
    finally:
        conn.close()


def _convert_legacy_rule(row, converter: ConditionConverter) -> dict:
    """permission_rules (legacy) → permission_rules_v2 rule

    [映射]
      condition (自由文本) → converter.convert() → [{field,op,value}]
      is_denied=0 → include_conditions
      is_denied=1 → exclude_conditions
      permission_level → 直接透传 (默认 'read')
      resource_type → 直接透传
      inherit_to_children=1 → derivation_mode='dynamic' (子维度继承)
      inherit_to_children=0 → derivation_mode='static'
    """
    condition_text = row['condition'] if 'condition' in row.keys() else None
    conditions = converter.convert(condition_text)
    is_denied = bool(row['is_denied']) if 'is_denied' in row.keys() else False
    permission_level = (
        row['permission_level'] if 'permission_level' in row.keys() else 'read'
    )
    resource_type = (
        row['resource_type'] if 'resource_type' in row.keys() else None
    )

    if not resource_type:
        return None

    # 没有条件且不是 is_denied → 跳过 (无意义)
    if not conditions and not is_denied:
        return None

    # inherit_to_children → derivation_mode
    inherit = (
        row['inherit_to_children'] if 'inherit_to_children' in row.keys() else 0
    )
    derivation_mode = 'dynamic' if inherit else 'static'

    if is_denied:
        # is_denied=1 → exclude_conditions
        return {
            'role_id': row['role_id'],
            'resource_type': resource_type,
            'permission_level': permission_level,
            'include_conditions': [],
            'exclude_conditions': conditions,
            'derivation_mode': derivation_mode,
        }
    else:
        # is_denied=0 → include_conditions
        return {
            'role_id': row['role_id'],
            'resource_type': resource_type,
            'permission_level': permission_level,
            'include_conditions': conditions,
            'exclude_conditions': [],
            'derivation_mode': derivation_mode,
        }


def _insert_v2_rule(conn, rule: dict, source: str = 'migrated_perm_rule') -> None:
    """插入 permission_rules_v2 (source 标记来源)"""
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
            rule.get('permission_level', 'read'),
            json.dumps(rule.get('include_conditions', []), ensure_ascii=False),
            json.dumps(rule.get('exclude_conditions', []), ensure_ascii=False),
            rule.get('derivation_mode', 'static'),
            source,
        ],
    )


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        _PROJECT_ROOT, 'meta', 'architecture.db'
    )
    up(db)
