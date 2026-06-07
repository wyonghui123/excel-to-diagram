#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
排查 value_help 过滤器难测试的原因 - 诊断版

核心问题：el-select 下拉面板遮挡确认按钮，且 Escape 会关闭整个 el-popover
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def diagnose_value_help_filter():
    """诊断 value_help 过滤器的测试困难点"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        # 收集 console 日志
        console_logs = []
        page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))

        try:
            # 1. 登录
            print("\n" + "=" * 60)
            print("诊断：value_help 过滤器测试困难点排查")
            print("=" * 60)

            print("\n[步骤1] 登录...")
            page.goto('http://localhost:3004/login', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)
            page.fill('input[type="text"]', 'admin')
            page.fill('input[type="password"]', 'admin123')
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)
            print("   [DECORATIVE] 登录完成")

            # 2. 导航到用户组页面
            print("\n[步骤2] 导航到用户组页面...")
            page.goto('http://localhost:3004/user-permission?tab=user-groups', wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(5000)

            # 3. 找到父组列并打开过滤器
            print("\n[步骤3] 查找父组列过滤器...")
            headers = page.locator('.el-table__header th')
            parent_col_idx = -1
            for i in range(headers.count()):
                text = headers.nth(i).text_content().strip()
                if '父组' in text:
                    parent_col_idx = i
                    print(f"   [DECORATIVE] 找到父组列 (第 {i+1} 列)")
                    break

            if parent_col_idx < 0:
                print("   [DECORATIVE] 没有找到父组列，退出")
                return

            trigger = headers.nth(parent_col_idx).locator('.filter-trigger')
            if trigger.count() == 0:
                print("   [DECORATIVE] 该列没有过滤器触发器，退出")
                return

            # 4. 打开 popover
            print("\n[步骤4] 打开过滤器 popover...")
            trigger.first.click()
            page.wait_for_timeout(1500)

            # 检查 popover 和 filter-panel 状态
            filter_panel = page.locator('.filter-panel:visible')
            popover_count = filter_panel.count()
            print(f"   filter-panel:visible 数量: {popover_count}")

            if popover_count == 0:
                print("   [DECORATIVE] filter-panel 不可见！")
                # 检查是否有 el-popover 存在
                all_popovers = page.locator('.el-popover')
                print(f"   el-popover 总数: {all_popovers.count()}")
                for i in range(all_popovers.count()):
                    vis = all_popovers.nth(i).is_visible()
                    print(f"   el-popover[{i}]: visible={vis}")
                return

            # 5. 诊断 filter-panel 结构
            print("\n[步骤5] 诊断 filter-panel 结构...")
            panel_html = filter_panel.first.inner_html()
            print(f"   filter-panel HTML 长度: {len(panel_html)}")

            # 检查 value_help 组件
            vh_field = filter_panel.locator('.value-help-field')
            print(f"   value-help-field 数量: {vh_field.count()}")

            # 检查确认按钮（value_help 的确认按钮在顶部）
            confirm_btn = filter_panel.locator('.el-button--primary')
            print(f"   确认按钮数量: {confirm_btn.count()}")
            if confirm_btn.count() > 0:
                print(f"   确认按钮可见: {confirm_btn.first.is_visible()}")
                print(f"   确认按钮文本: {confirm_btn.first.text_content().strip()}")

            # 检查 el-select
            el_select = filter_panel.locator('.el-select')
            print(f"   el-select 数量: {el_select.count()}")

            # 6. 点击 el-select 打开下拉
            print("\n[步骤6] 点击 el-select 打开下拉...")
            el_select.first.click()
            page.wait_for_timeout(2000)

            # 7. 诊断下拉面板状态
            print("\n[步骤7] 诊断下拉面板状态...")

            # 检查所有 el-select-dropdown
            all_dropdowns = page.locator('.el-select-dropdown')
            visible_dropdowns = page.locator('.el-select-dropdown:visible')
            print(f"   el-select-dropdown 总数: {all_dropdowns.count()}")
            print(f"   el-select-dropdown:visible 数量: {visible_dropdowns.count()}")

            # 检查 filter-panel 是否仍然可见
            print(f"   filter-panel 仍然可见: {filter_panel.first.is_visible()}")
            print(f"   确认按钮仍然可见: {confirm_btn.first.is_visible() if confirm_btn.count() > 0 else 'N/A'}")

            # 8. 选择一个选项
            print("\n[步骤8] 选择选项...")
            options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
            opt_count = options.count()
            print(f"   可见选项数量: {opt_count}")

            if opt_count > 0:
                # 找到第一个非分页选项
                target_opt = None
                for j in range(opt_count):
                    opt_text = options.nth(j).text_content().strip()
                    if '条/页' not in opt_text:
                        target_opt = options.nth(j)
                        print(f"   [DECORATIVE] 选择选项: {opt_text}")
                        break

                if target_opt:
                    target_opt.click()
                    page.wait_for_timeout(500)
                    print("   [DECORATIVE] 选项已选择")

            # 9. 诊断选择后的状态
            print("\n[步骤9] 选择选项后的状态...")
            print(f"   filter-panel 可见: {filter_panel.first.is_visible()}")
            print(f"   确认按钮可见: {confirm_btn.first.is_visible() if confirm_btn.count() > 0 else 'N/A'}")
            print(f"   el-select-dropdown:visible 数量: {page.locator('.el-select-dropdown:visible').count()}")

            # 10. 尝试方法1：点击空白区域关闭下拉（不关闭 popover）
            print("\n[步骤10] 方法1：点击 filter-panel 空白区域关闭下拉...")
            # 点击 filter-panel 本身（不是 el-select 内部），应该只关闭 el-select 下拉
            filter_panel.first.click(position={'x': 10, 'y': 10})
            page.wait_for_timeout(1000)

            dropdown_after = page.locator('.el-select-dropdown:visible').count()
            panel_after = filter_panel.first.is_visible()
            btn_after = confirm_btn.first.is_visible() if confirm_btn.count() > 0 else False
            print(f"   el-select-dropdown:visible: {dropdown_after}")
            print(f"   filter-panel 可见: {panel_after}")
            print(f"   确认按钮可见: {btn_after}")

            if btn_after:
                print("   [DECORATIVE] 方法1成功！确认按钮可见了")
                confirm_btn.first.click()
                page.wait_for_timeout(1000)
                print("   [DECORATIVE] 点击确认按钮成功")
            else:
                # 11. 方法2：通过 JS 关闭 el-select 下拉
                print("\n[步骤11] 方法1失败，尝试方法2：JS 关闭 el-select 下拉...")
                # 重新打开 popover
                trigger.first.click()
                page.wait_for_timeout(500)
                trigger.first.click()
                page.wait_for_timeout(1500)

                # 检查 popover 是否重新打开
                if filter_panel.first.is_visible():
                    print("   [DECORATIVE] popover 重新打开了")

                    # 点击 el-select 打开下拉
                    el_select.first.click()
                    page.wait_for_timeout(2000)

                    # 选择选项
                    options2 = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
                    for j in range(options2.count()):
                        opt_text = options2.nth(j).text_content().strip()
                        if '条/页' not in opt_text:
                            options2.nth(j).click()
                            page.wait_for_timeout(500)
                            print(f"   [DECORATIVE] 选择了: {opt_text}")
                            break

                    # 通过 JS 关闭 el-select 下拉
                    page.evaluate("""() => {
                        // 找到所有可见的 el-select-dropdown 并隐藏
                        document.querySelectorAll('.el-select-dropdown').forEach(el => {
                            if (el.style.display !== 'none') {
                                el.style.display = 'none';
                            }
                        });
                    }""")
                    page.wait_for_timeout(500)

                    btn_vis = confirm_btn.first.is_visible() if confirm_btn.count() > 0 else False
                    print(f"   JS 隐藏后确认按钮可见: {btn_vis}")

                    if btn_vis:
                        confirm_btn.first.click()
                        page.wait_for_timeout(1000)
                        print("   [DECORATIVE] 方法2成功！点击确认按钮")
                    else:
                        # 12. 方法3：使用 force click
                        print("\n[步骤12] 方法2失败，尝试方法3：force click...")
                        if confirm_btn.count() > 0:
                            confirm_btn.first.click(force=True)
                            page.wait_for_timeout(1000)
                            print("   [DECORATIVE] force click 执行完毕")
                        else:
                            print("   [DECORATIVE] 确认按钮不存在")

                else:
                    print("   [DECORATIVE] popover 未重新打开")

            # 13. 检查过滤结果
            print("\n[步骤13] 检查过滤结果...")
            rows = page.locator('.el-table__body tr')
            row_count = rows.count()
            print(f"   表格行数: {row_count}")

            # 检查是否有 active 过滤器
            active_filters = page.locator('.filter-trigger.is-active')
            print(f"   活跃过滤器数量: {active_filters.count()}")

            # 14. 输出 console 错误
            print("\n[步骤14] Console 错误日志:")
            errors = [log for log in console_logs if '[error]' in log.lower() or 'error' in log.lower()]
            if errors:
                for err in errors[:10]:
                    print(f"   {err}")
            else:
                print("   无错误日志")

            # 15. 截图
            print("\n[步骤15] 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_diagnose_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   [DECORATIVE] 截图保存到: {screenshot_path}")

            # 总结
            print("\n" + "=" * 60)
            print("诊断总结")
            print("=" * 60)
            print("""
核心问题：el-select 下拉面板遮挡确认按钮

原因分析：
1. ValueHelpField 使用 el-select 渲染下拉选项
2. el-select 的下拉面板 (el-select-dropdown) 是 teleport 到 body 的
3. 下拉面板 z-index 高于 el-popover，遮挡了 popover 内的确认按钮
4. 按 Escape 会关闭整个 el-popover（因为 el-popover 也监听 Escape），而不是只关闭 el-select 下拉
5. 点击空白区域可能同时触发 el-popover 的 clickOutside 关闭逻辑

可能的解决方案：
A. 在 TableHeaderFilter 中，value_help 类型的确认按钮放在 el-select 上方
   （已实现 filter-actions--top，但 el-select 下拉仍然遮挡）
B. 修改 ValueHelpField 的 el-select 配置，让下拉面板不遮挡确认按钮
C. 在测试中，使用点击空白区域方式关闭 el-select 下拉（而非 Escape）
D. 修改 el-select 的 popper-append-to-body 为 false，让下拉在 popover 内部渲染
""")

        except Exception as e:
            print(f"\n[DECORATIVE] 诊断失败: {e}")
            import traceback
            traceback.print_exc()

            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_diagnose_error.png')
            page.screenshot(path=screenshot_path, full_page=True)

        finally:
            browser.close()


if __name__ == '__main__':
    diagnose_value_help_filter()
