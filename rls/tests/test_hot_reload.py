"""
test_hot_reload.py - M11 v1.3.0 配置热加载 + 5×5 场景矩阵

TODO-3 验证：
- HotReloadWatcher mtime 检测
- check_and_reload 手动检查
- start_hot_reload / stop_hot_reload 生命周期
- 文件修改后自动重新加载

TODO-4 验证：
- 5 角色 × 5 entity 端到端场景矩阵
- 覆盖 admin / manager / user / viewer / ai-agent
- 覆盖 order / user / product / role / business_object
- 验证 5×5 = 25 场景全部正确
"""
import os
import sys
import time
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestHotReloadWatcher(unittest.TestCase):
    """HotReloadWatcher 单元测试（TODO-3）"""

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_hot_')
        self._write_yaml('order.yaml', """
entity: order
actions:
  read: [role:user]
""")

    def tearDown(self):
        from rls.hot_reload import stop_hot_reload
        stop_hot_reload()
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def _write_yaml(self, filename, content):
        with open(os.path.join(self.tmpdir, filename), 'w', encoding='utf-8') as f:
            f.write(content.lstrip())

    def test_initial_mtime_recorded(self):
        """初始 mtime 被记录"""
        from rls.hot_reload import HotReloadWatcher
        watcher = HotReloadWatcher(self.tmpdir, callback=lambda: None)
        mtimes = watcher._get_mtimes()
        self.assertEqual(len(mtimes), 1)
        self.assertIn('order.yaml', list(mtimes.keys())[0])

    def test_check_once_no_change(self):
        """无变化时 check_once 返回 False"""
        from rls.hot_reload import HotReloadWatcher
        watcher = HotReloadWatcher(self.tmpdir, callback=lambda: None)
        watcher._initialized = True  # 模拟已建立 baseline
        watcher._last_mtimes = watcher._get_mtimes()
        self.assertFalse(watcher.check_once())

    def test_check_once_file_modified(self):
        """文件修改后 check_once 返回 True"""
        from rls.hot_reload import HotReloadWatcher
        watcher = HotReloadWatcher(self.tmpdir, callback=lambda: None)
        watcher._initialized = True  # 模拟已建立 baseline
        watcher._last_mtimes = watcher._get_mtimes()
        # 修改文件
        time.sleep(0.05)  # 确保 mtime 变化
        self._write_yaml('order.yaml', """
entity: order
actions:
  read: [role:admin, role:user]
""")
        self.assertTrue(watcher.check_once())

    def test_check_once_file_added(self):
        """新增 yaml 后 check_once 返回 True"""
        from rls.hot_reload import HotReloadWatcher
        watcher = HotReloadWatcher(self.tmpdir, callback=lambda: None)
        watcher._initialized = True  # 模拟已建立 baseline
        watcher._last_mtimes = watcher._get_mtimes()
        time.sleep(0.05)
        self._write_yaml('user.yaml', """
entity: user
actions:
  read: [role:admin]
""")
        self.assertTrue(watcher.check_once())

    def test_check_once_callback_invoked(self):
        """check_once 调用 callback"""
        from rls.hot_reload import HotReloadWatcher
        mock_cb = MagicMock()
        watcher = HotReloadWatcher(self.tmpdir, callback=mock_cb)
        watcher._initialized = True  # 模拟已建立 baseline
        watcher._last_mtimes = watcher._get_mtimes()
        time.sleep(0.05)
        self._write_yaml('order.yaml', """
entity: order
actions:
  read: [role:admin]
""")
        self.assertTrue(watcher.check_once())
        mock_cb.assert_called_once()

    def test_check_once_callback_exception(self):
        """callback 抛错时不传播"""
        from rls.hot_reload import HotReloadWatcher
        mock_cb = MagicMock(side_effect=Exception('test error'))
        watcher = HotReloadWatcher(self.tmpdir, callback=mock_cb)
        watcher._initialized = True  # 模拟已建立 baseline
        watcher._last_mtimes = watcher._get_mtimes()
        time.sleep(0.05)
        self._write_yaml('order.yaml', """
entity: order
actions:
  read: [role:admin]
""")
        # 不抛错
        self.assertTrue(watcher.check_once())

    def test_nonexistent_dir_no_error(self):
        """不存在的目录不抛错"""
        from rls.hot_reload import HotReloadWatcher
        watcher = HotReloadWatcher('/nonexistent/path', callback=lambda: None)
        mtimes = watcher._get_mtimes()
        self.assertEqual(mtimes, {})


class TestCheckAndReload(unittest.TestCase):
    """check_and_reload 公开 API"""

    def setUp(self):
        from rls.loader import RLSLoader
        from rls import reset_check_and_reload_state
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        reset_check_and_reload_state()
        self.tmpdir = tempfile.mkdtemp(prefix='rls_check_reload_')
        with open(os.path.join(self.tmpdir, 'order.yaml'), 'w', encoding='utf-8') as f:
            f.write("entity: order\nactions:\n  read: [role:user]\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_check_and_reload_no_change(self):
        """无变化返回 False"""
        from rls import check_and_reload
        # 先加载一次以建立 baseline
        check_and_reload(self.tmpdir)
        # 第二次调用应返回 False
        result = check_and_reload(self.tmpdir)
        self.assertFalse(result)

    def test_check_and_reload_with_change(self):
        """有变化返回 True + 重新加载"""
        from rls import check_and_reload
        # 先加载（首次 baseline）
        first = check_and_reload(self.tmpdir)
        self.assertFalse(first)  # 首次建立 baseline → False
        time.sleep(0.05)
        # 修改
        with open(os.path.join(self.tmpdir, 'order.yaml'), 'w', encoding='utf-8') as f:
            f.write("entity: order\nactions:\n  read: [role:admin, role:user]\n")
        # 重新加载（mtime 变化）
        result = check_and_reload(self.tmpdir)
        self.assertTrue(result)


class TestStartHotReload(unittest.TestCase):
    """start_hot_reload / stop_hot_reload 单例管理"""

    def tearDown(self):
        from rls.hot_reload import stop_hot_reload
        stop_hot_reload()

    def test_start_and_stop(self):
        """start + stop 生命周期"""
        from rls.hot_reload import start_hot_reload, stop_hot_reload
        tmpdir = tempfile.mkdtemp(prefix='rls_start_')
        try:
            watcher = start_hot_reload(tmpdir, interval=0.5)
            self.assertIsNotNone(watcher)
            self.assertTrue(watcher._thread.is_alive())
            stop_hot_reload()
            # 停止后线程应在 2s 内结束（通过 stop_event）
            self.assertTrue(watcher._stop_event.wait(2.5))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_start_replaces_previous(self):
        """再次 start 会替换前一个"""
        from rls.hot_reload import start_hot_reload, stop_hot_reload
        from rls import hot_reload as hr_mod
        tmpdir1 = tempfile.mkdtemp(prefix='rls_replace_1_')
        tmpdir2 = tempfile.mkdtemp(prefix='rls_replace_2_')
        try:
            w1 = start_hot_reload(tmpdir1, interval=0.5)
            w2 = start_hot_reload(tmpdir2, interval=0.5)
            self.assertIsNot(w1, w2)
            self.assertIs(hr_mod._watcher_instance, w2)
            stop_hot_reload()
        finally:
            shutil.rmtree(tmpdir1, ignore_errors=True)
            shutil.rmtree(tmpdir2, ignore_errors=True)


class TestFiveByFiveScenarios(unittest.TestCase):
    """5 角色 × 5 entity 端到端场景矩阵（TODO-4）"""

    ROLES = ['admin', 'manager', 'user', 'viewer', 'ai-agent']
    ENTITIES = ['order', 'user', 'product', 'role', 'business_object']

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_5x5_')
        for entity in self.ENTITIES:
            with open(os.path.join(self.tmpdir, f'{entity}.yaml'), 'w', encoding='utf-8') as f:
                f.write(f"""
entity: {entity}
row_filters:
  - applies_to: [role:user, role:viewer]
    condition: "user.company_id == {entity}.company_id"
  - applies_to: [role:admin, role:manager]
    condition: "true"
  - applies_to: [role:ai-agent]
    condition: "{entity}.is_public == true"
field_masks:
  - field: phone
    mask: "***-****-{{}}"
    applies_to: [role:user, role:viewer, role:ai-agent]
  - field: amount
    mask: "***"
    applies_to: [role:viewer, role:ai-agent]
actions:
  create: [role:admin, role:manager]
  read: [role:admin, role:manager, role:user, role:viewer, role:ai-agent]
  update: [role:admin, role:manager]
  delete: [role:admin]
  export: [role:admin, role:manager, role:ai-agent]
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_admin_can_do_anything(self):
        """admin 角色：可 create/read/update/delete/export"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        for entity in self.ENTITIES:
            for action in ['create', 'read', 'update', 'delete', 'export']:
                result = _check_yaml_permission(
                    {'id': 1, 'roles': ['admin']}, entity, action
                )
                self.assertEqual(
                    result, True,
                    f'admin 角色应能 {action} {entity}（实际: {result}）'
                )

    def test_manager_can_crud_export(self):
        """manager 角色：可 create/read/update/export（不可 delete）"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        for entity in self.ENTITIES:
            for action in ['create', 'read', 'update', 'export']:
                result = _check_yaml_permission(
                    {'id': 1, 'roles': ['manager']}, entity, action
                )
                self.assertEqual(
                    result, True,
                    f'manager 角色应能 {action} {entity}'
                )
            # delete 不允许
            result = _check_yaml_permission(
                {'id': 1, 'roles': ['manager']}, entity, 'delete'
            )
            self.assertEqual(
                result, False,
                f'manager 角色不应能 delete {entity}'
            )

    def test_user_can_read_only(self):
        """user 角色：仅可 read"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        for entity in self.ENTITIES:
            result = _check_yaml_permission(
                {'id': 1, 'roles': ['user']}, entity, 'read'
            )
            self.assertEqual(result, True, f'user 角色应能 read {entity}')
            for action in ['create', 'update', 'delete', 'export']:
                result = _check_yaml_permission(
                    {'id': 1, 'roles': ['user']}, entity, action
                )
                self.assertEqual(
                    result, False,
                    f'user 角色不应能 {action} {entity}'
                )

    def test_viewer_can_read_only(self):
        """viewer 角色：仅可 read（与 user 相同 actions）"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        for entity in self.ENTITIES:
            result = _check_yaml_permission(
                {'id': 1, 'roles': ['viewer']}, entity, 'read'
            )
            self.assertEqual(result, True)
            for action in ['create', 'update', 'delete', 'export']:
                result = _check_yaml_permission(
                    {'id': 1, 'roles': ['viewer']}, entity, action
                )
                self.assertEqual(result, False)

    def test_ai_agent_can_read_and_export(self):
        """ai-agent 角色：可 read + export（不可 create/update/delete）"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        for entity in self.ENTITIES:
            for action in ['read', 'export']:
                result = _check_yaml_permission(
                    {'id': 1, 'roles': ['ai-agent']}, entity, action
                )
                self.assertEqual(
                    result, True,
                    f'ai-agent 角色应能 {action} {entity}'
                )
            for action in ['create', 'update', 'delete']:
                result = _check_yaml_permission(
                    {'id': 1, 'roles': ['ai-agent']}, entity, action
                )
                self.assertEqual(
                    result, False,
                    f'ai-agent 角色不应能 {action} {entity}'
                )

    def test_user_and_viewer_get_row_filter(self):
        """user/viewer 角色在所有 entity 都获得 company_id 行级过滤"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        for role in ['user', 'viewer']:
            for entity in self.ENTITIES:
                result = _check_yaml_row_filter(
                    {'id': 1, 'roles': [role]}, entity, '', user_id=1
                )
                self.assertIn(
                    'company_id', result,
                    f'{role} 角色在 {entity} 应获得 company_id 过滤'
                )

    def test_ai_agent_gets_is_public_filter(self):
        """ai-agent 角色在所有 entity 都获得 is_public 行级过滤"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        for entity in self.ENTITIES:
            result = _check_yaml_row_filter(
                {'id': 1, 'roles': ['ai-agent']}, entity, '', user_id=1
            )
            self.assertIn('is_public', result)

    def test_admin_manager_get_true(self):
        """admin/manager 角色获得 'true' 条件（无过滤）"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        for role in ['admin', 'manager']:
            for entity in self.ENTITIES:
                result = _check_yaml_row_filter(
                    {'id': 1, 'roles': [role]}, entity, '', user_id=1
                )
                self.assertEqual(result, 'true')

    def test_user_viewer_ai_agent_phone_masked(self):
        """user/viewer/ai-agent 角色 phone 字段脱敏"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _apply_yaml_field_masks
        for role in ['user', 'viewer', 'ai-agent']:
            for entity in self.ENTITIES:
                data = {'phone': '13800001234', 'id': 1}
                result = _apply_yaml_field_masks(
                    {'id': 1, 'roles': [role]}, entity, data
                )
                self.assertEqual(
                    result['phone'], '***-****-1234',
                    f'{role} 角色在 {entity} 的 phone 应被脱敏'
                )

    def test_admin_phone_not_masked(self):
        """admin 角色 phone 字段不脱敏"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _apply_yaml_field_masks
        for entity in self.ENTITIES:
            data = {'phone': '13800001234', 'id': 1}
            result = _apply_yaml_field_masks(
                {'id': 1, 'roles': ['admin']}, entity, data
            )
            self.assertEqual(
                result['phone'], '13800001234',
                f'admin 角色在 {entity} 的 phone 不应被脱敏'
            )

    def test_viewer_ai_agent_amount_masked(self):
        """viewer/ai-agent 角色 amount 字段脱敏"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _apply_yaml_field_masks
        for role in ['viewer', 'ai-agent']:
            for entity in self.ENTITIES:
                data = {'amount': 1000, 'id': 1}
                result = _apply_yaml_field_masks(
                    {'id': 1, 'roles': [role]}, entity, data
                )
                self.assertEqual(
                    result['amount'], '***',
                    f'{role} 角色在 {entity} 的 amount 应被脱敏'
                )

    def test_25_scenarios_complete(self):
        """完整 5 角色 × 5 entity = 25 场景汇总（read 操作）"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        results = {}
        for role in self.ROLES:
            for entity in self.ENTITIES:
                key = f'{role}->{entity}'
                result = _check_yaml_permission(
                    {'id': 1, 'roles': [role]}, entity, 'read'
                )
                results[key] = result
        # 25 场景全部应该允许 read
        for key, result in results.items():
            self.assertEqual(
                result, True,
                f'5×5 场景矩阵失败：{key}（{result}）'
            )
        self.assertEqual(len(results), 25)


if __name__ == '__main__':
    unittest.main()
