"""
验证 141→282 双重计数 bug - v2
直接用 Playwright sync API，绕过 PlaywrightCLI 封装
"""

from playwright.sync_api import sync_playwright
import re

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 1. 登录
        page.goto("http://localhost:3006/")
        page.fill("input[type='text']", "admin")
        page.fill("input[type='password']", "admin123")
        page.click("button")
        page.wait_for_load_state("networkidle")

        # 2. 导航到架构数据管理
        page.goto("http://localhost:3006/system/archdata")
        page.wait_for_load_state("networkidle")

        # 3. 等待产品版本选择器出现
        page.wait_for_selector(".el-select", timeout=10000)

        # 4. 点击产品版本选择器
        page.click(".el-select")
        page.wait_for_selector(".el-select-dropdown", timeout=5000)

        # 5. 选择 TTTTT000
        page.click("text=TTTTT000")
        page.wait_for_timeout(500)

        # 6. 选择 V11
        page.click("text=V11")
        page.wait_for_timeout(500)

        # 7. 点击确定
        page.click(".el-dialog .el-button--primary")
        page.wait_for_timeout(2000)

        # 8. 等待树加载
        page.wait_for_selector(".el-tree", timeout=10000)

        # 9. 勾选供应链云 domain
        # 等待树加载
        page.wait_for_selector(".el-tree-node", timeout=10000)

        # 找到供应链云节点
        supply_chain_label = page.locator(".oss-node-label").filter(has_text="供应链云")
        supply_chain_count = supply_chain_label.locator("..").locator(".oss-node-count").text_content()
        print(f"供应链云节点 count: {supply_chain_count}")

        # 勾选
        supply_chain_checkbox = supply_chain_label.locator("..").locator(".el-checkbox__input")
        supply_chain_checkbox.click()
        page.wait_for_timeout(1000)

        # 6. 读取 chip 显示值
        chip = page.locator(".rst-panel-object .collapsible-panel-badge")
        chip_text = chip.text_content()
        print(f"Chip 显示值: {chip_text}")

        # 7. 提取数字并验证
        chip_num = int(re.search(r'\d+', chip_text).group())
        node_num = int(re.search(r'\d+', supply_chain_count).group())

        if chip_num == node_num * 2:
            print(f"BUG 复现: chip {chip_num} = node count {node_num} * 2")
        elif chip_num == node_num:
            print(f"BUG 已修复: chip {chip_num} = node count {node_num}")
        else:
            print(f"未知情况: chip {chip_num}, node count {node_num}")

        # 8. 截图
        page.screenshot(path="verify_282_result_v2.png")

        browser.close()

if __name__ == '__main__':
    main()