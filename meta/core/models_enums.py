from enum import Enum


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


class EnumBindingStrength(Enum):
    STRICT = "strict"
    LOOSE = "loose"
    FILTER_ONLY = "filter_only"
    DISPLAY_ONLY = "display_only"


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
