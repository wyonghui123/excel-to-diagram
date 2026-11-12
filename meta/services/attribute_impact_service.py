# -*- coding: utf-8 -*-
"""属性影响面 —— 删除守卫计数 + 规则表达式引用扫描。

依据: docs/superpowers/specs/2026-10-25-attribute-extension-and-dictionary-spec.md §6
      （变更危险性分级：停用等同删除；有引用时必须先清引用）
      docs/superpowers/specs/2026-11-09-rule-model-scenario-and-extended-attributes-spec.md
      §9.5 P2（定义变更 → 受影响规则）

两条口径:
  1. 删除守卫：适用范围行（attribute_scopes）+ 已注册值表逐表 COUNT；
     任何一项 > 0 都拒绝删除，引导改为停用。
  2. 影响面：静态扫描元模型规则表达式中的 ``attrs.<code>`` /
     ``item.attrs.<code>`` / ``attrs['<code>']`` 引用，不执行规则、不访问数据库。
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: 可能引用扩展属性的规则字段（与 MetaRule 家族一致）
SCANNED_FIELDS = ('condition', 'action', 'formula', 'source_value')


class AttributeImpactError(ValueError):
    """属性仍被引用，拒绝删除 / 降级。"""

    def __init__(self, message: str, rule: str, field_name: str = ''):
        super().__init__(message)
        self.rule = rule
        self.field_name = field_name


class AttributeImpactService:
    """属性引用的只读计数（删除守卫与影响预览共用）。

    Args:
        data_source: 数据源（提供 query(sql, params) -> List[dict]）
        value_tables: 显式指定值表；缺省按 registry 自动发现
        registry: 规则扫描用的元模型注册表；缺省取全局 registry
    """

    SCOPE_TABLE = 'attribute_scopes'

    def __init__(self, data_source=None, value_tables: Optional[List[str]] = None,
                 registry: Any = None):
        self.ds = data_source
        self._value_tables = list(value_tables) if value_tables is not None else None
        self._registry = registry

    # ---------- 对外：删除守卫 ----------

    def preview(self, attribute_id: Any) -> Dict[str, Any]:
        """返回该属性的引用概览；任何一项 >0 即视为被引用。"""
        scope_count = self._count(self.SCOPE_TABLE, attribute_id)
        value_counts = {table: self._count(table, attribute_id)
                        for table in self.value_tables()}
        value_count = sum(value_counts.values())
        return {
            'attribute_id': attribute_id,
            'scope_count': scope_count,
            'value_count': value_count,
            'value_tables': value_counts,
            'referenced': scope_count > 0 or value_count > 0,
        }

    def assert_not_referenced(self, attribute_id: Any) -> None:
        """被引用则拒绝删除，并给出「先清引用 / 改为停用」的具体指引。"""
        info = self.preview(attribute_id)
        if not info['referenced']:
            return

        parts = []
        if info['scope_count']:
            parts.append(f"{info['scope_count']} 条适用范围")
        if info['value_count']:
            detail = '、'.join(f'{t}={n}' for t, n in info['value_tables'].items() if n)
            parts.append(f"{info['value_count']} 条属性值（{detail}）")

        raise AttributeImpactError(
            f"属性 {attribute_id} 仍被引用：{'；'.join(parts)}。"
            '请先清理这些行，或把定义改为停用（status=inactive）—— '
            '停用对业务的效果等同删除，但不破坏历史数据。',
            rule='attribute_in_use',
            field_name='id',
        )

    # ---------- 对外：规则表达式影响面（spec 2026-11-09 §9.5 P2）----------

    def find_rule_references(self, attribute_code: str,
                             object_type: Optional[str] = None
                             ) -> List[Dict[str, Any]]:
        """返回引用该属性的规则清单（按对象 / 规则排序）。

        每项: ``{object_type, rule_id, rule_name, attribute_code, field,
        expression}``。
        """
        code = str(attribute_code or '')
        if not code:
            return []
        pattern = _reference_pattern(code)
        impacts: List[Dict[str, Any]] = []
        for meta_object in self._objects():
            if object_type and meta_object.id != object_type:
                continue
            for rule in getattr(meta_object, 'rules', None) or []:
                for field_name in SCANNED_FIELDS:
                    expression = getattr(rule, field_name, '') or ''
                    if not isinstance(expression, str):
                        continue
                    if not pattern.search(expression):
                        continue
                    impacts.append({
                        'object_type': meta_object.id,
                        'rule_id': getattr(rule, 'id', ''),
                        'rule_name': getattr(rule, 'name', ''),
                        'attribute_code': code,
                        'field': field_name,
                        'expression': expression.strip(),
                    })
        impacts.sort(key=lambda item: (
            str(item['object_type']), str(item['rule_id']), item['field']))
        return impacts

    def find_many_rule_references(
            self, attribute_codes,
            object_type: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            code: self.find_rule_references(code, object_type=object_type)
            for code in dict.fromkeys(str(c) for c in attribute_codes if c)
        }

    # ---------- 值表发现 ----------

    def value_tables(self) -> List[str]:
        if self._value_tables is not None:
            return list(self._value_tables)
        return self._discover_value_tables()

    @staticmethod
    def _discover_value_tables() -> List[str]:
        from meta.core.models import registry

        tables = []
        for obj in registry.get_all().values():
            table = getattr(obj, 'table_name', '') or ''
            if not table.endswith('_attribute_values'):
                continue
            if not any(getattr(f, 'id', None) == 'attribute_id'
                       for f in (obj.fields or [])):
                continue
            tables.append(table)
        return tables

    # ---------- 查询辅助（可覆写注入）----------

    def _objects(self) -> List[Any]:
        registry = self._registry
        if registry is None:
            from meta.core.models import registry as default_registry
            registry = default_registry
        get_all = getattr(registry, 'get_all', None)
        if callable(get_all):
            result = get_all() or {}
            return list(result.values()) if isinstance(result, dict) else list(result)
        all_method = getattr(registry, 'all', None)
        return list(all_method() or []) if callable(all_method) else []

    def _count(self, table: str, attribute_id: Any) -> int:
        rows = self._query(
            f'SELECT COUNT(*) AS cnt FROM {table} WHERE attribute_id = ?',
            [attribute_id],
        )
        if not rows:
            return 0
        first = rows[0]
        try:
            return int(first.get('cnt', 0)) if isinstance(first, dict) else int(first[0])
        except (TypeError, ValueError, KeyError, IndexError):
            return 0

    def _query(self, sql: str, params) -> list:
        if self.ds is None:
            return []
        try:
            return self.ds.query(sql, params) or []
        except Exception as e:  # 查询失败 → fail-open（不阻断既有维护流程）
            logger.warning(f'[attribute_impact] 查询失败，跳过该项计数: {e}')
            return []


def _reference_pattern(code: str) -> 're.Pattern':
    """匹配 ``attrs.code`` / ``item.attrs.code`` / ``attrs['code']``。"""
    token = re.escape(code)
    return re.compile(
        r'(?:\b(?:item|related|self)\.)?\battrs\s*'
        r'(?:\.\s*%s\b|\[\s*[\'"]%s[\'"]\s*\])' % (token, token))
