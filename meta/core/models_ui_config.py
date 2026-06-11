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
    # [FIX 2026-06-10] 列头过滤时使用的 API 参数名 (默认与 key 相同)
    #   例: column key=category_label (展示 label), 但 API 用 ?category_type=xxx
    api_param_key: str = ""


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
    actions: List[str] = field(default_factory=list)
    customFetcher: str = ""


@dataclass
class UIDetailTab:
    """详情页 Tab 配置"""
    id: str
    label: str = ""
    type: str = "fields"
    fields: List[str] = field(default_factory=list)
    association: str = ""
    widget: str = ""
    actions: List[str] = field(default_factory=list)


@dataclass
class UIDetailViewConfig:
    """详情视图配置"""
    facets: List[UIDetailFacet] = field(default_factory=list)
    tabs: List[UIDetailTab] = field(default_factory=list)
    title: str = ""
    layout: str = "tabs"
    showChangeHistory: bool = True
    showRelations: bool = True


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
    columns: List[UIFormColumn] = field(default_factory=list)


@dataclass
class UIFormViewConfig:
    """表单视图配置"""
    sections: List[UIFormSection] = field(default_factory=list)
    layout: str = "vertical"


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
class UIViewConfig:
    """UI 视图配置（包含列表、详情、表单、筛选器）"""
    list: UIListViewConfig = field(default_factory=UIListViewConfig)
    detail: UIDetailViewConfig = field(default_factory=UIDetailViewConfig)
    form: UIFormViewConfig = field(default_factory=UIFormViewConfig)
    filter: UIFilterViewConfig = field(default_factory=UIFilterViewConfig)
    change_notification: Optional[ChangeNotificationConfig] = None
    child_sections: List[Dict[str, Any]] = field(default_factory=_M_LIST)
