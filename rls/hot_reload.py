"""
rls/hot_reload.py - M11 v1.3.0 YAML 配置热加载

功能：
- 监控 rls_rules/*.yaml 文件 mtime
- 文件修改后自动调用 loader.clear_cache()
- 1 秒内生效（无服务重启）
- 可集成到 bo_framework.before_action 钩子

用法（推荐）：
    from rls.hot_reload import start_hot_reload

    watcher = start_hot_reload('rls_rules/')
    # 后台线程会自动监控

用法（手动检查）：
    from rls.hot_reload import check_and_reload

    if check_and_reload('rls_rules/'):
        print('rules reloaded')
"""
import os
import glob
import time
import logging
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class HotReloadWatcher:
    """YAML 配置热加载监听器

    行为：
    1. 启动后台线程（daemon）
    2. 每 interval 秒检查 rls_rules/*.yaml 文件 mtime
    3. mtime 变化 → 调用 loader.clear_cache() → 下次 load_all() 重新加载
    """

    def __init__(
        self,
        rules_dir: str,
        callback: Optional[Callable[[], None]] = None,
        interval: float = 1.0,
    ):
        self._dir = rules_dir
        self._callback = callback
        self._interval = interval
        self._last_mtimes: dict = {}
        self._initialized = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _get_mtimes(self) -> dict:
        """获取当前所有 yaml 文件的 mtime"""
        mtimes = {}
        if not os.path.isdir(self._dir):
            return mtimes
        for yaml_file in glob.glob(os.path.join(self._dir, '*.yaml')):
            try:
                mtimes[yaml_file] = os.path.getmtime(yaml_file)
            except OSError:
                continue
        return mtimes

    def _has_changed(self) -> bool:
        """检查文件 mtime 是否变化"""
        current = self._get_mtimes()
        if current != self._last_mtimes:
            self._last_mtimes = current
            return True
        return False

    def check_once(self) -> bool:
        """检查一次（手动调用）。返回 True 表示有变化。

        首次调用：建立 baseline，不算 reload → 返回 False
        后续调用：mtime 变化 → 触发 callback → 返回 True
        """
        with self._lock:
            if not self._initialized:
                self._last_mtimes = self._get_mtimes()
                self._initialized = True
                return False  # 首次建立 baseline
            changed = self._has_changed()
            if changed and self._callback:
                try:
                    self._callback()
                except Exception as e:
                    logger.error(f"[HotReload] callback error: {e}")
            return changed

    def _loop(self):
        """后台线程主循环"""
        logger.info(f"[HotReload] watching {self._dir} every {self._interval}s")
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception as e:
                logger.error(f"[HotReload] error in loop: {e}")
            self._stop_event.wait(self._interval)

    def start(self) -> 'HotReloadWatcher':
        """启动后台线程"""
        if self._thread and self._thread.is_alive():
            return self  # 已启动
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """停止后台线程"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None


# ==================== 公开 API ====================

def _get_yaml_mtimes(rules_dir: str) -> dict:
    """获取 yaml 文件 mtime dict"""
    mtimes = {}
    if not os.path.isdir(rules_dir):
        return mtimes
    for yaml_file in glob.glob(os.path.join(rules_dir, '*.yaml')):
        try:
            mtimes[yaml_file] = os.path.getmtime(yaml_file)
        except OSError:
            continue
    return mtimes


# 跨调用状态（rules_dir -> {'mtimes': {}, 'initialized': False}）
_check_and_reload_state: dict = {}


def check_and_reload(rules_dir: str) -> bool:
    """手动检查并重载（无后台线程）

    跨调用保持状态：
    1. 首次调用：建立 baseline → 返回 False
    2. mtime 变化：清缓存 → 返回 True
    3. mtime 无变化：返回 False

    Args:
        rules_dir: rls_rules 目录路径

    Returns:
        bool: 是否有变化（True = 已重载）
    """
    from .loader import clear_cache

    current = _get_yaml_mtimes(rules_dir)
    state = _check_and_reload_state.setdefault(
        rules_dir, {'mtimes': {}, 'initialized': False}
    )

    if not state['initialized']:
        state['mtimes'] = current
        state['initialized'] = True
        return False  # 首次建立 baseline

    if current != state['mtimes']:
        state['mtimes'] = current
        clear_cache()
        logger.info(f"[HotReload] rules reloaded: {rules_dir}")
        return True
    return False


def reset_check_and_reload_state() -> None:
    """重置 check_and_reload 跨调用状态（测试用）"""
    global _check_and_reload_state
    _check_and_reload_state = {}


_watcher_instance: Optional[HotReloadWatcher] = None


def start_hot_reload(rules_dir: str, interval: float = 1.0) -> HotReloadWatcher:
    """启动全局热加载监听器（单例）

    Args:
        rules_dir: rls_rules 目录
        interval: 检查间隔（秒，默认 1.0）

    Returns:
        HotReloadWatcher 实例
    """
    global _watcher_instance
    from .loader import clear_cache

    if _watcher_instance is not None:
        _watcher_instance.stop()
        _watcher_instance = None

    def _reload():
        clear_cache()
        logger.info(f"[HotReload] global rules reloaded: {rules_dir}")

    _watcher_instance = HotReloadWatcher(
        rules_dir=rules_dir,
        callback=_reload,
        interval=interval,
    )
    _watcher_instance.start()
    return _watcher_instance


def stop_hot_reload() -> None:
    """停止全局热加载监听器"""
    global _watcher_instance
    if _watcher_instance:
        _watcher_instance.stop()
        _watcher_instance = None
