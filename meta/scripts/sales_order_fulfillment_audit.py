#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[MODULE] sales_order_fulfillment_audit — 履约状态一致性巡检 / 幂等重算 CLI

依据: docs/superpowers/specs/2026-10-28-sales-order-fulfillment-status-writeback-spec.md
      §4.9 一致性保障 (巡检 SQL + 幂等重算) / FR-007 / FR-008

用法:
    python meta/scripts/sales_order_fulfillment_audit.py            # 巡检（只读）
    python meta/scripts/sales_order_fulfillment_audit.py --repair   # 巡检 + 全量重算修复
    python meta/scripts/sales_order_fulfillment_audit.py --order 123 --repair  # 单订单

退出码:
    0  一致，或 --repair 已执行（修复后无残余漂移）
    1  巡检发现漂移（--check 模式下用于 CI 门禁）
    2  修复后仍有残余漂移
"""
import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _print_report(report):
    scanned = report['scanned']
    print('[巡检] 扫描订单 %d 个 / 订单行 %d 条'
          % (scanned['orders'], scanned['lines']))
    for item in report['lines']:
        print('[DRIFT] 行 %s（订单 %s）: 库中 %s，应为 %s'
              % (item['line_id'], item['order_id'],
                 item['stored'], item['expected']))
    for item in report['orders']:
        print('[DRIFT] 抬头 %s: 库中 %s，应为 %s'
              % (item['order_id'], item['stored'], item['expected']))
    stale = report.get('stale') or {'lines': [], 'orders': []}
    for item in stale['lines']:
        print('[STALE] 行 %s（订单 %s）: 派生确认于 %s，其后有变更 %s'
              % (item['line_id'], item['order_id'],
                 item['derived_at'], item['changed_at']))
    for item in stale['orders']:
        print('[STALE] 抬头 %s: 派生确认于 %s，其后有变更 %s'
              % (item['order_id'], item['derived_at'], item['changed_at']))
    drift_total = len(report['lines']) + len(report['orders'])
    stale_total = len(stale['lines']) + len(stale['orders'])
    print('[巡检] 不一致 %d 处（行 %d / 抬头 %d）；陈旧 %d 处（行 %d / 抬头 %d）'
          % (drift_total, len(report['lines']), len(report['orders']),
             stale_total, len(stale['lines']), len(stale['orders'])))
    return drift_total + stale_total


def _has_drift(report):
    stale = report.get('stale') or {'lines': [], 'orders': []}
    return bool(report['lines'] or report['orders']
                or stale['lines'] or stale['orders'])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='销售订单履约状态一致性巡检 / 幂等重算')
    parser.add_argument('--repair', action='store_true',
                        help='巡检后用 recompute 修复（幂等，可重复执行）')
    parser.add_argument('--order', type=int, default=None,
                        help='只处理和巡检指定订单 id')
    parser.add_argument('--batch-size', type=int, default=500,
                        help='全量巡检/重算的分页大小（默认 500）')
    args = parser.parse_args(argv)

    from meta.core.datasource import get_data_source
    from meta.tests.test_utils import get_meta_db_path
    from meta.services.sales_order_fulfillment_service import (
        SalesOrderFulfillmentService,
    )

    ds = get_data_source('sqlite', database=str(get_meta_db_path()))
    service = SalesOrderFulfillmentService(ds)

    report = service.check_drift(order_id=args.order,
                                 batch_size=args.batch_size)
    drift = _print_report(report)
    if not args.repair:
        return 1 if drift else 0

    if not drift:
        print('[修复] 无需修复')
        return 0

    if args.order is not None:
        service.recompute_order(args.order)
        after = service.check_drift(order_id=args.order,
                                    batch_size=args.batch_size)
    else:
        stats = service.recompute_all(batch_size=args.batch_size)
        print('[修复] 重算订单 %d 个，写行 %d 条，写抬头 %d 个'
              % (stats['orders'], stats['lines_written'],
                 stats['orders_written']))
        after = service.check_drift(batch_size=args.batch_size)

    remaining = _print_report(after)
    return 0 if not remaining else 2


if __name__ == '__main__':
    raise SystemExit(main())
