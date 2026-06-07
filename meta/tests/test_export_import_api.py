# -*- coding: utf-8 -*-
"""
GAP-029: export_import_api (12+ 端点)

[SUBCLASS] 拆 3 个子类: TestExport / TestImport / TestDownload
"""
import pytest
from meta.tests.shared.assertions import expect, assert_data_contains, HTTPStatus

# 状态码域
VALIDATION = HTTPStatus.VALIDATION_AUTH
OK_AUTH = HTTPStatus.OK_AUTH
NOT_FOUND_AUTH = HTTPStatus.NOT_FOUND_AUTH
NOT_FOUND_500 = HTTPStatus.NOT_FOUND_500
PATH_TRAVERSAL = (400, 403, 404, 500)


EXPORT_VALID_CASES = [
    pytest.param({'object_type': 'domain', 'scope': 'single'}, id='single'),
    pytest.param({'object_type': 'domain', 'scope': 'cascade'}, id='cascade'),
    pytest.param(
        {'object_type': 'domain', 'scope': 'single',
         'options': {'include_metadata_sheet': True, 'protect_sheet': False}},
        id='with_options'
    ),
    pytest.param(
        {'object_type': 'domain', 'scope': 'single', 'page': 1, 'page_size': 10},
        id='with_pagination'
    ),
]

EXPORT_MISSING_CASES = [
    pytest.param({}, id='missing_body'),
    pytest.param({'scope': 'single'}, id='missing_object_type'),
]

IMPORT_NOT_FOUND_CASES = [
    pytest.param('/api/v1/import/template/nonexistent_type', id='import_template'),
    pytest.param('/api/v1/import-export/config/nonexistent_type', id='import_export_config'),
]


class TestExport:
    """export 系列端点 (8 测试)"""

    @pytest.mark.parametrize('body', EXPORT_MISSING_CASES)
    def test_export_missing(self, api_client, body):
        expect(api_client, 'post', '/api/v1/export', VALIDATION, json=body)

    @pytest.mark.parametrize('body', EXPORT_VALID_CASES)
    def test_export_valid(self, api_client, body):
        expect(api_client, 'post', '/api/v1/export', OK_AUTH, json=body)

    def test_export_async_missing_object_type(self, api_client):
        expect(api_client, 'post', '/api/v1/export/async', VALIDATION, json={})

    def test_export_async_valid(self, api_client):
        r = expect(api_client, 'post', '/api/v1/export/async', OK_AUTH, json={
            'object_type': 'domain', 'scope': 'cascade'
        })
        assert_data_contains(r, 'task_id', scope='data')

    def test_export_status_nonexistent(self, api_client):
        expect(api_client, 'get', '/api/v1/export/status/nonexistent_task_id', NOT_FOUND_AUTH)


class TestImport:
    """import 系列端点 (4 测试)"""

    def test_import_no_file(self, api_client):
        expect(api_client, 'post', '/api/v1/import', VALIDATION, data={})

    def test_import_invalid_extension(self, api_client, tmp_path):
        fake_file = tmp_path / "test.txt"
        fake_file.write_text("not an excel")
        with open(fake_file, 'rb') as f:
            expect(api_client, 'post', '/api/v1/import', VALIDATION,
                   data={'file': (f, 'test.txt')},
                   content_type='multipart/form-data')

    @pytest.mark.parametrize('endpoint', IMPORT_NOT_FOUND_CASES)
    def test_template_config_not_found(self, api_client, endpoint):
        expect(api_client, 'get', endpoint, NOT_FOUND_AUTH)


class TestDownload:
    """download 系列端点 (2 测试)"""

    def test_download_export_path_traversal(self, api_client):
        expect(api_client, 'get', '/api/v1/export/download/../../../etc/passwd', PATH_TRAVERSAL)

    def test_download_export_nonexistent(self, api_client):
        expect(api_client, 'get', '/api/v1/export/download/nonexistent_file.xlsx', NOT_FOUND_500)
