# -*- coding: utf-8 -*-
"""
[P2.3] 给存量 audit_logs 补充 transaction_id

[P2 2026-06-20] 数据回填脚本
- 业务侧: 当前 tx_id 覆盖率仅 7.1%, 业务人员无法按"这次保存做了什么"追踪
- 已修复: audit_interceptor.py auto-gen tx_id (新增路径)
- 本脚本: 给存量 2992 条无 tx_id 的非 system 记录启发式回填

策略: 同 user + ip + 2 秒窗口 → 归到同一事务
不修改: system 用户 (seed/migration 脚本无业务事务)

用法:
    python scripts/backfill_audit_transaction_id.py
    python scripts/backfill_audit_transaction_id.py --dry-run
"""
import argparse
import sqlite3
import sys
import uuid
from datetime import datetime


WINDOW_MS = 2000  # 2 秒窗口


def parse_iso(ts: str):
    """解析 ISO 时间戳, 容忍 Z 后缀"""
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def backfill_tx_id(db_path: str, dry_run: bool = False) -> int:
    """启发式回填 transaction_id

    Returns:
        回填的记录数
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 仅处理非 system 用户的无 tx_id 记录
    c.execute(
        """
        SELECT id, created_at, user_name, ip_address, action, object_type
        FROM audit_logs
        WHERE (transaction_id IS NULL OR transaction_id = '')
          AND (user_name IS NULL OR user_name != 'system')
        ORDER BY created_at ASC
        """
    )
    rows = c.fetchall()
    print(f"[INFO] Found {len(rows)} records to backfill (excluding system)")

    fixed = 0
    last_tx_per_group = {}  # (user, ip) -> (tx_id, timestamp)

    for log_id, created_at, user_name, ip, action, obj_type in rows:
        t = parse_iso(created_at)
        if not t:
            continue

        group_key = (user_name or "", ip or "")
        if group_key in last_tx_per_group:
            last_tx, last_t = last_tx_per_group[group_key]
            if abs((t - last_t).total_seconds() * 1000) < WINDOW_MS:
                if dry_run:
                    print(f"  [DRY] id={log_id}: merge into {last_tx}")
                else:
                    c.execute(
                        "UPDATE audit_logs SET transaction_id = ? WHERE id = ?",
                        (last_tx, log_id),
                    )
                fixed += 1
                continue

        new_tx = f"tx_{uuid.uuid4().hex[:16]}"
        if dry_run:
            print(f"  [DRY] id={log_id}: assign new tx {new_tx}")
        else:
            c.execute(
                "UPDATE audit_logs SET transaction_id = ? WHERE id = ?",
                (new_tx, log_id),
            )
        last_tx_per_group[group_key] = (new_tx, t)
        fixed += 1

    if not dry_run:
        conn.commit()
    print(f"\n[DONE] {'Would backfill' if dry_run else 'Backfilled'} {fixed}/{len(rows)} records")
    conn.close()
    return fixed


def main():
    parser = argparse.ArgumentParser(description="回填 audit_logs.transaction_id")
    parser.add_argument("--db", default="meta/architecture.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return backfill_tx_id(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())