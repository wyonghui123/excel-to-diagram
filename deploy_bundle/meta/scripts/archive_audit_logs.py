# -*- coding: utf-8 -*-
r"""
Archive Audit Logs - 6 月保留期归档脚本
【2026-06-05 Spec v1.0 实施】FR-LOG-008

策略（Stripe 模式）：
  - 每天 0:00 cron 跑一次
  - retention_until < NOW() 的日志移到 audit_logs_archive
  - 保留原表 audit_logs 中 6 月内的记录
  - 归档操作自身也写 audit_log（递归审计）

用法：
  python d:\filework\excel-to-diagram\meta\scripts\archive_audit_logs.py
  python d:\filework\excel-to-diagram\meta\scripts\archive_audit_logs.py --dry-run
  python d:\filework\excel-to-diagram\meta\scripts\archive_audit_logs.py --retention-days 90

Cron 例子（每天 0:00）：
  0 0 * * * cd /path/to/excel-to-diagram && python meta/scripts/archive_audit_logs.py
"""
import os
import sys
import sqlite3
import logging
import argparse
from datetime import datetime, timedelta
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# 默认 DB 路径
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, 'meta', 'architecture.db')
DEFAULT_RETENTION_DAYS = 180  # 6 月

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger(__name__)


def archive_old_audit_logs(db_path: str, retention_days: int = DEFAULT_RETENTION_DAYS,
                           dry_run: bool = False) -> dict:
    """
    主入口：将 retention_until < NOW() 的 audit_logs 移到 audit_logs_archive

    Returns: dict { archived_count, error_count, dry_run }
    """
    if not os.path.exists(db_path):
        logger.error(f"DB not found: {db_path}")
        return {"archived_count": 0, "error_count": 1, "dry_run": dry_run}

    # 计算截止时间（用 ISO 8601 字符串比较，兼容 SQLite TEXT 存储）
    cutoff_iso = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
    archived_at = datetime.utcnow().isoformat()

    logger.info(f"Archive audit logs older than {cutoff_iso} (retention={retention_days} days, dry_run={dry_run})")

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    archived_count = 0
    error_count = 0

    try:
        # 1. 查需要归档的记录数
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM audit_logs WHERE retention_until IS NOT NULL AND retention_until < ?",
            (cutoff_iso,)
        )
        total = cur.fetchone()['cnt']
        logger.info(f"Found {total} records to archive")

        if total == 0:
            logger.info("Nothing to archive, exit")
            return {"archived_count": 0, "error_count": 0, "dry_run": dry_run}

        if dry_run:
            logger.info(f"[DRY RUN] Would archive {total} records")
            return {"archived_count": 0, "error_count": 0, "dry_run": True, "would_archive": total}

        # 2. 批量复制到 archive 表（500/批，事务）
        BATCH_SIZE = 500
        offset = 0
        while True:
            cur.execute(
                """SELECT * FROM audit_logs
                   WHERE retention_until IS NOT NULL AND retention_until < ?
                   ORDER BY id ASC LIMIT ? OFFSET ?""",
                (cutoff_iso, BATCH_SIZE, offset)
            )
            rows = cur.fetchall()
            if not rows:
                break

            # 复制到 archive 表
            for row in rows:
                row_dict = dict(row)
                row_dict['archived_at'] = archived_at
                try:
                    cols = ', '.join(row_dict.keys())
                    placeholders = ', '.join(['?'] * len(row_dict))
                    cur.execute(
                        f"INSERT OR IGNORE INTO audit_logs_archive ({cols}) VALUES ({placeholders})",
                        list(row_dict.values())
                    )
                except Exception as e:
                    logger.warning(f"Failed to copy row id={row_dict.get('id')}: {e}")
                    error_count += 1
                    continue

            # 3. 从原表删除
            ids = [row['id'] for row in rows]
            placeholders = ', '.join(['?'] * len(ids))
            try:
                cur.execute(
                    f"DELETE FROM audit_logs WHERE id IN ({placeholders})",
                    ids
                )
                archived_count += len(ids)
                logger.info(f"Archived batch: {len(ids)} records (total: {archived_count}/{total})")
            except Exception as e:
                logger.error(f"Failed to delete batch: {e}")
                error_count += len(ids)
                conn.rollback()
                continue

            offset += BATCH_SIZE
            # 提交当前批
            conn.commit()

    except Exception as e:
        logger.error(f"Archive failed: {e}")
        conn.rollback()
        return {"archived_count": archived_count, "error_count": error_count + 1, "dry_run": dry_run}
    finally:
        conn.close()

    logger.info(f"Archive done: {archived_count} archived, {error_count} errors")

    # 4. 归档操作自身也写 audit（FR-LOG-008 自己产生的归档操作也审计）
    try:
        _log_archive_action(db_path, archived_count, error_count, retention_days)
    except Exception as e:
        logger.warning(f"Failed to log archive action to audit: {e}")

    return {"archived_count": archived_count, "error_count": error_count, "dry_run": dry_run}


def _log_archive_action(db_path: str, archived_count: int, error_count: int, retention_days: int) -> None:
    """归档操作自身写 audit（system action）"""
    conn = sqlite3.connect(db_path, timeout=10)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO audit_logs (
                object_type, object_id, action, field_name, old_value, new_value,
                user_id, user_name, ip_address, user_agent, created_at,
                action_kind, outcome, error_message, retention_until,
                log_category, log_level, status
            ) VALUES (
                'audit_log', 'archive', 'archive_old_logs', 'archived_count', NULL, ?,
                0, 'system:cron', '127.0.0.1', 'archive_audit_logs.py', ?,
                'static', ?, ?, ?,
                'system', 'INFO', 'success'
            )
        """, (
            f"{archived_count} archived, {error_count} errors",
            datetime.utcnow().isoformat(),
            'success' if error_count == 0 else 'failure',
            f"{error_count} errors" if error_count > 0 else None,
            (datetime.utcnow() + timedelta(days=DEFAULT_RETENTION_DAYS)).isoformat(),
        ))
        conn.commit()
        logger.info("Archive action logged to audit_logs")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Archive audit logs older than retention period')
    parser.add_argument('--db-path', default=DEFAULT_DB_PATH, help='SQLite DB path')
    parser.add_argument('--retention-days', type=int, default=DEFAULT_RETENTION_DAYS,
                        help=f'Retention period in days (default: {DEFAULT_RETENTION_DAYS} = 6 months)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be archived without making changes')
    args = parser.parse_args()

    result = archive_old_audit_logs(args.db_path, args.retention_days, args.dry_run)
    sys.exit(0 if result['error_count'] == 0 else 1)


if __name__ == '__main__':
    main()
