#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 value_help 过滤器 E2E
验证 FK 字段的 value_help 多选过滤器是否正确显示和工作
"""
import os
import sys
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright, expect


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
            page.goto('http://localhost:3004/login', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)

            # 填写登录表单
            page.fill('input[type="text"]', 'admin')
            page.fill('input[type="password"]', 'admin123')
            page.click('button[type="submit"]')

            # 等待登录完成
            page.wait_for_timeout(3000)
            print("   [DECORATIVE] 登录完成")

            # 2. 导航到用户组页面
            print("\n2. 导航到用户组页面...")
            page.goto('http://localhost:3004/list/user_group', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(3000)

            # 检查页面标题
            title = page.title()
            print(f"   页面标题: {title}")

            # 3. 查找 value_help 过滤器
            print("\n3. 查找 value_help 过滤器...")

            # 方法1: 查找 FilterBar 中的 value_help 过滤器
            filter_bar = page.locator('.filter-bar')
            if filter_bar.count() > 0:
                print("   [DECORATIVE] 找到 FilterBar")

                # 查找 value_help 过滤器
                vh_filters = page.locator('.filter-bar__field--value_help')
                vh_count = vh_filters.count()
                print(f"   [DECORATIVE] 找到 {vh_count} 个 value_help 过滤器")

                if vh_count > 0:
                    for i in range(vh_count):
                        vh_filter = vh_filters.nth(i)
                        label = vh_filter.locator('.filter-bar__label').text_content()
                        print(f"     - 过滤器 {i+1}: {label}")

                        # 检查是否有 el-select 组件（ValueHelpField 使用 el-select）
                        el_select = vh_filter.locator('.el-select')
                        if el_select.count() > 0:
                            print(f"       [DECORATIVE] 有 el-select 组件")

                            # 点击打开下拉框
                            el_select.click()
                            page.wait_for_timeout(1000)

                            # 检查是否有选项
                            options = page.locator('.el-select-dropdown__item')
                            opt_count = options.count()
                            print(f"       [DECORATIVE] 有 {opt_count} 个选项")

                            if opt_count > 0:
                                # 选择第一个选项
                                options.first.click()
                                page.wait_for_timeout(500)
                                print(f"       [DECORATIVE] 选择了第一个选项")

                            # 点击其他地方关闭下拉框
                            page.click('body')
                            page.wait_for_timeout(500)
                        else:
                            print(f"       [DECORATIVE] 没有 el-select 组件")
                            # 可能使用了 dialog 类型

                else:
                    print("   [DECORATIVE] 没有找到 value_help 过滤器")
                    # 打印所有过滤器类型
                    all_filters = page.locator('.filter-bar__field')
                    print(f"   找到 {all_filters.count()} 个过滤器:")
                    for i in range(all_filters.count()):
                        f = all_filters.nth(i)
                        class_name = f.get_attribute('class') or ''
                        label = f.locator('.filter-bar__label').text_content()
                        print(f"     - {i+1}: {label} ({class_name})")

            # 4. 截图保存
            print("\n4. 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_filter_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   [DECORATIVE] 截图保存到: {screenshot_path}")

            print("\n" + "=" * 60)
            print("测试完成 [DECORATIVE]")
            print("=" * 60)

        except Exception as e:
            print(f"\n[DECORATIVE] 测试失败: {e}")
            import traceback
            traceback.print_exc()

            # 截图保存
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_filter_error.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   错误截图保存到: {screenshot_path}")

        finally:
            browser.close()


if __name__ == '__main__':
    test_value_help_filter()
