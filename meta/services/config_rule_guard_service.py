# -*- coding: utf-8 -*-
"""配置规则守卫 —— 规则头与条件项的写入不变量。

依据: meta/schemas/config_rule.yaml / config_rule_term.yaml 头注释
      docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md §5.3–§5.5 / §9

落点划分:
  R8  三个 target_* 列恰好一列非空 —— `validate_term_write`
  R9  只有 structure_role = model 的结构可声明规则 —— `validate_rule_write`
  R16 规则只能引用同一结构版本内的行、选项类与特征 —— `validate_term_write`
      「同一结构版本内」按「根模型 + 其选项类子结构可达树」解释（§5.1 要求跨层约束，
      但嵌套模型是独立求解单元，故不穿透到子模型）。
  形状 按 §5.5 校验 clause / target_type / operator 的相容性 —— `validate_term_write`
  结构 规则已有条件项时禁止改 structure_id —— `validate_rule_write`

查询失败一律 fail-open + WARNING（沿用 item_structure_guard 口径）。
已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过。
"""

import logging
from typing import Any, Dict, Iterable, Optional, Set

logger = logging.getLogger(__name__)

_STRUCTURE_TABLE = 'item_structures'
_LINE_TABLE = 'item_structure_lines'
_ATTRIBUTE_TABLE = 'item_structure_attributes'
_RULE_TABLE = 'config_rules'
_TERM_TABLE = 'config_rule_terms'

_TARGET_TYPES = ('structure_line', 'option_class', 'characteristic')
_CLAUSES = ('if', 'then')

# operator 与 target_type 的相容关系（§5.5）
_OPERATOR_TARGETS = {
    'selected': {'structure_line', 'option_class'},
    'not_selected': {'structure_line', 'option_class'},
    'equals': {'characteristic'},
    'not_equals': {'characteristic'},
    'in': {'characteristic'},
    'qty_ge': {'structure_line'},
    'qty_le': {'structure_line'},
    'qty_between': {'structure_line'},
    'enabled': {'structure_line', 'option_class'},
    'disabled': {'structure_line', 'option_class'},
}

# then 子句允许的 operator（§5.5）
_THEN_OPERATORS = {
    'require': {'selected'},
    'bind': {'selected'},
    'exclude': {'selected'},
    'negate': {'selected', 'not_selected'},
    'default': {'selected', 'equals'},
    'condition': {'enabled', 'disabled'},
}

# if 子句只接受一项的规则类型（§5.5）
_SINGLE_IF_TYPES = ('bind', 'exclude', 'negate')

# 查询失败哨兵
_QUERY_FAILED = object()


class ConfigRuleGuardError(ValueError):
    """配置规则守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _as_number(value: Any) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ConfigRuleGuardService:
    """配置规则头 / 条件项的写入前校验。查询方法可覆写，便于单测注入。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def validate_rule_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """规则头创建 / 更新前校验 R9 与 structure_id 变更限制。"""
        structure_id = data.get('structure_id')
        if _is_blank(structure_id):
            return  # 缺必填交给必填校验兜底

        # R9：只有模型可以声明规则
        role = self._fetch_structure_role(structure_id)
        if role and role != 'model':
            raise ConfigRuleGuardError(
                f'只有模型（结构角色 = 模型）可以声明配置规则；'
                f'该结构的父项角色是「{role}」',
                field_name='structure_id',
                rule='config_rule_requires_model')

        # 规则已有条件项时，换结构会让条件项指向另一棵树，直接拒绝
        if exclude_id is not None:
            current = self._fetch_rule(exclude_id)
            if current and str(current.get('structure_id')) != str(structure_id):
                if self._count_terms(exclude_id) > 0:
                    raise ConfigRuleGuardError(
                        '该规则已有条件项，不能改所属结构版本；请新建规则',
                        field_name='structure_id',
                        rule='config_rule_structure_locked')

    def validate_term_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """条件项创建 / 更新前校验 R8 / R16 与 §5.5 形状。"""
        rule_id = data.get('rule_id')
        if _is_blank(rule_id):
            return  # 缺必填交给必填校验兜底

        rule = self._fetch_rule(rule_id)
        if not rule:
            return  # 规则不存在交给 FK 兜底

        clause = str(data.get('clause') or '').strip()
        target_type = str(data.get('target_type') or '').strip()
        operator = str(data.get('operator') or '').strip()

        if clause and clause not in _CLAUSES:
            raise ConfigRuleGuardError(
                "条件项子句只能是「if」或「then」",
                field_name='clause',
                rule='config_rule_term_clause_invalid')
        if target_type and target_type not in _TARGET_TYPES:
            raise ConfigRuleGuardError(
                '条件项目标类型只能是结构行 / 选项类 / 特征',
                field_name='target_type',
                rule='config_rule_term_target_type_invalid')

        self._validate_target_columns(data, target_type)
        self._validate_operator(rule, clause, target_type, operator)
        self._validate_value_shape(data, operator)
        self._validate_clause_count(rule, data, clause, exclude_id)

        structure_id = rule.get('structure_id')
        reachable = self._reachable_structure_ids(structure_id)

        if target_type == 'structure_line':
            line_id = data.get('target_line_id')
            if _is_blank(line_id):
                return
            line_structure_id = self._fetch_line_structure(line_id)
            if line_structure_id is _QUERY_FAILED:
                return  # fail-open
            if line_structure_id is None:
                raise ConfigRuleGuardError(
                    '条件项引用的结构行不存在',
                    field_name='target_line_id',
                    rule='config_rule_term_line_missing')
            if reachable is not None and str(line_structure_id) not in reachable:
                raise ConfigRuleGuardError(
                    '条件项只能引用本模型（含其选项类）内的结构行；'
                    '请选择同一结构树中的行',
                    field_name='target_line_id',
                    rule='config_rule_term_out_of_scope')

        elif target_type == 'option_class':
            item_id = data.get('target_class_item_id')
            if _is_blank(item_id):
                return
            role = self._fetch_item_role(item_id)
            if role is _QUERY_FAILED:
                return
            if role != 'option_class':
                raise ConfigRuleGuardError(
                    '条件项目标必须是选项类物料（结构角色 = 选项类）',
                    field_name='target_class_item_id',
                    rule='config_rule_term_not_option_class')
            if reachable is not None:
                class_structures = self._fetch_item_structures(item_id)
                if class_structures is _QUERY_FAILED:
                    return
                if not (set(class_structures) & reachable):
                    raise ConfigRuleGuardError(
                        '该选项类不在本模型的组件树内',
                        field_name='target_class_item_id',
                        rule='config_rule_term_out_of_scope')

        elif target_type == 'characteristic':
            code = str(data.get('attribute_code') or '').strip()
            if not code or reachable is None:
                return
            if not self._attribute_declared(reachable, code):
                raise ConfigRuleGuardError(
                    f"特征 '{code}' 未在本模型的特征清单中声明；"
                    '请先在「模型特征」中声明',
                    field_name='attribute_code',
                    rule='config_rule_term_attribute_undeclared')

    # ---------- 形状校验 ----------

    @staticmethod
    def _validate_target_columns(data: Dict[str, Any], target_type: str) -> None:
        """R8：三个 target_* 列恰好一列非空，且与 target_type 对应。"""
        filled = {
            'structure_line': not _is_blank(data.get('target_line_id')),
            'option_class': not _is_blank(data.get('target_class_item_id')),
            'characteristic': not _is_blank(data.get('attribute_code')),
        }
        count = sum(1 for v in filled.values() if v)
        if count != 1:
            raise ConfigRuleGuardError(
                '条件项必须在「结构行 / 选项类 / 特征」中恰好指定一个目标',
                field_name='target_type',
                rule='config_rule_term_target_exclusive')
        if target_type and not filled.get(target_type):
            raise ConfigRuleGuardError(
                '条件项的目标列与目标类型不一致',
                field_name='target_type',
                rule='config_rule_term_target_mismatch')

    @staticmethod
    def _validate_operator(rule: Dict[str, Any], clause: str, target_type: str,
                           operator: str) -> None:
        if not operator:
            return
        allowed_targets = _OPERATOR_TARGETS.get(operator)
        if allowed_targets is None:
            raise ConfigRuleGuardError(
                f'条件项运算符「{operator}」不受支持',
                field_name='operator',
                rule='config_rule_term_operator_invalid')
        if target_type and target_type not in allowed_targets:
            raise ConfigRuleGuardError(
                f'运算符「{operator}」不适用于目标类型「{target_type}」',
                field_name='operator',
                rule='config_rule_term_operator_target_mismatch')

        rule_type = str(rule.get('rule_type') or '')
        if clause == 'then':
            allowed = _THEN_OPERATORS.get(rule_type)
            if allowed is not None and operator not in allowed:
                raise ConfigRuleGuardError(
                    f'{rule_type} 规则的 then 子句只能用 '
                    f'{" / ".join(sorted(allowed))}',
                    field_name='operator',
                    rule='config_rule_term_then_operator_invalid')
        elif clause == 'if' and operator in ('enabled', 'disabled'):
            raise ConfigRuleGuardError(
                'enabled / disabled 只能出现在 condition 规则的 then 子句',
                field_name='operator',
                rule='config_rule_term_operator_clause_mismatch')

    @staticmethod
    def _validate_value_shape(data: Dict[str, Any], operator: str) -> None:
        if operator == 'in':
            values = data.get('value_list')
            if not values:
                raise ConfigRuleGuardError(
                    'in 运算符必须给出多值清单',
                    field_name='value_list',
                    rule='config_rule_term_value_missing')
            return
        if operator == 'qty_between':
            low = _as_number(data.get('value_number'))
            high = _as_number(data.get('value_number_to'))
            if low is None or high is None:
                raise ConfigRuleGuardError(
                    'qty_between 必须同时给出数量下界与上界',
                    field_name='value_number',
                    rule='config_rule_term_value_missing')
            if low > high:
                raise ConfigRuleGuardError(
                    '数量区间下界不得大于上界',
                    field_name='value_number_to',
                    rule='config_rule_term_value_range_invalid')
            return
        if operator in ('qty_ge', 'qty_le') and _as_number(data.get('value_number')) is None:
            raise ConfigRuleGuardError(
                f'{operator} 必须给出数量值',
                field_name='value_number',
                rule='config_rule_term_value_missing')

    def _validate_clause_count(self, rule: Dict[str, Any], data: Dict[str, Any],
                               clause: str, exclude_id: Any) -> None:
        """then 最多一项；bind / exclude / negate 的 if 只允许一项。"""
        if clause not in _CLAUSES:
            return
        rule_id = rule.get('id')
        existing = self._count_terms(rule_id, clause=clause, exclude_id=exclude_id)
        if existing is _QUERY_FAILED:
            return  # fail-open
        rule_type = str(rule.get('rule_type') or '')
        if clause == 'then' and existing >= 1:
            raise ConfigRuleGuardError(
                '一条规则的 then 子句最多一项',
                field_name='clause',
                rule='config_rule_term_then_multiple')
        if clause == 'if' and rule_type in _SINGLE_IF_TYPES and existing >= 1:
            raise ConfigRuleGuardError(
                f'{rule_type} 规则的 if 子句只允许一项',
                field_name='clause',
                rule='config_rule_term_if_multiple')

    # ---------- 可达结构树 ----------

    def _reachable_structure_ids(self, root_structure_id: Any) -> Optional[Set[str]]:
        """根模型 + 其选项类子结构（含选项类内嵌套的选项类），不下钻子模型。

        返回 None 表示查询失败（调用方 fail-open）。
        """
        if _is_blank(root_structure_id):
            return set()
        root = str(root_structure_id)
        reachable = {root}
        queue = [root]
        while queue:
            current = queue.pop()
            lines = self._fetch_line_components(current)
            if lines is _QUERY_FAILED:
                return None
            for component_item_id in lines:
                role = self._fetch_item_role(component_item_id)
                if role is _QUERY_FAILED:
                    return None
                if role != 'option_class':
                    continue
                structures = self._fetch_item_structures(component_item_id)
                if structures is _QUERY_FAILED:
                    return None
                for sid in structures:
                    if sid not in reachable:
                        reachable.add(sid)
                        queue.append(sid)
        return reachable

    # ---------- 查询（可覆写，便于单测注入）----------

    def _fetch_structure_role(self, structure_id: Any) -> str:
        sql = (f"SELECT i.structure_role AS role FROM {_STRUCTURE_TABLE} s "
               f"JOIN items i ON i.id = s.item_id WHERE s.id = ?")
        try:
            rows = self.ds.query(sql, [structure_id])
        except Exception as e:  # fail-open
            logger.warning(f'[config_rule_guard] 读取结构角色失败: {e}')
            return ''
        return str(rows[0].get('role') or '') if rows else ''

    def _fetch_rule(self, rule_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                f"SELECT id, structure_id, rule_type FROM {_RULE_TABLE} WHERE id = ?",
                [rule_id])
        except Exception as e:  # fail-open
            logger.warning(f'[config_rule_guard] 读取规则失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_line_structure(self, line_id: Any):
        try:
            rows = self.ds.query(
                f"SELECT structure_id FROM {_LINE_TABLE} WHERE id = ?", [line_id])
        except Exception as e:  # fail-open
            logger.warning(f'[config_rule_guard] 读取结构行失败: {e}')
            return _QUERY_FAILED
        return rows[0].get('structure_id') if rows else None

    def _fetch_line_components(self, structure_id: Any):
        try:
            rows = self.ds.query(
                f"SELECT component_item_id FROM {_LINE_TABLE} WHERE structure_id = ?",
                [structure_id])
        except Exception as e:  # fail-open
            logger.warning(f'[config_rule_guard] 读取结构行组件失败: {e}')
            return _QUERY_FAILED
        return [row.get('component_item_id') for row in rows or []]

    def _fetch_item_role(self, item_id: Any):
        try:
            rows = self.ds.query(
                "SELECT structure_role FROM items WHERE id = ?", [item_id])
        except Exception as e:  # fail-open
            logger.warning(f'[config_rule_guard] 读取物料角色失败: {e}')
            return _QUERY_FAILED
        return str(rows[0].get('structure_role') or '') if rows else ''

    def _fetch_item_structures(self, item_id: Any):
        try:
            rows = self.ds.query(
                f"SELECT id FROM {_STRUCTURE_TABLE} WHERE item_id = ?", [item_id])
        except Exception as e:  # fail-open
            logger.warning(f'[config_rule_guard] 读取物料结构失败: {e}')
            return _QUERY_FAILED
        return [str(row.get('id')) for row in rows or []]

    def _count_terms(self, rule_id: Any, clause: str = '', exclude_id: Any = None):
        sql = f"SELECT COUNT(*) AS cnt FROM {_TERM_TABLE} WHERE rule_id = ?"
        params = [rule_id]
        if clause:
            sql += " AND clause = ?"
            params.append(clause)
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # fail-open
            logger.warning(f'[config_rule_guard] 统计条件项失败: {e}')
            return _QUERY_FAILED
        return int(rows[0].get('cnt') or 0) if rows else 0

    def _attribute_declared(self, reachable: Iterable[str], code: str) -> bool:
        ids = [int(sid) for sid in reachable if str(sid).lstrip('-').isdigit()]
        if not ids:
            return False
        placeholders = ', '.join('?' for _ in ids)
        sql = (f"SELECT COUNT(*) AS cnt FROM {_ATTRIBUTE_TABLE} "
               f"WHERE structure_id IN ({placeholders}) AND attribute_code = ?")
        try:
            rows = self.ds.query(sql, ids + [code])
        except Exception as e:  # fail-open
            logger.warning(f'[config_rule_guard] 读取模型特征失败: {e}')
            return True
        return bool(rows and int(rows[0].get('cnt') or 0) > 0)
