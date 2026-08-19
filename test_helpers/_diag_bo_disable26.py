# -*- coding: utf-8 -*-
"""验证 v26: 组合修复最终验证 - 禁用服务模块/子领域 + 节点完整性 + 恢复"""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
errs = []
cli = PlaywrightCLI()
page = cli._ensure_browser()
page.on('pageerror', lambda e: errs.append(str(e)[:300]))

page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until='domcontentloaded', timeout=15000)
page.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP&mode=debug",
          wait_until='domcontentloaded', timeout=20000)
for _ in range(12):
    time.sleep(2)
    if page.evaluate("() => !!document.querySelector('.mermaid svg')"):
        break
print('SVG ready')
page.evaluate("() => window.__archPage?.debug?.setExpandLevel('businessObject')")
time.sleep(4)

def svg_stats():
    return page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        if (!svg) return { svg: false }
        const nodes = Array.from(svg.querySelectorAll('g.node')).filter(e => e.style.display !== 'none')
        return { total: nodes.length, clusters: svg.querySelectorAll('g.cluster').length }
    }""")

def mutate_panel(fn_src):
    return page.evaluate("""(fnSrc) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        if (!lc || !lc.groups) return 'no layoutControl'
        const copy = JSON.parse(JSON.stringify(lc))
        const fn = new Function('copy', 'return (' + fnSrc + ')(copy)')
        const res = fn(copy)
        Object.assign(window.__archPage.chartConfig.layoutControl, copy)
        return res
    }""", fn_src)

def set_group_enabled(code, enabled):
    return mutate_panel("""({code, enabled}) => (copy) => {
        function walk(list) {
            for (const g of list || []) {
                if ((g.elementCode || g.id) === code) { g.enabled = enabled; return 'set ' + code + '=' + enabled }
                const r = walk(g.children); if (r) return r
            }
            return null
        }
        return walk(copy.groups)
    }""") if False else page.evaluate("""({code, enabled}) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        const copy = JSON.parse(JSON.stringify(lc))
        let hit = 0
        function walk(list) {
            for (const g of list || []) {
                if ((g.elementCode || g.id) === code) { g.enabled = enabled; hit++ }
                walk(g.children)
            }
        }
        walk(copy.groups)
        Object.assign(window.__archPage.chartConfig.layoutControl, copy)
        return 'hit=' + hit
    }""", {'code': code, 'enabled': enabled})

print('初始:', json.dumps(svg_stats(), ensure_ascii=False))

print('\n[1] 禁用服务模块 DP')
print('  ', set_group_enabled('DP', False)); time.sleep(6)
print('  禁用后:', json.dumps(svg_stats(), ensure_ascii=False))
print('  [恢复]', set_group_enabled('DP', True)); time.sleep(6)
print('  恢复后:', json.dumps(svg_stats(), ensure_ascii=False))

print('\n[2] 禁用子领域 SCP')
print('  ', set_group_enabled('SCP', False)); time.sleep(6)
print('  禁用后:', json.dumps(svg_stats(), ensure_ascii=False))
print('  [恢复]', set_group_enabled('SCP', True)); time.sleep(6)
print('  恢复后:', json.dumps(svg_stats(), ensure_ascii=False))

print('\n[3] 禁用领域 SCM')
print('  ', set_group_enabled('SCM', False)); time.sleep(6)
print('  禁用后:', json.dumps(svg_stats(), ensure_ascii=False))
print('  [恢复]', set_group_enabled('SCM', True)); time.sleep(6)
print('  恢复后:', json.dumps(svg_stats(), ensure_ascii=False))

print('\nerrors:', errs[:5])
cli.close()
