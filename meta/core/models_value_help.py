from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ValueHelpParameterBinding:
    local_field: str = ""
    target_field: str = ""
    required: bool = False
    constant: str = ""


@dataclass
class ValueHelpOutMapping:
    value_help_field: str = ""
    local_field: str = ""


@dataclass
class CascadeSelectConfig:
    """级联选择配置 — parameter_bindings 的声明式语法糖
    
    在 YAML 层面提供更直观的 cascade_select 配置，
    由 yaml_loader 自动展开为 parameter_bindings。
    """
    parent_field: str = ""
    child_field: str = ""
    cascade_source: str = ""
    cascade_field: str = ""
    required: bool = False


@dataclass
class ValueHelpSource:
    type: str = "enum"
    enum_type_id: str = ""
    filter_by_dimension: Dict[str, Any] = field(default_factory=dict)
    value_filter: Dict[str, Any] = field(default_factory=dict)
    sort_by: str = ""
    i18n_join_fields: List[str] = field(default_factory=list)
    default_value_code: str = ""
    target_bo: str = ""
    value_field: str = "id"
    display_field: str = "name"
    code_field: str = "code"
    hierarchy: Dict[str, Any] = field(default_factory=dict)
    apply_target_permissions: bool = True
    endpoint: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValueHelpBehavior:
    binding_strength: str = "strict"
    validation: bool = True
    search_fields: List[str] = field(default_factory=list)
    min_search_length: int = 0
    debounce_ms: int = 300
    multiple: Optional[bool] = None  # None=未设置（FK字段默认True），False=显式单选，True=显式多选
    parameter_bindings: List[ValueHelpParameterBinding] = field(default_factory=list)
    out_mappings: List[ValueHelpOutMapping] = field(default_factory=list)
    cascade_select: List['CascadeSelectConfig'] = field(default_factory=list)
    enabled_condition: str = ""


@dataclass
class ValueHelpDisplayColumn:
    field: str = ""
    label: str = ""
    width: int = 0
    sortable: bool = True


@dataclass
class ValueHelpPresentation:
    result_type: str = "dropdown"
    display_mode: str = "flat"
    display_columns: List[ValueHelpDisplayColumn] = field(default_factory=list)
    sort_by: List[Dict[str, str]] = field(default_factory=list)
    page_size: int = 50
    display_format: str = ""
    color_mapping: Dict[str, str] = field(default_factory=dict)


@dataclass
class ValueHelpConfig:
    """值帮助配置（借鉴 SAP @Consumption.valueHelpDefinition）
    
    统一 Value Help 配置，替代旧版4字段模型。
    三层架构：Source（数据源）+ Behavior（行为）+ Presentation（展示）
    """
    source: 'ValueHelpSource' = None
    behavior: 'ValueHelpBehavior' = None
    presentation: 'ValueHelpPresentation' = None

    # 旧版兼容字段（deprecated，迁移后移除）
    validation: bool = False
    validation_message: str = ""
    distinct: bool = True
    label: str = ""
    enabled_condition: str = ""

    def is_unified(self) -> bool:
        return self.source is not None

    def get_binding_strength(self) -> str:
        if self.behavior:
            return self.behavior.binding_strength
        return "strict" if self.validation else "loose"

    def get_result_type(self) -> str:
        if self.presentation:
            return self.presentation.result_type
        return "dropdown"
