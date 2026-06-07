# -*- coding: utf-8 -*-
"""
GraphQL 协议层 - M9 Phase D1+D2（3 entity POC）

设计原则（关注现有代码 + 减少影响）：
- 0 新依赖（不引入 graphql-core / strawberry / graphene）
- 0 修改 server.py 主体（仅末尾追加 1 个 blueprint）
- 100% 复用 bo_framework（已有 18+ 拦截器链）
- 100% 复用现有 v1+v2 API
- 3 entity (user + role + user_group) + 6 query (每 entity × 2: getById + list)
- 0 mutation / 0 subscription（最小化破坏）

D2 增量（D1 → D2）：
- 从 1 entity 扩展到 3 entity
- 重构为 entity-based 配置（DRY）
- 自动注册 6 个 root query

参考：
- spec v1.0.0 §5 (后端实施)
- spec v1.0.0 §13 (不破坏现有 - 1 处新增)
- Phase B PR 4 注入式依赖（callPost 来源可替换）
"""
import re
import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

graphql_bp = Blueprint('graphql_v3', __name__, url_prefix='/graphql')


# =============================================================================
# 1. Entity Schema Registry（DRY - 单一事实源）
# =============================================================================
# key: PascalCase GraphQL type name
# value: {
#   object_type: snake_case object_type (bo_framework / DB)
#   fields: list of GraphQL fields (PascalCase)
#   field_map: snake_case → camelCase 映射
# }

ENTITY_SCHEMAS = {
    'User': {
        'object_type': 'user',
        'fields': ['id', 'username', 'displayName', 'email', 'status', 'createdAt', 'updatedAt', 'lastLoginAt'],
        'field_map': {
            'id': 'id',
            'username': 'username',
            'display_name': 'displayName',
            'email': 'email',
            'status': 'status',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
            'last_login_at': 'lastLoginAt',
        },
    },
    'Role': {
        'object_type': 'role',
        'fields': ['id', 'code', 'name', 'description', 'createdAt', 'updatedAt'],
        'field_map': {
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'description': 'description',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    },
    'UserGroup': {
        'object_type': 'user_group',
        'fields': ['id', 'code', 'name', 'description', 'createdAt', 'updatedAt'],
        'field_map': {
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'description': 'description',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    },
    'Product': {
        'object_type': 'product',
        'fields': ['id', 'code', 'name', 'description', 'isActive', 'childCount', 'createdAt', 'updatedAt'],
        'field_map': {
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'description': 'description',
            'is_active': 'isActive',
            'child_count': 'childCount',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    },
    'BusinessObject': {
        'object_type': 'business_object',
        'fields': ['id', 'code', 'name', 'description', 'versionId', 'serviceModuleId', 'serviceModuleName', 'createdAt', 'updatedAt'],
        'field_map': {
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'description': 'description',
            'version_id': 'versionId',
            'service_module_id': 'serviceModuleId',
            'service_module_name': 'serviceModuleName',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    },
    'Version': {
        'object_type': 'version',
        'fields': ['id', 'code', 'name', 'description', 'isCurrent', 'productId', 'productName', 'createdAt', 'updatedAt'],
        'field_map': {
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'description': 'description',
            'is_current': 'isCurrent',
            'product_id': 'productId',
            'product_name': 'productName',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    },
    'Domain': {
        'object_type': 'domain',
        'fields': ['id', 'code', 'name', 'description', 'versionId', 'createdAt', 'updatedAt'],
        'field_map': {
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'description': 'description',
            'version_id': 'versionId',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    },
    'SubDomain': {
        'object_type': 'sub_domain',
        'fields': ['id', 'code', 'name', 'description', 'domainId', 'createdAt', 'updatedAt'],
        'field_map': {
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'description': 'description',
            'domain_id': 'domainId',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    },
    'ServiceModule': {
        'object_type': 'service_module',
        'fields': ['id', 'code', 'name', 'description', 'subDomainId', 'createdAt', 'updatedAt'],
        'field_map': {
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'description': 'description',
            'sub_domain_id': 'subDomainId',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    },
    'Annotation': {
        'object_type': 'annotation',
        'fields': ['id', 'targetType', 'targetId', 'category', 'content', 'createdAt', 'updatedAt', 'createdBy'],
        'field_map': {
            'id': 'id',
            'target_type': 'targetType',
            'target_id': 'targetId',
            'category': 'category',
            'content': 'content',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
            'created_by': 'createdBy',
        },
    },
}


# =============================================================================
# 2. 字段映射（snake_case → camelCase）
# =============================================================================

def _to_camel_case(data, entity_name='UserGroup'):
    """snake_case dict → camelCase dict (递归，按 entity 选择 field_map)"""
    field_map = ENTITY_SCHEMAS.get(entity_name, {}).get('field_map', {})
    if isinstance(data, list):
        return [_to_camel_case(item, entity_name) for item in data]
    if isinstance(data, dict):
        return {field_map.get(k, k): v for k, v in data.items()}
    return data


# 兼容旧 API（向后兼容 Phase B 测试）
USER_GROUP_FIELD_MAP = ENTITY_SCHEMAS['UserGroup']['field_map']


# =============================================================================
# 3. 简单 Query Parser（手写 ~80 行，足够支持 POC）
# =============================================================================
# 支持语法：
#   { fieldName(arg1: value1) { sub1 sub2 sub3 } }
# 不支持：variables / fragments / aliases / directives / mutation
# 后续如需扩展，使用 graphql-core 标准库替换

QUERY_PATTERN = re.compile(
    r'\{\s*'                       # 顶层 {
    r'(?P<field>\w+)\s*'           # field name
    r'(?:\((?P<args>[^)]*)\))?\s*'  # 可选 args
    r'\{\s*'                       # 子 {
    r'(?P<subs>[^}]*)\s*'           # sub fields
    r'\}\s*\}\s*$'                 # 闭合
)


def parse_query(query_str):
    """
    简单 GraphQL query 解析（支持 1 个 root field + 1 层 nested fields）

    Returns:
        dict: {field, args, sub_fields} or None
    """
    if not query_str or not query_str.strip():
        return None

    # 1. 去除注释
    clean = re.sub(r'#[^\n]*', '', query_str).strip()

    # 2. 匹配结构
    m = QUERY_PATTERN.match(clean)
    if not m:
        return None

    field = m.group('field')
    args_str = m.group('args') or ''
    subs_str = m.group('subs') or ''

    # 3. 解析 args（支持 id: 1 / pageSize: 20 / filter: "x"）
    args = {}
    for arg_match in re.finditer(r'(\w+)\s*:\s*("[^"]*"|\d+)', args_str):
        key = arg_match.group(1)
        raw = arg_match.group(2)
        if raw.startswith('"'):
            args[key] = raw.strip('"')
        elif raw.isdigit():
            args[key] = int(raw)
        else:
            args[key] = raw

    # 4. 解析 sub-fields（空格分隔）
    sub_fields = [s.strip() for s in subs_str.split() if s.strip()]

    return {
        'field': field,
        'args': args,
        'sub_fields': sub_fields,
    }


# =============================================================================
# 4. 通用 Resolver（支持所有 entity）
# =============================================================================

def _resolve_entity_single(object_type, entity_name, args, _context):
    """resolve single entity: { user(id: 1) { ... } }"""
    entity_id = args.get('id')
    if entity_id is None:
        return None
    try:
        result = _bo.read(object_type, entity_id)
        if not result.success:
            return None
        return _to_camel_case(result.data, entity_name) if result.data else None
    except Exception as e:
        logger.error(f"[GraphQL] resolve_{object_type}(id={entity_id}) failed: {e}")
        return None


def _resolve_entity_list(object_type, entity_name, args, _context):
    """resolve list entity: { users(page: 1, pageSize: 20) { ... } }"""
    page = args.get('page', 1)
    page_size = args.get('pageSize', 20)
    try:
        result = _bo.query(
            object_type,
            filters={},
            page=page,
            page_size=page_size,
        )
        if not result.success:
            return []
        items = result.data.get('items', []) if result.data else []
        return [_to_camel_case(item, entity_name) for item in items]
    except Exception as e:
        logger.error(f"[GraphQL] resolve_{object_type}_list failed: {e}")
        return []


# 自动从 ENTITY_SCHEMAS 生成 ROOT_QUERIES
def _build_root_queries():
    """
    自动构建 ROOT_QUERIES：
    - 每 entity 派生 1 个 single query（user / role / userGroup）
    - 每 entity 派生 1 个 list query（users / roles / userGroups）
    """
    queries = {}
    for entity_name, schema in ENTITY_SCHEMAS.items():
        object_type = schema['object_type']
        # single query: user / role / userGroup (camelCase root)
        single_root = entity_name[0].lower() + entity_name[1:]  # User → user
        queries[single_root] = lambda args, ctx, ot=object_type, en=entity_name: _resolve_entity_single(ot, en, args, ctx)
        # list query: users / roles / userGroups
        list_root = single_root + 's'  # user → users
        if single_root.endswith('y'):
            # 特殊：暂不处理（user / role / userGroup 都是规则形式）
            pass
        queries[list_root] = lambda args, ctx, ot=object_type, en=entity_name: _resolve_entity_list(ot, en, args, ctx)
    return queries


ROOT_QUERIES = _build_root_queries()


# 延迟导入 bo_framework（避免循环引用 + 测试时可 mock）
def _get_bo_framework():
    from meta.core.bo_framework import bo_framework
    return bo_framework

# 在 module load 时绑定到全局 resolver 闭包
_bo = _get_bo_framework()


# =============================================================================
# 5. Response Formatter（按 sub_fields 过滤）
# =============================================================================

def format_response(data, sub_fields):
    """
    按 GraphQL sub_fields 过滤数据

    Args:
        data: dict / list[dict] / None
        sub_fields: list of str (e.g. ['id', 'name', 'code'])

    Returns:
        dict / list[dict] / None
    """
    if data is None:
        return None
    if isinstance(data, list):
        return [{f: item.get(f) for f in sub_fields} for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return {f: data.get(f) for f in sub_fields}
    return data


# =============================================================================
# 6. GraphQL Endpoint（POST /graphql）
# =============================================================================

@graphql_bp.route('', methods=['POST', 'OPTIONS'])
def graphql_endpoint():
    """
    GraphQL endpoint - M9 3-entity POC

    POST /graphql
    Body: {"query": "{ userGroups(page: 1, pageSize: 10) { id name code } }"}

    Returns:
        {"data": {"userGroups": [{"id": 1, "name": "...", "code": "..."}]}}
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        req_body = request.get_json(silent=True) or {}
        query_str = req_body.get('query', '')

        # 1. 解析 query
        parsed = parse_query(query_str)
        if not parsed:
            return jsonify({
                'errors': [{'message': 'Invalid query format. Expected: { field(args) { sub1 sub2 } }'}]
            }), 400

        # 2. 查找 resolver
        field = parsed['field']
        resolver = ROOT_QUERIES.get(field)
        if not resolver:
            return jsonify({
                'errors': [{'message': f'Unknown field: {field}. Supported: {list(ROOT_QUERIES.keys())}'}]
            }), 400

        # 3. 调 resolver（复用 bo_framework）
        data = resolver(parsed['args'], {})

        # 4. 按 sub_fields 格式化
        result = format_response(data, parsed['sub_fields'])

        logger.info(
            f"[GraphQL] query={field} args={parsed['args']} "
            f"subs={parsed['sub_fields']} count={len(result) if isinstance(result, list) else 1 if result else 0}"
        )

        return jsonify({'data': {field: result}})

    except Exception as e:
        logger.error(f"[GraphQL] unexpected error: {e}", exc_info=True)
        return jsonify({
            'errors': [{'message': f'Internal error: {type(e).__name__}'}]
        }), 500


# =============================================================================
# 7. Schema 文档端点（GET /graphql/schema - 便于探索）
# =============================================================================

@graphql_bp.route('/schema', methods=['GET'])
def graphql_schema_doc():
    """返回 schema 文档（便于 GraphiQL-like 探索）"""
    types = {}
    for entity_name, schema in ENTITY_SCHEMAS.items():
        types[entity_name] = {
            'fields': schema['fields'],
        }

    queries = {}
    for entity_name, schema in ENTITY_SCHEMAS.items():
        object_type = schema['object_type']
        single_root = entity_name[0].lower() + entity_name[1:]
        queries[f'{single_root}(id: Int!)'] = f'{entity_name} - 根据 ID 查单个{entity_name}'
        queries[f'{single_root}s(page: Int, pageSize: Int)'] = f'[{entity_name}!]! - 列出{entity_name}（分页）'

    return jsonify({
        'name': 'M9 GraphQL POC',
        'version': '0.4.0',
        'phase': 'D5',
        'types': types,
        'queries': queries,
        'examples': [
            {
                'name': '列出前 5 个用户组',
                'query': '{ userGroups(page: 1, pageSize: 5) { id name code createdAt } }',
            },
            {
                'name': '根据 ID 查单个用户组',
                'query': '{ userGroup(id: 1) { id name code description } }',
            },
            {
                'name': '列出前 5 个用户',
                'query': '{ users(page: 1, pageSize: 5) { id username displayName email } }',
            },
            {
                'name': '根据 ID 查单个用户',
                'query': '{ user(id: 1) { id username displayName status } }',
            },
            {
                'name': '列出前 5 个角色',
                'query': '{ roles(page: 1, pageSize: 5) { id name code description } }',
            },
            {
                'name': '根据 ID 查单个角色',
                'query': '{ role(id: 1) { id name code } }',
            },
            {
                'name': '列出前 5 个产品线',
                'query': '{ products(page: 1, pageSize: 5) { id name code isActive childCount } }',
            },
            {
                'name': '根据 ID 查单个产品线',
                'query': '{ product(id: 1) { id name code description isActive } }',
            },
            {
                'name': '列出前 5 个版本',
                'query': '{ versions(page: 1, pageSize: 5) { id code name isCurrent productName } }',
            },
            {
                'name': '根据 ID 查单个版本',
                'query': '{ version(id: 1) { id code name isCurrent productName } }',
            },
            {
                'name': '列出前 5 个领域',
                'query': '{ domains(page: 1, pageSize: 5) { id code name versionId } }',
            },
            {
                'name': '根据 ID 查单个领域',
                'query': '{ domain(id: 1) { id code name versionId } }',
            },
            {
                'name': '列出前 5 个子领域',
                'query': '{ subDomains(page: 1, pageSize: 5) { id code name domainId } }',
            },
            {
                'name': '列出前 5 个服务模块',
                'query': '{ serviceModules(page: 1, pageSize: 5) { id code name subDomainId } }',
            },
            {
                'name': '列出前 5 个备注',
                'query': '{ annotations(page: 1, pageSize: 5) { id targetType targetId category content } }',
            },
        ],
        'note': 'M9 Phase D5 POC - 10 entities × 2 queries = 20 root queries. 0 mutation / 0 subscription. v1+v2 API 继续工作。',
    })


# =============================================================================
# 8. 健康检查（GET /graphql/health - 便于 E2E 验证）
# =============================================================================

@graphql_bp.route('/health', methods=['GET'])
def graphql_health():
    """GraphQL endpoint 健康检查"""
    return jsonify({
        'status': 'ok',
        'endpoint': 'graphql',
        'entities': list(ENTITY_SCHEMAS.keys()),
        'queries': list(ROOT_QUERIES.keys()),
        'phase': 'M9-D5-POC',
    })
