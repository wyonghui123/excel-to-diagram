# -*- coding: utf-8 -*-
"""
派生字段查询引擎 - DerivationExecutor

实现从 audit_logs 派生 created_by/updated_by 的查询机制。
参考 SAP CDS Virtual Field 机制，支持解析 derivation.rule 中的 SQL 规则。

设计原则：
- 规则驱动：通过 derivation.rule 定义派生逻辑
- 性能优化：支持批量派生，减少数据库查询次数
- 可扩展：支持多种派生源（audit_logs、其他表等）
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class DerivationRule:
    """
    派生规则定义
    
    从 SQL 风格的规则字符串解析而来，例如：
    - "user_name WHERE action = 'CREATE'"
    - "user_name ORDER BY created_at DESC LIMIT 1 WHERE action IN ('CREATE', 'UPDATE')"
    """
    select_field: str = ""
    where_clause: str = ""
    order_by: str = ""
    limit: int = 1
    raw_rule: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "select_field": self.select_field,
            "where_clause": self.where_clause,
            "order_by": self.order_by,
            "limit": self.limit,
            "raw_rule": self.raw_rule,
        }


@dataclass
class DerivationResult:
    """
    派生结果
    
    包含派生后的字段值和元数据
    """
    success: bool = True
    field_name: str = ""
    value: Any = None
    source: str = ""
    rule: str = ""
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "field_name": self.field_name,
            "value": self.value,
            "source": self.source,
            "rule": self.rule,
            "message": self.message,
        }


class DerivationRuleParser:
    """
    派生规则解析器
    
    解析 SQL 风格的派生规则字符串，支持：
    - SELECT 字段选择
    - WHERE 条件过滤
    - ORDER BY 排序
    - LIMIT 结果限制
    """
    
    SELECT_PATTERN = re.compile(r'^\s*(\w+)\s*', re.IGNORECASE)
    WHERE_PATTERN = re.compile(r'\bWHERE\s+(.+?)(?=\s+ORDER|\s+LIMIT|$)', re.IGNORECASE)
    ORDER_PATTERN = re.compile(r'\bORDER\s+BY\s+(.+?)(?=\s+LIMIT|$)', re.IGNORECASE)
    LIMIT_PATTERN = re.compile(r'\bLIMIT\s+(\d+)', re.IGNORECASE)
    
    @classmethod
    def parse(cls, rule_str: str) -> DerivationRule:
        """
        解析派生规则字符串
        
        Args:
            rule_str: 规则字符串，例如 "user_name WHERE action = 'CREATE'"
            
        Returns:
            DerivationRule 解析后的规则对象
        """
        if not rule_str or not rule_str.strip():
            return DerivationRule(raw_rule=rule_str)
        
        rule = DerivationRule(raw_rule=rule_str)
        
        select_match = cls.SELECT_PATTERN.match(rule_str)
        if select_match:
            rule.select_field = select_match.group(1)
        
        where_match = cls.WHERE_PATTERN.search(rule_str)
        if where_match:
            rule.where_clause = where_match.group(1).strip()
        
        order_match = cls.ORDER_PATTERN.search(rule_str)
        if order_match:
            rule.order_by = order_match.group(1).strip()
        
        limit_match = cls.LIMIT_PATTERN.search(rule_str)
        if limit_match:
            rule.limit = int(limit_match.group(1))
        
        return rule
    
    @classmethod
    def validate_rule(cls, rule: DerivationRule) -> Tuple[bool, str]:
        """
        验证派生规则的有效性
        
        Args:
            rule: 派生规则对象
            
        Returns:
            (是否有效, 错误消息)
        """
        if not rule.select_field:
            return False, "Missing select field"
        
        if rule.limit < 1:
            return False, "Limit must be at least 1"
        
        return True, ""


class DerivationExecutor:
    """
    派生字段查询引擎
    
    实现从 audit_logs 派生 created_by/updated_by 的查询机制。
    参考 SAP CDS Virtual Field 机制。
    
    使用示例：
    ```python
    from meta.core.derivation_executor import DerivationExecutor
    from meta.core.datasource import DataSource
    
    ds = DataSource()
    executor = DerivationExecutor(ds)
    
    # 派生单个字段
    result = executor.derive_field(
        object_type="domain",
        object_id=123,
        field_name="created_by",
        derivation_rule="user_name WHERE action = 'CREATE'"
    )
    
    # 批量派生
    results = executor.derive_batch(
        object_type="domain",
        object_ids=[1, 2, 3],
        field_names=["created_by", "updated_by"],
        derivation_rules={
            "created_by": "user_name WHERE action = 'CREATE'",
            "updated_by": "user_name ORDER BY created_at DESC LIMIT 1 WHERE action IN ('CREATE', 'UPDATE')"
        }
    )
    ```
    """
    
    AUDIT_TABLE = "audit_logs"
    
    def __init__(self, data_source=None):
        """
        初始化派生执行器
        
        Args:
            data_source: 数据源实例
        """
        self.ds = data_source
        self._cache: Dict[str, Any] = {}
        self._cache_enabled = True
        self._cache_ttl = 300
    
    def derive_field(
        self,
        object_type: str,
        object_id: Any,
        field_name: str,
        derivation_rule: str,
        use_cache: bool = True
    ) -> DerivationResult:
        """
        根据 derivation 规则派生字段值
        
        Args:
            object_type: 对象类型（如 "domain", "business_object"）
            object_id: 对象ID
            field_name: 字段名（如 "created_by", "updated_by"）
            derivation_rule: 派生规则字符串
            use_cache: 是否使用缓存
            
        Returns:
            DerivationResult 派生结果
        """
        if not self.ds:
            return DerivationResult(
                success=False,
                field_name=field_name,
                source="audit_logs",
                rule=derivation_rule,
                message="No data source configured"
            )
        
        cache_key = self._build_cache_key(object_type, object_id, field_name)
        if use_cache and self._cache_enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            if self._is_cache_valid(cached):
                return DerivationResult(
                    success=True,
                    field_name=field_name,
                    value=cached["value"],
                    source="cache",
                    rule=derivation_rule,
                    message="Retrieved from cache"
                )
        
        rule = DerivationRuleParser.parse(derivation_rule)
        valid, msg = DerivationRuleParser.validate_rule(rule)
        if not valid:
            return DerivationResult(
                success=False,
                field_name=field_name,
                source="audit_logs",
                rule=derivation_rule,
                message=f"Invalid rule: {msg}"
            )
        
        if field_name in ("created_by", "updated_by"):
            result = self._derive_user_name(
                object_type=object_type,
                object_id=object_id,
                field_name=field_name,
                rule=rule
            )
        else:
            result = self._derive_from_audit_logs(
                object_type=object_type,
                object_id=object_id,
                field_name=field_name,
                rule=rule
            )
        
        if use_cache and self._cache_enabled and result.success:
            self._cache[cache_key] = {
                "value": result.value,
                "timestamp": datetime.now().timestamp()
            }
        
        return result
    
    def _derive_from_audit_logs(
        self,
        object_type: str,
        object_id: Any,
        field_name: str,
        rule: DerivationRule
    ) -> DerivationResult:
        """
        从 audit_logs 派生字段
        
        Args:
            object_type: 对象类型
            object_id: 对象ID
            field_name: 字段名
            rule: 派生规则
            
        Returns:
            DerivationResult 派生结果
        """
        try:
            filters = {
                "object_type": object_type,
                "object_id": object_id,
            }
            
            if rule.where_clause:
                where_filters = self._parse_where_clause(rule.where_clause)
                filters.update(where_filters)
            
            order_by = rule.order_by if rule.order_by else "created_at DESC"
            records = self.ds.find(
                self.AUDIT_TABLE,
                filters=filters,
                order_by=order_by,
                limit=rule.limit
            )
            
            if not records:
                return DerivationResult(
                    success=False,
                    field_name=field_name,
                    source="audit_logs",
                    rule=rule.raw_rule,
                    message=f"No audit logs found for {object_type}/{object_id}"
                )
            
            if rule.limit == 1:
                value = records[0].get(rule.select_field)
            else:
                value = [r.get(rule.select_field) for r in records]
            
            return DerivationResult(
                success=True,
                field_name=field_name,
                value=value,
                source="audit_logs",
                rule=rule.raw_rule,
                message=f"Derived from {len(records)} audit log(s)"
            )
            
        except Exception as e:
            logger.error("DerivationExecutor failed to derive from audit_logs: %s - %s",
                        object_type, str(e))
            return DerivationResult(
                success=False,
                field_name=field_name,
                source="audit_logs",
                rule=rule.raw_rule,
                message=f"Error: {str(e)}"
            )
    
    def _derive_user_name(
        self,
        object_type: str,
        object_id: Any,
        field_name: str,
        rule: DerivationRule
    ) -> DerivationResult:
        """
        派生 created_by/updated_by 字段
        
        专门处理用户名字段的派生，支持：
        - created_by: 查询 action = 'CREATE' 的记录
        - updated_by: 查询 action IN ('CREATE', 'UPDATE') 的最新记录
        
        Args:
            object_type: 对象类型
            object_id: 对象ID
            field_name: 字段名（created_by 或 updated_by）
            rule: 派生规则
            
        Returns:
            DerivationResult 派生结果
        """
        try:
            filters = {
                "object_type": object_type,
                "object_id": object_id,
            }
            
            if rule.where_clause:
                where_filters = self._parse_where_clause(rule.where_clause)
                filters.update(where_filters)
            else:
                if field_name == "created_by":
                    filters["action"] = "CREATE"
                elif field_name == "updated_by":
                    pass
            
            order_by = rule.order_by if rule.order_by else "created_at DESC"
            records = self.ds.find(
                self.AUDIT_TABLE,
                filters=filters,
                order_by=order_by,
                limit=rule.limit
            )
            
            if not records:
                return DerivationResult(
                    success=False,
                    field_name=field_name,
                    source="audit_logs",
                    rule=rule.raw_rule,
                    message=f"No audit logs found for {field_name}"
                )
            
            user_name = records[0].get("user_name", "")
            
            return DerivationResult(
                success=True,
                field_name=field_name,
                value=user_name,
                source="audit_logs",
                rule=rule.raw_rule,
                message=f"Derived user_name: {user_name}"
            )
            
        except Exception as e:
            logger.error("DerivationExecutor failed to derive user_name: %s - %s",
                        field_name, str(e))
            return DerivationResult(
                success=False,
                field_name=field_name,
                source="audit_logs",
                rule=rule.raw_rule,
                message=f"Error: {str(e)}"
            )
    
    def derive_batch(
        self,
        object_type: str,
        object_ids: List[Any],
        field_names: List[str],
        derivation_rules: Dict[str, str],
        use_cache: bool = True
    ) -> Dict[str, Dict[str, DerivationResult]]:
        """
        批量派生字段（性能优化）
        
        通过一次查询获取多个对象、多个字段的派生值，减少数据库查询次数。
        
        Args:
            object_type: 对象类型
            object_ids: 对象ID列表
            field_names: 字段名列表
            derivation_rules: 字段派生规则映射 {field_name: rule}
            use_cache: 是否使用缓存
            
        Returns:
            Dict[str, Dict[str, DerivationResult]] 结果映射 {object_id: {field_name: result}}
        """
        if not self.ds:
            results = {}
            for obj_id in object_ids:
                results[str(obj_id)] = {}
                for field_name in field_names:
                    results[str(obj_id)][field_name] = DerivationResult(
                        success=False,
                        field_name=field_name,
                        message="No data source configured"
                    )
            return results
        
        results = {}
        for obj_id in object_ids:
            results[str(obj_id)] = {}
        
        uncached_queries = {}
        
        if use_cache and self._cache_enabled:
            for obj_id in object_ids:
                for field_name in field_names:
                    cache_key = self._build_cache_key(object_type, obj_id, field_name)
                    if cache_key in self._cache:
                        cached = self._cache[cache_key]
                        if self._is_cache_valid(cached):
                            results[str(obj_id)][field_name] = DerivationResult(
                                success=True,
                                field_name=field_name,
                                value=cached["value"],
                                source="cache",
                                rule=derivation_rules.get(field_name, ""),
                                message="Retrieved from cache"
                            )
                            continue
                    
                    if field_name not in uncached_queries:
                        uncached_queries[field_name] = []
                    uncached_queries[field_name].append(obj_id)
        else:
            for field_name in field_names:
                uncached_queries[field_name] = list(object_ids)
        
        for field_name, obj_ids in uncached_queries.items():
            if not obj_ids:
                continue
            
            rule_str = derivation_rules.get(field_name, "")
            if not rule_str:
                for obj_id in obj_ids:
                    results[str(obj_id)][field_name] = DerivationResult(
                        success=False,
                        field_name=field_name,
                        message="No derivation rule provided"
                    )
                continue
            
            rule = DerivationRuleParser.parse(rule_str)
            valid, msg = DerivationRuleParser.validate_rule(rule)
            if not valid:
                for obj_id in obj_ids:
                    results[str(obj_id)][field_name] = DerivationResult(
                        success=False,
                        field_name=field_name,
                        rule=rule_str,
                        message=f"Invalid rule: {msg}"
                    )
                continue
            
            batch_results = self._derive_batch_from_audit_logs(
                object_type=object_type,
                object_ids=obj_ids,
                field_name=field_name,
                rule=rule
            )
            
            for obj_id, result in batch_results.items():
                results[str(obj_id)][field_name] = result
                
                if use_cache and self._cache_enabled and result.success:
                    cache_key = self._build_cache_key(object_type, obj_id, field_name)
                    self._cache[cache_key] = {
                        "value": result.value,
                        "timestamp": datetime.now().timestamp()
                    }
        
        return results
    
    def _derive_batch_from_audit_logs(
        self,
        object_type: str,
        object_ids: List[Any],
        field_name: str,
        rule: DerivationRule
    ) -> Dict[str, DerivationResult]:
        """
        批量从 audit_logs 派生字段
        
        Args:
            object_type: 对象类型
            object_ids: 对象ID列表
            field_name: 字段名
            rule: 派生规则
            
        Returns:
            Dict[str, DerivationResult] 结果映射 {object_id: result}
        """
        results = {str(obj_id): DerivationResult(
            success=False,
            field_name=field_name,
            rule=rule.raw_rule
        ) for obj_id in object_ids}
        
        try:
            filters = {"object_type": object_type}
            
            if rule.where_clause:
                where_filters = self._parse_where_clause(rule.where_clause)
                filters.update(where_filters)
            
            all_records = self.ds.find(
                self.AUDIT_TABLE,
                filters=filters,
                order_by="created_at DESC"
            )
            
            object_records = {}
            for record in all_records:
                obj_id = record.get("object_id")
                if obj_id in object_ids:
                    if obj_id not in object_records:
                        object_records[obj_id] = []
                    object_records[obj_id].append(record)
            
            for obj_id in object_ids:
                records = object_records.get(obj_id, [])
                
                if not records:
                    results[str(obj_id)] = DerivationResult(
                        success=False,
                        field_name=field_name,
                        source="audit_logs",
                        rule=rule.raw_rule,
                        message=f"No audit logs found"
                    )
                    continue
                
                if rule.order_by:
                    reverse = "DESC" in rule.order_by.upper()
                    sort_field = rule.order_by.split()[0] if rule.order_by else "created_at"
                    records = sorted(
                        records,
                        key=lambda r: r.get(sort_field, ""),
                        reverse=reverse
                    )
                
                records = records[:rule.limit]
                
                if rule.limit == 1:
                    value = records[0].get(rule.select_field)
                else:
                    value = [r.get(rule.select_field) for r in records]
                
                results[str(obj_id)] = DerivationResult(
                    success=True,
                    field_name=field_name,
                    value=value,
                    source="audit_logs",
                    rule=rule.raw_rule,
                    message=f"Derived from {len(records)} audit log(s)"
                )
                
        except Exception as e:
            logger.error("DerivationExecutor batch derivation failed: %s - %s",
                        object_type, str(e))
            for obj_id in object_ids:
                results[str(obj_id)] = DerivationResult(
                    success=False,
                    field_name=field_name,
                    source="audit_logs",
                    rule=rule.raw_rule,
                    message=f"Error: {str(e)}"
                )
        
        return results
    
    def _parse_where_clause(self, where_clause: str) -> Dict[str, Any]:
        """
        解析 WHERE 子句为过滤器字典
        
        支持的格式：
        - "action = 'CREATE'"
        - "action IN ('CREATE', 'UPDATE')"
        - "user_id = 123"
        
        Args:
            where_clause: WHERE 子句字符串
            
        Returns:
            Dict[str, Any] 过滤器字典
        """
        filters = {}
        
        in_pattern = re.compile(r'(\w+)\s+IN\s*\(\s*(.+?)\s*\)', re.IGNORECASE)
        in_match = in_pattern.search(where_clause)
        if in_match:
            field = in_match.group(1)
            values_str = in_match.group(2)
            values = re.findall(r"'([^']+)'", values_str)
            if values:
                filters[field] = values
            return filters
        
        eq_pattern = re.compile(r"(\w+)\s*=\s*'([^']+)'", re.IGNORECASE)
        eq_matches = eq_pattern.findall(where_clause)
        for field, value in eq_matches:
            filters[field] = value
        
        eq_num_pattern = re.compile(r'(\w+)\s*=\s*(\d+)', re.IGNORECASE)
        eq_num_matches = eq_num_pattern.findall(where_clause)
        for field, value in eq_num_matches:
            filters[field] = int(value)
        
        return filters
    
    def _build_cache_key(self, object_type: str, object_id: Any, field_name: str) -> str:
        """构建缓存键"""
        return f"{object_type}:{object_id}:{field_name}"
    
    def _is_cache_valid(self, cached: Dict[str, Any]) -> bool:
        """检查缓存是否有效"""
        if not cached or "timestamp" not in cached:
            return False
        
        age = datetime.now().timestamp() - cached["timestamp"]
        return age < self._cache_ttl
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
    
    def enable_cache(self, ttl: int = 300):
        """
        启用缓存
        
        Args:
            ttl: 缓存有效期（秒）
        """
        self._cache_enabled = True
        self._cache_ttl = ttl
    
    def disable_cache(self):
        """禁用缓存"""
        self._cache_enabled = False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "enabled": self._cache_enabled,
            "ttl": self._cache_ttl,
            "size": len(self._cache),
            "keys": list(self._cache.keys())[:10],
        }
