# -*- coding: utf-8 -*-
"""期初库存入库日期一次性回填（P8-15）。

依据: docs/specs/p8-inventory-aging-model/spec.md §7.1「期初库存」

背景:
- 无任何库存事务历史的余额行（期初上载 / 历史迁移）不伪造日期，保持 NULL，
  库龄报表落 UNASSIGNED。
- 业务确认上线日后，用本脚本把该组织的期初余额显式指定为上线日（SAP 561
  期初上载口径：过账日 = 上线日）。

用法:
    python scripts/backfill_first_received_date.py --org 1 --date 2026-11-01
    python scripts/backfill_first_received_date.py --org 1 --date 2026-11-01 \
        --db meta/architecture.db --dry-run

幂等: 只更新 first_received_date IS NULL 且 qty_on_hand > 0 的行；
      二次执行更新 0 行。负数库存保持 NULL（D7）。
"""
import argparse
import sqlite3
import sys

BAL_TABLE = 'inventory_balances'
COLUMN = 'first_received_date'


def _columns(conn):
    return {row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % BAL_TABLE).fetchall()}


def backfill(db_path, org_id, received_date, dry_run=False):
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        if COLUMN not in _columns(conn):
            print('  - [FAIL] %s.%s 不存在，请先执行迁移 v224'
                  % (BAL_TABLE, COLUMN))
            return -1
        where = ('org_id = ? AND qty_on_hand > 0 AND %s IS NULL'
                 % COLUMN)
        count = conn.execute(
            'SELECT COUNT(*) FROM %s WHERE %s' % (BAL_TABLE, where),
            [org_id]).fetchone()[0]
        print('  - [FOUND] org=%s 待回填余额行 %s 条' % (org_id, count))
        if dry_run:
            print('  - [DRY-RUN] 未写入')
            return count
        cursor = conn.execute(
            'UPDATE %s SET %s = ? WHERE %s'
            % (BAL_TABLE, COLUMN, where),
            [received_date, org_id])
        conn.commit()
        print('  - [UPDATE] 已写入 %s 条（%s = %s）'
              % (cursor.rowcount, COLUMN, received_date))
        return cursor.rowcount
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='期初库存入库日期回填（一次性脚本，幂等）')
    parser.add_argument('--org', type=int, required=True,
                        help='库存组织 ID')
    parser.add_argument('--date', required=True,
                        help='期初上线日 YYYY-MM-DD')
    parser.add_argument('--db', default='meta/architecture.db',
                        help='SQLite 库路径')
    parser.add_argument('--dry-run', action='store_true',
                        help='只统计不写入')
    args = parser.parse_args(argv)
    text = str(args.date)[:10]
    try:
        from datetime import datetime
        datetime.strptime(text, '%Y-%m-%d')
    except ValueError:
        print('  - [FAIL] --date 格式非法，应为 YYYY-MM-DD: %s' % args.date)
        return 2
    print('[backfill_first_received_date] org=%s date=%s'
          % (args.org, text))
    updated = backfill(args.db, args.org, text, dry_run=args.dry_run)
    return 0 if updated >= 0 else 1


if __name__ == '__main__':
    sys.exit(main())
