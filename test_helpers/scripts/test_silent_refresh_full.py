"""
完整 silent refresh 状态保持测试
基于 test_exact_copy.py 的成功模式
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

        # 3. 装 monitor (调用 getCheckedKeys 初始化 el-tree state)
        print("[Step 3] 装 monitor")
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
                    window.__storeHistory.push({
                        time: Date.now(),
                        event,
                        checked,
                        total: store.nodesMap ? Object.keys(store.nodesMap).length : 0,
                        keys: allIds.length
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

        # 关键: 调用 getCheckedKeys 初始化 el-tree
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                vueComp.proxy.getCheckedKeys();
            }
        """)
        time.sleep(0.2)

        # 4. 点击 范围外
        print("[Step 4] 点击 范围外")
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
        assert s1['checked'] > 0, f"应该 > 0, got {s1['checked']}"
        print(f"[OK] 点击 范围外 成功, {s1['checked']} 节点选中")

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
        # 打印关键事件
        for h in history:
            t_offset = h['time'] - history[0]['time']
            if h['event'] == 'init' or t_offset % 1000 < 100:
                print(f"  +{t_offset}ms, event={h['event']}, checked={h['checked']}, keys={h['keys']}")

        # 9. 结论
        last = history[-1] if history else None
        if last:
            print(f"\n[最终] checked={last['checked']}, keys={last['keys']}")
            if last['checked'] == s1['checked']:
                print(f"[PASS] Silent refresh 状态保持: {last['checked']} 节点")
            else:
                print(f"[FAIL] Silent refresh 状态丢失: {s1['checked']} -> {last['checked']}")

        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/silent_refresh.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
