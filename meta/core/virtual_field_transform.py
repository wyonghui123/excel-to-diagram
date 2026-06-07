"""虚拟字段转换引擎

参考 SAP SADL 的 IF_SADL_EXIT_SORT_TRANSFORM 机制，
将虚拟字段的排序和过滤转换为数据库可执行的 SQL 表达式。

## 架构原则：单一事实源（Single Source of Truth）

本模块遵循语义模型驱动架构的核心原则：
- 规则定义的唯一来源：hierarchies.yaml 中的 hierarchy_scopes
- 字段配置通过 `ref` 引用权威定义，不重复定义规则
- 系统运行时自动从权威来源生成 SQL 表达式

示例配置（推荐方式 - 引用权威定义）：
  semantics:
    computed_by: hierarchy_scope
    scope_rules_ref: hierarchies.hierarchy_scopes  # 引用权威定义

示例配置（旧方式 - 直接定义，仅用于无权威来源的场景）：
  sort_transform:
    by: category_type              # 映射到已有字段
    # 或
    sql_expr: |                    # SQL 表达式
      CASE WHEN source_domain_id != target_domain_id THEN 1 ELSE 2 END
"""

import logging
from typing import Any, Dict, Optional, Tuple, List

logger = logging.getLogger(__name__)

# 权威规则缓存
_scope_rules_cache: Dict[str, List[Dict[str, Any]]] = {}


def load_scope_rules_from_ref(ref: str) -> List[Dict[str, Any]]:
    """从引用路径加载权威规则定义
    
    Args:
        ref: 引用路径，如 'hierarchies.hierarchy_scopes'
        
    Returns:
        规则列表，每个规则包含 id, name, rule 等字段
    """
    if ref in _scope_rules_cache:
        return _scope_rules_cache[ref]
    
    parts = ref.split('.')
    if len(parts) != 2:
        logger.warning(f"[TransformEngine] Invalid ref format: {ref}, expected 'file.key'")
        return []
    
    file_name, key = parts
    
    try:
        import yaml
        from pathlib import Path
        
        schema_dir = Path(__file__).parent.parent / 'schemas'
        yaml_file = schema_dir / f'{file_name}.yaml'
        
        if not yaml_file.exists():
            logger.warning(f"[TransformEngine] Schema file not found: {yaml_file}")
            return []
        
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        rules = data.get(key, [])
        _scope_rules_cache[ref] = rules
        logger.info(f"[TransformEngine] Loaded {len(rules)} scope rules from {ref}")
        return rules
        
    except Exception as e:
        logger.error(f"[TransformEngine] Failed to load scope rules from {ref}: {e}")
        return []


def generate_scope_sql_from_rules(rules: List[Dict[str, Any]], for_sort: bool = False) -> str:
    """从规则定义生成 SQL CASE 表达式
    
    Args:
        rules: 规则列表
        for_sort: 是否用于排序（排序返回数字序号，过滤返回标签名）
        
    Returns:
        SQL CASE 表达式
    """
    if not rules:
        return ""
    
    cases = []
    for idx, rule in enumerate(rules, 1):
        rule_expr = rule.get('rule', '')
        sql_rule = _transform_rule_to_sql(rule_expr)
        
        if for_sort:
            cases.append(f"WHEN {sql_rule} THEN {idx}")
        else:
            name = rule.get('name', rule.get('id', ''))
            cases.append(f"WHEN {sql_rule} THEN '{name}'")
    
    return f"CASE {' '.join(cases)} END"


def _transform_rule_to_sql(rule: str) -> str:
    """将规则表达式转换为 SQL 表达式
    
    转换规则（使用直接表列引用，避免 SELECT 别名在 ORDER BY CASE 中的解析问题）：
    - source.domain_id -> d1.id (domains 表别名)
    - target.domain_id -> d2.id
    - source.sub_domain_id -> sd1.id (sub_domains 表别名)
    - target.sub_domain_id -> sd2.id
    - source.service_module_id -> sm1.id (service_modules 表别名)
    - target.service_module_id -> sm2.id
    - == -> = (SQL 标准等号)
    - AND/OR 保持不变
    """
    sql_rule = rule
    sql_rule = sql_rule.replace('source.domain_id', 'd1.id')
    sql_rule = sql_rule.replace('target.domain_id', 'd2.id')
    sql_rule = sql_rule.replace('source.sub_domain_id', 'sd1.id')
    sql_rule = sql_rule.replace('target.sub_domain_id', 'sd2.id')
    sql_rule = sql_rule.replace('source.service_module_id', 'sm1.id')
    sql_rule = sql_rule.replace('target.service_module_id', 'sm2.id')
    sql_rule = sql_rule.replace('==', '=')
    return sql_rule


class VirtualFieldTransformEngine:
    """虚拟字段转换引擎
    
    负责将虚拟字段的排序和过滤操作转换为数据库可执行的 SQL。
    
    转换策略（按优先级）：
    1. scope_rules_ref: 从权威定义自动生成 SQL（推荐，符合单一事实源原则）
    2. sort_transform.by: 将虚拟字段排序映射到真实字段
    3. sort_transform.sql_expr: 使用直接定义的 SQL 表达式
    
    如果无法转换，返回 None，由调用方决定回退策略（如内存排序）。
    """
    
    def __init__(self, meta_registry=None):
        """初始化转换引擎
        
        Args:
            meta_registry: 元模型注册中心，用于查找字段定义
        """
        self.meta_registry = meta_registry
    
    def transform_sort(
        self, 
        meta_obj: Any, 
        field_id: str, 
        direction: str = "asc"
    ) -> Optional[Tuple[str, bool]]:
        """将虚拟字段排序转换为 SQL ORDER BY 表达式
        
        Args:
            meta_obj: 元对象
            field_id: 字段ID
            direction: 排序方向 (asc/desc)
            
        Returns:
            Tuple[str, bool]: (SQL表达式, 是否为表达式而非字段名)
            None: 无法转换，需要回退到内存排序
        """
        if not meta_obj:
            return None
        
        field = meta_obj.get_field(field_id) if hasattr(meta_obj, 'get_field') else None
        if not field:
            logger.debug(f"[TransformEngine] Field '{field_id}' not found in meta object")
            return None
        
        semantics = getattr(field, 'semantics', None)
        if not semantics:
            return None
        
        # 方案1: 从权威定义引用（推荐）
        scope_rules_ref = getattr(semantics, 'scope_rules_ref', None) or \
                         (semantics.get('scope_rules_ref') if isinstance(semantics, dict) else None)
        if scope_rules_ref:
            rules = load_scope_rules_from_ref(scope_rules_ref)
            if rules:
                sql_expr = generate_scope_sql_from_rules(rules, for_sort=True)
                direction_upper = direction.upper()
                full_expr = f"({sql_expr}) {direction_upper}"
                logger.info(f"[TransformEngine] Generated sort SQL from ref '{scope_rules_ref}': {full_expr}")
                return (full_expr, True)
        
        sort_transform = getattr(semantics, 'sort_transform', None)
        if not sort_transform:
            logger.debug(f"[TransformEngine] Field '{field_id}' has no sort_transform config")
            return None
        
        # 方案2: 映射到已有字段
        if 'by' in sort_transform:
            mapped_field = sort_transform['by']
            logger.info(f"[TransformEngine] Mapping sort from '{field_id}' to '{mapped_field}'")
            return (mapped_field, False)
        
        # 方案3: 使用直接定义的 SQL 表达式
        if 'sql_expr' in sort_transform:
            sql_expr = sort_transform['sql_expr'].strip()
            direction_upper = direction.upper()
            full_expr = f"({sql_expr}) {direction_upper}"
            logger.info(f"[TransformEngine] Using SQL expression for sort: {full_expr}")
            return (full_expr, True)
        
        logger.debug(f"[TransformEngine] No valid sort transform config for '{field_id}'")
        return None
    
    def transform_filter(
        self,
        meta_obj: Any,
        field_id: str,
        operator: str,
        value: Any
    ) -> Optional[str]:
        """将虚拟字段过滤转换为 SQL WHERE 条件
        
        Args:
            meta_obj: 元对象
            field_id: 字段ID
            operator: 操作符 (eq, ne, gt, lt, gte, lte, like, in, not_in)
            value: 过滤值
            
        Returns:
            str: SQL WHERE 条件表达式
            None: 无法转换
        """
        if not meta_obj:
            return None
        
        field = meta_obj.get_field(field_id) if hasattr(meta_obj, 'get_field') else None
        if not field:
            return None
        
        semantics = getattr(field, 'semantics', None)
        if not semantics:
            return None
        
        # 方案1: 从权威定义引用（推荐）
        scope_rules_ref = getattr(semantics, 'scope_rules_ref', None) or \
                         (semantics.get('scope_rules_ref') if isinstance(semantics, dict) else None)
        if scope_rules_ref:
            rules = load_scope_rules_from_ref(scope_rules_ref)
            if rules:
                sql_expr = generate_scope_sql_from_rules(rules, for_sort=False)
                sql_operator = self._map_operator(operator)
                if not sql_operator:
                    return None
                
                if operator in ('in', 'not_in'):
                    if not isinstance(value, (list, tuple)):
                        value = [value]
                    placeholders = ', '.join(['?' for _ in value])
                    condition = f"({sql_expr}) {sql_operator} ({placeholders})"
                    params = list(value)
                else:
                    condition = f"({sql_expr}) {sql_operator} ?"
                    params = [value]
                
                logger.info(f"[TransformEngine] Generated filter SQL from ref '{scope_rules_ref}': {condition}")
                return condition
        
        filter_transform = getattr(semantics, 'filter_transform', None)
        if not filter_transform:
            logger.debug(f"[TransformEngine] Field '{field_id}' has no filter_transform config")
            return None
        
        # 方案2: 使用直接定义的 SQL 表达式
        if 'sql_expr' not in filter_transform:
            return None
        
        sql_expr = filter_transform['sql_expr'].strip()
        
        sql_operator = self._map_operator(operator)
        if not sql_operator:
            logger.warning(f"[TransformEngine] Unsupported operator: {operator}")
            return None
        
        if operator in ('in', 'not_in'):
            if not isinstance(value, (list, tuple)):
                value = [value]
            placeholders = ', '.join(['?' for _ in value])
            condition = f"({sql_expr}) {sql_operator} ({placeholders})"
        elif isinstance(value, str):
            condition = f"({sql_expr}) {sql_operator} ?"
        elif isinstance(value, (int, float)):
            condition = f"({sql_expr}) {sql_operator} ?"
        elif value is None:
            if operator == 'eq':
                condition = f"({sql_expr}) IS NULL"
            elif operator == 'ne':
                condition = f"({sql_expr}) IS NOT NULL"
            else:
                return None
        else:
            condition = f"({sql_expr}) {sql_operator} ?"
        
        logger.info(f"[TransformEngine] Filter transform: {condition}")
        return condition
    
    def _map_operator(self, operator: str) -> Optional[str]:
        """将应用层操作符映射到 SQL 操作符"""
        operator_map = {
            'eq': '=',
            'ne': '!=',
            'gt': '>',
            'lt': '<',
            'gte': '>=',
            'lte': '<=',
            'like': 'LIKE',
            'ilike': 'LIKE',  # SQLite 不区分大小写
            'in': 'IN',
            'not_in': 'NOT IN',
            'is_null': 'IS NULL',
            'is_not_null': 'IS NOT NULL',
        }
        return operator_map.get(operator.lower())
    
    def get_sort_transform_info(self, meta_obj: Any, field_id: str) -> Dict[str, Any]:
        """获取字段的排序转换信息（用于调试和日志）"""
        if not meta_obj:
            return {'has_transform': False, 'reason': 'no_meta_obj'}
        
        field = meta_obj.get_field(field_id) if hasattr(meta_obj, 'get_field') else None
        if not field:
            return {'has_transform': False, 'reason': 'field_not_found'}
        
        storage = getattr(field, 'storage', None)
        from meta.core.models import FieldStorage
        is_virtual = storage == FieldStorage.VIRTUAL
        
        semantics = getattr(field, 'semantics', None)
        sort_transform = getattr(semantics, 'sort_transform', None) if semantics else None
        
        return {
            'has_transform': bool(sort_transform),
            'is_virtual': is_virtual,
            'transform_type': 'by' if sort_transform and 'by' in sort_transform else 
                              'sql_expr' if sort_transform and 'sql_expr' in sort_transform else None,
            'transform_config': sort_transform,
        }


# 全局单例
_transform_engine: Optional[VirtualFieldTransformEngine] = None


def get_transform_engine(meta_registry=None) -> VirtualFieldTransformEngine:
    """获取转换引擎单例"""
    global _transform_engine
    if _transform_engine is None:
        _transform_engine = VirtualFieldTransformEngine(meta_registry)
    return _transform_engine
