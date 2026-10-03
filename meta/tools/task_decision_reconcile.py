# -*- coding: utf-8 -*-
"""[B3 2026-10-03] 决策-生效一致性巡检（跨库方向）—— 触发式运维脚本

契约: task-model spec §9.7 规范 5 / §12.1 B3。
      对账逻辑见 meta/core/decision_effect.reconcile_effects；与 F1
      （meta/tools/task_hold_reconcile.py）契约同形（--db/--json/--strict，退出码 0/1/2）。

与心跳段的分工:
- 心跳（platform_tick）只跑**平台库内可判**方向（done 无回执 / 配置完整性）。
- 本 CLI 承接**跨库方向**：`--current-statuses-json` 注入单据现状（effect_mismatch）、
  `--pending-docs-json` 注入等待审批单据（pending_without_task），保持跨库解耦。

用法（repo 根目录）::

    python -m meta.tools.task_decision_reconcile --db <平台库路径>
    python -m meta.tools.task_decision_reconcile --db data/platform.db --json
    python -m meta.tools.task_decision_reconcile --db data/platform.db --strict
    python -m meta.tools.task_decision_reconcile --db data/platform.db \
        --current-statuses-json '{"DOC-1":"approved"}'

说明:
- 默认**只读**巡检，绝不写库。
- --strict：存在 findings 时退出码 1（CI / 运维告警用）。
- 异常（库不可读 / 被锁 / 注入 JSON 非法）：[ERROR] 一行 + 退出码 2（不抛裸栈）；
  --db 指向不存在的文件同样 exit 2（不静默新建空库）。
"""
import argparse
import json
import os
import sys
from typing import Any, List, Optional

from meta.core.datasource import get_data_source
from meta.core.decision_effect import reconcile_effects


def _load_json_arg(raw: Optional[str], arg_name: str, expected: type) -> Any:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{arg_name} 不是合法 JSON: {e}") from e
    if not isinstance(value, expected):
        raise ValueError(f"{arg_name} 必须是 {expected.__name__}")
    return value


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="决策-生效一致性巡检（B3 跨库方向，触发式）")
    parser.add_argument("--db", required=True, help="平台库文件路径")
    parser.add_argument("--json", action="store_true", help="输出机读 JSON")
    parser.add_argument("--strict", action="store_true",
                        help="存在 findings 时退出码 1")
    parser.add_argument("--current-statuses-json",
                        help='单据现状映射 JSON，如 \'{"DOC-1":"approved"}\'')
    parser.add_argument("--pending-docs-json",
                        help="等待审批单据 JSON 数组，元素为 doc_ref 或 {doc_ref, since}")
    parser.add_argument("--stale-hours", type=float, default=24,
                        help="pending_without_task 的过期阈值（小时，默认 24）")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.db):
        # 防 SQLite 连接时静默新建空库 → 误报无发现
        print("[ERROR] 库文件不存在: {0}".format(args.db))
        return 2

    try:
        current_statuses = _load_json_arg(
            args.current_statuses_json, "--current-statuses-json", dict)
        pending_docs = _load_json_arg(
            args.pending_docs_json, "--pending-docs-json", list)
        ds = get_data_source("sqlite", database=args.db)
        findings = reconcile_effects(
            ds, current_statuses=current_statuses, pending_docs=pending_docs,
            stale_hours=args.stale_hours,
        )
    except Exception as e:  # noqa: BLE001 - 库不可读/被锁/注入非法：异常兜底
        print("[ERROR] 对账失败: {0}".format(e))
        return 2

    if args.json:
        print(json.dumps(
            {"db": args.db, "findings": findings, "count": len(findings)},
            ensure_ascii=False, indent=2,
        ))
    else:
        print("=== 决策-生效一致性巡检（B3）===")
        print("库: {0}".format(args.db))
        if not findings:
            print("[OK] 无发现")
        else:
            for f in findings:
                ref = f.get("task_id") or f.get("doc_ref") or "-"
                print("[{0}] {1} — {2}".format(f["kind"].upper(), ref, f["detail"]))

    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())