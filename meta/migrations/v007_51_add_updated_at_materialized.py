# -*- coding: utf-8 -*-
"""
[V007.51] Phase 2: 审计派生字段物化 — updated_at 物化列 + Backfill
[V007.52] SSOT 化：目标表从 _audit_materialization.yaml 读取

背景:
  audit_derived_fields.py 每次请求跑 MAX(created_at) FROM v_audit_all
  WHERE action='UPDATE' GROUP BY object_id，在 265K 行上性能差。

方案:
  1. 给 audit_callback 策略的表添加物化列
  2. 从 v_audit_all 回填 (Backfill)
  3. 审计异步写入完成后同步更新物化列（应用层回调，不用 SQLite 触发器）
  4. 读取路径优先读物化列，fallback 到 v_audit_all

策略目标表 (来自 SSOT _audit_materialization.yaml):
  - enum_types, enum_values, users
  - 新表加 updated_at 时，只需在 SSOT 加一行

设计:
  - 物化列类型: TEXT（存 ISO 字符串，与 audit_logs.created_at 一致）
  - 默认值: NULL（非 CURRENT_TIMESTAMP，避免与审计不一致）
  - Backfill: UPDATE <table> SET updated_at = (
      SELECT MAX(created_at) FROM v_audit_all
      WHERE object_type='<type>' AND object_id=<table>.id AND action='UPDATE'
    ) WHERE updated_at IS NULL
  - 幂等: ALTER TABLE ADD COLUMN 已有列时跳过（SQLite 会报错，需 try/except）

版本: v007.51 → V007.52 SSOT 化
日期: 2026-07-14
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def _get_target_tables() -> List[Tuple[str, str]]:
    """[V007.52 SSOT] 从 MaterializationRegistry 读取 audit_callback 目标表

    Returns:
        list of (table_name, object_type) tuples
    """
    try:
        from meta.core.materialization_registry import get_registry
        return get_registry().get_audit_callback_tables()
    except Exception as e:
        logger.warning(
            "[V007.51] Failed to load SSOT registry, using hardcoded fallback: %s", e
        )
        # Fallback：SSOT 加载失败时使用（仅限启动早期或测试环境）
        return [
            ("enum_types", "enum_type"),
            ("enum_values", "enum_value"),
            ("users", "user"),
        ]


# 向后兼容：保留旧名称（延迟加载）
_TABLES_TO_MATERIALIZE: List[Tuple[str, str]] = []

# 已有 updated_at 物理列但不走审计派生的表（仅文档记录，不操作）
_TABLES_WITH_UPDATED_AT_ALREADY = [
    "roles", "user_groups",
    "ai_async_tasks", "filter_variants",
    "scheduled_tasks", "task_workers", "task_definitions",
    "permission_bundles",
]


def _column_exists(cur, table_name: str, column_name: str) -> bool:
    """检查表中是否已存在某列"""
    cur.execute(f"PRAGMA table_info({table_name})")
    return any(col[1] == column_name for col in cur.fetchall())


def _view_exists(cur) -> bool:
    """检查 v_audit_all VIEW 是否存在"""
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='v_audit_all'"
    )
    return cur.fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """执行 v007_51 迁移：添加物化列 + Backfill

    Args:
        db_path: architecture.db 路径
        skip_backup: True 时跳过 DB 备份（Phase 1 已备份过 / 启动时重复调用）

    Returns:
        True 迁移成功
    """
    if not db_path.exists():
        logger.error(f"[V007.51] DB not found: {db_path}")
        return False

    # [V007.52 SSOT] 从注册表读取目标表
    target_tables = _get_target_tables()
    if not target_tables:
        logger.warning("[V007.51] No audit_callback tables found in SSOT, skipping")
        return True

    # 幂等检查：如果所有目标表都已有 updated_at 列，跳过
    conn_check = sqlite3.connect(str(db_path))
    cur_check = conn_check.cursor()
    all_exist = all(
        _column_exists(cur_check, tbl, "updated_at")
        for tbl, _ in target_tables
    )
    conn_check.close()
    if all_exist:
        logger.info("[V007.51] All target tables already have updated_at, skipping")
        return True

    # 备份
    if not skip_backup:
        import shutil
        bak_path = str(db_path) + ".bak.v00751"
        if not Path(bak_path).exists():
            logger.info(f"[V007.51] Backing up DB to {bak_path}")
            shutil.copy2(str(db_path), bak_path)

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = DELETE")  # 安全模式，避免 WAL 并发问题
    cur = conn.cursor()

    try:
        # Step 1: 添加物化列
        for table_name, _ in target_tables:
            if _column_exists(cur, table_name, "updated_at"):
                logger.info(f"[V007.51] {table_name}.updated_at already exists, skipping ADD COLUMN")
                continue
            try:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN updated_at TEXT")
                logger.info(f"[V007.51] Added updated_at TEXT to {table_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"[V007.51] {table_name}.updated_at already exists (duplicate)")
                else:
                    raise

        conn.commit()

        # Step 2: Backfill from v_audit_all
        if _view_exists(cur):
            for table_name, object_type in target_tables:
                logger.info(f"[V007.51] Backfilling {table_name}.updated_at from v_audit_all (object_type={object_type})...")
                cur.execute(f"""
                    UPDATE {table_name}
                    SET updated_at = (
                        SELECT MAX(va.created_at)
                        FROM v_audit_all va
                        WHERE va.object_type = ?
                          AND va.object_id = {table_name}.id
                          AND va.action = 'UPDATE'
                    )
                    WHERE updated_at IS NULL
                """, (object_type,))
                updated = cur.rowcount
                logger.info(f"[V007.51] {table_name}: backfilled {updated} rows")

                # 没有 UPDATE 审计记录的行，fallback 为 created_at
                cur.execute(f"""
                    UPDATE {table_name}
                    SET updated_at = created_at
                    WHERE updated_at IS NULL AND created_at IS NOT NULL
                """)
                fallback = cur.rowcount
                if fallback:
                    logger.info(f"[V007.51] {table_name}: fallback {fallback} rows to created_at")
        else:
            # v_audit_all 不存在，fallback 从 audit_logs (热表) 回填
            logger.warning("[V007.51] v_audit_all not found, backfilling from audit_logs (hot table only)")
            for table_name, object_type in target_tables:
                cur.execute(f"""
                    UPDATE {table_name}
                    SET updated_at = (
                        SELECT MAX(al.created_at)
                        FROM audit_logs al
                        WHERE al.object_type = ?
                          AND al.object_id = {table_name}.id
                          AND al.action = 'UPDATE'
                    )
                    WHERE updated_at IS NULL
                """, (object_type,))
                updated = cur.rowcount
                logger.info(f"[V007.51] {table_name}: backfilled {updated} rows from audit_logs")

                cur.execute(f"""
                    UPDATE {table_name}
                    SET updated_at = created_at
                    WHERE updated_at IS NULL AND created_at IS NOT NULL
                """)

        conn.commit()
        logger.info("[V007.51] Migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"[V007.51] Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def refresh_materialized_updated_at(conn, object_type: str, object_id) -> None:
    """刷新单个对象的物化 updated_at（在审计写入后调用）

    由 audit_async_queue._do_flush_batch 成功后回调。
    直接使用传入的连接（同一事务内或独立事务均可）。

    Args:
        conn: sqlite3.Connection
        object_type: 审计对象类型（如 'user', 'enum_type'）
        object_id: 审计对象 ID
    """
    try:
        from meta.core.materialization_registry import get_registry
        entry = get_registry().get_by_object_type(object_type)
        if not entry:
            return  # 未注册的 object_type
        if entry.get("strategy") != "audit_callback":
            return  # 不是 audit_callback 策略
        table_name = entry["name"]

        # 从 v_audit_all 获取最新 UPDATE 时间
        row = conn.execute(
            "SELECT MAX(created_at) FROM v_audit_all "
            "WHERE object_type = ? AND object_id = ? AND action = 'UPDATE'",
            (object_type, str(object_id)),
        ).fetchone()

        new_val = row[0] if row and row[0] else None

        if new_val:
            conn.execute(
                f"UPDATE {table_name} SET updated_at = ? WHERE id = ?",
                (new_val, object_id),
            )
        # 没有 UPDATE 审计记录时不更新（保留 created_at fallback 值）
    except Exception as e:
        # 物化列更新失败不应阻断审计写入主流程
        logger.warning(
            "[V007.51] refresh_materialized_updated_at failed for %s/%s: %s",
            object_type, object_id, e,
        )


def batch_refresh_materialized_updated_at(conn, updates: list) -> None:
    """批量刷新物化 updated_at（审计批量 flush 后调用）

    Args:
        conn: sqlite3.Connection
        updates: list of (object_type, object_id) tuples
    """
    if not updates:
        return

    try:
        from meta.core.materialization_registry import get_registry
        from collections import defaultdict
        registry = get_registry()

        # 按 object_type 分组，减少查询次数
        by_type = defaultdict(list)
        for obj_type, obj_id in updates:
            entry = registry.get_by_object_type(obj_type)
            if entry and entry.get("strategy") == "audit_callback":
                by_type[obj_type].append(str(obj_id))

        for object_type, obj_ids in by_type.items():
            entry = registry.get_by_object_type(object_type)
            if not entry:
                continue
            table_name = entry["name"]

            try:
                placeholders = ",".join(["?" for _ in obj_ids])
                rows = conn.execute(
                    f"SELECT object_id, MAX(created_at) as max_created "
                    f"FROM v_audit_all "
                    f"WHERE object_type = ? AND object_id IN ({placeholders}) "
                    f"AND action = 'UPDATE' "
                    f"GROUP BY object_id",
                    [object_type] + obj_ids,
                ).fetchall()

                for row in rows:
                    oid = row[0]
                    max_created = row[1]
                    if max_created:
                        conn.execute(
                            f"UPDATE {table_name} SET updated_at = ? WHERE id = ?",
                            (max_created, oid),
                        )
            except Exception as e:
                logger.warning(
                    "[V007.51] batch_refresh failed for %s (%d items): %s",
                    object_type, len(obj_ids), e,
                )
    except Exception as e:
        logger.warning("[V007.51] batch_refresh_materialized_updated_at failed: %s", e)