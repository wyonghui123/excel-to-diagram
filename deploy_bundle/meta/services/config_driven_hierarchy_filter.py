# -*- coding: utf-8 -*-
"""
配置驱动的层级过滤服务

基于 SAP One Model 原则：
1. 声明式数据模型 - 使用 hierarchies.yaml 配置
2. Association 语义 - 自动解析层级关系
3. Code-To-Data - 查询下沉到数据库层
"""

import yaml
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from meta.core.models import registry as meta_registry, FieldStorage
from meta.services.query_service import QueryService, SearchRequest, QueryCondition


class HierarchyConfigLoader:
    """层级配置加载器"""
    
    _instance = None
    _config = None
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        if cls._config is None:
            config_path = Path(__file__).parent.parent / 'schemas' / 'hierarchies.yaml'
            with open(config_path, 'r', encoding='utf-8') as f:
                cls._config = yaml.safe_load(f)
        return cls._config
    
    @classmethod
    def get_hierarchy(cls, hierarchy_id: str = 'biz_hierarchy') -> Dict[str, Any]:
        config = cls.get_config()
        for h in config.get('hierarchies', []):
            if h.get('id') == hierarchy_id:
                return h
        return {}
    
    @classmethod
    def get_levels(cls, hierarchy_id: str = 'biz_hierarchy') -> List[Dict[str, Any]]:
        hierarchy = cls.get_hierarchy(hierarchy_id)
        return hierarchy.get('levels', [])
    
    @classmethod
    def get_dimensions(cls) -> List[Dict[str, Any]]:
        config = cls.get_config()
        return config.get('dimensions', [])
    
    @classmethod
    def get_dimension(cls, dimension_id: str) -> Dict[str, Any]:
        for d in cls.get_dimensions():
            if d.get('id') == dimension_id:
                return d
        return {}
    
    @classmethod
    def get_api_mappings(cls) -> Dict[str, Any]:
        config = cls.get_config()
        return config.get('api_mappings', {})
    
    @classmethod
    def get_level_by_object(cls, object_type: str) -> Dict[str, Any]:
        levels = cls.get_levels()
        for level in levels:
            if level.get('object') == object_type:
                return level
        return {}
    
    @classmethod
    def get_association_filter_config(cls, object_type: str) -> Optional[Dict[str, Any]]:
        level = cls.get_level_by_object(object_type)
        if level.get('kind') != 'association':
            return None
        return level.get('association_filter_config')
    
    @classmethod
    def get_association_filter_levels(cls, object_type: str) -> List[Dict[str, Any]]:
        config = cls.get_association_filter_config(object_type)
        if not config:
            return []
        return config.get('hierarchy_filter_levels', [])
    
    @classmethod
    def get_parent_object(cls, object_type: str) -> Optional[str]:
        level = cls.get_level_by_object(object_type)
        return level.get('parent_object')
    
    @classmethod
    def get_child_objects(cls, object_type: str) -> List[str]:
        levels = cls.get_levels()
        children = []
        for level in levels:
            if level.get('parent_object') == object_type:
                children.append(level.get('object'))
        return children
    
    @classmethod
    def get_filter_param(cls, object_type: str) -> str:
        dimension = cls.get_dimension(object_type)
        return dimension.get('filter_param', 'id')
    
    @classmethod
    def get_ancestor_param(cls, object_type: str) -> Optional[str]:
        dimension = cls.get_dimension(object_type)
        return dimension.get('ancestor_param')
    
    @classmethod
    def build_hierarchy_chain(cls, from_type: str, to_type: str) -> List[str]:
        """构建从 from_type 到 to_type 的层级链
        
        例如：build_hierarchy_chain('business_object', 'domain')
        返回：['business_object', 'service_module', 'sub_domain', 'domain']
        """
        levels = cls.get_levels()
        
        # 构建对象到层级的映射
        object_to_level = {l.get('object'): l for l in levels}
        
        # 从 from_type 向上追溯到 to_type
        chain = [from_type]
        current = from_type
        
        while current != to_type:
            level = object_to_level.get(current, {})
            parent = level.get('parent_object')
            if not parent or parent == 'version':
                break
            chain.append(parent)
            current = parent
        
        return chain if current == to_type else []
    
    @classmethod
    def build_child_chain(cls, from_type: str, to_type: str) -> List[str]:
        """构建从 from_type 到 to_type 的子级链
        
        例如：build_child_chain('domain', 'business_object')
        返回：['domain', 'sub_domain', 'service_module', 'business_object']
        """
        levels = cls.get_levels()
        
        # 构建父级到子级的映射
        parent_to_children = {}
        for level in levels:
            parent = level.get('parent_object')
            child = level.get('object')
            if parent and parent != 'version':
                if parent not in parent_to_children:
                    parent_to_children[parent] = []
                parent_to_children[parent].append((level.get('level', 0), child))
        
        # 对每个父级的子级按 level 排序
        for parent in parent_to_children:
            parent_to_children[parent].sort(key=lambda x: x[0])
            parent_to_children[parent] = [c[1] for c in parent_to_children[parent]]
        
        print(f"[build_child_chain] parent_to_children={parent_to_children}")
        # 从 from_type 向下遍历到 to_type
        chain = [from_type]
        current = from_type
        
        while current != to_type:
            children = parent_to_children.get(current, [])
            if not children:
                break
            # 选择第一个子级（按层级顺序）
            next_child = None
            for child in children:
                chain.append(child)
                if child == to_type:
                    return chain
                next_child = child
                break
            if not next_child:
                break
            current = next_child
        
        return chain if current == to_type else []


class ConfigDrivenHierarchyFilterService:
    """配置驱动的层级过滤服务"""
    
    def __init__(self, query_service: QueryService, data_source=None):
        self.query_service = query_service
        self.data_source = data_source
        self.config_loader = HierarchyConfigLoader
    
    def resolve_filter_params(self, object_type: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """解析过滤参数
        
        根据 hierarchies.yaml 配置，将任意层级的过滤参数转换为当前对象的过滤条件
        
        与 resolve_conditions 保持一致的逻辑：
        1. 检查参数是否是当前对象的直接字段（非虚拟），直接用该字段过滤
        2. 如果参数名与当前对象类型匹配（如 service_module + service_module_id），用 id 过滤
        3. 如果是父级参数，向下追溯并用 id 过滤
        4. 如果是子级参数，向上追溯并用 id 过滤
        
        维度感知：只处理当前对象类型及其祖先层级的参数，忽略后代层级的参数
        这样可以避免"全选时空叶子节点被排除"的问题
        """
        from meta.core.models import registry as meta_registry, FieldStorage
        
        resolved = {}
        
        if 'version_id' in filters:
            resolved['version_id'] = filters['version_id']
        
        if 'relation_codes' in filters:
            resolved['relation_codes'] = filters['relation_codes']
        
        meta_obj = meta_registry.get(object_type)
        if not meta_obj:
            return resolved
        
        allowed_params = self._get_allowed_filter_params(object_type)
        
        for param_name, param_value in filters.items():
            if param_name in ('version_id', 'relation_codes'):
                continue
            
            if param_name not in allowed_params:
                continue
            
            field = meta_obj.get_field(param_name)
            is_virtual = field and (field.storage == FieldStorage.VIRTUAL or getattr(field.semantics, 'virtual', False))
            
            if field and not is_virtual:
                resolved[param_name] = param_value
                continue
            
            dimension_id = param_name.replace('_id', '')
            dimension = self.config_loader.get_dimension(dimension_id)
            
            if dimension:
                dim_object = dimension.get('object')
                
                if dim_object == object_type:
                    resolved['id'] = param_value
                    continue
                
                chain = self.config_loader.build_child_chain(dim_object, object_type)
                if chain and len(chain) > 1:
                    ids = self._traverse_down(chain, param_value)
                    if ids:
                        resolved['id'] = ids
                        continue
                
                chain = self.config_loader.build_hierarchy_chain(dim_object, object_type)
                if chain and len(chain) > 1:
                    ids = self._traverse_up(chain, param_value)
                    if ids:
                        resolved['id'] = ids
                        continue
        
        return resolved
    
    def _get_allowed_filter_params(self, object_type: str) -> set:
        """获取当前对象类型允许的过滤参数
        
        只允许当前对象类型及其祖先层级的参数，忽略后代层级的参数
        例如：domain 只允许 version_id 和 domain_id
              sub_domain 允许 version_id, domain_id, sub_domain_id
        """
        allowed = {'version_id', 'relation_codes'}
        
        levels = self.config_loader.get_levels()
        object_to_level = {l.get('object'): l.get('level', 0) for l in levels}
        
        current_level = object_to_level.get(object_type, 0)
        
        for level in levels:
            level_num = level.get('level', 0)
            if level_num <= current_level:
                obj = level.get('object')
                if obj:
                    allowed.add(obj + '_id')
        
        dimension = self.config_loader.get_dimension(object_type)
        if dimension:
            filter_param = dimension.get('filter_param')
            if filter_param:
                allowed.add(filter_param)
        
        return allowed

    def _traverse_down(self, chain: List[str], parent_ids: List[int], version_id: int = None) -> List[int]:
        """从父级向下追溯获取子级 ID

        例如：chain = ['domain', 'sub_domain', 'service_module']
        parent_ids = [1, 2]
        返回：domain 1 和 2 下的所有 service_module ID

        Args:
            chain: 层级链
            parent_ids: 父级 ID 列表
            version_id: 可选的版本 ID，用于过滤结果
        """
        current_ids = parent_ids if isinstance(parent_ids, list) else [parent_ids]
        print(f"[TraverseDown] chain={chain}, initial_ids={current_ids}, version_id={version_id}")

        for i in range(len(chain) - 1):
            parent_type = chain[i]
            child_type = chain[i + 1]

            child_level = self.config_loader.get_level_by_object(child_type)
            foreign_key = child_level.get('foreign_key_field')

            print(f"[TraverseDown] step {i}: parent={parent_type}, child={child_type}, fk={foreign_key}, ids={current_ids}")

            if not foreign_key:
                break

            current_ids = self._query_child_ids(child_type, foreign_key, current_ids, version_id)
            print(f"[TraverseDown] step {i} result: {current_ids}")
            if not current_ids:
                return []

        return current_ids
    
    def _traverse_up(self, chain: List[str], child_ids: List[int]) -> List[int]:
        """从子级向上追溯获取父级 ID
        
        例如：chain = ['business_object', 'service_module', 'sub_domain']
        child_ids = [1, 2]
        返回：business_object 1 和 2 所属的 sub_domain ID
        """
        current_ids = child_ids if isinstance(child_ids, list) else [child_ids]
        
        for i in range(len(chain) - 1):
            child_type = chain[i]
            parent_type = chain[i + 1]
            
            # 获取子级层级的配置
            child_level = self.config_loader.get_level_by_object(child_type)
            foreign_key = child_level.get('foreign_key_field')

            if not foreign_key:
                break

            current_ids = self._query_parent_ids(child_type, foreign_key, current_ids)
            if not current_ids:
                return []

        return current_ids

    def _query_child_ids(self, child_type: str, foreign_key: str, parent_ids: List[int], version_id: int = None) -> List[int]:
        """查询子级对象 ID

        Args:
            child_type: 子级对象类型
            foreign_key: 外键字段名
            parent_ids: 父级 ID 列表
            version_id: 可选的版本 ID，用于过滤结果
        """
        if not parent_ids:
            return []

        conditions = [QueryCondition(field=foreign_key, operator='in', values=parent_ids)]
        if version_id is not None:
            conditions.append(QueryCondition(field='version_id', operator='eq', value=version_id))

        search_req = SearchRequest(
            object_type=child_type,
            conditions=conditions,
            page=1,
            page_size=100000,
        )

        result = self.query_service.search(search_req)
        child_ids = [r.get('id') for r in (result.data or []) if r.get('id')]
        print(f"[_query_child_ids] object_type={child_type}, fk={foreign_key}, parent_ids={parent_ids}, version_id={version_id}, result_count={len(child_ids)}, ids={child_ids}")
        return child_ids
    
    def _query_parent_ids(self, child_type: str, foreign_key: str, child_ids: List[int]) -> List[int]:
        """查询父级对象 ID"""
        if not child_ids:
            return []
        
        conditions = [QueryCondition(field='id', operator='in', values=child_ids)]
        search_req = SearchRequest(
            object_type=child_type,
            conditions=conditions,
            page=1,
            page_size=100000,
        )
        
        result = self.query_service.search(search_req)
        parent_ids = set()
        for r in (result.data or []):
            parent_id = r.get(foreign_key)
            if parent_id:
                parent_ids.add(parent_id)
        
        return list(parent_ids)
    
    def get_objects_by_dimension(self, dimension_id: str, filter_ids: List[int], version_id: int = None) -> List[int]:
        """获取指定维度下的对象 ID

        例如：get_objects_by_dimension('domain', [1, 2], version_id=2)
        返回：domain 1 和 2 下的所有 business_object ID（限制为 version 2）

        Args:
            dimension_id: 维度 ID（如 'domain', 'sub_domain', 'service_module'）
            filter_ids: 过滤的 ID 列表
            version_id: 可选的版本 ID，用于过滤结果
        """
        dimension = self.config_loader.get_dimension(dimension_id)
        if not dimension:
            return []

        object_type = dimension.get('object')

        # 获取最底层的对象类型
        levels = self.config_loader.get_levels()
        if not levels:
            return filter_ids

        bottom_type = levels[-1].get('object')

        # 构建从当前维度到底层对象的链
        chain = self.config_loader.build_child_chain(object_type, bottom_type)
        print(f"[get_objects_by_dimension] dimension={dimension_id}, object_type={object_type}, bottom_type={bottom_type}, chain={chain}")
        if not chain:
            print(f"[get_objects_by_dimension] No chain found for {dimension_id} -> {bottom_type}, returning empty list (avoiding wrong ID fallback)")
            return []

        return self._traverse_down(chain, filter_ids, version_id)
