# -*- coding: utf-8 -*-
"""业务单据冲销统一入口。

档位由 reversal_profiles 声明；本模块只做分派，不重复实现边引擎
（doc_flow_reversal）与边表降级逻辑（doc_flow_attach）。
"""
from meta.core.doc_flow_reversal import counter_edge, red_ink_edge, reverse_edge
from meta.core.reversal_profiles import (
    MODE_COUNTER,
    MODE_RED_INK,
    MODE_RED_REVERSE,
    get_profile,
)


def resolve_mode(document_type):
    """返回单据的冲销档位。"""
    return get_profile(document_type)['mode']


def _require_reason(document_type, profile, reason):
    if profile['reason_required'] and not (reason or '').strip():
        raise ValueError('{0} 冲销原因必填'.format(document_type))


def reverse_document(app_ds, platform_ds, document_type, *, edge_id,
                     reason, ref_id, quantity=None, return_rule_id=None,
                     target_data=None):
    """单边冲销；档位由 profile 决定，承诺处理由调用方钩子承担。"""
    profile = get_profile(document_type)
    _require_reason(document_type, profile, reason)
    mode = profile['mode']

    if mode == MODE_RED_REVERSE:
        red_ink_edge(app_ds, edge_id, quantity=quantity,
                     ref_id=str(ref_id), derived_by=reason)
        return reverse_edge(app_ds, edge_id, reversed_by=reason)
    if mode == MODE_COUNTER:
        return counter_edge(app_ds, platform_ds, edge_id,
                            return_rule_id=return_rule_id,
                            quantity=quantity, ref_id=ref_id,
                            target_data=target_data, derived_by=reason)
    return red_ink_edge(app_ds, edge_id, quantity=quantity,
                        ref_id=str(ref_id), derived_by=reason)


def reverse_document_edges(app_ds, platform_ds, document_type, source_id, *,
                           ref_id, reason):
    """按 profile 声明的边锚点，整体冲销某源对象的全部 active 正向边。

    边表缺失 / 单边失败由 doc_flow_attach 降级为告警，不阻断业务红冲。
    """
    profile = get_profile(document_type)
    _require_reason(document_type, profile, reason)
    if profile['mode'] != MODE_RED_REVERSE:
        raise ValueError(
            '{0} 档位 {1} 不支持按源整体冲销'.format(
                document_type, profile['mode']))
    if source_id in (None, ''):
        return 0

    from meta.core.doc_flow_attach import reverse_edges_by_source

    total = 0
    for edge in profile['edges']:
        total += reverse_edges_by_source(
            app_ds, edge['rule_id'], edge['source_bo'], source_id,
            ref_id=ref_id, derived_by=reason)
    return total
