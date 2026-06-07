"""
关键修正版: setupState.treeRef 是 el-tree 的 proxy 代理（不是 shallowRef）
直接调用 setupState.treeRef.getCheckedKeys() 等方法
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

        # 初始化 console 捕获
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

        # 1. 直接调用 setupState.treeRef 上的方法
        print("\n[1] setupState.treeRef 直接调用")
        r1 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                const treeRef = setupState.treeRef;

                return {
                    treeRefType: typeof treeRef,
                    hasGetCheckedKeys: typeof treeRef?.getCheckedKeys,
                    hasSetChecked: typeof treeRef?.setChecked,
                    hasSetCheckedKeys: typeof treeRef?.setCheckedKeys,
                    hasGetCheckedNodes: typeof treeRef?.getCheckedNodes,
                    currentCheckedKeys: treeRef?.getCheckedKeys ? treeRef.getCheckedKeys() : null,
                    currentCheckedNodes: treeRef?.getCheckedNodes ? treeRef.getCheckedNodes().map(n => ({
                        id: n.id, name: n.name, type: n.type
                    })) : null
                };
            }
        """)
        print(json.dumps(r1, ensure_ascii=False, indent=2))

        # 2. 用 setupState.treeRef.setChecked 设置第一个节点
        print("\n[2] setupState.treeRef.setChecked('d_5', true)")
        r2 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                const treeRef = setupState.treeRef;

                // 关键: 这是用户在 setupState 中使用的方式
                treeRef.setChecked('d_5', true);

                return {
                    called: true,
                    checkedKeys: treeRef.getCheckedKeys(),
                    checkedNodes: treeRef.getCheckedNodes().map(n => ({
                        id: n.id, name: n.name, type: n.type
                    }))
                };
            }
        """)
        print(json.dumps(r2, ensure_ascii=False, indent=2))

        time.sleep(0.5)

        # 3. 检查 DOM 是否同步
        print("\n[3] DOM 状态")
        r3 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                return {
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                    domCheckedLabels: Array.from(targetTree.querySelectorAll('.el-checkbox.is-checked')).map(cb => {
                        return cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                    })
                };
            }
        """)
        print(json.dumps(r3, ensure_ascii=False, indent=2))

        # 4. 检查 emit 事件和 checkedBoIds 状态
        print("\n[4] emit 后状态")
        r4 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                return {
                    checkedBoIds: setupState.checkedBoIds,
                    settingFromPropValue: setupState.settingFromProp
                };
            }
        """)
        print(json.dumps(r4, ensure_ascii=False, indent=2))

        # 5. 现在测试真实点击 - 模拟用户行为
        print("\n[5] 真实点击 input checkbox")
        r5 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp?.proxy;

                // 先清空
                elTreeRef.setCheckedKeys([]);

                // 找到第一个可见的 checkbox 内部 input
                const checkboxes = targetTree.querySelectorAll('.el-checkbox');
                let targetCheckbox = null;
                for (let i = 0; i < checkboxes.length; i++) {
                    const node = checkboxes[i].closest('.el-tree-node');
                    const rect = node?.getBoundingClientRect();
                    if (rect && rect.width > 0 && rect.height > 0) {
                        targetCheckbox = checkboxes[i];
                        break;
                    }
                }

                if (!targetCheckbox) return { error: 'No checkbox' };

                // 尝试三种点击方式
                const label = targetCheckbox.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                const before = {
                    domChecked: targetCheckbox.classList.contains('is-checked'),
                    getCheckedKeys: elTreeRef.getCheckedKeys()
                };

                // Element Plus el-tree 内部: 当点击 checkbox 的 input 元素时, 它会处理
                // 我们使用 dispatchEvent 模拟
                const input = targetCheckbox.querySelector('input[type="checkbox"]');
                const clickTarget = input || targetCheckbox;
                const ev = new MouseEvent('click', { bubbles: true, cancelable: true, view: window });
                clickTarget.dispatchEvent(ev);

                return {
                    clicked: true,
                    label,
                    before,
                    after: {
                        domChecked: targetCheckbox.classList.contains('is-checked'),
                        getCheckedKeys: elTreeRef.getCheckedKeys(),
                        checkboxClass: targetCheckbox.className
                    }
                };
            }
        """)
        print(json.dumps(r5, ensure_ascii=False, indent=2))

        time.sleep(0.5)

        # 6. 再次检查
        print("\n[6] 真实点击后 DOM 状态")
        r6 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp?.proxy;
                return {
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                    domCheckedLabels: Array.from(targetTree.querySelectorAll('.el-checkbox.is-checked')).map(cb => {
                        return cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                    }),
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys()
                };
            }
        """)
        print(json.dumps(r6, ensure_ascii=False, indent=2))

        # 7. 用 el-tree 原生方法 handleNodeCheck 模拟
        print("\n[7] 模拟 el-tree 内部 handleNodeCheck")
        r7 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp?.proxy;
                const store = elTreeRef.store;

                // 先清空
                elTreeRef.setCheckedKeys([]);

                const node = store.nodesMap['d_5'];
                if (!node) return { error: 'No node d_5' };

                // 模拟 el-tree 内部点击 checkbox 的处理: 触发 setChecked
                // el-tree 在 checkbox click 时调用 store.setCheckedNode
                store.setCheckedNode(node, true);

                return {
                    called: true,
                    checkedKeys: elTreeRef.getCheckedKeys(),
                    nodeChecked: node.checked
                };
            }
        """)
        print(json.dumps(r7, ensure_ascii=False, indent=2))

        time.sleep(0.5)

        # 8. 检查 store 内部状态
        print("\n[8] store.setCheckedNode 后状态")
        r8 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp?.proxy;
                const store = elTreeRef.store;

                return {
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                    nodeChecked: store.nodesMap['d_5']?.checked,
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys()
                };
            }
        """)
        print(json.dumps(r8, ensure_ascii=False, indent=2))

        # 9. 控制台日志
        print("\n[9] 控制台日志")
        logs = cli.evaluate("() => window.__logs || []")
        relevant = [l for l in logs if 'ObjectScope' in l or 'handleBoCheck' in l]
        print(f"[相关日志] {len(relevant)} 条")
        for log in relevant[-10:]:
            print(f"  - {log[:200]}")

        cli.screenshot('deep_diag_v4_final.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
