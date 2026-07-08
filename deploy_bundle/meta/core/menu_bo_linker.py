# -*- coding: utf-8 -*-
r"""
Menu-BO 权限自动关联（FR-013, SAP SU24 等价物）

【背景 2026-06-04】
Spec v1.4 FR-013: 当菜单绑定 BO 时，自动应用 BO 的默认权限。
借鉴 SAP SU24 思路：
- SU24 维护"事务码 → 权限对象默认建议"映射
- 角色配置时自动应用这些默认建议
- 我们类比：菜单绑定 BO 时，自动应用 BO 的默认权限

【v1.4 用户关键洞察】
"菜单如果关联到同一个 BO，应该有默认权限"——SU24 是行业标准。
"""
import logging
from typing import Dict, List, Any, Optional

from meta.core.bo_schema_loader import get_bo_schema_loader

logger = logging.getLogger(__name__)


class MenuBOLinker:
    """Menu-BO 权限自动关联（FR-013 实施）

    职责：
    1. 根据 BO 的 actions 自动生成默认权限码
    2. 菜单绑定 BO 时自动应用这些默认权限
    """

    DEFAULT_PERMISSION_ACTIONS = ['read', 'list', 'update', 'delete']

    def __init__(self):
        self._schema_loader = get_bo_schema_loader()

    def get_default_bo_permissions(self, bo_id: str) -> List[str]:
        """获取 BO 的默认权限码列表

        Args:
            bo_id: BO 标识符

        Returns:
            权限码列表，如 ['business_object:read', 'business_object:list', ...]
        """
        bo_schema = self._schema_loader.get_bo_schema(bo_id)
        if not bo_schema:
            # 无 schema 时用默认 CRUD
            return [f'{bo_id}:{a}' for a in self.DEFAULT_PERMISSION_ACTIONS]

        # 用 BO 的 actions 字段（如有）
        actions = bo_schema.get('actions', []) or []
        action_ids = [
            a.get('id', '') for a in actions
            if isinstance(a, dict) and a.get('id')
        ]
        if action_ids:
            return [f'{bo_id}:{aid}' for aid in action_ids]

        # fallback：默认 CRUD
        return [f'{bo_id}:{a}' for a in self.DEFAULT_PERMISSION_ACTIONS]

    def get_effective_permissions_for_menu(
        self,
        menu_code: str,
        bo_bindings: List[Dict[str, Any]],
    ) -> List[str]:
        """获取菜单的有效权限（菜单的 + 关联 BO 的默认权限）

        Args:
            menu_code: 菜单编码（占位）
            bo_bindings: 菜单的 BO 绑定列表 [{bo_id: '...', role: 'primary'}, ...]

        Returns:
            有效权限码列表（去重）
        """
        effective: List[str] = []
        for binding in bo_bindings:
            bo_id = binding.get('bo_id')
            if not bo_id:
                continue
            effective.extend(self.get_default_bo_permissions(bo_id))
        return sorted(set(effective))

    def get_cross_menu_bo_intent_summary(
        self,
        bo_id: str,
        all_menu_bindings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """获取 BO 跨菜单使用情况（FR-015 跨菜单累加显式化）

        Args:
            bo_id: BO 标识符
            all_menu_bindings: 所有菜单的 BO 绑定（包含 menu_code）

        Returns:
            {
                'bo_id': '...',
                'menu_count': 3,
                'menus': [
                    {'menu_code': '...', 'role': 'primary', 'actions': [...]},
                    ...
                ],
                'all_actions': [...],   # 累加后的所有 actions
                'has_conflict': bool,   # 是否有不同 role 冲突
            }
        """
        menus = []
        roles_seen: set = set()
        for binding in all_menu_bindings:
            if binding.get('bo_id') != bo_id:
                continue
            menu_code = binding.get('menu_code', '')
            role = binding.get('role', 'primary')
            roles_seen.add(role)
            menus.append({
                'menu_code': menu_code,
                'role': role,
                'actions': self.get_default_bo_permissions(bo_id),
            })
        all_actions: List[str] = []
        for m in menus:
            all_actions.extend(m['actions'])
        return {
            'bo_id': bo_id,
            'menu_count': len(menus),
            'menus': menus,
            'all_actions': sorted(set(all_actions)),
            'has_conflict': len(roles_seen) > 1,
        }


_linker_instance: Optional[MenuBOLinker] = None


def get_menu_bo_linker() -> MenuBOLinker:
    """获取全局单例"""
    global _linker_instance
    if _linker_instance is None:
        _linker_instance = MenuBOLinker()
    return _linker_instance
