# -*- coding: utf-8 -*-
"""
订阅过滤条件解析器

支持解析和应用订阅的过滤条件，包括：
- 字段值匹配：field = value
- 字段范围：field > value, field < value
- 字段包含：field contains value
- 字段前缀：field starts_with value
- 字段后缀：field ends_with value
- 字段存在：field exists
- 逻辑组合：AND, OR, NOT
"""

import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from enum import Enum

logger = logging.getLogger(__name__)


class Operator(Enum):
    """支持的比较运算符"""
    EQ = "eq"           # 等于
    NE = "ne"          # 不等于
    GT = "gt"          # 大于
    GE = "ge"          # 大于等于
    LT = "lt"          # 小于
    LE = "le"          # 小于等于
    CONTAINS = "contains"    # 包含
    STARTS_WITH = "starts_with"  # 以...开始
    ENDS_WITH = "ends_with"      # 以...结束
    IN = "in"          # 在列表中
    NOT_IN = "not_in"  # 不在列表中
    EXISTS = "exists"   # 字段存在
    NOT_EXISTS = "not_exists"  # 字段不存在
    LIKE = "like"      # SQL LIKE
    ILIKE = "ilike"    # 不区分大小写的LIKE


class FilterExpression:
    """过滤表达式基类"""
    pass


@dataclass
class Condition(FilterExpression):
    """单个条件"""
    field: str
    operator: Operator
    value: Any
    
    def evaluate(self, data: Dict[str, Any]) -> bool:
        """评估条件是否匹配数据"""
        field_value = data.get(self.field)
        
        if self.operator == Operator.EQ:
            return field_value == self.value
        
        elif self.operator == Operator.NE:
            return field_value != self.value
        
        elif self.operator == Operator.GT:
            return field_value is not None and field_value > self.value
        
        elif self.operator == Operator.GE:
            return field_value is not None and field_value >= self.value
        
        elif self.operator == Operator.LT:
            return field_value is not None and field_value < self.value
        
        elif self.operator == Operator.LE:
            return field_value is not None and field_value <= self.value
        
        elif self.operator == Operator.CONTAINS:
            if field_value is None:
                return False
            return str(self.value).lower() in str(field_value).lower()
        
        elif self.operator == Operator.STARTS_WITH:
            if field_value is None:
                return False
            return str(field_value).lower().startswith(str(self.value).lower())
        
        elif self.operator == Operator.ENDS_WITH:
            if field_value is None:
                return False
            return str(field_value).lower().endswith(str(self.value).lower())
        
        elif self.operator == Operator.IN:
            return field_value in self.value
        
        elif self.operator == Operator.NOT_IN:
            return field_value not in self.value
        
        elif self.operator == Operator.EXISTS:
            return field_value is not None
        
        elif self.operator == Operator.NOT_EXISTS:
            return field_value is None
        
        elif self.operator == Operator.LIKE:
            if field_value is None:
                return False
            pattern = self.value.replace('%', '.*').replace('_', '.')
            return bool(re.match(pattern, str(field_value)))
        
        elif self.operator == Operator.ILIKE:
            if field_value is None:
                return False
            pattern = self.value.replace('%', '.*').replace('_', '.').lower()
            return bool(re.match(pattern, str(field_value).lower()))
        
        return False


@dataclass
class AndExpression(FilterExpression):
    """AND 组合表达式"""
    conditions: List[FilterExpression]
    
    def evaluate(self, data: Dict[str, Any]) -> bool:
        return all(c.evaluate(data) if isinstance(c, FilterExpression) else c 
                   for c in self.conditions)


@dataclass
class OrExpression(FilterExpression):
    """OR 组合表达式"""
    conditions: List[FilterExpression]
    
    def evaluate(self, data: Dict[str, Any]) -> bool:
        return any(c.evaluate(data) if isinstance(c, FilterExpression) else c 
                   for c in self.conditions)


@dataclass
class NotExpression(FilterExpression):
    """NOT 表达式"""
    condition: FilterExpression
    
    def evaluate(self, data: Dict[str, Any]) -> bool:
        return not self.condition.evaluate(data)


class FilterParser:
    """过滤条件解析器"""
    
    OPERATOR_MAP = {
        "=": Operator.EQ,
        "==": Operator.EQ,
        "!=": Operator.NE,
        "<>": Operator.NE,
        ">": Operator.GT,
        "gt": Operator.GT,
        ">=": Operator.GE,
        "ge": Operator.GE,
        "<": Operator.LT,
        "lt": Operator.LT,
        "<=": Operator.LE,
        "le": Operator.LE,
        "contains": Operator.CONTAINS,
        "starts_with": Operator.STARTS_WITH,
        "ends_with": Operator.ENDS_WITH,
        "in": Operator.IN,
        "not_in": Operator.NOT_IN,
        "exists": Operator.EXISTS,
        "not_exists": Operator.NOT_EXISTS,
        "like": Operator.LIKE,
        "ilike": Operator.ILIKE,
    }
    
    def parse(self, filter_config: Union[Dict, str, List]) -> Optional[FilterExpression]:
        """
        解析过滤配置
        
        Args:
            filter_config: 过滤配置，支持多种格式：
                - 简单字典: {"field": "name", "op": "eq", "value": "test"}
                - 字符串: "field = 'value'"
                - 列表: [{"field": "status", "op": "eq", "value": "active"}, ...]
                - 嵌套: {"and": [...]}, {"or": [...]}, {"not": {...}}
        
        Returns:
            FilterExpression 或 None
        """
        if filter_config is None:
            return None
        
        if isinstance(filter_config, str):
            return self._parse_string(filter_config)
        
        if isinstance(filter_config, dict):
            return self._parse_dict(filter_config)
        
        if isinstance(filter_config, list):
            if len(filter_config) == 1:
                return self.parse(filter_config[0])
            return AndExpression(conditions=[self.parse(c) for c in filter_config])
        
        return None
    
    def _parse_dict(self, config: Dict) -> Optional[FilterExpression]:
        """解析字典格式"""
        if not config:
            return None
        
        # 检查逻辑运算符
        if "and" in config:
            conditions = [self.parse(c) for c in config["and"]]
            return AndExpression(conditions=[c for c in conditions if c is not None])
        
        if "or" in config:
            conditions = [self.parse(c) for c in config["or"]]
            return OrExpression(conditions=[c for c in conditions if c is not None])
        
        if "not" in config:
            inner = self.parse(config["not"])
            if inner:
                return NotExpression(condition=inner)
            return None
        
        # 单个条件
        field = config.get("field")
        if not field:
            return None
        
        op_str = config.get("op", "eq")
        if isinstance(op_str, str):
            op_str = op_str.lower()
        
        operator = self.OPERATOR_MAP.get(op_str, Operator.EQ)
        value = config.get("value")
        
        return Condition(field=field, operator=operator, value=value)
    
    def _parse_string(self, expr: str) -> Optional[FilterExpression]:
        """解析字符串格式"""
        expr = expr.strip()
        
        # 解析 AND
        if " AND " in expr.upper():
            parts = re.split(r'\s+AND\s+', expr, flags=re.IGNORECASE)
            conditions = [self.parse_string(p) for p in parts]
            return AndExpression(conditions=[c for c in conditions if c])
        
        # 解析 OR
        if " OR " in expr.upper():
            parts = re.split(r'\s+OR\s+', expr, flags=re.IGNORECASE)
            conditions = [self.parse_string(p) for p in parts]
            return OrExpression(conditions=[c for c in conditions if c])
        
        # 解析 NOT
        not_match = re.match(r'NOT\s+(.*)', expr, re.IGNORECASE)
        if not_match:
            inner = self.parse_string(not_match.group(1))
            if inner:
                return NotExpression(condition=inner)
            return None
        
        # 解析简单条件
        return self._parse_simple_condition(expr)
    
    def _parse_simple_condition(self, expr: str) -> Optional[Condition]:
        """解析简单条件表达式"""
        expr = expr.strip()
        
        # 匹配 field op 'value' 或 field op value
        patterns = [
            (r"(\w+)\s*=\s*'(.*)'", Operator.EQ),
            (r'(\w+)\s*=\s*"(.*)"', Operator.EQ),
            (r"(\w+)\s*=\s*(\S+)", Operator.EQ),
            (r"(\w+)\s*!=\s*'(.*)'", Operator.NE),
            (r'(\w+)\s*!=\s*"(.*)"', Operator.NE),
            (r"(\w+)\s*!=\s*(\S+)", Operator.NE),
            (r"(\w+)\s*>\s*(\S+)", Operator.GT),
            (r"(\w+)\s*>=\s*(\S+)", Operator.GE),
            (r"(\w+)\s*<\s*(\S+)", Operator.LT),
            (r"(\w+)\s*<=\s*(\S+)", Operator.LE),
            (r"(\w+)\s+contains\s+'(.*)'", Operator.CONTAINS),
            (r"(\w+)\s+starts_with\s+'(.*)'", Operator.STARTS_WITH),
            (r"(\w+)\s+ends_with\s+'(.*)'", Operator.ENDS_WITH),
            (r"(\w+)\s+exists", Operator.EXISTS),
            (r"(\w+)\s+not_exists", Operator.NOT_EXISTS),
        ]
        
        for pattern, op in patterns:
            match = re.match(pattern, expr, re.IGNORECASE)
            if match:
                groups = match.groups()
                field = groups[0]
                value = groups[1] if len(groups) > 1 else None
                
                # 类型转换
                if value is not None:
                    if value.lower() == 'null' or value.lower() == 'none':
                        value = None
                    elif value.lower() == 'true':
                        value = True
                    elif value.lower() == 'false':
                        value = False
                    elif value.isdigit():
                        value = int(value)
                    elif re.match(r'^\d+\.\d+$', value):
                        value = float(value)
                
                return Condition(field=field, operator=op, value=value)
        
        return None
    
    def parse_string(self, expr: str) -> Optional[FilterExpression]:
        """别名方法"""
        return self._parse_string(expr)


class SubscriptionFilter:
    """订阅过滤器"""
    
    def __init__(self):
        self.parser = FilterParser()
    
    def matches(
        self,
        filter_condition: Union[Dict, str, List],
        event_data: Dict[str, Any]
    ) -> bool:
        """
        检查事件是否匹配过滤条件
        
        Args:
            filter_condition: 过滤条件配置
            event_data: 事件数据
        
        Returns:
            bool: 是否匹配
        """
        if not filter_condition:
            return True
        
        expression = self.parser.parse(filter_condition)
        if not expression:
            return True
        
        try:
            return expression.evaluate(event_data)
        except Exception as e:
            logger.warning(
                f"Filter evaluation error: {e}, returning True",
                extra={"condition": filter_condition, "data": event_data}
            )
            return True
    
    def matches_subscription(
        self,
        subscription: Dict[str, Any],
        event_data: Dict[str, Any]
    ) -> bool:
        """
        检查事件是否匹配订阅的过滤条件
        
        Args:
            subscription: 订阅配置
            event_data: 事件数据
        
        Returns:
            bool: 是否匹配
        """
        filter_condition = subscription.get('filter_condition')
        
        if not filter_condition:
            return True
        
        if isinstance(filter_condition, str):
            try:
                import json
                filter_condition = json.loads(filter_condition)
            except json.JSONDecodeError:
                pass
        
        return self.matches(filter_condition, event_data)


subscription_filter = SubscriptionFilter()
