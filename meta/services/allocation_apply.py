# -*- coding: utf-8 -*-
"""
BO 业务 Action: allocation.apply / allocation.split
===================================================

把父行的量按权重守恒地分摊到 N 个已有子行 (apply),
或拆分成 N 个新子行 (split)。算法与写入引擎见
meta/services/allocation_service.py。

[两种口径 · 2026-10-07] `apply` 按参数分派：
    带 allocation_rule_id → `allocate_by_rule`：规则驱动（basis / group_by /
        floor / rounding），并在 `allocation_results` 留痕，可回放；
    不带                 → `allocate`：显式 weights 的直调口径，
        **不留痕**（没有规则 id 就写不出留痕行的非空外键）。
`split` 无规则驱动变体（新建行不属于任何既有规则），故只有直调口径。

共性: requires_admin=True (跨行改写, 影响面大), 返回统一信封
{'success','data','message'}。
"""
import logging
from typing import Any, Dict

from meta.core.db_path import get_meta_db_path

logger = logging.getLogger(__name__)


def _set_user_context():
    """写入审计日志的用户上下文 (无请求上下文时静默跳过)。"""
    from flask import request
    from meta.services.auth_middleware import get_current_user
    from meta.core.bo_framework import bo_framework
    current_user = get_current_user()
    bo_framework.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get(
            'display_name', current_user.get('username', 'unknown')
        ),
        ip_address=request.remote_addr,
    )


def _get_ds():
    from meta.core.datasource import get_data_source
    return get_data_source('sqlite', database=get_meta_db_path())


def _run(service_method: str, params: Dict[str, Any], label: str) -> Dict[str, Any]:
    """共用调用壳: 取数源 → 设用户上下文 → 调服务 → 统一错误信封。"""
    from meta.services.allocation_service import AllocationError, AllocationService

    try:
        _set_user_context()
    except Exception:
        pass

    try:
        ds = _get_ds()
    except Exception as e:  # noqa: BLE001
        logger.exception(f'[{label}] 数据源初始化失败: {e}')
        return {'success': False, 'data': None, 'message': f'数据源未初始化: {e}'}
    if not ds:
        return {'success': False, 'data': None, 'message': '数据源未初始化'}

    try:
        data = getattr(AllocationService(ds), service_method)(params)
    except AllocationError as e:
        return {
            'success': False,
            'data': None,
            'message': str(e),
            'code': 'ALLOCATION_ERROR',
            'status_code': getattr(e, 'status_code', 400),
        }
    except Exception as e:  # noqa: BLE001
        logger.exception(f'[{label}] failed: {e}')
        return {'success': False, 'data': None, 'message': f'{label} 失败: {e}'}

    return {'success': True, 'data': data, 'message': f'{label}成功'}


def allocation_apply_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """把父行的量按权重分摊到已有 N 个子行。

    带 `allocation_rule_id` 走规则驱动（`allocate_by_rule`，含留痕），
    否则走显式 `weights` 的直调口径（`allocate`）。分派依据是参数事实而非
    开关：给了规则 id 就是"按规则摊"，没给就没规则可留痕。
    """
    p = params or {}
    method = 'allocate_by_rule' if p.get('allocation_rule_id') else 'allocate'
    return _run(method, p, '分摊')


def allocation_split_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """把父行的量守恒地拆分成 N 个新建子行。"""
    return _run('split', params or {}, '拆分')
