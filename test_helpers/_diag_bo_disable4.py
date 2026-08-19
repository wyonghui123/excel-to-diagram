# -*- coding: utf-8 -*-
"""诊断 v4: 禁用 BO 后强制 reload (forceRerender), 区分 未触发重渲染 vs 禁用码未生效"""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
errs = []
cli = PlaywrightCLI()
page = cli._ensure_browser()
page.on('pageerror', lambda e: errs.append(str(e)[:300]))

page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until='domcontentloaded', timeout=15000)
page.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP",
          wait_until='domcontentloaded', timeout=20000)
for _ in range(12):
    time.sleep(2)
    if page.evaluate("() => !!document.querySelector('.mermaid svg')"):
        break

# 全展开
for i in range(20):
    r = page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        const agg = Array.from(svg.querySelectorAll('g.node')).find(n => /[\\[【]/.test(n.textContent||''))
        if (!agg) return false
        agg.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, detail: 2 }))
        return true
    }""")
    if not r:
        break
    time.sleep(3)

def has_bo(code):
    return page.evaluate("""(code) => {
        const svg = document.querySelector('.mermaid svg')
        return Array.from(svg.querySelectorAll('g.node')).some(n => (n.textContent||'').endsWith(code))
    }""", code)

print('DP10 present before:', has_bo('DP10'))

# 禁用 DP10 面板叶子
page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    function walk(list) {
        for (const g of list || []) {
            const leaf = (g.containers||[]).find(c => c && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10')
            if (leaf) { leaf.enabled = false; return true }
            if (walk(g.children)) return true
            if (walk(g.containers)) return true
        }
        return false
    }
    return walk(lc?.groups)
}""")
print('DP10 enabled set false')

# 检查 window.__archPage 是否有 reload; 有则调用强制重渲染
has_reload = page.evaluate("() => typeof window.__archPage?.reload === 'function'")
print('has __archPage.reload:', has_reload)
if has_reload:
    page.evaluate("() => window.__archPage.reload()")
    time.sleep(6)
    print('DP10 present after reload:', has_bo('DP10'))
else:
    # 兜底: 触发 generateDiagram
    page.evaluate("() => window.__archPage?.generateDiagram && window.__archPage.generateDiagram()")
    time.sleep(6)
    print('DP10 present after generateDiagram:', has_bo('DP10'))

# 读取布局控制配置里的 disabledBoCodes 是否被收集 (通过 expandState 旁路不可见, 尝试直接查 props)
info = page.evaluate("""() => {
    const svg = document.querySelector('.mermaid svg')
    return {
        nodes: svg ? svg.querySelectorAll('g.node').length : -1,
        names: svg ? Array.from(svg.querySelectorAll('g.node')).map(n=>(n.textContent||'').trim()).slice(0,8) : []
    }
}""")
print('final:', json.dumps(info, ensure_ascii=False, default=str))
print('errors:', errs[:3])
cli.close()
