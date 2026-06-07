#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 value_help 过滤器 E2E v2
更详细地检查页面 DOM
"""
import os
import sys
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def test_value_help_filter_detailed():
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

            # 3. 详细检查页面 DOM
            print("\n3. 检查页面 DOM...")

            # 检查是否有 FilterBar 组件
            filter_bar_selectors = [
                '.filter-bar',
                '[class*="filter-bar"]',
                '[class*="FilterBar"]',
                '[class*="filter"]'
            ]

            found_filters = []
            for selector in filter_bar_selectors:
                elements = page.locator(selector)
                count = elements.count()
                if count > 0:
                    print(f"   [DECORATIVE] {selector}: 找到 {count} 个元素")
                    found_filters.append((selector, count))

            # 检查 MetaListPage 组件
            meta_list_selectors = [
                '.meta-list-page',
                '.meta-list',
                '[class*="meta-list"]',
                '.list-page'
            ]

            for selector in meta_list_selectors:
                elements = page.locator(selector)
                count = elements.count()
                if count > 0:
                    print(f"   [DECORATIVE] {selector}: 找到 {count} 个元素")

            # 检查是否有筛选器相关元素
            filter_related = [
                '.filter',
                '[class*="filter"]',
                '[class*="Filter"]'
            ]

            for selector in filter_related:
                elements = page.locator(selector)
                count = elements.count()
                if count > 0:
                    print(f"   {selector}: 找到 {count} 个元素")

            # 检查表格列
            table_headers = page.locator('th, .el-table__header th')
            if table_headers.count() > 0:
                print(f"\n4. 表格列 ({table_headers.count()} 个):")
                for i in range(min(10, table_headers.count())):
                    header = table_headers.nth(i)
                    text = header.text_content()
                    print(f"   - {i+1}: {text.strip()}")

            # 检查是否有 value_help 相关的输入框
            print("\n5. 检查 value_help 组件:")
            vh_related = page.locator('.value-help-field, [class*="value-help"]')
            print(f"   .value-help-field: 找到 {vh_related.count()} 个")

            el_selects = page.locator('.el-select')
            print(f"   .el-select: 找到 {el_selects.count()} 个")

            # 6. 检查 MetaListPage 组件的内部结构
            print("\n6. 检查页面主要内容:")
            main_content = page.locator('main, .main, #app main, .content')
            if main_content.count() > 0:
                print(f"   [DECORATIVE] 找到 main 内容区域")

            # 检查是否有任何 el-input
            el_inputs = page.locator('.el-input, .el-select')
            print(f"   .el-input/.el-select: 找到 {el_inputs.count()} 个")

            # 7. 保存截图
            print("\n7. 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_filter_v2_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   [DECORATIVE] 截图保存到: {screenshot_path}")

            # 8. 检查 API 调用
            print("\n8. 检查 API 调用:")
            page.evaluate("""
                () => {
                    // 检查 network 请求
                    const requests = window.performance.getEntriesByType('resource');
                    const apiRequests = requests.filter(r => r.name.includes('/api/'));
                    console.log('API requests:', apiRequests.length);
                    apiRequests.forEach(r => console.log('  -', r.name));
                }
            """)

            # 获取控制台日志
            page.on('console', lambda msg: print(f"   [Console] {msg.text}") if 'value_help' in msg.text.lower() or 'filter' in msg.text.lower() else None)

            print("\n" + "=" * 60)
            print("测试完成")
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
    test_value_help_filter_detailed()
