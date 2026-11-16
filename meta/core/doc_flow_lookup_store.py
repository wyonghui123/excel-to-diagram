# -*- coding: utf-8 -*-
"""单据流映射码表存储（M4：`lookup_ref` 钩子的数据源）。

依据: docs/specs/spec-integration-module-2026-11-15.md §5.2
  - 映射链第 4 环 `lookup_ref`：``{目标字段: lookup_code}``，把已映射值经码表
    转成目标值（等价 OIC 的 Lookup 对象）。
  - 码表缺失/键不存在时返回 None，由调用方（派生引擎）决定是否报错。

单一事实模型：码表是配置对象（与 doc_flow_rule 同库），不是事实流水。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 码表物理表名
LOOKUP_TABLE = "doc_flow_lookup"

LOOKUP_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_lookup (
    lookup_code  TEXT NOT NULL,
    source_value TEXT NOT NULL,
    target_value TEXT,
    description  TEXT NOT NULL DEFAULT '',
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT,
    updated_at   TEXT,
    PRIMARY KEY (lookup_code, source_value)
)
"""

LOOKUP_TABLE_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_doc_flow_lookup_code "
    "ON doc_flow_lookup(lookup_code)"
)


def ensure_doc_flow_lookup_table(platform_ds) -> None:
    """幂等建表（平台库；旧库启动时自动补齐）。"""
    platform_ds.execute(LOOKUP_TABLE_DDL)
    platform_ds.execute(LOOKUP_TABLE_INDEX_DDL)


def _text(value) -> str:
    return "" if value is None else str(value)


def resolve_lookup(platform_ds, lookup_code: str,
                   source_value) -> "str | None":
    """按 ``(lookup_code, source_value)`` 取目标值。

    Returns:
        命中且启用 → 目标值（可能是空串）；码表/键不存在 → None。
    """
    if not lookup_code:
        return None
    rows = platform_ds.execute(
        "SELECT target_value FROM " + LOOKUP_TABLE +
        " WHERE lookup_code = ? AND source_value = ? AND is_active = 1",
        (str(lookup_code), _text(source_value)),
    ).fetchall()
    if not rows:
        return None
    return _text(rows[0][0])


def load_lookup_map(platform_ds, lookup_code: str) -> dict:
    """整表载入某码表（供派生引擎单批缓存，避免逐行查询）。"""
    rows = platform_ds.execute(
        "SELECT source_value, target_value FROM " + LOOKUP_TABLE +
        " WHERE lookup_code = ? AND is_active = 1",
        (str(lookup_code),),
    ).fetchall()
    return {_text(src): _text(tgt) for src, tgt in rows}


def upsert_lookup_values(platform_ds, rows) -> int:
    """批量写码表（幂等 upsert），返回写入条数。

    rows: ``[{"lookup_code": ..., "source_value": ..., "target_value": ...,
              "description": ...}, ...]``
    """
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")
    sql = (
        "INSERT INTO " + LOOKUP_TABLE +
        " (lookup_code, source_value, target_value, description, is_active,"
        "  created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)"
        " ON CONFLICT(lookup_code, source_value) DO UPDATE SET"
        "   target_value = excluded.target_value,"
        "   description = excluded.description,"
        "   is_active = 1,"
        "   updated_at = excluded.updated_at"
    )
    count = 0
    for row in rows or []:
        code = _text(row.get("lookup_code"))
        src = _text(row.get("source_value"))
        if not code or not src:
            raise ValueError("lookup_code / source_value 不能为空")
        platform_ds.execute(sql, (
            code, src, _text(row.get("target_value")),
            _text(row.get("description")), now, now,
        ))
        count += 1
    return count


def list_lookup_values(platform_ds, lookup_code: "str | None" = None) -> list:
    """列码表行（可按 lookup_code 过滤），按 code + source_value 排序。"""
    sql = (
        "SELECT lookup_code, source_value, target_value, description, is_active"
        " FROM " + LOOKUP_TABLE
    )
    params: tuple = ()
    if lookup_code:
        sql += " WHERE lookup_code = ?"
        params = (str(lookup_code),)
    sql += " ORDER BY lookup_code, source_value"
    cursor = platform_ds.execute(sql, params)
    columns = [d[0] for d in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]