# -*- coding: utf-8 -*-
"""
[MODULE] write_scope_interceptor — 写路径数据范围拦截器 (v2.1)
[DESCRIPTION] 在 BO 框架 before_action 阶段对 crud_update/crud_delete/associate/dissociate
              动作做"写数据范围"校验, 跟 PermissionInterceptor (功能权限) 配合实现
              "双闸门" 模型 (SAP ACTVT+Org Level / Oracle Function+Data Policy).

[5 步校验]
  step 1: admin 跳过 (复用 is_admin)
  step 2: owner chain 直接放行 (含沿 HIERARCHY_CHAIN 向上追溯)
  step 3: dim scope 匹配 (复用 DimensionScopeEngine.derive_data_conditions)
  step 4: visibility 放行 (BO 有 visibility 字段 + 链上父 product 公开)
  step 5: 拒绝 (抛 WriteScopeDenied)

[性能优化]
  - 单一记录加载: 用一次 SQL JOIN 沿 chain 查 owner (避免 N+1)
  - role 派生缓存: 复用 DimensionScopeEngine LRU 缓存
  - role_ids 缓存: per-request 缓存 user_role_ids
  - 灰度开关: env var 读取, 无需重启

[灰度升级]
  WRITE_SCOPE_AUDIT_ONLY=true  → 仅 log + /_diagnostics 计数, 不抛异常
  WRITE_SCOPE_AUDIT_ONLY=false → 硬拒 (默认, 同 PermissionDenied 模式)
"""
import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from flask import g  # [V2.1 2026-06-22] 模块顶层导入, 便于 mock.patch 替换

from meta.core.interceptors.base import Interceptor
# [v1.1.5] 复用共享 chain owner resolver (跟 DataPermissionInterceptor 保持一致)
from meta.services.chain_owner_resolver import (
    resolve_root_owner as _chain_resolve_root_owner,
    resolve_root_product_id as _chain_resolve_root_product_id,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

# v2.1 业务 TBD-C: admin 默认不配 dim scope, 走 step 1 跳过
# v2.1 业务 TBD-I: 拦截器文案用中文
# v2.1 业务 TBD-J: SoD 留扩展点, 本次不实现

# [TBD-B] 关联操作字段名约定: 跟现有 object_id/record_id 一致
_ASSOCIATE_SRC_KEY = 'src_id'
_ASSOCIATE_DST_KEY = 'target_id'

# [性能] 链向上追溯: 用单次 SQL JOIN 查 owner, 避免 N+1
# HIERARCHY_CHAIN 顺序: product → version → domain → sub_domain (从顶层到底层)
# 注意: 沿 chain 向上追溯 owner 时, 字段名 = {parent_bo}_id
# 例: domain.product_id (直接) OR domain → version → product (chain)
_PARENT_FIELD_OVERRIDE = {
    # resource_bo → (direct_owner_field, parent_chain)
    # HIERARCHY_CHAIN 是 4 层, version/domain/sub_domain 没有 owner_id, 要沿 chain 找
    # [v2.1] 简化: 4 层 BO 都最终追到 product 查 owner
}

# [H14.1 2026-06-15] create 操作时, 通过 parent 加载 record (新 record 没 id)
#   例: 创建 domain 时, parent 是 version (从 context.params.version_id 取)
#   product create 是顶层 BO, 无 parent → 跳过 (让 functional perm 阶段处理)
_PARENT_FIELD_FOR_CREATE = {
    'version': ('product', 'product_id'),
    'domain': ('version', 'version_id'),
    'sub_domain': ('domain', 'domain_id'),
    # business_object/service_module 主 FK 是 sub_domain_id / service_module_id (DB schema 确认)
    # 不走 version, 走业务链追溯更准确
    'service_module': ('sub_domain', 'sub_domain_id'),
    'business_object': ('service_module', 'service_module_id'),
    # [FIX v1.2.30 2026-06-20] relationship create 通过 source_bo_id 的 BO chain 校验 dim scope
    'relationship': ('business_object', 'source_bo_id'),
    # [FIX v1.2.34 2026-06-21] annotation create 通过 target_type + target_id 校验 parent 的 dim scope
    #   annotation 是多态辅助对象, create 时 target_type + target_id 在 context.params 中
    #   但 target_type 是动态的, 无法静态映射, 所以这里用 target_id 作为 parent_id
    #   实际的 parent_type 在 _get_targets 运行时从 context.params.target_type 获取
    'annotation': ('_dynamic', 'target_id'),
}

# v2.1 业务 TBD-F: owner chain fallback 用 created_by 字段
_BIZ_BO_WITH_DIRECT_OWNER = {'product'}  # 只有 product 直接有 owner_id 字段
# 其他 BO (version, domain, sub_domain) 沿 chain 向上查 product.owner_id

# [FIX v1.2.37 2026-06-21] 父对象类型中文名映射 (用于 create 路径错误消息)
#   create 路径时, target 是 parent, 错误消息需区分 "自身对象(新增)" 与 "父对象(编码)"
_PARENT_TYPE_NAME_CN = {
    'product': '产品',
    'version': '版本',
    'domain': '领域',
    'sub_domain': '子领域',
    'service_module': '服务模块',
    'business_object': '业务对象',
    'relationship': '业务关系',
    'annotation': '备注信息',
}


class WriteScopeDenied(Exception):
    """[v2.1] 写 scope 拒绝异常 (status_code=403)

    [FIX v1.2.25 2026-06-20] 支持 business_key + object_type_name + side_info
    简化错误消息: `无写权限: <object_type_name>(<business_key>), 失败侧: <...>`
    """
    status_code = 403

    def __init__(self, object_type: str, target_id: int, user_id: int,
                 check_results: Dict[str, Any], side: str = 'primary',
                 business_key: Optional[str] = None,
                 object_type_name: Optional[str] = None,
                 side_info: Optional[str] = None):
        self.object_type = object_type
        self.target_id = target_id
        self.user_id = user_id
        self.check_results = check_results
        self.side = side
        self.business_key = business_key
        self.object_type_name = object_type_name
        self.side_info = side_info

        # 中文对象名 (默认 object_type, 如 "relationship")
        type_name = object_type_name or object_type
        # 业务键 (默认 target_id, 如 "21")
        key_value = business_key if business_key else str(target_id)

        msg = f'无写权限: {type_name}({key_value})'
        if side_info:
            msg += f', {side_info}'

        super().__init__(msg)


class ScopeViolationError(Exception):
    """[v2.0 2026-06-16] FK 字段写路径 dim scope 校验失败 (status_code=422)

    Spec: docs/specs/spec-write-scope-policy-v2.md FR-002/FR-003
    """
    status_code = 422

    def __init__(self, field: str = None, fields: List[str] = None,
                 value: Any = None, scope_policy: str = '',
                 scope_group: str = None, allowed_scope: str = ''):
        self.field = field
        self.fields = fields or ([field] if field else [])
        self.value = value
        self.scope_policy = scope_policy
        self.scope_group = scope_group
        self.allowed_scope = allowed_scope

        if scope_policy == 'enforce':
            msg = f"字段 {field} 的值 {value} 不在您的数据权限范围内"
        elif scope_policy == 'inherit':
            msg = f"字段 {field} 的值 {value} 不在父字段的权限范围内"
        elif scope_policy == 'or_bypass':
            msg = f"字段组 {scope_group} 中所有值都不在您的数据权限范围内"
        else:
            msg = f"字段 {field} 的值 {value} 不在数据权限范围内"

        super().__init__(msg)

    def to_response(self) -> Dict[str, Any]:
        """转换为 API 响应格式"""
        if self.scope_policy in ('enforce', 'inherit'):
            return {
                'success': False,
                'error_code': 'WRITE_SCOPE_VIOLATION',
                'message': str(self),
                'details': {
                    'field': self.field,
                    'value': self.value,
                    'scope_policy': self.scope_policy,
                    'allowed_scope': self.allowed_scope,
                    'fix_hint': '请选择您有权限的领域内的值',
                }
            }
        elif self.scope_policy == 'or_bypass':
            return {
                'success': False,
                'error_code': 'WRITE_SCOPE_VIOLATION',
                'message': str(self),
                'details': {
                    'fields': self.fields,
                    'scope_policy': 'or_bypass',
                    'scope_group': self.scope_group,
                    'allowed_scope': self.allowed_scope,
                    'fix_hint': '至少一个端点必须在您的数据权限范围内',
                }
            }
        return {
            'success': False,
            'error_code': 'WRITE_SCOPE_VIOLATION',
            'message': str(self),
        }


class ScopeViolationBatchError(Exception):
    """[v2.0 2026-06-16] 批量操作 FK scope 校验失败 (status_code=422)

    All-or-Nothing 策略: 任一记录失败则整个 batch 拒绝。
    Spec: docs/specs/spec-write-scope-policy-v2.md FR-006
    """
    status_code = 422

    def __init__(self, violations: List[Dict[str, Any]], total: int = 0):
        self.violations = violations
        self.total = total
        super().__init__(
            f"批量操作中 {len(violations)} 条记录超出数据权限范围"
        )

    def to_response(self) -> Dict[str, Any]:
        return {
            'success': False,
            'error_code': 'WRITE_SCOPE_VIOLATION_BATCH',
            'message': str(self),
            'details': {
                'total': self.total,
                'failed': len(self.violations),
                'violations': self.violations,
                'fix_hint': '请修正超出权限范围的字段值后重新提交',
            }
        }


# v2.1 灰度开关 (业务 TBD-D 走 3 阶段: audit → soft-default → hard-reject)
_WRITE_SCOPE_AUDIT_ONLY = os.environ.get('WRITE_SCOPE_AUDIT_ONLY', 'false').lower() in (
    'true', '1', 'yes',
)

# [V1.2.0 2026-06-15] 跨领域关系 functional perm 校验灰度开关
# Phase 1 (软警告): WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN=true
#   - 仅 log warn + /_diagnostics + X-Rel-Perm-Warning header, 不拒绝
#   - 用于收集 1 周生产数据, 确认无历史角色配置被误拒
# Phase 2 (硬拒绝): WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN=false (默认, 2026-06-15 切换)
#   - 真正拒绝 (return False from _check_relationship_ancestor_dim_scope)
#   - 此时 _check_dim_scope 返回 {'matched': False}, 触发 WriteScopeDenied
#
# Spec: .trae/specs/cross-domain-relationship-permission/spec.md
_WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN = os.environ.get(
    'WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN', 'false'
).lower() in ('true', '1', 'yes')

# [V2.1 2026-06-22] 写权限 × Dim Scope 联动校验开关
# 启用后, _check_dim_scope 在 role 循环前增加 perm 前置检查
# Spec: .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md
_WRITE_SCOPE_V2_1_PERM_CHECK = os.environ.get(
    'WRITE_SCOPE_V2_1_PERM_CHECK', 'false'
).lower() in ('true', '1', 'yes')

# [V2.1 2026-06-22] action → perm 后缀映射
_ACTION_TO_PERM_SUFFIX = {
    'crud_create': 'create',
    'crud_update': 'update',
    'crud_delete': 'delete',
    'associate': 'update',   # 关联动作算 update
    'dissociate': 'delete',  # 解除关联算 delete
}


class WriteScopeInterceptor(Interceptor):
    """
    [v2.1] 写路径数据范围拦截器

    priority=35 — 在 PermissionInterceptor(30) 之后, OwnerAutoPermissionInterceptor(96) 之前
    仅对 crud_update/crud_delete/associate/dissociate 生效
    """

    @property
    def name(self) -> str:
        return 'write_scope'

    @property
    def priority(self) -> int:
        return 35

    def should_execute(self, context: 'ActionContext') -> bool:
        # 仅对写操作生效, 读操作已有 DataPermissionInterceptor
        # 支持: crud_create / crud_update / crud_delete / associate / dissociate
        # [H14.1 2026-06-15] 加 crud_create — 之前 create 完全无数据范围检查
        return context.action in (
            'crud_create', 'crud_update', 'crud_delete',
            'associate', 'dissociate',
        )

    def before_action(self, context: 'ActionContext') -> None:
        from flask import g
        from meta.services.auth_middleware import is_admin

        # [FIX v1.2.20 2026-06-20] 支持 worker thread 路径
        # 1) 优先读 flask.g.current_user (BOFramework 主流程)
        # 2) fallback 读 context.user_info (ManageService → ActionExecutor 路径,
        #    由 ActionExecutor._check_write_scope 传入)
        # 3) 都拿不到 → 防御性 return
        user_info = None
        try:
            user_info = g.get('current_user') if hasattr(g, 'current_user') else None
        except RuntimeError:
            # worker thread 无 Flask app context
            user_info = None

        if not user_info:
            user_info = getattr(context, 'user_info', None)

        if not user_info:
            # PermissionInterceptor 已处理未登录
            return

        # [FIX H13 2026-06-15] JWT payload 字段是 user_id, 不是 id
        #   之前 user_info.get('id') 返 None, _check_target 拿不到 user_id
        #   → owner chain 永远 False + dim scope 永远空 → 所有写操作被拒
        user_id = user_info.get('user_id') or user_info.get('id')
        if not user_id:
            logger.warning('write_scope: user_info 缺少 user_id, 跳过 (防御性)')
            return

        # step 1: admin / '*' 跳过
        if is_admin(user_info):
            return
        permissions = user_info.get('permissions', [])
        if isinstance(permissions, set):
            permissions = list(permissions)
        if '*' in permissions:
            return

        # 遍历 target (主对象 + 关联操作 src/target)
        for side, target in self._get_targets(context):
            self._check_target(context, user_id, side, target)

        # [v2.0 2026-06-16] FK 字段写路径 dim scope 校验
        # Spec: docs/specs/spec-write-scope-policy-v2.md FR-002/FR-003/FR-005/FR-006
        self._validate_fk_scope_policies(context, user_id)

    def _get_targets(self, context: 'ActionContext') -> List[Tuple[str, Dict[str, Any]]]:
        """获取需要校验的 target 列表

        Returns:
            [(side, {'type': bo, 'id': int}), ...]
        """
        if context.action in ('associate', 'dissociate'):
            return [
                ('src', {'type': context.object_type,
                         'id': context.params.get(_ASSOCIATE_SRC_KEY)}),
                ('dst', {'type': context.object_type,
                         'id': context.params.get(_ASSOCIATE_DST_KEY)}),
            ]
        # [H14.1 2026-06-15] create 操作: 新 record 没 id, 用 parent (e.g. version_id) 加载
        #   例: 创建 domain 时, parent_type=version, parent_id 从 params.version_id 取
        #   顶层 BO (product) create 无 parent → 跳过 (让 functional perm 阶段处理)
        if context.action == 'crud_create':
            parent_spec = _PARENT_FIELD_FOR_CREATE.get(context.object_type)
            if not parent_spec:
                return []  # 顶层 BO create, 跳过拦截器
            parent_type, parent_field = parent_spec
            parent_id = context.params.get(parent_field)
            if not parent_id:
                return []  # 防御: 父 id 缺失, 跳过
            # [FIX v1.2.34 2026-06-21] annotation 的 parent_type 是动态的 (从 target_type 获取)
            if parent_type == '_dynamic':
                dynamic_parent_type = context.params.get('target_type')
                if not dynamic_parent_type:
                    return []  # 防御: target_type 缺失, 跳过
                parent_type = dynamic_parent_type
            return [('create_parent', {
                'type': parent_type,
                'id': parent_id,
                # [H14.1] 把 child type 带到 target, 给 _check_target 用
                'child_type': context.object_type,
            })]
        return [('primary', {'type': context.object_type, 'id': context.object_id})]

    def _check_target(self, context: 'ActionContext', user_id: int,
                      side: str, target: Dict[str, Any]) -> None:
        """检查单个 target 的写权限 (5 步校验)"""
        object_type = target['type']
        target_id = target['id']

        # [DEBUG v1.2.34] annotation 调试
        if object_type == 'annotation':
            logger.warning(f'[WriteScope ANNOTATION DEBUG] _check_target called: object_type={object_type}, target_id={target_id}, user_id={user_id}, side={side}')

        # [H14.1 2026-06-15] 移除 `if not target_id: return`
        #   create 路径由 _get_targets 把 parent_id 作为 target_id 传入, 有值
        #   之前没 create 拦截, 这里直接跳过; 现在 create 也走完整 step 2-5

        # 加载 record (含 owner_id)
        record = self._load_record(context, object_type, target_id)
        if not record:
            # [DEBUG v1.2.34] annotation 调试日志
            if object_type == 'annotation':
                logger.info(f'[WriteScope ANNOTATION] _load_record returned None for annotation({target_id})')
            raise WriteScopeDenied(
                object_type, target_id, user_id, {}, side
            )

        # [DEBUG v1.2.34] annotation 调试日志
        if object_type == 'annotation':
            logger.info(f'[WriteScope ANNOTATION] _load_record for annotation({target_id}): target_type={record.get("target_type")}, target_id={record.get("target_id")}')

        # [V1.1.8 2026-06-15] create 路径: _get_targets 已把 parent 作为 target
        # object_type = parent type, record = parent record
        # step 3-4 直接用 parent 的信息检查 (语义: parent 是否在 scope 内)

        # [V1.1.8] step 2 owner chain 检查已移至 OwnerChainInterceptor (priority=25)
        #   OwnerChainInterceptor 命中时已设置 context._owner_chain_match=True
        #   PermissionInterceptor (30) 会检查这个 flag 并放行
        #   写权限拦截器 (35) 仅做 dim scope + visibility 检查 (在非 owner 场景)
        #   注: 如果 owner 命中, PermissionInterceptor 放行后写权限拦截器仍会执行,
        #       但 dim scope + visibility 检查不会拒绝 owner 的写入 (因为 dim scope
        #       检查的是 "非 owner 用户的范围控制", owner 的检查已在上游完成)
        owner_match = bool(getattr(context, '_owner_chain_match', False))
        if owner_match:
            # owner 命中, 写权限拦截器放行 (不需再 dim scope + visibility)
            logger.debug(
                f'WriteScopeInterceptor: owner chain matched for {object_type}({target_id}), '
                f'skipping dim scope + visibility check'
            )
            return

        # step 3: dim scope 检查 (多 role 取并集)
        # [V1.1.8 2026-06-15] 写权限 dim scope 语义:
        #   - update/delete: 只匹配"直接声明的维度层级", 不匹配向上展开
        #   - create: 检查 parent 下是否有用户 scope 内的 child (允许在 scope 范围的 parent 下创建)
        # [FIX v1.2.34 2026-06-21] annotation create: 写权限跟随 parent derived,
        #   不走 _check_parent_dim_scope (检查 child), 而走 _check_ancestor_dim_scope (检查 parent 在 scope 内)
        # [V2.1 2026-06-22] 根据 action 自动决定 target_perm_suffix
        # Spec: .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md
        target_perm_suffix = _ACTION_TO_PERM_SUFFIX.get(context.action, 'update')

        is_annotation_create = (side == 'create_parent' and target.get('child_type') == 'annotation')
        if is_annotation_create:
            dim_check = self._check_dim_scope_for_annotation_create(
                context, object_type, record, user_id
            )
        else:
            dim_check = self._check_dim_scope(
                context, object_type, record, user_id,
                is_create=(side == 'create_parent'),
                target_perm_suffix=target_perm_suffix,
            )

        # step 4: visibility 检查 (BO 有 visibility 字段 + 公开)
        visibility_check = self._check_visibility(
            context, object_type, record
        )

        check_results = {
            'admin': False,
            'owner': owner_match,
            'dim_scope': dim_check['roles_checked'],
            'visibility': visibility_check.get('visibility', 'private'),
        }

        # [FIX v1.1.6 H13 2026-06-15] 写权限严格化: dim_scope + visibility 联动
        #   之前: owner OR dim_scope OR visibility 任一通过放行
        #     → dim_scope 派生命中的 record 即使 owner≠user 也能改 (例如 475 owner=admin,
        #       TEST333 配 dim scope 含 475, 改 475 通过 — 但 user 期望拒绝)
        #   修复: dim_scope 派生不能独立放行, 必须配对 visibility=public 才放行
        #   写权限 = owner chain 命中 OR (dim_scope 命中 AND visibility=public)
        if dim_check['matched'] and visibility_check['allow']:
            return

        # step 5: 全部不满足
        if _WRITE_SCOPE_AUDIT_ONLY:
            # 灰度阶段 1: 软警告 (log + /_diagnostics + header)
            self._log_warning(
                context, object_type, target_id, user_id, check_results, side
            )
            self._add_diagnostics(
                context, object_type, target_id, user_id, check_results, side
            )
            self._add_response_header(object_type, side, 'soft_warn_only')
            return  # 不抛异常, 放行
        else:
            # 阶段 2/3: 硬拒
            self._log_reject(
                context, object_type, target_id, user_id, check_results, side
            )
            # [FIX v1.2.25 2026-06-20] 传中文对象名 + 业务键 + 失败侧
            object_type_name = (
                context.meta_object.name
                if getattr(context, 'meta_object', None) else None
            )
            # [FIX v1.2.37 2026-06-21] create 路径错误消息优化:
            #   - business_key 优先从 params 获取自身对象编码 (Excel 已录入时显示实际编码)
            #   - side_info 标注父对象类型+编码, 区分父对象权限与自身对象权限
            #   - relationship create: side_info 标注失败侧 (源对象/目标对象)
            is_create_path = (side == 'create_parent')
            if is_create_path:
                # [FIX v1.2.38 2026-06-21] 优先从 params 获取自身对象编码
                # 用户反馈: Excel 中已录入编码时, 不应显示 "新增"
                self_code = None
                try:
                    params = context.params or {}
                    if object_type == 'relationship':
                        src = params.get('source_code')
                        tgt = params.get('target_code')
                        if src and tgt:
                            self_code = f'{src}→{tgt}'
                        elif src:
                            self_code = src
                    else:
                        self_code = params.get('code')
                except Exception:
                    self_code = None
                business_key = self_code if self_code else '新增'
                parent_type = target.get('type', '')
                child_type = target.get('child_type', '')
                parent_type_cn = _PARENT_TYPE_NAME_CN.get(parent_type, parent_type)
                parent_code = self._extract_business_key(parent_type, record)
                # relationship create: _rel_failed_side 在 _check_relationship_ancestor_dim_scope
                # 中设置 (update 路径), create 路径未设置, 需手动构造
                rel_failed_side = getattr(context, '_rel_failed_side', None)
                if rel_failed_side:
                    side_info = f'失败侧: {rel_failed_side}'
                elif child_type == 'relationship' and parent_code:
                    # relationship create: parent 是 source_bo, 标注为 "失败侧: 源对象"
                    side_info = f'失败侧: 源对象({parent_code})'
                elif parent_code:
                    side_info = f'父对象: {parent_type_cn}({parent_code})'
                else:
                    side_info = f'父对象: {parent_type_cn}(id={target_id})'
            else:
                business_key = self._extract_business_key(object_type, record)
                side_info = None
                if object_type == 'relationship':
                    failed_side = getattr(context, '_rel_failed_side', None)
                    if failed_side:
                        side_info = f'失败侧: {failed_side}'
            raise WriteScopeDenied(
                object_type, target_id, user_id, check_results, side,
                business_key=business_key,
                object_type_name=object_type_name,
                side_info=side_info,
            )

    # ========================================================================
    # [FR-003 v2.1] Owner chain 沿 HIERARCHY_CHAIN 向上追溯
    # 性能: 单次 SQL JOIN 查 product.owner_id (避免 N+1)
    # ========================================================================
    def _check_owner_chain(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], user_id: Optional[int]
    ) -> Dict[str, Any]:
        """[v2.1] 检查 record 是否属于 user (含沿 chain 向上)

        策略:
        - product: 直接查 product.owner_id == user_id
        - version/domain/sub_domain: 沿 chain 向上到 product, 查 product.owner_id
        - relationship/其他: [TBD-F fallback] 用 created_by 字段

        性能: 用单次 SQL JOIN 查 product.owner_id (避免 3 次单独查询)
        """
        if user_id is None:
            return {'matched': False, 'chain_root': None}

        # 路径 1: 直接 owner 字段
        direct_owner = record.get('owner_id')
        if direct_owner == user_id:
            return {
                'matched': True,
                'chain_root': {
                    'object_type': object_type, 'id': record.get('id'),
                    'owner_id': user_id,
                },
            }

        # 路径 2: 沿 HIERARCHY_CHAIN 向上追 product.owner_id
        # [性能] 单次 JOIN 查 product.owner_id
        product_owner = self._resolve_root_owner(context, object_type, record)
        if product_owner is not None and product_owner == user_id:
            return {
                'matched': True,
                'chain_root': {
                    'object_type': 'product',
                    'id': self._resolve_root_product_id(context, object_type, record),
                    'owner_id': user_id,
                },
            }

        # 路径 3: [TBD-F fallback] 用 created_by 字段
        created_by = record.get('created_by')
        if created_by == user_id:
            return {
                'matched': True,
                'chain_root': {
                    'object_type': object_type, 'id': record.get('id'),
                    'created_by': user_id, 'fallback': 'created_by',
                },
            }

        # 不匹配
        return {
            'matched': False,
            'chain_root': {
                'object_type': object_type, 'id': record.get('id'),
                'owner_id': direct_owner, 'root_owner_id': product_owner,
            },
        }

    @lru_cache(maxsize=2048)
    def _resolve_root_owner_cached(
        self, ds_id: int, object_type: str, target_id: int
    ) -> Optional[int]:
        """[v2.1 性能] LRU 缓存: 沿 chain 查 product.owner_id

        注: ds_id 用于 cache key (DataSource 通常是单例)
        """
        # 此方法由 _resolve_root_owner 包装, 实际查询在包装方法
        return None  # 占位, 实际不会调用此方法

    def _resolve_root_owner(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Optional[int]:
        """[v1.1.5] 单次 SQL 查询: 沿 HIERARCHY_CHAIN 查 product.owner_id

        性能优化: 用 LEFT JOIN 一次性查完, 避免 N+1

        [v1.1.5 2026-06-15] 委托给共享 chain_owner_resolver (跟 DataPermissionInterceptor 保持一致)

        Returns:
            product.owner_id (int) 或 None (无 product 父链)
        """
        if object_type in _BIZ_BO_WITH_DIRECT_OWNER:
            return record.get('owner_id')
        if not record.get('id'):
            return None
        return _chain_resolve_root_owner(context.data_source, object_type, record['id'])

    def _resolve_root_product_id(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Optional[int]:
        """[v1.1.5] 沿 HIERARCHY_CHAIN 查 product.id (用于 chain_root 报告)"""
        if object_type == 'product':
            return record.get('id')
        if not record.get('id'):
            return None
        return _chain_resolve_root_product_id(context.data_source, object_type, record['id'])

    # ========================================================================
    # [FR-002 step 3] dim scope 多 role 取并集
    # ========================================================================
    def _check_dim_scope(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], user_id: int,
        is_create: bool = False,
        target_perm_suffix: str = 'update',
    ) -> Dict[str, Any]:
        """[v2.1] 检查 record 是否在用户任一 role 的 dim scope 内

        性能: 复用 DimensionScopeEngine 缓存

        [V1.1.8 2026-06-15] 写权限 dim scope 语义:
          - 读权限: derive_data_conditions 包含向上展开, 用于过滤查询结果
          - 写权限 (update/delete): 只匹配"直接声明的维度层级", 不匹配向上展开
            例: 角色 5970 配 domain=[703]
              → update domain 703: domain 在直接声明中 → matched ✓
              → update product 475: product 不在直接声明中 (向上展开) → not matched ✓
          - 写权限 (create): 检查 parent 下是否有用户 scope 内的 child
            例: create domain under version 764
              → version 764 下有 domain 703 (在 scope 内) → 允许创建

        [V2.1 2026-06-22] 写权限 × Dim Scope 联动校验:
          - 灰度开关 _WRITE_SCOPE_V2_1_PERM_CHECK=true 时启用
          - dim scope 派生前, 先校验 role 是否有 target_perm (object_type:target_perm_suffix)
          - 无 perm 的 role 直接跳过 (skipped='missing_functional_perm')
          - Spec: .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md

        Args:
            target_perm_suffix: 'create'/'update'/'delete' (默认 'update')
        """
        role_ids = self._get_user_role_ids(context, user_id)
        if not role_ids:
            return {'matched': False, 'roles_checked': []}

        # [V2.1 2026-06-22] target_perm: 'service_module:update' 等
        target_perm = f'{object_type}:{target_perm_suffix}'

        roles_checked = []
        try:
            from meta.services.dimension_scope_engine import DimensionScopeEngine
            engine = DimensionScopeEngine(context.data_source)
        except Exception as e:
            logger.debug(f'load DimensionScopeEngine failed: {e}')
            return {'matched': False, 'roles_checked': []}

        for role_id in role_ids:
            try:
                # [V2.1.2 2026-06-22] 前置 perm 检查: 检查该 ROLE 自身是否有 target perm
                # 修复 V2.1 bug: 之前用 user 全量 perm, 导致 role A (read) + role B (write)
                # 情况下, role A 的 dim scope 命中会被误放行
                # V2.1.2: 查询 role_permissions JOIN permissions WHERE role_id = ?
                if _WRITE_SCOPE_V2_1_PERM_CHECK:
                    role_perm_codes = self._get_role_perm_codes(context, role_id)
                    if not self._role_has_perm(role_id, target_perm, role_perm_codes):
                        roles_checked.append({
                            'role_id': role_id,
                            'cond': None,
                            'skipped': 'missing_functional_perm',
                            'perm_required': target_perm,
                        })
                        logger.debug(
                            f'_check_dim_scope: role={role_id} missing {target_perm}, '
                            f'skipping dim scope check'
                        )
                        continue

                # [V1.1.8] 写权限: 只用直接声明的维度
                expanded = engine.expand_dimension_values(role_id)
                # 检查 object_type 是否在直接声明的维度中
                if object_type in expanded and expanded[object_type]:
                    # 直接声明: 用 derive_data_conditions 的 cond 匹配
                    conditions = engine.derive_data_conditions(role_id)
                    cond_expr = conditions.get(object_type)
                    role_check_entry = {
                        'role_id': role_id, 'cond': cond_expr,
                        'direct_dim': True, 'dim_code': object_type,
                    }
                    if _WRITE_SCOPE_V2_1_PERM_CHECK:
                        role_check_entry['perm_check'] = 'passed'
                    roles_checked.append(role_check_entry)
                    if cond_expr and self._record_matches_cond(
                        context, object_type, record, cond_expr
                    ):
                        return {'matched': True, 'roles_checked': roles_checked}
                elif is_create:
                    # [V1.1.8] create 路径: object_type 是 parent, 检查其下是否有 scope 内的 child
                    parent_match = self._check_parent_dim_scope(
                        context, object_type, record, expanded, engine, role_id
                    )
                    parent_entry = {
                        'role_id': role_id, 'cond': None,
                        'direct_dim': False, 'parent_match': parent_match,
                    }
                    if _WRITE_SCOPE_V2_1_PERM_CHECK:
                        parent_entry['perm_check'] = 'passed'
                    roles_checked.append(parent_entry)
                    if parent_match:
                        return {'matched': True, 'roles_checked': roles_checked}
                else:
                    # [V1.1.8] update/delete 路径: 向下展开 — 检查 record 的祖先是否在 scope 内
                    # 例: sub_domain(138) 的 domain_id=703, domain 703 在 scope 内 → matched
                    ancestor_match = self._check_ancestor_dim_scope(
                        context, object_type, record, expanded
                    )
                    ancestor_entry = {
                        'role_id': role_id, 'cond': None,
                        'direct_dim': False, 'ancestor_match': ancestor_match,
                    }
                    if _WRITE_SCOPE_V2_1_PERM_CHECK:
                        ancestor_entry['perm_check'] = 'passed'
                    roles_checked.append(ancestor_entry)
                    if ancestor_match:
                        return {'matched': True, 'roles_checked': roles_checked}
            except Exception as e:
                logger.debug(f'derive_data_conditions failed for role {role_id}: {e}')
                continue

        return {'matched': False, 'roles_checked': roles_checked}

    # [V2.1 2026-06-22] 写权限 × Dim Scope 联动校验 helper 方法
    def _get_user_perm_codes(self, context: 'ActionContext') -> set:
        """[V2.1] 获取用户所有 perm code (from g.current_user.permissions)

        Spec: .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md
        Permission 来源: JWT token 注入到 g.current_user.permissions (auth_middleware)

        [DEPRECATED V2.1.2] 应改用 _get_role_perm_codes (role-specific) 而非 user-wide
        """
        try:
            if hasattr(g, 'current_user') and g.current_user:
                # per-request 缓存
                cached = g.current_user.get('_perm_codes_cache')
                if cached is not None:
                    return cached
                perms = g.current_user.get('permissions', [])
                if isinstance(perms, set):
                    perm_set = perms
                elif isinstance(perms, (list, tuple)):
                    perm_set = set(perms)
                else:
                    perm_set = set()
                g.current_user['_perm_codes_cache'] = perm_set
                return perm_set
        except Exception:
            pass
        return set()

    def _get_role_perm_codes(self, context: 'ActionContext', role_id: int) -> set:
        """[V2.1.2] 获取指定 role 的 perm codes (role-specific, NOT user-wide)

        修复 V2.1 bug: 之前用 _get_user_perm_codes (user 全量), 导致
        multi-role 用户的 read-only role 的 dim scope 命中会被误放行.

        Spec: .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md
        数据源: role_permissions JOIN permissions WHERE role_id = ?

        [CACHE] per-request 缓存在 context._role_perm_codes_cache[role_id]
        """
        try:
            # per-request cache
            cache = getattr(context, '_role_perm_codes_cache', None)
            if cache is None:
                cache = {}
                context._role_perm_codes_cache = cache
            if role_id in cache:
                return cache[role_id]

            # 查询 role 自身的 perm codes
            ds = getattr(context, 'data_source', None)
            if ds is None:
                cache[role_id] = set()
                return set()

            rows = ds.execute(
                "SELECT p.code FROM permissions p "
                "JOIN role_permissions rp ON p.id = rp.permission_id "
                "WHERE rp.role_id = ?",
                [role_id],
            ).fetchall()
            codes = {row[0] for row in rows}
            cache[role_id] = codes
            return codes
        except Exception as e:
            logger.debug(f'_get_role_perm_codes(role_id={role_id}) failed: {e}')
            return set()

    def _role_has_perm(
        self, role_id: int, target_perm: str, perm_codes: set
    ) -> bool:
        """[V2.1] 检查 perm_codes 中是否含 target_perm (role-specific 或 user-wide)

        Args:
            role_id: role ID (保留用于 logging)
            target_perm: 'service_module:update' 等
            perm_codes: 候选 perm code 集合 (V2.1.2 应为 role-specific)

        支持通配:
          - '*' (admin 通配)
          - 'service_module:update' (精确)
          - 'service_module:*' (object 通配)
          - 'service_module' (无后缀简写)

        Spec: .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md
        """
        if not perm_codes:
            return False
        if '*' in perm_codes:
            return True
        if target_perm in perm_codes:
            return True
        obj_type = target_perm.split(':', 1)[0]
        if f'{obj_type}:*' in perm_codes:
            return True
        if obj_type in perm_codes:
            return True
        return False

    def _check_dim_scope_for_annotation_create(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], user_id: int
    ) -> Dict[str, Any]:
        """[FIX v1.2.34 2026-06-21] annotation create 的 dim scope 检查

        annotation 是辅助对象, 写权限跟随 parent derived.
        create 时, object_type 是 parent 类型 (如 service_module),
        检查 parent 是否在用户的 dim scope 内 (和 update 一样的 ancestor 逻辑).

        不走 _check_parent_dim_scope (语义: parent 下是否有 scope 内的 child),
        因为 annotation 不是 HIERARCHY_CHAIN 的 child.
        """
        role_ids = self._get_user_role_ids(context, user_id)
        if not role_ids:
            return {'matched': False, 'roles_checked': []}

        roles_checked = []
        try:
            from meta.services.dimension_scope_engine import DimensionScopeEngine
            engine = DimensionScopeEngine(context.data_source)
        except Exception as e:
            logger.debug(f'load DimensionScopeEngine failed: {e}')
            return {'matched': False, 'roles_checked': []}

        for role_id in role_ids:
            try:
                expanded = engine.expand_dimension_values(role_id)
                # 检查 parent 对象是否在直接声明的维度中
                if object_type in expanded and expanded[object_type]:
                    conditions = engine.derive_data_conditions(role_id)
                    cond_expr = conditions.get(object_type)
                    roles_checked.append({
                        'role_id': role_id, 'cond': cond_expr,
                        'direct_dim': True, 'dim_code': object_type,
                    })
                    if cond_expr and self._record_matches_cond(
                        context, object_type, record, cond_expr
                    ):
                        return {'matched': True, 'roles_checked': roles_checked}
                # 检查 parent 对象的祖先是否在 scope 内 (和 update 逻辑一致)
                ancestor_match = self._check_ancestor_dim_scope(
                    context, object_type, record, expanded
                )
                roles_checked.append({
                    'role_id': role_id, 'cond': None,
                    'direct_dim': False, 'ancestor_match': ancestor_match,
                })
                if ancestor_match:
                    return {'matched': True, 'roles_checked': roles_checked}
            except Exception as e:
                logger.debug(f'derive_data_conditions failed for role {role_id}: {e}')
                continue

        return {'matched': False, 'roles_checked': roles_checked}

    def _check_ancestor_dim_scope(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], expanded: Dict[str, set],
    ) -> bool:
        """[V1.1.8] 向下展开: 检查 record 的祖先是否在用户直接 dim scope 内

        语义: 用户配 domain=[703], update sub_domain(138) 时
              sub_domain 不在直接声明中, 但 sub_domain 的 domain_id=703
              而 domain 703 在 scope 内 → 允许

        安全性: 向下展开是安全的 (只扩大范围到已声明维度的子级)
                向上展开不安全 (domain=[703] 不应推导出 product=[475] 写权限)

        [V1.1.8+] 扩展支持 relationship: 沿 source_bo_id/target_bo_id 业务链反推
        """
        # [V1.1.8+] relationship 业务链反推
        if object_type == 'relationship':
            return self._check_relationship_ancestor_dim_scope(
                context, record, expanded
            )

        # [FIX v1.2.34 2026-06-21] annotation 写权限跟随 parent derived
        #   annotation 是多态辅助对象, 通过 target_type + target_id 关联到架构对象
        #   写权限应继承自其关联的 parent 对象 (如 service_module, business_object 等)
        #   逻辑: 找到 parent 对象, 加载其 record, 递归检查 parent 的 dim scope
        # [FIX v1.2.36 2026-06-21] 优先使用 context.params 中的 target_type/target_id
        #   场景: annotation update 时, Excel 中有 target_code='BO_SALES_INV',
        #   _pre_resolve_foreign_keys 已把 target_code 解析为 target_id 写回 params.
        #   但 _load_record 加载的 DB record 中 target_id 可能是旧值 (如 orphan id=154).
        #   应优先用 params 中的新 target_id 检查权限, 否则 orphan annotation 会绕过检查.
        if object_type == 'annotation':
            # 优先从 params 获取 (经 _pre_resolve_foreign_keys 解析后的最新值)
            params_target_type = context.params.get('target_type') if hasattr(context, 'params') else None
            params_target_id = context.params.get('target_id') if hasattr(context, 'params') else None
            # 处理 "code - name" 格式
            if isinstance(params_target_type, str) and ' - ' in params_target_type:
                params_target_type = params_target_type.split(' - ')[0].strip()
            # fallback 到 record (DB 中的值)
            target_type = params_target_type or record.get('target_type')
            target_id = params_target_id or record.get('target_id')
            if not target_type or not target_id:
                logger.info(f'[WriteScope ANNOTATION] no target_type/target_id, allowing (no parent to check)')
                return True  # 无 parent 信息, 无法检查, 放行
            # 加载 parent 对象的 record
            parent_record = self._load_record(context, target_type, int(target_id))
            if not parent_record:
                # parent 不存在 (数据不一致), 无法验证权限
                # 不应因此阻止 annotation 的写操作 — 这是数据问题, 不是权限问题
                logger.info(f'[WriteScope ANNOTATION] parent {target_type}({target_id}) not found, allowing (orphan annotation)')
                return True
            logger.info(f'[WriteScope ANNOTATION] checking parent {target_type}({target_id}) for annotation({record.get("id")})')
            # 递归检查 parent 的 dim scope
            #   如果 parent 是 relationship, _check_ancestor_dim_scope 会走 relationship 分支
            #   如果 parent 是 service_module/business_object, 会走 EXT_CHAIN 分支
            #   如果 parent 是 sub_domain/domain, 会走 HIERARCHY_CHAIN 分支
            return self._check_ancestor_dim_scope(context, target_type, parent_record, expanded)

        from meta.services.dimension_scope_engine import HIERARCHY_CHAIN, EXTENDED_CHAIN_ANCHOR, EXTENDED_CHAIN_PARENT
        from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP, PARENT_FIELD_MAP

        current_id = record.get('id')
        if not current_id:
            return False

        # [v1.2.30 2026-06-20] 非 HIERARCHY_CHAIN 的 BO (service_module/business_object):
        #   沿 EXTENDED_CHAIN_PARENT 递归步进, 每一跳查 parent_field 直到进入 HIERARCHY_CHAIN
        #   例: business_object(468) → service_module_id=138 → service_module(138)
        #         → sub_domain_id=138 → sub_domain(138) → domain_id=703
        #         → domain 703 in expanded['domain'] → return True
        #     service_module(886) → sub_domain_id=148 → sub_domain(148) → domain_id=703
        #         → domain 703 in expanded['domain'] → return True
        # parent_dim 写死映射 (BO→SM, SM→SD), 因 BO/SM 都不在 HIERARCHY_CHAIN 中
        _EXT_TO_PARENT_DIM = {
            'business_object': 'service_module',
            'service_module': 'sub_domain',
        }
        if object_type in EXTENDED_CHAIN_PARENT:
            visited = 0
            while visited < 10 and object_type not in HIERARCHY_CHAIN:
                parent_field = EXTENDED_CHAIN_PARENT.get(object_type)
                own_table = RESOURCE_TABLE_MAP.get(object_type)
                if not parent_field or not own_table:
                    logger.info(f'[WriteScope EXT_CHAIN] ABORT: no parent_field or own_table for {object_type}')
                    return False
                row = context.data_source.execute(
                    f"SELECT {parent_field} FROM {own_table} WHERE id = ?",
                    [current_id]
                ).fetchone()
                if not row or not row[0]:
                    logger.info(f'[WriteScope EXT_CHAIN] ABORT: no parent found for {object_type}({current_id}).{parent_field}')
                    return False
                parent_dim = _EXT_TO_PARENT_DIM.get(object_type)
                if not parent_dim:
                    logger.info(f'[WriteScope EXT_CHAIN] ABORT: no parent_dim mapping for {object_type}')
                    return False
                old_id = current_id
                current_id = int(row[0])
                object_type = parent_dim
                visited += 1
                logger.info(f'[WriteScope EXT_CHAIN] step {visited}: {object_type}({current_id}) from {own_table}({old_id}).{parent_field}')
            # 跳出 while: object_type 现在是 HIERARCHY_CHAIN 内的 dim (sub_domain)
            if object_type not in HIERARCHY_CHAIN:
                logger.info(f'[WriteScope EXT_CHAIN] ABORT: object_type={object_type} not in HIERARCHY_CHAIN after {visited} steps')
                return False  # visited 用尽仍未进入 chain, 异常

        obj_dim = object_type

        # 找 object_type (或锚点 dim) 在 chain 中的位置
        try:
            obj_idx = HIERARCHY_CHAIN.index(obj_dim)
        except ValueError:
            logger.info(f'[WriteScope ANCESTOR] obj_dim={obj_dim} not in HIERARCHY_CHAIN')
            return False

        # 沿 chain 向上找, 检查每个祖先是否在直接声明的维度中
        for ancestor_idx in range(obj_idx - 1, -1, -1):
            ancestor_dim = HIERARCHY_CHAIN[ancestor_idx]
            if ancestor_dim not in expanded or not expanded[ancestor_dim]:
                continue

            ancestor_ids = expanded[ancestor_dim]

            # 从 current_id (锚点 id) 沿 chain 向上逐步查到 ancestor_dim
            step_id = current_id
            for step_idx in range(obj_idx, ancestor_idx, -1):
                step_dim = HIERARCHY_CHAIN[step_idx]
                step_parent_field = PARENT_FIELD_MAP.get(step_dim)
                step_table = RESOURCE_TABLE_MAP.get(step_dim)
                if not step_parent_field or not step_table:
                    break
                row = context.data_source.execute(
                    f"SELECT {step_parent_field} FROM {step_table} WHERE id = ?",
                    [step_id]
                ).fetchone()
                if row and row[0]:
                    step_id = int(row[0])
                else:
                    break
            else:
                if step_id in ancestor_ids:
                    return True

        return False

    def _check_relationship_ancestor_dim_scope(
        self, context: 'ActionContext', record: Dict[str, Any],
        expanded: Dict[str, set]
    ) -> bool:
        """[V1.1.8+] 沿 relationship 的 source_bo_id/target_bo_id 业务链反推 ancestor

        语义: 用户配 domain=[703], update relationship(135) 时
              relationship 不在 HIERARCHY_CHAIN 中, 但其 source_bo_id 链上
              有 domain 703 → 允许

        链: business_objects → service_modules → sub_domains → domains → versions → products
        一次 SQL JOIN 拿到 source/target BO 的各级 ancestor id, 然后比对 expanded

        [V1.1.8+] 注: record 可能含 source_bo_id/target_bo_id (导入/update 场景 FK 解析后)
        优先使用 record 中的值; 若 record 中无, 则从数据库查询

        [FIX v1.2.31 2026-06-21] 导入场景: record 中 source_bo_id 是 FK 解析后的新值
        (如 source_bo_id=468, DOM=703), 而数据库旧值可能是不同 domain 的同名 BO
        (如 source_bo_id=2, DOM=1). 权限检查应基于"写入后的值"

        [V1.2.0 2026-06-15] 跨领域关系 functional perm 校验 (OR-edit 写权限的"写 gate"):
        - 在 dim scope 反推前, 先校验 user 是否有 business_object:edit/:update/:delete 任一
        - 这是 OR-edit 语义的关键: 端点必须可编辑
        - Phase 1 (默认): 仅 log warn, 不拒绝 (兼容历史配置)
        - Phase 2: 硬拒绝
        - Spec: .trae/specs/cross-domain-relationship-permission/spec.md

        [FIX v1.2.40 2026-06-21] delete 权限同时检查源和目标
        - create/update: 仅检查 source_bo_id 链 (目标允许外域, relationship.yaml 配置)
        - delete: 同时检查 source_bo_id 和 target_bo_id 链 (两端都必须在 scope 内)
        - 原因: 删除关系影响两端, 需要两端都有写权限
        - 参考: 用户反馈 "实例的删除权限难道不是依赖源和目标来的吗, 参考写的权限"
        """
        # [V1.2.0] Functional perm gate: 防止"只读 user 误创关系"
        # 仅对 relationship 操作生效 (object_type 在 _check_dim_scope 调用前已路由到此)
        # 注意: admin / '*' 通配 在 before_action step 1 已跳过, 此处不需要再校验
        # 依赖注入 user_info: 让 helper 接受参数, 避免直接 fetch flask.g
        user_info = self._fetch_user_info_for_rel_perm()
        if not self._user_has_bo_edit_perm_for_relationship(user_info):
            if _WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN:
                # Phase 1: 软警告 — log + diagnostics + header, 不拒绝
                self._log_rel_func_perm_warning(context, record, 'soft_warn', user_info)
                # 软警告模式: 继续后续 dim scope 反推 (不 return False)
            else:
                # Phase 2: 硬拒绝
                self._log_rel_func_perm_warning(context, record, 'hard_reject', user_info)
                return False

        target_id = record.get('id')
        if not target_id:
            return False

        # [FIX v1.2.31 2026-06-21] 优先使用 context.params 中的 source_bo_id/target_bo_id
        # 导入/update 场景: context.params 包含 FK 解析后的新值 (如 source_bo_id=468, DOM=703)
        # record (从 _load_record 加载) 是数据库旧值, 可能指向不同 domain 的同名 BO
        # (如 source_bo_id=2, DOM=1). 权限检查应基于"写入后的值"而非"写入前的旧值"
        params = getattr(context, 'params', {}) or {}
        src_bo_id = params.get('source_bo_id')
        tgt_bo_id = params.get('target_bo_id')
        src_code = None
        tgt_code = None

        # 如果 context.params 中没有, 尝试 record (从 _load_record 加载, 含 DB 旧值)
        if src_bo_id is None:
            src_bo_id = record.get('source_bo_id')
        if tgt_bo_id is None:
            tgt_bo_id = record.get('target_bo_id')

        # 如果仍然没有, 从数据库查询
        if src_bo_id is None and tgt_bo_id is None:
            try:
                row = context.data_source.execute(
                    """SELECT r.source_bo_id, r.target_bo_id,
                              COALESCE(sbo.code, 'BO#' || r.source_bo_id) AS source_code,
                              COALESCE(tbo.code, 'BO#' || r.target_bo_id) AS target_code
                       FROM relationships r
                       LEFT JOIN business_objects sbo ON sbo.id = r.source_bo_id
                       LEFT JOIN business_objects tbo ON tbo.id = r.target_bo_id
                       WHERE r.id = ?""",
                    [target_id]
                ).fetchone()
                if not row:
                    return False
                src_bo_id, tgt_bo_id, src_code, tgt_code = row
            except Exception as e:
                logger.debug(f'_check_relationship_ancestor DB query failed: {e}')
                return False
        else:
            # 有值, 补查 code 用于 failed side 信息
            try:
                if src_bo_id:
                    src_row = context.data_source.execute(
                        "SELECT code FROM business_objects WHERE id = ?", [int(src_bo_id)]
                    ).fetchone()
                    src_code = src_row[0] if src_row else f'BO#{src_bo_id}'
                if tgt_bo_id:
                    tgt_row = context.data_source.execute(
                        "SELECT code FROM business_objects WHERE id = ?", [int(tgt_bo_id)]
                    ).fetchone()
                    tgt_code = tgt_row[0] if tgt_row else f'BO#{tgt_bo_id}'
            except Exception as e:
                logger.debug(f'_check_relationship_ancestor code lookup failed: {e}')

        # [FIX v1.2.40 2026-06-21] delete 路径同时检查源和目标
        # create/update: 仅检查 source_bo_id 链 (目标允许外域)
        # delete: 同时检查 source_bo_id 和 target_bo_id 链 (两端都必须在 scope 内)
        is_delete_path = (context.action == 'crud_delete')
        bo_ids_to_check = []
        if src_bo_id:
            bo_ids_to_check.append(('source', int(src_bo_id)))
        if is_delete_path and tgt_bo_id:
            bo_ids_to_check.append(('target', int(tgt_bo_id)))

        if not bo_ids_to_check:
            return False

        # 一次 SQL JOIN 拿到所有 BO 沿业务链的各级 ancestor id
        bo_ids = [bid for _, bid in bo_ids_to_check]
        placeholders = ','.join('?' * len(bo_ids))
        try:
            rows = context.data_source.execute(
                f'''
                SELECT bo.id,
                       sm.sub_domain_id,
                       sd.domain_id,
                       d.version_id,
                       v.product_id
                FROM business_objects bo
                LEFT JOIN service_modules sm ON sm.id = bo.service_module_id
                LEFT JOIN sub_domains sd ON sd.id = sm.sub_domain_id
                LEFT JOIN domains d ON d.id = sd.domain_id
                LEFT JOIN versions v ON v.id = d.version_id
                WHERE bo.id IN ({placeholders})
                ''',
                bo_ids
            ).fetchall()
        except Exception as e:
            logger.debug(f'_check_relationship_ancestor query failed: {e}')
            return False

        # 检查每个 BO 链上每一级 ancestor dim 是否在 expanded scope 内
        ancestor_field_to_dim = {
            'sub_domain_id': 'sub_domain',
            'domain_id': 'domain',
            'version_id': 'version',
            'product_id': 'product',
        }
        # [FIX v1.2.40] 记录每端的匹配结果
        # - create/update: 只需 source 匹配
        # - delete: source 和 target 都必须匹配
        side_matches = {}  # {'source': bool, 'target': bool}
        for side, bo_id in bo_ids_to_check:
            side_matches[side] = False
            for row in rows:
                if row[0] != bo_id:
                    continue
                for field, dim in ancestor_field_to_dim.items():
                    ancestor_id = row[['sub_domain_id', 'domain_id', 'version_id', 'product_id'].index(field) + 1]
                    if ancestor_id and dim in expanded and expanded[dim] and ancestor_id in expanded[dim]:
                        side_matches[side] = True
                        break
                break  # 每个 bo_id 只有一行

        # 判定最终结果
        if is_delete_path:
            # delete: source 和 target 都必须在 scope 内
            src_ok = side_matches.get('source', False)
            tgt_ok = side_matches.get('target', False)
            if src_ok and tgt_ok:
                return True
            # 设置失败侧信息用于错误消息
            if not src_ok and not tgt_ok:
                context._rel_failed_side = f'源对象({src_code})和目标对象({tgt_code})'
            elif not src_ok:
                context._rel_failed_side = f'源对象({src_code})'
            else:
                context._rel_failed_side = f'目标对象({tgt_code})'
            return False
        else:
            # create/update: 只需 source 在 scope 内
            if side_matches.get('source', False):
                return True
            context._rel_failed_side = f'源对象({src_code})'
            return False

    # ========================================================================
    # [V1.2.0 2026-06-15] 跨领域关系 functional perm 校验辅助方法
    # Spec: .trae/specs/cross-domain-relationship-permission/spec.md
    # 区别于 PermissionInterceptor:
    #   - PermissionInterceptor (priority=30) 校验 relationship:create/update/delete
    #   - 此处 (WriteScopeInterceptor 内部) 校验 business_object:edit 类 perm
    #   - 二者互补: 前者管"关系表 perm", 后者管"端点 BO 写 gate" (OR-edit 的关键)
    # ========================================================================

    def _fetch_user_info_for_rel_perm(
        self
    ) -> Optional[Dict[str, Any]]:
        """[V1.2.0] 从 flask.g.current_user 提取 user_info (用于 relationship perm 校验)

        防御性: 不在 flask 上下文 (单元测试) 时返回 None
        """
        try:
            from flask import g, has_app_context, has_request_context
            if not (has_app_context() and has_request_context()):
                return None
            return g.get('current_user') if hasattr(g, 'current_user') else None
        except Exception:
            return None

    def _user_has_bo_edit_perm_for_relationship(
        self, user_info: Optional[Dict[str, Any]]
    ) -> bool:
        """[V1.2.0] 检查 user 是否有 business_object:edit 类 perm (OR 语义)

        用于 relationship 写权限校验: 任一 BO:edit 类 perm 即视为"可写端点"
        - business_object:edit (统一 edit perm)
        - business_object:update (CRUD update)
        - business_object:delete (CRUD delete)
        - '*' 通配 (admin 已在 before_action 跳过, 此处防御性检查)

        Args:
            user_info: 用户信息 dict (从 flask.g.current_user 提取), 可为 None

        Returns:
            True: user 有 BO:edit 类 perm, 可继续 dim scope 检查
            False: user 无 BO:edit 类 perm, 应被软警告/硬拒绝
        """
        if not user_info:
            # 防御: 没有 user_info, 默认放行 (PermissionInterceptor 已处理未登录)
            return True

        permissions = user_info.get('permissions', [])
        if not isinstance(permissions, (set, list, tuple)):
            return True  # 防御: 异常 perm 格式, 放行

        perms_set = set(permissions) if permissions else set()
        if '*' in perms_set:
            return True

        # OR 语义: edit / update / delete 任一即可
        edit_perms = {
            'business_object:edit',
            'business_object:update',
            'business_object:delete',
        }
        return bool(perms_set & edit_perms)

    def _log_rel_func_perm_warning(
        self, context: 'ActionContext', record: Dict[str, Any],
        decision: str, user_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """[V1.2.0] 记录 relationship functional perm 校验日志 (软警告/硬拒绝)

        Args:
            context: ActionContext
            record: 当前操作的 record (含 id)
            decision: 'soft_warn' 或 'hard_reject'
            user_info: 用户信息 (dependency injection, 测试友好)
        """
        # 如果没传 user_info, 尝试从 flask.g 取
        if user_info is None:
            user_info = self._fetch_user_info_for_rel_perm()

        user_id = (user_info or {}).get('user_id') or (user_info or {}).get('id')
        target_id = record.get('id') if record else None
        object_type = getattr(context, 'object_type', None)
        action = getattr(context, 'action', None)

        log_extra = {
            'user_id': user_id,
            'object_type': object_type,
            'action': action,
            'target_id': target_id,
            'missing_perm': 'business_object:edit/update/delete',
            'decision': decision,
            'spec': 'cross-domain-relationship-permission@v1.2.0',
        }

        if decision == 'soft_warn':
            logger.warning(
                'write_scope.relationship.functional_perm.soft_warn',
                extra=log_extra,
            )
        else:  # hard_reject
            logger.warning(
                'write_scope.relationship.functional_perm.hard_reject',
                extra=log_extra,
            )

        # 写入 /_diagnostics (供 AI Production Diagnostician 用)
        try:
            from meta.core.diagnostics import get_diagnostics
            diag = get_diagnostics()
            key = 'rel_func_perm_warnings'
            if key not in diag:
                diag[key] = []
            diag[key].append({
                'user_id': user_id,
                'object_type': object_type,
                'action': action,
                'target_id': target_id,
                'decision': decision,
            })
            # 保留最近 100 条
            if len(diag[key]) > 100:
                diag[key] = diag[key][-100:]
        except Exception as e:
            logger.debug(f'_log_rel_func_perm_warning: diagnostics write failed: {e}')

        # 添加 response header (供前端/监控识别软警告)
        try:
            from flask import request, has_request_context
            if has_request_context() and request and hasattr(request, 'response') and request.response:
                if decision == 'soft_warn':
                    request.response.headers['X-Rel-Perm-Warning'] = (
                        f'missing BO:edit (target_id={target_id}, user_id={user_id})'
                    )
        except Exception:
            pass

    def _check_parent_dim_scope(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], expanded: Dict[str, set],
        engine, role_id: int
    ) -> bool:
        """[V1.1.8] 检查 object_type (parent) 下是否有用户直接 dim scope 内的 child

        语义: create domain under version 764 时, 检查 version 764 下
              是否有 domain 在用户的 dim scope 中 (domain=[703])
              → domain 703 属于 version 764 → 允许创建

        [FIX v1.2.32 2026-06-21] 支持 EXTENDED_CHAIN 类型 (business_object, service_module)
              create relationship 时, object_type=business_object (source BO)
              business_object 不在 HIERARCHY_CHAIN 中, 需先沿 EXTENDED_CHAIN 步进到
              HIERARCHY_CHAIN 中的 sub_domain, 再检查其下是否有 scope 内的 child

        Returns: True 如果 parent 下有用户 scope 内的 child
        """
        from meta.services.dimension_scope_engine import HIERARCHY_CHAIN, EXTENDED_CHAIN_PARENT
        from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP, PARENT_FIELD_MAP

        # [FIX v1.2.32] EXTENDED_CHAIN 类型: 先步进到 HIERARCHY_CHAIN
        current_id = record.get('id')
        effective_object_type = object_type
        if object_type in EXTENDED_CHAIN_PARENT:
            _EXT_TO_PARENT_DIM = {
                'business_object': 'service_module',
                'service_module': 'sub_domain',
            }
            visited = 0
            while visited < 10 and effective_object_type not in HIERARCHY_CHAIN:
                parent_field = EXTENDED_CHAIN_PARENT.get(effective_object_type)
                own_table = RESOURCE_TABLE_MAP.get(effective_object_type)
                if not parent_field or not own_table:
                    return False
                row = context.data_source.execute(
                    f"SELECT {parent_field} FROM {own_table} WHERE id = ?",
                    [current_id]
                ).fetchone()
                if not row or not row[0]:
                    return False
                current_id = int(row[0])
                effective_object_type = _EXT_TO_PARENT_DIM.get(effective_object_type, '')
                visited += 1
            if effective_object_type not in HIERARCHY_CHAIN:
                return False
            # 用步进后的 record (sub_domain) 替代原始 record
            record = {'id': current_id}

            # [FIX v1.2.32] 步进到 sub_domain 后, 直接检查其 domain_id 是否在 scope 内
            # 因为 sub_domain 是 HIERARCHY_CHAIN 最底层, 没有更深的 child dim 可检查
            # 但用户 scope 通常声明 domain (如 domain=[703]), 需要检查 sub_domain 的 domain_id
            if effective_object_type == 'sub_domain' and 'domain' in expanded and expanded['domain']:
                domain_ids = expanded['domain']
                sd_row = context.data_source.execute(
                    "SELECT domain_id FROM sub_domains WHERE id = ?",
                    [current_id]
                ).fetchone()
                if sd_row and sd_row[0] in domain_ids:
                    return True

        # 找 effective_object_type 在 chain 中的位置
        try:
            obj_idx = HIERARCHY_CHAIN.index(effective_object_type)
        except ValueError:
            return False

        # 检查所有更深层级的维度是否有直接声明
        for child_idx in range(obj_idx + 1, len(HIERARCHY_CHAIN)):
            child_dim = HIERARCHY_CHAIN[child_idx]
            if child_dim not in expanded or not expanded[child_dim]:
                continue

            child_ids = expanded[child_dim]
            child_table = RESOURCE_TABLE_MAP.get(child_dim)
            if not child_table:
                continue

            # 构造查询: 从 child_dim 沿 chain 向上到 object_type
            # 例: object_type='version', child_dim='domain'
            #   → domains WHERE version_id = ? AND id IN (703)
            # 例: object_type='product', child_dim='sub_domain'
            #   → 需要沿 sub_domain → domain → version → product
            #   → sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE version_id IN
            #     (SELECT id FROM versions WHERE product_id = ?)) AND id IN (child_ids)
            #
            # 简化: 只处理相邻层级 (child_dim 的 parent_field 直接指向 object_type)
            #   对于跨层级 (product → sub_domain), 逐步查中间表
            if child_idx == obj_idx + 1:
                # 相邻: child 的 parent_field 直接指向 object_type 的记录
                parent_field = PARENT_FIELD_MAP.get(child_dim)
                if not parent_field:
                    continue
                ph = ','.join('?' * len(child_ids))
                row = context.data_source.execute(
                    f"SELECT 1 FROM {child_table} WHERE {parent_field} = ? AND id IN ({ph}) LIMIT 1",
                    [record['id']] + list(child_ids)
                ).fetchone()
                if row is not None:
                    return True
            else:
                # 跨层级: 逐步查中间表
                # 例: object_type='product', child_dim='sub_domain'
                #   先查 domains WHERE version_id IN (versions WHERE product_id = ?)
                #   再查 sub_domains WHERE domain_id IN (上述 domains) AND id IN (child_ids)
                current_ids = {record['id']}
                for step_idx in range(obj_idx + 1, child_idx + 1):
                    step_dim = HIERARCHY_CHAIN[step_idx]
                    step_table = RESOURCE_TABLE_MAP.get(step_dim)
                    step_parent_field = PARENT_FIELD_MAP.get(step_dim)
                    if not step_table or not step_parent_field:
                        break
                    ph = ','.join('?' * len(current_ids))
                    if step_idx == child_idx:
                        # 最后一步: 加上 child_ids 过滤
                        child_ph = ','.join('?' * len(child_ids))
                        row = context.data_source.execute(
                            f"SELECT 1 FROM {step_table} WHERE {step_parent_field} IN ({ph}) AND id IN ({child_ph}) LIMIT 1",
                            list(current_ids) + list(child_ids)
                        ).fetchone()
                        if row is not None:
                            return True
                    else:
                        # 中间步骤: 收集中间层 ID
                        rows = context.data_source.execute(
                            f"SELECT id FROM {step_table} WHERE {step_parent_field} IN ({ph})",
                            list(current_ids)
                        ).fetchall()
                        current_ids = {r[0] for r in rows}
                        if not current_ids:
                            break
        return False

    @lru_cache(maxsize=512)
    def _get_user_role_ids_cached(self, user_id: int, ds_id: int) -> Tuple[int, ...]:
        """[v2.1 性能] LRU 缓存: user → role_ids (per-process)

        注: cache key 含 user_id, 切 user 立即失效
        """
        return ()  # 占位

    def _get_user_role_ids(
        self, context: 'ActionContext', user_id: Optional[int]
    ) -> List[int]:
        """[v2.1] 获取 user 的所有 role_id

        性能: per-request 缓存 (g.current_user.role_ids) + LRU fallback
        """
        if not user_id:
            return []
        try:
            from flask import g
            if hasattr(g, 'current_user') and g.current_user:
                cached = g.current_user.get('_role_ids_cache')
                if cached is not None:
                    return cached
        except Exception:
            pass

        try:
            rows = context.data_source.execute(
                "SELECT DISTINCT gr.role_id FROM group_roles gr "
                "JOIN user_group_members ugm ON ugm.group_id = gr.group_id "
                "WHERE ugm.user_id = ?",
                [user_id]
            ).fetchall()
            role_ids = [r[0] for r in rows]
        except Exception as e:
            logger.debug(f'_get_user_role_ids failed for user {user_id}: {e}')
            role_ids = []

        # 写回 g.current_user (per-request 缓存)
        try:
            from flask import g
            if hasattr(g, 'current_user') and g.current_user:
                g.current_user['_role_ids_cache'] = role_ids
        except Exception:
            pass
        return role_ids

    def _record_matches_cond(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], cond_expr: str,
    ) -> bool:
        """[v2.1] 检查 record 是否满足 cond_expr

        性能: 用 SQL 子查询 (1 次查询) 代替 Python 内存比对

        [V1.1.8 2026-06-15] 简化: 移除 table_type/skip_id_check 参数
          create 路径: _get_targets 已把 parent 作为 target, object_type = parent type
          所以直接用 object_type 查表, record.id 就是 parent.id
        """
        if not cond_expr:
            return False
        if not record.get('id'):
            return False
        try:
            from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP
            table = RESOURCE_TABLE_MAP.get(object_type)
            if not table:
                return False
            # [安全] cond_expr 来自 DimensionScopeEngine 内部生成, 不接受用户输入
            row = context.data_source.execute(
                f"SELECT 1 FROM {table} WHERE id = ? AND ({cond_expr}) LIMIT 1",
                [record['id']]
            ).fetchone()
            return row is not None
        except Exception as e:
            logger.debug(f'_record_matches_cond failed: cond={cond_expr}, err={e}')
            return False

    # ========================================================================
    # [FR-002 step 4] visibility 检查
    # ========================================================================
    def _check_visibility(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """[v2.1] 检查 record 是否公开可见 (有 visibility 字段 + public)

        [V1.1.7 2026-06-15] 业务语义: visibility 是产品顶层 attribute
          只有 products 表存 visibility 字段 (顶层)
          子表 (version/domain/sub_domain/business_object/service_module) 没有 visibility
          子表 visibility 沿 chain 查 product.visibility
          跟 SAP-style 顶层 attribute 设计一致 (跟 OOP 继承)

        [FIX v1.2.34 2026-06-21] annotation 没有 product_id,
          visibility 继承自 parent 对象 (target_type + target_id)

        Returns: {'allow': bool, 'visibility': 'public'/'private'/None}
        """
        # [V1.1.7] product 顶层: 直接读 record['visibility']
        # 顶层 BO 不会有 visibility 字段 (待加)
        if object_type == 'product':
            visibility = record.get('visibility')
        elif object_type == 'annotation':
            # [FIX v1.2.34] annotation 的 visibility 继承自 parent 对象
            # [FIX v1.2.36] 优先使用 context.params 中的 target_type/target_id
            #   (经 _pre_resolve_foreign_keys 解析后的最新值, 避免 orphan 旧值绕过检查)
            params_target_type = context.params.get('target_type') if hasattr(context, 'params') else None
            params_target_id = context.params.get('target_id') if hasattr(context, 'params') else None
            if isinstance(params_target_type, str) and ' - ' in params_target_type:
                params_target_type = params_target_type.split(' - ')[0].strip()
            target_type = params_target_type or record.get('target_type')
            target_id = params_target_id or record.get('target_id')
            if target_type and target_id:
                parent_record = self._load_record(context, target_type, int(target_id))
                if parent_record:
                    return self._check_visibility(context, target_type, parent_record)
            # orphan annotation: 无法确定 visibility, 默认放行
            return {'allow': True, 'visibility': 'public'}
        else:
            # [V1.1.7] 子表: 沿 chain 查 product.visibility
            product_id = self._get_product_id(context, object_type, record)
            if not product_id:
                return {'allow': False, 'visibility': 'private'}
            row = context.data_source.execute(
                "SELECT visibility FROM products WHERE id = ?", [product_id]
            ).fetchone()
            visibility = row[0] if row else None
        if visibility == 'public':
            return {'allow': True, 'visibility': 'public'}
        return {'allow': False, 'visibility': visibility or 'private'}

    def _get_product_id(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Optional[int]:
        """[V1.1.7 2026-06-15] 沿 chain 查 product_id

        HIERARCHY_CHAIN: product → version → domain → sub_domain
        顶层 BO:
          - product: 自己的 id
          - version: record.product_id
        子 BO (经 versions):
          - domain: record.version_id → versions.product_id
          - sub_domain: record.version_id → versions.product_id
          - business_object: record.version_id → versions.product_id
          - service_module: record.version_id → versions.product_id

        返回: product_id (int) 或 None
        """
        try:
            if object_type == 'product':
                return record.get('id')
            if object_type == 'version':
                pid = record.get('product_id')
                return int(pid) if pid else None
            # 其他子表: 沿 versions 表查 product_id
            version_id = record.get('version_id')
            if not version_id:
                return None
            row = context.data_source.execute(
                "SELECT product_id FROM versions WHERE id = ?", [version_id]
            ).fetchone()
            return int(row[0]) if row and row[0] else None
        except Exception as e:
            logger.debug(f'_get_product_id failed: {e}')
            return None

    # ========================================================================
    # 辅助: 加载 record
    # ========================================================================
    @lru_cache(maxsize=1024)
    def _load_record_cached(self, table: str, target_id: int) -> Optional[Tuple]:
        """[v2.1 性能] LRU 缓存: record 加载

        注: 实际查表时不能用 LRU 缓存, 因为 DataSource 不可 hash
             此处仅示意, 真实实现走 _load_record
        """
        return None

    def _load_record(
        self, context: 'ActionContext', object_type: str, target_id: int
    ) -> Optional[Dict[str, Any]]:
        """[v2.1] 加载 record dict (含 owner_id / visibility / created_by)

        性能: 单次 SELECT * (含必需字段), 不做 N+1
        """
        try:
            from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP
            table = RESOURCE_TABLE_MAP.get(object_type)
            if not table:
                return None
            # [FIX v1.1.6 H13 2026-06-15] 改用 SELECT * + 动态列名
            #   之前显式列 `version_id, product_id, domain_id` 在 product 表不存在 → SQL 失败
            #   → _load_record 返 None → line 159 早 raise (空 check_results, 拒绝无 detail)
            #   修后用 SELECT * 拿所有列, 然后只取需要的
            cursor = context.data_source.execute(
                f"SELECT * FROM {table} WHERE id = ? LIMIT 1",
                [target_id]
            )
            row = cursor.fetchone()
            if not row:
                return None
            cols = [c[0] for c in cursor.description]
            record = dict(zip(cols, row))
            # [FIX v1.2.30 2026-06-20] 包含 code / source_code / target_code
            #   用于 _extract_business_key 显示中文业务名
            result = {
                'id': record.get('id'),
                'owner_id': record.get('owner_id'),
                'visibility': record.get('visibility'),
                'created_by': record.get('created_by'),
                'product_id': record.get('product_id'),
                'version_id': record.get('version_id'),
                'domain_id': record.get('domain_id'),
                'code': record.get('code'),
            }
            if table == 'relationships':
                result['source_bo_id'] = record.get('source_bo_id')
                result['target_bo_id'] = record.get('target_bo_id')
                result['source_code'] = record.get('source_code')
                result['target_code'] = record.get('target_code')
            # [FIX v1.2.34 2026-06-21] annotation 需要 target_type + target_id 用于 parent derived
            if table == 'annotations':
                result['target_type'] = record.get('target_type')
                result['target_id'] = record.get('target_id')
            # [FIX v1.2.34 2026-06-21] EXTENDED_CHAIN 步进需要 parent FK 字段
            #   service_module.sub_domain_id → sub_domain
            #   business_object.service_module_id → service_module
            if table == 'service_modules':
                result['sub_domain_id'] = record.get('sub_domain_id')
            if table == 'business_objects':
                result['service_module_id'] = record.get('service_module_id')
            return result
        except Exception as e:
            logger.debug(f'_load_record failed for {object_type}({target_id}): {e}')
            return None

    # ========================================================================
    # 辅助: 提取业务键 (code → 中文业务名)
    # ========================================================================
    def _extract_business_key(self, object_type: str, record: Optional[Dict[str, Any]]) -> Optional[str]:
        """[v1.2.30 2026-06-20] 从 record 提取业务键 (code 字段)

        relationship: `源code→目标code`
        其他 BO:     `code` 字段值
        fallback:    None (调用方用 target_id)
        """
        if not record:
            return None
        try:
            if object_type == 'relationship':
                src = record.get('source_code') or record.get('code')
                tgt = record.get('target_code')
                if src and tgt:
                    return f'{src}→{tgt}'
                if src:
                    return src
                return None
            # 其他 BO: 优先 code, 其次 name
            bk = record.get('code')
            return bk if bk else None
        except Exception:
            return None

    # ========================================================================
    # 日志 / 诊断 / 响应头
    # ========================================================================
    def _log_warning(self, context, object_type, target_id, user_id,
                     check_results, side):
        """[v2.1] 灰度阶段 1: log WARNING (不阻塞)"""
        logger.warning(
            'permission.write_scope.missing (audit-only)',
            extra={
                'object_type': object_type,
                'target_id': target_id,
                'user_id': user_id,
                'action': context.action,
                'side': side,
                'check_results': check_results,
                'decision': 'soft_warn',
            }
        )

    def _log_reject(self, context, object_type, target_id, user_id,
                    check_results, side):
        """[v2.1] 硬拒: log WARNING"""
        logger.warning(
            'permission.write_scope.denied',
            extra={
                'object_type': object_type,
                'target_id': target_id,
                'user_id': user_id,
                'action': context.action,
                'side': side,
                'check_results': check_results,
                'decision': 'hard_reject',
            }
        )

    def _add_diagnostics(self, context, object_type, target_id, user_id,
                         check_results, side):
        """[v2.1] 写入 /_diagnostics 计数"""
        try:
            from meta.core.diagnostics import get_diagnostics
            diag = get_diagnostics()
            if 'write_scope_warnings' not in diag:
                diag['write_scope_warnings'] = []
            diag['write_scope_warnings'].append({
                'object_type': object_type,
                'target_id': target_id,
                'user_id': user_id,
                'action': context.action,
                'side': side,
                'check_results': check_results,
                'decision': 'soft_warn',  # [v2.1] audit-only 模式固定值
                'ts': context.trace_id or '',
            })
            if len(diag['write_scope_warnings']) > 100:
                diag['write_scope_warnings'] = diag['write_scope_warnings'][-100:]
        except Exception as e:
            logger.debug(f'_add_diagnostics failed: {e}')

    def _add_response_header(self, object_type: str, side: str, decision: str):
        """[v2.1] 写响应 header (用于前端探测)"""
        try:
            from flask import request
            if request and hasattr(request, 'response') and request.response:
                request.response.headers['X-Write-Scope-Warning'] = (
                    f'{object_type} {side} {decision}'
                )
        except Exception:
            pass

    # ========================================================================
    # 拦截器生命周期
    # ========================================================================
    # ------------------------------------------------------------------
    # [v2.0 2026-06-16] FK 字段写路径 dim scope 校验
    # Spec: docs/specs/spec-write-scope-policy-v2.md
    # ------------------------------------------------------------------

    def _validate_fk_scope_policies(self, context: 'ActionContext', user_id: int):
        """校验 FK 字段的 write_scope_policy (enforce / inherit / or_bypass)

        在现有 parent dim scope 校验之后执行, 检查用户提交的 FK 字段值
        是否在其 dim scope 内。
        """
        meta_object = getattr(context, 'meta_object', None)
        if not meta_object:
            return

        # 收集所有 enforce/or_bypass/inherit 字段
        enforce_fields = []
        bypass_groups: Dict[str, List[Dict]] = {}
        inherit_fields = []

        for field_def in getattr(meta_object, 'fields', []):
            # EnhancedMetaField 对象 (有 value_help 属性)
            if hasattr(field_def, 'value_help'):
                vh = field_def.value_help
            elif isinstance(field_def, dict):
                vh = field_def.get('value_help')
            else:
                continue

            if not vh:
                continue

            # 获取 source
            if hasattr(vh, 'source'):
                source = vh.source
            elif isinstance(vh, dict):
                source = vh.get('source')
            else:
                continue

            if not source:
                continue

            # 获取 write_scope_policy
            policy = getattr(source, 'write_scope_policy', 'none') if hasattr(source, 'write_scope_policy') else (source.get('write_scope_policy', 'none') if isinstance(source, dict) else 'none')
            if policy == 'none':
                continue

            scope_group = getattr(source, 'scope_group', None) if hasattr(source, 'scope_group') else (source.get('scope_group') if isinstance(source, dict) else None)
            scope_inherit_from = getattr(source, 'scope_inherit_from', None) if hasattr(source, 'scope_inherit_from') else (source.get('scope_inherit_from') if isinstance(source, dict) else None)
            target_bo = getattr(source, 'target_bo', '') if hasattr(source, 'target_bo') else (source.get('target_bo', '') if isinstance(source, dict) else '')
            field_id = getattr(field_def, 'id', '') if hasattr(field_def, 'id') else (field_def.get('id', '') if isinstance(field_def, dict) else '')

            if policy == 'enforce':
                enforce_fields.append({
                    'field_id': field_id,
                    'target_bo': target_bo,
                    'policy': 'enforce',
                })
            elif policy == 'inherit':
                inherit_fields.append({
                    'field_id': field_id,
                    'target_bo': target_bo,
                    'policy': 'inherit',
                    'scope_inherit_from': scope_inherit_from,
                })
            elif policy == 'or_bypass':
                group = scope_group or field_id
                bypass_groups.setdefault(group, []).append({
                    'field_id': field_id,
                    'target_bo': target_bo,
                    'policy': 'or_bypass',
                    'scope_group': group,
                })

        if not enforce_fields and not inherit_fields and not bypass_groups:
            return  # 无需校验

        data_source = context.data_source

        # 解析 inherit → 展开为 enforce (沿 scope_inherit_from 链)
        resolved_enforce = list(enforce_fields)
        for inh in inherit_fields:
            parent_field_id = inh['scope_inherit_from']
            parent_fk_value = context.params.get(parent_field_id) if hasattr(context, 'params') else None

            if parent_fk_value is not None:
                # 父字段有值: inherit 字段的 FK 值必须属于父字段值的子集
                fk_value = context.params.get(inh['field_id']) if hasattr(context, 'params') else None
                if fk_value is None:
                    continue
                self._validate_inherit_field(
                    inh['field_id'], fk_value, inh['target_bo'],
                    parent_field_id, parent_fk_value, user_id, data_source
                )
            else:
                # 父字段无值: 退化为 enforce
                resolved_enforce.append({
                    'field_id': inh['field_id'],
                    'target_bo': inh['target_bo'],
                    'policy': 'inherit',
                })

        # 校验 enforce 字段
        for field_info in resolved_enforce:
            fk_value = context.params.get(field_info['field_id']) if hasattr(context, 'params') else None
            if fk_value is None:
                continue  # 未提供的字段不校验

            if not self._is_fk_value_in_scope(user_id, field_info['target_bo'], fk_value, data_source):
                raise ScopeViolationError(
                    field=field_info['field_id'],
                    value=fk_value,
                    scope_policy=field_info['policy'],
                    allowed_scope=self._describe_user_scope(user_id, field_info['target_bo'], data_source),
                )

        # 校验 or_bypass 字段组
        for group_name, fields in bypass_groups.items():
            any_in_scope = False
            violated_fields = []
            for field_info in fields:
                fk_value = context.params.get(field_info['field_id']) if hasattr(context, 'params') else None
                if fk_value is None:
                    continue
                if self._is_fk_value_in_scope(user_id, field_info['target_bo'], fk_value, data_source):
                    any_in_scope = True
                    break
                violated_fields.append(field_info)

            if not any_in_scope and violated_fields:
                raise ScopeViolationError(
                    fields=[f['field_id'] for f in violated_fields],
                    scope_policy='or_bypass',
                    scope_group=group_name,
                    allowed_scope=self._describe_user_scope(user_id, violated_fields[0]['target_bo'], data_source),
                )

    def _validate_inherit_field(self, field_id: str, fk_value: Any,
                                 target_bo: str, parent_field_id: str,
                                 parent_fk_value: Any, user_id: int,
                                 data_source):
        """校验 inherit 字段: FK 值必须属于父字段 FK 值的子集"""
        # 查询: target_bo(id=fk_value) 的 parent_field_id 列值
        table_name = self._get_table_name_for_bo(target_bo)
        try:
            cursor = data_source.execute(
                f"SELECT {parent_field_id} FROM {table_name} WHERE id = ?",
                [fk_value]
            )
            row = cursor.fetchone()
            if row and row[0] == parent_fk_value:
                # FK 值属于父字段值的子集, 但父字段值本身需要在 scope 内
                if self._is_fk_value_in_scope(user_id, target_bo, fk_value, data_source):
                    return  # FK 值在 scope 内, 通过
        except Exception as e:
            logger.warning(f'_validate_inherit_field: query failed: {e}')

        # 校验失败
        if not self._is_fk_value_in_scope(user_id, target_bo, fk_value, data_source):
            raise ScopeViolationError(
                field=field_id,
                value=fk_value,
                scope_policy='inherit',
                allowed_scope=self._describe_user_scope(user_id, target_bo, data_source),
            )

    def _is_fk_value_in_scope(self, user_id: int, target_bo: str, fk_value: Any,
                               data_source) -> bool:
        """检查 FK 值是否在用户的 dim scope 内

        使用 DimensionScopeEngine 派生条件, 然后查询数据库验证。
        """
        # [FIX v1.2.30 2026-06-20] 跳过非整数 FK 值 (字符串名称/非 ID)
        #   例: source_domain_id='采购管理' (domain NAME, 不是 id)
        #   若不放行会导致 _validate_fk_scope_policies 报错: "字段 source_domain_id 的值 采购管理 不在您的数据权限范围内"
        #   实际上 FK 解析阶段会报更准确的 "引用的关联对象 '采购管理' 不存在"
        if not isinstance(fk_value, int):
            if isinstance(fk_value, bool):
                return True  # bool 是 int 子类, 显式排除
            return True  # 字符串等非整数值放行, 让 FK 解析阶段报错
        # 1. 获取用户的 role_ids
        role_ids = self._get_user_role_ids_direct(user_id, data_source)
        if not role_ids:
            return False  # 无角色 → 无 dim scope → 拒绝

        # 2. 检查是否有 dim scope 配置
        try:
            placeholders = ','.join('?' * len(role_ids))
            cursor = data_source.execute(
                f"SELECT COUNT(*) FROM role_dimension_scopes WHERE role_id IN ({placeholders})",
                list(role_ids)
            )
            count = cursor.fetchone()[0]
            if not count:
                return True  # 无 dim scope 配置 → 不限制
        except Exception:
            return True  # 查询失败 → 不限制 (安全默认)

        # 3. 用 DimensionScopeEngine 派生条件, 查询 FK 值是否匹配
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        engine = DimensionScopeEngine(data_source)

        for role_id in role_ids:
            try:
                conditions = engine.derive_data_conditions(role_id)
                cond_expr = conditions.get(target_bo)
                if not cond_expr:
                    continue

                # 直接用 cond_expr 作为 SQL WHERE 条件 (跟 _record_matches_cond 一致)
                # cond_expr 来自 DimensionScopeEngine 内部生成, 不接受用户输入
                table_name = self._get_table_name_for_bo(target_bo)
                if not table_name:
                    continue
                try:
                    sql = f"SELECT COUNT(*) FROM {table_name} WHERE id = ? AND ({cond_expr})"
                    cursor = data_source.execute(sql, [fk_value])
                    if cursor.fetchone()[0] > 0:
                        return True  # FK 值在 scope 内
                except Exception as e:
                    logger.warning(f'_is_fk_value_in_scope: query failed: {e}')

            except Exception as e:
                logger.warning(f'_is_fk_value_in_scope: derive role={role_id} failed: {e}')

        return False  # 所有 role 都不匹配

    def _get_table_name_for_bo(self, object_type: str) -> Optional[str]:
        """获取 BO 对象类型对应的数据库表名"""
        from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP
        return RESOURCE_TABLE_MAP.get(object_type)

    def _get_user_role_ids_direct(self, user_id: int, data_source) -> Tuple[int, ...]:
        """获取用户的 role_ids (直接 data_source 版本, 用于 FK scope 校验)"""
        try:
            cursor = data_source.execute(
                """SELECT DISTINCT gr.role_id
                   FROM group_roles gr
                   JOIN user_group_members ugm ON gr.group_id = ugm.group_id
                   WHERE ugm.user_id = ?""",
                [user_id]
            )
            return tuple(row[0] for row in cursor.fetchall())
        except Exception:
            return ()

    def _describe_user_scope(self, user_id: int, target_bo: str,
                              data_source) -> str:
        """生成用户对某 BO 的 scope 描述"""
        role_ids = self._get_user_role_ids_direct(user_id, data_source)
        if not role_ids:
            return f'{target_bo}: 无角色'

        from meta.services.dimension_scope_engine import DimensionScopeEngine
        engine = DimensionScopeEngine(data_source)

        for role_id in role_ids:
            conditions = engine.derive_data_conditions(role_id)
            cond_expr = conditions.get(target_bo)
            if cond_expr:
                return f'{target_bo}: {cond_expr[:100]}'

        return f'{target_bo}: 无 dim scope 限制'

    def after_action(self, context: 'ActionContext') -> None:
        # 写路径 scope 校验仅在 before_action 完成, 无需 after
        pass

    def on_error(self, context: 'ActionContext', error: Exception):
        """[v2.1] 处理 WriteScopeDenied / ScopeViolationError 异常 → JSON 响应"""
        if isinstance(error, (ScopeViolationError, ScopeViolationBatchError)):
            from flask import jsonify
            response = jsonify(error.to_response())
            response.status_code = error.status_code
            return response
        # WriteScopeDenied → 委托给 PermissionInterceptor.on_error
        from meta.core.interceptors.permission_interceptor import PermissionInterceptor
        return PermissionInterceptor.on_error(self, context, error)
