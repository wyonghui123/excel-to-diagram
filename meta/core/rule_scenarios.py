# -*- coding: utf-8 -*-
"""规则场景注册表（spec 2026-11-09 §9.3.1 / FR-001）。

唯一声明源：场景、载体、语义分类、命中策略、因子轴、trace 接入状态与目录能力。
本模块只依赖标准库，禁止 import 平台内其它模块，避免与 ``rule_keys`` 循环引用。

派生（下游只能 import，不得另写清单）：
    SOURCES                   全部载体（含无场景的只读来源）
    NOT_INSTRUMENTED_SOURCES  尚未接入 trace 求值的载体
    SCENARIO_FACTOR_KEYS      场景 → 因子轴
    TRACE_SCENARIO_HANDLERS   场景 → trace 处理器键
    DIMENSION_FIELDS          旧 4 维因子轴的只读投影（仅供旧代码兼容）

闭合校验在 import 时执行：登记错误直接启动失败，不允许运行时静默降级。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Tuple


class ScenarioRegistryError(ValueError):
    """场景注册表不合闭合约束（启动期报错，不得吞掉）。"""


@dataclass(frozen=True)
class ScenarioSpec:
    """单个规则场景的声明。

    ``stage_map`` 用于声明场景内部阶段 → 统一 stage（如 sourcing 的三段解释）；
    ``stage`` 是旧 trace 信封的整场景阶段，仅已接入场景需要。
    """

    scenario: str
    source: str
    semantic_class: str
    semantic_type: str
    legacy_rule_type: str
    hit_policy: str
    factor_keys: Tuple[str, ...]
    instrumented: bool
    configurable: bool
    publishable: bool
    stage: Optional[str] = None
    stage_map: Mapping[str, str] = field(default_factory=dict)
    handler: Optional[str] = None
    #: 是否参与旧 DIMENSION_FIELDS 并集投影（旧 6 场景专用，新场景应为 False）
    global_projection: bool = True


SCENARIOS: Tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        scenario='default', source='bo_yaml',
        semantic_class='action', semantic_type='computation',
        legacy_rule_type='default', hit_policy='first',
        factor_keys=(), instrumented=True,
        configurable=False, publishable=False,
        stage='before_save', handler='core',
    ),
    ScenarioSpec(
        scenario='control_parameter', source='control_parameter',
        semantic_class='decision', semantic_type='determination',
        legacy_rule_type='control_parameter', hit_policy='best',
        factor_keys=('org_id', 'document_type_id', 'line_type_id', 'item_group_id'),
        instrumented=True, configurable=True, publishable=True,
        stage='calc', handler='control_parameter',
    ),
    ScenarioSpec(
        scenario='line_type', source='line_type',
        semantic_class='decision', semantic_type='determination',
        legacy_rule_type='line_type_assignment', hit_policy='best',
        factor_keys=('document_type_id', 'item_group_id'),
        instrumented=True, configurable=True, publishable=True,
        stage='calc', handler='line_type',
    ),
    ScenarioSpec(
        scenario='approval', source='approval',
        semantic_class='decision', semantic_type='approval',
        legacy_rule_type='approval', hit_policy='all',
        factor_keys=(), instrumented=True,
        configurable=False, publishable=False,
        stage='approve', handler='core',
    ),
    ScenarioSpec(
        scenario='state_transition', source='bo_yaml',
        semantic_class='decision', semantic_type='transition',
        legacy_rule_type='state_transition', hit_policy='all',
        factor_keys=(), instrumented=True,
        configurable=False, publishable=False,
        stage='status_transition', handler='core',
    ),
    ScenarioSpec(
        scenario='doc_flow', source='doc_flow',
        semantic_class='constraint', semantic_type='declaration',
        legacy_rule_type='doc_flow', hit_policy='all',
        factor_keys=(), instrumented=True,
        configurable=False, publishable=False,
        stage='validate', handler='doc_flow',
    ),
    ScenarioSpec(
        scenario='sourcing', source='sourcing',
        semantic_class='decision', semantic_type='determination',
        legacy_rule_type='sourcing', hit_policy='first',
        factor_keys=('dest_org_id', 'item_id', 'usage', 'eval_date'),
        instrumented=True, configurable=False, publishable=False,
        stage_map={
            'assignment': 'scope',
            'line_filter': 'filter',
            'line_pick': 'select',
        },
        handler='sourcing', global_projection=False,
    ),
)

# 载体序列化顺序（视图 sources / 筛选项展示用；新增来源追加到末尾）
SOURCE_ORDER: Tuple[str, ...] = (
    'bo_yaml', 'doc_flow', 'approval', 'control_parameter',
    'line_type', 'state_machine', 'numbering', 'validation',
)

# 逻辑来源 → 实际载体（validation 由 bo_yaml 规则以 source_tags 承载）
SOURCE_CARRIERS: Mapping[str, str] = {
    'validation': 'bo_yaml',
}

# 全部载体：显式顺序 + 注册表场景引入的新载体
SOURCES: Tuple[str, ...] = tuple(dict.fromkeys(
    list(SOURCE_ORDER) + [spec.source for spec in SCENARIOS]
))


def _covered_sources() -> frozenset:
    """已有统一读取入口的载体：instrumented 场景来源 + 逻辑来源的载体。"""
    return frozenset(
        [spec.source for spec in SCENARIOS if spec.instrumented]
    ) | frozenset(SOURCE_CARRIERS)


NOT_INSTRUMENTED_SOURCES: Tuple[str, ...] = tuple(
    source for source in SOURCES if source not in _covered_sources()
)

SCENARIO_FACTOR_KEYS: Dict[str, Tuple[str, ...]] = {
    spec.scenario: spec.factor_keys for spec in SCENARIOS
}

#: 已接入 trace 的场景（视图 trace.scenarios 同源）
TRACE_SCENARIOS: Tuple[str, ...] = tuple(
    spec.scenario for spec in SCENARIOS if spec.instrumented
)

TRACE_SCENARIO_HANDLERS: Dict[str, str] = {
    spec.scenario: spec.handler
    for spec in SCENARIOS if spec.handler
}

#: trace 节点可出现的全部 stage（整场景 stage + 场景内部 stage_map 值域）
TRACE_STAGES: Tuple[str, ...] = tuple(dict.fromkeys(
    [spec.stage for spec in SCENARIOS if spec.instrumented and spec.stage]
    + [
        stage
        for spec in SCENARIOS if spec.instrumented
        for stage in spec.stage_map.values()
    ]
))

#: 旧 4 维因子轴 = 兼容投影场景的 factor_keys 并集（顺序按首次出现）
DIMENSION_FIELDS: Tuple[str, ...] = tuple(dict.fromkeys(
    key
    for spec in SCENARIOS if spec.global_projection
    for key in spec.factor_keys
))


def get_scenario(scenario: str) -> Optional[ScenarioSpec]:
    for spec in SCENARIOS:
        if spec.scenario == scenario:
            return spec
    return None


def validate_registry() -> None:
    """闭合校验：场景唯一、载体可追溯、已接入场景必须有 stage 与 handler。"""
    names = [spec.scenario for spec in SCENARIOS]
    if len(names) != len(set(names)):
        raise ScenarioRegistryError(f'场景重复登记: {names}')

    declared = set(SOURCES)
    for source in SOURCE_ORDER:
        if source not in declared:
            raise ScenarioRegistryError(f'来源 {source!r} 未登记到 SOURCES')

    covered = _covered_sources()
    for source in SOURCES:
        if source in covered or source in NOT_INSTRUMENTED_SOURCES:
            continue
        raise ScenarioRegistryError(
            f'来源 {source!r} 既无 instrumented 场景，也未登记为未接入来源')

    for source, carrier in SOURCE_CARRIERS.items():
        if source not in declared:
            raise ScenarioRegistryError(f'逻辑来源 {source!r} 未登记到 SOURCES')
        if carrier not in declared:
            raise ScenarioRegistryError(
                f'逻辑来源 {source!r} 的载体 {carrier!r} 未登记到 SOURCES')
        if carrier not in covered:
            raise ScenarioRegistryError(
                f'逻辑来源 {source!r} 的载体 {carrier!r} 未接入 trace')

    for spec in SCENARIOS:
        if spec.instrumented:
            if not (spec.stage or spec.stage_map):
                raise ScenarioRegistryError(
                    f'已接入场景 {spec.scenario!r} 缺少 stage 声明')
            if not spec.handler:
                raise ScenarioRegistryError(
                    f'已接入场景 {spec.scenario!r} 缺少 trace handler')
        elif spec.handler:
            raise ScenarioRegistryError(
                f'未接入场景 {spec.scenario!r} 不得声明 handler')


def validate_attribute_factor_namespace(attribute_codes: Iterable[str]) -> None:
    """FR-010：扩展属性 code 不得与任一场景的因子轴重名。

    属性只能作为条件变量；需要参与因子/审计键时必须先经 attribute_promotion
    提升为物理字段（物理字段名不再属于属性命名空间）。
    """
    codes = {str(code) for code in attribute_codes}
    conflicts = sorted(
        codes & {key for spec in SCENARIOS for key in spec.factor_keys}
    )
    if conflicts:
        raise ScenarioRegistryError(
            '扩展属性不得作为因子轴：{0}；请先经 attribute_promotion 提升为物理字段'
            .format(conflicts))


validate_registry()
