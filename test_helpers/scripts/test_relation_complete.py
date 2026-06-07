"""
完整测试关系范围树 silent refresh 状态保留
1. 勾选某些节点
2. 触发 silent refresh (通过修改对象范围触发 refreshAll)
3. 验证状态保持
4. 测试三态联动
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
        print(f"[Step 1] trees loaded: {tree_count}")

        # 1. 勾选 domain (财务管理)
        print("\n[Step 1] 勾选 财务管理 domain")
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
        print("\n[Step 2] 展开关系范围面板")
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
        print(f"[Step 2] relation nodes: {rel_count}")

        # 3. 监视 store 状态 + 包装 setData
        print("\n[Step 3] 安装 store 监视器")
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

                // 监视 store.setData
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
        print("\n[Step 4] 勾选 范围外")
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
        time.sleep(3)

        # 5. 触发 silent refresh: 模拟对象范围 tree 改变触发 coordinator.refreshAll
        # 方法: 在 domain 上再切换勾选状态
        print("\n[Step 5] 触发 silent refresh (重新勾选 财务管理)")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const objectTree = trees[0];
                const nodes = objectTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.oss-node-label');
                    if (labelEl?.textContent?.trim() === '财务管理') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) {
                            checkbox.click();
                            return;
                        }
                    }
                }
            }
        """)
        time.sleep(2)
        # 再次点击（toggle）
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const objectTree = trees[0];
                const nodes = objectTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.oss-node-label');
                    if (labelEl?.textContent?.trim() === '财务管理') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) {
                            checkbox.click();
                            return;
                        }
                    }
                }
            }
        """)
        time.sleep(4)

        # 6. 收集历史
        cli.evaluate("() => clearInterval(window.__recorder)")
        history = cli.evaluate("() => window.__storeHistory || []")
        print(f"\n[store history] ({len(history)} 条):")
        for h in history:
            t_offset = h['time'] - history[0]['time']
            print(f"  +{t_offset}ms, event={h['event']}, checked={h['checked']}, indet={h['indet']}, total={h['total']}, keys={h['checkedKeysCount']}")

        # 分析: setData 之后是否 checked 保持?
        last = history[-1] if history else None
        if last:
            print(f"\n[最终状态] checked={last['checked']}, indet={last['indet']}, keys={last['checkedKeysCount']}")
            if last['checked'] > 0:
                print("[OK] 关系范围树状态保持成功")
            else:
                print("[FAIL] 关系范围树状态丢失")

        # 7. 测试三态联动
        print("\n[Step 7] 测试三态联动")
        # 7.1 全选
        print("  7.1 全选")
        cli.evaluate("""
            () => {
                const buttons = document.querySelectorAll('.rss-toolbar .app-btn');
                for (const btn of buttons) {
                    if (btn.textContent?.includes('全选')) {
                        btn.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)
        all_checked = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                const total = Object.keys(store.nodesMap).length;
                const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                return { total, checked };
            }
        """)
        print(f"  7.1 全选后: total={all_checked['total']}, checked={all_checked['checked']}")

        # 7.2 清空
        print("  7.2 清空")
        cli.evaluate("""
            () => {
                const buttons = document.querySelectorAll('.rss-toolbar .app-btn');
                for (const btn of buttons) {
                    if (btn.textContent?.includes('清空')) {
                        btn.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)
        cleared = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                const total = Object.keys(store.nodesMap).length;
                const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                return { total, checked };
            }
        """)
        print(f"  7.2 清空后: total={cleared['total']}, checked={cleared['checked']}")

        # 7.3 部分选择 (勾选 范围内 节点 - 验证父子联动)
        print("  7.3 勾选 范围内 节点 (测试父子联动)")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围内') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)
        partial = cli.evaluate("""
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
        print(f"  7.3 勾选 范围内 后: total={partial['total']}, checked={partial['checked']}, indet={partial['indet']}")

        # 截图保存
        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/relation_scope_test.png')
        print("\n[截图] d:/filework/excel-to-diagram/screenshots/relation_scope_test.png")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
