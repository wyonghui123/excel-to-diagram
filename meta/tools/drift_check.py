# -*- coding: utf-8 -*-
"""
Schema drift 检查工具 - 对比本地 yaml 与本地/远端 DB schema

[v0.1 2026-09-22 PoC C 实证]
基于 meta.core.schema_generator.SchemaComparator 的封装,产出机读 drift 报告。

用法:
    python -m meta.tools.drift_check                          # 默认 sqlite local DB
    python -m meta.tools.drift_check --source sqlite --local data/app.db
    python -m meta.tools.drift_check --json .drift_report.json   # 输出 JSON
    python -m meta.tools.drift_check --strict                    # 严格模式 (任何 drift 即 exit 1)
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta import registry, get_meta_object
from meta.core.schema_generator import SchemaComparator
from meta.core.datasource import get_data_source


DRIFT_REPORT_FILE = "meta/schemas/.drift_report.json"


def check_all_objects(strict_mode: bool = False) -> Dict[str, Any]:
    """对所有 yaml 对象做 drift 检测"""
    if not registry.list_objects():
        register_from_directory(get_yaml_schema_dir())

    ds = get_data_source("sqlite", database="meta/architecture.db")
    comparator = SchemaComparator(ds)

    reports = []
    drift_count = 0
    for obj_id in registry.list_objects():
        obj = get_meta_object(obj_id)
        if not obj:
            continue
        # 跳过 VIRTUAL 对象(无表)
        if not obj.table_name:
            continue

        report = comparator.compare(obj)
        reports.append(report)
        if not report["exists"] or report["missing_columns"] or report["extra_columns"]:
            drift_count += 1

    return {
        "source": "sqlite",
        "local_db": "meta/architecture.db",
        "yaml_objects_scanned": len(reports),
        "yaml_objects_with_drift": drift_count,
        "reports": reports,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }


def print_summary(drift: Dict[str, Any]):
    print(f"=== Schema drift 检测 ===")
    print(f"yaml 对象: {drift['yaml_objects_scanned']}")
    print(f"含 drift: {drift['yaml_objects_with_drift']}")
    print()

    if drift["yaml_objects_with_drift"] == 0:
        print("[OK] 无 drift, schema 与 yaml 一致")
        return

    print(f"[FAIL] 发现 {drift['yaml_objects_with_drift']} 个对象的 drift:")
    for r in drift["reports"]:
        if not r["exists"] or r["missing_columns"] or r["extra_columns"]:
            print(f"\n  - {r['object_id']} ({r['table_name']})")
            if not r["exists"]:
                print(f"    表不存在")
            if r["missing_columns"]:
                print(f"    缺失列: {r['missing_columns']}")
            if r["extra_columns"]:
                print(f"    多余列: {r['extra_columns']}")


def save_report(drift: Dict[str, Any], path: str = DRIFT_REPORT_FILE):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(drift, f, indent=2, ensure_ascii=False)
    print(f"[WRITE] {out_path} size={os.path.getsize(out_path)} bytes")


def main():
    parser = argparse.ArgumentParser(description="Schema drift 检查工具")
    parser.add_argument("--source", default="sqlite", help="数据源 (sqlite/mysql/postgresql)")
    parser.add_argument("--local", default="data/app.db", help="SQLite 本地路径")
    parser.add_argument("--json", default=DRIFT_REPORT_FILE, help="输出 JSON 路径")
    parser.add_argument("--strict", action="store_true", help="严格模式 (任何 drift 即 exit 1)")
    args = parser.parse_args()

    try:
        drift = check_all_objects()
    except Exception as e:
        print(f"[ERROR] drift check 失败: {e}")
        sys.exit(2)

    print_summary(drift)
    save_report(drift, args.json)

    if args.strict and drift["yaml_objects_with_drift"] > 0:
        sys.exit(1)
    if drift["yaml_objects_with_drift"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()