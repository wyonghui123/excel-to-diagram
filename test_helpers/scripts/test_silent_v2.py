"""
完整 silent refresh 状态保持测试 - 完全照搬 test_exact_copy.py
"""
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

        # 1. 勾选 财务管理
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

        # 2. 展开关系面板
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

        # 3. 装 monitor
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
                    const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
                    const allIds = elTreeRef.getCheckedKeys();
                    window.__storeHistory.push({
                        time: Date.now(),
                        event,
                        checked,
                        indet,
                        total: store.nodesMap ? Object.keys(store.nodesMap).length : 0,
                        checkedKeysCount: allIds.length
                    });
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

        # 4. 点击 范围外
        print("[Step 4] 点击 范围外")
        # 先看 click 前状态
        before_click = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                return {
                    treeCount: trees.length,
                    panels: Array.from(document.querySelectorAll('.collapsible-panel')).map(p => ({
                        title: p.querySelector('.panel-title, [class*="title"]')?.textContent?.trim(),
                        collapsed: p.classList.contains('is-collapsed')
                    }))
                };
            }
        """)
        print(f"  before click: {before_click}")

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
        time.sleep(2)

        # 5. 验证点击后状态
        s1 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length < 2) {
                    return { treeCount: trees.length, panels: Array.from(document.querySelectorAll('.collapsible-panel')).map(p => p.classList.contains('is-collapsed')) };
                }
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                return {
                    total: Object.keys(store.nodesMap).length,
                    checked: Object.values(store.nodesMap).filter(n => n.checked).length
                };
            }
        """)
        print(f"[After Click] {s1}")

        # 6. 触发 silent refresh: toggle 财务管理
        print("\n[Step 6] 触发 silent refresh (toggle 财务管理)")
        for i in range(2):
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
            time.sleep(1)

        time.sleep(4)  # 等 silent refresh 完成

        # 7. 检查状态
        s2 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                return {
                    total: Object.keys(store.nodesMap).length,
                    checked: Object.values(store.nodesMap).filter(n => n.checked).length
                };
            }
        """)
        print(f"[After Refresh] {s2}")

        # 8. 收集历史
        cli.evaluate("() => clearInterval(window.__recorder)")
        history = cli.evaluate("() => window.__storeHistory || []")
        print(f"\n[store history] ({len(history)} 条):")
        for h in history:
            t_offset = h['time'] - history[0]['time']
            if h['event'] == 'init' or h['event'].startswith('before') or h['event'].startswith('after') or t_offset % 1000 < 100:
                print(f"  +{t_offset}ms, event={h['event']}, checked={h['checked']}, keys={h['checkedKeysCount']}")

        # 9. 结论
        last = history[-1] if history else None
        if last:
            print(f"\n[最终] checked={last['checked']}, keys={last['checkedKeysCount']}")
            if s1['checked'] > 0 and last['checked'] == s1['checked']:
                print(f"[PASS] Silent refresh 状态保持: {last['checked']} 节点")
            elif s1['checked'] == 0:
                print(f"[FAIL] 点击未生效")
            else:
                print(f"[INFO] 状态变化: {s1['checked']} -> {last['checked']}")

        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/silent_refresh.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
