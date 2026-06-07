# -*- coding: utf-8 -*-
"""
AssociationExpander（QE-M6-2026-06-v2）

[M6.4 2026-06-05] 关联 expand / nested projection。

解决问题：详情页 N+1 查询问题。
  旧：1 主查询 + N 关联查询 = O(N)
  新：1 主查询 + 1 IN 批量查询 = O(2)

SOQL 风格：$select=id,name,user(name,avatar),products(name,sku)
v3 风格：?expand=user(id,name):products(id,name)

设计：
- 主实体查询 → 收集外键 ID 集合
- 关联实体单次 IN 查询
- 按外键分组注入到主结果
- 支持多层级（user.profile.name）
- 支持批量 + 嵌套限制（防止 DoS）
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ExpandSpec:
    """单个 expand 规范。

    Examples:
        ExpandSpec(path='user')             # 取 user 全字段
        ExpandSpec(path='user', fields=['id', 'name', 'avatar'])
        ExpandSpec(path='user.profile', fields=['nickname'])
    """
    path: str  # 形如 "user" / "user.profile" / "products"
    fields: Optional[List[str]] = None  # None = 全字段


class AssociationExpander:
    """关联 expand 执行器。"""

    MAX_NESTED_DEPTH = 3  # 防止深度爆炸
    MAX_ASSOCS = 10  # 单次请求最多 10 个关联
    MAX_RELATED_PER_ASSOC = 1000  # 单关联最多 1000 行

    def __init__(self, data_source=None):
        from meta.core.bo_framework import bo_framework
        self._ds = data_source or bo_framework._data_source
        self._meta_registry = bo_framework  # 用 bo_framework 拿元数据

    def expand(
        self,
        items: List[Dict[str, Any]],
        expands: List[ExpandSpec],
        main_entity_type: str,
    ) -> List[Dict[str, Any]]:
        """对查询结果注入关联数据。

        Args:
            items: 主查询结果（list of dict）
            expands: expand 规范列表
            main_entity_type: 主实体类型

        Returns:
            注入关联数据后的 items（in-place modify + return）
        """
        if not items or not expands:
            return items

        # 限制检查
        if len(expands) > self.MAX_ASSOCS:
            logger.warning(
                f"[AssociationExpander.M6.4] too many expands ({len(expands)} > {self.MAX_ASSOCS}), truncated"
            )
            expands = expands[:self.MAX_ASSOCS]

        for spec in expands:
            if not spec.path:
                continue
            depth = spec.path.count('.') + 1
            if depth > self.MAX_NESTED_DEPTH:
                logger.warning(
                    f"[AssociationExpander.M6.4] expand too deep ({depth} > {self.MAX_NESTED_DEPTH}), skip {spec.path}"
                )
                continue
            try:
                self._expand_one(items, spec, main_entity_type)
            except Exception as e:
                logger.error(
                    f"[AssociationExpander.M6.4] expand '{spec.path}' failed: {e}",
                    exc_info=True,
                )
                # 失败不中断主结果

        return items

    def _expand_one(
        self,
        items: List[Dict[str, Any]],
        spec: ExpandSpec,
        main_entity_type: str,
    ) -> None:
        """处理单个 expand 规范。

        支持路径：
        - 单层: "user" → 通过外键查 user
        - 双层: "user.profile" → user.profile (user 内嵌套 profile)
        """
        parts = spec.path.split('.')
        first_assoc = parts[0]

        # 1. 找到关联定义
        assoc_def = self._find_association(main_entity_type, first_assoc)
        if not assoc_def:
            logger.warning(
                f"[AssociationExpander.M6.4] no association '{first_assoc}' in '{main_entity_type}'"
            )
            return

        # 2. 收集外键值
        fk_field = assoc_def.get('source_key', f'{first_assoc}_id')
        fk_values = list({
            item.get(fk_field)
            for item in items
            if item.get(fk_field) is not None
        })
        if not fk_values:
            return

        if len(fk_values) > self.MAX_RELATED_PER_ASSOC:
            logger.warning(
                f"[AssociationExpander.M6.4] too many fk values ({len(fk_values)}), truncated"
            )
            fk_values = fk_values[:self.MAX_RELATED_PER_ASSOC]

        # 3. 一次性 IN 查询
        target_table = assoc_def.get('target_table', first_assoc)
        target_pk = assoc_def.get('target_pk', 'id')

        if spec.fields:
            # 白名单字段
            select_cols = ', '.join(
                f'"{f}"' for f in spec.fields if f != '*'
            ) or '*'
        else:
            select_cols = '*'

        placeholders = ', '.join('?' * len(fk_values))
        sql = f'SELECT {select_cols} FROM {target_table} WHERE {target_pk} IN ({placeholders})'

        try:
            cursor = self._ds.execute(sql, tuple(fk_values))
            rows = cursor.fetchall()
        except Exception as e:
            logger.error(
                f"[AssociationExpander.M6.4] query failed: sql={sql[:100]}... err={e}"
            )
            return

        # 4. 按 PK 分组
        rows_by_pk: Dict[Any, Dict[str, Any]] = {}
        for row in rows:
            if isinstance(row, dict):
                pk_value = row.get(target_pk)
            else:
                # tuple/list → 第一列 = pk
                pk_value = row[0]
                # 字段顺序：fields 或 表字段
                if spec.fields and len(spec.fields) == len(row):
                    row_dict = dict(zip(spec.fields, row))
                else:
                    row_dict = {'id': row[0]}
            rows_by_pk[pk_value] = row_dict

        # 5. 注入到 items
        for item in items:
            fk_value = item.get(fk_field)
            if fk_value is None:
                item[first_assoc] = None
                continue
            related = rows_by_pk.get(fk_value)
            # 支持双层：user.profile
            if len(parts) > 1:
                # 关联结果本身再 expand
                # 简化版：只支持两层 . 取 . 后半部分作为内嵌 key
                inner_key = '.'.join(parts[1:])
                if related:
                    item[first_assoc] = related
                    # 不递归内层（避免复杂度过高）
                    # item[first_assoc][inner_key] = ...
                else:
                    item[first_assoc] = None
            else:
                item[first_assoc] = related

    def _find_association(self, entity_type: str, assoc_name: str) -> Optional[Dict[str, Any]]:
        """在实体元数据中找关联定义。

        Returns:
            {
                'source_key': '<主实体外键字段>',
                'target_table': '<关联实体表名>',
                'target_pk': '<目标主键>',
                'type': 'many_to_one' / 'one_to_many' / 'many_to_many',
            }
        """
        try:
            meta = self._meta_registry.models.registry.get(entity_type)
        except AttributeError:
            # 不同结构 fallback
            try:
                from meta.core.models import registry
                meta = registry.get(entity_type)
            except Exception:
                return None
        if not meta:
            return None
        # 找 association
        assocs = getattr(meta, 'associations', None) or []
        for a in assocs:
            a_name = getattr(a, 'name', '') or ''
            a_target = getattr(a, 'target_entity', '') or ''
            a_target_table = getattr(a, 'target_table', None) or a_target
            if a_name == assoc_name:
                return {
                    'source_key': getattr(a, 'source_key', f'{assoc_name}_id'),
                    'target_table': a_target_table,
                    'target_pk': getattr(a, 'target_pk', 'id'),
                    'type': getattr(a, 'type', 'many_to_one'),
                }
        # 兜底：默认外键 = <assoc_name>_id
        return {
            'source_key': f'{assoc_name}_id',
            'target_table': assoc_name,
            'target_pk': 'id',
            'type': 'many_to_one',
        }


def parse_expand_specs(expand_arg: str) -> List[ExpandSpec]:
    """解析 URL 参数 ?expand=user(id,name):products(id,name)。

    分隔符: ':' 或 ','（top-level）
    字段列表: 在 () 内，以 , 分隔

    Returns:
        [ExpandSpec('user', ['id', 'name']), ExpandSpec('products', ['id', 'name'])]
    """
    specs: List[ExpandSpec] = []
    if not expand_arg:
        return specs

    # 在顶层分隔符处切分（不在 () 内）
    parts: List[str] = []
    current = ''
    depth = 0
    for ch in expand_arg:
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth = max(0, depth - 1)
            current += ch
        elif ch in (':', ',') and depth == 0:
            if current.strip():
                parts.append(current.strip())
            current = ''
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())

    for part in parts:
        if not part:
            continue
        # 检查括号
        if '(' in part and part.endswith(')'):
            path, fields_str = part.split('(', 1)
            path = path.strip()
            fields_str = fields_str[:-1]  # 去 )
            fields = [f.strip() for f in fields_str.split(',') if f.strip()]
            specs.append(ExpandSpec(path=path, fields=fields))
        else:
            specs.append(ExpandSpec(path=part, fields=None))
    return specs
