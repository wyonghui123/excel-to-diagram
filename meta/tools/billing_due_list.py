# -*- coding: utf-8 -*-
"""开票计划到期清单 —— S8 Wave B 只读工具。

依据: docs/specs/s8-customer-invoice-wave-b/spec.md §7.1。

语义:
  · 列出 `sales_order_schedules` 中 kind=billing、状态可开票、尚未开满、
    承诺日期已到（含当天）、且订单状态可开票的期次；
  · 期金额与剩余金额按 `ROUND(billing_percent / 100 * order_line.net_amount, 4)`
    计算，与服务层口径一致；
  · `--as-of` 默认今天，可指定任意日期做回溯/预警。

用法（repo 根目录）::

    python -m meta.tools.billing_due_list --db meta/architecture.db
    python -m meta.tools.billing_due_list --db data/warehouse.db --as-of 2026-12-01 --json

退出码: 0 = 无到期期次；2 = 有到期期次（便于脚本判断）；1 = 运行错误。
全程只读：以 sqlite3 URI `mode=ro` 打开，任何写操作都会被 SQLite 拒绝。
"""
import argparse
import datetime
import json
import os
import sqlite3
import sys
from typing import Dict, List, Optional

_SQL_DUE = """
SELECT o.order_no,
       ol.line_no,
       s.id AS schedule_id,
       s.schedule_no,
       s.promised_date,
       s.billing_percent,
       ol.net_amount,
       ROUND(s.billing_percent / 100.0 * ol.net_amount, 4) AS period_amount,
       s.billed_amount,
       ROUND(s.billing_percent / 100.0 * ol.net_amount, 4) - s.billed_amount
           AS remaining,
       s.billing_status
  FROM sales_order_schedules s
  JOIN sales_order_lines ol ON ol.id = s.line_id
  JOIN sales_orders o       ON o.id = ol.order_id
 WHERE s.schedule_kind = 'billing'
   AND s.status IN ('planned', 'confirmed')
   AND s.billing_status <> 'full'
   AND ol.billing_relevance = 'plan'
   AND s.promised_date IS NOT NULL
   AND s.promised_date <= ?
   AND o.status IN ('confirmed', 'closed')
 ORDER BY s.promised_date, o.order_no, s.schedule_no
"""


def _connect_readonly(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        raise FileNotFoundError("库文件不存在: {0}".format(db_path))
    uri = "file:{0}?mode=ro".format(db_path.replace("\\", "/"))
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def query_due(db_path: str, as_of: Optional[str] = None) -> List[Dict[str, object]]:
    """返回到期期次；表缺失时抛 sqlite3.OperationalError。"""
    as_of = as_of or datetime.date.today().strftime('%Y-%m-%d')
    conn = _connect_readonly(db_path)
    try:
        rows = conn.execute(_SQL_DUE, [as_of]).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="开票计划到期清单（S8 Wave B，只读）")
    parser.add_argument("--db", required=True, help="应用库文件路径")
    parser.add_argument("--as-of", dest="as_of", default=None,
                        help="到期基准日 YYYY-MM-DD（默认今天）")
    parser.add_argument("--json", action="store_true", help="输出机读 JSON")
    args = parser.parse_args(argv)

    try:
        rows = query_due(args.db, args.as_of)
    except (FileNotFoundError, sqlite3.Error) as error:
        print("[ERROR] {0}".format(error))
        return 1

    if args.json:
        print(json.dumps({"as_of": args.as_of or
                          datetime.date.today().strftime('%Y-%m-%d'),
                          "total": len(rows), "items": rows},
                         ensure_ascii=False, indent=2, default=str))
    else:
        print("=== 开票计划到期清单（S8 Wave B）===")
        print("库: {0}  基准日: {1}".format(
            args.db, args.as_of or datetime.date.today().strftime('%Y-%m-%d')))
        if not rows:
            print("[OK] 无到期期次")
        for row in rows:
            print("  {0}".format(json.dumps(row, ensure_ascii=False,
                                            default=str)))
    return 2 if rows else 0


if __name__ == "__main__":
    sys.exit(main())