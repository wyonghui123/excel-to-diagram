# -*- coding: utf-8 -*-
"""
ConditionExpressionParser

将结构化条件 [{field, op, value}] 转换为 SQL WHERE 子句。

[支持操作符]
  =, !=, <, <=, >, >=, IN, NOT IN, CHILDREN_OF, ANCESTORS_OF

[运行时变量]
  ${user.id} 等变量在 to_sql() 时通过 runtime_vars 参数解析

[CHILDREN_OF]
  生成子查询: field IN (SELECT id FROM <child_table> WHERE parent_field = ?)
"""
from typing import Any, Dict, List, Optional, Tuple

# 操作符白名单 (与 SafeExpressionEvaluator.ALLOWED_OPERATORS 对齐)
SUPPORTED_OPS = {
    '=', '!=', '<', '<=', '>', '>=',
    'IN', 'NOT IN',
    'CHILDREN_OF', 'ANCESTORS_OF',
    # [P1-A3 2026-07-26] 递归操作符 (跨多层)
    'DESCENDANTS_OF',   # 向下递归: parent_dim → 所有层级的 children
    'ANCESTORS_ALL_OF', # 向上递归: child_id → 所有层级的 ancestors
    'RAW',  # [P4 补充] 原生 SQL 片段 (用于推导管道 cross-BO 条件)
}

# [P1-A3 2026-07-26] HIERARCHY 链 (与 dimension_scope_engine 一致)
# (dim_code, fk_field_pointing_to_parent, table_name)
# 用于 DESCENDANTS_OF / ANCESTORS_ALL_OF 递归查询
_HIERARCHY_FK = [
    ('product', None, 'products'),
    ('version', 'product_id', 'versions'),
    ('domain', 'version_id', 'domains'),
    ('sub_domain', 'domain_id', 'sub_domains'),
    ('service_module', 'sub_domain_id', 'service_modules'),
    ('business_object', 'service_module_id', 'business_objects'),
]

# 维度字段 → 子表映射 (用于 CHILDREN_OF)
_DIM_CHILD_TABLES = {
    'domain_id': {'table': 'domains', 'id_col': 'id'},
    'sub_domain_id': {'table': 'sub_domains', 'id_col': 'id', 'parent_col': 'domain_id'},
    'service_module_id': {'table': 'service_modules', 'id_col': 'id', 'parent_col': 'sub_domain_id'},
    'product_id': {'table': 'products', 'id_col': 'id'},
    'version_id': {'table': 'versions', 'id_col': 'id', 'parent_col': 'product_id'},
}


class ConditionExpressionParser:
    """结构化条件 → SQL WHERE 解析器"""

    def to_sql(
        self,
        conditions: List[Dict[str, Any]],
        runtime_vars: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], List[Any]]:
        """将条件列表转换为 SQL WHERE 子句

        Args:
            conditions: [{field, op, value}, ...]
            runtime_vars: 运行时变量, 如 {'user.id': 159}

        Returns:
            (sql, params): SQL 片段 (不含 WHERE 关键字) 和参数列表
            空条件返回 (None, [])
        """
        if not conditions:
            return None, []

        runtime_vars = runtime_vars or {}
        parts: List[str] = []
        params: List[Any] = []

        for cond in conditions:
            field = cond['field']
            op = cond['op']
            value = cond['value']

            if op not in SUPPORTED_OPS:
                raise ValueError(
                    f'Unsupported operator: {op}. Supported: {SUPPORTED_OPS}'
                )

            # 解析运行时变量
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                var_name = value[2:-1]  # 去掉 ${ }
                if var_name in runtime_vars:
                    value = runtime_vars[var_name]
                else:
                    raise ValueError(f'Unresolved runtime variable: {value}')

            sql_part, part_params = self._build_clause(field, op, value)
            parts.append(sql_part)
            params.extend(part_params)

        sql = ' AND '.join(parts)
        return sql, params

    def _build_clause(self, field: str, op: str, value: Any) -> Tuple[str, List[Any]]:
        """构建单个条件的 SQL 片段"""

        if op in ('=', '!=', '<', '<=', '>', '>='):
            return f'{field} {op} ?', [value]

        if op == 'IN':
            if not isinstance(value, list):
                value = [value]
            placeholders = ', '.join(['?'] * len(value))
            return f'{field} IN ({placeholders})', list(value)

        if op == 'NOT IN':
            if not isinstance(value, list):
                value = [value]
            placeholders = ', '.join(['?'] * len(value))
            return f'{field} NOT IN ({placeholders})', list(value)

        if op == 'CHILDREN_OF':
            return self._build_children_of(field, value)

        if op == 'ANCESTORS_OF':
            return self._build_ancestors_of(field, value)

        # [P1-A3 2026-07-26] 递归操作符 (跨多层)
        if op == 'DESCENDANTS_OF':
            return self._build_descendants_of(field, value)

        if op == 'ANCESTORS_ALL_OF':
            return self._build_ancestors_all_of(field, value)

        if op == 'RAW':
            # [P4 补充] 原生 SQL 片段: value 是 SQL 字符串 (不含 WHERE)
            # params 直接透传 (如果 value 是 dict 含 params)
            if isinstance(value, dict):
                return value.get('sql', '1=1'), value.get('params', [])
            if isinstance(value, str):
                return value, []
            return '1=1', []

        # 不会到达这里, 因为前面已经校验
        raise ValueError(f'Unsupported operator: {op}')

    def _build_children_of(self, field: str, value: Dict) -> Tuple[str, List[Any]]:
        """CHILDREN_OF: 生成子查询

        value 格式: {parent_field: "domain_id", parent_value: 1}
        或: {parent_field: "domain_id", parent_value: [1, 2]}

        生成: field IN (SELECT id FROM <child_table> WHERE parent_field = ?)
        """
        parent_field = value.get('parent_field', '')
        parent_value = value.get('parent_value')

        # 从字段名推断子表
        child_table_info = _DIM_CHILD_TABLES.get(field)
        if child_table_info is None:
            raise ValueError(
                f'CHILDREN_OF: unknown dimension field {field}, '
                f'cannot determine child table'
            )

        table = child_table_info['table']
        id_col = child_table_info['id_col']
        parent_col = child_table_info.get('parent_col', parent_field)

        if isinstance(parent_value, list):
            placeholders = ', '.join(['?'] * len(parent_value))
            sql = (
                f'{field} IN (SELECT {id_col} FROM {table} '
                f'WHERE {parent_col} IN ({placeholders}))'
            )
            return sql, list(parent_value)
        else:
            sql = (
                f'{field} IN (SELECT {id_col} FROM {table} '
                f'WHERE {parent_col} = ?)'
            )
            return sql, [parent_value]

    def _build_ancestors_of(self, field: str, value: Dict) -> Tuple[str, List[Any]]:
        """ANCESTORS_OF: 向上查询祖先 (极少使用)

        value 格式: {child_table: "sub_domains", child_id: 101, parent_col: "domain_id"}

        生成: field IN (SELECT parent_col FROM child_table WHERE id = ?)
        """
        child_table = value.get('child_table', '')
        child_id = value.get('child_id')
        parent_col = value.get('parent_col', '')

        sql = (
            f'{field} IN (SELECT {parent_col} FROM {child_table} '
            f'WHERE id = ?)'
        )
        return sql, [child_id]

    # ============================================================
    # [P1-A3 2026-07-26] 递归操作符 (跨多层)
    # ============================================================
    def _build_descendants_of(self, field: str, value: Dict) -> Tuple[str, List[Any]]:
        """DESCENDANTS_OF: 向下递归所有层级

        [语义]
          给定 parent_dim 的 id 值, 找出该 parent 下所有层级的 children
          (跨多层 HIERARCHY, 与 CHILDREN_OF 单层不同)

        [value 格式]
          {parent_dim: "domain", parent_value: 2200}
          或: {parent_dim: "domain", parent_value: [2200, 2201]}

        [生成 SQL 示例]
          field=domain_id (即 sub_domain 表的 domain_id 列),
          parent_dim=product, parent_value=1

          → domain_id IN (
              SELECT id FROM sub_domains WHERE domain_id IN (
                SELECT id FROM domains WHERE version_id IN (
                  SELECT id FROM versions WHERE product_id IN (
                    SELECT id FROM products WHERE id IN (?)
                  )
                )
              )
            )

        [适用场景]
          - 配置 permission_rule: field=service_module_id, op=DESCENDANTS_OF,
            parent_dim=domain, parent_value=2200
            → 该 service_module 必须在 domain=2200 下的任意层级 (sub_domain 内的 SM)
          - 与 CHILDREN_OF 区别: CHILDREN_OF 只查一层, DESCENDANTS_OF 递归到底
        """
        parent_dim = value.get('parent_dim', '')
        parent_value = value.get('parent_value')

        # 找到 parent_dim 在 HIERARCHY 中的位置
        parent_idx = None
        for i, (code, _, _) in enumerate(_HIERARCHY_FK):
            if code == parent_dim:
                parent_idx = i
                break
        if parent_idx is None:
            raise ValueError(
                f'DESCENDANTS_OF: unknown parent_dim {parent_dim}, '
                f'supported: {[c for c, _, _ in _HIERARCHY_FK]}'
            )

        # 找到 field 对应的 dim (即 fk_field 所属的 dim)
        # field 例如 'domain_id' → 该 fk_field 是 sub_domain 的, 指向 domain
        # 所以 current_dim = sub_domain (idx=3)
        current_idx = None
        for i, (code, fk, _) in enumerate(_HIERARCHY_FK):
            if fk == field:
                current_idx = i
                break
        if current_idx is None:
            raise ValueError(
                f'DESCENDANTS_OF: cannot determine dim for field {field}, '
                f'fk_fields: {[fk for _, fk, _ in _HIERARCHY_FK if fk]}'
            )

        # parent_idx 必须严格小于 current_idx (parent 是祖先)
        if parent_idx >= current_idx:
            raise ValueError(
                f'DESCENDANTS_OF: parent_dim {parent_dim} (idx={parent_idx}) '
                f'must be ancestor of field {field} (idx={current_idx})'
            )

        # 构建递归子查询: 从 parent_dim 出发, 逐层向下到 current_dim
        vals = parent_value if isinstance(parent_value, list) else [parent_value]
        placeholders = ', '.join(['?'] * len(vals))

        # 第一层: SELECT id FROM <parent_table> WHERE id IN (vals)
        parent_table = _HIERARCHY_FK[parent_idx][2]
        inner_query = f"SELECT id FROM {parent_table} WHERE id IN ({placeholders})"

        # 逐层向下到 current_dim
        # 每层: SELECT id FROM <dim_table> WHERE <fk_field> IN (上层)
        for i in range(parent_idx + 1, current_idx + 1):
            _, fk_field, dim_table = _HIERARCHY_FK[i]
            inner_query = (
                f"SELECT id FROM {dim_table} "
                f"WHERE {fk_field} IN ({inner_query})"
            )

        sql = f"{field} IN ({inner_query})"
        return sql, list(vals)

    def _build_ancestors_all_of(self, field: str, value: Dict) -> Tuple[str, List[Any]]:
        """ANCESTORS_ALL_OF: 向上递归所有层级

        [语义]
          给定 child_dim 的 id, 找出该 child 上溯到 target_dim 的祖先 id
          (跨多层 HIERARCHY, 与 ANCESTORS_OF 单层不同)

        [value 格式]
          {child_dim: "sub_domain", child_id: 101, target_dim: "product"}

        [生成 SQL 示例]
          field=product_id, child_dim=sub_domain, child_id=101, target_dim=product

          → product_id IN (
              SELECT product_id FROM versions WHERE id IN (
                SELECT version_id FROM domains WHERE id IN (
                  SELECT domain_id FROM sub_domains WHERE id = ?
                )
              )
            )

        [适用场景]
          - 配置 permission_rule: field=product_id, op=ANCESTORS_ALL_OF,
            child_dim=sub_domain, child_id=101, target_dim=product
            → 该 product 必须是 sub_domain=101 的祖先 product
          - 与 ANCESTORS_OF 区别: ANCESTORS_OF 只查一层 (直接 parent),
            ANCESTORS_ALL_OF 跨多层到指定 target_dim
        """
        child_dim = value.get('child_dim', '')
        child_id = value.get('child_id')
        target_dim = value.get('target_dim', '')

        # 找 child_dim 和 target_dim 在 HIERARCHY 中的位置
        child_idx = None
        target_idx = None
        for i, (code, _, _) in enumerate(_HIERARCHY_FK):
            if code == child_dim:
                child_idx = i
            if code == target_dim:
                target_idx = i

        if child_idx is None:
            raise ValueError(
                f'ANCESTORS_ALL_OF: unknown child_dim {child_dim}, '
                f'supported: {[c for c, _, _ in _HIERARCHY_FK]}'
            )
        if target_idx is None:
            raise ValueError(
                f'ANCESTORS_ALL_OF: unknown target_dim {target_dim}, '
                f'supported: {[c for c, _, _ in _HIERARCHY_FK]}'
            )

        # target_dim 必须是 child_dim 的祖先 (target_idx < child_idx)
        if target_idx >= child_idx:
            raise ValueError(
                f'ANCESTORS_ALL_OF: target_dim {target_dim} (idx={target_idx}) '
                f'must be ancestor of child_dim {child_dim} (idx={child_idx})'
            )

        # 从 child 向上递归到 target_dim
        # 每层查 fk_field (= 指向上一层 parent 的 id)
        # 最内层: SELECT <child_fk> FROM <child_table> WHERE id = ?
        # 中间层 (child-1 到 target+1): SELECT <fk> FROM <dim_table> WHERE id IN (上层)
        # 最外层 (target): SELECT id FROM <target_table> WHERE id IN (上层)

        # child 这一层的 fk_field (指向上一层的 id)
        child_fk_field = _HIERARCHY_FK[child_idx][1]
        if not child_fk_field:
            raise ValueError(
                f'ANCESTORS_ALL_OF: child_dim {child_dim} has no parent (顶层)'
            )

        # 最内层: SELECT <child_fk_field> FROM <child_table> WHERE id = ?
        child_table = _HIERARCHY_FK[child_idx][2]
        inner_query = f"SELECT {child_fk_field} FROM {child_table} WHERE id = ?"

        # 上溯: 从 child_idx - 1 到 target_idx (包含)
        # 中间层 SELECT fk_field (向上递归到 parent)
        # target 层 SELECT id (匹配 field = target_fk_field IN (SELECT id FROM target_table))
        for i in range(child_idx - 1, target_idx - 1, -1):
            _, fk_field, dim_table = _HIERARCHY_FK[i]
            if i == target_idx:
                # 到达 target_dim, SELECT id (用于匹配 field = target 的 fk_field)
                inner_query = (
                    f"SELECT id FROM {dim_table} "
                    f"WHERE id IN ({inner_query})"
                )
            else:
                # 中间层, SELECT fk_field (向上递归到 parent)
                inner_query = (
                    f"SELECT {fk_field} FROM {dim_table} "
                    f"WHERE id IN ({inner_query})"
                )

        sql = f"{field} IN ({inner_query})"
        return sql, [child_id]
