# -*- coding: utf-8 -*-
"""
ConditionConverter — 自由文本条件 → 结构化 [{field,op,value}]

[背景]
  data_permission_rules.condition 字段当前以自由文本存储 (如 "domain_id IN (1,2,3)"),
  Phase 2 需要迁移为结构化格式 [{field, op, value}], 供推导管道使用。

[支持的操作符]
  =, !=, <, <=, >, >=, IN, NOT IN, LIKE, IS NULL, IS NOT NULL

[支持的形式]
  - 简单比较:     status = 'active'
  - 数值比较:     risk_level <= 3
  - IN 子句:      domain_id IN (1, 2, 3)
  - AND 组合:     a = 1 AND b = 2
  - 运行时变量:   owner_id = ${user.id}

[不支持]
  - OR 组合 (语义复杂, 旧系统也少用)
  - 嵌套括号 (转义困难, 推荐拆分为多规则)
"""
import re
from typing import Any, List, Dict, Optional


# 操作符正则 (按长度递减, 优先匹配长操作符)
_OPERATORS = [
    'IS NOT NULL', 'IS NULL',
    'NOT IN', 'IN',
    '<=', '>=', '!=', '<', '>', '=',
    'LIKE',
]

# 匹配单条条件: field OP value
# - field: 标识符 (字母数字下划线, 含点号)
# - OP: 上述操作符之一
# - value: 字符串/数字/列表/变量
_CONDITION_RE = re.compile(
    r'^\s*'
    r'(?P<field>[A-Za-z_][A-Za-z0-9_\.]*)\s+'
    r'(?P<op>IS\s+NOT\s+NULL|IS\s+NULL|NOT\s+IN|IN|<=|>=|!=|<|>|=|LIKE)\s+'
    r'(?P<value>.+?)\s*$',
    re.IGNORECASE,
)

# AND 拆分 (顶级, 不在括号内)
_AND_RE = re.compile(r'\s+AND\s+', re.IGNORECASE)

# 运行时变量 ${...}
_VAR_RE = re.compile(r'^\$\{[^}]+\}$')

# IN 列表 (1, 2, 3)
_IN_LIST_RE = re.compile(r'^\(([^)]*)\)$')

# 字符串字面量 'xxx'
_STR_LITERAL_RE = re.compile(r"^'([^']*)'$")

# 数字字面量 (含负数、小数)
_NUM_LITERAL_RE = re.compile(r'^-?\d+(?:\.\d+)?$')


class ConditionParseError(ValueError):
    """条件文本无法被扁平 AND 解析器完整消费（禁止静默丢弃）。"""


class ConditionConverter:
    """自由文本条件 → 结构化 [{field, op, value}]"""

    def convert(self, text: Optional[str]) -> List[Dict[str, Any]]:
        """转换自由文本为结构化条件列表

        Args:
            text: 自由文本条件
                - "status = 'active'"
                - "domain_id IN (1, 2, 3) AND risk_level <= 3"
                - None / "" → []

        Returns:
            [{field, op, value}, ...]
            失败的子条件会被跳过 (不抛异常, 保持向前兼容)
        """
        if not text or not text.strip():
            return []

        # 顶级按 AND 拆分 (保持简单, 不处理嵌套括号)
        parts = self._split_and(text)
        conditions = []
        for part in parts:
            cond = self._parse_single(part.strip())
            if cond is not None:
                conditions.append(cond)
        return conditions

    def _split_and(self, text: str) -> List[str]:
        """按顶级 AND 拆分 (忽略括号内的 AND)

        简单实现: 跟踪括号深度, 在深度 0 处拆分。
        """
        parts = []
        depth = 0
        current = []
        i = 0
        upper = text.upper()
        while i < len(text):
            c = text[i]
            if c == '(':
                depth += 1
                current.append(c)
                i += 1
            elif c == ')':
                depth -= 1
                current.append(c)
                i += 1
            elif depth == 0 and i + 5 <= len(text) and upper[i:i + 5] == ' AND ':
                parts.append(''.join(current))
                current = []
                i += 5
            else:
                current.append(c)
                i += 1
        if current:
            parts.append(''.join(current))
        return [p for p in (p.strip() for p in parts) if p]

    def _parse_single(self, expr: str) -> Optional[Dict[str, Any]]:
        """解析单条条件: field OP value"""
        if not expr:
            return None

        # IS NULL / IS NOT NULL (无值)
        m_is = re.match(
            r'^\s*(?P<field>[A-Za-z_][A-Za-z0-9_\.]*)\s+'
            r'(?P<op>IS\s+NOT\s+NULL|IS\s+NULL)\s*$',
            expr, re.IGNORECASE,
        )
        if m_is:
            op_norm = 'IS NOT NULL' if 'NOT' in m_is.group('op').upper() else 'IS NULL'
            return {
                'field': m_is.group('field'),
                'op': op_norm,
                'value': None,
            }

        m = _CONDITION_RE.match(expr)
        if not m:
            return None

        field = m.group('field')
        op = m.group('op').upper()
        value_raw = m.group('value').strip()

        # 处理 NULL 字面量
        if value_raw.upper() == 'NULL':
            return {'field': field, 'op': op, 'value': None}

        # IN / NOT IN: 解析为 list
        if op in ('IN', 'NOT IN'):
            value = self._parse_in_list(value_raw)
            if value is None:
                return None
            return {'field': field, 'op': op, 'value': value}

        # 单值
        value = self._parse_value(value_raw)
        if value is None and not _VAR_RE.match(value_raw):
            # 既不是字面量也不是变量, 跳过
            return None
        return {'field': field, 'op': op, 'value': value}

    def _parse_in_list(self, raw: str) -> Optional[List[Any]]:
        """解析 IN 列表: (1, 2, 3) → [1, 2, 3]"""
        m = _IN_LIST_RE.match(raw)
        if not m:
            return None
        items = []
        for item in m.group(1).split(','):
            item = item.strip()
            if not item:
                continue
            v = self._parse_value(item)
            if v is None and not _VAR_RE.match(item):
                continue
            items.append(v if v is not None else item)
        return items if items else None

    def _parse_value(self, raw: str) -> Any:
        """解析单值: 字符串/数字/变量/NULL"""
        if not raw:
            return None
        # 运行时变量 ${user.id}
        if _VAR_RE.match(raw):
            return raw
        # 字符串字面量
        m = _STR_LITERAL_RE.match(raw)
        if m:
            return m.group(1)
        # 数字字面量
        if _NUM_LITERAL_RE.match(raw):
            return int(raw) if '.' not in raw else float(raw)
        # 布尔 (兼容老格式)
        if raw.upper() in ('TRUE', 'FALSE'):
            return raw.upper() == 'TRUE'
        # 裸字符串 (可能是字段名, 不带引号), 作为字符串返回
        if re.match(r'^[A-Za-z_][A-Za-z0-9_\.]*$', raw):
            return raw
        return None


def validate_condition_text(text: Optional[str]) -> List[Dict[str, Any]]:
    """严格解析条件文本：任何片段无法解析即抛 :class:`ConditionParseError`。

    与 ``ConditionConverter.convert`` 的区别：convert 为向前兼容会**静默跳过**
    无法解析的片段（如未知算子 / OR 组合 / 嵌套括号），导致落库后求值链路
    只消费部分条件（fail-open 风险）。写路径必须用本函数，保证「存什么就求什么」。

    Returns:
        [{field, op, value}, ...]；空文本返回 []。

    Raises:
        ConditionParseError: 存在 OR 组合 / 括号不匹配 / 无法解析的片段。
    """
    if text is None:
        return []
    raw = str(text)
    if not raw.strip():
        return []

    # 1. 顶层 OR：求值链路（condition_evaluator）只按 AND 拆分，OR 会被吞掉
    upper = raw.upper()
    depth = 0
    for i, ch in enumerate(raw):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                raise ConditionParseError('条件括号不匹配')
        elif depth == 0 and upper[i:i + 4] == ' OR ':
            raise ConditionParseError('条件不支持 OR 组合（求值链路仅支持 AND 串联），请拆分为多条规则')
    if depth != 0:
        raise ConditionParseError('条件括号不匹配')

    # 2. 逐段严格解析：复用 convert 的拆分 / 单条解析，但不允许任何片段被丢弃
    converter = ConditionConverter()
    conditions: List[Dict[str, Any]] = []
    for part in converter._split_and(raw):
        cond = converter._parse_single(part)
        if cond is None:
            raise ConditionParseError(f'条件片段无法解析: {part}')
        conditions.append(cond)
    return conditions
