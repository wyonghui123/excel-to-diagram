# -*- coding: utf-8 -*-
"""
ActionPolicy - 动作策略引擎

提供动作级别的策略处理，包括：
1. Action vs CRUD 关系处理
2. Import/Export 显示策略
3. 基于 mutability 的操作过滤
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


#: 动作可用性判定失败原因（B1-2 下沉，前端不再自行求值）
REASON_UNSUPPORTED = 'unsupported'
REASON_READONLY_OBJECT = 'readonly_object'
REASON_NO_PERMISSION = 'no_permission'
REASON_PRECONDITION_FALSE = 'precondition_false'


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
        
        if mutability == 'fullEditable':
            # fullEditable: 保留所有操作
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

    # ── [B1-2 2026-11-13] 动作可用性下沉评估 ──
    # 前端不再自行求值 permission / condition；统一由后端返回 enabled + reason。
    # 权限检查与条件评估通过 callable 注入，保持本模块纯逻辑、不依赖 DB。

    def evaluate_action(
        self,
        action,
        record=None,
        permission_checker: Optional[Callable[[str], bool]] = None,
        condition_evaluator: Optional[Callable[[str, Optional[Dict[str, Any]]], bool]] = None,
    ) -> 'ActionAvailability':
        """判定单个动作在当前记录下是否可用（fail-closed）。

        判定顺序：
        1. 缺少 id → unsupported
        2. 对象 locked 且动作属于写操作 → readonly_object
        3. 声明了 permission 但检查失败/检查器缺失 → no_permission
        4. 声明了 condition 但求值为 False/评估器缺失/抛异常 → precondition_false
        5. 其余 → enabled
        """
        action_id = _action_id(action)
        if not action_id:
            return ActionAvailability(enabled=False, reason=REASON_UNSUPPORTED)

        required_permission = _action_field(action, 'permission', '') or ''
        condition = _action_field(action, 'condition', '') or ''

        if self.is_readonly() and action_id in (
                self.CREATE_ACTIONS | self.UPDATE_ACTIONS | self.DELETE_ACTIONS):
            return ActionAvailability(
                enabled=False,
                reason=REASON_READONLY_OBJECT,
                required_permission=required_permission,
            )

        if required_permission:
            allowed = False
            if permission_checker is None:
                logger.warning(
                    '[action_policy] 未注入权限检查器，动作 %s 按 fail-closed 处理',
                    action_id)
            else:
                try:
                    allowed = bool(permission_checker(required_permission))
                except Exception as e:  # noqa: BLE001 - 检查器故障一律拒绝
                    logger.warning(
                        '[action_policy] 权限检查异常，动作 %s 按 fail-closed 处理: %s',
                        action_id, e)
                    allowed = False
            if not allowed:
                return ActionAvailability(
                    enabled=False,
                    reason=REASON_NO_PERMISSION,
                    required_permission=required_permission,
                )

        if condition:
            matched = False
            if condition_evaluator is None:
                logger.warning(
                    '[action_policy] 未注入条件评估器，动作 %s 按 fail-closed 处理',
                    action_id)
            else:
                try:
                    matched = bool(condition_evaluator(condition, record))
                except Exception as e:  # noqa: BLE001 - 评估器故障一律拒绝
                    logger.warning(
                        '[action_policy] 条件评估异常，动作 %s 按 fail-closed 处理: %s',
                        action_id, e)
                    matched = False
            if not matched:
                return ActionAvailability(
                    enabled=False,
                    reason=REASON_PRECONDITION_FALSE,
                    required_permission=required_permission,
                )

        return ActionAvailability(
            enabled=True, reason='', required_permission=required_permission)

    def evaluate_batch(
        self,
        ids: Optional[List[Any]] = None,
        actions: Optional[List[Any]] = None,
        permission_checker: Optional[Callable[[str], bool]] = None,
        condition_evaluator: Optional[Callable[[str, Optional[Dict[str, Any]]], bool]] = None,
        records: Optional[Any] = None,
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """批量判定动作可用性，返回 `{ [id]: { [action_id]: availability } }`。

        - `ids` 为空时使用 `'_object'` 桶（对象级动作，record=None）
        - `records` 支持 dict（按 str(key) 映射）或 list（与 ids 顺序对齐）
        """
        id_list = [str(i) for i in (ids or [])]
        if not id_list:
            id_list = [_OBJECT_BUCKET]

        record_map = _normalize_records(records, id_list)
        action_list = list(actions or [])

        result: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for obj_id in id_list:
            record = record_map.get(obj_id)
            bucket: Dict[str, Dict[str, Any]] = {}
            for action in action_list:
                aid = _action_id(action)
                if not aid:
                    continue
                availability = self.evaluate_action(
                    action,
                    record=record,
                    permission_checker=permission_checker,
                    condition_evaluator=condition_evaluator,
                )
                bucket[aid] = availability.to_dict()
            result[obj_id] = bucket
        return result


@dataclass
class ActionAvailability:
    """动作可用性判定结果"""
    enabled: bool
    reason: str = ''
    required_permission: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'reason': self.reason,
            'required_permission': self.required_permission,
        }


#: 无 ids 时的对象级动作桶键
_OBJECT_BUCKET = '_object'


def _action_id(action) -> str:
    """读取动作 id，兼容 dict / 对象两种结构。"""
    return str(_action_field(action, 'id', '') or '').strip().lower()


def _action_field(action, name: str, default=None):
    """读取动作字段，兼容 dict / 对象两种结构。"""
    if isinstance(action, dict):
        value = action.get(name, default)
    else:
        value = getattr(action, name, default)
    return default if value is None else value


def _normalize_records(records, id_list: List[str]) -> Dict[str, Any]:
    """把 records 归一为 `{ id: record }` 映射。"""
    if records is None:
        return {}
    if isinstance(records, dict):
        return {str(k): v for k, v in records.items()}
    if isinstance(records, (list, tuple)):
        return {
            obj_id: records[idx]
            for idx, obj_id in enumerate(id_list)
            if idx < len(records)
        }
    return {}


def create_action_policy(meta_object=None) -> ActionPolicy:
    """
    工厂函数：创建 ActionPolicy 实例
    
    Args:
        meta_object: 元数据对象
        
    Returns:
        ActionPolicy: ActionPolicy 实例
    """
    return ActionPolicy(meta_object)
