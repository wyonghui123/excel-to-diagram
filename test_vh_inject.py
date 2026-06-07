#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
排查 value_help 过滤器 - 检查 column.prop 和 headerFilterValues
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def test_column_prop_and_values():
    """检查 column.prop 和 headerFilterValues 的值"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        console_logs = []
        page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))

        try:
            print("\n" + "=" * 60)
            print("检查 column.prop 和 headerFilterValues")
            print("=" * 60)

            # 1. 登录
            print("\n[步骤1] 登录...")
            page.goto('http://localhost:3004/login', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)
            page.fill('input[type="text"]', 'admin')
            page.fill('input[type="password"]', 'admin123')
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)

            # 2. 导航到用户组页面
            print("\n[步骤2] 导航到用户组页面...")
            page.goto('http://localhost:3004/user-permission?tab=user-groups', wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(5000)

            # 3. 注入代码来拦截 handleHeaderFilter 调用
            print("\n[步骤3] 注入拦截代码...")
            page.evaluate("""() => {
                // 在 window 上存储调试信息
                window._debugInfo = {
                    handleHeaderFilterCalls: [],
                    headerFilterValuesSnapshots: [],
                };
                
                // 拦截 fetch 请求
                const origFetch = window.fetch;
                window.fetch = function(...args) {
                    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url;
                    if (url && url.includes('user-group')) {
                        console.log('[DEBUG-FETCH] ' + url);
                        // 解析 URL 参数
                        const urlObj = new URL(url, 'http://localhost');
                        const params = Object.fromEntries(urlObj.searchParams.entries());
                        console.log('[DEBUG-PARAMS] ' + JSON.stringify(params));
                    }
                    return origFetch.apply(this, args);
                };
            }""")

            # 4. 打开父组过滤器
            print("\n[步骤4] 打开父组过滤器...")
            headers = page.locator('.el-table__header th')
            parent_col_idx = -1
            for i in range(headers.count()):
                text = headers.nth(i).text_content().strip()
                if '父组' in text:
                    parent_col_idx = i
                    break

            trigger = headers.nth(parent_col_idx).locator('.filter-trigger')
            trigger.first.click()
            page.wait_for_timeout(1500)

            # 5. 选择选项
            print("\n[步骤5] 选择选项...")
            el_select = page.locator('.filter-panel:visible .el-select')
            el_select.first.click()
            page.wait_for_timeout(2000)

            options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
            for j in range(options.count()):
                opt_text = options.nth(j).text_content().strip()
                if '条/页' not in opt_text:
                    print(f"   选择: {opt_text}")
                    options.nth(j).click()
                    page.wait_for_timeout(500)
                    break

            # 6. 检查 ValueHelpField 内部状态
            print("\n[步骤6] 检查 ValueHelpField 内部状态...")
            vh_state = page.evaluate("""() => {
                // 找到 el-select 组件
                const selectWrapper = document.querySelector('.filter-panel .el-select');
                if (!selectWrapper) return 'No el-select wrapper';
                
                // Vue 3: 通过 __vue_parent_component 获取组件实例
                let comp = selectWrapper.__vue_parent_component;
                if (!comp) return 'No component';
                
                // 遍历找到 el-select 组件
                let selectComp = null;
                let current = comp;
                let depth = 0;
                while (current && depth < 10) {
                    if (current.type?.name === 'ElSelect' || current.type?.__name === 'ElSelect') {
                        selectComp = current;
                        break;
                    }
                    current = current.subTree?.component || current.subTree?.children?.[0]?.component;
                    depth++;
                }
                
                if (!selectComp) {
                    // 尝试直接获取 props
                    return {
                        compName: comp.type?.name || comp.type?.__name,
                        propsKeys: comp.props ? Object.keys(comp.props) : [],
                        modelValue: comp.props?.modelValue !== undefined ? 
                            JSON.stringify(comp.props.modelValue) : 'undefined',
                    };
                }
                
                return {
                    selectFound: true,
                    modelValue: JSON.stringify(selectComp.props?.modelValue),
                    multiple: selectComp.props?.multiple,
                };
            }""")
            print(f"   ValueHelpField 状态: {vh_state}")

            # 7. 点击确认按钮
            print("\n[步骤7] 点击确认按钮...")
            console_logs.clear()

            confirm_btn = page.locator('.filter-panel:visible .el-button--primary')
            if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                confirm_btn.first.click()
                page.wait_for_timeout(3000)
            else:
                filter_panel = page.locator('.filter-panel:visible')
                if filter_panel.count() > 0:
                    filter_panel.first.click(position={'x': 10, 'y': 10})
                    page.wait_for_timeout(500)
                    if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                        confirm_btn.first.click()
                        page.wait_for_timeout(3000)

            # 8. 输出调试日志
            print("\n[步骤8] 调试日志:")
            for log in console_logs:
                if 'DEBUG' in log or 'parent_id' in log or 'modelValue' in log or 'filter' in log.lower():
                    print(f"   {log}")

            # 9. 检查 headerFilterValues
            print("\n[步骤9] 检查 headerFilterValues...")
            hfv = page.evaluate("""() => {
                // 遍历所有 DOM 元素找 Vue 组件
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                    const comp = el.__vue_parent_component;
                    if (!comp) continue;
                    
                    const ss = comp.setupState;
                    if (ss && ss.headerFilterValues) {
                        const val = ss.headerFilterValues;
                        // 检查是否是 ref
                        if (val && typeof val === 'object' && '__v_isRef' in val) {
                            return {
                                isRef: true,
                                value: JSON.stringify(val.value || val),
                            };
                        }
                        return {
                            isRef: false,
                            value: JSON.stringify(val),
                            type: typeof val,
                            keys: Object.keys(val),
                        };
                    }
                }
                return 'Not found in any component';
            }""")
            print(f"   headerFilterValues: {hfv}")

        except Exception as e:
            print(f"\n[DECORATIVE] 测试失败: {e}")
            import traceback
            traceback.print_exc()

        finally:
            browser.close()


if __name__ == '__main__':
    test_column_prop_and_values()
