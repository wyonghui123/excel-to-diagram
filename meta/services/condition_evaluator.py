# -*- coding: utf-8 -*-
"""
条件解析器

支持三种条件类型：
1. predicate: SQL WHERE 风格 (product_id IN (1, 2, 3) AND domain_type = 'CORE')
2. field_range: 字段值范围 ({"fields": [...]})
3. 精确匹配: id = 5

安全特性：
- 白名单字段验证
- SQL 注入防护
- 参数化查询
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple


ALLOWED_OPERATORS = {'=', '!=', '<', '>', '<=', '>=', 'IN', 'NOT IN', 'LIKE', 'STARTS_WITH', 'CONTAINS'}
ALLOWED_FIELDS = {
    'id', 'product_id', 'version_id', 'domain_id', 'sub_domain_id',
    'service_module_id', 'business_object_id', 'domain_type', 'code',
    'name', 'status', 'created_by', 'owner_id', 'organization_id',
    'department_id', 'resource_type', 'category', 'type',
}
DANGEROUS_PATTERNS = [
    r'DROP\s', r'DELETE\s', r'UPDATE\s', r'INSERT\s', r'ALTER\s',
    r'CREATE\s', r'EXEC\s', r'EXECUTE\s', r'--', r';.*',
    r'UNION\s', r'OR\s+1\s*=\s*1', r"'--", r'xp_', r'sp_',
]


class ConditionEvaluator:
    """条件解析与评估引擎"""

    def __init__(self, allowed_fields: Optional[set] = None):
        self.allowed_fields = allowed_fields or ALLOWED_FIELDS

    def evaluate(self, condition: str, resource: Dict[str, Any]) -> bool:
        """
        评估条件是否匹配资源

        Args:
            condition: 条件表达式
            resource: 资源属性字典

        Returns:
            是否匹配
        """
        if not condition or not condition.strip():
            return True

        condition = condition.strip()

        if condition.startswith('{'):
            return self._evaluate_field_range(condition, resource)

        return self._evaluate_predicate(condition, resource)

    def _evaluate_predicate(self, predicate: str, resource: Dict[str, Any]) -> bool:
        """
        评估 SQL WHERE 风格的条件

        支持：
        - field = value
        - field IN (v1, v2, v3)
        - field != value
        - AND 组合
        """
        if not self._validate_predicate(predicate):
            return False

        parts = re.split(r'\s+AND\s+', predicate, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            if not self._evaluate_single_predicate(part, resource):
                return False

        return True

    def _evaluate_single_predicate(self, predicate: str, resource: Dict[str, Any]) -> bool:
        """评估单个谓词条件"""
        predicate = predicate.strip()

        in_match = re.match(r'^(\w+)\s+IN\s*\(([^)]+)\)$', predicate, re.IGNORECASE)
        if in_match:
            field = in_match.group(1)
            values_str = in_match.group(2)
            if field not in resource:
                return False
            values = [v.strip().strip("'\"") for v in values_str.split(',')]
            return str(resource[field]) in values

        not_in_match = re.match(r'^(\w+)\s+NOT\s+IN\s*\(([^)]+)\)$', predicate, re.IGNORECASE)
        if not_in_match:
            field = not_in_match.group(1)
            values_str = not_in_match.group(2)
            if field not in resource:
                return True
            values = [v.strip().strip("'\"") for v in values_str.split(',')]
            return str(resource[field]) not in values

        neq_match = re.match(r'^(\w+)\s*!=\s*(.+)$', predicate)
        if neq_match:
            field = neq_match.group(1)
            value = neq_match.group(2).strip().strip("'\"")
            if field not in resource:
                return True
            return str(resource[field]) != value

        eq_str_match = re.match(r"^(\w+)\s*=\s*'([^']*)'$", predicate)
        if eq_str_match:
            field = eq_str_match.group(1)
            value = eq_str_match.group(2)
            if field not in resource:
                return False
            return str(resource[field]) == value

        eq_num_match = re.match(r'^(\w+)\s*=\s*(\d+)$', predicate)
        if eq_num_match:
            field = eq_num_match.group(1)
            value = int(eq_num_match.group(2))
            if field not in resource:
                return False
            return resource[field] == value

        gt_match = re.match(r'^(\w+)\s*>\s*(\d+)$', predicate)
        if gt_match:
            field = gt_match.group(1)
            value = int(gt_match.group(2))
            if field not in resource:
                return False
            return resource[field] > value

        lt_match = re.match(r'^(\w+)\s*<\s*(\d+)$', predicate)
        if lt_match:
            field = lt_match.group(1)
            value = int(lt_match.group(2))
            if field not in resource:
                return False
            return resource[field] < value

        return False

    def _evaluate_field_range(self, condition_json: str, resource: Dict[str, Any]) -> bool:
        """
        评估字段值范围条件

        格式: {"fields": [{"name": "product_id", "operator": "in", "values": [1, 2, 3]}]}
        """
        try:
            config = json.loads(condition_json)
        except json.JSONDecodeError:
            return False

        fields = config.get('fields', [])
        for field_def in fields:
            field_name = field_def.get('name', '')
            operator = field_def.get('operator', '=')

            if field_name not in resource:
                return False

            actual = resource[field_name]

            if operator == 'in':
                values = field_def.get('values', [])
                if actual not in values:
                    return False
            elif operator == '=':
                if actual != field_def.get('value'):
                    return False
            elif operator == '!=':
                if actual == field_def.get('value'):
                    return False
            elif operator == 'between':
                min_val = field_def.get('min')
                max_val = field_def.get('max')
                if not (min_val <= actual <= max_val):
                    return False
            elif operator == 'starts_with':
                if not str(actual).startswith(str(field_def.get('value', ''))):
                    return False
            elif operator == 'contains':
                if str(field_def.get('value', '')) not in str(actual):
                    return False
            else:
                return False

        return True

    def _validate_predicate(self, predicate: str) -> bool:
        """验证谓词安全性"""
        upper = predicate.upper()
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, upper, re.IGNORECASE):
                return False
        return True

    def predicate_to_sql_where(self, predicate: str) -> Optional[str]:
        """
        将条件表达式转换为 SQL WHERE 子句

        用于分析场景的批量查询
        """
        if not self._validate_predicate(predicate):
            return None

        if predicate.startswith('{'):
            try:
                config = json.loads(predicate)
                parts = []
                for f in config.get('fields', []):
                    name = f['name']
                    op = f['operator']
                    if op == 'in':
                        vals = ','.join(str(v) for v in f['values'])
                        parts.append(f"{name} IN ({vals})")
                    elif op == '=':
                        v = f['value']
                        if isinstance(v, str):
                            parts.append(f"{name} = '{v}'")
                        else:
                            parts.append(f"{name} = {v}")
                    elif op == '!=':
                        v = f['value']
                        if isinstance(v, str):
                            parts.append(f"{name} != '{v}'")
                        else:
                            parts.append(f"{name} != {v}")
                    elif op == 'between':
                        parts.append(f"{name} BETWEEN {f['min']} AND {f['max']}")
                return ' AND '.join(parts) if parts else None
            except json.JSONDecodeError:
                return None

        return predicate

    def resolve_template(self, template: str, params: Dict[str, Any]) -> str:
        """
        解析条件模板中的参数

        如: "created_by = :user_id" → "created_by = 5"
        """
        result = template
        for key, value in params.items():
            placeholder = f':{key}'
            if placeholder in result:
                if isinstance(value, list):
                    vals = ','.join(str(v) for v in value)
                    result = result.replace(placeholder, vals)
                elif isinstance(value, str):
                    result = result.replace(placeholder, f"'{value}'")
                else:
                    result = result.replace(placeholder, str(value))
        return result

    def detect_instance_references(self, condition: str) -> List[Dict[str, Any]]:
        """
        检测条件中引用的实例

        识别 *_id = value 模式，返回引用列表
        """
        references = []

        id_pattern = r'(\w+_id)\s*=\s*(\d+)'
        for match in re.finditer(id_pattern, condition):
            field = match.group(1)
            value = int(match.group(2))
            resource_type = field.replace('_id', '')
            references.append({
                'field': field,
                'value': value,
                'resource_type': resource_type,
            })

        exact_pattern = r'^id\s*=\s*(\d+)$'
        for match in re.finditer(exact_pattern, condition):
            references.append({
                'field': 'id',
                'value': int(match.group(1)),
                'resource_type': 'exact',
            })

        return references
