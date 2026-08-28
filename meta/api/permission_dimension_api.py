# -*- coding: utf-8 -*-
"""
管理维度权限配置 API

提供管理维度、维度实例、权限规则配置、影响范围计算等端点
"""

import json
import logging
import os
from functools import wraps
from typing import Any, Dict, List, Optional, Set

import yaml

from flask import Blueprint, g, jsonify, request

from meta.core.datasource import get_data_source
from meta.core.yaml_loader import get_biz_hierarchy
from meta.services.permission_dimension_engine import (
    CHILD_TYPE_MAP,
    CODE_FIELD_MAP,
    DISPLAY_FIELD_MAP,
    PARENT_FIELD_MAP,
    RESOURCE_TABLE_MAP,
    PermissionDimensionEngine,
    ConditionEvaluator,
)
from meta.services.dimension_scope_engine import DimensionScopeEngine

_PARENT_INFO_MAP = {
    'version': ('product', 'products', 'product_id', 'name'),
    'domain': ('version', 'versions', 'version_id', 'name'),
    # [FIX 2026-06-15] parent_display 字段名纠正: 实际 schema 中所有子表都用 'name' 而非 'parent_name'
    # 之前用 domain_name / sub_domain_name / module_name 在 SQL JOIN 时报 "no such column"
    'sub_domain': ('domain', 'domains', 'domain_id', 'name'),
    'service_module': ('sub_domain', 'sub_domains', 'sub_domain_id', 'name'),
    'business_object': ('service_module', 'service_modules', 'service_module_id', 'name'),
}

logger = logging.getLogger(__name__)

permission_dimension_bp = Blueprint(
    "permission_dimension", __name__, url_prefix="/api/v2/bo/permission_dimension"
)

_engine: Optional[PermissionDimensionEngine] = None
_data_source = None


def _get_engine() -> PermissionDimensionEngine:
    global _engine, _data_source
    if _engine is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "architecture.db"
        )
        _data_source = get_data_source("sqlite", database=db_path)
        _engine = PermissionDimensionEngine(_data_source, ttl_seconds=300)
    return _engine


def _is_testing():
    """检查是否为测试模式"""
    import os
    return os.environ.get("FLASK_ENV") == "testing" or os.environ.get("TESTING") == "1"


def _get_user_dim_scope_ids(user_id: int, dimension_id: str) -> Optional[Set[int]]:
    """[FIX 2026-06-15] 收集用户在指定 dimension 上可见的 id 集合

    数据源链路:
        org_members → org_permission_sets → permission_set_dimension_scopes
        → DimensionScopeEngine.expand_dimension_values(permission_set_id) → {dim: set(ids)}

    链式扩展:
        HIERARCHY_CHAIN 只到 sub_domain, 但 service_module/business_object
        仍需按 FK 链 (sub_domain → service_module → business_object) 手动扩展

    返回:
        - None: 该用户**没有任何角色**对任何 dimension 设了 scope → 不过滤 (兼容旧行为)
        - set(): 该用户**有角色配置了 scope**, 但 expand 后为空 → 严格 0 条可见
        - set([...]): 该用户可见的 id 集合 (来自 dim_values / inherit_children / FK 链扩展)

    边界:
        - admin 用户 / '*' 权限: 不调此函数 (调用方判断后跳过)
        - 数据格式异常 (e.g. dim_values=NULL): 用 inherit_children 兜底
        - inherit_children=0 也强制扩展 (因为用户有 BO:edit 等下层 perm)
    """
    global _data_source
    if _data_source is None:
        return None

    try:
        # 1. user → group_ids
        cursor = _data_source.execute(
            "SELECT org_id FROM org_members WHERE user_id = ?",
            [user_id]
        )
        group_ids = [r[0] for r in cursor.fetchall()]
        if not group_ids:
            return None

        # 2. groups → role_ids (DISTINCT)
        placeholders = ",".join("?" for _ in group_ids)
        cursor = _data_source.execute(
            f"SELECT DISTINCT permission_set_id FROM org_permission_sets WHERE org_id IN ({placeholders})",
            group_ids
        )
        role_ids = [r[0] for r in cursor.fetchall()]
        if not role_ids:
            return None

        # 3. 对每个 role 调 expand_dimension_values, union 该 dimension 的 id
        engine = DimensionScopeEngine(_data_source)
        all_ids: Set[int] = set()
        has_any_scope = False
        any_dimension_scope: Dict[str, Set[int]] = {}
        # [V2.2 2026-07-22] Spec 08: 新结构 Dict[str, Dict[str, Set]]
        #   - wildcard-only (无 exclude) → 该 dim 全可见 → 直接返回 None (无限制)
        #   - 其他情况 (include / exclude / wildcard+exclude) → 收集 include 集合
        #     (exclude 由 derive_data_conditions 在 SQL 层处理, 此处仅做粗粒度 list filter)
        from meta.services.dimension_scope_engine import (
            _dim_has_any_values as _has_any,
            _dim_include_values as _include_of,
            _dim_is_wildcard as _is_wc,
            _dim_exclude_values as _exclude_of,
        )

        for permission_set_id in role_ids:
            try:
                expanded = engine.expand_dimension_values(permission_set_id)
            except Exception:
                expanded = {}

            # 收集该 role 全部 dimension 的 scope (用于后续 FK 链扩展)
            for dim, dim_data in expanded.items():
                if not _has_any(dim_data):
                    continue
                has_any_scope = True
                # wildcard-only (无 exclude) → 该 dim 全可见 → 整体返回 None
                if _is_wc(dim_data) and not _exclude_of(dim_data):
                    logger.info(
                        f'[get_user_dimension_scope] role={permission_set_id} dim={dim} wildcard-only '
                        f'→ 全可见, 返回 None'
                    )
                    return None
                # 其他情况: 收集 include 集合 (exclude 留给 SQL 层处理)
                inc = _include_of(dim_data)
                if inc:
                    if dim not in any_dimension_scope:
                        any_dimension_scope[dim] = set()
                    any_dimension_scope[dim].update(inc)

        if not has_any_scope:
            return None

        # 4. 如果目标 dimension 直接有 scope, 直接用
        if dimension_id in any_dimension_scope and any_dimension_scope[dimension_id]:
            return any_dimension_scope[dimension_id]

        # 5. [FIX 2026-06-15] 目标 dimension 不在 scope 链中, 但 user 在更高 dim 有 scope
        #    通过 FK 链手动扩展 (product → version → domain → sub_domain → service_module → business_object)
        #    强制扩展: 即便 inherit_children=0, 因为 user 配了 BO:edit 等下层 perm, 必须看到下层
        return _expand_via_fk_chain(dimension_id, any_dimension_scope, _data_source)
    except Exception as e:
        logger.error(f"获取用户 dim scope 失败 [user_id={user_id}, dim={dimension_id}]: {e}")
        return None


def _expand_via_fk_chain(
    target_dim: str,
    scope_by_dim: Dict[str, Set[int]],
    ds
) -> Set[int]:
    """[FIX 2026-06-15] 通过 FK 链把高层 dim scope 扩展到目标 dim

    链路: product → version → domain → sub_domain → service_module → business_object
    每个 step 用 parent_fk 字段反向查子表 (子表.parent_fk IN current_ids)
    """
    # [FIX 2026-06-15] 完整 6 级 FK 链 (engine 的 HIERARCHY_CHAIN 只到 sub_domain)
    CHAIN = [
        # (dim_name, child_table, parent_fk_on_child_table)
        ('product', None, None),                          # root, 无 parent
        ('version', 'versions', 'product_id'),
        ('domain', 'domains', 'version_id'),
        ('sub_domain', 'sub_domains', 'domain_id'),
        ('service_module', 'service_modules', 'sub_domain_id'),
        ('business_object', 'business_objects', 'service_module_id'),
    ]

    if target_dim not in [c[0] for c in CHAIN]:
        return set()

    # 1. 找起始位置: 从最高 (i=0) 找第一个有 scope 的 dim, 或到达 target_dim
    current_ids: Optional[Set[int]] = None
    start_idx = -1
    for i, (dim, _, _) in enumerate(CHAIN):
        if dim in scope_by_dim and scope_by_dim[dim]:
            current_ids = set(scope_by_dim[dim])
            start_idx = i
            break

    if current_ids is None:
        # 没有任何 dim 有 scope, 已经不会到这一步 (caller has_any_scope check)
        return set()

    # 1.5 方向检查: target 必须 ≤ start_idx (只能向下走, 不能向上)
    target_idx = next(i for i, (d, _, _) in enumerate(CHAIN) if d == target_dim)
    if target_idx < start_idx:
        # target 在 start 之上, 无法向上扩展 (如: scope=domain, target=product)
        return set()

    # 2. 从 start_idx 开始, 沿 FK 链向下走, 每次查 child_table
    for i in range(start_idx, len(CHAIN)):
        dim, child_table, parent_fk = CHAIN[i]

        if dim == target_dim:
            # 到达目标
            return current_ids

        # 否则继续向下走一步: 用 current_ids 查下一级
        next_i = i + 1
        if next_i >= len(CHAIN):
            break
        next_dim, next_table, next_fk = CHAIN[next_i]
        if not next_table or not next_fk:
            continue

        # 覆盖中间 dim 的 scope (如果存在, 直接用 scope 替换)
        if next_dim in scope_by_dim and scope_by_dim[next_dim]:
            current_ids = set(scope_by_dim[next_dim])
        else:
            # 用 parent_fk 反查子表
            current_ids = _query_child_ids(ds, next_table, next_fk, current_ids)

    return set()


def _query_child_ids(ds, child_table: str, parent_fk: str, parent_ids: Set[int]) -> Set[int]:
    """查子表 id 集合 (child_table.parent_fk IN parent_ids)"""
    if not parent_ids:
        return set()
    placeholders = ",".join("?" for _ in parent_ids)
    try:
        cursor = ds.execute(
            f"SELECT id FROM {child_table} WHERE {parent_fk} IN ({placeholders})",
            list(parent_ids)
        )
        return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"_query_child_ids failed: table={child_table} parent_fk={parent_fk} err={e}")
        return set()


def _parse_id_field(raw) -> List[int]:
    """解析 id 字段: 支持 JSON 字符串 / list / None"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [int(x) for x in raw if str(x).isdigit()]
    if isinstance(raw, str):
        try:
            import json as _json
            parsed = _json.loads(raw)
            if isinstance(parsed, list):
                return [int(x) for x in parsed if str(x).isdigit()]
        except Exception:
            # fallback: 按逗号分隔
            return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
    return []


def _is_admin_user() -> bool:
    """判断当前用户是否 admin (绕过 dim scope)"""
    if not hasattr(g, "current_user") or not g.current_user:
        return False
    perms = g.current_user.get("permissions", []) or []
    if "*" in perms or "admin" in perms:
        return True
    if g.current_user.get("is_admin") is True:
        return True
    return False


def _login_required(f):
    """自定义 login_required 装饰器，支持测试模式"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if _is_testing():
            if not hasattr(g, "current_user") or g.current_user is None:
                g.current_user = {
                    "user_id": 1,
                    "username": "test_user",
                    "permissions": ["*"],
                    "roles": ["admin"],
                }
            return f(*args, **kwargs)
        
        from meta.services.auth_middleware import login_required as auth_login_required
        return auth_login_required(f)(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @_login_required
    def decorated(*args, **kwargs):
        if not hasattr(g, "current_user") or not g.current_user:
            return jsonify({"success": False, "message": "请先登录后再操作"}), 401
        perms = g.current_user.get("permissions", [])
        if "*" not in perms and "admin" not in perms:
            return jsonify({"success": False, "message": "Admin required"}), 403
        return f(*args, **kwargs)

    return decorated


def _build_ancestor_path(dimension_id: str, instance_id: int, data_source) -> str:
    """
    构建维度实例的完整祖先路径 (方案 B: 1 列完整路径)
    
    层级链: product → version → domain → sub_domain → service_module → business_object
    
    返回格式: "parent1 > parent2 > ... > parentN"
    - version: "产品名"
    - domain: "产品名 > 版本名"
    - sub_domain: "产品名 > 版本名 > 领域名"
    - service_module: "产品名 > 版本名 > 领域名 > 子领域名"
    - business_object: "产品名 > 版本名 > 领域名 > 子领域名 > 服务模块名"
    
    性能: 递归查询, 每层 1 次 SQL (数据量小, 可接受)
    """
    if dimension_id == 'product':
        return ""  # product 是 root, 无祖先
    
    path_parts = []
    current_dim = dimension_id
    current_id = instance_id
    
    # 最多递归 6 层 (product → version → domain → sub_domain → service_module → business_object)
    for _ in range(6):
        parent_info = _PARENT_INFO_MAP.get(current_dim)
        if not parent_info:
            break
        
        parent_type, parent_table, parent_fk, parent_display = parent_info
        current_table = RESOURCE_TABLE_MAP.get(current_dim)
        
        # 查当前记录的 parent_id 和 parent_name
        sql = f"""
            SELECT main.{parent_fk}, parent.{parent_display}
            FROM {current_table} main
            LEFT JOIN {parent_table} parent ON main.{parent_fk} = parent.id
            WHERE main.id = ?
        """
        cursor = data_source.execute(sql, [current_id])
        row = cursor.fetchone()
        if not row:
            break
        
        parent_id, parent_name = row
        if parent_id is None or parent_name is None:
            break
        
        # 加到路径 (从 root 到 direct parent, 所以插入到开头)
        path_parts.insert(0, str(parent_name))
        
        # 向上一层
        current_dim = parent_type
        current_id = parent_id
    
    return " > ".join(path_parts)


# [REFACTOR 2026-07-22] 层级值帮助 picker: 构造层级树 (扁平数组, 前端组装嵌套)
# 元数据驱动: 链 / icon / display_name / 颜色 全部从 hierarchies.yaml 读取
# CHAIN 硬编码已移除, RESOURCE_TABLE_MAP/PARENT_FIELD_MAP/DISPLAY_FIELD_MAP 作为 fallback
def _build_dimension_tree(dim: str, version_id: Optional[int] = None,
                          search: Optional[str] = None,
                          user_id: Optional[int] = None) -> Dict[str, Any]:
    """构建层级树的扁平数组 (前端组装嵌套)

    Returns:
        {
          "hierarchy_meta": {
            "root_type": str,
            "levels": [{object_type, display_name, icon, color, level}],
            "ui_config": {default_expand_level, show_count, allow_multi_select},
            "version_id_injected": bool,  # True if version context was used to filter
          },
          "data": [TreeNode...],
          "total": int,
        }

    TreeNode shape:
        {id, parent_id, level, type, name, code, display_name, icon, color,
         has_children, child_count, unique_key, parent_unique_key}
        - unique_key: "{type}_{id}", 全局唯一 (生产数据中 id 在 4 层间会冲突)
        - parent_unique_key: "{parent_type}_{parent_id}" (顶层为 null)
        - display_name/icon/color: 从 YAML level 元数据透传, 前端无需再硬编码
    """
    if dim not in RESOURCE_TABLE_MAP:
        return {"data": [], "total": 0, "hierarchy_meta": _empty_hierarchy_meta()}

    # 复用 _get_engine() 初始化的 _data_source (共享缓存)
    _get_engine()  # 确保 _data_source 已初始化
    ds = _data_source

    # ── 元数据: 优先从 hierarchies.yaml 读取 ──
    biz_h = get_biz_hierarchy()
    if biz_h and biz_h.get('levels'):
        yaml_levels = biz_h['levels']
        # 按 target dim 在 yaml levels 中的位置切链
        yaml_objects = [lv['object'] for lv in yaml_levels if lv.get('object')]
        try:
            target_idx = yaml_objects.index(dim)
        except ValueError:
            target_idx = None
        if target_idx is not None:
            relevant_chain = yaml_objects[:target_idx + 1]
            # 每个 object 的元数据 (用于 hierarchy_meta + node.icon)
            level_meta = {}
            for lv in yaml_levels:
                if lv.get('object'):
                    level_meta[lv['object']] = {
                        'display_name': lv.get('display_name', lv['object']),
                        'icon': (lv.get('ui') or {}).get('icon'),
                        'color': (lv.get('ui') or {}).get('color'),
                    }
            hierarchy_meta = {
                'root_type': biz_h.get('root_object', 'product'),
                'levels': [
                    {
                        'object_type': lv['object'],
                        'display_name': level_meta[lv['object']]['display_name'],
                        'icon': level_meta[lv['object']]['icon'],
                        'color': level_meta[lv['object']]['color'],
                        'level': lv.get('level', idx),
                    }
                    for idx, lv in enumerate(yaml_levels)
                    if lv.get('object') in relevant_chain
                ],
                'ui_config': biz_h.get('ui_config', {}),
                'version_id_injected': bool(version_id),
            }
        else:
            # YAML 里有 hierarchies 但不包含此 dim, 退回 CHAIN fallback
            relevant_chain = ['product', 'version', 'domain', 'sub_domain']
            try:
                relevant_chain = relevant_chain[:relevant_chain.index(dim) + 1]
            except ValueError:
                return {"data": [], "total": 0, "hierarchy_meta": _empty_hierarchy_meta()}
            level_meta = {}
            hierarchy_meta = _empty_hierarchy_meta()
    else:
        # YAML 加载失败, 退回旧硬编码 CHAIN (向后兼容)
        CHAIN_FALLBACK = ['product', 'version', 'domain', 'sub_domain']
        try:
            relevant_chain = CHAIN_FALLBACK[:CHAIN_FALLBACK.index(dim) + 1]
        except ValueError:
            return {"data": [], "total": 0, "hierarchy_meta": _empty_hierarchy_meta()}
        level_meta = {}
        hierarchy_meta = _empty_hierarchy_meta()

    all_nodes = []

    # [TEMP DEBUG R21]
    print(f"[R21-DEBUG] dim={dim}, version_id={version_id}, relevant_chain={relevant_chain}")

    for level_idx, object_type in enumerate(relevant_chain):
        table_name = RESOURCE_TABLE_MAP[object_type]
        display_field = DISPLAY_FIELD_MAP[object_type]
        code_field = CODE_FIELD_MAP.get(object_type, 'code')

        # 探测实际列名: production schema 中 domain/sub_domain 的名称列实际是 'name',
        # 而 DISPLAY_FIELD_MAP 旧值是 'domain_name'/'sub_domain_name', 必须 fallback
        actual_display = display_field
        for candidate in [display_field, 'name']:
            row = ds.execute(
                f"SELECT name FROM pragma_table_info('{table_name}') WHERE name = ?",
                [candidate]
            ).fetchone()
            if row:
                actual_display = candidate
                break

        # 探测 code 列是否存在 (versions 表实际没有 code 列)
        has_code = ds.execute(
            f"SELECT name FROM pragma_table_info('{table_name}') WHERE name = ?",
            [code_field]
        ).fetchone() is not None

        # 构造 SELECT (id, name, code, parent_id)
        if object_type == 'product':
            sql = f"SELECT id, {actual_display}, {code_field} FROM {table_name}"
            params = []
        elif object_type == 'version':
            # versions 表没有 code 列, 用 '' 占位
            parent_fk = PARENT_FIELD_MAP[object_type]
            sql = f"SELECT id, {actual_display}, '' AS code, {parent_fk} FROM {table_name}"
            params = []
            if version_id:
                sql += " WHERE id = ?"
                params.append(version_id)
        else:
            parent_fk = PARENT_FIELD_MAP[object_type]
            sql = f"SELECT id, {actual_display}, {code_field}, {parent_fk} FROM {table_name}"
            params = []

            # version 维度按 version_id 直接过滤
            if object_type == 'domain' and version_id:
                sql += " WHERE version_id = ?"
                params.append(version_id)
            elif object_type == 'sub_domain' and version_id:
                # 跨 domain.version_id 间接过滤
                sql = (
                    f"SELECT sd.id, sd.{actual_display}, sd.{code_field}, sd.{PARENT_FIELD_MAP['sub_domain']} "
                    f"FROM {table_name} sd "
                    f"JOIN domains d ON sd.{PARENT_FIELD_MAP['sub_domain']} = d.id "
                    f"WHERE d.version_id = ?"
                )
                params = [version_id]
            elif object_type == 'service_module' and version_id:
                # [R21 2026-07-24] service_module: 跨 sub_domain → domain → version 三层 JOIN
                sql = (
                    f"SELECT sm.id, sm.{actual_display}, sm.{code_field}, sm.{PARENT_FIELD_MAP['service_module']} "
                    f"FROM {table_name} sm "
                    f"JOIN sub_domains sd ON sm.{PARENT_FIELD_MAP['service_module']} = sd.id "
                    f"JOIN domains d ON sd.{PARENT_FIELD_MAP['sub_domain']} = d.id "
                    f"WHERE d.version_id = ?"
                )
                params = [version_id]
            elif object_type == 'business_object' and version_id:
                # [R21 2026-07-24] business_object: 跨 service_module → sub_domain → domain → version 四层 JOIN
                sql = (
                    f"SELECT bo.id, bo.{actual_display}, bo.{code_field}, bo.{PARENT_FIELD_MAP['business_object']} "
                    f"FROM {table_name} bo "
                    f"JOIN service_modules sm ON bo.{PARENT_FIELD_MAP['business_object']} = sm.id "
                    f"JOIN sub_domains sd ON sm.{PARENT_FIELD_MAP['service_module']} = sd.id "
                    f"JOIN domains d ON sd.{PARENT_FIELD_MAP['sub_domain']} = d.id "
                    f"WHERE d.version_id = ?"
                )
                params = [version_id]

        cursor = ds.execute(sql, params)
        rows = cursor.fetchall()

        # [TEMP DEBUG R21]
        print(f"[R21-DEBUG] level={level_idx} type={object_type} rows={len(rows)} sql={sql[:80]}...")

        # 计算 child_count: 优先从 db 字段, 否则通过 SQL 子查询
        is_leaf = (level_idx == len(relevant_chain) - 1)
        for row in rows:
            node_id = row[0]
            name = row[1]
            code = row[2]
            parent_id = row[3] if level_idx > 0 else None

            child_count = 0
            if not is_leaf:
                child_dim = relevant_chain[level_idx + 1]
                child_table = RESOURCE_TABLE_MAP[child_dim]
                child_parent_fk = PARENT_FIELD_MAP[child_dim]
                count_sql = f"SELECT COUNT(*) FROM {child_table} WHERE {child_parent_fk} = ?"
                c = ds.execute(count_sql, [node_id]).fetchone()
                child_count = c[0] if c else 0

            # [FIX 2026-07-24-R17] parent_id 为 None 时, parent_unique_key 必须为 None
            #   旧逻辑: f"{parent_type}_{None}" = "version_None" (字符串)
            #   新逻辑: None → None, 让前端正确识别为根节点候选
            puk = None
            if level_idx > 0 and parent_id is not None:
                puk = f"{relevant_chain[level_idx - 1]}_{parent_id}"

            # node-level 元数据 (从 level_meta 透传)
            meta = level_meta.get(object_type, {})
            all_nodes.append({
                "id": node_id,
                "parent_id": parent_id,
                "level": level_idx,
                "type": object_type,
                "name": name,
                "code": code,
                "display_name": meta.get('display_name', object_type),
                "icon": meta.get('icon'),
                "color": meta.get('color'),
                "has_children": not is_leaf and child_count > 0,
                "child_count": child_count,
                "unique_key": f"{object_type}_{node_id}",
                "parent_unique_key": puk,
            })

    # [FIX 2026-07-24-R17] 反向过滤: 只保留与目标 dim 节点有祖先关系的节点
    #   原因: 数据库存在大量孤儿节点 (parent_fk 指向不存在的记录, 或 parent_fk 为 NULL)
    #   前端 R14v2 丢弃孤儿, 但为彻底消除顶级出现非 product 节点的问题, 后端也做反向过滤
    #   逻辑: 从目标 dim 叶子反向追溯祖先链, 只保留链上的节点
    #   效果: 顶级只剩 product (product 的 parent_unique_key 为 None 且在祖先链上)
    # [FIX 2026-07-24-R18] 修复: 孤儿节点 (parent_unique_key=None 但 type != root) 不保留
    #   旧 R17 bug: cur.parent_unique_key is None → break, 但 keep 已 add cur → 孤儿被保留
    #   新 R18: 如果 cur.parent_unique_key is None 且 cur.type != root_type, 从 keep 中移除
    if all_nodes and dim != relevant_chain[0]:
        root_type = relevant_chain[0]  # 通常是 'product'
        by_key = {n["unique_key"]: n for n in all_nodes}
        target_keys = {n["unique_key"]: n for n in all_nodes if n["type"] == dim}
        keep = set()
        for tk, tnode in target_keys.items():
            cur = tnode
            depth = 0
            visited = set()
            chain_keys = []  # 先收集链, 验证根节点后再加入 keep
            while cur and depth < 10 and cur["unique_key"] not in visited:
                visited.add(cur["unique_key"])
                chain_keys.append(cur["unique_key"])
                if cur["parent_unique_key"] is None:
                    # 到达根节点: 检查是否为 root_type
                    if cur["type"] == root_type:
                        # 合法链, 全部加入 keep
                        keep.update(chain_keys)
                    # 否则是孤儿 (非 root_type 但 parent_unique_key=None), 不保留
                    break
                cur = by_key.get(cur["parent_unique_key"])
                depth += 1
            else:
                # while 循环正常结束 (没 break), 说明链断裂 (parent 找不到)
                # 这是孤儿, 不保留
                pass
        # [TEMP DEBUG R21]
        target_count = len(target_keys)
        print(f"[R21-DEBUG] reverse_filter: target_keys={target_count}, keep={len(keep)}, before={len(all_nodes)}")
        all_nodes = [n for n in all_nodes if n["unique_key"] in keep]
        print(f"[R21-DEBUG] reverse_filter: after={len(all_nodes)}")

    # [DEBUG 2026-07-24-R17] 写 debug 信息到文件 (临时, 验证后删除)
    try:
        import os as _os
        _debug_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            'test_temp', 'tree_debug.log'
        )
        _os.makedirs(_os.path.dirname(_debug_path), exist_ok=True)
        _type_count = {}
        for _n in all_nodes:
            _type_count[_n["type"]] = _type_count.get(_n["type"], 0) + 1
        _roots = [n for n in all_nodes if n["parent_unique_key"] is None]
        _root_types = {}
        for _r in _roots:
            _root_types[_r["type"]] = _root_types.get(_r["type"], 0) + 1
        _scm = [n for n in all_nodes if n.get("name") == "供应链云"]
        _lines = [
            f"dim={dim}, version_id={version_id}, search={search}",
            f"total={len(all_nodes)}",
            f"type_counts={_type_count}",
            f"root_count={len(_roots)}, root_types={_root_types}",
            f"供应链云 matches={len(_scm)}:",
        ]
        for _n in _scm:
            _lines.append(
                f"  id={_n['id']}, type={_n['type']}, "
                f"unique_key={_n['unique_key']}, "
                f"parent_unique_key={_n['parent_unique_key']}"
            )
        _lines.append("first 10 roots:")
        for _r in _roots[:10]:
            _lines.append(f"  id={_r['id']}, type={_r['type']}, name={_r['name']}")
        with open(_debug_path, 'w', encoding='utf-8') as _f:
            _f.write('\n'.join(_lines))
    except Exception as _e:
        logger.warning(f"[R17-DEBUG] write failed: {_e}")

    # [R21 2026-07-24] 权限过滤: 与 get_dimension_instances 保持一致
    #   复用 _get_user_dim_scope_ids (含 FK 链扩展, 支持 service_module)
    #   仅过滤目标 dim 节点 (如 service_module), 父节点 (product/version/domain/sub_domain) 保留作为路径
    #   admin 跳过; 用户无 scope 配置 (返回 None) 跳过
    if user_id and not _is_admin_user():
        scope_ids = _get_user_dim_scope_ids(int(user_id), dim)
        if scope_ids is not None:
            if scope_ids:
                allowed = scope_ids
                before = len(all_nodes)
                all_nodes = [
                    n for n in all_nodes
                    if n["type"] != dim or n["id"] in allowed
                ]
                logger.info(
                    f"[R21-dim-scope] user_id={user_id} dim={dim} "
                    f"scope={len(allowed)}ids → {before}→{len(all_nodes)}nodes"
                )
            else:
                # 空集: 用户有 scope 但 expand 后无 ids → 移除所有目标 dim 节点
                before = len(all_nodes)
                all_nodes = [n for n in all_nodes if n["type"] != dim]
                logger.info(
                    f"[R21-dim-scope] user_id={user_id} dim={dim} "
                    f"empty scope → {before}→{len(all_nodes)}nodes (target dim removed)"
                )

    # search 过滤: 命中节点 + 完整父链
    if search:
        q = search.lower()
        matched_keys = {n["unique_key"] for n in all_nodes
                        if q in (n["name"] or "").lower() or q in (n["code"] or "").lower()}
        if matched_keys:
            by_key = {n["unique_key"]: n for n in all_nodes}
            keep = set()
            for mk in matched_keys:
                cur = by_key.get(mk)
                # [FIX 2026-07-22] 防循环: depth 限制 + visited 跟踪
                depth = 0
                visited = set()
                while cur and depth < 10 and cur["unique_key"] not in visited:
                    visited.add(cur["unique_key"])
                    keep.add(cur["unique_key"])
                    if cur["parent_unique_key"] is None:
                        break
                    cur = by_key.get(cur["parent_unique_key"])
                    depth += 1
            all_nodes = [n for n in all_nodes if n["unique_key"] in keep]

    return {"data": all_nodes, "total": len(all_nodes), "hierarchy_meta": hierarchy_meta}


def _empty_hierarchy_meta() -> Dict[str, Any]:
    """空 hierarchy_meta (YAML 加载失败时使用)"""
    return {
        "root_type": None,
        "levels": [],
        "ui_config": {},
        "version_id_injected": False,
    }


def _validate_required_fields(data: Dict[str, Any], fields: list) -> Optional[str]:
    for field in fields:
        if field not in data or data[field] is None:
            return f"'{field}' is required"
    return None


@permission_dimension_bp.route("/<dim>/tree", methods=["GET"])
@_login_required
def list_dimension_tree(dim: str):
    """[FIX 2026-07-22] 返回 dim 维度的层级树 (扁平数组)

    URL: /api/v2/bo/permission_dimension/<dim>/tree
    Query: search=<str>, version_id=<int>
    """
    # [R21 2026-07-24] 加 service_module/business_object: 详情页字段用 Tree Search Help
    VALID_DIMS = {"product", "version", "domain", "sub_domain", "service_module", "business_object"}
    if dim not in VALID_DIMS:
        return jsonify({"error": f"invalid dim: {dim}"}), 400

    version_id = request.args.get("version_id", type=int)
    search = request.args.get("search", "").strip() or None
    # [R21] 传入 user_id 做权限过滤 (与 get_dimension_instances 保持一致)
    user_id = None
    if hasattr(g, "current_user") and g.current_user:
        user_id = g.current_user.get("user_id")
    result = _build_dimension_tree(dim, version_id=version_id, search=search, user_id=user_id)
    return jsonify(result), 200


@permission_dimension_bp.route("", methods=["GET"])
@_login_required
def get_dimensions():
    """
    获取管理维度列表

    返回维度列表（产品、版本、领域、子领域、服务模块、业务对象、关系）
    每个维度包含：id, name, code, description, icon, rule_count
    """
    try:
        engine = _get_engine()
        dimensions = engine.get_available_dimensions()

        result_dimensions = []
        for dim in dimensions:
            dim_id = dim.get("id")
            rule_count = _get_rule_count_for_dimension(dim_id)

            result_dimensions.append(
                {
                    "id": dim_id,
                    "name": dim.get("name", ""),
                    "code": dim_id.upper() if dim_id else "",
                    "description": dim.get("description", ""),
                    "icon": _get_icon_for_dimension(dim_id),
                    "rule_count": rule_count,
                }
            )

        return jsonify(
            {"success": True, "data": {"dimensions": result_dimensions}}
        )
    except Exception as e:
        logger.error(f"获取管理维度列表失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================================
# [P1-Base-02] /meta 权限配置元数据聚合端点（yaml 单一权威源下发）
# ============================================================================

# 默认中文标签（resource_types.yaml 无 label 字段，SSOT 中文名在此兜底）
_RESOURCE_TYPE_LABELS = {
    'product': '产品', 'version': '版本', 'domain': '领域', 'sub_domain': '子领域',
    'service_module': '服务模块', 'business_object': '业务对象',
    'relationship': '关系', 'annotation': '标注', 'audit_log': '审计日志',
    'user': '用户', 'role': '角色',
    # [v34 2026-08-27] meta/schemas/*.yaml 拆分声明的 BO，未在 resource_types.yaml 汇总
    #   此处补齐中文 label 兜底（来源：bo.yaml display_name / 业务命名约定）
    'ai_async_task': 'AI 异步任务',
    'enum_type': '枚举类型',
    'scheduled_task': '定时任务',
    'task_execution': '任务执行记录',
    'task_queue': '任务队列',
}

# [Phase 6 2026-08-25] 权限主体白名单（identity resources）
#   这些是「授权主体」(principal)，不是业务对象 ——
#   用户、角色、用户组的分配走专用路径（用户详情/角色详情/用户组详情），不在功能权限矩阵展示。
#   与 SAP PFCG / Oracle Security Console / AWS IAM / Salesforce Profile 一致。
_IDENTITY_RESOURCE_TYPES = frozenset({'user', 'role', 'org'})

def _is_identity_resource(rt: str) -> bool:
    return rt in _IDENTITY_RESOURCE_TYPES

# 默认动作标签（[P2-Matrix-01 / D5] resource_types.yaml.actions 可授权动作的中文标签）
# [v36 2026-08-27] 删除 'list': 后端路由统一校验 'read'（manage_api.py list_records 守卫 read），
#   action_policy.READ_ACTIONS 不包含 list, 维度范围派生也走 read。保留 list 列只增加 UI 噪音。
#   行为变化: 勾 list 现在等价 read, 矩阵不再显示该列。
# [v36 2026-08-27] 新增 'import': _standard_actions.yaml 早已声明 (导入)，但 _ACTION_LABELS
#   未注册导致矩阵不显示此列, 后端 import_export_api 已校验 ot:'import' 守卫, 现在打通。
_ACTION_LABELS = {
    'create': '创建', 'read': '查看', 'update': '编辑',
    'delete': '删除', 'export': '导出', 'import': '导入', 'manage': '管理',
    # [v62 2026-08-28] 补齐 _standard_actions.yaml 已声明的业务动作标签，
    # 差异化动作下沉到行内「+N 动作」popover 后以中文名展示（避免英文 code）
    'approve': '审批', 'search': '搜索',
    'assign': '分配', 'unassign': '取消分配',
    'associate': '关联', 'dissociate': '取消关联',
    'grant': '授权', 'revoke': '撤销', 'list': '列表',
}

# ConditionRuleEditor 默认合法操作符（E6：A2 合法操作符过滤在 Phase 3 由后端按字段类型下发）
_DEFAULT_OPERATORS = ['eq', 'ne', 'in', 'nin', 'contains']


def _load_schema_yaml(filename: str) -> Dict[str, Any]:
    """读取 meta/schemas 下 yaml（/meta 用，直接读文件避免全局缓存陈旧）"""
    schema_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schemas"
    )
    path = os.path.join(schema_dir, filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {}
    except Exception as e:
        logger.warning(f"读取 {filename} 失败: {e}")
        return {}


def _build_tree_picker_data(hierarchy: Dict[str, Any]) -> List[Dict[str, Any]]:
    """[P1-Base-02/E6] 从 hierarchies.yaml levels 生成 HierarchicalTreePicker 数据源

    Returns:
        嵌套树节点数组（entity 按 parent_object 嵌套；association 如 relationship 为根级叶子）：
        [{object, label, table_name, parent_object, foreign_key_field, filter_param,
          icon, color, kind, children}]
    """
    levels = hierarchy.get("levels", []) or []
    nodes: Dict[str, Dict[str, Any]] = {}
    for lv in levels:
        obj = lv.get("object")
        if not obj:
            continue
        ui = lv.get("ui", {}) or {}
        nodes[obj] = {
            "object": obj,
            "label": lv.get("display_name", obj),
            "table_name": lv.get("table_name", ""),
            "parent_object": lv.get("parent_object"),
            "foreign_key_field": lv.get("foreign_key_field"),
            "filter_param": lv.get("filter_param"),
            "icon": ui.get("icon", ""),
            "color": ui.get("color", ""),
            "kind": lv.get("kind", "entity"),
            "children": [],
        }
    roots: List[Dict[str, Any]] = []
    for obj, node in nodes.items():
        parent = node.get("parent_object")
        if parent and parent in nodes:
            nodes[parent]["children"].append(node)
        else:
            roots.append(node)
    return roots


def _load_available_scope_codes() -> List[str]:
    """[P2-Matrix-02] 读取所有可用的 scope code 白名单

    来源: sub_domains.code（去重排序），与前端 archdata 树节点 code 一致
    （如 SCP=供应链计划 / SCM=采购管理）。

    用途: /permission_dimension/meta?scope_code=xxx 的白名单校验。
    scope_code 匹配失败必须返回 400 SCOPE_CODE_INVALID（5.5.4 P0 铁律），
    **绝不** 返回 200 OK + 空数组 / 全量数据（防 2026-08-08 全量加载卡死事故）。

    读取失败时返回空列表（此时任意 scope_code 都会被判无效，宁可 400 也不放行全量）。
    """
    if not _data_source:
        return []
    try:
        cursor = _data_source.execute(
            "SELECT DISTINCT code FROM sub_domains "
            "WHERE code IS NOT NULL AND code != '' ORDER BY code"
        )
        rows = cursor.fetchall() or []
        return [str(r[0]) for r in rows]
    except Exception as e:
        logger.warning(f"[P2-Matrix-02] 读取可用 scope codes 失败，按空白名单处理: {e}")
        return []


# [P2-Matrix-03] 资源×动作矩阵的默认动作列顺序
# 前端矩阵视图按 resource_types.actions 动态过滤（不支持的动作列灰化禁选）。
# 实际列集合由 /meta 按 resource_action_matrix 并集下发（见 _build_resource_action_matrix），
# 此处仅作无 actions 数据时的回退。
_MATRIX_ACTION_COLUMNS = [
    "create", "read", "list", "update", "delete", "export", "manage",
]

# [v62 2026-08-28] 主矩阵列的动作支持率阈值：支持该动作的资源占比 >= 此值才进主列，
# 低频差异化动作下沉到前端行内「+N 动作」popover（见 _matrix_action_columns）
STANDARD_COLUMN_THRESHOLD = 0.5


def _build_resource_action_matrix() -> Dict[str, List[str]]:
    """[P2-Matrix-01 / A5] 构建每个资源类型的可授权动作清单

    来源: resource_types.yaml 每个 rt 的 actions 字段（如 audit_log: [read, list, export]）。
    前端矩阵视图据此动态生成动作列，不支持的列灰化禁选（audit_log 无 create/update/delete）。

    无 actions 字段的 rt 回退默认 CRUD 集（防御：yaml 改动遗漏时矩阵不塌）。

    [Phase 6 2026-08-25] 过滤权限主体 (user/role/org) ——
      它们走专用分配路径，不进入功能权限矩阵的可授权动作白名单。
    """
    # [v36 2026-08-27] 合并 list→read; 新增 import 作为默认动作（导出/导入是常见配套）
    default_actions = ["read", "create", "update", "delete", "export", "import"]
    resource_types_data = _load_schema_yaml("resource_types.yaml")
    result: Dict[str, List[str]] = {}
    for rt, rt_cfg in resource_types_data.items():
        if not isinstance(rt_cfg, dict):
            continue
        # [Phase 6 2026-08-25] 过滤权限主体
        if _is_identity_resource(rt):
            continue
        actions = rt_cfg.get("actions")
        if isinstance(actions, list) and actions:
            result[rt] = [str(a) for a in actions]
        else:
            result[rt] = list(default_actions)
    return result


def _matrix_action_columns() -> List[str]:
    """[P2-Matrix-01] 矩阵动作列 = 所有资源类型支持动作的并集（保序去重）

    [v62 2026-08-28] 高频动作过滤（用户确认方案）：
    仅支持率 >= STANDARD_COLUMN_THRESHOLD 的动作进入主矩阵列；
    低频（差异化）动作下沉到前端行内「+N 动作」popover 配置。
    - 当前数据下所有动作支持率 >= 7/9 → 主列不变，界面零变化
    - 未来某 BO 声明 approve/assign 等差异化动作（支持率 1-2/9）→ 不膨胀主列
    全量 supportedActions 仍经 /meta 的 resource_action_matrix 下发，
    前端据此计算每行「更多动作」集合。
    """
    action_matrix = _build_resource_action_matrix()
    if not action_matrix:
        return list(_MATRIX_ACTION_COLUMNS)

    total = len(action_matrix)
    threshold = STANDARD_COLUMN_THRESHOLD

    columns: List[str] = []
    for acts in action_matrix.values():
        for a in acts:
            if a not in columns:
                columns.append(a)

    def _support_count(a: str) -> int:
        return sum(1 for acts in action_matrix.values() if a in acts)

    # 支持率过滤：全支持（total 本身就是声明动作的资源集合）除外时按阈值筛选
    columns = [a for a in columns
               if total > 0 and _support_count(a) / total >= threshold]
    return columns or list(_MATRIX_ACTION_COLUMNS)


def _build_role_matrices(permission_set_id: int,
                         columns: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """[P2-Matrix-03] 构建角色资源×动作矩阵 + 来源明细（Spec 5.4.1 验收）

    数据源与来源语义（Spec 5.3.1 来源标签 4 色）：
    - include（手动）：permission_set_permissions JOIN permissions 直接分配的功能权限
    - auto（菜单）：  permission_set_menu_permissions → menus.required_permissions（勾选菜单自动授予）
    - derived（维度）：permission_set_dimension_scopes（维度范围勾选 → 派生 read）
    - exclude（Deny）：permission_rules / data_permission_rules 中 is_denied=1
    合并优先级（Deny 优先，Spec 2.2）：exclude > include > auto > derived

    返回 None 表示构建失败（调用方应回退为 null，不阻断 /meta 元数据返回）。
    """
    if not _data_source:
        return None
    try:
        ds = _data_source
        action_columns = columns or _matrix_action_columns()
        # [v62 2026-08-28] 全量 supportedActions（含低频差异化动作），供 cells 全集生成
        action_matrix = _build_resource_action_matrix()

        # ---- 1. include（手动分配）----
        manual: Dict[tuple, str] = {}
        cursor = ds.execute(
            "SELECT p.resource_type, p.action, p.code "
            "FROM permissions p JOIN permission_set_permissions rp ON p.id = rp.permission_id "
            "WHERE rp.permission_set_id = ?",
            [permission_set_id],
        )
        for row in cursor.fetchall() or []:
            rt, action, code = row
            if code == "*":
                continue  # 超级权限跳过（不进入矩阵明细）
            if rt and action:
                manual[(rt, action)] = "include"

        # ---- 2. auto（菜单分配：勾选菜单 → required_permissions 自动授予）----
        auto: Dict[tuple, str] = {}
        cursor = ds.execute(
            "SELECT m.required_permissions "
            "FROM menus m JOIN permission_set_menu_permissions rmp ON m.menu_code = rmp.menu_code "
            "WHERE rmp.permission_set_id = ? AND m.is_active = 1",
            [permission_set_id],
        )
        for row in cursor.fetchall() or []:
            req_raw = row[0]
            try:
                req = json.loads(req_raw) if req_raw else []
            except Exception:
                req = []
            if not isinstance(req, list):
                continue
            for code in req:
                parts = str(code).split(":")
                if len(parts) == 2 and parts[0] and parts[1]:
                    auto[(parts[0], parts[1])] = "auto"

        # ---- 3. derived（维度范围勾选 → 派生 read）----
        derived: Dict[tuple, str] = {}
        cursor = ds.execute(
            "SELECT dimension_code FROM permission_set_dimension_scopes WHERE permission_set_id = ?",
            [permission_set_id],
        )
        dimension_codes_with_scope: Set[str] = set()
        for row in cursor.fetchall() or []:
            dim_code = row[0]
            if dim_code:
                dimension_codes_with_scope.add(dim_code)
                derived[(dim_code, "read")] = "derived"

        # ---- 3a. [v42 2026-08-27] association 资源从端点派生 (Spec: 关系不需独立鉴权)
        # 业界共识（SAP/Palantir/Salesforce Junction Object）: 关联资源权限跟随端点
        # 当 role 在 version/domain/sub_domain 任一端点配了 dimension scope,
        # 自动派生 relationship 的 CRUD 权限（与 dimension_scope_engine.derive_permissions 对齐）。
        # 设计意图来源: dimension_scope_engine.py line 920-944 注释
        # 这里我们检查 dimension_codes_with_scope 是否包含 association 的端点。
        ASSOCIATION_ENDPOINTS = {
            'relationship': ('version', 'domain', 'sub_domain'),
        }
        for bo_id, source_bos in ASSOCIATION_ENDPOINTS.items():
            if any(rt in dimension_codes_with_scope for rt in source_bos):
                for action in ('read', 'create', 'update', 'delete'):
                    key = (bo_id, action)
                    # 优先级：exclude > manual/auto > derived（仅当更高级未覆盖时才写 derived）
                    if key not in derived:
                        derived[key] = "derived"

        # ---- 3b. [v42 2026-08-27] subordinate 资源 owner-auto-grant 派生
        # 业界共识（Salesforce Lookup + 本项目 inherit_owner: true 一致）：
        #   annotation/audit_log 的创建者自动获得该资源的 read+update 权限（owner 自治）。
        # 这里记录 role 内的"owner 级 auto"来源，供运行时 owner 命中时使用。
        # 当前矩阵不直接 grant（owner 校验在运行时做），但来源明细里显式列出，
        # 让管理员看到「这个资源的 read 是因为 owner 自治」而非「未配置」。
        # 注：实际 grant 由运行时 interceptors（chain_owner_resolver + owner_permission）实现。
        SUBORDINATE_OWNER_AUTO = ('annotation', 'audit_log')
        # 仅记录到 sources_detail，不直接写入 derived（避免与 manual/auto 冲突）
        subordinate_owner_auto: Dict[tuple, str] = {}
        for bo_id in SUBORDINATE_OWNER_AUTO:
            for action in ('read', 'update'):
                subordinate_owner_auto[(bo_id, action)] = "owner_auto"

        # ---- 4. exclude（Deny 优先：is_denied=1）----
        exclude: Dict[tuple, str] = {}
        cursor = ds.execute(
            "SELECT resource_type, permission_level FROM data_permission_rules "
            "WHERE permission_set_id = ? AND is_denied = 1",
            [permission_set_id],
        )
        for row in cursor.fetchall() or []:
            rt, pl = row
            if rt and pl:
                exclude[(rt, pl)] = "exclude"
        cursor = ds.execute(
            "SELECT resource_type, permission_level FROM permission_rules "
            "WHERE permission_set_id = ? AND is_denied = 1",
            [permission_set_id],
        )
        for row in cursor.fetchall() or []:
            rt, pl = row
            if rt and pl:
                exclude[(rt, pl)] = "exclude"

        # ---- 合并（exclude > include > auto > derived）----
        # 后写覆盖前写，故最高优先级最后写入：先 derived（最低）再 auto / manual，最后 exclude
        merged: Dict[tuple, str] = {}
        for src in (derived, auto, manual, exclude):
            for key, source in src.items():
                # [Phase 6 2026-08-25] 过滤掉权限主体的合并项 —— 它们走专用分配路径
                if _is_identity_resource(key[0]):
                    continue
                merged[key] = source

        # ---- 行集合（含中文标签）----
        resource_type_labels = dict(_RESOURCE_TYPE_LABELS)
        resource_types_data = _load_schema_yaml("resource_types.yaml")
        for rt, rt_cfg in resource_types_data.items():
            if isinstance(rt_cfg, dict) and rt not in resource_type_labels:
                resource_type_labels[rt] = rt

        # 行集合 = 所有资源类型（即使无权限记录也显示空行），按 yaml 定义顺序
        # [Phase 6 2026-08-25] 排除权限主体 (user/role/org) ——
        #   它们在「用户详情/角色详情/用户组详情」走专用分配路径，不进入功能权限矩阵
        # [FIX 2026-08-25] 合并 merged 里出现但 yaml 未声明的 bo_id
        #   例如 scheduled_task / task_queue / enum_type 等业务 bo，
        #   菜单 required_permissions 引用但 yaml 里没声明 —— 现在也会生成对应行
        declared_rts = set(resource_types_data.keys()) if resource_types_data else set()
        merged_rts = {key[0] for key in merged if not _is_identity_resource(key[0])}
        extra_rts = sorted(merged_rts - declared_rts)
        # [FIX 2026-08-25] 把 merged 里有但 yaml 没声明的 bo 也暴露给前端
        # （fallback label = bo_id 本身，前端用 props.resourceTypeLabels[rt] || rt 兜底）
        for rt in extra_rts:
            if rt and rt not in resource_type_labels:
                resource_type_labels[rt] = rt
        row_types = (
            [rt for rt in resource_types_data.keys() if not _is_identity_resource(rt)]
            + extra_rts
        )
        resources = []
        # [v62 2026-08-28] cells 覆盖「主矩阵列 + 该 RT 专属动作」全集：
        # 主列已按支持率 >=50% 过滤，低频差异化动作若不在此生成 cell，
        # 刷新后其 granted/source 状态会丢失（前端「+N 动作」popover 无法回显）。
        for rt in row_types:
            rt_extra_actions = [
                a for a in action_matrix.get(rt, []) if a not in action_columns
            ]
            cells = {}
            for action in list(action_columns) + rt_extra_actions:
                source = merged.get((rt, action))
                if source:
                    cells[action] = {
                        "granted": source != "exclude",
                        "source": source,
                    }
                else:
                    cells[action] = {"granted": False, "source": ""}
            resources.append({
                "resource_type": rt,
                "label": resource_type_labels.get(rt, rt),
                "cells": cells,
            })

        # ---- 来源明细（[v69 2026-08-28] tooltip 文案通俗化: 去掉技术表名, 讲清楚联动行为）----
        sources_detail = []
        for (rt, action) in manual:
            if _is_identity_resource(rt):
                continue
            sources_detail.append({
                "source": "include", "resource_type": rt, "action": action,
                "origin": "管理员单独授予（独立生效，不随菜单勾选变化）",
            })
        for (rt, action) in auto:
            if _is_identity_resource(rt):
                continue
            sources_detail.append({
                "source": "auto", "resource_type": rt, "action": action,
                "origin": "跟随菜单勾选自动授予（取消菜单时联动清除）",
            })
        for (rt, action) in derived:
            if _is_identity_resource(rt):
                continue
            # [v42 2026-08-27] 区分 dimension 直派生 vs association 端点派生
            is_assoc_derive = rt in ASSOCIATION_ENDPOINTS and action in ('read', 'create', 'update', 'delete')
            origin_text = (
                f"由关联资源自动派生（{rt} 的权限跟随其关联端点的范围配置）"
                if is_assoc_derive
                else "由维度范围自动派生（跟随范围配置联动）"
            )
            sources_detail.append({
                "source": "derived", "resource_type": rt, "action": action,
                "origin": origin_text,
            })
        # [v42 2026-08-27] subordinate owner_auto 来源说明
        for (rt, action) in subordinate_owner_auto:
            if _is_identity_resource(rt):
                continue
            sources_detail.append({
                "source": "owner_auto", "resource_type": rt, "action": action,
                "origin": "Owner 自治：该资源的创建者自动获得此权限（运行时实施）",
            })
        for (rt, action) in exclude:
            if _is_identity_resource(rt):
                continue
            sources_detail.append({
                "source": "exclude", "resource_type": rt, "action": action,
                "origin": "已被明确排除（即使其他来源授予权限也不生效）",
            })

        return {
            "permission_set_id": permission_set_id,
            "columns": action_columns,
            "resources": resources,
            "sources_detail": sources_detail,
        }
    except Exception as e:
        logger.error(f"[P2-Matrix-03] 构建角色矩阵失败 [permission_set_id={permission_set_id}]: {e}")
        return None


@permission_dimension_bp.route("/meta", methods=["GET"])
@_login_required
def get_permission_meta():
    """[P1-Base-02] 权限配置元数据聚合端点（D2 致命修复）

    URL: /api/v2/bo/permission_dimension/meta
    Query: permission_set_id=<int>（可选，Phase 2 起返回角色矩阵占位）

    返回（验收 §5.4.1 P1-Base-02）：
    - dimension_priority: {dimension_code: priority}
    - combination_policy: {scope_combination, owner_always_visible}
    - resource_type_labels: {resource_type: 中文名}
    - action_labels: {action: 中文名}
    - hierarchies_ui_config: {object: {display_name, icon, color, table_name}}
    - normalizedForTreePicker / normalizedForDimensionSelector / normalizedForConditionEditor
      （E6 三个 pre-normalized 适配字段，前端零转换）
    - role_resource_action_matrix / menu_permission_matrix:
      有 permission_set_id 时空对象占位（Phase 2 P2-Matrix-03 填充），无 permission_set_id 为 null
    """
    try:
        engine = _get_engine()
        permission_set_id = request.args.get("permission_set_id", type=int)

        # [P2-Matrix-02] scope_code 白名单校验（BLOCKER，5.5.4 P0 铁律）
        # 支持逗号分隔多编码（与前端 archdata scopeCode=SCP,SCM 一致）。
        # 任一编码无效 → 400 SCOPE_CODE_INVALID，绝不返回 200 OK + 空数组/全量
        # （防 2026-08-08 scopeCode 匹配失败静默回退全量 3230 对象 30s+ 卡死事故）。
        scope_code_raw = (request.args.get("scope_code") or "").strip()
        if scope_code_raw:
            scope_codes = [c.strip() for c in scope_code_raw.split(",") if c.strip()]
            available_scope_codes = _load_available_scope_codes()
            available_set = set(available_scope_codes)
            invalid_codes = [c for c in scope_codes if c not in available_set]
            if invalid_codes:
                return jsonify({
                    "success": False,
                    "error": "SCOPE_CODE_INVALID",
                    "message": (
                        f"范围编码（scope_code）无效: {', '.join(invalid_codes)}，"
                        "已中止加载，未返回任何数据。请使用 available_scope_codes 中的编码"
                    ),
                    "available_scope_codes": available_scope_codes,
                }), 400

        # 1. dimension_priority + combination_policy（engine 已读 dimension_object_mapping.yaml）
        dimension_priority = engine.get_dimension_priority()
        combination_policy = engine.get_combination_policy()
        dimension_object_mappings = engine.get_dimension_object_mappings()

        # 2. hierarchies.ui_config（A4：层级 icon 不再写死，从 hierarchies.yaml ui 段读）
        hierarchies_data = _load_schema_yaml("hierarchies.yaml")
        hierarchy = None
        for h in hierarchies_data.get("hierarchies", []) or []:
            if h.get("id") == "biz_hierarchy":
                hierarchy = h
                break
        hierarchies_ui_config: Dict[str, Dict[str, Any]] = {}
        for lv in (hierarchy or {}).get("levels", []) or []:
            obj = lv.get("object")
            if not obj:
                continue
            ui = lv.get("ui", {}) or {}
            hierarchies_ui_config[obj] = {
                "display_name": lv.get("display_name", obj),
                "icon": ui.get("icon", ""),
                "color": ui.get("color", ""),
                "table_name": lv.get("table_name", ""),
            }

        # 3. resource_type_labels / action_labels + [P2-Matrix-01] 可授权动作清单
        resource_types_data = _load_schema_yaml("resource_types.yaml")
        resource_type_labels = dict(_RESOURCE_TYPE_LABELS)
        for rt in resource_types_data:
            # [Phase 6 2026-08-25] 过滤权限主体 —— 它们走专用路径，矩阵不暴露
            if _is_identity_resource(rt):
                continue
            if isinstance(resource_types_data[rt], dict) and rt not in resource_type_labels:
                resource_type_labels[rt] = rt
        # [Phase 6 2026-08-25] 把权限主体标签也剔掉
        for iden in _IDENTITY_RESOURCE_TYPES:
            resource_type_labels.pop(iden, None)
        # [FIX 2026-08-25] 把菜单里实际引用的 bo 也加进 labels（即使 yaml 没声明）
        # 例如 scheduled_task / task_queue / enum_type —— 菜单 required_permissions 引用
        if _data_source is not None:
            try:
                cursor = _data_source.execute(
                    "SELECT required_permissions, primary_object_type, object_types "
                    "FROM menus WHERE is_active = 1"
                )
                for row in cursor.fetchall() or []:
                    req_raw, primary, obj_types_raw = row
                    try:
                        reqs = json.loads(req_raw) if req_raw else []
                    except Exception:
                        reqs = []
                    for code in reqs:
                        parts = str(code).split(":")
                        if parts and parts[0] and parts[0] != "*" and not _is_identity_resource(parts[0]):
                            if parts[0] not in resource_type_labels:
                                resource_type_labels[parts[0]] = parts[0]
                    if primary and not _is_identity_resource(primary) and primary not in resource_type_labels:
                        resource_type_labels[primary] = primary
                    if obj_types_raw:
                        try:
                            obj_types = json.loads(obj_types_raw) if isinstance(obj_types_raw, str) else obj_types_raw
                            if isinstance(obj_types, list):
                                for t in obj_types:
                                    if t and not _is_identity_resource(t) and t not in resource_type_labels:
                                        resource_type_labels[t] = t
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"[Phase 6 2026-08-25] 收集菜单 bo 失败：{e}")
        action_labels = dict(_ACTION_LABELS)
        # {resource_type: [actions]}，前端矩阵据此灰化禁选不支持的动作列（A5）
        resource_action_matrix = _build_resource_action_matrix()
        # 动作列 = 所有资源类型支持动作的并集（保序）
        matrix_columns = _matrix_action_columns()

        # 4. E6 三个 pre-normalized 适配字段（前端零转换）
        normalized_for_tree_picker = _build_tree_picker_data(hierarchy) if hierarchy else []

        normalized_for_dimension_selector = []
        for mapping in dimension_object_mappings:
            code = mapping.get("dimension_code")
            if not code:
                continue
            ui_node = hierarchies_ui_config.get(code, {})
            normalized_for_dimension_selector.append({
                "id": code,
                "name": ui_node.get("display_name", code),
                "description": mapping.get("description", ""),
                "icon": ui_node.get("icon", ""),
                "ruleCount": _get_rule_count_for_dimension(code),
            })

        normalized_for_condition_editor = []
        for rt, rt_cfg in resource_types_data.items():
            if not isinstance(rt_cfg, dict):
                continue
            normalized_for_condition_editor.append({
                "value": rt,
                "label": resource_type_labels.get(rt, rt),
                "operators": list(_DEFAULT_OPERATORS),
            })

        # 5. 角色矩阵（[P2-Matrix-03] 填充：资源×动作矩阵 + 菜单矩阵 + 来源明细）
        role_matrix: Optional[Dict[str, Any]] = None
        menu_matrix: Optional[List[Dict[str, Any]]] = None
        if permission_set_id:
            # [FIX 2026-08-25] 确保 _data_source 已初始化（多进程 waitress 下不同 worker 可能未初始化）
            if not _data_source:
                _get_engine()
            # 菜单矩阵复用 role_menu_api 已重构的纯函数（菜单→required_permissions→bo_permission_groups）
            from meta.api.role_menu_api import _build_role_unified_data

            unified_data = _build_role_unified_data(permission_set_id)
            if unified_data is not None:
                menu_matrix = unified_data.get("menus")
            role_matrix = _build_role_matrices(permission_set_id, columns=matrix_columns)

        return jsonify({
            "success": True,
            "data": {
                "dimension_priority": dimension_priority,
                "combination_policy": combination_policy,
                "resource_type_labels": resource_type_labels,
                "action_labels": action_labels,
                # [P2-Matrix-01 / A5] {resource_type: [可授权动作]}，前端灰化禁选依据
                "resource_action_matrix": resource_action_matrix,
                "hierarchies_ui_config": hierarchies_ui_config,
                "normalizedForTreePicker": normalized_for_tree_picker,
                "normalizedForDimensionSelector": normalized_for_dimension_selector,
                "normalizedForConditionEditor": normalized_for_condition_editor,
                "role_resource_action_matrix": role_matrix,
                "menu_permission_matrix": menu_matrix,
            }
        }), 200
    except Exception as e:
        logger.error(f"获取权限配置元数据失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@permission_dimension_bp.route(
    "/<string:dimension_id>/instances", methods=["GET"]
)
@_login_required
def get_dimension_instances(dimension_id: str):
    """
    获取维度实例列表（用于 value help）

    参数：dimension_id, search, page, page_size
    返回：实例列表（如：所有领域、所有产品）
    支持搜索、过滤、分页
    """
    try:
        engine = _get_engine()

        search = request.args.get("search", "").strip()
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 20, type=int)

        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20

        offset = (page - 1) * page_size

        table_name = RESOURCE_TABLE_MAP.get(dimension_id)
        if not table_name:
            return jsonify(
                {"success": False, "message": f"Unknown dimension: {dimension_id}"}
            ), 400

        display_field = DISPLAY_FIELD_MAP.get(dimension_id, "name")
        code_field = CODE_FIELD_MAP.get(dimension_id, "code")

        parent_info = _PARENT_INFO_MAP.get(dimension_id)
        has_parent = parent_info is not None

        try:
            cursor = _data_source.execute(f"PRAGMA table_info({table_name})")
            columns = [r[1] for r in cursor.fetchall()]
        except Exception:
            columns = []

        if display_field not in columns:
            if "name" in columns:
                display_field = "name"
            elif code_field in columns:
                display_field = code_field
            else:
                display_field = "id"

        if code_field not in columns:
            code_field = "id"

        where_clause = ""
        params = []
        seen_filter_keys = set()
        if search:
            where_clause = f"WHERE (main.{display_field} LIKE ? OR main.{code_field} LIKE ?)"
            search_param = f"%{search}%"
            params = [search_param, search_param]

        for key in request.args:
            if key.startswith('filter_') and key not in seen_filter_keys:
                field_name = key[7:]
                if field_name in columns:
                    filter_values = request.args.getlist(key)
                    filter_values = [v for v in filter_values if v]
                    if not filter_values:
                        continue
                    seen_filter_keys.add(key)
                    if len(filter_values) == 1:
                        if where_clause:
                            where_clause += f" AND main.{field_name} = ?"
                        else:
                            where_clause = f"WHERE main.{field_name} = ?"
                        params.append(filter_values[0])
                    else:
                        placeholders = ','.join(['?' for _ in filter_values])
                        if where_clause:
                            where_clause += f" AND main.{field_name} IN ({placeholders})"
                        else:
                            where_clause = f"WHERE main.{field_name} IN ({placeholders})"
                        params.extend(filter_values)

        # [FIX 2026-06-15] 应用用户 dim scope 过滤
        # 业务背景: ValueHelp 弹窗 (来源/目标 4 级级联) 需按用户 role 的 dimension scope 过滤
        # 修复前: 完全不过滤, TEST888 配 dim_scope=domain=703 却看到全部 484 个 domain
        # 修复后: 仅返回用户 role scope 覆盖的 instance (admin 跳过)
        if not _is_admin_user() and hasattr(g, "current_user") and g.current_user:
            user_id = g.current_user.get("user_id")
            if user_id:
                scope_ids = _get_user_dim_scope_ids(int(user_id), dimension_id)
                if scope_ids is not None:
                    # [FIX 2026-06-15] scope_ids 是空集 vs 非空集 区分:
                    #   非空 → IN (ids)
                    #   空集 (role 有 scope 但 expand 后无 ids) → 无可见 (返回空分页)
                    if scope_ids:
                        id_placeholders = ','.join(['?' for _ in scope_ids])
                        if where_clause:
                            where_clause += f" AND main.id IN ({id_placeholders})"
                        else:
                            where_clause = f"WHERE main.id IN ({id_placeholders})"
                        params.extend(list(scope_ids))
                    else:
                        # 空集: 强一致 0 条可见
                        if where_clause:
                            where_clause += " AND 1=0"
                        else:
                            where_clause = "WHERE 1=0"
                        logger.info(
                            f"[dim-scope] user_id={user_id} dim={dimension_id} "
                            f"role scope 配置但 expand 后为空, 强制 0 条可见"
                        )

        select_fields = f"main.id, main.{code_field}, main.{display_field}"
        from_clause = f"FROM {table_name} main"
        count_from = f"FROM {table_name} main"

        if has_parent:
            parent_type, parent_table, parent_fk, parent_display = parent_info
            select_fields += f", parent.{parent_display} AS parent_name"
            from_clause += f" LEFT JOIN {parent_table} parent ON main.{parent_fk} = parent.id"
            count_from += f" LEFT JOIN {parent_table} parent ON main.{parent_fk} = parent.id"

        count_sql = f"SELECT COUNT(*) {count_from} {where_clause}"
        cursor = _data_source.execute(count_sql, params)
        total_count = cursor.fetchone()[0]

        sql = f"""
            SELECT {select_fields}
            {from_clause}
            {where_clause}
            ORDER BY main.{display_field}
            LIMIT ? OFFSET ?
        """
        params_with_pagination = params + [page_size, offset]
        cursor = _data_source.execute(sql, params_with_pagination)

        instances = []
        if has_parent:
            for row in cursor.fetchall():
                inst = {
                    "id": row[0],
                    "code": str(row[1]) if row[1] else "",
                    "name": str(row[2]) if row[2] else "",
                    "parent_name": str(row[3]) if row[3] is not None else "",
                }
                # 方案 B: 完整祖先路径
                inst["ancestor_path"] = _build_ancestor_path(dimension_id, row[0], _data_source)
                instances.append(inst)
        else:
            for row in cursor.fetchall():
                inst = {
                    "id": row[0],
                    "code": str(row[1]) if row[1] else "",
                    "name": str(row[2]) if row[2] else "",
                }
                # product 维度无祖先, ancestor_path 为空字符串
                inst["ancestor_path"] = ""
                instances.append(inst)

        return jsonify(
            {
                "success": True,
                "data": {
                    "instances": instances,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total_count": total_count,
                        "total_pages": (total_count + page_size - 1) // page_size,
                    },
                },
            }
        )
    except Exception as e:
        logger.error(f"获取维度实例列表失败 [dimension_id={dimension_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@permission_dimension_bp.route(
    "/../roles/<int:permission_set_id>/permission-rules", methods=["GET"]
)
@_login_required
def get_role_permission_rules(permission_set_id: int):
    """
    获取角色的权限规则

    参数：permission_set_id
    返回：该角色的所有权限规则（从 permission_rule 表查询）
    """
    try:
        engine = _get_engine()
        rules = engine._get_role_permission_rules(permission_set_id)

        return jsonify({"success": True, "data": {"rules": rules, "permission_set_id": permission_set_id}})
    except Exception as e:
        logger.error(f"获取角色权限规则失败 [permission_set_id={permission_set_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


roles_bp = Blueprint("permission_dimension_roles", __name__, url_prefix="/api/v1/roles")


@roles_bp.route("/<int:permission_set_id>/permission-rules", methods=["GET"])
@_login_required
def get_role_permission_rules_v2(permission_set_id: int):
    """
    获取角色的权限规则

    参数：permission_set_id
    返回：该角色的所有权限规则（从 permission_rule 表查询）
    """
    try:
        engine = _get_engine()
        rules = engine._get_role_permission_rules(permission_set_id)

        return jsonify({"success": True, "data": {"rules": rules, "permission_set_id": permission_set_id}})
    except Exception as e:
        logger.error(f"获取角色权限规则失败 [permission_set_id={permission_set_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@roles_bp.route("/<int:permission_set_id>/permission-rules", methods=["POST"])
@_login_required
def save_permission_rule(permission_set_id: int):
    """
    保存权限规则

    参数：permission_set_id, resource_type, condition, permission_level, inherit_to_children, propagate_to_parents, is_denied
    返回：保存结果
    保存后自动失效缓存
    """
    try:
        try:
            data = request.get_json(force=True, silent=True)
        except Exception:
            data = None
        
        if not data:
            return jsonify({"success": False, "message": "Request body is required"}), 400

        error = _validate_required_fields(data, ["resource_type", "condition"])
        if error:
            return jsonify({"success": False, "message": error}), 400

        engine = _get_engine()

        rule_data = {
            "permission_set_id": permission_set_id,
            "resource_type": data["resource_type"],
            "condition": data["condition"],
            "permission_level": data.get("permission_level", "read"),
            "is_denied": data.get("is_denied", False),
            "inherit_to_children": data.get("inherit_to_children", True),
            "propagate_to_parents": data.get("propagate_to_parents", True),
            "analysis_mode": data.get("analysis_mode"),
            "created_by": g.current_user.get("user_id")
            if hasattr(g, "current_user") and g.current_user
            else None,
        }

        cursor = _data_source.execute(
            """INSERT INTO permission_rules
               (permission_set_id, resource_type, condition, permission_level, is_denied,
                inherit_to_children, propagate_to_parents, analysis_mode, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                rule_data["permission_set_id"],
                rule_data["resource_type"],
                rule_data["condition"],
                rule_data["permission_level"],
                1 if rule_data["is_denied"] else 0,
                1 if rule_data["inherit_to_children"] else 0,
                1 if rule_data["propagate_to_parents"] else 0,
                rule_data["analysis_mode"],
                rule_data["created_by"],
            ],
        )

        rule_id = cursor.lastrowid

        engine.invalidate_cache(permission_set_id=permission_set_id)

        logger.info(f"保存权限规则成功 [permission_set_id={permission_set_id}, rule_id={rule_id}]")

        # [FIX 2026-06-12] 角色权限规则审计日志: 关联到角色对象
        from meta.api._audit_helper import write_permission_config_audit
        write_permission_config_audit(
            action='CREATE',
            object_type='permission_rule',
            object_id=rule_id,
            data={
                'permission_set_id': permission_set_id,
                'resource_type': data.get('resource_type'),
                'permission_level': data.get('permission_level', 'read'),
            },
            parent_object_type='role',
            parent_object_id=permission_set_id,
        )

        return jsonify(
            {
                "success": True,
                "data": {"rule_id": rule_id, "permission_set_id": permission_set_id},
                "message": "Permission rule saved successfully",
            }
        )
    except Exception as e:
        logger.error(f"保存权限规则失败 [permission_set_id={permission_set_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@roles_bp.route("/<int:permission_set_id>/resource-action-matrix", methods=["PUT"])
@_login_required
def save_resource_action_matrix(permission_set_id: int):
    """
    保存角色「资源 × 动作」矩阵手动授权

    [FIX v41 2026-08-27] Bug 修复：前端 ResourceActionMatrix 的 cell.granted 变更
    此前无对应写入端点，导致用户勾选矩阵后保存无效（refresh 即丢失）。

    入参：
      { "cells": [
          {"resource_type": "business_object", "action": "read", "granted": true},
          ...
      ]}

    存储语义（与 _build_role_matrices 的 manual 来源对齐）：
      - granted=true  → 确保 permissions 表存在 code="{rt}:{action}" 记录，
                          resource_type=rt, action=action，然后 INSERT permission_set_permissions(permission_set_id, permission_id)
      - granted=false → DELETE permission_set_permissions 中对应 permission 的关联行
      - 已存在的 permission_set_menu_permissions / permission_set_dimension_scopes 不在此端点处理
        （它们走 PUT /menu-permissions 和 POST /dimension-scopes）

    事务 + 缓存失效：失败自动回滚。
    """
    try:
        try:
            data = request.get_json(force=True, silent=True)
        except Exception:
            data = None

        if not data or not isinstance(data.get("cells"), list):
            return jsonify({
                "success": False,
                "message": "Request body 需包含 cells 数组",
            }), 400

        cells = data["cells"]
        if not all(isinstance(c, dict) and c.get("resource_type") and c.get("action") for c in cells):
            return jsonify({
                "success": False,
                "message": "每个 cell 必须包含 resource_type 与 action",
            }), 400

        ds = _data_source
        if ds is None:
            # 多进程 / test 模式下 worker 可能未初始化 → 显式触发初始化
            _get_engine()
            ds = _data_source
        if ds is None:
            return jsonify({
                "success": False,
                "message": "DataSource 未初始化，无法保存",
            }), 500

        granted_count = 0
        revoked_count = 0

        with ds.transaction():
            for c in cells:
                rt = str(c["resource_type"]).strip()
                action = str(c["action"]).strip()
                granted = bool(c.get("granted"))

                if not rt or not action:
                    continue

                # 过滤权限主体（与 _build_role_matrices 对齐，不进入功能权限矩阵）
                if _is_identity_resource(rt):
                    continue

                # 找 / 创 permissions(code="{rt}:{action}")
                code = f"{rt}:{action}"
                cursor = ds.execute(
                    "SELECT id FROM permissions WHERE code = ?", [code]
                )
                row = cursor.fetchone() if cursor else None
                if row is None:
                    # 没找到 → 创建（resource_type + action 必须填，否则 _build_role_matrices 读不到）
                    cur = ds.execute(
                        """INSERT INTO permissions (code, name, resource_type, action, description)
                           VALUES (?, ?, ?, ?, ?)""",
                        [code, code, rt, action, f"Auto-created for {rt}:{action}"],
                    )
                    # 兼容不同 data_source 实现：sqlite3 cursor 用 lastrowid
                    perm_id = getattr(cur, "lastrowid", None)
                    if perm_id is None:
                        # 重新 select 获取 id
                        cur2 = ds.execute(
                            "SELECT id FROM permissions WHERE code = ?", [code]
                        )
                        r2 = cur2.fetchone() if cur2 else None
                        perm_id = r2[0] if r2 else None
                else:
                    # sqlite3.Row 索引 + tuple 都支持
                    perm_id = row[0] if isinstance(row, tuple) else row["id"]

                if not perm_id:
                    raise RuntimeError(f"无法为 {code} 分配 permission_id")

                if granted:
                    # 确保 (permission_set_id, permission_id) 存在 —— INSERT OR IGNORE 避免重复键冲突
                    ds.execute(
                        """INSERT OR IGNORE INTO permission_set_permissions (permission_set_id, permission_id)
                           VALUES (?, ?)""",
                        [permission_set_id, perm_id],
                    )
                    granted_count += 1
                else:
                    # 撤销：DELETE 关联
                    ds.execute(
                        "DELETE FROM permission_set_permissions WHERE permission_set_id = ? AND permission_id = ?",
                        [permission_set_id, perm_id],
                    )
                    revoked_count += 1

        # 缓存失效（与 POST /permission-rules 同样的 invalidate 模式）
        try:
            engine = _get_engine()
            engine.invalidate_cache(permission_set_id=permission_set_id)
        except Exception as cache_err:
            logger.warning(f"[resource-action-matrix] 缓存失效失败（非阻断）: {cache_err}")

        logger.info(
            f"[resource-action-matrix] 保存成功 permission_set_id={permission_set_id} "
            f"granted={granted_count} revoked={revoked_count}"
        )

        return jsonify({
            "success": True,
            "data": {
                "permission_set_id": permission_set_id,
                "granted": granted_count,
                "revoked": revoked_count,
                "total": len(cells),
            },
            "message": "Resource action matrix saved",
        })
    except Exception as e:
        logger.error(f"保存资源×动作矩阵失败 [permission_set_id={permission_set_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@roles_bp.route("/<int:permission_set_id>/calculate-impact", methods=["POST"])
@_login_required
def calculate_impact(permission_set_id: int):
    """
    计算影响范围

    参数：permission_set_id
    返回：影响范围（调用 PermissionDimensionEngine.calculate_impact()）
    """
    try:
        engine = _get_engine()
        result = engine.calculate_impact(permission_set_id)

        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"计算影响范围失败 [permission_set_id={permission_set_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


meta_bp = Blueprint("permission_dimension_meta", __name__, url_prefix="/api/v1/meta")


@meta_bp.route("/cache-stats", methods=["GET"])
@_login_required
def get_cache_stats():
    """
    获取缓存统计

    返回：缓存命中率、缓存大小、性能指标
    """
    try:
        engine = _get_engine()
        stats = engine.get_cache_stats()

        return jsonify({"success": True, "data": stats})
    except Exception as e:
        logger.error(f"获取缓存统计失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


def _get_rule_count_for_dimension(dimension_id: Optional[str]) -> int:
    """获取维度的规则数量"""
    if not dimension_id or not _data_source:
        return 0

    try:
        cursor = _data_source.execute(
            "SELECT COUNT(*) FROM permission_rules WHERE resource_type = ?",
            [dimension_id],
        )
        result = cursor.fetchone()
        return result[0] if result else 0
    except Exception:
        return 0


def _get_icon_for_dimension(dimension_id: Optional[str]) -> str:
    """获取维度的图标"""
    icon_map = {
        "product": "package",
        "version": "tag",
        "domain": "business",
        "sub_domain": "account_tree",
        "service_module": "widgets",
        "business_object": "description",
        "relationship": "link",
    }
    return icon_map.get(dimension_id, "category")


def register_permission_dimension_apis(app):
    """注册管理维度 API 蓝图"""
    app.register_blueprint(permission_dimension_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(meta_bp)
    logger.info("[OK] 管理维度 API 注册完成")
