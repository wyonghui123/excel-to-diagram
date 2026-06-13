# -*- coding: utf-8 -*-
"""
YAML 元模型加载器

从 YAML 配置文件加载元模型定义，支持：
- 解析 YAML 文件为 MetaObject
- 类型枚举自动映射
- 批量加载目录下所有 YAML 文件
"""

import os
import logging
import yaml
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class RestrictRule:
    """强依赖检查规则"""
    table: str
    foreign_key: str
    message: str
    custom_check_sql: Optional[str] = None

@dataclass
class CascadeRule:
    """级联删除规则"""
    table: str
    where_clause: Optional[str] = None

@dataclass
class SoftDeleteRule:
    """软删除规则（已弃用，保留兼容性）"""
    enabled: bool = False
    soft_delete_field: str = "deleted_at"
    deleted_by_field: str = "deleted_by"

@dataclass
class DeletionPolicy:
    """删除策略配置"""
    restrict_on: List[RestrictRule] = field(default_factory=list)
    cascade_delete: List[str] = field(default_factory=list)
    soft_delete: Optional[SoftDeleteRule] = None
    post_delete: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class AssociationActionDef:
    """关联操作定义"""
    name: str
    label: str
    handler: str = ""
    readonly: bool = False
    params: List[str] = field(default_factory=list)

@dataclass
class AssociationDefinition:
    """关联关系定义
    
    新增字段说明：
    - cardinality: 基数（many_to_one/one_to_many/many_to_many）
    - hierarchy: 是否参与层级计算
    - foreign_key_field: 外键字段（显式指定）
    - cascade_delete: 是否级联删除
    - polymorphic_type_field: 多态关联的类型字段
    - polymorphic_id_field: 多态关联的ID字段
    - async_delete: 异步删除（默认 false，同步删除）
    """
    name: str
    type: str
    through: Optional[str] = None
    source_key: str = ""
    target_entity: str = ""
    target_key: str = ""
    actions: Dict[str, AssociationActionDef] = field(default_factory=dict)
    
    cardinality: str = "many_to_many"
    hierarchy: bool = False
    foreign_key_field: Optional[str] = None
    cascade_delete: bool = False

    polymorphic_type_field: Optional[str] = None
    polymorphic_id_field: Optional[str] = None
    async_delete: bool = False
    max_cardinality: Optional[int] = None
    allow_reassign: bool = False
    readonly: bool = False  # [FIX 2026-06-09] 详情页/列表页用：true 时隐藏移除/解绑按钮

from meta.core.models import (
    MetaObject,
    MetaField,
    MetaRelation,
    MetaIndex,
    MetaAction,
    MetaValidation,
    MetaConstraint,
    MetaComputation,
    MetaStateTransition,
    MetaTrigger,
    MetaRule,
    MetaQuery,
    MetaQueryFilter,
    MetaQuerySort,
    MetaFunction,
    SemanticAnnotation,
    ImportExportConfig,
    FieldType,
    RelationType,
    ActionType,
    ValidationSeverity,
    QueryOperator,
    RuleType,
    RuleScope,
    RuleTrigger,
    ObjectType,
    FieldStorage,
    FieldSource,
    ViewConfig,
    ViewSource,
    ViewJoin,
    ViewAggregate,
    ViewFilter,
    VirtualConfig,
    MetricReference,
    registry,
    UIAnnotation,
    PermissionAnnotation,
    I18nKey,
    UIListViewColumn,
    UIListViewConfig,
    UIDetailFacet,
    UIDetailViewConfig,
    UIFormColumn,
    UIFormSection,
    UIFormViewConfig,
    UIFilterDefinition,
    UIFilterViewConfig,
    UIViewConfig,
    ActionParameter,
    DeletabilityConfig,
    AddabilityConfig,
    ActionPrecondition,
    ActionEffect,
    ActionBehavior,
    ChangeEventConfig,
    WebhookConfig,
    ChangeNotificationConfig,
    IndexType,
    IndexPriority,
    IndexSource,
    IndexHint,
    CascadeSelectConfig,
)


FIELD_TYPE_MAP = {
    "string": FieldType.STRING,
    "integer": FieldType.INTEGER,
    "int": FieldType.INTEGER,
    "float": FieldType.FLOAT,
    "boolean": FieldType.BOOLEAN,
    "bool": FieldType.BOOLEAN,
    "datetime": FieldType.DATETIME,
    "text": FieldType.TEXT,
    "json": FieldType.JSON,
}

RELATION_TYPE_MAP = {
    "parent_child": RelationType.PARENT_CHILD,
    "reference": RelationType.REFERENCE,
    "many_to_many": RelationType.MANY_TO_MANY,
    "composition": RelationType.COMPOSITION,
}

ACTION_TYPE_MAP = {
    "crud": ActionType.CRUD,
    "batch": ActionType.BATCH,
    "business": ActionType.BUSINESS,
    "custom": ActionType.CUSTOM,
}

SEVERITY_MAP = {
    "error": ValidationSeverity.ERROR,
    "warning": ValidationSeverity.WARNING,
    "info": ValidationSeverity.INFO,
}

OPERATOR_MAP = {
    "eq": QueryOperator.EQ,
    "=": QueryOperator.EQ,
    "ne": QueryOperator.NE,
    "!=": QueryOperator.NE,
    "gt": QueryOperator.GT,
    ">": QueryOperator.GT,
    "ge": QueryOperator.GE,
    ">=": QueryOperator.GE,
    "lt": QueryOperator.LT,
    "<": QueryOperator.LT,
    "le": QueryOperator.LE,
    "<=": QueryOperator.LE,
    "like": QueryOperator.LIKE,
    "ilike": QueryOperator.ILIKE,
    "in": QueryOperator.IN,
    "not_in": QueryOperator.NOT_IN,
    "is_null": QueryOperator.IS_NULL,
    "is_not_null": QueryOperator.IS_NOT_NULL,
    "between": QueryOperator.BETWEEN,
}

RULE_TYPE_MAP = {
    "validation": RuleType.VALIDATION,
    "constraint": RuleType.CONSTRAINT,
    "computation": RuleType.COMPUTATION,
    "state_transition": RuleType.STATE_TRANSITION,
    "permission": RuleType.PERMISSION,
    "trigger": RuleType.TRIGGER,
    "derivation": RuleType.DERIVATION,
}

RULE_SCOPE_MAP = {
    "field": RuleScope.FIELD,
    "cross_field": RuleScope.CROSS_FIELD,
    "object": RuleScope.OBJECT,
    "cross_object": RuleScope.CROSS_OBJECT,
    "global": RuleScope.GLOBAL,
}

RULE_TRIGGER_MAP = {
    "before_create": RuleTrigger.BEFORE_CREATE,
    "after_create": RuleTrigger.AFTER_CREATE,
    "before_update": RuleTrigger.BEFORE_UPDATE,
    "after_update": RuleTrigger.AFTER_UPDATE,
    "before_delete": RuleTrigger.BEFORE_DELETE,
    "after_delete": RuleTrigger.AFTER_DELETE,
    "before_save": RuleTrigger.BEFORE_SAVE,
    "after_save": RuleTrigger.AFTER_SAVE,
    "on_query": RuleTrigger.ON_QUERY,
    "on_change": RuleTrigger.ON_CHANGE,
    "manual": RuleTrigger.MANUAL,
    "scheduled": RuleTrigger.SCHEDULED,
}

OBJECT_TYPE_MAP = {
    "entity": ObjectType.ENTITY,
    "view": ObjectType.VIEW,
    "virtual": ObjectType.VIRTUAL,
}

FIELD_STORAGE_MAP = {
    "stored": FieldStorage.STORED,
    "virtual": FieldStorage.VIRTUAL,
}

FIELD_SOURCE_MAP = {
    "own": FieldSource.OWN,
    "mapped": FieldSource.MAPPED,
    "computed": FieldSource.COMPUTED,
    "derived": FieldSource.DERIVED,
    "aggregated": FieldSource.AGGREGATED,
}


def parse_index_hint(data: Optional[Dict[str, Any]]) -> Optional[IndexHint]:
    """解析字段级索引提示（借鉴 SAP CDS @AbapCatalog.index + Salesforce IsIndexed）"""
    if not data:
        return None
    
    return IndexHint(
        indexed=data.get("indexed", False),
        unique=data.get("unique", False),
        priority=data.get("priority", "medium"),
        auto_create=data.get("auto_create", True),
        include_in_composite=data.get("include_in_composite", False),
        search_weight=data.get("search_weight", 0),
    )


def parse_semantics(data: Dict[str, Any]) -> SemanticAnnotation:
    """解析语义标注"""
    if not data:
        return SemanticAnnotation()
    
    return SemanticAnnotation(
        meaning=data.get("meaning", ""),
        business_key=data.get("business_key", False),
        display_name=data.get("display_name", False),
        pattern=data.get("pattern", ""),
        examples=data.get("examples", []),
        aliases=data.get("aliases", []),
        category=data.get("category", ""),
        hierarchy_level=data.get("hierarchy_level", 0),
        custom=data.get("custom", {}),
        data_category=data.get("data_category", ""),
        import_visible=data.get("import_visible", True),
        export_visible=data.get("export_visible", True),
        import_order=data.get("import_order", 100),
        virtual=data.get("virtual", False),
        immutable=data.get("immutable", False),
        parent_key=data.get("parent_key", False),
        mandatory=data.get("mandatory", False),
        readonly_always=data.get("readonly_always", False),
        context_field=data.get("context_field", False),
        search_help_for=data.get("search_help_for", None),
        resolve_from_field=data.get("resolve_from_field", ""),
        resolve_to_object=data.get("resolve_to_object", ""),
        resolve_to_field=data.get("resolve_to_field", ""),
        auto_fill=data.get("auto_fill", {}),
        analytics=data.get("analytics", {}),
        index_hint=parse_index_hint(data.get("index_hint", None)),
        redundancy=data.get("redundancy", {}),
        computed_by=data.get("computed_by", ""),
        sort_transform=data.get("sort_transform", {}),
        filter_transform=data.get("filter_transform", {}),
        scope_rules_ref=data.get("scope_rules_ref", ""),
        enum_type_ref=data.get("enum_type_ref", ""),
        enum_join_fields=data.get("enum_join_fields", []),
        # 过滤字段定义（元模型驱动过滤系统）
        filterable=data.get("filterable", False),
        filter_type=data.get("filter_type", "text"),
        filter_label=data.get("filter_label", None),
        filter_placeholder=data.get("filter_placeholder", None),
        filter_default=data.get("filter_default", None),
        filter_scope=data.get("filter_scope", "both"),
        filter_options=data.get("filter_options", []),
        filter_mandatory=data.get("filter_mandatory", False),
        filter_operator=data.get("filter_operator", "eq"),
    )


def parse_import_export_config(data: Dict[str, Any]) -> ImportExportConfig:
    """解析导入导出配置"""
    if not data:
        return ImportExportConfig()
    
    return ImportExportConfig(
        import_enabled=data.get("import_enabled", True),
        export_enabled=data.get("export_enabled", True),
        cascade_export=data.get("cascade_export", True),
        cascade_import=data.get("cascade_import", True),
        conflict_strategy=data.get("conflict_strategy", "upsert"),
        conflict_key=data.get("conflict_key", ""),
        description_for_agent=data.get("description_for_agent", ""),
    )


def parse_audit_action_config(data: Dict[str, Any]) -> "AuditActionConfig":
    """解析单个动作的审计配置"""
    from meta.core.models import AuditActionConfig
    return AuditActionConfig(
        enabled=data.get("enabled", True),
        fields=data.get("fields", "all"),
        exclude=data.get("exclude", []),
        log_message=data.get("log_message", ""),
    )


def parse_audit_config(data: Dict[str, Any]) -> "AuditConfig":
    """解析审计日志配置"""
    from meta.core.models import AuditConfig, AuditActionConfig
    if not data:
        return AuditConfig()
    
    config = AuditConfig(
        enabled=data.get("enabled", True),
    )
    
    if "create" in data:
        config.create = parse_audit_action_config(data["create"])
    if "update" in data:
        config.update = parse_audit_action_config(data["update"])
    if "delete" in data:
        config.delete = parse_audit_action_config(data["delete"])
    if "associate" in data:
        config.associate = parse_audit_action_config(data["associate"])
    
    if "actions" in data:
        for action_name, action_data in data["actions"].items():
            config.actions[action_name] = parse_audit_action_config(action_data)
    
    return config


def parse_render_hints(data: Dict[str, Any]) -> Optional["RenderHints"]:
    """解析渲染提示"""
    if not data or "render_hints" not in data:
        return None
    rh = data["render_hints"]
    from meta.core.models import RenderHints
    return RenderHints(
        searchable=rh.get("searchable", True),
        sortable=rh.get("sortable", True),
        prominent=rh.get("prominent", False),
        display_mode=rh.get("display_mode", "auto"),
        hidden_if_empty=rh.get("hidden_if_empty", False),
        show_in_summary=rh.get("show_in_summary", True),
        show_in_detail=rh.get("show_in_detail", True),
        show_in_list=rh.get("show_in_list", True),
        column_width=rh.get("column_width", 0),
        min_width=rh.get("min_width", 0),
        max_width=rh.get("max_width", 0),
        text_align=rh.get("text_align", "left"),
        format_pattern=rh.get("format_pattern", ""),
        placeholder=rh.get("placeholder", ""),
        help_text=rh.get("help_text", ""),
    )


def parse_value_help(data: Dict[str, Any]) -> Optional["ValueHelpConfig"]:
    """解析值帮助配置（支持统一三层架构和旧版兼容）"""
    if not data or "value_help" not in data:
        return None
    vh = data["value_help"]
    from meta.core.models import (
        ValueHelpConfig, ValueHelpSource, ValueHelpBehavior, ValueHelpPresentation,
        ValueHelpParameterBinding, ValueHelpOutMapping, ValueHelpDisplayColumn,
    )

    if any(k in vh for k in ("source", "behavior", "presentation")):
        source = None
        if "source" in vh:
            sd = vh["source"]
            source = ValueHelpSource(
                type=sd.get("type", "enum"),
                enum_type_id=sd.get("enum_type_id", ""),
                filter_by_dimension=sd.get("filter_by_dimension", {}),
                value_filter=sd.get("value_filter", {}),
                sort_by=sd.get("sort_by", ""),
                i18n_join_fields=sd.get("i18n_join_fields", []),
                default_value_code=sd.get("default_value_code", ""),
                target_bo=sd.get("target_bo", ""),
                value_field=sd.get("value_field", "id"),
                display_field=sd.get("display_field", "name"),
                code_field=sd.get("code_field", "code"),
                hierarchy=sd.get("hierarchy", {}),
                apply_target_permissions=sd.get("apply_target_permissions", True),
                endpoint=sd.get("endpoint", ""),
                params=sd.get("params", {}),
            )

        behavior = None
        if "behavior" in vh:
            bd = vh["behavior"]
            param_bindings = []
            for pb in bd.get("parameter_bindings", []):
                param_bindings.append(ValueHelpParameterBinding(
                    local_field=pb.get("local_field", ""),
                    target_field=pb.get("target_field", ""),
                    required=pb.get("required", False),
                    constant=pb.get("constant", ""),
                ))
            out_mappings = []
            for om in bd.get("out_mappings", []):
                out_mappings.append(ValueHelpOutMapping(
                    value_help_field=om.get("value_help_field", ""),
                    local_field=om.get("local_field", ""),
                ))

            cascade_selects = []
            for cs in bd.get("cascade_select", []):
                cascade_selects.append(CascadeSelectConfig(
                    parent_field=cs.get("parent_field", ""),
                    child_field=cs.get("child_field", ""),
                    cascade_source=cs.get("cascade_source", ""),
                    cascade_field=cs.get("cascade_field", ""),
                    required=cs.get("required", False),
                ))

            for cs in bd.get("cascade_select", []):
                param_bindings.append(ValueHelpParameterBinding(
                    local_field=cs.get("child_field", ""),
                    target_field=cs.get("cascade_field", ""),
                    required=cs.get("required", False),
                ))

            behavior = ValueHelpBehavior(
                binding_strength=bd.get("binding_strength", "strict"),
                validation=bd.get("validation", True),
                search_fields=bd.get("search_fields", []),
                min_search_length=bd.get("min_search_length", 0),
                debounce_ms=bd.get("debounce_ms", 300),
                multiple=bd.get("multiple", None),
                parameter_bindings=param_bindings,
                out_mappings=out_mappings,
                cascade_select=cascade_selects,
                enabled_condition=bd.get("enabled_condition", ""),
            )

        presentation = None
        if "presentation" in vh:
            pd = vh["presentation"]
            display_cols = []
            for dc in pd.get("display_columns", []):
                display_cols.append(ValueHelpDisplayColumn(
                    field=dc.get("field", ""),
                    label=dc.get("label", ""),
                    width=dc.get("width", 0),
                    sortable=dc.get("sortable", True),
                ))
            presentation = ValueHelpPresentation(
                result_type=pd.get("result_type", "dropdown"),
                display_mode=pd.get("display_mode", "flat"),
                display_columns=display_cols,
                sort_by=pd.get("sort_by", []),
                page_size=pd.get("page_size", 50),
                display_format=pd.get("display_format", ""),
                color_mapping=pd.get("color_mapping", {}),
            )

        return ValueHelpConfig(
            source=source,
            behavior=behavior,
            presentation=presentation,
        )

    return ValueHelpConfig(
        validation=vh.get("validation", False),
        validation_message=vh.get("validation_message", ""),
        distinct=vh.get("distinct", True),
        label=vh.get("label", ""),
        enabled_condition=vh.get("enabled_condition", ""),
    )


def parse_ui_annotation(data: Dict[str, Any]) -> UIAnnotation:
    """解析 UI 注解"""
    if not data:
        return UIAnnotation()
    
    return UIAnnotation(
        lineItem=data.get("lineItem"),
        fieldGroup=data.get("fieldGroup"),
        fieldGroupPosition=data.get("fieldGroupPosition", 100),
        widget=data.get("widget", "input"),
        visible=data.get("visible", True),
        editable=data.get("editable", True),
        readonly=data.get("readonly", False),
        hidden_in_detail=data.get("hidden_in_detail", False),
        hidden_in_form=data.get("hidden_in_form", False),
        hidden_in_list=data.get("hidden_in_list", False),
        width=data.get("width", "auto"),
        i18n_key=data.get("i18n_key", ""),
        relation=data.get("relation", ""),
        display_field=data.get("display_field", ""),
        depends_on=data.get("depends_on", ""),
        cascade_group=data.get("cascade_group", ""),
        cascade_level=data.get("cascade_level", 0),
        options=data.get("options", []),
        render_hints=parse_render_hints(data),
        value_help=parse_value_help(data),
    )


def parse_permission_annotation(data: Dict[str, Any]) -> PermissionAnnotation:
    """解析权限注解"""
    if not data:
        return PermissionAnnotation()

    return PermissionAnnotation(
        readable=data.get("readable", True),
        writable=data.get("writable", True),
        roles=data.get("roles", []),
    )


def parse_policy_rule(data: Dict[str, Any]) -> 'PolicyRule':
    """解析策略规则"""
    from meta.core.models import PolicyRule
    return PolicyRule(
        when_expr=data.get("when"),
        value=data.get("value"),
        default=data.get("default", False),
    )


def parse_editable_policy(data: Dict[str, Any]) -> 'EditablePolicy':
    """解析可编辑策略"""
    from meta.core.models import EditablePolicy, PolicyRule
    determination_data = data.get("determination", [])
    determination = [parse_policy_rule(d) for d in determination_data]
    return EditablePolicy(
        determination=determination,
        default=data.get("default", True),
    )


def parse_visible_policy(data: Dict[str, Any]) -> 'VisiblePolicy':
    """解析可见性策略"""
    from meta.core.models import VisiblePolicy, PolicyRule
    determination_data = data.get("determination", [])
    determination = [parse_policy_rule(d) for d in determination_data]
    return VisiblePolicy(
        determination=determination,
        default=data.get("default", True),
    )


def parse_required_policy(data: Dict[str, Any]) -> 'RequiredPolicy':
    """解析必填性策略"""
    from meta.core.models import RequiredPolicy, PolicyRule
    determination_data = data.get("determination", [])
    determination = [parse_policy_rule(d) for d in determination_data]
    return RequiredPolicy(
        determination=determination,
        default=data.get("default", False),
    )


def parse_field_policy(data: Dict[str, Any]) -> 'FieldPolicy':
    """解析字段策略"""
    from meta.core.models import FieldPolicy
    editable_policy = None
    visible_policy = None
    required_policy = None
    
    if "editable" in data:
        editable_policy = parse_editable_policy(data["editable"])
    
    if "visible" in data:
        visible_policy = parse_visible_policy(data["visible"])
    
    if "required" in data:
        required_policy = parse_required_policy(data["required"])
    
    return FieldPolicy(
        editable=editable_policy,
        visible=visible_policy,
        required=required_policy,
    )


def parse_i18n_key(data: Dict[str, Any]) -> I18nKey:
    """解析多语言 Key"""
    if not data:
        return I18nKey(key="", default_text="")
    
    if isinstance(data, str):
        return I18nKey(key=data, default_text="")
    
    return I18nKey(
        key=data.get("key", ""),
        default_text=data.get("default_text", ""),
    )


def _convert_filter_options_value(options: List[Any]) -> List[Dict[str, Any]]:
    """转换过滤器选项中的布尔值为整数
    
    YAML 解析器可能将 1/0 转换为布尔值，这会导致过滤匹配失败。
    因为数据库中存储的是整数（1/0），而不是布尔值（True/False）。
    """
    result = []
    for opt in options:
        if isinstance(opt, dict):
            value = opt.get("value", "")
            if value is True:
                value = 1
            elif value is False:
                value = 0
            result.append({
                "value": value,
                "label": opt.get("label", ""),
                "color": opt.get("color", ""),
            })
        else:
            result.append({"value": str(opt), "label": str(opt)})
    return result


def parse_ui_list_view_column(data: Dict[str, Any]) -> UIListViewColumn:
    """解析列表视图列配置"""
    # 解析 filter_options，确保布尔值被正确转换
    raw_filter_options = data.get("filter_options", [])
    filter_options = _convert_filter_options_value(raw_filter_options) if raw_filter_options else []
    # [FIX 2026-06-10] 解析 enum_values (跟 filter_options 格式相同: [{value, label, color}])
    raw_enum_values = data.get("enum_values", [])
    enum_values = _convert_filter_options_value(raw_enum_values) if raw_enum_values else []
    # [FIX 2026-06-13] 列级 value_help: 兼容 value_help (YAML 风格) 和 value_help_config (API 风格)
    col_value_help = data.get("value_help") or data.get("value_help_config") or {}

    return UIListViewColumn(
        key=data.get("key") or data.get("field", ""),
        title=data.get("title") or data.get("label") or data.get("field", ""),  # title fallback to field
        width=data.get("width", "auto"),
        position=data.get("position", 100),
        importance=data.get("importance", "medium"),
        sortable=data.get("sortable", True),
        filterable=data.get("filterable", True),  # 单一事实原则：默认所有字段都可过滤
        filter_type=data.get("filter_type", ""),  # 过滤器类型
        filter_options=filter_options,  # 过滤器选项
        filter_placeholder=data.get("filter_placeholder", ""),  # 过滤器占位符
        i18n_key=data.get("i18n_key", ""),
        field_type=data.get("field_type", "") or data.get("type", ""),  # field_type fallback to type
        format=data.get("format", ""),  # 格式化类型
        enum_type=data.get("enum_type", ""),  # [FIX 2026-06-10] 枚举类型
        enum_values=enum_values,  # [FIX 2026-06-10] 枚举值
        options=data.get("options", []),
        computed=data.get("computed", False),
        computation=data.get("computation", {}),
        editable=data.get("editable", True),  # 是否可编辑，默认True
        default_visible=data.get("defaultVisible", data.get("default_visible", True)),  # 默认可见性
        # [FIX v1.0.9 2026-06-10] 隐藏配置 (让 list 列也能遵守 hidden_in_form)
        hidden_in_form=data.get("hidden_in_form", False),
        hidden_in_detail=data.get("hidden_in_detail", False),
        hidden_in_list=data.get("hidden_in_list", False),
        # [FIX 2026-06-10] 列头过滤时使用的 API 参数名 (默认与 key 相同)
        api_param_key=data.get("api_param_key", ""),
        # [FIX 2026-06-13] FK 列配置: 是否纳入顶部 keyword search
        searchable=data.get("searchable", True),
        # [FIX 2026-06-13] FK 列的 value_help 配置 (YAML 写 value_help, 内部存 value_help_config)
        value_help=col_value_help,
    )


def parse_ui_list_view_config(data: Dict[str, Any], fields: List[Dict[str, Any]] = None) -> UIListViewConfig:
    """解析列表视图配置

    Args:
        data: 列表视图配置数据
        fields: 字段定义列表，用于在title为空时获取中文名称
    """
    if not data:
        return UIListViewConfig()

    # 构建 fields_dict，方便通过 field_id 查找
    fields_dict = {}
    if fields:
        for f in fields:
            fid = f.get("id") or f.get("name")
            if fid:
                fields_dict[fid] = f

    columns = []
    for c in data.get("columns", []):
        col = parse_ui_list_view_column(c)
        # 如果 title 为空，尝试从 fields 获取中文名称
        if not col.title or col.title == col.key:
            field_id = col.key
            if field_id and field_id in fields_dict:
                field_name = fields_dict[field_id].get("name", "")
                if field_name:
                    col.title = field_name
        columns.append(col)
    
    return UIListViewConfig(
        columns=columns,
        defaultSort=data.get("defaultSort", {}),
        searchFields=data.get("searchFields", []),
        filters=data.get("filters", []),
        pageSize=data.get("pageSize", 20),
        selectable=data.get("selectable", True),
        actions=data.get("actions", []),
        batch_actions=data.get("batch_actions", []),
        title=data.get("title", ""),
        description=data.get("description", ""),
        inlineEdit=data.get("inlineEdit", {}),
        detail_mode=data.get("detail_mode", "drawer"),
        detail_path=data.get("detail_path", ""),
    )


def parse_ui_detail_facet(data: Dict[str, Any]) -> UIDetailFacet:
    """解析详情分区配置"""
    actions = []
    for a in data.get("actions", []):
        if isinstance(a, dict):
            actions.append(a.get("id", a.get("name", "")))
        else:
            actions.append(str(a))
    
    return UIDetailFacet(
        title=data.get("title", ""),
        type=data.get("type", "fieldGroup"),
        qualifier=data.get("qualifier", ""),
        fields=data.get("fields", []),
        i18n_key=data.get("i18n_key", ""),
        id=data.get("id", ""),
        label=data.get("label", ""),
        association=data.get("association", ""),
        widget=data.get("widget", ""),
        readonly=data.get("readonly", False),
        pageSize=data.get("pageSize", 20),
        display=data.get("display", "inline"),
        actions=actions,
        customFetcher=data.get("customFetcher", ""),
    )


def parse_ui_detail_tab(data: Dict[str, Any]) -> 'UIDetailTab':
    """解析详情页 Tab 配置"""
    from meta.core.models import UIDetailTab
    
    actions = []
    for a in data.get("actions", []):
        if isinstance(a, dict):
            actions.append(a.get("id", a.get("name", "")))
        else:
            actions.append(str(a))
    
    return UIDetailTab(
        id=data.get("id", ""),
        label=data.get("label", ""),
        type=data.get("type", "fields"),
        fields=data.get("fields", []),
        association=data.get("association", ""),
        widget=data.get("widget", ""),
        actions=actions,
    )


def parse_ui_detail_view_config(data: Dict[str, Any]) -> UIDetailViewConfig:
    """解析详情视图配置"""
    if not data:
        return UIDetailViewConfig()
    
    facets = [parse_ui_detail_facet(f) for f in data.get("facets", [])]
    tabs_data = data.get("tabs", [])
    tabs = [parse_ui_detail_tab(t) for t in tabs_data]
    
    logger.info(f"[YAML Loader] parse_ui_detail_view_config: tabs_data={tabs_data}")
    logger.info(f"[YAML Loader] parse_ui_detail_view_config: tabs={tabs}")
    
    return UIDetailViewConfig(
        facets=facets,
        tabs=tabs,
        title=data.get("title", ""),
        layout=data.get("layout", "tabs"),
        showChangeHistory=data.get("showChangeHistory", True),
        showRelations=data.get("showRelations", True),
    )


def parse_ui_form_section(data: Dict[str, Any]) -> UIFormSection:
    """解析表单分区配置"""
    columns = []
    columns_raw = data.get("columns", [])
    
    # 支持 columns: 2 这种简写形式（表示2列布局）
    if isinstance(columns_raw, int):
        columns = [UIFormColumn(title="", fields=[]) for _ in range(columns_raw)]
    elif isinstance(columns_raw, list):
        for col_data in columns_raw:
            if isinstance(col_data, dict):
                columns.append(UIFormColumn(
                    title=col_data.get("title", ""),
                    fields=col_data.get("fields", []),
                ))
    
    return UIFormSection(
        title=data.get("title", ""),
        fields=data.get("fields", []),
        i18n_key=data.get("i18n_key", ""),
        layout=data.get("layout", "vertical"),
        columns=columns,
    )


def parse_ui_form_view_config(data: Dict[str, Any]) -> UIFormViewConfig:
    """解析表单视图配置"""
    if not data:
        return UIFormViewConfig()
    
    sections = [parse_ui_form_section(s) for s in data.get("sections", [])]
    
    return UIFormViewConfig(
        sections=sections,
        layout=data.get("layout", "vertical"),
    )


def parse_ui_filter_definition(data: Dict[str, Any]) -> UIFilterDefinition:
    """解析筛选器定义"""
    options = []
    for opt in data.get("options", []):
        if isinstance(opt, dict):
            value = opt.get("value", "")
            # YAML 解析器可能将 1/0 转换为布尔值，这里确保布尔值被正确转换回整数
            # 这对于布尔字段的过滤选项特别重要，因为数据库中存储的是整数
            if value is True:
                value = 1
            elif value is False:
                value = 0
            options.append({
                "value": value,
                "label": opt.get("label", ""),
            })
        else:
            options.append({"value": str(opt), "label": str(opt)})
    
    return UIFilterDefinition(
        key=data.get("key", ""),
        title=data.get("title", ""),
        type=data.get("type", ""),
        position=data.get("position", 0),
        default=data.get("default"),
        source=data.get("source", ""),
        display_field=data.get("display_field", ""),
        options=options,
        required=data.get("required", False),
        tree_structure=data.get("tree_structure", ""),
        tree_levels=data.get("tree_levels", []),
        leaf_value_field=data.get("leaf_value_field", "id"),
        show_count=data.get("show_count", True),
        filter_by=data.get("filter_by", ""),
        # [FIX 2026-06-10] 支持 source: enum_value + enum_type 模式
        enum_type=data.get("enum_type", ""),
    )


def parse_ui_filter_view_config(data: Dict[str, Any]) -> UIFilterViewConfig:
    """解析筛选器视图配置"""
    if not data:
        return UIFilterViewConfig()
    
    filters = []
    for filter_data in data.get("filters", []):
        filters.append(parse_ui_filter_definition(filter_data))
    
    return UIFilterViewConfig(filters=filters)


def parse_change_event_config(data: Dict[str, Any]) -> ChangeEventConfig:
    """解析变更事件配置"""
    return ChangeEventConfig(
        type=data.get("type", ""),
        channels=data.get("channels", []),
        track_fields=data.get("track_fields", []),
        payload=data.get("payload", []),
    )


def parse_webhook_config(data: Dict[str, Any]) -> WebhookConfig:
    """解析 Webhook 配置"""
    return WebhookConfig(
        url=data.get("url", ""),
        secret=data.get("secret", ""),
        retry_count=data.get("retry_count", 3),
    )


def parse_change_notification_config(data: Dict[str, Any]) -> ChangeNotificationConfig:
    """解析变更通知配置"""
    if not data:
        return ChangeNotificationConfig()
    
    events = [parse_change_event_config(e) for e in data.get("events", [])]
    
    webhook_config = None
    if data.get("webhook_config"):
        webhook_config = parse_webhook_config(data.get("webhook_config"))
    
    return ChangeNotificationConfig(
        enabled=data.get("enabled", False),
        events=events,
        webhook_config=webhook_config,
    )


def parse_ui_view_config(data: Dict[str, Any], fields: List[Dict[str, Any]] = None) -> UIViewConfig:
    """解析 UI 视图配置

    Args:
        data: UI视图配置数据
        fields: 字段定义列表，用于在title为空时获取中文名称
    """
    if not data:
        return UIViewConfig()

    list_config = parse_ui_list_view_config(data.get("list", {}), fields)
    detail_config = parse_ui_detail_view_config(data.get("detail", {}))
    form_config = parse_ui_form_view_config(data.get("form", {}))
    filter_config = parse_ui_filter_view_config(data.get("filter", {}))

    change_notification_config = None
    if data.get("change_notification"):
        change_notification_config = parse_change_notification_config(data.get("change_notification"))

    return UIViewConfig(
        list=list_config,
        detail=detail_config,
        form=form_config,
        filter=filter_config,
        change_notification=change_notification_config,
        child_sections=data.get("child_sections", []),
    )


def parse_deletability(data: Dict[str, Any]) -> Optional[DeletabilityConfig]:
    if not data:
        return None
    if "deletability" in data:
        d = data["deletability"]
        return DeletabilityConfig(
            condition=d.get("condition", ""),
            message=d.get("message", ""),
        )
    return None


def parse_addability(data: Dict[str, Any]) -> Optional[AddabilityConfig]:
    if not data:
        return None
    if "addability" in data:
        a = data["addability"]
        return AddabilityConfig(
            condition=a.get("condition", ""),
            message=a.get("message", ""),
        )
    return None


def parse_deletion_policy(data: Dict[str, Any]) -> Optional[DeletionPolicy]:
    """解析删除策略配置"""
    if not data or "deletion_policy" not in data:
        return None
    
    dp = data["deletion_policy"]
    
    restrict_rules = []
    restrict_on_raw = dp.get("restrict_on")
    if restrict_on_raw is None:
        restrict_on_raw = []
    for r in restrict_on_raw:
        if isinstance(r, dict):
            restrict_rules.append(RestrictRule(
                table=r.get("table", ""),
                foreign_key=r.get("foreign_key", ""),
                message=r.get("message", ""),
                custom_check_sql=r.get("custom_check_sql"),
            ))
    
    cascade_tables = dp.get("cascade_delete") or []

    soft_del = None
    if dp.get("soft_delete"):
        sd = dp["soft_delete"]
        soft_del = SoftDeleteRule(
            enabled=sd.get("enabled", False),
            soft_delete_field=sd.get("field", "deleted_at"),
            deleted_by_field=sd.get("deleted_by_field", "deleted_by"),
        )
    
    return DeletionPolicy(
        restrict_on=restrict_rules,
        cascade_delete=cascade_tables,
        soft_delete=soft_del,
        post_delete=dp.get("post_delete", []),
    )


def parse_association(data: Dict[str, Any]) -> AssociationDefinition:
    """解析关联关系定义
    
    新增字段：
    - cardinality: 基数（many_to_one/one_to_many/many_to_many）
    - hierarchy: 是否参与层级计算
    - foreign_key_field: 外键字段（显式指定）
    - cascade_delete: 是否级联删除
    """
    actions_dict = {}
    for action_name, action_data in data.get("actions", {}).items():
        if isinstance(action_data, dict):
            actions_dict[action_name] = AssociationActionDef(
                name=action_data.get("name", action_name),
                label=action_data.get("label", ""),
                handler=action_data.get("handler", ""),
                readonly=action_data.get("readonly", False),
                params=action_data.get("params", []),
            )
    
    return AssociationDefinition(
        name=data.get("name", ""),
        type=data.get("type", "association"),
        through=data.get("through"),
        source_key=data.get("source_key", ""),
        target_entity=data.get("target_entity") or data.get("target_type", ""),
        target_key=data.get("target_key") or data.get("foreign_key_target", ""),
        actions=actions_dict,
        cardinality=data.get("cardinality", "many_to_many"),
        hierarchy=data.get("hierarchy", False),
        # [FIX] YAML 中既可能用 foreign_key_field (驼峰)，也可能用 foreign_key_source (下划线)
        foreign_key_field=(
            data.get("foreign_key_field")
            or data.get("foreign_key_source")
        ),
        cascade_delete=data.get("cascade_delete", False),
        polymorphic_type_field=data.get("polymorphic_type_field"),
        polymorphic_id_field=data.get("polymorphic_id_field"),
        async_delete=data.get("async_delete", False),
        max_cardinality=data.get("max_cardinality"),
        allow_reassign=data.get("allow_reassign", False),
        readonly=data.get("readonly", False),
    )


def parse_hierarchy(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """解析层级配置"""
    hierarchy = data.get('hierarchy')
    if hierarchy is None:
        return None
    if isinstance(hierarchy, dict):
        return hierarchy
    return None


def parse_context(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """解析上下文配置"""
    context = data.get('context')
    if context is None:
        return None
    if isinstance(context, dict):
        return context
    return None


def parse_cascade_select(data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """解析级联选择配置"""
    cascade = data.get('cascade_select')
    if cascade is None:
        return None
    if isinstance(cascade, list):
        return cascade
    return None


def parse_key_template(data: Dict[str, Any]) -> Dict[str, Any]:
    """解析 key_template 配置，支持 sequence 子配置块"""
    kt = data.get("key_template")
    if not kt or not isinstance(kt, dict):
        return data.get("key_template", {})

    seq_data = kt.get("sequence")
    if seq_data and isinstance(seq_data, dict):
        sequence = {}
        sequence["start"] = seq_data.get("start", 1)
        sequence["step"] = seq_data.get("step", 1)
        sequence["padding"] = seq_data.get("padding", 0)
        reset_val = seq_data.get("reset_strategy", seq_data.get("reset", ""))
        sequence["reset_strategy"] = reset_val
        scope_val = seq_data.get("reset_scope", seq_data.get("scope_fields", []))
        if isinstance(scope_val, str):
            scope_val = [scope_val]
        sequence["reset_scope"] = scope_val
        kt["sequence"] = sequence

    return kt


def parse_associations(data: Dict[str, Any]) -> Dict[str, AssociationDefinition]:
    """解析所有关联关系，支持dict和list两种格式"""
    result = {}
    raw = data.get("associations", {})
    if isinstance(raw, list):
        for assoc_data in raw:
            if isinstance(assoc_data, dict):
                assoc_name = assoc_data.get("name", "")
                if assoc_name:
                    result[assoc_name] = parse_association(assoc_data)
    elif isinstance(raw, dict):
        for assoc_name, assoc_data in raw.items():
            if isinstance(assoc_data, dict):
                result[assoc_name] = parse_association(assoc_data)
    return result


def derive_parent_object(associations: Dict[str, AssociationDefinition]) -> Optional[str]:
    """从 Association 配置推导 parent_object
    
    规则：
    1. 查找 cardinality='many_to_one' 且 type='composition' 的 Association
    2. 其 target_entity 即为 parent_object
    
    Args:
        associations: 解析后的 Association 字典
        
    Returns:
        parent_object 名称，如果不存在则返回 None
    """
    for assoc in associations.values():
        if (assoc.cardinality == 'many_to_one' and 
            assoc.type == 'composition'):
            return assoc.target_entity
    return None


def derive_foreign_key_field(associations: Dict[str, AssociationDefinition]) -> Optional[str]:
    """从 Association 配置推导 foreign_key_field
    
    规则：
    1. 查找 cardinality='many_to_one' 且 type='composition' 的 Association
    2. 优先使用显式配置的 foreign_key_field
    3. 否则自动推导：target_entity + "_id"
    
    Args:
        associations: 解析后的 Association 字典
        
    Returns:
        foreign_key_field 名称，如果不存在则返回 None
    """
    for assoc in associations.values():
        if (assoc.cardinality == 'many_to_one' and 
            assoc.type == 'composition'):
            if assoc.foreign_key_field:
                return assoc.foreign_key_field
            if assoc.target_entity:
                return f"{assoc.target_entity}_id"
    return None


def derive_hierarchy_fields(associations: Dict[str, AssociationDefinition]) -> Dict[str, Optional[str]]:
    """从 Association 配置推导 path_field 和 depth_field
    
    规则：
    1. 存在 cardinality='one_to_many' 且 hierarchy=True 的 Association 时
    2. 自动生成 path_field='hierarchy_path' 和 depth_field='hierarchy_depth'
    
    Args:
        associations: 解析后的 Association 字典
        
    Returns:
        包含 path_field 和 depth_field 的字典
    """
    has_hierarchy = any(
        assoc.cardinality == 'one_to_many' and assoc.hierarchy
        for assoc in associations.values()
    )
    
    return {
        'path_field': 'hierarchy_path' if has_hierarchy else None,
        'depth_field': 'hierarchy_depth' if has_hierarchy else None
    }


def parse_behavior(data: Dict[str, Any]) -> Optional[ActionBehavior]:
    if not data or "behavior" not in data:
        return None
    b = data["behavior"]
    precondition = None
    if "precondition" in b:
        p = b["precondition"]
        precondition = ActionPrecondition(
            condition=p.get("condition", ""),
            message=p.get("message", ""),
        )
    effects = []
    for e in b.get("effects", []):
        effects.append(ActionEffect(
            type=e.get("type", ""),
            target=e.get("target", "self"),
            fields=e.get("fields", {}),
            handler=e.get("handler", ""),
        ))
    return ActionBehavior(precondition=precondition, effects=effects)


def parse_action_parameter(data: Dict[str, Any]) -> ActionParameter:
    """解析操作参数"""
    return ActionParameter(
        id=data.get("id", ""),
        name=data.get("name", ""),
        type=data.get("type", "string"),
        required=data.get("required", True),
        description=data.get("description", ""),
        default=data.get("default"),
        enum_values=data.get("enum_values", []),
        i18n_key=data.get("i18n_key", ""),
    )


def parse_field(data: Dict[str, Any], included_from: str = "") -> MetaField:
    field_type_str = data.get("type", "string").lower()
    field_type = FIELD_TYPE_MAP.get(field_type_str, FieldType.STRING)

    storage_str = data.get("storage", "stored").lower()
    storage = FIELD_STORAGE_MAP.get(storage_str, FieldStorage.STORED)

    source_str = data.get("source", "own").lower()
    source = FIELD_SOURCE_MAP.get(source_str, FieldSource.OWN)

    ui_annotation = parse_ui_annotation(data.get("ui", {}))
    permission_annotation = parse_permission_annotation(data.get("permission", {}))
    
    semantics_data = data.get("semantics", {})
    if data.get("redundancy"):
        semantics_data = dict(semantics_data)
        semantics_data["redundancy"] = data.get("redundancy")

    field_value_help = parse_value_help(data)
    if not field_value_help:
        field_value_help = _infer_value_help_from_field(data, ui_annotation)

    is_computed = data.get("computed", False)
    if not is_computed and isinstance(semantics_data, dict):
        is_computed = semantics_data.get("computed", False)
    # [FIX] 字段只要声明了 computation.type（如 count_relations），就视为计算字段，
    # 这样 _try_build_computed_filter / _build_computed_count_sort_clause 才能用子查询处理。
    if not is_computed:
        computation_decl = data.get("computation") or {}
        if isinstance(computation_decl, dict) and computation_decl.get("type"):
            is_computed = True

    if isinstance(semantics_data, dict) and semantics_data.get("virtual", False):
        storage = FieldStorage.VIRTUAL

    return MetaField(
        id=data.get("id", ""),
        name=data.get("name", ""),
        field_type=field_type,
        db_column=data.get("db_column", data.get("id", "")),
        required=data.get("required", False),
        unique=data.get("unique", False),
        default=data.get("default"),
        description=data.get("description", ""),
        storage=storage,
        source=source,
        derive_from_object=data.get("derive_from_object", ""),
        derive_from_field=data.get("derive_from_field", ""),
        derive_rule=data.get("derive_rule", ""),
        aggregate_function=data.get("aggregate_function", ""),
        aggregate_source_field=data.get("aggregate_source_field", ""),
        compute_expr=data.get("compute_expr", ""),
        computed=is_computed,
        computation=data.get("computation", {}),
        semantics=parse_semantics(semantics_data),
        validations=[],
        is_hierarchy_path=data.get("is_hierarchy_path", False),
        hierarchy_separator=data.get("hierarchy_separator", "/"),
        ui=ui_annotation,
        permission=permission_annotation,
        enum_values=data.get("enum_values", []),
        included_from=included_from,
        constraints=data.get("constraints", []),
        value_help=field_value_help,
    )


def parse_relation(data: Dict[str, Any]) -> MetaRelation:
    """解析关联关系"""
    rel_type_str = data.get("type", "reference").lower()
    rel_type = RELATION_TYPE_MAP.get(rel_type_str, RelationType.REFERENCE)
    
    return MetaRelation(
        id=data.get("id", ""),
        name=data.get("name", ""),
        relation_type=rel_type,
        target_object=data.get("target", data.get("target_object", "")),
        source_field=data.get("source_field", ""),
        target_field=data.get("target_field", "id"),
        cardinality=data.get("cardinality", "1:N"),
        description=data.get("description", ""),
        semantics=parse_semantics(data.get("semantics", {})),
        cascade_delete=data.get("cascade_delete", False),
        ownership=data.get("ownership", False),
        display_format=data.get("display_format"),
    )


def parse_action(data: Dict[str, Any]) -> MetaAction:
    """解析操作定义"""
    action_type_str = data.get("type", "crud").lower()
    action_type = ACTION_TYPE_MAP.get(action_type_str, ActionType.CRUD)
    
    parameters = [parse_action_parameter(p) for p in data.get("parameters", [])]
    
    return MetaAction(
        id=data.get("id", ""),
        name=data.get("name", ""),
        action_type=action_type,
        method=data.get("method", "GET"),
        path=data.get("path", ""),
        description=data.get("description", ""),
        input_schema=data.get("input_schema", {}),
        output_schema=data.get("output_schema", {}),
        semantics=parse_semantics(data.get("semantics", {})),
        parameters=parameters,
        behavior=parse_behavior(data),
    )


def parse_validation(data: Dict[str, Any]) -> MetaValidation:
    """解析校验规则"""
    severity_str = data.get("severity", "error").lower()
    severity = SEVERITY_MAP.get(severity_str, ValidationSeverity.ERROR)
    
    scope_str = data.get("scope", "field").lower()
    scope = RULE_SCOPE_MAP.get(scope_str, RuleScope.FIELD)
    
    triggers = _parse_triggers(data.get("triggers", []))
    
    return MetaValidation(
        id=data.get("id", ""),
        name=data.get("name", ""),
        scope=scope,
        triggers=triggers,
        condition=data.get("condition", ""),
        action=data.get("action", data.get("rule", "")),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
        message=data.get("message", ""),
        error_code=data.get("error_code", ""),
        description=data.get("description", ""),
        target_fields=data.get("target_fields", []),
        severity=severity,
        validation_mode=data.get("validation_mode", "strict"),
        semantics=parse_semantics(data.get("semantics", {})),
    )


def parse_constraint(data: Dict[str, Any]) -> MetaConstraint:
    """解析约束规则"""
    scope_str = data.get("scope", "object").lower()
    scope = RULE_SCOPE_MAP.get(scope_str, RuleScope.OBJECT)
    
    triggers = _parse_triggers(data.get("triggers", []))
    
    return MetaConstraint(
        id=data.get("id", ""),
        name=data.get("name", ""),
        scope=scope,
        triggers=triggers,
        condition=data.get("condition", ""),
        action=data.get("action", ""),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
        message=data.get("message", ""),
        description=data.get("description", ""),
        constraint_type=data.get("constraint_type", "check"),
        deferrable=data.get("deferrable", False),
        semantics=parse_semantics(data.get("semantics", {})),
    )


def parse_computation(data: Dict[str, Any]) -> MetaComputation:
    """解析计算规则"""
    scope_str = data.get("scope", "field").lower()
    scope = RULE_SCOPE_MAP.get(scope_str, RuleScope.FIELD)
    
    triggers = _parse_triggers(data.get("triggers", []))
    
    return MetaComputation(
        id=data.get("id", ""),
        name=data.get("name", ""),
        scope=scope,
        triggers=triggers,
        condition=data.get("condition", ""),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
        description=data.get("description", ""),
        formula=data.get("formula", data.get("action", "")),
        source_fields=data.get("source_fields", []),
        target_field=data.get("target_field", ""),
        compute_on_change=data.get("compute_on_change", True),
        semantics=parse_semantics(data.get("semantics", {})),
    )


def parse_state_transition_side_effect(data: Dict[str, Any]) -> "StateTransitionSideEffect":
    """解析状态转换副作用"""
    from meta.core.models import StateTransitionSideEffect
    return StateTransitionSideEffect(
        type=data.get("type", ""),
        target=data.get("target", ""),
        value=data.get("value"),
        handler=data.get("handler", ""),
    )


def parse_state_transition_ui_hints(data: Dict[str, Any]) -> Optional["StateTransitionUIHints"]:
    """解析状态转换 UI 提示"""
    if not data or "ui_hints" not in data:
        return None
    uh = data["ui_hints"]
    from meta.core.models import StateTransitionUIHints
    return StateTransitionUIHints(
        hidden=uh.get("hidden", False),
        label=uh.get("label", ""),
        icon=uh.get("icon", ""),
        confirm_message=uh.get("confirm_message", ""),
        highlight=uh.get("highlight", False),
    )


def parse_state_transition(data: Dict[str, Any]) -> MetaStateTransition:
    """解析状态转换规则"""
    scope_str = data.get("scope", "object").lower()
    scope = RULE_SCOPE_MAP.get(scope_str, RuleScope.OBJECT)
    
    triggers = _parse_triggers(data.get("triggers", []))
    
    side_effects = []
    for se in data.get("side_effects", []):
        side_effects.append(parse_state_transition_side_effect(se))
    
    return MetaStateTransition(
        id=data.get("id", ""),
        name=data.get("name", ""),
        scope=scope,
        triggers=triggers,
        condition=data.get("condition", ""),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
        description=data.get("description", ""),
        state_field=data.get("state_field", "status"),
        from_states=data.get("from_states", []),
        to_state=data.get("to_state", ""),
        allowed_roles=data.get("allowed_roles", []),
        auto_actions=data.get("auto_actions", []),
        validation_expression=data.get("validation_expression", ""),
        validation_message=data.get("validation_message", ""),
        side_effects=side_effects,
        ui_hints=parse_state_transition_ui_hints(data),
        semantics=parse_semantics(data.get("semantics", {})),
    )


def parse_trigger_rule(data: Dict[str, Any]) -> MetaTrigger:
    """解析触发规则"""
    scope_str = data.get("scope", "object").lower()
    scope = RULE_SCOPE_MAP.get(scope_str, RuleScope.OBJECT)
    
    triggers = _parse_triggers(data.get("triggers", []))
    
    return MetaTrigger(
        id=data.get("id", ""),
        name=data.get("name", ""),
        scope=scope,
        triggers=triggers,
        condition=data.get("condition", ""),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
        description=data.get("description", ""),
        event_type=data.get("event_type", ""),
        handler=data.get("handler", ""),
        async_exec=data.get("async_exec", True),
        retry_count=data.get("retry_count", 3),
        retry_delay=data.get("retry_delay", 1000),
        semantics=parse_semantics(data.get("semantics", {})),
    )


def _parse_triggers(trigger_list: List[str]) -> List[RuleTrigger]:
    """解析触发时机列表"""
    triggers = []
    for t in trigger_list:
        t_lower = t.lower()
        if t_lower in RULE_TRIGGER_MAP:
            triggers.append(RULE_TRIGGER_MAP[t_lower])
    return triggers


def parse_rule(data: Dict[str, Any]) -> MetaRule:
    """
    解析规则（自动识别类型）
    
    根据规则类型自动选择对应的解析函数
    """
    rule_type_str = data.get("type", "validation").lower()
    rule_type = RULE_TYPE_MAP.get(rule_type_str, RuleType.VALIDATION)
    
    if rule_type == RuleType.VALIDATION:
        return parse_validation(data)
    elif rule_type == RuleType.CONSTRAINT:
        return parse_constraint(data)
    elif rule_type == RuleType.COMPUTATION:
        return parse_computation(data)
    elif rule_type == RuleType.STATE_TRANSITION:
        return parse_state_transition(data)
    elif rule_type == RuleType.TRIGGER:
        return parse_trigger_rule(data)
    else:
        return MetaRule(
            id=data.get("id", ""),
            name=data.get("name", ""),
            rule_type=rule_type,
            scope=RULE_SCOPE_MAP.get(data.get("scope", "field").lower(), RuleScope.FIELD),
            triggers=_parse_triggers(data.get("triggers", [])),
            condition=data.get("condition", ""),
            action=data.get("action", ""),
            priority=data.get("priority", 100),
            enabled=data.get("enabled", True),
            message=data.get("message", ""),
            description=data.get("description", ""),
            semantics=parse_semantics(data.get("semantics", {})),
        )


def parse_query_filter(data: Dict[str, Any]) -> MetaQueryFilter:
    """解析查询过滤条件"""
    operator_str = data.get("operator", "eq").lower()
    operator = OPERATOR_MAP.get(operator_str, QueryOperator.EQ)
    
    return MetaQueryFilter(
        field=data.get("field", ""),
        operator=operator,
        value=data.get("value"),
        param=data.get("param", ""),
        description=data.get("description", ""),
    )


def parse_query_sort(data: Dict[str, Any]) -> MetaQuerySort:
    """解析查询排序"""
    return MetaQuerySort(
        field=data.get("field", ""),
        direction=data.get("direction", "asc"),
    )


def parse_query(data: Dict[str, Any]) -> MetaQuery:
    """解析查询定义"""
    filters = [parse_query_filter(f) for f in data.get("filters", [])]
    sorts = [parse_query_sort(s) for s in data.get("sorts", data.get("order_by", []))]
    
    return MetaQuery(
        id=data.get("id", ""),
        name=data.get("name", ""),
        filters=filters,
        sorts=sorts,
        limit=data.get("limit", 0),
        offset=data.get("offset", 0),
        fields=data.get("fields", []),
        group_by=data.get("group_by", []),
        aggregates=data.get("aggregates", {}),
        description=data.get("description", ""),
        semantics=parse_semantics(data.get("semantics", {})),
    )


def parse_index(data: Dict[str, Any]) -> MetaIndex:
    """解析索引定义（增强版）
    
    支持的索引类型（借鉴 SAP CDS @AbapCatalog.index）：
    - btree: 默认B-Tree索引
    - unique: 唯一索引
    - composite: 复合索引
    - partial: 部分索引（带WHERE条件）
    - fts: 全文索引
    """
    index_type_str = data.get("type", "btree").lower()
    index_type_map = {
        "btree": IndexType.BTREE,
        "unique": IndexType.UNIQUE,
        "composite": IndexType.COMPOSITE,
        "partial": IndexType.PARTIAL,
        "fts": IndexType.FTS,
    }
    index_type = index_type_map.get(index_type_str, IndexType.BTREE)
    
    priority_str = data.get("priority", "medium").lower()
    priority_map = {
        "high": IndexPriority.HIGH,
        "medium": IndexPriority.MEDIUM,
        "low": IndexPriority.LOW,
    }
    priority = priority_map.get(priority_str, IndexPriority.MEDIUM)
    
    source_str = data.get("source", "schema").lower()
    source_map = {
        "schema": IndexSource.SCHEMA,
        "rule_engine": IndexSource.RULE_ENGINE,
        "query_analysis": IndexSource.QUERY_ANALYSIS,
        "manual": IndexSource.MANUAL,
    }
    source = source_map.get(source_str, IndexSource.SCHEMA)
    
    if index_type == IndexType.UNIQUE:
        unique = True
    else:
        unique = data.get("unique", False)
    
    return MetaIndex(
        fields=data.get("fields", []),
        name=data.get("name", ""),
        unique=unique,
        description=data.get("description", ""),
        index_type=index_type,
        priority=priority,
        source=source,
        condition=data.get("condition", ""),
        auto_create=data.get("auto_create", True),
        db_columns=data.get("db_columns", []),
    )


def parse_view_source(data: Dict[str, Any]) -> ViewSource:
    """解析视图数据源"""
    return ViewSource(
        object=data.get("object", ""),
        alias=data.get("alias", ""),
    )


def parse_view_join(data: Dict[str, Any]) -> ViewJoin:
    """解析视图关联"""
    return ViewJoin(
        type=data.get("type", "left"),
        source=data.get("source", ""),
        target=data.get("target", ""),
        condition=data.get("condition", ""),
    )


def parse_view_aggregate(data: Dict[str, Any]) -> ViewAggregate:
    """解析视图聚合"""
    return ViewAggregate(
        field=data.get("field", ""),
        function=data.get("function", ""),
        alias=data.get("alias", ""),
    )


def parse_view_filter(data: Dict[str, Any]) -> ViewFilter:
    """解析视图过滤"""
    return ViewFilter(
        field=data.get("field", ""),
        operator=data.get("operator", "eq"),
        value=data.get("value"),
    )


def parse_view_config(data: Dict[str, Any]) -> ViewConfig:
    """解析视图配置"""
    sources = [parse_view_source(s) for s in data.get("sources", [])]
    joins = [parse_view_join(j) for j in data.get("joins", [])]
    aggregates = [parse_view_aggregate(a) for a in data.get("aggregates", [])]
    filters = [parse_view_filter(f) for f in data.get("filters", [])]
    
    return ViewConfig(
        sources=sources,
        joins=joins,
        group_by=data.get("group_by", []),
        aggregates=aggregates,
        having=data.get("having", ""),
        filters=filters,
        order_by=data.get("order_by", []),
        sql_definition=data.get("sql_definition", ""),
        cache_enabled=data.get("cache_enabled", False),
        cache_ttl=data.get("cache_ttl", 3600),
    )


def parse_virtual_config(data: Dict[str, Any]) -> VirtualConfig:
    """解析虚拟对象配置"""
    return VirtualConfig(
        usage=data.get("usage", "general"),
        source_type=data.get("source_type", "memory"),
        lifecycle=data.get("lifecycle", "transient"),
        serializable=data.get("serializable", True),
        api_config=data.get("api_config"),
    )


def parse_metric_ref(data: Dict[str, Any]) -> MetricReference:
    """解析指标引用"""
    return MetricReference(
        object_id=data.get("object_id", ""),
        field_id=data.get("field_id", ""),
        function_id=data.get("function_id", ""),
        filter=data.get("filter", ""),
    )


def parse_function(data: Dict[str, Any]) -> MetaFunction:
    """解析计算函数"""
    return_type_str = data.get("return_type", "float").lower()
    return_type = FIELD_TYPE_MAP.get(return_type_str, FieldType.FLOAT)
    
    return MetaFunction(
        id=data.get("id", ""),
        name=data.get("name", ""),
        expression=data.get("expression", ""),
        return_type=return_type,
        parameters=data.get("parameters", []),
        references=data.get("references", []),
        description=data.get("description", ""),
        semantics=parse_semantics(data.get("semantics", {})),
    )


def _resolve_authorization(object_id: str, auth_config: Dict) -> Optional[Dict]:
    if not auth_config:
        return None

    resolved = {}

    if auth_config.get("check", False):
        resolved["check"] = True
        resolved["permissions"] = dict(auth_config.get("permissions", {}))
        if "scope" in auth_config:
            resolved["scope"] = auth_config["scope"]
        for action in ("create", "read", "update", "delete"):
            if action not in resolved["permissions"] or not resolved["permissions"][action]:
                resolved["permissions"][action] = "{0}:{1}".format(object_id, action)

    if "scope" in auth_config and "scope" not in resolved:
        resolved["scope"] = auth_config["scope"]

    if "auto_owner" in auth_config:
        resolved["auto_owner"] = auth_config["auto_owner"]

    if "auto_permission" in auth_config:
        resolved["auto_permission"] = auth_config["auto_permission"]

    if "inherit_to_children" in auth_config:
        resolved["inherit_to_children"] = auth_config["inherit_to_children"]

    return resolved if resolved else None


def parse_shared_properties(schema_dir: str = None) -> Dict[str, List[Dict[str, Any]]]:
    if schema_dir is None:
        schema_dir = str(Path(__file__).parent.parent / "schemas")
    sp_path = os.path.join(schema_dir, "shared_properties.yaml")
    if not os.path.exists(sp_path):
        return {}
    try:
        with open(sp_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or not isinstance(data, dict):
            return {}
        return data
    except Exception as e:
        print("[YAML Loader] Error loading shared_properties.yaml: {0}".format(str(e)))
        return {}


def parse_aspects_yaml(schema_dir: str) -> Dict[str, Dict]:
    aspects_path = os.path.join(schema_dir, "aspects.yaml")
    result: Dict[str, Dict] = {}

    if os.path.exists(aspects_path):
        try:
            with open(aspects_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and isinstance(data, dict):
                for aspect_name, aspect_def in data.items():
                    if isinstance(aspect_def, dict):
                        result[aspect_name] = {
                            "fields": aspect_def.get("fields", []),
                            "validations": aspect_def.get("validations", []),
                            "rules": aspect_def.get("rules", []),
                        }
                    elif isinstance(aspect_def, list):
                        result[aspect_name] = {
                            "fields": aspect_def,
                            "validations": [],
                            "rules": [],
                        }
        except Exception as e:
            print("[YAML Loader] Error loading aspects.yaml: {0}".format(str(e)))

    sp_path = os.path.join(schema_dir, "shared_properties.yaml")
    if os.path.exists(sp_path):
        try:
            with open(sp_path, "r", encoding="utf-8") as f:
                sp_data = yaml.safe_load(f)
            if sp_data and isinstance(sp_data, dict):
                for group_name, group_fields in sp_data.items():
                    if group_name not in result:
                        if isinstance(group_fields, list):
                            result[group_name] = {
                                "fields": group_fields,
                                "validations": [],
                                "rules": [],
                            }
        except Exception as e:
            print("[YAML Loader] Error loading shared_properties.yaml for aspects: {0}".format(str(e)))

    return result


def _resolve_aspects(
    data: Dict[str, Any],
    aspects_defs: Dict[str, Dict],
    shared_props: Dict[str, List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    aspect_names = data.get("aspects", [])
    includes = data.get("includes", [])
    if not aspect_names and includes:
        aspect_names = includes
    if not aspect_names:
        return data

    local_field_ids = set()
    for f in data.get("fields", []):
        local_field_ids.add(f.get("id", ""))

    merged_fields = []
    merged_validations = []
    merged_rules = []
    seen_field_ids: Dict[str, str] = {}

    for aspect_name in aspect_names:
        aspect_def = aspects_defs.get(aspect_name)
        if aspect_def is None:
            if shared_props:
                group_fields = shared_props.get(aspect_name, [])
                for sf in group_fields:
                    sf_copy = dict(sf)
                    sf_copy["included_from"] = aspect_name
                    merged_fields.append(sf_copy)
            continue

        aspect_fields = aspect_def.get("fields", [])
        for sf in aspect_fields:
            sf_copy = dict(sf)
            sf_id = sf_copy.get("id", "")
            if sf_id in seen_field_ids:
                print("[YAML Loader] Warning: field '{0}' from aspect '{1}' overrides aspect '{2}'".format(
                    sf_id, aspect_name, seen_field_ids[sf_id]))
            sf_copy["included_from"] = aspect_name
            seen_field_ids[sf_id] = aspect_name
            merged_fields.append(sf_copy)

        for val_data in aspect_def.get("validations", []):
            val_copy = dict(val_data)
            original_id = val_copy.get("id", "")
            if original_id:
                val_copy["id"] = "{0}__{1}".format(aspect_name, original_id)
            merged_validations.append(val_copy)

        for rule_data in aspect_def.get("rules", []):
            rule_copy = dict(rule_data)
            original_id = rule_copy.get("id", "")
            if original_id:
                rule_copy["id"] = "{0}__{1}".format(aspect_name, original_id)
            merged_rules.append(rule_copy)

    existing_fields = data.get("fields", [])
    final_fields = []
    for mf in merged_fields:
        mf_id = mf.get("id", "")
        if mf_id not in local_field_ids:
            final_fields.append(mf)
        else:
            for lf in existing_fields:
                if lf.get("id", "") == mf_id:
                    lf["included_from"] = mf.get("included_from", "")
                    break
    final_fields.extend(existing_fields)

    data = dict(data)
    data["fields"] = final_fields
    data["aspects"] = aspect_names
    data["includes"] = includes

    if merged_validations:
        existing_validations = list(data.get("validations", []))
        existing_validations.extend(merged_validations)
        data["validations"] = existing_validations

    if merged_rules:
        existing_rules = list(data.get("rules", []))
        existing_rules.extend(merged_rules)
        data["rules"] = existing_rules

    return data


def _resolve_includes_compat(data: Dict[str, Any], shared_props: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return _resolve_aspects(data, aspects_defs={}, shared_props=shared_props)


_resolve_includes = _resolve_includes_compat


def parse_meta_object(data: Dict[str, Any]) -> MetaObject:
    fields = [parse_field(f, included_from=f.get("included_from", "")) for f in data.get("fields", [])]
    relations = [parse_relation(r) for r in data.get("relations", [])]
    actions = [parse_action(a) for a in data.get("actions", [])]
    validations = [parse_validation(v) for v in data.get("validations", [])]
    queries = [parse_query(q) for q in data.get("queries", [])]
    rules = [parse_rule(r) for r in data.get("rules", [])]
    indexes = [parse_index(i) for i in data.get("indexes", [])]
    functions = [parse_function(f) for f in data.get("functions", [])]
    
    object_type_str = data.get("object_type", "entity").lower()
    object_type = OBJECT_TYPE_MAP.get(object_type_str, ObjectType.ENTITY)
    
    view_config = None
    if data.get("view_config"):
        view_config = parse_view_config(data.get("view_config"))
    
    virtual_config = None
    if data.get("virtual_config"):
        virtual_config = parse_virtual_config(data.get("virtual_config"))
    
    ui_view_config = parse_ui_view_config(data.get("ui_view_config", {}), data.get("fields"))

    ui_view_configs = {}
    for name, config in data.get("ui_view_configs", {}).items():
        ui_view_configs[name] = parse_ui_view_config(config, data.get("fields"))

    authorization = _resolve_authorization(
        data.get("id", ""),
        data.get("authorization", None),
    )

    aspects = data.get("aspects", [])
    includes = data.get("includes", [])
    if not aspects and includes:
        aspects = includes

    obj = MetaObject(
        id=data.get("id", ""),
        name=data.get("name", ""),
        table_name=data.get("table_name", ""),
        description=data.get("description", ""),
        object_type=object_type,
        view_config=view_config,
        virtual_config=virtual_config,
        base_objects=data.get("base_objects", []),
        includes=includes,
        aspects=aspects,
        functions=functions,
        persistent=data.get("persistent", True),
        is_view=data.get("is_view", False),
        view_definition=data.get("view_definition", ""),
        soft_delete=data.get("soft_delete", False),
        soft_delete_field=data.get("soft_delete_field", "is_deleted"),
        soft_delete_value=data.get("soft_delete_value", True),
        soft_delete_undelete_value=data.get("soft_delete_undelete_value", False),
        fields=fields,
        relations=relations,
        indexes=indexes,
        actions=actions,
        validations=validations,
        rules=rules,
        queries=queries,
        parent_object=data.get("parent_object", data.get("parent", "")),
        semantics=parse_semantics(data.get("semantics", {})),
        import_export=parse_import_export_config(data.get("import_export", {})),
        audit=parse_audit_config(data.get("audit", {})),
        analytical_model=data.get("analytical_model", {}),
        key_template=parse_key_template(data),
        ui_view_config=ui_view_config,
        ui_view_configs=ui_view_configs,
        authorization=authorization,
        deletability=parse_deletability(data),
        addability=parse_addability(data),
        display_name_field=data.get("display_name_field"),
    )
    obj._deletion_policy = parse_deletion_policy(data)
    obj.associations = parse_associations(data)
    obj.deletion_policy = parse_deletion_policy(data)
    obj.hierarchy = parse_hierarchy(data)
    obj.context = parse_context(data)
    obj.cascade_select = parse_cascade_select(data)
    
    associations = obj.associations
    if associations:
        derived_parent = derive_parent_object(associations)
        if not obj.parent_object and derived_parent:
            obj.parent_object = derived_parent
        
        derived_fk = derive_foreign_key_field(associations)
        if derived_fk:
            if obj.hierarchy is None:
                obj.hierarchy = {}
            if not obj.hierarchy.get('foreign_key_field'):
                obj.hierarchy['foreign_key_field'] = derived_fk
        
        derived_hierarchy_fields = derive_hierarchy_fields(associations)
        if derived_hierarchy_fields['path_field']:
            if obj.hierarchy is None:
                obj.hierarchy = {}
            if not obj.hierarchy.get('path_field'):
                obj.hierarchy['path_field'] = derived_hierarchy_fields['path_field']
            if not obj.hierarchy.get('depth_field'):
                obj.hierarchy['depth_field'] = derived_hierarchy_fields['depth_field']
    
    return obj


_yaml_cache = {}
_shared_mtimes = {}
_dir_registry_cache = {}

def _get_file_cache_key(file_path: str) -> Optional[str]:
    """获取文件缓存键（基于 file_path + mtime），如果文件不存在返回 None

    [FIX v3.18 2026-06-10] 修复 cache key 撞车 bug：
    原实现只返回 mtime，但 mtime 只到秒/毫秒精度。如果两个文件同时被修改
    (例如 git checkout, 批量导入)，mtime 完全相同，cache 会返回错对象，
    导致 `sub_domain.yaml` 加载为 `business_object` 等诡异 bug。
    现改为 (str(file_path) + mtime) 作为 key。
    """
    try:
        p = Path(file_path)
        if not p.exists():
            return None
        # 必须包含 path 才能避免撞 key
        return f"{p.resolve()}|{p.stat().st_mtime}"
    except Exception:
        return None


def _check_and_invalidate_shared_cache(shared_path: Path, aspects_path: Path):
    """检查 shared_properties/aspects 是否变更，若是则使全缓存失效"""
    for path in (shared_path, aspects_path):
        try:
            if path.exists():
                mtime = str(path.stat().st_mtime)
                if path.name in _shared_mtimes and _shared_mtimes[path.name] != mtime:
                    _yaml_cache.clear()
                    break
                _shared_mtimes[path.name] = mtime
        except Exception:
            pass


def _invalidate_yaml_cache():
    """使所有 YAML 缓存失效"""
    _yaml_cache.clear()
    _shared_mtimes.clear()


def load_yaml_file(file_path: str, shared_props: Dict[str, List[Dict[str, Any]]] = None, aspects_defs: Dict[str, Dict] = None) -> Optional[MetaObject]:
    cache_key = _get_file_cache_key(file_path)
    if cache_key and cache_key in _yaml_cache:
        return _yaml_cache[cache_key]

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        if aspects_defs:
            data = _resolve_aspects(data, aspects_defs, shared_props=shared_props)
        elif shared_props:
            data = _resolve_includes(data, shared_props)

        obj = parse_meta_object(data)

        obj = ensure_crud_actions(obj)
        
        if cache_key:
            _yaml_cache[cache_key] = obj
        return obj
    except Exception as e:
        print("[YAML Loader] Error loading {0}: {1}".format(file_path, str(e)))
        return None


CRUD_ACTION_TEMPLATES = {
    "_create": {
        "name": "创建",
        "type": "crud",
        "method": "POST",
        "path": "/api/v1/{object_id}s",
        "description": "创建新记录"
    },
    "_read": {
        "name": "查询",
        "type": "crud",
        "method": "GET",
        "path": "/api/v1/{object_id}s/{{id}}",
        "description": "查询单个记录"
    },
    "_update": {
        "name": "更新",
        "type": "crud",
        "method": "PUT",
        "path": "/api/v1/{object_id}s/{{id}}",
        "description": "更新记录"
    },
    "_delete": {
        "name": "删除",
        "type": "crud",
        "method": "DELETE",
        "path": "/api/v1/{object_id}s/{{id}}",
        "description": "删除记录"
    },
    "_list": {
        "name": "列表查询",
        "type": "crud",
        "method": "GET",
        "path": "/api/v1/{object_id}s",
        "description": "查询记录列表"
    }
}


def ensure_crud_actions(obj: 'MetaObject') -> 'MetaObject':
    """
    确保元数据对象包含完整的CRUD基础actions
    
    如果对象缺少某些CRUD action，自动补充。
    这保证了每个持久化对象都有完整的CRUD能力。
    如果对象已经明确定义了某些actions（通过检查 import_export.auto_crud 配置），则不自动添加。
    """
    if not obj.persistent:
        return obj
    
    # 检查是否禁用自动添加 CRUD actions
    if hasattr(obj, 'import_export') and obj.import_export:
        if hasattr(obj.import_export, 'auto_crud') and obj.import_export.auto_crud is False:
            print(f"[YAML Loader] Auto-crud disabled for object '{obj.id}', skipping automatic action addition")
            return obj
    
    existing_ids = {action.id for action in obj.actions}
    
    crud_suffixes = ['_create', '_read', '_update', '_delete', '_list']
    bo_crud_ids = {f'{obj.id}{s}' for s in crud_suffixes}
    legacy_crud_ids = {'crud_create', 'crud_read', 'crud_update', 'crud_delete', 'crud_list'}
    
    has_any_crud = any(cid in existing_ids for cid in bo_crud_ids)
    has_legacy_crud = any(cid in existing_ids for cid in legacy_crud_ids)
    
    if has_any_crud:
        print(f"[YAML Loader] Object '{obj.id}' already has {obj.id}_* CRUD actions defined, skipping automatic addition")
        return obj
    
    if has_legacy_crud:
        print(f"[YAML Loader] Object '{obj.id}' uses legacy crud_* naming, keeping existing actions")
        return obj
    
    missing_actions = []
    
    for suffix, action_template in CRUD_ACTION_TEMPLATES.items():
        action_id = f'{obj.id}{suffix}'
        if action_id not in existing_ids:
            path = action_template["path"].format(object_id=obj.id)
            action_data = {
                "id": action_id,
                "name": f"{obj.name}{action_template['name']}",
                "type": action_template["type"],
                "method": action_template["method"],
                "path": path,
                "description": f"{obj.name}的{action_template['description']}"
            }
            new_action = parse_action(action_data)
            missing_actions.append(new_action)
            print(f"[YAML Loader] Auto-added missing action '{action_id}' for object '{obj.id}'")
    
    if missing_actions:
        obj.actions = obj.actions + missing_actions
    
    return obj


def load_yaml_directory(dir_path: str) -> List[MetaObject]:
    objects = []
    dir_path = Path(dir_path)
    
    if not dir_path.exists():
        print("[YAML Loader] Directory not found: {0}".format(dir_path))
        return objects
    
    shared_path = dir_path / "shared_properties.yaml"
    aspects_path = dir_path / "aspects.yaml"

    _check_and_invalidate_shared_cache(shared_path, aspects_path)
    
    shared_props = parse_shared_properties(str(dir_path))
    aspects_defs = parse_aspects_yaml(str(dir_path))
    
    for yaml_file in dir_path.glob("*.yaml"):
        if yaml_file.name in ("shared_properties.yaml", "aspects.yaml", "_standard_actions.yaml", "_action_groups.yaml"):
            continue
        obj = load_yaml_file(str(yaml_file), shared_props=shared_props, aspects_defs=aspects_defs if aspects_defs else None)
        if obj:
            objects.append(obj)
            print("[YAML Loader] Loaded: {0} from {1}".format(obj.id, yaml_file.name))
    
    return objects


def register_from_yaml(file_path: str, shared_props: Dict[str, List[Dict[str, Any]]] = None) -> bool:
    obj = load_yaml_file(file_path, shared_props=shared_props)
    if obj:
        registry.register(obj)
        return True
    return False


def register_from_directory(dir_path: str, target: Dict = None) -> int:
    """
    从目录加载并注册所有 YAML 元模型
    
    Args:
        dir_path: 目录路径
        target: 目标字典，如果提供则写入到该字典而非全局注册表
        
    Returns:
        注册成功的数量
        
    Note:
        使用目录级别缓存避免重复加载。对于全局注册（target=None），
        同一目录只会在首次调用时实际加载，后续调用直接返回缓存结果。
        对于传入 target 的情况，不使用缓存（允许独立加载到不同字典）。
    """
    from meta.core.models import MetaRegistry
    canonical_dir = str(Path(dir_path).resolve())
    
    # 检查是否强制重新加载
    if target is None and canonical_dir in _dir_registry_cache and not MetaRegistry.__force_reload__:
        if registry._objects:
            cached_count = _dir_registry_cache[canonical_dir]
            print("[YAML Loader] Using cached registration for directory: {0} ({1} objects)".format(
                canonical_dir, cached_count))
            return cached_count
    
    count = 0
    objects = load_yaml_directory(dir_path)
    
    if target is not None:
        for obj in objects:
            target[obj.id] = obj
            count += 1
    else:
        for obj in objects:
            registry.register(obj)
            count += 1
        _dir_registry_cache[canonical_dir] = count
    
    return count


def get_meta_object(object_id: str) -> Optional['MetaObject']:
    """获取元数据对象
    
    便捷函数，用于测试和快速访问元数据
    """
    return registry.get(object_id)


def get_yaml_schema_dir() -> str:
    current_dir = Path(__file__).parent.parent
    return str(current_dir / "schemas")


def _infer_value_help_from_field(data: Dict[str, Any], ui_annotation) -> Optional["ValueHelpConfig"]:
    if not ui_annotation:
        return None
    widget = getattr(ui_annotation, 'widget', '') or ''
    relation = getattr(ui_annotation, 'relation', '') or ''
    if widget not in ('select', 'lookup', 'select_with_search', 'association_selector'):
        return None
    from meta.core.models import (
        ValueHelpConfig, ValueHelpSource, ValueHelpBehavior, ValueHelpPresentation,
    )
    field_type = (data.get('type') or '').lower()
    is_fk_field = field_type in ('integer', 'int', 'long') and relation
    if relation and is_fk_field:
        return ValueHelpConfig(
            source=ValueHelpSource(type="bo", target_bo=relation, apply_target_permissions=True),
            behavior=ValueHelpBehavior(binding_strength="strict", validation=True),
            presentation=ValueHelpPresentation(result_type="dropdown"),
        )
    if relation and widget in ('select', 'select_with_search'):
        return ValueHelpConfig(
            source=ValueHelpSource(type="enum", enum_type_id=relation),
            behavior=ValueHelpBehavior(binding_strength="strict", validation=True),
            presentation=ValueHelpPresentation(result_type="dropdown"),
        )
    if relation and widget in ('lookup', 'association_selector'):
        return ValueHelpConfig(
            source=ValueHelpSource(type="bo", target_bo=relation, apply_target_permissions=True),
            behavior=ValueHelpBehavior(binding_strength="strict", validation=True),
            presentation=ValueHelpPresentation(result_type="dialog"),
        )

    enum_type_id = (data.get('ui', {}) or {}).get('enum_type', '')
    options_source = (data.get('ui', {}) or {}).get('options_source', '')
    if enum_type_id and options_source == 'enum':
        return ValueHelpConfig(
            source=ValueHelpSource(type="enum", enum_type_id=enum_type_id, sort_by="sort_order"),
            behavior=ValueHelpBehavior(binding_strength="strict", validation=True),
            presentation=ValueHelpPresentation(result_type="dropdown"),
        )
    if enum_type_id and widget in ('select', 'select_with_search'):
        return ValueHelpConfig(
            source=ValueHelpSource(type="enum", enum_type_id=enum_type_id, sort_by="sort_order"),
            behavior=ValueHelpBehavior(binding_strength="strict", validation=True),
            presentation=ValueHelpPresentation(result_type="dropdown"),
        )

    return None


if __name__ == "__main__":
    schema_dir = get_yaml_schema_dir()
    print("=== YAML 元模型加载 ===")
    print("Schema 目录: {0}".format(schema_dir))
    print()
    
    count = register_from_directory(schema_dir)
    print("\n已注册 {0} 个元模型".format(count))
    
    print("\n=== 元模型列表 ===")
    for obj_id in registry.list_objects():
        obj = registry.get(obj_id)
        print("  - {0}: {1} (层级: {2})".format(
            obj_id, obj.name, obj.semantics.hierarchy_level
        ))

load_meta_object = get_meta_object
load_user_yaml = lambda: get_meta_object('user')
load_role_yaml = lambda: get_meta_object('role')
