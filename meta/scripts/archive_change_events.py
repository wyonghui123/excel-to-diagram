# -*- coding: utf-8 -*-
r"""Archive Change Events - change_events 保留期归档 CLI

策略（P1-d 起统一托付 meta/services/change_event_archive.py）：
  - 每日 03:00 由 MaintenanceScheduler 作业 change_event_archive 触发
  - retention_until < NOW() 的事件移到 change_events_archive
  - 同批清理 notification_inbox / notification_deliveries 对应行
  - 复制成功且确认落地后才删除源行（复制失败的行保留，防丢数据）

用法：
  python meta/scripts/archive_change_events.py
  python meta/scripts/archive_change_events.py --dry-run
  python meta/scripts/archive_change_events.py --db-path <db>
"""
import os
import sys
import logging
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.services.change_event_archive import archive_expired  # noqa: E402

DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, 'meta', 'architecture.db')

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger(__name__)


def archive_old_change_events(db_path: str, dry_run: bool = False) -> dict:
    """兼容旧入口：委托 change_event_archive.archive_expired。

    Returns: dict { archived_count, error_count, dry_run, ... }
    """
    result = archive_expired(db_path, dry_run=dry_run)
    if dry_run and 'would_archive' not in result:
        result['would_archive'] = 0
    return result


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