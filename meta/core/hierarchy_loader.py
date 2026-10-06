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
from typing import Any, Dict, List, Optional, Tuple

import yaml

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

# 模块级缓存：这些映射在进程生命周期内不变，读一次即可。
_chain_cache: Optional[List[Tuple[str, Optional[str], str]]] = None


def _load_entity_levels() -> List[Dict[str, Any]]:
    """读取 levels[] 中**实体**层（排除 kind=association 的关联层）。

    关联层（level 6 relationship）没有 table_name，按 table_name 判空即可
    天然排除；`kind` 判断作为显式保险，避免将来 yaml 给关联层补上 table_name
    时把它误当作实体层纳入表名映射。
    """
    if not os.path.exists(_YAML_PATH):
        return []

    try:
        with open(_YAML_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[Warning] hierarchy_loader: hierarchies.yaml 解析失败，使用硬编码 fallback: {e}")
        return []

    # 多组 hierarchy 时取 levels[] 最完整的一组（多组时以最长链为准）
    best: List[Dict[str, Any]] = []
    for h in data.get('hierarchies', []) or []:
        levels = [
            lv for lv in (h.get('levels') or [])
            if lv.get('table_name') and lv.get('kind') != 'association'
        ]
        if len(levels) > len(best):
            best = levels

    best.sort(key=lambda lv: lv.get('level', 0))
    return best


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
