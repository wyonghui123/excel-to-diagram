# -*- coding: utf-8 -*-
"""[多产品平台 S6 / G5] 应用依赖校验测试

覆盖:
- app.yaml `requires:` 段解析（未声明 = None 零影响 / 结构非法报错）
- 版本比较语义（右侧补零 / 六种操作符 / 非法约束）
- 平台版本区间校验（min / max / 越界 / 非法 / 平台版本不可解析时跳过）
- requires.bo / requires.rules 依赖缺失
- 本应用 doc_flow 规则引用的 source_bo / target_bo 缺失
- 多应用整体校验（跨应用引用在启用集合内成立）
- 安装期闸门（install_app 拒装）与启用期闸门（register_apps 拒绝启用）

边界: 本模块只测「声明 → 校验 → 拒绝」；column_version 本版仅登记不校验。
本文件零裸写 SQL 字面量: 建表走 ensure_installed_apps_table / DataSource DDL API。

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §五 S6
"""
import sys
from pathlib import Path

import pytest
import yaml
from flask import Flask

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from meta.core.app_dependency import (  # noqa: E402
    DependencyError,
    _cmp,
    _parse_version,
    _satisfies,
    assert_app_set,
    collect_declared_ids,
    get_platform_version,
    validate_app_set,
    validate_dependencies,
)
from meta.core.app_installer import (  # noqa: E402
    AppInstallError,
    ensure_installed_apps_table,
    install_app,
)
from meta.core.app_loader import (  # noqa: E402
    AppManifest,
    AppManifestError,
    DocFlowRuleDecl,
    RequiresDecl,
    load_manifest,
)
from meta.core.app_package import build_package  # noqa: E402
from meta.core.app_registry import AppRegistrationError, register_apps  # noqa: E402
from meta.core.datasource import get_data_source  # noqa: E402


def _manifest(tmp_path, app_id="app_a", *, min_version="", max_version="",
              requires=None, rules=(), own_bo_ids=()) -> AppManifest:
    """构造内存 manifest（不读文件；own_bo_ids 用参数显式给定，避免 IO）。"""
    schemas = []
    for bo in own_bo_ids:
        rel = f"schemas/{bo}.yaml"
        path = tmp_path / app_id / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump({"id": bo, "name": bo, "table_name": f"{bo}s"},
                           allow_unicode=True),
            encoding="utf-8",
        )
        schemas.append(rel)
    return AppManifest(
        app_id=app_id, name=app_id, version="1.0.0",
        app_dir=tmp_path / app_id,
        platform_min_version=min_version,
        platform_max_version=max_version,
        schemas=schemas,
        requires=requires,
        doc_flow_rules=list(rules),
    )


def _codes(findings):
    return [f.code for f in findings]


# ─────────────────────────────────────────────────────────────────────────────
# requires 段解析（app_loader）
# ─────────────────────────────────────────────────────────────────────────────
class TestRequiresParsing:
    def _write(self, tmp_path, app_id, extra):
        app = {"id": app_id, "name": app_id, "version": "1.0.0"}
        app.update(extra)
        app_dir = tmp_path / app_id
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "app.yaml").write_text(
            yaml.safe_dump({"app": app}, allow_unicode=True), encoding="utf-8")
        return app_dir

    def test_absent_requires_is_none(self, tmp_path):
        assert load_manifest(self._write(tmp_path, "no_req", {})).requires is None

    def test_parses_three_fields(self, tmp_path):
        app_dir = self._write(tmp_path, "with_req", {
            "requires": {"bo": ["outbound_order"], "rules": ["r-1"],
                         "column_version": "abc123"},
        })
        req = load_manifest(app_dir).requires
        assert req == RequiresDecl(
            bo=["outbound_order"], rules=["r-1"], column_version="abc123")

    def test_requires_not_object_raises(self, tmp_path):
        app_dir = self._write(tmp_path, "bad_req", {"requires": ["outbound_order"]})
        with pytest.raises(AppManifestError, match="requires 需为对象"):
            load_manifest(app_dir)

    def test_requires_bo_not_list_raises(self, tmp_path):
        app_dir = self._write(tmp_path, "bad_bo", {"requires": {"bo": "one"}})
        with pytest.raises(AppManifestError, match="'bo' 需为字符串列表"):
            load_manifest(app_dir)


# ─────────────────────────────────────────────────────────────────────────────
# 版本比较语义
# ─────────────────────────────────────────────────────────────────────────────
class TestVersionSemantics:
    def test_trailing_zero_equal(self):
        assert _cmp((1, 0), (1, 0, 0)) == 0
        assert _cmp((0, 9, 5), (1, 0)) < 0
        assert _cmp((1, 0, 1), (1, 0)) > 0

    def test_parse_version(self):
        assert _parse_version("0.9.1") == (0, 9, 1)
        assert _parse_version("  1.0 ") == (1, 0)
        assert _parse_version("dev") is None
        assert _parse_version("") is None

    @pytest.mark.parametrize("raw,ok", [
        (">=0.9.0", True), (">0.9.0", True), ("<1.0.0", True),
        ("<=0.9.5", True), ("==0.9.5", True), ("=0.9.5", True),
        ("0.9.5", True),                     # 无操作符 → min 语义
        (">0.9.5", False), ("<0.9.5", False), ("==1.0.0", False),
        ("0.9.6", False),
    ])
    def test_satisfies_against_0_9_5(self, raw, ok):
        assert _satisfies((0, 9, 5), raw) is ok

    def test_satisfies_unparsable_is_none(self):
        assert _satisfies((0, 9, 5), "latest") is None
        assert _satisfies(None, ">=0.9.0") is None


# ─────────────────────────────────────────────────────────────────────────────
# 平台版本区间
# ─────────────────────────────────────────────────────────────────────────────
class TestPlatformConstraint:
    def test_default_platform_version(self, monkeypatch):
        monkeypatch.delenv("PLATFORM_VERSION", raising=False)
        assert get_platform_version() == "0.9.5"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PLATFORM_VERSION", "1.2.3")
        assert get_platform_version() == "1.2.3"

    def test_in_range_ok(self, tmp_path):
        m = _manifest(tmp_path, min_version="0.9.0", max_version="<1.0.0")
        assert validate_dependencies(m, platform_version="0.9.5") == []

    def test_below_min_reported(self, tmp_path):
        m = _manifest(tmp_path, min_version="0.9.0")
        assert "PLATFORM_VERSION_OUT_OF_RANGE" in _codes(
            validate_dependencies(m, platform_version="0.8.9"))

    def test_max_is_exclusive_by_default(self, tmp_path):
        m = _manifest(tmp_path, max_version="<1.0.0")
        assert "PLATFORM_VERSION_OUT_OF_RANGE" in _codes(
            validate_dependencies(m, platform_version="1.0.0"))

    def test_max_inclusive_ok(self, tmp_path):
        m = _manifest(tmp_path, max_version="<=1.0.0")
        assert validate_dependencies(m, platform_version="1.0.0") == []

    def test_invalid_constraint_reported(self, tmp_path):
        m = _manifest(tmp_path, min_version="最新版")
        assert "PLATFORM_CONSTRAINT_INVALID" in _codes(
            validate_dependencies(m, platform_version="0.9.5"))

    def test_no_declaration_zero_findings(self, tmp_path):
        m = _manifest(tmp_path)
        assert validate_dependencies(m, platform_version="99.0.0") == []

    def test_unparsable_platform_version_skips_check(self, tmp_path):
        m = _manifest(tmp_path, min_version="0.9.0", max_version="<1.0.0")
        assert validate_dependencies(m, platform_version="dev-build") == []


# ─────────────────────────────────────────────────────────────────────────────
# requires.bo / requires.rules
# ─────────────────────────────────────────────────────────────────────────────
class TestRequiresBo:
    def test_satisfied_by_available(self, tmp_path):
        m = _manifest(tmp_path, requires=RequiresDecl(bo=["outbound_order"]))
        assert validate_dependencies(m, available_bo_ids={"outbound_order"}) == []

    def test_satisfied_by_own_bo(self, tmp_path):
        m = _manifest(tmp_path, own_bo_ids=("thing",),
                      requires=RequiresDecl(bo=["thing"]))
        assert validate_dependencies(m, available_bo_ids=set()) == []

    def test_missing_reported(self, tmp_path):
        m = _manifest(tmp_path, requires=RequiresDecl(bo=["ghost_bo"]))
        findings = validate_dependencies(m, available_bo_ids={"other"})
        assert _codes(findings) == ["BO_DEPENDENCY_MISSING"]
        assert findings[0].severity == "error"


class TestRequiresRules:
    def test_satisfied(self, tmp_path):
        m = _manifest(tmp_path, requires=RequiresDecl(rules=["r-1"]))
        assert validate_dependencies(m, available_rule_ids={"r-1"}) == []

    def test_missing_reported(self, tmp_path):
        m = _manifest(tmp_path, requires=RequiresDecl(rules=["r-1"]))
        findings = validate_dependencies(m, available_rule_ids=set())
        assert _codes(findings) == ["RULE_DEPENDENCY_MISSING"]


class TestDocFlowRuleBo:
    def _rule(self, source, target):
        return DocFlowRuleDecl(rule_id="rule-1", source_bo=source, target_bo=target)

    def test_own_rule_bo_ok(self, tmp_path):
        m = _manifest(tmp_path, own_bo_ids=("sales", "delivery"),
                      rules=[self._rule("sales", "delivery")])
        assert validate_dependencies(m, available_bo_ids=set()) == []

    def test_missing_target_bo_reported(self, tmp_path):
        m = _manifest(tmp_path, own_bo_ids=("sales",),
                      rules=[self._rule("sales", "delivery")])
        findings = validate_dependencies(m, available_bo_ids=set())
        assert _codes(findings) == ["RULE_BO_MISSING"]
        assert "target_bo" in findings[0].detail


# ─────────────────────────────────────────────────────────────────────────────
# 多应用整体校验
# ─────────────────────────────────────────────────────────────────────────────
class TestAppSet:
    def test_cross_app_reference_ok(self, tmp_path):
        provider = _manifest(tmp_path, "provider", own_bo_ids=("outbound_order",))
        consumer = _manifest(tmp_path, "consumer",
                             requires=RequiresDecl(bo=["outbound_order"]))
        assert validate_app_set([provider, consumer]) == {}

    def test_cross_app_reference_missing(self, tmp_path):
        consumer = _manifest(tmp_path, "consumer",
                             requires=RequiresDecl(bo=["outbound_order"]))
        problems = validate_app_set([consumer])
        assert _codes(problems["consumer"]) == ["BO_DEPENDENCY_MISSING"]

    def test_platform_bo_ids_counted(self, tmp_path):
        m = _manifest(tmp_path, requires=RequiresDecl(bo=["product"]))
        assert validate_app_set([m], platform_bo_ids={"product"}) == {}

    def test_collect_declared_ids(self, tmp_path):
        provider = _manifest(tmp_path, "provider", own_bo_ids=("thing",),
                             rules=[DocFlowRuleDecl("r-1", "thing", "thing")])
        bos, rules = collect_declared_ids([provider])
        assert bos == {"thing"}
        assert rules == {"r-1"}

    def test_assert_app_set_raises(self, tmp_path):
        m = _manifest(tmp_path, requires=RequiresDecl(bo=["ghost"]))
        with pytest.raises(DependencyError, match="ghost"):
            assert_app_set([m])

    def test_assert_app_set_returns_count(self, tmp_path):
        m = _manifest(tmp_path, own_bo_ids=("thing",))
        assert assert_app_set([m]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 安装期闸门（install_app）
# ─────────────────────────────────────────────────────────────────────────────
def _make_package(tmp_path, app_id="demo_app", *, bo_ids=("thing",),
                  requires=None, platform=None):
    """造一个真实 .bip 包（含 app.yaml + schema）。"""
    app_dir = tmp_path / "src" / app_id
    (app_dir / "schemas").mkdir(parents=True, exist_ok=True)
    raw = {
        "id": app_id, "name": f"{app_id} 应用", "version": "1.0.0",
        "vendor": "internal", "description": "测试应用",
        "schemas": [f"schemas/{bo}.yaml" for bo in bo_ids],
        "blueprints": [],
        "permission_namespace": app_id,
        "database": {"file": f"data/{app_id}.db"},
        "menu": {"portal_mount": {"code": f"app_{app_id}", "order": 500}},
        "product_binding": {"mode": "fixed", "product_code": app_id.upper()},
    }
    if requires:
        raw["requires"] = requires
    if platform:
        raw["platform"] = platform
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump({"app": raw}, allow_unicode=True), encoding="utf-8")
    for bo in bo_ids:
        (app_dir / "schemas" / f"{bo}.yaml").write_text(
            yaml.safe_dump({"id": bo, "name": bo, "table_name": f"{bo}s"},
                           allow_unicode=True),
            encoding="utf-8")
    return build_package(app_dir, tmp_path / "dist")


@pytest.fixture
def platform_ds(tmp_path):
    ds = get_data_source("sqlite", database=str(tmp_path / "platform.db"))
    ensure_installed_apps_table(ds)
    yield ds
    ds.disconnect()


class TestInstallGate:
    def test_install_without_requires_ok(self, tmp_path, platform_ds):
        """未声明 requires = 旧行为，零影响。"""
        bip = _make_package(tmp_path, "plain_app")
        record = install_app(bip, apps_root=tmp_path / "apps", data_source=platform_ds)
        assert record["app_id"] == "plain_app"

    def test_install_rejected_missing_required_bo(self, tmp_path, platform_ds):
        bip = _make_package(tmp_path, "need_app",
                            requires={"bo": ["ghost_bo"]})
        with pytest.raises(AppInstallError, match="依赖校验失败"):
            install_app(bip, apps_root=tmp_path / "apps", data_source=platform_ds)

    def test_install_ok_when_dependency_installed(self, tmp_path, platform_ds):
        apps_root = tmp_path / "apps"
        install_app(_make_package(tmp_path, "provider_app", bo_ids=("shared_thing",)),
                    apps_root=apps_root, data_source=platform_ds)
        bip = _make_package(tmp_path, "consumer_app",
                            requires={"bo": ["shared_thing"]})
        record = install_app(bip, apps_root=apps_root, data_source=platform_ds)
        assert record["app_id"] == "consumer_app"

    def test_install_rejected_platform_out_of_range(self, tmp_path, platform_ds):
        bip = _make_package(tmp_path, "future_app",
                            platform={"min_version": "9.9.9"})
        with pytest.raises(AppInstallError, match="PLATFORM_VERSION_OUT_OF_RANGE"):
            install_app(bip, apps_root=tmp_path / "apps", data_source=platform_ds)

    def test_install_rejected_missing_rule(self, tmp_path, platform_ds):
        bip = _make_package(tmp_path, "rule_app",
                            requires={"rules": ["ghost-rule"]})
        with pytest.raises(AppInstallError, match="RULE_DEPENDENCY_MISSING"):
            install_app(bip, apps_root=tmp_path / "apps", data_source=platform_ds)


# ─────────────────────────────────────────────────────────────────────────────
# 启用期闸门（register_apps）
# ─────────────────────────────────────────────────────────────────────────────
def _write_app_dir(tmp_path, app_id, *, bo_ids=(), **extra):
    """写一个最小应用目录；bo_ids 会生成对应 schema 文件（依赖声明需可解析）。"""
    app = {"id": app_id, "name": app_id, "version": "1.0.0",
           "schemas": [f"schemas/{bo}.yaml" for bo in bo_ids],
           "blueprints": []}
    app.update(extra)
    app_dir = tmp_path / app_id
    (app_dir / "schemas").mkdir(parents=True, exist_ok=True)
    for bo in bo_ids:
        (app_dir / "schemas" / f"{bo}.yaml").write_text(
            yaml.safe_dump({"id": bo, "name": bo, "table_name": f"{bo}s"},
                           allow_unicode=True),
            encoding="utf-8")
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump({"app": app}, allow_unicode=True), encoding="utf-8")
    return app_dir


@pytest.fixture
def bare_app():
    app = Flask(f"dep_probe_{id(object())}")
    app.config["TESTING"] = True
    return app


class TestRegistryGate:
    def test_register_ok_without_requires(self, tmp_path, bare_app):
        _write_app_dir(tmp_path, "clean_app")
        manifests = register_apps(bare_app, app_ids=["clean_app"],
                                  apps_root=tmp_path, register_schemas=False)
        assert [m.app_id for m in manifests] == ["clean_app"]

    def test_register_rejected_platform_out_of_range(self, tmp_path, bare_app):
        _write_app_dir(tmp_path, "future_app", platform={"min_version": "9.9.9"})
        with pytest.raises(AppRegistrationError, match="PLATFORM_VERSION_OUT_OF_RANGE"):
            register_apps(bare_app, app_ids=["future_app"],
                          apps_root=tmp_path, register_schemas=False)

    def test_register_rejected_missing_required_bo(self, tmp_path, bare_app):
        _write_app_dir(tmp_path, "need_app", requires={"bo": ["ghost_bo"]})
        with pytest.raises(AppRegistrationError, match="BO_DEPENDENCY_MISSING"):
            register_apps(bare_app, app_ids=["need_app"],
                          apps_root=tmp_path, register_schemas=False)

    def test_register_env_platform_version_injected(self, tmp_path, bare_app,
                                                    monkeypatch):
        _write_app_dir(tmp_path, "old_app",
                       platform={"min_version": "0.9.0", "max_version": "<1.0.0"})
        monkeypatch.setenv("PLATFORM_VERSION", "1.0.0")
        with pytest.raises(AppRegistrationError, match="PLATFORM_VERSION_OUT_OF_RANGE"):
            register_apps(bare_app, app_ids=["old_app"],
                          apps_root=tmp_path, register_schemas=False)

    def test_register_ok_when_dependency_enabled(self, tmp_path, bare_app):
        """跨应用引用在启用集合内成立（provider 声明的 BO 供 consumer 依赖）。"""
        _write_app_dir(tmp_path, "provider_app", bo_ids=("shared_thing",))
        _write_app_dir(tmp_path, "consumer_app", requires={"bo": ["shared_thing"]})
        manifests = register_apps(
            bare_app, app_ids=["provider_app", "consumer_app"],
            apps_root=tmp_path, register_schemas=False)
        assert [m.app_id for m in manifests] == ["provider_app", "consumer_app"]
