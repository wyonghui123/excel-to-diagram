# -*- coding: utf-8 -*-
"""
过滤条件构建服务
参考 SAP SADL 框架的自动过滤构建机制
"""

from typing import List, Dict, Optional, Literal, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class QueryCondition:
    """查询条件"""
    field: str
    operator: str
    value: Any
    logic: str = 'AND'


class FilterService:
    """
    过滤条件构建服务
    
    参考：
    - SAP SADL 框架
    - SAP CDS @Consumption.filter 注解
    - Salesforce System Dictionary
    - ServiceNow sys_dictionary
    """
    
    def build_filters_from_meta(
        self,
        meta_obj: Dict,
        params: Dict[str, str],
        scope: str = 'global'
    ) -> List[QueryCondition]:
        """
        从元模型定义和请求参数构建过滤条件
        
        Args:
            meta_obj: 元模型对象（包含fields定义）
            params: 请求参数（来自前端）
            scope: 过滤作用域（'global' 或 'local'）
        
        Returns:
            查询条件列表
        """
        conditions = []
        
        if not meta_obj or 'fields' not in meta_obj:
            return conditions
        
        for field in meta_obj['fields']:
            # 检查字段是否有语义定义
            if not isinstance(field, dict):
                continue
            
            semantics = field.get('semantics')
            if not semantics or not isinstance(semantics, dict):
                continue
            
            # 检查是否可过滤（@Consumption.filter）
            if not semantics.get('filterable', False):
                continue
            
            # 检查作用域
            filter_scope = semantics.get('filter_scope', 'both')
            if scope == 'global' and filter_scope == 'local':
                continue
            if scope == 'local' and filter_scope == 'global':
                continue
            
            # 根据过滤类型构建条件（selectionType）
            filter_type = semantics.get('filter_type', 'text')
            db_column = field.get('db_column', field.get('id', ''))
            field_id = field.get('id', '')
            
            try:
                if filter_type == 'date':
                    # 日期范围过滤（#INTERVAL）
                    conditions.extend(self._build_date_filter(field_id, db_column, params))
                
                elif filter_type == 'user':
                    # 用户模糊匹配
                    condition = self._build_user_filter(field_id, db_column, params, semantics)
                    if condition:
                        conditions.append(condition)
                
                elif filter_type == 'enum':
                    # 枚举精确匹配
                    condition = self._build_enum_filter(field_id, db_column, params)
                    if condition:
                        conditions.append(condition)
                
                elif filter_type == 'foreign_key':
                    # 外键关联过滤
                    condition = self._build_foreign_key_filter(field_id, db_column, params)
                    if condition:
                        conditions.append(condition)
                
                else:
                    # 文本模糊匹配（默认）
                    condition = self._build_text_filter(field_id, db_column, params, semantics)
                    if condition:
                        conditions.append(condition)
            
            except Exception as e:
                logger.error(f"Failed to build filter for field {field_id}: {e}")
                continue
        
        return conditions
    
    def _build_date_filter(
        self,
        field_id: str,
        db_column: str,
        params: Dict[str, str]
    ) -> List[QueryCondition]:
        """构建日期范围过滤条件"""
        conditions = []
        from_key = f"{field_id}_from"
        to_key = f"{field_id}_to"
        
        if from_key in params and params[from_key]:
            conditions.append(QueryCondition(
                field=db_column,
                operator='>=',
                value=params[from_key]
            ))
        
        if to_key in params and params[to_key]:
            conditions.append(QueryCondition(
                field=db_column,
                operator='<=',
                value=params[to_key]
            ))
        
        return conditions
    
    def _build_user_filter(
        self,
        field_id: str,
        db_column: str,
        params: Dict[str, str],
        semantics: Dict
    ) -> Optional[QueryCondition]:
        """构建用户过滤条件（模糊匹配）"""
        if field_id not in params or not params[field_id]:
            return None
        
        # 获取操作符（默认为like）
        operator = semantics.get('filter_operator', 'like')
        
        if operator == 'like':
            value = f"%{params[field_id]}%"
        else:
            value = params[field_id]
        
        return QueryCondition(
            field=db_column,
            operator=operator,
            value=value
        )
    
    def _build_enum_filter(
        self,
        field_id: str,
        db_column: str,
        params: Dict[str, str]
    ) -> Optional[QueryCondition]:
        """构建枚举过滤条件（精确匹配）"""
        if field_id not in params:
            return None
        value = params[field_id]
        if value is None or value == '':
            return None
        
        return QueryCondition(
            field=db_column,
            operator='eq',
            value=value
        )
    
    def _build_foreign_key_filter(
        self,
        field_id: str,
        db_column: str,
        params: Dict[str, str]
    ) -> Optional[QueryCondition]:
        """构建外键过滤条件"""
        if field_id not in params or not params[field_id]:
            return None
        
        # 尝试转换为整数
        try:
            value = int(params[field_id])
        except ValueError:
            value = params[field_id]
        
        return QueryCondition(
            field=db_column,
            operator='eq',
            value=value
        )
    
    def _build_text_filter(
        self,
        field_id: str,
        db_column: str,
        params: Dict[str, str],
        semantics: Dict
    ) -> Optional[QueryCondition]:
        """构建文本过滤条件"""
        if field_id not in params or not params[field_id]:
            return None
        
        # 获取操作符
        operator = semantics.get('filter_operator', 'like')
        
        if operator == 'like':
            value = f"%{params[field_id]}%"
        else:
            value = params[field_id]
        
        return QueryCondition(
            field=db_column,
            operator=operator,
            value=value
        )
    
    def conditions_to_sql(
        self,
        conditions: List[QueryCondition],
        logic: str = 'AND'
    ) -> tuple:
        """
        将查询条件转换为SQL片段和参数列表
        
        Args:
            conditions: 查询条件列表
            logic: 条件之间的逻辑关系（'AND' 或 'OR'）
        
        Returns:
            (where_clause, params) - SQL WHERE子句和参数列表
        """
        if not conditions:
            return '', []
        
        where_clauses = []
        params = []
        
        for cond in conditions:
            if cond.operator == 'in':
                # IN 查询
                values = cond.value if isinstance(cond.value, list) else [cond.value]
                placeholders = ', '.join(['?'] * len(values))
                where_clauses.append(f"{cond.field} IN ({placeholders})")
                params.extend(values)
            else:
                # 其他操作符
                where_clauses.append(f"{cond.field} {cond.operator} ?")
                params.append(cond.value)
        
        where_clause = f" {logic} ".join(where_clauses)
        
        return where_clause, params


# 全局实例
filter_service = FilterService()
