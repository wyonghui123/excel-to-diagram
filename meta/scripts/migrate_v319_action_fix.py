#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_log.action 列修复迁移脚本 (v3.19 / 2026-07-22)

[FIX 2026-07-22] 修复 action 列混入性能指标 (架构混淆 bug)

问题:
  StructuredLogger.log_performance() 把 metric_name (api_response_time / db_query_time / time / METRIC)
  直接写入 action 列。action 应该是抽象业务动作 (CREATE/UPDATE/DELETE/...),
  metric_name 是指标维度, 二者语义不同。

修复:
  1. 将这些记录的 action 改为占位 'METRIC_RECORD'
  2. 原 metric_name 移到 extra_data.metric_name (如果不在的话)
  3. 记录数: 257 条 (257+20 ≈ 实测)

回滚: 见 --rollback
"""
import sqlite3
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime

# __file__ = meta/scripts/migrate_v319_action_fix.py
DB_PATH = Path(__file__).parent.parent / "architecture.db"

# 需要修复的 action 值 (这些都是 log_performance() 误写入的 metric_name)
BAD_ACTIONS = ['api_response_time', 'db_query_time', 'time', 'METRIC']

# 修复目标: action='METRIC_RECORD' 占位
FIXED_ACTION = 'METRIC_RECORD'


def has_column(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())


def count_bad_records(conn):
    """统计需要修复的记录数"""
    placeholders = ','.join('?' * len(BAD_ACTIONS))
    cur = conn.execute(
        f"SELECT COUNT(*) FROM audit_logs WHERE action IN ({placeholders})",
        BAD_ACTIONS
    )
    return cur.fetchone()[0]


def fix_records(apply: bool):
    """修复被污染的记录

    策略:
    1. SELECT 所有需要修复的记录 (含 extra_data JSON)
    2. 对每条记录:
       - 把原 action 值保存到 extra_data.metric_name (如果 extra_data 已有 metric_name 则跳过)
       - 把 action 改为 'METRIC_RECORD'
    3. 批量 UPDATE
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        placeholders = ','.join('?' * len(BAD_ACTIONS))
        rows = conn.execute(
            f"SELECT id, action, extra_data FROM audit_logs WHERE action IN ({placeholders})",
            BAD_ACTIONS
        ).fetchall()

        if not rows:
            print(f"  [INFO] 没有需要修复的记录")
            return

        print(f"  [INFO] 发现 {len(rows)} 条需要修复的记录")
        # 按原 action 分组
        by_action = {}
        for row in rows:
            by_action.setdefault(row[1], []).append(row[0])
        for old_action, ids in by_action.items():
            print(f"         {old_action:25} → METRIC_RECORD ({len(ids)} 条)")

        if not apply:
            print(f"\n  [DRY-RUN] --apply 后会真正执行")
            return

        # 修复每条记录
        fixed = 0
        skipped = 0
        for row_id, old_action, extra_data_str in rows:
            try:
                extra_data = json.loads(extra_data_str) if extra_data_str else {}
            except (json.JSONDecodeError, TypeError):
                extra_data = {}

            # 把原 action 值移到 metric_name (如果还没有的话)
            if 'metric_name' not in extra_data:
                extra_data['metric_name'] = old_action
                # 同时打个迁移标记
                extra_data['_migration_note'] = 'v319: action 列修复，metric_name 从 action 移入'
                new_extra = json.dumps(extra_data, ensure_ascii=False, default=str)
                conn.execute(
                    "UPDATE audit_logs SET action=?, extra_data=? WHERE id=?",
                    (FIXED_ACTION, new_extra, row_id)
                )
                fixed += 1
            else:
                # 已经有过 metric_name, 直接改 action
                conn.execute(
                    "UPDATE audit_logs SET action=? WHERE id=?",
                    (FIXED_ACTION, row_id)
                )
                fixed += 1

        # 登记到 schema_migrations
        try:
            cur = conn.execute(
                "SELECT id FROM schema_migrations WHERE migration_name=?",
                ("migrate_v319_action_fix.py",)
            )
            if cur.fetchone() is None:
                conn.execute(
                    "INSERT INTO schema_migrations (migration_name, executed_at) VALUES (?, ?)",
                    ("migrate_v319_action_fix.py", datetime.now().isoformat())
                )
                print(f"  [SCHEMA_MIGRATIONS] 记录已添加")
        except Exception as e:
            print(f"  [SCHEMA_MIGRATIONS] 跳过: {e}")

        conn.commit()
        print(f"\n  [FIXED] {fixed} 条已修复")

        # 验证
        remaining = count_bad_records(conn)
        print(f"  [VERIFY] 剩余污染记录: {remaining}")
        print(f"\n{'='*50}\n  {'APPLIED' if apply else 'DRY-RUN'} (no errors)\n{'='*50}")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] {e}")
        raise
    finally:
        conn.close()


def rollback(apply: bool):
    """回滚: 把 action='METRIC_RECORD' 的记录恢复为 extra_data.metric_name 原值"""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        rows = conn.execute(
            "SELECT id, extra_data FROM audit_logs WHERE action=?",
            (FIXED_ACTION,)
        ).fetchall()

        if not rows:
            print(f"  [INFO] 没有 METRIC_RECORD 记录，无需回滚")
            return

        print(f"  [INFO] 发现 {len(rows)} 条 METRIC_RECORD 记录")

        if not apply:
            print(f"  [DRY-RUN] --apply 后会真正回滚")
            return

        restored = 0
        for row_id, extra_data_str in rows:
            try:
                extra_data = json.loads(extra_data_str) if extra_data_str else {}
                original = extra_data.get('metric_name')
                if original and original in BAD_ACTIONS:
                    # 清理迁移标记
                    extra_data.pop('_migration_note', None)
                    new_extra = json.dumps(extra_data, ensure_ascii=False, default=str)
                    conn.execute(
                        "UPDATE audit_logs SET action=?, extra_data=? WHERE id=?",
                        (original, new_extra, row_id)
                    )
                    restored += 1
                else:
                    print(f"  [WARN] id={row_id} 的 metric_name={original!r} 不在 BAD_ACTIONS，跳过")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"  [WARN] id={row_id} extra_data 解析失败: {e}")

        # 删除 schema_migrations 记录
        try:
            conn.execute(
                "DELETE FROM schema_migrations WHERE migration_name=?",
                ("migrate_v319_action_fix.py",)
            )
        except Exception:
            pass

        conn.commit()
        print(f"\n  [RESTORED] {restored} 条已恢复")
        print(f"\n{'='*50}\n  {'ROLLED BACK' if apply else 'DRY-RUN'}\n{'='*50}")
    finally:
        conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="真改 (默认 dry-run)")
    p.add_argument("--rollback", action="store_true", help="回滚")
    args = p.parse_args()

    print(f"DB: {DB_PATH}")
    print(f"BAD_ACTIONS: {BAD_ACTIONS}")
    print(f"FIXED_ACTION: {FIXED_ACTION}")
    print()
    if args.rollback:
        rollback(args.apply)
    else:
        fix_records(args.apply)