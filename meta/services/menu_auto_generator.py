# -*- coding: utf-8 -*-
"""
菜单自动生成引擎

从已注册的 BO 元数据自动推导菜单定义（含 bo_bindings 和 required_permissions）
并持久化到 menus 导航表

功能：
1. generate_object_list_menu(): 从单个 BO 生成列表页菜单
2. generate_multi_object_menu(): 从多个 BO 生成聚合页菜单
3. generate_all(): 批量生成所有 BO 的菜单
4. persist_to_db(): 持久化到数据库

设计原则：
- 菜单与 BO 通过 bo_bindings 声明关联
- required_permissions 从 bo_bindings 自动推导
- 支持 SAP PFCG 风格的菜单-权限联动
"""

import json
import logging
from typing import Dict, List, Optional
from pathlib import Path

from meta.core.models import MetaObject, registry

logger = logging.getLogger(__name__)

_MENU_LAST_MTIME = None


def _schema_mtime_changed() -> bool:
    """检查 meta/schemas/ 目录下是否有任何 .yaml 文件变更"""
    global _MENU_LAST_MTIME
    try:
        from meta.core.yaml_loader import get_yaml_schema_dir
        schema_dir = Path(get_yaml_schema_dir())
        if not schema_dir.exists():
            return True
        max_mtime = 0.0
        for yaml_file in schema_dir.glob("*.yaml"):
            try:
                mtime = yaml_file.stat().st_mtime
                if mtime > max_mtime:
                    max_mtime = mtime
            except Exception:
                pass
        if max_mtime == 0.0:
            return True
        if _MENU_LAST_MTIME is None or max_mtime > _MENU_LAST_MTIME:
            _MENU_LAST_MTIME = max_mtime
            return True
        return False
    except Exception:
        return True


def _mark_menu_synced():
    """标记菜单同步完成"""
    global _MENU_LAST_MTIME
    try:
        from meta.core.yaml_loader import get_yaml_schema_dir
        schema_dir = Path(get_yaml_schema_dir())
        if not schema_dir.exists():
            return
        max_mtime = max(
            (f.stat().st_mtime for f in schema_dir.glob("*.yaml") if f.exists()),
            default=0.0
        )
        if max_mtime > 0.0:
            _MENU_LAST_MTIME = max_mtime
    except Exception:
        pass


class MenuAutoGenerator:

    def generate_object_list_menu(self, meta_obj: MetaObject) -> Dict:
        """从单个 BO 生成列表页菜单
        
        自动生成：
        - bo_bindings: BO 绑定声明
        - required_permissions: 从 bo_bindings 推导的权限列表
        - data_permission_hint: 数据权限提示
        """
        menu_code = f"{meta_obj.id}-list"
        bo_bindings = self._derive_bo_bindings(meta_obj)
        required_permissions = self._derive_permissions_from_bindings(bo_bindings)
        page_config = self._extract_list_config(meta_obj)

        return {
            'menu_code': menu_code,
            'menu_name': f"{meta_obj.name}\u7ba1\u7406",
            'menu_path': f"/{meta_obj.id.replace('_', '-')}",
            'page_type': 'object_list',
            'primary_object_type': meta_obj.id,
            'object_types': [meta_obj.id],
            'bo_bindings': bo_bindings,
            'required_permissions': required_permissions,
            'required_any_permission': False,
            'data_permission_hint': {
                'resource_types': [meta_obj.id],
                'message': f"\u5efa\u8bae\u5206\u914d{meta_obj.name}\u6570\u636e\u6743\u9650"
            },
            'page_config': page_config,
            'auto_generated': True,
        }

    def generate_multi_object_menu(self, menu_code: str, menu_name: str,
                                    object_types: List[str], menu_path: str,
                                    primary_object_type: str = None,
                                    extra_config: Dict = None) -> Dict:
        """从多个 BO 生成聚合页菜单
        
        参数：
        - menu_code: 菜单编码
        - menu_name: 菜单名称
        - object_types: 关联的 BO ID 列表
        - menu_path: 路由路径
        - primary_object_type: 主 BO（可选）
        - extra_config: 额外配置
        """
        bo_bindings = []
        all_perms = []
        
        for i, ot in enumerate(object_types):
            obj = registry.get(ot)
            if obj:
                role = 'primary' if ot == primary_object_type else ('secondary' if i == 0 else 'secondary')
                binding = self._derive_bo_bindings(obj, role=role, read_only=(role != 'primary'))
                bo_bindings.extend(binding)
                all_perms.extend(self._derive_permissions_from_bindings(binding))

        return {
            'menu_code': menu_code,
            'menu_name': menu_name,
            'menu_path': menu_path,
            'page_type': 'multi_object_hub',
            'primary_object_type': primary_object_type or object_types[0] if object_types else '',
            'object_types': object_types,
            'bo_bindings': bo_bindings,
            'required_permissions': all_perms,
            'required_any_permission': False,
            'data_permission_hint': {
                'resource_types': object_types,
                'message': '\u5efa\u8bae\u5206\u914d\u76f8\u5173\u6570\u636e\u6743\u9650'
            },
            'page_config': extra_config or {},
            'auto_generated': True,
        }

    def _derive_bo_bindings(self, meta_obj: MetaObject, role: str = 'primary',
                            read_only: bool = False) -> List[Dict]:
        """从 BO 推导 bo_bindings，包括 CRUD actions + standalone actions
        
        参数：
        - meta_obj: BO 元数据
        - role: 绑定角色（primary/secondary/reference）
        - read_only: 是否只包含只读操作
        
        返回：
        - bo_bindings 列表
        """
        include_actions = []
        read_suffixes = {'read', 'list', 'export'}
        
        # 1. 收集 CRUD actions（现有逻辑）
        for action in meta_obj.actions:
            suffix = action.get_permission_suffix()
            if read_only and suffix not in read_suffixes:
                continue
            include_actions.append(suffix)
        
        # 2. 自动推导 standalone actions（新增逻辑）
        # 2a. 从 associations 推导 associate/dissociate 和 assign/unassign
        if hasattr(meta_obj, 'associations') and meta_obj.associations:
            for assoc in meta_obj.associations:
                # assoc 可能是 dict 或对象
                if isinstance(assoc, dict):
                    assoc_actions = assoc.get('actions', {})
                else:
                    assoc_actions = getattr(assoc, 'actions', {}) or {}
                
                # 如果 association 定义了 assign/unassign action（如 user_group.members）
                if 'assign' in assoc_actions:
                    include_actions.append('assign')
                if 'unassign' in assoc_actions:
                    include_actions.append('unassign')
                # 如果 association 定义了 associate/dissociate action
                if 'associate' in assoc_actions:
                    include_actions.append('associate')
                if 'dissociate' in assoc_actions:
                    include_actions.append('dissociate')
        
        # 2b. 从 import_export 配置推导 export/import
        if hasattr(meta_obj, 'import_export') and meta_obj.import_export:
            ie_config = meta_obj.import_export
            if isinstance(ie_config, dict):
                if ie_config.get('export_enabled', False):
                    include_actions.append('export')
                if ie_config.get('import_enabled', False):
                    include_actions.append('import')
            else:
                if getattr(ie_config, 'export_enabled', False):
                    include_actions.append('export')
                if getattr(ie_config, 'import_enabled', False):
                    include_actions.append('import')
        
        # 2c. 从 security 配置推导 grant/revoke
        if hasattr(meta_obj, 'security') and meta_obj.security:
            sec_config = meta_obj.security
            if isinstance(sec_config, dict):
                if sec_config.get('permission_delegation', False):
                    include_actions.append('grant')
                    include_actions.append('revoke')
            else:
                if getattr(sec_config, 'permission_delegation', False):
                    include_actions.append('grant')
                    include_actions.append('revoke')
        
        # 3. 去重
        include_actions = list(set(include_actions))
        
        return [{
            'bo_id': meta_obj.id,
            'role': role,
            'include_actions': include_actions,
        }]

    def _derive_permissions_from_bindings(self, bo_bindings: List[Dict]) -> List[str]:
        """从 bo_bindings 推导权限列表
        
        参数：
        - bo_bindings: BO 绑定声明列表
        
        返回：
        - 权限编码列表
        """
        perms = []
        
        for binding in bo_bindings:
            bo_id = binding.get('bo_id')
            include_actions = binding.get('include_actions', [])
            
            for action_suffix in include_actions:
                perm_code = f"{bo_id}:{action_suffix}"
                if perm_code not in perms:
                    perms.append(perm_code)
        
        return perms

    def _derive_permissions(self, meta_obj: MetaObject,
                            read_only: bool = False) -> List[str]:
        """直接从 BO 推导权限列表（兼容旧逻辑）"""
        read_suffixes = {'read', 'export'}
        perms = []
        for action in meta_obj.actions:
            if read_only and action.get_permission_suffix() not in read_suffixes:
                continue
            perms.append(action.get_permission_code(meta_obj.id))
        return perms

    def _extract_list_config(self, meta_obj: MetaObject) -> Dict:
        list_cfg = meta_obj.ui_view_config.list
        config = {}
        if list_cfg.title:
            config['page_title'] = list_cfg.title
        if list_cfg.description:
            config['page_description'] = list_cfg.description
        if list_cfg.pageSize:
            config['page_size'] = list_cfg.pageSize
        return config

    def generate_all(self) -> List[Dict]:
        """
        从已注册的 BO 元数据自动生成菜单
        
        跳过逻辑：
        1. 以 '_' 开头的对象（如 _template）
        2. ui_view_config.skip_auto_menu = True 的对象
        
        注意：不再使用硬编码的 skip 集合，而是从 YAML 元数据读取
        """
        menus = []
        for obj_id, obj in registry.get_all().items():
            if obj_id.startswith('_'):
                continue
            
            if obj.ui_view_config:
                skip_auto_menu = getattr(obj.ui_view_config, 'skip_auto_menu', False)
                if skip_auto_menu:
                    logger.debug(f"MenuAutoGenerator: skipping {obj_id} (skip_auto_menu=True)")
                    continue
                
                if obj.ui_view_config.list and obj.ui_view_config.list.columns:
                    menus.append(self.generate_object_list_menu(obj))
        return menus

    def persist_to_db(self, data_source, menus: List[Dict] = None) -> int:
        """将菜单记录持久化到 menus 导航表"""
        if not _schema_mtime_changed():
            logger.debug("[MenuAutoGenerator] No YAML changes detected, skipping persist_to_db")
            return 0

        if menus is None:
            menus = self.generate_all()

        count = 0
        for menu in menus:
            try:
                data_source.execute(
                    """INSERT OR IGNORE INTO menus
                    (menu_code, menu_name, menu_path, page_type, object_types,
                     primary_object_type, bo_bindings, required_permissions, 
                     required_any_permission, data_permission_hint, page_config, 
                     parent_menu, icon, color, description, sort_order, 
                     is_active, show_in_sidebar, auto_generated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 1)""",
                    [
                        menu['menu_code'],
                        menu['menu_name'],
                        menu.get('menu_path', ''),
                        menu.get('page_type', 'object_list'),
                        json.dumps(menu.get('object_types', []), ensure_ascii=False),
                        menu.get('primary_object_type', ''),
                        json.dumps(menu.get('bo_bindings', []), ensure_ascii=False),
                        json.dumps(menu.get('required_permissions', []), ensure_ascii=False),
                        menu.get('required_any_permission', False),
                        json.dumps(menu.get('data_permission_hint', {}), ensure_ascii=False),
                        json.dumps(menu.get('page_config', {}), ensure_ascii=False),
                        menu.get('parent_menu', ''),
                        menu.get('icon', 'Box'),
                        menu.get('color', ''),
                        menu.get('description', ''),
                        menu.get('sort_order', 99)
                    ]
                )
                count += 1
            except Exception as e:
                logger.warning(f"MenuAutoGenerator persist failed for {menu.get('menu_code')}: {e}")

        logger.info(f"MenuAutoGenerator persisted {count} menus to DB")
        _mark_menu_synced()
        return count

    def update_menu_bo_bindings(self, data_source, menu_code: str, 
                                 bo_bindings: List[Dict]) -> bool:
        """更新菜单的 bo_bindings 并重新推导权限
        
        参数：
        - data_source: 数据源
        - menu_code: 菜单编码
        - bo_bindings: 新的 BO 绑定声明
        
        返回：
        - 是否更新成功
        """
        required_permissions = self._derive_permissions_from_bindings(bo_bindings)
        
        try:
            data_source.execute(
                """UPDATE menus 
                   SET bo_bindings = ?, required_permissions = ?
                   WHERE menu_code = ?""",
                [
                    json.dumps(bo_bindings, ensure_ascii=False),
                    json.dumps(required_permissions, ensure_ascii=False),
                    menu_code
                ]
            )
            logger.info(f"Updated bo_bindings for menu {menu_code}")
            return True
        except Exception as e:
            logger.error(f"Failed to update bo_bindings for {menu_code}: {e}")
            return False

    def validate_menu_bo_bindings(self, menu: Dict) -> Dict:
        """校验菜单的 bo_bindings 是否有效
        
        返回：
        - is_valid: 是否有效
        - missing_bo_ids: 缺失的 BO ID
        - invalid_actions: 无效的 action
        """
        bo_bindings = menu.get('bo_bindings', [])
        missing_bo_ids = []
        invalid_actions = []
        
        for binding in bo_bindings:
            bo_id = binding.get('bo_id')
            obj = registry.get(bo_id)
            
            if not obj:
                missing_bo_ids.append(bo_id)
                continue
            
            valid_actions = {a.get_permission_suffix() for a in obj.actions}
            for action in binding.get('include_actions', []):
                if action not in valid_actions:
                    invalid_actions.append(f"{bo_id}:{action}")
        
        return {
            'is_valid': len(missing_bo_ids) == 0 and len(invalid_actions) == 0,
            'missing_bo_ids': missing_bo_ids,
            'invalid_actions': invalid_actions,
        }


menu_auto_generator = MenuAutoGenerator()
