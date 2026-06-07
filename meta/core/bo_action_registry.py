# -*- coding: utf-8 -*-
"""
BO 业务 Action 注册表
========================

提供业务 Action 的统一注册、查询、调用入口。
所有业务 Action（user.authenticate、{bo}.batch_save 等）
通过本注册表接入 bo_framework，自动获得 18 拦截器链保护。

设计原则：
- 单例: 整个进程共享一个 registry
- 轻量: 不依赖 Flask/Context
- 可扩展: 业务 Action 可按需注册/注销
- 可观测: 每个 Action 都有元数据(描述、权限、是否异步)
"""
import logging
import threading
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BusinessActionMeta:
    """业务 Action 元数据 (符合行业标准: Salesforce @AuraEnabled / Power Platform Operation)"""
    action_id: str                       # 如 'user.authenticate' (PascalCase.namespace)
    handler: Callable                    # 处理器函数
    description: str = ''                # 人类可读描述
    object_type: Optional[str] = None    # 关联业务对象 (可空)
    permission_required: Optional[str] = None   # 需要的权限代码 (None=公开)
    async_supported: bool = False        # 是否支持异步
    category: str = 'business'           # 分类
    # [DECORATIVE] v3.1: 行业标准元数据 (Power Platform / ServiceNow 强制要求)
    input_schema: Optional[Dict[str, Any]] = None   # JSON Schema 描述入参
    output_schema: Optional[Dict[str, Any]] = None  # JSON Schema 描述出参
    requires_auth: bool = True           # 是否需要登录
    requires_admin: bool = False         # 是否需要 admin 权限
    visibility: str = 'normal'           # normal / important / internal
    idempotent: bool = False             # 幂等性 (重复调用结果一致)
    # [DECORATIVE] v3.4: 区分 Action (写) vs Function (读/计算) - SAP CAP / Palantir 模式
    operation_type: str = 'action'       # 'action' (写) | 'function' (读/计算)
    cacheable: bool = False              # Function 模式可缓存
    cache_ttl: int = 0                   # Function 缓存秒数 (0=不缓存)


class BoActionRegistry:
    """
    业务 Action 注册表 (单例)
    """

    _instance: Optional['BoActionRegistry'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._actions: Dict[str, BusinessActionMeta] = {}
        return cls._instance

    def register(
        self,
        action_id: str,
        handler: Callable,
        description: str = '',
        object_type: Optional[str] = None,
        permission_required: Optional[str] = None,
        async_supported: bool = False,
        category: str = 'business',
        # [DECORATIVE] v3.1 行业标准元数据
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        requires_auth: bool = True,
        requires_admin: bool = False,
        visibility: str = 'normal',
        idempotent: bool = False,
        # [DECORATIVE] v3.4 SAP CAP / Palantir 模式: 区分 action vs function
        operation_type: str = 'action',
        cacheable: bool = False,
        cache_ttl: int = 0,
    ) -> 'BoActionRegistry':
        """注册一个业务 Action

        [DECORATIVE] v3.1: 支持 input_schema/output_schema/requires_admin/idempotent 等行业标准元数据
        参照 Salesforce @AuraEnabled / Power Platform Operation 规范
        """
        if action_id in self._actions:
            logger.warning(
                f"[BoActionRegistry] Overwriting existing action: {action_id}"
            )
        self._actions[action_id] = BusinessActionMeta(
            action_id=action_id,
            handler=handler,
            description=description,
            object_type=object_type,
            permission_required=permission_required,
            async_supported=async_supported,
            category=category,
            input_schema=input_schema,
            output_schema=output_schema,
            requires_auth=requires_auth,
            requires_admin=requires_admin,
            visibility=visibility,
            idempotent=idempotent,
            operation_type=operation_type,
            cacheable=cacheable,
            cache_ttl=cache_ttl,
        )
        logger.info(
            f"[BoActionRegistry] Registered: {action_id} "
            f"(object_type={object_type}, perm={permission_required}, "
            f"admin={requires_admin}, idempotent={idempotent})"
        )
        return self

    def list_schemas(self) -> List[Dict[str, Any]]:
        """
        列出所有 Action 的 OpenAPI-style schema (用于生成 OpenAPI 3.0 spec)

        Returns:
            List of {
                'action_id': str,
                'description': str,
                'input_schema': dict,
                'output_schema': dict,
                'requires_auth': bool,
                'requires_admin': bool,
                'idempotent': bool,
                'operation_type': str,  # [DECORATIVE] v3.4
                'cacheable': bool,      # [DECORATIVE] v3.4
                'cache_ttl': int,       # [DECORATIVE] v3.4
            }
        """
        return [
            {
                'action_id': meta.action_id,
                'description': meta.description,
                'object_type': meta.object_type,
                'category': meta.category,
                'input_schema': meta.input_schema,
                'output_schema': meta.output_schema,
                'requires_auth': meta.requires_auth,
                'requires_admin': meta.requires_admin,
                'visibility': meta.visibility,
                'idempotent': meta.idempotent,
                'operation_type': meta.operation_type,
                'cacheable': meta.cacheable,
                'cache_ttl': meta.cache_ttl,
            }
            for meta in self.list_all()
        ]

    def get(self, action_id: str) -> Optional[BusinessActionMeta]:
        """获取 Action 元数据"""
        return self._actions.get(action_id)

    def has(self, action_id: str) -> bool:
        return action_id in self._actions

    def list_all(self) -> List[BusinessActionMeta]:
        return list(self._actions.values())

    def list_ids(self) -> List[str]:
        return list(self._actions.keys())

    def clear(self) -> None:
        """清空注册表 (仅用于测试)"""
        self._actions.clear()

    def call(
        self,
        action_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        调用业务 Action
        不走 bo_framework 的标准拦截器链（轻量级调用）
        用于简单业务 Action

        返回: {'success': bool, 'data': ..., 'message': str}
        """
        meta = self.get(action_id)
        if not meta:
            return {
                'success': False,
                'data': None,
                'message': f'Unknown action: {action_id}',
            }

        # 简单权限检查
        if meta.permission_required:
            ctx = context or {}
            user_perms = ctx.get('permissions', []) or []
            if meta.permission_required not in user_perms:
                return {
                    'success': False,
                    'data': None,
                    'message': f'Permission denied: {meta.permission_required} required',
                }

        try:
            result = meta.handler(params, context or {})
            # [DECORATIVE] v3.1: 兼容 ActionResult (文件流支持)
            from meta.api.bo_action_api import ActionResult
            if isinstance(result, ActionResult):
                return result  # 直接返回, 由 API 层处理
            if not isinstance(result, dict):
                return {
                    'success': False,
                    'data': None,
                    'message': f'Handler must return dict or ActionResult, got {type(result)}',
                }
            if 'success' not in result:
                result['success'] = True
            return result
        except Exception as e:
            logger.exception(
                f"[BoActionRegistry] Error executing {action_id}: {e}"
            )
            return {
                'success': False,
                'data': None,
                'message': str(e),
            }


bo_action_registry = BoActionRegistry()
