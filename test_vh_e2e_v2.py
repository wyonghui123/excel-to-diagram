#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 value_help 过滤器 E2E - 详细版
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def test_value_help_filter():
    """测试 value_help 过滤器"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        try:
            # 1. 登录
            print("\n1. 登录...")
            page.goto('http://localhost:3004/login', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)

            page.fill('input[type="text"]', 'admin')
            page.fill('input[type="password"]', 'admin123')
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)
            print("   [DECORATIVE] 登录完成")

            # 2. 导航到用户组页面
            print("\n2. 导航到用户组页面...")
            page.goto('http://localhost:3004/user-permission/groups', wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(5000)

            # 3. 列出所有表头
            print("\n3. 表头列表:")
            headers = page.locator('.el-table__header th')
            for i in range(headers.count()):
                text = headers.nth(i).text_content().strip()
                # 也获取列的属性
                cls = headers.nth(i).get_attribute('class') or ''
                print(f"   {i+1}. text='{text}', class='{cls[:80]}'")

            # 4. 逐个点击过滤器触发器
            print("\n4. 逐个点击过滤器触发器:")
            filter_triggers = page.locator('.filter-trigger')
            for i in range(filter_triggers.count()):
                trigger = filter_triggers.nth(i)

                # 获取触发器所在的表头文本
                parent_th = trigger.locator('xpath=ancestor::th')
                if parent_th.count() > 0:
                    header_text = parent_th.first.text_content().strip()[:30]
                else:
                    header_text = f"unknown-{i}"

                # 点击触发器
                trigger.click()
                page.wait_for_timeout(1000)

                # 检查 popover 内容
                popover = page.locator('.el-popover:visible, .filter-panel')
                if popover.count() > 0:
                    # 检查是否有 value_help
                    vh_field = page.locator('.value-help-field')
                    el_select = page.locator('.el-select:visible')

                    filter_type = "unknown"
                    if vh_field.count() > 0:
                        filter_type = "value_help"
                    elif el_select.count() > 0:
                        filter_type = "select"
                    else:
                        # 检查其他类型
                        date_picker = page.locator('.el-date-editor:visible')
                        input_field = page.locator('.el-input:visible')
                        if date_picker.count() > 0:
                            filter_type = "date-range"
                        elif input_field.count() > 0:
                            filter_type = "search"

                    print(f"   {i+1}. 列 '{header_text}': filter_type={filter_type}")

                    if filter_type == "value_help":
                        print(f"      [DECORATIVE] 找到 value_help 过滤器！")

                        # 点击 el-select 打开下拉
                        el_select_vh = vh_field.locator('.el-select')
                        if el_select_vh.count() > 0:
                            el_select_vh.first.click()
                            page.wait_for_timeout(2000)

                            options = page.locator('.el-select-dropdown__item:visible')
                            opt_count = options.count()
                            print(f"      [DECORATIVE] 有 {opt_count} 个选项")

                            if opt_count > 0:
                                for j in range(min(3, opt_count)):
                                    opt_text = options.nth(j).text_content().strip()
                                    print(f"        - 选项 {j+1}: {opt_text}")

                                # 选择第一个选项
                                options.first.click()
                                page.wait_for_timeout(500)
                                print(f"      [DECORATIVE] 选择了第一个选项")

                    # 关闭 popover
                    page.keyboard.press('Escape')
                    page.wait_for_timeout(500)
                else:
                    print(f"   {i+1}. 列 '{header_text}': 没有弹出 popover")

            # 5. 截图
            print("\n5. 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_e2e_v2_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   [DECORATIVE] 截图保存到: {screenshot_path}")

            print("\n" + "=" * 60)
            print("测试完成 [DECORATIVE]")
            print("=" * 60)

        except Exception as e:
            print(f"\n[DECORATIVE] 测试失败: {e}")
            import traceback
            traceback.print_exc()

            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_e2e_error.png')
            page.screenshot(path=screenshot_path, full_page=True)

        finally:
            browser.close()


if __name__ == '__main__':
    test_value_help_filter()
