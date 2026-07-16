"""audit_coverage_check.py - 审计日志覆盖率检测 [V007.64 2026-07-14]
[L13.4 自动检测 audit 缺口]

用法:
  python audit_coverage_check.py [--db /path/to/architecture.db] [--days 90] [--json]
"""
import sqlite3
import json
import sys
import argparse
from datetime import datetime, timedelta


# 关键表 + 期望审计覆盖率
CRITICAL_TABLES = {
    "roles": {"action": "DELETE", "expected_coverage": 1.0},
    "users": {"action": "DELETE", "expected_coverage": 1.0},
    "permissions": {"action": "*", "expected_coverage": 1.0},
    "role_permissions": {"action": "*", "expected_coverage": 1.0},
    "role_menu_permissions": {"action": "*", "expected_coverage": 0.9},
    "role_dimension_scopes": {"action": "*", "expected_coverage": 0.9},
    "business_object": {"action": "*", "expected_coverage": 0.8},
    "products": {"action": "DELETE", "expected_coverage": 0.9},
}


def check_coverage(db_path: str, lookback_days: int = 90) -> dict:
    """检查关键表的 audit 覆盖率

    Args:
        db_path: SQLite db 路径
        lookback_days: 只看最近 N 天

    Returns:
        {
            "lookback_days": int,
            "tables": {
                "<table>": {
                    "total": N,
                    "audited": M,
                    "coverage": float,
                    "expected": float,
                    "status": "ok|warn|fail",
                } or {"error": "..."}
            },
            "overall": {"ok": N, "warn": N, "fail": N},
        }
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cutoff_ts = int((datetime.now() - timedelta(days=lookback_days)).timestamp())

    report = {
        "lookback_days": lookback_days,
        "tables": {},
        "overall": {"ok": 0, "warn": 0, "fail": 0},
    }

    for table, cfg in CRITICAL_TABLES.items():
        # 检查表是否存在
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not cur.fetchone():
            report["tables"][table] = {"error": "table not exists"}
            continue

        # 总数 (updated_at 在 lookback 内)
        total = 0
        try:
            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE updated_at >= ?",
                (cutoff_ts,),
            )
            total = cur.fetchone()[0]
        except Exception:
            # 表可能没有 updated_at 列
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                total = cur.fetchone()[0]
            except Exception:
                total = 0

        # 审计数
        if cfg["action"] == "*":
            cur.execute(
                """
                SELECT COUNT(*) FROM audit_logs
                WHERE object_type = ? AND created_at >= ?
                """,
                (table, cutoff_ts),
            )
        else:
            cur.execute(
                """
                SELECT COUNT(*) FROM audit_logs
                WHERE object_type = ? AND action = ? AND created_at >= ?
                """,
                (table, cfg["action"], cutoff_ts),
            )
        audited = cur.fetchone()[0]

        coverage = (audited / total) if total > 0 else 1.0
        expected = cfg["expected_coverage"]
        if coverage >= expected:
            status = "ok"
        elif coverage >= expected * 0.5:
            status = "warn"
        else:
            status = "fail"
        report["overall"][status] += 1
        report["tables"][table] = {
            "total": total,
            "audited": audited,
            "coverage": round(coverage, 4),
            "expected": expected,
            "status": status,
        }

    conn.close()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default="/opt/app/deployments/meta/architecture.db",
        help="SQLite db path",
    )
    parser.add_argument("--days", type=int, default=90, help="Lookback days")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    if not __import__("os").path.exists(args.db):
        print(f"ERROR: db not found: {args.db}", file=sys.stderr)
        sys.exit(2)

    report = check_coverage(args.db, args.days)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\n=== Audit Coverage Report ({args.days} days) ===\n")
        for table, r in report["tables"].items():
            if "error" in r:
                print(f"  [X] {table}: {r['error']}")
                continue
            icons = {"ok": "[OK]", "warn": "[WARN]", "fail": "[X]"}
            print(
                f"  {icons[r['status']]} {table}: {r['audited']}/{r['total']} "
                f"({r['coverage'] * 100:.1f}% >= {r['expected'] * 100:.0f}%)"
            )
        ov = report["overall"]
        print(f"\n  ok: {ov['ok']}, warn: {ov['warn']}, fail: {ov['fail']}")

    if report["overall"]["fail"] > 0:
        sys.exit(1)
    if args.fail_on_warn and report["overall"]["warn"] > 0:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()