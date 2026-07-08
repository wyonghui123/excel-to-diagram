# -*- coding: utf-8 -*-
import re

_SQL_RESERVED_WORDS = frozenset({
    'WHERE', 'AND', 'OR', 'NOT', 'NULL', 'TRUE', 'FALSE',
    'SELECT', 'FROM', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'ON',
    'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT', 'OFFSET',
    'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER',
    'IS', 'IN', 'LIKE', 'ILIKE', 'BETWEEN', 'EXISTS', 'AS',
    'ASC', 'DESC', 'DISTINCT', 'ALL', 'UNION', 'CASE', 'WHEN',
    'THEN', 'ELSE', 'END', 'SET', 'VALUES', 'INTO',
})

_COLUMN_ALIAS_PATTERN = re.compile(
    r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*'
    r'(=|<>|!=|>|<|>=|<=|LIKE|ILIKE|IN|NOT IN|IS|IS NOT)\s*',
    re.IGNORECASE,
)


def add_table_alias_to_where(sql: str, alias: str) -> str:
    """为 WHERE 子句中的裸列名添加表别名前缀

    消除 _execute_computed_field_query 和 _execute_virtual_field_query
    中两处完全重复的内部函数定义。
    """
    def replace_column(match):
        col = match.group(1)
        op = match.group(2)
        if col.upper() in _SQL_RESERVED_WORDS:
            return match.group(0)
        if '.' in col:
            return match.group(0)
        return f"{alias}.{col} {op} "

    return _COLUMN_ALIAS_PATTERN.sub(replace_column, sql)
