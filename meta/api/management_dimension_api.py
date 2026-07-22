# -*- coding: utf-8 -*-
"""
管理维度权限配置 API

提供管理维度、维度实例、权限规则配置、影响范围计算等端点
"""

import logging
import os
from functools import wraps
from typing import Any, Dict, List, Optional, Set

from flask import Blueprint, g, jsonify, request

from meta.core.datasource import get_data_source
from meta.core.yaml_loader import get_biz_hierarchy
from meta.services.management_dimension_engine import (
    CHILD_TYPE_MAP,
    CODE_FIELD_MAP,
    DISPLAY_FIELD_MAP,
    PARENT_FIELD_MAP,
    RESOURCE_TABLE_MAP,
    ManagementDimensionEngine,
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

management_dimension_bp = Blueprint(
    "management_dimension", __name__, url_prefix="/api/v2/bo/management_dimension"
)

_engine: Optional[ManagementDimensionEngine] = None
_data_source = None


def _get_engine() -> ManagementDimensionEngine:
    global _engine, _data_source
    if _engine is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "architecture.db"
        )
        _data_source = get_data_source("sqlite", database=db_path)
        _engine = ManagementDimensionEngine(_data_source, ttl_seconds=300)
    return _engine


def _is_testing():
    """检查是否为测试模式"""
    import os
    return os.environ.get("FLASK_ENV") == "testing" or os.environ.get("TESTING") == "1"


def _get_user_dim_scope_ids(user_id: int, dimension_id: str) -> Optional[Set[int]]:
    """[FIX 2026-06-15] 收集用户在指定 dimension 上可见的 id 集合

    数据源链路:
        user_group_members → group_roles → role_dimension_scopes
        → DimensionScopeEngine.expand_dimension_values(role_id) → {dim: set(ids)}

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
            "SELECT group_id FROM user_group_members WHERE user_id = ?",
            [user_id]
        )
        group_ids = [r[0] for r in cursor.fetchall()]
        if not group_ids:
            return None

        # 2. groups → role_ids (DISTINCT)
        placeholders = ",".join("?" for _ in group_ids)
        cursor = _data_source.execute(
            f"SELECT DISTINCT role_id FROM group_roles WHERE group_id IN ({placeholders})",
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

        for role_id in role_ids:
            try:
                expanded = engine.expand_dimension_values(role_id)
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
                        f'[get_user_dimension_scope] role={role_id} dim={dim} wildcard-only '
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
                          search: Optional[str] = None) -> Dict[str, Any]:
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

        cursor = ds.execute(sql, params)
        rows = cursor.fetchall()

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
                "parent_unique_key": (
                    f"{relevant_chain[level_idx - 1]}_{parent_id}"
                    if level_idx > 0 else None
                ),
            })

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


@management_dimension_bp.route("/<dim>/tree", methods=["GET"])
@_login_required
def list_dimension_tree(dim: str):
    """[FIX 2026-07-22] 返回 dim 维度的层级树 (扁平数组)

    URL: /api/v2/bo/management_dimension/<dim>/tree
    Query: search=<str>, version_id=<int>
    """
    VALID_DIMS = {"product", "version", "domain", "sub_domain"}
    if dim not in VALID_DIMS:
        return jsonify({"error": f"invalid dim: {dim}"}), 400

    version_id = request.args.get("version_id", type=int)
    search = request.args.get("search", "").strip() or None
    result = _build_dimension_tree(dim, version_id=version_id, search=search)
    return jsonify(result), 200


@management_dimension_bp.route("", methods=["GET"])
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


@management_dimension_bp.route(
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


@management_dimension_bp.route(
    "/../roles/<int:role_id>/permission-rules", methods=["GET"]
)
@_login_required
def get_role_permission_rules(role_id: int):
    """
    获取角色的权限规则

    参数：role_id
    返回：该角色的所有权限规则（从 permission_rule 表查询）
    """
    try:
        engine = _get_engine()
        rules = engine._get_role_permission_rules(role_id)

        return jsonify({"success": True, "data": {"rules": rules, "role_id": role_id}})
    except Exception as e:
        logger.error(f"获取角色权限规则失败 [role_id={role_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


roles_bp = Blueprint("management_dimension_roles", __name__, url_prefix="/api/v1/roles")


@roles_bp.route("/<int:role_id>/permission-rules", methods=["GET"])
@_login_required
def get_role_permission_rules_v2(role_id: int):
    """
    获取角色的权限规则

    参数：role_id
    返回：该角色的所有权限规则（从 permission_rule 表查询）
    """
    try:
        engine = _get_engine()
        rules = engine._get_role_permission_rules(role_id)

        return jsonify({"success": True, "data": {"rules": rules, "role_id": role_id}})
    except Exception as e:
        logger.error(f"获取角色权限规则失败 [role_id={role_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@roles_bp.route("/<int:role_id>/permission-rules", methods=["POST"])
@_login_required
def save_permission_rule(role_id: int):
    """
    保存权限规则

    参数：role_id, resource_type, condition, permission_level, inherit_to_children, propagate_to_parents, is_denied
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
            "role_id": role_id,
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
               (role_id, resource_type, condition, permission_level, is_denied,
                inherit_to_children, propagate_to_parents, analysis_mode, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                rule_data["role_id"],
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

        engine.invalidate_cache(role_id=role_id)

        logger.info(f"保存权限规则成功 [role_id={role_id}, rule_id={rule_id}]")

        # [FIX 2026-06-12] 角色权限规则审计日志: 关联到角色对象
        from meta.api._audit_helper import write_permission_config_audit
        write_permission_config_audit(
            action='CREATE',
            object_type='permission_rule',
            object_id=rule_id,
            data={
                'role_id': role_id,
                'resource_type': data.get('resource_type'),
                'permission_level': data.get('permission_level', 'read'),
            },
            parent_object_type='role',
            parent_object_id=role_id,
        )

        return jsonify(
            {
                "success": True,
                "data": {"rule_id": rule_id, "role_id": role_id},
                "message": "Permission rule saved successfully",
            }
        )
    except Exception as e:
        logger.error(f"保存权限规则失败 [role_id={role_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@roles_bp.route("/<int:role_id>/calculate-impact", methods=["POST"])
@_login_required
def calculate_impact(role_id: int):
    """
    计算影响范围

    参数：role_id
    返回：影响范围（调用 ManagementDimensionEngine.calculate_impact()）
    """
    try:
        engine = _get_engine()
        result = engine.calculate_impact(role_id)

        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"计算影响范围失败 [role_id={role_id}]: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


meta_bp = Blueprint("management_dimension_meta", __name__, url_prefix="/api/v1/meta")


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


def register_management_dimension_apis(app):
    """注册管理维度 API 蓝图"""
    app.register_blueprint(management_dimension_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(meta_bp)
    logger.info("[OK] 管理维度 API 注册完成")
