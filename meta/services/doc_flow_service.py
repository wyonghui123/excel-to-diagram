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

_ENGINE_ERROR_MAP = {
    "BATCH_EMPTY": ("DOC_FLOW_QTY_INVALID", 400),
    "RULE_NOT_FOUND": ("DOC_FLOW_RULE_NOT_FOUND", 404),
    "RULE_DEPRECATED": ("DOC_FLOW_RULE_NOT_FOUND", 404),
    "BO_NOT_REGISTERED": ("DOC_FLOW_RULE_INVALID", 409),
    "SOURCE_QTY_FIELD_MISSING": ("DOC_FLOW_RULE_INVALID", 409),
    "TARGET_LINE_BO_MISSING": ("DOC_FLOW_RULE_INVALID", 409),
    "HEAD_FK_NOT_FOUND": ("DOC_FLOW_RULE_INVALID", 409),
    "SPLIT_KEY_FIELD_MISSING": ("DOC_FLOW_SPLIT_KEY_FIELD_MISSING", 400),
    "SOURCE_ROW_NOT_FOUND": ("DOC_FLOW_SOURCE_NOT_FOUND", 404),
    "TARGET_ROW_NOT_FOUND": ("DOC_FLOW_TARGET_NOT_FOUND", 404),
    "INVALID_QUANTITY": ("DOC_FLOW_QTY_INVALID", 400),
    "OVER_DERIVE": ("DOC_FLOW_QTY_EXCEEDED", 409),
    "HEAD_LINE_MULTI_NOT_SUPPORTED": ("HEAD_LINE_MULTI_NOT_SUPPORTED", 409),
}


_EDGE_COLUMNS = (
    "id", "source_bo", "source_id", "source_item",
    "target_bo", "target_id", "target_item",
    "quantity", "quantity_sign", "rule_id", "status", "pool",
    "edge_kind", "reverses_edge_id", "unit",
    "derived_at", "derived_by",
)


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

    # ------------------------------------------------------------------ 派生
    def derive(self, payload: Dict[str, Any],
               derived_by: str = "") -> Dict[str, Any]:
        payload = payload or {}
        rule = self._require_rule(payload.get("rule_id"))
        target = payload.get("target") or {}
        mode = target.get("mode") or "create"
        two_level = bool(rule.get("target_line_bo"))

        if mode not in ("create", "append"):
            raise DocFlowServiceError(
                "DOC_FLOW_TARGET_MODE_INVALID",
                "target.mode 仅支持 create / append", 400)
        if mode == "append" and not two_level:
            raise DocFlowServiceError(
                "DOC_FLOW_TARGET_MODE_INVALID",
                "单表模式不支持追加，请使用 create", 400)
        if mode == "append" and target.get("id") in (None, ""):
            raise DocFlowServiceError(
                "DOC_FLOW_TARGET_MODE_INVALID",
                "append 模式必须提供目标单据 ID", 400)

        raw_sources = payload.get("sources") or []
        if not isinstance(raw_sources, list) or not raw_sources:
            raise DocFlowServiceError(
                "DOC_FLOW_QTY_INVALID", "sources 不能为空", 400)

        normalized: List[Dict[str, Any]] = []
        seen = set()
        for raw in raw_sources:
            if not isinstance(raw, dict):
                raise DocFlowServiceError(
                    "DOC_FLOW_QTY_INVALID", "sources 元素必须是对象", 400)
            source_id = raw.get("source_id")
            if source_id in (None, ""):
                raise DocFlowServiceError(
                    "DOC_FLOW_SOURCE_NOT_FOUND", "source_id 不能为空", 404)
            source_item = raw.get("source_item") or ""
            key = (str(source_id), source_item)
            if key in seen:
                raise DocFlowServiceError(
                    "DOC_FLOW_DUPLICATE_SOURCE",
                    "同一源行重复出现: {0}/{1}".format(source_id, source_item), 400)
            seen.add(key)
            quantity = raw.get("quantity")
            if quantity is not None:
                quantity = _num(quantity)
                if not math.isfinite(quantity) or quantity <= 0:
                    raise DocFlowServiceError(
                        "DOC_FLOW_QTY_INVALID",
                        "quantity 必须是大于 0 的有限数", 400)
            normalized.append({"source_id": source_id,
                               "source_item": source_item,
                               "quantity": quantity})

        head_overrides = None
        if mode == "append":
            head_overrides = {"id": target.get("id")}
            if isinstance(target.get("data"), dict):
                head_overrides.update(target["data"])

        with self.app_ds.transaction():
            self._assert_open_qty(rule, normalized)
            try:
                batch = derive_batch(
                    self.app_ds, self.platform_ds, rule["rule_id"],
                    normalized, head_overrides=head_overrides,
                    derived_by=derived_by)
            except Exception as exc:
                self._raise_mapped(exc)
        return self._derive_view(rule, batch)

    def _assert_open_qty(self, rule: Dict[str, Any],
                         items: List[Dict[str, Any]]) -> None:
        obj, id_field, qty_field = self._source_meta(rule)
        pool = rule.get("pool") or "default"
        for item in items:
            rows = self.app_ds.execute(
                "SELECT {0} FROM {1} WHERE {2} = ?".format(
                    qty_field.db_column, obj.table_name, id_field.db_column),
                (item["source_id"],),
            ).fetchall()
            if not rows:
                raise DocFlowServiceError(
                    "DOC_FLOW_SOURCE_NOT_FOUND",
                    "上游记录不存在: {0}".format(item["source_id"]), 404)
            total_qty = _num(rows[0][0])
            consumed = _consumed_in_pool(
                self.app_ds, rule.get("source_bo"), item["source_id"],
                item["source_item"], pool)
            open_qty = total_qty - consumed
            if item["quantity"] is None:
                if open_qty <= _QTY_EPSILON:
                    raise DocFlowServiceError(
                        "DOC_FLOW_QTY_INVALID",
                        "上游已结清，无可用数量: {0}".format(item["source_id"]), 400)
                item["quantity"] = open_qty
            elif item["quantity"] > open_qty + _QTY_EPSILON:
                raise DocFlowServiceError(
                    "DOC_FLOW_QTY_EXCEEDED", "本次生成数量超过未结量", 409,
                    {"source_id": item["source_id"],
                     "source_item": item["source_item"],
                     "open_qty": open_qty,
                     "requested": item["quantity"]})

    def _raise_mapped(self, exc: Exception) -> None:
        code = getattr(exc, "code", "")
        mapped = _ENGINE_ERROR_MAP.get(code)
        if mapped is None:
            raise exc
        new_code, status = mapped
        message = getattr(exc, "message", None) or str(exc)
        raise DocFlowServiceError(new_code, message, status)

    def _derive_view(self, rule: Dict[str, Any], batch) -> Dict[str, Any]:
        created: List[Dict[str, Any]] = []
        replayed: List[Dict[str, Any]] = []
        for result in batch.results:
            entry = {
                "source_id": result.source_id,
                "source_item": result.source_item,
                "target_id": result.target_id,
                "target_item": result.target_item,
                "quantity": result.quantity,
                "edge_id": result.edge_id,
            }
            (replayed if result.replay else created).append(entry)
        return {
            "target": {"bo": rule.get("target_bo"), "ids": list(batch.heads)},
            "created": created,
            "replayed": replayed,
            "totals": {
                "requested": len(created) + len(replayed),
                "written": batch.total_edges,
                "replayed": batch.skipped_replays,
            },
        }

    # ------------------------------------------------------------------ 追溯
    def list_edges(self, source_bo: Optional[str] = None,
                   source_id: Any = None,
                   source_item: Optional[str] = None,
                   target_bo: Optional[str] = None,
                   target_id: Any = None) -> Dict[str, Any]:
        if source_bo and source_id not in (None, ""):
            where = ["source_bo = ?", "source_id = ?"]
            params: List[Any] = [source_bo, str(source_id)]
            if source_item is not None:
                where.append("source_item = ?")
                params.append(source_item)
        elif target_bo and target_id not in (None, ""):
            where = ["target_bo = ?", "target_id = ?"]
            params = [target_bo, str(target_id)]
        else:
            raise DocFlowServiceError(
                "DOC_FLOW_EDGE_FILTER_REQUIRED",
                "必须提供 source_bo+source_id 或 target_bo+target_id", 400)

        rows = self.app_ds.execute(
            "SELECT " + ", ".join(_EDGE_COLUMNS) + " FROM doc_flow_edges"
            " WHERE " + " AND ".join(where) +
            " ORDER BY derived_at, id",
            tuple(params),
        ).fetchall()
        items = [dict(zip(_EDGE_COLUMNS, row)) for row in rows]
        return {"items": items, "total": len(items)}