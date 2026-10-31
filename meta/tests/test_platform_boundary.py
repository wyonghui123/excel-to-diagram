# -*- coding: utf-8 -*-
"""FR-011 平台模块 import 门禁 + NFR-005 三个回滚开关。

覆盖：
- 白名单精确 / 前缀 / `from 包 import 子模块` 命中
- 越界 import（含函数内嵌套 import）在加载期失败，信息含 app 名与模块名
- 真实 apps/ 目录全部通过门禁（现有 3 个声明应用不受影响）
- register_apps 启动期拒绝违规应用
- 三开关默认值 / 取值解析 / 相互独立
- 响应契约、事务守卫、权限 gate 的 strict / shadow / off 行为
"""
import pytest
import yaml
from flask import Flask

from meta.api._response_contract import (
    ResponseContractViolation,
    json_response,
    ok,
)
from meta.core import platform_flags
from meta.core.app_loader import (
    AppManifestError,
    discover_apps,
    load_manifest,
    validate_platform_imports,
)
from meta.core.app_registry import AppRegistrationError, register_apps
from meta.core.bo_framework import TransactionBoundaryError, _check_write_tx_scope
from meta.core.permission_gate import evaluate, evaluate_code
from meta.core.platform_flags import (
    ENV_PERMISSION_GATE,
    ENV_STRICT_CONTRACT,
    ENV_TX_GUARD,
    OFF,
    SHADOW,
    STRICT,
    contract_mode,
    permission_gate_mode,
    tx_guard_mode,
)

FLAGS = (ENV_STRICT_CONTRACT, ENV_TX_GUARD, ENV_PERMISSION_GATE)


def _clear_flags(monkeypatch):
    for name in FLAGS:
        monkeypatch.delenv(name, raising=False)


def _write_app(tmp_path, app_id, *, allowed=None, files=None):
    """造一个最小应用包（app.yaml + 指定源码文件）。"""
    app = {"id": app_id, "name": "边界门禁测试应用", "version": "1.0.0"}
    if allowed is not None:
        app["allowed_platform_modules"] = allowed
    app_dir = tmp_path / app_id
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump({"app": app}, allow_unicode=True), encoding="utf-8"
    )
    for rel, source in (files or {}).items():
        path = app_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return app_dir


class TestImportGate:
    """FR-011：allowed_platform_modules 的加载期执行点"""

    def test_allowed_exact_module_passes(self, tmp_path):
        app_dir = _write_app(
            tmp_path, "ok_app", allowed=["meta.core.datasource"],
            files={"blueprints/api.py": "from meta.core.datasource import resolve_data_source\n"},
        )
        validate_platform_imports(load_manifest(app_dir))

    def test_allowed_prefix_covers_submodule(self, tmp_path):
        app_dir = _write_app(
            tmp_path, "prefix_app", allowed=["meta.core"],
            files={"helper.py": "import meta.core.bo_framework.engine\n"},
        )
        validate_platform_imports(load_manifest(app_dir))

    def test_from_package_import_allowed_when_submodule_declared(self, tmp_path):
        app_dir = _write_app(
            tmp_path, "from_app", allowed=["meta.core.datasource"],
            files={"helper.py": "from meta.core import datasource\n"},
        )
        validate_platform_imports(load_manifest(app_dir))

    def test_nested_import_is_scanned(self, tmp_path):
        app_dir = _write_app(
            tmp_path, "nested_app", allowed=["meta.core.datasource"],
            files={"api.py": (
                "def handler():\n"
                "    from meta.core.action_executor import ActionRegistry\n"
                "    return ActionRegistry\n"
            )},
        )
        with pytest.raises(AppManifestError, match="action_executor"):
            validate_platform_imports(load_manifest(app_dir))

    def test_unauthorized_import_raises_with_app_and_module(self, tmp_path):
        app_dir = _write_app(
            tmp_path, "bad_app", allowed=[],
            files={"blueprints/api.py": "import meta.core.bo_framework\n"},
        )
        with pytest.raises(AppManifestError) as exc:
            validate_platform_imports(load_manifest(app_dir))
        message = str(exc.value)
        assert "bad_app" in message
        assert "meta.core.bo_framework" in message
        assert "allowed_platform_modules" in message

    def test_all_real_apps_pass_gate(self):
        manifests = discover_apps()
        assert manifests, "apps/ 目录应至少有一个应用包"
        for manifest in manifests.values():
            validate_platform_imports(manifest)

    def test_register_apps_aborts_on_violation(self, tmp_path):
        _write_app(
            tmp_path, "violating_app", allowed=[],
            files={"helper.py": "from meta.core.models import registry\n"},
        )
        with pytest.raises(AppRegistrationError, match="import 门禁"):
            register_apps(
                Flask("import_gate_probe"),
                app_ids=["violating_app"],
                apps_root=tmp_path,
                register_schemas=False,
            )


class TestPlatformFlags:
    """NFR-005：三个开关的取值与默认值"""

    def test_defaults(self, monkeypatch):
        _clear_flags(monkeypatch)
        assert contract_mode() == SHADOW
        assert tx_guard_mode() == SHADOW
        assert permission_gate_mode() == STRICT

    def test_each_switch_parses_strict_and_off(self, monkeypatch):
        pairs = (
            (ENV_STRICT_CONTRACT, contract_mode),
            (ENV_TX_GUARD, tx_guard_mode),
            (ENV_PERMISSION_GATE, permission_gate_mode),
        )
        for name, getter in pairs:
            _clear_flags(monkeypatch)
            monkeypatch.setenv(name, "1")
            assert getter() == STRICT
            monkeypatch.setenv(name, "0")
            assert getter() == OFF

    def test_invalid_value_falls_back_to_default(self):
        assert platform_flags.parse_mode("bogus", SHADOW, "X") == SHADOW
        assert platform_flags.parse_mode("", STRICT, "X") == STRICT

    def test_switches_are_independent(self, monkeypatch):
        _clear_flags(monkeypatch)
        monkeypatch.setenv(ENV_STRICT_CONTRACT, "1")
        assert contract_mode() == STRICT
        assert tx_guard_mode() == SHADOW
        assert permission_gate_mode() == STRICT


class TestContractGuard:
    """PLATFORM_STRICT_CONTRACT"""

    @pytest.fixture
    def app_ctx(self):
        app = Flask("contract_guard_probe")
        with app.app_context():
            yield app

    def test_default_shadow_allows(self, monkeypatch, app_ctx):
        _clear_flags(monkeypatch)
        response, status = json_response({"items": []})
        assert status == 200
        assert response.get_json() == {"items": []}

    def test_strict_rejects_json_response(self, monkeypatch, app_ctx):
        monkeypatch.setenv(ENV_STRICT_CONTRACT, "1")
        with pytest.raises(ResponseContractViolation, match="json_response"):
            json_response({"items": []})

    def test_strict_rejects_list_in_ok(self, monkeypatch, app_ctx):
        monkeypatch.setenv(ENV_STRICT_CONTRACT, "strict")
        with pytest.raises(ResponseContractViolation, match="ok_list"):
            ok([1, 2])

    def test_off_allows_list_in_ok(self, monkeypatch, app_ctx):
        monkeypatch.setenv(ENV_STRICT_CONTRACT, "0")
        response = ok([1, 2])
        assert response.get_json()["data"] == [1, 2]


class TestTxGuard:
    """PLATFORM_TX_GUARD"""

    class _DS:
        def __init__(self, in_transaction=False):
            self.in_transaction = in_transaction

    def test_default_shadow_does_not_raise(self, monkeypatch):
        _clear_flags(monkeypatch)
        _check_write_tx_scope("user", "crud_create", self._DS())

    def test_strict_raises_when_not_in_transaction(self, monkeypatch):
        monkeypatch.setenv(ENV_TX_GUARD, "1")
        with pytest.raises(TransactionBoundaryError, match="TX-GUARD"):
            _check_write_tx_scope("user", "crud_create", self._DS())

    def test_strict_allows_when_already_in_transaction(self, monkeypatch):
        monkeypatch.setenv(ENV_TX_GUARD, "strict")
        _check_write_tx_scope("user", "crud_create", self._DS(in_transaction=True))

    def test_off_never_raises(self, monkeypatch):
        monkeypatch.setenv(ENV_TX_GUARD, "0")
        _check_write_tx_scope("user", "crud_create", self._DS())


class TestPermissionGate:
    """PLATFORM_PERMISSION_GATE"""

    def test_default_strict_denies(self, monkeypatch):
        _clear_flags(monkeypatch)
        assert evaluate_code({"permissions": []}, "user:read") is False

    def test_shadow_allows(self, monkeypatch):
        monkeypatch.setenv(ENV_PERMISSION_GATE, "shadow")
        assert evaluate_code({"permissions": []}, "user:read") is True
        decision = evaluate(
            {"user_id": 1, "permissions": []}, "no_such_object_2026", "crud_read",
        )
        assert decision.allowed is True

    def test_off_allows(self, monkeypatch):
        monkeypatch.setenv(ENV_PERMISSION_GATE, "0")
        assert evaluate_code({"permissions": []}, "user:read") is True

    def test_granted_user_passes_in_strict_mode(self, monkeypatch):
        _clear_flags(monkeypatch)
        assert evaluate_code({"permissions": ["user:read"]}, "user:read") is True
