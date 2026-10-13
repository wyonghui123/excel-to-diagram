# -*- coding: utf-8 -*-
"""[平台模块启用开关 / roadmap v1.32.0 §6.2.4] 测试

覆盖:
- is_module_enabled 的三条路径（默认全开 / 黑名单命中 / 空白与未设）
- 解析细节（逗号分隔 / 空格容忍 / 大小写敏感 / 只解析一次）
- disabled_modules / KNOWN_PLATFORM_MODULES / clear_cache
- 作用点①: server.py 条件注册 —— 禁用后三个 task blueprint 的路由真 404
- 作用点②: 菜单种子同门 —— 禁用时不写 task 菜单

边界: 本文件不测 app 依赖校验（`requires` 段暂无平台模块声明面，见 §6.2.4 (6)-4）。

执行: python d:\\filework\\test.py --file meta/tests/test_platform_modules_20261013.py
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from meta.core import platform_modules  # noqa: E402
from meta.core.platform_modules import (  # noqa: E402
    CLOSABLE_PLATFORM_MODULES,
    ENV_DISABLED_PLATFORM_MODULES,
    KNOWN_PLATFORM_MODULES,
    clear_cache,
    disabled_modules,
    ineffective_disables,
    is_module_enabled,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """每个用例都从"未设置 + 空缓存"起步。"""
    monkeypatch.delenv(ENV_DISABLED_PLATFORM_MODULES, raising=False)
    clear_cache()
    yield
    clear_cache()


class TestIsModuleEnabled:
    """黑名单语义：不在黑名单中即启用（默认全开）。"""

    def test_default_all_enabled(self):
        assert is_module_enabled('tasks') is True
        assert is_module_enabled('rules') is True

    def test_blacklist_hit_disables(self, monkeypatch):
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        assert is_module_enabled('tasks') is False
        assert is_module_enabled('rules') is True   # 只关命中的

    def test_blank_value_treated_as_unset(self, monkeypatch):
        """.env 里写了空值（`DISABLED_PLATFORM_MODULES=`）必须视为未设置。"""
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, '')
        clear_cache()
        assert is_module_enabled('tasks') is True

    def test_whitespace_only_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, '  ,  , ')
        clear_cache()
        assert is_module_enabled('tasks') is True

    def test_multi_value_parsed(self, monkeypatch):
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks,rules')
        clear_cache()
        assert is_module_enabled('tasks') is False
        assert is_module_enabled('rules') is False

    def test_spaces_around_comma_tolerated(self, monkeypatch):
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, ' tasks , rules ')
        clear_cache()
        assert is_module_enabled('tasks') is False
        assert is_module_enabled('rules') is False

    def test_unknown_module_id_defaults_enabled(self):
        """未登记的 id 也默认启用 —— 不因没登记就意外关闭。"""
        assert is_module_enabled('not_a_real_module') is True

    def test_id_matching_is_case_sensitive(self, monkeypatch):
        """大小写不匹配 ⇒ 不命中黑名单（避免 'Tasks' 静默失效）。"""
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'TASKS')
        clear_cache()
        assert is_module_enabled('tasks') is True


class TestParsing:
    """解析结果与缓存行为。"""

    def test_disabled_modules_returns_frozenset(self, monkeypatch):
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        assert disabled_modules() == frozenset({'tasks'})

    def test_disabled_modules_empty_by_default(self):
        assert disabled_modules() == frozenset()

    def test_parsed_once_then_cached(self, monkeypatch):
        """进程内只解析一次 —— 改环境变量需 clear_cache（与 feature_flags 同约定）。"""
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        assert is_module_enabled('tasks') is False
        # 不 clear_cache 直接改 env —— 缓存仍在，值不变
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, '')
        assert is_module_enabled('tasks') is False
        clear_cache()
        assert is_module_enabled('tasks') is True

    def test_clear_cache_resets(self, monkeypatch):
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        assert disabled_modules() == frozenset({'tasks'})
        monkeypatch.delenv(ENV_DISABLED_PLATFORM_MODULES)
        clear_cache()
        assert disabled_modules() == frozenset()


class TestKnownModules:
    """登记表与常量。"""

    def test_known_modules_contains_two(self):
        assert set(KNOWN_PLATFORM_MODULES) == {'tasks', 'rules'}

    def test_only_tasks_is_closable(self):
        """规则体系暂不可关闭（无独立入口）—— 见 platform_modules.py 注释。"""
        assert set(CLOSABLE_PLATFORM_MODULES) == {'tasks'}

    def test_env_key_name(self):
        assert ENV_DISABLED_PLATFORM_MODULES == 'DISABLED_PLATFORM_MODULES'


class TestIneffectiveDisables:
    """写了但无效果的 id 须可被发现（避免误以为已关闭）。"""

    def test_empty_by_default(self):
        assert ineffective_disables() == frozenset()

    def test_effective_disable_not_reported(self, monkeypatch):
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        assert ineffective_disables() == frozenset(), "tasks 是真关闭，不该报为无效"

    def test_inclosable_id_reported(self, monkeypatch):
        """rules 写了不报错但无效果 —— 必须能被探出来。"""
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'rules')
        clear_cache()
        assert ineffective_disables() == frozenset({'rules'})

    def test_mixed_reports_only_inclosable(self, monkeypatch):
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks,rules')
        clear_cache()
        assert ineffective_disables() == frozenset({'rules'})


class TestHealthExposesSwitch:
    """/health 须暴露开关状态（部署后能确认是否真生效）。"""

    def test_health_reports_default_empty(self, tmp_path_factory, monkeypatch):
        TestServerBlueprintGate._isolate_db(tmp_path_factory, monkeypatch, 'pmod_health_on')
        app = TestServerBlueprintGate._build_app()
        body = app.test_client().get('/health').get_json()
        assert body['disabled_platform_modules'] == []
        assert body['ineffective_platform_modules'] == []

    def test_health_reports_disabled_tasks(self, tmp_path_factory, monkeypatch):
        TestServerBlueprintGate._isolate_db(tmp_path_factory, monkeypatch, 'pmod_health_off')
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        try:
            app = TestServerBlueprintGate._build_app()
            body = app.test_client().get('/health').get_json()
            assert body['disabled_platform_modules'] == ['tasks']
            assert body['ineffective_platform_modules'] == []
            # 既有字段不受影响
            assert body['status'] == 'ok'
            assert body['service'] == 'arch-data-manage-api'
        finally:
            clear_cache()

    def test_health_flags_ineffective_rules(self, tmp_path_factory, monkeypatch):
        TestServerBlueprintGate._isolate_db(tmp_path_factory, monkeypatch, 'pmod_health_rules')
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'rules')
        clear_cache()
        try:
            app = TestServerBlueprintGate._build_app()
            body = app.test_client().get('/health').get_json()
            assert body['disabled_platform_modules'] == ['rules']
            assert body['ineffective_platform_modules'] == ['rules'], \
                "写了 rules 但关不掉 —— 探活点须如实报出"
        finally:
            clear_cache()


class TestServerBlueprintGate:
    """作用点①：禁用后 task blueprint 不注册 ⇒ 路由真 404。

    用真实 create_app() 验证（不是只测 is_module_enabled）。

    注意：平台库路径只认 SQLITE_DB_PATH / ARCH_DB_PATH（见 core/db_path.py），
    **不认 SQLITE_DB_DIR** —— 必须设 SQLITE_DB_PATH，否则 create_app 会
    对仓库内 meta/architecture.db 跑迁移与种子（污染开发库）。
    """

    @staticmethod
    def _isolate_db(tmp_path_factory, monkeypatch, tag):
        d = tmp_path_factory.mktemp(tag)
        monkeypatch.setenv("SQLITE_DB_PATH", str(Path(d) / "architecture.db"))
        monkeypatch.setenv("SQLITE_DB_DIR", str(d))
        return d

    @staticmethod
    def _build_app():
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from meta.server import create_app
            app = create_app()
        app.config["TESTING"] = True
        return app

    def test_task_routes_registered_when_enabled(self, tmp_path_factory, monkeypatch):
        """默认全开 ⇒ task 路由存在（存量零风险的第一道保证）。"""
        self._isolate_db(tmp_path_factory, monkeypatch, 'pmod_on')
        app = self._build_app()
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert any('/api/v1/tasks' in r for r in rules), \
            "默认应注册 task blueprint（存量零风险）"

    def test_task_routes_absent_when_disabled(self, tmp_path_factory, monkeypatch):
        """禁用 ⇒ 路由不存在（不是"前端看不见"，是真 404）。"""
        self._isolate_db(tmp_path_factory, monkeypatch, 'pmod_off')
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        try:
            app = self._build_app()
            rules = {r.rule for r in app.url_map.iter_rules()}
            assert not any(r.startswith('/api/v1/tasks') for r in rules), \
                "禁用后不应存在 /api/v1/tasks* 路由"
            assert not any('task-inbox' in r for r in rules), \
                "禁用后不应存在 task_inbox 路由"
        finally:
            clear_cache()

    def test_unrelated_routes_survive_when_disabled(self, tmp_path_factory, monkeypatch):
        """只关任务体系 —— 其他平台路由不受影响。"""
        self._isolate_db(tmp_path_factory, monkeypatch, 'pmod_off2')
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        try:
            app = self._build_app()
            rules = {r.rule for r in app.url_map.iter_rules()}
            # 平台基础能力必须在（证明是"按模块关闭"而非"整体失败"）
            assert any('/api/v2/meta' in r for r in rules)
        finally:
            clear_cache()


class TestMenuSeedGate:
    """作用点②：禁用时不写 task 菜单 ⇒ 前端侧栏无数据。

    用真实 create_app() + 查 menus 表验证（不是打桩）。
    """

    def test_task_menus_written_when_enabled(self, tmp_path_factory, monkeypatch):
        """默认全开 ⇒ 任务菜单种子写入（存量行为不变）。"""
        import sqlite3
        d = TestServerBlueprintGate._isolate_db(tmp_path_factory, monkeypatch, 'pmod_menu_on')
        TestServerBlueprintGate._build_app()
        con = sqlite3.connect(str(Path(d) / "architecture.db"))
        codes = {r[0] for r in con.execute(
            "SELECT menu_code FROM menus WHERE menu_code LIKE '%task%'")}
        con.close()
        assert 'task-management' in codes, "默认应写入任务菜单种子"

    def test_task_menus_absent_when_disabled(self, tmp_path_factory, monkeypatch):
        """禁用 ⇒ 种子菜单不写入（前端侧栏无数据）。

        残留的 *-list 菜单（scheduled_task-list 等）由 menu_auto_generator 生成，
        恒为 show_in_sidebar=0 ⇒ 侧栏本就不可见（已实测）。
        """
        import sqlite3
        d = TestServerBlueprintGate._isolate_db(tmp_path_factory, monkeypatch, 'pmod_menu_off')
        monkeypatch.setenv(ENV_DISABLED_PLATFORM_MODULES, 'tasks')
        clear_cache()
        try:
            TestServerBlueprintGate._build_app()
            con = sqlite3.connect(str(Path(d) / "architecture.db"))
            rows = con.execute(
                "SELECT menu_code, show_in_sidebar FROM menus WHERE menu_code LIKE '%task%'"
            ).fetchall()
            con.close()
            codes = {r[0] for r in rows}
            assert 'task-management' not in codes, "禁用后不应写入 task-management 菜单"
            assert 'task-definitions' not in codes
            # 任何残留项都不得在侧栏可见
            for code, sidebar in rows:
                assert not sidebar, f"禁用后残留菜单 {code} 不应 show_in_sidebar=1"
        finally:
            clear_cache()