from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class EnumReference:
    """增强的枚举引用（替代简单的 enum_type_ref: string）
    
    使用示例：
        fields:
          - id: status
            enum_reference:
              enum_type_id: order_status
              binding_strength: strict
              filter_by_dimension:
                version_id: "${context.version_id}"
              cascade_update: true
              role_filter: "filter_by_user_role"
              i18n_join_fields:
                - code
                - order_text
    """
    enum_type_id: str = ""
    binding_strength: str = "strict"     # strict | loose | none
    filter_by_dimension: Dict[str, Any] = field(default_factory=dict)
    cascade_update: bool = False
    role_filter: str = ""
    i18n_join_fields: List[str] = field(default_factory=list)
    value_filter: Dict[str, Any] = field(default_factory=dict)
    sort_by: str = ""
    default_value_code: str = ""
    display_format: str = ""
    color_mapping: Dict[str, str] = field(default_factory=dict)


@dataclass
class DimensionReference:
    """维度引用配置
    
    用于声明字段引用了一个维度 BO（如 Version、Product、Domain 等），
    系统根据此配置自动：
    1. 创建外键约束（使用 id 字段）
    2. 在 UI 渲染时生成 Search Help 对话框
    3. 在索引规则中识别为高频 JOIN 字段
    """
    target_bo: str = ""                             # 目标 BO 对象类型（如 'version'、'product'）
    reference_type: str = "foreign_key"             # foreign_key | search_help
    display_field: str = "name"                     # 显示字段
    value_field: str = "id"                         # 值字段
    search_help: Dict[str, Any] = field(default_factory=dict)   # Search Help 配置
    on_delete: str = "RESTRICT"                     # RESTRICT | CASCADE | SET_NULL
    redundancy: Dict[str, Any] = field(default_factory=dict)    # 冗余一致性声明
    auto_create_join: bool = True
    min_search_length: int = 0
    search_fields: List[str] = field(default_factory=list)
    code_field: str = ""
    apply_target_permissions: bool = False


@dataclass
class FieldDependency:
    """字段依赖定义"""
    target_field: str = ""
    dependency_type: str = "visibility"              # visibility / readonly / required / value
    condition_expression: str = ""                   # 条件表达式

    when_true: Dict[str, Any] = field(default_factory=dict)
    when_false: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexHint:
    """字段级索引提示（借鉴 SAP CDS @AbapCatalog.index 注解）
    
    嵌入在 MetaField.semantics 中，指导索引规则引擎自动推断索引。
    设计参考：
    - Salesforce: IsIndexed 字段标记
    - SAP CDS: @AbapCatalog.index 注解
    - Palantir: indexed/searchable 属性
    """
    indexed: bool = False
    unique: bool = False
    priority: str = "medium"
    auto_create: bool = True
    include_in_composite: bool = False
    search_weight: int = 0


@dataclass
class SemanticAnnotation:
    """语义标注"""
    meaning: str = ""
    business_key: bool = False
    display_name: bool = False
    pattern: str = ""
    examples: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    category: str = ""
    hierarchy_level: int = 0
    custom: Dict[str, Any] = field(default_factory=dict)
    
    # 导入导出相关字段（借鉴 SAP Fiori "所见即所导" 原则）
    data_category: str = ""           # 数据类别：text | code | date | number | timestamp | amount | quantity | boolean
    import_visible: bool = True       # 导入时是否可见
    export_visible: Optional[bool] = None  # 导出时是否可见（None=跟随 ui.visible，True=强制导出，False=强制排除）
    import_order: int = 100           # 导出列顺序
    virtual: bool = False             # 虚拟字段，不存储在数据库（借鉴 SAP CDS View）
    
    # 字段控制属性（借鉴 SAP CDS View 注解体系）
    immutable: bool = False           # 创建后不可变（类似 @Core.Immutable），新建可编辑，编辑时只读
    parent_key: bool = False          # 父对象键标识（用于层级关联），新建可编辑，编辑时只读
    parent_key_display: bool = False  # 父对象键的编码显示字段（FK编码显示，虚拟冗余，紧跟FK列出现）
    mandatory: bool = False           # 业务必填（类似 @mandatory，区别于数据库 required）
    readonly_always: bool = False     # 始终只读（类似 SAP readOnly: true），新建和编辑都只读

    # 上下文字段（借鉴 SAP One Model 参数化导入）
    # 上下文字段不参与导入导出的数据行，而是通过导入界面的选择器确定
    # 例如：version_id, product_id 等是上下文字段，用户在导入前选择版本，系统自动填充
    context_field: bool = False
    
    # Search Help 字段联动（借鉴 SAP @Consumption.valueHelpDefinition additionalBinding）
    # search_help_for 指向目标字段，当目标字段是 immutable 且在编辑模式时，Search Help 字段也应只读
    search_help_for: Optional[str] = None
    
    # 外键解析配置（借鉴 SAP @ObjectModel.foreignKey.association）
    # 用于导入时根据业务键编码自动解析外键ID
    # 例如：source_bo_id 字段可以从 source_code 字段解析，resolve_to_object 为 business_object
    resolve_from_field: str = ""
    resolve_to_object: str = ""
    resolve_to_field: str = ""
    auto_fill: Dict[str, str] = field(default_factory=dict)
    
    analytics: Dict[str, Any] = field(default_factory=dict)
    
    # 索引提示（借鉴 SAP CDS @AbapCatalog.index + Salesforce IsIndexed + Palantir indexed）
    # 指导索引规则引擎自动推断索引策略
    index_hint: Optional[IndexHint] = None
    
    # 冗余字段一致性声明（Redundancy Consistency Declaration）
    # 用于声明字段的冗余性质和一致性保障策略
    # 示例：
    #   redundancy:
    #     type: stored              # stored | virtual | resolution
    #     source_field: source_bo_id
    #     derived_from: business_object.code
    #     join_path:
    #       - table: business_objects
    #         from: source_bo_id
    #         to: id
    #         select: code
    #     consistency:
    #       strategy: sync_on_write
    #       cascade_on_change: true
    #       allow_stale: false
    #       repair_strategy: recompute
    redundancy: Dict[str, Any] = field(default_factory=dict)
    
    # 计算字段声明（Computed Field Declaration）
    # 用于声明虚拟字段的计算方式
    # 示例：
    #   computed_by: hierarchy_scope  # 使用 hierarchy_scope 计算器
    computed_by: str = ""
    
    # 排序转换声明（Sort Transform Declaration）
    # 参考 SAP SADL IF_SADL_EXIT_SORT_TRANSFORM
    # 用于将虚拟字段排序转换为数据库可执行的 SQL
    # 示例：
    #   sort_transform:
    #     by: category_type              # 映射到已有字段
    #     # 或
    #     sql_expr: |                    # SQL 表达式
    #       CASE WHEN source_domain_id != target_domain_id THEN 1 ELSE 2 END
    sort_transform: Dict[str, Any] = field(default_factory=dict)
    
    # 过滤转换声明（Filter Transform Declaration）
    # 用于将虚拟字段过滤转换为数据库可执行的 SQL
    # 示例：
    #   filter_transform:
    #     sql_expr: |
    #       CASE WHEN source_domain_id != target_domain_id THEN '跨领域' ELSE '同领域' END
    filter_transform: Dict[str, Any] = field(default_factory=dict)
    
    # 权威规则引用（Scope Rules Reference）
    # 【架构原则】单一事实源：引用权威定义，不重复定义规则
    # 示例：
    #   scope_rules_ref: hierarchies.hierarchy_scopes
    # 系统将自动从 hierarchies.yaml 的 hierarchy_scopes 生成 SQL 表达式
    scope_rules_ref: str = ""
    
    # 枚举类型引用（Enum Type Reference）
    
    # 过滤字段定义（Filter Field Definition）
    # 参考 SAP CDS @Consumption.filter 注解、Salesforce System Dictionary、ServiceNow sys_dictionary
    filterable: bool = False                    # 是否可过滤（类似 @Consumption.filter）
    filter_type: str = 'text'                   # 过滤类型：date/user/enum/text/foreign_key（类似 selectionType）
    filter_label: Optional[str] = None          # 过滤组件标签（类似 @EndUserText.label）
    filter_placeholder: Optional[str] = None    # 过滤组件占位符
    filter_default: Optional[str] = None        # 过滤默认值
    filter_scope: str = 'both'                  # 过滤作用域：global/local/both
    filter_options: List[Dict[str, str]] = field(default_factory=list)  # 枚举选项列表
    filter_mandatory: bool = False              # 过滤是否必填（类似 @Consumption.filter.mandatory）
    filter_operator: str = 'eq'                 # 默认过滤操作符
    # 用于声明字段引用的枚举类型，支持自动 JOIN 和显示
    enum_type_ref: str = ""
    
    # 枚举关联字段（Enum Join Fields）
    # 用于声明需要从枚举值表 JOIN 的字段
    enum_join_fields: List[str] = field(default_factory=list)


@dataclass
class RenderHints:
    """渲染提示（借鉴 Palantir Render Hints）"""
    searchable: bool = True
    sortable: bool = True
    prominent: bool = False
    display_mode: str = "auto"
    hidden_if_empty: bool = False
    show_in_summary: bool = True
    show_in_detail: bool = True
    show_in_list: bool = True
    column_width: int = 0
    min_width: int = 0
    max_width: int = 0
    text_align: str = "left"
    format_pattern: str = ""
    placeholder: str = ""
    help_text: str = ""


@dataclass
class UIAnnotation:
    """UI 注解（借鉴 SAP @UI 注解体系）"""
    lineItem: bool = True
    fieldGroup: str = ""
    fieldGroupPosition: int = 100
    group_label: str = ""
    qualifier: str = ""
    importance: str = "medium"
    widget: str = ""
    hidden: bool = False
    visible: bool = True
    editable: bool = True
    readonly: bool = False
    hidden_in_detail: bool = False
    hidden_in_form: bool = False
    hidden_in_list: bool = False
    readonly_in_create: bool = False
    order: int = 100
    width: str = ""
    i18n_key: str = ""
    relation: str = ""
    display_field: str = ""
    depends_on: str = ""
    options: List[Dict[str, Any]] = field(default_factory=list)
    render_hints: Optional[RenderHints] = None
    value_help: Optional['ValueHelpConfig'] = None
    cascade_group: str = ""
    cascade_level: int = 0


@dataclass
class PermissionAnnotation:
    """字段级权限注解"""
    readable: bool = True
    writable: bool = True
    roles: List[str] = field(default_factory=list)


@dataclass
class I18nKey:
    """多语言国际化键"""
    key: str = ""
    default_text: str = ""
