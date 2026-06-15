# -*- coding: utf-8 -*-
"""
管理维度引擎

核心功能：
1. 从 hierarchies.yaml 和 permission_rule.yaml 加载维度定义
2. 计算权限影响范围（核心方法）
3. 实现向下继承和向上传播规则
4. 集成 EnumCacheManager 提供缓存能力

性能要求：
- 缓存命中 < 0.1ms
- 首次计算 < 100ms
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import yaml

from meta.core.enums.cache_manager import EnumCacheManager
from meta.services.condition_evaluator import ConditionEvaluator

logger = logging.getLogger(__name__)

# [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
# 新的层级链: product → version → domain → sub_domain (4层)
RESOURCE_TABLE_MAP = {
    'product': 'products',
    'version': 'versions',
    'domain': 'domains',
    'sub_domain': 'sub_domains',
    # [V1.1.8 2026-06-15] 重新加回 service_module / business_object / relationship 的表映射
    #   原因: dimension_scope_engine 的 _build_chain_condition 需要
    #   RESOURCE_TABLE_MAP 查这些 BO 的物理表名 (即使它们不参与 HIERARCHY_CHAIN 展开)
    #   旧版注释掉导致 chain 构造时 RESOURCE_TABLE_MAP.get('service_module') → None, 链式 SQL 失败
    'service_module': 'service_modules',
    'business_object': 'business_objects',
    'relationship': 'relationships',
}

CHILD_TYPE_MAP = {
    'product': ['version'],
    'version': ['domain'],
    'domain': ['sub_domain'],
    'sub_domain': [],  # 已移除 service_module 和 business_object
    # 'service_module': ['business_object'],  # 已移除
}

PARENT_FIELD_MAP = {
    'version': 'product_id',
    'domain': 'version_id',
    'sub_domain': 'domain_id',
    # 'service_module': 'sub_domain_id',  # 已移除
    # 'business_object': 'service_module_id',  # 已移除
}

DISPLAY_FIELD_MAP = {
    'product': 'name',
    'version': 'name',
    'domain': 'domain_name',
    'sub_domain': 'sub_domain_name',
    # 'service_module': 'module_name',  # 已移除
    # 'business_object': 'object_name',  # 已移除
}

CODE_FIELD_MAP = {
    'product': 'code',
    'version': 'code',
    'domain': 'code',
    'sub_domain': 'code',
    # 'service_module': 'code',  # 已移除
    # 'business_object': 'code',  # 已移除
}


class ManagementDimensionEngine:
    """
    管理维度引擎
    
    提供权限影响范围计算、维度定义加载、继承规则应用等核心功能。
    """
    
    def __init__(self, data_source, ttl_seconds: int = 300):
        """
        初始化管理维度引擎
        
        Args:
            data_source: 数据源对象
            ttl_seconds: 缓存TTL（秒），默认300秒
        """
        self.ds = data_source
        self.evaluator = ConditionEvaluator()
        self.cache = EnumCacheManager(ttl_seconds=ttl_seconds, max_size=500)
        
        self._dimension_metadata: Optional[Dict[str, Any]] = None
        self._schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
        
        logger.info(f"[OK] ManagementDimensionEngine 初始化完成 (TTL={ttl_seconds}s)")
    
    def _load_dimension_metadata(self) -> Dict[str, Any]:
        """
        从 hierarchies.yaml 和 permission_rule.yaml 加载维度定义
        
        Returns:
            维度元数据字典，包含：
            - dimensions: 维度列表
            - resource_types: 资源类型列表
            - hierarchies: 层级结构定义
        """
        cache_key = 'dimension_metadata'
        
        async def loader():
            metadata = {
                'dimensions': [],
                'resource_types': [],
                'hierarchies': {},
                'loaded_at': datetime.now(timezone.utc).isoformat()
            }
            
            hierarchies_path = os.path.join(self._schema_dir, 'hierarchies.yaml')
            if os.path.exists(hierarchies_path):
                with open(hierarchies_path, 'r', encoding='utf-8') as f:
                    hierarchies_data = yaml.safe_load(f)
                    if hierarchies_data:
                        metadata['dimensions'] = hierarchies_data.get('dimensions', [])
                        metadata['hierarchies'] = hierarchies_data.get('hierarchies', {})
            
            permission_rule_path = os.path.join(self._schema_dir, 'permission_rule.yaml')
            if os.path.exists(permission_rule_path):
                with open(permission_rule_path, 'r', encoding='utf-8') as f:
                    permission_data = yaml.safe_load(f)
                    if permission_data:
                        fields = permission_data.get('fields', [])
                        for field in fields:
                            if field.get('id') == 'resource_type':
                                description = field.get('description', '')
                                # [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
                                if 'domain/sub_domain' in description:
                                    metadata['resource_types'] = ['domain', 'sub_domain']
                                break
            
            if not metadata['resource_types']:
                # [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
                metadata['resource_types'] = ['domain', 'sub_domain']
            
            logger.info(f"[OK] 加载维度元数据: {len(metadata['dimensions'])} 个维度, {len(metadata['resource_types'])} 个资源类型")
            return metadata
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            metadata = self._load_dimension_metadata_sync()
        else:
            metadata = loop.run_until_complete(self.cache.get_or_load(cache_key, loader))
        
        return metadata
    
    def _load_dimension_metadata_sync(self) -> Dict[str, Any]:
        """
        同步加载维度元数据（用于异步环境不可用时）
        """
        metadata = {
            'dimensions': [],
            'resource_types': [],
            'hierarchies': {},
            'loaded_at': datetime.now(timezone.utc).isoformat()
        }
        
        hierarchies_path = os.path.join(self._schema_dir, 'hierarchies.yaml')
        if os.path.exists(hierarchies_path):
            with open(hierarchies_path, 'r', encoding='utf-8') as f:
                hierarchies_data = yaml.safe_load(f)
                if hierarchies_data:
                    metadata['dimensions'] = hierarchies_data.get('dimensions', [])
                    metadata['hierarchies'] = hierarchies_data.get('hierarchies', {})
        
        permission_rule_path = os.path.join(self._schema_dir, 'permission_rule.yaml')
        if os.path.exists(permission_rule_path):
            with open(permission_rule_path, 'r', encoding='utf-8') as f:
                permission_data = yaml.safe_load(f)
                if permission_data:
                    fields = permission_data.get('fields', [])
                    for field in fields:
                        if field.get('id') == 'resource_type':
                            description = field.get('description', '')
                            # [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
                            if 'domain/sub_domain' in description:
                                metadata['resource_types'] = ['domain', 'sub_domain']
                            break
        
        if not metadata['resource_types']:
            # [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
            metadata['resource_types'] = ['domain', 'sub_domain']
        
        return metadata
    
    def get_available_dimensions(self) -> List[Dict[str, Any]]:
        """
        获取可用管理维度列表
        
        Returns:
            维度列表，包含：
            - id: 维度ID
            - name: 维度名称
            - object: 对象类型
            - description: 描述
        """
        metadata = self._load_dimension_metadata()
        
        dimensions = []
        for dim in metadata.get('dimensions', []):
            dimensions.append({
                'id': dim.get('id'),
                'name': dim.get('name'),
                'object': dim.get('object'),
                'description': dim.get('description', ''),
                'hierarchy': dim.get('hierarchy'),
                'filter_param': dim.get('filter_param'),
            })
        
        return dimensions
    
    def calculate_impact(self, role_id: int) -> Dict[str, Any]:
        """
        计算权限影响范围（核心方法）
        
        Args:
            role_id: 角色ID
            
        Returns:
            影响范围结果，包含：
            - summary: 汇总信息
            - affected_objects: 受影响对象列表
            - calculation_meta: 计算元数据
        """
        start_time = time.perf_counter()
        cache_key = f"impact:role:{role_id}"
        
        async def loader():
            return self._calculate_impact_internal(role_id)
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            result = self._calculate_impact_internal(role_id)
            cache_hit = False
        else:
            result = loop.run_until_complete(self.cache.get_or_load(cache_key, loader))
            cache_hit = cache_key in self.cache
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        if 'calculation_meta' in result:
            result['calculation_meta']['performance_ms'] = round(elapsed_ms, 2)
            result['calculation_meta']['cache_hit'] = cache_hit
        
        logger.info(f"[OK] 计算权限影响范围 [role_id={role_id}]: {result['summary']['total_affected']} 个对象, 耗时 {elapsed_ms:.2f}ms")
        
        return result
    
    def _calculate_impact_internal(self, role_id: int) -> Dict[str, Any]:
        """
        内部方法：计算权限影响范围
        """
        rules = self._get_role_permission_rules(role_id)
        
        if not rules:
            return {
                'summary': {
                    'total_affected': 0,
                    'by_type': {}
                },
                'affected_objects': [],
                'calculation_meta': {
                    'calculated_at': datetime.now(timezone.utc).isoformat(),
                    'cache_hit': False,
                    'performance_ms': 0
                }
            }
        
        affected_objects = []
        by_type_count = {}
        
        for rule in rules:
            resource_type = rule.get('resource_type')
            condition = rule.get('condition')
            permission_level = rule.get('permission_level', 'read')
            inherit_to_children = rule.get('inherit_to_children', True)
            propagate_to_parents = rule.get('propagate_to_parents', True)
            is_denied = rule.get('is_denied', False)
            
            direct_objects = self._build_impact_query(condition, resource_type)
            
            for obj in direct_objects:
                obj['impact_type'] = 'direct_match'
                obj['permission_level'] = permission_level
                obj['is_denied'] = is_denied
                affected_objects.append(obj)
                
                obj_type = obj['object_type']
                by_type_count[obj_type] = by_type_count.get(obj_type, 0) + 1
            
            if inherit_to_children and not is_denied:
                inherited_objects = self._apply_inheritance_rules(
                    direct_objects, inherit_to_children=True, propagate_to_parents=False
                )
                for obj in inherited_objects:
                    if obj['object_id'] not in [o['object_id'] for o in affected_objects if o['object_type'] == obj['object_type']]:
                        obj['impact_type'] = 'inherit_to_children'
                        obj['permission_level'] = permission_level
                        obj['is_denied'] = False
                        affected_objects.append(obj)
                        
                        obj_type = obj['object_type']
                        by_type_count[obj_type] = by_type_count.get(obj_type, 0) + 1
            
            if propagate_to_parents and not is_denied:
                propagated_objects = self._apply_inheritance_rules(
                    direct_objects, inherit_to_children=False, propagate_to_parents=True
                )
                for obj in propagated_objects:
                    if obj['object_id'] not in [o['object_id'] for o in affected_objects if o['object_type'] == obj['object_type']]:
                        obj['impact_type'] = 'propagate_to_parents'
                        obj['permission_level'] = 'read'
                        obj['is_denied'] = False
                        affected_objects.append(obj)
                        
                        obj_type = obj['object_type']
                        by_type_count[obj_type] = by_type_count.get(obj_type, 0) + 1
        
        return {
            'summary': {
                'total_affected': len(affected_objects),
                'by_type': by_type_count
            },
            'affected_objects': affected_objects,
            'calculation_meta': {
                'calculated_at': datetime.now(timezone.utc).isoformat(),
                'cache_hit': False,
                'performance_ms': 0
            }
        }
    
    def _build_impact_query(self, condition: str, resource_type: str) -> List[Dict[str, Any]]:
        """
        基于 condition 构建影响范围查询
        
        Args:
            condition: 条件表达式
            resource_type: 资源类型
            
        Returns:
            匹配的对象列表
        """
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            logger.warning(f"未知的资源类型: {resource_type}")
            return []
        
        sql_where = self.evaluator.predicate_to_sql_where(condition)
        if not sql_where:
            return []
        
        display_field = DISPLAY_FIELD_MAP.get(resource_type, 'name')
        code_field = CODE_FIELD_MAP.get(resource_type, 'code')
        
        try:
            cursor = self.ds.execute(f"PRAGMA table_info({table_name})")
            columns = [r[1] for r in cursor.fetchall()]
        except Exception:
            columns = []
        
        if display_field not in columns:
            if 'name' in columns:
                display_field = 'name'
            elif code_field in columns:
                display_field = code_field
            else:
                display_field = 'id'
        
        if code_field not in columns:
            code_field = 'id'
        
        try:
            sql = f"""
                SELECT id, {code_field}, {display_field}
                FROM {table_name}
                WHERE {sql_where}
            """
            cursor = self.ds.execute(sql)
            
            objects = []
            for row in cursor.fetchall():
                objects.append({
                    'object_type': resource_type,
                    'object_id': row[0],
                    'object_code': str(row[1]) if row[1] else '',
                    'object_name': str(row[2]) if row[2] else '',
                })
            
            return objects
            
        except Exception as e:
            logger.error(f"查询影响范围失败 [{resource_type}]: {e}")
            return []
    
    def _apply_inheritance_rules(
        self,
        affected_objects: List[Dict[str, Any]],
        inherit_to_children: bool = False,
        propagate_to_parents: bool = False
    ) -> List[Dict[str, Any]]:
        """
        应用向下继承和向上传播规则
        
        Args:
            affected_objects: 受影响对象列表
            inherit_to_children: 是否向下继承
            propagate_to_parents: 是否向上传播
            
        Returns:
            继承/传播后的对象列表
        """
        result = []
        
        if inherit_to_children:
            for obj in affected_objects:
                children = self._get_all_children(obj['object_type'], obj['object_id'])
                result.extend(children)
        
        if propagate_to_parents:
            for obj in affected_objects:
                parents = self._get_all_parents(obj['object_type'], obj['object_id'])
                result.extend(parents)
        
        return result
    
    def _get_all_children(self, resource_type: str, resource_id: int) -> List[Dict[str, Any]]:
        """
        获取所有子对象（递归）
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            
        Returns:
            子对象列表
        """
        children = []
        child_types = CHILD_TYPE_MAP.get(resource_type, [])
        
        for child_type in child_types:
            child_table = RESOURCE_TABLE_MAP.get(child_type)
            if not child_table:
                continue
            
            parent_field = PARENT_FIELD_MAP.get(child_type)
            if not parent_field:
                continue
            
            display_field = DISPLAY_FIELD_MAP.get(child_type, 'name')
            code_field = CODE_FIELD_MAP.get(child_type, 'code')
            
            try:
                cursor = self.ds.execute(f"PRAGMA table_info({child_table})")
                columns = [r[1] for r in cursor.fetchall()]
            except Exception:
                columns = []
            
            if display_field not in columns:
                if 'name' in columns:
                    display_field = 'name'
                elif code_field in columns:
                    display_field = code_field
                else:
                    display_field = 'id'
            
            if code_field not in columns:
                code_field = 'id'
            
            try:
                sql = f"""
                    SELECT id, {code_field}, {display_field}
                    FROM {child_table}
                    WHERE {parent_field} = ?
                """
                cursor = self.ds.execute(sql, [resource_id])
                
                for row in cursor.fetchall():
                    children.append({
                        'object_type': child_type,
                        'object_id': row[0],
                        'object_code': str(row[1]) if row[1] else '',
                        'object_name': str(row[2]) if row[2] else '',
                    })
                
                for child in children[:]:
                    sub_children = self._get_all_children(child['object_type'], child['object_id'])
                    children.extend(sub_children)
                    
            except Exception as e:
                logger.error(f"获取子对象失败 [{child_type}]: {e}")
        
        return children
    
    def _get_all_parents(self, resource_type: str, resource_id: int) -> List[Dict[str, Any]]:
        """
        获取所有父对象（递归）
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            
        Returns:
            父对象列表
        """
        parents = []
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return parents
        
        parent_field = PARENT_FIELD_MAP.get(resource_type)
        if not parent_field:
            return parents
        
        parent_type = None
        for ptype, pfield in PARENT_FIELD_MAP.items():
            if ptype != resource_type and pfield == parent_field:
                continue
            if ptype == resource_type:
                continue
        
        for ptype, pfield in PARENT_FIELD_MAP.items():
            if ptype != resource_type:
                child_field = PARENT_FIELD_MAP.get(resource_type)
                if pfield == child_field:
                    continue
                if resource_type in CHILD_TYPE_MAP.get(ptype, []):
                    parent_type = ptype
                    break
        
        if not parent_type:
            for ptype, pfield in PARENT_FIELD_MAP.items():
                if ptype != resource_type and pfield != parent_field:
                    if resource_type in CHILD_TYPE_MAP.get(ptype, []):
                        parent_type = ptype
                        break
        
        if not parent_field or not parent_type:
            return parents
        
        try:
            cursor = self.ds.execute(
                f"SELECT {parent_field} FROM {table_name} WHERE id = ?",
                [resource_id]
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return parents
            
            parent_id = row[0]
            parent_table = RESOURCE_TABLE_MAP.get(parent_type)
            if not parent_table:
                return parents
            
            display_field = DISPLAY_FIELD_MAP.get(parent_type, 'name')
            code_field = CODE_FIELD_MAP.get(parent_type, 'code')
            
            try:
                cursor = self.ds.execute(f"PRAGMA table_info({parent_table})")
                columns = [r[1] for r in cursor.fetchall()]
            except Exception:
                columns = []
            
            if display_field not in columns:
                if 'name' in columns:
                    display_field = 'name'
                elif code_field in columns:
                    display_field = code_field
                else:
                    display_field = 'id'
            
            if code_field not in columns:
                code_field = 'id'
            
            sql = f"""
                SELECT id, {code_field}, {display_field}
                FROM {parent_table}
                WHERE id = ?
            """
            cursor = self.ds.execute(sql, [parent_id])
            parent_row = cursor.fetchone()
            
            if parent_row:
                parents.append({
                    'object_type': parent_type,
                    'object_id': parent_row[0],
                    'object_code': str(parent_row[1]) if parent_row[1] else '',
                    'object_name': str(parent_row[2]) if parent_row[2] else '',
                })
                
                grand_parents = self._get_all_parents(parent_type, parent_id)
                parents.extend(grand_parents)
                
        except Exception as e:
            logger.error(f"获取父对象失败 [{resource_type}]: {e}")
        
        return parents
    
    def _get_role_permission_rules(self, role_id: int) -> List[Dict[str, Any]]:
        """
        获取角色的权限规则
        
        Args:
            role_id: 角色ID
            
        Returns:
            权限规则列表
        """
        try:
            cursor = self.ds.execute(
                """SELECT rowid AS id, role_id, resource_type, condition, permission_level,
                          is_denied, inherit_to_children, propagate_to_parents, analysis_mode
                   FROM permission_rules
                   WHERE role_id = ?
                   ORDER BY is_denied DESC, rowid""",
                [role_id]
            )
            
            rules = []
            for row in cursor.fetchall():
                rule = {
                    'id': row[0],
                    'role_id': row[1],
                    'resource_type': row[2],
                    'condition': row[3],
                    'permission_level': row[4],
                    'is_denied': bool(row[5]),
                    'inherit_to_children': bool(row[6]),
                    'propagate_to_parents': bool(row[7]),
                    'analysis_mode': json.loads(row[8]) if row[8] else None,
                }
                rules.append(rule)
            
            return rules
            
        except Exception as e:
            logger.error(f"获取角色权限规则失败 [role_id={role_id}]: {e}")
            return []
    
    def invalidate_cache(self, role_id: Optional[int] = None):
        """
        失效缓存
        
        Args:
            role_id: 角色ID，如果为None则清空所有缓存
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if role_id:
            cache_key = f"impact:role:{role_id}"
            if loop.is_running():
                if cache_key in self.cache._l1_cache:
                    del self.cache._l1_cache[cache_key]
                    if self.cache.stats:
                        self.cache.stats.invalidations += 1
            else:
                loop.run_until_complete(self.cache.invalidate(cache_key))
            logger.info(f"[REFRESH] 缓存失效 [role_id={role_id}]")
        else:
            if loop.is_running():
                self.cache._l1_cache.clear()
                if self.cache.stats:
                    self.cache.stats.invalidations += 1
            else:
                loop.run_until_complete(self.cache.invalidate_all())
            logger.info("[SYMBOL] 清空所有缓存")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计信息
        """
        return self.cache.get_stats()
