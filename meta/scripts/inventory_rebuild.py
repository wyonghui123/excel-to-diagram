#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""库存余额重建 / 对账 CLI —— INV-1 FR-012 / IF-004。

用法:
    python meta/scripts/inventory_rebuild.py                 # 全量差异报告（只读）
    python meta/scripts/inventory_rebuild.py --org 7         # 指定库存组织差异报告
    python meta/scripts/inventory_rebuild.py --apply         # 全量重建余额
    python meta/scripts/inventory_rebuild.py --org 7 --apply # 指定组织重建
    python meta/scripts/inventory_rebuild.py --json          # JSON 输出

退出码:
    0  无差异（或 --apply 重建成功）
    1  报告模式发现差异
    2  执行失败
"""

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _print_diff(report) -> None:
    print('[对账] 组织范围=%s 差异=%d 处'
          % (report.get('org_id') or 'ALL', report.get('diff_count', 0)))
    for row in report.get('rows') or []:
        print(
            '[DIFF] org=%s location=%s item=%s batch=%s status=%s '
            '账=%s 余额=%s 差额=%s%s%s'
            % (
                row['org_id'], row['location_id'], row['item_id'],
                row['batch_id'], row['stock_status'],
                row['account_qty'], row['balance_qty'], row['diff'],
                ' [缺余额行]' if row.get('missing_balance') else '',
                ' [孤儿余额]' if row.get('orphan_balance') else '',
            )
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='库存余额重建 / 对账（INV-1）')
    parser.add_argument('--org', type=int, default=None,
                        help='只处理指定库存组织 id')
    parser.add_argument('--apply', action='store_true',
                        help='按分录重建余额（默认只输出差异报告）')
    parser.add_argument('--json', action='store_true',
                        help='以 JSON 输出结果')
    parser.add_argument('--include-zero', action='store_true',
                        help='差异报告包含零差异行')
    args = parser.parse_args(argv)

    try:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        from meta.services.inventory_posting_service import (
            InventoryPostingService,
        )

        ds = get_data_source('sqlite', database=get_meta_db_path())
        service = InventoryPostingService(ds)
        if args.apply:
            result = service.rebuild_balances(org_id=args.org)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print('[重建] 组织范围=%s 重建余额 %d 行，合计 %s'
                      % (args.org or 'ALL', result['rows'],
                         result['total_qty']))
            return 0

        report = service.diff_report(org_id=args.org,
                                     include_zero=args.include_zero)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_diff(report)
        return 0 if report['ok'] else 1
    except Exception as exc:  # noqa: BLE001 - CLI 边界统一兜底
        print('[ERROR] %s' % exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
