# -*- coding: utf-8 -*-
"""属性引用影响 —— 删除定义前的引用计数。

依据: docs/superpowers/specs/2026-10-25-attribute-extension-and-dictionary-spec.md §6
      （变更危险性分级：停用等同删除；有引用时必须先清引用）

为什么需要它: 「删除」在属性字典里是唯一不可自助的高危动作 —— 删掉定义会让值表里的行
变成孤儿。SQLite 的外键约束在运行时不保证开启，schema 的 restrict 只是声明，因此必须在
写入前用应用层计数拦住。

计数口径:
  - 适用范围行（attribute_scopes）：任何状态都算引用，停用的范围行需先清理
  - 值行：按已注册值表逐个 COUNT；值表由 registry 中「表名以 _attribute_values 结尾
    且含 attribute_id 字段」的对象自动发现，新增值表无需改本文件
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    """

    SCOPE_TABLE = 'attribute_scopes'

    def __init__(self, data_source=None, value_tables: Optional[List[str]] = None):
        self.ds = data_source
        self._value_tables = list(value_tables) if value_tables is not None else None

    # ---------- 对外 ----------

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
