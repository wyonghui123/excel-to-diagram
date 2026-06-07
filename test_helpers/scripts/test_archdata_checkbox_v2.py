"""
架构数据管理页面 checkbox 测试
使用 PlaywrightCLI 统一管理浏览器生命周期
"""

import sys
import time
import json

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI


def test_archdata_checkbox():
    """测试架构数据管理页面的 checkbox 功能"""

    results = {
        "success": False,
        "steps": [],
        "errors": [],
        "final_state": {}
    }

    cli = PlaywrightCLI(headless=True)

    try:
        # ========== Step 1-4: 认证 + 导航 ==========
        print("[Step 1-4] 认证 + 导航到架构数据管理页面...")
        page = cli.authenticated_navigate(
            '/system/archdata',
            wait_for_selector='.el-tree',
            timeout=15000
        )
        print(f"[INFO] 当前 URL: {page.url}")
        results["steps"].append(f"导航到: {page.url}")

        # ========== Step 5: 截图 ==========
        cli.screenshot('test_archdata_v2_01.png', full_page=True)
        print("[INFO] 截图已保存: test_output/test_archdata_v2_01.png")

        # ========== Step 6: 检查 el-tree ==========
        print("[Step 6] 检查 el-tree...")
        tree_info = page.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                return {
                    count: trees.length,
                    details: Array.from(trees).slice(0, 3).map(t => ({
                        id: t.id,
                        className: t.className?.substring(0, 50),
                        nodeCount: t.querySelectorAll('.el-tree-node').length,
                        checkboxCount: t.querySelectorAll('.el-tree-node__content .el-checkbox').length,
                        checkedCount: t.querySelectorAll('.is-checked').length
                    }))
                };
            }
        """)
        print(f"[INFO] El-tree: {json.dumps(tree_info, ensure_ascii=False)}")
        results["steps"].append(f"El-tree: {json.dumps(tree_info, ensure_ascii=False)[:200]}")

        # ========== Step 7: 点击 checkbox ==========
        print("[Step 7] 点击 checkbox...")
        checkbox_clicked = False
        checkbox = page.query_selector('.el-tree-node__content .el-checkbox')
        if checkbox:
            checkbox.click()
            checkbox_clicked = True
            print("[OK] 点击 checkbox 成功")
        else:
            all_checkboxes = page.query_selector_all('.el-tree .el-checkbox')
            print(f"[INFO] 找到 {len(all_checkboxes)} 个 checkbox")
            for cb in all_checkboxes[:3]:
                try:
                    if cb.is_visible():
                        cb.click()
                        checkbox_clicked = True
                        print("[OK] 点击可见 checkbox")
                        break
                except:
                    pass
        page.wait_for_timeout(1000)

        # ========== Step 8: 验证选中状态 ==========
        print("[Step 8] 验证选中状态...")
        after_click_tree = page.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                return {
                    count: trees.length,
                    details: Array.from(trees).slice(0, 3).map(t => ({
                        checkedCount: t.querySelectorAll('.is-checked').length,
                        checkedNodes: Array.from(t.querySelectorAll('.is-checked')).map(n => ({
                            text: n.textContent?.trim().substring(0, 30)
                        }))
                    }))
                };
            }
        """)
        checked_count = 0
        if after_click_tree.get('details'):
            checked_count = after_click_tree['details'][0].get('checkedCount', 0)
        print(f"[INFO] 点击后 checkedCount: {checked_count}")
        results["steps"].append(f"点击后 checkedCount: {checked_count}")

        store_info = page.evaluate("""
            () => {
                const app = document.querySelector('#app');
                if (!app || !app.__vue_app__) return null;
                const pinia = app.__vue_app__.config.globalProperties.$pinia;
                const boCrud = pinia._s.get('boCrud');
                return { checkedBoIds: boCrud?.checkedBoIds, hasBoCrud: !!boCrud };
            }
        """)
        print(f"[INFO] Store: {json.dumps(store_info, ensure_ascii=False)}")

        cli.screenshot('test_archdata_v2_02.png', full_page=True)
        print("[INFO] 截图已保存: test_output/test_archdata_v2_02.png")

        success = (
            checked_count > 0 or
            (store_info and store_info.get('checkedBoIds') and len(store_info['checkedBoIds']) > 0)
        )
        results["success"] = success
        results["final_state"] = {
            "checkedCount": checked_count,
            "checkedBoIds": store_info.get('checkedBoIds') if store_info else None,
            "treeFound": tree_info.get('count', 0) > 0,
            "checkboxClicked": checkbox_clicked
        }

        print("\n" + "=" * 60)
        print("测试结果摘要")
        print("=" * 60)
        print(f"El-tree 数量: {tree_info.get('count', 0)}")
        print(f"Checkbox 点击: {checkbox_clicked}")
        print(f"选中数量: {checked_count}")
        print(f"测试成功: {success}")
        print("=" * 60)

        return results

    except Exception as e:
        error_msg = f"测试异常: {str(e)}"
        results["errors"].append(error_msg)
        print(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        try:
            cli.screenshot('test_archdata_v2_error.png', full_page=True)
        except:
            pass
        return results

    finally:
        cli.close()


if __name__ == "__main__":
    print("=" * 60)
    print("开始测试: 架构数据管理页面 Checkbox")
    print("=" * 60)

    results = test_archdata_checkbox()
    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if results["success"] else 1)