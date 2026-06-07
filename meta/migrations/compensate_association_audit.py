# -*- coding: utf-8 -*-
"""
关联操作审计日志数据补偿脚本

为修复 Bug 前缺失的关联操作审计日志生成补偿数据。
来源：
  - user_roles 表 -> user-role ASSOCIATE 补偿记录
  - user_group_members 表 -> user_group-member ASSOCIATE 补偿记录

特性：
  - 幂等：同一关联关系只生成一次补偿记录
  - 支持 --dry-run 模式预览
  - 补偿记录使用 field_name 后缀 __compensation__ 标识
  - 操作人默认设为 system_compensation
"""

import os
import sys
import sqlite3
import argparse
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

COMPENSATION_USER_ID = 'system_compensation'
COMPENSATION_USER_NAME = 'system_compensation'
COMPENSATION_MARKER = '__compensation__'


def get_db_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db'
    )


def compensate_user_roles(conn, dry_run=False):
    """从 user_roles 表补偿 user-role ASSOCIATE 审计日志"""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ur.user_id, ur.role_id, users.username, roles.name as role_name
        FROM user_roles ur
        LEFT JOIN users ON ur.user_id = users.id
        LEFT JOIN roles ON ur.role_id = roles.id
    """)
    records = cursor.fetchall()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    compensated = 0
    skipped = 0

    for user_id, role_id, username, role_name in records:
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs
            WHERE object_type = 'user'
            AND object_id = ?
            AND action = 'ASSOCIATE'
            AND new_value LIKE ?
            AND field_name = ?
        """, [str(user_id), f'%role%{role_id}%', f'roles{COMPENSATION_MARKER}'])

        if cursor.fetchone()[0] > 0:
            skipped += 1
            continue

        if not dry_run:
            cursor.execute("""
                INSERT INTO audit_logs (
                    object_type, object_id, action, field_name,
                    new_value, user_id, user_name,
                    log_category, log_level, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                'user',
                str(user_id),
                'ASSOCIATE',
                f'roles{COMPENSATION_MARKER}',
                f'{{"target_type": "role", "target_id": {role_id}}}',
                COMPENSATION_USER_ID,
                COMPENSATION_USER_NAME,
                'BUSINESS',
                'INFO',
                'written',
                now,
                now,
            ])

        compensated += 1

    logger.info(f"[UserRoles] Total: {len(records)}, Compensated: {compensated}, Skipped: {skipped}")
    return compensated


def compensate_user_group_members(conn, dry_run=False):
    """从 user_group_members 表补偿 user_group-member ASSOCIATE 审计日志"""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ugm.user_id, ugm.group_id, ug.code as group_code
        FROM user_group_members ugm
        LEFT JOIN user_groups ug ON ugm.group_id = ug.id
    """)
    records = cursor.fetchall()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    compensated = 0
    skipped = 0

    for user_id, group_id, group_code in records:
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs
            WHERE object_type = 'user_group'
            AND object_id = ?
            AND action = 'ASSOCIATE'
            AND new_value LIKE ?
            AND field_name = ?
        """, [str(group_id), f'%user%{user_id}%', f'members{COMPENSATION_MARKER}'])

        if cursor.fetchone()[0] > 0:
            skipped += 1
            continue

        if not dry_run:
            cursor.execute("""
                INSERT INTO audit_logs (
                    object_type, object_id, action, field_name,
                    new_value, user_id, user_name,
                    log_category, log_level, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                'user_group',
                str(group_id),
                'ASSOCIATE',
                f'members{COMPENSATION_MARKER}',
                f'{{"target_type": "user", "target_id": {user_id}}}',
                COMPENSATION_USER_ID,
                COMPENSATION_USER_NAME,
                'BUSINESS',
                'INFO',
                'written',
                now,
                now,
            ])

        compensated += 1

    logger.info(f"[UserGroupMembers] Total: {len(records)}, Compensated: {compensated}, Skipped: {skipped}")
    return compensated


def main():
    parser = argparse.ArgumentParser(description='补偿关联操作审计日志')
    parser.add_argument('--dry-run', action='store_true',
                        help='预览模式，不实际写入数据库')
    parser.add_argument('--user-roles-only', action='store_true',
                        help='仅补偿 user_roles')
    parser.add_argument('--group-members-only', action='store_true',
                        help='仅补偿 user_group_members')
    args = parser.parse_args()

    db_path = get_db_path()
    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        sys.exit(1)

    logger.info(f"Database: {db_path}")
    if args.dry_run:
        logger.info("[DRY RUN] Preview mode - no changes will be written")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        total = 0

        if not args.group_members_only:
            total += compensate_user_roles(conn, dry_run=args.dry_run)

        if not args.user_roles_only:
            total += compensate_user_group_members(conn, dry_run=args.dry_run)

        if args.dry_run:
            logger.info(f"[DRY RUN] Would compensate {total} records total")
            conn.rollback()
        else:
            conn.commit()
            logger.info(f"Successfully compensated {total} audit log records")

    except Exception as e:
        logger.error(f"Compensation failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
