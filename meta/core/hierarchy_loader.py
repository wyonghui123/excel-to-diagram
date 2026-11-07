# -*- coding: utf-8 -*-
"""
Hierarchy Loader — 产品版本维度链的单一读取入口 (SSOT 访问器)

【背景 2026-10-06】
`meta/schemas/hierarchies.yaml` 的 `hierarchies[].levels[]` 是产品版本维度链的
权威声明，但「BO 对象名 → 物理表名」这张映射曾以字面量散落在 9 处模块内
（权限预览、值帮助、意图适配、派生管道、维度展开、审计级联 ...）。
这些副本内容逐项相同，却会各自漂移；新增层级时需逐处手工同步。

本模块把该映射收敛为一份，并沿用仓库既有 SSOT 加载范式
（yaml 优先 + 硬编码兜底 + 解析失败告警），与以下实现同构：
  - meta/services/permission_dimension_engine.py::_load_resource_table_map
  - meta/core/dimension_object_mapping_loader.py (LRU + TTL)
注：condition_parser.py 曾有一份同构的私有实现 `_load_hierarchy_chain`，
2026-10-06 已删除并改为复用本模块，故不再单列。

【范围边界】
本模块只提供**产品版本维度链 6 层实体**的表名/外键推导。以下实体**不在**此列，
其表名须回落到各自的 schema 文件或 registry，不得从本模块获取：
  - relationship : levels[] 中为 `kind: association` 且**无 table_name**，
                   物理表见 meta/schemas/relationship.yaml
  - annotation   : 完全不在 hierarchies.yaml 中，见 meta/schemas/annotation.yaml
  - org / user   : 组织与用户实体，见 meta/schemas/org.yaml、user.yaml
                   （权限委托授权 Spec 19 M2 依赖）

【换业务域时的行为】
新增业务域只需在 hierarchies.yaml 增加一组 hierarchy，本模块自动按
「levels[] 最长者」取用；调用方无需改动。
"""
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from meta.core import yaml_compat as yaml

# 硬编码兜底基底 (yaml 不可用时使用)。
# 与 hierarchies.yaml biz_hierarchy level 0~5 实测逐项相等；
# 保留它是为了 yaml 缺失/损坏时权限与派生链路仍能工作（fail-safe 而非 fail-open）。
_FALLBACK_CHAIN: List[Tuple[str, Optional[str], str]] = [
    ('product', None, 'products'),
    ('version', 'product_id', 'versions'),
    ('domain', 'version_id', 'domains'),
    ('sub_domain', 'domain_id', 'sub_domains'),
    ('service_module', 'sub_domain_id', 'service_modules'),
    ('business_object', 'service_module_id', 'business_objects'),
]

_SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
_YAML_PATH = os.path.join(_SCHEMA_DIR, 'hierarchies.yaml')

# 展示列 / 编码列 / 父级展示列的硬编码兜底（yaml 不可用时使用）。
_FALLBACK_DISPLAY = {
    'product': 'name',
    'version': 'name',
    'domain': 'domain_name',
    'sub_domain': 'sub_domain_name',
    'service_module': 'name',
    'business_object': 'name',
}
_FALLBACK_CODE = {obj: 'code' for obj, _fk, _table in _FALLBACK_CHAIN}

# dimension_profiles 的硬编码兜底（yaml 不可用时使用）
_FALLBACK_PROFILES = {'default': 4, 'full': 6}

# 模块级缓存：这些映射在进程生命周期内不变，读一次即可。
_chain_cache: Optional[List[Tuple[str, Optional[str], str]]] = None
_display_cache: Optional[Dict[str, str]] = None
_code_cache: Optional[Dict[str, str]] = None
_parent_info_cache: Optional[Dict[str, Tuple[str, str, str, str]]] = None
_scope_chain_cache: Optional[List[str]] = None
_levels_cache: Optional[List['DimensionLevel']] = None
_child_map_cache: Dict[str, Dict[str, List[str]]] = {}
_extra_entity_cache: Optional[Dict[str, Dict[str, Any]]] = None
_profiles_cache: Optional[Dict[str, int]] = None


@dataclass(frozen=True)
class DimensionLevel:
    """`hierarchies.yaml` 中一层的完整声明（FR-002）。"""

    level: int
    object: str
    level_type: str
    parent_level: Optional[int]
    parent_object: Optional[str]
    scope_anchor: bool
    owner_field: Optional[str]
    table_name: Optional[str]
    foreign_key_field: Optional[str]
    display_field: Optional[str]
    code_field: Optional[str]


def _load_levels() -> List[Dict[str, Any]]:
    """读取 levels[] 全部声明（含 association 层），取最完整的一组。"""
    if not os.path.exists(_YAML_PATH):
        return []

    try:
        with open(_YAML_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[Warning] hierarchy_loader: hierarchies.yaml 解析失败，使用硬编码 fallback: {e}")
        return []

    best: List[Dict[str, Any]] = []
    for h in data.get('hierarchies', []) or []:
        levels = list(h.get('levels') or [])
        if len(levels) > len(best):
            best = levels

    best.sort(key=lambda lv: lv.get('level', 0))
    return best


def _load_entity_levels() -> List[Dict[str, Any]]:
    """读取 levels[] 中**实体**层（排除 kind=association 的关联层）。

    关联层（level 6 relationship）没有 table_name，按 table_name 判空即可
    天然排除；`kind` 判断作为显式保险，避免将来 yaml 给关联层补上 table_name
    时把它误当作实体层纳入表名映射。
    """
    return [
        lv for lv in _load_levels()
        if lv.get('table_name') and lv.get('kind') != 'association'
    ]


def get_hierarchy_chain() -> List[Tuple[str, Optional[str], str]]:
    """返回 [(object, foreign_key_field, table_name), ...]，按 level 升序。

    首次调用时读取 yaml 并缓存；yaml 不可用时返回硬编码兜底。
    """
    global _chain_cache
    if _chain_cache is None:
        levels = _load_entity_levels()
        chain = [
            (lv['object'], lv.get('foreign_key_field'), lv['table_name'])
            for lv in levels
            if lv.get('object') and lv.get('table_name')
        ]
        _chain_cache = chain or list(_FALLBACK_CHAIN)
    return list(_chain_cache)


def get_table_map() -> Dict[str, str]:
    """返回 {object: table_name}，仅含 6 层实体对象。

    注意：不含 relationship / annotation / org / user，理由见模块 docstring。
    调用方若需这些表名，应各自从其 schema 文件获取，不得在此扩张——
    那会让「维度链表名」与「业务实体表名」两类性质不同的东西混为一谈。
    """
    return {obj: table for obj, _fk, table in get_hierarchy_chain()}


def _declared_map(key: str, fallback: Dict[str, str]) -> Dict[str, str]:
    """按 levels[] 的某个声明键取值；缺失层用兜底补齐。"""
    levels = _load_entity_levels()
    mapping = {
        lv['object']: lv[key]
        for lv in levels
        if lv.get('object') and lv.get(key)
    }
    for obj, value in fallback.items():
        mapping.setdefault(obj, value)
    return mapping


def get_display_field_map() -> Dict[str, str]:
    """返回 {object: display_field}（该层自身的名称列）。"""
    global _display_cache
    if _display_cache is None:
        _display_cache = _declared_map('display_field', _FALLBACK_DISPLAY)
    return dict(_display_cache)


def get_code_field_map() -> Dict[str, str]:
    """返回 {object: code_field}（业务编码列）。"""
    global _code_cache
    if _code_cache is None:
        _code_cache = _declared_map('code_field', _FALLBACK_CODE)
    return dict(_code_cache)


def get_parent_info_map() -> Dict[str, Tuple[str, str, str, str]]:
    """返回 {child_object: (parent_object, parent_table, child_fk, parent_display_field)}。

    供值帮助反推祖先路径、层级树拼接 JOIN 使用。level 0（product）无父级，不在结果中。
    """
    global _parent_info_cache
    if _parent_info_cache is not None:
        return dict(_parent_info_cache)

    levels = _load_entity_levels()
    by_object = {lv['object']: lv for lv in levels if lv.get('object')}
    fallback_tables = {
        obj: table for obj, _fk, table in _FALLBACK_CHAIN
    }
    result: Dict[str, Tuple[str, str, str, str]] = {}
    for child, fallback_fk, _table in _FALLBACK_CHAIN:
        if not fallback_fk:
            continue
        child_level = by_object.get(child, {})
        parent = (
            child_level.get('parent_object')
            or fallback_fk[:-3]
        )
        parent_level = by_object.get(parent, {})
        parent_table = (
            parent_level.get('table_name') or fallback_tables[parent]
        )
        parent_display = (
            child_level.get('parent_display_field')
            or parent_level.get('display_field')
            or 'name'
        )
        fk = child_level.get('foreign_key_field') or fallback_fk
        result[child] = (parent, parent_table, fk, parent_display)

    _parent_info_cache = result
    return dict(_parent_info_cache)


def get_scope_chain() -> List[str]:
    """返回授权层级链（scope_anchor=true 的层，按 level 升序）。

    [TBD-4 2026-11-07] 默认仍为 4 层：product → version → domain → sub_domain；
    service_module / business_object 若未声明 scope_anchor 则不纳入授权范围。
    """
    global _scope_chain_cache
    if _scope_chain_cache is not None:
        return list(_scope_chain_cache)

    levels = _load_entity_levels()
    anchored = [
        lv['object'] for lv in levels
        if lv.get('object') and lv.get('scope_anchor')
    ]
    if not anchored:
        anchored = [obj for obj, _fk, _table in _FALLBACK_CHAIN][:4]
    _scope_chain_cache = anchored
    return list(_scope_chain_cache)


def get_dimension_levels() -> List[DimensionLevel]:
    """返回 `hierarchies.yaml` 声明中的全部层级（含 association 层）。

    FR-002：`level_type / parent_level / scope_anchor / owner_field` 均以声明为准；
    yaml 缺失时按 `_FALLBACK_CHAIN` 兜底推导。
    """
    global _levels_cache
    if _levels_cache is not None:
        return list(_levels_cache)

    raw_levels = _load_levels()
    if not raw_levels:
        result = [
            DimensionLevel(
                level=i,
                object=obj,
                level_type='entity',
                parent_level=(i - 1) if i > 0 else None,
                parent_object=_FALLBACK_CHAIN[i - 1][0] if i > 0 else None,
                scope_anchor=i < 4,
                owner_field='owner_id',
                table_name=table,
                foreign_key_field=fk,
                display_field=_FALLBACK_DISPLAY.get(obj),
                code_field=_FALLBACK_CODE.get(obj),
            )
            for i, (obj, fk, table) in enumerate(_FALLBACK_CHAIN)
        ]
        _levels_cache = result
        return list(_levels_cache)

    result: List[DimensionLevel] = []
    previous_entity_level: Optional[int] = None
    for lv in raw_levels:
        level_type = lv.get('level_type') or lv.get('kind') or 'entity'
        if 'parent_level' in lv:
            parent_level = lv.get('parent_level')
        else:
            parent_level = previous_entity_level
        owner_field = lv.get('owner_field')
        if 'owner_field' not in lv:
            owner_field = 'owner_id' if level_type == 'entity' else None
        result.append(DimensionLevel(
            level=int(lv.get('level', len(result))),
            object=lv.get('object') or '',
            level_type=level_type,
            parent_level=parent_level,
            parent_object=lv.get('parent_object'),
            scope_anchor=bool(lv.get('scope_anchor')),
            owner_field=owner_field,
            table_name=lv.get('table_name'),
            foreign_key_field=lv.get('foreign_key_field'),
            display_field=lv.get('display_field'),
            code_field=lv.get('code_field'),
        ))
        if level_type == 'entity':
            previous_entity_level = int(lv.get('level', len(result) - 1))

    _levels_cache = [lv for lv in result if lv.object]
    return list(_levels_cache)


def get_dimension_profiles() -> Dict[str, int]:
    """返回 `dimension_profiles` 声明：{profile: depth}。

    yaml 缺失/损坏时回落到 `_FALLBACK_PROFILES`（fail-safe）。
    """
    global _profiles_cache
    if _profiles_cache is not None:
        return dict(_profiles_cache)

    profiles: Dict[str, int] = {}
    if os.path.exists(_YAML_PATH):
        try:
            with open(_YAML_PATH, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            for name, depth in (data.get('dimension_profiles') or {}).items():
                try:
                    profiles[str(name)] = int(depth)
                except (TypeError, ValueError):
                    continue
        except Exception as e:
            print(f"[Warning] hierarchy_loader: dimension_profiles 解析失败，使用兜底: {e}")

    _profiles_cache = profiles or dict(_FALLBACK_PROFILES)
    return dict(_profiles_cache)


def get_dimension_profile_depth(profile: str = 'default') -> int:
    """返回 profile 对应的默认深度（层数）。

    未声明的 profile 抛 `ValueError`，避免拼写错误被静默当作 default。
    """
    profiles = get_dimension_profiles()
    if profile not in profiles:
        raise ValueError(
            "unknown dimension profile %r; declared: %s"
            % (profile, ', '.join(sorted(profiles))))
    return profiles[profile]


def get_child_type_map(profile: str = 'default', include_extra: bool = False) -> Dict[str, List[str]]:
    """返回 {parent_object: [child_object, ...]}，深度由 profile 决定。

    - `default`（4 层）：product → version → domain → sub_domain；
    - `full`（6 层）：继续下探 service_module / business_object；
    - `include_extra=True` 时追加 `extra_entity_tables` 中 `self_parent: true`
      的对象自环（org），供条件权限服务使用。
    """
    cache_key = '%s|%s' % (profile, bool(include_extra))
    if cache_key in _child_map_cache:
        return {key: list(value) for key, value in _child_map_cache[cache_key].items()}

    depth = get_dimension_profile_depth(profile)
    entity_levels = [lv for lv in get_dimension_levels() if lv.level_type == 'entity'][:depth]
    by_level = {lv.level: lv for lv in entity_levels}

    result: Dict[str, List[str]] = {lv.object: [] for lv in entity_levels}
    for lv in entity_levels:
        if lv.parent_level is None:
            continue
        parent = by_level.get(lv.parent_level)
        if parent is not None:
            result[parent.object].append(lv.object)

    if include_extra:
        for obj, info in get_extra_entity_map().items():
            if info.get('self_parent'):
                result.setdefault(obj, []).append(obj)

    _child_map_cache[cache_key] = result
    return {key: list(value) for key, value in result.items()}


def get_extra_entity_map() -> Dict[str, Dict[str, Any]]:
    """返回 `extra_entity_tables` 声明：{object: {table_name, parent_field, self_parent}}。"""
    global _extra_entity_cache
    if _extra_entity_cache is not None:
        return {key: dict(value) for key, value in _extra_entity_cache.items()}
    if not os.path.exists(_YAML_PATH):
        _extra_entity_cache = {}
        return {}

    try:
        with open(_YAML_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[Warning] hierarchy_loader: extra_entity_tables 解析失败: {e}")
        _extra_entity_cache = {}
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    for item in data.get('extra_entity_tables') or []:
        obj = item.get('object')
        if obj:
            result[obj] = dict(item)
    _extra_entity_cache = result
    return {key: dict(value) for key, value in result.items()}


def get_extra_entity_table_map(*objects: str) -> Dict[str, str]:
    """返回非维度链实体的 {object: table_name}；不传参返回全部。"""
    extra = get_extra_entity_map()
    selected = objects or tuple(extra.keys())
    return {
        obj: extra[obj]['table_name']
        for obj in selected
        if obj in extra and extra[obj].get('table_name')
    }


def get_parent_field_map(include_extra: bool = False) -> Dict[str, str]:
    """返回 {child_object: child_fk_field}；`include_extra` 时追加声明了 parent_field 的实体。"""
    result = {
        obj: info[2] for obj, info in get_parent_info_map().items()
    }
    if include_extra:
        for obj, info in get_extra_entity_map().items():
            if info.get('parent_field'):
                result[obj] = info['parent_field']
    return result


def reload() -> None:
    """清空全部进程内缓存（测试 / 热加载用）。"""
    global _chain_cache, _display_cache, _code_cache
    global _parent_info_cache, _scope_chain_cache
    global _levels_cache, _extra_entity_cache, _profiles_cache
    _chain_cache = None
    _display_cache = None
    _code_cache = None
    _parent_info_cache = None
    _scope_chain_cache = None
    _levels_cache = None
    _extra_entity_cache = None
    _profiles_cache = None
    _child_map_cache.clear()


def get_fk_chain() -> List[Tuple[str, str, str]]:
    """返回 [(parent_object, child_table, child_fk_field), ...]，按 level 升序。

    与 get_hierarchy_chain() 的方向相反：本表以**父**为键描述「向下取子表」的边，
    供维度展开 / 权限子树过滤拼接 JOIN 使用。level 0 无子表，故首项不出现在结果中。
    """
    chain = get_hierarchy_chain()
    return [
        (chain[i][0], chain[i + 1][2], chain[i + 1][1])
        for i in range(len(chain) - 1)
        if chain[i + 1][1]  # 子层须有指向父的外键
    ]


def get_descendant_paths() -> Dict[str, List[Tuple[str, str]]]:
    """返回 {object_type: [(中间表, 该步用于 JOIN 的外键), ...]}，供自底向上拼 JOIN。

    与 get_fk_chain() 方向又相反：`_descendant_subquery` 从 business_objects 出发
    逐层向上 JOIN，故每一步的顺序是**从最深层往目标层**（逆序）。

    推导规则：对位于 level i 的目标对象 T，中间层为 level i+1 .. 链尾-1，
    按**从深到浅**（逆序）产出 `(中间层表名, 更深一层指向该中间层的外键)`。
    外键取自更深一层的 `foreign_key_field` —— 因为 JOIN 语义是
    `JOIN <中间层> ON <更深一层别名>.<该 fk> = <中间层>.id`。

    「更深一层指向目标层」的那最后一个 fk（即 T 自己指向其父的 fk）是 WHERE 条件，
    不属于中间 JOIN 链，由调用方单独处理，故本函数不含它。
    `service_module` 的中间层为空，返回空列表——这是合法终止态，
    调用方以「未注册」与「空链」区分二者（见 _descendant_subquery）。
    """
    chain = get_hierarchy_chain()
    paths: Dict[str, List[Tuple[str, str]]] = {}
    for i, (obj, _fk, _table) in enumerate(chain):
        steps: List[Tuple[str, str]] = []
        # j 是「中间层」下标；它更深一层的 fk 即 chain[j+1].foreign_key_field
        for j in range(len(chain) - 2, i, -1):
            deeper_fk = chain[j + 1][1]
            if deeper_fk:
                steps.append((chain[j][2], deeper_fk))
        paths[obj] = steps
    return paths
