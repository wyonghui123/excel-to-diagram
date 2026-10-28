# -*- coding: utf-8 -*-
"""bo_api 写入口 value_help 校验（C3 第三段，2026-10-28）

覆盖范围
--------
`create_bo` / `update_bo` / `update_bo_by_string_id` 在调用 BOFramework 之前
按 `meta.core.value_help_accessor.validate_value_helps` 的判据校验字段值：
- 非法值 ⇒ 400 + `error_code=VALUE_HELP_VALIDATION_FAILED`，且 **BO 的
  create/update 一次都不被调用**（不落库）。
- 合法值 ⇒ 正常放行。
- 未注册的对象类型 ⇒ 不校验（保持既有行为）。

为什么用假数据源 + 假 BO
------------------------
本文件只验证「路由层接线」：判据本身已在 `test_value_help_write_guard.py` 和
`test_value_help_write_validation.py` 覆盖。假数据源可避免触碰 architecture.db，
也不会触发 conftest 的 raw-SQL 整文件 skip。
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)

from meta.core.action_executor import ActionResult
from meta.core.models import FieldType, MetaField, MetaObject, registry
from meta.core.models_value_help import (
    ValueHelpBehavior,
    ValueHelpConfig,
    ValueHelpSource,
)
import meta.api.bo_api as bo_api

TARGET_BO = 't10_api_wh_uom'
GUARD_BO = 't10_api_wh_item'


# ---------------------------------------------------------------- fake infra

class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDataSource:
    """固定 count 的假数据源（count=0 表示"值不在有效选项中"）。"""

    def __init__(self, count=0):
        self.count = count
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, list(params or [])))
        return _FakeCursor((self.count,))


class _RecordingBO:
    """记录 BOFramework 调用；默认返回成功。"""

    def __init__(self, success=True):
        self.success = success
        self.calls = []

    def create(self, object_type, data):
        self.calls.append(('create', object_type, dict(data)))
        return ActionResult(success=self.success, data={})

    def update(self, object_type, obj_id, data):
        self.calls.append(('update', object_type, obj_id, dict(data)))
        return ActionResult(success=self.success, data={})


# ---------------------------------------------------------------- fixtures

def _make_target_obj():
    return MetaObject(
        id=TARGET_BO,
        name='候选集',
        table_name=TARGET_BO,
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER, db_column='id'),
            MetaField(id='code', name='编码', field_type=FieldType.STRING, db_column='code'),
            MetaField(id='status', name='状态', field_type=FieldType.STRING, db_column='status'),
        ],
    )


def _make_guard_obj():
    vh = ValueHelpConfig(
        source=ValueHelpSource(
            type='bo',
            target_bo=TARGET_BO,
            value_field='code',
            value_filter={'status': 'active'},
        ),
        behavior=ValueHelpBehavior(validation=True),
    )
    return MetaObject(
        id=GUARD_BO,
        name='API 写校验对象',
        table_name=GUARD_BO,
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER, db_column='id'),
            MetaField(
                id='uom_code',
                name='计量单位',
                field_type=FieldType.STRING,
                db_column='uom_code',
                value_help=vh,
            ),
        ],
    )


@pytest.fixture(scope='module', autouse=True)
def register_test_objects():
    registry.register(_make_target_obj())
    registry.register(_make_guard_obj())
    yield


@pytest.fixture(scope='module')
def app_client():
    from meta.tests.conftest import get_shared_app

    app, client = get_shared_app()
    return app, client


@pytest.fixture(scope='module')
def admin_headers():
    from meta.services.auth_provider import UserInfo
    from meta.services.token_service import TokenService

    user = UserInfo(
        user_id='1', username='test_user', display_name='Test User',
        email='test@test.com', roles=['admin'], permissions=['*'],
    )
    token, _ = TokenService.create_token(user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_user',
    }


# ---------------------------------------------------------------- create

class TestCreateBoValueHelpGuard:

    def test_invalid_value_rejected_before_create(self, app_client, admin_headers, monkeypatch):
        fake_bo = _RecordingBO()
        monkeypatch.setattr(bo_api, '_get_bo', lambda: fake_bo)
        monkeypatch.setattr(bo_api, '_get_data_source', lambda: _FakeDataSource(count=0))

        _, client = app_client
        resp = client.post(
            f'/api/v2/bo/{GUARD_BO}',
            headers=admin_headers,
            json={'uom_code': 'NOT_EXIST'},
        )

        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False
        assert body['error_code'] == 'VALUE_HELP_VALIDATION_FAILED'
        assert body['errors'] and 'NOT_EXIST' in body['errors'][0]
        assert fake_bo.calls == []

    def test_valid_value_passes_through(self, app_client, admin_headers, monkeypatch):
        fake_bo = _RecordingBO()
        monkeypatch.setattr(bo_api, '_get_bo', lambda: fake_bo)
        monkeypatch.setattr(bo_api, '_get_data_source', lambda: _FakeDataSource(count=1))

        _, client = app_client
        resp = client.post(
            f'/api/v2/bo/{GUARD_BO}',
            headers=admin_headers,
            json={'uom_code': 'PCS'},
        )

        assert resp.status_code == 201
        assert resp.get_json()['success'] is True
        assert len(fake_bo.calls) == 1
        assert fake_bo.calls[0][0] == 'create'

    def test_unregistered_object_skips_validation(self, app_client, admin_headers, monkeypatch):
        """未在 registry 中注册的对象不做 value_help 校验（既有行为不变）。"""
        fake_bo = _RecordingBO()
        monkeypatch.setattr(bo_api, '_get_bo', lambda: fake_bo)
        monkeypatch.setattr(bo_api, '_get_data_source', lambda: _FakeDataSource(count=0))

        _, client = app_client
        resp = client.post(
            '/api/v2/bo/t10_api_wh_unknown',
            headers=admin_headers,
            json={'anything': 'x'},
        )

        assert resp.status_code == 201
        assert len(fake_bo.calls) == 1


# ---------------------------------------------------------------- update

class TestUpdateBoValueHelpGuard:

    def test_int_id_invalid_value_rejected_before_update(self, app_client, admin_headers, monkeypatch):
        fake_bo = _RecordingBO()
        monkeypatch.setattr(bo_api, '_get_bo', lambda: fake_bo)
        monkeypatch.setattr(bo_api, '_get_data_source', lambda: _FakeDataSource(count=0))

        _, client = app_client
        resp = client.put(
            f'/api/v2/bo/{GUARD_BO}/1',
            headers=admin_headers,
            json={'uom_code': 'NOT_EXIST'},
        )

        assert resp.status_code == 400
        body = resp.get_json()
        assert body['error_code'] == 'VALUE_HELP_VALIDATION_FAILED'
        assert fake_bo.calls == []

    def test_string_id_valid_value_passes_through(self, app_client, admin_headers, monkeypatch):
        fake_bo = _RecordingBO()
        monkeypatch.setattr(bo_api, '_get_bo', lambda: fake_bo)
        monkeypatch.setattr(bo_api, '_get_data_source', lambda: _FakeDataSource(count=1))

        _, client = app_client
        resp = client.put(
            f'/api/v2/bo/{GUARD_BO}/CODE-1',
            headers=admin_headers,
            json={'uom_code': 'PCS'},
        )

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        assert len(fake_bo.calls) == 1
        assert fake_bo.calls[0][0] == 'update'

    def test_partial_update_without_guarded_field_passes(self, app_client, admin_headers, monkeypatch):
        """只更新无关字段时不做 value_help 校验（不拿库中旧值误判）。"""
        fake_bo = _RecordingBO()
        monkeypatch.setattr(bo_api, '_get_bo', lambda: fake_bo)
        monkeypatch.setattr(bo_api, '_get_data_source', lambda: _FakeDataSource(count=0))

        _, client = app_client
        resp = client.put(
            f'/api/v2/bo/{GUARD_BO}/1',
            headers=admin_headers,
            json={'id': 1},
        )

        assert resp.status_code == 200
        assert len(fake_bo.calls) == 1
