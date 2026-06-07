import sys, time, json

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=False)
page = cli._ensure_browser()

page.goto('http://localhost:3010/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded', timeout=10000)
time.sleep(1)
page.goto('http://localhost:3004/system/archdata?productId=1&versionId=1', wait_until='domcontentloaded', timeout=20000)
time.sleep(5)
page.wait_for_selector('.el-tree', timeout=30000)
time.sleep(2)

# Expand RSS panel
page.evaluate("""() => {
    const panel = document.querySelector('.rst-panel-relation');
    if (panel && panel.classList.contains('is-collapsed')) {
        panel.querySelector('.collapsible-panel__header').click();
    }
}""")
time.sleep(1)

# How many el-trees are there?
tree_count_res = page.evaluate("() => document.querySelectorAll('.el-tree').length")
print(f"Total .el-tree elements: {tree_count_res}")

# Dump RSS tree content HTML (not just label)
html = page.evaluate("""() => {
    const trees = document.querySelectorAll('.el-tree');
    if (trees.length < 2) return 'no RSS tree (found ' + trees.length + ' trees)';
    const rssTree = trees[1];
    const nodes = rssTree.querySelectorAll('.el-tree-node');
    const result = [];
    for (let i = 0; i < Math.min(nodes.length, 10); i++) {
        const n = nodes[i];
        const content = n.querySelector('.el-tree-node__content');
        const label = n.querySelector('.el-tree-node__label');
        const checkbox = n.querySelector('.el-checkbox');
        const checkboxInput = checkbox ? checkbox.querySelector('input') : null;
        const checkboxChecked = checkboxInput ? checkboxInput.checked : 'no checkbox input';
        result.push({
            i,
            contentHTML: content ? content.innerHTML.substring(0, 500) : 'NO_CONTENT',
            labelExists: label !== null,
            labelHTML: label ? label.innerHTML.substring(0, 300) : 'NO_LABEL',
            nodeClass: n.className,
            isExpanded: n.classList.contains('is-expanded'),
            hasRssNode: content ? (content.querySelector('.rss-node') !== null) : false,
            checkboxChecked
        });
    }
    return result;
}""")

print("\n=== RSS Tree Node Content HTML Dump ===")
for item in html:
    print(f"[{item['i']}] class={item['nodeClass']} expanded={item['isExpanded']}")
    print(f"    labelExists: {item['labelExists']}")
    print(f"    hasRssNode: {item['hasRssNode']}")
    print(f"    checkboxChecked: {item['checkboxChecked']}")
    print(f"    contentHTML: {item['contentHTML'][:400]}")
    print()

# Try to access the tree node data through el-tree store
store_data = page.evaluate("""() => {
    const trees = document.querySelectorAll('.el-tree');
    if (trees.length < 2) return 'not enough trees';
    const rssTree = trees[1];
    // Try to access through element-plus internals
    const el = rssTree;
    // Try __vueParentComponent
    const vpc = el.__vueParentComponent;
    if (!vpc) return 'no __vueParentComponent';
    const proxy = vpc.proxy;
    // Check if proxy has store
    if (proxy.store) {
        const nodesMap = proxy.store.nodesMap || {};
        const root = proxy.store.root;
        const data = proxy.store.data || [];
        const result = {
            dataLength: data.length,
            rootChildNodes: root?.childNodes?.length || 0,
            firstDataNode: data.length > 0 ? data[0] : null,
        };
        // Get first few rendered nodes
        const nodeEntries = Object.entries(nodesMap).slice(0, 5).map(([k, v]) => ({
            key: k,
            label: v.label,
            data_name: v.data?.name,
            data_label: v.data?.label,
            data_id: v.data?.id,
            data_keys: v.data ? Object.keys(v.data).slice(0, 10) : [],
            childNodes: v.childNodes?.length || 0
        }));
        result.sampleNodes = nodeEntries;
        return result;
    }
    return { proxy_keys: proxy ? Object.keys(proxy).slice(0, 30) : 'no proxy' };
}""")
print(f"\n=== el-tree store data ===")
print(json.dumps(store_data, indent=2, ensure_ascii=False, default=str)[:2000])

# Also try to access classifierTreeData via Vue devtools global
vuedata = page.evaluate("""() => {
    const trees = document.querySelectorAll('.el-tree');
    if (trees.length < 2) return 'not enough trees';
    const rssTree = trees[1];

    // Walk up to find RSS component
    let el = rssTree.parentElement;
    for (let i = 0; i < 10; i++) {
        if (!el) break;
        const vpc = el.__vueParentComponent;
        if (vpc && vpc.type?.__name === 'RelationScopeSection') {
            return {
                found: true,
                hasClassifierTreeData: !!vpc.proxy.classifierTreeData,
                classifierTreeDataLen: vpc.proxy.classifierTreeData?.value?.length || vpc.proxy.classifierTreeData?.length || 'unknown',
                hasAllRelationships: !!vpc.proxy.allRelationships,
                allRelationshipsLen: vpc.proxy.allRelationships?.value?.length || vpc.proxy.allRelationships?.length || 'unknown',
                hasBusinessObjects: !!vpc.proxy.businessObjects,
                businessObjectsLen: vpc.proxy.businessObjects?.value?.length || vpc.proxy.businessObjects?.length || 'unknown',
                useState: vpc.proxy.stale,
                useLoadError: vpc.proxy.loadError,
            };
        }
        el = el.parentElement;
    }

    // Try walking the full Vue app tree
    const app = document.querySelector('#app').__vue_app__;
    const root = app._instance;

    function deepFind(inst, depth) {
        if (!inst || depth > 15) return null;
        const name = inst.type?.__name__ || inst.type?.name || '';
        if (name === 'RelationScopeSection') {
            return {
                depth,
                hasSetupState: !!inst.setupState,
                setupStateKeys: inst.setupState ? Object.keys(inst.setupState) : [],
            };
        }
        // Check subTree
        if (inst.subTree?.component) {
            const found = deepFind(inst.subTree.component, depth + 1);
            if (found) return found;
        }
        if (inst.subTree?.children) {
            for (const c of inst.subTree.children) {
                if (c.component) {
                    const found = deepFind(c.component, depth + 1);
                    if (found) return found;
                }
            }
        }
        return null;
    }

    const found = deepFind(root, 0);
    return { foundViaApp: found || 'not found' };
}""")
print(f"\n=== RelationScopeSection info ===")
print(json.dumps(vuedata, indent=2, ensure_ascii=False, default=str)[:3000])

# Check if the el-tree is using the right thing for label
# Look at the rendered HTML more carefully - maybe the content is empty
content_dump = page.evaluate("""() => {
    const trees = document.querySelectorAll('.el-tree');
    if (trees.length < 2) return 'not enough trees';
    const rssTree = trees[1];
    // Get the actual rendered DOM
    const allText = rssTree.innerText.trim();
    const allContents = rssTree.querySelectorAll('.el-tree-node__content');
    const results = [];
    for (let i = 0; i < Math.min(allContents.length, 5); i++) {
        results.push({
            i,
            innerHTML: allContents[i].innerHTML.substring(0, 300),
            textContent: allContents[i].textContent.substring(0, 100),
        });
    }
    return {
        treeText: allText.substring(0, 500),
        allContentCount: allContents.length,
        contents: results
    };
}""")
print(f"\n=== Tree node content raw ===")
print(json.dumps(content_dump, indent=2, ensure_ascii=False, default=str)[:3000])

cli.close()
