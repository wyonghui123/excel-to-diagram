"""
深入排查: 父节点 d_4 半选状态在 store 中正确，但 DOM class 没有
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

        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                trees[0].__vueParentComponent.proxy.setCheckedKeys([]);
            }
        """)
        time.sleep(0.3)

        # 点击子节点
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const nodes = targetTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.oss-node-label');
                    if (labelEl?.textContent?.trim() === '应付管理') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(1)

        # 检查 d_4 节点的所有相关状态
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;

                // 找 d_4 节点
                const d4 = store.nodesMap['d_4'];
                if (!d4) return { error: 'd_4 not found' };

                // 找 d_4 的 DOM
                const nodes = targetTree.querySelectorAll('.el-tree-node');
                let d4Dom = null;
                for (const node of nodes) {
                    const labelEl = node.querySelector('.oss-node-label');
                    if (labelEl?.textContent?.trim() === '财务管理') {
                        d4Dom = node;
                        break;
                    }
                }

                return {
                    storeState: {
                        d4Checked: d4.checked,
                        d4Indeterminate: d4.indeterminate,
                        d4IsLeaf: d4.isLeaf,
                        d4IsEffectivelyChecked: d4.isEffectivelyChecked
                    },
                    domState: d4Dom ? {
                        hasIsCheckedClass: d4Dom.querySelector('.el-checkbox')?.classList.contains('is-checked'),
                        hasIsIndeterminateClass: d4Dom.querySelector('.el-checkbox')?.classList.contains('is-indeterminate'),
                        checkboxClasses: d4Dom.querySelector('.el-checkbox')?.className,
                        innerHTML: d4Dom.querySelector('.el-checkbox')?.outerHTML?.substring(0, 200)
                    } : null,
                    getHalfCheckedKeys: elTreeRef.getHalfCheckedKeys(),
                    getCheckedKeys: elTreeRef.getCheckedKeys()
                };
            }
        """)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
