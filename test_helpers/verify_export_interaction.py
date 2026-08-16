"""可复用: 导出 HTML 连线交互验证 (高亮/淡化/标签热点) — 2026-08-16 优化后的标准验证入口

背景: 当前后端数据在标准测试范围(SCP/PLAM)下 links=0, 无真实连线;
      因此本探针用「合成连线注入」验证导出 HTML 的连线交互逻辑:
        - 点击连线标签文字(span.edgeLabel) → 触发连线高亮 (标签热点)
        - 点击连线 path → 高亮该线 + 其余线淡化 (透明度/箭头)
      使用 2026-08-16 新增钩子, 免去下载/加载链路:
        - await __archPage.exportHtmlFull()   → 直接取导出 HTML 字符串
        - 导出页 window.__exportHl.snapshot() → 一条 evaluate 读连线/高亮状态
      用法: python test_helpers/verify_export_interaction.py
"""
import sys, os, time, json, tempfile
sys.path.insert(0, 'd:/filework/excel-to-diagram')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from test_helpers.browser_auth_cli import PlaywrightCLI
from test_helpers.env_preflight import FRONTEND_URL, preflight

URL = f'{FRONTEND_URL}/system/archdata?preset=scp&mode=debug'
OUT_HTML = os.path.join(tempfile.gettempdir(), 'exported_verify.html')

# 合成连线结构注入 (当前数据无连线, 用标准 mermaid 边结构验证导出交互逻辑)
INJECT_SCRIPT = """() => {
  const svg = document.querySelector('.mermaid svg');
  let defs = svg.querySelector('defs');
  if (!defs) { defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs'); svg.appendChild(defs); }
  if (!defs.querySelector('#arrowhead-abc')) {
    const m = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    m.setAttribute('id', 'arrowhead-abc'); m.setAttribute('markerWidth', '10'); m.setAttribute('markerHeight', '10');
    m.setAttribute('refX', '9'); m.setAttribute('refY', '5'); m.setAttribute('orient', 'auto');
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', 'M0,0 L10,5 L0,10 z'); p.setAttribute('fill', '#1890ff');
    m.appendChild(p); defs.appendChild(m);
  }
  const addNode = (code, x, y) => {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'node'); g.setAttribute('data-code', code); g.setAttribute('transform', 'translate(' + x + ',' + y + ')');
    const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r.setAttribute('width', '80'); r.setAttribute('height', '30'); r.setAttribute('fill', '#fff');
    const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.textContent = code; t.setAttribute('x', '40'); t.setAttribute('y', '20'); t.setAttribute('text-anchor', 'middle');
    g.appendChild(r); g.appendChild(t); svg.appendChild(g);
  };
  addNode('AAA', 50, 200); addNode('BBB', 250, 200); addNode('CCC', 500, 200);
  let edges = svg.querySelector('g.edges.edgePaths') || svg.querySelector('g.edges');
  if (!edges) { edges = document.createElementNS('http://www.w3.org/2000/svg', 'g'); edges.setAttribute('class', 'edges edgePaths'); svg.appendChild(edges); }
  const addPath = (d, labelText) => {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('class', 'flowchart-link'); p.setAttribute('d', d);
    p.setAttribute('marker-end', 'url(#arrowhead-abc)'); p.setAttribute('fill', 'none');
    p.setAttribute('stroke', '#1890ff'); p.setAttribute('stroke-width', '2');
    edges.appendChild(p);
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'edgeLabel');
    const fo = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
    fo.setAttribute('x', '100'); fo.setAttribute('y', '80'); fo.setAttribute('width', '120'); fo.setAttribute('height', '30');
    const div = document.createElement('div'); div.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml');
    const span = document.createElement('span'); span.setAttribute('class', 'edgeLabel'); span.textContent = labelText;
    div.appendChild(span); fo.appendChild(div); g.appendChild(fo);
    const gls = svg.querySelector('g.edgeLabels');
    if (gls) gls.appendChild(g); else svg.appendChild(g);
    g.setAttribute('transform', 'translate(120,100)');
  };
  addPath('M130 215 L250 215', 'AAA-BBB');
  addPath('M330 215 L500 215', 'BBB-CCC');
  return { ok: true };
}"""

def main():
    preflight(require_backend=True)
    cli = PlaywrightCLI(headless=True)
    fails = []
    try:
        page = cli._ensure_browser()
        page.set_default_timeout(60000)
        page.goto(f'{FRONTEND_URL}/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)
        page.goto(URL, wait_until='domcontentloaded', timeout=15000)
        time.sleep(12)
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            pass
        time.sleep(2)

        # 0) 连线诊断 (标准范围当前数据无连线)
        cl = page.evaluate("() => (window.__archPage && window.__archPage.debug && window.__archPage.debug.chartLinks && window.__archPage.debug.chartLinks()) || {}")
        print('[chartLinks]', json.dumps(cl, ensure_ascii=False))
        if cl.get('links', 0) > 0:
            print('[INFO] 当前数据有真实连线, 可直接验证; 本探针仍用合成注入保证结构完整')

        # 1) 免下载取导出 HTML
        html = page.evaluate("async () => (await window.__archPage.exportHtmlFull()) || ''")
        if not html or len(html) < 1000 or '__exportHl' not in html:
            print('[FAIL] exportHtmlFull 返回异常'); return
        open(OUT_HTML, 'w', encoding='utf-8').write(html)
        print(f'[OK] exportHtmlFull 取到 HTML ({len(html)} bytes)')

        # 2) 加载导出页 + 注入合成连线
        page2 = cli._browser.new_page()
        page2.set_default_timeout(30000)
        page2.goto('file:///' + OUT_HTML.replace('\\', '/'), wait_until='domcontentloaded', timeout=15000)
        page2.wait_for_selector('.mermaid svg', timeout=25000)
        page2.wait_for_timeout(7000)  # 等渲染 + 交互接线(600ms)
        inj = page2.evaluate(INJECT_SCRIPT)
        print('[INJECT]', json.dumps(inj, ensure_ascii=False))

        # 3) 标签文字点击 → 应触发连线高亮 (issue B: 标签热点)
        page2.evaluate("""() => {
          const svg = document.querySelector('.mermaid svg');
          const span = Array.from(svg.querySelectorAll('span.edgeLabel')).find(s => (s.textContent || '').includes('AAA-BBB'));
          if (span) span.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
        }""")
        page2.wait_for_timeout(250)
        s1 = page2.evaluate("() => (window.__exportHl && window.__exportHl.snapshot()) || {}")
        ok_label = s1.get('hlEdge') == 1 and s1.get('hlNode') >= 2 and s1.get('dimLine') == 1
        print('[LABEL-CLICK]', json.dumps(s1, ensure_ascii=False), '=>', 'PASS' if ok_label else 'FAIL')
        if not ok_label: fails.append('label-click')

        # 4) 点击连线 path → 高亮该线 + 另一条淡化 (透明度/箭头)
        page2.evaluate("""() => {
          const svg = document.querySelector('.mermaid svg');
          const p = svg.querySelector('path.flowchart-link');
          if (p) p.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
        }""")
        page2.wait_for_timeout(250)
        s2 = page2.evaluate("""() => ({
          snap: (window.__exportHl && window.__exportHl.snapshot()) || {},
          opacity: (window.__exportHl && window.__exportHl.dimLineOpacity()) || null
        })""")
        ok_path = s2['snap'].get('hlEdge') == 1 and s2['snap'].get('dimLine') == 1
        ok_op = s2.get('opacity') is not None and float(s2['opacity']) <= 0.05
        print('[PATH-CLICK]', json.dumps(s2, ensure_ascii=False), '=>', 'PASS' if (ok_path and ok_op) else 'FAIL')
        if not (ok_path and ok_op): fails.append('path-click/dim')

        print('\n[RESULT]', 'PASS' if not fails else 'FAIL: ' + ', '.join(fails))
    finally:
        cli.close()

if __name__ == '__main__':
    main()
