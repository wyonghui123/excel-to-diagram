#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[P1.3] 修复 audit_logs.user_name 中残留的 "Admin (admin)" 格式

[P1 2026-06-20] D.2 v4 数据修复脚本
- 业务人员之前看到 "Admin (admin)" 不理解
- 现在统一只用 display_name (修复在 action_executor.py:2265 + action_handlers.py:228 + _audit_helper.py:42)
- 本脚本清理历史残留

用法:
    python scripts/fix_audit_admin_parentheses.py
    python scripts/fix_audit_admin_parentheses.py --dry-run  # 只显示不修改
"""
import argparse
import re
import sqlite3
import sys


def fix_user_name_parentheses(db_path: str, dry_run: bool = False) -> int:
    """修复 'Display (username)' 格式 → 'Display'

    Returns:
        修复的记录数
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 找出所有 "xxx (yyy)" 格式
    pattern = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")
    c.execute(
        "SELECT id, user_name FROM audit_logs "
        "WHERE user_name LIKE '%(%' AND user_name LIKE '%)%'"
    )
    rows = c.fetchall()

    fixed = 0
    for log_id, old_name in rows:
        if not old_name:
            continue
        m = pattern.match(old_name)
        if not m:
            continue
        display = m.group(1).strip()
        username = m.group(2).strip()
        # 只在 display 和 username 不同且都不为空时修复
        if display and username and display != username:
            new_name = display
            if dry_run:
                print(f"  [DRY] id={log_id}: {old_name!r} -> {new_name!r}")
            else:
                c.execute(
                    "UPDATE audit_logs SET user_name = ? WHERE id = ?",
                    (new_name, log_id),
                )
                print(f"  [FIX] id={log_id}: {old_name!r} -> {new_name!r}")
            fixed += 1

    if not dry_run:
        conn.commit()
    print(f"\n[DONE] {'Would fix' if dry_run else 'Fixed'} {fixed}/{len(rows)} records")
    conn.close()
    return fixed


def main():
    parser = argparse.ArgumentParser(description="修复 audit_logs.user_name 残留括号格式")
    parser.add_argument(
        "--db", default="meta/architecture.db", help="DB 路径 (默认 meta/architecture.db)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只显示不修改"
    )
    args = parser.parse_args()

    return fix_user_name_parentheses(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())