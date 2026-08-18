# -*- coding: utf-8 -*-
"""验证空对象范围时图表展示 (2026-08-17)

场景:
  A. 空对象范围 (对象+关系都未选) → 图表应显示空态提示, 不渲染全量大图
     (修复前: hasFilter=false 展示全部 BO + 全部关系)
  B. 空对象范围 → 关系范围树只含「对象范围外部」(2026-08-17 修复)
  C. SCP 标准范围 → 图表正常渲染 (不回归)

用法: python test_helpers/verify_scope_classification.py
"""
import sys, time, json, urllib.request
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

for i in range(30):
    try:
        urllib.request.urlopen('http://localhost:3010/api/v1/health', timeout=2)
        break
    except Exception as e:
        if '410' in str(e) or 'GONE' in str(e): break
        time.sleep(1)

cli = PlaywrightCLI()  # headless=True, 避免 sandbox 对 GUI 渲染文件访问限制
page = cli._ensure_browser()
page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="commit", timeout=10000)
time.sleep(2)

BASE = "http://localhost:3004/system/archdata"

# ---------- Part B: 空对象范围 → 关系范围树只含「对象范围外部」 ----------
page.goto(f"{BASE}?productCode=TTTTT000&versionCode=V11", wait_until="networkidle", timeout=60000)
time.sleep(8)
page.evaluate("() => { document.querySelector('.rst-panel-relation')?.querySelector('.collapsible-panel__header')?.click(); }")
time.sleep(6)
b = page.evaluate("""() => {
    const trees = document.querySelectorAll('.el-tree');
    if (trees.length < 2) return {error: 'no RSS tree'};
    const roots = trees[1].querySelectorAll(':scope > .el-tree-node');
    const names = [];
    roots.forEach(r => {
        const label = r.querySelector('.rss-node-label');
        const count = r.querySelector('.rss-node-count');
        names.push((label ? label.textContent.trim() : '') + (count ? count.textContent.trim() : ''));
    });
    return {roots: names};
}""")
print("=== B. 空范围关系树 ===")
print(json.dumps(b, ensure_ascii=False))
b_ok = len(b.get('roots', [])) == 1 and '对象范围外部' in b['roots'][0] and '对象范围内部' not in b['roots'][0]
print('=> PASS' if b_ok else '=> FAIL')

# ---------- Part A: 空对象范围 → 图表空态 (进入图表 → 清空对象范围) ----------
# 注意: URL 直入 view=chart 无 scope 参数会自动全选 3230 (设计行为), 先进入全量图表,
#   然后清空对象范围 → hierarchyFilter 空 → reinit → 应显示空态 (本修复目标).
page.goto(f"{BASE}?productCode=TTTTT000&versionCode=V11&view=chart", wait_until="networkidle", timeout=60000)
time.sleep(12)
pre = page.evaluate("() => window.__archPage?.scopeState || null")
print("pre-clear scopeState:", json.dumps(pre, ensure_ascii=False, default=str))
# 清空对象范围 (对象范围面板 toolbar 的"清空")
cleared = page.evaluate("""() => {
    const panel = document.querySelector('.rst-panel-object');
    if (!panel) return 'no panel';
    const btns = panel.querySelectorAll('button');
    for (const b of btns) { if ((b.textContent || '').includes('清空')) { b.click(); return true; } }
    return 'no clear btn';
}""")
print("clear object scope:", cleared)
time.sleep(10)
diag = page.evaluate("""() => ({
    chartMode: !!document.querySelector('.momp-chart-mode'),
    emptyShown: !!document.querySelector('.embedded-chart-view__empty'),
    emptyText: document.querySelector('.embedded-chart-view__empty')?.innerText?.trim() || '',
    loadingShown: !!document.querySelector('.embedded-chart-view__loading'),
    errorShown: !!document.querySelector('.embedded-chart-view__error'),
    mermaidRendered: !!document.querySelector('.mermaid svg')
})""")
print("=== A. 清空后页面状态 ===")
print(json.dumps(diag, ensure_ascii=False, default=str))
a_scope = page.evaluate("() => window.__archPage?.scopeState || null")
print("scopeState:", json.dumps(a_scope, ensure_ascii=False, default=str))
a_ok = bool(diag and diag.get('emptyShown')) and not (diag and diag.get('mermaidRendered'))
print('=> PASS' if a_ok else '=> FAIL')

# ---------- Part C: SCP 标准范围 → 图表正常渲染 ----------
page.goto(f"{BASE}?productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP", wait_until="networkidle", timeout=60000)
time.sleep(10)
c = page.evaluate("""() => ({
    url: location.href,
    emptyShown: !!document.querySelector('.embedded-chart-view__empty'),
    mermaidRendered: !!document.querySelector('.mermaid svg'),
    scopeState: window.__archPage?.scopeState || null
})""")
print("=== C. SCP 图表渲染 ===")
print(json.dumps(c, ensure_ascii=False, default=str))
c_ok = c.get('mermaidRendered') and not c.get('emptyShown')
print('=> PASS' if c_ok else '=> FAIL')

cli.close()
