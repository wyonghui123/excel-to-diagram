# -*- coding: utf-8 -*-
"""[单据流 E7] DOC_FLOW 一致性巡检 + 投影重建 —— 触发式运维脚本（S7 最小版）

契约: doc-flow spec §9.6 Phase 2 "S7 巡检最小版（触发式脚本）"；
      巡检/重建逻辑见 meta/core/doc_flow_reconcile.py（3 域：结构 / 边域 / 视图对账）。

用法（repo 根目录）::

    python -m meta.tools.doc_flow_reconcile --db <应用库路径>
    python -m meta.tools.doc_flow_reconcile --db data/warehouse.db --json
    python -m meta.tools.doc_flow_reconcile --db data/warehouse.db --rebuild
    python -m meta.tools.doc_flow_reconcile --db data/warehouse.db --strict

说明:
- 默认**只读**巡检；--rebuild 显式重建投影（视图 + 缺失索引，绝不改边数据），
  重建后再复检一次并输出前后对照。
- --strict：存在 findings 时退出码 1（CI / 运维告警用）。
- 重建失败（如重复键挡唯一索引，fail-loud）退出码恒为 1。
"""
import argparse
import json
import sys
from typing import List, Optional

from meta.core.datasource import get_data_source
from meta.core.doc_flow_reconcile import (
    RebuildResult, ReconcileReport, rebuild_projection, scan,
)


def _print_report(report: ReconcileReport, indent: str = "") -> None:
    if report.ok:
        print("{0}[OK] 无发现".format(indent))
        return
    for f in report.findings:
        print("{0}[{1}] {2} — {3}".format(
            indent, f.severity.upper(), f.code, f.detail))


def _print_human(db: str, report: ReconcileReport,
                 rebuild: Optional[RebuildResult],
                 report_after: Optional[ReconcileReport]) -> None:
    print("=== DOC_FLOW 一致性巡检（S7 最小版）===")
    print("库: {0}".format(db))
    print("边总数: {0}（active: {1}）".format(report.edge_count, report.active_count))
    _print_report(report)

    if rebuild is None:
        return
    print("--- 投影重建（显式触发） ---")
    print("视图重建: {0}（重建前视图{1}）".format(
        "OK" if rebuild.view_rebuilt else "未达规范形态",
        "存在" if rebuild.view_existed else "缺失",
    ))
    print("唯一索引: {0}".format(
        "OK" if rebuild.index_restored else "未恢复"))
    if rebuild.error:
        print("[REBUILD-FAILED] {0}".format(rebuild.error))
    print("重建后复检:")
    _print_report(report_after, indent="  ")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="DOC_FLOW 一致性巡检 + 投影重建（S7 最小版，触发式）")
    parser.add_argument("--db", required=True, help="应用库文件路径")
    parser.add_argument("--json", action="store_true", help="输出机读 JSON")
    parser.add_argument("--strict", action="store_true",
                        help="存在 findings 时退出码 1")
    parser.add_argument("--rebuild", action="store_true",
                        help="显式重建投影（视图 + 缺失索引；绝不改边数据）")
    args = parser.parse_args(argv)

    app_ds = get_data_source("sqlite", database=args.db)
    report = scan(app_ds)
    rebuild = rebuild_projection(app_ds) if args.rebuild else None
    report_after = scan(app_ds) if args.rebuild else None

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