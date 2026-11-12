"""启动期「声明内容哈希」守卫的统一工具包（TEST-EFF P0-1）

为什么需要它
------------
`create_app()` 里的若干同步/种子环节（schema sync、enum migrate、菜单权限、
菜单自动持久化、YAML 目录解析）都遵循同一套范式：

    声明内容不变 ⇒ 跳过整轮写操作；声明内容变了 ⇒ 全量重做。

在 P0/P1 系列优化中，这套范式被手写了 4 份，各自解决「版本号、内容哈希、
对象存在性、异常降级、原子写入」中的一部分，导致：

- P1-3 曾用 `list(set(...))` 生成哈希，跨进程受 PYTHONHASHSEED 影响而抖动，
  守卫永久 miss（优化收益全部消失）；
- 多数实现没有统一的「为什么 miss」日志，排查只能靠读代码；
- 没有统一的逃生口，验证「改了声明是否真的生效」只能手工删表。

本模块把四条正确性收敛到一个 API，新守卫只需提供 `payload`（声明内容）和
可选的 `presence`（期望对象是否已存在）两个回调。

四条正确性（使用方无需再各自实现）
----------------------------------
1. 确定性哈希：payload 规范化（键排序、禁止无序容器）后 sha256；
   `set/frozenset` 会被排序并告警，避免复刻 P1-3 的跨进程抖动。
2. 版本 + 内容双因子：`version` 不等或 `declaration_hash` 不等都算 miss，
   且不依赖版本号单独做判断（V056 事故的教训）。
3. 存在性前提：`presence` 返回假值即 miss，保留「库被删表后自愈」的能力。
4. 失败即降级：任何异常都返回 miss 并记 warning，绝不阻断启动；
   只有全量执行成功之后才允许调用 `mark_applied`。

逃生口
------
`GUARD_FORCE=1` 时所有守卫一律 miss（强制全量重跑），用于验证「我改了声明，
守卫为什么还命中」。

命令行
------
    python -m meta.core.declaration_guard --db meta/architecture.db --status
    python -m meta.core.declaration_guard --db meta/architecture.db --reset 全部
    python -m meta.core.declaration_guard --db meta/architecture.db --reset <scope_key>
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 新守卫统一使用的表；存量守卫的表（schema_sync_guard / menu_sync_guard）保持不变，
# 由 --status 统一展示，按「触碰时迁移」策略逐步收敛。
TABLE = "declaration_guard"

_TABLE_DDL = (
    f"CREATE TABLE IF NOT EXISTS {TABLE} ("
    "scope_key VARCHAR(80) PRIMARY KEY,"
    "version INTEGER NOT NULL,"
    "declaration_hash VARCHAR(64) NOT NULL,"
    "applied_at DATETIME)"
)

# 命中 / 未命中的原因，统一进日志，便于一眼区分「哈希变了」还是「对象没了」
REASON_HIT = "hit"
REASON_NO_RECORD = "no_record"
REASON_VERSION_MISS = "version_miss"
REASON_HASH_MISS = "hash_miss"
REASON_PRESENCE_MISSING = "presence_missing"
REASON_FORCED = "forced"
REASON_ERROR = "error"


@dataclass(frozen=True)
class GuardDecision:
    """一次守卫判定的结果（不可变，可直接用于断言与日志）。"""

    hit: bool
    reason: str
    declaration_hash: str = ""
    stored_hash: str = ""
    stored_version: int = 0

    @property
    def skipped(self) -> bool:
        return self.hit


@dataclass(frozen=True)
class GuardSpec:
    """守卫声明。

    scope_key: 守卫作用域，同一 DB 内唯一（如 "schema_sync" / "enum_migrate"）。
    version:   生成语义版本，声明/生成逻辑变更时必须 +1。
    payload:   参与哈希的声明内容；只能用 dict/list/str/int/float/bool/None/bytes。
    presence:  可选回调，入参为 data_source（有 execute 的对象），返回真值表示
               「期望对象已存在」。返回 (bool, detail) 时取第一个元素。
    """

    scope_key: str
    version: int
    payload: Any
    presence: Optional[Callable[[Any], Any]] = None
    namespace: str = ""


def _forced() -> bool:
    return os.environ.get("GUARD_FORCE", "") in ("1", "true", "True", "yes")


def _normalize(value: Any, path: str = "payload") -> Any:
    """把 payload 规范化成确定性的 JSON 结构。

    set 会被排序后转成 list（并告警）：宁可多一次 warning，也不能让哈希
    受 PYTHONHASHSEED 影响。
    """
    if isinstance(value, (set, frozenset)):
        logger.warning(
            "[GUARD] %s 含 set/frozenset，已按稳定序转换；请改用 sorted(list) "
            "避免跨进程哈希抖动", path,
        )
        items = [_normalize(item, f"{path}[]") for item in value]
        return sorted(items, key=lambda item: json.dumps(
            item, sort_keys=True, ensure_ascii=False))
    if isinstance(value, dict):
        return {str(k): _normalize(v, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item, f"{path}[]") for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(
        f"{path} 的类型 {type(value).__name__} 无法稳定参与哈希；"
        "请只传 dict/list/str/int/float/bool/None/bytes，"
        "或先显式转换成稳定字符串"
    )


def hash_payload(payload: Any, namespace: str = "") -> str:
    """计算声明内容哈希（确定性：同内容 ⇒ 同哈希，跨进程一致）。"""
    body = json.dumps(
        _normalize(payload), sort_keys=True, ensure_ascii=False,
        separators=(",", ":"),
    )
    hasher = hashlib.sha256()
    hasher.update(f"{namespace}\n".encode("utf-8"))
    hasher.update(body.encode("utf-8"))
    return hasher.hexdigest()


def _row_value(row: Any, key: str, index: int) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        keys = row.keys()
    except Exception:
        keys = None
    if keys is not None:
        try:
            return row[key]
        except Exception:
            pass
    try:
        return row[index]
    except Exception:
        return None


def ensure_schema(conn: Any) -> None:
    conn.execute(_TABLE_DDL)
    conn.commit()


def _lookup(conn: Any, scope_key: str):
    return conn.execute(
        f"SELECT version, declaration_hash, applied_at FROM {TABLE} "
        "WHERE scope_key = ?",
        (scope_key,),
    ).fetchone()


def _presence_ok(presence: Callable[[Any], Any], conn: Any):
    result = presence(conn)
    if isinstance(result, tuple) and result:
        return bool(result[0]), (result[1] if len(result) > 1 else "")
    return bool(result), ""


def evaluate(conn: Any, spec: GuardSpec) -> GuardDecision:
    """判定守卫是否命中；任何异常都降级为 miss（不抛出）。"""
    if _forced():
        logger.info(
            "[GUARD] scope=%s v=%s hit=False reason=%s（GUARD_FORCE 生效）",
            spec.scope_key, spec.version, REASON_FORCED,
        )
        return GuardDecision(False, REASON_FORCED)

    try:
        declaration_hash = hash_payload(spec.payload, spec.namespace)
    except Exception as exc:
        logger.warning(
            "[GUARD] scope=%s 哈希计算失败，回落全量: %s", spec.scope_key, exc)
        return GuardDecision(False, REASON_ERROR)

    try:
        ensure_schema(conn)
        row = _lookup(conn, spec.scope_key)
    except Exception as exc:
        logger.warning(
            "[GUARD] scope=%s 守卫读取失败，回落全量: %s", spec.scope_key, exc)
        return GuardDecision(False, REASON_ERROR, declaration_hash)

    if row is None:
        return GuardDecision(False, REASON_NO_RECORD, declaration_hash)

    stored_version = int(_row_value(row, "version", 0) or 0)
    stored_hash = str(_row_value(row, "declaration_hash", 1) or "")

    if stored_version != int(spec.version):
        return GuardDecision(
            False, REASON_VERSION_MISS, declaration_hash, stored_hash,
            stored_version)
    if stored_hash != declaration_hash:
        return GuardDecision(
            False, REASON_HASH_MISS, declaration_hash, stored_hash,
            stored_version)

    if spec.presence is not None:
        try:
            ok, detail = _presence_ok(spec.presence, conn)
        except Exception as exc:
            logger.warning(
                "[GUARD] scope=%s 存在性检查失败，回落全量: %s",
                spec.scope_key, exc)
            return GuardDecision(
                False, REASON_ERROR, declaration_hash, stored_hash,
                stored_version)
        if not ok:
            logger.info(
                "[GUARD] scope=%s hit=False reason=%s detail=%s",
                spec.scope_key, REASON_PRESENCE_MISSING, detail or "-")
            return GuardDecision(
                False, REASON_PRESENCE_MISSING, declaration_hash, stored_hash,
                stored_version)

    return GuardDecision(True, REASON_HIT, declaration_hash, stored_hash,
                         stored_version)


def log_decision(spec: GuardSpec, decision: GuardDecision) -> GuardDecision:
    """按统一格式输出一行守卫日志，并原样返回 decision。"""
    if decision.hit:
        logger.info(
            "[GUARD] scope=%s v=%s hit=True reason=%s hash=%s",
            spec.scope_key, spec.version, decision.reason,
            decision.declaration_hash[:12])
    elif decision.reason == REASON_ERROR:
        # evaluate 内部已记 warning，这里不再重复
        pass
    else:
        logger.info(
            "[GUARD] scope=%s v=%s hit=False reason=%s hash=%s stored=%s v_stored=%s",
            spec.scope_key, spec.version, decision.reason,
            decision.declaration_hash[:12] or "-",
            decision.stored_hash[:12] or "-", decision.stored_version)
    return decision


def should_skip(conn: Any, spec: GuardSpec) -> bool:
    """守卫命中 ⇒ True（调用方直接 return，不做全量）。"""
    return log_decision(spec, evaluate(conn, spec)).hit


def mark_applied(conn: Any, spec: GuardSpec) -> bool:
    """在全量执行成功之后记录守卫；失败只告警，不影响本次结果。"""
    from datetime import datetime

    try:
        declaration_hash = hash_payload(spec.payload, spec.namespace)
        ensure_schema(conn)
        conn.execute(
            f"INSERT OR REPLACE INTO {TABLE} "
            "(scope_key, version, declaration_hash, applied_at) VALUES (?, ?, ?, ?)",
            (spec.scope_key, int(spec.version), declaration_hash,
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        logger.info(
            "[GUARD] scope=%s v=%s 已记录 hash=%s",
            spec.scope_key, spec.version, declaration_hash[:12])
        return True
    except Exception as exc:
        logger.warning(
            "[GUARD] scope=%s 守卫写入失败（下次将重跑全量）: %s",
            spec.scope_key, exc)
        return False


def status(db_path: str) -> list:
    """列出 DB 内所有守卫表（含存量表）及其记录，供排查「为什么 miss」。"""
    import sqlite3

    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE '%guard%' ORDER BY name"
            )
        ]
        result = []
        for table in tables:
            rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
            result.append({"table": table, "rows": rows})
        return result
    finally:
        conn.close()


def reset(db_path: str, scope_key: str = None) -> int:
    """删除守卫记录；scope_key 为 None / "all" 时清空所有守卫表。"""
    import sqlite3

    conn = sqlite3.connect(db_path, timeout=5)
    try:
        tables = [
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE '%guard%'"
            )
        ]
        affected = 0
        for table in tables:
            columns = [
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            ]
            if "scope_key" in columns and scope_key not in (None, "all"):
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE scope_key = ?", (scope_key,))
            elif "guard_key" in columns and scope_key not in (None, "all"):
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE guard_key = ?", (scope_key,))
            else:
                cursor = conn.execute(f"DELETE FROM {table}")
            affected += cursor.rowcount or 0
        conn.commit()
        return affected
    finally:
        conn.close()


def _main(argv=None) -> int:
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="声明哈希守卫状态查看 / 重置（含存量 guard 表）")
    parser.add_argument("--db", required=True, help="目标 SQLite 库路径")
    parser.add_argument("--status", action="store_true", help="打印所有守卫记录")
    parser.add_argument("--reset", nargs="?", const="all", default=None,
                        help="删除守卫记录：all（默认）或指定 scope_key")
    args = parser.parse_args(argv)

    if args.reset is not None:
        affected = reset(args.db, args.reset)
        print(f"已删除 {affected} 条守卫记录（scope={args.reset}）")
        return 0

    payload = status(args.db)
    if not payload:
        print("未发现任何守卫表")
        return 0
    for group in payload:
        print(f"[{group['table']}] {len(group['rows'])} 条")
        for row in group["rows"]:
            print("  " + json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())