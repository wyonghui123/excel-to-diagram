"""
使用 Playwright 真实 page.click() 测试 checkbox 点击
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

        # 1. 用 Playwright 真实点击 - 找到第一个 checkbox
        print("\n[1] 用 Playwright page.click 真实点击")

        # 通过 evaluate 获取目标节点信息
        target_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const checkboxes = targetTree.querySelectorAll('.el-checkbox');

                // 找第一个可见的 checkbox
                for (let i = 0; i < checkboxes.length; i++) {
                    const node = checkboxes[i].closest('.el-tree-node');
                    if (!node) continue;
                    const rect = node.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        // 给 checkbox 添加一个唯一的标识
                        checkboxes[i].setAttribute('data-test-target', '1');
                        return {
                            index: i,
                            label: node.querySelector('.oss-node-label')?.textContent?.trim()
                        };
                    }
                }
                return null;
            }
        """)
        print(f"[目标] {target_info}")

        if not target_info:
            print("[ERROR] 未找到可见 checkbox")
            return

        # 2. 截图点击前
        cli.screenshot('click_before.png')

        # 3. Playwright 真实点击
        page = cli._page
        try:
            page.click('[data-test-target="1"]', timeout=5000)
            print("[OK] page.click 成功")
        except Exception as e:
            print(f"[ERROR] page.click 失败: {e}")

        time.sleep(1.5)

        # 4. 检查点击后状态
        print("\n[2] 点击后状态")
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                const elTreeRef = vueComp.proxy;

                return {
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                    domCheckedLabels: Array.from(targetTree.querySelectorAll('.el-checkbox.is-checked')).map(cb => {
                        return cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                    }),
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                    treeRefCheckedNodes: elTreeRef.getCheckedNodes().map(n => ({
                        id: n.id, name: n.name, type: n.type
                    })),
                    setupStateCheckedBoIds: setupState.checkedBoIds,
                    settingFromPropValue: setupState.settingFromProp
                };
            }
        """)
        print(json.dumps(result, ensure_ascii=False, indent=2))

        # 5. 检查控制台
        print("\n[3] 控制台日志")
        logs = cli.evaluate("() => window.__logs || []")
        relevant = [l for l in logs if 'ObjectScope' in l or 'handleBoCheck' in l or 'emit' in l]
        print(f"[总日志] {len(logs)}")
        print(f"[相关] {len(relevant)}")
        for log in relevant[-10:]:
            print(f"  - {log[:250]}")

        cli.screenshot('click_after.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
