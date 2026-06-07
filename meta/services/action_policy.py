# -*- coding: utf-8 -*-
"""
ActionPolicy - 动作策略引擎

提供动作级别的策略处理，包括：
1. Action vs CRUD 关系处理
2. Import/Export 显示策略
3. 基于 mutability 的操作过滤
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field


@dataclass
class ActionDefinition:
    """动作定义"""
    id: str
    label: str = None
    icon: str = None
    type: str = 'default'  # default | primary | danger
    position: str = None  # toolbar | batch | row
    confirm: str = None


@dataclass
class ActionPolicyConfig:
    """动作策略配置"""
    create_actions: List[str] = field(default_factory=list)
    update_actions: List[str] = field(default_factory=list)
    delete_actions: List[str] = field(default_factory=list)
    readonly_actions: List[str] = field(default_factory=list)


class ActionPolicy:
    """动作策略引擎"""
    
    # CRUD 操作标识
    CREATE_ACTIONS = {'create', 'new', 'add'}
    UPDATE_ACTIONS = {'edit', 'update', 'modify'}
    DELETE_ACTIONS = {'delete', 'remove', 'drop'}
    READ_ACTIONS = {'read', 'view', 'detail', 'detail'}
    
    # 动作类型映射
    ACTION_TYPES = {
        'create': 'create',
        'new': 'create',
        'add': 'create',
        'edit': 'update',
        'update': 'update',
        'modify': 'update',
        'delete': 'delete',
        'remove': 'delete',
        'drop': 'delete',
    }
    
    def __init__(self, meta_object=None):
        self.meta_object = meta_object
        self._existing_actions: Set[str] = set()
        self._import_export_enabled = False
        
        if meta_object:
            self._load_from_meta_object()
    
    def _load_from_meta_object(self):
        """从元数据对象加载配置"""
        if not self.meta_object:
            return
        
        # 加载现有操作 - 支持两种路径
        # 路径1: meta.ui_view_config.list.actions (实际结构)
        # 路径2: meta.list_config.actions (测试 Mock 结构)
        actions = []
        
        # 尝试路径1: ui_view_config.list
        ui_view_config = getattr(self.meta_object, 'ui_view_config', None)
        if ui_view_config:
            list_config = getattr(ui_view_config, 'list', None)
            if list_config:
                raw_actions = getattr(list_config, 'actions', None)
                if isinstance(raw_actions, list):
                    actions = raw_actions
        
        # 如果路径1为空，尝试路径2: list_config
        if not actions:
            list_config = getattr(self.meta_object, 'list_config', None)
            if list_config:
                raw_actions = getattr(list_config, 'actions', None)
                if isinstance(raw_actions, list):
                    actions = raw_actions
        
        for action in actions:
            action_id = action.get('id', '')
            self._existing_actions.add(action_id.lower())
        
        # 加载 import/export 配置
        import_export = getattr(self.meta_object, 'import_export', None)
        if import_export:
            self._import_export_enabled = True
    
    def has_crud_action(self, action_type: str = 'create') -> bool:
        """
        检查是否存在指定类型的 CRUD 操作
        
        Args:
            action_type: 操作类型 ('create', 'update', 'delete')
            
        Returns:
            bool: 是否存在该类型的操作
        """
        action_set = self._get_action_set(action_type)
        return bool(self._existing_actions & action_set)
    
    def _get_action_set(self, action_type: str) -> Set[str]:
        """获取指定类型的动作集合"""
        if action_type == 'create':
            return self.CREATE_ACTIONS
        elif action_type == 'update':
            return self.UPDATE_ACTIONS
        elif action_type == 'delete':
            return self.DELETE_ACTIONS
        return set()
    
    def should_show_action(self, action_id: str) -> bool:
        """
        判断是否应该显示指定动作
        
        Args:
            action_id: 动作标识
            
        Returns:
            bool: 是否显示
        """
        if not action_id:
            return False
        
        action_id_lower = action_id.lower()
        
        # 读取操作始终显示
        if action_id_lower in self.READ_ACTIONS:
            return True
        
        # CRUD 操作需要根据 mutability 判断
        return True
    
    def should_show_import(self) -> bool:
        """
        判断是否应该显示导入按钮
        
        导入需要创建权限，只在有 CRUD 操作时显示。
        
        Returns:
            bool: 是否显示
        """
        if not self._import_export_enabled:
            return False
        
        # 需要有创建操作
        return self.has_crud_action('create')
    
    def should_show_export(self) -> bool:
        """
        判断是否应该显示导出按钮
        
        导出只需要读取权限，始终显示（如果启用）。
        
        Returns:
            bool: 是否显示
        """
        return self._import_export_enabled
    
    def should_show_create(self) -> bool:
        """
        判断是否应该显示新建按钮
        
        Returns:
            bool: 是否显示
        """
        return self.has_crud_action('create')
    
    def should_show_edit(self) -> bool:
        """
        判断是否应该显示编辑按钮
        
        Returns:
            bool: 是否显示
        """
        return self.has_crud_action('update')
    
    def should_show_delete(self) -> bool:
        """
        判断是否应该显示删除按钮
        
        Returns:
            bool: 是否显示
        """
        return self.has_crud_action('delete')
    
    def get_allowed_actions(self) -> List[str]:
        """
        获取允许的动作列表
        
        基于 mutability 过滤动作。
        
        Returns:
            List[str]: 允许的动作标识列表
        """
        mutability = self._get_mutability()
        
        if mutability == 'locked':
            # locked: 只允许读取和导出
            return ['read', 'view', 'export', 'detail']
        
        # 其他情况返回现有动作
        return list(self._existing_actions)
    
    def _get_mutability(self) -> Optional[str]:
        """获取对象的 mutability 配置"""
        if not self.meta_object:
            return None
        
        semantics = getattr(self.meta_object, 'semantics', None)
        if not semantics:
            return None
        
        if isinstance(semantics, dict):
            return semantics.get('mutability')
        
        return getattr(semantics, 'mutability', None)
    
    def filter_actions_by_mutability(
        self, 
        actions: List[Dict]
    ) -> List[Dict]:
        """
        根据 mutability 过滤动作列表
        
        Args:
            actions: 原始动作列表
            
        Returns:
            List[Dict]: 过滤后的动作列表
        """
        mutability = self._get_mutability()
        
        if mutability == 'locked':
            # locked: 移除所有写入操作
            write_actions = self.CREATE_ACTIONS | self.UPDATE_ACTIONS | self.DELETE_ACTIONS
            return [
                a for a in actions 
                if a.get('id', '').lower() not in write_actions
            ]
        
        if mutability == 'extensible':
            # extensible: 保留所有操作
            return actions
        
        if mutability == 'fully_editable':
            # fully_editable: 保留所有操作
            return actions
        
        return actions
    
    def get_default_actions(self) -> List[ActionDefinition]:
        """
        获取默认动作列表
        
        基于 import_export 配置和 CRUD 操作生成默认动作。
        
        Returns:
            List[ActionDefinition]: 默认动作列表
        """
        actions = []
        
        # 导入按钮（需要创建权限）
        if self.should_show_import():
            actions.append(ActionDefinition(
                id='import',
                label='导入',
                icon='upload',
                type='default'
            ))
        
        # 导出按钮（只需要读取权限）
        if self.should_show_export():
            actions.append(ActionDefinition(
                id='export',
                label='导出',
                icon='download',
                type='default'
            ))
        
        return actions
    
    def is_readonly(self) -> bool:
        """
        判断对象是否只读
        
        Returns:
            bool: 是否只读
        """
        mutability = self._get_mutability()
        return mutability == 'locked'


def create_action_policy(meta_object=None) -> ActionPolicy:
    """
    工厂函数：创建 ActionPolicy 实例
    
    Args:
        meta_object: 元数据对象
        
    Returns:
        ActionPolicy: ActionPolicy 实例
    """
    return ActionPolicy(meta_object)
