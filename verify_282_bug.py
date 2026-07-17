"""
验证 141→282 双重计数 bug
用 PlaywrightCLI 在 production dist 上复现和验证
"""

import sys
import json
import re
sys.path.insert(0, 'd:/filework/worktrees/release-prep')

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI(headless=False)  # headless=False 方便调试
    
    # 1. 通过前端 vite proxy 访问 dev-login
    # (后端不在 3010 端口，需要通过 3006 vite proxy 访问)
    page = cli._ensure_browser()
    page.goto(
        "http://localhost:3006/api/v1/auth/dev-login?username=admin",
        wait_until="domcontentloaded",
        timeout=10000
    )
    cli._cookies_set = True

    # 2. 导航到首页
    page.goto("http://localhost:3006/", wait_until="domcontentloaded", timeout=10000)

    # 3. 等待 store 就绪
    cli.wait_for_function("() => window.__PINIA_STATE__ != null", timeout=5000)

    # 4. 导航到 RelationshipManagement 页面
    page.goto("http://localhost:3006/system/archdata", wait_until="domcontentloaded", timeout=10000)
    cli.wait_for_selector('.el-table', timeout=10000)
    
    # 5. 等待产品/版本选择器
    print("等待产品/版本选择器...")
    cli.wait_for_selector('.product-version-selector', timeout=10000)

    # 6. 点击产品/版本选择器，打开弹出窗口
    cli.click('.product-version-selector')
    cli.wait_for_selector('.el-dialog', timeout=5000)

    # 7. 选择产品 TTTTT000
    print("选择产品 TTTTT000...")
    product_selector = "//span[contains(text(), 'TTTTT000')]"
    cli.page.locator(product_selector).click()

    # 8. 选择版本 V11
    print("选择版本 V11...")
    version_selector = "//span[contains(text(), 'V11')]"
    cli.page.locator(version_selector).click()

    # 9. 点击确定按钮
    print("点击确定...")
    cli.click('.el-dialog .el-button--primary')
    cli.wait_for_selector('.rst-panel-object', timeout=10000)

    # 10. 勾选供应链云 domain
    print("勾选供应链云 domain...")
    # 先展开树（如果需要）
    # 找到供应链云节点并勾选
    domain_label = "//span[contains(@class, 'oss-node-label') and contains(text(), '供应链云')]"
    domain_node = cli.page.locator(domain_label)
    domain_node.wait_for(timeout=10000)
    
    # 点击 checkbox
    checkbox = domain_node.locator('xpath=..').locator('.el-checkbox__input')
    checkbox.click()
    
    # 8. 等待 chip 更新
    cli.wait_for_timeout(1000)
    
    # 9. 读取 chip 显示值
    chip_text = cli.page.locator('.rst-panel-object .collapsible-panel-badge').text_content()
    print(f"Chip 显示值: {chip_text}")
    
    # 10. 读取节点显示的 count
    node_text = domain_node.text_content()
    # 提取 (数字)
    match = re.search(r'\((\d+)\)', node_text)
    node_count = int(match.group(1)) if match else None
    print(f"节点显示 count: {node_count}")
    
    # 11. 从 DOM 读取 el-tree 的 checked nodes
    checked_info = cli.page.evaluate('''() => {
        const tree = document.querySelector('.el-tree');
        if (!tree) return null;
        
        // 找到所有 checked 的节点
        const checkedNodes = [];
        const checkboxes = tree.querySelectorAll('.el-checkbox.is-checked');
        for (const cb of checkboxes) {
            const content = cb.closest('.el-tree-node__content');
            const label = content.querySelector('.oss-node-label')?.textContent;
            const countText = content.querySelector('.oss-node-count')?.textContent;
            checkedNodes.push({ label, count: countText });
        }
        return checkedNodes;
    }''')
    print(f"Checked nodes: {json.dumps(checked_info, indent=2, ensure_ascii=False)}")
    
    # 12. 验证 bug
    if node_count and chip_text:
        # chip_text 可能是 "282 对象" 或 "282"
        chip_num = int(re.search(r'\d+', chip_text).group())
        if chip_num == node_count * 2:
            print(f"BUG 复现: chip {chip_num} = node count {node_count} * 2")
        elif chip_num == node_count:
            print(f"BUG 已修复: chip {chip_num} = node count {node_count}")
        else:
            print(f"未知情况: chip {chip_num}, node count {node_count}")
    
    # 13. 截图保存
    cli.screenshot('verify_282_result.png')
    
    cli.close()

if __name__ == '__main__':
    main()