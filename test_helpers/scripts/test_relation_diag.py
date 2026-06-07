"""
深入排查关系范围树 checkbox 状态丢失
监视:
  1. handleClassifierCheck 是否被调用
  2. store.setData 是否触发 (silent refresh)
  3. classifier.selectedScopeIds 何时变化
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time
import json


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
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            time.sleep(1)

        # 1. 勾选 domain
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

        # 3. 等待关系树加载
        for i in range(15):
            rel_node_count = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    if (trees.length < 2) return 0;
                    return trees[1].querySelectorAll('.el-tree-node').length;
                }
            """)
            if rel_node_count > 1:
                print(f"[OK] 关系树加载: {rel_node_count} nodes")
                break
            time.sleep(1)

        # 4. 安装所有监视器
        print("\n[Step 2] 安装监视器")
        cli.evaluate("""
            () => {
                window.__history = [];

                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;

                // 监视 store.setData
                const origSetData = store.setData.bind(store);
                store.setData = function(data) {
                    const branch = data !== store.root.data ? 'rebuild' : 'updateChildren';
                    window.__history.push({
                        time: Date.now(),
                        event: 'store.setData',
                        branch,
                        dataLength: data?.length
                    });
                    return origSetData(data);
                };

                // 监视根节点 updateChildren
                const origUpdateChildren = store.root.updateChildren.bind(store.root);
                store.root.updateChildren = function() {
                    window.__history.push({
                        time: Date.now(),
                        event: 'root.updateChildren'
                    });
                    return origUpdateChildren();
                };

                // 找到 RelationScopeSection 组件
                let comp = vueComp;
                while (comp && comp.type?.__name !== 'RelationScopeSection') {
                    comp = comp.parent;
                }
                if (comp) {
                    // 监视 handleClassifierCheck
                    const setupState = comp.setupState;
                    if (setupState) {
                        window.__setupState = setupState;
                        window.__classifier = setupState.classifier;

                        // 监视 selectedScopeIds
                        let prevIds = setupState.classifier?.selectedScopeIds?.value || [];
                        window.__watcher = setInterval(() => {
                            const curIds = setupState.classifier?.selectedScopeIds?.value || [];
                            if (JSON.stringify(curIds) !== JSON.stringify(prevIds)) {
                                window.__history.push({
                                    time: Date.now(),
                                    event: 'selectedScopeIds changed',
                                    from: prevIds,
                                    to: curIds
                                });
                                prevIds = curIds;
                            }
                        }, 10);
                    }
                }
            }
        """)

        # 5. 点击关系树的一个 checkbox
        print("\n[Step 3] 点击关系树 checkbox")
        click_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (let i = 0; i < nodes.length; i++) {
                    const node = nodes[i];
                    const labelEl = node.querySelector('.rss-node-label');
                    if (!labelEl) continue;
                    const label = labelEl.textContent?.trim();
                    if (!label) continue;
                    const checkbox = node.querySelector('.el-checkbox');
                    if (checkbox) {
                        const before = checkbox.querySelector('.el-checkbox__input')?.classList.contains('is-checked') || false;
                        checkbox.click();
                        return {
                            clicked: true,
                            index: i,
                            label,
                            beforeChecked: before
                        };
                    }
                }
                return { error: 'No checkbox' };
            }
        """)
        print(f"  click: {json.dumps(click_info, ensure_ascii=False)}")
        time.sleep(2)

        # 6. 收集历史
        history = cli.evaluate("() => { clearInterval(window.__watcher); return window.__history || []; }")
        print(f"\n[历史] ({len(history)} 条):")
        for i, h in enumerate(history):
            print(f"  [{i}] t={h['time']}, event={h['event']}, "
                  f"branch={h.get('branch', '')}, dataLength={h.get('dataLength', '')}, "
                  f"from={h.get('from', '')}, to={h.get('to', '')}")

        # 7. 最终状态
        final = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                return {
                    domCheckedCount: relTree.querySelectorAll('.el-checkbox__input.is-checked').length,
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                    selectedScopeIds: window.__classifier?.selectedScopeIds?.value
                };
            }
        """)
        print(f"\n[最终状态]: {json.dumps(final, ensure_ascii=False, indent=2)}")

        cli.screenshot('relation_diag.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
