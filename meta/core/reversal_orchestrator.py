# -*- coding: utf-8 -*-
"""业务单据冲销统一入口。

两条路径并存（规格 §10 M5：旧实现保留一版）：

1. **档位分派**（:func:`reverse_document` / :func:`reverse_document_edges`）：
   由 ``reversal_profiles`` 声明 A/B/C 档，直接调 ``doc_flow_reversal`` 边引擎；
2. **ReversalOrchestrator**（:func:`execute`，阶段 D1）：
   读取 schema ``doc_effect`` 声明，按固定 7 步（resolve → guard → txn →
   faces → project → state → commit）执行，自持事务。

未声明 ``doc_effect.reversal`` 的对象调用 ``execute`` → ``REVERSAL_NOT_DECLARED``（D8）。

对应方案: docs/specs/spec-reversal-platform-2026-11-06.md §7 / §8
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.doc_effect_validator import (
    DocEffectDeclarationError,
    validate_object,
)
from meta.core.doc_flow_reversal import counter_edge, red_ink_edge, reverse_edge
from meta.core.reversal_primitives import (
    ReversalContext,
    get_doc_creator,
    get_primitive,
)
from meta.core.reversal_profiles import (
    MODE_COUNTER,
    MODE_RED_INK,
    MODE_RED_REVERSE,
    get_profile,
)

logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\}")
_FULL_PLACEHOLDER_RE = re.compile(
    r"^\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\}$")

# 判定某写面是否产生了事实（strict 模式用）
_FACT_KEYS = ("txn_ids", "created", "count", "reversed", "updated",
              "unfulfilled", "compensated")


class ReversalError(Exception):
    """逆向守卫拒绝 / 声明错误 / 原语失败统一异常（规格 §8.4）。"""

    def __init__(self, code: str, message: str,
                 field_name: str = "", rule: str = ""):
        super().__init__("[{0}] {1}".format(code, message))
        self.code = code
        self.message = message
        self.field_name = field_name
        self.rule = rule


@dataclass
class ReversalOutcome:
    doc_id: Any
    to_state: str
    replay: bool = False
    faces: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    projections: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    document: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# 既有档位分派（兼容期保留）
# ─────────────────────────────────────────────────────────────────────────────

def resolve_mode(document_type):
    """返回单据的冲销档位。"""
    return get_profile(document_type)['mode']


def _require_reason(document_type, profile, reason):
    if profile['reason_required'] and not (reason or '').strip():
        raise ValueError('{0} 冲销原因必填'.format(document_type))


def reverse_document(app_ds, platform_ds, document_type, *, edge_id,
                     reason, ref_id, quantity=None, return_rule_id=None,
                     target_data=None):
    """单边冲销；档位由 profile 决定，承诺处理由调用方钩子承担。"""
    profile = get_profile(document_type)
    _require_reason(document_type, profile, reason)
    mode = profile['mode']

    if mode == MODE_RED_REVERSE:
        red_ink_edge(app_ds, edge_id, quantity=quantity,
                     ref_id=str(ref_id), derived_by=reason)
        return reverse_edge(app_ds, edge_id, reversed_by=reason)
    if mode == MODE_COUNTER:
        return counter_edge(app_ds, platform_ds, edge_id,
                            return_rule_id=return_rule_id,
                            quantity=quantity, ref_id=ref_id,
                            target_data=target_data, derived_by=reason)
    return red_ink_edge(app_ds, edge_id, quantity=quantity,
                        ref_id=str(ref_id), derived_by=reason)


def reverse_document_edges(app_ds, platform_ds, document_type, source_id, *,
                           ref_id, reason):
    """按 profile 声明的边锚点，整体冲销某源对象的全部 active 正向边。

    边表缺失 / 单边失败由 doc_flow_attach 降级为告警，不阻断业务红冲。
    """
    profile = get_profile(document_type)
    _require_reason(document_type, profile, reason)
    if profile['mode'] != MODE_RED_REVERSE:
        raise ValueError(
            '{0} 档位 {1} 不支持按源整体冲销'.format(
                document_type, profile['mode']))
    if source_id in (None, ''):
        return 0

    from meta.core.doc_flow_attach import reverse_edges_by_source

    total = 0
    for edge in profile['edges']:
        total += reverse_edges_by_source(
            app_ds, edge['rule_id'], edge['source_bo'], source_id,
            ref_id=ref_id, derived_by=reason)
    return total


# ─────────────────────────────────────────────────────────────────────────────
# ReversalOrchestrator（阶段 D1）
# ─────────────────────────────────────────────────────────────────────────────

def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _load_schema(schema_id: str):
    """取 schema；测试可 monkeypatch 本函数注入 fake schema。"""
    from meta.core.models import registry
    return registry.get(schema_id)


def _declaration(schema: Any) -> Dict[str, Any]:
    doc_effect = _get(schema, "doc_effect") or {}
    if not isinstance(doc_effect, dict):
        return {}
    return doc_effect


def _table_name(schema: Any) -> str:
    table = str(_get(schema, "table_name", "") or "")
    if not _IDENT_RE.match(table):
        raise ReversalError("REVERSAL_DECL_INVALID",
                            "schema 未声明合法 table_name: {0}".format(table))
    return table


def _status_field(schema: Any) -> str:
    for field_obj in (_get(schema, "fields") or []):
        field_id = str(_get(field_obj, "id", "") or "")
        db_column = str(_get(field_obj, "db_column", "") or "")
        if field_id == "status" or db_column == "status":
            return db_column or field_id
    return "status"


def _read_doc(ds, table: str, doc_id: Any) -> Optional[Dict[str, Any]]:
    rows = ds.query("SELECT * FROM {0} WHERE id = ?".format(table), [doc_id])
    if not rows:
        return None
    row = rows[0]
    return dict(row) if not isinstance(row, dict) else dict(row)


def _lookup(env: Dict[str, Any], path: str, required: bool = True) -> Any:
    current: Any = env
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if required:
            raise ReversalError(
                "REVERSAL_DECL_INVALID",
                "占位符不可解析: {{{0}}}".format(path))
        return None
    return current


def _resolve_value(value: Any, env: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        full = _FULL_PLACEHOLDER_RE.match(value)
        if full:
            return _lookup(env, full.group(1))
        return _PLACEHOLDER_RE.sub(
            lambda match: str(_lookup(env, match.group(1))), value)
    if isinstance(value, list):
        return [_resolve_value(item, env) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_value(item, env) for key, item in value.items()}
    return value


def _parse_literal(text: str) -> str:
    raw = text.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw


def _enabled(face: Dict[str, Any], env: Dict[str, Any]) -> bool:
    """``enabled_when`` 最小求值：仅支持 ``==`` / ``!=`` / ``and``（规格 R1）。"""
    expression = str(_get(face, "enabled_when") or "").strip()
    if not expression:
        return True
    for part in expression.split(" and "):
        clause = part.strip()
        for op in ("!=", "=="):
            if op not in clause:
                continue
            left, right = clause.split(op, 1)
            left_value = _lookup(env, left.strip(), required=False)
            equal = str(left_value) == _parse_literal(right)
            if equal != (op == "=="):
                return False
            break
        else:
            if not _lookup(env, clause, required=False):
                return False
    return True


def _has_fact(result: Dict[str, Any]) -> bool:
    return any(result.get(key) for key in _FACT_KEYS)


def _apply_state(ds, table: str, status_field: str, to_state: str,
                 reversal: Dict[str, Any], env: Dict[str, Any],
                 doc_id: Any, current: str) -> None:
    """状态推进 + 审计字段（条件更新，防并发覆盖）。"""
    assignments = ["{0} = ?".format(status_field)]
    params: List[Any] = [to_state]
    for field_name, template in \
            (reversal.get("write_audit_fields") or {}).items():
        if not _IDENT_RE.match(str(field_name)):
            raise ReversalError(
                "REVERSAL_DECL_INVALID",
                "write_audit_fields 字段名非法: {0}".format(field_name))
        assignments.append("{0} = ?".format(field_name))
        params.append(_resolve_value(template, env))
    params.extend([doc_id, current])
    cursor = ds.execute(
        "UPDATE {0} SET {1} WHERE id = ? AND status = ?".format(
            table, ", ".join(assignments)), params)
    rowcount = getattr(cursor, "rowcount", None)
    if rowcount is not None and rowcount != 1:
        raise ReversalError(
            "REVERSAL_FAILED",
            "状态更新未命中唯一行（并发或状态已变化）", field_name=status_field)


def supports(schema_id: str) -> bool:
    """该 schema 是否声明了逆向能力（供 API / 前端判定）。"""
    schema = _load_schema(schema_id)
    if schema is None:
        return False
    return bool(_declaration(schema).get("reversal"))


def execute(ds, *, schema_id: str, doc_id: Any, reason: str = "",
            ref: Optional[str] = None,
            user_info: Optional[dict] = None,
            params: Optional[dict] = None) -> ReversalOutcome:
    """按 schema 的 ``doc_effect`` 声明执行逆向（固定 7 步，自持事务）。

    ``params`` 为调用方透传的上下文（如预分配红字单号 / 业务日期），
    供 ``create_document`` 创建器读取，不参与占位符解析。
    """
    # 1. resolve
    schema = _load_schema(schema_id)
    if schema is None:
        raise ReversalError("REVERSAL_NOT_DECLARED",
                            "schema 不存在: {0}".format(schema_id))
    doc_effect = _declaration(schema)
    reversal = doc_effect.get("reversal") or {}
    if not reversal:
        raise ReversalError("REVERSAL_NOT_DECLARED",
                            "单据未声明逆向能力: {0}".format(schema_id))
    try:
        validate_object(schema)
    except DocEffectDeclarationError as exc:
        raise ReversalError("REVERSAL_DECL_INVALID", str(exc),
                            rule=exc.code) from None

    table = _table_name(schema)
    status_field = _status_field(schema)
    to_state = str(reversal.get("to_state") or "")
    from_states = [str(state) for state in (reversal.get("from_states") or [])]
    idem_states = [str(state) for state in
                   (reversal.get("idempotent_states") or [to_state])]
    ref_field = str(reversal.get("ref_field") or "")

    # 2. guard（幂等命中不开事务）
    row = _read_doc(ds, table, doc_id)
    if row is None:
        raise ReversalError("REVERSAL_FAILED",
                            "单据不存在: {0}".format(doc_id), field_name="id")
    current = str(row.get(status_field) or "")
    if current in idem_states:
        return ReversalOutcome(doc_id=doc_id, to_state=to_state, replay=True)
    if current not in from_states:
        raise ReversalError(
            "REVERSAL_STATE_INVALID",
            "状态 {0} 不可逆向（允许: {1}）".format(current, from_states),
            field_name=status_field)

    ref_value = str(ref or (row.get(ref_field) if ref_field else "") or "")
    if ref_field and not ref_value:
        raise ReversalError("REVERSAL_REF_MISSING",
                            "业务锚 {0} 未提供".format(ref_field),
                            field_name=ref_field)

    now = datetime.now().isoformat(timespec="seconds")
    reason_text = reason or ""
    ctx = ReversalContext(ds=ds, schema_id=schema_id, doc_id=doc_id,
                          ref=ref_value, now=now, reason=reason_text,
                          row=dict(row), user_info=user_info,
                          params=dict(params or {}))

    env: Dict[str, Any] = {
        "id": doc_id,
        "now": now,
        "reason": reason_text,
        "direction": "",
        "order_id": row.get("order_id"),
        "reversal": {"ref": ref_value, "reason": reason_text, "now": now,
                     "doc": {}},
        "posting": {},
    }
    for key, value in row.items():
        env.setdefault(key, value)
    posting = doc_effect.get("posting") or {}
    direction_field = str(posting.get("direction_field") or "")
    if direction_field:
        # 方向优先取调用方透传（如交货单的方向在 document_types 而非单据行）
        env["direction"] = str(row.get(direction_field)
                               or (params or {}).get("direction") or "")
    for key, template in posting.items():
        if key == "direction_field":
            continue
        env["posting"][key] = _resolve_value(template, env)

    faces = list(doc_effect.get("faces") or [])
    projections = list(doc_effect.get("projections") or [])
    order_mode = str(reversal.get("order") or "inverted")
    sequence = list(reversed(faces)) if order_mode == "inverted" else faces
    faces_out: Dict[str, Dict[str, Any]] = {}
    projections_out: Dict[str, Dict[str, Any]] = {}

    create_spec = reversal.get("create_document") or {}
    document: Dict[str, Any] = {}

    # 3. txn（嵌套时透传外层事务）
    with ds.transaction():
        # 3.1 红字单（可选声明）：先建单，写面才能引用 {reversal.doc.*}
        if create_spec:
            creator_id = str(_get(create_spec, "primitive") or "")
            creator = get_doc_creator(creator_id)
            if creator is None:
                raise ReversalError(
                    "REVERSAL_PRIMITIVE_UNKNOWN",
                    "create_document 引用未注册创建器: {0}".format(creator_id))
            try:
                document = dict(creator(ds, ctx) or {})
            except ReversalError:
                raise
            except Exception as exc:  # noqa: BLE001
                # 保留创建器的业务规则码 / 字段定位，供调用方映射原错误
                code = getattr(exc, "rule", "") or getattr(exc, "code", "")
                field_name = str(getattr(exc, "field_name", "") or "")
                raise ReversalError(
                    "REVERSAL_FAILED",
                    "create_document 执行失败: {0}".format(exc),
                    field_name=field_name,
                    rule=str(code)) from exc
            env["reversal"]["doc"] = document

        if document.get("replay"):
            # 红字单已存在 → 只推进原单状态（对齐既有幂等分支，不重放写面）
            _apply_state(ds, table, status_field, to_state, reversal, env,
                         doc_id, current)
            return ReversalOutcome(doc_id=doc_id, to_state=to_state,
                                   replay=True, document=document)

        # 4. faces
        for face in sequence:
            face_id = str(_get(face, "id") or "")
            if not _enabled(face, env):
                continue
            primitive_id = str(_get(face, "primitive") or "")
            primitive = get_primitive(primitive_id)
            if primitive is None:
                raise ReversalError(
                    "REVERSAL_PRIMITIVE_UNKNOWN",
                    "face {0} 引用未注册原语: {1}".format(face_id, primitive_id),
                    field_name=face_id)
            args = _resolve_value(_get(face, "args") or {}, env)
            try:
                result = primitive(ds, args, ctx) or {}
            except ReversalError:
                raise
            except Exception as exc:  # noqa: BLE001 - 统一转 REVERSAL_FAILED
                code = getattr(exc, "rule", "") or getattr(exc, "code", "")
                raise ReversalError(
                    "REVERSAL_FAILED",
                    "{0} 执行失败: {1}".format(primitive_id, exc),
                    field_name=face_id, rule=str(code)) from exc
            result = dict(result)
            ctx.executed[face_id] = result
            env[face_id] = result
            faces_out[face_id] = result
            if str(_get(face, "on_missing") or "skip") == "strict" \
                    and not _has_fact(result):
                raise ReversalError(
                    "REVERSAL_FACT_MISSING",
                    "写面 {0} 无事实（strict）".format(face_id),
                    field_name=face_id)

        # 5. projections（faces 全部完成后统一执行）
        for projection in projections:
            projection_id = str(_get(projection, "id") or "")
            primitive_id = str(_get(projection, "primitive") or "")
            primitive = get_primitive(primitive_id)
            if primitive is None:
                raise ReversalError(
                    "REVERSAL_PRIMITIVE_UNKNOWN",
                    "投影 {0} 引用未注册原语: {1}".format(
                        projection_id, primitive_id), field_name=projection_id)
            args = _resolve_value(_get(projection, "args") or {}, env)
            try:
                result = primitive(ds, args, ctx) or {}
            except ReversalError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ReversalError(
                    "REVERSAL_FAILED",
                    "{0} 执行失败: {1}".format(primitive_id, exc),
                    field_name=projection_id) from exc
            projections_out[projection_id] = dict(result)
            env[projection_id] = projections_out[projection_id]

        # 6. state
        _apply_state(ds, table, status_field, to_state, reversal, env,
                     doc_id, current)

    # 7. commit（事务外不再写）
    logger.info("[reversal] %s:%s → %s（faces=%s, projections=%s）",
                schema_id, doc_id, to_state, list(faces_out),
                list(projections_out))
    return ReversalOutcome(doc_id=doc_id, to_state=to_state, replay=False,
                           faces=faces_out, projections=projections_out,
                           document=document)
