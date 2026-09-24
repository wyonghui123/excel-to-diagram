# -*- coding: utf-8 -*-
"""[多产品平台] 应用包（.bip）打包/解包测试（PoC 1 步骤 2）

覆盖:
- 真实 apps/hello_world 打包成功且内容完整
- manifest.json 字段与 app.yaml 一致
- 校验: 非法 app.yaml / 缺 app.yaml / 包被篡改 / 路径越界
- 排除项: __pycache__ / *.pyc / data/
"""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from meta.core.app_loader import get_apps_root
from meta.core.app_package import (
    BIP_FORMAT_VERSION,
    PACKAGE_MANIFEST_NAME,
    AppPackageError,
    build_package,
    extract_package,
    read_package_manifest,
)

REAL_APP_DIR = get_apps_root() / "hello_world"


def _write_app(app_dir: Path, app_id: str, **overrides) -> Path:
    """写一个最小可打包的应用目录。"""
    app_dir.mkdir(parents=True, exist_ok=True)
    raw = {
        "id": app_id,
        "name": f"{app_id} 应用",
        "version": "1.2.3",
        "vendor": "internal",
        "schemas": ["schemas/thing.yaml"],
        "blueprints": [],
        "permission_namespace": app_id,
        "database": {"file": f"data/{app_id}.db"},
        "menu": {"portal_mount": {"code": f"app_{app_id}"}},
    }
    raw.update(overrides)
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump({"app": raw}, allow_unicode=True), encoding="utf-8"
    )
    schema_dir = app_dir / "schemas"
    schema_dir.mkdir(exist_ok=True)
    (schema_dir / "thing.yaml").write_text(
        yaml.safe_dump({"id": "thing", "name": "物件", "table_name": "things"},
                       allow_unicode=True),
        encoding="utf-8",
    )
    return app_dir


class TestBuildRealPackage:
    """真实 apps/hello_world 的打包结果。"""

    def test_build_produces_bip(self, tmp_path):
        bip = build_package(REAL_APP_DIR, tmp_path)
        assert bip.is_file()
        assert bip.name == "hello_world-1.0.0.bip"
        assert zipfile.is_zipfile(bip)

    def test_package_manifest_matches_app_yaml(self, tmp_path):
        bip = build_package(REAL_APP_DIR, tmp_path)
        manifest = read_package_manifest(bip)
        assert manifest["format_version"] == BIP_FORMAT_VERSION
        assert manifest["app_id"] == "hello_world"
        assert manifest["version"] == "1.0.0"
        assert manifest["permission_namespace"] == "hello_world"
        assert manifest["product_binding"] == {"mode": "fixed", "product_code": "HELLO"}
        assert manifest["bo_ids"] == ["greeting"]

    def test_package_contains_declared_files(self, tmp_path):
        bip = build_package(REAL_APP_DIR, tmp_path)
        manifest = read_package_manifest(bip)
        paths = {e["path"] for e in manifest["files"]}
        assert paths == {"app.yaml", "schemas/greeting.yaml", "blueprints/greeting_api.py"}
        with zipfile.ZipFile(bip) as zf:
            assert PACKAGE_MANIFEST_NAME in zf.namelist()
            assert paths <= set(zf.namelist())

    def test_default_out_dir_is_repo_dist(self, tmp_path):
        """不传 out_dir 时落在 <repo>/dist。"""
        app_dir = _write_app(tmp_path / "demo", "demo")
        bip = build_package(app_dir)
        try:
            assert bip.parent == get_apps_root().parent / "dist"
        finally:
            bip.unlink(missing_ok=True)


class TestBuildValidation:
    """打包前的校验（复用 app_loader）。"""

    def test_missing_app_yaml(self, tmp_path):
        app_dir = tmp_path / "nope"
        app_dir.mkdir()
        with pytest.raises(AppPackageError):
            build_package(app_dir, tmp_path / "out")

    def test_app_id_mismatch_dir_name(self, tmp_path):
        app_dir = _write_app(tmp_path / "wrong_dir", "other_id")
        with pytest.raises(AppPackageError):
            build_package(app_dir, tmp_path / "out")

    def test_nonexistent_dir(self, tmp_path):
        with pytest.raises(AppPackageError):
            build_package(tmp_path / "ghost", tmp_path / "out")


class TestBuildExcludes:
    """运行时产物不应进包。"""

    def test_excludes_pycache_data_and_pyc(self, tmp_path):
        app_dir = _write_app(tmp_path / "demo", "demo")
        (app_dir / "__pycache__").mkdir()
        (app_dir / "__pycache__" / "x.cpython-314.pyc").write_bytes(b"junk")
        (app_dir / "data").mkdir()
        (app_dir / "data" / "demo.db").write_bytes(b"junk")
        (app_dir / "blueprints").mkdir()
        (app_dir / "blueprints" / "stale.pyc").write_bytes(b"junk")

        bip = build_package(app_dir, tmp_path / "out")
        paths = {e["path"] for e in read_package_manifest(bip)["files"]}
        assert paths == {"app.yaml", "schemas/thing.yaml"}


class TestExtract:
    """解包与完整性校验。"""

    def test_extract_roundtrip(self, tmp_path):
        app_dir = _write_app(tmp_path / "demo", "demo")
        bip = build_package(app_dir, tmp_path / "out")
        dest = tmp_path / "installed"
        manifest = extract_package(bip, dest)

        assert manifest["app_id"] == "demo"
        assert (dest / "app.yaml").is_file()
        assert (dest / "schemas" / "thing.yaml").is_file()
        assert (dest / "app.yaml").read_bytes() == (app_dir / "app.yaml").read_bytes()

    def test_tampered_package_rejected(self, tmp_path):
        """改包内文件但不改 manifest.json → 必须拒绝。"""
        app_dir = _write_app(tmp_path / "demo", "demo")
        bip = build_package(app_dir, tmp_path / "out")

        tampered = tmp_path / "tampered.bip"
        with zipfile.ZipFile(bip) as src, zipfile.ZipFile(tampered, "w") as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "schemas/thing.yaml":
                    data = data.replace(b"things", b"evil_table")
                dst.writestr(item, data)

        with pytest.raises(AppPackageError, match="文件校验失败"):
            extract_package(tampered, tmp_path / "dest")

    def test_missing_file_in_package_rejected(self, tmp_path):
        app_dir = _write_app(tmp_path / "demo", "demo")
        bip = build_package(app_dir, tmp_path / "out")

        stripped = tmp_path / "stripped.bip"
        with zipfile.ZipFile(bip) as src, zipfile.ZipFile(stripped, "w") as dst:
            for item in src.infolist():
                if item.filename == "schemas/thing.yaml":
                    continue
                dst.writestr(item, src.read(item.filename))

        with pytest.raises(AppPackageError, match="包内缺少文件"):
            extract_package(stripped, tmp_path / "dest")

    def test_unsupported_format_version_rejected(self, tmp_path):
        bip = tmp_path / "bad.bip"
        with zipfile.ZipFile(bip, "w") as zf:
            zf.writestr(PACKAGE_MANIFEST_NAME,
                        json.dumps({"format_version": 999, "files": []}))
        with pytest.raises(AppPackageError, match="不支持的包格式版本"):
            read_package_manifest(bip)

    def test_missing_manifest_rejected(self, tmp_path):
        bip = tmp_path / "bad.bip"
        with zipfile.ZipFile(bip, "w") as zf:
            zf.writestr("app.yaml", "app: {}")
        with pytest.raises(AppPackageError, match="缺少"):
            read_package_manifest(bip)

    def test_path_traversal_rejected(self, tmp_path):
        """manifest.json 声明 ../../escape 时必须拒绝。"""
        bip = tmp_path / "evil.bip"
        payload = b"pwned"
        with zipfile.ZipFile(bip, "w") as zf:
            zf.writestr(PACKAGE_MANIFEST_NAME, json.dumps({
                "format_version": BIP_FORMAT_VERSION,
                "app_id": "evil",
                "files": [{
                    "path": "../escape.txt",
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }],
            }))
            zf.writestr("../escape.txt", payload)

        with pytest.raises(AppPackageError, match="越界"):
            extract_package(bip, tmp_path / "dest")
        assert not (tmp_path / "escape.txt").exists()
