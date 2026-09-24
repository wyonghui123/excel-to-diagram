# -*- coding: utf-8 -*-
"""[多产品平台] 应用安装/卸载测试（PoC 1 步骤 3 / 6）

覆盖:
- 安装: 写 installed_apps 登记 / 解包到 apps/<app_id> / bo_ids 与 menu_root_code 落库
- 覆盖安装: 无 --force 拒绝; 有 --force 备份旧目录到 apps/_backup/
- 卸载: 清应用根菜单 + 应用内菜单 + 删登记; --purge-files 删目录
- 迁移 v090: 幂等 / verify / downgrade

DB 用真实 SQLite 文件（临时目录），不用 :memory:（池模式不支持）。
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

from meta.core.app_installer import (
    AppInstallError,
    ensure_installed_apps_table,
    get_installed,
    install_app,
    list_installed,
    uninstall_app,
)
from meta.core.app_package import build_package
from meta.core.datasource import get_data_source

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MENUS_DDL = """
CREATE TABLE IF NOT EXISTS menus (
    menu_code VARCHAR(64) PRIMARY KEY,
    menu_name VARCHAR(128) NOT NULL DEFAULT '',
    menu_path VARCHAR(255) NOT NULL DEFAULT '',
    page_type VARCHAR(32) NOT NULL DEFAULT '',
    object_types TEXT NOT NULL DEFAULT '[]',
    primary_object_type VARCHAR(64) NOT NULL DEFAULT '',
    bo_bindings TEXT NOT NULL DEFAULT '[]',
    required_permissions TEXT NOT NULL DEFAULT '[]',
    required_any_permission INTEGER NOT NULL DEFAULT 0,
    data_permission_hint TEXT NOT NULL DEFAULT '{}',
    page_config TEXT NOT NULL DEFAULT '{}',
    parent_menu VARCHAR(64) NOT NULL DEFAULT '',
    icon VARCHAR(64) NOT NULL DEFAULT '',
    color VARCHAR(32) NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    show_in_sidebar INTEGER NOT NULL DEFAULT 0,
    auto_generated INTEGER NOT NULL DEFAULT 0
)
"""


@pytest.fixture
def platform_db(tmp_path):
    """建一个含 menus 表的平台库, 返回 (db_path, data_source)。"""
    db_path = tmp_path / "platform.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(MENUS_DDL)
        conn.commit()
    finally:
        conn.close()

    ds = get_data_source("sqlite", database=str(db_path))
    yield db_path, ds
    ds.disconnect()


def _make_app_package(tmp_path, app_id="demo_app", version="1.0.0", bo_ids=("thing",)):
    """造一个真实 .bip 包（含 app.yaml + schema）。"""
    app_dir = tmp_path / "src" / app_id
    (app_dir / "schemas").mkdir(parents=True, exist_ok=True)
    raw = {
        "id": app_id,
        "name": f"{app_id} 应用",
        "version": version,
        "vendor": "internal",
        "description": "测试应用",
        "schemas": [f"schemas/{bo}.yaml" for bo in bo_ids],
        "blueprints": [],
        "permission_namespace": app_id,
        "database": {"file": f"data/{app_id}.db"},
        "menu": {"portal_mount": {"code": f"app_{app_id}", "order": 500}},
        "product_binding": {"mode": "fixed", "product_code": app_id.upper()},
    }
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump({"app": raw}, allow_unicode=True), encoding="utf-8"
    )
    for bo in bo_ids:
        (app_dir / "schemas" / f"{bo}.yaml").write_text(
            yaml.safe_dump({"id": bo, "name": bo, "table_name": f"{bo}s"},
                           allow_unicode=True),
            encoding="utf-8",
        )
    return build_package(app_dir, tmp_path / "dist")


def _seed_app_menus(ds, apps_root, app_id, bo_ids):
    """走**生产路径**生成双层菜单（等同启动期 register_apps 的效果）。

    刻意不用 raw SQL —— 本项目 conftest 会 skip 含 INSERT/UPDATE/DELETE 的测试文件
    （meta/tests/conftest.py `_check_raw_sql_in_tests`）。
    """
    from meta.core.app_loader import load_manifest
    from meta.core.app_registry import _attach_app_menus_to_root, _ensure_app_root_menu
    from meta.services.menu_auto_generator import menu_auto_generator

    manifest = load_manifest(apps_root / app_id)
    root_code = _ensure_app_root_menu(ds, manifest)
    menus = [
        {
            "menu_code": f"{bo}-list",
            "menu_name": f"{bo}管理",
            "menu_path": f"/{bo}",
            "page_type": "object_list",
            "primary_object_type": bo,
            "object_types": [bo],
        }
        for bo in bo_ids
    ]
    menu_auto_generator.persist_to_db(ds, menus=menus, force=True)
    _attach_app_menus_to_root(ds, list(bo_ids), root_code)
    return root_code


def _menu_codes(ds):
    return {r[0] for r in ds.execute("SELECT menu_code FROM menus").fetchall()}


class TestInstall:
    def test_install_writes_registry(self, tmp_path, platform_db):
        _, ds = platform_db
        bip = _make_app_package(tmp_path)

        record = install_app(bip, apps_root=tmp_path / "apps", data_source=ds)

        assert record["app_id"] == "demo_app"
        assert record["version"] == "1.0.0"
        assert record["bo_ids"] == ["thing"]
        assert record["menu_root_code"] == "app_demo_app"
        assert record["product_binding_mode"] == "fixed"
        assert record["product_code"] == "DEMO_APP"
        assert record["package_sha256"]

        stored = get_installed(ds, "demo_app")
        assert stored is not None
        assert stored["version"] == "1.0.0"
        assert stored["bo_ids"] == ["thing"]

    def test_install_extracts_app_dir(self, tmp_path, platform_db):
        _, ds = platform_db
        bip = _make_app_package(tmp_path)
        apps_root = tmp_path / "apps"

        install_app(bip, apps_root=apps_root, data_source=ds)

        assert (apps_root / "demo_app" / "app.yaml").is_file()
        assert (apps_root / "demo_app" / "schemas" / "thing.yaml").is_file()

    def test_install_twice_without_force_rejected(self, tmp_path, platform_db):
        _, ds = platform_db
        bip = _make_app_package(tmp_path)
        apps_root = tmp_path / "apps"
        install_app(bip, apps_root=apps_root, data_source=ds)

        with pytest.raises(AppInstallError, match="已存在"):
            install_app(bip, apps_root=apps_root, data_source=ds)

    def test_force_install_backs_up_and_upgrades(self, tmp_path, platform_db):
        _, ds = platform_db
        apps_root = tmp_path / "apps"
        install_app(_make_app_package(tmp_path, version="1.0.0"),
                    apps_root=apps_root, data_source=ds)

        bip_v2 = _make_app_package(tmp_path, version="1.1.0")
        record = install_app(bip_v2, apps_root=apps_root, data_source=ds, force=True)

        assert record["version"] == "1.1.0"
        assert record["backup_path"]
        assert Path(record["backup_path"]).is_dir()
        assert get_installed(ds, "demo_app")["version"] == "1.1.0"
        # 备份目录以 _ 开头 → discover_apps 会跳过, 不会被当成应用
        assert Path(record["backup_path"]).parent.name == "_backup"

    def test_list_installed_sorted(self, tmp_path, platform_db):
        _, ds = platform_db
        apps_root = tmp_path / "apps"
        install_app(_make_app_package(tmp_path, app_id="zzz_app"),
                    apps_root=apps_root, data_source=ds)
        install_app(_make_app_package(tmp_path, app_id="aaa_app"),
                    apps_root=apps_root, data_source=ds)

        assert [r["app_id"] for r in list_installed(ds)] == ["aaa_app", "zzz_app"]

    def test_install_without_data_source_rejected(self, tmp_path):
        bip = _make_app_package(tmp_path)
        with pytest.raises(AppInstallError, match="data_source"):
            install_app(bip, apps_root=tmp_path / "apps")


class TestUninstall:
    def test_uninstall_removes_menus_and_registry(self, tmp_path, platform_db):
        _, ds = platform_db
        apps_root = tmp_path / "apps"
        install_app(_make_app_package(tmp_path, bo_ids=("thing", "other")),
                    apps_root=apps_root, data_source=ds)
        _seed_app_menus(ds, apps_root, "demo_app", ["thing", "other"])
        assert _menu_codes(ds) == {"app_demo_app", "thing-list", "other-list"}

        result = uninstall_app("demo_app", apps_root=apps_root, data_source=ds)

        assert result["menus_deleted"] == 3
        assert _menu_codes(ds) == set()
        assert get_installed(ds, "demo_app") is None
        # 默认保留应用目录与业务表
        assert (apps_root / "demo_app").is_dir()
        assert result["purged_dir"] == ""

    def test_uninstall_keeps_unrelated_menus(self, tmp_path, platform_db):
        _, ds = platform_db
        apps_root = tmp_path / "apps"
        install_app(_make_app_package(tmp_path), apps_root=apps_root, data_source=ds)
        _seed_app_menus(ds, apps_root, "demo_app", ["thing"])

        # 平台自己的菜单（与本应用无关）必须保留
        from meta.services.menu_auto_generator import menu_auto_generator

        menu_auto_generator.persist_to_db(ds, menus=[{
            "menu_code": "user-list", "menu_name": "用户管理",
            "primary_object_type": "user", "object_types": ["user"],
        }], force=True)

        uninstall_app("demo_app", apps_root=apps_root, data_source=ds)

        assert _menu_codes(ds) == {"user-list"}

    def test_uninstall_purge_files(self, tmp_path, platform_db):
        _, ds = platform_db
        apps_root = tmp_path / "apps"
        install_app(_make_app_package(tmp_path), apps_root=apps_root, data_source=ds)

        result = uninstall_app("demo_app", apps_root=apps_root, data_source=ds,
                              purge_files=True)

        assert result["purged_dir"]
        assert not (apps_root / "demo_app").exists()

    def test_uninstall_unknown_app_rejected(self, tmp_path, platform_db):
        _, ds = platform_db
        with pytest.raises(AppInstallError, match="未安装"):
            uninstall_app("ghost", apps_root=tmp_path / "apps", data_source=ds)

    def test_uninstall_works_after_dir_deleted(self, tmp_path, platform_db):
        """菜单清理依赖 installed_apps.bo_ids, 不依赖应用目录存在。"""
        _, ds = platform_db
        apps_root = tmp_path / "apps"
        install_app(_make_app_package(tmp_path), apps_root=apps_root, data_source=ds)
        _seed_app_menus(ds, apps_root, "demo_app", ["thing"])
        shutil.rmtree(apps_root / "demo_app")

        result = uninstall_app("demo_app", apps_root=apps_root, data_source=ds)

        assert result["menus_deleted"] == 2
        assert _menu_codes(ds) == set()


class TestEnsureTable:
    def test_ensure_table_idempotent(self, platform_db):
        _, ds = platform_db
        ensure_installed_apps_table(ds)
        ensure_installed_apps_table(ds)
        assert list_installed(ds) == []

    def test_bo_ids_roundtrip_as_json(self, tmp_path, platform_db):
        db_path, ds = platform_db
        install_app(_make_app_package(tmp_path, bo_ids=("a", "b")),
                    apps_root=tmp_path / "apps", data_source=ds)

        conn = sqlite3.connect(str(db_path))
        try:
            raw = conn.execute(
                "SELECT bo_ids FROM installed_apps WHERE app_id='demo_app'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert json.loads(raw) == ["a", "b"]


class TestMigrationV090:
    """迁移脚本自身的幂等 / verify / downgrade。"""

    @staticmethod
    def _load():
        import importlib.util

        path = REPO_ROOT / "meta" / "migrations" / "v090__create_installed_apps.py"
        spec = importlib.util.spec_from_file_location("v090_installed_apps", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_migrate_then_verify(self, platform_db):
        db_path, _ = platform_db
        module = self._load()

        assert module.migrate(db_path) is True
        assert module.verify(db_path) is True

    def test_migrate_idempotent(self, platform_db):
        db_path, _ = platform_db
        module = self._load()
        module.migrate(db_path)
        assert module.migrate(db_path) is True
        assert module.verify(db_path) is True

    def test_migrate_missing_db_returns_false(self, tmp_path):
        module = self._load()
        assert module.migrate(tmp_path / "nope.db") is False

    def test_downgrade_drops_table(self, platform_db):
        db_path, _ = platform_db
        module = self._load()
        module.migrate(db_path)

        assert module.downgrade(db_path) is True
        conn = sqlite3.connect(str(db_path))
        try:
            found = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='installed_apps'"
            ).fetchone()
        finally:
            conn.close()
        assert found is None
