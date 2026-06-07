"""
深入排查: selectedScopeIds 有 32 keys, 但 DOM 不显示勾选
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

        # 3. 等待关系树
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

        # 4. 监视 selectedScopeIds 变化
        cli.evaluate("""
            () => {
                window.__history = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                let comp = vueComp;
                while (comp && comp.type?.__name !== 'RelationScopeSection') {
                    comp = comp.parent;
                }
                if (comp) {
                    const setupState = comp.setupState;
                    if (setupState?.classifier) {
                        const classifier = setupState.classifier;
                        window.__classifier = classifier;

                        let prevIds = JSON.stringify(classifier.selectedScopeIds?.value || []);
                        window.__watcher = setInterval(() => {
                            const curIds = JSON.stringify(classifier.selectedScopeIds?.value || []);
                            if (curIds !== prevIds) {
                                window.__history.push({
                                    time: Date.now(),
                                    event: 'selectedScopeIds changed',
                                    newValue: JSON.parse(curIds),
                                    length: classifier.selectedScopeIds?.value?.length
                                });
                                prevIds = curIds;
                            }
                        }, 5);

                        // 监视 classifierTreeData 变化
                        let prevData = JSON.stringify(classifier.treeData?.value);
                        window.__dataWatcher = setInterval(() => {
                            const curData = JSON.stringify(classifier.treeData?.value);
                            if (curData !== prevData) {
                                window.__history.push({
                                    time: Date.now(),
                                    event: 'classifierTreeData changed',
                                    rootNodeCount: classifier.treeData?.value?.length
                                });
                                prevData = curData;
                            }
                        }, 5);
                    }
                }
            }
        """)

        # 5. 多次点击测试
        print("\n[Step] 点击 范围外 节点 (含子节点)")
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
                    if (label === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        const beforeChecked = checkbox?.querySelector('.el-checkbox__input')?.classList.contains('is-checked');
                        checkbox.click();
                        return { clicked: true, index: i, label, beforeChecked };
                    }
                }
                return { error: 'not found' };
            }
        """)
        print(f"  click: {click_info}")
        time.sleep(0.5)

        # 检查 store 状态
        print("\n[Step] 立即检查 store 状态")
        immediate_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;

                let checkedCount = 0;
                let indeterminateCount = 0;
                const nodeIds = [];
                Object.values(store.nodesMap).forEach(node => {
                    if (node.checked) checkedCount++;
                    if (node.indeterminate) indeterminateCount++;
                    if (node.checked || node.indeterminate) {
                        nodeIds.push({ id: node.data?.id, name: node.data?.name, checked: node.checked, indet: node.indeterminate });
                    }
                });

                return {
                    storeCheckedCount: checkedCount,
                    storeIndeterminateCount: indeterminateCount,
                    storeAffectedNodes: nodeIds,
                    domCheckedCount: relTree.querySelectorAll('.el-checkbox__input.is-checked').length,
                    domIndeterminateCount: relTree.querySelectorAll('.el-checkbox__input.is-indeterminate').length,
                    getCheckedKeys: elTreeRef.getCheckedKeys()
                };
            }
        """)
        print(json.dumps(immediate_state, ensure_ascii=False, indent=2))

        # 6. 等 2 秒
        time.sleep(2)

        # 7. 检查最终状态
        final_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                return {
                    storeCheckedCount: Object.values(store.nodesMap).filter(n => n.checked).length,
                    domCheckedCount: relTree.querySelectorAll('.el-checkbox__input.is-checked').length,
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                    selectedScopeIdsLength: window.__classifier?.selectedScopeIds?.value?.length
                };
            }
        """)
        print(f"\n[2s后状态]: {json.dumps(final_state, ensure_ascii=False, indent=2)}")

        # 8. 历史
        cli.evaluate("() => { clearInterval(window.__watcher); clearInterval(window.__dataWatcher); }")
        history = cli.evaluate("() => window.__history || []")
        print(f"\n[历史] ({len(history)} 条):")
        for i, h in enumerate(history[:20]):
            print(f"  [{i}] t={h['time']}, event={h['event']}, length={h.get('length', '')}, "
                  f"rootNodeCount={h.get('rootNodeCount', '')}")
            if h['event'] == 'selectedScopeIds changed':
                print(f"      newValue: {h['newValue'][:5]}...")

        cli.screenshot('relation_state.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
