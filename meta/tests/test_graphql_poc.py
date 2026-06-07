# -*- coding: utf-8 -*-
"""
M9 GraphQL POC 单测 - 验证 1 entity + 2 query + 0 mutation

测试设计：
- L1 静态契约：parse_query 5 个用例
- L2 字段映射：_to_camel_case 3 个用例
- L3 响应格式化：format_response 4 个用例
- L4 端点 E2E：/graphql/health + /graphql/schema 2 个用例

不依赖 dev server（纯函数 + blueprint 测试）
"""
import pytest
import json

from meta.graphql import (
    parse_query,
    _to_camel_case,
    format_response,
    USER_GROUP_FIELD_MAP,
    ROOT_QUERIES,
    graphql_bp,
)


# =============================================================================
# L1 静态契约：parse_query
# =============================================================================

class TestParseQuery:
    """parse_query 静态契约 - 5 个用例"""

    def test_parse_query_basic(self):
        """基本 query：无 args + 3 个 sub fields"""
        result = parse_query("{ userGroups { id name code } }")
        assert result is not None
        assert result['field'] == 'userGroups'
        assert result['args'] == {}
        assert result['sub_fields'] == ['id', 'name', 'code']

    def test_parse_query_with_int_arg(self):
        """带 Int args: page / pageSize / id"""
        result = parse_query("{ userGroups(page: 1, pageSize: 20) { id name } }")
        assert result is not None
        assert result['field'] == 'userGroups'
        assert result['args'] == {'page': 1, 'pageSize': 20}
        assert result['sub_fields'] == ['id', 'name']

    def test_parse_query_with_string_arg(self):
        """带 String args: 字符串字面量"""
        result = parse_query('{ search(keyword: "admin") { id } }')
        assert result is not None
        assert result['field'] == 'search'
        assert result['args'] == {'keyword': 'admin'}

    def test_parse_query_invalid_returns_none(self):
        """无效 query 返回 None"""
        assert parse_query("") is None
        assert parse_query("not a query") is None
        assert parse_query("{ userGroups") is None  # 不闭合

    def test_parse_query_strips_comments(self):
        """GraphQL 注释 # 开头被去除"""
        result = parse_query("{ # comment\n userGroups { id name } }")
        assert result is not None
        assert result['field'] == 'userGroups'


# =============================================================================
# L2 字段映射：_to_camel_case
# =============================================================================

class TestCamelCaseMapping:
    """_to_camel_case 字段映射 - 3 个用例"""

    def test_camel_case_basic(self):
        """snake_case → camelCase 基础"""
        data = {'id': 1, 'created_at': '2026-01-01', 'updated_at': '2026-01-02'}
        result = _to_camel_case(data)
        assert result['id'] == 1
        assert result['createdAt'] == '2026-01-01'
        assert result['updatedAt'] == '2026-01-02'

    def test_camel_case_list_of_dicts(self):
        """list[dict] 递归转换"""
        data = [
            {'id': 1, 'created_at': '2026-01-01'},
            {'id': 2, 'created_at': '2026-01-02'},
        ]
        result = _to_camel_case(data)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]['createdAt'] == '2026-01-01'
        assert result[1]['createdAt'] == '2026-01-02'

    def test_camel_case_passthrough_unknown_fields(self):
        """未在映射表中的字段保持原样"""
        data = {'id': 1, 'unknown_field': 'value'}
        result = _to_camel_case(data)
        assert result['id'] == 1
        assert result['unknown_field'] == 'value'  # 保持原样


# =============================================================================
# L3 响应格式化：format_response
# =============================================================================

class TestFormatResponse:
    """format_response 按 sub_fields 过滤 - 4 个用例"""

    def test_format_response_single_dict(self):
        """单 dict 按 sub_fields 过滤"""
        data = {'id': 1, 'name': 'admin', 'code': 'ADMIN', 'description': 'desc'}
        result = format_response(data, ['id', 'name'])
        assert result == {'id': 1, 'name': 'admin'}
        assert 'code' not in result
        assert 'description' not in result

    def test_format_response_list(self):
        """list[dict] 按 sub_fields 过滤"""
        data = [
            {'id': 1, 'name': 'a', 'code': 'A'},
            {'id': 2, 'name': 'b', 'code': 'B'},
        ]
        result = format_response(data, ['id', 'name'])
        assert result == [
            {'id': 1, 'name': 'a'},
            {'id': 2, 'name': 'b'},
        ]

    def test_format_response_none(self):
        """None 数据透传"""
        assert format_response(None, ['id']) is None

    def test_format_response_empty_subfields(self):
        """空 sub_fields 返回空 dict/list"""
        data = {'id': 1, 'name': 'admin'}
        result = format_response(data, [])
        assert result == {}


# =============================================================================
# L4 Schema Registry 静态契约
# =============================================================================

class TestSchemaRegistry:
    """Schema Registry 静态契约 - 验证 1 entity + 2 query + 0 mutation"""

    def test_root_queries_count(self):
        """D5: 恰好 20 个 root Queries（10 entity × 2 query）"""
        assert len(ROOT_QUERIES) == 20

    def test_user_group_query_exists(self):
        """userGroup(id: Int!) query 存在"""
        assert 'userGroup' in ROOT_QUERIES
        assert callable(ROOT_QUERIES['userGroup'])

    def test_user_groups_query_exists(self):
        """userGroups(page, pageSize) query 存在"""
        assert 'userGroups' in ROOT_QUERIES
        assert callable(ROOT_QUERIES['userGroups'])

    def test_user_query_exists(self):
        """D2: user(id: Int!) query 存在"""
        assert 'user' in ROOT_QUERIES
        assert callable(ROOT_QUERIES['user'])

    def test_users_query_exists(self):
        """D2: users(page, pageSize) query 存在"""
        assert 'users' in ROOT_QUERIES
        assert callable(ROOT_QUERIES['users'])

    def test_role_query_exists(self):
        """D2: role(id: Int!) query 存在"""
        assert 'role' in ROOT_QUERIES
        assert callable(ROOT_QUERIES['role'])

    def test_roles_query_exists(self):
        """D2: roles(page, pageSize) query 存在"""
        assert 'roles' in ROOT_QUERIES
        assert callable(ROOT_QUERIES['roles'])

    def test_no_mutation_or_subscription(self):
        """0 mutation / 0 subscription（POC 范围控制）"""
        for key in ROOT_QUERIES.keys():
            assert not key.startswith('create'), f"{key} should not be in POC"
            assert not key.startswith('update'), f"{key} should not be in POC"
            assert not key.startswith('delete'), f"{key} should not be in POC"

    def test_user_group_field_map_complete(self):
        """USER_GROUP_FIELD_MAP 至少 6 个字段"""
        assert len(USER_GROUP_FIELD_MAP) >= 6
        assert USER_GROUP_FIELD_MAP['created_at'] == 'createdAt'
        assert USER_GROUP_FIELD_MAP['updated_at'] == 'updatedAt'

    def test_d2_entity_schemas_3(self):
        """D5: ENTITY_SCHEMAS 恰好 10 个 entity"""
        from meta.graphql import ENTITY_SCHEMAS
        assert len(ENTITY_SCHEMAS) == 10
        assert 'User' in ENTITY_SCHEMAS
        assert 'Role' in ENTITY_SCHEMAS
        assert 'UserGroup' in ENTITY_SCHEMAS
        assert 'Product' in ENTITY_SCHEMAS
        assert 'BusinessObject' in ENTITY_SCHEMAS
        assert 'Version' in ENTITY_SCHEMAS
        assert 'Domain' in ENTITY_SCHEMAS
        assert 'SubDomain' in ENTITY_SCHEMAS
        assert 'ServiceModule' in ENTITY_SCHEMAS
        assert 'Annotation' in ENTITY_SCHEMAS

    def test_d4_product_query_exists(self):
        """D4: product + products query 存在"""
        from meta.graphql import ROOT_QUERIES
        assert 'product' in ROOT_QUERIES
        assert 'products' in ROOT_QUERIES
        assert callable(ROOT_QUERIES['product'])
        assert callable(ROOT_QUERIES['products'])

    def test_d4_business_object_query_exists(self):
        """D4: businessObject + businessObjects query 存在"""
        from meta.graphql import ROOT_QUERIES
        assert 'businessObject' in ROOT_QUERIES
        assert 'businessObjects' in ROOT_QUERIES
        assert callable(ROOT_QUERIES['businessObject'])
        assert callable(ROOT_QUERIES['businessObjects'])

    def test_d4_product_field_map(self):
        """D4: Product 的 snake_case → camelCase 映射"""
        from meta.graphql import ENTITY_SCHEMAS
        pm = ENTITY_SCHEMAS['Product']['field_map']
        assert pm['is_active'] == 'isActive'
        assert pm['child_count'] == 'childCount'

    def test_d4_business_object_field_map(self):
        """D4: BusinessObject 的 snake_case → camelCase 映射"""
        from meta.graphql import ENTITY_SCHEMAS
        bm = ENTITY_SCHEMAS['BusinessObject']['field_map']
        assert bm['version_id'] == 'versionId'
        assert bm['service_module_id'] == 'serviceModuleId'
        assert bm['service_module_name'] == 'serviceModuleName'

    def test_d5_version_query_exists(self):
        """D5: version + versions query 存在"""
        from meta.graphql import ROOT_QUERIES
        assert 'version' in ROOT_QUERIES
        assert 'versions' in ROOT_QUERIES

    def test_d5_domain_query_exists(self):
        """D5: domain + domains query 存在"""
        from meta.graphql import ROOT_QUERIES
        assert 'domain' in ROOT_QUERIES
        assert 'domains' in ROOT_QUERIES

    def test_d5_sub_domain_query_exists(self):
        """D5: subDomain + subDomains query 存在"""
        from meta.graphql import ROOT_QUERIES
        assert 'subDomain' in ROOT_QUERIES
        assert 'subDomains' in ROOT_QUERIES

    def test_d5_service_module_query_exists(self):
        """D5: serviceModule + serviceModules query 存在"""
        from meta.graphql import ROOT_QUERIES
        assert 'serviceModule' in ROOT_QUERIES
        assert 'serviceModules' in ROOT_QUERIES

    def test_d5_annotation_query_exists(self):
        """D5: annotation + annotations query 存在"""
        from meta.graphql import ROOT_QUERIES
        assert 'annotation' in ROOT_QUERIES
        assert 'annotations' in ROOT_QUERIES

    def test_d5_version_field_map(self):
        """D5: Version 的 snake_case → camelCase 映射"""
        from meta.graphql import ENTITY_SCHEMAS
        vm = ENTITY_SCHEMAS['Version']['field_map']
        assert vm['is_current'] == 'isCurrent'
        assert vm['product_id'] == 'productId'

    def test_d5_annotation_field_map(self):
        """D5: Annotation 的 snake_case → camelCase 映射（特殊：无 parent_id）"""
        from meta.graphql import ENTITY_SCHEMAS
        am = ENTITY_SCHEMAS['Annotation']['field_map']
        assert am['target_type'] == 'targetType'
        assert am['target_id'] == 'targetId'
        assert am['created_by'] == 'createdBy'

    def test_d2_user_field_map_camelcase(self):
        """D2: User 的 snake_case → camelCase 映射正确"""
        from meta.graphql import ENTITY_SCHEMAS
        user_map = ENTITY_SCHEMAS['User']['field_map']
        assert user_map['display_name'] == 'displayName'
        assert user_map['last_login_at'] == 'lastLoginAt'
        assert user_map['created_at'] == 'createdAt'

    def test_d2_camel_case_per_entity(self):
        """D2: _to_camel_case 按 entity 选不同 field_map"""
        from meta.graphql import _to_camel_case
        user_data = {'id': 1, 'display_name': 'Admin', 'last_login_at': '2026-01-01'}
        result = _to_camel_case(user_data, 'User')
        assert result['displayName'] == 'Admin'
        assert result['lastLoginAt'] == '2026-01-01'

        # 用不同 entity 转换，应该不应用 user 的 field_map
        result2 = _to_camel_case(user_data, 'UserGroup')
        assert 'displayName' not in result2  # UserGroup field_map 没有 display_name
        assert result2['display_name'] == 'Admin'  # 保持原样


# =============================================================================
# L5 Blueprint 集成
# =============================================================================

class TestBlueprint:
    """Blueprint 集成测试 - 3 个用例"""

    def test_blueprint_registered(self):
        """graphql_bp 是 Flask Blueprint 实例"""
        from flask import Blueprint
        assert isinstance(graphql_bp, Blueprint)
        assert graphql_bp.name == 'graphql_v3'
        assert graphql_bp.url_prefix == '/graphql'

    def test_blueprint_routes(self):
        """Blueprint 包含 3 个路由（POST /graphql + GET /graphql/schema + GET /graphql/health）"""
        # view_functions 在 register_blueprint 之后才有，模块级别直接检查函数
        from meta.graphql import graphql_endpoint, graphql_schema_doc, graphql_health
        assert callable(graphql_endpoint)
        assert callable(graphql_schema_doc)
        assert callable(graphql_health)

    def test_blueprint_url_prefix(self):
        """url_prefix = /graphql"""
        assert graphql_bp.url_prefix == '/graphql'
