# -*- coding: utf-8 -*-
"""[多产品平台] DB 路径单一入口测试（§6.5.1 F2）

覆盖:
- 平台库路径: env `SQLITE_DB_PATH` 优先 / 仓库内兜底
- 应用库目录: env `SQLITE_DB_DIR` 优先 / 仓库内 `data/` 兜底
- 应用库路径: 文件名取自 `app.yaml` 的 `database.file`，目录由部署环境决定
- app_id 安全校验（阻断路径穿越，因该参数可能来自 URL 路由）

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.5.1 F2
"""
import os

import pytest

from meta.core.app_loader import get_apps_root, load_manifest
from meta.core.db_path import get_app_data_dir, get_app_db_path, get_meta_db_path


class TestMetaDbPath:

    def test_env_takes_priority(self, monkeypatch, tmp_path):
        custom = str(tmp_path / 'staging.db')
        monkeypatch.setenv('SQLITE_DB_PATH', custom)
        assert get_meta_db_path() == custom

    def test_fallback_to_repo_meta(self, monkeypatch):
        monkeypatch.delenv('SQLITE_DB_PATH', raising=False)
        path = get_meta_db_path()
        assert os.path.isabs(path)
        assert path.endswith(os.path.join('meta', 'architecture.db'))


class TestAppDataDir:

    def test_env_takes_priority(self, monkeypatch, tmp_path):
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        assert get_app_data_dir() == str(tmp_path)

    def test_fallback_to_repo_data(self, monkeypatch):
        monkeypatch.delenv('SQLITE_DB_DIR', raising=False)
        path = get_app_data_dir()
        assert os.path.isabs(path)
        assert path.endswith(os.sep + 'data')

    def test_does_not_create_directory(self, monkeypatch, tmp_path):
        """路径解析不产生副作用 —— 建目录由数据源/迁移流程负责。"""
        target = tmp_path / 'not_created'
        monkeypatch.setenv('SQLITE_DB_DIR', str(target))
        get_app_data_dir()
        get_app_db_path('demo_app')
        assert not target.exists()


class TestAppDbPath:

    def test_filename_from_database_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        assert get_app_db_path('hello_world', 'data/hello_world.db') == \
            str(tmp_path / 'hello_world.db')

    def test_directory_part_of_database_file_is_ignored(self, monkeypatch, tmp_path):
        """`database.file` 只提供文件名；目录一律由部署环境决定。"""
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        assert get_app_db_path('hello_world', 'some/other/dir/x.db') == \
            str(tmp_path / 'x.db')

    def test_absolute_database_file_only_contributes_filename(self, monkeypatch, tmp_path):
        """应用包不应固化绝对路径，故绝对路径同样只取文件名。"""
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        assert get_app_db_path('hello_world', '/opt/data/hello.db') == \
            str(tmp_path / 'hello.db')

    def test_default_filename_when_not_declared(self, monkeypatch, tmp_path):
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        assert get_app_db_path('demo_app') == str(tmp_path / 'demo_app.db')

    def test_blank_database_file_falls_back_to_app_id(self, monkeypatch, tmp_path):
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        assert get_app_db_path('demo_app', '') == str(tmp_path / 'demo_app.db')

    def test_distinct_apps_get_distinct_paths(self, monkeypatch, tmp_path):
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        warehouse = get_app_db_path('warehouse', 'data/warehouse.db')
        tms = get_app_db_path('tms', 'data/tms.db')
        assert warehouse != tms

    def test_env_relocates_whole_app_data_dir(self, monkeypatch, tmp_path):
        """同一应用包在本地与 staging 落在不同目录，但文件名一致。"""
        monkeypatch.delenv('SQLITE_DB_DIR', raising=False)
        local = get_app_db_path('hello_world', 'data/hello_world.db')
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        staging = get_app_db_path('hello_world', 'data/hello_world.db')
        assert os.path.basename(local) == os.path.basename(staging) == 'hello_world.db'
        assert local != staging


class TestAppIdSafety:

    @pytest.mark.parametrize('bad', [
        '',            # 空值
        '.',           # 当前目录
        '..',          # 上级目录
        '../evil',     # 穿越
        'a/b',         # 含分隔符
        'a\\b',        # 含 Windows 分隔符
        '/abs',        # 绝对路径
    ])
    def test_rejects_unsafe_app_id(self, bad):
        with pytest.raises(ValueError):
            get_app_db_path(bad, 'data/x.db')

    @pytest.mark.parametrize('good', ['hello_world', 'tms', 'a1', 'warehouse_app'])
    def test_accepts_valid_app_id(self, monkeypatch, tmp_path, good):
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        assert get_app_db_path(good) == str(tmp_path / f'{good}.db')


class TestRealAppPackageIntegration:

    def test_hello_world_package_resolves_to_declared_filename(self, monkeypatch, tmp_path):
        """真实 app.yaml 的 `database.file` 能被路径入口正确解析（端到端）。"""
        monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path))
        manifest = load_manifest(get_apps_root() / 'hello_world')
        assert manifest.database_file == 'data/hello_world.db'
        assert get_app_db_path(manifest.app_id, manifest.database_file) == \
            str(tmp_path / 'hello_world.db')
