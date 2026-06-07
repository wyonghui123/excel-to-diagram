"""直接检查 toolbar 按钮的实际状态变化"""
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

        # 1. 勾选 domain
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
        time.sleep(3)

        # 1. 检查 toolbar 按钮
        print("[Step 1] 检查 toolbar 按钮")
        btns = cli.evaluate("""
            () => {
                const buttons = document.querySelectorAll('.rss-toolbar .app-btn');
                return Array.from(buttons).map(b => ({
                    text: b.textContent?.trim(),
                    visible: b.offsetParent !== null,
                    classes: b.className
                }));
            }
        """)
        for b in btns:
            print(f"  - {b['text']}: visible={b['visible']}, classes={b['classes']}")

        # 2. 监视所有 store 状态
        cli.evaluate("""
            () => {
                window.__log = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;

                window.__getStats = () => {
                    const total = Object.keys(store.nodesMap).length;
                    const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                    const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
                    return { total, checked, indet };
                };

                // 包装 setCheckedKeys
                const orig = relTree.setCheckedKeys;
                relTree.setCheckedKeys = function(...args) {
                    window.__log.push({ event: 'setCheckedKeys_called', args_count: args[0]?.length });
                    const r = orig.apply(this, args);
                    const s = window.__getStats();
                    window.__log.push({ event: 'setCheckedKeys_returned', checked: s.checked, indet: s.indet });
                    return r;
                };

                // 包装 setChecked
                if (relTree.setChecked) {
                    const origSetChecked = relTree.setChecked;
                    relTree.setChecked = function(...args) {
                        window.__log.push({ event: 'setChecked_called', data: args[0]?.id });
                        const r = origSetChecked.apply(this, args);
                        const s = window.__getStats();
                        window.__log.push({ event: 'setChecked_returned', checked: s.checked, indet: s.indet });
                        return r;
                    };
                }
            }
        """)

        # 3. 点击 全选
        print("\n[Step 3] 点击 全选 按钮")
        before = cli.evaluate("() => window.__getStats()")
        print(f"  before: {before}")
        cli.evaluate("""
            () => {
                const buttons = document.querySelectorAll('.rss-toolbar .app-btn');
                for (const btn of buttons) {
                    if (btn.textContent?.trim() === '全选') {
                        btn.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(1)
        after = cli.evaluate("() => window.__getStats()")
        print(f"  after: {after}")
        log = cli.evaluate("() => window.__log || []")
        print(f"  log: {log}")

        # 4. 点击 清空
        print("\n[Step 4] 点击 清空 按钮")
        cli.evaluate("() => { window.__log = [] }")
        cli.evaluate("""
            () => {
                const buttons = document.querySelectorAll('.rss-toolbar .app-btn');
                for (const btn of buttons) {
                    if (btn.textContent?.trim() === '清空') {
                        btn.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(1)
        log = cli.evaluate("() => window.__log || []")
        after = cli.evaluate("() => window.__getStats()")
        print(f"  after: {after}")
        print(f"  log: {log}")

        # 5. 单独勾选一个 module
        print("\n[Step 5] 勾选第一个子节点 (在 范围内 展开后)")
        # 先展开 范围内
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围内') {
                        // 展开
                        const expandIcon = node.querySelector('.el-tree-node__expand-icon');
                        if (expandIcon && expandIcon.classList.contains('is-leaf') === false) {
                            expandIcon.click();
                        }
                        return;
                    }
                }
            }
        """)
        time.sleep(1)

        # 看可见的子节点
        visible = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                return Array.from(nodes).slice(0, 8).map(n => ({
                    text: n.querySelector('.rss-node-label')?.textContent?.trim(),
                    visible: n.offsetParent !== null
                }));
            }
        """)
        print(f"  visible nodes: {visible}")

        # 6. 直接调用 el-tree 内部接口
        print("\n[Step 6] 验证 getCheckedKeys vs store 状态")
        all_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                const total = Object.keys(store.nodesMap).length;
                const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
                const elTreeChecked = relTree.getCheckedKeys();
                return { total, checked, indet, elTreeCheckedCount: elTreeChecked.length, elTreeChecked: elTreeChecked.slice(0, 5) };
            }
        """)
        print(f"  stats: {all_info}")

        # 7. 调用 全选 后的 setCheckedKeys
        print("\n[Step 7] 手动调用 setCheckedKeys 验证")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                relTree.setCheckedKeys(['internal', 'cross-boundary', 'external'], false);
            }
        """)
        time.sleep(1)
        all_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                const total = Object.keys(store.nodesMap).length;
                const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
                const elTreeChecked = relTree.getCheckedKeys();
                return { total, checked, indet, elTreeCheckedCount: elTreeChecked.length };
            }
        """)
        print(f"  stats after manual setCheckedKeys: {all_info}")

        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/relation_scope_debug.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
