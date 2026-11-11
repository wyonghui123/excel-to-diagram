# -*- coding: utf-8 -*-
"""封箱 / 解封 / 批量封箱 API（v218 / spec §11.16.5）。

覆盖:
  · scan 预检：可封 / 空内容 / 子容器未封 / 库位缺失
  · seal 成功写 seal 事件；重复封箱 409；不存在 404
  · batch-seal 逐箱独立结果（成功项不回滚）
  · unseal 仅 sealed 可解封
  · 无 seal / unseal 权限 403
  · HU 三表缺失时 scan 404、列表空

ALLOW_RAW_SQL: API 测试直接造 HU 夹具；Factory 无对应支持。
"""

from flask import Flask
import pytest

pytestmark = pytest.mark.unit

from meta.tests.hu_test_doubles import (  # noqa: E402
    add_item,
    add_serial,
    build_db,
    ds,
    service,
)

PERM_READ = 'handling_unit:read'
PERM_SEAL = 'handling_unit:seal'
PERM_UNSEAL = 'handling_unit:unseal'


class _FakeBlacklist:
    def is_blacklisted(self, token):
        return False


class _FakeTokenService:
    @staticmethod
    def verify_token(token):
        return {'user_id': 1, 'username': 'admin'}


@pytest.fixture()
def api(monkeypatch):
    """绕过登录 / 权限查库，用 permitted 集合控制权限码。"""
    import meta.services.auth_middleware as auth_mw
    import meta.api.handling_unit_api as hu_api

    monkeypatch.setattr(auth_mw, '_extract_token', lambda: 'test-token')
    monkeypatch.setattr(auth_mw, 'token_blacklist_service', _FakeBlacklist())
    monkeypatch.setattr(auth_mw, 'TokenService', _FakeTokenService)
    monkeypatch.setattr(hu_api, '_service', None)

    permitted = set()
    monkeypatch.setattr(
        auth_mw, 'evaluate_code',
        lambda user, code: code in permitted)

    def build(conn, allowed=(PERM_READ, PERM_SEAL, PERM_UNSEAL)):
        permitted.clear()
        permitted.update(allowed)
        hu_api.init_handling_unit_service(ds(conn))
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(hu_api.handling_unit_bp)
        return app.test_client()

    build.permitted = permitted
    return build


def _seed_hu(conn, hu_no='HU-1', with_serial=True, location_id=7,
             seal=False, serial_location=7):
    if not conn.execute('SELECT 1 FROM items WHERE id = 900').fetchone():
        add_item(conn)
    hu = service(conn).create_hu({
        'hu_no': hu_no, 'org_id': 1, 'location_id': location_id})
    if with_serial:
        serial_id = add_serial(
            conn, serial_no='SN-' + hu_no, location_id=serial_location)
        service(conn).pack(hu['id'], [{'serial_id': serial_id}])
    if seal:
        service(conn).seal(hu['id'])
    return hu['id']


def _post(client, path, payload=None):
    return client.post(path, json=payload or {})


def test_list_defaults_to_open_status(api):
    conn = build_db()
    _seed_hu(conn, 'HU-OPEN')
    _seed_hu(conn, 'HU-SEALED', seal=True)
    client = api(conn)

    body = client.get('/api/v1/handling-units').get_json()
    assert body['success'] is True
    assert body['data']['total'] == 1
    assert body['data']['items'][0]['hu_no'] == 'HU-OPEN'


def test_scan_returns_can_seal_and_contents(api):
    conn = build_db()
    hu_id = _seed_hu(conn, with_serial=True)
    client = api(conn)

    body = client.get('/api/v1/handling-units/scan?hu_no=HU-1').get_json()
    assert body['success'] is True
    data = body['data']
    assert data['hu']['id'] == hu_id
    assert data['checks']['can_seal'] is True
    assert data['checks']['blockers'] == []
    assert data['contents'][0]['serial_no'] == 'SN-HU-1'


def test_scan_blocks_empty_and_child_unsealed(api):
    conn = build_db()
    _seed_hu(conn, 'HU-EMPTY', with_serial=False)
    parent_id = _seed_hu(conn, 'HU-P', with_serial=False)
    child_id = _seed_hu(conn, 'HU-C', seal=True)
    service(conn).pack(parent_id, [{'child_hu_id': child_id}])
    service(conn).unseal(child_id)
    client = api(conn)

    empty = client.get('/api/v1/handling-units/scan?hu_no=HU-EMPTY').get_json()
    assert empty['data']['checks']['can_seal'] is False
    assert empty['data']['checks']['blockers'][0]['rule'] == 'HU_CONTENT_EMPTY'

    parent = client.get('/api/v1/handling-units/scan?hu_no=HU-P').get_json()
    assert parent['data']['checks']['can_seal'] is False
    blocker = parent['data']['checks']['blockers'][0]
    assert blocker['rule'] == 'HU_CHILD_STATUS_INVALID'
    assert 'HU-C' in blocker['message']
    assert parent['data']['children'][0]['hu_no'] == 'HU-C'


def test_scan_blocks_missing_location(api):
    conn = build_db()
    add_item(conn)
    hu = service(conn).create_hu({'hu_no': 'HU-NOLOC', 'org_id': 1})
    service(conn).pack(hu['id'], [{'item_id': 900, 'qty': 1}])
    client = api(conn)

    body = client.get('/api/v1/handling-units/scan?hu_no=HU-NOLOC').get_json()
    assert body['data']['checks']['can_seal'] is False
    assert body['data']['checks']['blockers'][0]['rule'] \
        == 'HU_CONTENT_LOCATION_MISMATCH'


def test_scan_param_and_not_found(api):
    conn = build_db()
    _seed_hu(conn)
    client = api(conn)

    assert client.get('/api/v1/handling-units/scan').status_code == 400
    resp = client.get('/api/v1/handling-units/scan?hu_no=HU-X')
    assert resp.status_code == 404
    assert resp.get_json()['code'] == 'HU_NOT_FOUND'


def test_seal_writes_event_and_rejects_second_seal(api):
    conn = build_db()
    hu_id = _seed_hu(conn)
    client = api(conn)

    resp = _post(client, '/api/v1/handling-units/%s/seal' % hu_id)
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['status'] == 'sealed'
    assert data['location_id'] == 7

    txn = ds(conn).query(
        'SELECT * FROM hu_transactions WHERE hu_id = ? AND txn_type = ?',
        [hu_id, 'seal'])
    assert len(txn) == 1

    again = _post(client, '/api/v1/handling-units/%s/seal' % hu_id)
    assert again.status_code == 409
    assert again.get_json()['code'] == 'HU_STATUS_INVALID'

    missing = _post(client, '/api/v1/handling-units/999/seal')
    assert missing.status_code == 404
    assert missing.get_json()['code'] == 'HU_NOT_FOUND'


def test_seal_without_permission_403(api):
    conn = build_db()
    hu_id = _seed_hu(conn)
    client = api(conn, allowed=(PERM_READ,))

    resp = _post(client, '/api/v1/handling-units/%s/seal' % hu_id)
    assert resp.status_code == 403
    assert resp.get_json()['code'] == 'FORBIDDEN'


def test_batch_seal_mixed_result_keeps_success(api):
    conn = build_db()
    ok_id = _seed_hu(conn, 'HU-B1')
    sealed_id = _seed_hu(conn, 'HU-B2', seal=True)
    client = api(conn)

    body = _post(client, '/api/v1/handling-units/batch-seal',
                 {'hu_ids': [ok_id, sealed_id, 999]}).get_json()
    assert body['success'] is True
    data = body['data']
    assert data['total'] == 3
    assert data['sealed'] == 1
    assert data['failed'] == 2
    rows = {row['hu_id']: row for row in data['items']}
    assert rows[ok_id]['ok'] is True
    assert rows[sealed_id]['rule'] == 'HU_STATUS_INVALID'
    assert rows[999]['rule'] == 'HU_NOT_FOUND'
    assert ds(conn).query('SELECT * FROM handling_units WHERE id = ?',
                          [ok_id])[0]['status'] == 'sealed'


def test_batch_seal_param_validation(api):
    conn = build_db()
    client = api(conn)

    assert _post(client, '/api/v1/handling-units/batch-seal').status_code == 400
    assert _post(client, '/api/v1/handling-units/batch-seal',
                 {'hu_ids': []}).status_code == 400
    assert _post(client, '/api/v1/handling-units/batch-seal',
                 {'hu_ids': [1] * 51}).status_code == 400
    assert _post(client, '/api/v1/handling-units/batch-seal',
                 {'hu_ids': ['x']}).status_code == 400


def test_unseal_requires_sealed(api):
    conn = build_db()
    open_id = _seed_hu(conn, 'HU-U1')
    sealed_id = _seed_hu(conn, 'HU-U2', seal=True)
    client = api(conn)

    resp = _post(client, '/api/v1/handling-units/%s/unseal' % open_id)
    assert resp.status_code == 409
    assert resp.get_json()['code'] == 'HU_STATUS_INVALID'

    resp = _post(client, '/api/v1/handling-units/%s/unseal' % sealed_id)
    assert resp.status_code == 200
    assert resp.get_json()['data']['status'] == 'open'


def test_scan_and_list_without_hu_tables(api):
    conn = build_db(with_hu=False)
    client = api(conn)

    body = client.get('/api/v1/handling-units').get_json()
    assert body['success'] is True
    assert body['data']['items'] == []

    resp = client.get('/api/v1/handling-units/scan?hu_no=HU-X')
    assert resp.status_code == 404
    assert resp.get_json()['code'] == 'HU_NOT_FOUND'
