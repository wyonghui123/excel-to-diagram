"""
最终用户操作模拟: 真实 Playwright click 验证修复
模拟用户操作流程:
  1. 进入页面
  2. 真实点击多个节点的 checkbox
  3. 验证勾选状态正确显示
  4. 验证状态保持
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

        # 1. 用 Playwright page.click 真实点击
        targets = [
            'TestDomainForDelete',
            '财务管理',
            '应付管理'
        ]

        for target in targets:
            print(f"\n[Click] {target}")
            cli.evaluate(f"""
                () => {{
                    const trees = document.querySelectorAll('.el-tree');
                    const targetTree = trees[0];
                    const nodes = targetTree.querySelectorAll('.el-tree-node');
                    for (const node of nodes) {{
                        const labelEl = node.querySelector('.oss-node-label');
                        if (labelEl?.textContent?.trim() === '{target}') {{
                            const checkbox = node.querySelector('.el-checkbox');
                            if (checkbox) {{
                                checkbox.setAttribute('data-test-target', 'click-{target}');
                                return;
                            }}
                        }}
                    }}
                }}
            """)

            try:
                cli._page.click(f'[data-test-target="click-{target}"]', timeout=5000)
                print(f"  [OK] clicked")
            except Exception as e:
                print(f"  [ERROR] {e}")
                continue

            time.sleep(0.8)

        # 2. 检查最终状态
        state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                return {
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                    domCheckedLabels: Array.from(targetTree.querySelectorAll('.el-checkbox.is-checked')).map(cb => {
                        return cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                    }),
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                    treeRefCheckedNodes: elTreeRef.getCheckedNodes().map(n => ({
                        id: n.id, name: n.name, type: n.type
                    }))
                };
            }
        """)
        print(f"\n[最终状态]: {json.dumps(state, ensure_ascii=False, indent=2)}")

        # 3. 等 2 秒, 看状态是否保持
        time.sleep(2)
        state_after = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                return {
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys()
                };
            }
        """)
        print(f"\n[2秒后状态]: dom={state_after['domCheckedCount']}, keys={state_after['treeRefCheckedKeys']}")

        cli.screenshot('final_user_test.png')

        # 4. 验证
        assert state['domCheckedCount'] == 3, f"Should have 3 checked, got {state['domCheckedCount']}"
        assert state_after['domCheckedCount'] == 3, f"After 2s should still have 3, got {state_after['domCheckedCount']}"
        print("\n[OK] 修复确认! 用户真实点击 3 个节点后状态正确保持")

    except AssertionError as e:
        print(f"\n[FAIL] 验证失败: {e}")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
