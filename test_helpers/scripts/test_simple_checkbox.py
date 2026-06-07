"""
简单直接的 checkbox 测试
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_simple_checkbox():
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

        # 获取页面结构
        print("[Step 2] 分析页面结构...")
        page_structure = cli.evaluate("""
            () => {
                const result = { main: null, ossTree: null, relationTree: null };

                // 查找左侧栏的 oss-tree 容器
                const ossTree = document.querySelector('.oss-tree');
                const relationTree = document.querySelector('.relation-tree');

                result.ossTree = {
                    exists: !!ossTree,
                    childCount: ossTree?.children?.length || 0,
                    className: ossTree?.className || ''
                };

                result.relationTree = {
                    exists: !!relationTree,
                    childCount: relationTree?.children?.length || 0
                };

                // 查找所有 el-tree
                const trees = document.querySelectorAll('.el-tree');
                result.treeCount = trees.length;

                trees.forEach((tree, i) => {
                    const container = tree.closest('.oss-tree, .relation-tree, [class*="scope"], [class*="tree"]');
                    console.log('Tree', i, 'container:', container?.className || 'none');
                });

                return result;
            }
        """)
        print(f"[INFO] 页面结构: {page_structure}")

        # 等待 el-tree
        print("[Step 3] 等待 el-tree...")
        max_wait = 10
        for i in range(max_wait):
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            if tree_count > 0:
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            import time
            time.sleep(1)

        # 查找第一个 el-tree 的第一个 checkbox
        print("[Step 4] 查找 checkbox...")

        first_checkbox = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length === 0) return { error: 'No trees' };

                // 查找第一个 el-tree
                const tree = trees[0];
                const checkbox = tree.querySelector('.el-tree-node__content .el-checkbox');

                if (!checkbox) return { error: 'No checkbox' };

                const node = checkbox.closest('.el-tree-node');
                const label = node?.querySelector('.oss-node-label')?.textContent?.trim() || 'unknown';

                // 获取 Vue 组件信息
                const vueComp = tree.__vueParentComponent;
                const parentComp = vueComp?.parent;
                const parentName = parentComp?.type?.__name || parentComp?.type?.name || 'unknown';

                return {
                    exists: true,
                    label: label,
                    treeIndex: 0,
                    parentComponentName: parentName,
                    beforeChecked: checkbox.classList.contains('is-checked')
                };
            }
        """)
        print(f"[INFO] 第一个 checkbox: {first_checkbox}")

        if first_checkbox.get('error'):
            results["errors"].append(first_checkbox['error'])
            return results

        # 点击 checkbox
        print("[Step 5] 点击 checkbox...")

        import time
        time.sleep(1)

        click_result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const checkbox = tree.querySelector('.el-tree-node__content .el-checkbox');
                const node = checkbox.closest('.el-tree-node');
                const label = node?.querySelector('.oss-node-label')?.textContent?.trim();

                console.log('=== Before click ===');
                console.log('Label:', label);
                console.log('Checkbox checked:', checkbox.classList.contains('is-checked'));

                // 点击 checkbox
                checkbox.click();

                setTimeout(() => {
                    console.log('=== After click ===');
                    console.log('Checkbox checked:', checkbox.classList.contains('is-checked'));
                }, 500);

                return { clicked: true, label: label };
            }
        """)
        print(f"[INFO] 点击结果: {click_result}")

        # 等待事件处理
        time.sleep(2)

        # 检查选中状态
        print("[Step 6] 检查选中状态...")

        after_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];

                // 检查第一个 checkbox
                const checkbox = tree.querySelector('.el-tree-node__content .el-checkbox');
                const node = checkbox?.closest('.el-tree-node');
                const label = node?.querySelector('.oss-node-label')?.textContent?.trim();

                // 检查所有选中项
                const allChecked = tree.querySelectorAll('.el-checkbox.is-checked');
                const checkedLabels = [];
                allChecked.forEach(cb => {
                    const n = cb.closest('.el-tree-node');
                    const l = n?.querySelector('.oss-node-label')?.textContent?.trim();
                    checkedLabels.push(l?.substring(0, 30));
                });

                return {
                    firstCheckboxChecked: checkbox?.classList.contains('is-checked') || false,
                    firstCheckboxLabel: label?.substring(0, 30),
                    totalCheckedCount: allChecked.length,
                    checkedLabels
                };
            }
        """)
        print(f"[INFO] 点击后状态: {after_state}")

        # 检查控制台日志
        console_logs = cli.evaluate("() => window.__consoleLogs || []")
        relevant_logs = [l for l in console_logs if 'handleBoCheck' in str(l) or 'ObjectScope' in str(l) or 'emit' in str(l).lower()]
        print(f"[INFO] 相关日志数量: {len(relevant_logs)}")
        if relevant_logs:
            print(f"[INFO] 日志内容: {relevant_logs[-10:]}")

        # 截图
        cli.screenshot('test_simple_checkbox.png')

        # 判断结果
        success = after_state.get('totalCheckedCount', 0) > 0
        results["success"] = success
        results["final_state"] = after_state

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"第一个 checkbox 初始状态: {first_checkbox.get('beforeChecked')}")
        print(f"点击后第一个 checkbox: {after_state.get('firstCheckboxChecked')}")
        print(f"总选中数: {after_state.get('totalCheckedCount', 0)}")
        print(f"相关日志数量: {len(relevant_logs)}")
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
    print("简单 checkbox 测试")
    print("=" * 60)

    import json
    results = test_simple_checkbox()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
