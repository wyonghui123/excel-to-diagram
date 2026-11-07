# -*- coding: utf-8 -*-
r"""Archive Change Events - change_events 365 天保留期归档脚本

策略（T7.1 归档策略）：
  - 每天 0:00 cron 跑一次
  - retention_until < NOW() 的事件移到 change_events_archive
  - 复制成功且确认落地后才删除源行（复制失败的行保留，防丢数据）
  - keyset 分页（id > last_id），避免 OFFSET + DELETE 跳行
  - 归档操作自身写 audit_logs（system action）

用法：
  python meta/scripts/archive_change_events.py
  python meta/scripts/archive_change_events.py --dry-run
  python meta/scripts/archive_change_events.py --db-path <db>

Cron 例子（每天 0:05，排在 audit 归档之后）：
  5 0 * * * cd /path/to/excel-to-diagram && python meta/scripts/archive_change_events.py
"""
import os
import sys
import sqlite3
import logging
import argparse
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, 'meta', 'architecture.db')
BATCH_SIZE = 500

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger(__name__)


def archive_old_change_events(db_path: str, dry_run: bool = False) -> dict:
    """将 retention_until < NOW() 的 change_events 移到 change_events_archive

    Returns: dict { archived_count, error_count, dry_run }
    """
    if not os.path.exists(db_path):
        logger.error(f"DB not found: {db_path}")
        return {"archived_count": 0, "error_count": 1, "dry_run": dry_run}

    cutoff_iso = datetime.now().isoformat()
    archived_at = datetime.now().isoformat()

    logger.info(f"Archive change_events before {cutoff_iso} (dry_run={dry_run})")

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    archived_count = 0
    error_count = 0

    try:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM change_events "
            "WHERE retention_until IS NOT NULL AND retention_until < ?",
            (cutoff_iso,)
        )
        total = cur.fetchone()['cnt']
        logger.info(f"Found {total} records to archive")

        if total == 0:
            logger.info("Nothing to archive, exit")
            return {"archived_count": 0, "error_count": 0, "dry_run": dry_run}

        if dry_run:
            logger.info(f"[DRY RUN] Would archive {total} records")
            return {"archived_count": 0, "error_count": 0, "dry_run": True,
                    "would_archive": total}

        last_id = 0
        while True:
            cur.execute(
                """SELECT * FROM change_events
                   WHERE retention_until IS NOT NULL AND retention_until < ? AND id > ?
                   ORDER BY id ASC LIMIT ?""",
                (cutoff_iso, last_id, BATCH_SIZE)
            )
            rows = cur.fetchall()
            if not rows:
                break
            last_id = rows[-1]['id']

            copied_ids = []
            for row in rows:
                row_dict = dict(row)
                row_dict['archived_at'] = archived_at
                try:
                    cols = ', '.join(row_dict.keys())
                    placeholders = ', '.join(['?'] * len(row_dict))
                    cur.execute(
                        f"INSERT OR IGNORE INTO change_events_archive ({cols}) "
                        f"VALUES ({placeholders})",
                        list(row_dict.values())
                    )
                    copied_ids.append(row['id'])
                except Exception as e:
                    logger.error(f"Failed to copy row id={row_dict.get('id')}, keep it in source: {e}")
                    error_count += 1

            if not copied_ids:
                conn.commit()
                continue

            # 删除前确认 archive 中确实存在对应行（防止复制失败仍删除）
            placeholders = ', '.join(['?'] * len(copied_ids))
            cur.execute(
                f"SELECT id FROM change_events_archive WHERE id IN ({placeholders})",
                copied_ids
            )
            archived_ids = {r['id'] for r in cur.fetchall()}
            safe_ids = [i for i in copied_ids if i in archived_ids]
            missing = len(copied_ids) - len(safe_ids)
            if missing:
                logger.error(f"{missing} rows not found in archive after copy, skip deleting them")
                error_count += missing

            if safe_ids:
                placeholders = ', '.join(['?'] * len(safe_ids))
                try:
                    cur.execute(
                        f"DELETE FROM change_events WHERE id IN ({placeholders})",
                        safe_ids
                    )
                    archived_count += len(safe_ids)
                    logger.info(f"Archived batch: {len(safe_ids)} records "
                                f"(total: {archived_count}/{total})")
                except Exception as e:
                    logger.error(f"Failed to delete batch: {e}")
                    error_count += len(safe_ids)
                    conn.rollback()
                    continue

            conn.commit()

    except Exception as e:
        logger.error(f"Archive failed: {e}")
        conn.rollback()
        return {"archived_count": archived_count, "error_count": error_count + 1,
                "dry_run": dry_run}
    finally:
        conn.close()

    logger.info(f"Archive done: {archived_count} archived, {error_count} errors")

    try:
        _log_archive_action(db_path, archived_count, error_count)
    except Exception as e:
        logger.warning(f"Failed to log archive action to audit: {e}")

    return {"archived_count": archived_count, "error_count": error_count,
            "dry_run": dry_run}


def _log_archive_action(db_path: str, archived_count: int, error_count: int) -> None:
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
                'change_event', 'archive', 'archive_old_events', 'archived_count', NULL, ?,
                0, 'system:cron', '127.0.0.1', 'archive_change_events.py', ?,
                'static', ?, ?, ?,
                'system', 'INFO', 'success'
            )
        """, (
            f"{archived_count} archived, {error_count} errors",
            datetime.now().isoformat(),
            'success' if error_count == 0 else 'failure',
            f"{error_count} errors" if error_count > 0 else None,
            (datetime.now() + timedelta(days=365)).isoformat(),
        ))
        conn.commit()
        logger.info("Archive action logged to audit_logs")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Archive change_events past retention')
    parser.add_argument('--db-path', default=DEFAULT_DB_PATH, help='SQLite DB path')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be archived without making changes')
    args = parser.parse_args()

    result = archive_old_change_events(args.db_path, args.dry_run)
    sys.exit(0 if result['error_count'] == 0 else 1)


if __name__ == '__main__':
    main()
