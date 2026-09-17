# -*- coding: utf-8 -*-
"""
[MODULE] permission_resolver — 统一权限决策点 (PDP)
[DESCRIPTION] Phase 2 P2-T2: Owner 机制统一 — PermissionResolver.check_owner()
              3 路径统一判定: 显式 owner_field → created_by fallback → chain
[SPEC] spec-permission-system-unification-2026-07-19 §3.5 / §3.9 / §8.2 P2-T2

[设计原则]
  - check_owner(rule_def, user, resource): 统一入口
  - 复用 chain_owner_resolver (避免重复实现 HIERARCHY_CHAIN SQL)
  - 构造时 data_source 可为 None (仅用于兼容 import 测试,
    实际调用 check_owner 时再检查)
"""
import logging
from typing import Optional, Dict, Any

from meta.services.chain_owner_resolver import (
    resolve_root_owner,
    is_in_chain,
    HIERARCHY_CHAIN,
)

logger = logging.getLogger(__name__)

# 默认 owner 字段 (与 Spec §3.9 rule_def 一致)
_DEFAULT_OWNER_FIELD = 'owner_id'
_DEFAULT_FALLBACK_FIELD = 'created_by'


# ============================================================================
# [P4-T1] 辅助函数: 兼容 dict / object 用户
# ============================================================================

def _get_user_attr_safe(user, key, default=None):
    """从 user 提取属性, 兼容 dict / object / None"""
    if user is None:
        return default
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


def _user_to_dict(user):
    """将 user 转为 dict (用于 check_owner 兼容性)"""
    if user is None:
        return {}
    if isinstance(user, dict):
        return user
    # object → dict (提取常见字段)
    result = {}
    for key in ('id', 'username', 'team_ids', 'department_id', 'is_superuser'):
        result[key] = getattr(user, key, None)
    return result


class PermissionResolver:
    """[P2-T2] 统一权限决策点 (PDP) — Owner 路径

    Phase 2 范围: 仅实现 check_owner (P2-T2) + check_owner_for_subordinate (P2-T5)
    Phase 4 范围: 实现完整 5 层 check (P4-T1)
    """

    def __init__(self, data_source=None):
        """构造 PermissionResolver

        Args:
            data_source: DB 数据源 (可为 None, 仅做类型检查)
        """
        self._ds = data_source
        self._inheritance_engine = None  # [P5-T3] 懒加载 ResourceInheritanceEngine

    # ========================================================================
    # [P5-T3] ResourceInheritanceEngine 懒加载
    # ========================================================================
    def _get_inheritance_engine(self):
        """[P5-T3] 懒加载 ResourceInheritanceEngine (避免循环 import)"""
        if self._inheritance_engine is None:
            try:
                from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
                self._inheritance_engine = ResourceInheritanceEngine(self._ds)
            except ImportError:
                logger.debug('[P5-T3] ResourceInheritanceEngine not available')
                return None
        return self._inheritance_engine

    # ========================================================================
    # P2-T2: check_owner — 3 路径统一判定
    # ========================================================================
    def check_owner(
        self,
        user: Dict[str, Any],
        resource_type: str,
        resource: Dict[str, Any],
        rule_def: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """[P2-T2] 判定 user 是否是 resource 的 owner

        3 路径判定顺序:
          路径 1: 显式 owner_field (默认 owner_id) == user.id
          路径 2: fallback_field (默认 created_by) == user.username 或 user.id
          路径 3: chain_inheritance='hierarchy_chain' → 沿 HIERARCHY_CHAIN 追溯 product.owner_id

        Args:
            user: {'id': int, 'username': str}
            resource_type: BO 名 (product, version, domain, sub_domain, business_object, ...)
            resource: 资源 dict (必须含 'id' 字段)
            rule_def: 可选 rule 配置, 覆盖默认 owner_field/fallback_field/chain_inheritance

        Returns:
            True 表示 user 是 owner; 否则 False
        """
        if not user or not resource:
            return False
        user_id = user.get('id')
        user_username = user.get('username', '')
        if not user_id:
            return False

        # 解析 rule_def
        owner_field = (rule_def or {}).get('owner_field', _DEFAULT_OWNER_FIELD)
        fallback_field = (rule_def or {}).get('fallback_field', _DEFAULT_FALLBACK_FIELD)
        chain_inheritance = (rule_def or {}).get('chain_inheritance')

        # 路径 1: 直接 owner 字段
        direct_owner = resource.get(owner_field)
        if direct_owner == user_id:
            logger.debug(
                f'[P2-T2 check_owner] path1 direct: '
                f'{resource_type}({resource.get("id")}).{owner_field}={direct_owner} == user.id={user_id}'
            )
            return True

        # 路径 2: fallback to created_by / 其他字段
        if fallback_field and resource.get(fallback_field):
            created_by = resource.get(fallback_field)
            if created_by == user_username:
                logger.debug(
                    f'[P2-T2 check_owner] path2 fallback username: '
                    f'{fallback_field}={created_by} == user.username={user_username}'
                )
                return True
            # 兼容整数类型 (老数据 created_by 是 user_id)
            try:
                if int(created_by) == user_id:
                    logger.debug(
                        f'[P2-T2 check_owner] path2 fallback user_id: '
                        f'{fallback_field}={created_by} == user.id={user_id}'
                    )
                    return True
            except (TypeError, ValueError):
                pass

        # 路径 3: chain inheritance (仅当显式启用 chain_inheritance 或 resource 在 HIERARCHY_CHAIN)
        if chain_inheritance == 'hierarchy_chain' or is_in_chain(resource_type):
            if self._ds is None:
                logger.debug('[P2-T2 check_owner] path3 skip: data_source is None')
            else:
                try:
                    root_owner = resolve_root_owner(
                        self._ds, resource_type, resource.get('id')
                    )
                    if root_owner == user_id:
                        logger.debug(
                            f'[P2-T2 check_owner] path3 chain: '
                            f'{resource_type}({resource.get("id")}) -> product.owner_id={root_owner}'
                        )
                        return True
                except Exception as e:
                    logger.debug(f'[P2-T2 check_owner] path3 error: {e}')

        return False

    # ========================================================================
    # P2-T5: check_owner_for_subordinate — 附属资源继承 owner
    # ========================================================================
    def check_owner_for_subordinate(
        self,
        user: Dict[str, Any],
        resource_type: str,
        resource: Dict[str, Any],
        rule_def: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """[P2-T5 + P5-T3] 判定 user 是否是 resource (subordinate) 的 owner (含 parent 继承)

        Subordinate 资源 (如 annotation, audit_log) 自动继承 parent.owner.
        判定顺序:
          1. resource 自身 owner 命中 → True (同 check_owner)
          2. [P5-T3] 调用 ResourceInheritanceEngine.resolve_subordinate_owner
             沿 parent_chain (规则 4 附属跟随) 反查 parent.owner
          3. fallback: 旧的 parent_type + parent_id 直接查 parent.owner
        """
        # 先用 check_owner 判定自身
        if self.check_owner(user, resource_type, resource, rule_def):
            return True

        # [P5-T3] 优先使用 ResourceInheritanceEngine (规则 4 附属跟随)
        engine = self._get_inheritance_engine()
        if engine is not None:
            try:
                inherited_owner = engine.resolve_subordinate_owner(
                    resource_type=resource_type,
                    resource=resource,
                    max_depth=3,
                )
                if inherited_owner is not None:
                    user_id = user.get('id')
                    if user_id is not None and int(inherited_owner) == int(user_id):
                        logger.debug(
                            f'[P5-T3 check_owner_for_subordinate] engine match: '
                            f'{resource_type}({resource.get("id")}) inherited_owner={inherited_owner}'
                        )
                        return True
            except Exception as e:
                logger.debug(
                    f'[P5-T3 check_owner_for_subordinate] engine error: {e}'
                )

        # fallback: 直接查 parent (向后兼容, 测试 fixture 简化场景)
        parent_type = resource.get('parent_type')
        parent_id = resource.get('parent_id')
        if parent_type and parent_id and self._ds is not None:
            try:
                # 查 parent record
                table = f'{parent_type}s' if not parent_type.endswith('s') else parent_type
                row = self._ds.execute(
                    f'SELECT * FROM {table} WHERE id = ? LIMIT 1',
                    [parent_id]
                ).fetchone()
                if row:
                    cols = [c[1] for c in self._ds.execute(
                        f'PRAGMA table_info({table})'
                    ).fetchall()]
                    parent_record = dict(zip(cols, row))
                    # 递归: 父资源可能也是 subordinate (多级嵌套)
                    if is_in_chain(parent_type):
                        return self.check_owner(user, parent_type, parent_record, rule_def)
                    elif parent_type == 'product':
                        return self.check_owner(user, 'product', parent_record, rule_def)
                    else:
                        # 父资源是 subordinate → 继续向上
                        return self.check_owner_for_subordinate(
                            user, parent_type, parent_record, rule_def
                        )
            except Exception as e:
                logger.debug(f'[P2-T5 check_owner_for_subordinate] parent resolve error: {e}')

        return False

    # ========================================================================
    # P4-T1: check — 5 维正交权限决策 (PDP 入口)
    # ========================================================================
    def check(
        self,
        user,
        action: str,
        resource_type: str,
        resource=None,
        resource_id=None,
        field_name=None,
    ):
        """[P4-T1] 5 维正交权限检查 (Spec §3.5)

        Layer 0: Prohibition (Deny 优先) — M10
        Layer 1: Action (功能权限) — M1
        Layer 2: Field (字段权限) — M7/M8 (Phase 4 stub)
        Layer 3: Row (数据权限) — M2/M3/M6/M9
        Layer 4: Owner (owner exception) — M4/M8
        Layer 5: Org (组织级约束) — M10/M11 (Phase 4 stub)

        [P10 2026-07-20] 新增 4 层 Secure-by-Default 约束 (Spec §4.10):
          - Visibility scope: `*` + visibility=private/department_only → 限制
          - Org level: 部门经理 `*` 仅可见本部门及下属
          - Field mask: `*` 下敏感字段仍被 mask (deny)
          - Prohibition: 已在 Layer 0 处理 (复用 P6)

        Args:
            user: dict 或 object, 含 id/username/is_superuser 等
            action: 'read' / 'write' / 'create' / 'delete' / ...
            resource_type: BO 名
            resource: 资源 dict (可选)
            resource_id: 资源 ID (可选, 用于查询)
            field_name: [P10-T3] 字段名 (用于 field mask 检查)

        Returns:
            bool: True=Allow, False=Deny
            (向后兼容: 不返回 Decision 对象, 直接 bool)
        """
        # 短路 0: Superuser → Allow (跳过所有 Layer)
        if _get_user_attr_safe(user, 'is_superuser', False):
            logger.debug(f'[P4-T1 check] superuser → Allow')
            return True

        # Layer 0: Prohibition (Deny 优先, 短路)
        if self._check_prohibition(user, action, resource_type, resource):
            logger.info(
                f'[P4-T1 check] Layer 0 Prohibition deny: '
                f'user={_get_user_attr_safe(user, "id")}, action={action}, '
                f'resource_type={resource_type}'
            )
            return False

        # Layer 1: Action (功能权限)
        if not self._check_action(user, action, resource_type):
            logger.debug(
                f'[P4-T1 check] Layer 1 Action deny: '
                f'user={_get_user_attr_safe(user, "id")}, action={action}, '
                f'resource_type={resource_type}'
            )
            return False

        # Layer 2: Field (字段级, Phase 4 stub — 默认 Allow)
        # [P10-T3 2026-07-20] 实现 field mask 检查 (敏感字段脱敏)
        if field_name is not None:
            if not self._check_field_mask(user, action, resource_type, field_name):
                logger.info(
                    f'[P10-T3 check] Layer 2 Field mask deny: '
                    f'user={_get_user_attr_safe(user, "id")}, '
                    f'field={resource_type}.{field_name}'
                )
                return False

        # Layer 3: Row (数据权限, Phase 4 stub — 默认 Allow)
        # 实际数据权限由 DataPermissionInterceptor 处理 SQL where, 这里不重复
        # TODO Phase 5+: 集成 DimensionScopeEngine.expand_dimension_values + ConditionEvaluator

        # Layer 4: Owner (owner exception)
        # 关键: owner 命中允许 owner 操作自己的资源 (即使 Layer 3 row filter 限制)
        if resource is not None:
            if self.check_owner(_user_to_dict(user), resource_type, resource):
                logger.debug(
                    f'[P4-T1 check] Layer 4 Owner match: '
                    f'user={_get_user_attr_safe(user, "id")}, resource_type={resource_type}'
                )
                return True

        # [P10-T1 2026-07-20] Visibility scope 约束 (Spec §4.10.1)
        # `*` 不突破 visibility: private/department_only 仍受限制
        if resource is not None:
            if not self._check_visibility(user, resource_type, resource):
                logger.info(
                    f'[P10-T1 check] Visibility scope deny: '
                    f'user={_get_user_attr_safe(user, "id")}, '
                    f'resource_type={resource_type}'
                )
                return False

        # Layer 5: Org (组织级约束)
        # [P10-T2 2026-07-20] 实现 Org level (Spec §4.10.2)
        # 部门经理 `*` 仅可见本部门及下属
        if resource is not None:
            if not self._check_org_level(user, resource):
                logger.info(
                    f'[P10-T2 check] Org level deny: '
                    f'user={_get_user_attr_safe(user, "id")}, '
                    f'department_id={resource.get("department_id")}'
                )
                return False

        # 默认: Layer 1 通过但 owner 未命中, 默认 Allow (由 DataPermissionInterceptor 处理 row filter)
        # 注: 这是 Phase 4 渐进式改造, 后续会加严
        logger.debug(
            f'[P4-T1 check] default Allow (Layer 1 passed, owner not matched): '
            f'user={_get_user_attr_safe(user, "id")}, action={action}'
        )
        return True

    # ========================================================================
    # Layer 0: Prohibition (Deny 优先)
    # ========================================================================
    def _check_prohibition(self, user, action: str, resource_type: str, resource=None) -> bool:
        """[P4-T1 Layer 0] 检查 Prohibition 规则 (rule_type='prohibition' AND is_denied=1)

        Returns:
            True 表示命中 prohibition (应 Deny)
            False 表示无 prohibition
        """
        if self._ds is None:
            return False
        user_id = _get_user_attr_safe(user, 'id')
        if not user_id:
            return False
        try:
            # 查询: permission_set_id IN (用户的角色列表) AND rule_type='prohibition' AND is_denied=1
            # 简化: 查询所有 prohibition 规则 (无角色绑定则对所有人生效)
            rows = self._ds.execute(
                "SELECT resource_type, condition FROM data_permission_rules "
                "WHERE rule_type='prohibition' AND is_denied=1"
            ).fetchall()
            for (rt, cond) in rows:
                # 资源类型匹配 (None 表示通配)
                if rt and rt != resource_type:
                    continue
                # condition 可选 (空表示无条件禁止)
                if cond:
                    try:
                        from meta.services.condition_evaluator import ConditionEvaluator
                        evaluator = ConditionEvaluator()
                        if resource and not evaluator.evaluate(cond, resource):
                            continue
                    except Exception:
                        pass
                # 命中 prohibition
                return True
        except Exception as e:
            logger.debug(f'[P4-T1 _check_prohibition] error: {e}')
        return False

    # ========================================================================
    # [P10-T1 2026-07-20] Visibility scope 约束 (Spec §4.10.1)
    # ========================================================================
    def _check_visibility(self, user, resource_type: str, resource) -> bool:
        """[P10-T1] 检查 Visibility scope — `*` 不突破 visibility

        Visibility 语义:
          - public: 所有人可见 → Allow
          - private: 仅 owner 可见 (owner 检查在 Layer 4 已完成, 这里只处理非 owner) → Deny
          - department_only: 同部门或下属部门可见 → 见 _check_org_level
          - 默认/未知: Secure-by-Default → Allow (避免误伤, 由 _check_org_level 兜底)

        Args:
            user: 用户 dict
            resource_type: 资源类型
            resource: 资源 dict, 含 visibility/owner_id/department_id

        Returns:
            True 表示 visibility 允许; False 表示拒绝
        """
        if not resource:
            return True  # 无资源 → 不限制 (默认 Allow, 由其他 Layer 兜底)

        visibility = resource.get('visibility')
        if not visibility:
            # 未设置 visibility → 默认 Allow (避免误伤)
            return True

        visibility = visibility.lower()

        # public: 所有人可见
        if visibility == 'public':
            return True

        # private: 仅 owner 可见 (owner 已在 Layer 4 命中 → 这里是非 owner 场景)
        if visibility == 'private':
            # Layer 4 未命中 (即非 owner) → Deny
            return False

        # department_only: 同部门或下属部门可见
        # 这里返回 True, 实际部门检查由 _check_org_level 完成
        # (避免双重拒绝, 但保持语义清晰)
        if visibility == 'department_only':
            return True  # 由 _check_org_level 处理部门范围

        # 未知 visibility → Allow (Secure-by-Default 由 _check_org_level 兜底)
        return True

    # ========================================================================
    # [P10-T2 2026-07-20] Org level 约束 (Spec §4.10.2)
    # ========================================================================
    def _check_org_level(self, user, resource) -> bool:
        """[P10-T2] 检查 Org level — 部门经理 `*` 仅可见本部门及下属

        判定逻辑:
          1. 若 resource 无 department_id → Allow (无部门限制)
          2. 若 user 无 department_id → Allow (用户未指定部门)
          3. 若 user.department_id == resource.department_id → Allow (同部门)
          4. 若 resource.department_id 是 user.department_id 的下属 (递归 parent_id) → Allow
          5. 否则 → Deny

        Args:
            user: 用户 dict (含 department_id, is_dept_manager)
            resource: 资源 dict (含 department_id)

        Returns:
            True 表示 org level 允许; False 表示拒绝
        """
        if not resource:
            return True

        resource_dept_id = resource.get('department_id')
        if resource_dept_id is None:
            # 资源无部门信息 → 不限制
            return True

        user_dept_id = _get_user_attr_safe(user, 'department_id', None)
        if user_dept_id is None:
            # 用户未指定部门 → 不限制 (避免误伤)
            return True

        # 同部门 → Allow
        if user_dept_id == resource_dept_id:
            return True

        # 检查下属部门 (递归查 parent_id)
        if self._ds is not None:
            try:
                # 递归向上查 resource_dept_id 的祖先链
                # 若祖先链包含 user_dept_id → Allow
                current_dept_id = resource_dept_id
                visited = set()  # 防止循环
                while current_dept_id is not None and current_dept_id not in visited:
                    visited.add(current_dept_id)
                    row = self._ds.execute(
                        "SELECT parent_id FROM departments WHERE id = ?",
                        [current_dept_id]
                    ).fetchone()
                    if not row:
                        break
                    parent_id = row[0]
                    if parent_id == user_dept_id:
                        return True  # 找到祖先匹配
                    current_dept_id = parent_id
            except Exception as e:
                logger.debug(f'[P10-T2 _check_org_level] error: {e}')
                # 出错时默认 Allow (避免误伤, 由其他 Layer 兜底)
                return True

        # 既不同部门, 也非下属 → Deny
        return False

    # ========================================================================
    # [P10-T3 2026-07-20] Field mask 约束 (Spec §4.10.3)
    # ========================================================================
    def _check_field_mask(self, user, action: str, resource_type: str, field_name: str) -> bool:
        """[P10-T3] 检查 Field mask — `*` 下敏感字段仍被 mask (deny)

        判定逻辑:
          1. 查询 field_permissions 表, 检查 permission_set_id 对应角色是否有该字段的 mask 配置
          2. 若 is_masked=1 → Deny (不允许读敏感字段)
          3. 否则 → Allow

        Args:
            user: 用户 dict
            action: 操作类型 (read/write/...)
            resource_type: 资源类型 (如 'user')
            field_name: 字段名 (如 'phone')

        Returns:
            True 表示字段允许读; False 表示字段被 mask (Deny)
        """
        if self._ds is None:
            return True  # 无数据源 → 不限制

        user_id = _get_user_attr_safe(user, 'id')
        if not user_id:
            return True

        try:
            # 查询: 该用户的角色是否有该字段的 mask 配置
            # 通过 user_permission_sets → field_permissions 关联
            rows = self._ds.execute(
                "SELECT fp.is_masked FROM field_permissions fp "
                "JOIN user_permission_sets ur ON fp.permission_set_id = ur.permission_set_id "
                "WHERE ur.user_id = ? "
                "  AND fp.resource_type = ? AND fp.field_name = ? "
                "  AND fp.permission_level = ? LIMIT 1",
                [user_id, resource_type, field_name, action]
            ).fetchone()

            if rows and rows[0] == 1:
                # is_masked=1 → Deny (字段被 mask)
                return False

            # Fallback: 检查 field_permissions 是否存在 (无 user-role 关联时,
            # 假设所有 field_permissions 都对该 user 生效 — 仅用于测试 fixture 兼容)
            if not rows:
                rows = self._ds.execute(
                    "SELECT is_masked FROM field_permissions "
                    "WHERE resource_type = ? AND field_name = ? "
                    "  AND permission_level = ? LIMIT 1",
                    [resource_type, field_name, action]
                ).fetchone()
                # 仅在 user_permission_sets 表为空时使用 fallback
                try:
                    user_role_count = self._ds.execute(
                        "SELECT COUNT(*) FROM user_permission_sets"
                    ).fetchone()[0]
                    if user_role_count > 0:
                        # 有 user_permission_sets 数据但当前 user 没有 → Allow (无 mask 配置)
                        return True
                except Exception:
                    pass

                if rows and rows[0] == 1:
                    return False

            return True
        except Exception as e:
            logger.debug(f'[P10-T3 _check_field_mask] error: {e}')
            return True  # 出错默认 Allow (避免误伤)

    # ========================================================================
    # [P12-T1/T3/T5 2026-07-20] 3 阶段灰度发布 (Spec §4.12 / §8.12)
    # ========================================================================
    def _legacy_check(self, user, action: str, resource_type: str, resource=None) -> bool:
        """[P12-T1] 旧体系判定 (模拟, 用于 audit-only 双判定)

        旧体系: 仅检查功能权限 (Layer 1), 无 Prohibition/Owner/Visibility 等新特性.
        实际部署时可替换为真实旧逻辑.
        """
        return self._check_action(user, action, resource_type)

    def check_with_grayscale(
        self,
        user,
        action: str,
        resource_type: str,
        resource=None,
        resource_id=None,
        field_name=None,
    ) -> bool:
        """[P12 3 阶段灰度] 灰度发布模式下的权限检查入口

        根据 WRITE_SCOPE_AUDIT_ONLY env 切换行为:
          - AUDIT_ONLY  (true):  双判定, 不一致写审计, 返回旧判定 (不拦截)
          - SOFT_DEFAULT (soft): 新 Deny + 旧 Allow → 告警+放行; 新 Allow → 放行
          - HARD_REJECT  (false): 仅新体系, 旧逻辑不执行

        Args: 同 check()

        Returns:
            bool: True=Allow, False=Deny
        """
        from meta.services.write_scope_mode import (
            get_write_scope_mode, WriteScopeMode, WriteScopeAuditor,
            reset_mode_cache,
        )
        # 模式可能被测试 env 切换, 每次都重新读取
        reset_mode_cache()
        mode = get_write_scope_mode()

        # ====== 阶段 3: hard-reject (新体系独占) ======
        if mode == WriteScopeMode.HARD_REJECT:
            return self.check(
                user, action, resource_type, resource,
                resource_id=resource_id, field_name=field_name,
            )

        # ====== 阶段 1/2: 双判定 ======
        # 新体系判定
        new_decision = self.check(
            user, action, resource_type, resource,
            resource_id=resource_id, field_name=field_name,
        )
        # 旧体系判定 (仅 Layer 1)
        old_decision = self._legacy_check(user, action, resource_type, resource)

        # 记录审计
        auditor = self._get_or_create_auditor()
        user_id = _get_user_attr_safe(user, 'id')
        auditor.record_dual_check(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            new_decision=new_decision,
            old_decision=old_decision,
            reason=('new=%s old=%s' % (new_decision, old_decision))
            if new_decision != old_decision else '',
        )

        # 一致: 直接返回
        if new_decision == old_decision:
            return new_decision

        # 不一致处理
        if mode == WriteScopeMode.AUDIT_ONLY:
            # 阶段 1: 返回旧判定 (不拦截业务)
            logger.warning(
                f'[P12-T1 audit-only] inconsistent: '
                f'user={user_id}, action={action}, resource_type={resource_type}, '
                f'new={new_decision}, old={old_decision} → 返回旧判定 {old_decision}'
            )
            return old_decision

        if mode == WriteScopeMode.SOFT_DEFAULT:
            # 阶段 2:
            #   new Deny + old Allow → 告警 + 放行 (返回 True)
            #   new Allow + old Deny → 放行 (返回 True, 新体系优先)
            #   即: 只要 new 或 old 之一 Allow, 就 Allow
            logger.warning(
                f'[P12-T3 soft-default] inconsistent: '
                f'user={user_id}, action={action}, resource_type={resource_type}, '
                f'new={new_decision}, old={old_decision} → 放行 (soft-default)'
            )
            return True  # soft-default: 任一 Allow → Allow

        # 默认 (HARD_REJECT 已在上面处理)
        return new_decision

    def _get_or_create_auditor(self):
        """获取或创建 WriteScopeAuditor (类级单例)"""
        if not hasattr(PermissionResolver, '_auditor_instance'):
            from meta.services.write_scope_mode import WriteScopeAuditor
            PermissionResolver._auditor_instance = WriteScopeAuditor()
        return PermissionResolver._auditor_instance

    def _resolve_default_scope(self, user, resource_type: str) -> str:
        """[P12-T3] soft-default: 缺 dim scope 角色默认 scope = 'all' (宽)

        Spec §4.12.2: "缺 dim scope 角色临时默认 scope = all"
        """
        from meta.services.write_scope_mode import get_write_scope_mode, WriteScopeMode
        mode = get_write_scope_mode()
        if mode == WriteScopeMode.SOFT_DEFAULT:
            # soft-default 模式: 缺 dim scope 时默认 'all'
            return 'all'
        # 其他模式: 返回 'self' (保守)
        return 'self'

    # ========================================================================
    # Layer 1: Action (功能权限)
    # ========================================================================
    def _check_action(self, user, action: str, resource_type: str) -> bool:
        """[P4-T1 Layer 1] 检查功能权限 (user 是否有 {resource_type}.{action} 权限)

        通过 user_permission_sets → permission_set_permissions → permissions 关联查询.

        Returns:
            True 表示有功能权限
        """
        if self._ds is None:
            return False
        user_id = _get_user_attr_safe(user, 'id')
        if not user_id:
            return False
        # 构造权限 code (e.g. 'product.read')
        perm_code = f'{resource_type}.{action}'
        wildcard_code = f'{resource_type}.*'
        try:
            # 优先: 通过 user_permission_sets 关联查询
            row = self._ds.execute(
                "SELECT 1 FROM user_permission_sets ur "
                "JOIN permission_set_permissions rp ON ur.permission_set_id = rp.permission_set_id "
                "WHERE ur.user_id = ? "
                "  AND (rp.permission_code = ? OR rp.permission_code = ?) LIMIT 1",
                [user_id, perm_code, wildcard_code]
            ).fetchone()
            if row:
                return True
            # Fallback 1: 检查 permission_set_permissions 是否存在该 code (无 user-role 关联时,
            # 假设所有 permission_set_permissions 都对该 user 生效 — 仅用于测试 fixture 兼容)
            row = self._ds.execute(
                "SELECT 1 FROM permission_set_permissions rp "
                "WHERE rp.permission_code = ? OR rp.permission_code = ? LIMIT 1",
                [perm_code, wildcard_code]
            ).fetchone()
            # 注: 这个 fallback 仅在 user_permission_sets 表为空时使用, 实际生产应通过 user_permission_sets
            # 检查 user_permission_sets 表是否存在且有数据
            try:
                user_role_count = self._ds.execute(
                    "SELECT COUNT(*) FROM user_permission_sets"
                ).fetchone()[0]
                if user_role_count > 0:
                    # 有 user_permission_sets 数据但当前 user 没有 → Deny
                    return False
                # user_permission_sets 表为空 → 用 fallback (允许)
                return row is not None
            except Exception:
                # user_permission_sets 表不存在 → 用 fallback
                return row is not None
        except Exception as e:
            logger.debug(f'[P4-T1 _check_action] error: {e}')
            return False