from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, ClassVar
import re
import threading

_M_LIST = list

from meta.core.action_constants import (
    CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE,
    ASSOCIATE, DISSOCIATE,
)
from meta.core.models_enums import (
    FieldType, ObjectType, FieldStorage, FieldSource,
    RelationType, ActionType, ValidationSeverity, QueryOperator, AggregateType,
    RuleType, RuleScope, RuleTrigger, DataCategory, AnnotationCategory, ArchObjectType,
    DimensionKey, BusinessRelationType, RelationCategory, Direction,
    HierarchyScopeType,
    BusinessObjectCategory, BoSubCategory, EnumBindingStrength, DimensionReferenceType,
    DataPermissionDimensionType, DerivationType, DerivationStrategy,
    IndexType, IndexPriority, IndexSource,
)
from meta.core.models_annotations import (
    EnumReference, DimensionReference, FieldDependency, IndexHint,
    SemanticAnnotation, RenderHints, UIAnnotation, PermissionAnnotation, I18nKey,
)
from meta.core.models_value_help import (
    ValueHelpConfig, ValueHelpParameterBinding, ValueHelpOutMapping,
    CascadeSelectConfig, ValueHelpSource, ValueHelpBehavior,
    ValueHelpDisplayColumn, ValueHelpPresentation,
)
from meta.core.models_ui_config import (
    UIListViewColumn, UIListViewConfig, UIDetailFacet, UIDetailTab,
    UIDetailViewConfig, UIFormColumn, UIFormSection, UIFormViewConfig,
    UIFilterDefinition, UIFilterViewConfig, ChangeEventConfig,
    WebhookConfig, ChangeNotificationConfig, UIViewConfig,
)


@dataclass
class ActionParameter:
    """操作参数定义"""
    id: str
    name: str
    type: str = "string"
    required: bool = True
    description: str = ""
    default: Any = None
    enum_values: List[str] = field(default_factory=list)
    i18n_key: str = ""


@dataclass
class ViewSource:
    """视图数据源"""
    object: str = ""                     # 对象ID
    alias: str = ""                      # 别名


@dataclass
class ViewJoin:
    """视图关联配置"""
    type: str = "left"                   # left / right / inner / full
    source: str = ""                     # 源别名
    target: str = ""                     # 目标别名
    condition: str = ""                  # 关联条件


@dataclass
class ViewAggregate:
    """视图聚合配置"""
    field: str = ""                      # 字段
    function: str = ""                   # SUM / COUNT / AVG / MAX / MIN
    alias: str = ""                      # 别名


@dataclass
class ViewFilter:
    """视图过滤配置"""
    field: str = ""
    operator: str = "eq"
    value: Any = None


@dataclass
class ViewConfig:
    """视图配置（统一聚合和关联能力）"""
    sources: List[ViewSource] = field(default_factory=list)
    joins: List[ViewJoin] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    aggregates: List[ViewAggregate] = field(default_factory=list)
    having: str = ""
    filters: List[ViewFilter] = field(default_factory=list)
    order_by: List[str] = field(default_factory=list)
    sql_definition: str = ""
    cache_enabled: bool = False
    cache_ttl: int = 3600


@dataclass
class VirtualConfig:
    """虚拟对象配置"""
    usage: str = "general"               # general / dto / form / calculation
    source_type: str = "memory"          # memory / api / frontend
    lifecycle: str = "transient"         # transient / session / request
    serializable: bool = True
    api_config: Optional[Dict] = None


@dataclass
class MetricReference:
    """指标引用"""
    object_id: str = ""                  # 对象ID
    field_id: str = ""                   # 字段ID
    function_id: str = ""                # 函数ID（二选一）
    filter: str = ""                     # 过滤条件


@dataclass
class MetaFunction:
    """
    计算函数（借鉴 Palantir Function）
    
    特点：
    - 无副作用，纯计算
    - 可以跨对象引用
    - 结果可被规则引用
    - 不持久化，按需计算
    """
    id: str
    name: str
    expression: str                       # 计算表达式
    return_type: FieldType = FieldType.FLOAT
    parameters: List[Dict] = field(default_factory=list)  # 参数列表
    references: List[str] = field(default_factory=list)   # 引用的对象.字段
    description: str = ""
    semantics: SemanticAnnotation = field(default_factory=SemanticAnnotation)


@dataclass
class MetaRule:
    """
    规则基类
    
    所有规则的基础定义，支持：
    - 多种规则类型（校验、约束、计算、状态转换等）
    - 多种作用域（字段级、跨字段、对象级等）
    - 多种触发时机（创建前、更新后等）
    """
    id: str
    name: str
    rule_type: RuleType = RuleType.VALIDATION
    scope: RuleScope = RuleScope.FIELD
    triggers: List[RuleTrigger] = field(default_factory=list)
    condition: str = ""              # 触发条件表达式
    action: str = ""                 # 执行动作/规则表达式
    priority: int = 100              # 优先级，数字越小越先执行
    enabled: bool = True             # 是否启用
    message: str = ""                # 错误/提示信息
    error_code: str = ""             # 错误代码
    description: str = ""            # 规则描述
    target_fields: List[str] = field(default_factory=list)  # 目标字段
    depends_on: List[str] = field(default_factory=list)     # 依赖的其他规则
    
    # 新增：指标引用
    metric_refs: List[MetricReference] = field(default_factory=list)
    
    semantics: SemanticAnnotation = field(default_factory=SemanticAnnotation)
    custom: Dict[str, Any] = field(default_factory=dict)    # 自定义扩展


@dataclass
class MetaValidation(MetaRule):
    """
    校验规则
    
    用于数据校验，继承自 MetaRule。
    默认 rule_type = VALIDATION
    """
    rule_type: RuleType = field(default=RuleType.VALIDATION)
    severity: ValidationSeverity = ValidationSeverity.ERROR
    validation_mode: str = "strict"  # strict / warning / info
    
    def __post_init__(self):
        if not self.triggers:
            self.triggers = [RuleTrigger.BEFORE_SAVE]


@dataclass
class MetaConstraint(MetaRule):
    """
    约束规则
    
    用于数据完整性约束，如唯一性、引用完整性等。
    """
    rule_type: RuleType = field(default=RuleType.CONSTRAINT)
    constraint_type: str = "check"   # unique / foreign_key / check / exclusion
    deferrable: bool = False         # 是否可延迟
    
    def __post_init__(self):
        if not self.triggers:
            self.triggers = [RuleTrigger.BEFORE_SAVE]


@dataclass
class MetaComputation(MetaRule):
    """
    计算规则
    
    用于字段值的自动计算，如折扣计算、总价计算等。
    """
    rule_type: RuleType = field(default=RuleType.COMPUTATION)
    formula: str = ""                # 计算公式
    source_fields: List[str] = field(default_factory=list)  # 源字段
    target_field: str = ""           # 目标字段
    compute_on_change: bool = True   # 源字段变更时重新计算
    
    def __post_init__(self):
        if not self.triggers:
            self.triggers = [RuleTrigger.BEFORE_SAVE, RuleTrigger.ON_CHANGE]


@dataclass
class StateTransitionSideEffect:
    """状态转换副作用"""
    type: str = ""
    target: str = ""
    value: Any = None
    handler: str = ""


@dataclass
class StateTransitionUIHints:
    """状态转换 UI 提示"""
    hidden: bool = False
    label: str = ""
    icon: str = ""
    confirm_message: str = ""
    highlight: bool = False


@dataclass
class MetaStateTransition(MetaRule):
    """
    状态转换规则
    
    用于定义状态机的状态转换规则。
    """
    rule_type: RuleType = field(default=RuleType.STATE_TRANSITION)
    state_field: str = "status"
    from_states: List[str] = field(default_factory=list)
    to_state: str = ""
    allowed_roles: List[str] = field(default_factory=list)
    auto_actions: List[str] = field(default_factory=list)
    validation_expression: str = ""
    validation_message: str = ""
    side_effects: List[StateTransitionSideEffect] = field(default_factory=list)
    ui_hints: Optional[StateTransitionUIHints] = None
    
    def __post_init__(self):
        if not self.triggers:
            self.triggers = [RuleTrigger.BEFORE_UPDATE]


@dataclass
class MetaTrigger(MetaRule):
    """
    触发规则
    
    用于定义事件驱动的规则，如发送通知、调用外部服务等。
    """
    rule_type: RuleType = field(default=RuleType.TRIGGER)
    event_type: str = ""             # 事件类型
    handler: str = ""                # 处理器（函数名或服务名）
    async_exec: bool = True          # 是否异步执行
    retry_count: int = 3             # 重试次数
    retry_delay: int = 1000          # 重试延迟（毫秒）
    
    def __post_init__(self):
        if not self.triggers:
            self.triggers = [RuleTrigger.AFTER_SAVE]


@dataclass
class DerivationAggregate:
    """聚合定义"""
    target_field: str                 # 目标字段名
    function: str                     # 聚合函数: SUM, COUNT, AVG, MAX, MIN
    source_field: str = ""            # 源字段（COUNT可为空）
    condition: str = ""               # 聚合条件


@dataclass
class DerivationMapping:
    """字段映射定义"""
    source_field: str                 # 源字段
    target_field: str                 # 目标字段
    transform: str = ""               # 转换表达式（可选）
    default: Any = None               # 默认值


@dataclass
class MetaDerivation(MetaRule):
    """
    派生规则
    
    用于跨对象的数据派生，支持聚合、转换、过滤等多种派生类型。
    
    设计原则：
    - 规则只声明"派生逻辑"，不定义字段结构
    - 字段定义（类型、是否持久化等）在 MetaObject.fields 中
    - 规则中的 source_fields/target_field 只是引用字段ID
    
    与计算规则的区别：
    - 计算规则：对象内字段到字段的同步计算
    - 派生规则：跨对象的数据派生，可能涉及聚合、延迟执行等
    
    示例：
    1. 聚合派生：订单列表 -> 销售统计（按日期聚合）
    2. 转换派生：源系统数据 -> 目标系统格式
    3. 过滤派生：全量数据 -> 特定条件子集
    """
    rule_type: RuleType = field(default=RuleType.DERIVATION)
    
    derivation_type: DerivationType = DerivationType.AGGREGATION
    strategy: DerivationStrategy = DerivationStrategy.IMMEDIATE
    
    source_object: str = ""           # 源对象ID（引用 MetaObject.id）
    target_object: str = ""           # 目标对象ID（引用 MetaObject.id，可以是自己）
    
    source_fields: List[str] = field(default_factory=list)  # 源字段ID列表（引用源对象的字段）
    
    field_mappings: List[DerivationMapping] = field(default_factory=list)  # 字段映射
    aggregates: List[DerivationAggregate] = field(default_factory=list)    # 聚合定义
    
    group_by: List[str] = field(default_factory=list)    # 分组字段
    having: str = ""                                      # 分组过滤条件
    filter: str = ""                                      # 过滤条件
    order_by: List[str] = field(default_factory=list)    # 排序字段
    
    schedule_cron: str = ""           # 定时表达式（strategy=scheduled时使用）
    batch_size: int = 1000            # 批处理大小
    incremental: bool = True          # 是否增量派生
    
    def get_target_fields(self) -> List[str]:
        """获取目标字段列表（从 aggregates 或 field_mappings 中提取）"""
        fields = []
        for agg in self.aggregates:
            if agg.target_field and agg.target_field not in fields:
                fields.append(agg.target_field)
        for mapping in self.field_mappings:
            if mapping.target_field and mapping.target_field not in fields:
                fields.append(mapping.target_field)
        return fields
    
    def __post_init__(self):
        if not self.triggers:
            if self.strategy == DerivationStrategy.IMMEDIATE:
                self.triggers = [RuleTrigger.AFTER_SAVE]
            elif self.strategy == DerivationStrategy.SCHEDULED:
                self.triggers = [RuleTrigger.SCHEDULED]
            else:
                self.triggers = [RuleTrigger.MANUAL]


@dataclass
class MetaField:
    """元数据字段"""
    id: str
    name: str
    field_type: FieldType
    db_column: str
    required: bool = False
    unique: bool = False
    default: Any = None
    description: str = ""
    
    storage: FieldStorage = FieldStorage.STORED
    source: FieldSource = FieldSource.OWN

    derive_from_object: str = ""
    derive_from_field: str = ""
    derive_rule: str = ""

    aggregate_function: str = ""
    aggregate_source_field: str = ""

    compute_expr: str = ""

    computed: bool = False
    computation: Dict[str, Any] = field(default_factory=dict)

    semantics: SemanticAnnotation = field(default_factory=SemanticAnnotation)
    validations: List[MetaValidation] = field(default_factory=list)
    is_hierarchy_path: bool = False
    hierarchy_separator: str = "/"

    ui: UIAnnotation = field(default_factory=UIAnnotation)
    permission: PermissionAnnotation = field(default_factory=PermissionAnnotation)
    
    enum_type: str = ""
    enum_filter: Dict[str, Any] = field(default_factory=dict)
    enum_default_value: str = ""
    enum_values: List[Dict[str, Any]] = field(default_factory=list)
    included_from: str = ""
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    value_help: Optional[ValueHelpConfig] = None


@dataclass
class PolicyRule:
    """策略规则"""
    when_expr: str = None
    value: Any = None
    default: bool = False


@dataclass
class EditablePolicy:
    """可编辑策略"""
    determination: List[PolicyRule] = field(default_factory=list)
    default: bool = True


@dataclass
class VisiblePolicy:
    """可见性策略"""
    determination: List[PolicyRule] = field(default_factory=list)
    default: bool = True


@dataclass
class RequiredPolicy:
    """必填性策略"""
    determination: List[PolicyRule] = field(default_factory=list)
    default: bool = False


@dataclass
class FieldPolicy:
    """字段策略声明"""
    editable: EditablePolicy = None
    visible: VisiblePolicy = None
    required: RequiredPolicy = None


@dataclass
class EnhancedMetaField(MetaField):
    """增强版元数据字段（继承现有MetaField并扩展）
    
    向后兼容：所有新增字段都有默认值
    """
    
    # ── 替代原有的简单字段 ──
    enum_reference: Optional[EnumReference] = None   # 结构化枚举引用
    dimension_reference: Optional[DimensionReference] = None  # 维度引用
    value_help: Optional[ValueHelpConfig] = None      # 统一 Value Help 配置（单一事实源）
    
    # ── 新增：字段间依赖 ──
    dependencies: List[FieldDependency] = field(default_factory=list)
    
    # ── 新增：字段分组 ──
    field_group: str = ""                             # 所属字段组
    group_position: int = 100                         # 组内位置
    
    # ── 新增：数据质量 ──
    data_quality_rules: Dict[str, Any] = field(default_factory=dict)
    
    # ── 新增：跨系统映射 ──
    external_mappings: Dict[str, Dict[str, str]] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化时自动转换旧字段到新格式"""
        if getattr(self, 'enum_type', None) and not self.enum_reference:
            if self.enum_type:
                self.enum_reference = EnumReference(
                    enum_type_id=self.enum_type,
                    binding_strength=EnumBindingStrength.STRICT
                )
        
        if self.enum_filter and self.enum_reference:
            if not self.enum_reference.value_filter:
                self.enum_reference.value_filter = self.enum_filter

        if not self.value_help:
            self.value_help = migrate_to_unified_value_help(self)


@dataclass
class HierarchyPathInfo:
    """层级路径信息"""
    path_field: str = "hierarchy_path"
    depth_field: str = "hierarchy_depth"
    separator: str = "/"
    include_self: bool = True


@dataclass
class MetaRelation:
    """元数据关联关系"""
    id: str
    name: str
    relation_type: RelationType
    target_object: str
    source_field: str = ""
    target_field: str = "id"
    cardinality: str = "1:N"  # 1:1, 1:N, N:1, N:M
    description: str = ""
    semantics: SemanticAnnotation = field(default_factory=SemanticAnnotation)
    cascade_delete: bool = False
    ownership: bool = False
    # Phase 13: 关联对象的组合显示格式，如 "{code} - {name}"
    display_format: Optional[str] = None


@dataclass
class DeletabilityConfig:
    condition: str = ""
    message: str = ""


@dataclass
class AddabilityConfig:
    condition: str = ""
    message: str = ""


@dataclass
class ActionPrecondition:
    condition: str = ""
    message: str = ""


@dataclass
class ActionEffect:
    type: str = ""
    target: str = "self"
    fields: Dict[str, Any] = field(default_factory=dict)
    handler: str = ""


@dataclass
class ActionBehavior:
    precondition: Optional[ActionPrecondition] = None
    effects: List[ActionEffect] = field(default_factory=list)


@dataclass
class DataPermissionDimension:
    field: str
    type: DataPermissionDimensionType = DataPermissionDimensionType.FIELD_FILTER
    description: str = ""
    allowed_filters: List[str] = field(default_factory=list)


@dataclass
class MetaAction:
    """元数据操作"""
    
    id: str
    name: str
    action_type: ActionType
    method: str
    path: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    semantics: SemanticAnnotation = field(default_factory=SemanticAnnotation)
    parameters: List[ActionParameter] = field(default_factory=list)
    behavior: Optional[ActionBehavior] = None
    
    def get_permission_suffix(self) -> str:
        from meta.core.standard_action_loader import StandardActionLoader
        return StandardActionLoader.get_suffix_map().get(self.id, self.id)
    
    def get_permission_code(self, object_id: str) -> str:
        return f"{object_id}:{self.get_permission_suffix()}"
    
    def to_tool_schema(self) -> Dict[str, Any]:
        """转换为 LLM Tool Schema（OpenAI Function Calling 格式）"""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description or param.name
            }
            if param.enum_values:
                prop["enum"] = param.enum_values
            properties[param.id] = prop
            if param.required:
                required.append(param.id)
        
        return {
            "name": self.id,
            "description": f"{self.name}: {self.description}" if self.description else self.name,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }


@dataclass
class MetaQueryFilter:
    """查询过滤条件"""
    field: str
    operator: QueryOperator = QueryOperator.EQ
    value: Any = None
    param: str = ""  # 参数名，用于动态传值
    description: str = ""


@dataclass
class MetaQuerySort:
    """查询排序"""
    field: str
    direction: str = "asc"  # asc / desc


@dataclass
class MetaQuery:
    """元数据查询定义"""
    id: str
    name: str
    filters: List[MetaQueryFilter] = field(default_factory=list)
    sorts: List[MetaQuerySort] = field(default_factory=list)
    limit: int = 0
    offset: int = 0
    fields: List[str] = field(default_factory=list)  # 返回字段，空为全部
    group_by: List[str] = field(default_factory=list)
    aggregates: Dict[str, str] = field(default_factory=dict)  # {alias: "count(id)"}
    description: str = ""
    semantics: SemanticAnnotation = field(default_factory=SemanticAnnotation)

@dataclass
class MetaIndex:
    """索引定义（增强版）
    
    设计参考：
    - SAP S/4HANA: CDS @AbapCatalog.index 注解体系
    - Salesforce: MT_Indexes 虚拟索引表
    - Palantir: Ontology indexed/searchable 属性
    - DataHub: Elasticsearch 索引配置
    
    索引来源优先级：
    1. schema: YAML 中显式定义的索引（最高优先级）
    2. rule_engine: 规则引擎从语义标注自动推导
    3. query_analysis: 查询模式分析推荐
    4. manual: 手动创建
    """
    fields: List[str]
    name: str = ""
    unique: bool = False
    description: str = ""
    index_type: IndexType = IndexType.BTREE
    priority: IndexPriority = IndexPriority.MEDIUM
    source: IndexSource = IndexSource.SCHEMA
    condition: str = ""
    auto_create: bool = True
    db_columns: List[str] = field(default_factory=list)


@dataclass
class BoCategoryConfig:
    """BO分类的行为配置模板"""
    category: BusinessObjectCategory
    sub_category: Optional[BoSubCategory] = None
    
    # 默认行为特征
    default_lifecycle: str = "active"           # active/versioned/archived
    default_audit_level: str = "standard"       # none/light/standard/detailed
    default_soft_delete: bool = False
    default_versioning: bool = False
    default_state_machine: bool = False
    default_import_export: bool = True
    
    # 数据特征
    change_frequency: str = "medium"            # low/medium/high/realtime
    consistency_requirement: str = "eventual"  # eventual/strong
    sharing_scope: str = "local"                # local/domain/global
    
    # 分析特征
    is_analytical_source: bool = False         # 是否可作为分析数据源
    supports_aggregation: bool = False          # 是否支持聚合
    time_dimension_required: bool = False       # 是否必须包含时间维度
    
    # UI特征
    default_list_page_size: int = 20
    supports_batch_operation: bool = True
    supports_hierarchy_display: bool = False


# 预置的分类行为模板
BO_CATEGORY_TEMPLATES: Dict[BusinessObjectCategory, BoCategoryConfig] = {
    BusinessObjectCategory.TRANSACTIONAL: BoCategoryConfig(
        category=BusinessObjectCategory.TRANSACTIONAL,
        default_lifecycle="active",
        default_audit_level="detailed",
        default_soft_delete=True,
        default_versioning=False,
        default_state_machine=True,
        default_import_export=True,
        change_frequency="high",
        consistency_requirement="strong",
        sharing_scope="local",
        is_analytical_source=True,
        supports_aggregation=True,
        time_dimension_required=True,
        default_list_page_size=20,
        supports_batch_operation=True,
        supports_hierarchy_display=False,
    ),
    
    BusinessObjectCategory.MASTER_DATA: BoCategoryConfig(
        category=BusinessObjectCategory.MASTER_DATA,
        default_lifecycle="versioned",
        default_audit_level="standard",
        default_soft_delete=False,
        default_versioning=True,
        default_state_machine=False,
        default_import_export=True,
        change_frequency="low",
        consistency_requirement="strong",
        sharing_scope="global",
        is_analytical_source=True,
        supports_aggregation=True,
        time_dimension_required=False,
        default_list_page_size=50,
        supports_batch_operation=True,
        supports_hierarchy_display=True,
    ),
    
    BusinessObjectCategory.ANALYTICAL: BoCategoryConfig(
        category=BusinessObjectCategory.ANALYTICAL,
        default_lifecycle="active",
        default_audit_level="none",
        default_soft_delete=False,
        default_versioning=False,
        default_state_machine=False,
        default_import_export=False,
        change_frequency="realtime",
        consistency_requirement="eventual",
        sharing_scope="global",
        is_analytical_source=False,
        supports_aggregation=False,
        time_dimension_required=True,
        default_list_page_size=100,
        supports_batch_operation=False,
        supports_hierarchy_display=False,
    ),
    
    BusinessObjectCategory.CONFIGURATION: BoCategoryConfig(
        category=BusinessObjectCategory.CONFIGURATION,
        default_lifecycle="versioned",
        default_audit_level="light",
        default_soft_delete=False,
        default_versioning=True,
        default_state_machine=False,
        default_import_export=True,
        change_frequency="low",
        consistency_requirement="strong",
        sharing_scope="global",
        is_analytical_source=False,
        supports_aggregation=False,
        time_dimension_required=False,
        default_list_page_size=100,
        supports_batch_operation=True,
        supports_hierarchy_display=True,
    ),
}


@dataclass
class ImportExportConfig:
    """导入导出配置（借鉴 SAP @ObjectModel 注解）
    
    定义对象级别的导入导出行为
    """
    import_enabled: bool = True           # 是否允许导入
    export_enabled: bool = True           # 是否允许导出
    cascade_export: bool = True           # 是否支持级联导出（包含子对象）
    cascade_import: bool = True           # 是否支持级联导入
    conflict_strategy: str = "upsert"     # 冲突处理策略：upsert | skip | replace
    conflict_key: str = ""                # 冲突判断字段，空则使用business_key字段
    description_for_agent: str = ""       # Agent可理解的描述（为未来AI Agent准备）


@dataclass
class AuditActionConfig:
    """单个动作的审计配置"""
    enabled: bool = True
    fields: str = "all"                    # all | changed_only | business_only
    exclude: List[str] = field(default_factory=list)
    log_message: str = ""


@dataclass
class AuditConfig:
    """审计日志配置"""
    enabled: bool = True
    
    create: AuditActionConfig = field(default_factory=lambda: AuditActionConfig(enabled=True, fields="all"))
    update: AuditActionConfig = field(default_factory=lambda: AuditActionConfig(enabled=True, fields="changed_only", exclude=["id", "created_at", "updated_at"]))
    delete: AuditActionConfig = field(default_factory=lambda: AuditActionConfig(enabled=True, fields="business_only", exclude=["id", "created_at", "updated_at"]))
    
    associate: AuditActionConfig = field(default_factory=lambda: AuditActionConfig(enabled=True))
    dissociate: AuditActionConfig = field(default_factory=lambda: AuditActionConfig(enabled=True))
    
    actions: Dict[str, AuditActionConfig] = field(default_factory=dict)
    
    def get_action_config(self, action: str) -> AuditActionConfig:
        """获取动作的审计配置"""
        if action in self.actions:
            return self.actions[action]

        # [FIX 2026-06-12] 批量关联操作复用 associate/dissociate 的审计配置
        # 否则 batch_unassign/batch_assign 返回 enabled=False, 不写审计日志
        action_map = {
            CRUD_CREATE: self.create,
            CRUD_UPDATE: self.update,
            CRUD_DELETE: self.delete,
            ASSOCIATE: self.associate,
            DISSOCIATE: self.dissociate,
            'batch_assign': self.associate,
            'batch_unassign': self.dissociate,
            'assign': self.associate,
            'unassign': self.dissociate,
        }

        return action_map.get(action, AuditActionConfig(enabled=False))


@dataclass
class MetaObject:
    """元数据对象"""
    id: str
    name: str
    table_name: str
    description: str = ""
    
    object_type: ObjectType = ObjectType.ENTITY
    
    view_config: Optional[ViewConfig] = None
    
    virtual_config: Optional[VirtualConfig] = None
    
    base_objects: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    aspects: List[str] = field(default_factory=list)
    
    functions: List[MetaFunction] = field(default_factory=list)
    
    persistent: bool = True
    is_view: bool = False
    view_definition: str = ""
    
    soft_delete: bool = False
    soft_delete_field: str = "is_deleted"
    soft_delete_value: Any = True
    soft_delete_undelete_value: Any = False
    
    fields: List[MetaField] = field(default_factory=list)
    relations: List[MetaRelation] = field(default_factory=list)
    indexes: List[MetaIndex] = field(default_factory=list)
    actions: List[MetaAction] = field(default_factory=list)
    validations: List[MetaValidation] = field(default_factory=list)
    rules: List[MetaRule] = field(default_factory=list)
    queries: List[MetaQuery] = field(default_factory=list)
    parent_object: str = ""
    semantics: SemanticAnnotation = field(default_factory=SemanticAnnotation)
    
    # 导入导出配置
    import_export: ImportExportConfig = field(default_factory=ImportExportConfig)
    
    # 审计日志配置
    audit: AuditConfig = field(default_factory=AuditConfig)
    
    # 分析模型配置
    analytical_model: Dict[str, Any] = field(default_factory=dict)
    
    # KeyTemplate 编码规则配置
    key_template: Dict[str, Any] = field(default_factory=dict)
    
    ui_view_config: UIViewConfig = field(default_factory=UIViewConfig)
    ui_view_configs: Dict[str, UIViewConfig] = field(default_factory=dict)
    authorization: Optional[Dict] = None

    deletability: Optional[DeletabilityConfig] = None
    addability: Optional[AddabilityConfig] = None

    # Phase 13: 对象级显示名称字段（如 "name"），关联选择器/删除确认/面包屑等场景使用
    display_name_field: Optional[str] = None

    # ── 新增：BO分类字段 ──
    bo_category: BusinessObjectCategory = BusinessObjectCategory.MASTER_DATA  # 默认为主数据
    bo_sub_category: Optional[BoSubCategory] = None
    category_config: Optional[BoCategoryConfig] = None  # 运行时自动填充

    # ── 新增：关联定义 ──
    associations: Optional[Any] = None  # Dict[str, AssociationDefinition] or List

    # ── 新增：删除策略 ──
    deletion_policy: Optional[Any] = None

    # ── 新增：层级配置 ──
    hierarchy: Optional[Dict[str, Any]] = None

    # ── 新增：上下文配置 ──
    context: Optional[Dict[str, Any]] = None

    # ── 新增：级联选择配置 ──
    cascade_select: Optional[List[Dict[str, Any]]] = None

    # ── 新增：数据权限维度声明 ──
    data_permission_dimensions: List[DataPermissionDimension] = field(default_factory=list)

    def __post_init__(self):
        """初始化时自动应用分类模板"""
        # 自动填充 category_config
        if self.category_config is None:
            self.category_config = BO_CATEGORY_TEMPLATES.get(
                self.bo_category,
                BO_CATEGORY_TEMPLATES[BusinessObjectCategory.MASTER_DATA]
            )
        
        # 根据分类自动设置默认值（如果未显式指定）
        config = self.category_config
        if config:
            # 可以在这里根据模板设置其他默认值
            pass

    def get_persistent_fields(self) -> List[MetaField]:
        """获取需要持久化的字段（storage = STORED）"""
        return [f for f in self.fields if f.storage == FieldStorage.STORED]
    
    def has_version_field(self) -> bool:
        """检查是否包含 version 字段（用于乐观锁）"""
        return any(f.db_column == 'version' for f in self.fields)

    def get_virtual_fields(self) -> List[MetaField]:
        """获取虚拟字段（不持久化）

        包括：
        1. storage = VIRTUAL
        2. storage = DERIVED
        3. computed = True
        """
        return [f for f in self.fields if f.storage != FieldStorage.STORED or f.computed]

    def get_computed_fields(self) -> List[MetaField]:
        """获取计算字段"""
        return [f for f in self.fields if f.computed]
    
    def get_field(self, field_id: str) -> Optional[MetaField]:
        """获取字段"""
        for f in self.fields:
            if f.id == field_id:
                return f
        return None
    
    def get_relation(self, relation_id: str) -> Optional[MetaRelation]:
        """获取关联关系"""
        for r in self.relations:
            if r.id == relation_id:
                return r
        return None
    
    def get_action(self, action_id: str) -> Optional[MetaAction]:
        """获取操作"""
        for a in self.actions:
            if a.id == action_id:
                return a
        return None
    
    def get_action_by_suffix(self, suffix: str) -> Optional[MetaAction]:
        """通过权限后缀反查 action"""
        for a in self.actions:
            if a.get_permission_suffix() == suffix:
                return a
        return None
    
    def get_permission_label(self, suffix: str) -> str:
        """获取权限显示标签（从 actions 的 name 字段推导）"""
        action = self.get_action_by_suffix(suffix)
        if action and action.name:
            return action.name
        return f"{self.name}{suffix}"
    
    def get_query(self, query_id: str) -> Optional[MetaQuery]:
        """获取查询定义"""
        for q in self.queries:
            if q.id == query_id:
                return q
        return None
    
    def get_rule(self, rule_id: str) -> Optional[MetaRule]:
        """获取规则"""
        for r in self.rules:
            if r.id == rule_id:
                return r
        return None
    
    def get_rules_by_type(self, rule_type: RuleType) -> List[MetaRule]:
        """按类型获取规则"""
        return [r for r in self.rules if r.rule_type == rule_type]
    
    def get_rules_by_trigger(self, trigger: RuleTrigger) -> List[MetaRule]:
        """按触发时机获取规则"""
        return [r for r in self.rules if trigger in r.triggers and r.enabled]
    
    def get_validations(self) -> List[MetaValidation]:
        """获取所有校验规则"""
        return [r for r in self.rules if isinstance(r, MetaValidation)]
    
    def get_constraints(self) -> List[MetaConstraint]:
        """获取所有约束规则"""
        return [r for r in self.rules if isinstance(r, MetaConstraint)]
    
    def get_computations(self) -> List[MetaComputation]:
        """获取所有计算规则"""
        return [r for r in self.rules if isinstance(r, MetaComputation)]
    
    def get_state_transitions(self) -> List[MetaStateTransition]:
        """获取所有状态转换规则"""
        return [r for r in self.rules if isinstance(r, MetaStateTransition)]
    
    def get_triggers(self) -> List[MetaTrigger]:
        """获取所有触发规则"""
        return [r for r in self.rules if isinstance(r, MetaTrigger)]
    
    def get_derivations(self) -> List['MetaDerivation']:
        """获取所有派生规则"""
        return [r for r in self.rules if isinstance(r, MetaDerivation)]
    
    def get_function(self, function_id: str) -> Optional[MetaFunction]:
        """获取函数"""
        for f in self.functions:
            if f.id == function_id:
                return f
        return None
    
    def get_functions(self) -> List[MetaFunction]:
        """获取所有函数"""
        return self.functions
    
    def get_business_key_field(self) -> Optional[MetaField]:
        """获取业务标识字段（deprecated: 仅返回第一个，请用 get_business_key_fields）"""
        for f in self.fields:
            if f.semantics.business_key:
                return f
        return None

    def get_business_key_fields(self) -> list:
        """[FR-011] 获取所有业务键字段（支持组合键）

        返回所有 business_key=True 且非 virtual 的字段列表。
        替代 get_business_key_field()（只返回单个字段，不支持组合键）。
        """
        return [
            f for f in self.fields
            if getattr(f.semantics, 'business_key', False)
            and f.storage.value != 'virtual'
            and not getattr(f.semantics, 'virtual', False)
        ]
    
    def get_display_name_field(self) -> Optional[MetaField]:
        """获取显示名称字段"""
        for f in self.fields:
            if f.semantics.display_name:
                return f
        return None
    
    def get_hierarchy_path_field(self) -> Optional[MetaField]:
        """获取层级路径字段"""
        for f in self.fields:
            if f.is_hierarchy_path:
                return f
        return None
    
    def get_hierarchy_fields(self) -> List[MetaField]:
        """获取所有层级相关字段"""
        return [f for f in self.fields if f.is_hierarchy_path]
    
    def get_hierarchy_ancestors(self) -> List[str]:
        """获取所有祖先对象ID列表（从根到父）"""
        ancestors = []
        current_parent = self.parent_object
        while current_parent:
            ancestors.append(current_parent)
            parent_obj = registry.get(current_parent)
            current_parent = parent_obj.parent_object if parent_obj else None
        return ancestors
    
    def get_hierarchy_depth(self) -> int:
        """获取当前对象在层级中的深度"""
        return len(self.get_hierarchy_ancestors())
    
    def get_hierarchy_path_template(self, separator: str = "/") -> str:
        """
        获取层级路径模板（从根到当前）
        例如: product/version/domain/subdomain/...
        """
        ancestors = self.get_hierarchy_ancestors()
        ancestors.reverse()
        path_parts = ancestors + [self.id]
        return separator.join(path_parts)
    
    def get_category_behavior(self, property_name: str) -> Any:
        """获取分类决定的默认行为"""
        if self.category_config:
            return getattr(self.category_config, property_name, None)
        return None
    
    def is_transactional(self) -> bool:
        """判断是否为事务型BO"""
        return self.bo_category == BusinessObjectCategory.TRANSACTIONAL
    
    def is_master_data(self) -> bool:
        """判断是否为主数据型BO"""
        return self.bo_category == BusinessObjectCategory.MASTER_DATA
    
    def is_analytical(self) -> bool:
        """判断是否为分析型BO"""
        return self.bo_category == BusinessObjectCategory.ANALYTICAL
    
    def is_configuration(self) -> bool:
        """判断是否为配置/枚举型BO"""
        return self.bo_category == BusinessObjectCategory.CONFIGURATION
    
    def requires_state_machine(self) -> bool:
        """是否需要状态机"""
        if self.category_config:
            return self.category_config.default_state_machine
        return False

    def get_recommended_index_strategy(self) -> List[str]:
        """根据BO类型推荐索引策略"""
        indexes = []
        if self.is_transactional():
            # 事务型：状态+时间复合索引
            indexes.append(f"idx_{self.table_name}_status_time")
        elif self.is_master_data():
            # 主数据型：编码唯一索引
            indexes.append(f"uidx_{self.table_name}_code")
        return indexes


def migrate_to_unified_value_help(field: EnhancedMetaField) -> Optional[ValueHelpConfig]:
    """将旧模型（enum_reference / dimension_reference / UIAnnotation.value_help）迁移到统一 ValueHelpConfig"""
    source = None
    behavior = ValueHelpBehavior()
    presentation = ValueHelpPresentation()

    if field.enum_reference:
        er = field.enum_reference
        source = ValueHelpSource(
            type="enum",
            enum_type_id=er.enum_type_id,
            filter_by_dimension=er.filter_by_dimension or {},
            value_filter=er.value_filter or {},
            sort_by=er.sort_by,
            i18n_join_fields=er.i18n_join_fields or [],
            default_value_code=er.default_value_code,
        )
        behavior.binding_strength = er.binding_strength.value if hasattr(er.binding_strength, 'value') else str(er.binding_strength)
        behavior.validation = behavior.binding_strength == "strict"
        presentation.result_type = "dropdown"
        presentation.display_format = er.display_format or ""
        presentation.color_mapping = getattr(er, 'color_mapping', {}) or {}

    elif field.dimension_reference:
        dr = field.dimension_reference
        sh = dr.search_help or {}
        source = ValueHelpSource(
            type="bo",
            target_bo=dr.target_bo,
            value_field="id",
            display_field=dr.display_field,
            code_field=dr.code_field,
            apply_target_permissions=dr.apply_target_permissions,
        )
        behavior.min_search_length = sh.get("min_length", 0)
        behavior.validation = True
        behavior.binding_strength = "strict"
        for ab in sh.get("additional_bindings", []):
            behavior.parameter_bindings.append(ValueHelpParameterBinding(
                local_field=ab.get("source_field", ""),
                target_field=ab.get("target_field", ""),
            ))
        presentation.result_type = "dialog"
        if dr.code_field and dr.display_field:
            presentation.display_format = f"{{{dr.code_field}}} - {{{dr.display_field}}}"

    if field.ui and field.ui.value_help:
        old_vh = field.ui.value_help
        if not source and old_vh.is_unified():
            return old_vh
        if old_vh.validation:
            behavior.validation = old_vh.validation
        if old_vh.enabled_condition:
            behavior.enabled_condition = old_vh.enabled_condition
        if old_vh.label:
            presentation.display_format = old_vh.label

    if field.ui and field.ui.widget:
        widget_map = {
            "select": "dropdown",
            "lookup": "dialog",
            "select_with_search": "dropdown",
            "association_selector": "dialog",
        }
        if not presentation.result_type or presentation.result_type == "dropdown":
            presentation.result_type = widget_map.get(field.ui.widget, "dropdown")

    if source:
        return ValueHelpConfig(source=source, behavior=behavior, presentation=presentation)

    return None


class MetaRegistry:
    """元数据注册表 - 集中管理所有元数据"""

    _instance = None
    _lock = threading.Lock()
    __force_reload__ = False  # 设置为 True 可强制重新加载

    def __new__(cls):
        # 强制重新加载（开发模式）
        if cls.__force_reload__:
            cls._instance = None
            cls.__force_reload__ = False  # 重置标志
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._objects = {}
                    instance._initialized = False
                    instance._schema_dir = ''
                    instance._version = ''
                    instance._instance_lock = threading.Lock()
                    instance._rule_chain_cache = {}
                    instance._ui_config_cache = {}
                    cls._instance = instance
        return cls._instance

    def register(self, meta_object: MetaObject) -> None:
        """注册元数据对象"""
        with self._instance_lock:
            self._objects[meta_object.id] = meta_object
            self._rule_chain_cache.pop(meta_object.id, None)
            self._ui_config_cache.pop(meta_object.id, None)

    def get(self, object_id: str) -> Optional[MetaObject]:
        """获取元数据对象"""
        return self._objects.get(object_id)

    def list_objects(self) -> List[str]:
        """列出所有元数据对象ID"""
        return list(self._objects.keys())

    def list_types(self) -> List[str]:
        """列出所有元数据对象ID（别名）"""
        return list(self._objects.keys())

    def get_all(self) -> Dict[str, MetaObject]:
        """获取所有元数据对象"""
        return self._objects

    def all(self) -> List[MetaObject]:
        """获取所有元数据对象列表"""
        return list(self._objects.values())

    def get_version(self) -> str:
        """获取元数据版本号"""
        return self._version

    def reload(self, schema_dir: str = None) -> int:
        """重新加载所有 YAML 元模型（开发模式用）"""
        from meta.core.yaml_loader import register_from_directory
        from datetime import datetime
        
        target_dir = schema_dir or self._schema_dir
        if not target_dir:
            return 0
        
        new_objects = {}
        count = register_from_directory(target_dir, target=new_objects)
        
        with self._instance_lock:
            self._objects = new_objects
            self._initialized = True
            self._version = datetime.now().strftime("%Y%m%d%H%M%S")
            self._rule_chain_cache = {}
            self._ui_config_cache = {}
        
        return count

    def get_rule_chain(self, object_id: str):
        """获取缓存的规则链执行器"""
        return self._rule_chain_cache.get(object_id)

    def set_rule_chain(self, object_id: str, executor) -> None:
        """缓存规则链执行器"""
        self._rule_chain_cache[object_id] = executor

    def invalidate_rule_chain_cache(self) -> None:
        """使所有规则链缓存失效"""
        with self._instance_lock:
            self._rule_chain_cache = {}

    def get_ui_config(self, object_id: str) -> Optional[dict]:
        """获取缓存的 UI 配置"""
        return self._ui_config_cache.get(object_id)

    def set_ui_config(self, object_id: str, config: dict) -> None:
        """缓存 UI 配置"""
        self._ui_config_cache[object_id] = config

    def invalidate_ui_config_cache(self) -> None:
        """使所有 UI 配置缓存失效"""
        with self._instance_lock:
            self._ui_config_cache = {}

    def invalidate_caches(self) -> None:
        """使所有缓存失效"""
        with self._instance_lock:
            self._rule_chain_cache = {}
            self._ui_config_cache = {}
    
    def discover_by_semantic(self, key: str, value: Any) -> List[MetaObject]:
        """按语义发现元数据对象"""
        results = []
        for obj in self._objects.values():
            if hasattr(obj.semantics, key):
                if getattr(obj.semantics, key) == value:
                    results.append(obj)
            elif key in obj.semantics.custom:
                if obj.semantics.custom[key] == value:
                    results.append(obj)
        return results
    
    def get_relation_path(self, source: str, target: str) -> List[MetaRelation]:
        """获取两个对象之间的关联路径"""
        path = []
        visited = set()
        
        def dfs(current: str, destination: str, current_path: List[MetaRelation]) -> bool:
            if current == destination:
                return True
            if current in visited:
                return False
            visited.add(current)
            
            obj = self.get(current)
            if not obj:
                return False
            
            for rel in obj.relations:
                current_path.append(rel)
                if dfs(rel.target_object, destination, current_path):
                    return True
                current_path.pop()
            
            return False
        
        dfs(source, target, path)
        return path
    
    def get_hierarchy(self, object_id: str) -> List[str]:
        """获取对象的层级路径（从根到当前对象）"""
        hierarchy = []
        current = self.get(object_id)
        
        while current:
            hierarchy.insert(0, current.id)
            if current.parent_object:
                current = self.get(current.parent_object)
            else:
                break
        
        return hierarchy
    
    def get_objects_by_type(self, object_type: ObjectType) -> List[MetaObject]:
        """按类型获取对象"""
        return [obj for obj in self._objects.values() if obj.object_type == object_type]
    
    def get_functions(self, object_id: str) -> List[MetaFunction]:
        """获取对象的函数列表"""
        obj = self.get(object_id)
        if obj:
            return obj.functions
        return []


# 全局注册表实例
registry = MetaRegistry()
