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
    # [F1 显示名解析口径 2026-10-20] 显示名向哪个 BO 取（FK 显示名解析目标）。
    #   与 target_bo 的分工：
    #     - target_bo  = **候选集口径**（下拉里能被选到哪些行）
    #     - display_target_bo = **展示解析口径**（已存量行的显示名去哪取）
    #   两者不同的典型场景：FK 存的是身份锚 id（parties.id），而候选集被收窄到某个视图
    #   （party_internal / party_archive）。此时历史行可能指向视图外的行，
    #   若显示名也按视图查 ⇒ 解析为 null ⇒ 前端只能回退显示技术 id。
    #   声明 display_target_bo（=身份锚）后，两种口径解耦。
    #   留空 = 与 target_bo 同口径（默认，向后兼容）。
    display_target_bo: str = ""
    # [FK 跳转落点口径 2026-10-22] FK 链接点击后落到哪个 BO 的详情页。
    #   与上面两个口径的分工（三口径各管一件事）：
    #     - target_bo         = **候选集口径**（下拉里能被选到哪些行）
    #     - display_target_bo = **展示解析口径**（存量行的显示名去哪取）
    #     - detail_target_bo  = **跳转落点口径**（点击链接打开哪个详情页）
    #   为什么不直接复用 target_bo：target_bo 会被刻意收窄到只读视图
    #   （party_internal / org_legal_entity 等），而那些视图只有一个基本信息分区，
    #   落上去信息严格少于基表（org 的成员/权限集/操作日志/往来关系全都没有）。
    #   留空 = 与 target_bo 同口径（默认，向后兼容；不声明的字段行为不变）。
    detail_target_bo: str = ""
    # 落点 id 的取值列，声明在**解析口径表**（display_target_bo || target_bo 对应表）上。
    #   仅在 detail_target_bo 的 id 空间与 FK 存值不同时需要——典型如 FK 存 parties.id
    #   而落点 org 用 orgs.id，声明 org_id 即"先取 parties.org_id 当落点 id"。
    #   留空 = 直接拿 FK 原值当落点 id（id 空间同源时用）。
    detail_target_id_field: str = ""
    hierarchy: Dict[str, Any] = field(default_factory=dict)
    apply_target_permissions: bool = True
    endpoint: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    # [v2.0 2026-06-16] FK 字段写路径 dim scope 策略
    # enforce: FK 值必须在用户 dim scope 内
    # or_bypass: 同 scope_group 内任一字段在 scope 内即可 (OR-edit 语义)
    # inherit: 从 scope_inherit_from 指定的父字段继承 enforce 约束
    # none: 不做写路径 dim scope 校验 (默认, 向后兼容)
    write_scope_policy: str = 'none'
    scope_group: Optional[str] = None              # or_bypass 字段组名
    scope_inherit_from: Optional[str] = None       # inherit 父字段 id


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
    # [FIX 2026-09-05 父组织树状 SearchHelp] 自引用层级防环:
    # True 时前端 ValueHelpField 编辑态传入当前记录 id, SearchHelpDialog 通用树剪掉 自身+子孙
    exclude_self: bool = False


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
