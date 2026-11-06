# -*- coding: utf-8 -*-
"""[P2 2026-11-06] 冗余字段一致性审计工具（P1-5 / P2 声明的运行入口）。

只读：比对缓存列与声明真源（1:1 JOIN 或明细聚合），不做修复、不改写数据。

用法:
    python -m meta.tools.redundancy_audit
    python -m meta.tools.redundancy_audit --database meta/architecture.db
    python -m meta.tools.redundancy_audit --object purchase_order,receipt_line
    python -m meta.tools.redundancy_audit --json meta/schemas/.redundancy_report.json
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from meta import registry
from meta.core.consistency_guard import RedundancyAuditor
from meta.core.datasource import get_data_source
from meta.core.redundancy_registry import RedundancyType, redundancy_registry
from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

REPORT_FILE = "meta/schemas/.redundancy_report.json"


def _ensure_registry():
    if not registry.list_objects():
        register_from_directory(get_yaml_schema_dir())


def audit_all(
    database: str = "meta/architecture.db",
    object_ids: Optional[List[str]] = None,
    ds=None,
) -> Dict[str, Any]:
    """审计所有（或指定）对象的 stored 冗余声明，返回机读报告。"""
    _ensure_registry()
    redundancy_registry.build_from_registry()

    if ds is None:
        ds = get_data_source("sqlite", database=database)

    auditor = RedundancyAuditor(ds, redundancy_registry)
    targets = object_ids or list(registry.list_objects())

    scanned = 0
    violations: List[Dict[str, Any]] = []
    for obj_id in targets:
        stored_defs = {
            field_id: red for field_id, red in
            redundancy_registry.get_object_redundancies(obj_id).items()
            if red.redundancy_type == RedundancyType.STORED
        }
        if not stored_defs:
            continue

        scanned += 1
        for v in auditor.validate_object(obj_id):
            violations.append({
                "object_type": v.object_type,
                "record_id": v.record_id,
                "field_id": v.field_id,
                "expected_value": v.expected_value,
                "actual_value": v.actual_value,
                "severity": v.severity,
            })

    return {
        "database": database,
        "objects_with_stored_redundancy": scanned,
        "violation_count": len(violations),
        "violations": violations,
        "timestamp": datetime.now().isoformat(),
    }


def print_summary(report: Dict[str, Any]):
    print("=== 冗余一致性审计 ===")
    print("database: %s" % report["database"])
    print("扫描对象: %d" % report["objects_with_stored_redundancy"])
    print("违规记录: %d" % report["violation_count"])
    print()

    if report["violation_count"] == 0:
        print("[OK] 缓存列与声明真源一致")
        return

    for v in report["violations"]:
        print("  - %s#%s.%s: actual=%s expected=%s [%s]" % (
            v["object_type"], v["record_id"], v["field_id"],
            v["actual_value"], v["expected_value"], v["severity"]))


def save_report(report: Dict[str, Any], path: str = REPORT_FILE):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("[WRITE] %s" % out_path)


def main():
    parser = argparse.ArgumentParser(description="冗余字段一致性审计工具（只读）")
    parser.add_argument("--database", default="meta/architecture.db",
                        help="SQLite 数据库路径")
    parser.add_argument("--object", default="",
                        help="只审计指定对象，逗号分隔（默认全部）")
    parser.add_argument("--json", default=REPORT_FILE, help="输出 JSON 路径")
    args = parser.parse_args()

    object_ids = [s.strip() for s in args.object.split(",") if s.strip()]

    try:
        report = audit_all(args.database, object_ids or None)
    except Exception as e:  # noqa: BLE001 - CLI 统一出口
        print("[ERROR] 冗余审计失败: %s" % e)
        sys.exit(2)

    print_summary(report)
    save_report(report, args.json)

    if report["violation_count"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
