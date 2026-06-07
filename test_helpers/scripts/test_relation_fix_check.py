"""
调试: 验证修复代码是否执行
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

        # 捕获 console.log
        cli.evaluate("""
            () => {
                window.__logs = [];
                const origLog = console.log;
                console.log = function(...args) {
                    window.__logs.push(args.map(a =>
                        typeof a === 'string' ? a :
                        typeof a === 'object' ? JSON.stringify(a) : String(a)
                    ).join(' '));
                    return origLog.apply(this, args);
                };
            }
        """)

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
            rel_count = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    if (trees.length < 2) return 0;
                    return trees[1].querySelectorAll('.el-tree-node').length;
                }
            """)
            if rel_count > 1:
                print(f"[OK] 关系树加载: {rel_count} nodes")
                break
            time.sleep(1)

        # 4. 监视 selectedScopeIds 和 store 状态
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
                        window.__classifier = setupState.classifier;
                        window.__setupState = setupState;
                    }
                }

                // 监视 store
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const origSetData = store.setData.bind(store);
                store.setData = function(data) {
                    const branch = data !== store.root.data ? 'rebuild' : 'updateChildren';
                    window.__history.push({
                        time: Date.now(),
                        event: 'store.setData',
                        branch,
                        dataLength: data?.length,
                        rootDataChanged: data !== store.root.data
                    });
                    return origSetData(data);
                };

                let prevIds = JSON.stringify(window.__classifier.selectedScopeIds?.value || []);
                window.__watcher = setInterval(() => {
                    const curIds = JSON.stringify(window.__classifier.selectedScopeIds?.value || []);
                    if (curIds !== prevIds) {
                        window.__history.push({
                            time: Date.now(),
                            event: 'selectedScopeIds changed',
                            length: window.__classifier.selectedScopeIds?.value?.length
                        });
                        prevIds = curIds;
                    }

                    const curChecked = Object.values(store.nodesMap).filter(n => n.checked).length;
                    const curKey = `store_checked_${curChecked}`;
                    if (!window.__lastStoreKey || window.__lastStoreKey !== curKey) {
                        window.__history.push({
                            time: Date.now(),
                            event: 'store checked count',
                            count: curChecked
                        });
                        window.__lastStoreKey = curKey;
                    }
                }, 5);
            }
        """)

        # 5. 点击"范围外"
        print("\n[Step] 点击 范围外")
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

        # 6. 收集历史和日志
        history = cli.evaluate("() => { clearInterval(window.__watcher); return window.__history || []; }")
        logs = cli.evaluate("() => window.__logs || []")

        # 过滤相关日志
        relevant_logs = [l for l in logs if 'RelationScope' in l or 'silent' in l.lower() or 'skip' in l.lower() or 'preserve' in l.lower() or 'loadRelationships' in l]
        print(f"\n[相关日志] ({len(relevant_logs)} 条):")
        for l in relevant_logs:
            print(f"  - {l[:200]}")

        print(f"\n[历史] ({len(history)} 条):")
        for h in history:
            if h['event'] == 'store.setData':
                print(f"  [{h['time']}] store.setData branch={h['branch']}, dataLength={h['dataLength']}, rootChanged={h['rootDataChanged']}")
            elif h['event'] == 'selectedScopeIds changed':
                print(f"  [{h['time']}] selectedScopeIds length={h['length']}")
            elif h['event'] == 'store checked count':
                print(f"  [{h['time']}] store checked count = {h['count']}")

        # 7. 最终状态
        final = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                return {
                    domCheckedCount: relTree.querySelectorAll('.el-checkbox__input.is-checked').length,
                    storeCheckedCount: Object.values(elTreeRef.store.nodesMap).filter(n => n.checked).length,
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys().length
                };
            }
        """)
        print(f"\n[最终状态]: {json.dumps(final, ensure_ascii=False, indent=2)}")

        cli.screenshot('relation_fix_check.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
