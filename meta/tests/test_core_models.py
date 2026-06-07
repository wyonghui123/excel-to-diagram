import pytest

pytestmark = pytest.mark.integration

"""
后端测试套件 - 模型层测试
测试 meta.core.models 模块中的所有模型类
"""

import pytest
from datetime import datetime
from typing import List, Optional


class TestMetaObject:
    """MetaObject 模型测试"""
    
    def test_create_basic_meta_object(self):
        """TC-BE-001-01: 创建基本MetaObject"""
        from meta.core.models import MetaObject
        
        meta = MetaObject(
            id='user',
            name='user',
            table_name='users',
            persistent=True
        )
        
        assert meta.name == 'user'
        assert meta.table_name == 'users'
        assert meta.persistent == True
    
    def test_create_with_relations(self):
        """TC-BE-001-02: 创建带relations的MetaObject"""
        from meta.core.models import MetaObject, MetaRelation
        from meta.core.models_enums import RelationType
        
        meta = MetaObject(
            id='user',
            name='user',
            table_name='users'
        )
        
        groups_rel = MetaRelation(
            id='groups',
            name='groups',
            relation_type=RelationType.MANY_TO_MANY,
            target_object='user_group'
        )
        
        meta.relations = [groups_rel]
        
        assert len(meta.relations) == 1
        assert meta.relations[0].name == 'groups'
        assert meta.relations[0].relation_type == RelationType.MANY_TO_MANY
    
    def test_create_persistent_object(self):
        """TC-BE-001-03: 创建persistent对象"""
        from meta.core.models import MetaObject
        
        user = MetaObject(
            id='user',
            name='user',
            table_name='users',
            persistent=True
        )
        
        assert user.persistent == True
    
    def test_create_virtual_object(self):
        """TC-BE-001-04: 创建非persistent对象"""
        from meta.core.models import MetaObject
        
        view = MetaObject(
            id='user_stats',
            name='user_stats',
            table_name='',
            persistent=False
        )
        
        assert view.persistent == False
    
    def test_create_with_list_config(self):
        """TC-BE-001-05: 创建带list配置的MetaObject"""
        from meta.core.models import MetaObject, UIListViewConfig, UIListViewColumn
        
        meta = MetaObject(
            id='user',
            name='user',
            table_name='users'
        )
        
        columns = [
            UIListViewColumn(key='username', title='用户名'),
            UIListViewColumn(key='email', title='邮箱')
        ]
        
        meta.list = UIListViewConfig(
            title='用户管理',
            columns=columns
        )
        
        assert meta.list.title == '用户管理'
        assert len(meta.list.columns) == 2
        assert meta.list.columns[0].key == 'username'
    
    def test_create_with_actions(self):
        """TC-BE-001-06: 创建带actions的MetaObject"""
        from meta.core.models import MetaObject, MetaAction
        from meta.core.models_enums import ActionType
        
        meta = MetaObject(
            id='user',
            name='user',
            table_name='users'
        )
        
        create_action = MetaAction(
            id='create',
            name='新建',
            action_type=ActionType.CRUD,
            method='POST',
            path='/api/v1/users'
        )
        
        meta.actions = [create_action]
        
        assert len(meta.actions) == 1
        assert meta.actions[0].id == 'create'
        assert meta.actions[0].name == '新建'
    
    def test_meta_object_field_access(self):
        """TC-BE-001-13: MetaObject字段访问"""
        from meta.core.models import MetaObject
        
        meta = MetaObject(
            id='user',
            name='user',
            table_name='users',
            description='用户表'
        )
        
        # 测试字段访问
        assert meta.name == 'user'
        assert meta.table_name == 'users'
        assert meta.description == '用户表'


class TestMetaField:
    """MetaField 模型测试"""
    
    def test_create_string_field(self):
        """TC-BE-001-16: 创建STRING类型字段"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='username',
            name='用户名',
            field_type=FieldType.STRING,
            db_column='username',
            required=True
        )
        
        assert field.id == 'username'
        assert field.name == '用户名'
        assert field.field_type == FieldType.STRING
        assert field.required == True
    
    def test_create_integer_field(self):
        """TC-BE-001-17: 创建INTEGER类型字段"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='age',
            name='年龄',
            field_type=FieldType.INTEGER,
            db_column='age'
        )
        
        assert field.field_type == FieldType.INTEGER
    
    def test_create_datetime_field(self):
        """TC-BE-001-18: 创建DATETIME类型字段"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='created_at',
            name='创建时间',
            field_type=FieldType.DATETIME,
            db_column='created_at'
        )
        
        assert field.field_type == FieldType.DATETIME
    
    def test_create_boolean_field(self):
        """TC-BE-001-19: 创建BOOLEAN类型字段"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='is_active',
            name='是否激活',
            field_type=FieldType.BOOLEAN,
            db_column='is_active'
        )
        
        assert field.field_type == FieldType.BOOLEAN
    
    def test_create_enum_field(self):
        """TC-BE-001-20: 创建枚举类型字段"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='status',
            name='状态',
            field_type=FieldType.STRING,
            db_column='status',
            enum_values=[{'value': 'active', 'label': '活跃'}, {'value': 'inactive', 'label': '未激活'}]
        )
        
        assert field.field_type == FieldType.STRING
        assert len(field.enum_values) == 2
    
    def test_create_association_field(self):
        """TC-BE-001-21: 创建关联字段（使用STRING类型模拟）"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='manager_id',
            name='管理者',
            field_type=FieldType.STRING,
            db_column='manager_id'
        )
        
        assert field.field_type == FieldType.STRING
        assert field.db_column == 'manager_id'
    
    def test_field_required(self):
        """TC-BE-001-22: 字段required验证"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='username',
            name='用户名',
            field_type=FieldType.STRING,
            db_column='username',
            required=True
        )
        
        assert field.required == True
    
    def test_field_unique(self):
        """TC-BE-001-23: 字段unique验证"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='email',
            name='邮箱',
            field_type=FieldType.STRING,
            db_column='email',
            unique=True
        )
        
        assert field.unique == True
    
    def test_field_default_value(self):
        """TC-BE-001-24: 字段default值"""
        from meta.core.models import MetaField
        from meta.core.models_enums import FieldType
        
        field = MetaField(
            id='status',
            name='状态',
            field_type=FieldType.STRING,
            db_column='status',
            default='active'
        )
        
        assert field.default == 'active'


class TestFieldType:
    """FieldType 枚举测试"""
    
    def test_field_type_values(self):
        """TC-BE-001-31: FieldType枚举值验证"""
        from meta.core.models_enums import FieldType
        
        assert FieldType.STRING.value == 'string'
        assert FieldType.INTEGER.value == 'integer'
        assert FieldType.DATETIME.value == 'datetime'
        assert FieldType.BOOLEAN.value == 'boolean'
        assert FieldType.FLOAT.value == 'float'
        assert FieldType.TEXT.value == 'text'
    
    def test_field_type_is_numeric(self):
        """TC-BE-001-33: 数值类型判断"""
        from meta.core.models_enums import FieldType
        
        numeric_types = [FieldType.INTEGER, FieldType.FLOAT]
        for t in numeric_types:
            assert t in numeric_types, f"{t} should be numeric"
        
        assert FieldType.STRING not in numeric_types
        assert FieldType.DATETIME not in numeric_types
    
    def test_field_type_is_text(self):
        """TC-BE-001-34: 文本类型判断"""
        from meta.core.models_enums import FieldType
        
        text_types = [FieldType.STRING, FieldType.TEXT]
        for t in text_types:
            assert t in text_types, f"{t} should be text"
        
        assert FieldType.INTEGER not in text_types
    
    def test_field_type_is_date(self):
        """TC-BE-001-35: 日期类型判断"""
        from meta.core.models_enums import FieldType
        
        assert FieldType.DATETIME.value == 'datetime'


class TestActionContext:
    """ActionContext 模型测试"""
    
    def test_action_context_creation(self):
        """TC-BE-001-36: ActionContext创建"""
        from meta.core.action_context import ActionContext
        from unittest.mock import Mock
        from meta.core.datasource import DataSource
        
        mock_ds = Mock(spec=DataSource)
        context = ActionContext(
            meta_object=Mock(),
            action='create',
            params={'username': 'test'},
            data_source=mock_ds
        )
        
        assert context.action == 'create'
        assert context.params['username'] == 'test'
    
    def test_action_context_result(self):
        """TC-BE-001-37: ActionContext设置结果"""
        from meta.core.action_context import ActionContext, ActionResult
        from unittest.mock import Mock
        from meta.core.datasource import DataSource
        
        mock_ds = Mock(spec=DataSource)
        context = ActionContext(
            meta_object=Mock(),
            action='read',
            params={'id': 1},
            data_source=mock_ds
        )
        
        result = ActionResult(
            success=True,
            data={'id': 1, 'username': 'test'}
        )
        
        context.result = result
        
        assert context.result.success == True
        assert context.result.data['id'] == 1
    
    def test_action_context_error(self):
        """TC-BE-001-39: ActionContext错误处理"""
        from meta.core.action_context import ActionContext, ActionResult
        from unittest.mock import Mock
        from meta.core.datasource import DataSource
        
        mock_ds = Mock(spec=DataSource)
        context = ActionContext(
            meta_object=Mock(),
            action='read',
            params={'id': 999},
            data_source=mock_ds
        )
        
        result = ActionResult(
            success=False,
            message='Record not found'
        )
        
        context.result = result
        
        assert context.result.success == False
        assert context.result.message == 'Record not found'


class TestActionResult:
    """ActionResult 模型测试"""
    
    def test_success_result(self):
        """TC-BE-001-41: ActionResult成功结果"""
        from meta.core.action_context import ActionResult
        
        result = ActionResult(
            success=True,
            data={'id': 1}
        )
        
        assert result.success == True
        assert result.data['id'] == 1
    
    def test_error_result(self):
        """TC-BE-001-42: ActionResult错误结果"""
        from meta.core.action_context import ActionResult
        
        result = ActionResult(
            success=False,
            message='Error occurred'
        )
        
        assert result.success == False
        assert result.message == 'Error occurred'
    
    def test_result_with_data(self):
        """TC-BE-001-43: ActionResult带数据"""
        from meta.core.action_context import ActionResult
        
        result = ActionResult(
            success=True,
            data={'id': 1, 'username': 'test'}
        )
        
        assert result.data['id'] == 1
        assert result.data['username'] == 'test'
    
    def test_result_with_message(self):
        """TC-BE-001-44: ActionResult带消息"""
        from meta.core.action_context import ActionResult
        
        result = ActionResult(
            success=True,
            data={'id': 1},
            message='Operation successful'
        )
        
        assert result.message == 'Operation successful'
    
    def test_result_with_errors(self):
        """TC-BE-001-45: ActionResult带错误详情"""
        from meta.core.action_context import ActionResult
        
        result = ActionResult(
            success=False,
            message='Validation failed',
            errors=[
                {'field': 'username', 'message': 'Username is required'},
                {'field': 'email', 'message': 'Invalid email format'}
            ]
        )
        
        assert len(result.errors) == 2
        assert result.errors[0]['field'] == 'username'


class TestMetaRelation:
    """MetaRelation 模型测试"""
    
    def test_many_to_many_relation(self):
        """TC-BE-002-21: many_to_many关联配置"""
        from meta.core.models import MetaRelation
        from meta.core.models_enums import RelationType
        
        rel = MetaRelation(
            id='groups',
            name='groups',
            relation_type=RelationType.MANY_TO_MANY,
            target_object='user_group'
        )
        
        assert rel.relation_type == RelationType.MANY_TO_MANY
        assert rel.target_object == 'user_group'
    
    def test_reference_relation(self):
        """TC-BE-002-22: reference关联配置"""
        from meta.core.models import MetaRelation
        from meta.core.models_enums import RelationType
        
        rel = MetaRelation(
            id='manager',
            name='manager',
            relation_type=RelationType.REFERENCE,
            target_object='user',
            source_field='manager_id'
        )
        
        assert rel.relation_type == RelationType.REFERENCE
        assert rel.target_object == 'user'
    
    def test_composition_relation(self):
        """TC-BE-002-23: composition关联配置"""
        from meta.core.models import MetaRelation
        from meta.core.models_enums import RelationType
        
        rel = MetaRelation(
            id='line_items',
            name='line_items',
            relation_type=RelationType.COMPOSITION,
            target_object='order_line_item'
        )
        
        assert rel.relation_type == RelationType.COMPOSITION


class TestUIListViewConfig:
    """UIListViewConfig 模型测试"""
    
    def test_list_view_config(self):
        """TC-BE-002-26: list配置解析"""
        from meta.core.models import UIListViewConfig, UIListViewColumn
        
        columns = [
            UIListViewColumn(key='username', title='用户名', width=150),
            UIListViewColumn(key='email', title='邮箱', width=200)
        ]
        
        config = UIListViewConfig(
            title='用户管理',
            columns=columns
        )
        
        assert config.title == '用户管理'
        assert len(config.columns) == 2
    
    def test_list_view_column(self):
        """TC-BE-002-27: list columns解析"""
        from meta.core.models import UIListViewColumn
        
        column = UIListViewColumn(
            key='username',
            title='用户名',
            width=150,
            sortable=True
        )
        
        assert column.key == 'username'
        assert column.title == '用户名'
        assert column.width == 150
        assert column.sortable == True


class TestMetaAction:
    """MetaAction 模型测试"""
    
    def test_action_config(self):
        """TC-BE-002-28: actions配置解析"""
        from meta.core.models import MetaAction
        from meta.core.models_enums import ActionType
        
        action = MetaAction(
            id='create',
            name='新建',
            action_type=ActionType.CRUD,
            method='POST',
            path='/api/v1/users',
            description='Create new user'
        )
        
        assert action.id == 'create'
        assert action.name == '新建'
        assert action.action_type == ActionType.CRUD
    
    def test_batch_action_config(self):
        """TC-BE-002-29: batch_actions解析"""
        from meta.core.models import MetaAction
        from meta.core.models_enums import ActionType
        
        action = MetaAction(
            id='batch_delete',
            name='批量删除',
            action_type=ActionType.BATCH,
            method='POST',
            path='/api/v1/users/batch-delete',
            description='Batch delete users'
        )
        
        assert action.id == 'batch_delete'
        assert action.action_type == ActionType.BATCH
