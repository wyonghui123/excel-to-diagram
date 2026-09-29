# -*- coding: utf-8 -*-
"""[单据流 Phase 1] doc_flow_rule 规则注册表（平台库）

职责:
- 平台库内 `doc_flow_rule` 物理表的建表 + 启动期幂等 upsert + 读取
- 规则是运行时数据（可运维、可热改 status），不用 YAML——对比先例：
  resource_types.yaml 是静态能力表，而规则需要 status 生命周期演进（spec §5.1）

status 生命周期分离原则:
- app.yaml 声明的是**能力**（source_bo/target_bo/pool/hook 列位）→ upsert 管理
- `status`（active/deprecated）是**运行态**（运维停新不禁旧）→ upsert 不覆盖，
  仅 set_rule_status 显式变更（spec §5.2：deprecated 拒新派生、不影响历史边）

对应方案: docs/superpowers/specs/2026-09-29-doc-flow-phase1-spec.md §5
          docs/superpowers/specs/2026-09-29-doc-flow-phase2-spec.md §4
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RULE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_rule (
    rule_id         TEXT PRIMARY KEY,
    source_bo       TEXT NOT NULL,
    target_bo       TEXT NOT NULL,
    source_qty_field TEXT NOT NULL DEFAULT 'quantity',
    pool            TEXT NOT NULL DEFAULT 'default',
    status          TEXT NOT NULL DEFAULT 'active',
    check_hook      TEXT,
    map_hook        TEXT,
    create_hook     TEXT,
    field_map       TEXT NOT NULL DEFAULT '{}',
    split_key       TEXT NOT NULL DEFAULT '[]',
    target_line_bo  TEXT NOT NULL DEFAULT '',
    head_fk_field   TEXT NOT NULL DEFAULT '',
    created_at      TEXT,
    updated_at      TEXT
)
"""

# [Phase 2 §4.2] 存量部署的幂等加列清单（CREATE IF NOT EXISTS 不会给旧表加列）
# 约束：SQLite ALTER TABLE ADD COLUMN 只能追加带默认值的列——四列均满足。
_ADDED_COLUMNS = (
    ("field_map", "TEXT NOT NULL DEFAULT '{}'"),
    ("split_key", "TEXT NOT NULL DEFAULT '[]'"),
    ("target_line_bo", "TEXT NOT NULL DEFAULT ''"),
    ("head_fk_field", "TEXT NOT NULL DEFAULT ''"),
)

# upsert 覆盖的"声明字段"（status 是运行态，刻意不在列）
_UPSERT_DECL_FIELDS = (
    "source_bo", "target_bo", "source_qty_field", "pool",
    "check_hook", "map_hook", "create_hook",
    "field_map", "split_key", "target_line_bo", "head_fk_field",
)

RULE_COLUMNS = ("rule_id",) + _UPSERT_DECL_FIELDS + (
    "status", "created_at", "updated_at",
)


def _as_json_text(value: Any, default: str) -> str:
    """把声明值( dict/list )序列化为 JSON 文本；已是文本则原样保留。"""
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(text: Any, fallback: Any) -> Any:
    """解析 JSON 文本列；空/非法时回退默认值（不因运维误改崩启动）。"""
    if text is None or text == "":
        return fallback
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        logger.warning("[DocFlow] 规则 JSON 列解析失败，回退默认值: %r", text)
        return fallback


def _ensure_columns(data_source) -> None:
    """存量部署的幂等加列（SQLite: PRAGMA 探测 → ALTER TABLE ADD COLUMN）。"""
    rows = data_source.execute("PRAGMA table_info(doc_flow_rule)").fetchall()
    existing = {row[1] for row in rows}
    for col, ddl in _ADDED_COLUMNS:
        if col not in existing:
            data_source.execute(
                "ALTER TABLE doc_flow_rule ADD COLUMN {0} {1}".format(col, ddl)
            )


def ensure_doc_flow_rule_table(data_source) -> None:
    """在平台库建 doc_flow_rule 表（幂等，启动期调用）。

    建表后追加一次幂等列迁移：Phase 1 时期的旧表不会因 DDL 变更自动加列，
    故此处显式 ALTER（spec §4.2）。
    """
    data_source.execute(RULE_TABLE_DDL)
    _ensure_columns(data_source)


def upsert_rules(data_source, rules: List[Dict[str, Any]]) -> int:
    """把应用声明的规则幂等写入平台库（启动期；先例 = _sync_app_permissions 范式）。

    - 已存在 → 只更新声明字段（**不覆盖 status**，见模块 docstring）
    - 新增 → status='active'，补 created_at

    Args:
        data_source: 平台库数据源
        rules: 规则字典列表，键 = RULE_COLUMNS 子集
               （rule_id/source_bo/target_bo 必填；
                source_qty_field/pool/check_hook/map_hook/create_hook 可选）

    Returns:
        处理的规则条数
    """
    now = datetime.now().isoformat(timespec="seconds")
    count = 0
    for rule in rules:
        rule_id = rule["rule_id"]
        data_source.execute(
            """INSERT INTO doc_flow_rule
               (rule_id, source_bo, target_bo, source_qty_field, pool,
                check_hook, map_hook, create_hook,
                field_map, split_key, target_line_bo, head_fk_field,
                status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
               ON CONFLICT(rule_id) DO UPDATE SET
                 source_bo = excluded.source_bo,
                 target_bo = excluded.target_bo,
                 source_qty_field = excluded.source_qty_field,
                 pool = excluded.pool,
                 check_hook = excluded.check_hook,
                 map_hook = excluded.map_hook,
                 create_hook = excluded.create_hook,
                 field_map = excluded.field_map,
                 split_key = excluded.split_key,
                 target_line_bo = excluded.target_line_bo,
                 head_fk_field = excluded.head_fk_field,
                 updated_at = excluded.updated_at""",
            (
                rule_id,
                rule.get("source_bo", ""),
                rule.get("target_bo", ""),
                rule.get("source_qty_field") or "quantity",
                rule.get("pool") or "default",
                rule.get("check_hook") or None,
                rule.get("map_hook") or None,
                rule.get("create_hook") or None,
                _as_json_text(rule.get("field_map"), "{}"),
                _as_json_text(rule.get("split_key"), "[]"),
                rule.get("target_line_bo") or "",
                rule.get("head_fk_field") or "",
                now, now,
            ),
        )
        count += 1
    return count


def get_rule(data_source, rule_id: str) -> Optional[Dict[str, Any]]:
    """按 rule_id 读规则；不存在返回 None（derive 引擎的前置校验入口）。

    `field_map` / `split_key` 两个 JSON 列在此解析为 Python 对象
    （dict / list），消费方无需再关心存储形态。
    """
    rows = data_source.execute(
        "SELECT {0} FROM doc_flow_rule WHERE rule_id = ?".format(
            ", ".join(RULE_COLUMNS)
        ),
        (rule_id,),
    ).fetchall()
    if not rows:
        return None
    rule = dict(zip(RULE_COLUMNS, rows[0]))
    rule["field_map"] = _loads(rule.get("field_map"), {})
    rule["split_key"] = _loads(rule.get("split_key"), [])
    return rule


def set_rule_status(data_source, rule_id: str, status: str) -> bool:
    """显式变更规则运行态（active/deprecated）；返回是否命中规则行。

    deprecated 语义 = 停新不禁旧：新派生被拒，历史边查询不受影响（spec §8.8）。
    """
    if status not in ("active", "deprecated"):
        raise ValueError(f"非法规则状态: {status}（须为 active/deprecated）")
    now = datetime.now().isoformat(timespec="seconds")
    cursor = data_source.execute(
        "UPDATE doc_flow_rule SET status = ?, updated_at = ? WHERE rule_id = ?",
        (status, now, rule_id),
    )
    return bool(getattr(cursor, "rowcount", 0))
