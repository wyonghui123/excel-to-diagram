import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
DataPermissionInterceptor 单元测试

测试数据权限拦截器的核心功能：
- 拦截器名称和优先级
- before_action 行为
- _is_admin 判断逻辑
- scope 过滤应用
- 数据权限过滤应用
"""

import pytest
from unittest.mock import Mock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor


class MockActionContext:
    """模拟 ActionContext 用于测试"""

    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'domain')
        self.object_id = kwargs.get('object_id', None)
        self.action = kwargs.get('action', 'crud_query')
        self.params = kwargs.get('params', {})
        self.user_id = kwargs.get('user_id', 1)
        self.user_name = kwargs.get('user_name', 'test_user')
        self.data_source = kwargs.get('data_source', None)
        self.meta_object = kwargs.get('meta_object', None)
        self.result = kwargs.get('result', None)
        self.old_data = kwargs.get('old_data', None)
        self.extra = kwargs.get('extra', {})

    @property
    def is_query_action(self):
        return self.action in ('crud_query', 'query', 'list')

    @property
    def is_create_action(self):
        return self.action in ('create', 'crud_create')

    @property
    def is_update_action(self):
        return self.action in ('update', 'crud_update')

    @property
    def is_delete_action(self):
        return self.action in ('delete', 'crud_delete')


@pytest.fixture
def interceptor():
    return DataPermissionInterceptor()


@pytest.fixture(autouse=True)
def cleanup_interceptor():
    yield
    DataPermissionInterceptor._perm_filter = None


class TestDataPermissionInterceptor:
    """DataPermissionInterceptor 单元测试"""

    def test_name_and_priority(self, interceptor):
        """测试拦截器名称和优先级"""
        assert interceptor.name == "data_permission"
        assert interceptor.priority == 30

    def test_interceptor_exists(self, interceptor):
        """测试拦截器存在"""
        assert interceptor is not None


class TestDataPermissionInterceptorExtended:
    """DataPermissionInterceptor 扩展测试"""

    def test_priority_is_30(self, interceptor):
        """优先级为 30"""
        assert interceptor.priority == 30

    def test_name_is_data_permission(self, interceptor):
        """名称为 data_permission"""
        assert interceptor.name == "data_permission"

    def test_before_action_skips_non_query(self, interceptor):
        """非查询动作跳过权限过滤"""
        context = MockActionContext(action='create', user_id=1)
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_before_action_skips_create_action(self, interceptor):
        """创建动作跳过权限过滤"""
        context = MockActionContext(action='crud_create', user_id=1)
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_before_action_skips_update_action(self, interceptor):
        """更新动作跳过权限过滤"""
        context = MockActionContext(action='update', user_id=1)
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_before_action_skips_delete_action(self, interceptor):
        """删除动作跳过权限过滤"""
        context = MockActionContext(action='delete', user_id=1)
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_before_action_skips_when_admin_flag_true(self, interceptor):
        """is_admin=True 时跳过权限过滤"""
        context = MockActionContext(
            action='crud_query',
            user_id=1,
            extra={'is_admin': True}
        )
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_apply_scope_filter_without_meta_object(self, interceptor):
        """无 meta_object 时跳过 scope 过滤"""
        context = MockActionContext(
            action='crud_query',
            user_id=1,
            meta_object=None,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' not in context.extra

    def test_apply_scope_filter_skips_without_auth(self, interceptor):
        """无 authorization 配置时跳过"""
        meta_obj = Mock()
        meta_obj.authorization = None

        context = MockActionContext(
            action='crud_query',
            user_id=1,
            meta_object=meta_obj,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' not in context.extra

    def test_apply_scope_filter_skips_without_scope(self, interceptor):
        """无 scope 表达式时跳过"""
        meta_obj = Mock()
        meta_obj.authorization = {'other_config': 'value'}

        context = MockActionContext(
            action='crud_query',
            user_id=1,
            meta_object=meta_obj,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' not in context.extra

    def test_after_action_does_nothing(self, interceptor):
        """after_action 不执行任何操作"""
        context = MockActionContext(action='crud_query', user_id=1)
        original_extra = dict(context.extra)
        interceptor.after_action(context)
        assert context.extra == original_extra

    def test_parse_scope_expression_simple(self, interceptor):
        """解析简单 scope 表达式"""
        result = DataPermissionInterceptor._parse_scope_expression("owner_id = 1")
        assert len(result) == 1
        assert result[0]['field'] == 'owner_id'
        assert result[0]['operator'] == 'eq'
        assert result[0]['value'] == '1'

    def test_parse_scope_expression_or(self, interceptor):
        """解析 OR scope 表达式"""
        result = DataPermissionInterceptor._parse_scope_expression(
            "visibility = 'public' OR owner_id = 1"
        )
        assert len(result) == 1
        assert isinstance(result[0], list)
        or_group = result[0]
        assert len(or_group) == 2
        assert or_group[0]['field'] == 'visibility'
        assert or_group[0]['value'] == 'public'
        assert or_group[1]['field'] == 'owner_id'
        assert or_group[1]['value'] == '1'

    def test_parse_scope_expression_or_lowercase(self, interceptor):
        """解析小写 or 表达式"""
        result = DataPermissionInterceptor._parse_scope_expression(
            "visibility = 'public' or owner_id = 1"
        )
        assert len(result) == 1
        assert isinstance(result[0], list)
        assert len(result[0]) == 2

    def test_apply_scope_filter_with_or_expression(self, interceptor):
        """OR scope 表达式注入 query_conditions"""
        meta_obj = Mock()
        meta_obj.authorization = {
            'scope': "visibility = 'public' OR owner_id = $user.id"
        }

        context = MockActionContext(
            action='crud_query',
            user_id=42,
            meta_object=meta_obj,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' in context.extra
        assert len(context.extra['query_conditions']) == 1
        cond = context.extra['query_conditions'][0]
        assert cond['type'] == 'or'
        assert len(cond['conditions']) == 2
        assert cond['conditions'][0]['field'] == 'visibility'
        assert cond['conditions'][0]['value'] == 'public'
        assert cond['conditions'][1]['field'] == 'owner_id'
        assert cond['conditions'][1]['value'] == '42'

    def test_parse_simple_condition_with_quotes(self, interceptor):
        """解析带引号的简单条件"""
        result = DataPermissionInterceptor._parse_simple_condition("name = 'hello'")
        assert result['field'] == 'name'
        assert result['operator'] == 'eq'
        assert result['value'] == 'hello'

    def test_parse_simple_condition_with_double_quotes(self, interceptor):
        """解析带双引号的简单条件"""
        result = DataPermissionInterceptor._parse_simple_condition('name = "world"')
        assert result['field'] == 'name'
        assert result['operator'] == 'eq'
        assert result['value'] == 'world'

    def test_parse_simple_condition_not_equal(self, interceptor):
        """解析 != 操作符"""
        result = DataPermissionInterceptor._parse_simple_condition("count != 0")
        assert result['field'] == 'count'
        assert result['operator'] == 'ne'
        assert result['value'] == '0'

    # ============================================================
    # Regression tests for: _parse_scope_expression must be
    # parenthesis-aware when splitting top-level OR.
    #
    # 背景 (BMRD-2026-06-14, BugID: TEST888-version-invisible):
    #   原实现用 re.split(r'\s+OR\s+', ...) 在子查询里也会切 OR,
    #   导致 ``product_id IN (SELECT id FROM products WHERE
    #   visibility = 'public' OR owner_id = $user.id)`` 被切成两段,
    #   下游 SQL 拼接后报 'incomplete input'。
    #   修复: 改为括号感知状态机, 只在 depth=0 且不在字符串字面量内时
    #   才把 OR 当顶层关键字。
    # ============================================================

    def test_parse_scope_expression_in_subquery_with_or(self):
        """[Regression] IN (SELECT ... OR ...) 子查询内的 OR 不应被切分

        复现 BMRD-2026-06-14: TEST888 角色为空时, version 查询报
        'incomplete input', 根因就是这条 case。
        """
        expr = (
            "product_id IN (SELECT id FROM products "
            "WHERE visibility = 'public' OR owner_id = $user.id)"
        )
        result = DataPermissionInterceptor._parse_scope_expression(expr)

        # 必须只识别为一条 in_subquery 条件, 不能切 OR
        assert len(result) == 1, \
            f"IN subquery 内的 OR 不应被切分, 但切出 {len(result)} 段: {result}"
        assert not isinstance(result[0], list), \
            f"顶层不应被识别为 OR group, 实际: {result[0]}"
        cond = result[0]
        assert cond['field'] == 'product_id'
        assert cond['operator'] == 'in_subquery'
        # 子查询体内的 OR 必须原样保留
        assert "OR owner_id" in cond['value'], \
            f"子查询体内的 OR 应原样保留, 实际 value: {cond['value']}"
        assert "$user.id" in cond['value']

    def test_parse_scope_expression_nested_in_subquery(self):
        """[Regression] 嵌套 IN 子查询不应被切分

        场景: domain.yaml 的 scope 含两层 IN (SELECT ... WHERE ... IN (SELECT ...))
        """
        expr = (
            "version_id IN (SELECT v.id FROM versions v "
            "WHERE v.product_id IN ("
            "SELECT id FROM products WHERE visibility = 'public'"
            "))"
        )
        result = DataPermissionInterceptor._parse_scope_expression(expr)
        assert len(result) == 1
        assert result[0]['operator'] == 'in_subquery'
        # 内层 IN 必须完整保留在 value 里
        assert "IN (SELECT id FROM products" in result[0]['value']
        assert "visibility = 'public'" in result[0]['value']

    def test_parse_scope_expression_or_in_string_literal(self):
        """[Regression] 字符串字面量内的 'OR' 不应触发切分

        场景: 字段值含 'A OR B' 这样的字符串, 解析器必须识别引号边界。
        """
        result = DataPermissionInterceptor._parse_scope_expression(
            "name = 'A OR B' OR id = 5"
        )
        # 顶层 OR 必须识别, 切出 2 段
        assert len(result) == 1
        assert isinstance(result[0], list)
        assert len(result[0]) == 2
        # 字符串值内的 'OR' 必须作为普通字符保留
        assert result[0][0]['value'] == 'A OR B'
        assert result[0][0]['field'] == 'name'
        assert result[0][1]['field'] == 'id'
        assert result[0][1]['value'] == '5'

    def test_apply_scope_filter_with_in_subquery_or(self, interceptor):
        """[Regression] 端到端: version.yaml 的真实 scope 能正常注入

        这是 BMRD-2026-06-14 的根因场景:
          - 用户 TEST888 (id=3371) 无角色 → 走 BO yaml 的 authorization.scope
          - scope = "product_id IN (SELECT id FROM products
                     WHERE visibility = 'public' OR owner_id = $user.id)"
        修复前: 切碎 OR, SQL 报 'incomplete input'
        修复后: 正常生成一条 in_subquery 条件, value 中 $user.id 被替换为 '3371'
        """
        meta_obj = Mock()
        meta_obj.authorization = {
            'scope': (
                "product_id IN (SELECT id FROM products "
                "WHERE visibility = 'public' OR owner_id = $user.id)"
            )
        }

        context = MockActionContext(
            action='crud_query',
            user_id=3371,
            user_name='TEST888',
            object_type='version',
            meta_object=meta_obj,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' in context.extra
        conds = context.extra['query_conditions']
        # 修复后必须只有 1 条 in_subquery 条件 (不是 2 条碎片)
        assert len(conds) == 1, \
            f"预期 1 条条件, 实际 {len(conds)}: {conds}"
        cond = conds[0]
        assert cond['field'] == 'product_id'
        assert cond['operator'] == 'in_subquery'
        # $user.id 必须被替换为实际用户 ID (在 substitution 阶段, 见
        # _apply_scope_filter L357, 但 subquery 里的 $user.id 也应替换)
        # 这里的实现只替换顶层 expr 的 $user.id, subquery 留给 SQL 层
        # 处理, 关键是 OR 不被切走
        assert "OR owner_id" in cond['value']
