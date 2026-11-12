from enum import Enum
from typing import Optional


class FieldType(Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    TEXT = "text"
    JSON = "json"


class ObjectType(Enum):
    ENTITY = "entity"
    VIEW = "view"
    VIRTUAL = "virtual"


class FieldStorage(Enum):
    STORED = "stored"
    VIRTUAL = "virtual"


class FieldSource(Enum):
    OWN = "own"
    MAPPED = "mapped"
    COMPUTED = "computed"
    DERIVED = "derived"
    AGGREGATED = "aggregated"


class RelationType(Enum):
    PARENT_CHILD = "parent_child"
    REFERENCE = "reference"
    MANY_TO_MANY = "many_to_many"
    COMPOSITION = "composition"


class ActionType(Enum):
    CRUD = "crud"
    BATCH = "batch"
    BUSINESS = "business"
    CUSTOM = "custom"


class InstanceScope(Enum):
    """[Spec 21 PM 反馈 2026-09-12] 动作的语义作用域

    与 ActionType（业务分类）正交：
      - ActionType 决定矩阵列头分块（CRUD / 批量 / 业务）
      - InstanceScope 决定列头副标签（[对象级] vs [实例级]）

    取值：
      - OBJECT:  对象级动作（对该资源类型生效，无需指定具体实例）
                  例: 创建前无实例、列表入口、搜索、管理
      - INSTANCE: 实例级动作（对资源类型的具体实例生效，需配合数据范围限定实例集合）
                  例: 读/更新/删除/审批/分配/授权/撤销 等
    """
    OBJECT = "object"
    INSTANCE = "instance"


class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class QueryOperator(Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    LIKE = "like"
    ILIKE = "ilike"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    BETWEEN = "between"


class AggregateType(Enum):
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MAX = "max"
    MIN = "min"


class RuleType(Enum):
    VALIDATION = "validation"
    CONSTRAINT = "constraint"
    COMPUTATION = "computation"
    STATE_TRANSITION = "state_transition"
    PERMISSION = "permission"
    TRIGGER = "trigger"
    DERIVATION = "derivation"
    # [规则模型 T-05 2026-10-03] 属性确定（默认值）规则：新建/保存时按因子自动确定字段值
    # 语义与 COMPUTATION 的差异：COMPUTATION = 无条件/表达式覆盖；DEFAULT = 条件命中 + 首个命中 + FILL_IF_EMPTY/OVERRIDE
    DEFAULT = "default"


class RuleScope(Enum):
    FIELD = "field"
    CROSS_FIELD = "cross_field"
    OBJECT = "object"
    CROSS_OBJECT = "cross_object"
    GLOBAL = "global"


class RuleTrigger(Enum):
    BEFORE_CREATE = "before_create"
    AFTER_CREATE = "after_create"
    BEFORE_UPDATE = "before_update"
    AFTER_UPDATE = "after_update"
    BEFORE_DELETE = "before_delete"
    AFTER_DELETE = "after_delete"
    BEFORE_SAVE = "before_save"
    AFTER_SAVE = "after_save"
    ON_QUERY = "on_query"
    ON_CHANGE = "on_change"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class DataCategory(Enum):
    TEXT = "text"
    CODE = "code"
    DATE = "date"
    TIMESTAMP = "timestamp"
    NUMBER = "number"
    AMOUNT = "amount"
    QUANTITY = "quantity"
    BOOLEAN = "boolean"
    EMAIL = "email"
    URL = "url"


class AnnotationCategory(Enum):
    IMPORTANT = "important"
    WARNING = "warning"
    INFO = "info"
    TIP = "tip"


class ArchObjectType(Enum):
    """架构对象类型 — 用于 annotation.target_type 等字段的 value_help

    包含架构数据管理页面 MultiObjectManagementPage 涉及的所有可标注对象类型，
    也涵盖产品/版本层以便 annotation 跨层级引用。
    """
    PRODUCT = "product"
    VERSION = "version"
    DOMAIN = "domain"
    SUB_DOMAIN = "sub_domain"
    SERVICE_MODULE = "service_module"
    BUSINESS_OBJECT = "business_object"
    RELATIONSHIP = "relationship"
    ANNOTATION = "annotation"


class DimensionKey(Enum):
    DEFAULT = "default"
    LANGUAGE = "language"
    REGION = "region"
    COUNTRY = "country"
    CURRENCY = "currency"
    STATUS = "status"
    PRIORITY = "priority"
    CATEGORY = "category"
    TYPE = "type"
    PHASE = "phase"
    CHANNEL = "channel"
    DEPARTMENT = "department"


class BusinessRelationType(Enum):
    GENERATES = "GENERATES"
    UPDATES = "UPDATES"
    TRIGGERS = "TRIGGERS"
    REFERENCES = "REFERENCES"


class RelationCategory(Enum):
    DATA_FLOW = "data_flow"
    PROCESS_FLOW = "process_flow"
    DEPENDENCY = "dependency"


class Direction(Enum):
    PUSH = "PUSH"
    PULL = "PULL"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class HierarchyScopeType(Enum):
    """关系范围类型 (computed_by=hierarchy_scope 的 4 个 scope)

    数据单一事实源: hierarchies.yaml 的 hierarchy_scopes 段
    同步到 enum_values 表后, 前端 /api/v1/enum-values?enum_type_id=hierarchy_scope_type
    可直接拉取 4 个 options, 用于 relationship.category_type 的 filter 下拉.
    """
    CROSS_DOMAIN = "cross_domain"
    SAME_DOMAIN_CROSS_SUBDOMAIN = "same_domain_cross_subdomain"
    SAME_SUBDOMAIN_CROSS_MODULE = "same_subdomain_cross_module"
    SAME_MODULE = "same_module"


class BusinessObjectCategory(Enum):
    TRANSACTIONAL = "transactional"
    MASTER_DATA = "master_data"
    ANALYTICAL = "analytical"
    CONFIGURATION = "configuration"


class BoSubCategory(Enum):
    DOCUMENT = "document"
    PROCESS_INSTANCE = "process_instance"
    EVENT_LOG = "event_log"
    TEMPORARY = "temporary"
    PARTY = "party"
    PRODUCT = "product"
    ORGANIZATION = "organization"
    ASSET = "asset"
    FACT_TABLE = "fact_table"
    DIMENSION_TABLE = "dimension_table"
    AGGREGATE = "aggregate"
    KPI_DASHBOARD = "kpi_dashboard"
    ENUMERATION = "enumeration"
    PARAMETER = "parameter"
    LOOKUP = "lookup"
    CUSTOMIZING = "customizing"


class ObjectSemanticsCategory(Enum):
    """对象级 semantics.category 受控枚举（Spec §12.4 R24）。

    取值来自 meta/schemas 下 150 个 YAML 的实际声明（2026-11-12 取证），不重命名
    —— 改名会波及全部声明文件，并丢失 system_entity / meta_object / relationship /
    test / security_entity 的语义。同义分裂由 SEMANTICS_CATEGORY_ALIASES 在读取层
    归一，YAML 零改动（R25）。
    """
    CORE_ENTITY = "core_entity"
    SYSTEM_ENTITY = "system_entity"
    BUSINESS_DOCUMENT = "business_document"
    BUSINESS_DOCUMENT_LINE = "business_document_line"
    BUSINESS_OBJECT = "business_object"
    BUSINESS_CONFIG = "business_config"
    MASTER_DATA = "master_data"
    SECURITY_ENTITY = "security_entity"
    META_OBJECT = "meta_object"
    RELATIONSHIP = "relationship"
    AUXILIARY = "auxiliary"
    TEST = "test"
    TRANSACTIONAL = "transactional"
    CONFIGURATION = "configuration"


#: R25 别名归一：读取层完成，不改任何 YAML。判定顺序必须先于成员校验，
#: 保证归一后的取值不会残留 transactional / configuration。
SEMANTICS_CATEGORY_ALIASES = {
    "transactional": ObjectSemanticsCategory.BUSINESS_DOCUMENT,
    "configuration": ObjectSemanticsCategory.BUSINESS_CONFIG,
}

#: 显式 bo_category 的 YAML 取值 → 枚举（R26 第一优先级 override）。
BO_CATEGORY_VALUE_MAP = {c.value: c for c in BusinessObjectCategory}

#: R26 archetype → bo_category 的单一模板映射（第二优先级）。
#: 只用于派生与序列化，不参与运行期判定。
ARCHETYPE_TO_BO_CATEGORY = {
    ObjectSemanticsCategory.BUSINESS_DOCUMENT: BusinessObjectCategory.TRANSACTIONAL,
    ObjectSemanticsCategory.BUSINESS_DOCUMENT_LINE: BusinessObjectCategory.TRANSACTIONAL,
    ObjectSemanticsCategory.TRANSACTIONAL: BusinessObjectCategory.TRANSACTIONAL,
    ObjectSemanticsCategory.BUSINESS_CONFIG: BusinessObjectCategory.CONFIGURATION,
    ObjectSemanticsCategory.CONFIGURATION: BusinessObjectCategory.CONFIGURATION,
    ObjectSemanticsCategory.META_OBJECT: BusinessObjectCategory.CONFIGURATION,
    ObjectSemanticsCategory.SYSTEM_ENTITY: BusinessObjectCategory.CONFIGURATION,
    ObjectSemanticsCategory.CORE_ENTITY: BusinessObjectCategory.MASTER_DATA,
    ObjectSemanticsCategory.MASTER_DATA: BusinessObjectCategory.MASTER_DATA,
    ObjectSemanticsCategory.BUSINESS_OBJECT: BusinessObjectCategory.MASTER_DATA,
    ObjectSemanticsCategory.RELATIONSHIP: BusinessObjectCategory.MASTER_DATA,
    ObjectSemanticsCategory.SECURITY_ENTITY: BusinessObjectCategory.MASTER_DATA,
    ObjectSemanticsCategory.AUXILIARY: BusinessObjectCategory.MASTER_DATA,
    ObjectSemanticsCategory.TEST: BusinessObjectCategory.MASTER_DATA,
}


class EnumBindingStrength(Enum):
    STRICT = "strict"
    LOOSE = "loose"
    FILTER_ONLY = "filter_only"
    DISPLAY_ONLY = "display_only"


class AssociationKind(Enum):
    """关联语义类型（Spec R-MM-01 §3.2，五枚举，缺省 association）。

    声明位有两层，共同构成单一事实：
    - 聚合根级：`relationship.yaml` 的 `semantics.kind`（关系资源的自身类型）
    - 逐条级：对象 `associations[].kind`（该条关联的语义，`$associations?kind=` 过滤依据）

    只影响渲染与继承强度；不进 DDL、不新增表、不新增端点、不改
    `relationships` 表结构（R-MM-01 R4）。
    """
    ASSOCIATION = "association"      # 一般关联（默认）
    HIERARCHY = "hierarchy"          # 树形上下级
    REFERENCE = "reference"          # 引用/查阅（目标只读）
    MASTER_DETAIL = "master_detail"  # 主从强依赖
    DERIVED = "derived"              # 派生（视图/计算，只读）


def normalize_association_kind(raw) -> Optional[AssociationKind]:
    """把声明值归一为 AssociationKind；空串或未知取值返回 None（由调用方决定默认/告警）。"""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    try:
        return AssociationKind(text)
    except ValueError:
        return None


class DimensionReferenceType(Enum):
    FOREIGN_KEY = "foreign_key"
    DENORMALIZED = "denormalized"
    VIRTUAL_LOOKUP = "virtual_lookup"


class DataPermissionDimensionType(Enum):
    OWNER_SCOPE = "owner_scope"
    CONTEXT_SCOPE = "context_scope"
    FIELD_FILTER = "field_filter"
    ORGANIZATIONAL_SCOPE = "organizational_scope"


class DerivationType(Enum):
    AGGREGATION = "aggregation"
    TRANSFORMATION = "transformation"
    FILTERING = "filtering"
    ENRICHMENT = "enrichment"
    MATERIALIZATION = "materialization"


class DerivationStrategy(Enum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    ON_DEMAND = "on_demand"
    EVENT_DRIVEN = "event_driven"


class IndexType(Enum):
    BTREE = "btree"
    UNIQUE = "unique"
    COMPOSITE = "composite"
    PARTIAL = "partial"
    FTS = "fts"


class IndexPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IndexSource(Enum):
    SCHEMA = "schema"
    RULE_ENGINE = "rule_engine"
    QUERY_ANALYSIS = "query_analysis"
    MANUAL = "manual"
