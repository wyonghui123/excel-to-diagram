# -*- coding: utf-8 -*-
"""[单据流 Phase 3] 通用服务层（spec 2026-11-08-doc-flow-service-spec.md §6）。

职责：
- list_rules   : 规则目录 + UI 所需列元数据
- list_sources : 上游实例 + 已结量 / 未结量（单条 SQL，避免 N+1）
- derive       : 选择上游实例 -> 生成 / 追加下游对象（单事务）
- list_edges   : 单据流追溯（源侧 / 目标侧双口径）

约束：本模块不写业务常量，BO / 表 / 字段全部来自元数据与规则声明。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from meta.core.doc_flow_batch_engine import derive_batch
from meta.core.doc_flow_derive_engine import _consumed_in_pool, _num
from meta.core.doc_flow_rule_store import get_rule, list_rules
from meta.core.doc_flow_schema import DOC_FLOW_CONSUMED_VIEW
from meta.core.models import registry

_QTY_EPSILON = 1e-9
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class DocFlowServiceError(Exception):
    """服务层业务异常：code 直接作为 API 错误码。"""

    def __init__(self, code: str, message: str, status: int = 400,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


class DocFlowService:
    def __init__(self, app_ds, platform_ds):
        self.app_ds = app_ds
        self.platform_ds = platform_ds

    # ------------------------------------------------------------------ 规则
    def list_rules(self, source_bo: Optional[str] = None,
                   target_bo: Optional[str] = None) -> Dict[str, Any]:
        rules = list_rules(self.platform_ds, status="active")
        if source_bo:
            rules = [r for r in rules if r.get("source_bo") == source_bo]
        if target_bo:
            rules = [r for r in rules if r.get("target_bo") == target_bo]
        items = [self._rule_view(r) for r in rules]
        return {"rules": items, "total": len(items)}

    def _rule_view(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        source_obj = registry.get(rule.get("source_bo"))
        columns: List[Dict[str, str]] = []
        if source_obj is not None:
            for fid in rule.get("display_fields") or []:
                field = source_obj.get_field(fid)
                if field is not None:
                    columns.append({"field": fid, "label": field.name or fid})
        two_level = bool(rule.get("target_line_bo"))
        return {
            "rule_id": rule.get("rule_id"),
            "source_bo": rule.get("source_bo"),
            "target_bo": rule.get("target_bo"),
            "source_qty_field": rule.get("source_qty_field") or "quantity",
            "pool": rule.get("pool") or "default",
            "split_key": list(rule.get("split_key") or []),
            "target_line_bo": rule.get("target_line_bo") or "",
            "head_fk_field": rule.get("head_fk_field") or "",
            "display_fields": list(rule.get("display_fields") or []),
            "source_columns": columns,
            "allow_append": two_level,
            "append_label": "追加到当前单据" if two_level else "",
        }

    def _require_rule(self, rule_id: Optional[str]) -> Dict[str, Any]:
        rid = (rule_id or "").strip()
        rule = get_rule(self.platform_ds, rid) if rid else None
        if not rule:
            raise DocFlowServiceError(
                "DOC_FLOW_RULE_NOT_FOUND",
                "单据流规则不存在: {0}".format(rid), 404)
        if rule.get("status") != "active":
            raise DocFlowServiceError(
                "DOC_FLOW_RULE_NOT_FOUND",
                "单据流规则已停用: {0}".format(rid), 404)
        return rule

    def _source_meta(self, rule: Dict[str, Any]):
        obj = registry.get(rule.get("source_bo"))
        if obj is None:
            raise DocFlowServiceError(
                "DOC_FLOW_RULE_INVALID",
                "规则源对象未注册: {0}".format(rule.get("source_bo")), 409)
        id_field = obj.get_field("id")
        qty_field = obj.get_field(rule.get("source_qty_field") or "quantity")
        if id_field is None or qty_field is None:
            raise DocFlowServiceError(
                "DOC_FLOW_RULE_INVALID",
                "规则源字段缺失: {0}".format(rule.get("source_qty_field")), 409)
        return obj, id_field, qty_field

    # ------------------------------------------------------------------ 上游
    def list_sources(self, rule_id: str, filters: Optional[Dict[str, Any]] = None,
                     include_zero_open: bool = False, page: int = 1,
                     page_size: int = _DEFAULT_PAGE_SIZE,
                     source_item: str = "") -> Dict[str, Any]:
        rule = self._require_rule(rule_id)
        obj, id_field, qty_field = self._source_meta(rule)
        page = max(1, int(page or 1))
        page_size = min(_MAX_PAGE_SIZE, max(1, int(page_size or _DEFAULT_PAGE_SIZE)))

        used = {"source_id", "quantity", "consumed_qty"}
        display_fields: List[str] = []
        for fid in rule.get("display_fields") or []:
            field = obj.get_field(fid)
            if field is None or field.db_column in used:
                continue
            used.add(field.db_column)
            display_fields.append(fid)
        display_cols = [obj.get_field(fid).db_column for fid in display_fields]

        select_cols = [
            "s.{0} AS source_id".format(id_field.db_column),
            "s.{0} AS quantity".format(qty_field.db_column),
            "COALESCE(c.consumed_qty, 0) AS consumed_qty",
        ] + ["s.{0} AS {0}".format(col) for col in display_cols]

        from_sql = (
            " FROM {table} s LEFT JOIN {view} c"
            " ON c.source_bo = ? AND c.source_item = ? AND c.pool = ?"
            " AND c.source_id = CAST(s.{id_col} AS TEXT)"
        ).format(table=obj.table_name, view=DOC_FLOW_CONSUMED_VIEW,
                 id_col=id_field.db_column)

        where = ["1 = 1"]
        params: List[Any] = [
            rule.get("source_bo"), source_item or "",
            rule.get("pool") or "default",
        ]
        if not include_zero_open:
            where.append(
                "(s.{0} - COALESCE(c.consumed_qty, 0)) > ?".format(
                    qty_field.db_column))
            params.append(_QTY_EPSILON)
        for key, value in (filters or {}).items():
            if value in (None, ""):
                continue
            field = obj.get_field(key)
            if field is None:
                continue
            where.append("CAST(s.{0} AS TEXT) LIKE ?".format(field.db_column))
            params.append("%{0}%".format(value))
        where_sql = " WHERE " + " AND ".join(where)

        count_rows = self.app_ds.execute(
            "SELECT COUNT(*)" + from_sql + where_sql, tuple(params)).fetchall()
        total = int(count_rows[0][0]) if count_rows else 0

        rows = self.app_ds.execute(
            "SELECT " + ", ".join(select_cols) + from_sql + where_sql +
            " ORDER BY s.{0} LIMIT ? OFFSET ?".format(id_field.db_column),
            tuple(params + [page_size, (page - 1) * page_size]),
        ).fetchall()

        keys = ["source_id", "quantity", "consumed_qty"] + display_cols
        items: List[Dict[str, Any]] = []
        for row in rows:
            record = dict(zip(keys, row))
            quantity = _num(record.get("quantity"))
            consumed = _num(record.get("consumed_qty"))
            display_parts = [
                str(record.get(col)).strip()
                for col in display_cols
                if record.get(col) not in (None, "")
            ]
            split_values = {}
            for key in rule.get("split_key") or []:
                field = obj.get_field(key)
                if field is not None:
                    split_values[key] = record.get(field.db_column)
            display_values = {
                fid: record.get(obj.get_field(fid).db_column)
                for fid in display_fields
            }
            items.append({
                "source_id": record.get("source_id"),
                "source_item": source_item or "",
                "quantity": quantity,
                "consumed_qty": consumed,
                "open_qty": round(quantity - consumed, 6),
                "display": " / ".join(display_parts),
                "display_values": display_values,
                "split_key_values": split_values,
            })
        return {"items": items, "total": total,
                "page": page, "page_size": page_size}