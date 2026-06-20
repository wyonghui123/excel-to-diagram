# -*- coding: utf-8 -*-
"""
[P1+P2 综合验证] 检查 user_name 残留 + tx_id 覆盖率

用法:
    python scripts/verify_audit_fix.py
"""
import sqlite3
import sys
from datetime import datetime, timedelta


DB = "meta/architecture.db"
TWO_DAYS = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")


def check_p1_residual(c) -> int:
    """P1: 检查 user_name 残留 'xxx (yyy)' 格式"""
    c.execute("SELECT COUNT(*) FROM audit_logs WHERE user_name LIKE '%(%'")
    return c.fetchone()[0]


def check_p2_coverage(c, days: int = 2) -> tuple:
    """P2: tx_id 覆盖率 (排除 system 用户)"""
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            """
            SELECT COUNT(*), SUM(CASE WHEN transaction_id IS NOT NULL AND transaction_id != '' THEN 1 ELSE 0 END)
            FROM audit_logs WHERE created_at >= ? AND (user_name IS NULL OR user_name != 'system')
            """,
            (cutoff,),
        )
    else:
        c.execute(
            """
            SELECT COUNT(*), SUM(CASE WHEN transaction_id IS NOT NULL AND transaction_id != '' THEN 1 ELSE 0 END)
            FROM audit_logs WHERE (user_name IS NULL OR user_name != 'system')
            """
        )
    return c.fetchone()


def check_recent_users(c, days: int = 2) -> dict:
    """最近 N 天的 user_name 分布"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        """
        SELECT user_name, COUNT(*) FROM audit_logs
        WHERE created_at >= ? GROUP BY user_name ORDER BY 2 DESC
        """,
        (cutoff,),
    )
    return {row[0]: row[1] for row in c.fetchall()}


def main():
    print("=" * 60)
    print("审计日志修复验证 (P1 + P2)")
    print("=" * 60)

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # P1: 残留检查
    print("\n=== P1: user_name 'xxx (yyy)' 残留检查 ===")
    p1_residual = check_p1_residual(c)
    p1_status = "PASS" if p1_residual == 0 else "FAIL"
    print(f"  COUNT(*) user_name LIKE '%(%' = {p1_residual}")
    print(f"  Status: {p1_status}")

    # P2: 覆盖率检查 (近 2 天)
    print("\n=== P2: tx_id 覆盖率 (近 2 天, 非 system) ===")
    total_2d, with_tx_2d = check_p2_coverage(c, days=2)
    coverage_2d = (with_tx_2d * 100 / total_2d) if total_2d else 0
    print(f"  total={total_2d}  with_tx={with_tx_2d}  coverage={coverage_2d:.1f}%")

    # P2: 全表覆盖率
    print("\n=== P2: tx_id 全表覆盖率 (非 system) ===")
    total_all, with_tx_all = check_p2_coverage(c, days=None)
    coverage_all = (with_tx_all * 100 / total_all) if total_all else 0
    print(f"  total={total_all}  with_tx={with_tx_all}  coverage={coverage_all:.1f}%")

    # user_name 分布
    print("\n=== 最近 2 天 user_name 分布 ===")
    users = check_recent_users(c, days=2)
    for name, count in users.items():
        flag = " [LEAK]" if name and "(" in name else ""
        print(f"  {name!r:30} {count:>5}{flag}")

    # 总评
    print("\n" + "=" * 60)
    print("完成标准检查")
    print("=" * 60)
    p1_ok = p1_residual == 0
    p2_2d_ok = coverage_2d >= 95
    p2_all_ok = coverage_all >= 90
    print(f"  [P1] user_name 残留 = 0:              {'PASS' if p1_ok else 'FAIL'}")
    print(f"  [P2-2d] tx_id 覆盖率 >= 95%:         {'PASS' if p2_2d_ok else 'WARN'} ({coverage_2d:.1f}%)")
    print(f"  [P2-all] tx_id 全表覆盖率 >= 90%:    {'PASS' if p2_all_ok else 'WARN'} ({coverage_all:.1f}%)")
    overall = "PASS" if (p1_ok and p2_2d_ok) else "PARTIAL"
    print(f"\n  Overall: {overall}")
    conn.close()
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())