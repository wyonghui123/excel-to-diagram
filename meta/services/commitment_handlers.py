# -*- coding: utf-8 -*-
"""承诺履约事件钩子（进程内同步）。

单据服务只负责发出业务事件，承诺处理由这里注册的处理器完成，
避免服务之间直接互相调用。处理器异常由调用方（单据服务）决定是否降级。
"""

HANDLERS = {}


def register(event, handler):
    """注册处理器；同一事件重复注册同一函数只保留一份。"""
    handlers = HANDLERS.setdefault(event, [])
    if handler not in handlers:
        handlers.append(handler)


def dispatch(event, payload):
    """同步分派；无处理器时静默返回。"""
    for handler in HANDLERS.get(event, []):
        handler(payload)


def _handle_receipt_posted(payload):
    """完工收货过账 → 按累计完工量核销工单组件承诺。"""
    from meta.services.commitment_service import CommitmentService

    CommitmentService(payload['data_source']).fulfill_work_order_components(
        payload['work_order_id'], completed_qty=payload.get('completed_qty'))


register('receipt.posted', _handle_receipt_posted)
