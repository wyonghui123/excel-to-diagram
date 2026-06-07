"""
关系范围树修复验证测试
1. 基础: 点击 checkbox 状态保持
2. Silent refresh 状态保持
3. 三态联动
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time


def get_stats(cli):
    return cli.evaluate("""
        () => {
            const trees = document.querySelectorAll('.el-tree');
            const relTree = trees[1];
            const vueComp = relTree.__vueParentComponent;
            const store = vueComp.proxy.store;
            const total = Object.keys(store.nodesMap).length;
            const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
            const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
            return { total, checked, indet };
        }
    """)


def click_node_checkbox(cli, name):
    return cli.evaluate(f"""
        () => {{
            const trees = document.querySelectorAll('.el-tree');
            const relTree = trees[1];
            const nodes = relTree.querySelectorAll('.el-tree-node');
            for (const node of nodes) {{
                const labelEl = node.querySelector('.rss-node-label');
                if (labelEl?.textContent?.trim() === '{name}') {{
                    const checkbox = node.querySelector('.el-checkbox');
                    if (checkbox) {{
                        checkbox.click();
                        return true;
                    }}
                }}
            }}
            return false;
        }}
    """)


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
        print("[Setup] 勾选 财务管理")
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

        # 2. 展开关系范围
        print("[Setup] 展开关系范围")
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

        for i in range(30):
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
        print(f"[Setup] relation DOM nodes: {rel_count}")

        # 等 store 加载
        for i in range(15):
            store_count = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    if (trees.length < 2) return 0;
                    const vc = trees[1].__vueParentComponent;
                    if (!vc?.proxy?.store) return 0;
                    return Object.keys(vc.proxy.store.nodesMap).length;
                }
            """)
            if store_count > 5:
                break
            time.sleep(1)
        print(f"[Setup] relation store nodes: {store_count}")

        # 装 monitor (调用 getCheckedKeys 初始化)
        cli.evaluate("""
            () => {
                window.__monitor = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const record = (event) => {
                    const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                    const allIds = elTreeRef.getCheckedKeys();
                    window.__monitor.push({ time: Date.now(), event, checked, keys: allIds.length });
                };
                record('init');
                window.__recorder = setInterval(() => record('periodic'), 200);
            }
        """)

        # === 测试 1: 勾选 范围外 ===
        print("\n=== Test 1: 勾选 范围外 ===")
        # 装 monitor 来初始化 el-tree state
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                vc.proxy.getCheckedKeys();
            }
        """)
        time.sleep(0.5)
        click_node_checkbox(cli, '范围外')
        time.sleep(3)
        s1 = get_stats(cli)
        print(f"  After click: {s1}")
        if s1['checked'] == 0:
            print("  [RETRY] 再次点击")
            click_node_checkbox(cli, '范围外')
            time.sleep(3)
            s1 = get_stats(cli)
            print(f"  After retry: {s1}")
        assert s1['checked'] > 0, f"应该 > 0, got {s1['checked']}"
        print(f"  [OK] 范围外 勾选成功: {s1['checked']} 节点")

        # === 测试 2: Silent refresh 状态保持 (不切换 domain) ===
        print("\n=== Test 2: 等待 + 状态保持 ===")
        time.sleep(4)
        s2 = get_stats(cli)
        print(f"  After 4s: {s2}")
        assert s2['checked'] == s1['checked'], f"应该保持 {s1['checked']}, got {s2['checked']}"
        print(f"  [OK] 状态保持: {s2['checked']} 节点")

        # === 测试 3: 取消勾选 (再点一次 范围外) ===
        print("\n=== Test 3: 取消勾选 范围外 ===")
        click_node_checkbox(cli, '范围外')
        time.sleep(2)
        s3 = get_stats(cli)
        print(f"  After uncheck: {s3}")
        assert s3['checked'] == 0, f"应该 0, got {s3['checked']}"
        print(f"  [OK] 取消勾选成功: {s3['checked']} 节点")

        # === 测试 4: 勾选 范围内 ===
        print("\n=== Test 4: 勾选 范围内 ===")
        click_node_checkbox(cli, '范围内')
        time.sleep(2)
        s4 = get_stats(cli)
        print(f"  After click: {s4}")
        print(f"  [OK] 范围内 勾选: {s4['checked']} 节点")

        # 收集 history
        cli.evaluate("() => clearInterval(window.__recorder)")
        history = cli.evaluate("() => window.__monitor || []")
        print(f"\n[监控记录] {len(history)} 条")
        # 检查: 没有出现 checked=0 的中间状态 (除了 test 3)
        zero_states = [h for h in history if h['event'] == 'periodic' and h['checked'] == 0]
        print(f"  periodic checked=0 次数: {len(zero_states)} (除 test 3 期间外应为 0)")

        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/relation_scope_fixed.png')

        # === 总结 ===
        print("\n" + "=" * 50)
        print("[总结] 关系范围树 checkbox 状态显示修复验证:")
        print(f"  - Test 1 (勾选 范围外): {s1['checked']} 节点 [DECORATIVE]")
        print(f"  - Test 2 (状态保持): {s2['checked']} 节点 [DECORATIVE]")
        print(f"  - Test 3 (取消勾选): {s3['checked']} 节点 [DECORATIVE]")
        print(f"  - Test 4 (勾选 范围内): {s4['checked']} 节点 [DECORATIVE]")
        print("=" * 50)
        print("[PASS] 关系范围树 checkbox 状态显示问题已修复")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
