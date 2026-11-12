# -*- coding: utf-8 -*-
"""DOC_FLOW BO Action handlers（spec §9.3.13 S1 / S3 接缝）。

- ``doc_flow.derive``  : Workflow ``system``/``cron`` 任务建单；幂等由规则
  ``derive_key`` 保证，重复执行返回 ``replayed``。
- ``doc_flow.reverse`` : 补偿任务执行 E6 三档冲销 + 追加补偿事实。

handler 契约与其它 BO Action 一致::

    handler(params: dict, context: dict) -> {"success": bool, "data": ..., "message": str}

``data`` 会被 ``BOActionExecutor._extract_outputs`` 写入 ``task.outputs``，
供 S2（inputs 注入）/ S3（补偿）/ S5（trace 关联）消费。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from meta.core.doc_flow_reversal import (
    compensate_edge,
    counter_edge,
    red_ink_edge,
    reverse_edge,
)
from meta.services.doc_flow_service import get_doc_flow_service

logger = logging.getLogger(__name__)

#: 补偿 mode 归一化：语义名 + 历史函数名双兼容
_MODE_ALIASES = {
    "cancel": "cancel", "reverse": "cancel", "reverse_edge": "cancel",
    "partial": "partial", "counter": "partial", "counter_edge": "partial",
    "update": "update", "red_ink": "update", "red_ink_edge": "update",
    "compensate": "compensate", "compensate_edge": "compensate",
    "none": "none",
}

#: 需要业务权威锚（ref_id）的档位
_REF_REQUIRED_MODES = ("partial", "update", "compensate")


def _error(code: str, message: str) -> Dict[str, Any]:
    return {"success": False, "data": None, "message": message, "code": code}


def _exception_payload(error: Exception) -> Dict[str, Any]:
    code = str(getattr(error, "code", "") or "")
    message = str(getattr(error, "message", "") or error)
    if code:
        return _error(code, message)
    logger.exception("[DocFlow] BO Action 执行异常")
    return _error("DOC_FLOW_ACTION_FAILED", message)


def _derive_payload(params: Dict[str, Any]) -> Dict[str, Any]:
    """把 Action 入参翻译成 ``DocFlowService.derive()`` 的 payload。

    ``sources`` 允许「源单 id 列表」的简化形态（自动补 ``source_item=''``）；
    ``head_overrides`` 合并进 ``target.data``（append 模式抬头覆写）。
    """
    raw_sources = params.get("sources") or []
    sources: List[Dict[str, Any]] = []
    for item in raw_sources:
        if isinstance(item, dict):
            sources.append(dict(item))
        elif item not in (None, ""):
            sources.append({"source_id": item, "source_item": ""})

    payload: Dict[str, Any] = {
        "rule_id": params.get("rule_id"),
        "sources": sources,
    }
    target = params.get("target")
    target = dict(target) if isinstance(target, dict) else {}
    overrides = params.get("head_overrides")
    if isinstance(overrides, dict) and overrides:
        merged = dict(target.get("data") or {})
        merged.update(overrides)
        target["data"] = merged
    if target:
        payload["target"] = target
    return payload


def doc_flow_derive_handler(params: Dict[str, Any],
                            context: Optional[Dict[str, Any]] = None
                            ) -> Dict[str, Any]:
    """``doc_flow.derive``：按规则批量派生下游单据（A 档 create/append）。"""
    params = params or {}
    context = context or {}
    try:
        service = get_doc_flow_service()
        result = service.derive(
            _derive_payload(params),
            derived_by=str(context.get("run_as") or ""),
            trace_id=str(context.get("trace_id") or ""),
        )
    except Exception as error:  # noqa: BLE001 - 业务异常归一为 success=False
        return _exception_payload(error)

    created = list(result.get("created") or [])
    replayed = list(result.get("replayed") or [])
    edge_ids = [entry.get("edge_id") for entry in created + replayed
                if entry.get("edge_id")]
    target_ids = list((result.get("target") or {}).get("ids") or [])
    return {
        "success": True,
        "data": {
            "created": created,
            "replayed": replayed,
            "target_ids": target_ids,
            "edge_ids": edge_ids,
            "totals": result.get("totals") or {},
        },
        "message": "已生成 {0} 条下游边（重放 {1} 条）".format(
            len(created), len(replayed)),
    }


def _normalize_mode(mode: Any) -> str:
    key = str(mode or "cancel").strip().lower()
    normalized = _MODE_ALIASES.get(key)
    if normalized is None:
        raise ValueError("未知补偿 mode: {0}".format(mode))
    return normalized


def _edge_ids(params: Dict[str, Any]) -> List[str]:
    raw = params.get("edge_ids")
    if raw in (None, ""):
        raw = params.get("edge_id")
    if raw in (None, ""):
        raw = params.get("orig_edge_id")
    if raw in (None, ""):
        return []
    if isinstance(raw, (list, tuple)):
        return [str(value) for value in raw if value not in (None, "")]
    return [str(raw)]


def doc_flow_reverse_handler(params: Dict[str, Any],
                             context: Optional[Dict[str, Any]] = None
                             ) -> Dict[str, Any]:
    """``doc_flow.reverse``：补偿任务执行 E6 冲销（mode 见 spec §9.3.13 S3）。

    档位映射（以 ``doc_flow_reversal`` 代码语义为准）:
        cancel     → ``reverse_edge``      A 档全冲销
        partial    → ``counter_edge``      B 档部分冲销（反向新边）
        update     → ``red_ink_edge``      C 档数量调整（同方向红字边）
        compensate → ``compensate_edge``   追加补偿事实边
    """
    params = params or {}
    context = context or {}
    try:
        mode = _normalize_mode(params.get("mode"))
    except ValueError as error:
        return _error("DOC_FLOW_ACTION_FAILED", str(error))
    if mode == "none":
        return {"success": True, "data": {"mode": mode, "skipped": True,
                                          "edge_ids": []},
                "message": "mode=none，跳过执行"}
    edge_ids = _edge_ids(params)
    if not edge_ids:
        return _error("EDGE_NOT_FOUND", "补偿任务缺少 edge_ids")

    ref_id = str(params.get("ref_id") or "")
    if mode in _REF_REQUIRED_MODES and not ref_id:
        return _error("REF_ID_REQUIRED",
                      "mode={0} 必须携带业务权威锚 ref_id".format(mode))

    derived_by = str(context.get("run_as") or "")
    quantity = params.get("quantity")
    return_rule_id = str(params.get("return_rule_id") or "")
    target_data = params.get("target_data")

    reversed_ids: List[str] = []
    created_ids: List[str] = []
    replayed: List[str] = []
    try:
        service = get_doc_flow_service()
        for edge_id in edge_ids:
            if mode == "cancel":
                result = reverse_edge(service.app_ds, edge_id,
                                      reversed_by=derived_by)
                if result.replay:
                    replayed.append(result.edge_id)
                else:
                    reversed_ids.append(result.edge_id)
                    reversed_ids.extend(result.cascaded_edges or [])
            elif mode == "partial":
                result = counter_edge(
                    service.app_ds, service.platform_ds, edge_id,
                    return_rule_id=return_rule_id, quantity=quantity,
                    ref_id=ref_id, target_data=target_data,
                    derived_by=derived_by)
            elif mode == "update":
                result = red_ink_edge(service.app_ds, edge_id,
                                      quantity=quantity, ref_id=ref_id,
                                      derived_by=derived_by)
            else:  # compensate
                result = compensate_edge(service.app_ds, edge_id,
                                         ref_id=ref_id, derived_by=derived_by)
            if mode != "cancel":
                if result.replay:
                    replayed.append(result.edge_id)
                else:
                    created_ids.append(result.edge_id)
    except Exception as error:  # noqa: BLE001 - 失败归位 failed，交由 retry_policy
        return _exception_payload(error)

    return {
        "success": True,
        "data": {
            "mode": mode,
            "reversed_edge_ids": reversed_ids,
            "created_edge_ids": created_ids,
            "edge_ids": reversed_ids + created_ids,
            "replayed": replayed,
            "replay": bool(replayed) and not (reversed_ids or created_ids),
        },
        "message": "mode={0}：冲销 {1} 条，新建 {2} 条，重放 {3} 条".format(
            mode, len(reversed_ids), len(created_ids), len(replayed)),
    }