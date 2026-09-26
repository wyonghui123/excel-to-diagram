# -*- coding: utf-8 -*-
"""[A 可见性 2026-09-25] /health 暴露已加载应用 + 启动落盘 runtime_apps.json。

目标（排查"这台服务器部署了哪些 app"）:
- `/health`（唯一存活的无鉴权探活点）返回 apps / apps_mode / enabled_apps
- 启动期把"本进程实际加载的应用"落盘到平台库同目录 runtime_apps.json（事实副本）
- legacy 模式（未设置 ENABLED_APPS）: apps == []、mode == legacy ⇒ 零行为变化
- 落盘失败绝不阻断启动

执行: python d:\\filework\\test.py --file meta/tests/test_health_apps_visibility_20260925.py
"""
import json
import os
import warnings
from pathlib import Path

import pytest

from meta.core.app_registry import (
    RUNTIME_APPS_FILENAME,
    get_loaded_apps,
    reset_app_routing_index,
    write_runtime_apps_snapshot,
)

_ENV_KEYS = ("SQLITE_DB_PATH", "SQLITE_DB_DIR", "APP_DB_ROUTING", "ENABLED_APPS")


def _keep_env():
    return {k: os.environ.get(k) for k in _ENV_KEYS}


def _restore_env(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="module")
def enabled_app(tmp_path_factory):
    """启用 hello_world 的 app 实例（全文件唯一一次 create_app, §10.12 教训）。

    平台库用 create_app(db_path=...) 参数指向临时目录, 不污染仓库 meta/architecture.db。
    """
    previous = _keep_env()
    data_dir = tmp_path_factory.mktemp("appdata")
    os.environ["SQLITE_DB_DIR"] = str(data_dir)
    os.environ["APP_DB_ROUTING"] = "1"
    os.environ["ENABLED_APPS"] = "hello_world"
    os.environ.pop("SQLITE_DB_PATH", None)
    db_path = data_dir / "platform.db"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from meta.server import create_app
        app = create_app(db_path=str(db_path))
    app.config["TESTING"] = True
    try:
        yield {"app": app, "db_path": db_path, "data_dir": data_dir}
    finally:
        _restore_env(previous)
        reset_app_routing_index()


class TestHealthExposesApps:
    """`/health` 契约: 既有字段不变 + 新增应用维度字段。"""

    def test_health_keeps_legacy_fields(self, enabled_app):
        resp = enabled_app["app"].test_client().get("/health")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert body["service"] == "arch-data-manage-api"

    def test_health_lists_loaded_apps(self, enabled_app):
        body = enabled_app["app"].test_client().get("/health").get_json()
        assert body["apps_mode"] == "enabled"
        assert body["enabled_apps"] == ["hello_world"]
        assert [a["id"] for a in body["apps"]] == ["hello_world"]
        first = body["apps"][0]
        assert first["name"] == "示例应用"
        assert first["version"] == "1.0.0"
        assert first["route_prefix"] == "/api/v1/apps/hello_world"
        assert first["dir"].endswith(os.path.join("apps", "hello_world"))

    def test_registry_state_matches_health(self, enabled_app):
        """get_loaded_apps() 是 /health 的数据源, 两者必须一致。"""
        body = enabled_app["app"].test_client().get("/health").get_json()
        assert get_loaded_apps() == body["apps"]


class TestRuntimeSnapshot:
    """启动落盘的事实副本（服务停止 / 日志滚动后仍可查）。"""

    def test_snapshot_written_next_to_platform_db(self, enabled_app):
        snap = Path(enabled_app["db_path"]).parent / RUNTIME_APPS_FILENAME
        assert snap.is_file(), f"未落盘: {snap}"
        payload = json.loads(snap.read_text(encoding="utf-8"))
        assert payload["mode"] == "enabled"
        assert payload["enabled_apps"] == ["hello_world"]
        assert [a["id"] for a in payload["apps"]] == ["hello_world"]
        assert payload["db_path"] == str(enabled_app["db_path"])
        assert payload["apps_root"].endswith(os.path.join("", "apps"))
        assert payload["pid"] > 0
        assert payload["hostname"]
        assert payload["written_at"]

    def test_legacy_mode_records_empty_apps(self, tmp_path):
        """未启用应用: 清单为空 + 落盘 mode=legacy（零行为变化）。"""
        reset_app_routing_index()
        assert get_loaded_apps() == []
        out = write_runtime_apps_snapshot(str(tmp_path / "legacy.db"))
        assert out is not None
        payload = json.loads(Path(out).read_text(encoding="utf-8"))
        assert payload["mode"] == "legacy"
        assert payload["apps"] == []

    def test_snapshot_failure_never_raises(self, tmp_path):
        """落盘失败（父目录不存在）只返回 None, 绝不抛异常。"""
        out = write_runtime_apps_snapshot(
            str(tmp_path / "no" / "such" / "dir" / "platform.db")
        )
        assert out is None