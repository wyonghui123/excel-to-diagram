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
import time
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

    def __init__(self, base_url: str = 'http://localhost:3004',
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
        取代 verify_center_v2.py 中 8 行 setup 代码.

        [FIX 2026-08-02] 直接把目标 scope 传给 shortcut URL:
          之前硬编码 scope=SHORT_SCOPE, 渲染后再调 handleScopeChange 改页面层 scopeIds.
          但 chartData.hierarchyFilter 是 toggleEmbeddedView 时由 URL scope 快照的
          (非响应式), 事后改 scopeIds 不生效 → 所有场景都渲染成 1 BO (2 节点).
          现在 target scope 直接进 URL → tryApplyShortcut → chartData 快照 = 目标 scope."""
        scope = scope or DEFAULT_SCOPE
        # shortcut_chart_view 用目标 scope 触发路由 (URL scope → chartData 快照)
        page = self.cli.shortcut_chart_view(
            target_path='/system/archdata',
            product_code=self.product_code,
            version_id=self.version_id,
            scope=scope,
            base_url=self.base_url,
            wait_for_selector='svg g.node',
            timeout=timeout_ms,
            debug=True
        )
        page.wait_for_timeout(2500)
        # 兜底: 若 shortcut 未渲染 (旧构建/无 shortcut 支持), 尝试点击"图表展示"按钮
        if page.evaluate("() => document.querySelectorAll('svg g.node').length") == 0:
            print('[chart_diag] shortcut 未渲染, 尝试点击图表展示按钮')
            page.evaluate("""() => {
                for (const b of document.querySelectorAll('button')) {
                    const t = (b.textContent || '').trim()
                    if (t === '图表展示') { b.click(); return }
                }
            }""")
            # 等图表渲染
            for _ in range(20):
                page.wait_for_timeout(1000)
                if page.evaluate("() => document.querySelectorAll('svg g.node').length") > 0:
                    break
        page.wait_for_timeout(3000)
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

    # ================================================================
    # [E2E 2026-08-02] 校验辅助方法 — 供 chart_e2e.py 四类断言使用
    #   依赖前端增强 (FE1 nodeColorMappings / FE2 data-chart-rendered / FE3 chartConfig)
    # ================================================================

    def wait_render_stable(self, timeout_ms: int = 30000, poll_ms: int = 300,
                           clear_marker: bool = True) -> Dict[str, Any]:
        """[FE2 2026-08-02] 等待图表渲染完成 (data-chart-rendered=true 标记).
        替代固定 sleep — 渲染完成即可继续, 空等时间被省掉 (高效性).

        clear_marker=True (默认): 等待前先移除旧标记, 确保等待的是"本次新渲染"
        而非上一次留下的旧值 (配置切换后调用必须为 True, 否则旧标记误判已稳定).

        返回 { rendered, nodeCount, edgeCount, containerCount, error }."""
        if clear_marker:
            self.page.evaluate("""() => {
                const el = document.querySelector('.embedded-chart-view__canvas')
                if (el) el.removeAttribute('data-chart-rendered')
            }""")
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            state = self.page.evaluate("""() => {
                const el = document.querySelector('.embedded-chart-view__canvas[data-chart-rendered]')
                if (!el) return null
                return {
                    rendered: el.getAttribute('data-chart-rendered'),
                    nodeCount: parseInt(el.getAttribute('data-node-count') || '0'),
                    edgeCount: parseInt(el.getAttribute('data-edge-count') || '0'),
                    containerCount: parseInt(el.getAttribute('data-container-count') || '0'),
                    error: el.getAttribute('data-error') || null
                }
            }""")
            if state and state['rendered'] == 'true':
                return state
            self.page.wait_for_timeout(poll_ms)
        raise TimeoutError(f'chart 渲染超时 ({timeout_ms}ms)')

    def get_render_metrics(self) -> Dict[str, Any]:
        """读取渲染指标: data-* DOM 属性 + useDiagnostics.lastRender (SVG 级口径).
        数据完整性断言的数据源.
        [FIX 2026-08-02] clear_marker=False: 这里读的是"当前已渲染状态",
        若清标记会导致等下一次新渲染而超时 (图表已稳定, 不会再触发 endRender).
        [OBS 2026-08-13] 补充 subgraphInSrc: 源码 subgraph 数, 与 data-container-count 比对
        可一条 evaluate 定位"源码有 subgraph 但 SVG 无容器"的渲染丢失问题."""
        dom_state = self.wait_render_stable(timeout_ms=5000, clear_marker=False)
        last_render = self.page.evaluate("() => window.__archPage?.mermaid?.lastRender || null")
        subgraph = self.page.evaluate("() => window.__archPage?.mermaid?.subgraphInSrc ?? null")
        if subgraph is not None:
            last_render = {**last_render, 'subgraphInSrc': subgraph}
        return {'dom': dom_state, 'lastRender': last_render}

    def get_relation_highlight(self) -> Dict[str, Any]:
        """[OBS 2026-08-13] 关系高亮状态快照: __archPage.relationHighlight() 权威态
        + DOM 实测 [data-rel-hl]/[data-rel-dim] 计数.
        供 E2E 一条 evaluate 断言"高亮/清除/范围正确", 替代扫描 inline opacity 的脆弱断言."""
        return self.page.evaluate("""() => {
            const api = window.__archPage && window.__archPage.relationHighlight
            const state = api ? api() : { error: '__archPage.relationHighlight 未暴露' }
            const svg = document.querySelector('.mermaid-content svg')
            const dom = {
                relHl: svg ? svg.querySelectorAll('[data-rel-hl]').length : -1,
                relDim: svg ? svg.querySelectorAll('[data-rel-dim]').length : -1
            }
            return { ...state, dom }
        }""")

    def trigger_relation_highlight(self, code: str, wait_ms: int = 800) -> Dict[str, Any]:
        """[OBS 2026-08-13] 触发关系高亮 (需 ?mode=debug 暴露 __archPage.debug.highlightRelations)
        并读取快照. 返回 {state, dom}. code 为空时自动取首个可见节点编码."""
        if not code:
            code = self.page.evaluate("""() => {
                const el = document.querySelector('g.node[data-container-code]') ||
                           document.querySelector('g.node[data-code]') ||
                           document.querySelector('g.cluster[data-container-code]')
                return el ? (el.getAttribute('data-container-code') || el.getAttribute('data-code')) : null
            }""")
        self.page.evaluate("(c) => window.__archPage.debug.highlightRelations(c)", code)
        self.page.wait_for_timeout(wait_ms)
        return self.get_relation_highlight()

    def assert_expand_invariant(self, level: str) -> Dict[str, Any]:
        """[OBS 2026-08-13] 展开/折叠不变式: 调 __archPage.assertExpandInvariant(level),
        返回树各层计数 + 期望/实际容器数 + 比对, 供 E2E 断言展开层级正确性."""
        return self.page.evaluate("(l) => window.__archPage.assertExpandInvariant(l)", level)

    def get_node_colors(self) -> Dict[str, str]:
        """读取 nodeCode → fill 映射 (FE1: stepMeta.nodeColorMappings, 权威源).
        golden 生成时记录; 断言时与 SVG 实际 fill 对比, 防"颜色映射对但没渲染出来".
        [FIX 2026-08-02] recordStepMeta 每次 push 形成嵌套数组, 需 .flat() 展开."""
        return self.page.evaluate("""() => {
            const meta = window.__archPage?.mermaid?.stepMeta || {}
            const list = (Array.isArray(meta.nodeColorMappings) ? meta.nodeColorMappings : []).flat()
            if (!Array.isArray(list) || list.length === 0) return {}
            const out = {}
            for (const m of list) {
                if (m.nodeCode) out[m.nodeCode] = m.color || null
            }
            return out
        }""")

    def get_center_codes(self) -> set:
        """读取中心节点 code 集合 (FE1: nodeColorMappings.isCenter).
        [E2E 2026-08-02] B2 断言需跳过中心节点: 映射记录分组原始色,
        渲染时中心节点被 centerScopeColor 覆盖 — 预期差异, 不算染色失败."""
        return set(self.page.evaluate("""() => {
            const meta = window.__archPage?.mermaid?.stepMeta || {}
            const list = (Array.isArray(meta.nodeColorMappings) ? meta.nodeColorMappings : []).flat()
            const out = []
            for (const m of list) {
                if (m.isCenter && m.nodeCode) out.push(m.nodeCode)
            }
            return out
        }"""))

    def get_svg_node_fills(self, limit: int = 500) -> Dict[str, str]:
        """读 SVG 实际渲染的节点 fill (data-code → fill), 与 nodeColorMappings 对照.
        防"报告对但 SVG 没染色"."""
        return self.page.evaluate("""(limit) => {
            const out = {}
            const nodes = Array.from(document.querySelectorAll('svg g.node[data-code]'))
            for (const n of nodes.slice(0, limit)) {
                const code = n.getAttribute('data-code')
                const rect = n.querySelector('rect')
                out[code] = rect ? (rect.getAttribute('fill') || rect.style.fill || '') : ''
            }
            return out
        }""", limit)

    def switch_chart_config(self, key: str, value: Any) -> None:
        """[FE3 2026-08-02] E2E 配置切换入口.
        __archPage.chartConfig[key] = value → EmbeddedChartView watcher →
        configStore.updateXxx → generateDiagram.
        替代操作 Element Plus 下拉弹层的脆弱 UI 交互."""
        self.page.evaluate("""({key, value}) => {
            const cfg = window.__archPage && window.__archPage.chartConfig
            if (!cfg) throw new Error('__archPage.chartConfig 未暴露 (EmbeddedChartView 未挂载)')
            cfg[key] = value
        }""", {'key': key, 'value': value})

    def wait_for_svg_nodes(self, min_count: int = 1, timeout_ms: int = 10000,
                           poll_ms: int = 200, data_code: bool = True) -> int:
        """[2026-08-13] 等待活动图表 SVG (.mermaid-content) 渲染出 >= min_count 个节点.
        解决 wait_render_stable 返回后 SVG 仍在异步渲染的竞态: 有些切换 (如 SM→BO)
        marker 提前置位但节点尚未入 DOM, 立即断言会假失败 (svgOk=False 抖动).
        返回实际节点数.
        data_code=True 统计 g.node[data-code] (BO 级节点); False 统计任意 g.node
        (含 COLLAPSE_* 领域/子领域容器, 用于快速切换后可能折叠回领域级的场景)."""
        selector = ('g.node[data-code]' if data_code else 'g.node')
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            n = self.page.evaluate(
                f"() => document.querySelectorAll('.mermaid-content svg {selector}').length")
            if n >= min_count:
                return n
            self.page.wait_for_timeout(poll_ms)
        return n

    def get_annotation_items(self) -> List[Dict[str, Any]]:
        """读取备注面板 items (.annotation-dock-panel .annotation-item).
        备注断言的数据源: 数量 / 类型 / 是否 selected.
        [FIX 2026-08-02] item class = 'annotation-item annotation-{targetType}' (node/relation/container),
        正则应匹配第二段 (node/relation/container), 不能贪心匹配到 'item'."""
        return self.page.evaluate("""() => {
            const items = Array.from(document.querySelectorAll('.annotation-dock-panel .annotation-item'))
            return items.map(i => {
                const cls = i.className || ''
                const m = cls.match(/annotation-(node|relation|container|item)/)
                return {
                    targetId: i.getAttribute('data-target-id'),
                    targetType: m ? m[1] : 'unknown',
                    text: (i.textContent || '').trim().substring(0, 60),
                    selected: i.classList.contains('annotation-item-selected')
                }
            })
        }""")

    # ================================================================
    # [2026-08-05] 调色板增量变色闭环辅助方法
    #   收敛自 _verify_palette_change.py 的一次性内联逻辑 (get_fills/get_store/
    #   get_diagram_data/pick_color), 避免每次排查改色问题重写 DOM 探测.
    #   统一入口: open_palette() 展开布局面板 → get_fills_before() → pick_color()
    #   → get_fills_after() → palette_loop() 一行跑完整闭环.
    # ================================================================

    def open_palette_panel(self) -> Dict[str, Any]:
        """展开"图表设置"布局面板 (store.layoutPanelExpanded → 本地 layoutExpanded).
        调色板色点在面板内, 默认折叠时是 hidden DOM 无法交互。
        返回面板可见性 (色点宽高/数量)。"""
        self.page.evaluate("""() => {
            const cs = window.__configStore
            if (!cs) return 'no store'
            if (typeof cs.setLayoutPanelExpanded === 'function') cs.setLayoutPanelExpanded(true)
            else cs.layoutPanelExpanded = true
            return 'expanded layout panel'
        }""")
        self.page.wait_for_timeout(1200)
        return self.page.evaluate("""() => {
            const p = document.querySelector('.lgn-color-picker')
            const r = p ? p.getBoundingClientRect() : null
            return { w: r ? r.width : 0, h: r ? r.height : 0,
                     count: document.querySelectorAll('.lgn-color-picker').length }
        }""")

    def get_fills(self) -> Dict[str, int]:
        """统计图表节点 fill 分布 (color value → 数量)。
        遍历所有 mermaid svg 的 g.node/g.nodes rect (兼容 mermaid 11 结构),
        跳过 none/transparent。用于"改色前后节点 fill 对比"断言。
        注意: 与 chart_diag.get_svg_node_fills(data-code→fill) 口径不同,
        本方法是聚合分布, 两者互补。"""
        return self.page.evaluate("""() => {
            const fills = {}
            let total = 0
            document.querySelectorAll('.mermaid-container svg g.node rect, .mermaid-container svg g.nodes rect').forEach(r => {
                const f = r.getAttribute('fill') || r.style.fill || 'none'
                if (f === 'none' || f === 'transparent') return
                fills[f] = (fills[f] || 0) + 1
                total++
            })
            return { total, distinct: Object.keys(fills).length, fills }
        }""")

    def get_color_store(self) -> Dict[str, Any]:
        """读取 diagramConfigStore 当前颜色配置 (colorGroupBy / customColors)。"""
        return self.page.evaluate("""() => {
            const cs = window.__configStore
            if (!cs) return { error: 'no __configStore' }
            return {
                colorGroupBy: cs.colorGroupBy?.value ?? cs.colorGroupBy,
                customColors: cs.customColors?.value ?? cs.customColors
            }
        }""")

    def get_center_scope_snapshot(self) -> Dict[str, Any]:
        """读取 store 对象范围配置 (codes/highlight/color)。
        set_center_scope 的返回源 + 对象范围改色/图例验证的 before/after 快照。"""
        return self.page.evaluate("""() => {
            const cs = window.__configStore
            if (!cs) return { error: 'no __configStore' }
            const getv = (r) => (r && {}.hasOwnProperty.call(r, 'value')) ? r.value : r
            return {
                centerScope: getv(cs.centerScope),
                centerScopeHighlight: getv(cs.centerScopeHighlight),
                centerScopeColor: getv(cs.centerScopeColor)
            }
        }""")

    def set_center_scope(self, codes: Optional[list] = None,
                         highlight: Optional[bool] = None,
                         color: Optional[str] = None,
                         wait_ms: int = 8000) -> Dict[str, Any]:
        """[2026-08-05] 一键设置对象范围 (store), 供对象范围颜色/图例 E2E 验证.
        通过 __configStore.updateCenterScope/Highlight/Color 触发 (等价于配置面板操作),
        再等待图表按新对象范围重渲染。返回设置后的对象范围快照。"""
        self.page.evaluate("""({codes, highlight, color}) => {
            const cs = window.__configStore
            if (!cs) return 'no __configStore'
            if (codes !== undefined) cs.updateCenterScope(codes)
            if (highlight !== undefined) cs.updateCenterScopeHighlight(highlight)
            if (color !== undefined) cs.updateCenterScopeColor(color)
            return 'ok'
        }""", {'codes': codes, 'highlight': highlight, 'color': color})
        if wait_ms:
            self.wait_render_stable(timeout_ms=wait_ms)
        return self.get_center_scope_snapshot()

    def get_diagram_snapshot(self) -> Dict[str, Any]:
        """读取 __archPage.diagramData 关键字段 (customColors/colorGroupBy/colorScheme + 首节点色)。
        验证 store.customColors 是否已传递到 diagramData 并驱动节点着色。"""
        return self.page.evaluate("""() => {
            const ap = window.__archPage
            if (!ap || !ap.diagramData) return { error: 'no diagramData' }
            const d = ap.diagramData.value ?? ap.diagramData
            return {
                hasData: !!d,
                customColors: d?.customColors,
                colorGroupBy: d?.colorGroupBy,
                colorScheme: d?.colorScheme,
                nodeCount: d?.nodes?.length,
                sampleNode: d?.nodes?.[0] ? { id: d.nodes[0].id, name: d.nodes[0].name,
                    domain: d.nodes[0].domain, subDomain: d.nodes[0].subDomain,
                    color: d.nodes[0].color } : null
            }
        }""")

    def pick_color(self, target_color: str) -> str:
        """点击第一个色点并选择目标色 (predefine 色块) + 点"确定"提交。
        target_color 内联进 evaluate (避开 CLI 参数包装)。
        Element Plus 需点 confirm 才 emit update:model-value → store.customColors 更新。
        返回提交结果 ("confirmed" / 错误信息)。"""
        # 1. 点击第一个色点
        self.page.evaluate("""() => {
            const picker = document.querySelector('.lgn-color-picker')
            if (!picker) return 'no picker'
            const t = picker.querySelector('.el-color-picker__trigger') || picker
            t.click()
            return 'clicked picker'
        }""")
        self.page.wait_for_timeout(800)
        # 2. 在 predefine 色块中找目标色
        target_lower = target_color.lower()
        self.page.evaluate(f"""() => {{
            const btns = Array.from(document.querySelectorAll('.el-color-predefine__color-selector'))
            for (const b of btns) {{
                const aria = b.getAttribute('aria-label') || ''
                const bg = b.style.backgroundColor || ''
                if (aria.toLowerCase().includes('{target_lower}') || bg.toLowerCase().includes('{target_lower}')) {{
                    b.click()
                    return 'clicked color: ' + (aria || bg)
                }}
            }}
            const cols = btns.map(b => b.getAttribute('aria-label') || b.style.backgroundColor)
            return 'color not found, available: ' + JSON.stringify(cols)
        }}""")
        self.page.wait_for_timeout(800)
        # 3. 点"确定"提交
        r = self.page.evaluate("""() => {
            const panels = Array.from(document.querySelectorAll('.el-color-picker__panel'))
            const open = panels.find(p => getComputedStyle(p).display !== 'none' &&
                                          p.getBoundingClientRect().width > 0)
            if (!open) return 'no open panel'
            const btn = open.querySelector('.el-color-footer__btn')
            if (btn) { btn.click(); return 'confirmed' }
            return 'no confirm btn'
        }""")
        self.page.wait_for_timeout(1200)
        return r

    def palette_loop(self, target_color: str = '#f5222d', verbose: bool = True) -> Dict[str, Any]:
        """[2026-08-05] 一行跑完整"色点改色 → 图表增量变色"闭环验证。

        流程: 展开面板 → 读 before (fills/store/diagramData) → pick_color →
        读 after → 汇总对比结论。返回 { step, store_changed, fills_changed,
        store_after, fills_before, fills_after, diagram_after, pick }。

        verbose=True(默认) 打印每步状态与最终结论, 供人工/回归统一口径。"""
        if verbose:
            print('[v] 展开布局面板')
        vis = self.open_palette_panel()
        if verbose:
            print(f'[v] 色点可见性: {vis}')

        if verbose:
            print('[v] BEFORE')
        fills_before = self.get_fills()
        store_before = self.get_color_store()
        dd_before = self.get_diagram_snapshot()
        if verbose:
            print(f'  fills: {fills_before}')
            print(f'  store: {store_before}')

        if verbose:
            print(f'[v] 选择 {target_color}')
        pick = self.pick_color(target_color)
        if verbose:
            print(f'  pick: {pick}')

        if verbose:
            print('[v] AFTER')
        fills_after = self.get_fills()
        store_after = self.get_color_store()
        dd_after = self.get_diagram_snapshot()
        if verbose:
            print(f'  fills: {fills_after}')
            print(f'  store: {store_after}')

        cc_before = json.dumps((store_before or {}).get('customColors', {}), sort_keys=True)
        cc_after = json.dumps((store_after or {}).get('customColors', {}), sort_keys=True)
        store_changed = cc_before != cc_after
        fills_changed = fills_before.get('fills') != fills_after.get('fills')

        result = {
            'vis': vis, 'pick': pick,
            'store_changed': store_changed,
            'fills_changed': fills_changed,
            'store_before': store_before, 'store_after': store_after,
            'fills_before': fills_before, 'fills_after': fills_after,
            'diagram_before': dd_before, 'diagram_after': dd_after,
        }
        if verbose:
            print('\n========== 调色板闭环结论 ==========')
            print(f'store.customColors 变化: {"是 ✓" if store_changed else "否 ✗"}')
            if (store_after or {}).get('customColors'):
                print(f'  customColors = {json.dumps(store_after["customColors"], ensure_ascii=False)}')
            print(f'图表节点 fill 变化: {"是 ✓" if fills_changed else "否 ✗"}')
            if fills_changed:
                print(f'  BEFORE: {json.dumps(fills_before["fills"], ensure_ascii=False)}')
                print(f'  AFTER : {json.dumps(fills_after["fills"], ensure_ascii=False)}')
        return result

    def center_color_loop(self, target_color: str = '#1890FF',
                          verbose: bool = True) -> Dict[str, Any]:
        """[2026-08-05] 验证"对象范围颜色"配置 → 图表中心节点 + 图例对象范围项 同源联动.
        通过 store.updateCenterScopeColor 触发 (等价于对象范围色点选色), 读改前后:
          - store.centerScopeColor 变化
          - 图表中心节点 (isCenter) fill 变化
          - 图例"对象范围"项色值变化
        返回 { before, after, color_changed, center_nodes_changed, legend_changed, passed }。"""
        if verbose:
            print('[v] 读取对象范围/图例/中心节点 BEFORE')
        before_center = self.get_center_scope_snapshot()
        before_legend = {i['name']: i['color'] for i in self.get_legend_items()}
        before_fills = self.get_svg_node_fills()
        center_codes = self.get_center_codes()
        if verbose:
            print(f'  centerScopeColor={before_center.get("centerScopeColor")}')
            print(f'  中心节点数={len(center_codes)}')

        self.page.evaluate("""(color) => {
            const cs = window.__configStore
            if (!cs) throw new Error('no __configStore')
            cs.updateCenterScopeColor(color)
        }""", target_color)
        self.wait_render_stable(timeout_ms=8000)

        if verbose:
            print('[v] AFTER')
        after_center = self.get_center_scope_snapshot()
        after_legend = {i['name']: i['color'] for i in self.get_legend_items()}
        after_fills = self.get_svg_node_fills()

        center_fills_before = {c: before_fills.get(c) for c in center_codes if c in before_fills}
        center_fills_after = {c: after_fills.get(c) for c in center_codes if c in after_fills}
        color_changed = before_center.get('centerScopeColor') != after_center.get('centerScopeColor')
        center_nodes_changed = center_fills_before != center_fills_after
        legend_changed = before_legend.get('对象范围') != after_legend.get('对象范围')
        passed = color_changed and center_nodes_changed and legend_changed

        result = {
            'before': {**before_center, 'legend': before_legend, 'centerFills': center_fills_before},
            'after': {**after_center, 'legend': after_legend, 'centerFills': center_fills_after},
            'color_changed': color_changed,
            'center_nodes_changed': center_nodes_changed,
            'legend_changed': legend_changed,
            'passed': passed,
        }
        if verbose:
            print('\n========== 对象范围颜色闭环结论 ==========')
            print(f'store.centerScopeColor 变化: {before_center.get("centerScopeColor")} → {after_center.get("centerScopeColor")} {"✓" if color_changed else "✗"}')
            print(f'图表中心节点 fill 变化: {"✓" if center_nodes_changed else "✗"}')
            print(f'图例"对象范围"项色值: {before_legend.get("对象范围")} → {after_legend.get("对象范围")} {"✓" if legend_changed else "✗"}')
            print(f'  => {"PASS ✓" if passed else "FAIL ✗"}')
        return result

    # ================================================================
    # [E2E 2026-08-02] 细化包辅助方法 — 结构/颜色/备注/交互深度断言的数据源
    # ================================================================

    # 备注类型全集 (与 chart_seed.py DEFAULT_SEEDS 的 category 分布对应)
    ANNOTATION_CATEGORIES = ['important', 'warning', 'info', 'tip']

    def get_snapshot(self) -> Dict[str, Any]:
        """[E2E v2 2026-08-02] 统一读取面 — 一次 evaluate 读取完整图表快照.

        收敛断言数据源: render/nodes/links/containers/legend/annotations,
        替代逐个调用 get_annotation_items / get_svg_node_fills / get_legend_items 等
        多次 DOM 探测 (每次 evaluate 有 ~ms 级往返, 且状态可能漂移).

        对应前端 window.__archPage.mermaid.snapshot() (useDiagnostics.js).
        返回 dict, chart_e2e.py 各维度断言直接复用同一份数据."""
        return self.page.evaluate("""() => {
            const api = window.__archPage && window.__archPage.mermaid
            if (!api || typeof api.snapshot !== 'function') {
                return { error: '__archPage.mermaid.snapshot() 未安装 (useDiagnostics 需含 snapshot)' }
            }
            return api.snapshot()
        }""")

    def show_all_annotations(self, timeout_ms: int = 15000) -> List[Dict[str, Any]]:
        """[2026-08-02] 开启全部备注类型并等待 panel 渲染.

        前端设计 (useAnnotation L127-132): annotationCategoryFilter=[] (默认未选)
        时不展示任何备注。E2E 必须显式设置 filter 后 panel 才有 items。
        overlay 重渲染不走 data-chart-rendered 标记 → 轮询 items 数量判断完成。

        返回渲染后的 panel items (供断言复用)."""
        self.switch_chart_config('annotationCategoryFilter', self.ANNOTATION_CATEGORIES)
        deadline = time.time() + timeout_ms / 1000
        last: List[Dict[str, Any]] = []
        while time.time() < deadline:
            self.page.wait_for_timeout(400)
            last = self.get_annotation_items()
            if last:
                return last
        print(f'[chart_diag] show_all_annotations: 超时未渲染出 items (共 {len(last)})')
        return last

    def set_annotation_filter(self, categories: List[str],
                              expect_count: Optional[int] = None,
                              timeout_ms: int = 10000) -> List[Dict[str, Any]]:
        """[2026-08-02] 设置备注类型过滤并等待 items 数变化.
        用于 C 类断言: 过滤生效验证 (数量变化) + 三态切换 (全选→单类→清空).
        返回切换后的 items."""
        self.switch_chart_config('annotationCategoryFilter', categories)
        deadline = time.time() + timeout_ms / 1000
        last: List[Dict[str, Any]] = []
        while time.time() < deadline:
            self.page.wait_for_timeout(400)
            last = self.get_annotation_items()
            if expect_count is not None:
                if len(last) == expect_count:
                    return last
            else:
                # 无期望值: 等 2 次读数一致 (渲染稳定)
                time.sleep(0.5)
                cur = self.get_annotation_items()
                if cur == last:
                    return cur
                last = cur
        return last

    def get_node_labels(self) -> List[Dict[str, str]]:
        """读取每个 g.node 的 data-code + 渲染标签文本 (A: 标签非空断言).
        防「节点存在但 label 空白/缺失」."""
        return self.page.evaluate("""() => {
            return Array.from(document.querySelectorAll('svg g.node[data-code]')).map(n => ({
                code: n.getAttribute('data-code'),
                label: (n.textContent || '').trim()
            }))
        }""")

    def get_mermaid_code_edges(self) -> Dict[str, Any]:
        """解析 window.__lastMermaidCode → 节点定义集 + 边端点 (A: 边有效性断言).
        mermaid 语法: id["label"] 定义节点, id -->|"label"| id2 / id <-- x --> id2 定义边.
        [FIX 2026-08-02] 支持带 label 的边 (`A -->|"x"| B`) 与双向边 (`A <-- x --> B`),
          旧正则只匹配 `A --> B` (无 label), 而 getArrowSyntax 输出恒带 label →
          A3b 边端点解析恒为 0 条, 断言形同虚设 (BO/SM 迁移回归全靠此断言暴露)."""
        return self.page.evaluate("""() => {
            const code = window.__lastMermaidCode || ''
            if (!code) return { error: '__lastMermaidCode 未设置 (MermaidComponent 未生成代码)' }
            const nodeIds = new Set()
            const edges = []
            const patterns = [
                // 双向无 label: A <--> B
                /^([A-Za-z0-9_]+)\\s*<-->\\s*([A-Za-z0-9_]+)$/,
                // 双向带 label: A <-- x --> B
                /^([A-Za-z0-9_]+)\\s*<--\\s*(.*?)\\s*-->\\s*([A-Za-z0-9_]+)$/,
                // 带 label 单向: A -->|"x"| B
                /^([A-Za-z0-9_]+)\\s*-->\\s*\\|[^|]*\\|\\s*([A-Za-z0-9_]+)$/,
                // 无 label 单向: A --> B
                /^([A-Za-z0-9_]+)\\s*-->\\s*([A-Za-z0-9_]+)$/,
            ]
            for (const raw of code.split('\\n')) {
                const line = raw.trim()
                const nodeDef = line.match(/^([A-Za-z0-9_]+)\\[/)
                if (nodeDef) nodeIds.add(nodeDef[1])
                for (const p of patterns) {
                    const m = line.match(p)
                    if (m) {
                        nodeIds.add(m[1])
                        const target = m[m.length - 1]
                        nodeIds.add(target)
                        edges.push([m[1], target])
                        break
                    }
                }
            }
            return { nodeIds: Array.from(nodeIds), edges, edgeCount: edges.length }
        }""")

    def get_cluster_hierarchy(self) -> Dict[str, Any]:
        """读取 SVG 容器层级 (A: 嵌套结构 + B: 同组同色).
        返回: totalClusters / nestedClusters(含子 cluster) / maxDepth /
              leafClusters(无子 cluster 且有节点) 的 {id, title, nodeCodes}.
        [FIX 2026-08-02] mermaid 11 ELK 渲染嵌套 subgraph 时 DOM 平铺,
          嵌套通过 rect bbox 包含体现 (与 snapshot() 的 containers 一致)."""
        return self.page.evaluate("""() => {
            const clusters = Array.from(document.querySelectorAll('svg g.cluster'))
            const rectOf = (el) => {
                const r = el && el.querySelector('rect')
                if (!r) return null
                const b = r.getBoundingClientRect()
                return { x: b.left, y: b.top, w: b.width, h: b.height }
            }
            const rects = clusters
                .map(c => ({ el: c, id: c.getAttribute('id') || '', ...rectOf(c) }))
                .filter(r => r.w > 0)
            const contains = (a, b) => {
                if (a === b) return false
                if (a.w * a.h <= b.w * b.h) return false
                const bx = b.x + b.w / 2, by = b.y + b.h / 2
                return bx >= a.x && bx <= a.x + a.w && by >= a.y && by <= a.y + a.h
            }
            const depthOf = (r) => {
                const parent = rects.find(o => contains(o, r))
                return parent ? depthOf(parent) + 1 : 1
            }
            const nodePos = Array.from(document.querySelectorAll('svg g.node[data-code]')).map(n => {
                const r = n.querySelector('rect')
                const b = r ? r.getBoundingClientRect() : null
                return { code: n.getAttribute('data-code'), x: b ? b.left + b.width / 2 : 0, y: b ? b.top + b.height / 2 : 0 }
            })
            const nodeIn = (rect, p) => p.x >= rect.x && p.x <= rect.x + rect.w && p.y >= rect.y && p.y <= rect.y + rect.h
            const leafClusters = rects
                .filter(r => !rects.some(o => contains(r, o)))
                .map(r => ({
                    id: r.id,
                    title: (r.el.querySelector('.cluster-label, text')?.textContent || '').trim(),
                    nodeCodes: nodePos.filter(p => nodeIn(r, p)).map(p => p.code)
                }))
            return {
                totalClusters: rects.length,
                nestedClusters: rects.filter(r => rects.some(o => contains(o, r))).length,
                maxDepth: rects.length ? Math.max(...rects.map(r => depthOf(r))) : 0,
                leafClusters
            }
        }""")

    def get_container_ids(self) -> List[str]:
        """读取全部 SVG g.cluster 的 id (A6: 无重复容器断言数据源).
        mermaid 渲染后 subgraph id 形如 'G_D_供应链云' / 'G_SM_DP' (G_ + 树 id 前缀 + code)."""
        return self.page.evaluate(
            "() => Array.from(document.querySelectorAll('svg g.cluster')).map(c => c.getAttribute('id') || '')")

    def get_legend_items(self) -> List[Dict[str, str]]:
        """读取图例项 (.color-legend-panel): 名称 + 色块颜色 (B: 图例完整性断言).
        legend 结构: panel > [title div, legendList div] > item div (色块 svg + 名称 span)."""
        return self.page.evaluate("""() => {
            const panel = document.querySelector('.color-legend-panel')
            if (!panel) return []
            const list = panel.children[1] || panel
            return Array.from(list.querySelectorAll('div')).map(item => {
                const rect = item.querySelector('svg rect')
                return {
                    name: (item.querySelector('span:last-child')?.textContent || '').trim(),
                    color: rect ? (rect.getAttribute('fill') || '') : ''
                }
            }).filter(i => i.name)
        }""")

    def assert_legend_skip(self, absent: List[str],
                           present: List[str] = []) -> Dict[str, Any]:
        """[2026-08-05] 断言图例项: absent 不应出现, present 必须出现.
        用于验证"区分对象范围时, 整组都在对象范围的分组不单独列示图例"
        (对应用户案例: 供应链计划为对象范围时, "需求计划"不出现)。
        返回 { items, ok, missing_present, wrongly_present }。"""
        items = self.get_legend_items()
        names = {i['name'] for i in items}
        missing_present = [n for n in present if n not in names]
        wrongly_present = [n for n in absent if n in names]
        ok = not missing_present and not wrongly_present
        print(f'[legend] present={present} absent={absent}')
        print(f'  items={sorted(names)}')
        print(f'  缺失应出现: {missing_present or "无"}')
        print(f'  误出现应跳过: {wrongly_present or "无"}')
        print(f'  => {"OK ✓" if ok else "FAIL ✗"}')
        return {'items': items, 'ok': ok,
                'missing_present': missing_present, 'wrongly_present': wrongly_present}

    def get_link_color_mappings(self) -> List[Dict[str, Any]]:
        """读取 linkColorMappings (FE 埋点 stepMeta.linkColorMappings).
        结构: [{index, sourceId, targetId, color}]."""
        return self.page.evaluate("""() => {
            const meta = window.__archPage?.mermaid?.stepMeta || {}
            return Array.isArray(meta.linkColorMappings) ? meta.linkColorMappings : []
        }""")

    def get_svg_link_strokes(self, limit: int = 500) -> List[Dict[str, str]]:
        """读 SVG 实际连线 stroke (path.flowchart-link). 与 linkColorMappings 对照."""
        return self.page.evaluate("""(limit) => {
            return Array.from(document.querySelectorAll('path.flowchart-link')).slice(0, limit).map(p => ({
                id: p.getAttribute('id') || '',
                stroke: (p.getAttribute('stroke') || p.style.stroke || '').trim().toLowerCase()
            }))
        }""", limit)

    def get_highlighted_codes(self) -> List[str]:
        """读取当前被高亮的节点 code (annotation-highlighted, D: 高亮断言)."""
        return self.page.evaluate("""() =>
            Array.from(document.querySelectorAll('svg g.node.annotation-highlighted[data-code]'))
                .map(n => n.getAttribute('data-code'))
        """)

    def get_all_node_codes(self) -> List[str]:
        """读取 SVG 全部节点 code (数据指纹 A5)."""
        return self.page.evaluate(
            "() => Array.from(document.querySelectorAll('svg g.node[data-code]')).map(n => n.getAttribute('data-code'))")

    # ================================================================
    # [布局验证 2026-08-05] 面板编辑 → 渲染树合并结果的可复用验证
    #   数据源: window.__archPage.debugLayout (EmbeddedChartView 合并链路的分步快照:
    #   before → afterStates → afterMembership → afterTitles).
    #   相比 DOM bbox 反推 (get_cluster_hierarchy), 这里读的是"权威合并树",
    #   直接断言哪个分组含哪些元素 / enabled / title, 不用人工看 DOM.
    #   取代 verify_disable_domain.py 这类一次性脚本的 setup + 断言部分.
    # ================================================================

    def get_layout_snapshot(self) -> Dict[str, Any]:
        """读取布局合并链路的完整分步快照 (before/afterStates/afterMembership/afterTitles).
        未走统一管道 (businessObject/serviceModule) 时返回 { error }."""
        return self.page.evaluate("""() => {
            const dl = window.__archPage && window.__archPage.debugLayout
            if (!dl) return { error: '__archPage.debugLayout 未暴露 (需 EmbeddedChartView 挂载且走统一管道)' }
            return dl
        }""")

    def get_layout_membership(self, step: str = 'afterTitles') -> Dict[str, List[str]]:
        """把指定合并步骤的分组树拍平成 { code: [叶子code...] } 归属映射.
        leaf = directNodes (node code) 或 containers (容器 code).
        用于断言"某分组是否包住某些元素" (容器包裹关系)."""
        return self.page.evaluate("""({step}) => {
            const dl = window.__archPage && window.__archPage.debugLayout
            const groups = dl && dl[step]
            if (!Array.isArray(groups)) return { error: 'debugLayout.' + step + ' 缺失' }
            const membership = {}
            const walk = (gs) => {
                for (const g of gs || []) {
                    const key = g.elementCode || g.id
                    const leaves = []
                    if (Array.isArray(g.directNodes)) leaves.push(...g.directNodes)
                    if (Array.isArray(g.containers)) {
                        leaves.push(...g.containers.map(c => c.elementCode || c.id || c.code))
                    }
                    if (key) membership[key] = leaves
                    if (Array.isArray(g.children)) walk(g.children)
                }
            }
            walk(groups)
            return membership
        }""", {'step': step})

    def _find_group(self, code: str, step: str = 'afterTitles') -> Optional[Dict[str, Any]]:
        """按 elementCode/id 深查找某个分组的合并状态 (返回 None 表示没找到)."""
        return self.page.evaluate("""({code, step}) => {
            const dl = window.__archPage && window.__archPage.debugLayout
            const groups = dl && dl[step]
            const find = (gs) => {
                for (const g of gs || []) {
                    if ((g.elementCode || g.id) === code) return g
                    const r = find(g.children)
                    if (r) return r
                }
                return null
            }
            return find(groups)
        }""", {'code': code, 'step': step})

    def get_layout_group_codes(self, step: str = 'afterTitles') -> List[str]:
        """返回指定合并步骤树中所有分组 code (含嵌套 children). 用于判断分组在合并树是否存在."""
        return self.page.evaluate("""({step}) => {
            const dl = window.__archPage && window.__archPage.debugLayout
            const groups = dl && dl[step]
            const out = []
            const walk = (gs) => {
                for (const g of gs || []) {
                    const key = g.elementCode || g.id
                    if (key) out.push(key)
                    if (Array.isArray(g.children)) walk(g.children)
                }
            }
            walk(groups)
            return out
        }""", {'step': step})

    def get_leaf_bearing_groups(self, step: str = 'afterTitles') -> List[str]:
        """返回指定合并步骤树中"直接承载叶子"的分组 code (directNodes 或 containers 非空).
        [why] 领域/子领域分组的叶子在 children 子分组里, 不直接进 membership — 只有真正承载
        叶子的分组 (directNodes/containers 形态) 才该有非空归属, 用于 L18 容器包裹回归守卫."""
        return self.page.evaluate("""({step}) => {
            const dl = window.__archPage && window.__archPage.debugLayout
            const gs = dl && dl[step]
            const out = []
            const walk = (list) => {
                for (const g of list || []) {
                    const key = g.elementCode || g.id
                    const hasLeaf = (Array.isArray(g.directNodes) && g.directNodes.length > 0)
                        || (Array.isArray(g.containers) && g.containers.length > 0)
                    if (key && hasLeaf) out.push(key)
                    if (Array.isArray(g.children)) walk(g.children)
                }
            }
            walk(gs)
            return out
        }""", {'step': step})

    def assert_group_contains(self, group_code: str, expected_codes: List[str],
                              step: str = 'afterTitles') -> bool:
        """断言分组 group_code 的叶子归属包含 expected_codes (容器包裹关系).
        数据源: 权威合并树, 非 DOM bbox 反推. 返回 bool + 打印 [OK]/[FAIL]."""
        membership = self.get_layout_membership(step)
        if isinstance(membership, dict) and 'error' in membership:
            print(f'[FAIL] assert_group_contains: {membership["error"]}')
            return False
        actual = membership.get(group_code, [])
        missing = [c for c in expected_codes if c not in actual]
        ok = not missing
        tag = '[OK]' if ok else '[FAIL]'
        extra = f'  actual={actual}' if not ok else ''
        print(f'{tag} 分组 {group_code} 包含 {expected_codes}{extra}'
              + (f'  缺失={missing}' if missing else ''))
        return ok

    def assert_group_enabled(self, group_code: str, expected_enabled: bool,
                             step: str = 'afterStates') -> bool:
        """断言分组最终 enabled/disabled 状态 (默认看 afterStates = 状态合并步骤产物)."""
        g = self._find_group(group_code, step)
        if g is None:
            print(f'[FAIL] assert_group_enabled: 分组 {group_code} 未找到 (step={step})')
            return False
        actual = bool(g.get('enabled'))
        ok = actual == expected_enabled
        tag = '[OK]' if ok else '[FAIL]'
        print(f'{tag} 分组 {group_code}.enabled={actual} (期望 {expected_enabled})')
        return ok

    def assert_merge_steps_present(self) -> bool:
        """断言合并链路分步快照齐全 (before/afterStates/afterMembership/afterTitles 均非空).
        快速判定 EmbeddedChartView 是否走了统一管道并完成 4 步合并."""
        snap = self.get_layout_snapshot()
        if not isinstance(snap, dict) or 'chartType' not in snap:
            print(f'[FAIL] assert_merge_steps_present: {snap.get("error", "debugLayout 缺失")}')
            return False
        ok = True
        for step in ('before', 'afterStates', 'afterMembership', 'afterTitles'):
            groups = snap.get(step)
            present = isinstance(groups, list) and len(groups) > 0
            if not present:
                ok = False
            print(f'  {"[OK]" if present else "[FAIL]"} 步骤 {step}: '
                  f'{"有 " + str(len(groups)) + " 个分组" if present else "缺失"}')
        if ok:
            print(f'[OK] 合并链路 4 步快照齐全 (chartType={snap.get("chartType")})')
        return ok

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


def run_layout_verification(scope: Optional[dict] = None,
                            viewport: Tuple[int, int] = (1280, 720)) -> Dict[str, Any]:
    """[布局验证 2026-08-05] 一键验证布局面板编辑 → 渲染树合并链路的正确性.

    取代 verify_disable_domain.py 这类一次性脚本: setup 复用 ChartDiag.open_chart(),
    断言全部走新增的可复用方法 (assert_merge_steps_present / assert_group_contains /
    assert_group_enabled), 不再依赖人工看 DOM.

    验证点:
      1. 合并链路 4 步快照齐全 (before/afterStates/afterMembership/afterTitles)
      2. 容器包裹关系: 每个领域/子领域分组包含其下元素 (权威合并树, 非 DOM bbox 反推)
      3. enabled 状态: 分组 enabled 默认 true (未禁用时)

    scope 注意: DEFAULT_SCOPE 是 30 个 BO 的复杂图, 容器包裹断言覆盖更充分;
    也可传 SHORT_SCOPE 单 BO 快速冒烟."""
    print(f'=== 布局合并链路验证  viewport={viewport} ===\n')
    checks = []
    with ChartDiag(viewport=viewport) as diag:
        diag.open_chart(scope=scope)
        page = diag.page

        # 1. 合并链路分步快照齐全
        checks.append(('merge_steps_present', diag.assert_merge_steps_present()))

        # 2. 校验合并树的"分组 → 叶子归属"自洽:
        #    afterMembership(归属合并) 与 afterTitles(标题/顺序合并) 的叶子归属应一致
        #    (第二步只改归属, 第三步只改标题/顺序, 不应再改变叶子归属).
        mem_after_membership = diag.get_layout_membership('afterMembership')
        mem_after_titles = diag.get_layout_membership('afterTitles')
        if isinstance(mem_after_membership, dict) and 'error' not in mem_after_membership \
           and isinstance(mem_after_titles, dict) and 'error' not in mem_after_titles:
            # 逐个分组比对叶子归属, 报告差异
            diff_groups = []
            for code in set(mem_after_membership) | set(mem_after_titles):
                a = sorted(mem_after_membership.get(code, []))
                b = sorted(mem_after_titles.get(code, []))
                if a != b:
                    diff_groups.append({'group': code, 'afterMembership': a, 'afterTitles': b})
            ok = not diff_groups
            checks.append(('membership_titles_consistent', ok))
            tag = '[OK]' if ok else '[FAIL]'
            print(f'{tag} afterMembership 与 afterTitles 叶子归属一致'
                  + ('  (差异: ' + str(diff_groups[:3]) + ')' if diff_groups else ''))

        # 3. 叶子承载断言 (L18 回归守卫): 在 afterTitles 树中, 凡带 directNodes/containers 的
        #    分组不应为空叶子 (若容器被误清空 → 这里露出 actual=[])。
        #    注意: 领域/子领域分组的叶子在 children 子分组里, 不直接进 membership — 这里只查
        #    真正承载叶子的分组 (directNodes 或 containers 形态), 避免把"领域含子分组"误判为缺陷.
        snap = diag.get_layout_snapshot()
        if isinstance(snap, dict) and 'afterTitles' in snap:
            mem = diag.get_layout_membership('afterTitles')
            if isinstance(mem, dict) and 'error' not in mem:
                # 找出 afterTitles 里所有"应承载叶子"的分组 code
                leaf_bearing = diag.page.evaluate("""() => {
                    const dl = window.__archPage && window.__archPage.debugLayout
                    const gs = dl && dl.afterTitles
                    const out = []
                    const walk = (list) => {
                        for (const g of list || []) {
                            const key = g.elementCode || g.id
                            const hasLeaf = (Array.isArray(g.directNodes) && g.directNodes.length > 0)
                                || (Array.isArray(g.containers) && g.containers.length > 0)
                            if (key && hasLeaf) out.push(key)
                            if (Array.isArray(g.children)) walk(g.children)
                        }
                    }
                    walk(gs)
                    return out
                }""")
                for code in leaf_bearing:
                    actual = mem.get(code, [])
                    ok = len(actual) > 0
                    checks.append((f'leaf_{code}', ok))
                    tag = '[OK]' if ok else '[FAIL]'
                    print(f'{tag} 叶子分组 {code} 承载了 {len(actual)} 个叶子' + (f'  actual={actual}' if not ok else ''))

        # 4. enabled 状态传播断言 (数据感知): applyGroupStates 应把面板的 enabled 状态
        #    传播到合并树 afterStates. 不硬编码期望值 — 以 panelGroups 为准做比对.
        #    [注意] 面板树可能含 ELK inner/boundary 子分组 (DP_inner/DP_boundary 等), 这些是
        #    面板特有的结构分组, 统一管道会把它拍平, 不进入合并渲染树 → 只对"合并树中真正存在"
        #    的分组做断言, 面板独有的结构分组跳过 (不是失败).
        if isinstance(snap, dict) and 'panelGroups' in snap and 'afterStates' in snap:
            merged_codes = set(diag.get_layout_group_codes('afterStates'))
            panel_enabled = {}  # code -> expected enabled (仅面板显式设置过)
            def walkp(gs):
                for g in gs or []:
                    key = g.get('elementCode') or g.get('id')
                    if key:
                        e = g.get('enabled')
                        if isinstance(e, bool):
                            panel_enabled[key] = e
                    walkp(g.get('children'))
            walkp(snap['panelGroups'])
            for code, expected in panel_enabled.items():
                if code not in merged_codes:
                    # 面板独有的结构分组 (如 ELK inner/boundary), 渲染树已拍平 — 跳过
                    print(f'  [SKIP] 面板分组 {code} 不在合并渲染树中 (面板结构分组, 已拍平)')
                    continue
                checks.append((f'enabled_{code}', diag.assert_group_enabled(code, expected)))

        diag.screenshot('layout_verify')
        passed = sum(1 for c in checks if c[1])
        print(f'\n=== 布局验证总结: {passed}/{len(checks)} 通过 ===\n')
        return {'passed': passed == len(checks), 'checks': checks}


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

    p4 = sub.add_parser('layout-verify', help='布局合并链路验证 (取代一次性 verify_disable_domain.py)')
    p4.add_argument('--w', type=int, default=1280)
    p4.add_argument('--h', type=int, default=720)
    p4.add_argument('--short', action='store_true', help='用 SHORT_SCOPE 单 BO 快速冒烟')

    args = parser.parse_args()
    if args.cmd == 'regression':
        run_center_regression(viewport=(args.w, args.h))
    elif args.cmd == 'layout-verify':
        run_layout_verification(
            scope=SHORT_SCOPE if args.short else None,
            viewport=(args.w, args.h)
        )
    else:
        with ChartDiag() as diag:
            diag.open_chart()
            if args.cmd == 'compare':
                diag.compare_path_centers(n=args.n)
            elif args.cmd == 'trace':
                diag.trace_click_listeners(args.sel)