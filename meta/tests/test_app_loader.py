# -*- coding: utf-8 -*-
"""[多产品平台] 应用包加载器测试（PoC 1）

覆盖:
- 真实应用包 apps/hello_world 的解析
- app_id 规范 / 目录名一致性
- 必填字段、文件存在性、权限命名空间、产品绑定模式 的校验
- discover_apps / load_apps 的发现与查找

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.2
"""
import pytest
import yaml

from meta.core.app_loader import (
    AppManifestError,
    discover_apps,
    get_apps_root,
    load_apps,
    load_manifest,
)


def _write_app(tmp_path, app_id, *, files=(), **overrides):
    """在 tmp_path 下造一个最小应用包, 返回其目录。"""
    app = {"id": app_id, "name": "示例应用", "version": "1.0.0"}
    app.update(overrides)
    app_dir = tmp_path / app_id
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump({"app": app}, allow_unicode=True), encoding="utf-8"
    )
    for rel in files:
        p = app_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("placeholder", encoding="utf-8")
    return app_dir


class TestRealAppPackage:
    """验证真实的 apps/hello_world 应用包"""

    def test_load_hello_world_manifest(self):
        manifest = load_manifest(get_apps_root() / "hello_world")

        assert manifest.app_id == "hello_world"
        assert manifest.name == "示例应用"
        assert manifest.version == "1.0.0"

        # 派生属性（roadmap §6.7 路由命名空间）
        assert manifest.route_prefix == "/api/v1/apps/hello_world"
        assert manifest.frontend_prefix == "/app/hello_world"

        # 权限命名空间与产品绑定（roadmap §6.2）
        assert manifest.permission_namespace == "hello_world"
        assert manifest.product_binding.mode == "fixed"
        assert manifest.product_binding.product_code == "HELLO"

        # 声明的资源真实存在
        assert len(manifest.schemas) == 1
        assert manifest.schema_paths()[0].is_file()
        assert manifest.blueprint_paths()[0].is_file()

        assert manifest.database_file == "data/hello_world.db"

    def test_discover_apps_finds_hello_world(self):
        assert "hello_world" in discover_apps()

    def test_load_apps_by_id(self):
        manifests = load_apps(["hello_world"])
        assert len(manifests) == 1
        assert manifests[0].app_id == "hello_world"

    def test_load_apps_missing_id_raises(self):
        with pytest.raises(AppManifestError, match="未找到应用"):
            load_apps(["no_such_app"])

    def test_discover_skips_underscore_dirs(self, tmp_path):
        _write_app(tmp_path, "real_app")
        _write_app(tmp_path, "_template_app")  # 下划线开头应被跳过
        found = discover_apps(tmp_path)
        assert list(found) == ["real_app"]


class TestManifestValidation:
    """app.yaml 校验规则"""

    def test_manifest_file_absent(self, tmp_path):
        empty = tmp_path / "no_manifest"
        empty.mkdir()
        with pytest.raises(AppManifestError, match="未找到描述符"):
            load_manifest(empty)

    def test_missing_required_field(self, tmp_path):
        app_dir = tmp_path / "app_missing"
        app_dir.mkdir()
        (app_dir / "app.yaml").write_text(
            yaml.safe_dump({"app": {"id": "app_missing"}}, allow_unicode=True),
            encoding="utf-8",
        )
        with pytest.raises(AppManifestError, match="name"):
            load_manifest(app_dir)

    def test_invalid_app_id_rejected(self, tmp_path):
        # 含连字符 → 不符合 app_id 规范（ID 会被用作路由/DB/权限前缀）
        app_dir = _write_app(tmp_path, "app-x")
        with pytest.raises(AppManifestError, match="不符合规范"):
            load_manifest(app_dir)

    def test_app_id_must_match_dirname(self, tmp_path):
        app_dir = _write_app(tmp_path, "app_dir_name")
        (app_dir / "app.yaml").write_text(
            yaml.safe_dump(
                {"app": {"id": "app_other", "name": "x", "version": "1.0.0"}},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        with pytest.raises(AppManifestError, match="目录名"):
            load_manifest(app_dir)

    def test_declared_file_missing(self, tmp_path):
        app_dir = _write_app(tmp_path, "app_s", schemas=["schemas/nope.yaml"])
        with pytest.raises(AppManifestError, match="不存在"):
            load_manifest(app_dir)

    def test_permission_namespace_must_equal_app_id(self, tmp_path):
        app_dir = _write_app(tmp_path, "app_ns", permission_namespace="other_ns")
        with pytest.raises(AppManifestError, match="permission_namespace"):
            load_manifest(app_dir)


class TestProductBinding:
    """产品绑定模式（roadmap §6.2 的 3 条不变量）"""

    def test_fixed_requires_product_code(self, tmp_path):
        app_dir = _write_app(tmp_path, "app_pb", product_binding={"mode": "fixed"})
        with pytest.raises(AppManifestError, match="product_code"):
            load_manifest(app_dir)

    def test_multi_needs_no_product_code(self, tmp_path):
        app_dir = _write_app(tmp_path, "app_multi", product_binding={"mode": "multi"})
        manifest = load_manifest(app_dir)
        assert manifest.product_binding.mode == "multi"
        assert manifest.product_binding.product_code == ""

    def test_invalid_mode_rejected(self, tmp_path):
        app_dir = _write_app(tmp_path, "app_bad", product_binding={"mode": "weird"})
        with pytest.raises(AppManifestError, match="mode"):
            load_manifest(app_dir)

    def test_absent_binding_is_none(self, tmp_path):
        app_dir = _write_app(tmp_path, "app_none")
        assert load_manifest(app_dir).product_binding is None
