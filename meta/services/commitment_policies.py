# -*- coding: utf-8 -*-
"""承诺层策略表（声明式）。

把「哪种单据的行、按什么口径、形成什么需求」从 inventory 服务里上移为
平台策略。同类单据接入只需登记一条策略，通用引擎
（InventoryReservationService.sync_document_row_demands）无需改动。

带事件驱动核销或特殊数量推导的单据（工单组件、收货、销售订单行）仍走
各自适配器，不进本表。
"""

PEG_HARD = 'hard'
PEG_SOFT = 'soft'

DEMAND_SERVICE_ORDER = 'service_order'

SERVICE_REQUEST_SOURCE_TYPE = 'service_request'
SERVICE_LINE_KEY_PREFIX = 'SVC-LN'
#: 只有已提交/已批准的服务请求才占用可用量（草稿不承诺）
SERVICE_REQUEST_ACTIVE_STATUSES = ('submitted', 'approved')
#: 请求进入这些终态后备件需求结束，承诺全部释放
SERVICE_REQUEST_RELEASE_STATUSES = ('rejected', 'completed', 'closed',
                                    'cancelled')

#: 行式需求单据策略：单据头状态 + 明细行 → soft 承诺。
ROW_DEMAND_POLICIES = {
    SERVICE_REQUEST_SOURCE_TYPE: {
        'name': '服务请求',
        'doc_table': 'service_requests',
        'line_table': 'service_request_lines',
        'doc_field': 'request_id',
        'line_where': "line_type = 'goods' AND status = 'open'",
        'active_statuses': SERVICE_REQUEST_ACTIVE_STATUSES,
        'release_statuses': SERVICE_REQUEST_RELEASE_STATUSES,
        'demand_object_type': DEMAND_SERVICE_ORDER,
        'key_prefix': SERVICE_LINE_KEY_PREFIX,
        'org_fields': ('provider_org_id', 'requester_org_id'),
        'qty_field': 'qty',
        'uom_field': 'uom_id',
        'peg_type': PEG_SOFT,
        'release_reason': '服务请求备件行失效',
    },
}
