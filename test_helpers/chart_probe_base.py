"""
chart_probe_base.py - 图表"可见性/展开层级"浏览器探针共享骨架 (P0-3 2026-09-03)

沉淀自 probe_legend_v10 的排查教训:
  1. 确定性操作: 用 debug API (setExpandLevel/setGroupVisible) 而非依赖 DOM 点击时序;
     仅验证"真实 UI 入口"时保留 DOM 交互 (如 legend 点击), 包成方法复用.
  2. 事件驱动稳态: wait_until_snapshot 轮询 visibilitySnapshot 至断言成立, 禁用固定 sleep
     构造"竞态窗口" (2026-09-03 v11 假失败根因之一).
  3. 统一断言层: 一律消费 debug.visibilitySnapshot() 四层快照
     (store / chartConfig 面板树 / svg displayNone / collectHiddenState 分类),
     避免探针各自拼装导致"拿错层断言" (2026-09-03 v11 假失败直接根因).

前置: dev server (默认 http://localhost:3005) + 后端认证可达 + ?mode=debug 挂载 __archPage.debug.
用法:
    from test_helpers.chart_probe_base import ChartProbe
    with ChartProbe() as probe:
        probe.wait_chart_ready()
        s = probe.snapshot()
        probe.wait_until_snapshot(lambda s: 'SNC' not in s['storeUserHidden'], 'SNC 恢复可见')
"""
import sys, json, time
sys.path.insert(0, r'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FE = 'http://localhost:3005'
CHART_URL = (f'{FE}/system/archdata'
             '?productId=507&versionId=863&mode=debug&scopeCode=SCP&view=chart')

# 图例可点击项名: 探针以文本命中图例项 (真实 UI 入口, 非 debug API)
LEGEND_NAME = '✎供应网络'


class ChartProbe:
    def __init__(self, fe=FE, chart_url=CHART_URL, headless=True, login_user='admin'):
        self.fe = fe
        self.chart_url = chart_url
        self.headless = headless
        self.login_user = login_user
        self.cli = None

    # ---------- 生命周期 ----------
    def __enter__(self):
        self.cli = PlaywrightCLI(headless=self.headless).__enter__()
        return self

    def __exit__(self, *exc):
        return self.cli.__exit__(*exc)

    def js(self, code, arg=None):
        return self.cli._page.evaluate(code, arg) if arg is not None else self.cli._page.evaluate(code)

    # ---------- 登录 + 直达图表 ----------
    def login_and_open(self, wait_chart=True):
        page = self.cli._ensure_browser()
        page.goto(f'{self.fe}/api/v1/auth/dev-login?username={self.login_user}',
                  wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(800)
        page.goto(self.chart_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(15000)  # 首次数据加载/渲染预算
        if wait_chart:
            return self.wait_chart_ready()
        return page

    # ---------- 图表就绪 ----------
    def wait_chart_ready(self, attempts=40, interval_ms=1000):
        for _ in range(attempts):
            v = self.js("""() => ({ mc: document.querySelectorAll('.mermaid-container').length,
                                      node: document.querySelectorAll('g.node').length })""")
            if v.get('mc', 0) > 0 and v.get('node', 0) > 5:
                print('READY:', json.dumps(v))
                return v
            time.sleep(interval_ms / 1000)
        raise RuntimeError('chart not ready')

    # ---------- 统一快照: 四层一次读取 ----------
    def snapshot(self):
        """等价 __archPage.debug.visibilitySnapshot(): store/chart/svg/hiddenMeta + userHidden."""
        s = self.js("""() => {
          const d = window.__archPage?.debug
          if (!d || typeof d.visibilitySnapshot !== 'function') {
            return { __error: 'debug.visibilitySnapshot missing - 需含 P0-2 的前端构建/热更' }
          }
          return d.visibilitySnapshot()
        }""")
        if '__error' in s:
            raise RuntimeError(s['__error'])
        return s

    # ---------- 事件驱动稳态等待 (替代固定 sleep) ----------
    def wait_until_snapshot(self, cond, desc='condition', timeout_s=25, interval_s=0.5):
        """轮询 snapshot 直到 cond(snapshot) 为真; 超时抛出带末次快照摘要的异常."""
        deadline = time.time() + timeout_s
        last = None
        while time.time() < deadline:
            last = self.snapshot()
            try:
                if cond(last):
                    return last
            except Exception as e:  # 断言函数自身异常视为未满足
                last = {'__cond_err': str(e)}
            time.sleep(interval_s)
        raise AssertionError(f'wait_until_snapshot timeout: {desc}\nlast={json.dumps(last, ensure_ascii=False)[:2000]}')

    # ---------- 确定性 debug 操作 ----------
    def set_expand_level(self, lvl, wait_cond=None, timeout_s=25):
        self.js("""async (lvl) => { const d = window.__archPage?.debug
          ; return d && d.setExpandLevel ? await d.setExpandLevel(lvl) : { err: 'no api' } }""", lvl)
        if wait_cond is not None:
            return self.wait_until_snapshot(wait_cond, f'expandLevel={lvl}', timeout_s)

    def set_group_visible(self, code, visible):
        return self.js("""(c, v) => { const d = window.__archPage?.debug
          ; return d && d.setGroupVisible ? d.setGroupVisible(c, v) : { err: 'no api' } }""", (code, visible))

    # ---------- 真实 UI 入口: 图例点击隐藏 (返回是否命中) ----------
    def legend_click(self, name=LEGEND_NAME):
        r = self.js("""(name) => {
          const cands = Array.from(document.querySelectorAll('.color-legend-panel div'))
            .filter(d => getComputedStyle(d).cursor === 'pointer')
          const norm = (t) => (t || '').trim().replace(/^✎/, '')
          const t = cands.find(d => norm(d.textContent) === norm(name))
          if (!t) return { ok: false, items: cands.map(d => norm(d.textContent)).slice(0, 30) }
          t.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
          return { ok: true }
        }""", name)
        if not r.get('ok'):
            raise AssertionError('legend item not found: ' + json.dumps(r, ensure_ascii=False)[:500])
        return r

    # ---------- 便捷筛选 (语义与 visibilitySnapshot 的 elkAuto 判定一致) ----------
    @staticmethod
    def items_by_code(snap, layer, code):
        """layer ∈ {'store','chart'}; 返回该层匹配 code 的扁平项 (含 elkAuto/visible 等)."""
        items = (snap.get(layer) or {}).get('items', []) if snap.get(layer) else []
        return [i for i in items if i.get('code') == code]

    @staticmethod
    def user_hidden_codes(snap, layer='store'):
        return list(snap.get(layer + 'UserHidden') or []) if snap.get(layer) else None

    @staticmethod
    def svg_display_none_codes(snap):
        return [d.get('code') for d in (snap.get('svg') or {}).get('displayNone', []) if d.get('code')]


# 简易断言收集器 (迁移自 probe_legend_v10 的 PASS/FAIL 打印)
class CheckCollector:
    def __init__(self):
        self.results = []

    def add(self, name, ok, detail=''):
        self.results.append((name, bool(ok)))
        print(('PASS' if ok else 'FAIL') + ' | ' + name + (' | ' + detail if detail else ''))

    @property
    def all_pass(self):
        return all(ok for _, ok in self.results)

    def summary(self):
        passed = sum(1 for _, ok in self.results if ok)
        print(f'\nSUMMARY: {passed}/{len(self.results)} passed')
        print('RESULT: ' + ('ALL PASS' if self.all_pass else 'HAS FAILURES'))
        return self.all_pass


if __name__ == '__main__':
    with ChartProbe() as probe:
        probe.login_and_open()
        s = probe.snapshot()
        print('snapshot keys:', json.dumps(list(s.keys())))
        print('storeUserHidden:', json.dumps(probe.user_hidden_codes(s), ensure_ascii=False))
        print('svg displayNone:', json.dumps(probe.svg_display_none_codes(s), ensure_ascii=False))
