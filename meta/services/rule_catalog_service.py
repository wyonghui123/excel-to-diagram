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

import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

SOURCES = (
    'bo_yaml', 'doc_flow', 'approval', 'control_parameter',
    'line_type', 'state_machine', 'numbering', 'validation',
)

# 暂无统一只读入口的来源：目录如实标记，不编造空结果冒充「已覆盖」。
NOT_INSTRUMENTED = ('state_machine', 'numbering')

# 视图元数据中允许引用的动作 / widget 类型（封闭枚举，YAML 不能引入新类型）
ACTIONS = ('detail', 'edit', 'view_source', 'simulate', 'copy_key', 'publish', 'rollback')
WIDGETS = ('code', 'factor_matrix', 'source_snippet', 'audit_log')

_SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
VIEW_CONFIG_PATH = os.path.join(_SCHEMA_DIR, 'rule_center_view.yaml')

_VALIDATION_TYPES = ('validation', 'default', 'constraint')


class RuleCatalogError(ValueError):
    """视图元数据非法或来源读取失败。"""


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
    status: str = 'active',
    updated_at: str = '',
    priority: Optional[int] = None,
    source_tags: Optional[Iterable[str]] = None,
    detail: Optional[Dict[str, Any]] = None,
    layer: str = 'L2',
) -> Dict[str, Any]:
    return {
        'rule_key': rule_key,
        'layer': layer,
        'name': name or rule_key,
        'rule_type': rule_type or '',
        'source': source,
        'source_tags': list(source_tags or []),
        'scope_bo': scope_bo or '',
        'factors': factors or {},
        'configurable': bool(configurable),
        'status': status or 'active',
        'updated_at': updated_at or '',
        'priority': priority,
        'detail': detail or {},
    }


# ----------------------------------------------------------------------
# 各来源适配器
# ----------------------------------------------------------------------

def _bo_yaml_descriptors() -> List[Dict[str, Any]]:
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
                f'bo_yaml:{bo_id}.{rule_id}',
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


def _control_parameter_descriptors() -> List[Dict[str, Any]]:
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
        rows = grouped.get(definition.get('id'), [])
        items.append(_descriptor(
            'control_parameter',
            f'control_parameter:{code}',
            str(definition.get('name') or code),
            rule_type='control_parameter',
            factors={
                'domain': definition.get('domain') or '',
                'value_type': definition.get('value_type') or '',
                'default_value': definition.get('default_value'),
                'value_count': len(rows),
            },
            configurable=True,
            status=str(definition.get('status') or 'active'),
            detail={
                'condition': str(definition.get('description') or ''),
                'values': rows[:20],
                'values_truncated': len(rows) > 20,
            },
        ))
    return items


def _line_type_descriptors() -> List[Dict[str, Any]]:
    from meta.services.line_type_service import get_line_type_resolver

    resolver = get_line_type_resolver()
    rows = _query(
        resolver.ds,
        "SELECT * FROM line_type_assignments "
        "ORDER BY document_type_id, specificity_rank DESC, id",
    )
    items: List[Dict[str, Any]] = []
    for row in rows:
        doc_type_id = row.get('document_type_id')
        item_group_id = row.get('item_group_id')
        key = f'line_type:{doc_type_id}.{item_group_id if item_group_id is not None else "*"}'
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
            status=str(row.get('status') or 'active'),
            detail={'condition': str(row.get('description') or '')},
        ))
    return items


def _doc_flow_descriptors() -> List[Dict[str, Any]]:
    from meta.core.doc_flow_rule_store import list_rules

    items: List[Dict[str, Any]] = []
    for rule in list_rules(_meta_db()):
        rule_id = str(rule.get('rule_id') or '')
        items.append(_descriptor(
            'doc_flow',
            f'doc_flow:{rule_id}',
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
            detail={
                'field_map': rule.get('field_map') or {},
                'split_key': rule.get('split_key') or [],
                'pool': rule.get('pool'),
            },
        ))
    return items


def _approval_descriptors() -> List[Dict[str, Any]]:
    from meta.core.models import registry

    items: List[Dict[str, Any]] = []
    for bo_id, meta_obj in (registry.get_all() or {}).items():
        approval = getattr(meta_obj, 'approval', None)
        if not approval:
            continue
        items.append(_descriptor(
            'approval',
            f'approval:{bo_id}',
            f'{getattr(meta_obj, "name", bo_id)} 审批策略',
            rule_type='approval',
            scope_bo=bo_id,
            configurable=False,
            layer='L1',
            detail={'declaration': approval},
        ))
    return items


_ADAPTERS = {
    'bo_yaml': _bo_yaml_descriptors,
    'control_parameter': _control_parameter_descriptors,
    'line_type': _line_type_descriptors,
    'doc_flow': _doc_flow_descriptors,
    'approval': _approval_descriptors,
}


# ----------------------------------------------------------------------
# 对外入口
# ----------------------------------------------------------------------

class RuleCatalogService:
    """规则目录聚合服务（只读）。"""

    def __init__(self, view_path: str = VIEW_CONFIG_PATH):
        self._view_path = view_path
        self._view_config: Optional[Dict[str, Any]] = None

    # -- 视图元数据 ----------------------------------------------------

    def get_view_config(self) -> Dict[str, Any]:
        if self._view_config is not None:
            return self._view_config
        try:
            with open(self._view_path, 'r', encoding='utf-8') as handle:
                config = yaml.safe_load(handle) or {}
        except FileNotFoundError:
            raise RuleCatalogError(f'规则中心视图元数据不存在: {self._view_path}')
        except Exception as exc:  # noqa: BLE001
            raise RuleCatalogError(f'规则中心视图元数据解析失败: {exc}') from exc

        self._validate_view_config(config)
        self._view_config = config
        return config

    @staticmethod
    def _validate_view_config(config: Dict[str, Any]) -> None:
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

            for source in tab.get('sources') or []:
                if source not in SOURCES:
                    raise RuleCatalogError(f'页签 {tab_id} 引用了未知来源: {source}')
            for action in tab.get('actions') or []:
                if action not in ACTIONS:
                    raise RuleCatalogError(f'页签 {tab_id} 引用了未知动作: {action}')

        for section in (config.get('detail') or {}).get('sections') or []:
            widget = section.get('widget')
            if widget and widget not in WIDGETS:
                raise RuleCatalogError(f'详情分区 {section.get("id")} 引用了未知 widget: {widget}')

    # -- 目录 ----------------------------------------------------------

    def _collect(self) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        items: List[Dict[str, Any]] = []
        status: Dict[str, str] = {}

        # YAML 规则只跑一次，同时服务 bo_yaml 与 validation 两个逻辑来源
        bo_items: List[Dict[str, Any]] = []
        for source, adapter in _ADAPTERS.items():
            if source in ('bo_yaml', 'validation'):
                continue
            try:
                source_items = adapter()
            except Exception as exc:  # noqa: BLE001
                logger.warning('[rule_catalog] 来源 %s 读取失败: %s', source, exc)
                status[source] = f'error: {exc}'
                continue
            status[source] = 'ok'
            items.extend(source_items)

        try:
            bo_items = _bo_yaml_descriptors()
            status['bo_yaml'] = 'ok'
            status['validation'] = 'ok'
        except Exception as exc:  # noqa: BLE001
            logger.warning('[rule_catalog] 来源 bo_yaml 读取失败: %s', exc)
            status['bo_yaml'] = f'error: {exc}'
            status['validation'] = f'error: {exc}'

        for source in NOT_INSTRUMENTED:
            status[source] = 'not_instrumented'

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
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        items, source_status = self._collect()

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
        }

    def get_rule(self, rule_key: str) -> Optional[Dict[str, Any]]:
        items, _ = self._collect()
        for item in items:
            if item['rule_key'] == rule_key:
                return item
        return None

    def invalidate(self) -> None:
        self._view_config = None


_default_service: Optional[RuleCatalogService] = None


def get_rule_catalog_service() -> RuleCatalogService:
    global _default_service
    if _default_service is None:
        _default_service = RuleCatalogService()
    return _default_service