# -*- coding: utf-8 -*-
"""[F1] 任务 hold 一致性巡检 + 派生态视图重建 —— 触发式运维脚本

契约: task-model spec §12 F1 / §12.1 Q3（hold 事件化 + 当前态派生视图，
      同形态兄弟巡检域）；巡检/重建逻辑见 meta/core/task_hold.py。
      与 E7（meta/tools/doc_flow_reconcile.py）契约同形，但**入参是平台库**
      （事件账 task_events 所在库），故独立成工具、不并入 E7。

用法（repo 根目录）::

    python -m meta.tools.task_hold_reconcile --db <平台库路径>
    python -m meta.tools.task_hold_reconcile --db data/platform.db --json
    python -m meta.tools.task_hold_reconcile --db data/platform.db --rebuild
    python -m meta.tools.task_hold_reconcile --db data/platform.db --strict

说明:
- 默认**只读**巡检；--rebuild 显式重建派生态视图（**绝不改事件数据**，
  append-only 铁律），重建后再复检一次并输出前后对照。
- --strict：存在 **error 级** findings 时退出码 1（CI / 运维告警用）。
- 重建失败（fail-loud）退出码恒为 1。
- 异常（库不可读 / 被锁 / 半迁移）：[ERROR] 一行 + 退出码 2（不抛裸栈）；
  --db 指向不存在的文件同样 exit 2（不静默新建空库）。
"""
import argparse
import json
import os
import sys
from typing import List, Optional

from meta.core.datasource import get_data_source
from meta.core.task_hold import (
    HoldRebuildResult, HoldReport, hold_findings, rebuild_hold_view,
)


def _print_report(report: HoldReport, indent: str = "") -> None:
    if report.ok:
        print("{0}[OK] 无发现".format(indent))
        return
    for f in report.findings:
        print("{0}[{1}] {2} — {3}".format(
            indent, f.severity.upper(), f.code, f.detail))


def _print_human(db: str, report: HoldReport,
                 rebuild: Optional[HoldRebuildResult],
                 report_after: Optional[HoldReport]) -> None:
    print("=== 任务 hold 一致性巡检（F1）===")
    print("库: {0}".format(db))
    print("hold 事件总数: {0}（激活: {1}）".format(
        report.hold_event_count, report.active_hold_count))
    _print_report(report)

    if rebuild is None:
        return
    print("--- 派生态视图重建（显式触发） ---")
    print("视图重建: {0}（重建前视图{1}）".format(
        "OK" if rebuild.view_rebuilt else "未达规范形态",
        "存在" if rebuild.view_existed else "缺失",
    ))
    if rebuild.error:
        print("[REBUILD-FAILED] {0}".format(rebuild.error))
    print("重建后复检:")
    _print_report(report_after, indent="  ")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="任务 hold 一致性巡检 + 派生态视图重建（F1，触发式）")
    parser.add_argument("--db", required=True, help="平台库文件路径")
    parser.add_argument("--json", action="store_true", help="输出机读 JSON")
    parser.add_argument("--strict", action="store_true",
                        help="存在 error 级 findings 时退出码 1")
    parser.add_argument("--rebuild", action="store_true",
                        help="显式重建派生态视图（绝不改事件数据）")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.db):
        # 防 SQLite 连接时静默新建空库 → 误报 HOLD_EVENT_TABLE_MISSING
        print("[ERROR] 库文件不存在: {0}".format(args.db))
        return 2

    try:
        ds = get_data_source("sqlite", database=args.db)
        report = hold_findings(ds)
        rebuild = rebuild_hold_view(ds) if args.rebuild else None
        report_after = hold_findings(ds) if args.rebuild else None
    except Exception as e:  # noqa: BLE001 - 库不可读/被锁/半迁移：异常兜底
        print("[ERROR] 巡检失败: {0}".format(e))
        return 2

    if args.json:
        payload = {
            "db": args.db,
            "report": report.to_dict(),
            "rebuild": rebuild.to_dict() if rebuild else None,
            "report_after_rebuild": (
                report_after.to_dict() if report_after else None),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(args.db, report, rebuild, report_after)

    if rebuild is not None and not rebuild.ok:
        return 1
    if args.strict and not report.ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())