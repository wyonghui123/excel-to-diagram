# -*- coding: utf-8 -*-
"""视图对象只读护栏回归测试 (2026-10-05, F1 治理分域 C 方案前置)。

背景:
    通用 CRUD 路由 (POST/PUT/DELETE /<object_type>) 对任意 BO 均开放,
    在真视图 (YAML `object_type: view` → ObjectType.VIEW) 上写入会落到
    SQLite 报错 (500)。护栏在 ManageService 服务层前置拦截, 返回
    ActionResult.fail(error='READ_ONLY_VIEW') → API 侧映射 400。

    注意区分两种"视图":
      - 真视图   : `object_type: view`               → ObjectType.VIEW  → 拒写
      - 逻辑视图 : `is_view: true` (物理表上的别名)  → ObjectType.ENTITY → 不拦
"""
import os

import pytest

from meta.core.models import MetaObject, ObjectType
from meta.services.manage_service import (
    ManageService, CreateRequest, UpdateRequest, DeleteRequest,
)


def _db_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )


@pytest.fixture()
def service():
    from meta.core.datasource import get_data_source
    return ManageService(get_data_source("sqlite", database=_db_path()))


def _view_obj() -> MetaObject:
    return MetaObject(
        id='_test_ro_view',
        name='测试只读视图',
        table_name='v_test_ro',
        object_type=ObjectType.VIEW,
    )


def _logical_view_obj() -> MetaObject:
    """模拟 is_view: true 的物理表逻辑视图 (如 permission_resource)。"""
    return MetaObject(
        id='_test_logical_view',
        name='测试逻辑视图',
        table_name='permissions',   # 真实存在的物理表
        object_type=ObjectType.ENTITY,
        is_view=True,               # 仅逻辑标记, 不是真视图
    )


class TestReadOnlyViewGuard:

    def test_guard_rejects_real_view(self, service):
        result = service._reject_if_readonly_view(_view_obj())
        assert result is not None
        assert result.success is False
        assert result.error == 'READ_ONLY_VIEW'

    def test_guard_allows_entity(self, service):
        entity = MetaObject(id='_test_entity', name='测试实体',
                            table_name='orgs', object_type=ObjectType.ENTITY)
        assert service._reject_if_readonly_view(entity) is None

    def test_guard_allows_logical_view(self, service):
        """`is_view: true` 的逻辑视图 (object_type 仍 entity) 不应被拦。"""
        assert service._reject_if_readonly_view(_logical_view_obj()) is None

    def test_create_rejected(self, service, monkeypatch):
        monkeypatch.setattr(ManageService, '_get_meta_object',
                            lambda self, ot: _view_obj())
        result = service.create(CreateRequest(object_type='_test_ro_view', data={'x': 1}))
        assert result.success is False
        assert result.error == 'READ_ONLY_VIEW'

    def test_update_rejected(self, service, monkeypatch):
        monkeypatch.setattr(ManageService, '_get_meta_object',
                            lambda self, ot: _view_obj())
        result = service.update(UpdateRequest(object_type='_test_ro_view', id=1, data={'x': 2}))
        assert result.success is False
        assert result.error == 'READ_ONLY_VIEW'

    def test_delete_rejected(self, service, monkeypatch):
        monkeypatch.setattr(ManageService, '_get_meta_object',
                            lambda self, ot: _view_obj())
        result = service.delete(DeleteRequest(object_type='_test_ro_view', id=1))
        assert result.success is False
        assert result.error == 'READ_ONLY_VIEW'

    def test_real_logical_view_not_blocked_in_registry(self, service):
        """真实例回归: permission_resource (is_view:true) 不应被护栏拦下。"""
        from meta.core.models import registry
        obj = registry.get('permission_resource')
        if obj is None:            # registry 未加载时跳过 (不误报)
            pytest.skip('registry 未加载 permission_resource')
        assert obj.object_type != ObjectType.VIEW
        assert service._reject_if_readonly_view(obj) is None