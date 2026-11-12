# -*- coding: utf-8 -*-
"""配置编排服务 —— describe / validate / solve / freeze / read。

依据: docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md §6 / §7 / §8

职责:
  describe  读结构版本 + 模型特征（含值域）+ 结构行，供前端出表单。
  validate  规则引擎（P3）+ 手工选择（P2）串联，只校验不落库。
  solve     校验通过后一次写入 configuration / configuration_value /
            configuration_component 三表，并给出 config_hash。
  freeze    重算 hash 比对（R11）后置 frozen；冻结后实例只读。
  read      回读头 / 特征值 / 组件，status 折叠为对外两态。

错误码（§8.3，对外只有六个）:
  CONFIG_INCOMPLETE / CONFIG_CONFLICT / CONFIG_INVALID_VALUE /
  CONFIG_VERSION_MISMATCH / CONFIG_TIMEOUT / CONFIG_PRICE_MISSING（P4）

取值口径:
  - 特征值按 attribute_definition.data_type 落到 value_text / value_number /
    value_boolean；multi_value_flag 时按 seq 拆行。
  - config_hash 按 §6.4 规范化：编码小写、数值去尾零、布尔 1/0、多值升序、
    空值不拼接，model_code|revision|特征|组件 顺序拼接后 sha256。
  - 组件单位取 component_item.base_uom → uoms.code，回退结构 base_uom_code；
    两者皆空只告警，不阻断（组件 uom_code 列 required，落空串）。
  - 对外 status 折叠：draft / invalid → invalid；solved / frozen / superseded → solved。

查询方法均可覆写，便于单测注入。
"""

import hashlib
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from meta.services.item_structure_guard_service import (
    _is_blank,
    _to_date_text,
    _to_decimal,
)
from meta.services.item_structure_rule_engine import (
    ItemStructureRuleEngine,
    ItemStructureRuleError,
)
from meta.services.item_structure_select_service import (
    ItemStructureSelectError,
    ItemStructureSelectService,
    _normalize_selections,
)

logger = logging.getLogger(__name__)

_STRUCTURE_TABLE = 'item_structures'
_LINE_TABLE = 'item_structure_lines'
_ATTRIBUTE_TABLE = 'item_structure_attributes'
_DEFINITION_TABLE = 'attribute_definitions'
_ENUM_VALUE_TABLE = 'enum_values'
_ITEM_TABLE = 'items'
_UOM_TABLE = 'uoms'
_CONFIGURATION_TABLE = 'configurations'
_VALUE_TABLE = 'configuration_values'
_COMPONENT_TABLE = 'configuration_components'

_STATUS_OUT = {
    'draft': 'invalid',
    'invalid': 'invalid',
    'solved': 'solved',
    'frozen': 'solved',
    'superseded': 'solved',
}

# 结构缺陷类错误：六个对外码里没有专门项，归到 CONFIG_CONFLICT（选择集不可解）
_STRUCTURE_DEFECT_RULES = (
    'item_structure_cycle',
    'item_structure_max_depth_exceeded',
    'item_structure_option_class_missing_structure',
)

# 版本类错误
_VERSION_RULES = (
    'item_structure_not_found',
    'item_structure_version_ambiguous',
)


class ItemStructureConfigError(ValueError):
    """编排失败。`code` 为对外错误码，`conflicts` 为最小冲突集。"""

    def __init__(self, message: str, code: str = 'CONFIG_INVALID_VALUE',
                 rule: str = '', field_name: str = '',
                 conflicts: Optional[List[Dict[str, Any]]] = None,
                 configuration_id: Any = None, warnings: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.code = code
        self.rule = rule
        self.field_name = field_name
        self.conflicts = conflicts or []
        self.configuration_id = configuration_id
        self.warnings = warnings or []


def _map_error(exc: Exception) -> Tuple[str, str]:
    """内部 rule → (对外码, rule)。"""
    rule = str(getattr(exc, 'rule', '') or '')
    if rule == 'config_timeout':
        return 'CONFIG_TIMEOUT', rule
    if rule == 'config_conflict':
        return 'CONFIG_CONFLICT', rule
    if rule == 'item_structure_attribute_required':
        return 'CONFIG_INCOMPLETE', rule
    if rule in ('item_structure_select_too_few', 'item_structure_select_too_many'):
        return 'CONFIG_CONFLICT', rule
    if rule in _VERSION_RULES:
        return 'CONFIG_VERSION_MISMATCH', rule
    if rule in _STRUCTURE_DEFECT_RULES:
        return 'CONFIG_CONFLICT', rule
    if rule in ('item_structure_select_qty_range',
                'item_structure_select_line_unknown'):
        return 'CONFIG_INVALID_VALUE', rule
    return 'CONFIG_INVALID_VALUE', rule


# ---------- 规范化（§6.4） ----------

_RANGE_RE = re.compile(r'(-?\d+(?:\.\d+)?)\s*[,~]\s*(-?\d+(?:\.\d+)?)')


def _norm_code(value: Any) -> str:
    return str(value).strip().lower() if not _is_blank(value) else ''


def _norm_number(value: Any) -> str:
    if _is_blank(value):
        return ''
    number = _to_decimal(value)
    text = format(number.normalize(), 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def _quantize_qty(value: Any) -> float:
    """用量按 schema 的 6 位小数收敛，去掉 float 运算噪声。"""
    return float(_to_decimal(value).quantize(Decimal('0.000001')))


def _parse_boolean(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value != 0
    text = str(value).strip().lower()
    if text in ('1', 'true', 'y', 'yes', 'on'):
        return True
    if text in ('0', 'false', 'n', 'no', 'off'):
        return False
    return None


def _norm_scalar(value: Any, data_type: str) -> Optional[str]:
    """按 data_type 归一化单个标量；空值返回 None（不参与拼接）。"""
    if _is_blank(value):
        return None
    if data_type in ('number', 'integer'):
        text = _norm_number(value)
        return text or None
    if data_type == 'boolean':
        flag = _parse_boolean(value)
        return None if flag is None else ('1' if flag else '0')
    return str(value).strip() or None


class ItemStructureConfigService:
    """配置域的四个门面方法 + 冻结 / 回读。"""

    def __init__(self, data_source, rule_engine=None, select_service=None):
        self.ds = data_source
        self._engine = rule_engine or ItemStructureRuleEngine(data_source)
        self._select = select_service or ItemStructureSelectService(data_source)

    # ---------- describe ----------

    def describe(self, structure_id: Any, as_of: Optional[str] = None) -> Dict[str, Any]:
        """结构版本 + 特征声明（含值域）+ 结构行。"""
        head = self._fetch_structure_head(structure_id)
        if not head:
            raise ItemStructureConfigError(
                f'结构不存在: {structure_id}', code='CONFIG_VERSION_MISMATCH',
                rule='item_structure_not_found', field_name='structure_id')
        item = self._fetch_item(head.get('item_id')) or {}
        as_of_text = _to_date_text(as_of) or date.today().isoformat()

        component_ids = {
            line.get('component_item_id')
            for line in self._fetch_lines(head.get('id'))
        }
        items = self._fetch_items([cid for cid in component_ids if cid is not None])

        return {
            'structure_id': head.get('id'),
            'item_id': head.get('item_id'),
            'model_code': item.get('code'),
            'revision': head.get('revision'),
            'status': head.get('status'),
            'base_qty': float(_to_decimal(head.get('base_qty') or 1)),
            'base_uom_code': head.get('base_uom_code'),
            'min_select': head.get('min_select'),
            'max_select': head.get('max_select'),
            'valid_from': head.get('valid_from'),
            'valid_to': head.get('valid_to'),
            'as_of': as_of_text,
            'is_model': str(item.get('structure_role') or '') == 'model',
            'characteristics': self._describe_characteristics(head.get('id')),
            'lines': [
                {
                    'line_id': line.get('id'),
                    'line_no': line.get('line_no'),
                    'component_item_id': line.get('component_item_id'),
                    'component_code': (items.get(line.get('component_item_id')) or {}).get('code'),
                    'component_name': (items.get(line.get('component_item_id')) or {}).get('name'),
                    'structure_role': (items.get(line.get('component_item_id')) or {}).get('structure_role'),
                    'qty_per': line.get('qty_per'),
                    'fixed_qty': line.get('fixed_qty'),
                    'optional_flag': bool(line.get('optional_flag')),
                    'default_flag': bool(line.get('default_flag')),
                    'default_qty': line.get('default_qty'),
                    'min_qty': line.get('min_qty'),
                    'max_qty': line.get('max_qty'),
                    'phantom_flag': bool(line.get('phantom_flag')),
                }
                for line in self._fetch_lines(head.get('id'))
            ],
        }

    def _describe_characteristics(self, structure_id: Any) -> List[Dict[str, Any]]:
        return [
            {
                'attribute_code': row.get('attribute_code'),
                'name': row.get('name'),
                'data_type': row.get('data_type') or 'string',
                'usage_class': row.get('usage_class'),
                'value_domain_type': row.get('value_domain_type') or 'none',
                'value_domain_ref': row.get('value_domain_ref'),
                'multi_value_flag': bool(row.get('multi_value_flag')),
                'uom_code': row.get('uom_code') or row.get('attr_uom_code'),
                'required_flag': bool(row.get('required_flag')),
                'default_value_text': row.get('default_value_text'),
                'seq': row.get('seq'),
                'ui_widget': row.get('ui_widget'),
            }
            for row in self._fetch_characteristics(structure_id)
        ]

    # ---------- validate ----------

    def validate(self, structure_id: Any, selections: Any = None,
                 quantities: Optional[Mapping[Any, Any]] = None,
                 attribute_values: Optional[Mapping[str, Any]] = None,
                 qty: Any = 1, as_of: Optional[str] = None,
                 max_depth: int = 20,
                 model_version: Any = None) -> Dict[str, Any]:
        """只校验不落库；失败也返回结构（valid=False + 错误码 + 最小冲突集）。"""
        as_of_text = _to_date_text(as_of) or date.today().isoformat()
        try:
            head = self._fetch_structure_head(structure_id)
            if not head:
                raise ItemStructureConfigError(
                    f'结构不存在: {structure_id}', code='CONFIG_VERSION_MISMATCH',
                    rule='item_structure_not_found', field_name='structure_id')
            if not _is_blank(model_version) \
                    and str(model_version) != str(head.get('revision')):
                raise ItemStructureConfigError(
                    f'请求的模型版本 {model_version} 与实例锚定的版本 '
                    f'{head.get("revision")} 不一致',
                    code='CONFIG_VERSION_MISMATCH',
                    rule='configuration_model_version_mismatch',
                    field_name='model_version')

            declarations = self._fetch_characteristics(structure_id)
            prepared = self._prepare_values(declarations, attribute_values or {})
            evaluation = self._engine.evaluate(
                structure_id, selections, quantities, prepared['raw'],
                qty, as_of_text, max_depth)
            selection = self._select.select(
                structure_id, evaluation['selections'], quantities, prepared['raw'],
                qty, as_of_text, max_depth)
        except ItemStructureConfigError as exc:
            return self._failure(exc)
        except (ItemStructureRuleError, ItemStructureSelectError) as exc:
            code, rule = _map_error(exc)
            return self._failure(ItemStructureConfigError(
                str(exc), code=code, rule=rule,
                field_name=getattr(exc, 'field_name', ''),
                conflicts=getattr(exc, 'conflicts', []) or []))

        values = self._merge_values(declarations, prepared, evaluation)
        components = self._build_components(
            selection, evaluation, head, _normalize_selections(selections))
        return {
            'valid': True,
            'error_code': None,
            'message': None,
            'rule': None,
            'conflicts': [],
            'warnings': list(evaluation.get('warnings') or [])
                        + list(selection.get('warnings') or [])
                        + components['warnings'],
            'structure_id': head.get('id'),
            'item_id': head.get('item_id'),
            'revision': head.get('revision'),
            'as_of': as_of_text,
            'selections': evaluation.get('selections') or {},
            'values': values,
            'components': components['rows'],
            'skipped_optional': selection.get('skipped_optional'),
        }

    @staticmethod
    def _failure(exc: 'ItemStructureConfigError') -> Dict[str, Any]:
        return {
            'valid': False,
            'error_code': exc.code,
            'message': str(exc),
            'rule': exc.rule,
            'conflicts': exc.conflicts,
            'warnings': exc.warnings,
            'structure_id': None,
            'selections': {},
            'values': [],
            'components': [],
        }

    # ---------- 特征值 ----------

    def _prepare_values(self, declarations: Sequence[Dict[str, Any]],
                        attribute_values: Mapping[str, Any]) -> Dict[str, Any]:
        """校验入参特征：编码须已声明、类型/值域须相容；给出按类型归一后的原始值。"""
        declared = {str(row.get('attribute_code')): row for row in declarations}
        raw: Dict[str, Any] = {}
        for code, value in attribute_values.items():
            code = str(code)
            declaration = declared.get(code)
            if declaration is None:
                raise ItemStructureConfigError(
                    f'特征 {code} 未在模型版本中声明',
                    code='CONFIG_INVALID_VALUE',
                    rule='configuration_value_undeclared',
                    field_name='attribute_values')
            multi = bool(declaration.get('multi_value_flag'))
            if multi and isinstance(value, (list, tuple, set)):
                raw[code] = [self._coerce_scalar(code, declaration, item)
                             for item in value]
            else:
                raw[code] = self._coerce_scalar(code, declaration, value)
        return {'raw': {code: value for code, value in raw.items()
                        if value is not None
                        and not (isinstance(value, list) and not value)}}

    def _coerce_scalar(self, code: str, declaration: Dict[str, Any],
                       value: Any) -> Any:
        if _is_blank(value):
            return None
        data_type = str(declaration.get('data_type') or 'string')
        if data_type in ('number', 'integer'):
            try:
                number = Decimal(str(value).strip())
            except (InvalidOperation, ValueError):
                raise ItemStructureConfigError(
                    f'特征 {code} 的取值 {value!r} 不是合法数值',
                    code='CONFIG_INVALID_VALUE',
                    rule='configuration_value_type_invalid',
                    field_name='attribute_values')
            if data_type == 'integer' and number != number.to_integral_value():
                raise ItemStructureConfigError(
                    f'特征 {code} 的取值 {value!r} 不是整数',
                    code='CONFIG_INVALID_VALUE',
                    rule='configuration_value_type_invalid',
                    field_name='attribute_values')
            self._check_domain(code, declaration, number, data_type)
            return number
        if data_type == 'boolean':
            flag = _parse_boolean(value)
            if flag is None:
                raise ItemStructureConfigError(
                    f'特征 {code} 的取值 {value!r} 不是合法布尔值',
                    code='CONFIG_INVALID_VALUE',
                    rule='configuration_value_type_invalid',
                    field_name='attribute_values')
            self._check_domain(code, declaration, flag, data_type)
            return flag
        self._check_domain(code, declaration, value, data_type)
        return str(value).strip()

    def _check_domain(self, code: str, declaration: Dict[str, Any],
                      value: Any, data_type: str) -> None:
        domain_type = str(declaration.get('value_domain_type') or 'none')
        ref = declaration.get('value_domain_ref')
        if _is_blank(ref) or domain_type == 'none':
            return
        if domain_type == 'list':
            self._check_enum_member(code, str(ref), value)
            return
        if domain_type != 'range' or data_type not in ('number', 'integer'):
            return
        matched = _RANGE_RE.search(str(ref))
        if not matched:
            return
        low, high = Decimal(matched.group(1)), Decimal(matched.group(2))
        number = _to_decimal(value)
        if number is None:
            return
        if number < low or number > high:
            raise ItemStructureConfigError(
                f'特征 {code} 的取值 {value} 不在值域 {low}~{high} 内',
                code='CONFIG_INVALID_VALUE',
                rule='configuration_value_domain_invalid',
                field_name='attribute_values')

    def _check_enum_member(self, code: str, enum_type_code: str, value: Any) -> None:
        """list 型值域：值必须是该枚举类型下的成员（查询失败 fail-open）。"""
        text = str(value).strip().lower()
        try:
            rows = self.ds.query(
                f"SELECT 1 FROM {_ENUM_VALUE_TABLE} "
                "WHERE enum_type_id = ? AND lower(code) = ? LIMIT 1",
                [enum_type_code, text])
        except Exception as e:
            logger.warning(f'[item_structure_config] 校验枚举值域失败: {e}')
            return
        if not rows:
            raise ItemStructureConfigError(
                f'特征 {code} 的取值 {value!r} 不在枚举 {enum_type_code} 内',
                code='CONFIG_INVALID_VALUE',
                rule='configuration_value_domain_invalid',
                field_name='attribute_values')

    def _merge_values(self, declarations: Sequence[Dict[str, Any]],
                      prepared: Dict[str, Any],
                      evaluation: Dict[str, Any]) -> List[Dict[str, Any]]:
        """引擎给出的默认 / 规则值与用户入参合并，按 data_type 落到值列。"""
        from_engine = {str(row.get('attribute_code')): row
                       for row in evaluation.get('values') or []}
        rows: List[Dict[str, Any]] = []
        for declaration in declarations:
            code = str(declaration.get('attribute_code') or '')
            if not code:
                continue
            data_type = str(declaration.get('data_type') or 'string')
            multi = bool(declaration.get('multi_value_flag'))
            source, rule_id = 'user', None

            if code in prepared['raw']:
                value = prepared['raw'][code]
            elif code in from_engine:
                cell = from_engine[code]
                value = self._typed(declaration, cell.get('value_text'))
                source = str(cell.get('source') or 'default')
                rule_id = cell.get('source_rule_id')
            elif not _is_blank(declaration.get('default_value_text')):
                value = self._typed(declaration,
                                    declaration.get('default_value_text'))
                source = 'default'
            else:
                continue

            if value is None:
                continue
            sequence = list(value) if isinstance(value, (list, tuple)) and multi \
                else [value]
            for index, item in enumerate(sequence, 1):
                typed = self._typed(declaration, item)
                if typed is None:
                    continue
                rows.append(self._value_row(code, index, typed, data_type,
                                            source, rule_id))
        return rows

    def _typed(self, declaration: Dict[str, Any], value: Any) -> Any:
        if _is_blank(value):
            return None
        try:
            return self._coerce_scalar(
                str(declaration.get('attribute_code') or ''), declaration, value)
        except ItemStructureConfigError:
            # 库内默认 / 规则值不合法时不阻断求解，交由守卫在写入侧拦截
            return None

    @staticmethod
    def _value_row(code: str, seq: int, value: Any, data_type: str,
                   source: str, rule_id: Any) -> Dict[str, Any]:
        row = {
            'attribute_code': code,
            'seq': seq,
            'value_text': None,
            'value_number': None,
            'value_boolean': None,
            'source': source,
            'source_rule_id': rule_id,
        }
        if data_type in ('number', 'integer'):
            row['value_number'] = float(value)
        elif data_type == 'boolean':
            row['value_boolean'] = 1 if value else 0
        else:
            row['value_text'] = str(value)
        return row

    # ---------- 组件 ----------

    def _build_components(self, selection: Dict[str, Any],
                          evaluation: Dict[str, Any],
                          head: Dict[str, Any],
                          user_selections: Mapping[Any, bool]) -> Dict[str, Any]:
        origins = evaluation.get('origins') or {}
        user_lines = {lid for lid, value in user_selections.items() if value}
        items = self._fetch_items([row.get('component_item_id')
                                   for row in selection.get('components') or []])
        fallback_uom = head.get('base_uom_code')
        warnings: List[Dict[str, Any]] = []

        rows: List[Dict[str, Any]] = []
        for index, component in enumerate(selection.get('components') or [], 1):
            line_id = component.get('structure_line_id')
            if line_id in origins:
                source, rule_id = 'rule', origins[line_id]
            elif line_id in user_lines:
                source, rule_id = 'user', None
            else:
                source, rule_id = 'auto', None

            item = items.get(component.get('component_item_id')) or {}
            uom_code = item.get('uom_code') or fallback_uom
            if _is_blank(uom_code):
                warnings.append({
                    'rule': 'configuration_component_uom_missing',
                    'message': f'组件 {component.get("component_key")} 缺少计量单位',
                    'component_key': component.get('component_key'),
                })
                uom_code = ''
            rows.append({
                'component_key': component.get('component_key'),
                'structure_line_id': line_id,
                'component_item_id': component.get('component_item_id'),
                'qty': _quantize_qty(component.get('qty')),
                'uom_code': uom_code,
                'parent_component_key': component.get('parent_component_key'),
                'selection_source': source,
                'source_rule_id': rule_id,
                'substitute_for_key': None,
                'seq': index,
            })
        return {'rows': rows, 'warnings': warnings}

    # ---------- solve ----------

    def solve(self, structure_id: Any, selections: Any = None,
              quantities: Optional[Mapping[Any, Any]] = None,
              attribute_values: Optional[Mapping[str, Any]] = None,
              qty: Any = 1, as_of: Optional[str] = None, max_depth: int = 20,
              model_version: Any = None,
              context: Optional[Mapping[str, Any]] = None,
              record_invalid: bool = False) -> Dict[str, Any]:
        """校验通过后落三表并返回实例；失败抛 ItemStructureConfigError。

        record_invalid = True 时，失败也落一条 status = invalid 的头（带
        validation_result_json），便于试算面板留痕。
        """
        result = self.validate(structure_id, selections, quantities,
                               attribute_values or {},
                               qty, as_of, max_depth, model_version)
        if not result['valid']:
            configuration_id = None
            if record_invalid:
                configuration_id = self._insert_invalid(
                    structure_id, result, context)
            raise ItemStructureConfigError(
                result['message'] or '配置求解失败',
                code=result['error_code'] or 'CONFIG_INVALID_VALUE',
                rule=result.get('rule') or '',
                conflicts=result.get('conflicts') or [],
                configuration_id=configuration_id,
                warnings=result.get('warnings') or [])

        head = self._fetch_structure_head(result['structure_id'])
        item = self._fetch_item(head.get('item_id')) or {}
        model_code = item.get('code')
        config_hash = self._compute_hash(
            model_code, head.get('revision'), result['values'], result['components'],
            self._item_codes(result['components']))
        now = datetime.now().isoformat(timespec='seconds')

        head_row = {
            'model_item_id': head.get('item_id'),
            'structure_id': head.get('id'),
            'status': 'solved',
            'config_hash': config_hash,
            'revision': 1,
            'reused_from_id': None,
            'match_policy_used': str(item.get('config_match_policy') or 'no'),
            'source_level': 'L2',
            'context_json': json.dumps(context, ensure_ascii=False)
                            if context else None,
            'validation_result_json': json.dumps(
                {'error_code': None, 'warnings': result['warnings']},
                ensure_ascii=False) if result['warnings'] else None,
            'solved_at': now,
        }

        with self.ds.transaction():
            configuration_id = self.ds.insert(_CONFIGURATION_TABLE, head_row)
            for value in result['values']:
                self.ds.insert(_VALUE_TABLE, {
                    'configuration_id': configuration_id,
                    **value,
                })
            for component in result['components']:
                self.ds.insert(_COMPONENT_TABLE, {
                    'configuration_id': configuration_id,
                    **component,
                })

        # [2026-10-31 §12] auto 物化不再挂在求解：配置冻结时由
        # ConfigurationGuardInterceptor.after_action 触发（承诺点语义）。
        response = {
            'configuration_id': configuration_id,
            'config_hash': config_hash,
            'model_item_id': head.get('item_id'),
            'model_code': model_code,
            'structure_id': head.get('id'),
            'model_version': head.get('revision'),
            'status': 'solved',
            'status_out': 'solved',
            'revision': 1,
            'values': result['values'],
            'components': result['components'],
            'warnings': result['warnings'],
        }
        return response

    def _insert_invalid(self, structure_id: Any, result: Dict[str, Any],
                        context: Optional[Mapping[str, Any]]) -> Any:
        head = self._fetch_structure_head(structure_id) or {}
        item = self._fetch_item(head.get('item_id')) or {}
        payload = {
            'error_code': result.get('error_code'),
            'message': result.get('message'),
            'rule': result.get('rule'),
            'conflicts': result.get('conflicts') or [],
            'warnings': result.get('warnings') or [],
        }
        return self.ds.insert(_CONFIGURATION_TABLE, {
            'model_item_id': head.get('item_id'),
            'structure_id': head.get('id') or structure_id,
            'status': 'invalid',
            'config_hash': None,
            'revision': 1,
            'reused_from_id': None,
            'match_policy_used': str(item.get('config_match_policy') or 'no'),
            'source_level': 'L2',
            'context_json': json.dumps(context, ensure_ascii=False)
                            if context else None,
            'validation_result_json': json.dumps(payload, ensure_ascii=False),
            'solved_at': None,
        })

    # ---------- freeze / read ----------

    def freeze(self, configuration_id: Any) -> Dict[str, Any]:
        """重算 hash 比对后置 frozen；已冻结时幂等返回。"""
        head = self._fetch_configuration(configuration_id)
        if not head:
            raise ItemStructureConfigError(
                f'配置实例不存在: {configuration_id}',
                code='CONFIG_VERSION_MISMATCH',
                rule='configuration_not_found', field_name='id')
        status = str(head.get('status') or '')
        if status == 'frozen':
            return self.read(configuration_id)
        if status != 'solved':
            raise ItemStructureConfigError(
                f'实例状态 {status} 不允许冻结，只有 solved 可冻结',
                code='CONFIG_CONFLICT',
                rule='configuration_status_invalid', field_name='status')

        check = self.verify_hash(configuration_id)
        if not check['match']:
            raise ItemStructureConfigError(
                '实例内容与 config_hash 不一致，拒绝冻结（R11）',
                code='CONFIG_INVALID_VALUE',
                rule='configuration_hash_mismatch', field_name='config_hash')

        self.ds.update(_CONFIGURATION_TABLE, configuration_id, {
            'status': 'frozen',
            'frozen_at': datetime.now().isoformat(timespec='seconds'),
        })
        return self.read(configuration_id)

    def read(self, configuration_id: Any) -> Dict[str, Any]:
        """回读头 / 特征值 / 组件。"""
        head = self._fetch_configuration(configuration_id)
        if not head:
            raise ItemStructureConfigError(
                f'配置实例不存在: {configuration_id}',
                code='CONFIG_VERSION_MISMATCH',
                rule='configuration_not_found', field_name='id')
        item = self._fetch_item(head.get('model_item_id')) or {}
        structure = self._fetch_structure_head(head.get('structure_id')) or {}
        status = str(head.get('status') or '')
        return {
            'configuration_id': head.get('id'),
            'model_item_id': head.get('model_item_id'),
            'model_code': item.get('code'),
            'structure_id': head.get('structure_id'),
            'model_version': structure.get('revision'),
            'status': status,
            'status_out': _STATUS_OUT.get(status, 'invalid'),
            'config_hash': head.get('config_hash'),
            'revision': head.get('revision'),
            'reused_from_id': head.get('reused_from_id'),
            'match_policy_used': head.get('match_policy_used'),
            'source_level': head.get('source_level'),
            'context': self._loads(head.get('context_json')),
            'validation_result': self._loads(head.get('validation_result_json')),
            'solved_at': head.get('solved_at'),
            'frozen_at': head.get('frozen_at'),
            'values': self._fetch_values(configuration_id),
            'components': self._fetch_components(configuration_id),
        }

    def verify_hash(self, configuration_id: Any) -> Dict[str, Any]:
        """按库内三表重算 hash，与头上的 config_hash 比对（R11）。"""
        head = self._fetch_configuration(configuration_id)
        if not head:
            raise ItemStructureConfigError(
                f'配置实例不存在: {configuration_id}',
                code='CONFIG_VERSION_MISMATCH',
                rule='configuration_not_found', field_name='id')
        item = self._fetch_item(head.get('model_item_id')) or {}
        structure = self._fetch_structure_head(head.get('structure_id')) or {}
        values = self._fetch_values(configuration_id)
        components = self._fetch_components(configuration_id)
        computed = self._compute_hash(
            item.get('code'), structure.get('revision'), values, components)
        stored = head.get('config_hash')
        return {
            'configuration_id': configuration_id,
            'stored': stored,
            'computed': computed,
            'match': bool(stored) and stored == computed,
        }

    # ---------- hash ----------

    def _compute_hash(self, model_code: Any, model_version: Any,
                      values: Sequence[Mapping[str, Any]],
                      components: Sequence[Mapping[str, Any]],
                      item_codes: Optional[Mapping[Any, Any]] = None) -> str:
        """§6.4：model_code|revision|特征|组件，逐项规范化后 sha256。"""
        grouped: Dict[str, List[str]] = {}
        for value in values:
            code = _norm_code(value.get('attribute_code'))
            if not code:
                continue
            if value.get('value_boolean') is not None:
                text = '1' if value.get('value_boolean') else '0'
            elif value.get('value_number') is not None:
                text = _norm_number(value.get('value_number'))
            else:
                text = _norm_scalar(value.get('value_text'), 'string')
            if text:
                grouped.setdefault(code, []).append(text)
        characteristics = ','.join(
            f'{code}=' + ','.join(sorted(grouped[code]))
            for code in sorted(grouped))

        codes = item_codes or {}
        entries = []
        for component in components:
            key = _norm_code(component.get('component_key'))
            if not key:
                continue
            item_code = _norm_code(
                component.get('component_item_code')
                or codes.get(component.get('component_item_id')))
            entries.append(
                f'{key}:{item_code}:{_norm_number(component.get("qty"))}')
        entries.sort(key=lambda text: text.split(':', 1)[0])

        payload = '|'.join([
            _norm_code(model_code),
            str(model_version),
            characteristics,
            ','.join(entries),
        ])
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    # ---------- 查询（可覆写，便于单测注入） ----------

    def _fetch_structure_head(self, structure_id: Any) -> Optional[Dict[str, Any]]:
        """读结构头，并把基准单位统一成 `base_uom_code`。

        [口径] 表上存的是 `base_uom_id`（引用 uoms），而下游要的是单位编码；
        这里一次 JOIN 等价物化出 `base_uom_code`，避免各调用点各自换算。
        `SELECT *` 而非枚举列：结构表列随域演进而增删，枚举列会在新旧库
        之间产生"列不存在"的硬失败（真实库与内存测试库曾因此不一致）。
        """
        try:
            rows = self.ds.query(
                f"SELECT * FROM {_STRUCTURE_TABLE} WHERE id = ?", [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_config] 读取结构头失败: {e}')
            raise
        if not rows:
            return None
        head = dict(rows[0])
        head.setdefault('base_uom_code', None)
        if not head.get('base_uom_code') and head.get('base_uom_id') is not None:
            head['base_uom_code'] = self._uom_code(head.get('base_uom_id'))
        return head

    def _fetch_lines(self, structure_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, line_no, component_item_id, qty_per, fixed_qty, "
                "optional_flag, default_flag, default_qty, min_qty, max_qty, "
                "phantom_flag, valid_from, valid_to "
                f"FROM {_LINE_TABLE} WHERE structure_id = ? ORDER BY line_no",
                [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_config] 读取结构行失败: {e}')
            return []
        return rows or []

    def _fetch_characteristics(self, structure_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT a.attribute_code AS attribute_code, a.required_flag, "
                "a.default_value_text, a.seq, a.ui_widget, "
                "d.name, d.data_type, d.usage_class, d.value_domain_type, "
                "d.value_domain_ref, d.multi_value_flag, d.uom_code, "
                "d.uom_code AS attr_uom_code "
                f"FROM {_ATTRIBUTE_TABLE} a "
                f"LEFT JOIN {_DEFINITION_TABLE} d "
                "ON d.code = a.attribute_code AND d.tenant_id = 0 "
                f"WHERE a.structure_id = ? ORDER BY a.seq, a.id", [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_config] 读取模型特征失败: {e}')
            return []
        return rows or []

    def _fetch_item(self, item_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, code, name, structure_role, status, base_uom, "
                f"config_match_policy FROM {_ITEM_TABLE} WHERE id = ?", [item_id])
        except Exception as e:
            logger.warning(f'[item_structure_config] 读取物料失败: {e}')
            return None
        if not rows:
            return None
        row = dict(rows[0])
        row['uom_code'] = self._uom_code(row.get('base_uom'))
        return row

    def _fetch_items(self, item_ids: Sequence[Any]) -> Dict[Any, Dict[str, Any]]:
        ids = sorted({item for item in item_ids if item is not None})
        if not ids:
            return {}
        placeholders = ', '.join('?' for _ in ids)
        try:
            rows = self.ds.query(
                "SELECT id, code, name, structure_role, status, base_uom, "
                f"config_match_policy FROM {_ITEM_TABLE} "
                f"WHERE id IN ({placeholders})", list(ids))
        except Exception as e:
            logger.warning(f'[item_structure_config] 批量读取物料失败: {e}')
            return {}
        result: Dict[Any, Dict[str, Any]] = {}
        for row in rows or []:
            item = dict(row)
            item['uom_code'] = self._uom_code(item.get('base_uom'))
            result[item.get('id')] = item
        return result

    def _uom_code(self, uom_id: Any) -> Optional[str]:
        if uom_id is None:
            return None
        try:
            rows = self.ds.query(
                f"SELECT code FROM {_UOM_TABLE} WHERE id = ?", [uom_id])
        except Exception as e:
            logger.warning(f'[item_structure_config] 读取单位失败: {e}')
            return None
        return rows[0].get('code') if rows else None

    def _item_codes(self, components: Sequence[Mapping[str, Any]]) -> Dict[Any, Any]:
        items = self._fetch_items([row.get('component_item_id') for row in components])
        return {item_id: item.get('code') for item_id, item in items.items()}

    def _fetch_configuration(self, configuration_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, model_item_id, structure_id, status, config_hash, "
                "revision, reused_from_id, match_policy_used, source_level, "
                "context_json, validation_result_json, solved_at, frozen_at "
                f"FROM {_CONFIGURATION_TABLE} WHERE id = ?", [configuration_id])
        except Exception as e:
            logger.warning(f'[item_structure_config] 读取配置实例失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_values(self, configuration_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, attribute_code, seq, value_text, value_number, "
                "value_boolean, source, source_rule_id "
                f"FROM {_VALUE_TABLE} WHERE configuration_id = ? "
                "ORDER BY attribute_code, seq", [configuration_id])
        except Exception as e:
            logger.warning(f'[item_structure_config] 读取配置特征值失败: {e}')
            return []
        return rows or []

    def _fetch_components(self, configuration_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT c.id, c.component_key, c.structure_line_id, "
                "c.component_item_id, c.qty, c.uom_code, c.parent_component_key, "
                "c.selection_source, c.source_rule_id, c.substitute_for_key, "
                "c.child_configuration_id, c.seq, i.code AS component_item_code "
                f"FROM {_COMPONENT_TABLE} c "
                f"LEFT JOIN {_ITEM_TABLE} i ON i.id = c.component_item_id "
                f"WHERE c.configuration_id = ? ORDER BY c.seq", [configuration_id])
        except Exception as e:
            logger.warning(f'[item_structure_config] 读取配置组件失败: {e}')
            return []
        return rows or []

    @staticmethod
    def _loads(value: Any) -> Any:
        if _is_blank(value):
            return None
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
