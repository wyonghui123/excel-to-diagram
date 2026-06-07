# -*- coding: utf-8 -*-
"""
Action Handlers - 业务操作的处理器函数 (v2 增强)
【2026-06-05 Spec v1.0 实施】FR-LOG-004

- 原有 trigger 风格 handler（clear_other_current_versions）
- [DECORATIVE] v2: 新增 HANDLERS registry（handler_name → callable）
- [DECORATIVE] v2: 新增 get_handler() helper（被 action_dispatcher 调用）

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

    Args:
        meta_object: 元模型对象
        record: 当前记录
        params: 操作参数
        datasource: 数据源实例

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
        cursor = datasource.execute(
            "UPDATE versions SET is_current = 0 WHERE product_id = ? AND id != ? AND is_current = 1",
            (product_id, version_id)
        )
        # 检查受影响的行数
        affected = cursor.rowcount if hasattr(cursor, 'rowcount') else 0
        logger.info(f"Cleared is_current for {affected} other versions in product {product_id}")
        return {
            'success': True,
            'data': {'cleared_count': affected, 'product_id': product_id, 'version_id': version_id},
            'message': f'已清除 {affected} 个其他版本的 is_current',
        }
    except Exception as e:
        logger.error(f"Failed to clear other current versions: {e}")
        return {'success': False, 'data': None, 'message': str(e)}
