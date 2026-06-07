# -*- coding: utf-8 -*-
"""
NestedWhereParser（QE-M8-2026-06-v2）

[M8.VP-2 2026-06-06] 嵌套 WHERE DSL 解析器。

解决问题：
- 现有 v3 filter 只能扁平 AND
- 复杂场景 (A OR B) AND (C OR D) 无法表达
- 跨实体路径（customer.region__eq）需要 JOIN

DSL 语法：
  {
    "and": [cond, cond, ...]    # 全部 AND
    "or":  [cond, cond, ...]    # 全部 OR
    "not": cond                  # 取反
    "field__op": value           # 单条件
    "field__op": [v1, v2]        # IN
    "field__op": {"start": x, "end": y}  # BETWEEN
  }

限制：
- MAX_DEPTH = 5（防止 SQL 爆炸）
- MAX_CONDITIONS = 100
- 嵌套 AND/OR 计数：总条件数 ≤ 100

设计：
- 不重写 v3 现有 FilterValue 路径
- 仅在组合节点（and/or/not）时介入
- 单条件复用 v3 FilterValue.op
- 跨实体路径（path.to.field__op=v）通过 v3 现有嵌套外键 join 支持
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class NestedWhereError(Exception):
    """嵌套 WHERE DSL 错误。"""
    def __init__(self, code: str, message: str, detail: Dict = None):
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


class NestedWhereParser:
    """解析嵌套 WHERE DSL → (raw_sql, params, joins).

    Returns:
        (raw_sql, params, joins)
        - raw_sql: WHERE 子句（不含 WHERE 关键字）
        - params: 绑定参数列表
        - joins: 需要的关联 JOIN 子句（含 ON）
    """

    MAX_DEPTH = 5
    MAX_CONDITIONS = 100

    def __init__(self, base_alias: str = 'bo'):
        self._base_alias = base_alias
        self._depth = 0
        self._condition_count = 0
        self._joins: Dict[str, str] = {}  # alias -> JOIN SQL

    def parse(self, where: Dict) -> Tuple[str, List, List]:
        """解析入口。"""
        self._depth = 0
        self._condition_count = 0
        self._joins = {}
        if not where:
            return '1=1', [], []
        raw_sql, params = self._parse_node(where)
        return raw_sql, params, list(self._joins.values())

    def _parse_node(self, node: Dict) -> Tuple[str, List]:
        """递归解析节点。"""
        if not isinstance(node, dict):
            raise NestedWhereError(
                code='invalid_where_node',
                message=f'where node must be dict, got {type(node).__name__}',
            )

        # 组合节点
        if 'and' in node and 'or' in node:
            raise NestedWhereError(
                code='conflicting_logical_ops',
                message="where cannot contain both 'and' and 'or'",
            )
        if 'and' in node:
            return self._parse_logical('AND', node['and'])
        if 'or' in node:
            return self._parse_logical('OR', node['or'])
        if 'not' in node:
            inner_sql, inner_params = self._parse_node(node['not'])
            return f'NOT ({inner_sql})', inner_params

        # 条件节点
        return self._parse_conditions(node)

    def _parse_logical(self, op: str, items: List) -> Tuple[str, List]:
        """解析 AND/OR 列表。"""
        if not isinstance(items, list):
            raise NestedWhereError(
                code='invalid_logical_items',
                message=f"'{op}' must be a list, got {type(items).__name__}",
            )
        if len(items) == 0:
            return '1=1', []
        if len(items) > self.MAX_CONDITIONS:
            raise NestedWhereError(
                code='too_many_conditions',
                message=f"'{op}' has {len(items)} conditions, max {self.MAX_CONDITIONS}",
            )

        self._depth += 1
        if self._depth > self.MAX_DEPTH:
            raise NestedWhereError(
                code='nested_where_too_deep',
                message=f'nested where depth exceeds {self.MAX_DEPTH}',
            )
        try:
            sqls: List[str] = []
            all_params: List = []
            for item in items:
                self._condition_count += 1
                if self._condition_count > self.MAX_CONDITIONS:
                    raise NestedWhereError(
                        code='too_many_conditions',
                        message=f'total conditions exceed {self.MAX_CONDITIONS}',
                    )
                inner_sql, inner_params = self._parse_node(item)
                sqls.append(inner_sql)
                all_params.extend(inner_params)
            return f"({f' {op} '.join(sqls)})", all_params
        finally:
            self._depth -= 1

    def _parse_conditions(self, node: Dict) -> Tuple[str, List]:
        """解析条件节点。"""
        if not node:
            return '1=1', []
        sqls: List[str] = []
        params: List = []
        for key, value in node.items():
            self._condition_count += 1
            if self._condition_count > self.MAX_CONDITIONS:
                raise NestedWhereError(
                    code='too_many_conditions',
                    message=f'total conditions exceed {self.MAX_CONDITIONS}',
                )
            # 解析 field__op
            if '__' in key:
                # 找到最后一个 __（允许 field 含 _，但 op 不含）
                parts = key.rsplit('__', 1)
                field, op = parts[0], parts[1]
            else:
                field, op = key, 'eq'

            # 跨实体路径（customer.region）
            if '.' in field:
                col_sql, col_params = self._build_path_condition(
                    field, op, value,
                )
            else:
                col_sql, col_params = self._build_single_condition(
                    field, op, value,
                )
            sqls.append(col_sql)
            params.extend(col_params)

        if len(sqls) == 1:
            return sqls[0], params
        return f"({' AND '.join(sqls)})", params

    def _build_single_condition(
        self, field: str, op: str, value: Any,
    ) -> Tuple[str, List]:
        """单字段条件。"""
        column = f'{self._base_alias}.{field}'
        return self._build_op(column, op, value)

    def _build_path_condition(
        self, field: str, op: str, value: Any,
    ) -> Tuple[str, List]:
        """跨实体路径条件（customer.region__eq）。"""
        parts = field.split('.')
        # parts = ['customer', 'region']
        if len(parts) == 1:
            return self._build_single_condition(field, op, value)

        # 生成 JOIN 链
        current_alias = self._base_alias
        target_alias = parts[-1]
        for i in range(len(parts) - 1):
            seg = parts[i]
            next_seg = parts[i + 1] if i + 1 < len(parts) - 1 else parts[-1]
            next_alias = f'{seg}_{i}'
            # 注册 JOIN（简化版：默认外键 <seg>_id）
            join_sql = (
                f'LEFT JOIN {seg} AS {next_alias} '
                f'ON {next_alias}.id = {current_alias}.{seg}_id'
            )
            self._joins[next_alias] = join_sql
            current_alias = next_alias
        # 最后一跳：column = current_alias.target_field
        column = f'{current_alias}.{target_alias}'
        return self._build_op(column, op, value)

    def _build_op(self, column: str, op: str, value: Any) -> Tuple[str, List]:
        """操作符 → SQL 表达式。"""
        if op == 'eq':
            return f'{column} = ?', [value]
        if op == 'ne':
            return f'{column} != ?', [value]
        if op in ('gt', '>') or op == '_gt':
            return f'{column} > ?', [value]
        if op in ('gte', '>=') or op == '_gte':
            return f'{column} >= ?', [value]
        if op in ('lt', '<') or op == '_lt':
            return f'{column} < ?', [value]
        if op in ('lte', '<=') or op == '_lte':
            return f'{column} <= ?', [value]
        if op == 'in':
            if not isinstance(value, (list, tuple)):
                raise NestedWhereError(
                    code='invalid_in_value',
                    message=f"IN requires list value, got {type(value).__name__}",
                )
            if not value:
                return '1=0', []
            placeholders = ','.join('?' * len(value))
            return f'{column} IN ({placeholders})', list(value)
        if op == 'not_in':
            if not isinstance(value, (list, tuple)):
                raise NestedWhereError(
                    code='invalid_not_in_value',
                    message=f"NOT_IN requires list value",
                )
            if not value:
                return '1=1', []
            placeholders = ','.join('?' * len(value))
            return f'{column} NOT IN ({placeholders})', list(value)
        if op == 'like':
            return f'{column} LIKE ?', [value]
        if op in ('ilike', 'ilike_ci'):
            return f'{column} ILIKE ?', [value]
        if op in ('regex', 'iregex'):
            if op == 'iregex':
                return f'{column} REGEXP ? COLLATE NOCASE', [value]
            return f'{column} REGEXP ?', [value]
        if op == 'between':
            if not isinstance(value, dict) or 'start' not in value or 'end' not in value:
                raise NestedWhereError(
                    code='invalid_between',
                    message='between requires {"start": x, "end": y}',
                )
            return f'{column} BETWEEN ? AND ?', [value['start'], value['end']]
        if op == 'is_null':
            return f'{column} IS NULL', []
        if op == 'is_not_null':
            return f'{column} IS NOT NULL', []
        if op == 'date_diff':
            # value: {"field": "x", "unit": "day", "value": 7}
            # SQL: DATEDIFF({column}, {x_field}) >= 7
            if not isinstance(value, dict):
                raise NestedWhereError(
                    code='invalid_date_diff',
                    message='date_diff requires {"field": x, "unit": y, "value": n}',
                )
            return (
                f"DATEDIFF({column}, {self._base_alias}.{value['field']}) >= ?",
                [value.get('value', 0)],
            )
        raise NestedWhereError(
            code='unknown_op',
            message=f"unknown op: {op}",
        )
