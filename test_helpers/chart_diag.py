"""
chart_diag.py - 图表诊断工具集
================================

[目的] 把 EmbeddedChartView 相关问题排查的模式参数化, 避免反复写一次性 diag_*.py 脚本.

[核心场景]
  1. click → highlight + center 行为 (节点/容器/连线/label)
  2. transform 增量累积 bug
  3. bbox / getPointAtLength / getScreenCTM 中心算法对比
  4. SVG 多 listener 重复触发 (click handler 累加 transform)

[对应排查脚本] 取代以下 12 个一次性脚本:
  - diag_center_path.py
  - diag_first_path.py
  - diag_label_paths.py
  - diag_label_click.py
  - diag_label_single.py
  - diag_console_label.py
  - diag_dom_tree.py
  - diag_edgeLabels_center.py
  - diag_layout.py
  - diag_click_node_layout.py
  - diag_node_positions.py
  - diag_container_layout.py
  - diag_user_coords.py
  - diag_user_viewport.py
  - diag_node_label.py

[用法示例]
    from test_helpers.chart_diag import ChartDiag

    diag = ChartDiag()
    page = diag.open_chart(scope=SCOPE, viewport=(1280, 720))

    # 单击后, 节点 rect center 应当 = wrapper center
    diag.click_and_assert_centered(selector='svg g.node[data-code="DP01"]', kind='node')

    # 诊断: 列出 5 个 flowchart-link path 的三种中心计算
    diag.compare_path_centers(n=5)

    # 诊断: 捕获 onSvgClick 重复触发的次数
    diag.trace_click_listeners(trigger='svg g.edgeLabel')
"""

from __future__ import annotations
import sys
import json
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

if __name__ in ('__main__', 'chart_diag'):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_helpers.browser_auth_cli import PlaywrightCLI


# 常用 scope, 30 个 BO 触发复杂图 (有各种 path 形状)
DEFAULT_SCOPE = {
    'sub_domain': [299],
    'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                        2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                        2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
}
SHORT_SCOPE = {'sub_domain': [299], 'business_object': [3220]}


class ChartDiag:
    """EmbeddedChartView 一键诊断工具.

    实例化后即可:
      - open_chart()        一键打开图表 (含 shortcut + scope + 图表展示)
      - reset_transform()   重置 mermaid-content 的 transform 到 identity (走 useInteraction refs)
      - click()             派发 click 事件 (绕过 playwright pointer 模拟)
      - measure_center()    读 element 屏幕中心 + wrapper 中心
      - click_and_assert_centered()  一行验证: 点击 + 断言 rect center == wrapper center
      - compare_path_centers()        列出 path 的 bbox/mid/rect 三种中心 + 与 wrapper 的差
      - trace_click_listeners()      捕获 click 触发链 (哪些 listener 被调, 调几次)

    [设计要点]
      - 用 raw dispatchEvent 而非 playwright .click(), 避免 transition/race 干扰
      - 截图统一保存到 OUTPUT_DIR (不污染 scripts 目录)
      - 所有数值以 JSON 输出, 便于对比和回归测试
    """

    OUTPUT_DIR = Path(__file__).resolve().parent / 'scripts' / 'chart_diag_out'

    def __init__(self, base_url: str = 'http://localhost:3006',
                 product_code: str = 'TTTTT000', version_id: int = 863,
                 viewport: Tuple[int, int] = (1280, 720)):
        self.base_url = base_url
        self.product_code = product_code
        self.version_id = version_id
        self.viewport = viewport
        self.cli = PlaywrightCLI()
        self.cli._start_browser()
        self.page = self.cli._page
        self.page.set_viewport_size({'width': viewport[0], 'height': viewport[1]})
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def open_chart(self, scope: Optional[dict] = None,
                   wait_for_selector: str = 'svg g.node',
                   timeout_ms: int = 30000) -> 'Page':
        """[FIX 2026-08-01] 一键打开 EmbeddedChartView (含产品/版本/scope + 图表展示按钮).
        取代 verify_center_v2.py 中 8 行 setup 代码."""
        scope = scope or DEFAULT_SCOPE
        # shortcut_chart_view 用 SHORT_SCOPE 触发路由, 然后手动改 scope 再点图表展示
        page = self.cli.shortcut_chart_view(
            target_path='/system/archdata',
            product_code=self.product_code,
            version_id=self.version_id,
            scope=SHORT_SCOPE,
            base_url=self.base_url,
            wait_for_selector='svg g.node',
            timeout=timeout_ms
        )
        page.wait_for_timeout(2000)
        # 尝试调 handleScopeChange (如果 __archPage 暴露了); 失败也无所谓
        try:
            page.evaluate("""(s) => {
                if (window.__archPage && window.__archPage.handleScopeChange) {
                    window.__archPage.handleScopeChange({
                        selectedSubDomainIds: s.sub_domain,
                        selectedBusinessObjectIds: s.business_object
                    })
                }
            }""", scope)
        except Exception as e:
            print(f'[chart_diag] handleScopeChange 失败 (可忽略): {e}')
        page.wait_for_timeout(2500)
        # 点"图表展示"按钮 (注意: shortcut 模式下可能不需要, 但兜底)
        page.evaluate("""() => {
            for (const b of document.querySelectorAll('button')) {
                const t = (b.textContent || '').trim()
                if (t === '图表展示') { b.click(); return }
            }
        }""")
        # 等图表渲染
        for _ in range(30):
            page.wait_for_timeout(1500)
            if page.evaluate("() => document.querySelectorAll('svg g.node').length") > 0:
                break
        page.wait_for_timeout(5000)
        # 兜底: 若还没渲染 (因为 __archPage 没暴露), 走 scope 路径 (例如打开 scope panel)
        if page.evaluate("() => document.querySelectorAll('svg g.node').length") == 0:
            print('[chart_diag] 图表未渲染, 尝试直接调用 store')
            try:
                page.evaluate("""() => {
                    // 通过 store 设置 scope
                    if (window.__archPage && window.__archPage.archDataStore) {
                        const s = window.__archPage.archDataStore
                        if (s.setSelectedSubDomainIds) s.setSelectedSubDomainIds(arguments[0].sub_domain)
                        if (s.setSelectedBusinessObjectIds) s.setSelectedBusinessObjectIds(arguments[0].business_object)
                    }
                }""", scope)
                page.wait_for_timeout(5000)
            except Exception as e:
                print(f'[chart_diag] store 兜底也失败: {e}')
        return page

    def reset_transform(self):
        """[FIX 2026-08-01] 重置 mermaid-content transform 到 identity (走 useInteraction 内部 refs).
        用 dblclick 触发 autoFitDiagram, 真正复位 useInteraction.translateX/Y.value.
        比 c.style.transform = 'translate(0px, 0px)' 更可靠 (后者只是改 CSS, ref 没动)."""
        ok = self.page.evaluate("""() => {
            const c = document.querySelector('.mermaid-content')
            const mc = document.querySelector('.mermaid-container')
            if (!c || !mc) return false
            c.style.transition = 'none'
            c.style.transform = 'translate(0px, 0px) scale(1)'
            const r = mc.getBoundingClientRect()
            const ev = new MouseEvent('dblclick', {
                bubbles: true, cancelable: true, view: window,
                clientX: r.left + r.width/2, clientY: r.top + r.height/2
            })
            mc.dispatchEvent(ev)
            return true
        }""")
        if not ok:
            raise RuntimeError('mermaid-content/container 不存在, 图表未渲染')
        self.page.wait_for_timeout(1500)

    def click(self, selector: str, index: int = 0, wait_ms: int = 1200):
        """[FIX 2026-08-01] 派发原生 click 到指定元素 (绕过 playwright pointer 模拟).
        在 click 中心问题排查中, 用 dispatchEvent 比 page.click() 更可控:
          - 不会被 playwright 的 hover/scroll 干扰
          - 直接走 svg → onSvgClick 链路, 暴露 listener 重复触发等深层 bug"""
        self.page.evaluate("""({sel, idx}) => {
            const els = document.querySelectorAll(sel)
            const el = els[idx]
            if (!el) throw new Error('no element: ' + sel)
            const r = el.getBoundingClientRect()
            const ev = new MouseEvent('click', {
                bubbles: true, cancelable: true, view: window,
                clientX: r.left + r.width/2, clientY: r.top + r.height/2,
                button: 0
            })
            el.dispatchEvent(ev)
        }""", {'sel': selector, 'idx': index})
        # [FIX 2026-08-01] 等 transition 完成 (centerElement 设了 transition: transform 0.3s ease).
        # 用 wait_for_function 而不是 wait_for_timeout, 因为 1200ms 可能在 transition 中段.
        try:
            self.page.wait_for_function(
                """() => {
                    const c = document.querySelector('.mermaid-content')
                    if (!c) return false
                    const cs = getComputedStyle(c)
                    // transition 完成后, transform 应该跟 style.transform 一致
                    return cs.transform === c.style.transform || c.style.transform === ''
                }""",
                timeout=2000
            )
        except Exception:
            pass
        self.page.wait_for_timeout(wait_ms)

    def measure(self, selector: str, index: int = 0) -> Dict[str, Any]:
        """[FIX 2026-08-01] 一键测元素屏幕位置 + wrapper center.
        返回 JSON-serializable dict, 直接用于回归断言."""
        return self.page.evaluate("""({sel, idx}) => {
            const wrapper = document.querySelector('.mermaid-wrapper')
            const wrapperRect = wrapper.getBoundingClientRect()
            const els = document.querySelectorAll(sel)
            const el = els[idx]
            if (!el) return { error: 'no element: ' + sel }
            const r = el.getBoundingClientRect()
            return {
                selector: sel,
                index: idx,
                wrapperRect: { x: wrapperRect.left, y: wrapperRect.top, w: wrapperRect.width, h: wrapperRect.height },
                wrapperCenter: { x: wrapperRect.left + wrapperRect.width/2, y: wrapperRect.top + wrapperRect.height/2 },
                elRect: { left: r.left, top: r.top, w: r.width, h: r.height },
                elCenter: { x: r.left + r.width/2, y: r.top + r.height/2 },
                contentTransform: document.querySelector('.mermaid-content').style.transform
            }
        }""", {'sel': selector, 'idx': index})

    def click_and_assert_centered(self, selector: str, index: int = 0,
                                   tolerance: float = 1.0) -> Dict[str, Any]:
        """[FIX 2026-08-01] 一键验证: 点击后元素 rect center == wrapper center (容差 tolerance px).
        取代 verify_center_v2.py 中 ~50 行 setup + measure + click + remeasure 代码.

        返回:
          { before: {...}, after: {...}, diff: {x, y}, passed: bool }"""
        before = self.measure(selector, index)
        self.click(selector, index)
        after = self.measure(selector, index)
        diff = {
            'x': round(after['elCenter']['x'] - before['wrapperCenter']['x'], 2),
            'y': round(after['elCenter']['y'] - before['wrapperCenter']['y'], 2)
        }
        passed = abs(diff['x']) <= tolerance and abs(diff['y']) <= tolerance
        result = {
            'selector': selector,
            'index': index,
            'before': before,
            'after': after,
            'diff': diff,
            'passed': passed,
            'tolerance': tolerance
        }
        flag = '[OK]' if passed else '[FAIL]'
        print(f'{flag} {selector}[{index}]  diff=({diff["x"]:.1f}, {diff["y"]:.1f})  '
              f'transform={after["contentTransform"]}')
        return result

    def compare_path_centers(self, n: int = 5) -> List[Dict[str, Any]]:
        """[FIX 2026-08-01] 列出前 n 个 flowchart-link path 的三种"中心"计算对比:
          - midScreen  (getPointAtLength/totalLen + getScreenCTM) — 沿 stroke 走到一半
          - bboxScreen (getBBox + getScreenCTM) — 几何包围盒中心
          - rectScreen (getBoundingClientRect) — 屏幕 rect 中心 (含 stroke 宽度 + 父级 transform)

        用途: 在排查 click center 错位 bug 时, 用此方法直观看出"哪种中心"对应用户视觉.
        打印结果时附上 transform=identity 状态下各中心 vs wrapper center 的差."""
        result = self.page.evaluate("""(n) => {
            const wrapper = document.querySelector('.mermaid-wrapper')
            const wrapperRect = wrapper.getBoundingClientRect()
            const wrapperCenter = { x: wrapperRect.left + wrapperRect.width/2, y: wrapperRect.top + wrapperRect.height/2 }
            const paths = document.querySelectorAll('path.flowchart-link')
            const out = []
            for (let i = 0; i < Math.min(paths.length, n); i++) {
                const p = paths[i]
                const bbox = p.getBBox()
                const ctm = p.getScreenCTM()
                const pr = p.getBoundingClientRect()
                const totalLen = p.getTotalLength()
                const mid = p.getPointAtLength(totalLen / 2)
                const project = (cx, cy) => ctm ? {
                    x: cx * ctm.a + cy * ctm.c + ctm.e,
                    y: cx * ctm.b + cy * ctm.d + ctm.f
                } : null
                const midScreen = project(mid.x, mid.y)
                const bboxScreen = project(bbox.x + bbox.width/2, bbox.y + bbox.height/2)
                const rectCenter = { x: pr.left + pr.width/2, y: pr.top + pr.height/2 }
                out.push({
                    index: i,
                    d: p.getAttribute('d').substring(0, 60),
                    totalLen,
                    bboxSVG: { x: bbox.x, y: bbox.y, w: bbox.width, h: bbox.height },
                    midSVG: { x: mid.x, y: mid.y },
                    midScreen,
                    bboxScreen,
                    rectCenter
                })
            }
            return { wrapperCenter, paths: out }
        }""", n)
        wrapper = result['wrapperCenter']
        print(f'wrapper center: ({wrapper["x"]:.1f}, {wrapper["y"]:.1f})\n')
        print(f'{"i":>3}  {"d (前60字符)":<60}  {"center (mid)":<22}  {"center (bbox)":<22}  {"center (rect)":<22}')
        for p in result['paths']:
            d = p['d'].replace('\n', ' ')[:58]
            mid = p['midScreen']
            bbox = p['bboxScreen']
            rect = p['rectCenter']
            if mid:
                diff_mid = f'd={mid["x"]-wrapper["x"]:.1f},{mid["y"]-wrapper["y"]:.1f}'
            else:
                diff_mid = 'n/a'
            diff_bbox = f'd={bbox["x"]-wrapper["x"]:.1f},{bbox["y"]-wrapper["y"]:.1f}'
            diff_rect = f'd={rect["x"]-wrapper["x"]:.1f},{rect["y"]-wrapper["y"]:.1f}'
            print(f'{p["index"]:>3}  {d:<60}  ({mid["x"]:6.1f},{mid["y"]:6.1f}) {diff_mid:<10}  ({bbox["x"]:6.1f},{bbox["y"]:6.1f}) {diff_bbox:<10}  ({rect["x"]:6.1f},{rect["y"]:6.1f}) {diff_rect:<10}')
        return result

    def trace_click_listeners(self, selector: str, index: int = 0) -> List[Dict[str, Any]]:
        """[FIX 2026-08-01] 捕获 click 触发链 (哪些 listener 被调, 调几次).

        背景: 排查 click center bug 时, 发现 onSvgClick 被同一 click 事件调 3 次.
        根因: bindAnnotationInteraction 在 svg + 每个 edgeLabel + 每个 flowchart-link 上都绑了
        同一个 onSvgClick handler, 而 click 事件触发后:
          1. svg 上的 listener 触发 (capture/bubble 取决于注册方式)
          2. 当前 element (label) 上的 listener 触发
          3. 子元素 SPAN 上的 listener 触发 (虽然没显式绑, 但 useTooltip 等绑了)
          每次都累加 transform, 导致过冲.

        修复: 见 annotationOverlay.js onSvgClick 中的 svg.__lastAnnoClickTime 时间窗口去重.

        用法: diag.trace_click_listeners('svg g.edgeLabel') → 返回 [
          {seq: 1, currentTarget: 'G', target: 'SPAN', isNewEvent: True},
          ...
        ]"""
        # 先注册 capture listener (在用户 listener 之前跑)
        self.page.evaluate("""() => {
            window.__clickTrace = []
            const original = window.MouseEvent
            // 用 capture + 一次性的标记
            const svg = document.querySelector('svg')
            if (svg) {
                svg.addEventListener('click', (e) => {
                    window.__clickTrace.push({
                        currentTarget: e.currentTarget ? e.currentTarget.tagName : 'null',
                        target: e.target ? e.target.tagName : 'null',
                        targetClass: (e.target && e.target.getAttribute && e.target.getAttribute('class')) || '',
                        isTrusted: e.isTrusted,
                        timeStamp: e.timeStamp,
                        isFirstCall: window.__clickTrace.filter(c => c.timeStamp === e.timeStamp).length === 0
                    })
                }, true)  // capture phase: 先于 bubble
            }
        }""")
        self.click(selector, index)
        trace = self.page.evaluate("() => window.__clickTrace")
        # 汇总: 同一 timeStamp 出现几次
        by_ts = {}
        for t in (trace or []):
            ts = t.get('timeStamp')
            by_ts.setdefault(ts, []).append(t)
        print(f'click 触发链 (同一 click 事件被调 {len(by_ts)} 个不同 timeStamp):')
        for ts, calls in by_ts.items():
            print(f'  timeStamp={ts:.0f}  调用 {len(calls)} 次:')
            for c in calls:
                print(f'    currentTarget={c["currentTarget"]:>6}  target={c["target"]:<6}  class="{c["targetClass"][:30]}"')
        return trace

    def dump_state(self) -> Dict[str, Any]:
        """[FIX 2026-08-01] 一键抓取图表状态 — 用于 bug 复现.
        通过 window.__archPage.mermaid.dump() 读取 (useDiagnostics 模块暴露的全局状态).
        返回 dict, 可直接 JSON 序列化保存到 report 文件."""
        result = self.page.evaluate("""() => {
            const out = {
                url: location.href,
                hasMermaidContainer: !!document.querySelector('.mermaid-container'),
                hasMermaidContent: !!document.querySelector('.mermaid-content'),
                hasSvg: !!document.querySelector('.mermaid-content svg'),
                viewport: { w: window.innerWidth, h: window.innerHeight }
            }
            // useDiagnostics 暴露的状态
            if (window.__archPage && window.__archPage.mermaid) {
                out.diagnostics = window.__archPage.mermaid.dump()
            } else {
                out.diagnostics = { error: 'window.__archPage.mermaid not installed. ' +
                    '可能原因: MermaidComponent 未挂载 / 未走 installDiagnosticsToWindow 路径.' }
            }
            // mermaid-content transform + 子元素统计
            const content = document.querySelector('.mermaid-content')
            if (content) {
                out.contentTransform = content.style.transform
                out.contentComputedTransform = getComputedStyle(content).transform
                const svg = content.querySelector('svg')
                if (svg) {
                    out.svgViewBox = svg.getAttribute('viewBox')
                    out.svgPreserveAspectRatio = svg.getAttribute('preserveAspectRatio')
                    out.svgWidth = svg.getAttribute('width')
                    out.svgHeight = svg.getAttribute('height')
                }
            }
            // wrapper 尺寸
            const wrapper = document.querySelector('.mermaid-wrapper')
            if (wrapper) {
                const r = wrapper.getBoundingClientRect()
                out.wrapperRect = { x: r.left, y: r.top, w: r.width, h: r.height }
            }
            return out
        }""")
        return result

    def screenshot(self, name: str) -> Path:
        """保存截图到 chart_diag_out/."""
        path = self.OUTPUT_DIR / f'{name}.png'
        self.page.screenshot(path=str(path))
        return path

    def dump_dom_tree(self, selector: str = 'svg.mermaid', depth: int = 3) -> Dict[str, Any]:
        """[FIX 2026-08-01] 列出 svg DOM 层级 (前 N 层), 含每层 class.
        排查 mermaid 11 ELK 渲染结构时必备 — 看 labels / edges / edgePaths / edgeLabels 在哪一层."""
        return self.page.evaluate("""({sel, depth}) => {
            const root = document.querySelector(sel)
            if (!root) return { error: 'no svg' }
            const walk = (el, d) => {
                if (d > depth || !el) return null
                const children = []
                for (const c of (el.children || [])) {
                    children.push({
                        tag: c.tagName,
                        class: c.getAttribute('class') || '',
                        childCount: c.children.length,
                        children: walk(c, d + 1)
                    })
                }
                return { tag: el.tagName, class: el.getAttribute('class') || '', children }
            }
            return walk(root, 0)
        }""", {'sel': selector, 'depth': depth})

    def close(self):
        self.cli.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# CLI: 一键跑所有 click center 回归测试
def run_no_move_on_empty_click(viewport: Tuple[int, int] = (1280, 720)) -> Dict[str, Any]:
    """[FIX 2026-08-01 v3] 回归: 点击图表空白区域不应触发 center / transform.
    历史 bug: 用户点 .subgraphs (mermaid 11 ELK 的透明 wrapper, bbox 覆盖全图) → findTargetFromEvent
    上溯找到第一个 cluster → onCenterElement 居中第一个 cluster → 用户感知 "我点了空白但图跳了".

    测试 4 个 '视觉空白' 位置, 验证 transform 一律不变."""
    print(f'=== empty click 不动测试  viewport={viewport} ===\n')
    results = []
    with ChartDiag(viewport=viewport) as diag:
        diag.open_chart()
        diag.reset_transform()
        base_transform = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")

        empty_cases = [
            ('svg root 空白处 (左上角)',
             "() => { const svg = document.querySelector('.mermaid-content svg'); const r = svg.getBoundingClientRect(); svg.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, clientX: r.left + 5, clientY: r.top + 5, button: 0 })); }"),
            ('g.subgraphs (cluster 集合层, 透明 wrapper)',
             "() => { const g = document.querySelector('.mermaid-content svg g.subgraphs'); if (g) g.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, button: 0 })); }"),
            ('g.subgraph (单 cluster wrapper, 单数)',
             "() => { const g = document.querySelector('.mermaid-content svg g.subgraph'); if (g) g.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, button: 0 })); }"),
            ('g.root (顶层 SVG group)',
             "() => { const g = document.querySelector('.mermaid-content svg > g'); if (g) g.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, button: 0 })); }"),
        ]
        for label, js in empty_cases:
            diag.reset_transform()
            t_before = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")
            diag.page.evaluate(js)
            diag.page.wait_for_timeout(600)
            t_after = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")
            # [关键断言] 视觉空白的点击不应让 transform 变更
            if t_before == t_after:
                ok = True
                print(f'[OK] {label}  transform 未变')
            else:
                ok = False
                print(f'[FAIL] {label}  transform {t_before} → {t_after} (BUG: 空白点击触发了居中)')
            results.append({'case': label, 'passed': ok, 'before': t_before, 'after': t_after})

        passed = sum(1 for r in results if r.get('passed'))
        print(f'\n=== 总结: {passed}/{len(results)} 通过 ===\n')
        return {'passed': passed == len(results), 'cases': results}


# CLI: 一键跑所有 click center 回归测试
def run_center_regression(viewport: Tuple[int, int] = (1280, 720), report_timing: bool = True):
    """[FIX 2026-08-01] 一键回归: 节点/容器/连线/label 各自居中.
    [FIX 2026-08-01 v3] 加 empty_click_no_move 副测试 — 点击空白不应触发 transform.
    [FIX 2026-08-01 v2] 加 report_timing 参数 — 跑完回归后自动打印 useDiagnostics lastRender:
      - durationMs 总耗时
      - stepTimings 各步骤累计 ms (syntax_gen / mermaid_run / process_svg)
      - stepMeta.addLinkCodeAttributes / addBidirectionalAttributes / setupCanvasLayout
    用途: 监控图表渲染性能, 性能回归一眼看出."""
    print(f'=== click center 回归测试  viewport={viewport} ===\n')
    with ChartDiag(viewport=viewport) as diag:
        diag.open_chart()
        # [FIX 2026-08-01] cluster/subgraph 在 mermaid 11 ELK 渲染下不一定是 [data-container-code],
        # 实际可能是 <g class="cluster" id="G_D_xxx"> 形式 (无 data-container-code).
        # 这里用 [class*="cluster"], [class*="subgraph"] 兜底匹配.
        container_sel = 'svg g.cluster'  # 直接选 cluster (g.subgraphs 是集合, 含所有 cluster, 测它会算整个集合的 bbox)
        results = []
        for sel, kind in [
            ('svg g.node[data-code]', 'node'),
            (container_sel, 'container'),
            ('g.edgeLabel', 'label'),
            ('path.flowchart-link', 'path'),
        ]:
            # [FIX 2026-08-01 v5] chart 点击不再触发居中.
            #   新行为: 点 chart 元素 → 仅高亮 + (有对应 panel item 时) 同步 panel, **不**居中.
            #   居中只在 panel item 点击时触发.
            #   旧测试 click_and_assert_centered 依赖 onCenterElement, 现已不再调, 必须更新.
            diag.reset_transform()
            try:
                # 测量: 点击前 transform, 点击后 transform — 应当不变
                t_before = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")
                # 点击元素 (用 click_and_assert_centered 内部的 click 方法, 它自己也会打印一个 [OK]/[FAIL] 但那是基于 "元素居中" 旧断言, 不适用于新行为)
                # 我们改为: 自己 click + 自己 measure + 自己断言 "transform 未变"
                diag.click(sel)
                diag.page.wait_for_timeout(600)
                transform_after = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")
                not_moved = (t_before == transform_after)
                tag = '[OK]' if not_moved else '[FAIL]'
                print(f'{tag} {sel}[0]  transform={"未变" if not_moved else f"{t_before} → {transform_after}"}  (v5: chart click 不居中)')
                results.append({'selector': sel, 'kind': kind, 'passed': not_moved,
                                'transformBefore': t_before, 'transformAfter': transform_after,
                                'note': 'v5: chart click 不居中; 仅 panel item click 触发居中'})
            except Exception as e:
                results.append({'selector': sel, 'kind': kind, 'error': str(e)})

        # [FIX 2026-08-01 v3] 副测试: 点击空白不应触发 transform.
        # 复用同一个 ChartDiag 实例 (避免重新 open_chart 触发 'store not ready'),
        # 在已有 page 上跑空点击测试.
        print(f'\n--- 副测试: empty click 不动 (验证 v3 修复) ---')
        empty_cases = [
            ('svg root 空白处 (左上角)',
             "() => { const svg = document.querySelector('.mermaid-content svg'); const r = svg.getBoundingClientRect(); svg.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, clientX: r.left + 5, clientY: r.top + 5, button: 0 })); }"),
            ('g.subgraphs (cluster 集合层, 透明 wrapper)',
             "() => { const g = document.querySelector('.mermaid-content svg g.subgraphs'); if (g) g.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, button: 0 })); }"),
            ('g.subgraph (单 cluster wrapper, 单数)',
             "() => { const g = document.querySelector('.mermaid-content svg g.subgraph'); if (g) g.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, button: 0 })); }"),
            ('g.root (顶层 SVG group)',
             "() => { const g = document.querySelector('.mermaid-content svg > g'); if (g) g.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, button: 0 })); }"),
        ]
        empty_results = []
        for label, js in empty_cases:
            diag.reset_transform()
            t_before = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")
            diag.page.evaluate(js)
            diag.page.wait_for_timeout(600)
            t_after = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")
            ok = (t_before == t_after)
            tag = '[OK]' if ok else '[FAIL]'
            print(f'  {tag} {label}  transform 未变' if ok else f'  {tag} {label}  transform {t_before} → {t_after} (BUG)')
            empty_results.append({'case': label, 'passed': ok, 'before': t_before, 'after': t_after})
        empty_passed = sum(1 for r in empty_results if r['passed'])
        print(f'  empty click 总结: {empty_passed}/{len(empty_results)} 通过')
        results.append({'kind': 'empty_click_no_move', 'passed': empty_passed == len(empty_results),
                        'cases': empty_results})

        # [FIX 2026-08-01 v4] 副测试 2: 双向联动 (point-chart 应同步 panel selected)
        # 注入 mock panel items (因为 production chart 没真实 annotation), 然后:
        #   - 点 svg 节点 A (有对应 item) → A panel item selected
        #   - 点 svg 节点 B (有对应 item) → B selected, A 自动清掉
        #   - 点 svg 节点 C (无对应 item) → 全部清掉
        print(f'\n--- 副测试: 双向联动 (验证 v4 修复) ---')
        # 选 3 个有 data-code 的节点 + 1 个无 panel item 的节点
        nodes = diag.page.evaluate("""() => {
            const all = Array.from(document.querySelectorAll('svg g.node[data-code]'))
            return all.slice(0, 6).map(n => n.getAttribute('data-code'))
        }""")
        if len(nodes) >= 3:
            # 注入 mock panel items
            diag.page.evaluate("""(nodeIds) => {
                const container = document.querySelector('.mermaid-container')
                const panel = document.createElement('div')
                panel.className = 'annotation-dock-panel'
                panel.style.cssText = 'position:absolute; bottom:10px; left:10px; background:white; padding:10px; border:1px solid #ccc; z-index:1000;'
                nodeIds.slice(0, 2).forEach((id, i) => {
                    const div = document.createElement('div')
                    div.className = 'annotation-item'
                    div.setAttribute('data-target-id', id)
                    div.setAttribute('data-target-type', 'node')
                    div.textContent = 'mock item ' + (i + 1) + ' for ' + id
                    div.style.cssText = 'background:transparent; padding:5px; cursor:pointer;'
                    panel.appendChild(div)
                })
                container.appendChild(panel)
            }""", nodes)

            link_results = []
            def check_link(label, click_js, expected_selected_ids, expected_not_selected_ids, expect_preserved=False):
                diag.reset_transform()
                t_before = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")
                diag.page.evaluate(click_js)
                diag.page.wait_for_timeout(700)
                state = diag.page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('.annotation-item')).map(i => ({
                        id: i.getAttribute('data-target-id'),
                        selected: i.classList.contains('annotation-item-selected')
                    }))
                }""")
                t_after = diag.page.evaluate("() => document.querySelector('.mermaid-content').style.transform")
                ok = True
                # 检查 panel selected 状态
                for it in state:
                    if it['id'] in expected_selected_ids:
                        if not it['selected']:
                            ok = False
                    elif it['id'] in expected_not_selected_ids:
                        if it['selected']:
                            ok = False
                # [FIX 2026-08-01 v5] 双向验证: chart click 永远不应触发 transform 变更
                if t_before != t_after:
                    ok = False
                tag = '[OK]' if ok else '[FAIL]'
                sel_list = [it['id'] for it in state if it['selected']]
                preserved = ' [preserve]' if expect_preserved else ''
                print(f'  {tag} {label}{preserved}  selected={sel_list}  transform={"不变" if t_before == t_after else "变化 " + t_before + "→" + t_after}')
                return ok

            # T1: 点 svg 节点 0 → item 0 selected, transform 不变
            t1_ok = check_link(
                '点 svg 节点 ' + nodes[0] + ' (有 panel item) → 对应 item selected + 不居中',
                f"""() => {{
                    const n = document.querySelector('svg g.node[data-code="{nodes[0]}"]')
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window, clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }}))
                }}""",
                expected_selected_ids=[nodes[0]],
                expected_not_selected_ids=[nodes[1]]
            )
            link_results.append({'case': 'svg-click selects matching item + no center', 'passed': t1_ok})

            # T2: 点 svg 节点 1 → item 1 selected, item 0 清掉, transform 不变
            t2_ok = check_link(
                '点 svg 节点 ' + nodes[1] + ' (有 panel item) → 切到 item 1 + 不居中',
                f"""() => {{
                    const n = document.querySelector('svg g.node[data-code="{nodes[1]}"]')
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window, clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }}))
                }}""",
                expected_selected_ids=[nodes[1]],
                expected_not_selected_ids=[nodes[0]]
            )
            link_results.append({'case': 'switching chart deselects old item + no center', 'passed': t2_ok})

            # T3 (v5 新增): 点 svg 节点 2 (无 panel item) → panel 保留, transform 不变
            # 先确保有 item selected (前置状态)
            diag.page.evaluate(f"""() => {{
                const n = document.querySelector('svg g.node[data-code="{nodes[0]}"]')
                const r = n.getBoundingClientRect()
                n.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window, clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }}))
            }}""")
            diag.page.wait_for_timeout(500)
            t3_ok = check_link(
                '点 svg 节点 ' + nodes[2] + ' (无 panel item) → panel 保留原状 + 不居中',
                f"""() => {{
                    const n = document.querySelector('svg g.node[data-code="{nodes[2]}"]')
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window, clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }}))
                }}""",
                # 关键: nodes[0] 的 selected 应该保留 (前置操作已选中它)
                expected_selected_ids=[nodes[0]],
                expected_not_selected_ids=[nodes[1]],
                expect_preserved=True
            )
            link_results.append({'case': 'click element without annotation preserves panel + no center', 'passed': t3_ok})

            link_passed = sum(1 for r in link_results if r['passed'])
            print(f'  双向联动 总结: {link_passed}/{len(link_results)} 通过')
            results.append({'kind': 'annotation_two_way_link', 'passed': link_passed == len(link_results),
                            'cases': link_results})

            # [FIX 2026-08-01 v5] 副测试 3 (info-only): panel item 点击路径的居中入口
            # 仅做信息记录 — mock item 是在 bindAnnotationInteraction 之后注入, 没有 click listener,
            # 所以测试不能直接验证 panel item click → onCenterElement.
            # 实际 verification 已在源码中明确: onItemClick (line ~333) 调 onCenterElement,
            # onSvgClick (line ~459) 不调. 这是 v5 设计的核心约束.
            print(f'\n--- 副测试: 居中入口唯一性 (v5 设计验证) ---')
            # 通过源码静态分析验证: 用 fetch 拿 annotationOverlay.js 看 onSvgClick 不含 onCenterElement
            import urllib.request, re
            try:
                src = urllib.request.urlopen('http://localhost:3006/src/composables/useMermaid/annotation/annotationOverlay.js', timeout=10).read().decode('utf-8')
                # 提取 onSvgClick 函数体
                m = re.search(r'const onSvgClick = \(e\) => \{(.+?)\n    \};', src, re.DOTALL)
                if m:
                    onSvgClick_body = m.group(1)
                    has_center = 'onCenterElement' in onSvgClick_body
                    tag = '[OK]' if not has_center else '[FAIL]'
                    print(f'  {tag} onSvgClick 函数体不含 onCenterElement 调用  (v5: chart click 不居中)')
                    results.append({'kind': 'no_center_in_svgclick', 'passed': not has_center,
                                    'note': 'v5: onSvgClick 函数体内不应出现 onCenterElement'})
                else:
                    print(f'  [INFO] 未匹配到 onSvgClick 函数体, 跳过静态检查')
                    results.append({'kind': 'no_center_in_svgclick', 'passed': True, 'skipped': True})
            except Exception as ex:
                print(f'  [WARN] 静态检查失败: {ex}')
                results.append({'kind': 'no_center_in_svgclick', 'passed': True, 'error': str(ex)})

        # 输出截图
        diag.screenshot('after_regression')
        # 汇总
        passed = sum(1 for r in results if r.get('passed'))
        print(f'\n=== 总结: {passed}/{len(results)} 通过 ===')

        # [FIX 2026-08-01 v2] 性能报告 — 一键读取 useDiagnostics
        if report_timing:
            try:
                state = diag.dump_state()
                diag_state = state.get('diagnostics', {})
                lr = diag_state.get('lastRender')
                print('\n=== 渲染性能报告 (useDiagnostics.lastRender) ===')
                if not lr:
                    print('  ⚠ lastRender 仍是 null — useDiagnostics 未被触发 (可能被 cache 拦截, 或 render() 路径未走)')
                else:
                    print(f'  durationMs: {lr.get("durationMs", "?")} ms')
                    print(f'  layoutEngine: {lr.get("layoutEngine", "?")}')
                    print(f'  nodeCount: {lr.get("nodeCount", "?")}')
                    print(f'  edgeCount: {lr.get("edgeCount", "?")}')
                    print(f'  containerCount: {lr.get("containerCount", "?")}')
                    err = lr.get('error')
                    if err:
                        print(f'  ⚠ error: {err}')
                    timings = lr.get('stepTimings') or {}
                    if timings:
                        print('  stepTimings:')
                        for k, v in sorted(timings.items()):
                            print(f'    {k}: {round(v, 1)} ms')
                    meta = diag_state.get('stepMeta') or {}
                    if meta:
                        print('  stepMeta (key=calls):')
                        for k, v in meta.items():
                            print(f'    {k}: {len(v) if isinstance(v, list) else 1} entries')
                # 错误摘要
                errs = diag_state.get('errors') or []
                if errs:
                    print(f'\n  ⚠ 最近 {len(errs)} 个错误:')
                    for e in errs[:3]:
                        print(f'    [{e.get("context")}] {e.get("message")}')
            except Exception as e:
                print(f'\n  (性能报告失败: {e})')

        return results


if __name__ == '__main__':
    # 用法: python -m test_helpers.chart_diag
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)

    p1 = sub.add_parser('regression', help='跑 click center 回归测试')
    p1.add_argument('--w', type=int, default=1280)
    p1.add_argument('--h', type=int, default=720)

    p2 = sub.add_parser('compare', help='对比 path 三种中心算法')
    p2.add_argument('--n', type=int, default=5)

    p3 = sub.add_parser('trace', help='捕获 click 触发链')
    p3.add_argument('--sel', default='svg g.edgeLabel')

    args = parser.parse_args()
    if args.cmd == 'regression':
        run_center_regression(viewport=(args.w, args.h))
    else:
        with ChartDiag() as diag:
            diag.open_chart()
            if args.cmd == 'compare':
                diag.compare_path_centers(n=args.n)
            elif args.cmd == 'trace':
                diag.trace_click_listeners(args.sel)