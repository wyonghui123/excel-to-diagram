from flask import Blueprint, request, jsonify
from meta.services.auth_middleware import login_required, get_current_user, is_admin
from meta.services.cascade_service import get_type_order, HierarchyConfigLoader
from meta.core.datasource import get_data_source
from meta.core.enrichment_engine import enrich_records
import os
import logging
import traceback

logger = logging.getLogger(__name__)

special_bp = Blueprint('special', __name__, url_prefix='/api/v1')

_data_source = None
_query_service = None
_hierarchy_filter_service = None
_data_perm_filter = None
AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'true').lower() in ('true', '1', 'yes')


def init_special_services(data_source=None, manage_service=None, query_service=None,
                          hierarchy_filter_service=None, data_perm_filter=None):
    global _data_source, _query_service, _hierarchy_filter_service, _data_perm_filter
    _data_source = data_source or get_data_source()
    _query_service = query_service
    _hierarchy_filter_service = hierarchy_filter_service
    _data_perm_filter = data_perm_filter


def _compute_category(relation):
    name, scope_id, _ = HierarchyConfigLoader.compute_scope(relation)
    if name:
        return (name, scope_id)
    return ('同服务模块', 'same_module')


# [FIX 2026-06-10] relationship 表本身没有 source.domain_id / target.domain_id 列,
#   hierarchy_scope 规则表达式必须用内联子查询才能在关系表上直接 ORDER BY.
#   与下方 category_types 过滤逻辑保持一致 (避免 LEFT JOIN d1/d2/sd1/sd2/sm1/sm2)
def _relationship_source_domain_id():
    return ("(SELECT sd.domain_id FROM sub_domains sd "
            "JOIN service_modules sm ON sd.id = sm.sub_domain_id "
            "JOIN business_objects bo ON sm.id = bo.service_module_id "
            "WHERE bo.id = r.source_bo_id)")


def _relationship_target_domain_id():
    return ("(SELECT sd.domain_id FROM sub_domains sd "
            "JOIN service_modules sm ON sd.id = sm.sub_domain_id "
            "JOIN business_objects bo ON sm.id = bo.service_module_id "
            "WHERE bo.id = r.target_bo_id)")


def _relationship_source_sub_domain_id():
    return ("(SELECT sm.sub_domain_id FROM service_modules sm "
            "JOIN business_objects bo ON sm.id = bo.service_module_id "
            "WHERE bo.id = r.source_bo_id)")


def _relationship_target_sub_domain_id():
    return ("(SELECT sm.sub_domain_id FROM service_modules sm "
            "JOIN business_objects bo ON sm.id = bo.service_module_id "
            "WHERE bo.id = r.target_bo_id)")


def _relationship_source_service_module_id():
    return ("(SELECT bo.service_module_id FROM business_objects bo "
            "WHERE bo.id = r.source_bo_id)")


def _relationship_target_service_module_id():
    return ("(SELECT bo.service_module_id FROM business_objects bo "
            "WHERE bo.id = r.target_bo_id)")


def _derive_bo_ids_from_dim_scope(ds, user_id: int) -> list:
    """[FIX v1.1.14 2026-06-15] 从 user 的 dimension scope 派生业务对象 ID 列表

    用于 v1 /api/v1/relationships 关系范围树, 跟 v2 /api/v2/bo/relationship
    (走 DataPermissionInterceptor OR-of-AND) 行为对齐.

    语义: 多 role 时, 任一 role 派生命中 → 允许 (跟 DataPermissionInterceptor 一致)
          TEST333 (5434 + 5970) → 5970 派生 domain=703 → BO 派生
            → 7 个 BO (467, 468, 469, 470, 471, 492, 494)
            → 任一 role 派生: 5434 无 dim scope 不参与, 5970 派生 7 BO
            → 返回 [467, 468, 469, 470, 471, 492, 494]
            → 关系 list: source/target 任一在这 7 BO 内 → 4 条 (TEST333 实测)

    Args:
        ds: DataSource
        user_id: 用户 ID

    Returns:
        list[int]: BO id 列表, 空 list 表示无 dim scope (fallback 到 allowed_bo_ids=None)
    """
    try:
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        ds_engine = DimensionScopeEngine(ds)
    except Exception as e:
        logger.warning(f"[_derive_bo_ids_from_dim_scope] import DimensionScopeEngine failed: {e}")
        return []

    # 1. 拿 user → group → role 链路
    try:
        cursor = ds.execute(
            """SELECT DISTINCT gr.role_id
               FROM group_roles gr
               JOIN user_group_members ugm ON gr.group_id = ugm.group_id
               WHERE ugm.user_id = ?""",
            [user_id]
        )
        user_role_ids = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f"[_derive_bo_ids_from_dim_scope] query role_ids failed: {e}")
        return []

    if not user_role_ids:
        return []

    # 2. 对每个 role 调 expand_dimension_values, 沿 chain 派生 d/sd/sm 范围
    #    之后用 nested SQL 反查 BO
    #    语义: 多 role 取并集 (跟 V1.1.7 OR-of-AND 修复一致)
    # 注: TEST333 5970 派生 {domain: [703]}, 然后用 SQL chain 派生 BO
    all_d_ids = set()
    all_sd_ids = set()
    all_sm_ids = set()
    all_bo_ids = set()
    any_role_has_scope = False  # 至少一个 role 有 dim scope 配置

    for rid in user_role_ids:
        try:
            expanded = ds_engine.expand_dimension_values(rid)
        except Exception as e:
            logger.warning(f"[_derive_bo_ids_from_dim_scope] role {rid} expand failed: {e}")
            continue
        if not expanded:
            continue
        any_role_has_scope = True
        if 'domain' in expanded: all_d_ids.update(expanded['domain'])
        if 'sub_domain' in expanded: all_sd_ids.update(expanded['sub_domain'])
        if 'service_module' in expanded: all_sm_ids.update(expanded['service_module'])
        # [V1.1.14 增强] business_object 直接在 expanded (如果 yaml mapping 配了)
        if 'business_object' in expanded: all_bo_ids.update(expanded['business_object'])

    # 没有任何 role 有 dim scope → 返回 [] 让 v1 维持 allowed_bo_ids=None (不应用过滤)
    # 跟 v2 DataPermissionInterceptor 'not per_role_conditions' 行为一致
    if not any_role_has_scope:
        return []

    # 3. 沿 chain 用 raw SQL 派生 BO ids
    #    条件: bo.service_module_id IN (sm_in_sd) OR sm_id IN (sm_ids) OR
    #          sd_id IN (sd_ids) OR bo.id IN (bo_ids)
    parts = []
    params = []
    if all_d_ids:
        ph = ','.join('?' * len(all_d_ids))
        parts.append(f"sm.sub_domain_id IN (SELECT id FROM sub_domains WHERE domain_id IN ({ph}))")
        params.extend(all_d_ids)
    if all_sd_ids:
        ph = ','.join('?' * len(all_sd_ids))
        parts.append(f"sm.sub_domain_id IN ({ph})")
        params.extend(all_sd_ids)
    if all_sm_ids:
        ph = ','.join('?' * len(all_sm_ids))
        parts.append(f"bo.service_module_id IN ({ph})")
        params.extend(all_sm_ids)
    if all_bo_ids:
        ph = ','.join('?' * len(all_bo_ids))
        parts.append(f"bo.id IN ({ph})")
        params.extend(all_bo_ids)

    if not parts:
        return []

    try:
        cursor = ds.execute(
            f"""SELECT DISTINCT bo.id FROM business_objects bo
                LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
                WHERE {' OR '.join(parts)}""",
            params
        )
        bo_ids = [row[0] for row in cursor.fetchall()]
        logger.info(
            f"[_derive_bo_ids_from_dim_scope] user={user_id} roles={user_role_ids} "
            f"d={len(all_d_ids)} sd={len(all_sd_ids)} sm={len(all_sm_ids)} "
            f"bo_direct={len(all_bo_ids)} → derived_bo={len(bo_ids)}"
        )
        return bo_ids
    except Exception as e:
        logger.warning(f"[_derive_bo_ids_from_dim_scope] SQL query failed: {e}")
        return []


def _build_relationship_scope_sort_sql(rules, sort_by: str) -> str:
    """将 hierarchy_scopes 规则转换为 relationship 可直接使用的 ORDER BY CASE WHEN.

    关系表本身没有 domain_id / sub_domain_id / service_module_id 列,
    需用内联子查询从 business_objects → service_modules → sub_domains 派生.

    Args:
        rules: hierarchy_scopes 规则列表, 每条含 rule, id, name
        sort_by: 'category_label' (按 name 排序) 或 'category_type' (按 sort_order 排序)

    Returns:
        SQL CASE 表达式, 可直接嵌入 ORDER BY (...)
    """
    src_d = _relationship_source_domain_id()
    tgt_d = _relationship_target_domain_id()
    src_sd = _relationship_source_sub_domain_id()
    tgt_sd = _relationship_target_sub_domain_id()
    src_sm = _relationship_source_service_module_id()
    tgt_sm = _relationship_target_service_module_id()

    cases = []
    for idx, rule in enumerate(rules, 1):
        rule_expr = rule.get('rule', '').strip()
        if not rule_expr:
            continue

        # 解析 rule 表达式: source.domain_id / target.sub_domain_id / source.service_module_id
        # == 替换为 = (与 _transform_rule_to_sql 行为一致)
        sql_rule = rule_expr
        sql_rule = sql_rule.replace('source.domain_id', src_d)
        sql_rule = sql_rule.replace('target.domain_id', tgt_d)
        sql_rule = sql_rule.replace('source.sub_domain_id', src_sd)
        sql_rule = sql_rule.replace('target.sub_domain_id', tgt_sd)
        sql_rule = sql_rule.replace('source.service_module_id', src_sm)
        sql_rule = sql_rule.replace('target.service_module_id', tgt_sm)
        sql_rule = sql_rule.replace('==', '=')

        # [FIX 2026-06-11] SQL 排序统一用 idx (sort_order), 不嵌入中文字符串.
        # 否则 category_label 走 Chinese collation (同 < 跨) 破坏 sort_order.
        # category_label 字段值在 compute_by_semantics enrichment 阶段再填充, 顺序由 SQL 保证.
        cases.append(f"WHEN ({sql_rule}) THEN {idx}")

    return f"CASE {' '.join(cases)} ELSE 999 END"


def _compute_relation_stats(ds, version_id, where_clause, params):
    stats = {
        'total': 0,
        'by_category': {},
        'by_type': {},
    }
    try:
        type_sql = f"""
            SELECT r.relation_code, COUNT(*) as cnt
            FROM relationships r
            WHERE {where_clause}
            GROUP BY r.relation_code
        """
        cursor = ds.execute(type_sql, tuple(params))
        for row in cursor.fetchall():
            key = row[0] if row[0] is not None else '(未分类)'
            stats['by_type'][key] = row[1]
            stats['total'] += row[1]
    except Exception:
        pass
    return stats


@special_bp.route('/relationships', methods=['GET', 'POST'])
@login_required
def list_relationships():
    if _data_source is None:
        init_special_services()
    ds = _data_source

    user = get_current_user()
    user_id = user.get('user_id') if user else None
    user_is_admin = is_admin() if user else False

    try:
        return _list_relationships_impl(ds, user, user_id, user_is_admin)
    except Exception as e:
        logger.error(
            "[relationships] Unhandled error in list_relationships: %s\n%s",
            str(e), traceback.format_exc()
        )
        return jsonify({
            'success': False,
            'message': str(e),
            'data': [],
            'total': 0,
            'page': 1,
            'page_size': 20,
            'stats': {},
        }), 200


def _list_relationships_impl(ds, user, user_id, user_is_admin):
    # [FIX v1.0.4 2026-06-09] dimension scope 用户 (无 data_permissions 旧表配置) 兼容
    #   原 bug: TEST60 用 dimension_scope 替代 data_permissions, perm_service 返回空列表
    #           → L200-207 `1=0` 强制条件 → 0 条
    #   修复:    1) dimension scope 用户 → allowed_bo_ids = None (跳过 bo_id 过滤)
    #           2) 让 version_id / scope 自身控制可见性 (与 v2 端点行为一致)
    #
    # [FIX v1.1.14 2026-06-15] v1 关系范围树 dim scope 派生 (OR 语义)
    #   之前: dimension scope 用户 has_data_perms=False → allowed_bo_ids=None
    #         → 跳过 bo_id 过滤 → 返回全部 32 条 (v764 全部关系)
    #         与 v2 /api/v2/bo/relationship (走 DataPermissionInterceptor OR-of-AND) 行为不一致
    #   修复: dimension scope 用户调 DimensionScopeEngine 派生 bo 范围
    #         拼成 source/target OR 子查询 (跟 V1.1.9 修复一致)
    #   注: v1 与 v2 现在都走相同的 OR-of-AND 派生路径, TEST333 (5434+5970) 在两端都返回 4 条
    allowed_bo_ids = None
    dim_scope_conds = []  # 各 role 派生的 relationship cond_expr 列表
    if AUTH_ENABLED and user_id and not user_is_admin:
        try:
            bo_ids = _data_perm_filter.perm_service.get_allowed_resource_ids(user_id, 'business_object')
            # [FIX v3.18.1 2026-06-09] 检查用户是否有 business_object 类型的 data_permissions 配置
            from meta.services.data_permission_service import DataPermissionService
            dps = DataPermissionService(ds)
            bo_data_perms = [
                dp for dp in dps.get_user_data_permissions(user_id)
                if dp.get('resource_type') == 'business_object'
            ]
            has_data_perms = bool(bo_data_perms)
            if has_data_perms and bo_ids:
                allowed_bo_ids = bo_ids
            elif has_data_perms and not bo_ids:
                # 有 business_object data_perms 但 bo_ids 为空 → 显式拒绝
                allowed_bo_ids = []
            else:
                # [V1.1.14] dim scope 用户, 调 DimensionScopeEngine 派生 'business_object' cond
                # 跟 v2 /api/v2/bo/relationship (走 DataPermissionInterceptor) 行为对齐
                # 语义: 任一 role 派生命中 → 允许 (OR-of-AND per role)
                from meta.services.dimension_scope_engine import DimensionScopeEngine
                ds_engine = DimensionScopeEngine(ds)
                cursor = ds.execute(
                    """SELECT DISTINCT gr.role_id
                       FROM group_roles gr
                       JOIN user_group_members ugm ON gr.group_id = ugm.group_id
                       WHERE ugm.user_id = ?""",
                    [user_id]
                )
                user_role_ids = [row[0] for row in cursor.fetchall()]
                for role_id in user_role_ids:
                    data_conds = ds_engine.derive_data_conditions(role_id)
                    rel_cond = data_conds.get('relationship')
                    if rel_cond:
                        dim_scope_conds.append(rel_cond)
        except Exception as e:
            logger.warning(f"[relationships] dim scope calc failed: {e}")
            dim_scope_conds = []
    if request.method == 'POST':
        data = request.get_json() or {}
        page = data.get('page', 1)
        page_size = int(data.get('pageSize', data.get('page_size', 20)))
        version_id = data.get('version_id')
        business_objects = data.get('business_objects', [])
        business_object_ids = data.get('business_object_id', [])
        # [FIX 2026-06-10] 兼容 YAML ui_view_config.filter.filters[].key
        #   YAML 用单数 category_type, 后端传统用复数 category_types
        #   同时支持 ['a', 'b'] (数组) 与 "a,b" (字符串)
        category_types_raw = data.get('category_types', [])
        if not category_types_raw:
            cat_single = data.get('category_type')
            category_types = [cat_single] if cat_single else []
        else:
            if isinstance(category_types_raw, str):
                category_types = [v.strip() for v in category_types_raw.split(',') if v.strip()]
            else:
                category_types = list(category_types_raw)
        relation_codes = data.get('relation_codes', [])
        relation_ids = data.get('id__in', data.get('relation_ids', []))
        domain_ids = data.get('domain_id', [])
        sub_domain_ids = data.get('sub_domain_id', [])
        service_module_ids = data.get('service_module_id', [])
        keyword = (data.get('keyword') or '').strip()
        scope_mode = data.get('scope_mode', 'involved')
        sort_by = data.get('sort_by', 'created_at')
        sort_order = data.get('sort_order', 'desc')
        annotation_category = data.get('annotation_category')
        annotation_content_search = data.get('annotation_content_search')
    else:
        page = request.args.get('page', 1, type=int)
        page_size = int(request.args.get('pageSize', request.args.get('page_size', 20)))
        version_id = request.args.get('version_id', type=int)
        business_objects = request.args.getlist('business_objects', type=int)
        business_object_ids = request.args.getlist('business_object_id', type=int)
        # [FIX 2026-06-10] 兼容 category_type (单数, YAML 规范) 和 category_types (复数, 传统)
        #   同时支持 ?category_types=a,b (单值逗号分隔) 与 ?category_types=a&category_types=b (多值)
        #   [FIX 2026-06-10] 前端列头过滤用 category_label (column prop 名), 后端兼容之
        category_types = request.args.getlist('category_types')
        if not category_types:
            cat_single = request.args.get('category_type')
            category_types = [cat_single] if cat_single else []
        else:
            # 拆分单值内的逗号分隔: ?category_types=a,b → ['a', 'b']
            category_types = [
                v.strip() for raw in category_types
                for v in raw.split(',') if v and v.strip()
            ]
        # [FIX 2026-06-10] 兼容 category_label 参数 (前端列头过滤的 prop 名)
        if not category_types:
            cat_label = request.args.get('category_label')
            if cat_label:
                category_types = [v.strip() for v in cat_label.split(',') if v.strip()]
        if not category_types:
            cat_label_in = request.args.get('category_label__in', '')
            if cat_label_in:
                category_types = [v.strip() for v in cat_label_in.split(',') if v.strip()]
        relation_codes = request.args.getlist('relation_codes')
        relation_ids_str = request.args.get('id__in', '')
        relation_ids = [int(x) for x in relation_ids_str.split(',') if x.strip().isdigit()] if relation_ids_str else []
        domain_ids = request.args.getlist('domain_id', type=int)
        sub_domain_ids = request.args.getlist('sub_domain_id', type=int)
        service_module_ids = request.args.getlist('service_module_id', type=int)
        keyword = request.args.get('keyword', '').strip()
        scope_mode = request.args.get('scope_mode', 'involved')
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        annotation_category = request.args.get('annotation_category')
        annotation_content_search = request.args.get('annotation_content_search')

    valid_sort_fields = {
        'source_code': 'r.source_code',
        'target_code': 'r.target_code',
        'relation_code': 'r.relation_code',
        'created_at': 'r.created_at',
    }

    if sort_by in ('category_label', 'category_type'):
        # [FIX 2026-06-10] 用内联子查询生成 sort CASE WHEN, 避免依赖 d1/d2/sd1/sd2/sm1/sm2 等 JOIN 别名
        # 与下方 category_types 过滤逻辑保持一致, 不需要额外的 LEFT JOIN
        from meta.core.virtual_field_transform import load_scope_rules_from_ref
        rules = load_scope_rules_from_ref('hierarchies.hierarchy_scopes')
        if rules:
            scope_sql = _build_relationship_scope_sort_sql(rules, sort_by)
            order_field = scope_sql
        else:
            order_field = 'r.created_at'
    else:
        order_field = valid_sort_fields.get(sort_by, 'r.created_at')

    order_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

    if sort_by in ('category_label', 'category_type'):
        order_clause = f"({order_field}) {order_direction}"
    else:
        order_clause = f"{order_field} {order_direction}"

    conditions = []
    params = []

    if version_id:
        conditions.append("r.version_id = ?")
        params.append(version_id)

    if relation_codes:
        placeholders = ','.join(['?'] * len(relation_codes))
        conditions.append(f"r.relation_code IN ({placeholders})")
        params.extend(relation_codes)

    # [FIX] 支持按关系 ID 精确过滤（id__in），避免 relation_code 不唯一导致多余记录
    if relation_ids:
        placeholders = ','.join(['?'] * len(relation_ids))
        conditions.append(f"r.id IN ({placeholders})")
        params.extend(relation_ids)

    bo_ids_from_hierarchy = []
    if business_object_ids:
        bo_ids_from_hierarchy = business_object_ids
    elif business_objects:
        bo_ids_from_hierarchy = business_objects
    elif service_module_ids:
        bo_ids_from_hierarchy = _hierarchy_filter_service.get_bo_ids_by_service_module_ids(service_module_ids)
    elif sub_domain_ids:
        bo_ids_from_hierarchy = _hierarchy_filter_service.get_bo_ids_by_sub_domain_ids(sub_domain_ids)
    elif domain_ids:
        bo_ids_from_hierarchy = _hierarchy_filter_service.get_bo_ids_by_domain_ids(domain_ids, version_id)

    if bo_ids_from_hierarchy:
        placeholders = ','.join(['?'] * len(bo_ids_from_hierarchy))
        if scope_mode == 'internal':
            conditions.append(f"(r.source_bo_id IN ({placeholders}) AND r.target_bo_id IN ({placeholders}))")
            params.extend(bo_ids_from_hierarchy)
            params.extend(bo_ids_from_hierarchy)
        else:
            conditions.append(f"(r.source_bo_id IN ({placeholders}) OR r.target_bo_id IN ({placeholders}))")
            params.extend(bo_ids_from_hierarchy)
            params.extend(bo_ids_from_hierarchy)
    elif domain_ids or sub_domain_ids or service_module_ids or business_object_ids:
        conditions.append("1=0")

    if allowed_bo_ids is not None:
        if not allowed_bo_ids:
            conditions.append("1=0")
        else:
            placeholders = ','.join(['?'] * len(allowed_bo_ids))
            conditions.append(f"(r.source_bo_id IN ({placeholders}) OR r.target_bo_id IN ({placeholders}))")
            params.extend(allowed_bo_ids)
            params.extend(allowed_bo_ids)
    # [V1.1.9] dim scope 派生 cond: 多 role → OR-of-AND (单 role → 直接)
    #   跟 v2 /api/v2/bo/relationship 行为一致
    if dim_scope_conds:
        if len(dim_scope_conds) == 1:
            conditions.append(dim_scope_conds[0])
        else:
            conditions.append('(' + ') OR ('.join(dim_scope_conds) + ')')
    if keyword:
        conditions.append("""(
            r.relation_code LIKE ? OR
            EXISTS (SELECT 1 FROM business_objects WHERE id = r.source_bo_id AND (name LIKE ? OR code LIKE ?)) OR
            EXISTS (SELECT 1 FROM business_objects WHERE id = r.target_bo_id AND (name LIKE ? OR code LIKE ?))
        )""")
        keyword_param = f'%{keyword}%'
        params.extend([keyword_param, keyword_param, keyword_param, keyword_param, keyword_param])

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    cross_table_conditions = []
    if annotation_category:
        if isinstance(annotation_category, str):
            categories = [c.strip() for c in annotation_category.split(',') if c.strip()]
        elif isinstance(annotation_category, list):
            categories = annotation_category
        else:
            categories = []

        if categories:
            placeholders = ','.join(['?' for _ in categories])
            cross_table_conditions.append(f"""
                EXISTS (
                    SELECT 1 FROM annotations a
                    WHERE r.id = a.target_id
                    AND a.target_type = 'relationship'
                    AND a.category IN ({placeholders})
                )
            """)
            params.extend(categories)

    if annotation_content_search:
        cross_table_conditions.append(f"""
            EXISTS (
                SELECT 1 FROM annotations a
                WHERE r.id = a.target_id
                AND a.target_type = 'relationship'
                AND a.content LIKE ?
            )
        """)
        params.append(f'%{annotation_content_search}%')

    if cross_table_conditions:
        where_clause += " AND (" + " AND ".join(cross_table_conditions) + ")"

    category_conditions = []
    if category_types:
        src_sm = "(SELECT service_module_id FROM business_objects WHERE id = r.source_bo_id)"
        tgt_sm = "(SELECT service_module_id FROM business_objects WHERE id = r.target_bo_id)"
        src_sd = "(SELECT sub_domain_id FROM service_modules WHERE id = {src_sm})".format(src_sm=src_sm)
        tgt_sd = "(SELECT sub_domain_id FROM service_modules WHERE id = {tgt_sm})".format(tgt_sm=tgt_sm)
        src_d = "(SELECT domain_id FROM sub_domains WHERE id = {src_sd})".format(src_sd=src_sd)
        tgt_d = "(SELECT domain_id FROM sub_domains WHERE id = {tgt_sd})".format(tgt_sd=tgt_sd)
        for ct in category_types:
            if ct == 'cross_domain':
                category_conditions.append(f"{src_d} != {tgt_d}")
            elif ct == 'same_domain_cross_subdomain':
                category_conditions.append(f"{src_d} = {tgt_d} AND {src_sd} != {tgt_sd}")
            elif ct == 'same_subdomain_cross_module':
                category_conditions.append(f"{src_sd} = {tgt_sd} AND {src_sm} != {tgt_sm}")
            elif ct == 'same_module':
                category_conditions.append(f"{src_sm} = {tgt_sm}")

        if category_conditions:
            where_clause += " AND (" + " OR ".join(category_conditions) + ")"

    count_sql = f"""
        SELECT COUNT(*) as total
        FROM relationships r
        WHERE {where_clause}
    """
    cursor = ds.execute(count_sql, tuple(params))
    total = cursor.fetchone()[0]

    offset = (page - 1) * page_size

    data_sql = f"""
        SELECT r.*
        FROM relationships r
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    data_params = list(params) + [page_size, offset]
    cursor = ds.execute(data_sql, tuple(data_params))
    columns = [desc[0] for desc in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]

    try:
        data = enrich_records('relationship', data)
    except Exception as enrich_error:
        logger.warning(
            "[relationships] enrich_records failed for %d records: %s\n%s",
            len(data), str(enrich_error), traceback.format_exc()
        )

    for item in data:
        try:
            computed_label, computed_type = _compute_category(item)
            item['category_label'] = computed_label
            item['category_type'] = computed_type
        except Exception as cat_error:
            logger.warning(
                "[relationships] _compute_category failed for relation id=%s: %s",
                item.get('id', '?'), str(cat_error)
            )
            item['category_label'] = '同服务模块'
            item['category_type'] = 'same_module'

        if allowed_bo_ids is not None:
            source_visible = item.get('source_bo_id') in allowed_bo_ids
            target_visible = item.get('target_bo_id') in allowed_bo_ids
            item['source_visible'] = source_visible
            item['target_visible'] = target_visible

    stats = _compute_relation_stats(ds, version_id, where_clause, params)

    return jsonify({
        'success': True,
        'data': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'stats': stats,
    })


@special_bp.route('/business_object/<int:obj_id>/relations', methods=['GET'])
@login_required
def get_business_object_relations(obj_id):
    if _data_source is None:
        init_special_services()
    ds = _data_source

    display_mode = request.args.get('display_mode', 'all')

    source_sql = """
        SELECT r.*
        FROM relationships r
        WHERE r.source_bo_id = ?
        ORDER BY r.relation_code, r.created_at DESC
    """
    target_sql = """
        SELECT r.*
        FROM relationships r
        WHERE r.target_bo_id = ?
        ORDER BY r.relation_code, r.created_at DESC
    """

    source_relations = []
    target_relations = []

    if display_mode in ('all', 'source_only'):
        cursor = ds.execute(source_sql, (obj_id,))
        columns = [desc[0] for desc in cursor.description]
        source_relations = [dict(zip(columns, row)) for row in cursor.fetchall()]
        source_relations = enrich_records('relationship', source_relations)
        for item in source_relations:
            item['category_label'] = _compute_category(item)[0]

    if display_mode in ('all', 'target_only'):
        cursor = ds.execute(target_sql, (obj_id,))
        columns = [desc[0] for desc in cursor.description]
        target_relations = [dict(zip(columns, row)) for row in cursor.fetchall()]
        target_relations = enrich_records('relationship', target_relations)
        for item in target_relations:
            item['category_label'] = _compute_category(item)[0]

    stats = {
        'total': len(source_relations) + len(target_relations),
        'source_count': len(source_relations),
        'target_count': len(target_relations),
    }

    return jsonify({
        'success': True,
        'data': {
            'source_relations': source_relations,
            'target_relations': target_relations,
            'stats': stats,
        },
    })


@special_bp.route('/analytics/<object_type>', methods=['POST'])
@login_required
def analytics_query(object_type):
    if _data_source is None:
        init_special_services()
    ds = _data_source

    from meta.core.models import registry
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404

    body = request.get_json(silent=True) or {}

    dimensions = body.get('dimensions', [])
    measures = body.get('measures', [])
    filters = body.get('filters', [])
    order_by = body.get('orderBy', [])
    limit = body.get('limit', 0)

    if not dimensions and not measures:
        return jsonify({'success': False, 'message': 'At least one dimension or measure is required'}), 400

    try:
        from meta.core.analytics_query_builder import AnalyticsQueryBuilder

        builder = AnalyticsQueryBuilder(ds, meta_obj)

        for dim in dimensions:
            if isinstance(dim, str):
                builder.dimension(dim)
            elif isinstance(dim, dict):
                builder.dimension(dim.get('field'), dim.get('alias'))

        for measure in measures:
            if isinstance(measure, dict):
                builder.measure(
                    measure.get('field'),
                    measure.get('aggregation', 'COUNT'),
                    measure.get('alias')
                )

        for f in filters:
            if isinstance(f, dict):
                builder.filter(f.get('field'), f.get('operator', 'eq'), f.get('value'))

        for order in order_by:
            if isinstance(order, dict):
                builder.order_by(order.get('field'), order.get('direction', 'asc'))

        if limit > 0:
            builder.limit(limit)

        results = builder.execute()

        return jsonify({
            'success': True,
            'data': results,
            'total': len(results),
        })
    except Exception as e:
        logger.error(f"[Analytics] Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
