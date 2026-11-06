# -*- coding: utf-8 -*-
"""`doc_effect` 声明静态校验（Reversal Platform 阶段 D1）。

规格 §7.3 的 V1-V6：声明必须与状态机、原语注册表、占位符作用域一致。
本模块不落库、不读 DB，只做元数据交叉校验；

- 启动期：:func:`validate_registry` 遍历已加载 schema，逐条告警；
- 测试期：:func:`validate_object` 直接断言（失败抛 :class:`DocEffectDeclarationError`）。

未声明 ``doc_effect.reversal`` 的对象**不算非法**（D8 由编排器拒绝逆向调用）。

对应方案: docs/specs/spec-reversal-platform-2026-11-06.md §7.3
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Tuple

from meta.core.reversal_primitives import DOC_CREATORS, PRIMITIVES

logger = logging.getLogger(__name__)

# 占位符：{id} / {posting.event_key} / {inventory.txn_ids}
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\}")
# 静态可解析的根（其余根须为 face id 或 schema 字段 id）
_BUILTIN_ROOTS = frozenset({"id", "now", "reason", "reversal", "posting",
                            "direction", "order_id"})


class DocEffectDeclarationError(ValueError):
    """声明非法；``code`` ∈ 规格 §7.3 的 DECL_* 码。"""

    def __init__(self, code: str, message: str, schema_id: str = "",
                 path: str = ""):
        super().__init__("[{0}] {1}".format(code, message))
        self.code = code
        self.message = message
        self.schema_id = schema_id
        self.path = path


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _schema_id(obj: Any) -> str:
    return str(_get(obj, "id", "") or "")


def _status_values(obj: Any) -> List[str]:
    for field_obj in (_get(obj, "fields") or []):
        field_id = _get(field_obj, "id", "")
        db_column = _get(field_obj, "db_column", "")
        if field_id != "status" and db_column != "status":
            continue
        values: List[str] = []
        for enum in (_get(field_obj, "enum_values") or []):
            if isinstance(enum, dict):
                values.append(str(enum.get("value")))
            else:
                values.append(str(enum))
        return values
    return []


def _state_transition_rules(obj: Any) -> List[Any]:
    rules = []
    for rule in (_get(obj, "rules") or []):
        rule_type = _get(rule, "rule_type", "")
        rule_type = getattr(rule_type, "value", rule_type)
        if str(rule_type) != "state_transition":
            continue
        rules.append(rule)
    return rules


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)


def _validate_placeholders(schema_id: str, doc_effect: Dict[str, Any],
                           faces: List[Any], field_ids: set) -> None:
    allowed = set(_BUILTIN_ROOTS) | field_ids
    for face in faces:
        face_id = str(_get(face, "id", "") or "")
        if face_id:
            allowed.add(face_id)
    posting = doc_effect.get("posting") or {}
    scan = {
        "faces": doc_effect.get("faces") or [],
        "projections": doc_effect.get("projections") or [],
        "create_document": doc_effect.get("reversal", {}).get(
            "create_document") or {},
    }
    for raw in _iter_strings(scan):
        for path in _PLACEHOLDER_RE.findall(raw):
            root, _, rest = path.partition(".")
            if root == "posting":
                if rest.split(".")[0] not in posting:
                    raise DocEffectDeclarationError(
                        "DECL_UNRESOLVED_PLACEHOLDER",
                        "posting 段未声明占位符来源: {%s}" % path, schema_id)
                continue
            if root not in allowed:
                raise DocEffectDeclarationError(
                    "DECL_UNRESOLVED_PLACEHOLDER",
                    "占位符根不可解析: {%s}（允许：内置变量 / face id / 字段 id）"
                    % path, schema_id)


def validate_object(obj: Any) -> None:
    """校验单个 schema 对象；未声明逆向时直接返回。"""
    schema_id = _schema_id(obj)
    doc_effect = _get(obj, "doc_effect") or {}
    if not isinstance(doc_effect, dict) or not doc_effect:
        return
    reversal = doc_effect.get("reversal") or {}
    if not reversal:
        return

    # V1：to_state 必须存在于状态枚举
    to_state = str(reversal.get("to_state") or "")
    status_values = _status_values(obj)
    if not to_state:
        raise DocEffectDeclarationError(
            "DECL_INVALID_TO_STATE", "reversal.to_state 未声明", schema_id)
    if status_values and to_state not in status_values:
        raise DocEffectDeclarationError(
            "DECL_INVALID_TO_STATE",
            "reversal.to_state=%s 不在 status 枚举 %s 内"
            % (to_state, status_values), schema_id)

    # V2：from_states 必须与同 to_state 的 state_transition 规则一致
    from_states = [str(s) for s in (reversal.get("from_states") or [])]
    if not from_states:
        raise DocEffectDeclarationError(
            "DECL_STATE_MISMATCH", "reversal.from_states 未声明", schema_id)
    candidates = [rule for rule in _state_transition_rules(obj)
                  if str(_get(rule, "to_state", "") or "") == to_state]
    if not candidates:
        raise DocEffectDeclarationError(
            "DECL_STATE_MISMATCH",
            "未找到 to_state=%s 的 state_transition 规则" % to_state, schema_id)
    matched = any(
        set(str(s) for s in (_get(rule, "from_states") or [])) == set(from_states)
        for rule in candidates)
    if not matched:
        raise DocEffectDeclarationError(
            "DECL_STATE_MISMATCH",
            "reversal.from_states=%s 与状态机规则不一致（规则：%s）"
            % (from_states,
               [_get(rule, "from_states") for rule in candidates]),
            schema_id)

    # V6：face id 唯一 + 结构完整
    faces = doc_effect.get("faces") or []
    if not isinstance(faces, list):
        raise DocEffectDeclarationError(
            "DECL_FACE_INVALID", "faces 必须为列表", schema_id)
    seen = set()
    for index, face in enumerate(faces):
        face_id = str(_get(face, "id", "") or "")
        if not face_id:
            raise DocEffectDeclarationError(
                "DECL_FACE_INVALID", "faces[%d] 缺少 id" % index, schema_id)
        if face_id in seen:
            raise DocEffectDeclarationError(
                "DECL_DUPLICATE_FACE", "face id 重复: %s" % face_id, schema_id)
        seen.add(face_id)

        # V3：原语必须在注册表内
        primitive = str(_get(face, "primitive", "") or "")
        if primitive not in PRIMITIVES:
            raise DocEffectDeclarationError(
                "DECL_UNKNOWN_PRIMITIVE",
                "face %s 引用未注册原语: %s" % (face_id, primitive), schema_id)

        order_mode = str(_get(face, "on_missing", "skip") or "skip")
        if order_mode not in ("strict", "skip"):
            raise DocEffectDeclarationError(
                "DECL_FACE_INVALID",
                "face %s 的 on_missing 非法: %s" % (face_id, order_mode),
                schema_id)

    # V3（补充）：红字单创建器必须已注册
    create_spec = reversal.get("create_document") or {}
    if create_spec:
        creator_id = str(create_spec.get("primitive") or "")
        if creator_id not in DOC_CREATORS:
            raise DocEffectDeclarationError(
                "DECL_UNKNOWN_PRIMITIVE",
                "create_document 引用未注册创建器: {0}".format(creator_id),
                schema_id)

    # V4：存在补偿面时必须能确定业务权威锚——
    #     ref_field（从单据列取）或面内显式 ref 模板（如红字单 id）二者其一。
    edge_faces = [face for face in faces
                  if str(_get(face, "primitive", "")).startswith("edge_compensate")]
    if edge_faces and not str(reversal.get("ref_field") or ""):
        for face in edge_faces:
            args = _get(face, "args") or {}
            if not str(_get(args, "ref") or ""):
                raise DocEffectDeclarationError(
                    "DECL_REF_FIELD_REQUIRED",
                    "声明了 edge_compensate_* 面时必须提供 reversal.ref_field "
                    "或面内显式 args.ref",
                    schema_id)

    # V5：占位符必须可解析
    field_ids = {str(_get(f, "id", "")) for f in (_get(obj, "fields") or [])}
    _validate_placeholders(schema_id, doc_effect, faces, field_ids)


def validate_registry(registry=None) -> List[Tuple[str, str, str]]:
    """遍历 registry（缺省为全局元数据注册表），返回 [(schema_id, code, msg)]。"""
    if registry is None:
        from meta.core.models import registry as _default
        registry = _default
    errors: List[Tuple[str, str, str]] = []
    for obj in registry.all():
        try:
            validate_object(obj)
        except DocEffectDeclarationError as exc:
            errors.append((_schema_id(obj), exc.code, exc.message))
            logger.warning("[reversal] doc_effect 声明非法 %s: %s",
                           _schema_id(obj), exc)
    return errors
