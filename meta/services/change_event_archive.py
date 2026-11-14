# -*- coding: utf-8 -*-
"""变更事件与收件箱的保留期归档（P1-d）。

策略（spec-message-platform §12）：
    - 每日 03:00 由 MaintenanceScheduler 触发（作业码 change_event_archive）
    - retention_until < now 的 change_events 复制到 change_events_archive
    - 复制成功且确认落地后才删除源行（复制失败的行保留，防丢数据）
    - 同批清理 notification_inbox / notification_deliveries 中对应事件的行
    - keyset 分页（id > last_id），避免 OFFSET + DELETE 跳行
    - 归档操作自身写 audit_logs（system action）

兼容：`meta/scripts/archive_change_events.py` 的命令行入口委托本模块。
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
EVENTS_TABLE = 'change_events'
ARCHIVE_TABLE = 'change_events_archive'
INBOX_TABLE = 'notification_inbox'
DELIVERIES_TABLE = 'notification_deliveries'


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def _delete_children(cur, event_ids: List[int]) -> Dict[str, int]:
    """删除归档事件对应的收件箱 / 投递记录（表不存在时跳过）。"""
    result = {'inbox_deleted': 0, 'deliveries_deleted': 0}
    if not event_ids:
        return result
    placeholders = ', '.join(['?'] * len(event_ids))
    if _table_exists(cur, INBOX_TABLE):
        cur.execute(
            f"DELETE FROM {INBOX_TABLE} WHERE event_id IN ({placeholders})",
            event_ids,
        )
        result['inbox_deleted'] += max(cur.rowcount, 0)
    if _table_exists(cur, DELIVERIES_TABLE):
        cur.execute(
            f"DELETE FROM {DELIVERIES_TABLE} WHERE event_id IN ({placeholders})",
            event_ids,
        )
        result['deliveries_deleted'] += max(cur.rowcount, 0)
    return result


def _cleanup_orphans(cur) -> Dict[str, int]:
    """清理指向已不存在事件的收件箱 / 投递行（历史归档遗留）。"""
    result = {'inbox_deleted': 0, 'deliveries_deleted': 0}
    if _table_exists(cur, INBOX_TABLE):
        cur.execute(
            f"DELETE FROM {INBOX_TABLE} WHERE event_id IS NOT NULL "
            f"AND event_id NOT IN (SELECT id FROM {EVENTS_TABLE})"
        )
        result['inbox_deleted'] += max(cur.rowcount, 0)
    if _table_exists(cur, DELIVERIES_TABLE):
        cur.execute(
            f"DELETE FROM {DELIVERIES_TABLE} WHERE event_id IS NOT NULL "
            f"AND event_id NOT IN (SELECT id FROM {EVENTS_TABLE})"
        )
        result['deliveries_deleted'] += max(cur.rowcount, 0)
    return result


def _dry_run_counts(cur, cutoff_iso: str) -> Dict[str, int]:
    """dry-run：统计将归档事件数与将清理的收件箱数。"""
    cur.execute(
        f"SELECT COUNT(*) AS cnt FROM {EVENTS_TABLE} "
        "WHERE retention_until IS NOT NULL AND retention_until < ?",
        (cutoff_iso,),
    )
    total = cur.fetchone()['cnt']
    would_clean_inbox = 0
    if _table_exists(cur, INBOX_TABLE):
        cur.execute(
            f"SELECT COUNT(*) AS cnt FROM {INBOX_TABLE} WHERE event_id IS NOT NULL "
            f"AND (event_id NOT IN (SELECT id FROM {EVENTS_TABLE}) "
            f"OR event_id IN (SELECT id FROM {EVENTS_TABLE} "
            "WHERE retention_until IS NOT NULL AND retention_until < ?))",
            (cutoff_iso,),
        )
        would_clean_inbox = cur.fetchone()['cnt']
    return {'would_archive': total, 'would_clean_inbox': would_clean_inbox}


def archive_expired(
    db_path: str,
    dry_run: bool = False,
    batch_size: int = BATCH_SIZE,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    """归档过期变更事件并清理对应收件箱 / 投递记录。

    Returns:
        {archived_count, error_count, dry_run, inbox_deleted, deliveries_deleted}
        dry_run=True 时另含 would_archive / would_clean_inbox。
    """
    result: Dict[str, object] = {
        'archived_count': 0,
        'error_count': 0,
        'dry_run': dry_run,
        'inbox_deleted': 0,
        'deliveries_deleted': 0,
    }
    if not os.path.exists(db_path):
        logger.error("DB not found: %s", db_path)
        result['error_count'] = 1
        return result

    current = now or datetime.now()
    cutoff_iso = current.isoformat()
    archived_at = current.isoformat()
    logger.info("Archive change_events before %s (dry_run=%s)", cutoff_iso, dry_run)

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    archived_count = 0
    error_count = 0
    inbox_deleted = 0
    deliveries_deleted = 0

    try:
        if not _table_exists(cur, EVENTS_TABLE):
            logger.info("change_events table not found, nothing to archive")
            return result

        counts = _dry_run_counts(cur, cutoff_iso)
        total = counts['would_archive']
        logger.info("Found %s records to archive", total)
        if total == 0:
            result['error_count'] = 0
            return result

        if dry_run:
            logger.info(
                "[DRY RUN] Would archive %s events, clean %s inbox rows",
                total, counts['would_clean_inbox'],
            )
            result['would_archive'] = total
            result['would_clean_inbox'] = counts['would_clean_inbox']
            return result

        last_id = 0
        while True:
            cur.execute(
                f"""SELECT * FROM {EVENTS_TABLE}
                    WHERE retention_until IS NOT NULL AND retention_until < ?
                      AND id > ?
                    ORDER BY id ASC LIMIT ?""",
                (cutoff_iso, last_id, int(batch_size)),
            )
            rows = cur.fetchall()
            if not rows:
                break
            last_id = rows[-1]['id']

            copied_ids: List[int] = []
            for row in rows:
                row_dict = dict(row)
                row_dict['archived_at'] = archived_at
                try:
                    cols = ', '.join(row_dict.keys())
                    placeholders = ', '.join(['?'] * len(row_dict))
                    cur.execute(
                        f"INSERT OR IGNORE INTO {ARCHIVE_TABLE} ({cols}) "
                        f"VALUES ({placeholders})",
                        list(row_dict.values()),
                    )
                    copied_ids.append(row['id'])
                except Exception as e:
                    logger.error(
                        "Failed to copy row id=%s, keep it in source: %s",
                        row_dict.get('id'), e,
                    )
                    error_count += 1

            if not copied_ids:
                conn.commit()
                continue

            # 删除前确认 archive 中确实存在对应行（防止复制失败仍删除）
            placeholders = ', '.join(['?'] * len(copied_ids))
            cur.execute(
                f"SELECT id FROM {ARCHIVE_TABLE} WHERE id IN ({placeholders})",
                copied_ids,
            )
            archived_ids = {r['id'] for r in cur.fetchall()}
            safe_ids = [i for i in copied_ids if i in archived_ids]
            missing = len(copied_ids) - len(safe_ids)
            if missing:
                logger.error(
                    "%s rows not found in archive after copy, skip deleting them", missing
                )
                error_count += missing

            if safe_ids:
                placeholders = ', '.join(['?'] * len(safe_ids))
                try:
                    cur.execute(
                        f"DELETE FROM {EVENTS_TABLE} WHERE id IN ({placeholders})",
                        safe_ids,
                    )
                    archived_count += len(safe_ids)
                    children = _delete_children(cur, safe_ids)
                    inbox_deleted += children['inbox_deleted']
                    deliveries_deleted += children['deliveries_deleted']
                    logger.info(
                        "Archived batch: %s records (total: %s/%s), "
                        "inbox=%s deliveries=%s",
                        len(safe_ids), archived_count, total,
                        children['inbox_deleted'], children['deliveries_deleted'],
                    )
                except Exception as e:
                    logger.error("Failed to delete batch: %s", e)
                    error_count += len(safe_ids)
                    conn.rollback()
                    continue

            conn.commit()

        # 兜底：清理历史归档遗留的孤儿收件箱 / 投递行
        orphans = _cleanup_orphans(cur)
        inbox_deleted += orphans['inbox_deleted']
        deliveries_deleted += orphans['deliveries_deleted']
        conn.commit()

    except Exception as e:
        logger.error("Archive failed: %s", e)
        conn.rollback()
        result.update({
            'archived_count': archived_count,
            'error_count': error_count + 1,
        })
        return result
    finally:
        conn.close()

    logger.info(
        "Archive done: %s archived, %s errors, %s inbox, %s deliveries",
        archived_count, error_count, inbox_deleted, deliveries_deleted,
    )
    result.update({
        'archived_count': archived_count,
        'error_count': error_count,
        'inbox_deleted': inbox_deleted,
        'deliveries_deleted': deliveries_deleted,
    })

    try:
        _log_archive_action(db_path, archived_count, error_count, inbox_deleted)
    except Exception as e:
        logger.warning("Failed to log archive action to audit: %s", e)

    return result


def _log_archive_action(
    db_path: str, archived_count: int, error_count: int, inbox_deleted: int = 0
) -> None:
    """归档操作自身写 audit（system action）。"""
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
                0, 'system:cron', '127.0.0.1', 'change_event_archive', ?,
                'static', ?, ?, ?,
                'system', 'INFO', 'success'
            )
        """, (
            f"{archived_count} archived, {error_count} errors, "
            f"{inbox_deleted} inbox cleaned",
            datetime.now().isoformat(),
            'success' if error_count == 0 else 'failure',
            f"{error_count} errors" if error_count > 0 else None,
            (datetime.now() + timedelta(days=365)).isoformat(),
        ))
        conn.commit()
        logger.info("Archive action logged to audit_logs")
    finally:
        conn.close()


class ChangeEventArchiveHandler:
    """MaintenanceScheduler 作业处理器：每日归档过期事件与收件箱。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def execute(self, params: Optional[dict] = None, context: Optional[dict] = None):
        params = params or {}
        context = context or {}
        db_path = (
            self.db_path
            or params.get('db_path')
            or context.get('db_path')
        )
        if not db_path:
            from meta.core.db_path import get_meta_db_path
            db_path = get_meta_db_path()
        return archive_expired(db_path, dry_run=bool(params.get('dry_run')))