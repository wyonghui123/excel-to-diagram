# -*- coding: utf-8 -*-
"""配置规则引擎 —— 必选 / 默认 / 条件收缩 / 前向传播 / 冲突报告。

依据: docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md §5.5 / §5.6 / §7.1–§7.3

职责边界（§7.2）:
  能做：前向传播（A 选中 ⇒ B 选中）、冲突检测与最小冲突集、选项类基数交给 P2 选择服务。
  不做：反向推理、回溯搜索、全局优化、冲突自动修复。

求值顺序（对应 §7.1 十步流程的第 3–7 步）:
  1. 载入根模型 + 变量结构树（子项按生效版本解析，与 P2 选择服务同口径）。
  2. 必选行置选中；行 default_flag 与 default 类规则给出默认值；模型特征按
     显式值 > 默认值解析。
  3. 用户显式选择覆盖默认值。
  4. condition 规则收缩可选集：disabled 的行移出；若该行是用户显式选中的，
     报 CONFIG_CONFLICT（§5.6）。
  5. 约束规则按 priority 升序前向传播至不动点（上限 50 轮，超出 CONFIG_TIMEOUT）。
     同优先级内 default 类规则排在最后（本实现中 default 已在第 2 步应用）。
  6. 冲突判据：同一目标被要求选中又被要求未选中；严重度 warning 时保留先生效结果
     并写告警，blocking 时返回最小冲突集（目标 + 规则 + 条件项）。

能力边界补充:
  必选行（optional_flag = false）不参与可选集收缩；condition 试图 disabled 必选行
  按冲突处理，因为 P2 选择服务对必选行恒选，静默忽略会得到与规则不一致的结果。

查询方法均可覆写，便于单测注入。
"""

import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from meta.services.item_structure_guard_service import (
    _is_blank,
    _to_date_text,
    _to_decimal,
)
from meta.services.item_structure_select_service import _covers, _normalize_selections

logger = logging.getLogger(__name__)

_STRUCTURE_TABLE = 'item_structures'
_LINE_TABLE = 'item_structure_lines'
_ATTRIBUTE_TABLE = 'item_structure_attributes'

# §7.4 规模红线：传播轮次上限
MAX_ROUNDS = 50

_CONSTRAINT_TYPES = ('require', 'bind', 'exclude', 'negate')
_QUERY_FAILED = object()


class ItemStructureRuleError(ValueError):
    """规则求解失败。`rule` 供调用方映射对外错误码，`conflicts` 为最小冲突集。"""

    def __init__(self, message: str, rule: str = '', field_name: str = '',
                 conflicts: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.rule = rule
        self.field_name = field_name
        self.conflicts = conflicts or []


def _as_number(value: Any) -> Optional[Decimal]:
    if _is_blank(value) or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _same_value(actual: Any, expected: Any) -> bool:
    if _is_blank(expected):
        return False
    left, right = _as_number(actual), _as_number(expected)
    if left is not None and right is not None:
        return left == right
    return str(actual).strip().lower() == str(expected).strip().lower()


def _as_list(value: Any) -> List[Any]:
    if _is_blank(value):
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return [part.strip() for part in value.split(',') if part.strip()]
        return list(parsed) if isinstance(parsed, list) else [parsed]
    return [value]


class ItemStructureRuleEngine:
    """模型配置的规则求值（只读，不落库）。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def evaluate(self, structure_id: Any, selections: Any = None,
                 quantities: Optional[Mapping[Any, Any]] = None,
                 attribute_values: Optional[Mapping[str, Any]] = None,
                 qty: Any = 1, as_of: Optional[str] = None,
                 max_depth: int = 20) -> Dict[str, Any]:
        """返回 {selections, values, warnings, origins, ...}；冲突时抛 ItemStructureRuleError。"""
        self.as_of = _to_date_text(as_of) or date.today().isoformat()
        self.quantities = dict(quantities or {})
        self.root_qty = _to_decimal(qty)
        self.warnings: List[Dict[str, Any]] = []
        self.extra_selections: Dict[Any, bool] = {}

        self._load_tree(structure_id, max_depth)
        self._load_rules()
        self._init_state(attribute_values or {})
        self._apply_user_selections(selections)
        self._apply_condition_rules()
        self._propagate()
        return self._build_result()

    # ---------- 载入 ----------

    def _load_tree(self, structure_id: Any, max_depth: int) -> None:
        root = self._fetch_structure(structure_id)
        if not root:
            raise ItemStructureRuleError(
                f'结构不存在: {structure_id}', rule='item_structure_not_found',
                field_name='structure_id')
        self.root = root
        self.structures: Dict[Any, Dict[str, Any]] = {}
        self.lines: Dict[Any, Dict[str, Any]] = {}
        self.line_ids_by_structure: Dict[Any, List[Any]] = {}
        self.children: Dict[Any, Any] = {}
        self.container_of_structure: Dict[Any, Any] = {}
        self.qty_by_line: Dict[Any, Decimal] = {}
        self.option_class_lines: Dict[Any, List[Any]] = {}
        self._walk(root, self.root_qty, None, [root.get('item_id')], 1, max_depth)

    def _walk(self, structure: Dict[str, Any], parent_qty: Any,
              container_line_id: Any, item_chain: Sequence[Any],
              level: int, max_depth: int) -> None:
        if level > max_depth:
            raise ItemStructureRuleError(
                f'求解深度超过 {max_depth} 层，疑似结构异常',
                rule='item_structure_max_depth_exceeded',
                field_name='structure_id')
        sid = structure.get('id')
        self.structures[sid] = structure
        if container_line_id is not None:
            self.container_of_structure[sid] = container_line_id

        base_qty = _to_decimal(structure.get('base_qty') or 1)
        lines = [line for line in self._fetch_lines(sid)
                 if _covers(self.as_of, line.get('valid_from'), line.get('valid_to'))]
        self.line_ids_by_structure[sid] = [line.get('id') for line in lines]

        for line in lines:
            lid = line.get('id')
            line['_structure_id'] = sid
            self.lines[lid] = line
            self.qty_by_line[lid] = self._line_qty(line, parent_qty, base_qty)

            component_id = line.get('component_item_id')
            if self._item_role(component_id) != 'option_class':
                continue
            self.option_class_lines.setdefault(component_id, []).append(lid)
            if component_id in item_chain:
                raise ItemStructureRuleError(
                    f'组件物料 {component_id} 在求解链上重复出现，结构成环',
                    rule='item_structure_cycle', field_name='component_item_id')
            child = self._find_active_structure(
                component_id, structure.get('usage'), structure.get('alternative_no'))
            if not child:
                raise ItemStructureRuleError(
                    f'选项类物料 {component_id} 没有生效结构，无法解析其子项',
                    rule='item_structure_option_class_missing_structure',
                    field_name='component_item_id')
            self.children[lid] = child.get('id')
            self._walk(child, self.qty_by_line[lid], lid,
                       list(item_chain) + [component_id], level + 1, max_depth)

    def _load_rules(self) -> None:
        self.rules = self._fetch_rules(self.root.get('id'))
        # priority 升序；同优先级内 default 类最后（§5.6）
        self.rules.sort(key=lambda r: (int(r.get('priority') or 100),
                                       1 if r.get('rule_type') == 'default' else 0,
                                       r.get('id')))
        self.terms: Dict[Any, Dict[str, List[Dict[str, Any]]]] = {}
        if not self.rules:
            return
        rule_ids = [rule.get('id') for rule in self.rules]
        for rule_id in rule_ids:
            self.terms[rule_id] = {'if': [], 'then': []}
        for term in self._fetch_terms(rule_ids):
            bucket = self.terms.get(term.get('rule_id'))
            if bucket is None:
                continue
            clause = str(term.get('clause') or '').strip()
            if clause in bucket:
                bucket[clause].append(term)

    # ---------- 初始化状态 ----------

    def _init_state(self, attribute_values: Mapping[str, Any]) -> None:
        # {行 id: {'value': bool, 'source': auto|user|rule|default, 'rule_id': id}}
        self.state: Dict[Any, Dict[str, Any]] = {}
        # {特征编码: {'value': 标量, 'source': ..., 'rule_id': ...}}
        self.values: Dict[str, Dict[str, Any]] = {}

        for lid, line in self.lines.items():
            if not bool(line.get('optional_flag')):
                self.state[lid] = {'value': True, 'source': 'auto', 'rule_id': None}
        for lid, line in self.lines.items():
            if bool(line.get('optional_flag')) and bool(line.get('default_flag')) \
                    and lid not in self.state:
                self.state[lid] = {'value': True, 'source': 'auto', 'rule_id': None}

        for declaration in self._fetch_attributes(self.root.get('id')):
            code = declaration.get('attribute_code')
            if _is_blank(code):
                continue
            code = str(code)
            value = attribute_values.get(code)
            if not _is_blank(value):
                self.values[code] = {'value': value, 'source': 'user', 'rule_id': None}
            elif not _is_blank(declaration.get('default_value_text')):
                self.values[code] = {
                    'value': declaration.get('default_value_text'),
                    'source': 'default',
                    'rule_id': None,
                }

        for rule in self.rules:
            if rule.get('rule_type') != 'default':
                continue
            if not self._condition_true(rule):
                continue
            for term in self.terms.get(rule.get('id'), {}).get('then', []):
                self._apply_default_term(rule, term)

    def _apply_default_term(self, rule: Dict[str, Any], term: Dict[str, Any]) -> None:
        """默认类规则：只填补空位，不覆盖用户显式值与已有默认。"""
        if str(term.get('target_type')) == 'characteristic':
            code = str(term.get('attribute_code') or '').strip()
            if code and code not in self.values:
                expected = term.get('value_text')
                if _is_blank(expected):
                    expected = term.get('value_number')
                if not _is_blank(expected):
                    self.values[code] = {'value': expected, 'source': 'rule',
                                         'rule_id': rule.get('id')}
            return
        for lid in self._target_line_ids(term):
            if lid in self.state:
                continue
            self.state[lid] = {'value': True, 'source': 'rule',
                               'rule_id': rule.get('id')}

    def _apply_user_selections(self, selections: Any) -> None:
        selected = _normalize_selections(selections)
        for lid, value in selected.items():
            if lid not in self.lines:
                # 交给 P2 选择服务报 item_structure_select_line_unknown
                self.extra_selections[lid] = bool(value)
                continue
            self.state[lid] = {'value': bool(value), 'source': 'user', 'rule_id': None}
            if value:
                self._ensure_ancestors(lid, 'user', None)
            else:
                self._clear_descendants(lid)

    # ---------- condition 收缩 ----------

    def _apply_condition_rules(self) -> None:
        for rule in self.rules:
            if rule.get('rule_type') != 'condition':
                continue
            if not self._condition_true(rule):
                continue
            for term in self.terms.get(rule.get('id'), {}).get('then', []):
                operator = str(term.get('operator') or '')
                if operator not in ('enabled', 'disabled'):
                    continue
                if operator == 'enabled':
                    continue
                for lid in self._target_line_ids(term):
                    self._disable_line(rule, lid)

    def _disable_line(self, rule: Dict[str, Any], lid: Any) -> None:
        line = self.lines.get(lid)
        if line is None:
            return
        if not bool(line.get('optional_flag')):
            # 必选行恒选（P2），条件收缩无法生效 → 按冲突处理，避免静默不一致
            self._raise_conflict(
                rule,
                {'type': 'structure_line', 'id': lid,
                 'line_no': line.get('line_no'),
                 'structure_id': line.get('_structure_id')},
                {'value': True, 'source': 'auto', 'rule_id': None})
            return
        current = self.state.get(lid)
        if current is not None and current.get('value'):
            if current.get('source') == 'user':
                # §5.6：被移出的行若已被用户选中，报 CONFIG_CONFLICT
                self._raise_conflict(
                    rule,
                    {'type': 'structure_line', 'id': lid,
                     'line_no': line.get('line_no'),
                     'structure_id': line.get('_structure_id')},
                    current)
                return
        self.state[lid] = {'value': False, 'source': 'rule',
                           'rule_id': rule.get('id')}
        self._clear_descendants(lid)

    # ---------- 前向传播 ----------

    def _propagate(self) -> None:
        constraint_rules = [rule for rule in self.rules
                           if rule.get('rule_type') in _CONSTRAINT_TYPES]
        if not constraint_rules:
            return
        for _round in range(MAX_ROUNDS):
            changed = False
            for rule in constraint_rules:
                for lid in self._apply_rule(rule):
                    changed = True
            if not changed:
                return
        raise ItemStructureRuleError(
            f'规则传播超过 {MAX_ROUNDS} 轮未收敛，疑似规则集互锁',
            rule='config_timeout', field_name='structure_id')

    def _apply_rule(self, rule: Dict[str, Any]) -> List[Any]:
        """应用一条约束规则，返回被改动的行 id（供不动点判定）。"""
        rule_id = rule.get('id')
        rule_type = rule.get('rule_type')
        condition = self._condition_true(rule)
        changed: List[Any] = []

        for term in self.terms.get(rule_id, {}).get('then', []):
            targets = self._target_line_ids(term)
            if not targets:
                continue
            if rule_type == 'require':
                if not condition:
                    continue
                value = True
            elif rule_type == 'bind':
                value = bool(condition)
            elif rule_type == 'exclude':
                if not condition:
                    continue
                value = False
            else:  # negate
                value = not condition
            for lid in targets:
                if self._set_line(lid, value, 'rule', rule):
                    changed.append(lid)
        return changed

    def _set_line(self, lid: Any, value: bool, source: str,
                  rule: Optional[Dict[str, Any]]) -> bool:
        """设置行选择状态；与已生效状态矛盾时按 severity 报冲突或告警。"""
        line = self.lines.get(lid)
        if line is None:
            return False
        current = self.state.get(lid)
        current_value = bool(current.get('value')) if current else False
        if current_value == value:
            # 规则确认了既有选择：把 auto/default 的来源升级为规则，便于解释
            if value and source == 'rule' and current is not None \
                    and current.get('source') in ('auto', 'default') \
                    and current.get('rule_id') is None:
                self.state[lid] = {'value': True, 'source': 'rule',
                                   'rule_id': rule.get('id') if rule else None}
            return False

        if current is None:
            if not value:
                return False
            self.state[lid] = {'value': True, 'source': source,
                               'rule_id': rule.get('id') if rule else None}
            if source in ('rule', 'user'):
                self._ensure_ancestors(lid, source,
                                       rule.get('id') if rule else None)
            return True

        self._raise_conflict(
            rule,
            {'type': 'structure_line', 'id': lid,
             'line_no': line.get('line_no'),
             'structure_id': line.get('_structure_id')},
            current)
        return False

    def _ensure_ancestors(self, lid: Any, source: str, rule_id: Any) -> None:
        """选中子项必须选中其选项类容器（否则 P2 不会遍历到它）。"""
        sid = self.lines.get(lid, {}).get('_structure_id')
        guard = 0
        while sid in self.container_of_structure and guard < 100:
            guard += 1
            container_line_id = self.container_of_structure[sid]
            current = self.state.get(container_line_id)
            if current is not None and current.get('value'):
                parent_sid = self.lines.get(container_line_id, {}).get('_structure_id')
                sid = parent_sid
                continue
            if current is not None and not current.get('value'):
                # 容器被显式取消（用户/规则/条件），选中其子项即冲突
                self._raise_conflict(
                    None,
                    {'type': 'structure_line', 'id': container_line_id,
                     'line_no': self.lines.get(container_line_id, {}).get('line_no'),
                     'structure_id': self.lines.get(container_line_id, {}).get('_structure_id')},
                    current)
                return
            self.state[container_line_id] = {'value': True, 'source': source,
                                             'rule_id': rule_id}
            sid = self.lines.get(container_line_id, {}).get('_structure_id')

    def _clear_descendants(self, container_line_id: Any) -> bool:
        child_sid = self.children.get(container_line_id)
        if child_sid is None:
            return False
        changed = False
        for lid in self.line_ids_by_structure.get(child_sid, []):
            current = self.state.get(lid)
            if current is not None and current.get('value'):
                self.state[lid] = {'value': False, 'source': 'rule', 'rule_id': None}
                changed = True
            if self._clear_descendants(lid):
                changed = True
        return changed

    # ---------- 条件判定 ----------

    def _condition_true(self, rule: Dict[str, Any]) -> bool:
        terms = self.terms.get(rule.get('id'), {}).get('if', [])
        if not terms:
            return True
        return all(self._eval_term(term) is True for term in terms)

    def _eval_term(self, term: Dict[str, Any]) -> Optional[bool]:
        target_type = str(term.get('target_type') or '')
        operator = str(term.get('operator') or '')

        if target_type == 'structure_line':
            lid = term.get('target_line_id')
            if lid not in self.lines:
                return None
            if operator in ('qty_ge', 'qty_le', 'qty_between'):
                return self._eval_qty(term, lid)
            value = self._current_value(lid)
            if operator == 'selected':
                return value
            if operator == 'not_selected':
                return not value
            return None

        if target_type == 'option_class':
            lids = self.option_class_lines.get(term.get('target_class_item_id'), [])
            if not lids:
                return None
            selected = any(self._current_value(lid) for lid in lids)
            if operator == 'selected':
                return selected
            if operator == 'not_selected':
                return not selected
            return None

        if target_type == 'characteristic':
            code = term.get('attribute_code')
            if _is_blank(code):
                return None
            cell = self.values.get(str(code))
            if cell is None:
                return False
            expected = term.get('value_text')
            if _is_blank(expected):
                expected = term.get('value_number')
            if operator == 'equals':
                return _same_value(cell.get('value'), expected)
            if operator == 'not_equals':
                return not _same_value(cell.get('value'), expected)
            if operator == 'in':
                return any(_same_value(cell.get('value'), item)
                           for item in _as_list(term.get('value_list')))
            return None

        return None

    def _eval_qty(self, term: Dict[str, Any], lid: Any) -> Optional[bool]:
        qty = self.qty_by_line.get(lid)
        if qty is None:
            return None
        operator = str(term.get('operator') or '')
        low = _as_number(term.get('value_number'))
        if low is None:
            return None
        if operator == 'qty_ge':
            return qty >= low
        if operator == 'qty_le':
            return qty <= low
        high = _as_number(term.get('value_number_to'))
        if high is None:
            return None
        return low <= qty <= high

    def _current_value(self, lid: Any) -> bool:
        cell = self.state.get(lid)
        return bool(cell.get('value')) if cell else False

    def _target_line_ids(self, term: Dict[str, Any]) -> List[Any]:
        target_type = str(term.get('target_type') or '')
        if target_type == 'structure_line':
            lid = term.get('target_line_id')
            return [lid] if lid in self.lines else []
        if target_type == 'option_class':
            return list(self.option_class_lines.get(term.get('target_class_item_id'), []))
        return []

    # ---------- 结果 ----------

    def _build_result(self) -> Dict[str, Any]:
        selections: Dict[Any, bool] = {}
        self._collect(self.root.get('id'), selections)
        selections.update(self.extra_selections)

        values = [
            {
                'attribute_code': code,
                'value_text': str(cell.get('value')),
                'source': cell.get('source'),
                'source_rule_id': cell.get('rule_id'),
            }
            for code, cell in sorted(self.values.items())
        ]
        origins = {
            lid: cell.get('rule_id')
            for lid, cell in self.state.items()
            if cell.get('source') == 'rule' and cell.get('rule_id')
        }
        return {
            'structure_id': self.root.get('id'),
            'item_id': self.root.get('item_id'),
            'revision': self.root.get('revision'),
            'selections': selections,
            'values': values,
            'warnings': list(self.warnings),
            'origins': origins,
        }

    def _collect(self, structure_id: Any, out: Dict[Any, bool]) -> None:
        for lid in self.line_ids_by_structure.get(structure_id, []):
            line = self.lines.get(lid, {})
            cell = self.state.get(lid)
            optional = bool(line.get('optional_flag'))
            if optional and cell is not None:
                out[lid] = bool(cell.get('value'))
            if cell is not None and cell.get('value'):
                child = self.children.get(lid)
                if child is not None:
                    self._collect(child, out)

    # ---------- 冲突 ----------

    def _raise_conflict(self, rule: Optional[Dict[str, Any]],
                        target: Dict[str, Any], current: Dict[str, Any]) -> None:
        evidence = []
        if rule is not None:
            evidence.append(self._rule_evidence(rule))
        evidence.append(self._source_evidence(current))
        conflict = {'target': target, 'rules': evidence}

        severity = str((rule or {}).get('severity') or 'blocking')
        if severity == 'warning':
            warning = {
                'rule': 'config_rule_warning',
                'message': (rule or {}).get('message') or '规则与既有选择冲突，已保留先生效结果',
                'rule_id': (rule or {}).get('id'),
                'target': target,
                'kept_source': current.get('source'),
                'kept_rule_id': current.get('rule_id'),
            }
            # 前向传播会重复进入同一条规则，告警按 (规则, 目标) 去重
            key = (warning['rule_id'], (target or {}).get('id'))
            if not any(
                (item.get('rule_id'), (item.get('target') or {}).get('id')) == key
                for item in self.warnings
            ):
                self.warnings.append(warning)
            return
        raise ItemStructureRuleError(
            f"配置冲突：{(rule or {}).get('message') or '规则与既有选择矛盾'}",
            rule='config_conflict', field_name='selections', conflicts=[conflict])

    def _rule_evidence(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        terms = self.terms.get(rule.get('id'), {'if': [], 'then': []})
        return {
            'rule_id': rule.get('id'),
            'rule_type': rule.get('rule_type'),
            'priority': rule.get('priority'),
            'severity': rule.get('severity'),
            'message': rule.get('message'),
            'if': [self._term_evidence(term) for term in terms.get('if', [])],
            'then': [self._term_evidence(term) for term in terms.get('then', [])],
        }

    @staticmethod
    def _term_evidence(term: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'clause': term.get('clause'),
            'target_type': term.get('target_type'),
            'target_line_id': term.get('target_line_id'),
            'target_class_item_id': term.get('target_class_item_id'),
            'attribute_code': term.get('attribute_code'),
            'operator': term.get('operator'),
            'value_text': term.get('value_text'),
            'value_number': term.get('value_number'),
            'value_number_to': term.get('value_number_to'),
            'value_list': term.get('value_list'),
        }

    def _source_evidence(self, current: Dict[str, Any]) -> Dict[str, Any]:
        source = current.get('source')
        evidence = {'source': source, 'rule_id': current.get('rule_id')}
        if source == 'rule' and current.get('rule_id'):
            for rule in self.rules:
                if rule.get('id') == current.get('rule_id'):
                    evidence['rule_type'] = rule.get('rule_type')
                    evidence['message'] = rule.get('message')
                    evidence['terms'] = self._rule_evidence(rule)
                    break
        return evidence

    # ---------- 查询（可覆写，便于单测注入）----------

    def _fetch_structure(self, structure_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, item_id, usage, alternative_no, revision, status, "
                "base_qty, min_select, max_select, valid_from, valid_to "
                f"FROM {_STRUCTURE_TABLE} WHERE id = ?", [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_rule] 读取结构头失败: {e}')
            raise
        return rows[0] if rows else None

    def _fetch_lines(self, structure_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, line_no, component_item_id, qty_per, fixed_qty, "
                "optional_flag, default_flag, default_qty, min_qty, max_qty, "
                "phantom_flag, valid_from, valid_to "
                f"FROM {_LINE_TABLE} WHERE structure_id = ? ORDER BY line_no",
                [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_rule] 读取结构行失败: {e}')
            raise
        return rows or []

    def _fetch_attributes(self, structure_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT attribute_code, required_flag, default_value_text "
                f"FROM {_ATTRIBUTE_TABLE} WHERE structure_id = ? ORDER BY seq, id",
                [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_rule] 读取模型特征失败: {e}')
            return []
        return rows or []

    def _fetch_item(self, item_id: Any):
        try:
            rows = self.ds.query(
                "SELECT id, code, structure_role, status FROM items WHERE id = ?",
                [item_id])
        except Exception as e:
            logger.warning(f'[item_structure_rule] 读取物料失败: {e}')
            return _QUERY_FAILED
        return rows[0] if rows else None

    def _item_role(self, item_id: Any) -> str:
        state = self._fetch_item(item_id)
        if state is _QUERY_FAILED or state is None:
            return ''
        return str(state.get('structure_role') or '')

    def _find_active_structure(self, item_id: Any, usage: Any,
                               alternative_no: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, item_id, usage, alternative_no, revision, status, "
                "base_qty, min_select, max_select, valid_from, valid_to "
                f"FROM {_STRUCTURE_TABLE} "
                "WHERE item_id = ? AND usage = ? AND alternative_no = ? "
                "AND status = 'active' ORDER BY valid_from DESC, id DESC",
                [item_id, usage, alternative_no])
        except Exception as e:
            logger.warning(f'[item_structure_rule] 解析生效结构失败: {e}')
            raise
        matched = [row for row in (rows or [])
                   if _covers(self.as_of, row.get('valid_from'), row.get('valid_to'))]
        if len(matched) > 1:
            raise ItemStructureRuleError(
                f'物料 {item_id} 在 {self.as_of} 命中 {len(matched)} 个生效结构版本，'
                '生效区间重叠（数据异常）',
                rule='item_structure_version_ambiguous', field_name='structure_id')
        return matched[0] if matched else None

    def _fetch_rules(self, structure_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, structure_id, code, rule_type, severity, priority, "
                "message, status FROM config_rules "
                "WHERE structure_id = ? AND status = 'active' "
                "ORDER BY priority, id", [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_rule] 读取配置规则失败: {e}')
            return []
        return rows or []

    def _fetch_terms(self, rule_ids: Sequence[Any]) -> List[Dict[str, Any]]:
        if not rule_ids:
            return []
        placeholders = ', '.join('?' for _ in rule_ids)
        try:
            rows = self.ds.query(
                "SELECT id, rule_id, seq, clause, target_type, target_line_id, "
                "target_class_item_id, attribute_code, operator, value_text, "
                "value_number, value_number_to, value_list "
                f"FROM config_rule_terms WHERE rule_id IN ({placeholders}) "
                "ORDER BY rule_id, seq", list(rule_ids))
        except Exception as e:
            logger.warning(f'[item_structure_rule] 读取规则条件项失败: {e}')
            return []
        return rows or []

    # ---------- 数量 ----------

    def _line_qty(self, line: Dict[str, Any], parent_qty: Any,
                  base_qty: Any) -> Decimal:
        lid = line.get('id')
        optional = bool(line.get('optional_flag'))
        if lid in self.quantities:
            return _to_decimal(self.quantities[lid])
        if optional and not _is_blank(line.get('default_qty')):
            return _to_decimal(line.get('default_qty'))
        if not _is_blank(line.get('fixed_qty')):
            return _to_decimal(line.get('fixed_qty'))
        denominator = _to_decimal(base_qty)
        qty = _to_decimal(parent_qty) * _to_decimal(line.get('qty_per'))
        return qty / denominator if denominator else qty
