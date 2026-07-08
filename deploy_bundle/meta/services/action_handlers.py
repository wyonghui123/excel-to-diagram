# -*- coding: utf-8 -*-
"""
Action Handlers - 业务操作的处理器函数 (v2 增强)
【2026-06-05 Spec v1.0 实施】FR-LOG-004

- 原有 trigger 风格 handler（clear_other_current_versions）
- [DECORATIVE] v2: 新增 HANDLERS registry（handler_name → callable）
- [DECORATIVE] v2: 新增 get_handler() helper（被 action_dispatcher 调用）

[FIX 2026-06-12] 审计合规修复:
- clear_other_current_versions 之前直接走 SQL, 绕过 audit log
- 现在改走 bo_framework.update() 走完整拦截器链 (含 AuditInterceptor + 异步审计写入)

[WARNING] DEPRECATED 2026-06-05 → v3.2 迁移中:
- v3.2 实施: clear_other_current_versions_handler 已注册到 bo_action_registry as 'version.clear_other_current'
- HANDLERS dict 保留, 但已不推荐使用
- 当前未发现 action_dispatcher.py 调用, 本模块可用可删
- 后续会话将考虑完全删除
"""

from typing import Dict, Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


# [DECORATIVE] v2: handler registry
HANDLERS: Dict[str, Callable] = {}


def register_handler(name: str):
    """装饰器：注册 handler 到 HANDLERS dict"""
    def decorator(func: Callable) -> Callable:
        HANDLERS[name] = func
        logger.debug(f"[ActionHandlers] Registered handler: {name} → {func.__name__}")
        return func
    return decorator


def get_handler(name: Optional[str]) -> Optional[Callable]:
    """action_dispatcher 调用：按名字查 handler"""
    if not name:
        return None
    return HANDLERS.get(name)


# [DECORATIVE] v2: 把现有 trigger handler 注册为 named handler
@register_handler("clear_other_current_versions")
def clear_other_current_versions_handler(params: Dict[str, Any], context: Dict[str, Any], datasource=None) -> Dict[str, Any]:
    """set_current action 的 trigger handler 包装 (v3.2 兼容 BO Action 接口)"""
    # v3.2: 如果 context/context 没传 datasource, 自己从 BO framework 拿
    if not (datasource or context.get('datasource')):
        try:
            from meta.core.datasource import get_data_source
            import os
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'architecture.db',
            )
            datasource = get_data_source("sqlite", database=db_path)
        except Exception as e:
            logger.warning(f"[version.clear_other_current] Failed to get datasource: {e}")
            return {'success': False, 'data': None, 'message': f'获取数据源失败: {e}'}

    result = clear_other_current_versions(
        meta_object=context.get('meta_object'),
        record=params.get('record', {}),
        params=params,
        datasource=datasource or context.get('datasource'),
    )
    # 兜底: 如果旧函数返回 None, 转 dict
    if result is None:
        return {'success': True, 'data': None, 'message': 'No-op'}
    return result


# 保留原始 trigger 风格函数（向后兼容）
def clear_other_current_versions(meta_object, record: Dict[str, Any], params: Dict[str, Any], datasource=None) -> Dict[str, Any]:
    """
    清除同一产品下其他版本的 is_current 标志

    用于 set_current action 的 trigger handler。

    [FIX 2026-06-12] 审计合规修复:
    - 之前直接走 SQL: `UPDATE versions SET is_current = 0 ...` → 绕过 audit_logs 写入
    - 现在改走 bo_framework.update('version', vid, {'is_current': False}) →
      触发完整拦截器链 (PermissionInterceptor → DataPermissionInterceptor → CascadeInterceptor
      → AuditInterceptor → BusinessLogInterceptor → PersistenceInterceptor.after_action →
      ActionRegistry.update → ActionExecutor.execute → ActionExecutor._do_update →
      ActionExecutor._write_audit_log_v2 → audit_logs 表写入)

    [FIX 2026-06-12] User Context 同步:
    - 触发器是在 set_current action 处理过程中被调用的, 此时 Flask g.current_user 存在
    - 但 bo_framework._user_context / executor.audit_logger._current_user 可能未设
    - 在循环每个 version 之前先同步一次 (从 g.current_user → bo_framework + executor.audit_logger)

    Args:
        meta_object: 元模型对象
        record: 当前记录
        params: 操作参数
        datasource: 数据源实例 (从 action_executor 传入; 在 _resolve_handler 调用链中存在)

    Returns:
        {'success': bool, 'data': dict, 'message': str}
    """
    if not datasource:
        return {'success': False, 'data': None, 'message': 'No datasource provided'}

    version_id = record.get("id")
    product_id = record.get("product_id")

    if not version_id or not product_id:
        return {'success': False, 'data': None, 'message': 'Missing version_id or product_id'}

    try:
        # 1) 先 SELECT 待清空的 version IDs (用传入的 datasource, 不走 audit)
        cursor = datasource.execute(
            "SELECT id FROM versions WHERE product_id = ? AND id != ? AND is_current = 1",
            (product_id, version_id)
        )
        rows = cursor.fetchall() if hasattr(cursor, 'fetchall') else []
        ids_to_clear = []
        for row in rows:
            if isinstance(row, dict):
                vid = row.get('id')
            elif isinstance(row, (tuple, list)):
                vid = row[0] if row else None
            else:
                vid = row[0] if row else None
            if vid is not None:
                ids_to_clear.append(int(vid))

        if not ids_to_clear:
            logger.info(
                f"[clear_other_current_versions] No other current versions to clear "
                f"(product_id={product_id}, version_id={version_id})"
            )
            return {
                'success': True,
                'data': {'cleared_count': 0, 'product_id': product_id, 'version_id': version_id},
                'message': '没有需要清除的其他当前版本',
            }

        # 2) 同步 user context 到 bo_framework (从 Flask g.current_user / manage_api._set_audit_user)
        _sync_user_context_for_audit()

        # 3) 走 bo_framework.update() 触发 audit log
        from meta.core.bo_framework import bo_framework
        from meta.core.models import registry

        # 获取 version 元模型, 确保 registry 已经加载
        version_meta = registry.get('version') or meta_object

        cleared = 0
        failed: list = []
        for vid in ids_to_clear:
            try:
                result = bo_framework.update('version', vid, {'is_current': False})
                if result and result.success:
                    cleared += 1
                else:
                    failed.append({
                        'version_id': vid,
                        'message': (result.message if result else 'No result'),
                    })
                    logger.warning(
                        f"[clear_other_current_versions] bo.update('version', {vid}) failed: "
                        f"{(result.message if result else 'None')}"
                    )
            except Exception as per_vid_err:
                failed.append({'version_id': vid, 'message': str(per_vid_err)})
                logger.error(
                    f"[clear_other_current_versions] bo.update('version', {vid}) exception: {per_vid_err}",
                    exc_info=True
                )

        logger.info(
            f"[clear_other_current_versions] Cleared is_current for {cleared}/{len(ids_to_clear)} "
            f"other versions in product {product_id} (failed: {len(failed)})"
        )
        return {
            'success': True,
            'data': {
                'cleared_count': cleared,
                'product_id': product_id,
                'version_id': version_id,
                'failed': failed,
            },
            'message': f'已清除 {cleared} 个其他版本的 is_current'
                       + (f' ({len(failed)} 个失败)' if failed else ''),
        }
    except Exception as e:
        logger.error(f"[clear_other_current_versions] Failed: {e}", exc_info=True)
        return {'success': False, 'data': None, 'message': str(e)}


def _sync_user_context_for_audit() -> None:
    """[FIX 2026-06-12] 同步 Flask g.current_user → bo_framework + executor.audit_logger.

    set_current action 的 trigger handler (clear_other_current_versions) 在
    action_executor._execute_declarative_business 中被调用, 此时:
      - Flask g.current_user 已被 auth_middleware 设上 (经过 login_required + _extract_token + TokenService.verify_token)
      - bo_framework._user_context 可能未设 (manage_api 不调 _set_user_context)
      - executor.audit_logger._current_user 独立属性, 没人从 g 同步

    如果不设, _pseudo_resolver 解析 $user.name 会拿到空, created_by/updated_by 填空
    (audit_logs.action='UPDATE' 本身可以从 g.current_user 拿 user_name, OK; 但 versions 表 created_by/updated_by 不行)

    同步策略:
      1) 调 bo_framework.set_user_context (写 self._user_context)
      2) 遍历 bo_framework.interceptors 找到 PersistenceInterceptor, 再找其 _registry.executor,
         调 executor.set_audit_user (同时写 audit_logger._current_user + _pseudo_resolver._user_context)
    """
    try:
        from flask import g, request
        from meta.core.bo_framework import bo_framework
        from meta.services.auth_middleware import get_current_user

        current_user = get_current_user() or getattr(g, 'current_user', None) or {}
        if not current_user:
            logger.debug("[clear_other_current_versions] No current_user, skip user context sync")
            return

        # 1) 同步到 bo_framework._user_context
        user_id = current_user.get('user_id') or current_user.get('id')
        display = current_user.get('display_name') or ''
        username = current_user.get('username') or ''
        # [FIX 2026-06-20 P1 v4] 修复残留的 "display (username)" 拼接格式
        # 直接 display 优先, 不再拼接括号格式
        user_name = display or username or ''
        try:
            ip_address = request.remote_addr
        except RuntimeError:
            ip_address = ''
        try:
            user_agent = request.headers.get('User-Agent', '')
        except RuntimeError:
            user_agent = ''

        bo_framework.set_user_context(
            user_id=user_id,
            user_name=user_name,
            ip_address=ip_address,
        )

        # 2) 同步到 PersistenceInterceptor._registry.executor.audit_logger + _pseudo_resolver
        for interceptor in getattr(bo_framework, 'interceptors', []) or []:
            cls_name = interceptor.__class__.__name__
            if cls_name != 'PersistenceInterceptor':
                continue
            registry = getattr(interceptor, '_registry', None)
            if registry is None:
                continue
            executor = getattr(registry, 'executor', None)
            if executor is None:
                continue
            if hasattr(executor, 'set_audit_user'):
                executor.set_audit_user(
                    user_id=user_id,
                    user_name=user_name,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            break

        logger.debug(
            f"[clear_other_current_versions] User context synced: user_id={user_id}, user_name={user_name!r}"
        )
    except Exception as e:
        # 同步失败不能阻塞主流程 (audit 仍会从 g.current_user 拿, 只是 created_by 等填空)
        logger.debug(f"[clear_other_current_versions] User context sync skipped: {e}")
