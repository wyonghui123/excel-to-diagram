# -*- coding: utf-8 -*-
"""
层级过滤服务

基于 SAP One Model 原则：
1. 声明式数据模型 - 使用 hierarchies.yaml 配置
2. Association 语义 - 自动解析层级关系
3. Code-To-Data - 查询下沉到数据库层
"""

from typing import List, Dict, Any, Optional

from meta.core.models import registry as meta_registry, FieldStorage
from meta.services.query_service import QueryService, SearchRequest, QueryCondition
from meta.services.cascade_service import HierarchyConfigLoader
from meta.services.config_driven_hierarchy_filter import ConfigDrivenHierarchyFilterService


def _normalize_object_type(object_type: str) -> str:
    if meta_registry.get(object_type):
        return object_type
    if object_type.endswith('s') and len(object_type) > 1:
        singular = object_type[:-1]
        if meta_registry.get(singular):
            return singular
    if object_type.endswith('ies') and len(object_type) > 3:
        singular = object_type[:-3] + 'y'
        if meta_registry.get(singular):
            return singular
    return object_type


class HierarchyFilterService:
    """层级过滤服务 - 配置驱动实现"""

    def __init__(self, query_service: QueryService, data_source=None):
        self.query_service = query_service
        self.data_source = data_source
        self.config_loader = HierarchyConfigLoader
        self._config_driven = ConfigDrivenHierarchyFilterService(query_service, data_source)

    @property
    def HIERARCHY_ORDER(self):
        return self.config_loader.get_type_order()

    def resolve_conditions(self, object_type: str, args_dict: Dict[str, List[str]]) -> List[QueryCondition]:
        """解析过滤条件 - 配置驱动
        
        条件采纳原则：
        1. 当有更细粒度的 id 条件时，忽略更粗粒度的 parent_key 条件
        2. 例如：查询 sub_domain 时，有 sub_domain_id 条件则忽略 domain_id 条件
        """
        raw_conditions = []
        id_conditions = {}
        parent_key_field_conditions = {}
        
        normalized_type = _normalize_object_type(object_type)
        meta_obj = meta_registry.get(normalized_type)
        if not meta_obj:
            return raw_conditions
        
        current_level = self._get_hierarchy_level(normalized_type)
        
        for key, values in args_dict.items():
            if key in ('page', 'pageSize', 'page_size', 'keyword', 'order_by', 'sort_by', 'sort_order'):
                continue
            
            # 处理关键词搜索参数 _search 和 _search_fields
            # 注意：多个搜索字段使用 OR 逻辑组合
            if key == '_search':
                search_keyword = values[0] if values else ''
                search_fields_str = args_dict.get('_search_fields', [''])[0]
                if search_keyword and search_fields_str:
                    search_fields_list = search_fields_str.split(',')
                    for search_field in search_fields_list:
                        field = meta_obj.get_field(search_field.strip())
                        if field:
                            raw_conditions.append(QueryCondition(
                                field=search_field.strip(), 
                                operator='ilike', 
                                value=f'%{search_keyword}%',
                                combine_mode='or'  # 搜索条件使用 OR 组合
                            ))
                continue
            
            if key == '_search_fields':
                continue  # 已在 _search 中处理
            
            if key == 'relation_codes':
                valid_fields = set(f.id for f in meta_obj.fields)
                if 'relation_code' in valid_fields:
                    if len(values) > 1:
                        raw_conditions.append(QueryCondition(field='relation_code', operator='in', values=list(values)))
                    else:
                        raw_conditions.append(QueryCondition(field='relation_code', operator='eq', value=values[0]))
                continue
            
            if key == 'category_types':
                if len(values) > 1:
                    raw_conditions.append(QueryCondition(field='category', operator='in', values=list(values)))
                else:
                    raw_conditions.append(QueryCondition(field='category', operator='eq', value=values[0]))
                continue
            
            # 处理 key__like 格式（前端导出功能传递的模糊搜索参数）
            if key.endswith('__like'):
                actual_field = key[:-6]  # 移除 __like 后缀
                field = meta_obj.get_field(actual_field)
                if field:
                    like_value = values[0] if values else ''
                    if like_value and not like_value.startswith('%'):
                        like_value = f'%{like_value}%'
                    raw_conditions.append(QueryCondition(field=actual_field, operator='ilike', value=like_value))
                continue
            
            # 处理 key__in 格式（前端导出功能传递的多选参数）
            if key.endswith('__in'):
                actual_field = key[:-4]  # 移除 __in 后缀
                field = meta_obj.get_field(actual_field)
                if field:
                    if values and isinstance(values[0], str):
                        in_values = values[0].split(',')
                    else:
                        in_values = list(values)
                    if len(in_values) > 1:
                        raw_conditions.append(QueryCondition(field=actual_field, operator='in', values=in_values))
                    elif in_values:
                        raw_conditions.append(QueryCondition(field=actual_field, operator='eq', value=in_values[0]))
                continue
            
            # 处理 key_start 和 key_end 格式（前端日期范围选择器）
            if key.endswith('_start'):
                actual_field = key[:-6]  # 移除 _start 后缀
                field = meta_obj.get_field(actual_field)
                if field and values:
                    raw_conditions.append(QueryCondition(field=actual_field, operator='ge', value=values[0]))
                continue
            
            if key.endswith('_end'):
                actual_field = key[:-4]  # 移除 _end 后缀
                field = meta_obj.get_field(actual_field)
                if field and values:
                    raw_conditions.append(QueryCondition(field=actual_field, operator='le', value=values[0]))
                continue
            
            param_ids = [int(v) for v in values if v and str(v).lstrip('-').isdigit()]
            str_values = [v for v in values if v and not str(v).lstrip('-').isdigit()]
            
            field = meta_obj.get_field(key)
            is_virtual = field and (field.storage == FieldStorage.VIRTUAL or getattr(field.semantics, 'virtual', False))
            
            is_text_field = field and field.field_type.value in ('string', 'text')
            render_hints = getattr(field.ui, 'render_hints', None) if field and field.ui else None
            is_searchable = getattr(render_hints, 'searchable', False) if render_hints else False
            
            is_parent_key = field and getattr(field.semantics, 'parent_key', False)
            param_level = self._get_param_level(key)
            
            if field and not is_virtual:
                if is_parent_key and param_level is not None and param_level < current_level:
                    parent_key_field_conditions[key] = (param_ids, param_level)
                elif is_text_field and is_searchable and str_values:
                    raw_conditions.append(QueryCondition(field=key, operator='ilike', value=f'%{str_values[0]}%'))
                else:
                    if str_values:
                        if len(str_values) > 1:
                            raw_conditions.append(QueryCondition(field=key, operator='in', values=str_values))
                        else:
                            raw_conditions.append(QueryCondition(field=key, operator='eq', value=str_values[0]))
                    elif param_ids:
                        if len(param_ids) > 1:
                            raw_conditions.append(QueryCondition(field=key, operator='in', values=param_ids))
                        else:
                            raw_conditions.append(QueryCondition(field=key, operator='eq', value=param_ids[0]))
                continue
            
            if not param_ids:
                continue
            
            if is_parent_key:
                resolved_ids = self._resolve_hierarchy_param(normalized_type, key, param_ids)
                if resolved_ids:
                    if param_level is not None:
                        id_conditions[param_level] = resolved_ids
                    else:
                        if len(resolved_ids) > 1:
                            raw_conditions.append(QueryCondition(field='id', operator='in', values=resolved_ids))
                        else:
                            raw_conditions.append(QueryCondition(field='id', operator='eq', value=resolved_ids[0]))
                continue
            
            param_base_name = key.replace('_id', '')
            if param_base_name == normalized_type or param_base_name == object_type:
                if param_level is not None:
                    id_conditions[param_level] = param_ids
                else:
                    if len(param_ids) > 1:
                        raw_conditions.append(QueryCondition(field='id', operator='in', values=param_ids))
                    else:
                        raw_conditions.append(QueryCondition(field='id', operator='eq', value=param_ids[0]))
                continue
            
            resolved_ids = self._resolve_hierarchy_param(normalized_type, key, param_ids)
            if resolved_ids:
                if param_level is not None:
                    id_conditions[param_level] = resolved_ids
                else:
                    if len(resolved_ids) > 1:
                        raw_conditions.append(QueryCondition(field='id', operator='in', values=resolved_ids))
                    else:
                        raw_conditions.append(QueryCondition(field='id', operator='eq', value=resolved_ids[0]))
        
        has_finer_id_condition = any(lvl >= current_level for lvl in id_conditions.keys())

        if has_finer_id_condition:
            for level in sorted(id_conditions.keys(), reverse=True):
                if level >= current_level:
                    ids = id_conditions[level]
                    if len(ids) > 0:
                        raw_conditions.append(QueryCondition(field='id', operator='in', values=ids))
        else:
            for key, (ids, level) in sorted(parent_key_field_conditions.items(), key=lambda x: x[1][1], reverse=True):
                if len(ids) > 1:
                    raw_conditions.append(QueryCondition(field=key, operator='in', values=ids))
                else:
                    raw_conditions.append(QueryCondition(field=key, operator='eq', value=ids[0]))
            
            for level in sorted(id_conditions.keys(), reverse=True):
                ids = id_conditions[level]
                if len(ids) > 1:
                    raw_conditions.append(QueryCondition(field='id', operator='in', values=ids))
                else:
                    raw_conditions.append(QueryCondition(field='id', operator='eq', value=ids[0]))
        
        merged_conditions = []
        id_value_sets = {}
        
        for cond in raw_conditions:
            if cond.field == 'id' and cond.operator == 'in':
                if 'id' not in id_value_sets:
                    id_value_sets['id'] = set()
                id_value_sets['id'].update(cond.values)
            elif cond.field == 'id' and cond.operator == 'eq':
                if 'id' not in id_value_sets:
                    id_value_sets['id'] = set()
                id_value_sets['id'].add(cond.value)
            else:
                merged_conditions.append(cond)
        
        if 'id' in id_value_sets and id_value_sets['id']:
            merged_ids = list(id_value_sets['id'])
            if len(merged_ids) > 0:
                merged_conditions.append(QueryCondition(field='id', operator='in', values=merged_ids))
        
        return merged_conditions
    
    def _get_hierarchy_level(self, object_type: str) -> int:
        """获取对象在层级中的位置"""
        normalized = object_type.rstrip('s')
        for i, level in enumerate(self.HIERARCHY_ORDER):
            if level == normalized or level.rstrip('s') == normalized:
                return i
        return -1
    
    def _get_param_level(self, param_name: str) -> Optional[int]:
        """获取参数对应的层级"""
        base_name = param_name.replace('_id', '').rstrip('s')
        for i, level in enumerate(self.HIERARCHY_ORDER):
            if level == base_name or level.rstrip('s') == base_name:
                return i
        return None

    def _resolve_hierarchy_param(self, object_type: str, param_name: str, param_values: List[int]) -> List[int]:
        """解析层级参数 - 配置驱动
        
        根据参数名称自动判断是父级参数还是子级参数
        """
        # 检查是否是维度参数（如 domain_id, sub_domain_id）
        dimension_id = param_name.replace('_id', '')
        dimension = self.config_loader.get_dimension(dimension_id)
        
        if dimension:
            dim_object = dimension.get('object')
            
            # 如果参数对应的维度就是当前对象类型，直接返回
            if dim_object == object_type:
                return param_values
            
            # 构建层级链
            chain = self.config_loader.build_child_chain(dim_object, object_type)
            if chain and len(chain) > 1:
                # 父级参数，向下追溯
                return self._config_driven._traverse_down(chain, param_values)
            
            chain = self.config_loader.build_hierarchy_chain(dim_object, object_type)
            if chain and len(chain) > 1:
                # 子级参数，向上追溯
                return self._config_driven._traverse_up(chain, param_values)
        
        # 尝试作为子级参数处理（如 business_object_id）
        child_dimension = self.config_loader.get_dimension(param_name.replace('_id', ''))
        if child_dimension:
            child_type = child_dimension.get('object')
            chain = self.config_loader.build_hierarchy_chain(child_type, object_type)
            if chain and len(chain) > 1:
                return self._config_driven._traverse_up(chain, param_values)
        
        return []

    def resolve_filters(self, object_type: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """解析过滤参数 - 配置驱动"""
        resolved = {}
        
        if 'version_id' in filters:
            resolved['version_id'] = filters['version_id']
        
        if 'relation_codes' in filters:
            resolved['relation_codes'] = filters['relation_codes']
        
        # 使用配置驱动的解析
        config_resolved = self._config_driven.resolve_filter_params(object_type, filters)
        resolved.update(config_resolved)
        
        return resolved

    def get_hierarchy_chain(self, object_type: str) -> List[str]:
        """获取层级链 - 配置驱动"""
        levels = self.config_loader.get_levels()
        chain = []
        for level in levels:
            chain.append(level.get('object'))
        return chain

    def query_parent_ids(self, object_type: str, parent_field: str, ids: List[int]) -> List[int]:
        """查询父级 ID"""
        return self._config_driven._query_parent_ids(object_type, parent_field, ids)

    def _resolve_child_filter(self, object_type: str, filter_field: str, filter_values: List[int]) -> List[int]:
        """处理子级参数 - 使用配置驱动"""
        return self._resolve_hierarchy_param(object_type, filter_field, filter_values)

    def _get_parent_ids_from_child(self, child_type: str, parent_field: str, child_ids: List[int]) -> List[int]:
        """从子级获取父级 ID"""
        return self._config_driven._query_parent_ids(child_type, parent_field, child_ids)

    def get_bo_ids_by_domain_ids(self, domain_ids: List[int], version_id: int = None) -> List[int]:
        """获取领域下的业务对象 ID"""
        return self._config_driven.get_objects_by_dimension('domain', domain_ids, version_id)

    def get_bo_ids_by_sub_domain_ids(self, sub_domain_ids: List[int]) -> List[int]:
        """获取子领域下的业务对象 ID"""
        return self._config_driven.get_objects_by_dimension('sub_domain', sub_domain_ids, None)

    def get_bo_ids_by_service_module_ids(self, service_module_ids: List[int]) -> List[int]:
        """获取服务模块下的业务对象 ID"""
        return self._config_driven.get_objects_by_dimension('service_module', service_module_ids, None)
