"""
监视 treeData 何时被修改 - 通过 el-tree 的 props.data getter
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

        # 1. 监视 store 的根节点 data 引用
        cli.evaluate("""
            () => {
                window.__history = [];
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const rootNode = store.root;

                // 用 Proxy 拦截 root.data 变化
                let lastDataRef = rootNode.data;
                const origUpdateChildren = rootNode.updateChildren.bind(rootNode);
                rootNode.updateChildren = function() {
                    window.__history.push({
                        time: Date.now(),
                        event: 'root.updateChildren',
                        rootDataChanged: rootNode.data !== lastDataRef
                    });
                    lastDataRef = rootNode.data;
                    return origUpdateChildren();
                };

                // 监视 setData
                const origSetData = store.setData.bind(store);
                store.setData = function(data) {
                    const branch = data !== rootNode.data ? 'rebuild' : 'updateChildren';
                    window.__history.push({
                        time: Date.now(),
                        event: 'store.setData',
                        branch,
                        dataIsNewRoot: data !== rootNode.data
                    });
                    return origSetData(data);
                };

                // 监视 el-tree props.data (通过 getCurrentInstance 的 vnode)
                const vnode = vueComp.vnode;
                const propsData = vnode.props?.data;
                if (propsData) {
                    window.__initialPropsData = propsData;
                    window.__initialPropsDataRef = propsData;
                }
            }
        """)

        # 2. 找到目标节点
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const checkboxes = trees[0].querySelectorAll('.el-checkbox');
                for (let i = 0; i < checkboxes.length; i++) {
                    const node = checkboxes[i].closest('.el-tree-node');
                    if (!node) continue;
                    const rect = node.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        checkboxes[i].setAttribute('data-test-target', '1');
                        return;
                    }
                }
            }
        """)

        # 3. 点击
        cli._page.click('[data-test-target="1"]', timeout=5000)
        print("[OK] 点击成功")

        time.sleep(2)

        # 4. 收集历史
        history = cli.evaluate("() => window.__history || []")
        print(f"\n[历史 (共 {len(history)} 条)]:")
        for i, h in enumerate(history):
            print(f"  [{i}] t={h['time']}, event={h['event']}, branch={h.get('branch', '')}, "
                  f"dataIsNewRoot={h.get('dataIsNewRoot', '')}, rootDataChanged={h.get('rootDataChanged', '')}")

        # 5. 最终 store data
        final = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                return {
                    rootDataIsInitial: store.root.data === window.__initialPropsDataRef,
                    rootDataId: store.root.data?.length,
                    nodesMap_d5_id: store.nodesMap['d_5']?.id
                };
            }
        """)
        print(f"\n[最终 store data]: {json.dumps(final, ensure_ascii=False, indent=2)}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
