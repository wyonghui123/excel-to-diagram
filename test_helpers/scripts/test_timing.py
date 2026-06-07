"""直接测试 click 立即 vs 延迟的差异"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time


def main():
    cli = PlaywrightCLI()
    try:
        cli.authenticated_navigate(
            '/system/archdata?productId=1&versionId=1',
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        cli.wait_for_timeout(3000)

        for i in range(15):
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            if tree_count > 0:
                break
            time.sleep(1)

        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const objectTree = trees[0];
                const nodes = objectTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.oss-node-label');
                    if (labelEl?.textContent?.trim() === '财务管理') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel, .rst-panel-relation');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        const header = panel.querySelector('.panel-header, [class*="header"]');
                        if (header) header.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        for i in range(15):
            rel_count = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    if (trees.length < 2) return 0;
                    return trees[1].querySelectorAll('.el-tree-node').length;
                }
            """)
            if rel_count > 1:
                break
            time.sleep(1)

        # 装 monitor
        cli.evaluate("""
            () => {
                window.__storeHistory = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const recordState = (event) => {
                    const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                    const allIds = elTreeRef.getCheckedKeys();
                    window.__storeHistory.push({ time: Date.now(), event, checked, keys: allIds.length });
                };
                recordState('init');
                const origSetData = store.setData.bind(store);
                store.setData = function(data) {
                    recordState('before_setData');
                    const r = origSetData(data);
                    recordState('after_setData');
                    return r;
                };
                window.__recorder = setInterval(() => recordState('periodic'), 100);
            }
        """)

        # Click + 立即检查 (no sleep)
        print("[Step] click + 立即检查")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (let i = 0; i < nodes.length; i++) {
                    const node = nodes[i];
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        # 立即检查
        s_immediate = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length < 2) return { error: 'no tree[1]' };
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                if (!vueComp) return { error: 'no vueComp' };
                const store = vueComp.proxy.store;
                return {
                    total: Object.keys(store.nodesMap).length,
                    checked: Object.values(store.nodesMap).filter(n => n.checked).length
                };
            }
        """)
        print(f"  立即: {s_immediate}")

        # 等 100ms
        time.sleep(0.1)
        s_100 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length < 2) return { error: 'no tree[1]' };
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                return {
                    total: Object.keys(store.nodesMap).length,
                    checked: Object.values(store.nodesMap).filter(n => n.checked).length
                };
            }
        """)
        print(f"  +100ms: {s_100}")

        # 等 1s
        time.sleep(1)
        s_1100 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length < 2) return { error: 'no tree[1]' };
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                return {
                    total: Object.keys(store.nodesMap).length,
                    checked: Object.values(store.nodesMap).filter(n => n.checked).length
                };
            }
        """)
        print(f"  +1100ms: {s_1100}")

        time.sleep(2)
        s_3100 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length < 2) return { error: 'no tree[1]' };
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                return {
                    total: Object.keys(store.nodesMap).length,
                    checked: Object.values(store.nodesMap).filter(n => n.checked).length
                };
            }
        """)
        print(f"  +3100ms: {s_3100}")

        cli.evaluate("() => clearInterval(window.__recorder)")
        history = cli.evaluate("() => window.__storeHistory || []")
        print(f"\n[history] {len(history)} 条")
        for h in history[:20]:
            t_offset = h['time'] - history[0]['time']
            print(f"  +{t_offset}ms, {h['event']}, checked={h['checked']}, keys={h['keys']}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
