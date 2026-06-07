# -*- coding: utf-8 -*-
"""通过位置点击 OSS 的 service_module 来验证"""
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

cli = PlaywrightCLI(headless=False)
page = cli._ensure_browser()

logs = []
page.on("console", lambda msg: logs.append({"type": msg.type, "text": msg.text}))

page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="commit", timeout=10000)
time.sleep(2)
page.goto("http://localhost:3004/system/archdata?productId=1&versionId=1", wait_until="networkidle", timeout=30000)
time.sleep(5)

# 展开 OSS 面板
page.evaluate("() => { document.querySelector('.rst-panel-object')?.querySelector('.collapsible-panel__header')?.click(); }")
time.sleep(2)

# 展开所有 OSS 节点
page.evaluate("""() => {
    const trees = document.querySelectorAll('.el-tree');
    if (trees.length < 1) return;
    // 点击所有非叶子节点的展开箭头
    const arrows = trees[0].querySelectorAll('.el-tree-node__expand-icon:not(.is-leaf)');
    for (let i = 0; i < arrows.length; i++) {
        if (!arrows[i].parentElement.classList.contains('is-expanded')) {
            arrows[i].click();
        }
    }
}""")
time.sleep(3)

# 找所有 checkbox 并打印位置信息
cb_info = page.evaluate("""() => {
    const trees = document.querySelectorAll('.el-tree');
    if (trees.length < 1) return 'no tree';
    const nodes = trees[0].querySelectorAll('.el-tree-node');
    const result = [];
    nodes.forEach((n, i) => {
        const cb = n.querySelector('.el-checkbox__original');
        const label = n.querySelector('.el-tree-node__label');
        const txt = label ? (label.textContent || label.innerText || '').trim() : '';
        const leaf = n.classList.contains('is-leaf');
        const expanded = n.classList.contains('is-expanded');
        const content = n.querySelector('.el-tree-node__content');
        const indent = content ? parseInt(content.style.paddingLeft || '0') : 0;
        if (cb) {
            result.push({i, txt, leaf, expanded, indent, hasCB: true});
        }
    });
    return result;
}""")
print(f"OSS checkboxes ({len(cb_info)}):")
for item in cb_info:
    print(f"  [{item['i']}] indent={item['indent']} leaf={item['leaf']} txt='{item['txt'][:30]}'")

# 根据 indent 找最深的（service_module层）并点击第2个checkbox
# indent 越大 = 层级越深
if cb_info:
    max_indent = max(c['indent'] for c in cb_info)
    deep_cbs = [c for c in cb_info if c['indent'] == max_indent and c['leaf'] == False]
    if not deep_cbs:
        deep_cbs = [c for c in cb_info if c['indent'] == max_indent]
    
    if deep_cbs:
        target = deep_cbs[0]
        print(f"\nClicking node[{target['i']}] (indent={target['indent']})")
        page.evaluate(f"""
            const trees = document.querySelectorAll('.el-tree');
            const nodes = trees[0].querySelectorAll('.el-tree-node');
            const cb = nodes[{target['i']}].querySelector('.el-checkbox__original');
            if (cb) cb.click();
        """)
        time.sleep(8)

# 检查 RSS filter 日志
print("\n=== RSS FILTER ===")
for l in logs:
    if 'buildRelationScopeTree RESULT' in l['text'] or 'RSS-FILTER' in l['text']:
        print(f"[{l['type']}] {l['text'][:400]}")

# RSS filter params
rss = page.evaluate("""() => {
    const trees = document.querySelectorAll('.el-tree');
    if (trees.length < 2) return {error: 'no RSS'};
    const t = trees[1];
    let comp = t.__vueParentComponent;
    for (let i = 0; i < 20 && comp; i++) {
        if ((comp.type?.__name || '') === 'RelationScopeSection') {
            const p = comp.proxy;
            const smIds = p.selectedServiceModuleIds;
            return {
                domainIds: p.selectedDomainIds,
                serviceModuleIds: smIds,
                serviceModuleIdsTypes: smIds?.map(v => typeof v),
                subDomainIds: p.selectedSubDomainIds,
                boIds: p.selectedBoIds,
                treeDataLen: p.classifierTreeData?.length || 0
            };
        }
        comp = comp.parent;
    }
    return {error: 'no comp'};
}""")
print(f"\nRSS filter: {json.dumps(rss, indent=2, ensure_ascii=False, default=str)}")

# 检查是否有 RSS-FILTER HIDDEN 日志（之前debug加的）
hidden_count = sum(1 for l in logs if 'RSS-FILTER' in l['text'])
print(f"\nRSS-FILTER hidden nodes: {hidden_count}")

cli.close()
