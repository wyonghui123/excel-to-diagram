# -*- coding: utf-8 -*-
"""T13-5 UI 元数据聚合端点测试

覆盖 GET /api/v1/meta/<object_type>/ui-meta（meta_bp，与 §13.4 骨架一致）：
- 载荷形状完整（schema_version/object_type/label/partial/list/detail/form/filters/field_policies/actions）
- 单块构建异常 → partial=True，其余块正常
- 鉴权口径与旧 form-view 一致
- ui-meta.form 与旧 form-view 逐字段一致
"""

import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration

OBJECT_TYPE = "enum_type"
UI_META_URL = f"/api/v1/meta/{OBJECT_TYPE}/ui-meta"
FORM_VIEW_URL = f"/api/v1/meta/{OBJECT_TYPE}/form-view"

REQUIRED_KEYS = (
    "schema_version", "object_type", "label", "partial",
    "actions", "list", "detail", "form", "filters", "field_policies",
)


@pytest.fixture(scope="module")
def api_client():
    from meta.tests.conftest import get_shared_app

    return get_shared_app()[1]


def _fetch_ui_meta(client):
    resp = client.get(UI_META_URL)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body.get("success") is True
    return body["data"]


class TestUiMetaShape:
    def test_shape_complete(self, api_client):
        data = _fetch_ui_meta(api_client)
        for key in REQUIRED_KEYS:
            assert key in data, f"缺少字段 {key}"
        assert data["object_type"] == OBJECT_TYPE
        assert data["partial"] is False
        assert isinstance(data["schema_version"], str) and data["schema_version"]
        assert isinstance(data["label"], str) and data["label"]
        assert isinstance(data["list"], dict) and "columns" in data["list"]
        assert isinstance(data["detail"], dict) and "sections" in data["detail"]
        assert isinstance(data["form"], dict) and "fields" in data["form"]
        assert isinstance(data["filters"], list)
        assert isinstance(data["field_policies"], dict)
        assert isinstance(data["actions"], list)

    def test_actions_are_declaration_only(self, api_client):
        """ui-meta 不返回权限判定结果：动作不得携带 enabled 字段。"""
        data = _fetch_ui_meta(api_client)
        for action in data["actions"]:
            assert "enabled" not in action

    def test_form_matches_legacy_form_view(self, api_client):
        legacy_resp = api_client.get(FORM_VIEW_URL)
        assert legacy_resp.status_code == 200
        legacy = legacy_resp.get_json()["data"]
        meta_form = _fetch_ui_meta(api_client)["form"]

        legacy_fields = [fid for section in legacy["sections"] for fid in section["fields"]]
        meta_fields = [field["key"] for field in meta_form["fields"]]
        assert meta_fields == legacy_fields

        assert [s["title"] for s in legacy["sections"]] == [
            s["label"] for s in meta_form["sections"]
        ]
        assert [list(s["fields"]) for s in legacy["sections"]] == [
            list(s["fields"]) for s in meta_form["sections"]
        ]


class TestUiMetaPartial:
    def test_block_failure_sets_partial_true(self, api_client, monkeypatch):
        from meta.api import meta_api

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(meta_api, "_form_block", _boom)
        data = _fetch_ui_meta(api_client)

        assert data["partial"] is True
        assert data["form"] == {"sections": [], "tabs": [], "fields": []}
        # 其余块不受影响
        assert data["object_type"] == OBJECT_TYPE
        assert data["list"]["columns"] or data["list"] == {"columns": [], "actions": []}
        assert isinstance(data["filters"], list)

    def test_unknown_object_type_degrades_gracefully(self, api_client):
        resp = api_client.get("/api/v1/meta/no_such_object/ui-meta")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        data = body["data"]
        assert data["label"] == "no_such_object"


class TestUiMetaAuth:
    def test_auth_same_as_legacy_form_view(self, api_client):
        """鉴权口径与相邻 form-view 一致（同环境下同状态码）。"""
        legacy = api_client.get(FORM_VIEW_URL)
        meta = api_client.get(UI_META_URL)
        assert meta.status_code == legacy.status_code