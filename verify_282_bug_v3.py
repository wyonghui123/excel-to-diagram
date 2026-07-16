"""
验证 141→282 双重计数 bug - v3
简化版：不选择产品/版本，直接检查页面是否有数据
"""

from playwright.sync_api import sync_playwright
import re
import time

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)  # slow_mo 方便观察
        context = browser.new_context()
        page = context.new_page()

        try:
            # 1. 登录
            print("1. 登录...")
            page.goto("http://localhost:3006/")
            page.fill("input[type='text']", "admin")
            page.fill("input[type='password']", "admin123")
            page.click("button")
            page.wait_for_load_state("networkidle")
            print("  登录成功")

            # 2. 导航到架构数据管理
            print("2. 导航到架构数据管理...")
            page.goto("http://localhost:3006/system/archdata")
            page.wait_for_load_state("networkidle")
            print("  页面加载完成")

            # 3. 检查是否有树数据
            print("3. 检查树数据...")
            tree_exists = page.locator(".el-tree").count() > 0
            print(f"  树存在: {tree_exists}")

            if not tree_exists:
                print("  没有树数据，尝试选择产品/版本...")
                # 等待选择器
                page.wait_for_selector(".el-select", timeout=5000)
                # 点击选择器
                page.click(".el-select")
                time.sleep(1)
                # 截图查看状态
                page.screenshot(path="debug_select.png")

                # 尝试选择第一个产品和版本
                # 产品列表
                first_product = page.locator(".el-select-dropdown__item").first
                if first_product:
                    first_product.click()
                    time.sleep(1)

                # 版本列表（如果有的话）
                version_select = page.locator(".el-select").nth(1)
                if version_select.count() > 0:
                    version_select.click()
                    time.sleep(1)
                    first_version = page.locator(".el-select-dropdown__item").first
                    if first_version:
                        first_version.click()
                        time.sleep(1)

                # 确定按钮
                confirm_btn = page.locator(".el-dialog .el-button--primary")
                if confirm_btn.count() > 0:
                    confirm_btn.click()
                    time.sleep(2)

                # 再次检查树
                tree_exists = page.locator(".el-tree").count() > 0
                print(f"  选择后树存在: {tree_exists}")

            if tree_exists:
                # 4. 找到供应链云节点
                print("4. 查找供应链云节点...")
                supply_chain_labels = page.locator(".oss-node-label")
                count = supply_chain_labels.count()
                print(f"  找到 {count} 个节点标签")

                # 查找包含 "供应链云" 的节点
                for i in range(count):
                    label = supply_chain_labels.nth(i)
                    text = label.text_content()
                    if "供应链云" in text:
                        print(f"  找到供应链云节点: {text}")

                        # 读取 count
                        parent = label.locator("..")
                        count_elem = parent.locator(".oss-node-count")
                        if count_elem.count() > 0:
                            count_text = count_elem.text_content()
                            print(f"  节点 count: {count_text}")
                            node_num = int(re.search(r'\d+', count_text).group())
                        else:
                            print("  节点没有 count")
                            node_num = 0

                        # 勾选
                        checkbox = parent.locator(".el-checkbox__input")
                        checkbox.click()
                        time.sleep(1)

                        # 读取 chip
                        chip = page.locator(".rst-panel-object .collapsible-panel-badge")
                        if chip.count() > 0:
                            chip_text = chip.text_content()
                            print(f"  Chip 显示值: {chip_text}")
                            chip_num = int(re.search(r'\d+', chip_text).group())

                            # 验证
                            if chip_num == node_num * 2:
                                print(f"  [BUG 复现] chip {chip_num} = node count {node_num} * 2")
                            elif chip_num == node_num:
                                print(f"  [BUG 已修复] chip {chip_num} = node count {node_num}")
                            else:
                                print(f"  [未知情况] chip {chip_num}, node count {node_num}")
                        else:
                            print("  找不到 chip")

                        break
            else:
                print("  无法加载树数据")

            # 截图
            page.screenshot(path="verify_282_result_v3.png")

        except Exception as e:
            print(f"错误: {e}")
            page.screenshot(path="verify_282_error.png")
            raise

        finally:
            time.sleep(2)
            browser.close()

if __name__ == '__main__':
    main()