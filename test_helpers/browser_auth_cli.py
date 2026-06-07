"""
Playwright CLI 封装层 - 高效浏览器自动化测试工具

Token 效率：比 MCP 低 4-5x，适用于长流程测试和 CI 自动化

核心特性：
1. 认证 + 导航 一行搞定：authenticated_navigate()
2. 突变可识别：snapshot() → 操作 → diff_snapshots() → 精确知道什么变了
3. 内容可验证：assert_table() / assert_text() / get_component_state()
4. 一行验证：verify_action() 自动快照 + 执行 + diff
5. 增强型突变追踪：三层追踪（Store + DOM + Network），get_all_changes()
6. 多层一致性检查：verify_table_consistency() / detect_error_states()
7. 稳定性等待：wait_for_stable() 替代盲目的 wait_for_timeout

使用示例:
    from test_helpers.browser_auth_cli import PlaywrightCLI

    cli = PlaywrightCLI()

    # 认证 + 导航
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')

    # 一行验证：点击按钮后检查 boCrud store 变化
    result = cli.verify_action(
        "document.querySelector('.el-checkbox').click()",
        store_name='boCrud'
    )
    print(result['diff'])  # { changed: true, changes: { boCrud: { ... } } }

    # 增强型追踪：启动所有追踪 → 操作 → 获取完整变化报告
    cli.start_all_tracking()
    cli.click('.save-btn')
    cli.wait_for_stable()  # 智能等待稳定，不盲目 sleep
    changes = cli.get_all_changes()
    # changes['store']  → Pinia 哪些 store 变了
    # changes['dom']    → DOM 哪些属性/元素变了
    # changes['network']→ 发了哪些 API 请求

    # 跨层一致性验证
    consistency = cli.verify_table_consistency('boCrud', '.el-table')
    # { ok: true, domRowCount: 10, storeItemCount: 10, checks: {rowCountMatch: true} }

    # 错误状态自动检测
    errors = cli.assert_no_errors()
    # { ok: true/false, details: { hasErrors, hasWarnings, hasLoading, hasEmpty } }

    # 关闭
    cli.close()
"""

import atexit
import json
import os
import time
import urllib.request
import urllib.error
from typing import Optional, Any, Dict, List, Union
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
except ImportError:
    raise ImportError(
        "playwright 未安装。请运行: pip install playwright && playwright install chromium"
    )


class PlaywrightCLI:
    """
    Playwright CLI 封装类 - 提供高效的浏览器自动化测试接口

    相比 MCP DevTools 的优势:
    1. Token 消耗降低 4-5x
    2. Session 在命令间保持稳定
    3. 支持跨浏览器 (Chrome/Firefox/WebKit)
    4. 原生支持 CI 集成
    """

    DEFAULT_TIMEOUT = 30000
    NAVIGATION_TIMEOUT = 15000
    ELEMENT_TIMEOUT = 5000

    def __init__(
        self,
        browser_type: str = "chromium",
        headless: bool = True,
        screenshot_dir: str = None,
        telemetry_dir: str = None
    ):
        """
        初始化 Playwright CLI

        Args:
            browser_type: 浏览器类型 (chromium/firefox/webkit)
            headless: 是否无头模式
            screenshot_dir: 截图保存目录，默认 test_output/
            telemetry_dir: 遥测数据目录，默认 test_telemetry/（None 禁用）
        """
        self.browser_type = browser_type
        self.headless = headless
        self.screenshot_dir = screenshot_dir or os.path.join(os.getcwd(), 'test_output')

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._cookies_set = False
        self._closed = False

        self.telemetry = None
        if telemetry_dir is not None:
            from telemetry import TestTelemetry
            self.telemetry = TestTelemetry(
                telemetry_dir=telemetry_dir
            )

        atexit.register(self._cleanup)

    def _record_op(self, op: str, target: str, start: float, result: str = 'ok',
                   error: str = None, retries: int = None, waited_ms: int = None):
        if self.telemetry is None:
            return
        duration_ms = (time.time() - start) * 1000
        self.telemetry.record_operation(
            op=op, target=target, duration_ms=duration_ms,
            result=result, error=error, retries=retries, waited_ms=waited_ms
        )

    def _record_telemetry_event(self, type: str, layer: str, message: str,
                                 level: str = None, component: str = None):
        if self.telemetry is None:
            return
        self.telemetry.record_event(
            type=type, layer=layer, message=message,
            level=level, component=component
        )

    def _ensure_browser(self) -> Page:
        """确保浏览器已启动，返回当前页面"""
        if self._page is None or self._page.is_closed():
            self._start_browser()
        return self._page

    def _start_browser(self):
        """启动浏览器并创建新页面"""
        if self._playwright is None:
            self._playwright = sync_playwright().start()

        browser_map = {
            "chromium": self._playwright.chromium,
            "firefox": self._playwright.firefox,
            "webkit": self._playwright.webkit,
        }

        browser_launcher = browser_map.get(self.browser_type, self._playwright.chromium)
        self._browser = browser_launcher.launch(headless=self.headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._cookies_set = False

        self._page_errors = []
        self._console_errors = []
        self._page_crashed = False

        self._page.on('pageerror', lambda err: (
            self._page_errors.append({
                'type': 'pageerror',
                'message': str(err),
                'timestamp': time.time()
            }),
            self._record_telemetry_event('pageerror', 'page', str(err), level='error')
        ))

        def _on_console(msg):
            if msg.type in ('error', 'warning'):
                self._console_errors.append({
                    'type': 'console',
                    'level': msg.type,
                    'text': msg.text[:500],
                    'timestamp': time.time()
                })
                self._record_telemetry_event(
                    'console', 'console', msg.text[:500],
                    level='error' if msg.type == 'error' else 'warning'
                )
        self._page.on('console', _on_console)

        self._page.on('crash', lambda: (
            setattr(self, '_page_crashed', True),
            self._record_telemetry_event('crash', 'page', 'Page crashed', level='error')
        ))

    def request(self, url: str, method: str = "GET", data: dict = None) -> dict:
        """
        发送 HTTP 请求（用于 dev-login 等 API 调用）

        Args:
            url: 请求 URL
            method: HTTP 方法
            data: 请求数据 (dict 将转为 JSON)

        Returns:
            响应数据 (dict)
        """
        try:
            if data is not None:
                data_bytes = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data_bytes, method=method,
                    headers={"Content-Type": "application/json"}
                )
            else:
                req = urllib.request.Request(url, method=method)

            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode("utf-8")
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"data": content}

        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"error": f"URL Error: {e.reason}"}
        except Exception as e:
            return {"error": str(e)}

    def dev_login(self, username: str = "admin") -> bool:
        """
        执行 dev-login 认证

        Args:
            username: 用户名

        Returns:
            是否成功
        """
        result = self.request(
            f"http://localhost:3010/api/v1/auth/dev-login?username={username}"
        )

        if "error" in result:
            print(f"[ERROR] dev-login failed: {result['error']}")
            return False

        self._cookies_set = True
        return True

    def goto(self, url: str, wait_until: str = "domcontentloaded") -> Page:
        """
        导航到指定 URL

        Args:
            url: 目标 URL
            wait_until: 等待策略 (load/domcontentloaded/networkidle)

        Returns:
            Page 对象
        """
        page = self._ensure_browser()
        page.goto(url, wait_until=wait_until, timeout=self.NAVIGATION_TIMEOUT)
        return page

    def authenticated_navigate(
        self,
        target_path: str,
        base_url: str = "http://localhost:3004",
        wait_for_selector: str = None,
        wait_for_function: str = None,
        timeout: int = 15000
    ) -> Page:
        """
        带认证的 SPA 内部导航

        1. 浏览器访问 dev-login 设置 cookie
        2. 加载首页等待 store 就绪
        3. SPA 内部 router.push 导航

        Args:
            target_path: 目标路径，如 '/system/archdata'
            base_url: 前端基础 URL
            wait_for_selector: 等待指定的 CSS 选择器出现（支持逗号分隔的多选择器）
            wait_for_function: 等待指定的 JS 表达式返回真值
            timeout: 超时时间 (ms)

        Returns:
            Page 对象
        """
        t0 = time.time()
        if self.telemetry:
            self.telemetry.page_visited = target_path
            self.telemetry.test_name = self.telemetry.test_name or target_path.strip('/').replace('/', '_')

        page = self._ensure_browser()

        # Step 1: 浏览器访问 dev-login 设 cookie
        page.goto(
            "http://localhost:3010/api/v1/auth/dev-login?username=admin",
            wait_until="domcontentloaded",
            timeout=10000
        )

        # Step 2: 加载首页
        page.goto(base_url, wait_until="domcontentloaded", timeout=10000)

        # Step 3: 等待 store 就绪
        self._wait_for_store_ready(timeout=timeout)

        # Step 4: SPA 内部导航（不触发整页刷新）
        page.evaluate(f"""
            () => {{
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router
                router.push('{target_path}')
            }}
        """)

        # Step 5: 等待目标内容
        if wait_for_selector:
            page.wait_for_selector(wait_for_selector, timeout=timeout)
        elif wait_for_function:
            page.wait_for_function(
                f"() => {{ {wait_for_function} }}",
                timeout=timeout
            )
        else:
            # 默认等待表格或内容出现
            page.wait_for_timeout(1000)

        self._record_op('navigate', target_path, t0)
        return page

    def _sync_cookies_from_response(self):
        """从 dev-login 响应中同步 cookie 到 browser context"""
        # dev-login 通过 cookie 设置，browser 已自动接收
        pass

    def _wait_for_store_ready(self, timeout: int = 15000):
        """等待 Pinia store 就绪"""
        self._page.wait_for_function(
            """
            () => {
                // 方式1: 检查 #app.__vue_app__ 上的 Pinia
                const app = document.querySelector('#app')?.__vue_app__
                const pinia = app?.config?.globalProperties?.$pinia
                let store = pinia?._s?.get('auth')
                // 方式2: 通过 Vue devtools 全局状态
                if (!store && window.__pinia) {
                    store = window.__pinia._s?.get('auth')
                }
                // 方式3: 遍历 pinia state
                if (!store && pinia?._s) {
                    for (const [key, s] of pinia._s) {
                        if (s.$id === 'auth' || key === 'auth') {
                            store = s
                            break
                        }
                    }
                }
                return !!(store && store.user)
            }
            """,
            timeout=timeout
        )

    def wait_for_store_ready(self, timeout: int = 15000) -> bool:
        """
        等待 Pinia auth store 就绪

        Args:
            timeout: 超时时间 (ms)

        Returns:
            是否成功等待
        """
        try:
            self._ensure_browser()
            self._wait_for_store_ready(timeout)
            return True
        except Exception as e:
            print(f"[WARN] Store ready wait failed: {e}")
            return False

    def screenshot(
        self,
        path: str = None,
        full_page: bool = True,
        element: str = None
    ) -> str:
        """
        截图

        Args:
            path: 保存路径，默认使用 timestamp 命名
            full_page: 是否截取整个页面
            element: CSS 选择器，指定则截取元素

        Returns:
            截图文件路径
        """
        page = self._ensure_browser()

        if path is None:
            timestamp = int(time.time() * 1000)
            path = os.path.join(self.screenshot_dir, f"screenshot_{timestamp}.png")
        elif not os.path.isabs(path) and os.sep not in path:
            path = os.path.join(self.screenshot_dir, path)

        os.makedirs(os.path.dirname(path) or self.screenshot_dir, exist_ok=True)

        if element:
            locator = page.locator(element)
            locator.screenshot(path=path)
        else:
            page.screenshot(path=path, full_page=full_page)

        return path

    def evaluate(self, script: str, *args, retries: int = 3) -> Any:
        """
        执行 JavaScript 代码

        Args:
            script: JavaScript 代码（可以是无参数函数或表达式）
            *args: 传递给函数的参数
            retries: context 销毁时重试次数

        Returns:
            执行结果
        """
        import time as _time
        
        for attempt in range(retries):
            page = self._ensure_browser()
            try:
                # 如果是函数调用形式，直接执行
                if script.strip().startswith("()"):
                    return page.evaluate(script, *args)
                else:
                    # 否则包装为函数
                    return page.evaluate(f"() => {{ return {script} }}", *args)
            except Exception as e:
                error_msg = str(e)
                if 'context was destroyed' in error_msg or 'Target closed' in error_msg:
                    if attempt < retries - 1:
                        _time.sleep(1.0)
                        continue
                raise

    def evaluate_async(self, script: str, timeout: int = 10000) -> Any:
        """
        执行异步 JavaScript 代码

        Args:
            script: 异步 JavaScript（返回 Promise）
            timeout: 超时时间

        Returns:
            Promise 的 resolved 值
        """
        page = self._ensure_browser()
        return page.evaluate(f"async () => {{ return {script} }}")

    # ============================================================
    # 测试辅助方法 — 突变可识别性 + 内容可验证性
    # ============================================================

    def _inject_helpers(self):
        """注入 __test__ 辅助对象到页面"""
        if getattr(self, '_helpers_injected', False):
            return
        helpers_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'inject_helpers.js'
        )
        with open(helpers_path, 'r', encoding='utf-8') as f:
            js_content = f.read()
        # 去掉开头的注释，确保是纯 IIFE
        # 找到第一个 (() => { 或 window.__test__ = (() => {
        idx = js_content.find('window.__test__')
        if idx == -1:
            raise RuntimeError("inject_helpers.js 格式错误: 找不到 window.__test__")
        script = js_content[idx:]
        self.evaluate(script)
        self._helpers_injected = True

    def snapshot(self) -> Dict:
        """
        获取所有 Pinia store 的状态快照

        Returns:
            { timestamp, stores: { storeName: { ...state } } }
        """
        self._inject_helpers()
        return self.evaluate("window.__test__.snapshot()")

    def diff_snapshots(self, before: Dict, after: Dict) -> Dict:
        """
        对比两个快照，返回变化的属性

        Args:
            before: 操作前的快照
            after: 操作后的快照

        Returns:
            { changed: bool, changes: { storeName: { prop: {from, to} } } }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "([prev, curr]) => window.__test__.diff(prev, curr)",
            [before, after]
        )

    def start_watching(self) -> str:
        """
        开始追踪所有 Pinia store 的 mutation

        Returns:
            状态描述字符串
        """
        self._inject_helpers()
        return self.evaluate("window.__test__.startWatching()")

    def get_mutations(self) -> List[Dict]:
        """
        获取并清空已追踪的 mutation 列表

        Returns:
            [{ store, mutationType, storeId, timestamp }]
        """
        self._inject_helpers()
        return self.evaluate("window.__test__.getMutations()")

    def assert_table(self, selector: str) -> Dict:
        """
        检查表格结构

        Returns:
            { found, rowCount, headers, firstRow }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "(sel) => window.__test__.assertTable(sel)", selector
        )

    def assert_text(self, selector: str, expected: str) -> Dict:
        """
        检查元素文本是否包含预期内容

        Returns:
            { found, text, match }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "([sel, exp]) => window.__test__.assertText(sel, exp)",
            [selector, expected]
        )

    def get_component_state(self, selector: str) -> Dict:
        """
        获取 Vue 组件的 props 状态

        Returns:
            { found, hasVue, props }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "(sel) => window.__test__.getComponentState(sel)", selector
        )

    def get_select_options(self, selector: str) -> Dict:
        """
        获取下拉选择框的选项列表

        Returns:
            { found, count, values }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "(sel) => window.__test__.getSelectOptions(sel)", selector
        )

    def wait_for_store_property(
        self, store_name: str, property_name: str, timeout: int = 10000
    ) -> Dict:
        """
        等待 Pinia store 的某个属性变为非空

        Args:
            store_name: store 名称 (如 'auth', 'boCrud')
            property_name: 属性名
            timeout: 超时时间 (ms)

        Returns:
            { ready, value }
        """
        self._inject_helpers()
        return self.evaluate_async(
            f"window.__test__.waitForStore('{store_name}', '{property_name}', {timeout})",
            timeout=timeout + 2000
        )

    def verify_action(self, action_fn: str, store_name: str = None) -> Dict:
        """
        执行操作并返回突变 diff — 一行验证

        用法:
            result = cli.verify_action(
                "document.querySelector('.el-button').click()",
                store_name='boCrud'
            )

        Returns:
            { before, after, diff: {changed, changes}, mutations }
        """
        self._inject_helpers()
        before = self.snapshot()
        self.start_watching()
        self.evaluate(action_fn)
        self._page.wait_for_timeout(500)
        after = self.snapshot()
        mutations = self.get_mutations()

        if store_name:
            before_sub = {k: v for k, v in before['stores'].items() if k == store_name}
            after_sub = {k: v for k, v in after['stores'].items() if k == store_name}
            d = self.diff_snapshots({'stores': before_sub}, {'stores': after_sub})
        else:
            d = self.diff_snapshots(before, after)

        return {
            'before': before,
            'after': after,
            'diff': d,
            'mutations': mutations
        }

    # ============================================================
    # 增强型突变追踪 — 三层：Store + DOM + Network
    # ============================================================

    def start_all_tracking(self, target_selector: str = None) -> Dict:
        """
        启动所有追踪层（Store + DOM + Network）

        在操作前调用，操作后调用 get_all_changes() 获取完整变化报告。

        Args:
            target_selector: DOM 追踪的目标容器选择器（默认 body）

        Returns:
            { store, dom, network } 启动状态
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "(sel) => window.__test__.startAllTracking(sel)",
            target_selector
        )

    def get_all_changes(self) -> Dict:
        """
        获取所有追踪层的变化汇总

        Returns:
            {
                timestamp,
                store: [{ store, type, timestamp }],
                dom: [{ type, attributeName, target, addedCount, removedCount }],
                network: [{ url, method, status, duration }],
                pendingRequests: int
            }
        """
        self._inject_helpers()
        return self.evaluate("window.__test__.getAllChanges()")

    def start_dom_tracking(self, target_selector: str = None) -> str:
        """启动 DOM MutationObserver 追踪"""
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "(sel) => window.__test__.startDOMTracking(sel)",
            target_selector
        )

    def get_dom_mutations(self) -> List[Dict]:
        """获取 DOM 变化列表"""
        self._inject_helpers()
        return self.evaluate("window.__test__.getDOMMutations()")

    def start_network_tracking(self) -> str:
        """启动网络请求追踪（拦截 fetch 和 XHR）"""
        self._inject_helpers()
        return self.evaluate("window.__test__.startNetworkTracking()")

    def get_network_requests(self) -> List[Dict]:
        """获取网络请求列表"""
        self._inject_helpers()
        return self.evaluate("window.__test__.getNetworkRequests()")

    def get_pending_requests(self) -> int:
        """获取待完成的网络请求数"""
        self._inject_helpers()
        return self.evaluate("window.__test__.getPendingRequests()")

    def wait_for_stable(self, max_wait: int = 10000, stable_window: int = 500) -> Dict:
        """
        等待页面稳定（无 pending 请求 + 无新 mutation）

        替代盲目的 wait_for_timeout，基于实际状态判断稳定性。

        Args:
            max_wait: 最大等待时间 (ms)
            stable_window: 稳定窗口 (ms)，在此窗口内无变化即认为稳定

        Returns:
            { stable: bool, waited: int, ... }
        """
        t0 = time.time()
        self._inject_helpers()
        result = self.evaluate_async(
            f"window.__test__.waitForStable({max_wait}, {stable_window})",
            timeout=max_wait + 3000
        )
        waited_ms = result.get('waited', 0) if isinstance(result, dict) else 0
        stable = result.get('stable', False) if isinstance(result, dict) else False
        self._record_op(
            'wait_for_stable', f'max={max_wait}ms',
            t0, result='ok' if stable else 'timeout',
            waited_ms=waited_ms
        )
        return result

    # ============================================================
    # 内容可验证性 — 多层一致性检查
    # ============================================================

    def verify_table_consistency(self, store_name: str, table_selector: str) -> Dict:
        """
        验证表格 DOM 与 Store 数据的一致性

        Args:
            store_name: Pinia store 名称（如 'boCrud'）
            table_selector: 表格 CSS 选择器

        Returns:
            { ok, domRowCount, storeItemCount, checks: {rowCountMatch, ...} }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "([store, sel]) => window.__test__.verifyTableConsistency(store, sel)",
            [store_name, table_selector]
        )

    def verify_form_consistency(self, store_name: str, form_selector: str) -> Dict:
        """
        验证表单 DOM 与 Store 数据的一致性

        Args:
            store_name: Pinia store 名称
            form_selector: 表单 CSS 选择器

        Returns:
            { ok, totalFields, mismatches: [{field, dom, store}] }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "([store, sel]) => window.__test__.verifyFormConsistency(store, sel)",
            [store_name, form_selector]
        )

    def detect_error_states(self) -> Dict:
        """
        自动检测页面错误/警告/加载/空状态

        Returns:
            { hasErrors, hasWarnings, hasLoading, hasEmpty, items: [...] }
        """
        self._inject_helpers()
        return self.evaluate("window.__test__.detectErrorStates()")

    def assert_no_errors(self) -> Dict:
        """
        断言页面无错误/警告/加载状态

        Returns:
            { ok: bool, details: {...} }
        """
        states = self.detect_error_states()
        ok = not (states.get('hasErrors') or states.get('hasWarnings'))
        return {
            'ok': ok,
            'details': states
        }

    def verify_table_data(self, table_selector: str, expected: Dict = None) -> Dict:
        """
        结构化验证表格数据

        Args:
            table_selector: 表格 CSS 选择器
            expected: 期望数据 { rowCount, headers, cellContains }

        Returns:
            { ok, headers, rowCount, rows, checks }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "([sel, exp]) => window.__test__.verifyTableData(sel, exp)",
            [table_selector, expected]
        )

    def verify_page_structure(self, selectors: List[str]) -> Dict:
        """
        验证页面关键元素存在且可见

        Args:
            selectors: CSS 选择器列表

        Returns:
            { ok: bool, elements: { selector: {found, visible} } }
        """
        self._inject_helpers()
        page = self._ensure_browser()
        return page.evaluate(
            "(sels) => window.__test__.verifyPageStructure(sels)",
            selectors
        )

    def assert_network_complete(self) -> Dict:
        """
        断言所有网络请求已完成

        Returns:
            { ok: bool, pending: int, completed: int }
        """
        self._inject_helpers()
        pending = self.get_pending_requests()
        return {
            'ok': pending == 0,
            'pending': pending
        }

    def _guard_health(self, operation: str = ''):
        """
        轻量级健康守卫 — 在关键操作前调用。
        仅检查已记录的错误（不发起额外 evaluate 调用）。
        """
        if getattr(self, '_page_crashed', False):
            self._record_op('guard_health', operation, time.time(),
                            result='blocked_health', error='Page crashed')
            from test_helpers.error_collector import PageHealthError
            raise PageHealthError(
                f"Page has crashed. Operation '{operation}' aborted.",
                {'crashed': True}
            )
        page_errors = getattr(self, '_page_errors', [])
        if page_errors:
            err_msgs = [e.get('message', '')[:120] for e in page_errors[-3:]]
            self._record_op('guard_health', operation, time.time(),
                            result='blocked_health', error=err_msgs[0] if err_msgs else '')
            from test_helpers.error_collector import PageHealthError
            raise PageHealthError(
                f"Page has {len(page_errors)} uncaught JS error(s). "
                f"Operation '{operation}' aborted. Recent: {'; '.join(err_msgs)}",
                {'page_errors': page_errors}
            )

    def click(
        self,
        selector: str,
        timeout: int = 5000,
        wait_after: int = 300
    ) -> bool:
        """
        点击元素

        Args:
            selector: CSS 选择器
            timeout: 超时时间
            wait_after: 点击后等待时间 (ms)

        Returns:
            是否成功
        """
        t0 = time.time()
        try:
            self._guard_health(f'click({selector})')
        except Exception:
            self._record_op('click', selector, t0, result='blocked_health',
                            error='PageHealthError')
            raise
        page = self._ensure_browser()
        try:
            page.wait_for_selector(selector, timeout=timeout, state="visible")
            page.click(selector)
            if wait_after > 0:
                page.wait_for_timeout(wait_after)
            self._record_op('click', selector, t0)
            return True
        except Exception as e:
            self._record_op('click', selector, t0, result='fail', error=str(e)[:120])
            print(f"[ERROR] Click failed: {selector} - {e}")
            return False

    def fill(
        self,
        selector: str,
        value: str,
        timeout: int = 5000,
        press_enter: bool = False
    ) -> bool:
        """
        填写表单字段

        Args:
            selector: CSS 选择器
            value: 填写值
            timeout: 超时时间
            press_enter: 填写后是否按 Enter

        Returns:
            是否成功
        """
        t0 = time.time()
        try:
            self._guard_health(f'fill({selector})')
        except Exception:
            self._record_op('fill', selector, t0, result='blocked_health',
                            error='PageHealthError')
            raise
        page = self._ensure_browser()
        try:
            page.wait_for_selector(selector, timeout=timeout, state="visible")
            page.fill(selector, value)
            if press_enter:
                page.press(selector, "Enter")
            self._record_op('fill', selector, t0)
            return True
        except Exception as e:
            self._record_op('fill', selector, t0, result='fail', error=str(e)[:120])
            print(f"[ERROR] Fill failed: {selector} - {e}")
            return False

    def select(
        self,
        selector: str,
        value: str = None,
        label: str = None,
        timeout: int = 5000
    ) -> bool:
        """
        选择下拉选项

        Args:
            selector: select 元素选择器
            value: 选项的值
            label: 选项的显示文本
            timeout: 超时时间

        Returns:
            是否成功
        """
        t0 = time.time()
        try:
            self._guard_health(f'select({selector})')
        except Exception:
            self._record_op('select', selector, t0, result='blocked_health',
                            error='PageHealthError')
            raise
        page = self._ensure_browser()
        try:
            page.wait_for_selector(selector, timeout=timeout, state="visible")
            if value:
                page.select_option(selector, value=value)
            elif label:
                page.select_option(selector, label=label)
            self._record_op('select', selector, t0)
            return True
        except Exception as e:
            self._record_op('select', selector, t0, result='fail', error=str(e)[:120])
            print(f"[ERROR] Select failed: {selector} - {e}")
            return False

    def hover(self, selector: str, timeout: int = 5000) -> bool:
        """鼠标悬停"""
        page = self._ensure_browser()
        try:
            page.wait_for_selector(selector, timeout=timeout, state="visible")
            page.hover(selector)
            return True
        except Exception as e:
            print(f"[ERROR] Hover failed: {selector} - {e}")
            return False

    def is_visible(self, selector: str, timeout: int = 3000) -> bool:
        """检查元素是否可见"""
        page = self._ensure_browser()
        try:
            page.wait_for_selector(selector, timeout=timeout, state="visible")
            return True
        except Exception:
            return False

    def wait_for_selector(
        self,
        selector: str,
        timeout: int = 10000,
        state: str = "visible"
    ) -> bool:
        """
        等待元素出现或消失

        Args:
            selector: CSS 选择器
            timeout: 超时时间
            state: 等待状态 (visible/hidden/attached/detached)

        Returns:
            是否成功
        """
        page = self._ensure_browser()
        try:
            page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception:
            return False

    def wait_for_function(
        self,
        script: str,
        *args,
        timeout: int = 10000,
        polling: int = 100
    ) -> bool:
        """
        等待 JS 函数返回 true

        Args:
            script: JS 代码（应返回 boolean）
            *args: 传递给函数的参数
            timeout: 超时时间
            polling: 轮询间隔 (ms)

        Returns:
            函数是否返回 true
        """
        page = self._ensure_browser()
        try:
            page.wait_for_function(script, *args, timeout=timeout, polling=polling)
            return True
        except Exception:
            return False

    def wait_for_navigation(
        self,
        timeout: int = 15000,
        wait_until: str = "domcontentloaded"
    ) -> bool:
        """等待导航完成"""
        page = self._ensure_browser()
        try:
            page.wait_for_load_state(wait_until, timeout=timeout)
            return True
        except Exception:
            return False

    def wait_for_timeout(self, ms: int):
        """等待指定毫秒"""
        page = self._ensure_browser()
        page.wait_for_timeout(ms)

    def get_text(self, selector: str, timeout: int = 5000) -> str:
        """获取元素的文本内容"""
        page = self._ensure_browser()
        try:
            page.wait_for_selector(selector, timeout=timeout, state="visible")
            return page.locator(selector).text_content()
        except Exception:
            return ""

    def get_attribute(
        self,
        selector: str,
        attribute: str,
        timeout: int = 5000
    ) -> str:
        """获取元素的属性值"""
        page = self._ensure_browser()
        try:
            page.wait_for_selector(selector, timeout=timeout, state="visible")
            return page.get_attribute(selector, attribute)
        except Exception:
            return ""

    def reload(self):
        """刷新页面"""
        page = self._ensure_browser()
        page.reload(wait_until="domcontentloaded", timeout=self.NAVIGATION_TIMEOUT)

    def go_back(self):
        """后退"""
        page = self._ensure_browser()
        page.go_back(wait_until="domcontentloaded", timeout=self.NAVIGATION_TIMEOUT)

    def get_console_logs(self) -> List[str]:
        """获取控制台日志"""
        page = self._ensure_browser()
        return page.evaluate("() => window.__consoleLogs || []")

    def force_refresh_api(self, store_name: str = "boCrud") -> Any:
        """
        强制刷新 Pinia store 的 API 数据

        Args:
            store_name: store 名称

        Returns:
            API 调用结果
        """
        return self.evaluate(f"""
            () => {{
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                const store = pinia._s.get('{store_name}')
                if (store && store.fetchData) {{
                    return store.fetchData({{ forceRefresh: true }})
                }}
                return null
            }}
        """)

    def new_context(self):
        """创建新的浏览器上下文（隔离的 session）"""
        if self._browser is None:
            self._start_browser()
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._cookies_set = False
        return self._context

    def get_error_collector(self):
        """
        Get unified error collector aggregating errors from all layers.

        Returns:
            ErrorCollector instance
        """
        from test_helpers.error_collector import ErrorCollector

        collector = ErrorCollector()

        for err in getattr(self, '_page_errors', []):
            collector.add_page_error(err.get('message', ''))

        for err in getattr(self, '_console_errors', []):
            if err.get('level') == 'error':
                collector.add_console_error(err.get('text', ''))
            else:
                collector.add_console_warning(err.get('text', ''))

        try:
            vue_errors = self.evaluate("() => window.__appErrors || []")
            for ve in (vue_errors or []):
                collector.add_vue_error(
                    ve.get('message', ''),
                    ve.get('component', '')
                )
        except Exception:
            pass

        try:
            js_errors = self.evaluate("() => window.__consoleErrors || []")
            for je in (js_errors or []):
                collector.add_console_error(je.get('message', ''))
        except Exception:
            pass

        try:
            js_warns = self.evaluate("() => window.__consoleWarnings || []")
            for jw in (js_warns or []):
                collector.add_console_warning(jw.get('message', ''))
        except Exception:
            pass

        return collector

    def check_health(self) -> dict:
        """
        Fast health check before any operation.

        Returns:
            { healthy: bool, summary: str, details: dict }
        """
        collector = self.get_error_collector()

        if getattr(self, '_page_crashed', False):
            collector.add_health_failure('Page has crashed')

        try:
            has_app = self.evaluate("() => !!document.querySelector('#app')")
            if not has_app:
                collector.add_health_failure("Vue app root element (#app) not found in DOM")
        except Exception as e:
            collector.add_health_failure(f"Cannot evaluate page: {e}")

        return {
            'healthy': collector.is_healthy(),
            'summary': collector.summary(),
            'details': collector.to_dict()
        }

    def assert_healthy(self):
        """
        Assert page is healthy. Raises PageHealthError if unhealthy.

        Raises:
            PageHealthError: Page has fatal errors
        """
        health = self.check_health()
        if not health['healthy']:
            from test_helpers.error_collector import PageHealthError
            raise PageHealthError(health['summary'], health['details'])

    def close(self):
        """关闭浏览器"""
        if self.telemetry:
            try:
                health = self.check_health()
                result = 'pass' if health['healthy'] else 'fail'
            except Exception:
                result = 'error'
            self.telemetry.finalize(result=result)
            self.telemetry.flush_to_disk()
        self._closed = True
        self._cleanup()

    def _cleanup(self):
        """内部清理（atexit 安全）"""
        if self._page and not self._page.is_closed():
            try:
                self._page.close()
            except Exception:
                pass

        if self._context:
            try:
                self._context.close()
            except Exception:
                pass

        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._cookies_set = False

    # ============================================================
    # Element Plus Teleport 下拉框专用辅助方法
    # ============================================================
    # Element Plus 的 el-select / el-dropdown / el-cascader 等组件
    # 通过 Vue 3 的 Teleport 把下拉项渲染到 <body>，经常被 modal
    # 遮罩挡住，导致 Playwright 截图和断言失败。
    # 以下方法封装了"打开下拉 → 提取 → 验证 → 截图"的完整流程。

    def _find_popper_for(self, anchor_selector: str) -> Optional[dict]:
        """
        在页面上找到与 anchor 选择器关联的、当前可见的 el-popper

        策略:
          1. 点击 anchor 触发 Teleport 内容
          2. 在 body 下找到所有 .el-popper
          3. 返回有可见项、且 ID 与 anchor 不冲突的那一个

        Returns:
            { html, options, count, dropdown_idx } or None
        """
        page = self._ensure_browser()
        return page.evaluate("""
            (anchorSelector) => {
                const anchors = document.querySelectorAll(anchorSelector);
                if (anchors.length === 0) return { error: 'anchor not found: ' + anchorSelector };
                const anchor = anchors[0];

                // 触发点击以展开下拉
                anchor.click();
                // 等待下一个 tick 让 Teleport 完成
                return new Promise(resolve => {
                    setTimeout(() => {
                        const poppers = document.querySelectorAll('body .el-popper, body .el-select-dropdown, body .el-dropdown-menu');
                        let best = null;
                        let bestCount = 0;
                        for (let i = 0; i < poppers.length; i++) {
                            const p = poppers[i];
                            const rect = p.getBoundingClientRect();
                            const style = window.getComputedStyle(p);
                            const items = p.querySelectorAll('.el-select-dropdown__item, .el-dropdown-menu__item, .el-popper__item');
                            // 优先选择有可见 item、且 rect 有效 (h > 0) 的 popper
                            if (items.length > bestCount) {
                                bestCount = items.length;
                                best = { popper: p, idx: i, items, style, rect };
                            }
                        }
                        if (!best) resolve({ error: 'no popper with items found' });
                        else {
                            const optionTexts = Array.from(best.items).map(it => ({
                                text: it.textContent.trim(),
                                unicode: Array.from(it.textContent.trim()).map(c => 'U+' + c.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0')).join(' '),
                                isEmoji: /[\\u{1F300}-\\u{1FAFF}]|[\\u{2600}-\\u{27BF}]|[WARNING]|[ALERT]|ℹ|[DECORATIVE]/u.test(it.textContent)
                            }));
                            resolve({
                                ok: true,
                                count: best.items.length,
                                html: best.popper.outerHTML,
                                rect: { x: best.rect.x, y: best.rect.y, w: best.rect.width, h: best.rect.height },
                                zIndex: best.style.zIndex,
                                display: best.style.display,
                                visibility: best.style.visibility,
                                options: optionTexts
                            });
                        }
                    }, 600);
                });
            }
        """, anchor_selector)

    def open_dropdown(self, anchor_selector: str, wait_ms: int = 800) -> dict:
        """
        打开一个 el-select 下拉框并返回其状态

        智能处理：
        - 如果下拉已经打开，不重复点击（避免关闭）
        - 点击触发的是 mousedown/mouseup/click，目标是 .el-select__wrapper
        - 找最近的 popper（基于与 anchor 的距离 + 尺寸）

        Args:
            anchor_selector: 触发下拉的元素选择器
                - 简单 CSS: '.my-select'
                - text= 或 label= 前缀（见 _resolve_selector）
            wait_ms: 等待 popper 渲染时间

        Returns:
            { ok, count, options, rect, zIndex, html }
        """
        page = self._ensure_browser()
        resolved_selector = self._resolve_selector(anchor_selector)

        return page.evaluate("""
            async ({selector, waitMs}) => {
                // 兼容 CSS 和 XPath
                let anchor = null;
                if (selector.startsWith('xpath=')) {
                    const xp = selector.slice(6);
                    const result = document.evaluate(xp, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    anchor = result.singleNodeValue;
                } else {
                    anchor = document.querySelector(selector);
                }
                if (!anchor) return { ok: false, error: 'anchor not found: ' + selector };

                // Element Plus 的 el-select 实际点击目标不是 .el-select 本身，
                // 而是内部 .el-select__wrapper，需要派发 mousedown
                const wrapper = anchor.querySelector('.el-select__wrapper')
                    || anchor.querySelector('.el-select__input-wrapper')
                    || anchor.querySelector('input')
                    || anchor;

                // 1. 获取 wrapper 位置
                const anchorRect = wrapper.getBoundingClientRect();
                const anchorX = anchorRect.x + anchorRect.width / 2;
                const anchorY = anchorRect.y + anchorRect.height / 2;

                // 2. 智能检测：先看是否已经有匹配的 popper
                const findBestPopper = () => {
                    const poppers = document.querySelectorAll('body .el-select-dropdown, body .el-dropdown-menu, body .el-popper');
                    let best = null;
                    let bestScore = -Infinity;
                    for (const p of poppers) {
                        const items = p.querySelectorAll('.el-select-dropdown__item, .el-dropdown-menu__item, .el-popper__item');
                        if (items.length === 0) continue;
                        const rect = p.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        const popX = rect.x + rect.width / 2;
                        const popY = rect.y + rect.height / 2;
                        const dist = Math.sqrt((popX - anchorX) ** 2 + (popY - anchorY) ** 2);
                        const score = -dist + items.length * 0.001;
                        if (score > bestScore) {
                            bestScore = score;
                            best = p;
                        }
                    }
                    return best;
                };

                let best = findBestPopper();
                if (best) {
                    // 已经打开了，直接返回
                    await new Promise(r => setTimeout(r, 100));
                } else {
                    // 没打开，触发点击
                    wrapper.scrollIntoView({ block: 'center', inline: 'center' });
                    await new Promise(r => setTimeout(r, 100));
                    const mousedown = new MouseEvent('mousedown', { bubbles: true, button: 0, cancelable: true, view: window });
                    const mouseup = new MouseEvent('mouseup', { bubbles: true, button: 0, cancelable: true, view: window });
                    const click = new MouseEvent('click', { bubbles: true, button: 0, cancelable: true, view: window });
                    wrapper.dispatchEvent(mousedown);
                    wrapper.dispatchEvent(mouseup);
                    wrapper.dispatchEvent(click);
                    await new Promise(r => setTimeout(r, waitMs));
                    best = findBestPopper();
                }

                if (!best) return { ok: false, error: 'no visible popper near anchor found' };

                const rect = best.getBoundingClientRect();
                const style = window.getComputedStyle(best);
                const items = best.querySelectorAll('.el-select-dropdown__item, .el-dropdown-menu__item, .el-popper__item');
                return {
                    ok: true,
                    count: items.length,
                    html: best.outerHTML,
                    rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                    zIndex: style.zIndex,
                    display: style.display,
                    visibility: style.visibility,
                    options: Array.from(items).map(it => {
                        const text = it.textContent.trim();
                        return {
                            text,
                            unicode: Array.from(text).map(c => 'U+' + c.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0')).join(' '),
                            isEmoji: /[\\u{1F300}-\\u{1FAFF}]|[\\u{2600}-\\u{27BF}]|[WARNING]|[ALERT]|ℹ|[DECORATIVE]/u.test(text)
                        };
                    })
                };
            }
        """, {"selector": resolved_selector, "waitMs": wait_ms})

    @staticmethod
    def _resolve_selector(selector: str) -> Optional[str]:
        """
        解析 selector 字符串，支持多种格式

        例子:
          ".el-select"               → ".el-select"  (CSS)
          "text=重要"                 → xpath 查找包含文本的 .el-select
          "label=分类"                → 找 form-item 标签为指定值的 el-select
          "xpath=..."                 → 直接 xpath
        """
        if selector.startswith("xpath="):
            return selector
        if selector.startswith("text="):
            text = selector[5:].strip()
            return f"xpath=//div[contains(@class, 'el-select') and contains(., '{text}')][1]"
        if selector.startswith("label="):
            label = selector[6:].strip()
            return f"xpath=//*[contains(@class, 'el-form-item') and .//*[contains(@class, 'el-form-item__label') and normalize-space(text())='{label}']]//*[contains(@class, 'el-select')][1]"
        return selector

    def extract_dropdown_html(self, anchor_selector: str, wait_ms: int = 800) -> Optional[str]:
        """
        打开下拉并返回其 outerHTML（用于离线渲染截图）

        Args:
            anchor_selector: el-select 选择器
            wait_ms: 等待渲染时间

        Returns:
            HTML 字符串或 None
        """
        result = self.open_dropdown(anchor_selector, wait_ms)
        return result.get("html") if result.get("ok") else None

    def assert_visible(self, selector_or_handle, screenshot_path: str = None, **kwargs) -> dict:
        """
        【可测试性铁律】断言一个元素在视觉上真的可见

        这是替代"DOM 存在即 OK"错误判定的核心方法。
        它会同时检查：
          1. 元素存在于 DOM
          2. 元素有实际尺寸 (rect.width > 0 && rect.height > 0)
          3. 元素未被 CSS 隐藏 (display/visibility/opacity)
          4. 元素在视口内 (rect 在 viewport 内)
          5. 元素未被遮挡 (elementFromPoint 中心点 = 元素本身)
          6. 元素在最上层 (z-index 有效 + 非 popper 容器内)

        Args:
            selector_or_handle: CSS selector 字符串 / Locator / ElementHandle
            screenshot_path: 可选，失败时自动截图保存到此路径

        Returns:
            {
              ok: bool,           # 全部检查通过
              checks: {           # 每项检查的明细
                exists: bool,
                sized: bool,
                notHidden: bool,
                inViewport: bool,
                notObscured: bool,
                onTop: bool
              },
              rect: {x,y,w,h},
              zIndex: str,
              topElement: str,    # elementFromPoint 拿到的最上层元素
              reason: str         # 失败原因
            }

        Usage:
            result = cli.assert_visible('.el-select-dropdown', 'd:/test.png')
            assert result['ok'], f"下拉框视觉不可见: {result['reason']}"
        """
        page = self._ensure_browser()

        if isinstance(selector_or_handle, str):
            handle_or_sel = selector_or_handle
        else:
            handle_or_sel = selector_or_handle

        result = page.evaluate("""
            (sel) => {
                // 兼容 selector 字符串
                let el;
                if (typeof sel === 'string') {
                    el = document.querySelector(sel);
                } else {
                    el = sel;
                }
                if (!el) return { exists: false };

                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);

                const checks = {
                    exists: true,
                    sized: rect.width > 0 && rect.height > 0,
                    notHidden: (
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        parseFloat(style.opacity) > 0.01
                    ),
                    inViewport: (
                        rect.x >= 0 && rect.y >= 0 &&
                        rect.x + rect.width <= window.innerWidth &&
                        rect.y + rect.height <= window.innerHeight &&
                        rect.width > 0 && rect.height > 0
                    ),
                    notObscured: false,
                    onTop: parseInt(style.zIndex || '0', 10) > 0 || style.position === 'fixed'
                };

                // 检查遮挡
                let topElement = null;
                if (checks.inViewport && checks.sized) {
                    const cx = rect.x + rect.width / 2;
                    const cy = rect.y + rect.height / 2;
                    topElement = document.elementFromPoint(cx, cy);
                    if (topElement) {
                        checks.notObscured = el.contains(topElement) ||
                                             topElement === el ||
                                             (topElement.closest && topElement.closest('.el-select-dropdown, .el-popper, .el-tooltip__popper, .el-message-box') === el);
                    }
                }

                return {
                    exists: checks.exists,
                    sized: checks.sized,
                    notHidden: checks.notHidden,
                    inViewport: checks.inViewport,
                    notObscured: checks.notObscured,
                    onTop: checks.onTop,
                    rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
                    zIndex: style.zIndex,
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity,
                    position: style.position,
                    topElement: topElement ? `${topElement.tagName}.${String(topElement.className).slice(0, 80)}` : null,
                    ok: checks.sized && checks.notHidden && checks.inViewport && checks.notObscured
                };
            }
        """, handle_or_sel)

        # 计算 ok 状态
        if not result.get('exists'):
            result['ok'] = False
            result['reason'] = 'element not found in DOM'
        elif not result.get('sized'):
            result['ok'] = False
            result['reason'] = f'element has zero size: {result.get("rect")}'
        elif not result.get('notHidden'):
            result['ok'] = False
            result['reason'] = f'element hidden: display={result.get("display")}, visibility={result.get("visibility")}, opacity={result.get("opacity")}'
        elif not result.get('inViewport'):
            result['ok'] = False
            result['reason'] = f'element off-screen: {result.get("rect")}'
        elif not result.get('notObscured'):
            result['ok'] = False
            result['reason'] = f'element obscured by: {result.get("topElement")}'
        else:
            result['ok'] = True
            result['reason'] = 'all visual checks passed'

        # 失败时自动截图
        if not result['ok'] and screenshot_path:
            try:
                page.screenshot(path=screenshot_path, full_page=True)
                result['screenshot'] = screenshot_path
            except Exception as e:
                result['screenshot_error'] = str(e)

        return result

    def assert_visual_contains(self, text: str, screenshot_path: str = None) -> dict:
        """
        断言一段文本在视觉上真的可见（不是只在 DOM 里）

        Args:
            text: 要查找的文本
            screenshot_path: 失败时截图路径

        Returns:
            { ok, found_count, visible_count, ... }
        """
        page = self._ensure_browser()

        result = page.evaluate("""
            (searchText) => {
                const all = document.querySelectorAll('*');
                let foundCount = 0;
                let visibleCount = 0;
                const visibleInstances = [];
                for (const el of all) {
                    const txt = (el.textContent || '').trim();
                    if (el.children.length === 0 && txt === searchText) {
                        foundCount++;
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        if (rect.width > 0 && rect.height > 0 &&
                            style.display !== 'none' && style.visibility !== 'hidden' &&
                            rect.x >= 0 && rect.y >= 0 &&
                            rect.x + rect.width <= innerWidth && rect.y + rect.height <= innerHeight) {
                            visibleCount++;
                            visibleInstances.push({
                                tag: el.tagName,
                                class: String(el.className).slice(0, 60),
                                rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                            });
                        }
                    }
                }
                return { foundCount, visibleCount, visibleInstances };
            }
        """, text)

        result['ok'] = result.get('visibleCount', 0) > 0
        result['reason'] = (
            f'found {result.get("foundCount", 0)} in DOM, {result.get("visibleCount", 0)} visually visible'
        )

        if not result['ok'] and screenshot_path:
            try:
                page.screenshot(path=screenshot_path, full_page=True)
                result['screenshot'] = screenshot_path
            except Exception as e:
                result['screenshot_error'] = str(e)

        return result

    def get_dropdown_options(self, anchor_selector: str, wait_ms: int = 800) -> list:
        """
        打开下拉并返回选项文本列表

        Args:
            anchor_selector: el-select 选择器
            wait_ms: 等待渲染时间

        Returns:
            ["重要", "警告", "信息", "提示", ...]
        """
        result = self.open_dropdown(anchor_selector, wait_ms)
        if not result.get("ok"):
            return []
        return [opt["text"] for opt in result.get("options", [])]

    def verify_no_emoji(self, anchor_selector: str, expected: list = None) -> dict:
        """
        一站式验证下拉框内容（中文/无 emoji）

        Args:
            anchor_selector: el-select 选择器
            expected: 期望的文本列表 (可选，用于比对)

        Returns:
            {
                ok: bool,
                options: [str],
                hasEmoji: bool,
                missing: [str] (expected 中未出现)
            }
        """
        result = self.open_dropdown(anchor_selector)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error", "unknown")}

        options = [opt["text"] for opt in result["options"]]
        has_emoji = any(opt["isEmoji"] for opt in result["options"])
        missing = []
        if expected:
            missing = [e for e in expected if e not in options]

        return {
            "ok": (not has_emoji) and (not missing),
            "options": options,
            "hasEmoji": has_emoji,
            "missing": missing,
            "raw": result
        }

    def screenshot_dropdown(
        self,
        anchor_selector: str,
        save_path: str,
        include_extract_html: bool = True,
        wait_ms: int = 800
    ) -> dict:
        """
        打开下拉框并截图

        关键：Element Plus 的 Teleport + modal 遮罩 导致下拉被遮，
        本方法会先关闭 modal overlay (如果存在)，把 popper 移到视口中央
        再截图，保证 dropdown 内容清晰可见。

        Args:
            anchor_selector: 触发下拉的元素
            save_path: 截图保存路径
            include_extract_html: 是否同时生成 standalone HTML
            wait_ms: 等待 popper 渲染时间

        Returns:
            { ok, count, screenshot_path, html_path? }
        """
        page = self._ensure_browser()
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

        # 1. 打开下拉
        resolved = self._resolve_selector(anchor_selector)
        result = self.open_dropdown(anchor_selector, wait_ms=wait_ms)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error")}

        # 2. 移动 popper 到视口中央（绕过 modal 遮罩）
        # 只移动"目标 popper"，隐藏其他 popper
        page.evaluate("""
            (result) => {
                // 1. 隐藏所有 popper
                const allPoppers = document.querySelectorAll('body .el-select-dropdown, body .el-dropdown-menu, body .el-popper');
                allPoppers.forEach(p => {
                    p.style.display = 'none';
                    p.style.visibility = 'hidden';
                });

                // 2. 找到目标 popper (根据 result.html 的开头内容匹配)
                // 用 textContent 比较
                const targetItems = result.options.map(o => o.text);
                for (const p of allPoppers) {
                    const items = p.querySelectorAll('.el-select-dropdown__item, .el-dropdown-menu__item, .el-popper__item');
                    const texts = Array.from(items).map(i => i.textContent.trim());
                    const matches = targetItems.every(t => texts.includes(t)) && texts.length === targetItems.length;
                    if (matches) {
                        p.style.cssText = `
                            position: fixed !important;
                            top: 200px !important;
                            left: 500px !important;
                            z-index: 99999 !important;
                            display: block !important;
                            visibility: visible !important;
                            background: white !important;
                            border: 2px solid #333 !important;
                            box-shadow: 0 4px 16px rgba(0,0,0,0.3) !important;
                            min-width: 220px !important;
                        `;
                        items.forEach(item => {
                            item.style.cssText = 'padding: 12px 16px !important; font-size: 14px !important; display: block !important;';
                        });
                    }
                }

                // 3. 隐藏 modal overlay
                const overlays = document.querySelectorAll('.el-overlay, .el-overlay-dialog, .app-modal__wrapper');
                overlays.forEach(o => o.style.display = 'none');
            }
        """, result)
        page.wait_for_timeout(500)
        page.screenshot(path=save_path, full_page=True)

        ret = {
            "ok": True,
            "count": result["count"],
            "screenshot_path": save_path,
            "options": [opt["text"] for opt in result["options"]]
        }

        # 3. 可选：生成 standalone HTML
        if include_extract_html and result.get("html"):
            html_path = save_path.rsplit(".", 1)[0] + "_extracted.html"
            standalone = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
  .frame {{ display: inline-block; background: white; padding: 16px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  h2 {{ color: #333; margin-top: 0; }}
</style>
</head>
<body>
  <div class="frame">
    <h2>Element Plus 下拉框实际渲染内容（从浏览器实时提取）</h2>
    {result["html"]}
  </div>
</body>
</html>"""
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(standalone)
            ret["html_path"] = html_path

        return ret

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        try:
            self._cleanup()
        except Exception:
            pass


def run_script(script_path: str, *args) -> dict:
    """
    运行测试脚本的便捷函数

    Args:
        script_path: 脚本路径
        *args: 传递给脚本的参数

    Returns:
        执行结果
    """
    import runpy

    # 设置工作目录
    old_cwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(script_path)))

    try:
        result = runpy.run_path(script_path, globals(), run_name="__main__")
        return result.get("results", {})
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    # 简单测试
    print("[INFO] PlaywrightCLI 初始化测试...")

    with PlaywrightCLI() as cli:
        # 测试 dev-login
        print("[1/3] 测试 dev-login...")
        if cli.dev_login():
            print("[OK] dev-login 成功")
        else:
            print("[FAIL] dev-login 失败")

        # 测试 goto
        print("[2/3] 测试页面导航...")
        try:
            cli.goto("http://localhost:3004/")
            print("[OK] 页面加载成功")
        except Exception as e:
            print(f"[FAIL] 页面加载失败: {e}")

        # 测试截图
        print("[3/3] 测试截图...")
        try:
            path = cli.screenshot("test_cli_screenshot.png")
            print(f"[OK] 截图保存到: {path}")
        except Exception as e:
            print(f"[FAIL] 截图失败: {e}")

    print("[INFO] 测试完成")
