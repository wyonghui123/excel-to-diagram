# -*- coding: utf-8 -*-
"""单据冲销档位策略表（声明式）。

每类单据在平台侧只声明一行：冲销方式、承诺处理口径、边锚点。
新增单据类型 = 加一行数据，不改编排代码。

档位语义（与 doc_flow_reversal 三档一一对应）:
- red_reverse: 红字边 + 原边置 reversed —— 整单冲销且保留红字痕迹（收货）
- red_ink:     仅红字边，原边保留 —— 数量调整
- counter:     反向单据边（退货/回运承载）—— 发货、调拨发货

承诺口径:
- no_revert:        已发生的投料/核销不回退（红冲只冲库存事实）
- release_remaining: 释放单据剩余承诺量
"""

MODE_RED_REVERSE = 'red_reverse'
MODE_RED_INK = 'red_ink'
MODE_COUNTER = 'counter'

VALID_MODES = frozenset({MODE_RED_REVERSE, MODE_RED_INK, MODE_COUNTER})
VALID_COMMITMENTS = frozenset({'no_revert', 'release_remaining'})

REVERSAL_PROFILES = {
    'receipt': {
        'mode': MODE_RED_REVERSE,
        'commitment': 'no_revert',
        'close_guard': True,
        'reason_required': True,
        'edges': ({
            'rule_id': 'receipt_line_to_inventory_txn',
            'source_bo': 'receipt_line',
        },),
    },
    'shipment': {
        'mode': MODE_COUNTER,
        'commitment': 'release_remaining',
        'close_guard': True,
        'reason_required': True,
        'edges': (),
    },
    'transfer_shipment': {
        'mode': MODE_COUNTER,
        'commitment': 'release_remaining',
        'close_guard': True,
        'reason_required': True,
        'edges': (),
    },
    'customer_invoice': {
        'mode': MODE_RED_REVERSE,
        'commitment': 'release_remaining',
        'close_guard': True,
        'reason_required': True,
        'edges': ({
            'rule_id': 'customer_invoice_to_credit_memo',
            'source_bo': 'customer_invoice_line',
        },),
    },
}


def get_profile(document_type):
    """返回单据的冲销档位；未声明即 KeyError（不做隐式兜底）。"""
    try:
        return REVERSAL_PROFILES[document_type]
    except KeyError:
        raise KeyError(
            '未声明冲销档位的单据类型: {0}'.format(document_type)) from None
