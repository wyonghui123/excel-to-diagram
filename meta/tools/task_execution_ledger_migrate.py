# -*- coding: utf-8 -*-
"""Gen1 执行账本 → Gen2 事件账跨库投影（账本统一 Phase 2b）

背景
  Gen1 执行账本 `task_executions`（应用库）与 Gen2 事件账 `task_events`
  （平台库）长期双轨：前者由遗留调度器写、后者为空。账本统一的三步:
    2a v165 冻结 pending/running → cancelled；
    2b 本工具把 `task_executions` + `task_execution_archive` 投影到
       `task_events`（event_type=`legacy_execution`，payload 存整行）；
    2c v166 物理退役 Gen1 两张表。

为什么是独立工具而非 migration
  - 跨库（应用库 → 平台库）无法放进只接收单 `db_path` 的 migration runner；
  - 投影只读源表、只追加事件（append-only），可重复执行，适合按需运维触发。

幂等
  - 事件 id 以 `gen1-execution:<行id>` / `gen1-archive:<行id>` 派生；
    已存在即跳过 → 重复执行 0 新增。

用法（repo 根目录）::

    python -m meta.tools.task_execution_ledger_migrate \\
        --app-db <应用库> --platform-db <平台库>
    python -m meta.tools.task_execution_ledger_migrate --dry-run --json
    python -m meta.tools.task_execution_ledger_migrate --strict

退出码
  0 成功（含「无源表/无行」的空跑）
  1 --strict 判定未完成（有未投影行 / 投影后仍缺事件）
  2 参数或库不可用（源库不存在 / 目标缺 task_events）
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from meta.core.task_event_schema import EVENT_TYPES, TASK_EVENT_TABLE

EVENT_TYPE = "legacy_execution"

# (来源标识, 表名)；顺序即投影顺序
SOURCES: Tuple[Tuple[str, str], ...] = (
    ("execution", "task_executions"),
    ("archive", "task_execution_archive"),
)

ID_TEMPLATE = "gen1-{origin}:{row_id}"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _row_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _first_value(row: sqlite3.Row, keys: Tuple[str, ...]) -> Optional[str]:
    available = set(row.keys())
    for key in keys:
        if key in available and row[key]:
            return str(row[key])
    return None


def _occurred_at(row: sqlite3.Row) -> str:
    return _first_value(
        row, ("completed_at", "queued_at", "started_at", "created_at", "archived_at")
    ) or _now_iso()


def _task_id(row: sqlite3.Row, origin: str) -> str:
    raw = row["task_id"] if "task_id" in row.keys() else None
    if raw is None or str(raw).strip() == "":
        return "gen1-{0}:{1}".format(origin, row["id"])
    return "gen1-scheduled-task:{0}".format(raw)


def _build_event(row: sqlite3.Row, origin: str) -> Dict[str, Any]:
    row_id = row["id"]
    status = row["status"] if "status" in row.keys() else None
    return {
        "id": ID_TEMPLATE.format(origin=origin, row_id=row_id),
        "task_id": _task_id(row, origin),
        "workflow_run_id": None,
        "event_type": EVENT_TYPE,
        "from_status": None,
        "to_status": status,
        "actor": "gen1_scheduler",
        "actor_kind": "system",
        "reason": "Gen1 执行账本投影（origin={0}, status={1}）".format(
            origin, status or "?"),
        "payload": json.dumps(_row_dict(row), ensure_ascii=False, default=str),
        "doc_ref": None,
        "line_refs": None,
        "agent_session_id": None,
        "trace_id": None,
        "occurred_at": _occurred_at(row),
        "created_at": _now_iso(),
    }


def _read_source(conn: sqlite3.Connection, table: str) -> List[sqlite3.Row]:
    return conn.execute('SELECT * FROM "{0}" ORDER BY id'.format(table)).fetchall()


def _existing_ids(conn: sqlite3.Connection) -> set:
    prefix_exec = ID_TEMPLATE.format(origin="execution", row_id="")
    prefix_arch = ID_TEMPLATE.format(origin="archive", row_id="")
    rows = conn.execute(
        "SELECT id FROM {0} WHERE id LIKE ? OR id LIKE ?".format(TASK_EVENT_TABLE),
        (prefix_exec + "%", prefix_arch + "%"),
    ).fetchall()
    return {r[0] for r in rows}


def project(app_db: str, platform_db: str, dry_run: bool = False) -> Dict[str, Any]:
    """把 Gen1 两张账本表投影到平台库 task_events。

    Raises:
        ValueError: 源库不存在 / 目标库缺 task_events / 事件类型未登记。
    """
    if EVENT_TYPE not in EVENT_TYPES:
        raise ValueError(
            "event_type={0!r} 未登记进 task_event_schema.EVENT_TYPES".format(EVENT_TYPE))

    for label, path in (("app_db", app_db), ("platform_db", platform_db)):
        if not os.path.isfile(path):
            raise ValueError("{0} 不存在: {1}".format(label, path))

    app_conn = sqlite3.connect(app_db)
    app_conn.row_factory = sqlite3.Row
    same_file = os.path.abspath(app_db) == os.path.abspath(platform_db)
    plat_conn = app_conn if same_file else sqlite3.connect(platform_db)

    try:
        if not _table_exists(plat_conn, TASK_EVENT_TABLE):
            raise ValueError(
                "目标库缺 {0} 表: {1}".format(TASK_EVENT_TABLE, platform_db))

        existing = _existing_ids(plat_conn)
        events: List[Dict[str, Any]] = []
        sources: Dict[str, Dict[str, Any]] = {}

        for origin, table in SOURCES:
            present = _table_exists(app_conn, table)
            rows = _read_source(app_conn, table) if present else []
            sources[origin] = {"table": table, "rows": len(rows), "exists": present}
            for row in rows:
                event = _build_event(row, origin)
                if event["id"] not in existing:
                    events.append(event)

        if not dry_run and events:
            columns = ("id", "task_id", "workflow_run_id", "event_type",
                       "from_status", "to_status", "actor", "actor_kind",
                       "reason", "payload", "doc_ref", "line_refs",
                       "agent_session_id", "trace_id", "occurred_at", "created_at")
            placeholders = ", ".join("?" for _ in columns)
            plat_conn.execute("BEGIN")
            plat_conn.executemany(
                "INSERT INTO {0} ({1}) VALUES ({2})".format(
                    TASK_EVENT_TABLE, ", ".join(columns), placeholders),
                [tuple(e[c] for c in columns) for e in events],
            )
            plat_conn.commit()

        found = sum(s["rows"] for s in sources.values())
        already = found - len(events)
        report: Dict[str, Any] = {
            "app_db": app_db,
            "platform_db": platform_db,
            "sources": sources,
            "found": found,
            "projected": 0 if dry_run else len(events),
            "would_project": len(events),
            "already_present": already,
            "dry_run": dry_run,
        }

        if not dry_run:
            expected = {e["id"] for e in events} | existing
            after = _existing_ids(plat_conn)
            report["missing_after"] = sorted(expected - after)
        return report
    except Exception:
        try:
            plat_conn.rollback()
        except Exception:  # noqa: BLE001 - 已提交或连接不可用
            pass
        raise
    finally:
        if not same_file:
            plat_conn.close()
        app_conn.close()


def _print_human(report: Dict[str, Any]) -> None:
    print("=== Gen1 执行账本 → Gen2 事件账投影 ===")
    print("应用库: {0}".format(report["app_db"]))
    print("平台库: {0}".format(report["platform_db"]))
    for origin, info in report["sources"].items():
        state = "存在" if info["exists"] else "不存在"
        print("  {0}: {1}（{2} 行，{3}）".format(
            info["table"], origin, info["rows"], state))
    verb = "将投影" if report["dry_run"] else "已投影"
    print("{0}: {1} 行（已存在跳过: {2}）".format(
        verb, report["would_project"] if report["dry_run"] else report["projected"],
        report["already_present"]))
    if report["dry_run"]:
        print("模式: --dry-run（未写库）")
    if report.get("missing_after"):
        print("[FAIL] 投影后仍缺 {0} 条事件".format(len(report["missing_after"])))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gen1 执行账本 → Gen2 事件账跨库投影（账本统一 Phase 2b）")
    parser.add_argument("--app-db", required=True, help="应用库（task_executions 所在）")
    parser.add_argument("--platform-db", required=True, help="平台库（task_events 所在）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    parser.add_argument("--json", action="store_true", help="输出机读 JSON")
    parser.add_argument("--strict", action="store_true",
                        help="有未投影行 / 投影后仍缺事件时退出码 1")
    args = parser.parse_args(argv)

    try:
        report = project(args.app_db, args.platform_db, dry_run=args.dry_run)
    except Exception as e:  # noqa: BLE001 - 库不可用/参数非法：一行错误 + exit 2
        print("[ERROR] 投影失败: {0}".format(e))
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)

    if report.get("missing_after"):
        return 1
    if args.strict and args.dry_run and report["would_project"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
