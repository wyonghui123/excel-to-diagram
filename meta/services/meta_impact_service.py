# -*- coding: utf-8 -*-
"""元数据影响分析（where-used）。

对标 SAP SE11 where-used / CDS 依赖反查：改字段、枚举、状态之前，先回答
「还有谁在引用它」。当前 platform 只有三类专用 impact（扩展属性 / 权限维度 /
BOM 工程变更），没有通用元数据反查，本服务补这一层。

纯只读：输入 registry 里的 MetaObject，输出结构化引用清单；不写库、不缓存。
只做「声明层引用」，不追踪运行期 SQL 字符串。
"""

import re
from typing import Any, Dict, List, Optional

# 引用类型（输出里的 kind 取值）；新增类型时同步这里，便于前端收敛渲染。
REFERENCE_KINDS = (
    'rule',
    'state_transition',
    'state_field_policy',
    'relation',
    'index',
    'query',
    'view',
    'value_help',
    'cascade_select',
    'deletion_policy',
    'change_event',
    'action',
)


def _value(obj: Any, name: str, default: Any = None) -> Any:
    """同时兼容 dataclass 属性与 dict 键。"""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_list(raw: Any) -> List[Any]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return list(raw)
    return [raw]


def _mentions(text: Any, field_id: str) -> bool:
    """表达式/文案里是否以「独立标识符」形式出现该字段（避免 id 命中 id_xxx）。"""
    if not isinstance(text, str) or not text:
        return False
    pattern = r'(?<![A-Za-z0-9_])' + re.escape(field_id) + r'(?![A-Za-z0-9_])'
    return re.search(pattern, text) is not None


class MetaImpactService:
    """字段级元数据影响分析。"""

    def __init__(self, registry_obj=None):
        self._registry = registry_obj

    @property
    def registry(self):
        if self._registry is not None:
            return self._registry
        # 延迟导入：避免服务层在 import 期与 registry 单例互相牵连。
        from meta.core.models import registry as _registry
        return _registry

    # ── 对外入口 ────────────────────────────────────────────────

    def analyze(self, object_id: str, field_id: Optional[str] = None) -> Dict[str, Any]:
        """返回对象（或指定字段）的引用清单。

        object_id 不存在 → KeyError；field_id 不在对象字段中 → ValueError。
        由 API 层翻译为 404 / 400。
        """
        obj = self.registry.get(object_id)
        if obj is None:
            raise KeyError(object_id)

        field_ids = [f.id for f in _as_list(_value(obj, 'fields'))]
        if field_id:
            if field_id not in field_ids:
                raise ValueError(
                    "field {0!r} 不属于对象 {1!r}".format(field_id, object_id))
            targets = [field_id]
        else:
            targets = field_ids

        impacts: List[Dict[str, Any]] = []
        counts = {kind: 0 for kind in REFERENCE_KINDS}
        for fid in targets:
            refs = self._collect(obj, fid)
            for ref in refs:
                counts[ref['kind']] = counts.get(ref['kind'], 0) + 1
            if field_id or refs:
                impacts.append({'field': fid, 'references': refs})

        return {
            'object': _value(obj, 'id', object_id),
            'field': field_id or '',
            'impacts': impacts,
            'summary': {k: v for k, v in counts.items() if v},
            'total': sum(counts.values()),
        }

    # ── 引用采集 ────────────────────────────────────────────────

    def _collect(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs: List[Dict[str, Any]] = []
        refs.extend(self._rule_refs(obj, field_id))
        refs.extend(self._state_refs(obj, field_id))
        refs.extend(self._relation_refs(obj, field_id))
        refs.extend(self._index_refs(obj, field_id))
        refs.extend(self._query_refs(obj, field_id))
        refs.extend(self._view_refs(obj, field_id))
        refs.extend(self._value_help_refs(obj, field_id))
        refs.extend(self._cascade_refs(obj, field_id))
        refs.extend(self._deletion_refs(obj, field_id))
        refs.extend(self._change_event_refs(obj, field_id))
        refs.extend(self._action_refs(obj, field_id))
        return refs

    @staticmethod
    def _ref(kind: str, ref_id: str, detail: str, name: str = '') -> Dict[str, Any]:
        return {'kind': kind, 'id': ref_id, 'name': name, 'detail': detail}

    def _rule_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs = []
        for rule in _as_list(_value(obj, 'rules')):
            rule_type = _value(rule, 'rule_type')
            type_name = getattr(rule_type, 'value', rule_type)
            # 状态转换单独归类，避免同一规则被重复计数。
            if type_name == 'state_transition':
                continue
            rule_id = _value(rule, 'id', '?')
            rule_name = _value(rule, 'name', '')
            hit = None
            if field_id in _as_list(_value(rule, 'target_fields')):
                hit = 'target_field'
            elif field_id in _as_list(_value(rule, 'depends_on')):
                hit = 'depends_on'
            elif (_value(rule, 'source_type') == 'field'
                  and _value(rule, 'source_value') == field_id):
                hit = 'source_field'
            elif any(_mentions(_value(rule, key, ''), field_id)
                     for key in ('condition', 'action', 'formula')):
                hit = 'expression'
            if hit:
                refs.append(self._ref('rule', rule_id, '{0} ({1})'.format(hit, type_name),
                                      rule_name))
        return refs

    def _state_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs = []
        for rule in _as_list(_value(obj, 'rules')):
            rule_type = _value(rule, 'rule_type')
            if getattr(rule_type, 'value', rule_type) != 'state_transition':
                continue
            rule_id = _value(rule, 'id', '?')
            rule_name = _value(rule, 'name', '')
            if _value(rule, 'state_field') == field_id:
                refs.append(self._ref('state_transition', rule_id, 'state_field', rule_name))
            elif _mentions(_value(rule, 'validation_expression', ''), field_id):
                refs.append(self._ref('state_transition', rule_id, 'validation_expression',
                                      rule_name))

        for state, policy in (_value(obj, 'state_field_policies') or {}).items():
            for kind in ('readonly', 'required', 'hidden'):
                if field_id in _as_list(_value(policy, kind)):
                    refs.append(self._ref('state_field_policy',
                                          '{0}.{1}'.format(state, kind),
                                          'state={0}'.format(state)))
        return refs

    def _relation_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs = []
        object_id = _value(obj, 'id')
        for rel in _as_list(_value(obj, 'relations')):
            rel_id = _value(rel, 'id', '?')
            rel_name = _value(rel, 'name', '')
            if _value(rel, 'source_field') == field_id:
                refs.append(self._ref('relation', rel_id, 'source_field', rel_name))
            # target_field 指向目标对象的列，只有自关联时才属于本对象。
            if _value(rel, 'target_object') == object_id and _value(rel, 'target_field') == field_id:
                refs.append(self._ref('relation', rel_id, 'target_field', rel_name))
        return refs

    def _index_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs = []
        for idx in _as_list(_value(obj, 'indexes')):
            if field_id in _as_list(_value(idx, 'fields')):
                refs.append(self._ref('index', _value(idx, 'name', '?'),
                                      'unique={0}'.format(bool(_value(idx, 'unique')))))
        return refs

    def _query_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs = []
        for query in _as_list(_value(obj, 'queries')):
            qid = _value(query, 'id', '?')
            qname = _value(query, 'name', '')
            hit = None
            if any(_value(f, 'field') == field_id
                   for f in _as_list(_value(query, 'filters'))):
                hit = 'filter'
            elif any(_value(s, 'field') == field_id
                     for s in _as_list(_value(query, 'sorts'))):
                hit = 'sort'
            elif field_id in _as_list(_value(query, 'fields')):
                hit = 'select'
            elif field_id in _as_list(_value(query, 'group_by')):
                hit = 'group_by'
            elif any(_mentions(expr, field_id)
                     for expr in (_value(query, 'aggregates') or {}).values()):
                hit = 'aggregate'
            if hit:
                refs.append(self._ref('query', qid, hit, qname))
        return refs

    def _view_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs = []
        configs = [('ui_view_config', _value(obj, 'ui_view_config'))]
        for name, cfg in (_value(obj, 'ui_view_configs') or {}).items():
            configs.append((name, cfg))

        for view_name, cfg in configs:
            if not cfg:
                continue
            list_cfg = _value(cfg, 'list')
            for column in _as_list(_value(list_cfg, 'columns')):
                if _value(column, 'key') == field_id:
                    refs.append(self._ref('view', view_name, 'list.column'))
            if field_id in _as_list(_value(list_cfg, 'searchFields')):
                refs.append(self._ref('view', view_name, 'list.search'))

            for section in _as_list(_value(_value(cfg, 'form'), 'sections')):
                if field_id in _as_list(_value(section, 'fields')):
                    refs.append(self._ref('view', view_name, 'form.section'))
                for column in _as_list(_value(section, 'columns')):
                    if field_id in _as_list(_value(column, 'fields')):
                        refs.append(self._ref('view', view_name, 'form.row'))

            detail = _value(cfg, 'detail')
            for tab in _as_list(_value(detail, 'tabs')):
                if field_id in _as_list(_value(tab, 'fields')):
                    refs.append(self._ref('view', view_name,
                                          'detail.tab:{0}'.format(_value(tab, 'id', '?'))))
            for facet in _as_list(_value(detail, 'facets')):
                if field_id in _as_list(_value(facet, 'fields')):
                    refs.append(self._ref('view', view_name,
                                          'detail.facet:{0}'.format(_value(facet, 'id', '?'))))

            for flt in _as_list(_value(_value(cfg, 'filter'), 'filters')):
                if _value(flt, 'key') == field_id or _value(flt, 'source') == field_id:
                    refs.append(self._ref('view', view_name, 'filter'))
        return refs

    def _value_help_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        """字段自身的 value_help 若引用本字段（如 display_field 取同一字段）。"""
        refs = []
        for fld in _as_list(_value(obj, 'fields')):
            config = _value(fld, 'value_help')
            if not config:
                continue
            source = _value(config, 'source')
            for key in ('value_field', 'display_field', 'code_field'):
                if _value(source, key) == field_id:
                    refs.append(self._ref(
                        'value_help',
                        '{0}.{1}'.format(_value(fld, 'id', '?'), key),
                        'value_help.source.{0}'.format(key),
                        _value(fld, 'name', '')))
        return refs

    def _cascade_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs = []
        for entry in _as_list(_value(obj, 'cascade_select')):
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get('id') or entry.get('key') or 'cascade_select'
            for key in ('parent_field', 'child_field', 'source_field', 'target_field',
                        'field', 'depends_on'):
                target = entry.get(key)
                if target == field_id or field_id in _as_list(target):
                    refs.append(self._ref('cascade_select', entry_id,
                                          'cascade_select.{0}'.format(key)))
        return refs

    def _deletion_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        policy = _value(obj, 'deletion_policy')
        if not policy:
            return []
        if field_id in _as_list(_value(policy, 'restrict_on')):
            return [self._ref('deletion_policy', 'restrict_on', 'restrict_on')]
        return []

    def _change_event_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        config = _value(_value(obj, 'ui_view_config'), 'change_notification')
        if not config:
            return []
        refs = []
        if field_id in _as_list(_value(config, 'track_fields')):
            refs.append(self._ref('change_event', 'change_notification', 'track_fields'))
        if field_id in _as_list(_value(config, 'payload')):
            refs.append(self._ref('change_event', 'change_notification', 'payload'))
        return refs

    def _action_refs(self, obj: Any, field_id: str) -> List[Dict[str, Any]]:
        refs = []
        for action in _as_list(_value(obj, 'actions')):
            aid = _value(action, 'id', '?')
            aname = _value(action, 'name', '')
            if any(_value(param, 'id') == field_id
                   for param in _as_list(_value(action, 'parameters'))):
                refs.append(self._ref('action', aid, 'parameter', aname))
            elif field_id in ((_value(action, 'input_schema') or {}).get('properties') or {}):
                refs.append(self._ref('action', aid, 'input_schema', aname))
        return refs
