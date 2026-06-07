# -*- coding: utf-8 -*-
"""
QueryInterceptor 单元测试

测试查询增强拦截器的核心功能：
- 拦截器名称和优先级
- after_action 行为
- type 标记注入
- 记录增强
- 计算列计算
- can_delete 检查
"""

import unittest
import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch

pytestmark = pytest.mark.integration

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.interceptors.query_interceptor import QueryInterceptor

class MockResult:
    """模拟 Result"""

    def __init__(self, success=True, data=None):
        self.success = success
        self.data = data

class MockActionContext:
    """模拟 ActionContext"""

    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'domain')
        self.object_id = kwargs.get('object_id', None)
        self.action = kwargs.get('action', 'crud_query')
        self.params = kwargs.get('params', {})
        self.user_id = kwargs.get('user_id', 1)
        self.data_source = kwargs.get('data_source', None)
        self.meta_object = kwargs.get('meta_object', None)
        self.result = kwargs.get('result', None)
        self.extra = kwargs.get('extra', {})

    @property
    def is_query_action(self):
        return self.action in ('crud_query', 'query', 'list')

class TestQueryInterceptor:
    """QueryInterceptor 单元测试"""

    def setup_method(self):
        self.interceptor = QueryInterceptor()

    def test_name_and_priority(self):
        """测试拦截器名称和优先级"""
        assert self.interceptor.name == "query"
        assert self.interceptor.priority == 50

    def test_interceptor_exists(self):
        """测试拦截器存在"""
        assert self.interceptor is not None

class TestQueryInterceptorExtended:
    """QueryInterceptor 扩展测试"""

    def setup_method(self):
        self.interceptor = QueryInterceptor()

    def test_name_is_query(self):
        """名称为 query"""
        assert self.interceptor.name == "query"

    def test_priority_is_50(self):
        """优先级为 50"""
        assert self.interceptor.priority == 50

    def test_before_action_does_nothing(self):
        """before_action 不执行任何操作"""
        context = MockActionContext(action='crud_query')
        original_extra = dict(context.extra)
        self.interceptor.before_action(context)
        assert context.extra == original_extra

    def test_after_action_skips_failed_result(self):
        """失败结果跳过 after_action"""
        context = MockActionContext(
            action='crud_query',
            result=MockResult(success=False, data=None)
        )
        self.interceptor.after_action(context)
        assert not context.result.success

    def test_after_action_skips_none_result(self):
        """None 结果跳过 after_action"""
        context = MockActionContext(
            action='crud_query',
            result=None
        )
        self.interceptor.after_action(context)
        assert context.result is None

    def test_extract_items_from_list(self):
        """从列表提取 items"""
        data = [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}]
        context = MockActionContext(
            action='crud_query',
            result=MockResult(success=True, data=data)
        )
        items = self.interceptor._extract_items(context)
        assert len(items) == 2
        assert items[0]['id'] == 1

    def test_extract_items_from_dict_with_items(self):
        """从带 items 的 dict 提取"""
        data = {'items': [{'id': 1}, {'id': 2}], 'total': 2}
        context = MockActionContext(
            action='crud_query',
            result=MockResult(success=True, data=data)
        )
        items = self.interceptor._extract_items(context)
        assert len(items) == 2

    def test_extract_items_from_empty_data(self):
        """从空数据提取"""
        context = MockActionContext(
            action='crud_query',
            result=MockResult(success=True, data=None)
        )
        items = self.interceptor._extract_items(context)
        assert items == []

    def test_inject_type_tag(self):
        """注入 type 标记"""
        items = [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}]
        context = MockActionContext(
            object_type='domain',
            action='crud_query',
            result=MockResult(success=True, data=items)
        )
        self.interceptor._inject_type_tag(context, items)
        assert items[0]['type'] == 'domain'
        assert items[1]['type'] == 'domain'

    def test_inject_type_tag_preserves_existing(self):
        """注入 type 标记保留现有字段"""
        items = [{'id': 1, 'name': 'A', 'existing': 'value'}]
        context = MockActionContext(
            object_type='domain',
            action='crud_query',
            result=MockResult(success=True, data=items)
        )
        self.interceptor._inject_type_tag(context, items)
        assert items[0]['type'] == 'domain'
        assert items[0]['existing'] == 'value'

    def test_after_action_injects_type_for_query(self):
        """查询动作注入 type"""
        items = [{'id': 1, 'name': 'A'}]
        context = MockActionContext(
            object_type='domain',
            action='crud_query',
            result=MockResult(success=True, data=items)
        )
        self.interceptor.after_action(context)
        assert items[0]['type'] == 'domain'

    def test_after_action_skips_non_query(self):
        """非查询动作跳过 type 注入"""
        items = [{'id': 1, 'name': 'A'}]
        context = MockActionContext(
            object_type='domain',
            action='create',
            result=MockResult(success=True, data=items)
        )
        self.interceptor.after_action(context)
        assert 'type' not in items[0]

    def test_check_can_delete_without_deletability(self):
        """无 deletability 配置跳过 can_delete 检查"""
        items = [{'id': 1, 'name': 'A'}]
        meta_obj = Mock()
        meta_obj.deletability = None

        context = MockActionContext(
            object_type='domain',
            action='crud_query',
            meta_object=meta_obj,
            result=MockResult(success=True, data=items)
        )

        self.interceptor._check_can_delete(context, items)
        assert 'can_delete' not in items[0]

    def test_enrich_records_handles_exception(self):
        """enrich_records 异常处理"""
        items = [{'id': 1, 'name': 'A'}]
        context = MockActionContext(
            object_type='domain',
            action='crud_query',
            result=MockResult(success=True, data=items)
        )
        self.interceptor._enrich_records(context, items)
        assert len(items) == 1

    def test_compute_columns_handles_exception(self):
        """compute_columns 异常处理"""
        items = [{'id': 1, 'name': 'A'}]
        meta_obj = Mock()
        meta_obj.ui_view_config = None

        context = MockActionContext(
            object_type='domain',
            action='crud_query',
            meta_object=meta_obj,
            result=MockResult(success=True, data=items)
        )

        self.interceptor._compute_columns(context, items)
        assert len(items) == 1


class TestInjectDisplayValues:
    """[NEW] COV-004: _inject_display_values 专项测试 (10 用例)

    FR-3.1: 为每条记录追加 display_values 字段
    - enum 字段 → 标签
    - boolean → 是/否
    - date/datetime → 格式化
    - FK → <field>_display 虚拟字段
    """

    def setup_method(self):
        self.interceptor = QueryInterceptor()

    def _make_field(self, fid, field_type=None, enum_values=None, ui=None):
        f = Mock()
        f.id = fid
        f.field_type = field_type
        f.enum_values = enum_values
        f.ui = ui
        return f

    def _make_meta(self, fields, object_type='user'):
        m = Mock()
        m.id = object_type
        m.fields = fields
        return m

    def test_enum_str_values_get_label(self):
        """enum_values 元素为 str → 直接用作 display label"""
        field = self._make_field('status', field_type='string',
                                 enum_values=['active', 'inactive'])
        meta = self._make_meta([field])
        items = [{'id': 1, 'status': 'active'}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        assert items[0]['display_values']['status'] == 'active'

    def test_enum_dict_values_get_label(self):
        """enum_values 元素为 dict (含 label) → 取 .label"""
        field = self._make_field('priority', field_type='string', enum_values=[
            {'value': 'low', 'label': '低'},
            {'value': 'high', 'label': '高'},
        ])
        meta = self._make_meta([field])
        items = [{'id': 1, 'priority': 'high'}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        assert items[0]['display_values']['priority'] == '高'

    def test_boolean_true_maps_to_yes(self):
        """boolean=True → '是'"""
        field = self._make_field('is_active', field_type='BOOLEAN')
        meta = self._make_meta([field])
        items = [{'id': 1, 'is_active': True}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        assert items[0]['display_values']['is_active'] == '是'

    def test_boolean_false_maps_to_no(self):
        """boolean=False → '否'"""
        field = self._make_field('is_locked', field_type='BOOLEAN')
        meta = self._make_meta([field])
        items = [{'id': 1, 'is_locked': False}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        assert items[0]['display_values']['is_locked'] == '否'

    def test_fk_uses_virtual_display_field(self):
        """FK 字段使用 <field>_display 虚拟字段"""
        field = self._make_field('owner_id', ui={'relation': 'fk_user', 'display_field': 'name'})
        meta = self._make_meta([field])
        items = [{'id': 1, 'owner_id': 100, 'owner_id_display': 'Alice'}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        assert items[0]['display_values']['owner_id'] == 'Alice'

    def test_date_field_truncated_to_10_chars(self):
        """DATE 字段截取前 10 字符"""
        field = self._make_field('birthday', field_type='DATE')
        meta = self._make_meta([field])
        items = [{'id': 1, 'birthday': '2026-06-07'}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        assert items[0]['display_values']['birthday'] == '2026-06-07'

    def test_datetime_field_truncated_to_19_chars(self):
        """DATETIME 字段含 T 分隔 → 截取前 19 字符"""
        field = self._make_field('created_at', field_type='DATETIME')
        meta = self._make_meta([field])
        items = [{'id': 1, 'created_at': '2026-06-07T10:30:45.123456'}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        assert items[0]['display_values']['created_at'] == '2026-06-07T10:30:45'

    def test_unknown_object_type_skipped_silently(self):
        """registry.get 返回 None → 静默跳过"""
        items = [{'id': 1, 'status': 'active'}]
        context = MockActionContext(object_type='__nope__')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = None
            self.interceptor._inject_display_values(context, items)
        assert 'display_values' not in items[0]

    def test_null_values_not_in_display(self):
        """字段值为 None 时不写入 display_values"""
        field = self._make_field('status', field_type='string', enum_values=['active', 'inactive'])
        meta = self._make_meta([field])
        items = [{'id': 1, 'status': None}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        # display_values 仍可能因其他字段被创建，但 'status' 不应在内
        assert 'status' not in items[0].get('display_values', {})

    def test_preserves_existing_display_values(self):
        """已存在的 display_values 被保留（合并而非覆盖）"""
        field = self._make_field('is_active', field_type='BOOLEAN')
        meta = self._make_meta([field])
        items = [{'id': 1, 'is_active': True, 'display_values': {'existing': 'X'}}]
        context = MockActionContext(object_type='user')
        with patch('meta.core.models.registry') as reg:
            reg.get.return_value = meta
            self.interceptor._inject_display_values(context, items)
        dv = items[0]['display_values']
        assert dv.get('existing') == 'X'
        assert dv.get('is_active') == '是'

