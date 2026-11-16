from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

_M_LIST = list


@dataclass
class UIListViewColumn:
    """列表视图列配置"""
    key: str
    title: str = ""
    width: str = "auto"
    position: int = 100
    importance: str = "medium"
    sortable: bool = True
    filterable: bool = True
    filter_type: str = ""
    filter_options: List[Dict[str, Any]] = field(default_factory=list)
    filter_placeholder: str = ""
    i18n_key: str = ""
    field_type: str = ""
    widget: str = ""
    format: str = ""
    enum_type: str = ""
    options: List[Dict[str, Any]] = field(default_factory=list)
    computed: bool = False
    computation: Dict[str, Any] = field(default_factory=dict)
    editable: bool = True
    immutable: bool = False
    default_visible: bool = True
    business_key: bool = False
    value_help_config: Dict[str, Any] = field(default_factory=dict)
    enum_values: List[Dict[str, Any]] = field(default_factory=list)
    # [FIX v1.0.9 2026-06-10] 隐藏配置 (支持 inline 新增/编辑时禁用)
    hidden_in_form: bool = False
    hidden_in_detail: bool = False
    hidden_in_list: bool = False
    # [FIX v1.0.10 2026-06-10] 列头过滤时使用的 API 参数名 (默认与 key 相同)
    #   例: column key=category_label (展示 label), 但 API 用 ?category_type=xxx
    api_param_key: str = ""
    # [FIX 2026-06-13] FK 列配置: 是否纳入顶部 keyword search
    #   *_name 类虚拟列应设为 false (底层 FK 是 int, keyword 搜不到)
    searchable: bool = True
    # [FIX 2026-06-13] FK 列的 value_help 配置 (YAML 可写 value_help 或 value_help_config)
    #   用于列头 value_help 过滤 + parameter_bindings (如 version_id 上下文)
    value_help: Dict[str, Any] = field(default_factory=dict)
    # [M0 2026-11-16] 条件可见性（封闭文法 {field, in|equals|not_empty}，见
    #   docs/specs/spec-meta-driven-ui-2026-11-16.md §4.7）：列以 row=null 求值。
    visible_when: Dict[str, Any] = field(default_factory=dict)
    # [M0] 列级角色过滤（仅展示层；空数组 = 不限制）。
    roles: List[str] = field(default_factory=list)


@dataclass
class UIListViewConfig:
    """列表视图配置"""
    columns: List[UIListViewColumn] = field(default_factory=list)
    defaultSort: Dict[str, Any] = field(default_factory=dict)
    searchFields: List[str] = field(default_factory=list)
    filters: List[Any] = field(default_factory=list)
    pageSize: int = 20
    selectable: bool = True
    actions: List[Dict[str, Any]] = field(default_factory=list)
    batch_actions: List[Dict[str, Any]] = field(default_factory=list)
    title: str = ""
    description: str = ""
    inlineEdit: Dict[str, Any] = field(default_factory=dict)
    detail_mode: str = "drawer"
    detail_path: str = ""
    # [S8 2026-11-16] 声明式数据源（plan-integration-p1p2 §6.8 S8-1）。
    #   仅用于「列表数据不是通用 BO 端点」的资源页（集成模块三视图）；
    #   未声明时为空 dict，ui-meta 下发 null，前端继续走既有 fetcher。
    data_source: Dict[str, Any] = field(default_factory=dict)
    # [S8] 顶部指标条声明（url + 取值路径）；同样只对资源页生效。
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UIDetailFacet:
    """详情分区配置"""
    title: str
    type: str = "fieldGroup"
    qualifier: str = ""
    fields: List[str] = field(default_factory=list)
    i18n_key: str = ""
    id: str = ""
    label: str = ""
    association: str = ""
    widget: str = ""
    readonly: bool = False
    pageSize: int = 20
    display: str = "inline"
    # [入口 2026-10-20] 允许 dict 形态的 action（保留 id/label/variant/permission）。
    #   历史上此处只放字符串（'assign'/'unassign'/'list'）；字符串形态仍照旧。
    actions: List[Any] = field(default_factory=list)
    customFetcher: str = ""
    # [B 2026-10-23] 关联基数：'one' = 1:1 明细面（渲染为内联表单，不渲染表格）；
    #   'many' = 集合面（默认，渲染表格）。1:1 由子表外键唯一约束兜底
    #   （customer_accounts.relation_id / vendor_accounts.relation_id 均为 UNIQUE）。
    cardinality: str = "many"
    # [B 2026-10-23] 分区条件显示：按父行字段值决定是否渲染该分区。
    #   形如 {"field": "role", "equals": "customer"} 或 {"field": "x", "in": [...]}。
    #   用途：party_relation 的「一实例一角色」—— role 决定该关系只可能挂
    #   客户档案或供应商档案之一，故两个分区互斥渲染；不按 role 隐藏会让 UI
    #   允许 DB 禁止的状态（一条关系同时挂两类档案）。
    visibleWhen: Dict[str, Any] = field(default_factory=dict)
    # [UI 元数据聚合 2026-11-13] 分区稳定 key / 栅格列数 / 字段跨列声明，
    #   供 ui-meta 输出 UiSectionMeta；不参与旧 detail-view 的渲染含义。
    key: Optional[str] = None
    columns: int = 2
    col_span_map: Dict[str, int] = field(default_factory=dict)


@dataclass
class UIDetailTab:
    """详情页 Tab 配置"""
    id: str
    label: str = ""
    type: str = "fields"
    fields: List[str] = field(default_factory=list)
    association: str = ""
    widget: str = ""
    # [入口 2026-10-22] 与 UIDetailFacet 对齐：允许 dict 形态的 action
    #   （保留 key/label/variant/permission）；字符串形态照旧。
    actions: List[Any] = field(default_factory=list)
    # [权限预览] readonly_aggregate 等扩展 tab 字段
    endpoint: str = ""
    icon: str = ""
    props: Dict[str, Any] = field(default_factory=dict)
    # [自定义取数器 2026-10-21] 与 facets 的 UIDetailFacet.customFetcher 对齐。
    #   此前只有 facets 承载该字段，tabs 形态的 tab（如 org 的「往来关系」）即使
    #   在 YAML 里声明也会被 loader 丢弃 ⇒ 前端拿不到 → tab 被 DetailPage 静默跳过。
    customFetcher: str = ""
    # [2026-10-21] 与 facets 对齐的其余分区字段。DetailPage 的 tabs 分支本就会读
    #   tab.readonly / tab.pageSize / tab.display，但 dataclass 缺这三个字段 ⇒
    #   YAML 里声明的 readonly/pageSize 被 loader 静默丢弃（同 customFetcher 一类问题）。
    readonly: bool = False
    pageSize: int = 20
    display: str = "inline"


@dataclass
class UIDetailViewConfig:
    """详情视图配置"""
    facets: List[UIDetailFacet] = field(default_factory=list)
    tabs: List[UIDetailTab] = field(default_factory=list)
    title: str = ""
    # [2026-10-21 自解释说明] 详情页顶部的「这是什么」说明文案（业务语言）。
    #   动机: 只读面（party_internal / org_legal_entity 等）的对象名是技术口径，
    #   用户看到「内部治理台账详情 华东销售中心」无法自行推断这是自家公司还是外部单位。
    #   该文案在详情页内容区顶部渲染成一条说明横幅。
    description: str = ""
    layout: str = "tabs"
    showChangeHistory: bool = True
    showRelations: bool = True
    # [v1.7 2026-11-07] 规则推导分区声明（原样透传给前端 DetailPage）：
    #   {enabled, label, permission, scenarios, codes}
    #   不入库、不参与规则解析，仅决定详情页是否挂载「规则推导」分区。
    rule_trace: Dict[str, Any] = field(default_factory=dict)
    # [金额回溯 2026-11-13] 金额回溯分区声明（原样透传给前端 DetailPage）：
    #   {enabled, label, permission}；此前 dataclass 缺该字段 ⇒ YAML
    #   detail.amount_trace 被加载时静默丢弃，前端无法挂载金额分解面板。
    amount_trace: Dict[str, Any] = field(default_factory=dict)
    # [2026-11-12] 详情页业务动作声明（原样透传给前端 DetailPage）：
    #   [{id, label, icon, variant, permission, action, params, confirm_message,
    #     visible_when, input_fields}]；含 action 的项由前端派发 BO Action，
    #   不含 action 的项沿用声明式按钮语义（edit / delete / print …）。
    #   此前 dataclass 缺该字段 ⇒ YAML detail.actions 在加载时被静默丢弃。
    actions: List[Any] = field(default_factory=list)
    # [UI 元数据聚合 2026-11-13] 分区分组 tab（section_keys 引用 facets.key）。
    #   与既有 tabs（UIDetailTab 内容 tab）语义不同，单独存放，避免旧端点形状变化。
    section_tabs: List['UITabConfig'] = field(default_factory=list)


@dataclass
class UITabConfig:
    """分区分组 Tab（按 key 引用 section，不承载内容取数）"""
    key: str
    label: str = ""
    section_keys: List[str] = field(default_factory=list)


@dataclass
class UIFormColumn:
    """表单列配置（用于 row 布局）"""
    title: str = ""
    fields: List[str] = field(default_factory=list)


@dataclass
class UIFormSection:
    """表单分区配置"""
    title: str
    fields: List[str] = field(default_factory=list)
    i18n_key: str = ""
    layout: str = "vertical"  # vertical | row
    # [UI 元数据聚合 2026-11-13] UIFormSection.columns 是既有「行布局列」语义
    #   （List[UIFormColumn]，YAML columns: 2 简写也落在这里），不能改成 int，
    #   否则旧 form-view 载荷与 loader 全部破坏。ui-meta 的栅格列数在输出侧
    #   由 columns 长度推导（空则 2），见 meta_api._form_block。
    columns: List[UIFormColumn] = field(default_factory=list)
    key: Optional[str] = None
    col_span_map: Dict[str, int] = field(default_factory=dict)


@dataclass
class UIFormViewConfig:
    """表单视图配置"""
    sections: List[UIFormSection] = field(default_factory=list)
    layout: str = "vertical"
    # [UI 元数据聚合 2026-11-13] 分区分组 tab（section_keys 引用 sections.key）。
    tabs: List[UITabConfig] = field(default_factory=list)


@dataclass
class UIFilterDefinition:
    """筛选器定义"""
    key: str = ""
    title: str = ""
    type: str = ""  # select | checkbox_group | multi_select | tree
    position: int = 0
    default: str = "all"
    source: str = ""
    display_field: str = ""
    options: List[Dict[str, Any]] = field(default_factory=list)
    required: bool = False
    # 树形筛选器扩展
    tree_structure: str = ""  # hierarchy | category | custom
    tree_levels: List[str] = field(default_factory=list)  # ['domain', 'sub_domain', 'service_module', 'business_object']
    leaf_value_field: str = ""  # 叶子节点的值字段，如 'id' 或 'code'
    show_count: bool = True  # 是否需要显示数量统计
    filter_by: str = ""  # 依赖的上游筛选器字段
    # [FIX 2026-06-10] 支持 source: enum_value + enum_type 模式 (动态枚举)
    enum_type: str = ""


@dataclass
class UIFilterViewConfig:
    """筛选器视图配置"""
    filters: List[UIFilterDefinition] = field(default_factory=list)
    layout: str = "vertical"  # vertical | horizontal | sidebar


@dataclass
class ChangeEventConfig:
    """变更事件配置"""
    type: str = ""
    channels: List[str] = field(default_factory=list)
    track_fields: List[str] = field(default_factory=list)
    payload: List[str] = field(default_factory=list)


@dataclass
class WebhookConfig:
    """Webhook 配置"""
    url: str = ""
    secret: str = ""
    retry_count: int = 3
    timeout: int = 30


@dataclass
class ChangeNotificationConfig:
    """变更通知配置"""
    enabled: bool = False
    events: List[ChangeEventConfig] = field(default_factory=list)
    webhook_config: Optional[WebhookConfig] = None


@dataclass
class UIReportFilterConfig:
    """报表页筛选器声明（参数直接透传数据源接口）"""
    key: str = ""
    label: str = ""
    type: str = "text"  # value_help / date / select / number / text
    required: bool = False
    default: Any = None
    options: List[Dict[str, Any]] = field(default_factory=_M_LIST)
    target_type: str = ""


@dataclass
class UIReportKpiConfig:
    """报表页 KPI 卡（取响应顶层字段）"""
    label: str = ""
    field: str = ""
    format: str = "number"


@dataclass
class UIReportChartConfig:
    """报表页图表（P9 v1 只支持 bar）"""
    type: str = "bar"
    title: str = ""
    data_field: str = "summary"
    category_field: str = "bucket"
    value_field: str = "qty"


@dataclass
class UIReportTableConfig:
    """报表页明细表（列配置与列表页列结构兼容）"""
    data_field: str = "rows"
    page_size: int = 20
    row_key: List[str] = field(default_factory=_M_LIST)
    columns: List[Dict[str, Any]] = field(default_factory=_M_LIST)


@dataclass
class UIReportDrilldownConfig:
    """报表页行钻取配置"""
    endpoint: str = ""
    title: str = ""
    # 仅当响应中的 group_by 等于该值时可钻取（聚合行无完整主键）
    only_when_group_by: str = ""
    param_map: Dict[str, str] = field(default_factory=dict)


@dataclass
class UIReportConfig:
    """报表页配置（P9：元数据驱动的只读报表）"""
    title: str = ""
    description: str = ""
    endpoint: str = ""
    method: str = "GET"
    filters: List[UIReportFilterConfig] = field(default_factory=_M_LIST)
    kpis: List[UIReportKpiConfig] = field(default_factory=_M_LIST)
    chart: Optional[UIReportChartConfig] = None
    table: UIReportTableConfig = field(default_factory=UIReportTableConfig)
    drilldown: Optional[UIReportDrilldownConfig] = None


@dataclass
class UIViewConfig:
    """UI 视图配置（包含列表、详情、表单、筛选器）"""
    list: UIListViewConfig = field(default_factory=UIListViewConfig)
    detail: UIDetailViewConfig = field(default_factory=UIDetailViewConfig)
    form: UIFormViewConfig = field(default_factory=UIFormViewConfig)
    filter: UIFilterViewConfig = field(default_factory=UIFilterViewConfig)
    change_notification: Optional[ChangeNotificationConfig] = None
    child_sections: List[Dict[str, Any]] = field(default_factory=_M_LIST)
    # [HUB 2026-10-24] 页面聚合形态声明（左树 + 多对象 tab）。
    #   此前每个对象页在 src/views 下各有一个 ~100 行 Vue 壳承载 objectTypes/tabs/树参数/
    #   过滤映射；收敛为通用页面后，这些差异改为本字段声明，由前端 MultiObjectHubPage
    #   解析为 MOMP options（见 src/components/common/MultiObjectHubPage/hubOptions.js）。
    hub: Dict[str, Any] = field(default_factory=dict)
    # [P9 2026-11-06] 报表页配置；仅显式声明时输出，不参与自动生成。
    report: Optional[UIReportConfig] = None
    # [UI 元数据聚合 2026-11-13] 视图配置版本号（ui-meta 缓存失效键）；
    #   由 view_config_service.get_or_build_view_config 赋值，不从 YAML 读取。
    schema_version: str = ""
    # [M0 2026-11-16] YAML v1.1：文法版本（缺省 1 = 当前行为；2 才允许 variants）。
    version: int = 1
    # [M0] 对象级变体 patch（原样保留，不在加载期求值；合并语义见
    #   meta/core/ui_config/variant_merge.py）。键 = 变体名。
    variants: Dict[str, Dict[str, Any]] = field(default_factory=dict)
