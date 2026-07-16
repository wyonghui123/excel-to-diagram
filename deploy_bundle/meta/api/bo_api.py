# -*- coding: utf-8 -*-
import logging
import os
from flask import Blueprint, request, jsonify, g

# 用户输入 page_size 的上限（防止 DoS 攻击）
# 注：内部硬编码调用（如预览端点 page_size=5000）不受此限制
MAX_USER_PAGE_SIZE = 500

from meta.core.bo_framework import bo_framework
from meta.core.models import registry
from meta.services.auth_middleware import login_required, get_current_user
from meta.services.field_policy_engine import FieldPolicyEngine, PolicyContext, ObjectContext
from meta.services.view_config_service import view_config_service
from meta.services.computation_service import computation_service
from meta.api._audit_helper import write_permission_config_audit

logger = logging.getLogger(__name__)

bo_bp = Blueprint('bo_v2', __name__, url_prefix='/api/v2/bo')
meta_v2_bp = Blueprint('meta_v2', __name__, url_prefix='/api/v2/meta')


def _enrich_audit_log_items(items):
    """[FIX 2026-06-12] audit_log 列表通用 enrich.
    1. 把 extra_data 字符串解析为 extra_data_parsed (前端 deleted-data-section 用)
    2. 注入 object_type_label / field_name_label / parent_object_type_label (中英文映射)

    跟 v1 /audit/logs 接口对齐, 解决"v2 BO 列表看不到删除明细 JSON"问题.
    复用 meta.api.audit_api 的 OBJECT_TYPE_LABELS / FIELD_NAME_LABELS 映射.
    """
    if not items:
        return
    try:
        from meta.api.audit_api import (
            OBJECT_TYPE_LABELS,
            FIELD_NAME_LABELS,
            _extract_deleted_data,
        )
    except Exception as e:
        logger.warning(f"[audit_log enrich] import failed: {e}")
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        # 1) extra_data 解析
        ed_raw = item.get('extra_data')
        if ed_raw and not item.get('extra_data_parsed'):
            item['extra_data_parsed'] = _extract_deleted_data(ed_raw)
        # 2) label 注入
        ot = item.get('object_type', '') or ''
        fn = item.get('field_name', '') or ''
        pot = item.get('parent_object_type', '') or ''
        if ot and not item.get('object_type_label'):
            item['object_type_label'] = OBJECT_TYPE_LABELS.get(ot, ot)
        if fn and not item.get('field_name_label'):
            item['field_name_label'] = FIELD_NAME_LABELS.get(fn, fn)
        if pot and not item.get('parent_object_type_label'):
            item['parent_object_type_label'] = OBJECT_TYPE_LABELS.get(pot, pot)


def _set_user_context():
    try:
        current_user = get_current_user()
        if current_user:
            bo_framework.set_user_context(
                user_id=current_user.get('user_id') or current_user.get('id'),
                user_name=current_user.get('username') or current_user.get('display_name'),
                ip_address=request.remote_addr,
            )
    except Exception:
        pass


def _get_bo():
    _set_user_context()
    return bo_framework


_data_source = None


# 关联查询保留参数（这些 key 不应该作为过滤条件透传）
_ASSOC_RESERVED_KEYS = {
    'page', 'page_size', 'pageSize', 'ordering', 'search', 'keyword',
    '_order_by', '_limit', '_offset',
}


def _extract_assoc_query_params(args):
    """从 request.args 中提取关联查询的过滤/排序/搜索参数。

    返回 (filters, ordering, search)：
    - filters: dict，key 为字段名（含 __in/__like/__gte/__lte/_start/_end 后缀），
               value 为标量或字符串
    - ordering: 字符串（可能为 '-field' 形式），空字符串表示未指定
    - search: 搜索关键词字符串
    """
    filters = {}
    ordering = ''
    search = ''

    ordering_raw = args.get('ordering') or args.get('_order_by') or ''
    if isinstance(ordering_raw, str):
        ordering = ordering_raw.strip()

    for raw in (args.get('search'), args.get('keyword')):
        if raw and not search:
            search = str(raw).strip()

    for key, value in args.items():
        if key in _ASSOC_RESERVED_KEYS:
            continue
        if key.startswith('filters[') or key == 'filters':
            # 形如 filters[name]=value 或 filters[name][in]=v — 不在 SQL 层解析
            continue
        if value is None or value == '':
            continue
        filters[key] = value

    return filters, ordering, search


def _get_data_source():
    global _data_source
    if _data_source is None:
        from meta.core.datasource import get_data_source
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


# ── [R0-2 2026-06-11] 422 ComputationNotSupportedError 统一拦截 ──
from meta.core.computed_field_query import ComputationNotSupportedError


@bo_bp.errorhandler(ComputationNotSupportedError)
def handle_computation_not_supported(e: ComputationNotSupportedError):
    """计算字段不被支持 → 422 + 明确错误码, 不再 silent fallback

    [决策5] 422 Unprocessable Entity 语义最准:
    请求格式正确, 但服务器无法处理 (computation.type 配错了对象类型)
    """
    logger.warning(
        f"[bo_api] ComputationNotSupported: comp_type={e.comp_type} "
        f"object_type={e.object_type} scope={e.scope}"
    )
    return jsonify({
        'success': False,
        'error_code': 'COMPUTATION_NOT_SUPPORTED',
        'message': str(e),
        'details': {
            'comp_type': e.comp_type,
            'object_type': e.object_type,
            'scope': e.scope,
        }
    }), 422


# ── CRUD ──

@bo_bp.route('/<object_type>', methods=['POST'])
@login_required
def create_bo(object_type):
    logger.info(f"[bo_api] create_bo START: object_type={object_type}")
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    try:
        result = bo.create(object_type, data)
        logger.info(f"[bo_api] result: success={result.success}, message={result.message}")
        status_code = 201 if result.success else (result.status_code or 400)

        if result.success and result.data and result.data.get('id'):
            try:
                from meta.services.data_permission_generator import DataPermissionGenerator
                from meta.api.user_api import get_current_user
                from meta.core.models import registry
                meta_obj = registry.get(object_type)
                if meta_obj:
                    user = get_current_user()
                    if user and user.get('user_id'):
                        ds = _get_data_source()
                        gen = DataPermissionGenerator(ds)
                        count = gen.generate_on_create(
                            meta_obj,
                            result.data['id'],
                            user['user_id']
                        )
                        if count > 0:
                            logger.info(f"[bo_api] auto_granted {count} data_permissions for user={user['user_id']} on {object_type}:{result.data['id']}")
            except Exception as e:
                logger.warning(f"[bo_api] auto_grant failed (non-fatal): {e}")

        return jsonify({'success': result.success, 'data': result.data, 'message': result.message}), status_code
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] create error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@meta_v2_bp.route('/schema-version', methods=['GET'])
def get_schema_version():
    import hashlib
    from datetime import datetime

    schema_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
    hasher = hashlib.md5()

    try:
        for filename in sorted(os.listdir(schema_dir)):
            if filename.endswith('.yaml') and not filename.startswith('_'):
                filepath = os.path.join(schema_dir, filename)
                with open(filepath, 'rb') as f:
                    hasher.update(f.read())
    except Exception as e:
        logger.warning(f"[schema-version] failed to hash schemas: {e}")
        hasher.update(str(datetime.now().date()).encode())

    return jsonify({
        'success': True,
        'data': {
            'schema_version': hasher.hexdigest()[:12],
            'timestamp': datetime.now().isoformat()
        }
    })


def _attach_change_history(record: dict, object_type: str, obj_id) -> None:
    """[FIX 2026-06-09] 为 v2 BO 读取响应附加 change_history (含子对象/关联操作)

    与 v1 manage_api.get_record 行为一致, 使用 include_children=True 以包含:
    - 子对象 (parent_object_type=object_type) 的 CRUD 日志
    - ASSOCIATE/DISSOCIATE/ASSIGN/REVOKE 关联操作日志
    """
    if not record:
        return
    try:
        from meta.services.audit_service import AuditService
        audit_service = AuditService(_get_data_source())
        record['change_history'] = audit_service.get_object_history(
            object_type, obj_id, include_children=True
        )
    except Exception as e:
        logger.debug(f"[bo_api] change_history attach failed for {object_type}/{obj_id}: {e}")
        record['change_history'] = []


@bo_bp.route('/<object_type>/<int:obj_id>', methods=['GET'])
@login_required
def read_bo(object_type, obj_id):
    # [FIX 2026-06-12] audit_log 是只读对象 (persistent: false), BO framework 拒绝读 (404).
    # v2 BO 接口必须跟 v1 /audit/logs/{id} 对齐, 否则前端拿不到 extra_data_parsed.deleted_data.
    # 这里直接走 v1 端点拿到完整数据 + 注入中文 label.
    if object_type == 'audit_log':
        return _read_audit_log_via_v1(obj_id)

    # [FIX v1.1.10 2026-06-15] 单条 get 应用 dim scope (跟 list 一致)
    # 原 bug: DataPermissionInterceptor 派生的 query_conditions 是 list 用的,
    #         单条 crud_read 走 `WHERE id = ?` 直接查, 拦截器条件不生效
    #         → TEST333 能 GET 任意 BO 单条 (含域外), 拿到完整 description / change_history
    #         → 安全漏洞 (绕过 dim scope)
    # 修复: read_bo API 层加 dim scope 校验, 不在范围内 → 404 (不暴露存在性)
    # 注意: 关系 list 接口"上下文读取" (target_bo_name 等元数据) 走的是关系接口自
    #       己 SQL, 不走 BO 单条 get, 不受此限制 (符合 SAP 风格字段级授权)
    _deny = _check_single_bo_in_dim_scope(object_type, obj_id)
    if _deny:
        return jsonify({'success': False, 'message': '对象不存在或无访问权限'}), 404

    bo = _get_bo()
    result = bo.read(object_type, obj_id)
    if result.success:
        _attach_change_history(result.data, object_type, obj_id)
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), 404


def _check_single_bo_in_dim_scope(object_type: str, obj_id: int):
    """[V1.1.10 2026-06-15] 单条 BO get 应用 dim scope 校验

    语义: 调用 DimensionScopeEngine.derive_data_conditions(role_id) 派生当前 object_type 的 cond_expr,
          检查 obj_id 是否在派生范围内. 不在 → 返回 True (deny).

    [FIX 2026-06-17] owner 例外: 用户对自己 owner 的资源始终可见 (跟 _do_list 路径一致)
      - 拿 obj_id 对应 record 的 owner_id, 等于 user.id → allow
      - 这与 DataPermissionInterceptor._add_owner_exception 行为一致
      - 修复: TEST333 创建 product 493 (owner=TEST333) 后能直接看 detail
              之前 dim scope 派生条件不含 owner, TEST333 不是 product 派生范围 → 404

    例: TEST333 + 5970 读域外 BO 316:
      - 5970 dim scope: domain=[703] → 派生 BO cond: `id IN (chain 派生 → 8 个 BO)`
      - 316 不在 8 个内 → deny → 404

    Returns:
        True = 应拒绝, False = 允许
    """
    try:
        from flask import g
        user = getattr(g, 'current_user', None) or _get_current_user_safe()
        if not user:
            return False  # 无 user 上下文, 让其他拦截器处理
        # admin 跳过
        from meta.services.auth_middleware import is_admin
        if is_admin(user):
            return False
        # audit_log 等元数据对象不受 dim scope 限制
        if object_type in ('audit_log',):
            return False

        user_id = user.get('id') or user.get('user_id')
        ds = _get_data_source()

        # [FIX 2026-06-17] owner 例外: 用户对 owner=自己 的资源始终可见
        # 优先级最高, 先检查 (避免不必要的 dim scope 派生)
        meta_obj = registry.get(object_type)
        if meta_obj is not None and user_id:
            try:
                # 检查 BO 是否有 owner_id 字段
                has_owner_id = any(
                    getattr(f, 'id', getattr(f, 'name', '')) == 'owner_id'
                    for f in (getattr(meta_obj, 'fields', None) or [])
                )
                if has_owner_id:
                    table = meta_obj.table_name
                    owner_row = ds.execute(
                        f"SELECT 1 FROM {table} WHERE id = ? AND owner_id = ? LIMIT 1",
                        [obj_id, user_id]
                    ).fetchone()
                    if owner_row:
                        logger.info(
                            f'[_check_single_bo_in_dim_scope] ALLOW via owner_exception '
                            f'object_type={object_type} obj_id={obj_id} user={user_id}'
                        )
                        return False  # owner 例外放行
            except Exception as e:
                logger.debug(f'[_check_single_bo_in_dim_scope] owner check failed: {e}')

        # 拿 user 的所有 role_id
        cursor = ds.execute(
            """SELECT DISTINCT gr.role_id
               FROM group_roles gr
               JOIN user_group_members ugm ON gr.group_id = ugm.group_id
               WHERE ugm.user_id = ?""",
            [user_id]
        )
        role_ids = [row[0] for row in cursor.fetchall()]
        if not role_ids:
            return False

        # 多 role 任一允许 → 放行 (OR 语义)
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        engine = DimensionScopeEngine(ds)
        for role_id in role_ids:
            data_conds = engine.derive_data_conditions(role_id)
            cond_expr = data_conds.get(object_type)
            if not cond_expr:
                continue  # 该 role 无 dim scope 派生
            # 用 cond_expr 跑单条 id 校验
            # 把 cond_expr 的 "id IN (...)" 改为 "id = ?", 或者直接在子查询里加 WHERE id=?
            # 简化: 用一个独立 SQL — 派生 "id" 字段 chain, 把 obj_id 加进去
            # 解析 cond_expr, 找 chain 的 leaf
            if not meta_obj:
                continue
            table = meta_obj.table_name
            sql = f"SELECT 1 FROM {table} WHERE id = ? AND ({cond_expr}) LIMIT 1"
            row = ds.execute(sql, [obj_id]).fetchone()
            if row:
                return False  # 在 dim scope 内 → 允许
        # 所有 role 都没匹配 → deny
        logger.info(
            f'[_check_single_bo_in_dim_scope] DENY object_type={object_type} obj_id={obj_id} '
            f'user={user.get("id")} roles={role_ids}'
        )
        return True
    except Exception as e:
        logger.warning(f'[_check_single_bo_in_dim_scope] check failed, ALLOW (fail-open): {e}')
        return False  # 校验失败 → 放行 (避免误杀)


def _get_current_user_safe():
    try:
        from flask import g
        return g.get('current_user') if hasattr(g, 'current_user') else None
    except Exception:
        return None


def _read_audit_log_via_v1(obj_id):
    """[FIX 2026-06-12] audit_log 单条: 走 v1 /audit/logs/{id} (已有 extra_data_parsed)
    再 enrich 中英文 label, 跟 v2 BO 列表接口行为一致.
    """
    try:
        from meta.api.audit_api import _extract_deleted_data
        ds = _get_data_source()
        cursor = ds.execute("""
            SELECT id, object_type, object_id, action, field_name, old_value, new_value,
                   user_id, user_name, ip_address, user_agent, created_at, trace_id,
                   transaction_id, status, retry_count, error_message, agent_id,
                   agent_session_id, tool_call_id, agent_reasoning, extra_data
            FROM audit_logs WHERE id = ?
        """, [obj_id])
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'message': '审计日志不存在'}), 404
        columns = [d[0] for d in cursor.description]
        log = dict(zip(columns, row))
        for k, v in list(log.items()):
            if v is None:
                log[k] = ''
        log['extra_data_parsed'] = _extract_deleted_data(log.pop('extra_data', '') or '')

        # 注入中文 label (跟 list 端点对齐)
        try:
            from meta.api.audit_api import OBJECT_TYPE_LABELS, FIELD_NAME_LABELS
            ot = log.get('object_type', '') or ''
            fn = log.get('field_name', '') or ''
            pot = log.get('parent_object_type', '') or ''
            if ot:
                log['object_type_label'] = OBJECT_TYPE_LABELS.get(ot, ot)
            if fn:
                log['field_name_label'] = FIELD_NAME_LABELS.get(fn, fn)
            if pot:
                log['parent_object_type_label'] = OBJECT_TYPE_LABELS.get(pot, pot)
        except Exception:
            pass
        return jsonify({'success': True, 'data': log})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


def _data_source_default():
    """兼容旧调用方 — 直接用 _get_data_source()."""
    return _get_data_source()


@bo_bp.route('/<object_type>/<path:obj_id>', methods=['GET'])
@login_required
def read_bo_by_string_id(object_type, obj_id):
    """支持字符串ID的读取路由"""
    # [FIX 2026-06-12] audit_log 走 v1 路径
    if object_type == 'audit_log':
        return _read_audit_log_via_v1(obj_id)

    bo = _get_bo()
    result = bo.read(object_type, obj_id)
    if result.success:
        _attach_change_history(result.data, object_type, obj_id)
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), 404


@bo_bp.route('/<object_type>', methods=['GET'])
@login_required
def query_bo(object_type):
    bo = _get_bo()
    request_filters = dict(request.args)
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', request.args.get('pageSize', 20)))
    page_size = max(1, min(page_size, MAX_USER_PAGE_SIZE))  # 防止 DoS：限制用户输入
    ordering = request.args.get('ordering', '')

    # 移除分页和排序参数，只保留过滤参数
    clean_filters = {k: v for k, v in request_filters.items()
                     if k not in ('page', 'page_size', 'pageSize', 'ordering', '_limit', '_offset', '_order_by')}

    # 计算offset
    offset = (page - 1) * page_size

    # [FIX 2026-06-10] relationship 对象对 category_label / category_type 排序需要
    # 内联子查询计算层级 scope, 因为 DB 中这 2 列大多为 NULL (enrichment 发生在 SQL 后).
    # 这里直接走 special_routes_api 同款 SQL, 绕过 crud_query 静默忽略未知列的问题.
    scope_order_sql = None
    scope_order_is_desc = False
    if object_type == 'relationship' and ordering:
        bare = ordering.lstrip('-')
        if bare in ('category_label', 'category_type'):
            from meta.api.special_routes_api import _build_relationship_scope_sort_sql
            from meta.core.virtual_field_transform import load_scope_rules_from_ref
            rules = load_scope_rules_from_ref('hierarchies.hierarchy_scopes')
            logger.info(f"[query_bo] relationship sorting: ordering={ordering}, bare={bare}, rules_count={len(rules) if rules else 0}")
            if rules:
                scope_order_sql = _build_relationship_scope_sort_sql(rules, bare)
                scope_order_is_desc = ordering.startswith('-')
                logger.info(f"[query_bo] scope_order_sql={scope_order_sql[:200]}..., is_desc={scope_order_is_desc}")
                return _query_relationship_with_scope(
                    page=page, page_size=page_size, offset=offset,
                    clean_filters=clean_filters,
                    scope_sql=scope_order_sql, is_desc=scope_order_is_desc,
                )
            else:
                logger.warning(f"[query_bo] rules is empty, falling back to crud_query (virtual field sorting may not work)")

    # 构建查询参数，只传递过滤参数
    query_params = clean_filters.copy()
    if ordering:
        query_params['_order_by'] = ordering
    query_params['_limit'] = page_size
    query_params['_offset'] = offset

    logger.info(f"[query_bo] object_type={object_type}, page={page}, page_size={page_size}, ordering={ordering}, offset={offset}")
    logger.info(f"[query_bo] query_params={query_params}")

    # 直接使用crud_query action
    result = bo.execute(object_type, 'crud_query', query_params)

    if not result.success:
        logger.warning("[query_bo] query failed: object_type=%s msg=%s errors=%s",
                       object_type, result.message, result.errors)

    logger.info(f"[query_bo] result.success={result.success}, result.data type={type(result.data)}, len={len(result.data) if hasattr(result.data, '__len__') else 'N/A'}")

    # 转换数据格式以匹配前端期望
    if result.success:
        raw_data = result.data

        # 从 ActionResult 获取 total
        total = getattr(result, 'total', None)
        if total is None:
            # 如果 result.total 不存在，使用 len(raw_data)
            total = len(raw_data) if isinstance(raw_data, list) else 0

        # 获取 filters 数组（从 view-config 中获取）
        filters = []
        try:
            config = view_config_service.get_or_build_view_config(object_type, None)
            if config and hasattr(config, 'list') and config.list:
                filters = config.list.filters if hasattr(config.list, 'filters') else []
        except Exception as e:
            logger.warning(f"[query_bo] Failed to get filters from view-config: {e}")

        # 检查是否是数组格式（来自 _do_list）
        if isinstance(raw_data, list):
            computation_service.compute_by_semantics(object_type, raw_data)
            # [FIX 2026-06-12] audit_log 通用 enrich: 解析 extra_data 为 extra_data_parsed,
            # 注入 object_type_label / field_name_label / parent_object_type_label.
            # 让所有用 v2 BO /audit_log 列表的页面 (系统管理-审计日志管理, 全局搜索等)
            # 都能直接展示"删除对象完整明细" JSON + 中英文标签, 跟 v1 /audit/logs 接口对齐.
            if object_type == 'audit_log':
                _enrich_audit_log_items(raw_data)
            # 返回 { items: [], total: 20, filters: [] } 格式
            return jsonify({
                'success': True,
                'data': {
                    'items': raw_data,
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'filters': filters
                },
                'message': result.message
            })
        else:
            # 已经是正确格式
            if object_type == 'audit_log' and isinstance(result.data, dict) and isinstance(result.data.get('items'), list):
                _enrich_audit_log_items(result.data['items'])
            return jsonify({'success': True, 'data': result.data, 'message': result.message})
    else:
        logger.error(f"[query_bo] Error: {result.message}")
        status_code = result.status_code or 400
        return jsonify({'success': False, 'message': result.message}), status_code


# [SPR-08 T-S14-01] relationship 过滤白名单数据化
# 简易白名单过滤 (前端用 crud_query 行为对齐: 多值字段用 __in, 逗号分隔)
# 注: relation_code 不在这里, 因为它跟 relation_code__in 互斥 (优先级 __in > 精确)
# [CHANGED 2026-06-13] 移除 version_code - relationships 表无此列, 使用 version_id 过滤
_RELATIONSHIP_SIMPLE_EQ_FIELDS = ('version_id', 'product_code')
_RELATIONSHIP_IN_FIELD_KEYS = ('category_types__in', 'category_type__in', 'category_types', 'category_type')  # 复用同一 SQL 字段 category_type
# [FIX 2026-06-15] 增加 relation_type IN 支持
# 过滤面板的"关系类型"选的是 relation_type 枚举值 (GENERATES/UPDATES/TRIGGERS/REFERENCES),
# 这些值会通过 relation_type__in 传到这里. 旧版本只支持 relation_code (历史字段) 导致查询返回空.
_RELATIONSHIP_IN_FIELD_KEYS_FOR_TYPE = ('relation_type__in', 'relation_types__in', 'relation_type', 'relation_types')


def _build_relationship_filter_clause(clean_filters: dict) -> tuple:
    """[SPR-08 T-S14-01] 构建 relationship 表 WHERE 子句, 严格走白名单防 SQL 注入.

    支持:
    - 简单 EQ: version_id / product_code / version_code
    - relation_code 精确 / __in 多值 (互斥, __in 优先)
    - relation_type__in / relation_types__in 多值 IN (来自过滤面板"关系类型"选择)
    - category_type(s) 多值 IN (category_types__in / category_type__in / 简写都支持)

    Returns:
        (where_clause, params): where_clause 至少 '1=1' (无任何条件时)
    """
    conditions = []
    bind_params = []

    for field in _RELATIONSHIP_SIMPLE_EQ_FIELDS:
        if field in clean_filters:
            conditions.append(f'{field} = ?')
            bind_params.append(clean_filters[field])

    # relation_code 精确 / __in 互斥 (__in 优先, 与原 if/elif 行为对齐)
    if 'relation_code__in' in clean_filters:
        codes = [c.strip() for c in str(clean_filters['relation_code__in']).split(',') if c.strip()]
        if codes:
            placeholders = ','.join('?' for _ in codes)
            conditions.append(f'relation_code IN ({placeholders})')
            bind_params.extend(codes)
    elif 'relation_code' in clean_filters:
        conditions.append('relation_code = ?')
        bind_params.append(clean_filters['relation_code'])

    # [FIX 2026-06-15] relation_type / relation_types 多值 IN
    # 过滤面板"关系类型"下选的是 relation_type 枚举值, 走这个分支
    for key in _RELATIONSHIP_IN_FIELD_KEYS_FOR_TYPE:
        if key in clean_filters and clean_filters[key]:
            rts = [c.strip() for c in str(clean_filters[key]).split(',') if c.strip()]
            if rts:
                placeholders = ','.join('?' for _ in rts)
                conditions.append(f'relation_type IN ({placeholders})')
                bind_params.extend(rts)
            break  # 只取第一个非空的 key

    # category_type(s) 多值 IN (取第一个非空 key)
    for key in _RELATIONSHIP_IN_FIELD_KEYS:
        if key in clean_filters and clean_filters[key]:
            cts = [c.strip() for c in str(clean_filters[key]).split(',') if c.strip()]
            if cts:
                placeholders = ','.join('?' for _ in cts)
                conditions.append(f'category_type IN ({placeholders})')
                bind_params.extend(cts)
            break  # 只取第一个非空的 key

    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    return where_clause, bind_params


def _query_relationship_with_scope(page, page_size, offset, clean_filters, scope_sql, is_desc):
    """[FIX 2026-06-10] relationship + scope 排序专用查询路径.

    DB 中 category_label / category_type 列大多为 NULL, 排序必须用 CASE WHEN 内联子查询
    计算层级 scope. 直接走 data_source.execute, 复用 special_routes_api 的 scope SQL.

    过滤白名单见 _RELATIONSHIP_SIMPLE_EQ_FIELDS / _RELATIONSHIP_IN_FIELD_KEYS.
    """
    ds = _get_data_source()

    # [SPR-08 T-S14-01] WHERE 子句委托给白名单 helper
    where_clause, bind_params = _build_relationship_filter_clause(clean_filters)

    # count
    count_sql = f"SELECT COUNT(*) FROM relationships WHERE {where_clause}"
    total_cursor = ds.execute(count_sql, tuple(bind_params))
    total = total_cursor.fetchone()[0]

    # data
    direction = 'DESC' if is_desc else 'ASC'
    logger.info(f"[_query_relationship_with_scope] is_desc={is_desc}, direction={direction}")
    # 注意: scope_sql 使用了别名 r (r.source_bo_id, r.target_bo_id 等)
    # 因此 FROM 子句必须使用相同的别名
    data_sql = f"""
        SELECT r.* FROM relationships r
        WHERE {where_clause}
        ORDER BY ({scope_sql}) {direction}, r.id ASC
        LIMIT ? OFFSET ?
    """
    data_params = list(bind_params) + [page_size, offset]
    logger.info(f"[_query_relationship_with_scope] data_sql ORDER BY: ({scope_sql}) {direction}")
    cursor = ds.execute(data_sql, tuple(data_params))
    columns_desc = [desc[0] for desc in cursor.description]
    raw_data = [dict(zip(columns_desc, row)) for row in cursor.fetchall()]

    # [FIX 2026-06-11] 必须在 compute_by_semantics 前显式填充 source/target hierarchy ids,
    # 否则 compute_scope 把所有关系 fallback 为 '同服务模块' (因为 source_domain_id 全是 None),
    # 用户看到所有行 category_label 都是 '同服务模块', 误以为排序乱序.
    # SQL 排序实际是对的 (id=29 sort_key=1, id=2-28 sort_key=3, id=1-27 sort_key=4),
    # 但前端展示因 category_label 都是 '同服务模块' 而显得毫无变化.
    from meta.services.query.computed_utils import ensure_hierarchy_ids_for_relationships
    ensure_hierarchy_ids_for_relationships(ds, raw_data)
    computation_service.compute_by_semantics('relationship', raw_data)

    # 获取 filters 数组
    filters = []
    try:
        config = view_config_service.get_or_build_view_config('relationship', None)
        if config and hasattr(config, 'list') and config.list:
            filters = config.list.filters if hasattr(config.list, 'filters') else []
    except Exception as e:
        logger.warning(f"[_query_relationship_with_scope] Failed to get filters: {e}")

    return jsonify({
        'success': True,
        'data': {
            'items': raw_data,
            'total': total,
            'page': page,
            'page_size': page_size,
            'filters': filters
        }
    })


@bo_bp.route('/<object_type>/deep', methods=['POST'])
@login_required
def deep_insert_bo(object_type):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    try:
        result = bo.deep_insert(object_type, data)
        if result.success:
            return jsonify({'success': True, 'data': result.data, 'message': result.message}), 201
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)
    except Exception as e:
        logger.error(f"[bo_api] deep_insert error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@bo_bp.route('/<object_type>/<int:obj_id>', methods=['PUT'])
@login_required
def update_bo(object_type, obj_id):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    result = bo.update(object_type, obj_id, data)
    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<path:obj_id>', methods=['PUT'])
@login_required
def update_bo_by_string_id(object_type, obj_id):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    result = bo.update(object_type, obj_id, data)
    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>', methods=['DELETE'])
@login_required
def delete_bo(object_type, obj_id):
    bo = _get_bo()
    result = bo.delete(object_type, obj_id)
    if result.success:
        return jsonify({'success': True, 'message': result.message})
    if hasattr(result, 'error') and result.error == 'NOT_FOUND':
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), 404
    if '不存在' in result.message or 'NOT_FOUND' in result.message:
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), 404
    return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<path:obj_id>', methods=['DELETE'])
@login_required
def delete_bo_by_string_id(object_type, obj_id):
    bo = _get_bo()
    result = bo.delete(object_type, obj_id)
    if result.success:
        return jsonify({'success': True, 'message': result.message})
    if hasattr(result, 'error') and result.error == 'NOT_FOUND':
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), 404
    if '不存在' in result.message or 'NOT_FOUND' in result.message:
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), 404
    return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)


# ── Action ──

@bo_bp.route('/<object_type>/<int:obj_id>/actions/<action_id>', methods=['POST'])
@login_required
def execute_action(object_type, obj_id, action_id):
    bo = _get_bo()
    params = request.get_json(silent=True) or {}
    params['id'] = obj_id
    result = bo.execute_action(object_type, action_id, params)
    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


# ── Association ──

@bo_bp.route('/<object_type>/<int:obj_id>/associations/<association_name>', methods=['POST'])
@login_required
def associate_bo(object_type, obj_id, association_name):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    target_id = data.get('target_id') or data.get('tgt_id')
    target_type = data.get('target_type') or data.get('tgt_type')
    metadata = data.get('metadata', {})

    if not target_id:
        return jsonify({'success': False, 'message': '目标 ID 不能为空'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    result = bo.associate(
        src_type=object_type,
        src_id=obj_id,
        tgt_type=target_type,
        tgt_id=target_id,
        association_name=association_name,
        metadata=metadata,
    )

    if result.success:
        return jsonify({'success': True, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/associations/<association_name>', methods=['DELETE'])
@login_required
def dissociate_bo(object_type, obj_id, association_name):
    bo = _get_bo()
    target_id = request.args.get('target_id')
    target_type = request.args.get('target_type')

    if not target_id:
        data = request.get_json(silent=True) or {}
        target_id = data.get('target_id') or data.get('tgt_id')
        target_type = target_type or data.get('target_type') or data.get('tgt_type')

    if not target_id:
        return jsonify({'success': False, 'message': 'target_id is required (via query param or JSON body)'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    result = bo.dissociate(
        src_type=object_type,
        src_id=obj_id,
        tgt_type=target_type,
        tgt_id=int(target_id),
        association_name=association_name,
    )

    if result.success:
        return jsonify({'success': True, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/associations/<association_name>', methods=['GET'])
@login_required
def query_associations_bo(object_type, obj_id, association_name):
    bo = _get_bo()
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', request.args.get('pageSize', 50)))
    page_size = max(1, min(page_size, MAX_USER_PAGE_SIZE))  # 防止 DoS：限制用户输入

    filters, ordering, search = _extract_assoc_query_params(request.args)

    result = bo.query_associations(
        src_type=object_type,
        src_id=obj_id,
        association_name=association_name,
        page=page,
        page_size=page_size,
        search=search,
        filters=filters,
        ordering=ordering,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data})
    logger.error(f"[bo_api] query_associations failed: type={object_type}, id={obj_id}, assoc={association_name}, message={result.message}")
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


# ── Association v2 ($associations 路由) ──

@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>', methods=['GET'])
@login_required
def query_associations_v2(object_type, obj_id, association_name):
    """查询关联列表 - v2 API"""
    bo = _get_bo()
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', request.args.get('pageSize', 50)))

    filters, ordering, search = _extract_assoc_query_params(request.args)

    result = bo.query_associations(
        src_type=object_type,
        src_id=obj_id,
        association_name=association_name,
        page=page,
        page_size=page_size,
        search=search,
        filters=filters,
        ordering=ordering,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/count', methods=['GET'])
@login_required
def count_associations_v2(object_type, obj_id, association_name):
    """统计关联数量 - v2 API"""
    bo = _get_bo()
    # [FIX 2026-06-12] BOFramework 没有 count_associations() 方法
    result = bo.execute(
        object_type=object_type,
        action='count',
        params={
            'src_id': obj_id,
            'association_name': association_name,
        },
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/assign', methods=['POST'])
@login_required
def assign_association_v2(object_type, obj_id, association_name):
    """分配单个关联 - v2 API (返回 204)"""
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    target_id = data.get('target_id') or data.get('tgt_id')
    target_type = data.get('target_type') or data.get('tgt_type')
    metadata = data.get('metadata', {})

    if not target_id:
        return jsonify({'success': False, 'message': '目标 ID 不能为空'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    # [FIX 2026-06-12] BOFramework 没有 assign_association() 方法
    # 原 bo.assign_association(...) → AttributeError → 500
    # 改为 bo.associate(), 由 AssociationEngine._dispatch 处理
    try:
        result = bo.associate(
            src_type=object_type,
            src_id=obj_id,
            tgt_type=target_type,
            tgt_id=target_id,
            association_name=association_name,
            metadata=metadata,
        )
    except Exception as e:
        import traceback
        logger.error(f"[assign_association_v2] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': type(e).__name__, 'message': str(e)}), 500

    if result.success:
        return '', 204
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/unassign', methods=['POST'])
@login_required
def unassign_association_v2(object_type, obj_id, association_name):
    """取消分配单个关联 - v2 API (返回 204)"""
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    association_record_id = data.get('association_record_id')
    target_id = data.get('target_id') or data.get('tgt_id')
    target_type = data.get('target_type') or data.get('tgt_type')

    if not target_id and not association_record_id:
        return jsonify({'success': False, 'message': 'target_id or association_record_id is required'}), 400

    if association_record_id:
        from meta.core.yaml_loader import get_meta_object
        meta_obj = get_meta_object(object_type)
        if meta_obj and meta_obj.associations:
            assoc_def = meta_obj.associations.get(association_name)
            if assoc_def and hasattr(assoc_def, 'through') and assoc_def.through:
                ds = bo._data_source
                sql = f"SELECT * FROM {assoc_def.through} WHERE id = ?"
                logger.info(f"[unassign] Looking up record: {sql} with params: [{association_record_id}]")
                cursor = ds.execute(sql, [int(association_record_id)])
                row = cursor.fetchone()
                if not row:
                    return jsonify({'success': False, 'message': 'Association record not found'}), 404
                columns = [desc[0] for desc in cursor.description]
                record = dict(zip(columns, row))
                src_key = assoc_def.source_key if hasattr(assoc_def, 'source_key') else 'source_id'
                tgt_key = assoc_def.target_key if hasattr(assoc_def, 'target_key') else 'target_id'
                target_id = record.get(tgt_key)
                if not target_id:
                    return jsonify({'success': False, 'message': 'Cannot resolve target_id from association record'}), 400
                if not target_type:
                    target_type = getattr(assoc_def, 'target_entity', None) or getattr(assoc_def, 'target_object', None)
            else:
                return jsonify({'success': False, 'message': 'Association does not use through table'}), 400
        else:
            return jsonify({'success': False, 'message': 'Cannot resolve association definition'}), 400
    else:
        target_id = int(target_id) if target_id else None

    if not target_id:
        return jsonify({'success': False, 'message': '目标 ID 不能为空'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    # [FIX 2026-06-12] BOFramework 没有 unassign_association() 方法
    try:
        result = bo.dissociate(
            src_type=object_type,
            src_id=obj_id,
            tgt_type=target_type,
            tgt_id=target_id,
            association_name=association_name,
        )
    except Exception as e:
        import traceback
        logger.error(f"[unassign_association_v2] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': type(e).__name__, 'message': str(e)}), 500

    if result.success:
        return '', 204
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/batch_assign', methods=['POST'])
@login_required
def batch_assign_associations_v2(object_type, obj_id, association_name):
    """批量分配关联 - v2 API"""
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    target_ids = data.get('target_ids', [])
    target_type = data.get('target_type') or data.get('tgt_type')
    metadata = data.get('metadata', {})

    if not target_ids:
        return jsonify({'success': False, 'message': 'target_ids is required'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    # [FIX 2026-06-12] BOFramework 没有 batch_assign_associations() 方法
    try:
        result = bo.execute(
            object_type=object_type,
            action='batch_assign',
            params={
                'src_id': obj_id,
                'tgt_type': target_type,
                'target_ids': target_ids,
                'association_name': association_name,
                'metadata': metadata,
            },
        )
    except Exception as e:
        import traceback
        logger.error(f"[batch_assign_associations_v2] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': type(e).__name__, 'message': str(e)}), 500

    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/batch_unassign', methods=['POST'])
@login_required
def batch_unassign_associations_v2(object_type, obj_id, association_name):
    """批量取消分配关联 - v2 API"""
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    target_ids = data.get('target_ids', [])
    target_type = data.get('target_type') or data.get('tgt_type')
    association_record_ids = data.get('association_record_ids', [])

    if association_record_ids:
        from meta.core.yaml_loader import get_meta_object
        meta_obj = get_meta_object(object_type)
        if meta_obj and meta_obj.associations:
            assoc_def = meta_obj.associations.get(association_name)
            if assoc_def and hasattr(assoc_def, 'through') and assoc_def.through:
                ds = bo._data_source
                tgt_key = assoc_def.target_key if hasattr(assoc_def, 'target_key') else 'target_id'
                placeholders = ','.join(['?' for _ in association_record_ids])
                sql = f"SELECT id, {tgt_key} FROM {assoc_def.through} WHERE id IN ({placeholders})"
                cursor = ds.execute(sql, [int(rid) for rid in association_record_ids])
                rows = cursor.fetchall()
                resolved_ids = [row[1] for row in rows if row[1] is not None]
                if not resolved_ids:
                    return jsonify({'success': False, 'message': 'No valid target IDs found'}), 400
                target_ids = list(set(resolved_ids + target_ids))
                if not target_type:
                    target_type = assoc_def.target_entity
            else:
                return jsonify({'success': False, 'message': 'Association does not use through table'}), 400
        else:
            return jsonify({'success': False, 'message': 'Cannot resolve association definition'}), 400

    if not target_ids:
        return jsonify({'success': False, 'message': 'target_ids or association_record_ids is required'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    # [FIX 2026-06-12] BOFramework 没有 batch_unassign_associations() 方法
    try:
        result = bo.execute(
            object_type=object_type,
            action='batch_unassign',
            params={
                'src_id': obj_id,
                'tgt_type': target_type,
                'target_ids': target_ids,
                'association_name': association_name,
            },
        )
    except Exception as e:
        import traceback
        logger.error(f"[batch_unassign_associations_v2] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': type(e).__name__, 'message': str(e)}), 500

    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/$associations/<association_name>/batch-query', methods=['POST'])
@login_required
def batch_query_associations(object_type, association_name):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    source_ids = data.get('source_ids', [])
    page = data.get('page', 1)
    page_size = data.get('page_size', data.get('pageSize', 20))
    try:
        page_size = max(1, min(int(page_size), MAX_USER_PAGE_SIZE))  # 防止 DoS：限制用户输入
    except (TypeError, ValueError):
        page_size = 20
    search = data.get('search', '')

    if not source_ids:
        return jsonify({'success': True, 'data': {'items': [], 'total': 0, 'counts': {}}})

    result = bo.batch_query_associations(
        src_type=object_type,
        source_ids=source_ids,
        association_name=association_name,
        page=page,
        page_size=page_size,
        search=search,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/retrieve', methods=['GET'])
@login_required
def retrieve_with_associations(object_type, obj_id):
    """深度获取对象及其关联 - v2 API"""
    bo = _get_bo()

    associations_param = request.args.get('associations', '')
    associations = [a.strip() for a in associations_param.split(',') if a.strip()] if associations_param else None
    depth = int(request.args.get('depth', 1))

    if depth > 2:
        return jsonify({'success': False, 'message': '深度限制为2，防止循环引用'}), 400

    result = bo.retrieve_with_associations(
        object_type=object_type,
        obj_id=obj_id,
        associations=associations,
        depth=depth
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), 404


@bo_bp.route('/<object_type>/batch-delete', methods=['POST'])
@login_required
def batch_delete_bo(object_type):
    """批量删除记录"""
    from meta.services.manage_service import ManageService
    
    body = request.get_json(silent=True) or {}
    ids = body.get('ids', [])
    force = body.get('force', False)
    
    if not ids:
        return jsonify({'success': False, 'message': '请提供要删除的记录ID'}), 400
    
    try:
        bo = _get_bo()
        manage_service = ManageService(bo._data_source)
        
        # 设置审计用户
        current_user = getattr(g, 'current_user', None) or {}
        user_id = current_user.get('user_id') or request.headers.get('X-User-Id')
        user_name = current_user.get('display_name') or current_user.get('username') or request.headers.get('X-User-Name', '')
        user_ip = request.headers.get('X-Forwarded-For', request.remote_addr) or ''
        user_ua = request.headers.get('User-Agent', '')
        manage_service.set_audit_user(user_id, user_name, user_ip, user_ua)
        
        result = manage_service.batch_delete(object_type, ids, force)

        return jsonify({
            'success': result.failed_count == 0,
            'success_count': result.success_count,
            'failed_count': result.failed_count,
            'results': [r.to_dict() if hasattr(r, 'to_dict') else {'success': r.success, 'data': r.data, 'message': r.message, 'error': r.error} for r in result.results],
            'errors': result.errors,
        }), 200 if result.failed_count == 0 else 207
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] batch-delete error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [FIX GAP-008 2026-06-07] v2 端点补齐 — 8 个原仅 v1 存在的端点迁移到 v2
# v1 端点 (manage_api) 已被 sunset_at=2026-06-05, v2 路径未实现 → 测试报 500
# 解决: 在 v2 重新注册 8 个路由, 委托给 v1 handler (共享业务逻辑)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 延迟导入避免循环依赖
def _v1_handlers():
    """延迟导入 v1 handler 函数 (避免 manage_api 导入 bo_api 形成循环)"""
    from meta.api.manage_api import (
        list_records_post as _list_records_post,
        batch_create as _batch_create,
        batch_update as _batch_update,
        list_actions as _list_actions,
        recover_from_log as _recover_from_log,
        list_deleted_objects as _list_deleted_objects,
        get_state_history as _get_state_history,
        get_stage_metrics as _get_stage_metrics,
    )
    return {
        'list_records_post': _list_records_post,
        'batch_create': _batch_create,
        'batch_update': _batch_update,
        'list_actions': _list_actions,
        'recover_from_log': _recover_from_log,
        'list_deleted_objects': _list_deleted_objects,
        'get_state_history': _get_state_history,
        'get_stage_metrics': _get_stage_metrics,
    }


@bo_bp.route('/<object_type>/list', methods=['POST'])
@login_required
def v2_list_records_post(object_type):
    """POST 列表查询 (URL 过长场景) — 委托给 v1 manage_api"""
    return _v1_handlers()['list_records_post'](object_type)


@bo_bp.route('/<object_type>/batch-create', methods=['POST'])
@login_required
def v2_batch_create(object_type):
    """批量创建 — 委托给 v1 manage_api"""
    return _v1_handlers()['batch_create'](object_type)


@bo_bp.route('/<object_type>/batch-update', methods=['POST'])
@login_required
def v2_batch_update(object_type):
    """批量更新 — 委托给 v1 manage_api"""
    return _v1_handlers()['batch_update'](object_type)


@bo_bp.route('/<object_type>/<int:obj_id>/actions', methods=['GET'])
@login_required
def v2_list_actions(object_type, obj_id):
    """获取可执行 Action 列表 — 委托给 v1 manage_api"""
    return _v1_handlers()['list_actions'](object_type, obj_id)


@bo_bp.route('/<object_type>/<int:obj_id>/actions', methods=['GET'])
@login_required
def v2_list_actions_string(object_type, obj_id):
    """[path variant] 字符串 id 兼容 — 委托给 v1 manage_api"""
    return _v1_handlers()['list_actions'](object_type, obj_id)


@bo_bp.route('/<object_type>/<int:obj_id>/recover', methods=['POST'])
@login_required
def v2_recover_from_log(object_type, obj_id):
    """从 audit_log 恢复已删除 — 委托给 v1 manage_api"""
    return _v1_handlers()['recover_from_log'](object_type, obj_id)


@bo_bp.route('/<object_type>/deleted', methods=['GET'])
@login_required
def v2_list_deleted_objects(object_type):
    """查询已删除对象 — 委托给 v1 manage_api"""
    return _v1_handlers()['list_deleted_objects'](object_type)


@bo_bp.route('/<object_type>/<int:obj_id>/state_history', methods=['GET'])
@login_required
def v2_get_state_history(object_type, obj_id):
    """状态转换历史 — 委托给 v1 manage_api"""
    return _v1_handlers()['get_state_history'](object_type, obj_id)


@bo_bp.route('/<object_type>/<int:obj_id>/stage_metrics', methods=['GET'])
@login_required
def v2_get_stage_metrics(object_type, obj_id):
    """状态停留统计 — 委托给 v1 manage_api"""
    return _v1_handlers()['get_stage_metrics'](object_type, obj_id)


# ── Architecture Preview ──

@bo_bp.route('/architecture/preview', methods=['GET'])
@login_required
def get_architecture_preview():
    """架构预览聚合 API - 一次返回完整树结构数据"""
    try:
        bo = _get_bo()
        version_id = request.args.get('version_id', type=int)
        domain_ids = request.args.get('domain_ids', '')
        sub_domain_ids = request.args.get('sub_domain_ids', '')
        service_module_ids = request.args.get('service_module_ids', '')
        business_object_ids = request.args.get('business_object_ids', '')

        # 构建版本过滤条件
        version_filter = {'version_id': version_id} if version_id else {}

        # [BUG-V032 修复 2026-06-29] 循环分页拿全量, 绕过 MAX_USER_PAGE_SIZE=500 cap
        # 根因: bo.query → query_bo (line 463) 把 page_size 强制 min(_, 500),
        #       V863 有 2850 BO/5634 Rel, 单次 5000 实际被截到 500, 导致后续按 ID 过滤时大量缺失
        # 修复: 用分页循环 (每页 500), 直到 last_page < page_size 才停
        _PAGE_SIZE_INTERNAL = 500
        _MAX_PAGES = 100  # 防御死循环: 上限 50000 行
        _data_source_local = _get_data_source()

        def _fetch_all_by_version(object_type, version_filter_arg):
            """循环分页拉全量, 过滤条件 = version_filter_arg (或 page_size 内部 cap 500)"""
            from meta.core.query_builder import QueryBuilder
            from meta.core.models import registry
            meta_obj = registry.get(object_type)
            if not meta_obj:
                return []
            all_data = []
            for page_idx in range(_MAX_PAGES):
                builder = QueryBuilder(_data_source_local, meta_obj)
                for k, v in version_filter_arg.items():
                    builder.where_eq(k, v)
                builder.page(page_idx + 1, _PAGE_SIZE_INTERNAL)
                rows = builder.execute()
                if not rows:
                    break
                all_data.extend(rows)
                if len(rows) < _PAGE_SIZE_INTERNAL:
                    break
            return all_data

        domains = _fetch_all_by_version('domain', version_filter.copy())
        sub_domains = _fetch_all_by_version('sub_domain', version_filter.copy())
        modules = _fetch_all_by_version('service_module', version_filter.copy())
        business_objects = _fetch_all_by_version('business_object', version_filter.copy())
        relationships = _fetch_all_by_version('relationship', version_filter.copy())

        # 解析过滤 ID 列表
        domain_id_list = [int(x) for x in domain_ids.split(',') if x.strip()]
        sub_domain_id_list = [int(x) for x in sub_domain_ids.split(',') if x.strip()]
        module_id_list = [int(x) for x in service_module_ids.split(',') if x.strip()]
        bo_id_list = [int(x) for x in business_object_ids.split(',') if x.strip()]

        # 按 ID 过滤
        if domain_id_list:
            domains = [d for d in domains if d.get('id') in domain_id_list]
        if sub_domain_id_list:
            sub_domains = [d for d in sub_domains if d.get('id') in sub_domain_id_list]
        if module_id_list:
            modules = [m for m in modules if m.get('id') in module_id_list]
        if bo_id_list:
            business_objects = [b for b in business_objects if b.get('id') in bo_id_list]

        # ── [V1.1.13 2026-06-15] SAP 风格 dim scope 层级包容 (Hierarchical Inclusion) ──
        # 业务语义: "通过关系" 引入的外部 BO, 应当递归引出完整层级 (BO->SM->SD->D)
        # 之前 V1.1.11/12 只补全外部节点元数据 (is_external=true, 仍受 dim scope 隔离)
        # V1.1.13 把外部节点加入 dim scope (跟 SAP 风格一致):
        #   - 引入 1 个 BO = 引入它的 SM, SM = 引入它的 SD, SD = 引入它的 D
        #   - "通过关系" 关系另一头 (任一端) 递归加入
        # 实施:
        #   1. 收集当前 dim scope 派生的"中心" (4 个层级的 id)
        #   2. 调用 DimScopeRelationshipIncluder 扩展 (BFS 反推)
        #   3. 用扩展后的 scope 拉元数据 (raw SQL, 绕过 DataPermissionInterceptor)
        #   4. 把"已扩展"实体加入业务对象/模块/子域/域列表 (is_external=false)
        #   V1.1.11/12 仍跑 (处理更深一层的"无关系引用"情况), 但 V1.1.13 优先
        # ────────────────────────────────────────────
        try:
            from meta.services.dim_scope_relationship_includer import DimScopeRelationshipIncluder
            _ds2 = _get_data_source()
            includer = DimScopeRelationshipIncluder(_ds2)
            # 1. 收集当前 4 个层级 id 作为 initial
            initial = {
                'domain_ids': [d.get('id') for d in domains if d.get('id')],
                'sub_domain_ids': [sd.get('id') for sd in sub_domains if sd.get('id')],
                'sm_ids': [m.get('id') for m in modules if m.get('id')],
                'bo_ids': [b.get('id') for b in business_objects if b.get('id')],
            }
            # 2. 扩展
            expanded = includer.expand(initial, relationships)
            # 3. 拉扩展后的元数据
            existing_d_ids = set(initial['domain_ids'])
            existing_sd_ids = set(initial['sub_domain_ids'])
            existing_sm_ids = set(initial['sm_ids'])
            existing_bo_ids = set(initial['bo_ids'])
            new_d_ids = expanded['d'] - existing_d_ids
            new_sd_ids = expanded['sd'] - existing_sd_ids
            new_sm_ids = expanded['sm'] - existing_sm_ids
            new_bo_ids = expanded['bo'] - existing_bo_ids
            # 4. 拉元数据并加入列表 (is_external=false 因为是"已扩展 dim scope")
            if new_bo_ids:
                ph = ','.join('?' * len(new_bo_ids))
                # [V1.1.13 fix] 外部 BO 的 domain_id/sub_domain_id 可能为 NULL,
                # 必须通过 SM→SD→D 链路获取层级信息
                rows = _ds2.execute(
                    f"SELECT bo.id, bo.code, bo.name, bo.domain_id, bo.sub_domain_id, "
                    f"bo.service_module_id, bo.visibility, "
                    f"COALESCE(d_direct.name, d_chain.name) as domain_name, "
                    f"COALESCE(sd_direct.name, sd_chain.name) as sub_domain_name, "
                    f"COALESCE(sm_direct.name, sm_chain.name) as service_module_name, "
                    f"COALESCE(sm_direct.code, sm_chain.code) as service_module_code, "
                    f"COALESCE(bo.domain_id, d_chain.id) as effective_domain_id, "
                    f"COALESCE(bo.sub_domain_id, sd_chain.id) as effective_sub_domain_id "
                    f"FROM business_objects bo "
                    f"LEFT JOIN domains d_direct ON bo.domain_id = d_direct.id "
                    f"LEFT JOIN sub_domains sd_direct ON bo.sub_domain_id = sd_direct.id "
                    f"LEFT JOIN service_modules sm_direct ON bo.service_module_id = sm_direct.id "
                    f"LEFT JOIN service_modules sm_chain ON bo.service_module_id = sm_chain.id "
                    f"LEFT JOIN sub_domains sd_chain ON sm_chain.sub_domain_id = sd_chain.id "
                    f"LEFT JOIN domains d_chain ON sd_chain.domain_id = d_chain.id "
                    f"WHERE bo.id IN ({ph})", list(new_bo_ids)
                ).fetchall()
                # [V1.2.6] 去重 + 替换: 同 code 时, version 764 的 BO 优先于 version 1 的
                # 原 bug: V1.1.11 添加 version 1 的 BO (domain_name=采购管理),
                #   V1.1.13 添加 version 764 的 BO (domain_name=库存管理x) 被跳过,
                #   导致 availableDomains 缺少外域领域
                existing_bo_codes_v13 = {b.get('code') for b in business_objects if b.get('code')}
                added_codes_v13 = set()
                for r in rows:
                    r_code = r[1]
                    if r_code and r_code in added_codes_v13:
                        continue
                    new_bo = {
                        'id': r[0], 'code': r[1], 'name': r[2],
                        'domain_id': r[11] or r[3], 'sub_domain_id': r[12] or r[4],
                        'service_module_id': r[5],
                        'visibility': r[6],
                        'domain_name': r[7] or '',
                        'sub_domain_name': r[8] or '',
                        'service_module_name': r[9] or '',
                        'service_module_code': r[10] or '',
                        'is_external': True,
                    }
                    if r_code and r_code in existing_bo_codes_v13:
                        # [V1.2.6] 替换: 找到已有的同 code BO, 用 version 764 的替换
                        for i, b in enumerate(business_objects):
                            if b.get('code') == r_code:
                                business_objects[i] = new_bo
                                break
                    else:
                        business_objects.append(new_bo)
                    if r_code: added_codes_v13.add(r_code)
            if new_sm_ids:
                ph = ','.join('?' * len(new_sm_ids))
                rows = _ds2.execute(
                    f"SELECT sm.id, sm.name, sm.code, sm.sub_domain_id, sd.name as sub_domain_name "
                    f"FROM service_modules sm LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id "
                    f"WHERE sm.id IN ({ph})", list(new_sm_ids)
                ).fetchall()
                for r in rows:
                    modules.append({
                        'id': r[0], 'name': r[1], 'code': r[2], 'sub_domain_id': r[3],
                        'sub_domain_name': r[4] or '',
                        'is_included_via_relationship': True,
                    })
            if new_sd_ids:
                ph = ','.join('?' * len(new_sd_ids))
                rows = _ds2.execute(
                    f"SELECT sd.id, sd.name, sd.domain_id, d.name as domain_name "
                    f"FROM sub_domains sd LEFT JOIN domains d ON sd.domain_id = d.id "
                    f"WHERE sd.id IN ({ph})", list(new_sd_ids)
                ).fetchall()
                for r in rows:
                    sub_domains.append({
                        'id': r[0], 'name': r[1], 'domain_id': r[2],
                        'domain_name': r[3] or '',
                        'is_included_via_relationship': True,
                    })
            if new_d_ids:
                ph = ','.join('?' * len(new_d_ids))
                rows = _ds2.execute(
                    f"SELECT id, name, code, version_id FROM domains WHERE id IN ({ph})", list(new_d_ids)
                ).fetchall()
                for r in rows:
                    domains.append({
                        'id': r[0], 'name': r[1], 'code': r[2], 'version_id': r[3],
                        'is_included_via_relationship': True,
                    })
            logger.info(
                f'[V1.1.13] SAP-style hierarchical inclusion: '
                f'added d={len(new_d_ids)} sd={len(new_sd_ids)} sm={len(new_sm_ids)} bo={len(new_bo_ids)}'
            )
        except Exception as e:
            logger.warning(f'[V1.1.13] dim scope inclusion failed: {e}')

        # ── [v32 2026-06-11] 补全 hierarchy 范围（外部 BO 引用的 SM/SD/Domain 需保留）
        # 场景：用户在管理页勾选 SM 范围 + 关系范围"内+外部"，
        #      外部 SM 的 BO 会出现在 business_objects 中（因 bo_id_list 为空），
        #      但 modules/sub_domains/domains 已被严格过滤掉。
        # 结果：前端 buildServiceModules 无法为外部 SM 创建容器，
        #      外部 SM 的 BO 变成蓝色孤儿节点。
        # 修复：从 business_objects 反推缺失的 SM/SD/Domain 并补回。
        module_id_set = set(module_id_list) if module_id_list else None
        sub_domain_id_set = set(sub_domain_id_list) if sub_domain_id_list else None
        domain_id_set = set(domain_id_list) if domain_id_list else None
        referenced_sm_ids = set()
        referenced_sub_domain_ids = set()
        referenced_domain_ids = set()
        for b in business_objects:
            sm_id = b.get('service_module_id')
            sd_id = b.get('sub_domain_id')
            d_id = b.get('domain_id')
            if sm_id and (module_id_set is None or sm_id not in module_id_set):
                referenced_sm_ids.add(sm_id)
            if sd_id and (sub_domain_id_set is None or sd_id not in sub_domain_id_set):
                referenced_sub_domain_ids.add(sd_id)
            if d_id and (domain_id_set is None or d_id not in domain_id_set):
                referenced_domain_ids.add(d_id)
        if referenced_sm_ids or referenced_sub_domain_ids or referenced_domain_ids:
            # [BUG-V032 修复] 改用 modules/sub_domains/domains (list) 替代 .data (ActionResult)
            extra_modules = [m for m in modules if m.get('id') in referenced_sm_ids]
            extra_sub_domains = [sd for sd in sub_domains if sd.get('id') in referenced_sub_domain_ids]
            extra_domains = [d for d in domains if d.get('id') in referenced_domain_ids]
            seen = {m.get('id') for m in modules}
            for m in extra_modules:
                if m.get('id') not in seen:
                    modules.append(m)
                    seen.add(m.get('id'))
            seen = {sd.get('id') for sd in sub_domains}
            for sd in extra_sub_domains:
                if sd.get('id') not in seen:
                    sub_domains.append(sd)
                    seen.add(sd.get('id'))
            seen = {d.get('id') for d in domains}
            for d in extra_domains:
                if d.get('id') not in seen:
                    domains.append(d)
                    seen.add(d.get('id'))

        # ── [v1.1.11 2026-06-15] 补全关系引用的外部 BO 节点 (上下文读取) ──
        # 原 bug: BO list 受 dim scope 限制, 但关系 list 走 OR 语义允许 source/target
        #         任一端在 dim scope 内 (跨域 association 推导 V1.1.9)
        #   → cross-boundary 关系的 target BO 在域外, 不在 business_objects
        #   → 图表渲染: 边存在 (target_bo_name 来自关系 join), 节点缺失
        #   → 图表显示异常: 5 个孤立节点 + 10 条边 (其中 3 条指向"幽灵节点")
        # 业界标准 (SAP 字段级授权 + Salesforce OWD 引用模式):
        #   关系引用的 BO 走"上下文读取"模式, 元数据 (id/code/name/type/domain) 可见
        #   敏感字段 (description / attributes / custom_field) 仍受 BO 自身 dim scope 控制
        #   (v1.1.10 单条 get 已加 dim scope 校验, 这里补的是"图谱节点元数据"可见性)
        # 实施: 收集所有关系引用的 BO id, diff 出"在关系里但不在 business_objects"
        #       的 BO, 用 raw SQL 拉元数据字段 (绕过 DataPermissionInterceptor),
        #       标记 is_external=true 让前端区分 (灰显/特殊样式)
        try:
            _ds = _get_data_source()
            referenced_bo_ids = set()
            for r in relationships:
                sid = r.get('source_bo_id') or r.get('sourceBoId')
                tid = r.get('target_bo_id') or r.get('targetBoId')
                if sid: referenced_bo_ids.add(sid)
                if tid: referenced_bo_ids.add(tid)
            existing_bo_ids = {b.get('id') for b in business_objects}
            external_bo_ids = referenced_bo_ids - existing_bo_ids
            if external_bo_ids:
                placeholders = ','.join('?' * len(external_bo_ids))
                # [V1.2.5 2026-06-17] LEFT JOIN SM→SD→D 链路获取 effective domain/sub_domain
                # 原 bug: 外部 BO (version 1) 的 domain_id/sub_domain_id 为 NULL,
                #   导致前端 availableDomains/availableSubDomains 无法包含外域容器名称,
                #   颜色配置中缺少外域领域/子领域选项
                # 逻辑: BO.domain_id 有值 → 直接用; 为 NULL → 通过 SM.sub_domain_id → SD → D 反推
                ext_rows = _ds.execute(
                    f"""SELECT bo.id, bo.code, bo.name, bo.domain_id, bo.sub_domain_id,
                               bo.service_module_id, bo.visibility,
                               COALESCE(bo.sub_domain_id, sd_chain.id) as effective_sub_domain_id,
                               COALESCE(bo.domain_id, d_chain.id) as effective_domain_id,
                               sd_chain.name as effective_sub_domain_name,
                               d_chain.name as effective_domain_name,
                               sm.name as service_module_name,
                               sm.code as service_module_code
                        FROM business_objects bo
                        LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
                        LEFT JOIN sub_domains sd_chain ON sm.sub_domain_id = sd_chain.id
                        LEFT JOIN domains d_chain ON sd_chain.domain_id = d_chain.id
                        WHERE bo.id IN ({placeholders})""",
                    list(external_bo_ids)
                ).fetchall()
                # [V1.2.7 2026-06-17] 对同 code 的外部 BO, 优先使用当前 version 的 BO
                # 原 bug: 关系引用 version 1 的 BO (如 BO#8 BO_INVENTORY, domain=采购管理),
                #   但 version 764 有同名 BO (如 BO#474, domain=库存管理x),
                #   V1.1.11 只添加 version 1 的, 导致 domain_name 不对 → posX 错误 + 统计不准
                # 修复: 先收集所有外部 BO 的 code, 再从当前 version 查找同名 BO 替换
                ext_bo_codes = set()
                for row in ext_rows:
                    if row[1]:
                        ext_bo_codes.add(row[1])
                # 查找当前 version 中同 code 的 BO
                version_bo_map = {}  # code → row (from current version)
                if ext_bo_codes:
                    vph = ','.join('?' * len(ext_bo_codes))
                    version_id_val = version_id
                    # [V1.2.7] 修复: version 764 的 BO domain_id/sub_domain_id 可能为 NULL,
                    # 需要走 SM→SD→D 链路反推 (与 V1.2.5 ext_rows 查询一致)
                    version_rows = _ds.execute(
                        f"""SELECT bo.id, bo.code, bo.name, bo.domain_id, bo.sub_domain_id,
                                   bo.service_module_id, bo.visibility,
                                   COALESCE(bo.sub_domain_id, sd_chain.id) as effective_sub_domain_id,
                                   COALESCE(bo.domain_id, d_chain.id) as effective_domain_id,
                                   sd_chain.name as effective_sub_domain_name,
                                   d_chain.name as effective_domain_name,
                                   sm.name as service_module_name,
                                   sm.code as service_module_code
                            FROM business_objects bo
                            LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
                            LEFT JOIN sub_domains sd_chain ON sm.sub_domain_id = sd_chain.id
                            LEFT JOIN domains d_chain ON sd_chain.domain_id = d_chain.id
                            WHERE bo.code IN ({vph}) AND bo.version_id = ?""",
                        list(ext_bo_codes) + [version_id_val]
                    ).fetchall()
                    for vr in version_rows:
                        if vr[1]:
                            version_bo_map[vr[1]] = vr
                # 收集外部 BO 涉及的层级 id (用于 V1.1.12 补外部容器)
                ext_domain_ids = set()
                ext_sd_ids = set()
                ext_sm_ids = set()
                # [V1.2.6] 去重: 如果 business_objects 中已有同 code 的 BO, 不再添加
                # [V1.2.7] 优先使用当前 version 的 BO (domain_name 更准确)
                existing_bo_codes = {b.get('code') for b in business_objects if b.get('code')}
                added_codes = set()
                for row in ext_rows:
                    bo_code = row[1]
                    # [V1.2.7] 如果当前 version 有同名 BO, 优先用它
                    if bo_code and bo_code in version_bo_map:
                        vr = version_bo_map[bo_code]
                        eff_domain_id = vr[7] or vr[3]
                        eff_sub_domain_id = vr[8] or vr[4]
                    else:
                        eff_domain_id = row[7] if row[7] else row[3]
                        eff_sub_domain_id = row[8] if row[8] else row[4]
                    # 收集层级 id (无论是否跳过, 都需要用于容器补全)
                    if eff_domain_id: ext_domain_ids.add(eff_domain_id)
                    if eff_sub_domain_id: ext_sd_ids.add(eff_sub_domain_id)
                    sm_id = (version_bo_map.get(bo_code, [None])[5]
                             if bo_code and bo_code in version_bo_map else row[5])
                    if sm_id: ext_sm_ids.add(sm_id)
                    # 去重: 已有同 code 的 BO 或本次已添加同 code 的 BO, 跳过
                    if (bo_code and bo_code in existing_bo_codes) or (bo_code and bo_code in added_codes):
                        continue
                    # 构造 BO dict: 优先用 version 764 的数据
                    if bo_code and bo_code in version_bo_map:
                        vr = version_bo_map[bo_code]
                        bo = {
                            'id': vr[0], 'code': vr[1], 'name': vr[2],
                            'domain_id': vr[8] or vr[3],
                            'sub_domain_id': vr[7] or vr[4],
                            'service_module_id': vr[5],
                            'visibility': vr[6],
                            'domain_name': vr[10] or '',
                            'sub_domain_name': vr[9] or '',
                            'service_module_name': vr[11] or '',
                            'service_module_code': vr[12] or '',
                            'is_external': True,
                        }
                    else:
                        bo = {
                            'id': row[0], 'code': row[1], 'name': row[2],
                            'domain_id': eff_domain_id,
                            'sub_domain_id': eff_sub_domain_id,
                            'service_module_id': row[5],
                            'visibility': row[6],
                            'domain_name': row[10] or '',
                            'sub_domain_name': row[9] or '',
                            'service_module_name': row[11] or '',
                            'service_module_code': row[12] or '',
                            'is_external': True,
                        }
                    business_objects.append(bo)
                    if bo_code: added_codes.add(bo_code)
                logger.info(
                    f'[v1.1.11] chart view external BO nodes: '
                    f'external_added={len(external_bo_ids)} total_now={len(business_objects)}'
                )

                # ── [V1.1.12 2026-06-15] 补外部 BO 涉及的层级容器 (domain / sub_domain / service) ──
                # 原 bug: V32 的 hierarchy 补全在 V1.1.11 之前跑, 看不到 V1.1.11 补的外部 BO
                #   → 图表渲染: 外部 BO 节点有 data, 但没有父级 group 包裹, 变成蓝色孤儿
                # 修复: V1.1.11 补完外部 BO 后, 再从 business_objects (含外部) 反推 SM/SD/Domain
                # 业界标准: 拉容器 id+name+parent_id 3 字段, 不拉 description/其他敏感字段
                # ────────────────────────────────────────────
                # 收集当前 business_objects 涉及的 SM/SD/Domain id
                # (注意: V1.1.11 补的 BO 也在 business_objects 内, 所以这里能拿到外部的)
                # 同样用 module_result.data / sub_domain_result.data / domain_result.data
                # 拉未过滤的全量数据, 这样能拿到不在 dim scope 内的容器
                cur_referenced_sm_ids = set()
                cur_referenced_sub_domain_ids = set()
                cur_referenced_domain_ids = set()
                for b in business_objects:
                    sm_id = b.get('service_module_id')
                    sd_id = b.get('sub_domain_id')
                    d_id = b.get('domain_id')
                    if sm_id: cur_referenced_sm_ids.add(sm_id)
                    if sd_id: cur_referenced_sub_domain_ids.add(sd_id)
                    if d_id: cur_referenced_domain_ids.add(d_id)
                # diff: 在 referenced 里但不在当前容器列表
                existing_module_ids_set = {m.get('id') for m in modules}
                existing_sd_ids_set = {sd.get('id') for sd in sub_domains}
                existing_domain_ids_set = {d.get('id') for d in domains}
                need_sm = cur_referenced_sm_ids - existing_module_ids_set
                need_sd = cur_referenced_sub_domain_ids - existing_sd_ids_set
                need_d = cur_referenced_domain_ids - existing_domain_ids_set

                # [V1.2.4 2026-06-17] Phase 1: 添加外部 SM, 并从 SM 反推 SD → D
                # 原 bug: 外部 BO (version 1) 的 domain_id/sub_domain_id 为 NULL,
                #   V1.1.12 只从 BO 的 domain_id/sub_domain_id 收集, 无法发现外部容器。
                #   但外部 BO 有 service_module_id, 添加外部 SM 后可从 SM.sub_domain_id
                #   反推 SD → D, 完成容器链补全。
                if need_sm:
                    ph_sm = ','.join('?' * len(need_sm))
                    # [V1.2.8] 补全外部 SM 的 code + domain_name/sub_domain_name
                    sm_rows = _ds.execute(
                        f"""SELECT sm.id, sm.name, sm.code, sm.sub_domain_id,
                                   sd.name as sub_domain_name,
                                   d.name as domain_name,
                                   d.id as domain_id
                            FROM service_modules sm
                            LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                            LEFT JOIN domains d ON sd.domain_id = d.id
                            WHERE sm.id IN ({ph_sm})""",
                        list(need_sm)
                    ).fetchall()
                    for r in sm_rows:
                        modules.append({
                            'id': r[0], 'name': r[1], 'code': r[2] or '',
                            'sub_domain_id': r[3],
                            'sub_domain_name': r[4] or '',
                            'domain_name': r[5] or '',
                            'domain_id': r[6],
                            'is_external': True,
                        })
                        # [V1.2.4] 从 SM 的 sub_domain_id 反推 SD
                        if r[3]:
                            cur_referenced_sub_domain_ids.add(r[3])

                # [V1.2.4] Phase 2: 从反推的 sub_domain_ids 补外部 SD, 再从 SD 反推 D
                need_sd = cur_referenced_sub_domain_ids - existing_sd_ids_set
                if need_sd:
                    ph_sd = ','.join('?' * len(need_sd))
                    # [V1.2.8] 补全外部 SD 的 code + domain_name
                    sd_rows = _ds.execute(
                        f"""SELECT sd.id, sd.name, sd.code, sd.domain_id,
                                   d.name as domain_name
                            FROM sub_domains sd
                            LEFT JOIN domains d ON sd.domain_id = d.id
                            WHERE sd.id IN ({ph_sd})""",
                        list(need_sd)
                    ).fetchall()
                    for r in sd_rows:
                        sub_domains.append({
                            'id': r[0], 'name': r[1], 'code': r[2] or '',
                            'domain_id': r[3],
                            'domain_name': r[4] or '',
                            'is_external': True,
                        })
                        # [V1.2.4] 从 SD 的 domain_id 反推 D
                        if r[3]:
                            cur_referenced_domain_ids.add(r[3])

                # [V1.2.4] Phase 3: 从反推的 domain_ids 补外部 Domain
                need_d = cur_referenced_domain_ids - existing_domain_ids_set
                if need_d:
                    ph_d = ','.join('?' * len(need_d))
                    # [V1.2.8] 补全外部 Domain 的 code
                    d_rows = _ds.execute(
                        f"SELECT id, name, code, version_id FROM domains WHERE id IN ({ph_d})",
                        list(need_d)
                    ).fetchall()
                    for r in d_rows:
                        domains.append({
                            'id': r[0], 'name': r[1], 'code': r[2] or '',
                            'version_id': r[3],
                            'is_external': True,
                        })

                if need_sm or need_sd or need_d:
                    logger.info(
                        f'[v1.1.12+V1.2.4] chart view external containers: '
                        f'added_sm={len(need_sm) if need_sm else 0} '
                        f'added_sd={len(need_sd) if need_sd else 0} '
                        f'added_d={len(need_d) if need_d else 0}'
                    )
        except Exception as e:
            logger.warning(f'[bo_api.get_architecture_preview] external BO/containers ref fetch failed: {e}')

        # 计算 center_scope（中心范围的 BO code 列表）
        # [V1.2.9 修复] 无显式 hierarchyFilter 时，基于 dim scope 过滤后的 domains 计算
        # 之前：无 domain_id_list 等参数时 center_scope 为空，导致所有关系被标为 internal
        # 修复：用 DataPermissionInterceptor 过滤后的 domain ids 作为 fallback
        center_scope = []
        if bo_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('id') in bo_id_list]
        elif module_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('service_module_id') in module_id_list]
        elif sub_domain_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('sub_domain_id') in sub_domain_id_list]
        elif domain_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('domain_id') in domain_id_list]
        else:
            # [V1.2.9] 无显式过滤参数时，dim scope 过滤后的 domains 即为中心范围
            # DataPermissionInterceptor 已按用户 dim scope 过滤了 domains
            # 非 is_external 的 BO 都在用户 dim scope 内，即中心范围
            center_scope = [b.get('code', '') for b in business_objects if not b.get('is_external')]

        # ── Relation Classification（scope_type + category_type 下沉到后端）──
        # 构建 BO id → {domain_id, sub_domain_id, service_module_id} 映射
        bo_id_map = {}
        for b in business_objects:
            bo_id_map[b.get('id')] = {
                'domain_id': b.get('domain_id'),
                'sub_domain_id': b.get('sub_domain_id'),
                'service_module_id': b.get('service_module_id'),
            }

        # 确定哪些 BO 在范围内
        center_scope_set = set(center_scope)
        bo_code_map = {b.get('code'): b.get('id') for b in business_objects if b.get('code')}

        # 对每条 relationship 附加 scope_type 和 category_type
        for rel in relationships:
            src_code = rel.get('source_code') or rel.get('sourceCode')
            tgt_code = rel.get('target_code') or rel.get('targetCode')

            # 自环关系
            if src_code and tgt_code and src_code == tgt_code:
                rel['scope_type'] = 'external'
                rel['category_type'] = 'cross-domain'
                continue

            # 获取源和目标 BO 的层级信息
            src_bo_id = bo_code_map.get(src_code)
            tgt_bo_id = bo_code_map.get(tgt_code)
            src_info = bo_id_map.get(src_bo_id, {}) if src_bo_id else {}
            tgt_info = bo_id_map.get(tgt_bo_id, {}) if tgt_bo_id else {}

            # 计算 scope_type
            src_in_scope = src_code in center_scope_set if center_scope_set else True
            tgt_in_scope = tgt_code in center_scope_set if center_scope_set else True

            if src_in_scope and tgt_in_scope:
                scope_type = 'internal'
            elif src_in_scope or tgt_in_scope:
                scope_type = 'cross-boundary'
            else:
                scope_type = 'external'

            # 计算 category_type
            src_domain_id = src_info.get('domain_id')
            tgt_domain_id = tgt_info.get('domain_id')
            src_sub_domain_id = src_info.get('sub_domain_id')
            tgt_sub_domain_id = tgt_info.get('sub_domain_id')
            src_module_id = src_info.get('service_module_id')
            tgt_module_id = tgt_info.get('service_module_id')

            if src_domain_id and tgt_domain_id and src_domain_id != tgt_domain_id:
                category_type = 'cross-domain'
            elif src_sub_domain_id and tgt_sub_domain_id and src_sub_domain_id != tgt_sub_domain_id:
                category_type = 'same-domain-cross-subdomain'
            elif src_module_id and tgt_module_id and src_module_id != tgt_module_id:
                category_type = 'same-subdomain-cross-module'
            else:
                category_type = 'same-module'

            # 修正：外部关系但分类为同模块时，提升到更高级别
            if scope_type != 'internal' and category_type == 'same-module':
                if src_sub_domain_id and tgt_sub_domain_id and src_sub_domain_id != tgt_sub_domain_id:
                    category_type = 'same-domain-cross-subdomain'
                elif src_domain_id and tgt_domain_id and src_domain_id != tgt_domain_id:
                    category_type = 'cross-domain'

            rel['scope_type'] = scope_type
            rel['category_type'] = category_type

        # [V1.2.4→V1.2.9] 过滤 external 关系（对象范围外）
        # DataPermissionInterceptor V1.2.9 已过滤权限域外关系（source 和 target 都不在 dim scope 内）
        # 这里过滤的是对象范围外关系（source 和 target 都不在 center_scope 内）
        # 两层过滤互补:
        #   - 权限域外: source 和 target 都不在 dim scope (如库存管理→销售管理, 对采购管理用户)
        #   - 对象范围外: source 和 target 都不在 center_scope (如跨权限域但不在选中范围内)
        relationships = [r for r in relationships if r.get('scope_type') != 'external']

        # ── [V_NEW 2026-06-29] annotation 聚合 - 备注文本是辅助信息, 不影响主路径
        # 主线不受影响: 失败时所有 BO/Rel/SM/SD/D 都返回空 annotation_content/category
        # 这样前端 archDataConverter 即使没拿到字段也不会报错
        try:
            from meta.services.preview_service import aggregate_annotations_for_targets

            _ds_ann = _get_data_source()

            # BO annotations
            bo_ids = [b.get('id') for b in business_objects if b.get('id')]
            bo_ann = aggregate_annotations_for_targets('business_object', bo_ids, _ds_ann)
            for b in business_objects:
                ann = bo_ann.get(b.get('id'), {'contents': [], 'categories': []})
                b['annotation_contents'] = ann['contents']
                b['annotation_categories'] = ann['categories']

            # Relationship annotations
            rel_ids = [r.get('id') for r in relationships if r.get('id')]
            rel_ann = aggregate_annotations_for_targets('relationship', rel_ids, _ds_ann)
            for r in relationships:
                ann = rel_ann.get(r.get('id'), {'contents': [], 'categories': []})
                r['annotation_contents'] = ann['contents']
                r['annotation_categories'] = ann['categories']

            # SubDomain annotations
            sd_ids = [sd.get('id') for sd in sub_domains if sd.get('id')]
            sd_ann = aggregate_annotations_for_targets('sub_domain', sd_ids, _ds_ann)
            for sd in sub_domains:
                ann = sd_ann.get(sd.get('id'), {'contents': [], 'categories': []})
                sd['annotation_contents'] = ann['contents']
                sd['annotation_categories'] = ann['categories']

            # ServiceModule annotations
            sm_ids = [m.get('id') for m in modules if m.get('id')]
            sm_ann = aggregate_annotations_for_targets('service_module', sm_ids, _ds_ann)
            for m in modules:
                ann = sm_ann.get(m.get('id'), {'contents': [], 'categories': []})
                m['annotation_contents'] = ann['contents']
                m['annotation_categories'] = ann['categories']

            # Domain annotations
            d_ids = [d.get('id') for d in domains if d.get('id')]
            d_ann = aggregate_annotations_for_targets('domain', d_ids, _ds_ann)
            for d in domains:
                ann = d_ann.get(d.get('id'), {'contents': [], 'categories': []})
                d['annotation_contents'] = ann['contents']
                d['annotation_categories'] = ann['categories']
        except Exception as e:
            # 主线不受影响: annotation 聚合失败时, 给所有对象填空数组
            logger.warning(f'[bo_api.get_architecture_preview] annotation aggregation failed: {e}')
            for b in business_objects:
                b.setdefault('annotation_contents', [])
                b.setdefault('annotation_categories', [])
            for r in relationships:
                r.setdefault('annotation_contents', [])
                r.setdefault('annotation_categories', [])
            for sd in sub_domains:
                sd.setdefault('annotation_contents', [])
                sd.setdefault('annotation_categories', [])
            for m in modules:
                m.setdefault('annotation_contents', [])
                m.setdefault('annotation_categories', [])
            for d in domains:
                d.setdefault('annotation_contents', [])
                d.setdefault('annotation_categories', [])

        return jsonify({
            'success': True,
            'data': {
                'domains': domains,
                'sub_domains': sub_domains,
                'service_modules': modules,
                'business_objects': business_objects,
                'relationships': relationships,
                'center_scope': center_scope
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] architecture preview error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@bo_bp.route('/<object_type>/<int:obj_id>/state_transitions', methods=['GET'])
@login_required
def get_state_transitions(object_type, obj_id):
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404

    bo = _get_bo()
    result = bo.read(object_type, obj_id)
    if not result or not result.success:
        return jsonify({'success': False, 'message': '记录不存在'}), 404

    record = result.data if hasattr(result, 'data') else result

    state_transitions = []
    for rule in meta_obj.rules:
        if not hasattr(rule, 'state_field'):
            continue
        if not hasattr(rule, 'from_states') or not hasattr(rule, 'to_state'):
            continue

        current_state = record.get(rule.state_field) if isinstance(record, dict) else getattr(record, rule.state_field, None)
        is_available = current_state in rule.from_states

        ui_hints = getattr(rule, 'ui_hints', None)

        transition_info = {
            'id': rule.id,
            'name': rule.name,
            'stateField': rule.state_field,
            'fromStates': list(rule.from_states),
            'toState': rule.to_state,
            'currentState': current_state,
            'available': is_available,
            'label': ui_hints.label if ui_hints else rule.name,
            'icon': ui_hints.icon if ui_hints else '',
            'confirmMessage': ui_hints.confirm_message if ui_hints else '',
            'highlight': ui_hints.highlight if ui_hints else False,
            'hidden': ui_hints.hidden if ui_hints else False,
        }

        if rule.condition:
            transition_info['condition'] = rule.condition

        if not transition_info['hidden']:
            state_transitions.append(transition_info)

    return jsonify({
        'success': True,
        'data': state_transitions,
    })


@bo_bp.route('/<object_type>/<path:obj_id>/state_transitions', methods=['GET'])
@login_required
def get_state_transitions_by_string_id(object_type, obj_id):
    """支持字符串ID的状态转换路由"""
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404

    bo = _get_bo()
    result = bo.read(object_type, obj_id)
    if not result or not result.success:
        return jsonify({'success': False, 'message': '记录不存在'}), 404

    record = result.data if hasattr(result, 'data') else result

    state_transitions = []
    for rule in meta_obj.rules:
        if not hasattr(rule, 'state_field'):
            continue
        if not hasattr(rule, 'from_states') or not hasattr(rule, 'to_state'):
            continue

        current_state = record.get(rule.state_field) if isinstance(record, dict) else getattr(record, rule.state_field, None)
        is_available = current_state in rule.from_states

        ui_hints = getattr(rule, 'ui_hints', None)

        transition_info = {
            'id': rule.id,
            'name': rule.name,
            'stateField': rule.state_field,
            'fromStates': list(rule.from_states),
            'toState': rule.to_state,
            'currentState': current_state,
            'available': is_available,
            'label': ui_hints.label if ui_hints else rule.name,
            'icon': ui_hints.icon if ui_hints else '',
            'confirmMessage': ui_hints.confirm_message if ui_hints else '',
            'highlight': ui_hints.highlight if ui_hints else False,
            'hidden': ui_hints.hidden if ui_hints else False,
        }

        if rule.condition:
            transition_info['condition'] = rule.condition

        if not transition_info['hidden']:
            state_transitions.append(transition_info)

    return jsonify({
        'success': True,
        'data': state_transitions,
    })


# ── Meta / UI Config ──

@meta_v2_bp.route('/<object_type>/ui-config', methods=['GET'])
@login_required
def get_ui_config(object_type):
    try:
        bo = _get_bo()
        config = bo.get_ui_config(object_type)
        if config:
            json_safe_config = _make_json_safe(config)
            return jsonify({'success': True, 'data': json_safe_config})
        return jsonify({'success': False, 'message': f'Unknown object type: {object_type}'}), 404
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] ui-config error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


def _make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_json_safe(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    elif hasattr(obj, '__dict__'):
        return _make_json_safe(obj.__dict__)
    else:
        return str(obj)


@meta_v2_bp.route('/<object_type>/schema', methods=['GET'])
@login_required
def get_object_schema(object_type):
    try:
        bo = _get_bo()
        schema = bo.get_schema(object_type)
        if not schema:
            return jsonify({'success': False, 'message': f'Unknown object type: {object_type}'}), 404

        meta_obj = registry.get(object_type)
        if meta_obj:
            actions = getattr(meta_obj, 'actions', None)
            if actions:
                action_list = []
                if isinstance(actions, dict):
                    for name, action in actions.items():
                        a = _to_json_dict(action)
                        a['name'] = name
                        action_list.append(a)
                elif isinstance(actions, list):
                    for action in actions:
                        a = _to_json_dict(action)
                        action_list.append(a)
                schema['actions'] = action_list

            if hasattr(meta_obj, 'hierarchy') and meta_obj.hierarchy:
                schema['hierarchy'] = meta_obj.hierarchy

            if hasattr(meta_obj, 'context') and meta_obj.context:
                schema['context'] = meta_obj.context

            if hasattr(meta_obj, 'cascade_select') and meta_obj.cascade_select:
                schema['cascade_select'] = meta_obj.cascade_select

            if object_type == 'relationship':
                scope_rules = _load_scope_rules()
                if scope_rules:
                    schema['scope_rules'] = scope_rules

            if object_type in ['domain', 'sub_domain', 'service_module', 'business_object']:
                annotation_categories = _load_annotation_categories()
                if annotation_categories:
                    schema['annotations'] = {
                        'enabled': True,
                        'categories': annotation_categories
                    }

        return jsonify({'success': True, 'data': schema})
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] schema error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@meta_v2_bp.route('/<object_type>/full', methods=['GET'])
@login_required
def get_meta_full(object_type):
    """元数据合并 API - 一次返回 ui_config + schema + field_policies"""
    try:
        bo = _get_bo()

        # 获取 ui_config
        ui_config = bo.get_ui_config(object_type)

        # 获取 schema
        schema = bo.get_schema(object_type)

        # 获取 field_policies
        meta_obj = registry.get(object_type)
        field_policies = {}
        if meta_obj:
            context = request.args.get('context', 'read')
            mutability = request.args.get('mutability')
            engine = FieldPolicyEngine(meta_object=meta_obj)
            object_context = ObjectContext(mutability=mutability, object_type=object_type)
            policy_context = PolicyContext(object_context=object_context, action=context)
            for f in meta_obj.fields:
                field_policies[f.id] = {
                    'editable': engine.is_field_editable(f.id, policy_context),
                    'visible': engine.is_field_visible(f.id, policy_context),
                    'required': engine.is_field_required(f.id, policy_context),
                }

        return jsonify({
            'success': True,
            'data': {
                'ui_config': _make_json_safe(ui_config) if ui_config else {},
                'schema': schema,
                'field_policies': field_policies,
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] meta-full error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] [NEW] v1.2 / FR-2.4: 全量 OpenAPI 端点（Action + BO CRUD + Meta）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@meta_v2_bp.route('/_openapi.json', methods=['GET'])
def get_full_openapi():
    """
    [DECORATIVE] [NEW] v1.2 / FR-2.4: 全量 OpenAPI 规范（Action + BO CRUD + Meta）

    与 bo_action_api._openapi.json（Action-only）共存。
    复用 _generate_action_openapi + _generate_bo_crud_paths + _generate_bo_schema。
    """
    try:
        from flask import request as _req
        from meta.api.bo_action_api import _generate_action_openapi
        from meta.core.models import registry

        base_url = _req.host_url.rstrip('/')

        # 1. Action OpenAPI（从 bo_action_api 复用）
        action_spec = _generate_action_openapi(base_url)

        # 2. BO CRUD paths（防御性检查 registry.all()）
        meta_objects = list(registry.all()) if hasattr(registry, 'all') else []
        bo_paths = _generate_bo_crud_paths(meta_objects)

        # 3. BO schemas
        bo_schemas = {
            obj.id: _generate_bo_schema(obj)
            for obj in meta_objects
            if getattr(obj, 'table_name', None)
        }

        # 4. 合并
        spec = action_spec.copy()
        spec['paths'].update(bo_paths)
        spec['components']['schemas'].update(bo_schemas)
        spec['info']['title'] = 'Excel-to-Diagram Full API'
        spec['info']['version'] = 'v2.0'
        spec['info']['description'] = '全量 OpenAPI 规范（Action + BO CRUD + Meta）'

        return jsonify(spec)
    except Exception as e:
        import traceback
        return jsonify({
            'error': type(e).__name__,
            'message': str(e),
            'traceback': traceback.format_exc(),
        }), 500


@meta_v2_bp.route('/<object_type>/field-policies', methods=['GET'])
@login_required
def get_field_policies(object_type):
    """获取字段策略评估结果"""
    try:
        context = request.args.get('context', 'read')
        mutability = request.args.get('mutability', None)

        meta_obj = registry.get(object_type)
        if not meta_obj:
            return jsonify({'success': False, 'message': f'Object type {object_type} not found'}), 404

        engine = FieldPolicyEngine(meta_object=meta_obj)

        object_context = ObjectContext(mutability=mutability, object_type=object_type)
        policy_context = PolicyContext(object_context=object_context, action=context)

        field_ids = [f.id for f in meta_obj.fields]
        editable_fields = engine.get_editable_fields(field_ids, policy_context)
        readonly_fields = engine.get_readonly_fields(field_ids, policy_context)

        # [DECORATIVE] [NEW] v1.2 / FR-4.5a: 提取 conditional_required 规则（从 field.constraints）
        # 供前端 useFieldPolicy.requiredMap 消费
        policies = {}
        for field_id in field_ids:
            field_def = None
            for f in meta_obj.fields:
                if f.id == field_id:
                    field_def = f
                    break
            conditional_required = []
            if field_def:
                constraints = getattr(field_def, 'constraints', None)
                if isinstance(constraints, list):
                    for c in constraints:
                        if isinstance(c, dict) and c.get('type') == 'conditional_required':
                            conditional_required.append({
                                'condition': c.get('condition', ''),
                                'message': c.get('message', ''),
                                'severity': c.get('severity', 'error'),
                            })
                elif isinstance(constraints, dict) and constraints.get('type') == 'conditional_required':
                    conditional_required.append({
                        'condition': constraints.get('condition', ''),
                        'message': constraints.get('message', ''),
                        'severity': constraints.get('severity', 'error'),
                    })
            policies[field_id] = {
                'editable': field_id in editable_fields,
                'visible': engine.is_field_visible(field_id, policy_context),
                'required': engine.is_field_required(field_id, policy_context),
                'conditional_required': conditional_required,  # [DECORATIVE] FR-4.5a
            }

        return jsonify({
            'success': True,
            'data': policies
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] field-policies error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


def _load_scope_rules():
    """加载 scope_rules 配置"""
    try:
        from meta.core.virtual_field_transform import load_scope_rules_from_ref
        rules = load_scope_rules_from_ref()
        if rules:
            return [
                {
                    'id': r.get('id'),
                    'name': r.get('name'),
                    'description': r.get('description', ''),
                    'rule': r.get('rule', ''),
                    'color': r.get('color', '#999999')
                }
                for r in rules
            ]
    except Exception as e:
        logger.warning(f"[bo_api] Failed to load scope_rules: {e}")
    return None


def _load_annotation_categories():
    """加载备注分类配置"""
    try:
        ds = _get_data_source()
        cursor = ds.execute(
            "SELECT code, name, name_en FROM enum_values WHERE enum_type_id = 'annotation_category' AND is_active = 1 ORDER BY sort_order"
        )
        rows = cursor.fetchall()
        return [
            {'code': r[0], 'name': r[1], 'name_en': r[2] if len(r) > 2 else r[1]}
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"[bo_api] Failed to load annotation categories: {e}")
    return None


@meta_v2_bp.route('/<object_type>/view-config', methods=['GET'])
@meta_v2_bp.route('/<object_type>/view-config/<view_name>', methods=['GET'])
@login_required
def get_view_config(object_type, view_name='default'):
    try:
        from meta.services.view_config_service import view_config_service
        from meta.api.meta_api import _dataclass_to_dict, _ensure_fresh_meta

        # [BUG-V036 2026-06-29] 调用 _ensure_fresh_meta() 确保 YAML 修改被热加载
        # 否则 DEV_MODE=False 时 YAML 修改不会生效, 导致 column 的 value_help/filter_type 等配置丢失
        _ensure_fresh_meta()

        # 先获取原始配置
        original_config = view_config_service.get_view_config(object_type, view_name)
        logger.info(f"[bo_api] original_config: {original_config}")
        logger.info(f"[bo_api] original_config.list: {original_config.list if original_config else 'None'}")
        logger.info(f"[bo_api] original_config.list.actions: {original_config.list.actions if original_config and original_config.list else 'None'}")
        
        config = view_config_service.get_or_build_view_config(object_type, view_name)
        
        if not config:
            return jsonify({'success': False, 'message': f'View config not found for: {object_type}'}), 404
        
        logger.info(f"[bo_api] config.list.actions: {config.list.actions}")
        logger.info(f"[bo_api] config.list.actions length: {len(config.list.actions)}")
        
        data = _dataclass_to_dict(config)

        bo = _get_bo()
        ui_config = bo.get_ui_config(object_type)
        if ui_config.get('fields'):
            data['fields'] = ui_config['fields']
        # [FIX 2026-06-09] 合并 associations 元数据。
        # 原因：role.yaml 的 assigned_groups.readonly: true 需要传到前端
        #       DetailPage.vue 用 tab.readonly || assocDef?.readonly 判定，
        #       若不合并 associations → assocDef 找不到 → readonly 永远 false
        #       → AssociationSection.vue 仍显示"移除"按钮。
        if ui_config.get('associations'):
            data['associations'] = ui_config['associations']

        logger.info(f"[bo_api] data['list']['actions']: {data['list']['actions']}")
        logger.info(f"[bo_api] data['list']['actions'] length: {len(data['list']['actions'])}")
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] view-config error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@meta_v2_bp.route('/<object_type>/views', methods=['GET'])
@login_required
def list_view_configs(object_type):
    try:
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return jsonify({'success': False, 'message': f'Unknown object type: {object_type}'}), 404

        views = [{'name': 'default', 'label': '默认视图'}]

        view_configs = getattr(meta_obj, 'view_configs', None)
        if view_configs and isinstance(view_configs, dict):
            for name, config in view_configs.items():
                views.append({
                    'name': name,
                    'label': config.get('label', name)
                })

        ui_view_config = getattr(meta_obj, 'ui_view_config', None)
        if ui_view_config and isinstance(ui_view_config, dict):
            configured_views = ui_view_config.get('views', {})
            for name, config in configured_views.items():
                if not any(v['name'] == name for v in views):
                    views.append({
                        'name': name,
                        'label': config.get('label', name)
                    })

        return jsonify({'success': True, 'data': {'views': views}})
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] list views error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


def _to_json_dict(obj) -> dict:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, '__dict__'):
        result = {}
        for k, v in obj.__dict__.items():
            if hasattr(v, '__dict__') and not isinstance(v, (str, int, float, bool, list, dict)):
                result[k] = str(v)
            elif isinstance(v, (list, dict, str, int, float, bool)) or v is None:
                result[k] = v
            else:
                result[k] = str(v)
        return result
    return {'value': str(obj)}


@meta_v2_bp.route('/hierarchy/tree', methods=['GET'])
@login_required
def get_hierarchy_tree():
    """
    获取层级树

    Query params:
        - object_type: 起始对象类型（可选，默认从顶层开始）
        - parent_id: 父节点ID（可选，用于构建子树）
        - version_id: 版本ID（可选，用于版本上下文过滤）
        - levels: 包含的层级列表（可选，逗号分隔）

    Returns:
        {
            "success": true,
            "data": {
                "tree": [...]
            }
        }
    """
    try:
        from meta.services.hierarchy_service import HierarchyService

        object_type = request.args.get('object_type')
        parent_id = request.args.get('parent_id', type=int)
        version_id = request.args.get('version_id', type=int)
        levels_str = request.args.get('levels')
        include_relation_counts = request.args.get('include_counts', 'true').lower() == 'true'

        levels = None
        if levels_str:
            levels = [l.strip() for l in levels_str.split(',') if l.strip()]

        svc = HierarchyService()
        tree = svc.build_tree(
            object_type=object_type,
            parent_id=parent_id,
            version_id=version_id,
            levels=levels,
            include_relation_counts=include_relation_counts
        )

        return jsonify({
            'success': True,
            'data': {
                'tree': tree,
                'levels': svc.get_levels()
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] hierarchy tree error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@meta_v2_bp.route('/hierarchy/levels', methods=['GET'])
@login_required
def get_hierarchy_levels():
    """获取层级定义列表"""
    try:
        from meta.services.hierarchy_service import HierarchyService
        svc = HierarchyService()
        levels = svc.get_levels()
        return jsonify({
            'success': True,
            'data': {'levels': levels}
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def _infer_target_type(src_type: str, association_name: str) -> str:
    from meta.core.metadata_resolver import MetadataResolver
    return MetadataResolver.get_association_target(src_type, association_name)


# ── Role Unified Permissions (v2) ──

role_v2_bp = Blueprint('role_v2', __name__, url_prefix='/api/v2/roles')


@role_v2_bp.route('/<int:role_id>/unified-permissions', methods=['GET'])
@login_required
def get_role_unified_permissions(role_id):
    """获取角色的统一权限（菜单权限矩阵）

    权限计算公式: effective = (auto_menu ∪ manual_include) - manual_exclude
    - auto_menu: 已分配菜单的 required_permissions 自动派生
    - manual_include: role_permissions 中 granted=1 的记录
    - manual_exclude: role_permissions 中 granted=0 的记录
    """
    try:
        from meta.services.menu_permission_service import MenuPermissionService

        ds = _get_data_source()
        menu_service = MenuPermissionService(ds)

        # 获取角色已分配的菜单
        cursor = ds.execute("""
            SELECT rmp.menu_code, m.menu_name, m.menu_path, m.icon, m.sort_order
            FROM role_menu_permissions rmp
            JOIN menus m ON rmp.menu_code = m.menu_code
            WHERE rmp.role_id = ?
            ORDER BY m.sort_order, m.menu_name
        """, [role_id])

        assigned_menus = {}
        for row in cursor.fetchall():
            menu_code = row[0]
            assigned_menus[menu_code] = {
                'menu_code': menu_code,
                'display_name': row[1],
                'menu_path': row[2],
                'icon': row[3],
                'assigned': True,
                'required_permissions': []
            }

        # 查询角色的手动权限覆盖（include/exclude）
        cursor = ds.execute("""
            SELECT rp.permission_id, rp.granted, p.code
            FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = ?
        """, [role_id])
        manual_overrides = {}  # {perm_code: {'granted': bool, 'source': str}}
        for row in cursor.fetchall():
            manual_overrides[row[2]] = {
                'granted': bool(row[1]),
                'source': 'include' if bool(row[1]) else 'exclude'
            }

        # 获取所有菜单（[单一事实源] 与 LandingPage 末端节点一致）
        cursor = ds.execute("""
            SELECT menu_code, menu_name, menu_path, icon, sort_order,
                   required_permissions, required_any_permission, data_permission_hint
            FROM menus
            WHERE is_active = 1 AND show_in_sidebar = 1
              AND menu_code != 'dashboard'
              AND menu_code NOT IN (
                SELECT DISTINCT parent_menu FROM menus
                WHERE parent_menu IS NOT NULL AND parent_menu != ''
                  AND is_active = 1 AND show_in_sidebar = 1
              )
              AND menu_path IS NOT NULL AND menu_path != ''
              AND (parent_menu IS NULL OR parent_menu = ''
                   OR parent_menu NOT IN (
                     SELECT menu_code FROM menus
                     WHERE page_type = 'multi_object_hub' AND is_active = 1
                   ))
            ORDER BY sort_order, menu_name
        """)

        # 动作分组配置
        ACTION_GROUPS = {
            'view':   {'label': '查看', 'actions': ['read', 'list']},
            'edit':   {'label': '编辑', 'actions': ['read', 'list', 'create', 'update']},
            'manage': {'label': '管理', 'actions': ['read', 'list', 'create', 'update', 'delete']},
        }
        # 独立动作列表
        STANDALONE_ACTIONS = ['export', 'import', 'assign', 'unassign',
                              'associate', 'dissociate', 'grant', 'revoke']

        # 动作标签映射
        action_labels = {
            'read': '查看', 'create': '创建', 'update': '编辑',
            'delete': '删除', 'list': '列表', 'manage': '管理',
            'export': '导出', 'import': '导入', 'assign': '分配',
            'unassign': '取消分配', 'associate': '关联', 'dissociate': '取消关联',
            'grant': '授权', 'revoke': '撤销',
        }

        menus = []
        for row in cursor.fetchall():
            menu_code = row[0]
            required_perm_codes = []
            if row[5]:  # required_permissions
                try:
                    import json
                    required_perm_codes = json.loads(row[5]) if isinstance(row[5], str) else row[5]
                except:
                    pass

            # 转换为前端期望的格式: [{code, label, granted, source}]
            is_assigned = menu_code in assigned_menus
            required_perms = []
            for perm_code in required_perm_codes:
                # 解析权限代码: "domain:read" -> domain, read
                parts = perm_code.split(':')
                resource = parts[0] if len(parts) > 0 else perm_code
                action = parts[1] if len(parts) > 1 else 'read'

                # 计算权限状态
                if perm_code in manual_overrides:
                    override = manual_overrides[perm_code]
                    granted = override['granted']
                    source = override['source']
                elif is_assigned:
                    granted = True
                    source = 'auto'
                else:
                    granted = False
                    source = ''

                # 生成友好的标签
                label = f'{resource.title()} - {action_labels.get(action, action)}'

                required_perms.append({
                    'code': perm_code,
                    'label': label,
                    'granted': granted,
                    'source': source
                })



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            # 按 BO 分组推导动作分组状态
            # 收集每个 resource 的权限状态
            resource_perms = {}  # {resource: {action: {granted, source}}}
            for perm_code in required_perm_codes:
                parts = perm_code.split(':')
                resource = parts[0] if len(parts) > 0 else perm_code
                action = parts[1] if len(parts) > 1 else 'read'
                if resource not in resource_perms:
                    resource_perms[resource] = {}
                # 获取该权限的计算结果
                for p in required_perms:
                    if p['code'] == perm_code:
                        resource_perms[resource][action] = {
                            'granted': p['granted'],
                            'source': p['source']
                        }
                        break

            # 推导动作分组状态
            bo_permission_groups = []
            for resource, actions_map in resource_perms.items():
                groups = {}
                for group_key, group_def in ACTION_GROUPS.items():
                    group_actions = group_def['actions']
                    # 检查该 BO 是否有这些动作的权限
                    available_actions = [a for a in group_actions if a in actions_map]
                    if not available_actions:
                        continue  # 该 BO 没有此分组的动作

                    # 分组 granted = 所有可用动作都 granted
                    group_granted = all(
                        actions_map[a]['granted'] for a in available_actions
                    )

                    # 分组 source 推导
                    sources = set(
                        actions_map[a]['source'] for a in available_actions
                    )
                    if 'exclude' in sources:
                        group_source = 'exclude'
                    elif 'include' in sources:
                        group_source = 'include'
                    elif 'auto' in sources:
                        group_source = 'auto'
                    else:
                        group_source = ''

                    groups[group_key] = {
                        'granted': group_granted,
                        'source': group_source
                    }

                # 独立动作
                standalone_perms = []
                for action_key in STANDALONE_ACTIONS:
                    if action_key in actions_map:
                        standalone_perms.append({
                            'action': action_key,
                            'label': action_labels.get(action_key, action_key),
                            'granted': actions_map[action_key]['granted'],
                            'source': actions_map[action_key]['source']
                        })

                bo_permission_groups.append({
                    'bo_id': resource,
                    'bo_name': resource.title(),
                    'groups': groups,
                    'standalone': standalone_perms
                })

            data_hint = None
            if row[7]:  # data_permission_hint
                try:
                    import json
                    data_hint = json.loads(row[7]) if isinstance(row[7], str) else row[7]
                except:
                    pass

            menus.append({
                'menu_code': menu_code,
                'display_name': row[1],
                'menu_path': row[2],
                'icon': row[3],
                'assigned': is_assigned,
                'required_permissions': required_perms,
                'bo_permission_groups': bo_permission_groups,
                'has_data_scope': bool(row[6]),
                'data_permission_hint': data_hint
            })

        # 获取角色信息
        cursor = ds.execute("SELECT id, code, name FROM roles WHERE id = ?", [role_id])
        role_row = cursor.fetchone()
        role_info = None
        if role_row:
            role_info = {'id': role_row[0], 'code': role_row[1], 'name': role_row[2]}

        return jsonify({
            'success': True,
            'data': {
                'role': role_info,
                'menus': menus,
                'total_count': len(menus),
                'assigned_count': len(assigned_menus)
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] unified-permissions error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@role_v2_bp.route('/<int:role_id>/menu-permissions', methods=['PUT'])
@login_required
def update_role_menu_permissions(role_id):
    """更新角色的菜单权限和功能权限

    请求体:
    {
        "menu_codes": ["architecture_data", "system_management"],
        "permissions": [
            {"code": "domain:update", "granted": false},   // exclude
            {"code": "product:create", "granted": true}     // include
        ]
    }

    采用全量替换策略：DELETE 该角色所有 role_permissions 记录，再 INSERT 请求中的手动权限。
    """
    try:
        ds = _get_data_source()

        # 获取角色信息
        cursor = ds.execute("SELECT is_system FROM roles WHERE id = ?", [role_id])
        role_row = cursor.fetchone()
        if not role_row:
            return jsonify({'success': False, 'message': '角色不存在，请检查后重试'}), 404
        if role_row[0]:
            return jsonify({'success': False, 'message': '系统内置角色不能修改'}), 400

        data = request.get_json(silent=True) or {}
        menu_codes = data.get('menu_codes', [])
        permissions = data.get('permissions', [])

        with ds.transaction():
            # 1. 保存菜单分配
            ds.execute("DELETE FROM role_menu_permissions WHERE role_id = ?", [role_id])
            for menu_code in menu_codes:
                ds.execute(
                    "INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)",
                    [role_id, menu_code]
                )

            # 2. 全量替换手动权限 include/exclude
            ds.execute("DELETE FROM role_permissions WHERE role_id = ?", [role_id])
            for perm in permissions:
                perm_code = perm.get('code', '')
                granted = perm.get('granted', True)
                cursor = ds.execute("SELECT id FROM permissions WHERE code = ?", [perm_code])
                perm_row = cursor.fetchone()
                if perm_row:
                    ds.execute("""
                        INSERT INTO role_permissions (role_id, permission_id, granted, created_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """, [role_id, perm_row[0], 1 if granted else 0])

        # [FIX 2026-06-12] 角色 v2 菜单权限审计日志: 关联到角色对象
        write_permission_config_audit(
            action='UPDATE',
            object_type='role_v2_menu_permissions',
            object_id=role_id,
            data={'menu_codes': menu_codes, 'permission_count': len(permissions)},
            parent_object_type='role',
            parent_object_id=role_id,
        )

        return jsonify({
            'success': True,
            'message': f'已更新 {len(menu_codes)} 个菜单权限和 {len(permissions)} 个功能权限'
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] update-menu-permissions error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── Permission Rules (v2) ──

permission_rule_v2_bp = Blueprint('permission_rule_v2', __name__, url_prefix='/api/v2/permission-rules')


@permission_rule_v2_bp.route('', methods=['GET'])
@login_required
def list_permission_rules_v2():
    """获取权限规则列表"""
    try:
        from meta.services.condition_permission_service import ConditionPermissionService
        from meta.core.bo_framework import bo_framework
        
        service = ConditionPermissionService(bo_framework._data_source)
        
        role_id = request.args.get('role_id', type=int)
        
        if role_id:
            rules = service.get_rules_by_role(role_id)
        else:
            rules = service.get_all_rules()
        
        return jsonify({'success': True, 'data': rules})
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] list-permission-rules-v2 error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_v2_bp.route('', methods=['POST'])
@login_required
def create_permission_rule_v2():
    """创建权限规则"""
    try:
        from meta.services.condition_permission_service import ConditionPermissionService
        from meta.core.bo_framework import bo_framework
        
        service = ConditionPermissionService(bo_framework._data_source)
        
        data = request.get_json(silent=True) or {}
        
        required_fields = ['role_id', 'resource_type', 'condition']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} 是必填字段'}), 400
        
        # 获取当前用户
        current_user = getattr(g, 'current_user', None) or {}
        user_id = current_user.get('user_id')
        
        rule_data = {
            'role_id': data.get('role_id'),
            'resource_type': data.get('resource_type'),
            'condition': data.get('condition'),
            'permission_level': data.get('permission_level', 'read'),
            'is_denied': data.get('is_denied', False),
            'inherit_to_children': data.get('inherit_to_children', True),
            'propagate_to_parents': data.get('propagate_to_parents', True),
            'created_by': user_id
        }
        
        rule_id = service.create_rule(rule_data)
        
        return jsonify({
            'success': True,
            'data': {'id': rule_id},
            'message': '权限规则创建成功'
        }), 201
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] create-permission-rule-v2 error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_v2_bp.route('/<int:rule_id>', methods=['PUT'])
@login_required
def update_permission_rule_v2(rule_id):
    """更新权限规则"""
    try:
        from meta.services.condition_permission_service import ConditionPermissionService
        from meta.core.bo_framework import bo_framework
        
        service = ConditionPermissionService(bo_framework._data_source)
        
        data = request.get_json(silent=True) or {}
        
        success = service.update_rule(rule_id, data)
        
        if success:
            return jsonify({'success': True, 'message': '权限规则更新成功'})
        return jsonify({'success': False, 'message': '更新失败'}), 400
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] update-permission-rule-v2 error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_v2_bp.route('/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_permission_rule_v2(rule_id):
    """删除权限规则"""
    try:
        from meta.services.condition_permission_service import ConditionPermissionService
        from meta.core.bo_framework import bo_framework
        
        service = ConditionPermissionService(bo_framework._data_source)
        
        success = service.delete_rule(rule_id)
        
        if success:
            return jsonify({'success': True, 'message': '权限规则删除成功'})
        return jsonify({'success': False, 'message': '删除失败'}), 400
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] delete-permission-rule-v2 error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] [NEW] v1.2 / FR-2.2 / FR-2.3: OpenAPI 工具函数（被 FR-2.4 全量端点调用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_TYPE_MAP = {
    'string': 'string', 'text': 'string', 'integer': 'integer',
    'float': 'number', 'boolean': 'boolean', 'date': 'string',
    'datetime': 'string', 'json': 'object',
}


def _map_field_type(field_type) -> str:
    """将内部字段类型映射为 OpenAPI/JSON Schema 类型（兼容 enum 和 str）"""
    # 兼容 FieldType enum（.value / .name）和 str
    if hasattr(field_type, 'value'):
        field_type = field_type.value
    return _TYPE_MAP.get(str(field_type), 'string')


def _generate_bo_schema(meta_object) -> dict:
    """
    [DECORATIVE] [NEW] v1.2 / FR-2.3: 将 MetaObject 转换为 OpenAPI components/schemas 子对象

    防御: 用 getattr(field, 'xxx', None) 处理字段可能缺失的属性
    """
    properties = {}
    required = []
    for field in meta_object.fields:
        # MetaField 用 .field_type（FieldType enum），不是 .type
        field_type = getattr(field, 'field_type', None) or getattr(field, 'type', None)
        prop = {"type": _map_field_type(field_type)}
        if getattr(field, 'description', None):
            prop["description"] = field.description
        if getattr(field, 'enum_values', None):
            # [DECORATIVE] [NEW] v1.2 / bug #4 fix: 兼容 enum_values 元素可能是 str 或 dict
            enum_list = []
            for v in field.enum_values:
                if isinstance(v, dict):
                    enum_list.append(v.get('value'))
                else:
                    enum_list.append(v)  # 兼容 str / int
            if enum_list:
                prop["enum"] = enum_list
        # ui 可能是 dict 或 UIAnnotation 对象
        ui = getattr(field, 'ui', None)
        if isinstance(ui, dict):
            relation = ui.get('relation')
            display_field = ui.get('display_field')
        else:
            relation = getattr(ui, 'relation', None) if ui else None
            display_field = getattr(ui, 'display_field', None) if ui else None
        if relation:
            prop["x-relation"] = relation
            prop["x-display-field"] = display_field
        properties[field.id] = prop
        if field.required:
            required.append(field.id)
    return {
        "type": "object",
        "properties": properties,
        "required": required or None,
    }


def _generate_bo_crud_paths(meta_objects) -> dict:
    """
    [DECORATIVE] [NEW] v1.2 / FR-2.2: 为每个 BO 类型生成 7 个标准 CRUD 端点的 OpenAPI path 描述

    端点:
    - GET    /api/v2/bo/{type}            列表
    - POST   /api/v2/bo/{type}            创建
    - GET    /api/v2/bo/{type}/{id}       详情
    - PUT    /api/v2/bo/{type}/{id}       更新
    - DELETE /api/v2/bo/{type}/{id}       删除
    - POST   /api/v2/bo/{type}/deep       深度插入
    - POST   /api/v2/bo/{type}/batch-delete  批量删除
    """
    paths = {}
    for obj in meta_objects:
        if not getattr(obj, 'table_name', None):
            continue
        type_name = obj.id
        base = f'/api/v2/bo/{type_name}'
        type_tag = f'BO/{type_name}'

        paths[base] = {
            'get': {
                'operationId': f'bo_{type_name}_list',
                'summary': f'查询 {getattr(obj, "display_name", None) or type_name} 列表',
                'tags': [type_tag],
                'parameters': [
                    {'name': 'page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
                    {'name': 'page_size', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
                    {'name': 'order_by', 'in': 'query', 'schema': {'type': 'string'}},
                    {'name': 'search', 'in': 'query', 'schema': {'type': 'string'}},
                ],
                'responses': {
                    '200': {'description': '列表数据', 'content': {'application/json': {'schema': {'type': 'object', 'properties': {'items': {'type': 'array'}, 'total': {'type': 'integer'}}}}}}
                },
            },
            'post': {
                'operationId': f'bo_{type_name}_create',
                'summary': f'创建 {getattr(obj, "display_name", None) or type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {
                        'application/json': {
                            'schema': {'$ref': f'#/components/schemas/{type_name}'}
                        }
                    }
                },
                'responses': {
                    '201': {'description': '已创建'},
                    '400': {'description': '参数错误'},
                },
            },
        }
        paths[f'{base}/{{id}}'] = {
            'get': {
                'operationId': f'bo_{type_name}_get',
                'summary': f'获取 {type_name} 详情',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'responses': {
                    '200': {'description': '详情数据', 'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}},
                    '404': {'description': '未找到'},
                },
            },
            'put': {
                'operationId': f'bo_{type_name}_update',
                'summary': f'更新 {type_name}',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'requestBody': {
                    'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}
                },
                'responses': {
                    '200': {'description': '已更新'},
                    '400': {'description': '参数错误'},
                    '404': {'description': '未找到'},
                },
            },
            'delete': {
                'operationId': f'bo_{type_name}_delete',
                'summary': f'删除 {type_name}',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'responses': {
                    '204': {'description': '已删除'},
                    '404': {'description': '未找到'},
                },
            },
        }
        paths[f'{base}/deep'] = {
            'post': {
                'operationId': f'bo_{type_name}_deep_create',
                'summary': f'深度插入 {type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}
                },
                'responses': {
                    '201': {'description': '已深度插入'},
                },
            }
        }
        paths[f'{base}/batch-delete'] = {
            'post': {
                'operationId': f'bo_{type_name}_batch_delete',
                'summary': f'批量删除 {type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {'application/json': {'schema': {
                        'type': 'object',
                        'properties': {'ids': {'type': 'array', 'items': {'type': 'string'}}}
                    }}}
                },
                'responses': {
                    '200': {'description': '已批量删除'},
                },
            }
        }
    return paths

