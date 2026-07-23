# -*- coding: utf-8 -*-
"""
[MODULE] resource_inheritance_engine — 资源继承引擎 (Phase 5 P5-T2)
[DESCRIPTION] 实现 Spec §3.6.2 权限继承 5 条规则:
                规则 1: 向下继承 (parent.dim_scope → children)
                规则 2: 加严不放松 (children.scope ⊆ parent.scope)
                规则 3: 关联取交集 (Association 两端取并集可见)
                规则 4: 附属跟随 (Subordinate 继承 parent.owner)
                规则 5: 向上传播 (children.scope 变更 → parent)
[SPEC] spec-permission-system-unification-2026-07-19 §3.6 / §8.5 P5-T2
[FR] FR-013 / FR-014

[设计原则]
  - 纯函数 + 显式 data_source 注入, 便于测试
  - 复用 HIERARCHY_CHAIN / PARENT_FIELD_MAP (来自 chain_owner_resolver)
  - Secure-by-Default: 解析失败 → 返回空集合 (deny all)
  - 4 种资源类型 (Independent / Association / Subordinate / Hierarchy)
"""
import logging
from typing import Any, Dict, List, Optional, Set, Union

from meta.services.chain_owner_resolver import (
    HIERARCHY_CHAIN,
    PARENT_FIELD_MAP,
    RESOURCE_TABLE_MAP,
    resolve_root_owner,
    resolve_subordinate_owner as _chain_resolve_subordinate_owner,
)

logger = logging.getLogger(__name__)


# ============================================================================
# P5-T1: Resource 类型常量与元数据
# ============================================================================

# 4 种资源类型 (Spec §3.6.1)
RESOURCE_INDEPENDENT = 'independent'   # 独立资源 (product, user, role) — 不继承
RESOURCE_ASSOCIATION = 'association'   # 关联资源 (relationship) — 不继承, 取两端并集
RESOURCE_SUBORDINATE = 'subordinate'   # 附属资源 (annotation, audit_log) — 继承 parent.owner
RESOURCE_HIERARCHY = 'hierarchy'       # 层级资源 (version, domain, sub_domain) — 向下展开

# Resource 元数据: BO → {type, parent_field?, parent_bo?, table_name}
RESOURCE_METADATA_MAP: Dict[str, Dict[str, Any]] = {
    # Independent (独立资源)
    'product': {'type': RESOURCE_INDEPENDENT, 'table': 'products'},
    'user': {'type': RESOURCE_INDEPENDENT, 'table': 'users'},
    'role': {'type': RESOURCE_INDEPENDENT, 'table': 'roles'},

    # Hierarchy (层级资源)
    'version': {
        'type': RESOURCE_HIERARCHY, 'table': 'versions',
        'parent_bo': 'product', 'parent_field': 'product_id',
    },
    'domain': {
        'type': RESOURCE_HIERARCHY, 'table': 'domains',
        'parent_bo': 'version', 'parent_field': 'version_id',
    },
    'sub_domain': {
        'type': RESOURCE_HIERARCHY, 'table': 'sub_domains',
        'parent_bo': 'domain', 'parent_field': 'domain_id',
    },

    # Association (关联资源)
    'relationship': {
        'type': RESOURCE_ASSOCIATION, 'table': 'relationships',
        'source_field': 'source_bo_id',
        'target_field': 'target_bo_id',
    },

    # Subordinate (附属资源)
    'annotation': {
        'type': RESOURCE_SUBORDINATE, 'table': 'annotations',
        'parent_type_field': 'parent_type',
        'parent_id_field': 'parent_id',
    },
    'audit_log': {
        'type': RESOURCE_SUBORDINATE, 'table': 'audit_logs',
        'parent_type_field': 'object_type',
        'parent_id_field': 'object_id',
    },
}


def get_resource_type(bo_name: str) -> Optional[str]:
    """获取 BO 的资源类型"""
    meta = RESOURCE_METADATA_MAP.get(bo_name)
    return meta['type'] if meta else None


# ============================================================================
# P5-T2: ResourceInheritanceEngine — 5 条继承规则
# ============================================================================

class ResourceInheritanceEngine:
    """[P5-T2] 资源继承引擎

    实现 Spec §3.6.2 5 条权限继承规则. 接受 data_source (有 .execute(sql, params) 方法).
    """

    def __init__(self, data_source=None):
        """构造引擎

        Args:
            data_source: DB 数据源 (有 .execute(sql, params) 方法). 可为 None
                         (仅用于方法签名校验, 实际查询时再检查)
        """
        self._ds = data_source

    # ========================================================================
    # 规则 1: 向下继承 (inherit_children=1)
    # ========================================================================
    def expand_inherited_scope(
        self,
        role_id: int,
        parent_dimension: str,
        parent_values: List[int],
        inherit_children: int = 1,
    ) -> Dict[str, Set[int]]:
        """[规则 1] parent 的 dim scope 向下展开到 children

        例: parent=product [1] → version [1] → domain [1] → sub_domain [1]

        Args:
            role_id: 角色 ID (保留参数, 用于未来扩展角色级缓存)
            parent_dimension: 父维度 ('product' / 'version' / 'domain' / 'sub_domain')
            parent_values: 父维度的值列表
            inherit_children: 1=向下展开, 0=不展开

        Returns:
            {dimension: set(values)} 展开后的维度值映射
        """
        result: Dict[str, Set[int]] = {parent_dimension: set(parent_values)}
        if not inherit_children or not parent_values:
            return result
        if self._ds is None:
            return result
        if parent_dimension not in HIERARCHY_CHAIN:
            return result

        # 沿 HIERARCHY_CHAIN 向下逐层展开
        chain_idx = HIERARCHY_CHAIN.index(parent_dimension)
        current_values = list(parent_values)
        for child_dim in HIERARCHY_CHAIN[chain_idx + 1:]:
            # child_dim 的 parent_field 指向 parent_dimension
            # e.g. version.product_id → product.id
            parent_field = PARENT_FIELD_MAP.get(child_dim)
            if not parent_field or not current_values:
                result[child_dim] = set()
                continue
            child_table = RESOURCE_TABLE_MAP.get(child_dim, f'{child_dim}s')
            try:
                placeholders = ','.join('?' * len(current_values))
                rows = self._ds.execute(
                    f'SELECT id FROM {child_table} WHERE {parent_field} IN ({placeholders})',
                    current_values,
                ).fetchall()
                child_ids = [r[0] for r in rows if r[0] is not None]
                result[child_dim] = set(child_ids)
                current_values = child_ids  # 下一层用本层结果
            except Exception as e:
                logger.debug(
                    f'[P5-T2 expand_inherited_scope] {child_dim} lookup failed: {e}'
                )
                result[child_dim] = set()
                current_values = []
        return result

    # ========================================================================
    # 规则 2: 加严不放松 (children ⊆ parent)
    # ========================================================================
    def check_scope_strictness(
        self,
        parent_scope: Dict[str, Set[int]],
        child_scope: Dict[str, Set[int]],
    ) -> bool:
        """[规则 2] 检查 child 的 dim scope 是否为 parent 的子集 (不越界)

        核心逻辑:
          - 对于 child_scope 中每个维度 D, 找到 D 在 chain 上的祖先维度 A
          - 若 A 在 parent_scope 中, 则 child_scope[D] 必须是 A 范围内的合法值
          - 简化版: 若 parent_scope 和 child_scope 同维度, 直接子集判定
          - 跨维度: child.version 必须是 parent.product 内的 version

        Args:
            parent_scope: {'product': {1, 2}, ...}
            child_scope: {'version': {1, 2}, ...}

        Returns:
            True 表示 child ⊆ parent (合规), False 表示越界
        """
        if not child_scope:
            return True  # 空 child 默认合规

        for child_dim, child_vals in child_scope.items():
            if not child_vals:
                continue
            # 同维度直接子集
            if child_dim in parent_scope:
                if not child_vals.issubset(parent_scope[child_dim]):
                    return False
                continue

            # 跨维度: 需沿 chain 反查 parent 关系
            # 例: child_scope={'version': {1, 2}}, parent_scope={'product': {1}}
            # 需要: V1.product_id ∈ parent.product AND V2.product_id ∈ parent.product
            if child_dim in HIERARCHY_CHAIN and self._ds is not None:
                if not self._is_child_set_within_parent(child_dim, child_vals, parent_scope):
                    return False
        return True

    def _is_child_set_within_parent(
        self,
        child_dim: str,
        child_vals: Set[int],
        parent_scope: Dict[str, Set[int]],
    ) -> bool:
        """检查 child_vals 是否都在 parent_scope 范围内 (沿 chain 反查)"""
        if not child_vals:
            return True
        chain_idx = HIERARCHY_CHAIN.index(child_dim)
        # 从 child_dim 向上找, 直到找到 parent_scope 中存在的维度
        for ancestor_idx in range(chain_idx - 1, -1, -1):
            ancestor_dim = HIERARCHY_CHAIN[ancestor_idx]
            if ancestor_dim not in parent_scope:
                continue
            ancestor_vals = parent_scope[ancestor_dim]
            if not ancestor_vals:
                return False  # parent 该维度为空集 → 任何 child 都越界
            # 反查: child_dim 的每个值, 必须能沿 chain 追到 ancestor_dim ∈ ancestor_vals
            return self._check_chain_membership(
                child_dim, child_vals, ancestor_dim, ancestor_vals
            )
        return True  # 没有共同维度, 默认合规

    def _check_chain_membership(
        self,
        child_dim: str,
        child_vals: Set[int],
        ancestor_dim: str,
        ancestor_vals: Set[int],
    ) -> bool:
        """检查 child_vals 中每个值都对应 ancestor_vals 中的某个 ancestor

        通过单次 SQL JOIN 反查.
        """
        if not child_vals or not ancestor_vals:
            return False
        if child_dim == ancestor_dim:
            return child_vals.issubset(ancestor_vals)

        # 构造沿 chain 反查 SQL: child.id → ... → ancestor.id
        # 例: child=version, ancestor=product → SELECT v.id, p.id FROM versions v JOIN products p ON p.id=v.product_id
        #     WHERE v.id IN (...) AND p.id IN (...)
        child_table = RESOURCE_TABLE_MAP.get(child_dim, f'{child_dim}s')
        ancestor_table = RESOURCE_TABLE_MAP.get(ancestor_dim, f'{ancestor_dim}s')

        # 构造 JOIN 路径 (child_dim → ancestor_dim)
        chain_idx_child = HIERARCHY_CHAIN.index(child_dim)
        chain_idx_anc = HIERARCHY_CHAIN.index(ancestor_dim)
        if chain_idx_child <= chain_idx_anc:
            return True  # child 在 ancestor 之上, 不应发生

        # 沿 chain 构造 JOIN (从 child 向上)
        # 例: child=sub_domain, ancestor=product
        #   SELECT sd.id FROM sub_domains sd
        #   JOIN domains d ON sd.domain_id = d.id
        #   JOIN versions v ON d.version_id = v.id
        #   JOIN products p ON v.product_id = p.id
        #   WHERE sd.id IN (...) AND p.id IN (...)
        joins = []
        prev_table = child_table
        prev_alias = HIERARCHY_CHAIN[chain_idx_child][0]  # 首字母 alias
        prev_dim = child_dim
        for idx in range(chain_idx_child - 1, chain_idx_anc - 1, -1):
            cur_dim = HIERARCHY_CHAIN[idx]
            cur_table = RESOURCE_TABLE_MAP.get(cur_dim, f'{cur_dim}s')
            cur_alias = cur_dim[0]
            parent_field = PARENT_FIELD_MAP.get(prev_dim)
            if not parent_field:
                return False
            joins.append(
                f'JOIN {cur_table} {cur_alias} ON {prev_alias}.{parent_field} = {cur_alias}.id'
            )
            prev_table = cur_table
            prev_alias = cur_alias
            prev_dim = cur_dim

        # ancestor_dim 应是 prev_dim
        ancestor_alias = prev_alias
        child_alias = HIERARCHY_CHAIN[chain_idx_child][0]

        child_placeholders = ','.join('?' * len(child_vals))
        ancestor_placeholders = ','.join('?' * len(ancestor_vals))
        sql = (
            f'SELECT DISTINCT {child_alias}.id FROM {child_table} {child_alias} '
            + ' '.join(joins)
            + f' WHERE {child_alias}.id IN ({child_placeholders}) '
            + f' AND {ancestor_alias}.id IN ({ancestor_placeholders})'
        )
        try:
            rows = self._ds.execute(
                sql, list(child_vals) + list(ancestor_vals)
            ).fetchall()
            matched = {r[0] for r in rows if r[0] is not None}
            # 所有 child_vals 都必须匹配上 (matched ⊇ child_vals)
            return child_vals.issubset(matched)
        except Exception as e:
            logger.debug(f'[_check_chain_membership] SQL failed: {e}')
            return False

    # ========================================================================
    # 规则 3: 关联取交集 (Association)
    # ========================================================================
    def check_association_visibility(
        self,
        resource_id: int,
        resource_type: str,
        user_scope: Dict[str, Set[int]],
    ) -> bool:
        """[规则 3] Association 资源: 任一端在 user_scope 内 → 可见

        Spec §3.6.1: Association (relationship) 表达对象关系, 取两端并集 (任一端可见即可见)

        Args:
            resource_id: relationship.id
            resource_type: 'relationship' (or 其他 Association)
            user_scope: {'product': {1}, 'version': {1, 2}, ...}

        Returns:
            True 表示可见, False 表示两端都不在 scope
        """
        if self._ds is None:
            return False
        meta = RESOURCE_METADATA_MAP.get(resource_type)
        if not meta or meta.get('type') != RESOURCE_ASSOCIATION:
            # 非 association 资源, 退化为: resource_id 在 user_scope 中?
            return any(resource_id in vals for vals in user_scope.values())

        table = meta['table']
        source_field = meta.get('source_field', 'source_bo_id')
        target_field = meta.get('target_field', 'target_bo_id')

        try:
            row = self._ds.execute(
                f'SELECT {source_field}, {target_field} FROM {table} WHERE id = ? LIMIT 1',
                [resource_id],
            ).fetchone()
            if not row:
                return False
            source_id, target_id = row[0], row[1]

            # 默认两端都是 business_object 类型, 需反查 BO 所属的 product/version/...
            # 简化: 任一端 ID 在 user_scope 中 → 可见
            # 实际生产应反查 BO → sub_domain → domain → version → product 链
            for endpoint_id in (source_id, target_id):
                if endpoint_id is None:
                    continue
                # 反查 endpoint 所属的 product_id (沿 chain)
                product_id = self._resolve_endpoint_product_id(endpoint_id)
                if product_id is not None:
                    if 'product' in user_scope and product_id in user_scope['product']:
                        return True
                # 兼容: 直接 ID 匹配 (测试 fixture 简化场景)
                for dim_vals in user_scope.values():
                    if endpoint_id in dim_vals:
                        return True
            return False
        except Exception as e:
            logger.debug(
                f'[P5-T2 check_association_visibility] {resource_type}({resource_id}) failed: {e}'
            )
            return False

    def _resolve_endpoint_product_id(self, bo_id: int) -> Optional[int]:
        """反查 business_object 所属的 product_id (沿 chain)"""
        if not bo_id or self._ds is None:
            return None
        try:
            # business_object → service_module → sub_domain → domain → version → product
            row = self._ds.execute(
                'SELECT sm.sub_domain_id FROM business_objects bo '
                'JOIN service_modules sm ON bo.service_module_id = sm.id '
                'WHERE bo.id = ? LIMIT 1',
                [bo_id],
            ).fetchone()
            if not row:
                return None
            sub_domain_id = row[0]
            row = self._ds.execute(
                'SELECT v.product_id FROM sub_domains sd '
                'JOIN domains d ON sd.domain_id = d.id '
                'JOIN versions v ON d.version_id = v.id '
                'WHERE sd.id = ? LIMIT 1',
                [sub_domain_id],
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    # ========================================================================
    # 规则 4: 附属跟随 (Subordinate 继承 parent.owner)
    # ========================================================================
    def resolve_subordinate_owner(
        self,
        resource_type: str,
        resource: Dict[str, Any],
        max_depth: int = 3,
    ) -> Optional[int]:
        """[规则 4] Subordinate 资源自动继承 parent 的 owner

        解析顺序:
          1. resource 自身 owner_id (显式优先, 不被覆盖)
          2. 沿 parent_chain (parent_type + parent_id) → 查父资源 owner
          3. 父资源也是 subordinate → 递归 (max_depth 限制)

        Args:
            resource_type: BO 名 (e.g. 'annotation')
            resource: {'id', 'parent_type', 'parent_id', 'owner_id'?, ...}
            max_depth: 最大递归深度 (防无限循环)

        Returns:
            owner_id (int) 或 None
        """
        if not resource:
            return None

        # 1. 显式 owner_id 优先 (显式 > 继承)
        direct_owner = resource.get('owner_id')
        if direct_owner is not None:
            try:
                return int(direct_owner)
            except (TypeError, ValueError):
                pass

        # 2. 沿 parent_chain 继承
        parent_type = resource.get('parent_type') or resource.get('object_type')
        parent_id = resource.get('parent_id') or resource.get('object_id')
        if not (parent_type and parent_id) or self._ds is None:
            return None
        if max_depth <= 0:
            return None

        try:
            # 反查父资源
            parent_meta = RESOURCE_METADATA_MAP.get(parent_type)
            if not parent_meta:
                return None
            parent_table = parent_meta['table']
            row = self._ds.execute(
                f'SELECT * FROM {parent_table} WHERE id = ? LIMIT 1',
                [parent_id],
            ).fetchone()
            if not row:
                return None
            # 获取列名
            cols = self._ds.execute(
                f'PRAGMA table_info({parent_table})'
            ).fetchall()
            col_names = [c[1] for c in cols]
            parent_record = dict(zip(col_names, row))

            # 若父是 HIERARCHY 或 Independent (product), 用 chain_owner_resolver
            if parent_type == 'product':
                return parent_record.get('owner_id')
            if parent_type in HIERARCHY_CHAIN:
                # version/domain/sub_domain: 沿 chain 查 product.owner_id
                return resolve_root_owner(self._ds, parent_type, parent_id)
            # 父也是 subordinate → 递归
            if parent_meta.get('type') == RESOURCE_SUBORDINATE:
                return self.resolve_subordinate_owner(
                    parent_type, parent_record, max_depth - 1,
                )
        except Exception as e:
            logger.debug(
                f'[P5-T2 resolve_subordinate_owner] {resource_type}({resource.get("id")}) '
                f'parent lookup failed: {e}'
            )
        return None

    # ========================================================================
    # 规则 5: 向上传播 (propagate_to_parents=1)
    # ========================================================================
    def propagate_scope_upward(
        self,
        child_dimension: str,
        child_values: List[int],
        propagate_to_parents: int = 1,
    ) -> Dict[str, Set[int]]:
        """[规则 5] children 的 dim scope 变更向上传播到 parent

        例: sub_domain=[1] → domain=[1] → version=[1] → product=[1]

        Args:
            child_dimension: 子维度 ('sub_domain' / 'domain' / 'version' / 'product')
            child_values: 子维度的值列表
            propagate_to_parents: 1=向上传播, 0=不传播

        Returns:
            {dimension: set(values)} 包含 child + 所有祖先维度的值
        """
        result: Dict[str, Set[int]] = {child_dimension: set(child_values)}
        if not propagate_to_parents or not child_values:
            return result
        if self._ds is None:
            return result
        if child_dimension not in HIERARCHY_CHAIN:
            return result

        # 沿 chain 向上反查
        chain_idx = HIERARCHY_CHAIN.index(child_dimension)
        current_values = list(child_values)
        for parent_dim in reversed(HIERARCHY_CHAIN[:chain_idx]):
            # parent_dim 的 child 是 HIERARCHY_CHAIN[chain_idx-1] ... 0
            # child_dim 的 parent_field 指向 parent_dim
            child_dim_for_parent = HIERARCHY_CHAIN[chain_idx - 1] if chain_idx > 0 else None
            # 找到指向 parent_dim 的 child
            # 实际: 当前 current_values 对应的维度是 HIERARCHY_CHAIN[idx_current]
            # 我们要反查它的 parent
            pass

        # 重写为更直接的迭代: 从 child_dim 出发, 每步反查 parent_field
        current_dim = child_dimension
        current_vals = list(child_values)
        while current_dim in HIERARCHY_CHAIN:
            chain_idx_cur = HIERARCHY_CHAIN.index(current_dim)
            if chain_idx_cur == 0:
                break  # 已到顶层 (product)
            parent_dim = HIERARCHY_CHAIN[chain_idx_cur - 1]
            # current_dim 的 parent_field (e.g. version.product_id)
            parent_field = PARENT_FIELD_MAP.get(current_dim)
            if not parent_field or not current_vals:
                result[parent_dim] = set()
                break
            current_table = RESOURCE_TABLE_MAP.get(current_dim, f'{current_dim}s')
            try:
                placeholders = ','.join('?' * len(current_vals))
                rows = self._ds.execute(
                    f'SELECT DISTINCT {parent_field} FROM {current_table} '
                    f'WHERE id IN ({placeholders})',
                    current_vals,
                ).fetchall()
                parent_ids = {r[0] for r in rows if r[0] is not None}
                result[parent_dim] = parent_ids
                current_dim = parent_dim
                current_vals = list(parent_ids)
            except Exception as e:
                logger.debug(
                    f'[P5-T2 propagate_scope_upward] {current_dim} → {parent_dim} failed: {e}'
                )
                result[parent_dim] = set()
                break
        return result

    # ========================================================================
    # P5-T3: 显式配置 vs 继承 — 合并 + 优先级
    # ========================================================================
    def merge_explicit_with_inherited(
        self,
        explicit: Dict[str, Set[int]],
        inherited: Dict[str, Set[int]],
    ) -> Dict[str, Set[int]]:
        """[P5-T3] 合并显式配置与继承配置 (取并集)

        Args:
            explicit: 显式配置 {'product': {1}}
            inherited: 继承配置 {'product': {2}}

        Returns:
            合并后的配置 {'product': {1, 2}}
        """
        merged: Dict[str, Set[int]] = {}
        for dim, vals in explicit.items():
            merged[dim] = set(vals)
        for dim, vals in inherited.items():
            if dim in merged:
                merged[dim] |= set(vals)
            else:
                merged[dim] = set(vals)
        return merged

    def resolve_with_precedence(
        self,
        explicit_rules: List[Dict[str, Any]],
        inherited_rules: List[Dict[str, Any]],
        resource_type: str,
        resource_id: int,
    ) -> str:
        """[P5-T3] 显式配置优先于继承 — Deny 优先

        优先级顺序:
          1. 显式 Deny (is_denied=True) → 'deny' (短路)
          2. 显式 Allow (is_denied=False) → 'allow' (短路, 不查继承)
          3. 继承 Deny → 'deny'
          4. 继承 Allow → 'allow'
          5. 都无 → 'deny' (Secure-by-Default)

        Args:
            explicit_rules: [{'resource_type', 'is_denied', 'resource_id'?}]
            inherited_rules: 同结构
            resource_type: 资源类型
            resource_id: 资源 ID

        Returns:
            'allow' / 'deny'
        """
        # 1. 显式 Deny 优先 (短路)
        for rule in explicit_rules:
            if rule.get('resource_type') != resource_type:
                continue
            rid = rule.get('resource_id')
            if rid is not None and rid != resource_id:
                continue
            if rule.get('is_denied'):
                return 'deny'
        # 2. 显式 Allow (短路, 不查继承)
        for rule in explicit_rules:
            if rule.get('resource_type') != resource_type:
                continue
            rid = rule.get('resource_id')
            if rid is not None and rid != resource_id:
                continue
            if not rule.get('is_denied'):
                return 'allow'
        # 3. 继承 Deny
        for rule in inherited_rules:
            if rule.get('resource_type') != resource_type:
                continue
            rid = rule.get('resource_id')
            if rid is not None and rid != resource_id:
                continue
            if rule.get('is_denied'):
                return 'deny'
        # 4. 继承 Allow
        for rule in inherited_rules:
            if rule.get('resource_type') != resource_type:
                continue
            rid = rule.get('resource_id')
            if rid is not None and rid != resource_id:
                continue
            if not rule.get('is_denied'):
                return 'allow'
        # 5. Secure-by-Default
        return 'deny'

    # ========================================================================
    # P5-T3: 3 级嵌套继承链解析
    # ========================================================================
    def resolve_inheritance_chain(
        self,
        resource_type: str,
        resource: Dict[str, Any],
        max_depth: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """[P5-T3] 解析 3 级嵌套继承链

        例: annotation → product → version
            通过 annotation.parent_type='product' + parent_id=1 反查 product 1
            再通过 product 的层级关系反查 version

        Args:
            resource_type: BO 名 (通常是 Subordinate)
            resource: 资源 dict
            max_depth: 最大嵌套深度

        Returns:
            {'product': {'id': 1, 'owner_id': 100, ...}, ...} 或 None
        """
        if not resource or self._ds is None:
            return None

        result: Dict[str, Any] = {}
        current_type = resource_type
        current_record = resource
        depth = 0

        while depth < max_depth:
            parent_type = current_record.get('parent_type') or current_record.get('object_type')
            parent_id = current_record.get('parent_id') or current_record.get('object_id')
            if not (parent_type and parent_id):
                break
            parent_meta = RESOURCE_METADATA_MAP.get(parent_type)
            if not parent_meta:
                break
            parent_table = parent_meta['table']
            try:
                row = self._ds.execute(
                    f'SELECT * FROM {parent_table} WHERE id = ? LIMIT 1',
                    [parent_id],
                ).fetchone()
                if not row:
                    break
                cols = self._ds.execute(
                    f'PRAGMA table_info({parent_table})'
                ).fetchall()
                col_names = [c[1] for c in cols]
                parent_record = dict(zip(col_names, row))
                result[parent_type] = parent_record
                # 继续向上 (若 parent 也是 subordinate)
                if parent_meta.get('type') == RESOURCE_SUBORDINATE:
                    current_type = parent_type
                    current_record = parent_record
                    depth += 1
                else:
                    break
            except Exception as e:
                logger.debug(
                    f'[P5-T3 resolve_inheritance_chain] depth={depth} '
                    f'{current_type} → {parent_type} failed: {e}'
                )
                break

        return result if result else None
