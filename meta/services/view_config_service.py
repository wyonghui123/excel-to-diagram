# -*- coding: utf-8 -*-
"""
视图配置服务

提供运行时视图配置的获取、缓存和管理功能。
支持：
- 默认视图配置
- 多视图配置
- LRU 缓存 + TTL 过期
- 文件变更监控自动刷新
"""

import os
import time
import logging
from typing import Dict, Any, Optional, List
from functools import lru_cache
from pathlib import Path
from dataclasses import asdict

logger = logging.getLogger(__name__)

from meta.core.models import (
    MetaObject,
    UIViewConfig,
    UIListViewConfig,
    UIDetailViewConfig,
    UIFormViewConfig,
    registry,
)
from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir
from meta.core.ui_config.value_help_formatter import value_help_to_dict
from meta.services.action_policy import ActionPolicy, create_action_policy

DEV_MODE = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes') or os.environ.get('DEV_MODE', '').lower() in ('1', 'true', 'yes')


class ViewConfigCache:
    """视图配置缓存（LRU + TTL）"""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300, dev_mode: bool = False):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._timestamps: Dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._dev_mode = dev_mode
    
    def get(self, key: str) -> Optional[Any]:
        if self._dev_mode:
            return None
        if key not in self._cache:
            return None
        
        if time.time() - self._timestamps.get(key, 0) > self._ttl:
            del self._cache[key]
            del self._timestamps[key]
            return None
        
        return self._cache[key]
    
    def set(self, key: str, value: Any) -> None:
        if self._dev_mode:
            return
        if len(self._cache) >= self._max_size and key not in self._cache:
            oldest_key = min(self._timestamps, key=self._timestamps.get)
            del self._cache[oldest_key]
            del self._timestamps[oldest_key]
        
        self._cache[key] = value
        self._timestamps[key] = time.time()
    
    def invalidate(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            del self._timestamps[key]
            return True
        return False
    
    def clear(self) -> None:
        self._cache.clear()
        self._timestamps.clear()


class ViewConfigService:
    """
    视图配置服务
    
    提供视图配置的获取和管理功能。
    """
    
    _instance = None
    _cache: ViewConfigCache
    _file_timestamps: Dict[str, float] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = ViewConfigCache(dev_mode=DEV_MODE)
            cls._instance._file_timestamps = {}
        return cls._instance
    
    def get_view_config(self, object_type: str, view_name: Optional[str] = None) -> Optional[UIViewConfig]:
        """
        获取视图配置
        
        Args:
            object_type: 对象类型 ID
            view_name: 视图名称（可选，用于多视图支持）
            
        Returns:
            UIViewConfig 或 None
        """
        cache_key = f"{object_type}:{view_name or 'default'}"
        
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        meta_object = registry.get(object_type)
        if not meta_object:
            return None
        
        if view_name and view_name != 'default':
            config = meta_object.ui_view_configs.get(view_name)
        else:
            config = meta_object.ui_view_config
        
        if config:
            self._cache.set(cache_key, config)
        
        return config
    
    def get_list_view_config(self, object_type: str, view_name: Optional[str] = None) -> Optional[UIListViewConfig]:
        """
        获取列表视图配置
        
        Args:
            object_type: 对象类型 ID
            view_name: 视图名称（可选）
            
        Returns:
            UIListViewConfig 或 None
        """
        view_config = self.get_view_config(object_type, view_name)
        if view_config:
            return view_config.list
        return None
    
    def get_detail_view_config(self, object_type: str, view_name: Optional[str] = None) -> Optional[UIDetailViewConfig]:
        """
        获取详情视图配置
        
        Args:
            object_type: 对象类型 ID
            view_name: 视图名称（可选）
            
        Returns:
            UIDetailViewConfig 或 None
        """
        view_config = self.get_view_config(object_type, view_name)
        if view_config:
            return view_config.detail
        return None
    
    def get_form_view_config(self, object_type: str, view_name: Optional[str] = None) -> Optional[UIFormViewConfig]:
        """
        获取表单视图配置
        
        Args:
            object_type: 对象类型 ID
            view_name: 视图名称（可选）
            
        Returns:
            UIFormViewConfig 或 None
        """
        view_config = self.get_view_config(object_type, view_name)
        if view_config:
            return view_config.form
        return None
    
    def get_available_views(self, object_type: str) -> List[str]:
        """
        获取对象可用的视图名称列表
        
        Args:
            object_type: 对象类型 ID
            
        Returns:
            视图名称列表
        """
        meta_object = registry.get(object_type)
        if not meta_object:
            return []
        
        views = ["default"]
        views.extend(meta_object.ui_view_configs.keys())
        return views
    
    def build_list_view_from_fields(self, object_type: str) -> UIListViewConfig:
        """
        从字段定义构建列表视图配置
        
        当没有显式配置时，根据字段的 UI 注解自动生成。
        
        Args:
            object_type: 对象类型 ID
            
        Returns:
            UIListViewConfig
        """
        from meta.core.models import UIListViewColumn
        
        meta_object = registry.get(object_type)
        if not meta_object:
            return UIListViewConfig()
        
        columns = []
        position = 0
        
        for field in meta_object.fields:
            if field.ui.visible:
                # 获取 filter_type（从 semantics 中获取）
                semantics = getattr(field, 'semantics', None)
                field_filter_type = getattr(semantics, 'filter_type', 'text') if semantics else 'text'
                
                # 获取 enum_values 和 enum_type
                field_enum_values = getattr(field, 'enum_values', None) or []
                field_enum_type = getattr(field, 'enum_type', '') or ''
                
                column = UIListViewColumn(
                    key=field.id,
                    title=field.name,
                    width=field.ui.width,
                    position=field.ui.fieldGroupPosition if field.ui.fieldGroupPosition != 100 else position,
                    sortable=True,
                    i18n_key=field.ui.i18n_key,
                    field_type=field.field_type.value,
                    options=field.ui.options or [],
                    filter_type=field_filter_type,
                    enum_values=field_enum_values,
                    enum_type=field_enum_type,
                )
                columns.append(column)
                position += 1
        
        columns.sort(key=lambda c: c.position)
        
        # 根据import_export配置自动添加默认操作
        actions = []
        batch_actions = []
        
        # 新建操作（对于持久化对象）
        if meta_object.persistent:
            actions.append({
                'id': 'create',
                'label': '新建',
                'icon': 'plus',
                'type': 'primary',
                'position': 'toolbar'
            })
        
        # 导入操作
        if hasattr(meta_object, 'import_export') and meta_object.import_export:
            if meta_object.import_export.import_enabled:
                actions.append({
                    'id': 'import',
                    'label': '导入',
                    'icon': 'upload',
                    'type': 'default',
                    'position': 'toolbar'
                })
            
            # 导出操作
            if meta_object.import_export.export_enabled:
                actions.append({
                    'id': 'export',
                    'label': '导出',
                    'icon': 'download',
                    'type': 'default',
                    'position': 'toolbar'
                })
        
        # 批量删除（对于持久化对象）
        if meta_object.persistent:
            batch_actions.append({
                'id': 'batch_delete',
                'label': '批量删除',
                'icon': 'delete',
                'type': 'danger',
                'position': 'batch',
                'confirm': '确定要删除选中的记录吗？'
            })
        
        return UIListViewConfig(
            columns=columns,
            pageSize=20,
            selectable=True,
            actions=actions,
            batch_actions=batch_actions,
        )
    
    def build_detail_view_from_fields(self, object_type: str) -> UIDetailViewConfig:
        """
        从字段定义构建详情视图配置
        
        当没有显式配置时，根据字段的 fieldGroup 自动生成分区。
        
        Args:
            object_type: 对象类型 ID
            
        Returns:
            UIDetailViewConfig
        """
        from meta.core.models import UIDetailFacet
        
        meta_object = registry.get(object_type)
        if not meta_object:
            return UIDetailViewConfig()
        
        field_groups: Dict[str, List[str]] = {}
        
        for field in meta_object.fields:
            if field.ui.visible:
                group = field.ui.fieldGroup or "基本信息"
                if group not in field_groups:
                    field_groups[group] = []
                field_groups[group].append(field.id)
        
        facets = []
        for group_name, field_ids in field_groups.items():
            facet = UIDetailFacet(
                title=group_name,
                type="fieldGroup",
                fields=field_ids,
            )
            facets.append(facet)
        
        return UIDetailViewConfig(
            facets=facets,
            showChangeHistory=True,
            showRelations=True,
        )
    
    def build_form_view_from_fields(self, object_type: str) -> UIFormViewConfig:
        """
        从字段定义构建表单视图配置
        
        当没有显式配置时，根据字段的 fieldGroup 自动生成分区。
        
        Args:
            object_type: 对象类型 ID
            
        Returns:
            UIFormViewConfig
        """
        from meta.core.models import UIFormSection
        
        meta_object = registry.get(object_type)
        if not meta_object:
            return UIFormViewConfig()
        
        field_groups: Dict[str, List[str]] = {}
        
        for field in meta_object.fields:
            if field.ui.editable:
                group = field.ui.fieldGroup or "基本信息"
                if group not in field_groups:
                    field_groups[group] = []
                field_groups[group].append(field.id)
        
        sections = []
        for group_name, field_ids in field_groups.items():
            section = UIFormSection(
                title=group_name,
                fields=field_ids,
            )
            sections.append(section)
        
        return UIFormViewConfig(
            sections=sections,
            layout="vertical",
        )
    
    def get_or_build_view_config(self, object_type: str, view_name: Optional[str] = None) -> UIViewConfig:
        """
        获取或构建视图配置
        
        如果没有显式配置，则根据字段定义自动构建。
        
        Args:
            object_type: 对象类型 ID
            view_name: 视图名称（可选）
            
        Returns:
            UIViewConfig
        """
        config = self.get_view_config(object_type, view_name)
        
        if config and self._is_config_empty(config):
            config = UIViewConfig(
                list=self.build_list_view_from_fields(object_type),
                detail=self.build_detail_view_from_fields(object_type),
                form=self.build_form_view_from_fields(object_type),
            )
        elif not config:
            config = UIViewConfig(
                list=self.build_list_view_from_fields(object_type),
                detail=self.build_detail_view_from_fields(object_type),
                form=self.build_form_view_from_fields(object_type),
            )
        
        if config:
            if config.list:
                meta_object = registry.get(object_type)
                if meta_object:
                    self._merge_default_actions(config.list, meta_object)
            self._enrich_columns_with_field_meta(object_type, config)
        
        return config
    
    def _enrich_columns_with_field_meta(self, object_type: str, config):
        """
        用字段的 type、enum_values 等信息丰富视图配置
        
        单一事实原则：
        - 默认所有字段都可排序（除非显式声明 sortable: false）
        - 默认所有字段都可过滤（除非显式声明 filterable: false）
        - 默认所有字符串类型字段都可搜索
        """
        meta_object = registry.get(object_type)
        if not meta_object:
            return
        
        field_map = {f.id: f for f in meta_object.fields}
        
        if hasattr(config, 'list') and config.list:
            for col in config.list.columns:
                field = field_map.get(col.key)
                if field:
                    if not col.title:
                        col.title = field.name
                    col.field_type = field.field_type.value
                    if field.enum_values and not col.options:
                        col.options = self._convert_enum_values_to_options(field.enum_values)
                    
                    field_ui = getattr(field, 'ui', None)
                    if field_ui:
                        col.editable = getattr(field_ui, 'editable', True)
                        if not getattr(col, 'widget', None):
                            col.widget = getattr(field_ui, 'widget', '')
                        if not getattr(col, 'format', None):
                            col.format = getattr(field_ui, 'format', '')
                        if not col.options and getattr(field_ui, 'options', None):
                            col.options = field_ui.options
                    else:
                        col.editable = True
                    
                    field_value_help = getattr(field, 'value_help', None)
                    if field_value_help:
                        vh_source = getattr(field_value_help, 'source', None)
                        if vh_source:
                            enum_type_id = getattr(vh_source, 'enum_type_id', '')
                            if enum_type_id and not getattr(col, 'enum_type', None):
                                col.enum_type = enum_type_id
                    
                    # 自动识别系统字段，这些字段即使在新增行时也不可编辑
                    # 系统时间字段
                    field_id_lower = col.key.lower() if col.key else ''
                    system_fields = {
                        'created_at', 'updated_at', 'created_by', 'updated_by',
                        'created_date', 'updated_date', 'created_user', 'updated_user',
                        'is_system', 'system_flag', 'readonly'
                    }
                    if field_id_lower in system_fields:
                        col.editable = False
                        col.immutable = True
                    
                    # 添加字段级别的 immutable 信息（从 semantics 中提取）
                    semantics = getattr(field, 'semantics', None)
                    if semantics:
                        if isinstance(semantics, dict):
                            col.immutable = semantics.get('immutable', False)
                            col.business_key = semantics.get('business_key', False)
                        elif hasattr(semantics, 'immutable'):
                            col.immutable = semantics.immutable
                            col.business_key = getattr(semantics, 'business_key', False)
                        else:
                            col.immutable = False
                            col.business_key = False
                    else:
                        col.immutable = False
                        col.business_key = False
                    
                    if field_value_help:
                        # 如果 filter_type 是 'enum'，不设置 value_help_config
                        # enum 类型使用下拉选择，不需要 value_help
                        col_filter_type = getattr(col, 'filter_type', None)
                        if col_filter_type != 'enum':
                            col.value_help_config = self._serialize_value_help(field_value_help)
                            # 列表过滤用 value_help 时强制 multiple=True（支持多选过滤）
                            # 详情/表单的 value_help 由 ui-config 端点单独处理，不影响
                            if col.value_help_config and col.value_help_config.get('behavior'):
                                col.value_help_config['behavior']['multiple'] = True
                            # 如果当前 filter_type 是 'text' 且有 value_help，将 filter_type 设置为 'value_help'
                            if col_filter_type == 'text':
                                col.filter_type = 'value_help'
                    else:
                        # 如果没有 value_help，检查是否是 FK 字段
                        # FK 字段通过 ui.relation 或 related_object 属性识别
                        ui_relation = getattr(field.ui, 'relation', None) or getattr(field.ui, 'target_type', None)
                        related_object = getattr(field, 'related_object', None)
                        if ui_relation or related_object:
                            # 创建 value_help_config（使用标准格式）
                            target_type = ui_relation or related_object
                            col.value_help_config = {
                                'source': {
                                    'type': 'bo',
                                    'target_bo': target_type,
                                    'value_field': 'id',
                                    'display_field': 'name'
                                },
                                'behavior': {
                                    'multiple': True,
                                    'allow_clear': True
                                },
                                'presentation': {
                                    'result_type': 'dropdown'
                                }
                            }
                            col.filter_type = 'value_help'
                    
                    # 如果字段有 filter_type 设置（来自 semantics），覆盖列配置中的旧值
                    if semantics:
                        field_filter_type = getattr(semantics, 'filter_type', None)
                        if field_filter_type and field_filter_type != 'text':
                            col.filter_type = field_filter_type
                    
                    # 传递 enum_values（含 color，用于 Badge 渲染）
                    if field.enum_values and not col.enum_values:
                        col.enum_values = self._convert_enum_values_to_options(field.enum_values)
                        # 布尔字段的 enum_values value 统一转为整数，与 SQLite 数据库存储一致
                        if field.field_type.value == 'boolean':
                            for opt in col.enum_values:
                                raw_val = opt.get('value')
                                if isinstance(raw_val, bool):
                                    opt['value'] = 1 if raw_val else 0
                                elif isinstance(raw_val, str) and raw_val.lower() in ('true', 'false'):
                                    opt['value'] = 1 if raw_val.lower() == 'true' else 0
                    # 动态枚举引用（value_help.source.type=enum）：从数据库解析 enum_type 为 enum_values
                    if not col.enum_values and getattr(col, 'enum_type', ''):
                        resolved = self._resolve_enum_values_from_db(col.enum_type)
                        if resolved:
                            col.enum_values = resolved
                    # 布尔类型自动添加默认 enum_values（单一事实原则）
                    # 使用整数 1/0 作为 value，因为数据库存储的是整数
                    elif field.field_type.value == 'boolean' and not col.enum_values:
                        col.enum_values = [
                            {'value': 1, 'label': '是', 'color': 'success'},
                            {'value': 0, 'label': '否', 'color': 'info'}
                        ]
                
                # 处理列配置中的 target_type（转换为标准 value_help_config 格式）
                # 列配置可能直接指定 target_type 而非通过字段定义
                col_target_type = getattr(col, 'target_type', None)
                if col_target_type and not getattr(col, 'value_help_config', None):
                    col_filter_type = getattr(col, 'filter_type', None)
                    if col_filter_type == 'value_help':
                        display_field = getattr(col, 'display_field', 'name')
                        col.value_help_config = {
                            'source': {
                                'type': 'bo',
                                'target_bo': col_target_type,
                                'value_field': 'id',
                                'display_field': display_field
                            },
                            'behavior': {
                                'multiple': True,
                                'allow_clear': True
                            },
                            'presentation': {
                                'result_type': 'dropdown'
                            }
                        }
                
                # 单一事实原则：默认所有字段都可排序
                # 只有显式声明 sortable: false 才禁用
                if getattr(col, 'sortable', True) is None:
                    col.sortable = True
                
                # 单一事实原则：默认所有字段都可过滤
                # 只有显式声明 filterable: false 才禁用
                if getattr(col, 'filterable', True) is None:
                    col.filterable = True
            
            # 合并默认操作
            self._merge_default_actions(config.list, meta_object)
            
            # 合并 filter.filters 到 list.filters（YAML 中过滤器定义在 filter 下）
            if hasattr(config, 'filter') and config.filter:
                filter_config = config.filter
                if hasattr(filter_config, 'filters') and filter_config.filters:
                    if not hasattr(config.list, 'filters') or not config.list.filters:
                        config.list.filters = []
                    for f in filter_config.filters:
                        filter_dict = f if isinstance(f, dict) else asdict(f) if hasattr(f, '__dataclass_fields__') else vars(f)
                        normalized = {
                            'field': filter_dict.get('key') or filter_dict.get('field', ''),
                            'label': filter_dict.get('title') or filter_dict.get('label', ''),
                            'type': filter_dict.get('type', 'text'),
                            'options': filter_dict.get('options', []),
                            'position': filter_dict.get('position', 0),
                            'placeholder': filter_dict.get('placeholder', ''),
                            'default': filter_dict.get('default', ''),
                        }
                        config.list.filters.append(normalized)
                    if hasattr(filter_config, 'layout'):
                        config.list.filterLayout = filter_config.layout
            
            # 自动生成过滤器：从 columns 中 filterable != false 的字段继承
            self._auto_generate_filters(config.list, field_map)
            
            # 自动生成搜索字段：从字段类型推断（单一事实原则）
            self._auto_generate_search_fields(config.list, field_map)
            
            # 应用默认排序（单一事实原则）
            self._apply_default_sort(config.list, field_map)
            
            # 处理已存在的过滤器：自动填充 options（单一事实原则）
            if hasattr(config.list, 'filters') and config.list.filters:
                for filter_item in config.list.filters:
                    if isinstance(filter_item, dict):
                        field_id = filter_item.get('field', '')
                    else:
                        field_id = getattr(filter_item, 'field', '')
                    
                    field = field_map.get(field_id)
                    if not field:
                        continue
                    
                    # 如果过滤器已有 options，跳过
                    existing_options = filter_item.get('options', []) if isinstance(filter_item, dict) else getattr(filter_item, 'options', [])
                    if existing_options:
                        continue
                    
                    # 从字段的 enum_values 获取
                    if field.enum_values:
                        options = self._convert_enum_values_to_options(field.enum_values)
                        if isinstance(filter_item, dict):
                            filter_item['options'] = options
                        else:
                            filter_item.options = options
                        continue
                    
                    # boolean 字段自动生成 "是/否" 选项
                    # 使用整数值 1/0 与数据库存储一致
                    if field.field_type.value == 'boolean':
                        options = [
                            {'value': 1, 'label': '是', 'color': 'success'},
                            {'value': 0, 'label': '否', 'color': 'info'}
                        ]
                        if isinstance(filter_item, dict):
                            filter_item['options'] = options
                            if filter_item.get('type') == 'text' or not filter_item.get('type'):
                                filter_item['type'] = 'select'
                        else:
                            filter_item.options = options
                            if not getattr(filter_item, 'type', None) or filter_item.type == 'text':
                                filter_item.type = 'select'
        
        if hasattr(config, 'form') and config.form:
            if hasattr(config.form, 'fields') and config.form.fields:
                for field_id, field_config in config.form.fields.items():
                    if isinstance(field_config, dict):
                        field = field_map.get(field_id)
                        if field and field.enum_values:
                            if 'options' not in field_config:
                                field_config['options'] = self._convert_enum_values_to_options(field.enum_values)
    def _serialize_value_help(self, value_help):
        """序列化 value_help 配置为 dict（供前端 ValueHelpField 使用）
        
        委托给统一的 value_help_to_dict，确保所有序列化路径一致。
        """
        return value_help_to_dict(value_help)
    
    def _auto_generate_filters(self, list_config, field_map):
        """
        自动生成过滤器：从 columns 中 filterable != false 的字段继承
        
        单一事实原则：
        - 默认所有字段都可过滤（除非显式声明 filterable: false）
        - 过滤器定义来源于 columns 配置，无需重复定义
        """
        if not hasattr(list_config, 'columns'):
            return
        
        existing_filters = list_config.filters if hasattr(list_config, 'filters') else []
        existing_filter_fields = set()
        for f in existing_filters:
            if isinstance(f, dict):
                existing_filter_fields.add(f.get('field'))
            else:
                existing_filter_fields.add(getattr(f, 'field', None))
        
        auto_filters = []
        for col in list_config.columns:
            col_key = getattr(col, 'key', None) or getattr(col, 'field', None)
            if not col_key:
                continue
            
            # 单一事实原则：默认所有字段都可过滤，除非显式声明 filterable: false
            col_filterable = getattr(col, 'filterable', True)
            if col_filterable == False:
                continue
            
            if col_key in existing_filter_fields:
                continue
            
            field = field_map.get(col_key)
            col_title = getattr(col, 'title', None) or getattr(col, 'label', None) or col_key
            
            # 简化过滤器配置
            filter_config = {
                'field': col_key,
                'label': col_title,
                'type': 'text'
            }
            
            # 优先使用列配置中的 filter_type（单一事实原则）
            col_filter_type = getattr(col, 'filter_type', None)
            # 同时检查字段定义中的 filter_type（来自 semantics）
            if field and not col_filter_type:
                field_semantics = getattr(field, 'semantics', None)
                if field_semantics:
                    field_filter_type = getattr(field_semantics, 'filter_type', None)
                    if field_filter_type and field_filter_type != 'text':
                        col_filter_type = field_filter_type
            if col_filter_type:
                filter_config['type'] = col_filter_type
                # 如果列配置中有 value_help_config，使用它
                # 但如果 filter_type 是 'enum'，不设置 value_help（enum 类型使用下拉选择，不需要 value_help）
                col_value_help_config = getattr(col, 'value_help_config', None)
                if col_value_help_config and col_filter_type != 'enum':
                    filter_config['value_help'] = col_value_help_config
            elif field:
                # 优先检查 value_help 配置（FK 字段）
                field_value_help = getattr(field, 'value_help', None)
                if field_value_help:
                    filter_config['type'] = 'value_help'
                    filter_config['value_help'] = self._serialize_value_help(field_value_help)
                else:
                    field_type = field.field_type.value if hasattr(field, 'field_type') else 'string'
                    if field_type == 'datetime':
                        filter_config['type'] = 'date_range'
                    elif field_type in ['integer', 'number']:
                        filter_config['type'] = 'number_range'
                    elif hasattr(field, 'enum_values') and field.enum_values:
                        filter_config['type'] = 'select'
                        filter_config['options'] = self._convert_enum_values_to_options(field.enum_values)
                        # 布尔字段的 enum_values value 统一转为整数，与 SQLite 数据库存储一致
                        if field_type == 'boolean':
                            for opt in filter_config['options']:
                                raw_val = opt.get('value')
                                if isinstance(raw_val, bool):
                                    opt['value'] = 1 if raw_val else 0
                                elif isinstance(raw_val, str) and raw_val.lower() in ('true', 'false'):
                                    opt['value'] = 1 if raw_val.lower() == 'true' else 0
                    elif field_type == 'boolean':
                        filter_config['type'] = 'select'
                        filter_config['options'] = [
                            {'value': 1, 'label': '是', 'color': 'success'},
                            {'value': 0, 'label': '否', 'color': 'info'}
                        ]
                    else:
                        field_ui = getattr(field, 'ui', None)
                        if field_ui:
                            widget = getattr(field_ui, 'widget', '')
                            if widget in ('select', 'badge', 'tag', 'radio'):
                                filter_config['type'] = 'select'
                                ui_options = getattr(field_ui, 'options', None)
                                if ui_options and not filter_config.get('options'):
                                    filter_config['options'] = ui_options
            
            auto_filters.append(filter_config)
        
        # 直接设置过滤器列表
        list_config.filters = existing_filters + auto_filters
    
    def _auto_generate_search_fields(self, list_config, field_map):
        """
        自动生成搜索字段：从字段类型推断可搜索字段
        
        单一事实原则：默认所有字符串类型字段都可搜索，无需在 YAML 中重复声明
        """
        if hasattr(list_config, 'searchFields') and list_config.searchFields:
            return
        
        search_fields = []
        for col in getattr(list_config, 'columns', []):
            col_key = getattr(col, 'key', None) or getattr(col, 'field', None)
            if not col_key:
                continue
            
            field = field_map.get(col_key)
            if field:
                field_type = field.field_type.value if hasattr(field, 'field_type') else 'string'
                if field_type in ['string', 'text']:
                    search_fields.append(col_key)
        
        if search_fields:
            list_config.searchFields = search_fields
    
    def _apply_default_sort(self, list_config, field_map):
        """
        应用默认排序：如果没有指定 defaultSort，使用 updated_at 降序
        
        单一事实原则：默认排序逻辑统一处理，无需在每个 YAML 中重复配置
        """
        if hasattr(list_config, 'defaultSort') and list_config.defaultSort:
            return
        
        if 'updated_at' in field_map:
            list_config.defaultSort = {'field': 'updated_at', 'order': 'desc'}
        elif 'created_at' in field_map:
            list_config.defaultSort = {'field': 'created_at', 'order': 'desc'}
    
    def _create_filter_from_column(self, col, field):
        """
        根据列配置创建过滤器配置
        
        Args:
            col: 列配置
            field: 字段定义
            
        Returns:
            过滤器配置字典
        """
        col_key = getattr(col, 'key', None) or getattr(col, 'field', None)
        col_title = getattr(col, 'title', None) or getattr(col, 'label', None)
        filter_type = getattr(col, 'filter_type', None)
        
        filter_config = {
            'field': col_key,
            'label': col_title,
        }
        
        if filter_type:
            filter_config['type'] = filter_type
        elif field:
            field_type = field.field_type.value if hasattr(field, 'field_type') else 'string'
            if field_type == 'datetime':
                filter_config['type'] = 'date_range'
            elif field_type == 'integer' or field_type == 'number':
                filter_config['type'] = 'number_range'
            elif field.enum_values:
                filter_config['type'] = 'select'
                filter_config['options'] = self._convert_enum_values_to_options(field.enum_values)
            else:
                filter_config['type'] = 'text'
        else:
            filter_config['type'] = 'text'
        
        if field and field.enum_values:
            filter_config['options'] = self._convert_enum_values_to_options(field.enum_values)
        
        return filter_config
    
    def _merge_default_actions(self, list_config, meta_object):
        """合并默认操作到列表配置"""
        existing_action_ids = {action.get('id') for action in list_config.actions}
        default_actions = []
        
        # 使用 ActionPolicy 处理导入/导出按钮逻辑
        action_policy = create_action_policy(meta_object)
        
        # 新建按钮：持久化对象自动添加
        if meta_object.persistent and 'create' not in existing_action_ids:
            default_actions.append({
                'id': 'create',
                'label': '新建',
                'icon': 'plus',
                'type': 'primary',
                'position': 'toolbar'
            })
        
        # 导入按钮：只有有创建/更新操作时才添加
        if action_policy.should_show_import() and 'import' not in existing_action_ids:
            default_actions.append({
                'id': 'import',
                'label': '导入',
                'icon': 'upload',
                'type': 'default'
            })
        
        # 导出按钮：只要能读取数据就可以导出，不需要特殊权限
        if action_policy.should_show_export() and 'export' not in existing_action_ids:
            default_actions.append({
                'id': 'export',
                'label': '导出',
                'icon': 'download',
                'type': 'default'
            })
        
        # 将默认操作添加到现有操作列表
        if default_actions:
            list_config.actions = default_actions + list_config.actions
        
        # 根据 mutability 过滤操作
        list_config.actions = action_policy.filter_actions_by_mutability(list_config.actions)
        
        # 批量删除 - 持久化对象自动添加
        existing_batch_ids = {action.get('id') for action in list_config.batch_actions}
        if meta_object.persistent and 'batch_delete' not in existing_batch_ids:
            list_config.batch_actions.append({
                'id': 'batch_delete',
                'label': '批量删除',
                'icon': 'delete',
                'type': 'default',
                'confirm': '确定要删除选中的记录吗？'
            })
    
    def _convert_enum_values_to_options(self, enum_values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将字段的 enum_values 转换为选项列表"""
        options = []
        for enum_val in enum_values:
            option = {
                'value': enum_val.get('value', ''),
                'label': enum_val.get('label', enum_val.get('value', '')),
            }
            if 'color' in enum_val:
                option['color'] = enum_val['color']
            options.append(option)
        return options
    
    def _resolve_enum_values_from_db(self, enum_type_id: str) -> List[Dict[str, Any]]:
        """从数据库查询枚举值，支持动态枚举引用（value_help.source.type=enum）"""
        try:
            import os
            from meta.core.datasource import get_data_source
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
            ds = get_data_source("sqlite", database=db_path)
            sql = """
                SELECT code, name FROM enum_values
                WHERE enum_type_id = ? AND is_active = 1
                ORDER BY sort_order
            """
            rows = ds.query(sql, [enum_type_id])
            options = []
            for row in rows:
                options.append({
                    'value': row['code'],
                    'label': row['name'],
                })
            return options
        except Exception:
            return []

    def _is_config_empty(self, config: UIViewConfig) -> bool:
        """检查配置是否为空"""
        return (
            not config.list.columns and
            not config.detail.facets and
            not config.form.sections
        )
    
    def invalidate_cache(self, object_type: Optional[str] = None) -> None:
        """
        使缓存失效
        
        Args:
            object_type: 对象类型 ID（可选，不提供则清除所有）
        """
        if object_type:
            keys_to_remove = [
                k for k in self._cache._cache.keys()
                if k.startswith(f"{object_type}:")
            ]
            for key in keys_to_remove:
                self._cache.invalidate(key)
        else:
            self._cache.clear()
    
    def check_file_changes(self) -> List[str]:
        """
        检查文件变更
        
        Returns:
            变更的对象类型列表
        """
        schema_dir = Path(get_yaml_schema_dir())
        changed_objects = []
        
        for yaml_file in schema_dir.glob("*.yaml"):
            file_path = str(yaml_file)
            current_mtime = os.path.getmtime(file_path)
            
            if file_path in self._file_timestamps:
                if current_mtime > self._file_timestamps[file_path]:
                    changed_objects.append(yaml_file.stem)
            
            self._file_timestamps[file_path] = current_mtime
        
        return changed_objects
    
    def reload_if_changed(self) -> List[str]:
        """
        如果文件变更则重新加载
        
        Returns:
            重新加载的对象类型列表
        """
        changed = self.check_file_changes()
        
        for object_type in changed:
            self.invalidate_cache(object_type)
        
        return changed


view_config_service = ViewConfigService()
