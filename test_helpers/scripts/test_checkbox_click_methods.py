"""
测试不同点击方式触发 el-tree checkbox
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_click_methods():
    cli = PlaywrightCLI()
    results = {"success": False, "steps": [], "errors": []}

    try:
        # 认证导航
        print("[Step 1] 认证并导航...")
        cli.authenticated_navigate(
            '/system/archdata?productId=1&versionId=1',
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        cli.wait_for_timeout(3000)

        # 等待 el-tree
        print("[Step 2] 等待 el-tree...")
        max_wait = 10
        for i in range(max_wait):
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            if tree_count > 0:
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            import time
            time.sleep(1)

        # 方法1: 标准 click()
        print("\n[方法1] 测试标准 click()...")
        result1 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const checkbox = tree.querySelector('.el-tree-node__content .el-checkbox');
                const label = checkbox.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();

                console.log('Before click():', checkbox.classList.contains('is-checked'));
                checkbox.click();
                setTimeout(() => {
                    console.log('After click():', checkbox.classList.contains('is-checked'));
                }, 500);

                return { label: label?.substring(0, 30), clicked: true };
            }
        """)
        print(f"[结果] {result1}")
        import time
        time.sleep(1)

        after1 = cli.evaluate("""
            () => {
                const tree = document.querySelectorAll('.el-tree')[0];
                const checkbox = tree.querySelector('.el-tree-node__content .el-checkbox');
                return { checked: checkbox.classList.contains('is-checked') };
            }
        """)
        print(f"[结果] checked = {after1.get('checked')}")

        # 方法2: dispatchEvent
        print("\n[方法2] 测试 dispatchEvent(MouseEvent)...")
        result2 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const checkbox = tree.querySelector('.el-tree-node__content .el-checkbox');
                const label = checkbox.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();

                console.log('Before dispatchEvent:', checkbox.classList.contains('is-checked'));

                const event = new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
                checkbox.dispatchEvent(event);

                setTimeout(() => {
                    console.log('After dispatchEvent:', checkbox.classList.contains('is-checked'));
                }, 500);

                return { label: label?.substring(0, 30), clicked: true };
            }
        """)
        print(f"[结果] {result2}")
        time.sleep(1)

        after2 = cli.evaluate("""
            () => {
                const tree = document.querySelectorAll('.el-tree')[0];
                const checkbox = tree.querySelector('.el-tree-node__content .el-checkbox');
                return { checked: checkbox.classList.contains('is-checked') };
            }
        """)
        print(f"[结果] checked = {after2.get('checked')}")

        # 方法3: 使用 el-tree 的 setCheckedKeys
        print("\n[方法3] 使用 treeRef.setCheckedKeys()...")
        result3 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const treeRef = vueComp?.proxy;

                console.log('treeRef:', treeRef);
                console.log('has setCheckedKeys:', !!treeRef?.setCheckedKeys);

                if (treeRef?.setCheckedKeys) {
                    // 获取第一个节点的 key
                    const nodeKey = tree.querySelector('.el-tree-node')?.getAttribute('node-id');
                    console.log('Node key:', nodeKey);

                    treeRef.setCheckedKeys([nodeKey]);
                    return { method: 'setCheckedKeys', nodeKey };
                }

                return { error: 'setCheckedKeys not found' };
            }
        """)
        print(f"[结果] {result3}")
        time.sleep(1)

        after3 = cli.evaluate("""
            () => {
                const tree = document.querySelectorAll('.el-tree')[0];
                const checkboxes = tree.querySelectorAll('.el-checkbox.is-checked');
                return {
                    checkedCount: checkboxes.length,
                    labels: Array.from(checkboxes).map(cb =>
                        cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim()?.substring(0, 30)
                    )
                };
            }
        """)
        print(f"[结果] {after3}")

        # 检查控制台日志
        console_logs = cli.evaluate("() => window.__consoleLogs || []")
        relevant_logs = [l for l in console_logs if 'handleBoCheck' in str(l) or 'ObjectScope' in str(l)]
        print(f"\n[控制台日志] 相关日志数量: {len(relevant_logs)}")
        if relevant_logs:
            print(f"[日志内容] {relevant_logs[-10:]}")

        # 截图
        cli.screenshot('test_click_methods.png')

        success = after3.get('checkedCount', 0) > 0
        results["success"] = success
        results["final_state"] = {
            "method1_checked": after1.get('checked'),
            "method2_checked": after2.get('checked'),
            "method3_checked_count": after3.get('checkedCount', 0),
            "method3_labels": after3.get('labels', [])
        }

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"方法1 (click): {after1.get('checked')}")
        print(f"方法2 (dispatchEvent): {after2.get('checked')}")
        print(f"方法3 (setCheckedKeys): {after3.get('checkedCount', 0)} 项选中")
        print(f"测试成功: {success}")
        print("=" * 60)

        return results

    except Exception as e:
        error_msg = f"测试异常: {str(e)}"
        results["errors"].append(error_msg)
        print(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        return results

    finally:
        cli.close()
        print("[INFO] 浏览器已关闭")


if __name__ == "__main__":
    print("=" * 60)
    print("测试不同点击方式")
    print("=" * 60)

    import json
    results = test_click_methods()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
