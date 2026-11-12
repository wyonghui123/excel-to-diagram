"""create_app 启动链路分段计时 + 守卫状态快照（TEST-EFF P0-3）

为什么需要它
------------
P0/P1 系列（cron 关闭、atexit 短路、schema/enum/menu/yaml/preflight 五项守卫）
把 `create_app()` 从约 12.2s 降到约 2.1s。但每验证一项都要临时写探针、
跑完再删（一个会话写了 6 个），导致：

- 收益无法被下一个 agent 复现或对比；
- 守卫从「命中」退化为「永久 miss」时，没有人能第一时间发现；
- 新增同步/种子逻辑时，没有统一口径判断它让启动变慢了多少。

本工具把探针固化：分段计时 + 守卫记录快照，输出 JSON 可入库为基线。

口径说明
--------
- 只统计 `create_app()` 内部耗时，不含本进程 import 时间；
- run#0 是进程内首次（相对冷），run#1+ 是同进程重复（热，缓存/守卫已生效）；
- 默认使用 `meta/architecture.db` 的 SQLite backup 副本，不改生产库；
- 默认关闭 cron 调度器（与 conftest 的测试态一致），避免后台线程干扰计时；
- 默认不设 `SKIP_DB_PREFLIGHT`；需要与测试进程完全对齐时加 `--skip-preflight`。

用法
----
    python scripts/debug/verify/startup_breakdown.py
    python scripts/debug/verify/startup_breakdown.py --repeat 3 --skip-preflight
    python scripts/debug/verify/startup_breakdown.py \
        --json docs/testing/startup-baseline.json
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB = REPO_ROOT / "meta" / "architecture.db"

# meta/server.py 里的同步/种子/服务初始化入口；缺失的自动跳过并标记 n/a
SERVER_HOOKS = [
    ("preflight_db_check", "_preflight_db_check"),
    ("yaml_register_from_directory", "register_from_directory"),
    ("init_manage_services(schema sync)", "init_manage_services"),
    ("init_identity_services", "init_identity_services"),
    ("init_database_services", "init_database_services"),
    ("init_auth_services", "init_auth_services"),
    ("init_user_services", "init_user_services"),
    ("init_permission_set_services", "init_permission_set_services"),
    ("init_data_perm_services", "init_data_perm_services"),
    ("init_org_services", "init_org_services"),
    ("init_org_function_services", "init_org_function_services"),
    ("init_enum_services", "init_enum_services"),
    ("init_audit_services", "init_audit_services"),
    ("init_association_services", "init_association_services"),
    ("init_special_services", "init_special_services"),
    ("init_annotation_services", "init_annotation_services"),
    ("init_audit_mgmt_services", "init_audit_mgmt_services"),
    ("init_task_menus", "init_task_menus"),
    ("init_task_seed_data", "init_task_seed_data"),
    ("init_region_seed_data", "init_region_seed_data"),
    ("init_menu_permissions", "init_menu_permissions"),
]


def _apply_test_env(skip_preflight):
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("DISABLE_ASYNC_AUDIT_WRITER", "true")
    os.environ.setdefault("DISABLE_TASK_SCHEDULER", "true")
    os.environ.setdefault("DISABLE_WRITE_QUEUE", "true")
    os.environ.setdefault("DISABLE_RATE_LIMIT", "true")
    os.environ.setdefault("CRON_JOBS_ENABLED", "0")
    os.environ.setdefault("META_YAML_VERBOSE", "0")
    if skip_preflight:
        os.environ["SKIP_DB_PREFLIGHT"] = "1"
    else:
        os.environ.pop("SKIP_DB_PREFLIGHT", None)


def _copy_db(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    source = sqlite3.connect(str(src), timeout=10)
    target = sqlite3.connect(str(dst), timeout=10)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


class Timer:
    def __init__(self):
        self.sections = defaultdict(lambda: [0.0, 0])

    def wrap(self, target, attr, label):
        original = getattr(target, attr, None)
        if original is None:
            return None

        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                bucket = self.sections[label]
                bucket[0] += time.perf_counter() - started
                bucket[1] += 1

        setattr(target, attr, wrapper)

        def restore():
            setattr(target, attr, original)

        return restore

    def snapshot(self):
        return {
            label: {"seconds": round(seconds, 3), "calls": calls}
            for label, (seconds, calls) in sorted(
                self.sections.items(), key=lambda item: -item[1][0])
        }


def _guard_snapshot(db_path):
    try:
        from meta.core.declaration_guard import status
        return status(str(db_path))
    except Exception as exc:
        return [{"table": "<error>", "rows": [{"error": str(exc)}]}]


def main(argv=None):
    parser = argparse.ArgumentParser(description="create_app 启动链路分段计时")
    parser.add_argument("--db", default=None,
                        help="使用的 DB（默认复制 meta/architecture.db 到 test_temp/）")
    parser.add_argument("--repeat", type=int, default=2,
                        help="同进程连续 create_app 次数，默认 2（首次 + 热）")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="设 SKIP_DB_PREFLIGHT=1，与测试进程完全对齐")
    parser.add_argument("--json", default=None, help="结果写入 JSON 文件")
    parser.add_argument("--keep-db", action="store_true", help="保留临时 DB 副本")
    parser.add_argument("--verbose", action="store_true",
                        help="保留 create_app 期间的 INFO 日志（默认压到 WARNING）")
    args = parser.parse_args(argv)

    _apply_test_env(args.skip_preflight)

    if args.db:
        db_path = Path(args.db).resolve()
    else:
        db_path = REPO_ROOT / "test_temp" / "startup_breakdown.db"
        _copy_db(DEFAULT_DB, db_path)
    if not db_path.exists():
        print(f"DB 不存在: {db_path}", file=sys.stderr)
        return 2

    import meta.server as server
    from flask import Flask

    if not args.verbose:
        # server 导入期已 basicConfig(INFO)，这里压到 WARNING，保证结果可读
        logging.getLogger().setLevel(logging.WARNING)

    persist_target = getattr(server, "menu_auto_generator", None)

    def mount(timer):
        """挂载本轮计时补丁，返回 restore 列表（每轮独立计时）。"""
        mounted = []
        # 类级补丁会统计所有 Flask 实例；工具进程内只创建被测 app，可接受
        for attr in ("register_blueprint", "add_url_rule"):
            mounted.append(timer.wrap(Flask, attr, attr))
        for label, attr in SERVER_HOOKS:
            mounted.append(timer.wrap(server, attr, label))
        if persist_target is not None and hasattr(persist_target, "persist_to_db"):
            mounted.append(
                timer.wrap(persist_target, "persist_to_db", "menu_auto_persist"))
        return [restore for restore in mounted if restore]

    runs = []
    restores = []
    try:
        for index in range(max(1, args.repeat)):
            for restore in restores:
                restore()
            timer = Timer()
            restores = mount(timer)

            started = time.perf_counter()
            app = server.create_app(str(db_path))
            total = time.perf_counter() - started
            rules = len(app.url_map._rules)
            sections = timer.snapshot()
            runs.append({
                "run": index,
                "mode": "first" if index == 0 else "warm",
                "total_s": round(total, 3),
                "rules": rules,
                "sections": sections,
            })
    finally:
        for restore in restores:
            restore()

    guards = _guard_snapshot(db_path)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db": str(db_path),
        "db_note": "副本" if not args.db else "指定库",
        "env": {
            "SKIP_DB_PREFLIGHT": os.environ.get("SKIP_DB_PREFLIGHT"),
            "GUARD_FORCE": os.environ.get("GUARD_FORCE"),
            "CRON_JOBS_ENABLED": os.environ.get("CRON_JOBS_ENABLED"),
            "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED"),
            "TESTING": os.environ.get("TESTING"),
        },
        "runs": runs,
        "guards": guards,
    }

    for run in runs:
        print(f"\nRun #{run['run']} ({run['mode']}) "
              f"total={run['total_s']}s rules={run['rules']}")
        for label, stat in run["sections"].items():
            if label in ("add_url_rule",):
                note = "  (含于 register_blueprint)"
            else:
                note = ""
            print(f"  {label:<34} {stat['seconds']:>7.3f}s "
                  f"x{stat['calls']}{note}")

    hit = [
        row for group in guards for row in group.get("rows", [])
        if "scope_key" in row or "guard_key" in row
    ]
    print(f"\n守卫记录: {len(hit)} 条（详细见 --json）")
    for row in hit:
        key = row.get("scope_key") or row.get("guard_key")
        print(f"  {key}: v={row.get('version', '-')} "
              f"hash={str(row.get('declaration_hash') or row.get('guard_value'))[:12]} "
              f"applied={row.get('applied_at') or row.get('updated_at')}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 已写入 {out}")

    if not args.keep_db and not args.db:
        try:
            db_path.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())