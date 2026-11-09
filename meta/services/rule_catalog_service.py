# -*- coding: utf-8 -*-
"""规则中心目录服务（FR-014 / P1 只读）。

职责：把 6 类异构规则来源归一成同一 ``RuleDescriptor``，供规则中心列表与详情消费。
本模块只读：不做任何规则解析、写入或发布（试算见 IF-008，发布见 FR-018）。

来源与接入状态：
    bo_yaml / validation   YAML ``MetaRule``（经 RuleProvider 读取）
    control_parameter      control_parameter_defs + values
    line_type              line_type_assignments
    doc_flow               doc_flow_rule（DB 载体）
    approval               BO ``approval`` 声明
    state_machine/numbering 暂无统一读取入口 → 返回 not_instrumented，不伪造数据
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from meta.core.rule_keys import (
    NOT_INSTRUMENTED_SOURCES,
    RULE_SOURCES,
    RULE_TYPES,
    approval_key,
    bo_yaml_key,
    control_parameter_key,
    doc_flow_key,
    line_type_key,
    sourcing_key,
)
from meta.core.rule_trace_service import TRACE_SCENARIOS
from meta.core.rule_scenarios import SCENARIO_FACTOR_KEYS
from meta.core.rule_targets import links_for

logger = logging.getLogger(__name__)

# 来源枚举唯一事实源在 meta/core/rule_keys.py（spec §13.2）
SOURCES = RULE_SOURCES

# 暂无统一只读入口的来源：目录如实标记，不编造空结果冒充「已覆盖」。
NOT_INSTRUMENTED = NOT_INSTRUMENTED_SOURCES

# 视图元数据中允许引用的动作 / widget 类型（封闭枚举，YAML 不能引入新类型）
ACTIONS = ('detail', 'edit', 'view_source', 'simulate', 'copy_key', 'publish', 'rollback', 'rerun')
WIDGETS = ('code', 'factor_matrix', 'source_snippet', 'audit_log')
TAB_KINDS = ('table', 'simulate', 'health', 'rule_trace')
FILTER_KEYS = (
    'keyword', 'domain', 'rule_type', 'source', 'configurable', 'status',
    'document_type', 'line_type', 'item_group', 'source_bo', 'target_bo',
    'scope_bo', 'severity', 'enabled',
)

# 静态封闭值域（owner=本模块）；动态筛选项（source/rule_type/domain）由服务端派生，
# YAML 只允许写静态项，写动态项视为手写第二份业务枚举（spec §13.4）。
STATIC_FILTER_OPTIONS = {
    'status': ('active', 'inactive', 'draft'),
    'severity': ('error', 'warning', 'info'),
    'enabled': ('true', 'false'),
    'configurable': ('true', 'false'),
}
DERIVED_FILTER_OPTIONS = ('source', 'rule_type', 'domain')

SUPPORTED_VIEW_VERSION = 2

_SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
VIEW_CONFIG_PATH = os.path.join(_SCHEMA_DIR, 'rule_center_view.yaml')

_VALIDATION_TYPES = ('validation', 'default', 'constraint')


class RuleCatalogError(ValueError):
    """视图元数据非法或来源读取失败。"""


class RuleFilterError(RuleCatalogError):
    """请求期筛选值不在声明值域内（API 层转 400）。"""


def _enum(value: Any) -> Any:
    return getattr(value, 'value', value)


def _meta_db():
    from meta.core.db_path import get_meta_db_path
    from meta.core.datasource import get_data_source
    return get_data_source('sqlite', database=get_meta_db_path())


def _query(data_source, sql: str) -> List[Dict[str, Any]]:
    try:
        return list(data_source.query(sql) or [])
    except Exception as exc:  # noqa: BLE001 - 单来源失败不影响其它来源
        logger.warning('[rule_catalog] 查询失败 %s: %s', sql, exc)
        raise RuleCatalogError(str(exc)) from exc


def _descriptor(
    source: str,
    rule_key: str,
    name: str,
    rule_type: str = '',
    scope_bo: str = '',
    factors: Optional[Dict[str, Any]] = None,
    configurable: bool = False,
    publishable: bool = False,
    status: str = 'active',
    updated_at: str = '',
    priority: Optional[int] = None,
    source_tags: Optional[Iterable[str]] = None,
    detail: Optional[Dict[str, Any]] = None,
    layer: str = 'L2',
    links: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    item = {
        'rule_key': rule_key,
        'layer': layer,
        'name': name or rule_key,
        'rule_type': rule_type or '',
        'source': source,
        'source_tags': list(source_tags or []),
        'scope_bo': scope_bo or '',
        'factors': factors or {},
        'configurable': bool(configurable),
        'publishable': bool(publishable),
        'status': status or 'active',
        'updated_at': updated_at or '',
        'priority': priority,
        'detail': detail or {},
    }
    if links:
        item['links'] = links
    return item


# ----------------------------------------------------------------------
# 各来源适配器
# ----------------------------------------------------------------------

def _bo_yaml_descriptors(*, include_draft: bool = False) -> List[Dict[str, Any]]:
    from meta.core.models import registry
    from meta.core.rule_provider import get_rule_provider

    provider = get_rule_provider()
    items: List[Dict[str, Any]] = []
    for bo_id, meta_obj in (registry.get_all() or {}).items():
        for index, rule in enumerate(provider.get_rules(meta_obj)):
            rule_id = str(getattr(rule, 'id', '') or f'rule_{index}')
            rule_type = str(_enum(getattr(rule, 'rule_type', '')))
            tags = ['validation'] if rule_type in _VALIDATION_TYPES else []
            items.append(_descriptor(
                'bo_yaml',
                bo_yaml_key(bo_id, rule_id),
                str(getattr(rule, 'name', '') or rule_id),
                rule_type=rule_type,
                scope_bo=bo_id,
                configurable=False,
                status='active' if getattr(rule, 'enabled', True) else 'inactive',
                priority=getattr(rule, 'priority', None),
                source_tags=tags,
                layer='L1',
                detail={
                    'condition': str(getattr(rule, 'condition', '') or ''),
                    'action': str(getattr(rule, 'action', '') or ''),
                    'message': str(getattr(rule, 'message', '') or ''),
                    'error_code': str(getattr(rule, 'error_code', '') or ''),
                    'target_fields': list(getattr(rule, 'target_fields', []) or []),
                    'triggers': [str(_enum(t)) for t in (getattr(rule, 'triggers', []) or [])],
                    'declared_at': f'meta/schemas/{bo_id}.yaml#rules[{index}]',
                },
            ))
    return items


def _control_parameter_descriptors(*, include_draft: bool = False) -> List[Dict[str, Any]]:
    from meta.services.control_parameter_service import get_control_parameter_resolver

    resolver = get_control_parameter_resolver()
    defs = _query(resolver.ds, "SELECT * FROM control_parameter_defs ORDER BY code")
    values = _query(resolver.ds, "SELECT * FROM control_parameter_values")
    grouped: Dict[Any, List[Dict[str, Any]]] = {}
    for row in values:
        grouped.setdefault(row.get('control_parameter_id'), []).append(row)

    items: List[Dict[str, Any]] = []
    for definition in defs:
        code = str(definition.get('code') or '')
        status = str(definition.get('status') or 'active')
        # 默认只看生效态，与运行时读取口径一致；发布流 / 试算显式开启（spec §9.6.2）
        if not include_draft and status != 'active':
            continue
        rows = grouped.get(definition.get('id'), [])
        items.append(_descriptor(
            'control_parameter',
            control_parameter_key(code),
            str(definition.get('name') or code),
            rule_type='control_parameter',
            factors={
                'domain': definition.get('domain') or '',
                'value_type': definition.get('value_type') or '',
                'default_value': definition.get('default_value'),
                'value_count': len(rows),
            },
            configurable=True,
            publishable=True,
            status=status,
            links=links_for('control_parameter', status),
            detail={
                'condition': str(definition.get('description') or ''),
                'values': rows[:20],
                'values_truncated': len(rows) > 20,
            },
        ))
    return items


def _line_type_descriptors(*, include_draft: bool = False) -> List[Dict[str, Any]]:
    from meta.services.line_type_service import get_line_type_resolver

    resolver = get_line_type_resolver()
    rows = _query(
        resolver.ds,
        "SELECT * FROM line_type_assignments "
        "ORDER BY document_type_id, specificity_rank DESC, id",
    )
    items: List[Dict[str, Any]] = []
    for row in rows:
        status = str(row.get('status') or 'active')
        if not include_draft and status != 'active':
            continue
        doc_type_id = row.get('document_type_id')
        item_group_id = row.get('item_group_id')
        key = line_type_key(doc_type_id, item_group_id)
        items.append(_descriptor(
            'line_type',
            key,
            f'单据类型 {doc_type_id} / 物料组 {item_group_id if item_group_id is not None else "默认"}',
            rule_type='line_type_assignment',
            factors={
                'document_type_id': doc_type_id,
                'item_group_id': item_group_id,
                'line_type_id': row.get('line_type_id'),
                'specificity_rank': row.get('specificity_rank'),
            },
            configurable=True,
            publishable=True,
            status=status,
            links=links_for('line_type', status),
            detail={'condition': str(row.get('description') or '')},
        ))
    return items


def _doc_flow_descriptors(*, include_draft: bool = False) -> List[Dict[str, Any]]:
    from meta.core.doc_flow_header_contract import build_header_contract
    from meta.core.doc_flow_node_groups import build_node_groups, node_group_detail
    from meta.core.rule_provider import list_doc_flow_rules

    rules = list_doc_flow_rules(_meta_db())
    # FR-013：节点组是 YAML 元数据 + doc_flow_rule 的只读投影，不落库。
    groups = build_node_groups(rules)

    items: List[Dict[str, Any]] = []
    for rule in rules:
        rule_id = str(rule.get('rule_id') or '')
        detail = {
            'field_map': rule.get('field_map') or {},
            'split_key': rule.get('split_key') or [],
            'pool': rule.get('pool'),
            'source_qty_field': rule.get('source_qty_field'),
            'target_line_bo': rule.get('target_line_bo') or '',
            'head_fk_field': rule.get('head_fk_field') or '',
            'display_fields': rule.get('display_fields') or [],
        }
        node_group = node_group_detail(
            groups, str(rule.get('source_bo') or ''))
        if node_group:
            detail['node_group'] = node_group
        # TBD-007 P0：计划行角色与头字段契约均为只读增量字段（零 DDL）。
        detail['source_role'] = (node_group or {}).get('node_role', '')
        detail['header_contract'] = build_header_contract(rule)

        items.append(_descriptor(
            'doc_flow',
            doc_flow_key(rule_id),
            f"{rule.get('source_bo')} → {rule.get('target_bo')}",
            rule_type='doc_flow',
            factors={
                'source_bo': rule.get('source_bo'),
                'target_bo': rule.get('target_bo'),
                'pool': rule.get('pool'),
            },
            # L1 声明：单据流结构由 YAML/代码定义，规则中心只读
            configurable=False,
            status=str(rule.get('status') or 'active'),
            updated_at=str(rule.get('updated_at') or ''),
            detail=detail,
        ))
    return items


def _approval_descriptors(*, include_draft: bool = False) -> List[Dict[str, Any]]:
    from meta.core.models import registry

    items: List[Dict[str, Any]] = []
    for bo_id, meta_obj in (registry.get_all() or {}).items():
        approval = getattr(meta_obj, 'approval', None)
        if not approval:
            continue
        items.append(_descriptor(
            'approval',
            approval_key(bo_id),
            f'{getattr(meta_obj, "name", bo_id)} 审批策略',
            rule_type='approval',
            scope_bo=bo_id,
            configurable=False,
            layer='L1',
            detail={'declaration': approval},
        ))
    return items


def _scope_summary(assignments: List[Dict[str, Any]]) -> str:
    """作用域摘要：按分配行拼一段可读文本（目录列展示用，不参与求值）。"""
    if not assignments:
        return '未声明作用域'
    parts: List[str] = []
    for row in assignments[:3]:
        segment = str(row.get('scope_type') or '')
        ref_id = row.get('scope_ref_id')
        if ref_id is not None:
            segment = f'{segment}:{ref_id}'
        dest_org_id = row.get('dest_org_id')
        if dest_org_id is not None:
            segment = f'{segment}@{dest_org_id}'
        dest_location_id = row.get('dest_location_id')
        if dest_location_id is not None:
            segment = f'{segment}/库位{dest_location_id}'
        parts.append(segment)
    if len(assignments) > 3:
        parts.append(f'等{len(assignments)}项')
    return '；'.join(parts)


def _sourcing_descriptors(*, include_draft: bool = False) -> List[Dict[str, Any]]:
    """供应来源规则目录（只读）：BO 生命周期，不进入统一发布流。"""
    data_source = _meta_db()
    rules = _query(data_source, "SELECT * FROM sourcing_rules ORDER BY code")
    try:
        assignments = _query(
            data_source,
            "SELECT * FROM sourcing_rule_assignments "
            "ORDER BY rule_id, specificity_rank DESC, seq, id",
        )
    except RuleCatalogError as exc:  # 子表缺失不阻断规则头可见性
        logger.warning('[rule_catalog] sourcing 作用域读取失败: %s', exc)
        assignments = []

    grouped: Dict[Any, List[Dict[str, Any]]] = {}
    for row in assignments:
        grouped.setdefault(row.get('rule_id'), []).append(row)

    items: List[Dict[str, Any]] = []
    for rule in rules:
        code = str(rule.get('code') or '')
        status = str(rule.get('status') or 'draft')
        # 默认只看生效态，与运行时读取口径一致；草稿由详情/发布流显式开启
        if not include_draft and status != 'active':
            continue
        scopes = grouped.get(rule.get('id'), [])
        items.append(_descriptor(
            'sourcing',
            sourcing_key(code),
            str(rule.get('name') or code),
            rule_type='sourcing',
            factors={
                'rule_usage': rule.get('rule_usage') or '',
                'effectivity_start': rule.get('effectivity_start'),
                'effectivity_end': rule.get('effectivity_end'),
                'scope_count': len(scopes),
                'scope_summary': _scope_summary(scopes),
            },
            configurable=False,
            publishable=False,
            status=status,
            updated_at=str(rule.get('updated_at') or ''),
            links={'edit': {'target': 'sourcing_rule'}},
            detail={
                'condition': str(rule.get('description') or ''),
                'scope': scopes[:20],
                'scope_truncated': len(scopes) > 20,
            },
        ))
    return items


_ADAPTERS = {
    'bo_yaml': _bo_yaml_descriptors,
    'control_parameter': _control_parameter_descriptors,
    'line_type': _line_type_descriptors,
    'doc_flow': _doc_flow_descriptors,
    'approval': _approval_descriptors,
    'sourcing': _sourcing_descriptors,
}


# ----------------------------------------------------------------------
# 对外入口
# ----------------------------------------------------------------------

class RuleCatalogService:
    """规则目录聚合服务（只读）。"""

    #: 属性变量清单的上一版静态快照（派生失败时回退，IF-004）
    _attribute_variables_snapshot: Optional[Dict[str, Any]] = None

    def __init__(self, view_path: str = VIEW_CONFIG_PATH):
        self._view_path = view_path
        self._view_config: Optional[Dict[str, Any]] = None

    # -- 视图元数据 ----------------------------------------------------

    def get_view_config(self, data_source: Any = None) -> Dict[str, Any]:
        if self._view_config is not None:
            return self._view_config
        try:
            with open(self._view_path, 'r', encoding='utf-8') as handle:
                raw = handle.read()
            config = yaml.safe_load(raw) or {}
        except FileNotFoundError:
            raise RuleCatalogError(f'规则中心视图元数据不存在: {self._view_path}')
        except Exception as exc:  # noqa: BLE001
            raise RuleCatalogError(f'规则中心视图元数据解析失败: {exc}') from exc

        self._validate_view_config(config)
        # 声明源是场景注册表：校验通过后按注册表重排/派生，响应不再依赖 YAML 顺序
        declared_sources = {
            str(entry['id'] if isinstance(entry, dict) else entry): entry
            for entry in (config.get('sources') or [])
        }
        config['sources'] = [
            declared_sources.get(source_id, {'id': source_id, 'label': source_id})
            for source_id in SOURCES
        ]
        trace = config.setdefault('trace', {})
        trace['scenarios'] = list(TRACE_SCENARIOS)
        # IF-004：按场景下发因子轴（含 sourcing 四轴），旧 factor_keys 保持兼容
        trace['scenario_factor_keys'] = {
            scenario: list(keys)
            for scenario, keys in SCENARIO_FACTOR_KEYS.items()
        }
        config['filter_options'] = self._derive_filter_options(config)
        variables = self._derive_attribute_variables(data_source)
        if variables is not None:
            RuleCatalogService._attribute_variables_snapshot = variables
            config['attribute_variables'] = variables
        elif RuleCatalogService._attribute_variables_snapshot is not None:
            config['attribute_variables'] = (
                RuleCatalogService._attribute_variables_snapshot)
        else:
            config['attribute_variables'] = {}
        # 响应自带版本与内容指纹，消费端可据此感知元数据变更（spec §13 F-13-10）
        config['hash'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        self._view_config = config
        return config

    @staticmethod
    def _derive_attribute_variables(
            data_source: Any = None) -> Optional[Dict[str, Any]]:
        """按对象派生可配置属性变量；失败返回 None（保留上一版快照）。"""
        if data_source is None:
            try:
                data_source = _meta_db()
            except Exception as exc:  # noqa: BLE001
                logger.warning('view-config 属性变量派生失败（无数据源）: %s', exc)
                return None
        try:
            rows = data_source.query(
                "SELECT DISTINCT scope_ref FROM attribute_scopes "
                "WHERE scope_type = 'object' AND status = 'active'") or []
            from meta.core.attribute_provider import AttributeProvider
            provider = AttributeProvider(data_source)
            result: Dict[str, Any] = {}
            for row in rows:
                bo_id = str(row.get('scope_ref') or '')
                if not bo_id:
                    continue
                result[bo_id] = provider.available_variables(bo_id)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning('view-config 属性变量派生失败，保留上一版快照: %s', exc)
            return None

    @staticmethod
    def _derive_filter_options(config: Dict[str, Any]) -> Dict[str, Any]:
        """动态筛选项由代码声明派生，YAML 只保留静态封闭值域（spec §13.4）。"""
        options = dict(config.get('filter_options') or {})
        options['source'] = list(SOURCES)
        options['rule_type'] = list(RULE_TYPES)
        return options

    @staticmethod
    def _validate_view_config(config: Dict[str, Any]) -> None:
        from meta.core.rule_keys import DIMENSION_FIELDS
        from meta.core.rule_trace_service import (
            DECISION_KINDS,
            SCOPE_DOWNSTREAM,
            SCOPE_EVALUATED,
            SCOPE_NOT_TRIGGERED,
            SOURCE_TYPES,
            TRACE_STAGES,
        )
        from meta.services.rule_simulate_service import CONFIG_MODES, MAX_CODES

        version = config.get('version')
        if version != SUPPORTED_VIEW_VERSION:
            raise RuleCatalogError(
                f'rule_center_view version 不受支持: {version!r}'
                f'（期望 {SUPPORTED_VIEW_VERSION}）')

        declared_sources: List[str] = []
        for entry in config.get('sources') or []:
            source_id = entry if isinstance(entry, str) else (entry or {}).get('id')
            if not source_id:
                raise RuleCatalogError('rule_center_view.sources 存在无 id 的条目')
            if source_id in declared_sources:
                raise RuleCatalogError(f'rule_center_view.sources 重复声明: {source_id}')
            declared_sources.append(str(source_id))
        missing = sorted(set(SOURCES) - set(declared_sources))
        extra = sorted(set(declared_sources) - set(SOURCES))
        if missing or extra or len(declared_sources) != len(SOURCES):
            raise RuleCatalogError(
                'rule_center_view.sources 与 RuleCatalogService.SOURCES 必须双向等值：'
                f'缺少 {missing}，多余 {extra}')

        options = config.get('filter_options') or {}
        for key, values in options.items():
            if key in DERIVED_FILTER_OPTIONS:
                raise RuleCatalogError(
                    f'filter_options.{key} 属服务端派生项，YAML 不得内联: {values}')
            if key not in STATIC_FILTER_OPTIONS:
                raise RuleCatalogError(f'filter_options 含未知筛选项: {key}')
            given = tuple(str(value) for value in (values or []))
            expected = STATIC_FILTER_OPTIONS[key]
            if given != expected:
                raise RuleCatalogError(
                    f'filter_options.{key} 值域不闭合：{list(given)} != {list(expected)}')

        column_labels = set(config.get('column_labels') or {})
        filter_labels = set(config.get('filter_labels') or {})
        if not column_labels:
            raise RuleCatalogError('rule_center_view 缺少 column_labels')
        if not filter_labels:
            raise RuleCatalogError('rule_center_view 缺少 filter_labels')

        tabs = config.get('tabs') or []
        if not tabs:
            raise RuleCatalogError('rule_center_view 缺少 tabs')

        seen_tabs = set()
        for tab in tabs:
            tab_id = tab.get('id')
            if not tab_id:
                raise RuleCatalogError('rule_center_view 存在无 id 的页签')
            if tab_id in seen_tabs:
                raise RuleCatalogError(f'rule_center_view 页签 id 重复: {tab_id}')
            seen_tabs.add(tab_id)

            kind = tab.get('kind') or 'table'
            if kind not in TAB_KINDS:
                raise RuleCatalogError(f'页签 {tab_id} 引用未知 kind: {kind}')
            for source in tab.get('sources') or []:
                if source not in SOURCES:
                    raise RuleCatalogError(f'页签 {tab_id} 引用了未知来源: {source}')
                if kind == 'table' and source in NOT_INSTRUMENTED:
                    raise RuleCatalogError(
                        f'页签 {tab_id} 要求数据，但来源 {source} 尚未接入'
                        '（not_instrumented 不得出现在表格页签）')
            for column in tab.get('columns') or []:
                if column not in column_labels:
                    raise RuleCatalogError(f'页签 {tab_id} 引用了未知列: {column}')
            for filter_key in tab.get('filters') or []:
                if filter_key not in FILTER_KEYS:
                    raise RuleCatalogError(f'页签 {tab_id} 引用了未实现筛选: {filter_key}')
                if filter_key not in filter_labels:
                    raise RuleCatalogError(f'页签 {tab_id} 的筛选 {filter_key} 缺少显示名')
            for action in tab.get('actions') or []:
                if action not in ACTIONS:
                    raise RuleCatalogError(f'页签 {tab_id} 引用了未知动作: {action}')

        for section in (config.get('detail') or {}).get('sections') or []:
            widget = section.get('widget')
            if widget and widget not in WIDGETS:
                raise RuleCatalogError(f'详情分区 {section.get("id")} 引用了未知 widget: {widget}')

        trace = config.get('trace') or {}
        scenarios = [str(item) for item in (trace.get('scenarios') or [])]
        if len(scenarios) != len(TRACE_SCENARIOS) or set(scenarios) != set(TRACE_SCENARIOS):
            raise RuleCatalogError(
                f'trace.scenarios 与 TRACE_SCENARIOS 不等值：{scenarios} != {list(TRACE_SCENARIOS)}')
        scenario_labels = set(trace.get('scenario_labels') or {})
        if scenario_labels != set(scenarios):
            raise RuleCatalogError('trace.scenario_labels 键集合必须与 trace.scenarios 等值')
        scenario_rules = set(trace.get('scenario_rules') or {})
        unknown_rules = sorted(scenario_rules - set(scenarios))
        if unknown_rules:
            raise RuleCatalogError(f'trace.scenario_rules 含未知场景: {unknown_rules}')
        stages = set(trace.get('stages') or {})
        if stages != set(TRACE_STAGES):
            raise RuleCatalogError('trace.stages 与 TRACE_STAGES 值域不等值')
        decisions = set(trace.get('decisions') or {})
        missing_decisions = sorted(set(DECISION_KINDS) - decisions)
        if missing_decisions:
            raise RuleCatalogError(f'trace.decisions 缺少决策文案: {missing_decisions}')
        kinds = set(trace.get('kinds') or {})
        missing_kinds = sorted(set(DECISION_KINDS.values()) - kinds)
        if missing_kinds:
            raise RuleCatalogError(f'trace.kinds 缺少归一类别: {missing_kinds}')
        factor_keys = [str(key) for key in (trace.get('factor_keys') or [])]
        if len(factor_keys) != len(DIMENSION_FIELDS) or set(factor_keys) != set(DIMENSION_FIELDS):
            raise RuleCatalogError(
                f'trace.factor_keys 与后端因子轴不等值：{factor_keys} != {list(DIMENSION_FIELDS)}')
        factor_labels = set(trace.get('factor_labels') or {})
        if factor_labels != set(factor_keys):
            raise RuleCatalogError('trace.factor_labels 键集合必须与 trace.factor_keys 等值')
        # 推导表单必须覆盖全部因子轴，否则用户无法覆盖某些因子（spec §13 F-13-12）
        tab_fields = [str(field) for field in (trace.get('tab') or {}).get('fields') or []]
        unknown_tab_fields = sorted(set(tab_fields) - column_labels)
        if unknown_tab_fields:
            raise RuleCatalogError(
                f'trace.tab.fields 含未声明显示名的字段: {unknown_tab_fields}')
        missing_tab_factors = sorted(set(factor_keys) - set(tab_fields))
        if missing_tab_factors:
            raise RuleCatalogError(
                f'trace.tab.fields 缺少因子轴字段: {missing_tab_factors}')
        scopes = set(trace.get('scopes') or {})
        if scopes != {SCOPE_EVALUATED, SCOPE_NOT_TRIGGERED, SCOPE_DOWNSTREAM}:
            raise RuleCatalogError('trace.scopes 与后端 scope_of 取值不等值')
        source_types = set(trace.get('source_types') or {})
        if source_types != set(SOURCE_TYPES):
            raise RuleCatalogError('trace.source_types 与后端命中链 source.type 不等值')

        simulate = config.get('simulate') or {}
        modes = [str(mode) for mode in (simulate.get('config_modes') or [])]
        if len(modes) != len(CONFIG_MODES) or set(modes) != set(CONFIG_MODES):
            raise RuleCatalogError(
                f'simulate.config_modes 与 CONFIG_MODES 不等值：{modes} != {list(CONFIG_MODES)}')
        if simulate.get('max_codes') != MAX_CODES:
            raise RuleCatalogError(
                f'simulate.max_codes 与 MAX_CODES 不等值：{simulate.get("max_codes")} != {MAX_CODES}')
        # 试算表单同样必须覆盖全部因子轴，口径与 trace 一致（spec §13 F-13-12）
        simulate_fields = [str(field) for field in (simulate.get('fields') or [])]
        unknown_simulate_fields = sorted(set(simulate_fields) - column_labels)
        if unknown_simulate_fields:
            raise RuleCatalogError(
                f'simulate.fields 含未声明显示名的字段: {unknown_simulate_fields}')
        missing_simulate_factors = sorted(set(factor_keys) - set(simulate_fields))
        if missing_simulate_factors:
            raise RuleCatalogError(
                f'simulate.fields 缺少因子轴字段: {missing_simulate_factors}')

    # -- 目录 ----------------------------------------------------------

    def _collect(self, include_draft: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        items: List[Dict[str, Any]] = []
        status: Dict[str, str] = {}

        # YAML 规则只跑一次，同时服务 bo_yaml 与 validation 两个逻辑来源
        bo_items: List[Dict[str, Any]] = []
        for source, adapter in _ADAPTERS.items():
            if source in ('bo_yaml', 'validation'):
                continue
            try:
                source_items = adapter(include_draft=include_draft)
            except Exception as exc:  # noqa: BLE001
                logger.warning('[rule_catalog] 来源 %s 读取失败: %s', source, exc)
                status[source] = f'error: {exc}'
                continue
            status[source] = 'ok'
            items.extend(source_items)

        try:
            bo_items = _bo_yaml_descriptors(include_draft=include_draft)
            status['bo_yaml'] = 'ok'
            status['validation'] = 'ok'
        except Exception as exc:  # noqa: BLE001
            logger.warning('[rule_catalog] 来源 bo_yaml 读取失败: %s', exc)
            status['bo_yaml'] = f'error: {exc}'
            status['validation'] = f'error: {exc}'

        for source in NOT_INSTRUMENTED:
            # 已实现只读 adapter 的来源（如 sourcing）以实际读取结果为准；
            # 仅对完全没有入口的来源标记 not_instrumented。
            status.setdefault(source, 'not_instrumented')

        items.extend(bo_items)
        items.sort(key=lambda d: (d['source'], d['rule_key']))
        return items, status

    def list_rules(
        self,
        sources: Optional[List[str]] = None,
        rule_type: Optional[str] = None,
        configurable: Optional[bool] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        domain: Optional[str] = None,
        bo: Optional[str] = None,
        layer: Optional[str] = None,
        include_draft: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        self._validate_filters(sources, rule_type, status, layer)
        items, source_status = self._collect(include_draft=include_draft)

        if sources:
            wanted = set(sources)
            items = [
                item for item in items
                if item['source'] in wanted or wanted.intersection(item['source_tags'])
            ]
        if rule_type:
            items = [item for item in items if item['rule_type'] == rule_type]
        if configurable is not None:
            items = [item for item in items if item['configurable'] is configurable]
        if status:
            items = [item for item in items if item['status'] == status]
        if domain:
            items = [
                item for item in items
                if str(item['factors'].get('domain') or '') == domain
            ]
        if bo:
            items = [item for item in items if item['scope_bo'] == bo]
        if layer:
            items = [item for item in items if item['layer'] == layer]
        if keyword:
            needle = keyword.lower()
            items = [
                item for item in items
                if needle in item['rule_key'].lower()
                or needle in str(item['name']).lower()
                or needle in str(item['scope_bo']).lower()
            ]

        total = len(items)
        limit = max(1, min(int(limit or 50), 500))
        offset = max(0, int(offset or 0))
        page = items[offset:offset + limit]

        return {
            'items': page,
            'total': total,
            'limit': limit,
            'offset': offset,
            'sources': source_status,
            'not_instrumented': list(NOT_INSTRUMENTED),
            'degraded': any(
                str(value).startswith('error') for value in source_status.values()),
        }

    @staticmethod
    def _validate_filters(
        sources: Optional[List[str]],
        rule_type: Optional[str],
        status: Optional[str],
        layer: Optional[str],
    ) -> None:
        """请求期筛选值必须落在声明值域内，非法值报错而不是静默返回空列表。"""
        if sources:
            unknown = sorted(set(sources) - set(SOURCES))
            if unknown:
                raise RuleFilterError(f'未知 sources 取值: {unknown}；可选 {list(SOURCES)}')
        if rule_type and rule_type not in RULE_TYPES:
            raise RuleFilterError(
                f'未知 rule_type 取值: {rule_type!r}；可选 {list(RULE_TYPES)}')
        if status and status not in STATIC_FILTER_OPTIONS['status']:
            raise RuleFilterError(
                f'未知 status 取值: {status!r}；'
                f'可选 {list(STATIC_FILTER_OPTIONS["status"])}')
        if layer and layer not in ('L1', 'L2', 'L3'):
            raise RuleFilterError(f'未知 layer 取值: {layer!r}；可选 L1 / L2 / L3')

    def get_rule(self, rule_key: str) -> Optional[Dict[str, Any]]:
        # 详情/发布流需要能看到草稿行
        items, _ = self._collect(include_draft=True)
        for item in items:
            if item['rule_key'] == rule_key:
                return item
        return None

    def invalidate(self) -> None:
        """失效进程内视图元数据缓存（发布 / 回滚后目录需立即反映新态）。"""
        self._view_config = None


_default_service: Optional[RuleCatalogService] = None


def get_rule_catalog_service() -> RuleCatalogService:
    global _default_service
    if _default_service is None:
        _default_service = RuleCatalogService()
    return _default_service