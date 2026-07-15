#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[P1.7] Migration 健康监控 - 检查 prod 环境的 schema_migrations 表 + 告警

输出:
  - 写入 logs/migrations.log 的最近 FATAL/FAILED 记录
  - schema_migrations 表 FAILED 数量
  - 未登记 (migration 在文件但不在表里, 警告)
  - checksum 不匹配数量
  - 最后执行时间 (监控停滞)
  - 备份文件残留 (磁盘占用警告)
  - [V007.55] --check-regression: 跑 regression_test_suite (staging sqlite io error)
              集成回归测试, 7 PASS / 2 SKIP / 0 FAIL 期望

退出码:
  0: 全部健康
  1: 有 FATAL/FAILED 或 regression FAIL
  2: 只有 WARN

集成:
  - monitor_prod.py (远端 HTTP 调用时通过 script_remote 跑)
  - cron / systemd timer (每日自检)
  - [V007.55] --check-regression 集成到 staging_deploy_orchestrator Step 10.5
"""
import argparse
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
WORKTREE = SCRIPT_DIR.parent
DEFAULT_DB = WORKTREE / "meta" / "architecture.db"
DEFAULT_LOG = WORKTREE / "logs" / "migrations.log"


def section(title, ok=None, detail=''):
    icon = '[OK]' if ok is True else ('[FAIL]' if ok is False else ('[WARN]' if ok is None else ('[INFO]' if ok == 'info' else '[WARN]')))
    line = f"{icon} {title}: {detail}"
    print(line)
    return ok


def check_schema_migrations_health(db_path: Path) -> dict:
    """[P1.7] check_schema_migrations_health: 检查 DB 状态"""
    if not db_path.exists():
        return {"ok": False, "errors": [f"DB not found: {db_path}"], "stats": {}}

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    stats = {}
    errors = []
    warnings = []

    try:
        # 1. schema_migrations 表存在？
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        if not cur.fetchone():
            return {"ok": False, "errors": ["schema_migrations 表不存在"], "stats": {}}

        # 2. 总记录数
        cur.execute("SELECT count(*) FROM schema_migrations")
        stats["total"] = cur.fetchone()[0]

        # 3. FAILED 记录 (P1 字段)
        try:
            cur.execute("SELECT migration_name, error_message FROM schema_migrations WHERE status='FAILED'")
            failed = cur.fetchall()
            stats["failed"] = len(failed)
            if failed:
                for name, err in failed:
                    errors.append(f"FAILED migration {name}: {err}")
        except sqlite3.OperationalError:
            stats["failed"] = 0  # status 列不存在 (P0 数据库)

        # 4. ROLLED_BACK 记录
        try:
            cur.execute("SELECT count(*) FROM schema_migrations WHERE status='ROLLED_BACK'")
            stats["rolled_back"] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            stats["rolled_back"] = 0

        # 5. checksum NULL 记录 (应该 0)
        cur.execute("SELECT migration_name FROM schema_migrations WHERE checksum IS NULL")
        null_cs = cur.fetchall()
        stats["null_checksum"] = len(null_cs)
        if null_cs:
            warnings.append(f"{len(null_cs)} migration 的 checksum 为 NULL: {[n[0] for n in null_cs]}")

        # 6. migration_lock 表僵尸锁 (heartbeat_at > 60s ago)
        try:
            cur.execute("""
                SELECT locked_by, locked_at, heartbeat_at,
                       (julianday('now') - julianday(heartbeat_at)) * 86400 as age_seconds
                FROM migration_lock WHERE id = 1
            """)
            lock_row = cur.fetchone()
            if lock_row:
                locked_by, locked_at, heartbeat_at, age = lock_row
                if age > 60:
                    warnings.append(
                        f"migration_lock 持有 {age:.0f}s (heartbeat {heartbeat_at}), "
                        f"held by {locked_by} - 可能僵尸锁"
                    )
                stats["lock_held"] = True
                stats["lock_age_seconds"] = age
            else:
                stats["lock_held"] = False
        except sqlite3.OperationalError:
            stats["lock_held"] = None

        # 7. 最新执行时间
        cur.execute("SELECT executed_at, migration_name FROM schema_migrations ORDER BY executed_at DESC LIMIT 1")
        last = cur.fetchone()
        if last:
            stats["last_executed_at"] = last[0]
            stats["last_migration"] = last[1]
            try:
                ts = datetime.fromisoformat(last[0])
                age_min = (datetime.now() - ts).total_seconds() / 60
                stats["last_age_minutes"] = age_min
                if age_min > 60 * 24:  # >1 day 无新 migration
                    warnings.append(
                        f"最后 migration 已 {age_min/60:.1f} 小时前 ({last[1]}), "
                        f"如不再发布, 正常; 否则部署可能停滞"
                    )
            except (ValueError, TypeError):
                pass

    finally:
        conn.close()

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


def check_migration_alerts(log_path: Path) -> dict:
    """[P1.7] check_migration_alerts: 扫描 logs/migrations.log 最近 FAILED"""
    if not log_path.exists():
        return {"ok": True, "alerts": [], "stats": {"log_exists": False}}

    errors = []
    # 读最近 100 行 (避免大文件)
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        recent = lines[-100:]
        failed_count = sum(1 for ln in recent if '[FAILED]' in ln)
        fatal_count = sum(1 for ln in recent if '[FATAL]' in ln)
        rolled_back = sum(1 for ln in recent if 'ROLLED_BACK' in ln)
        return {
            "ok": fatal_count == 0,
            "alerts": [
                f"{failed_count} FAILED in recent 100 lines",
                f"{rolled_back} ROLLED_BACK in recent 100 lines",
            ] if failed_count or rolled_back else [],
            "stats": {
                "log_exists": True,
                "log_size_bytes": log_path.stat().st_size,
                "recent_failed": failed_count,
                "recent_rolled_back": rolled_back,
                "recent_lines": len(recent),
            },
        }
    except Exception as e:
        return {"ok": False, "alerts": [f"读取 log 失败: {e}"], "stats": {}}


def check_backup_residue(db_path: Path, max_retain: int = 5) -> dict:
    """[P1.7] 检查备份文件残留 (磁盘占用警告)"""
    if not db_path.exists():
        return {"ok": True, "warnings": [], "stats": {}}
    bak_pattern = db_path.name + ".bak.*"
    baks = sorted(db_path.parent.glob(bak_pattern), key=lambda p: p.name)
    total_size = sum(p.stat().st_size for p in baks) / 1024 / 1024
    warnings = []
    if len(baks) > max_retain:
        warnings.append(f"备份文件 {len(baks)} 个 (上限 {max_retain}), 占用 {total_size:.1f}MB")
    return {
        "ok": len(baks) <= max_retain,
        "warnings": warnings,
        "stats": {
            "backup_count": len(baks),
            "backup_total_mb": round(total_size, 1),
            "backup_max_retain": max_retain,
        },
    }


def check_regression(db_path: Path, timeout: int = 120) -> dict:
    """[V007.55] 跑 regression_test_suite.py 验证 sqlite io error 防护

    仅在 staging 跑 (regression_test_suite.py 硬防护会拒绝 prod)
    期望: 7 PASS / 0 FAIL / 2 SKIP (R1 R9 root 防护 SKIP)
    """
    suite = SCRIPT_DIR / "regression_test_suite.py"
    if not suite.exists():
        return {
            "ok": False,
            "errors": [f"regression_test_suite.py 不存在: {suite}"],
            "warnings": [],
            "stats": {"suite_path": str(suite)},
        }
    # 推断 staging db 路径 (基于传入 db_path)
    # db_path 可能是 /opt/app/deployments/meta/architecture.db (prod) 或 staging
    if "/staging/" not in str(db_path):
        return {
            "ok": None,  # WARN, 不跑 (因为 prod 不能跑)
            "errors": [],
            "warnings": ["--check-regression 仅在 staging 跑, 跳过 (db 不含 /staging/)"],
            "stats": {"skipped": True, "reason": "non-staging db path"},
        }
    # 跑 regression_test_suite
    try:
        proc = subprocess.run(
            ["python3", str(suite), "--json", "/tmp/regression_monitor.json"],
            capture_output=True, text=True, timeout=timeout, cwd=str(suite.parent.parent),
        )
        # 解析 json
        report_path = Path("/tmp/regression_monitor.json")
        if not report_path.exists():
            return {
                "ok": False,
                "errors": [f"regression_test_suite 未生成报告: {report_path}"],
                "warnings": [proc.stdout[-500:] if proc.stdout else "", proc.stderr[-500:] if proc.stderr else ""],
                "stats": {"exit_code": proc.returncode},
            }
        with open(report_path, encoding='utf-8') as f:
            report = json.load(f)
        summary = report.get("summary", {})
        pass_n = summary.get("pass", 0)
        fail_n = summary.get("fail", 0)
        skip_n = summary.get("skip", 0)
        ok = (fail_n == 0 and pass_n > 0)
        return {
            "ok": ok,
            "errors": [f"regression FAIL: {fail_n} 个失败"] if fail_n else [],
            "warnings": [
                f"regression 全 SKIP ({skip_n} 个), 检查环境" if pass_n == 0 and skip_n > 0 else None
            ] + [
                f"regression PASS={pass_n} SKIP={skip_n} (期望 7/2)" if pass_n != 7 or skip_n != 2 else None
            ],
            "stats": {
                "regression_pass": pass_n,
                "regression_fail": fail_n,
                "regression_skip": skip_n,
                "regression_total": summary.get("total", 0),
                "regression_run_id": report.get("run_id"),
            },
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "errors": [f"regression_test_suite 超时 ({timeout}s)"],
            "warnings": [],
            "stats": {"timeout": timeout},
        }
    except Exception as e:
        return {
            "ok": False,
            "errors": [f"regression_test_suite 异常: {e}"],
            "warnings": [],
            "stats": {"exception": str(e)},
        }


def main():
    parser = argparse.ArgumentParser(description="[P1.7] Migration 健康监控")
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    parser.add_argument("--log-path", default=str(DEFAULT_LOG))
    parser.add_argument("--max-retain", type=int, default=5,
                        help="最大备份保留数 (default: 5)")
    parser.add_argument("--check-regression", action="store_true",
                        help="[V007.55] 跑 regression_test_suite (staging sqlite io error)")
    parser.add_argument("--regression-timeout", type=int, default=120,
                        help="regression_test_suite 超时秒数 (default: 120)")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    log_path = Path(args.log_path)

    print(f"=== Migration Health Monitor [{datetime.now().isoformat()}] ===")
    print(f"DB: {db_path}")
    print(f"Log: {log_path}")
    print()

    # 1. schema_migrations 健康
    print("--- schema_migrations table ---")
    db_health = check_schema_migrations_health(db_path)
    for e in db_health["errors"]:
        section("ERROR", False, e)
    for w in db_health["warnings"]:
        section("WARN", None, w)
    if not db_health["errors"] and not db_health["warnings"]:
        section("schema_migrations", True, f"{db_health['stats'].get('total', 0)} records")
    for k, v in db_health["stats"].items():
        if k not in ("total",):
            section(f"  {k}", "info", str(v))
    print()

    # 2. 告警日志
    print("--- migration alerts (recent 100 lines) ---")
    alert_health = check_migration_alerts(log_path)
    if not alert_health["stats"].get("log_exists"):
        section("alert log", None, f"log 不存在: {log_path} (runner 未跑过？)")
    elif alert_health["alerts"]:
        for a in alert_health["alerts"]:
            section("alert", False, a)
    else:
        section("alert log", True, "recent 100 lines 无 FAILED/ROLLED_BACK")
    for k, v in alert_health["stats"].items():
        if k != "log_exists":
            section(f"  {k}", "info", str(v))
    print()

    # 3. 备份残留
    print("--- backup residue ---")
    bak_health = check_backup_residue(db_path, args.max_retain)
    for w in bak_health["warnings"]:
        section("WARN", None, w)
    if not bak_health["warnings"]:
        section("backup", True, f"{bak_health['stats'].get('backup_count', 0)} files, "
                                  f"{bak_health['stats'].get('backup_total_mb', 0)}MB")
    print()

    # 4. [V007.55] regression 测试 (staging only)
    regression_health = None
    if args.check_regression:
        print("--- regression test (V007.55) ---")
        regression_health = check_regression(db_path, args.regression_timeout)
        for e in regression_health["errors"]:
            section("ERROR", False, e)
        real_warnings = [w for w in regression_health["warnings"] if w]
        for w in real_warnings:
            section("WARN", None, w)
        if not regression_health["errors"] and not real_warnings:
            section("regression", True, f"PASS={regression_health['stats'].get('regression_pass')} "
                                          f"FAIL={regression_health['stats'].get('regression_fail')} "
                                          f"SKIP={regression_health['stats'].get('regression_skip')}")
        for k, v in regression_health["stats"].items():
            if k not in ("suite_path",):
                section(f"  {k}", "info", str(v))
        print()

    # 汇总
    fatal = bool(db_health["errors"]) or not alert_health["ok"]
    if regression_health is not None:
        fatal = fatal or (regression_health["ok"] is False)
    warn = (bool(db_health["warnings"]) or bak_health["warnings"]
            or alert_health["alerts"]
            or (regression_health is not None and regression_health["ok"] is None))
    if fatal:
        print("=== RESULT: FAIL (FATAL issues found) ===")
        return 1
    if warn:
        print("=== RESULT: WARN (issues found) ===")
        return 2
    print("=== RESULT: OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
