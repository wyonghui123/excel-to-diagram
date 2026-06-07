# -*- coding: utf-8 -*-
"""
[MODULE] 共享 Mock 类
[DESCRIPTION] 提供所有测试文件共享的 Mock 类，用于模拟系统组件

使用方式：
1. 在测试文件中导入:
   from meta.tests.shared.mocks import MockActionContext, MockResult

2. 在测试中使用:
   context = MockActionContext(action='crud_query', object_type='user')
   result = MockResult(success=True, data=[...])

可用的 Mock 类：
- MockResult: 模拟操作结果对象
- MockActionContext: 模拟 ActionContext 上下文
- MockActionResult: 模拟操作结果（用于权限检查）
"""

from unittest.mock import Mock, MagicMock


# ==================== Result Mocks ====================

class MockResult:
    """
    [MOCK] 操作结果模拟
    [DESCRIPTION] 模拟 API 操作或服务调用的返回结果
    [ATTRIBUTES]
        - success: bool - 操作是否成功
        - data: Any - 返回数据
        - error: str - 错误信息（如果失败）
        - code: int - 状态码
    [EXAMPLE]
        result = MockResult(success=True, data={'id': 1, 'name': 'test'})
        result = MockResult(success=False, error='Invalid input')
    """

    def __init__(self, success=True, data=None, error=None, code=200):
        self.success = success
        self.data = data
        self.error = error
        self.code = code

    def __repr__(self):
        if self.success:
            return f"<MockResult success=True data={self.data}>"
        return f"<MockResult success=False error={self.error}>"

    def is_success(self):
        return self.success

    def get_data(self):
        return self.data


class MockActionResult:
    """
    [MOCK] Action 执行结果模拟
    [DESCRIPTION] 模拟拦截器或动作执行器的返回结果
    [ATTRIBUTES]
        - allowed: bool - 是否允许执行
        - data: Any - 返回数据
        - message: str - 结果消息
        - error: str - 错误信息
    [EXAMPLE]
        result = MockActionResult(allowed=True, data={'id': 1})
        result = MockActionResult(allowed=False, message='Permission denied')
    """

    def __init__(self, allowed=True, data=None, message=None, error=None):
        self.allowed = allowed
        self.data = data
        self.message = message
        self.error = error

    def __repr__(self):
        if self.allowed:
            return f"<MockActionResult allowed=True data={self.data}>"
        return f"<MockActionResult allowed=False message={self.message}>"

    def is_allowed(self):
        return self.allowed

    def get_data(self):
        return self.data


# ==================== Context Mocks ====================

class MockActionContext:
    """
    [MOCK] ActionContext 上下文模拟
    [DESCRIPTION] 模拟拦截器链中的 ActionContext 对象
    [ATTRIBUTES]
        - object_type: str - 对象类型 (user, role, domain, etc.)
        - object_id: Any - 对象 ID
        - action: str - 操作类型 (crud_query, create, update, delete, etc.)
        - params: dict - 请求参数
        - user_id: int - 用户 ID
        - data_source: DataSource - 数据源
        - meta_object: MetaObject - 元对象
        - result: MockResult - 操作结果
        - extra: dict - 额外数据
    [PROPERTIES]
        - is_query_action: bool - 是否为查询操作
        - is_write_action: bool - 是否为写操作
    [EXAMPLE]
        context = MockActionContext(
            action='crud_query',
            object_type='user',
            object_id=1,
            user_id=1
        )
    """

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
        self._changes = kwargs.get('_changes', None)
        self._old_data = kwargs.get('_old_data', None)
        self._new_data = kwargs.get('_new_data', None)

    @property
    def is_query_action(self):
        """检查是否为查询操作"""
        return self.action in ('crud_query', 'query', 'list', 'detail')

    @property
    def is_write_action(self):
        """检查是否为写操作"""
        return self.action in ('create', 'update', 'delete', 'batch_create', 'batch_update', 'batch_delete')

    def get_object_type(self):
        return self.object_type

    def get_object_id(self):
        return self.object_id

    def get_action(self):
        return self.action

    def get_user_id(self):
        return self.user_id

    def get_param(self, key, default=None):
        """获取参数值"""
        return self.params.get(key, default)

    def set_result(self, result):
        """设置结果"""
        self.result = result

    def get_result(self):
        """获取结果"""
        return self.result

    def set_extra(self, key, value):
        """设置额外数据"""
        self.extra[key] = value

    def get_extra(self, key, default=None):
        """获取额外数据"""
        return self.extra.get(key, default)

    def __repr__(self):
        return f"<MockActionContext action={self.action} object_type={self.object_type} object_id={self.object_id}>"


# ==================== MetaObject Mock ====================

class MockMetaObject:
    """
    [MOCK] MetaObject 元对象模拟
    [DESCRIPTION] 模拟业务对象的元数据
    [ATTRIBUTES]
        - id: str - 对象 ID
        - name: str - 对象名称
        - fields: list - 字段列表
        - aspects: list - 切面列表
        - semantics: dict - 语义配置
    [EXAMPLE]
        meta_obj = MockMetaObject(id='user', name='User')
    """

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'mock_object')
        self.name = kwargs.get('name', 'Mock Object')
        self.fields = kwargs.get('fields', [])
        self.aspects = kwargs.get('aspects', [])
        self.semantics = kwargs.get('semantics', {})
        self.mutability = kwargs.get('mutability', 'editable')
        self.deletability = kwargs.get('deletability', None)
        self.readonly_always_fields = kwargs.get('readonly_always_fields', [])
        self.immutable_fields = kwargs.get('immutable_fields', [])

    def get_field(self, field_id):
        """获取字段"""
        return next((f for f in self.fields if getattr(f, 'id', None) == field_id), None)

    def has_aspect(self, aspect_name):
        """检查是否有指定切面"""
        return aspect_name in self.aspects

    def __repr__(self):
        return f"<MockMetaObject id={self.id} name={self.name}>"


class MockMetaField:
    """
    [MOCK] MetaField 元字段模拟
    [DESCRIPTION] 模拟业务对象的字段元数据
    [ATTRIBUTES]
        - id: str - 字段 ID
        - name: str - 字段名称
        - field_type: str - 字段类型
        - semantics: dict - 语义配置
    [EXAMPLE]
        field = MockMetaField(id='username', name='Username', field_type='string')
    """

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'mock_field')
        self.name = kwargs.get('name', 'Mock Field')
        self.field_type = kwargs.get('field_type', 'string')
        self.semantics = kwargs.get('semantics', {})
        self.required = kwargs.get('required', False)
        self.readonly = kwargs.get('readonly', False)
        self.default_value = kwargs.get('default_value', None)

    def get_semantic(self, key, default=None):
        """获取语义配置"""
        if isinstance(self.semantics, dict):
            return self.semantics.get(key, default)
        return getattr(self.semantics, key, default)

    def has_semantic(self, key):
        """检查是否有指定语义"""
        if isinstance(self.semantics, dict):
            return key in self.semantics
        return hasattr(self.semantics, key)

    def __repr__(self):
        return f"<MockMetaField id={self.id} name={self.name} type={self.field_type}>"


# ==================== DataSource Mock ====================

class MockDataSource:
    """
    [MOCK] DataSource 数据源模拟
    [DESCRIPTION] 模拟数据库访问接口
    [METHODS]
        - execute: 执行 SQL
        - query: 查询数据
        - insert: 插入数据
        - update: 更新数据
        - delete: 删除数据
    [EXAMPLE]
        ds = MockDataSource()
        ds.execute("INSERT INTO users VALUES (1, 'test')")
    """

    def __init__(self):
        self._storage = {}
        self._call_history = []

    def execute(self, sql, params=None):
        """执行 SQL"""
        self._call_history.append(('execute', sql, params))
        return MockResult(success=True, data={'affected_rows': 1})

    def query(self, sql, params=None):
        """查询数据"""
        self._call_history.append(('query', sql, params))
        return MockResult(success=True, data=[])

    def insert(self, table, data):
        """插入数据"""
        self._call_history.append(('insert', table, data))
        return MockResult(success=True, data={'id': 1})

    def update(self, table, data, where):
        """更新数据"""
        self._call_history.append(('update', table, data, where))
        return MockResult(success=True, data={'affected_rows': 1})

    def delete(self, table, where):
        """删除数据"""
        self._call_history.append(('delete', table, where))
        return MockResult(success=True, data={'affected_rows': 1})

    def get_history(self):
        """获取调用历史"""
        return self._call_history

    def clear_history(self):
        """清空调用历史"""
        self._call_history = []


# ==================== Factory Functions ====================

def create_mock_context(action='crud_query', object_type='user', **kwargs):
    """
    [FACTORY] 创建 MockActionContext 的便捷函数
    [DESCRIPTION] 简化 MockActionContext 的创建过程
    [PARAMETERS]
        - action: str - 操作类型
        - object_type: str - 对象类型
        - **kwargs: 其他参数传递给 MockActionContext
    [EXAMPLE]
        context = create_mock_context('create', 'user', object_id=1)
    """
    defaults = {
        'action': action,
        'object_type': object_type,
        'user_id': 1,
        'params': {},
        'extra': {}
    }
    defaults.update(kwargs)
    return MockActionContext(**defaults)


def create_mock_result(success=True, data=None, error=None, **kwargs):
    """
    [FACTORY] 创建 MockResult 的便捷函数
    [DESCRIPTION] 简化 MockResult 的创建过程
    [PARAMETERS]
        - success: bool - 是否成功
        - data: Any - 返回数据
        - error: str - 错误信息
        - **kwargs: 其他参数传递给 MockResult
    [EXAMPLE]
        result = create_mock_result(True, {'id': 1})
    """
    defaults = {
        'success': success,
        'data': data,
        'error': error
    }
    defaults.update(kwargs)
    return MockResult(**defaults)


def create_mock_meta_object(object_id='user', **kwargs):
    """
    [FACTORY] 创建 MockMetaObject 的便捷函数
    [DESCRIPTION] 简化 MockMetaObject 的创建过程
    [PARAMETERS]
        - object_id: str - 对象 ID
        - **kwargs: 其他参数传递给 MockMetaObject
    [EXAMPLE]
        meta_obj = create_mock_meta_object('user', name='User')
    """
    defaults = {
        'id': object_id,
        'name': object_id.title(),
        'fields': []
    }
    defaults.update(kwargs)
    return MockMetaObject(**defaults)
