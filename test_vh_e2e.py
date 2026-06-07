#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 value_help 过滤器 E2E - 使用正确 URL
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

            # 2. 导航到用户组页面（正确 URL）
            print("\n2. 导航到用户组页面...")
            page.goto('http://localhost:3004/user-permission/groups', wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(5000)

            # 3. 检查页面结构
            print("\n3. 检查页面结构:")

            table_count = page.locator('.el-table').count()
            print(f"   .el-table: {table_count} 个")

            if table_count > 0:
                # 检查表头
                th_count = page.locator('.el-table__header th').count()
                print(f"   .el-table__header th: {th_count} 个")

                # 检查过滤器触发器
                filter_triggers = page.locator('.filter-trigger')
                trigger_count = filter_triggers.count()
                print(f"   .filter-trigger: {trigger_count} 个")

                if trigger_count > 0:
                    # 4. 查找 parent_id 列的过滤器
                    print("\n4. 查找 parent_id 列过滤器:")

                    # 获取所有表头文本
                    headers = page.locator('.el-table__header th')
                    for i in range(headers.count()):
                        text = headers.nth(i).text_content().strip()
                        if '父组' in text or 'parent' in text.lower():
                            print(f"   [DECORATIVE] 找到父组列 (第 {i+1} 列): {text}")

                            # 检查该列是否有过滤器触发器
                            trigger = headers.nth(i).locator('.filter-trigger')
                            if trigger.count() > 0:
                                print(f"   [DECORATIVE] 该列有过滤器触发器")

                                # 点击触发器
                                trigger.first.click()
                                page.wait_for_timeout(1000)

                                # 检查是否有 value_help 过滤器
                                vh_field = page.locator('.value-help-field')
                                if vh_field.count() > 0:
                                    print(f"   [DECORATIVE] 找到 value-help-field 组件")

                                    # 检查 el-select
                                    el_select = vh_field.locator('.el-select')
                                    if el_select.count() > 0:
                                        print(f"   [DECORATIVE] 找到 el-select 组件")

                                        # 点击打开下拉
                                        el_select.first.click()
                                        page.wait_for_timeout(2000)

                                        # 检查选项
                                        options = page.locator('.el-select-dropdown__item')
                                        opt_count = options.count()
                                        print(f"   [DECORATIVE] 有 {opt_count} 个选项")

                                        if opt_count > 0:
                                            for j in range(min(3, opt_count)):
                                                opt_text = options.nth(j).text_content().strip()
                                                print(f"     - 选项 {j+1}: {opt_text}")

                                            # 选择第一个选项
                                            options.first.click()
                                            page.wait_for_timeout(500)
                                            print(f"   [DECORATIVE] 选择了第一个选项")

                                        # 关闭下拉
                                        page.keyboard.press('Escape')
                                        page.wait_for_timeout(500)
                                else:
                                    print(f"   [DECORATIVE] 没有找到 value-help-field 组件")

                                # 关闭 popover
                                page.keyboard.press('Escape')
                                page.wait_for_timeout(500)
                            else:
                                print(f"   [DECORATIVE] 该列没有过滤器触发器")
                            break

            # 5. 截图
            print("\n5. 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_e2e_screenshot.png')
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
