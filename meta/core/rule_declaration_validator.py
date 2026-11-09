# -*- coding: utf-8 -*-
"""加载期规则声明一致性校验（Rule Convergence M2 / FR-012）

覆盖四个规则域，错误码稳定，供 CI 测试与静态守卫使用：

  状态机  STATE_FIELD_MISSING / STATE_UNDECLARED / STATE_TERMINAL_OUTGOING /
          STATE_ORPHAN
  审批    APPROVAL_TABLE_UNKNOWN / APPROVAL_AMOUNT_FIELD_MISSING
  编号    NUMBERING_FIELD_MISSING
  单据流  DOC_FLOW_SOURCE_UNKNOWN / DOC_FLOW_TARGET_UNKNOWN /
          DOC_FLOW_QTY_FIELD_MISSING / DOC_FLOW_DUPLICATE

本模块只读声明与三元组，不查库、不写库；运行时不在请求链路内执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from meta.core.models import registry
from meta.core.models_enums import RuleType


@dataclass(frozen=True)
class DeclarationError:
    code: str
    object_type: str
    message: str

    def __str__(self) -> str:
        return '[%s] %s: %s' % (self.code, self.object_type, self.message)


def _objects(objects: Optional[Iterable[Any]] = None) -> List[Any]:
    if objects is not None:
        return list(objects)
    return list(registry.all())


def _field_names(meta_object: Any) -> set:
    names = set()
    for field in (getattr(meta_object, 'fields', None) or []):
        for key in ('id', 'db_column'):
            value = getattr(field, key, None)
            if value:
                names.add(str(value))
    return names


def _state_rules(meta_object: Any) -> List[Any]:
    return [
        rule for rule in (getattr(meta_object, 'rules', None) or [])
        if getattr(rule, 'rule_type', None) == RuleType.STATE_TRANSITION
    ]


def validate_state_machines(
        objects: Optional[Iterable[Any]] = None) -> List[DeclarationError]:
    """状态机声明校验：字段存在、状态已声明、无重复边、终态无出边、无孤儿状态。"""
    errors: List[DeclarationError] = []
    for meta_object in _objects(objects):
        rules = _state_rules(meta_object)
        if not rules:
            continue

        object_id = str(getattr(meta_object, 'id', '') or '')
        names = _field_names(meta_object)
        catalog: Dict[str, Any] = {
            str(getattr(item, 'code', '') or ''): item
            for item in (getattr(meta_object, 'states', None) or [])
        }

        by_field: Dict[str, List[Any]] = {}
        for rule in rules:
            by_field.setdefault(str(getattr(rule, 'state_field', '') or ''),
                                []).append(rule)

        for state_field, field_rules in by_field.items():
            if state_field not in names:
                errors.append(DeclarationError(
                    'STATE_FIELD_MISSING', object_id,
                    '状态字段 %r 不在对象字段' % state_field))
                continue

            edges = set()
            incoming = set()
            for rule in field_rules:
                to_state = str(getattr(rule, 'to_state', '') or '')
                for from_state in (getattr(rule, 'from_states', None) or []):
                    pair = (str(from_state), to_state)
                    # 同一 (from, to) 允许多条规则（不同 action_ref 落同一状态），
                    # Spec FR-012 只要求「无孤儿 / 无不可达 / 终态无出边」。
                    edges.add(pair)
                    incoming.add(to_state)

            if not catalog:
                continue

            for rule in field_rules:
                codes = [str(item) for item in
                         (getattr(rule, 'from_states', None) or [])]
                codes.append(str(getattr(rule, 'to_state', '') or ''))
                for code in codes:
                    if code and code not in catalog:
                        errors.append(DeclarationError(
                            'STATE_UNDECLARED', object_id,
                            '状态 %s 未在 states 目录声明' % code))

            terminal_outgoing = sorted({
                from_state for from_state, _ in edges
                if catalog.get(from_state) is not None
                and getattr(catalog[from_state], 'category', '') == 'terminal'
            })
            for code in terminal_outgoing:
                errors.append(DeclarationError(
                    'STATE_TERMINAL_OUTGOING', object_id,
                    '终态 %s 存在出边' % code))

            for code, definition in catalog.items():
                category = getattr(definition, 'category', '')
                if category in ('terminal', 'initial'):
                    continue
                if code not in incoming:
                    errors.append(DeclarationError(
                        'STATE_ORPHAN', object_id, '状态 %s 不可达' % code))
    return errors


def validate_approval(
        objects: Optional[Iterable[Any]] = None) -> List[DeclarationError]:
    """审批注册校验：表名已注册、金额字段至少一个存在。"""
    errors: List[DeclarationError] = []
    all_objects = _objects()
    table_names = {
        str(getattr(item, 'table_name', '') or '') for item in all_objects
    }

    for meta_object in (list(objects) if objects is not None else all_objects):
        raw = getattr(meta_object, 'approval', None) or {}
        if not raw:
            continue

        object_id = str(getattr(meta_object, 'id', '') or '')
        table = str(raw.get('table') or '')
        if not table or table not in table_names:
            errors.append(DeclarationError(
                'APPROVAL_TABLE_UNKNOWN', object_id,
                '审批表 %r 未在已注册对象 table_name 中找到' % table))

        amount_fields = [str(item) for item in (raw.get('amount_fields') or [])]
        if amount_fields:
            names = _field_names(meta_object)
            if not any(item in names for item in amount_fields):
                errors.append(DeclarationError(
                    'APPROVAL_AMOUNT_FIELD_MISSING', object_id,
                    '金额字段 %s 均不在对象字段' % '/'.join(amount_fields)))
    return errors


def validate_numbering(
        objects: Optional[Iterable[Any]] = None) -> List[DeclarationError]:
    """编号声明校验：no_field / date_field 必须存在于对象字段。"""
    errors: List[DeclarationError] = []
    for meta_object in _objects(objects):
        raw = getattr(meta_object, 'numbering', None) or {}
        if not raw:
            continue

        object_id = str(getattr(meta_object, 'id', '') or '')
        names = _field_names(meta_object)
        for key in ('no_field', 'date_field'):
            value = str(raw.get(key) or '')
            if value and value not in names:
                errors.append(DeclarationError(
                    'NUMBERING_FIELD_MISSING', object_id,
                    '%s=%r 不在对象字段' % (key, value)))
    return errors


def validate_doc_flow_rules(
        rules: Iterable[Dict[str, Any]],
        objects: Optional[Iterable[Any]] = None) -> List[DeclarationError]:
    """单据流规则校验：源 / 目标 BO 已注册、数量字段存在、直拷字段可解析、
    rule_id 唯一。"""
    errors: List[DeclarationError] = []
    known = {
        str(getattr(item, 'id', '') or ''): item
        for item in _objects(objects)
    }
    seen = set()

    for rule in rules:
        rule_id = str(rule.get('rule_id') or '')
        if rule_id in seen:
            errors.append(DeclarationError(
                'DOC_FLOW_DUPLICATE', rule_id, 'rule_id 重复'))
        seen.add(rule_id)

        if not known:
            continue

        source_bo = str(rule.get('source_bo') or '')
        target_bo = str(rule.get('target_bo') or '')
        if source_bo not in known:
            errors.append(DeclarationError(
                'DOC_FLOW_SOURCE_UNKNOWN', rule_id,
                'source_bo %r 未注册' % source_bo))
            continue
        target_known = target_bo in known
        if not target_known:
            errors.append(DeclarationError(
                'DOC_FLOW_TARGET_UNKNOWN', rule_id,
                'target_bo %r 未注册' % target_bo))

        qty_field = str(rule.get('source_qty_field') or '')
        if qty_field and qty_field not in _field_names(known[source_bo]):
            errors.append(DeclarationError(
                'DOC_FLOW_QTY_FIELD_MISSING', rule_id,
                'source_qty_field %r 不在 %s 字段' % (qty_field, source_bo)))

        if not target_known:
            continue

        target_qty_field = str(rule.get('target_qty_field') or '')
        if target_qty_field and \
                target_qty_field not in _field_names(known[target_bo]):
            errors.append(DeclarationError(
                'DOC_FLOW_TARGET_QTY_FIELD_MISSING', rule_id,
                'target_qty_field %r 不在 %s 字段'
                % (target_qty_field, target_bo)))

        for fid in (rule.get('copied_fields') or []):
            if fid not in _field_names(known[source_bo]) or \
                    fid not in _field_names(known[target_bo]):
                errors.append(DeclarationError(
                    'DOC_FLOW_COPIED_FIELD_MISSING', rule_id,
                    'copied_fields %r 须同时存在于 %s 与 %s 字段'
                    % (fid, source_bo, target_bo)))
    return errors


def validate_all(
        objects: Optional[Iterable[Any]] = None,
        doc_flow_rules: Optional[Iterable[Dict[str, Any]]] = None
) -> List[DeclarationError]:
    """聚合四域校验。"""
    target = list(objects) if objects is not None else None
    errors = validate_state_machines(target)
    errors.extend(validate_approval(target))
    errors.extend(validate_numbering(target))
    if doc_flow_rules is not None:
        errors.extend(validate_doc_flow_rules(doc_flow_rules, target))
    return errors
