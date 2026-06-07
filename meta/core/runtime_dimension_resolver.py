# -*- coding: utf-8 -*-
r"""
Runtime Dimension Resolver — 运行时维度解析器

【背景 2026-06-04】
Spec v1.3 (data-permission-unified-model) 引入运行时动态展开：
- 配置层：role_dimension_scopes（用户配的维度值）
- 应用层：BO 的 dimension_bindings（YAML 声明）
- 执行层：拦截器运行时从上述 2 源动态拼 SQL（无中间表）

本模块实现运行时从 role_dimension_scopes 读取用户配置，
结合 BO 的 dimension_bindings 解析为 SQL WHERE 条件。

【M2.1 扩展 — Owner 过滤】
按 FR-009，Owner 过滤（基于 owner_id）是记录级可见性机制，
与维度范围是 AND 组合关系。
按 FR-010，Draft 模式（visibility='draft' 仅 owner 可见）作为
通用 owner-scoped 可见性机制，由 BO 通过 aspect 引用。

使用示例：
    resolver = RuntimeDimensionResolver()
    # 维度范围
    conditions = resolver.resolve(user_id=5, bo_id='domain')
    # Owner 过滤
    owner_cond = resolver.resolve_owner_filter(user_id=5, bo_id='version')
    # 组合（AND）
    full = resolver.resolve_with_owner(user_id=5, bo_id='domain')
"""
import json
import re
import sqlite3
import os
import logging
from typing import List, Dict, Any, Optional

from meta.core.bo_schema_loader import get_bo_schema_loader
from meta.core.feature_flags import is_enabled
from meta.core.perm_cache import get_permission_cache, PermissionCache

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    """获取数据库路径"""
    current = os.path.abspath(__file__)
    for _ in range(2):
        current = os.path.dirname(current)
    return os.path.join(current, 'architecture.db')


class RuntimeDimensionResolver:
    """运行时维度解析器

    职责：
    1. 读取 role_dimension_scopes 中用户的维度值配置
    2. 结合 BO 的 dimension_bindings 解析为 SQL WHERE 条件
    3. 支持公共维度（bo_id=NULL）和 BO 级覆盖
    4. M2.1: 支持 Owner 过滤运行时展开
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _get_db_path()
        self._schema_loader = get_bo_schema_loader()

    def resolve(
        self,
        user_id: int,
        bo_id: str,
        role_ids: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """运行时解析数据权限条件

        Args:
            user_id: 用户 ID
            bo_id: BO 标识符
            role_ids: 角色 ID 列表（None 时从 DB 查询）

        Returns:
            条件列表：
                [{
                    'field': 'id',
                    'joins': [],  # FR-016 AC-2 新增（向后兼容默认空）
                    'operator': 'in',
                    'value': [1, 2],
                    'source': 'dimension',
                    'dimension': 'domain',
                }]
        """
        if not is_enabled('ENABLE_RUNTIME_RESOLUTION'):
            return []

        # P0 修复：NFR-001 缓存层（避免重复计算）
        cache = get_permission_cache()
        cache_key = PermissionCache.make_key(
            user_id=user_id, bo_id=bo_id, role_ids=role_ids,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        conditions = self._resolve_uncached(user_id, bo_id, role_ids)
        cache.set(cache_key, conditions)
        return conditions

    def _resolve_uncached(
        self,
        user_id: int,
        bo_id: str,
        role_ids: Optional[List[int]],
    ) -> List[Dict[str, Any]]:
        """无缓存的 resolve 实现（P0 重构：可缓存化）"""
        if role_ids is None:
            role_ids = self._get_user_roles(user_id)
        if not role_ids:
            return []

        dim_scopes = self._get_role_dim_scopes(role_ids)
        if not dim_scopes:
            return []

        bindings = self._schema_loader.get_dimension_bindings(bo_id)
        if not bindings:
            return []

        conditions = []
        for dim_scope in dim_scopes:
            # 公共维度 (bo_id=NULL) 或当前 BO
            if dim_scope['bo_id'] is not None and dim_scope['bo_id'] != bo_id:
                continue

            values = self._parse_dim_values(dim_scope.get('dimension_values', '[]'))
            if not values:
                continue

            dim_code = dim_scope['dimension_code']
            matched = [b for b in bindings if b.get('dimension') == dim_code]
            for binding in matched:
                # P0 修复：用 _resolve_field_with_joins 替代 _resolve_field
                # 携带 JOIN 路径信息（FR-016 AC-2）
                field_info = self._resolve_field_with_joins(binding, bo_id)
                if field_info is None:
                    continue
                conditions.append({
                    'field': field_info['field'],
                    'joins': field_info.get('joins', []),  # 新增
                    'operator': 'in' if len(values) > 1 else 'eq',
                    'value': values,
                    'source': 'dimension',
                    'dimension': dim_code,
                })
        return conditions

    # ----------------------------------------------------------------
    # M2.1: Owner 过滤运行时展开（FR-009）
    # ----------------------------------------------------------------

    def resolve_owner_filter(
        self,
        user_id: int,
        bo_id: str,
        owner_id_field: str = 'owner_id',
    ) -> Optional[Dict[str, Any]]:
        """运行时展开 Owner 过滤（记录级可见性）

        Args:
            user_id: 当前用户 ID
            bo_id: BO 标识符
            owner_id_field: BO 表中的 owner 字段名（默认 'owner_id'）

        Returns:
            条件项：
                {
                    'field': 'owner_id',
                    'operator': 'eq',
                    'value': <user_id>,
                    'source': 'owner',
                }
            如果 BO 不支持 owner 过滤（如未声明 owner_id 字段），返回 None
        """
        if not is_enabled('ENABLE_OWNER_FILTER'):
            return None

        if not self._schema_loader.has_owner_id(bo_id):
            return None

        return {
            'field': owner_id_field,
            'operator': 'eq',
            'value': user_id,
            'source': 'owner',
        }

    def resolve_with_owner(
        self,
        user_id: int,
        bo_id: str,
        role_ids: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """运行时解析数据权限条件（包含 owner 过滤）

        包装 resolve() 并叠加 owner 过滤。
        owner 过滤与维度范围是 AND 关系（数据权限依附功能权限）。

        Args:
            user_id: 当前用户 ID
            bo_id: BO 标识符
            role_ids: 角色 ID 列表

        Returns:
            条件列表
        """
        conditions = self.resolve(user_id, bo_id, role_ids)
        owner_cond = self.resolve_owner_filter(user_id, bo_id)
        if owner_cond:
            conditions.append(owner_cond)
        return conditions

    def _get_user_roles(self, user_id: int) -> List[int]:
        """获取用户的角色 ID 列表"""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT gr.role_id
                FROM user_group_members ugm
                JOIN group_roles gr ON ugm.group_id = gr.group_id
                WHERE ugm.user_id = ?
            """, (user_id,))
            roles = [row[0] for row in cursor.fetchall()]
            conn.close()
            return roles
        except Exception as e:
            logger.error(f"Failed to get user roles: {e}")
            return []

    def _get_role_dim_scopes(self, role_ids: List[int]) -> List[Dict[str, Any]]:
        """获取角色的维度范围配置"""
        if not role_ids:
            return []
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(role_ids))
            cursor.execute(f"""
                SELECT role_id, dimension_code, dimension_values, inherit_children,
                       scope_mode, bo_id
                FROM role_dimension_scopes
                WHERE role_id IN ({placeholders})
            """, role_ids)
            scopes = []
            for row in cursor.fetchall():
                scopes.append({
                    'role_id': row[0],
                    'dimension_code': row[1],
                    'dimension_values': row[2],
                    'inherit_children': row[3],
                    'scope_mode': row[4],
                    'bo_id': row[5],
                })
            conn.close()
            return scopes
        except Exception as e:
            logger.error(f"Failed to get role dim scopes: {e}")
            return []

    def _parse_dim_values(self, raw: Any) -> List[Any]:
        """解析 dimension_values（可能是 JSON 字符串）"""
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                # 不是 JSON 字符串，尝试按逗号分隔
                return [v.strip() for v in raw.split(',') if v.strip()]
        return []

    def _resolve_field(self, binding: Dict[str, Any], bo_id: str) -> Optional[str]:
        """解析字段（处理多跳关联，FR-016 AC-1 优先用冗余字段）

        Args:
            binding: dimension_bindings 项
                {'dimension': 'product', 'field': 'version_id', 'through': 'version'}
            bo_id: 当前 BO

        Returns:
            字段名：
            - 无 through: 直接返回 field
            - 有 through: 优先用冗余字段（如 domain_id），否则返回主字段
              （调用方负责 SQL JOIN 展开，参考 _resolve_field_with_joins）
        """
        field = binding.get('field')
        if not field:
            return None

        through = binding.get('through')
        if not through:
            return field

        # FR-016 AC-1: 多跳关联优先用冗余字段（修复 v1.3 实施 Bug）
        target_dim = binding.get('dimension')
        if target_dim:
            redundant_field = self._find_redundant_field(bo_id, target_dim)
            if redundant_field:
                return redundant_field

        # 没有冗余字段：返回主字段（fallback 保留向后兼容）
        return field

    def _find_redundant_field(self, bo_id: str, target_dim: str) -> Optional[str]:
        """查找 BO 的冗余字段（FR-016 AC-1）

        冗余字段定义：BO 的 fields 中 id = {target_dim}_id 且 storage != virtual 且 db_column 存在。
        即实际数据库表中存储的、可直接用于 WHERE 过滤的字段。

        Args:
            bo_id: BO 标识符（如 'business_object'）
            target_dim: 目标维度名（如 'domain', 'sub_domain', 'version'）

        Returns:
            冗余字段名（如 'domain_id'），如果 BO 没有冗余字段则返回 None
        """
        bo_schema = self._schema_loader.get_bo_schema(bo_id)
        if not bo_schema:
            return None

        target_field_id = f'{target_dim}_id'
        for f in bo_schema.get('fields', []) or []:
            if f.get('id') != target_field_id:
                continue
            # 必须是 db_column（实际存储）才视为冗余字段
            # storage == 'virtual' 的字段（如 business_object.domain_id）不算
            storage = f.get('storage')
            db_column = f.get('db_column')
            if storage == 'virtual':
                continue
            if not db_column:
                continue
            return f.get('id')
        return None

    def _resolve_field_with_joins(
        self,
        binding: Dict[str, Any],
        bo_id: str,
    ) -> Optional[Dict[str, Any]]:
        """解析字段 + JOIN 路径（FR-016 AC-2）

        Returns:
            {
                'field': <字段名>,
                'joins': [
                    {
                        'target_bo': 'sub_domain',
                        'target_table': 'sub_domains',
                        'alias': 'sd',
                        'path_type': 'parent_child' | 'association',
                        'level': 1,
                    },
                    ...
                ]
            }
            - 无 through: joins = []
            - 用了冗余字段: joins = []（无需 JOIN）
            - 否则 joins 包含从当前 BO 到目标 BO 的路径
        """
        field = self._resolve_field(binding, bo_id)
        if not field:
            return None

        through = binding.get('through')
        if not through:
            return {'field': field, 'joins': []}

        # 检查是否用了冗余字段（用了就不需要 JOIN）
        target_dim = binding.get('dimension')
        if target_dim:
            redundant_field = self._find_redundant_field(bo_id, target_dim)
            if redundant_field and redundant_field == field:
                return {'field': field, 'joins': []}

        # 主字段 + JOIN 路径
        joins = self._build_join_path(through)
        return {'field': field, 'joins': joins}

    def _build_join_path(self, through: str) -> List[Dict[str, Any]]:
        """构建 JOIN 路径（FR-016 AC-2 + Q9 字符串语法）

        字符串语法（Q9 决策）：
        - '->' : parent-child 路径
        - '-->' : association (FK) 路径

        例：
            'service_module->sub_domain->domain' →
            [
                {target_bo: 'sub_domain', path_type: 'parent_child', level: 1},
                {target_bo: 'domain', path_type: 'parent_child', level: 2},
            ]

            'order-->customer-->region' →
            [
                {target_bo: 'customer', path_type: 'association', level: 1},
                {target_bo: 'region', path_type: 'association', level: 2},
            ]

        Returns:
            JOIN 列表（不含第一个 BO，因为是当前 BO）
        """
        if not through:
            return []

        # 解析 token 序列：'bo1->bo2-->bo3'
        # 用 regex 一次性分词，避免 '-->' 被 '->' 误匹配
        tokens = re.findall(r'(?:-->|->|[^->\s]+)', through)
        parts: List[Dict[str, str]] = []
        current_tokens: List[str] = []
        current_path_type = 'parent_child'  # 默认

        for token in tokens:
            if token in ('->', '-->'):
                # flush current BO
                if current_tokens:
                    parts.append({
                        'bo': ''.join(current_tokens).strip(),
                        'path_type': current_path_type,
                    })
                    current_tokens = []
                current_path_type = (
                    'parent_child' if token == '->' else 'association'
                )
            else:
                current_tokens.append(token)
        if current_tokens:
            parts.append({
                'bo': ''.join(current_tokens).strip(),
                'path_type': current_path_type,
            })

        if not parts:
            return []

        # 跳过第一个（bo_id 自身），从第 2 个开始构建 JOIN
        joins: List[Dict[str, Any]] = []
        for i, p in enumerate(parts[1:]):
            target = p['bo']
            target_table = self._to_table_name(target)
            alias = ''.join(s[0] for s in target.split('_'))[:2] or target[:2]
            joins.append({
                'target_bo': target,
                'target_table': target_table,
                'alias': alias,
                'path_type': p['path_type'],
                'level': i + 1,
            })

        return joins

    @staticmethod
    def _to_table_name(bo_id: str) -> str:
        """BO 标识符 → 表名（简化版：复数化）

        例：
            'sub_domain' → 'sub_domains'
            'business_object' → 'business_objects'
            'category' → 'categories'
        """
        if not bo_id:
            return bo_id
        if bo_id.endswith('s'):
            return bo_id
        if bo_id.endswith('y') and len(bo_id) > 1 and bo_id[-2] not in 'aeiou':
            return bo_id[:-1] + 'ies'
        return bo_id + 's'


# 单例
_resolver_instance: Optional[RuntimeDimensionResolver] = None


def get_runtime_dimension_resolver() -> RuntimeDimensionResolver:
    """获取全局单例"""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = RuntimeDimensionResolver()
    return _resolver_instance
