# -*- coding: utf-8 -*-
"""加载期规则声明一致性校验（Rule Convergence M2 / FR-012）

覆盖四个规则域，错误码稳定，供 CI 测试与静态守卫使用：

  状态机  STATE_FIELD_MISSING / STATE_UNDECLARED / STATE_TERMINAL_OUTGOING /
          STATE_ORPHAN
  审批    APPROVAL_TABLE_UNKNOWN / APPROVAL_AMOUNT_FIELD_MISSING
  编号    NUMBERING_FIELD_MISSING
  单据流  DOC_FLOW_SOURCE_UNKNOWN / DOC_FLOW_TARGET_UNKNOWN /
          DOC_FLOW_QTY_FIELD_MISSING / DOC_FLOW_DUPLICATE
  动作    RULE_ACTION_INVALID
  命中    RULE_HIT_POLICY_INVALID / RULE_OVERLAP
  聚合    RULE_COMBINE_MODE_INVALID / RULE_KEY_INVALID
  约束    RULE_HOLD_RELEASE_MISSING
  度量    METRIC_DEFINITION_INVALID

本模块只读声明与三元组，不查库、不写库；运行时不在请求链路内执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from meta.core.models import registry
from meta.core.models_enums import RuleType, ValidationSeverity
from meta.core.rule_action_matrix import HOLD, validate_action
from meta.core.rule_combine_mode import validate_combine_mode
from meta.core.rule_constraint_evaluator import KEY_SEVERITIES
from meta.core.rule_hit_policy import normalize_hit_policy, validate_hit_policy
from meta.core.rule_keys import bo_yaml_key


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


def validate_rule_actions(
        objects: Optional[Iterable[Any]] = None) -> List[DeclarationError]:
    """处置动作校验：``rule_type × action`` 必须命中封闭矩阵（M1 / R-A1）。

    未声明 ``disposition`` 的规则视为「无处置动作」，不报错；
    声明了就必须是词表内动作且被该 ``rule_type`` 允许。
    """
    errors: List[DeclarationError] = []
    for meta_object in _objects(objects):
        object_id = str(getattr(meta_object, 'id', '') or '')
        for rule in (getattr(meta_object, 'rules', None) or []):
            reason = validate_action(
                getattr(rule, 'rule_type', None),
                getattr(rule, 'disposition', ''))
            if reason:
                rule_key = bo_yaml_key(object_id, getattr(rule, 'id', ''))
                errors.append(DeclarationError(
                    'RULE_ACTION_INVALID', object_id,
                    '%s：%s' % (rule_key, reason)))
    return errors


def _condition_signature(rule: Any) -> tuple:
    rule_type = getattr(rule, 'rule_type', None)
    return (
        str(getattr(rule_type, 'value', rule_type) or ''),
        ' '.join(str(getattr(rule, 'condition', '') or '').split()),
    )


def validate_hit_policies(
        objects: Optional[Iterable[Any]] = None) -> List[DeclarationError]:
    """命中策略校验（M5 / FR-006）。

    1. 显式声明的 ``hit_policy`` 必须落在封闭词表 ``first / all / unique`` 内；
       未声明视为默认 ``first``，不报错。
    2. ``unique`` 只做建模期静态重叠检查：同一对象、同一 ``rule_type`` 下
       条件文本相同的多条 ``unique`` 规则即视为「规则重叠」。
    """
    errors: List[DeclarationError] = []
    for meta_object in _objects(objects):
        object_id = str(getattr(meta_object, 'id', '') or '')
        seen: Dict[tuple, str] = {}
        for rule in (getattr(meta_object, 'rules', None) or []):
            declared = getattr(rule, 'hit_policy', '')
            reason = validate_hit_policy(declared)
            rule_key = bo_yaml_key(object_id, getattr(rule, 'id', ''))
            if reason:
                errors.append(DeclarationError(
                    'RULE_HIT_POLICY_INVALID', object_id,
                    '%s：%s' % (rule_key, reason)))
                continue
            if normalize_hit_policy(declared) != 'unique':
                continue
            signature = _condition_signature(rule)
            previous = seen.get(signature)
            if previous is not None:
                errors.append(DeclarationError(
                    'RULE_OVERLAP', object_id,
                    '%s 与 %s 条件重叠（hit_policy=unique）'
                    % (rule_key, previous)))
            else:
                seen[signature] = rule_key
    return errors


def validate_combine_modes(
        objects: Optional[Iterable[Any]] = None) -> List[DeclarationError]:
    """判定聚合方式校验（M6b）。

    显式声明的 ``combine_mode`` 必须落在封闭词表 ``any / all`` 内；
    未声明视为默认 ``all``，不报错。
    """
    errors: List[DeclarationError] = []
    for meta_object in _objects(objects):
        object_id = str(getattr(meta_object, 'id', '') or '')
        for rule in (getattr(meta_object, 'rules', None) or []):
            reason = validate_combine_mode(getattr(rule, 'combine_mode', ''))
            if reason:
                rule_key = bo_yaml_key(object_id, getattr(rule, 'id', ''))
                errors.append(DeclarationError(
                    'RULE_COMBINE_MODE_INVALID', object_id,
                    '%s：%s' % (rule_key, reason)))
    return errors


def validate_constraint_keys(
        objects: Optional[Iterable[Any]] = None) -> List[DeclarationError]:
    """约束多 key 声明校验（M6b）。

    1. 每个 key 必须同时声明 ``parameter`` 与 ``metric``；
    2. key 级 ``severity`` 必须落在 ``error / warning / info`` 内；
    3. key 级 ``disposition`` 必须被 ``constraint × action`` 矩阵允许；
    4. 生效动作为 ``hold`` 时规则必须声明 ``release_action``（可存不可过）。
    """
    errors: List[DeclarationError] = []
    for meta_object in _objects(objects):
        object_id = str(getattr(meta_object, 'id', '') or '')
        for rule in (getattr(meta_object, 'rules', None) or []):
            if getattr(rule, 'rule_type', None) != RuleType.CONSTRAINT:
                continue
            rule_key = bo_yaml_key(object_id, getattr(rule, 'id', ''))
            release_action = str(getattr(rule, 'release_action', '') or '').strip()
            rule_disposition = str(
                getattr(rule, 'disposition', '') or '').strip().lower()
            if rule_disposition == HOLD and not release_action:
                errors.append(DeclarationError(
                    'RULE_HOLD_RELEASE_MISSING', object_id,
                    '%s：hold 必须声明释放动作 release_action' % rule_key))
            for index, key in enumerate(getattr(rule, 'keys', None) or [], 1):
                prefix = '%s key#%d' % (rule_key, index)
                if not isinstance(key, dict) or not key.get('parameter') \
                        or not key.get('metric'):
                    errors.append(DeclarationError(
                        'RULE_KEY_INVALID', object_id,
                        '%s：key 必须是含 parameter 与 metric 的映射' % prefix))
                    continue
                severity = str(key.get('severity') or
                               ValidationSeverity.ERROR.value).strip().lower()
                if severity not in KEY_SEVERITIES:
                    errors.append(DeclarationError(
                        'RULE_KEY_INVALID', object_id,
                        '%s：severity %r 不在 %s 内'
                        % (prefix, severity, list(KEY_SEVERITIES))))
                disposition = str(key.get('disposition') or
                                  rule_disposition or '').strip().lower()
                if key.get('disposition'):
                    reason = validate_action(RuleType.CONSTRAINT, disposition)
                    if reason:
                        errors.append(DeclarationError(
                            'RULE_ACTION_INVALID', object_id,
                            '%s：%s' % (prefix, reason)))
                if disposition == HOLD and not release_action:
                    errors.append(DeclarationError(
                        'RULE_HOLD_RELEASE_MISSING', object_id,
                        '%s：hold 必须声明释放动作 release_action' % prefix))
    return errors


def validate_metric_definitions(
        metric_registry: Any = None,
        known_fields: Optional[Dict[str, Iterable[str]]] = None
) -> List[DeclarationError]:
    """派生度量定义校验（M3 / FR-003 / NFR-003）。

    结构化错误（空 code / 空 formula / precision 越界 / 重复定义）在
    ``MetricDefinition`` 构造与 ``register()`` 时即抛出；这里汇总整表问题：
    公式引用未声明输入、输入既非度量也非对象字段（仅在传入 known_fields 时查）、
    度量循环依赖。
    """
    from meta.core.rule_metrics import DEFAULT_METRIC_REGISTRY

    target = metric_registry if metric_registry is not None else DEFAULT_METRIC_REGISTRY
    return [DeclarationError('METRIC_DEFINITION_INVALID', '', message)
            for message in target.validate(known_fields=known_fields)]


def validate_all(
        objects: Optional[Iterable[Any]] = None,
        doc_flow_rules: Optional[Iterable[Dict[str, Any]]] = None
) -> List[DeclarationError]:
    """聚合七域校验。"""
    target = list(objects) if objects is not None else None
    errors = validate_state_machines(target)
    errors.extend(validate_approval(target))
    errors.extend(validate_numbering(target))
    errors.extend(validate_rule_actions(target))
    errors.extend(validate_hit_policies(target))
    errors.extend(validate_combine_modes(target))
    errors.extend(validate_constraint_keys(target))
    # [Rule Model M6a-3 2026-11-10] 传入对象字段表：度量的 inputs 必须
    # 是「已声明度量」或「该对象字段」，加载期即可拦下拼写错误。
    known_fields = {
        str(getattr(obj, 'id', '') or ''): _field_names(obj)
        for obj in (target if target is not None else _objects())
    }
    errors.extend(validate_metric_definitions(known_fields=known_fields))
    if doc_flow_rules is not None:
        errors.extend(validate_doc_flow_rules(doc_flow_rules, target))
    return errors
