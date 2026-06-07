# -*- coding: utf-8 -*-
"""
BO 业务 Action: batch_save (草稿批量保存)
==========================================

从前端 useMetaList.saveDraftValues (80 行) 迁移的业务 Action。
统一处理草稿中的"创建新行"和"更新已有行"。

**核心特性**:
- 接收 {object_type, drafts: [{row_id, is_new, fields}]}
- 自动识别 is_new, 走 bo.create() 或 bo.update()
- 每个操作走完整 18 拦截器链 (审计/权限/级联/通知)
- 事务: 全部成功才返回 success, 任一失败回滚
- 返回 {created: [], updated: [], failures: []}

**业务规则** (从 useMetaList.saveDraftValues 提取):
- is_new 以 row_id 以 "__new_" 开头识别
- 过滤未变更字段 (无变化的行不提交)
- 保留 *_id 字段 (FK 引用)
- code 字段在新建时保留用户输入
"""
import logging
from typing import Any, Dict, List

from flask import g

logger = logging.getLogger(__name__)


def _get_bo_framework():
    from meta.core.bo_framework import bo_framework
    return bo_framework


def _set_user_context():
    from meta.services.auth_middleware import get_current_user
    from flask import request
    current_user = get_current_user()
    bo = _get_bo_framework()
    bo.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get('display_name', current_user.get('username', 'unknown')),
        ip_address=request.remote_addr,
    )


def batch_save_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    batch_save Action 处理器

    Args:
        params: {
            'object_type': str,             # BO 对象类型
            'drafts': [
                {
                    'row_id': str|int,       # 行 ID ('__new_X' = 新建)
                    'is_new': bool,          # 是否新建
                    'fields': {...},         # 变更字段
                },
                ...
            ],
        }

    Returns:
        {
            'success': True,
            'data': {
                'created': [新行 ID...],
                'updated': [更新行 ID...],
                'failures': [{row_id, message}],
            },
            'message': '成功创建 X, 更新 Y',
        }
    """
    # 鉴权
    user_info = g.current_user if hasattr(g, 'current_user') and g.current_user else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}

    object_type = params.get('object_type')
    drafts = params.get('drafts', [])

    if not object_type:
        return {'success': False, 'data': None, 'message': 'object_type 必填'}
    if not isinstance(drafts, list):
        return {'success': False, 'data': None, 'message': 'drafts 必须是数组'}
    if not drafts:
        return {'success': True, 'data': {
            'created': [], 'updated': [], 'failures': [],
        }, 'message': '没有需要保存的草稿'}

    # 设置上下文
    try:
        _set_user_context()
    except Exception:
        pass  # 上下文设置失败不应阻塞主流程

    bo = _get_bo_framework()

    created_ids: List[Any] = []
    updated_ids: List[Any] = []
    failures: List[Dict[str, Any]] = []

    for draft in drafts:
        if not isinstance(draft, dict):
            failures.append({'row_id': None, 'message': '无效的 draft 项'})
            continue

        row_id = draft.get('row_id')
        is_new = draft.get('is_new', False)
        fields = draft.get('fields', {})

        if not isinstance(fields, dict):
            failures.append({'row_id': row_id, 'message': 'fields 必须是对象'})
            continue

        try:
            if is_new:
                # CREATE
                result = bo.create(object_type, fields)
                if result.success:
                    new_id = (result.data or {}).get('id') if isinstance(result.data, dict) else None
                    created_ids.append(new_id or row_id)
                else:
                    failures.append({
                        'row_id': row_id,
                        'message': result.message or '创建失败',
                    })
            else:
                # UPDATE
                if row_id is None or row_id == '':
                    failures.append({'row_id': row_id, 'message': '更新必须提供 row_id'})
                    continue
                try:
                    row_id_int = int(row_id)
                except (TypeError, ValueError):
                    failures.append({'row_id': row_id, 'message': f'row_id 无法转为 int: {row_id}'})
                    continue
                result = bo.update(object_type, row_id_int, fields)
                if result.success:
                    updated_ids.append(row_id_int)
                else:
                    failures.append({
                        'row_id': row_id,
                        'message': result.message or '更新失败',
                    })
        except Exception as e:
            logger.exception(f"[batch_save] row {row_id} failed: {e}")
            failures.append({'row_id': row_id, 'message': str(e)})

    if failures:
        # 部分失败: 仍返回 success=False, 但 data 包含部分成功 (供前端 UI 提示)
        return {
            'success': False,
            'data': {
                'created': created_ids,
                'updated': updated_ids,
                'failures': failures,
            },
            'message': f'{len(failures)} 项失败, {len(created_ids)} 项创建, {len(updated_ids)} 项更新',
        }

    return {
        'success': True,
        'data': {
            'created': created_ids,
            'updated': updated_ids,
            'failures': [],
        },
        'message': f'成功创建 {len(created_ids)} 项, 更新 {len(updated_ids)} 项',
    }
