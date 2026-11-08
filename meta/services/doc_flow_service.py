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