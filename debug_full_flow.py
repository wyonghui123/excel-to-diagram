"""
完整流程（修过 querySelector）: 选 product+version -> 切到 domain tab -> 新建 -> 检查 version 字段
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def find_visible_dropdown_items(cli):
    """使用 checkVisibility 找可见下拉项"""
    return cli.evaluate('''() => {
        const allDropdowns = document.querySelectorAll('.el-select-dropdown')
        const visibleDropdowns = []
        allDropdowns.forEach(d => {
            if (d.checkVisibility && d.checkVisibility()) {
                const items = d.querySelectorAll('.el-select-dropdown__item')
                items.forEach(i => visibleDropdowns.push(i.textContent.trim()))
            }
        })
        return visibleDropdowns
    }''')

def find_visible_elselect_dropdowns(cli):
    return cli.evaluate('''() => {
        const all = document.querySelectorAll('.el-select-dropdown')
        const visible = []
        all.forEach(d => {
            if (d.checkVisibility && d.checkVisibility()) {
                visible.push(d.className)
            }
        })
        return visible
    }''')

with PlaywrightCLI() as cli:
    print('=== Step 1: 打开架构数据管理 ===')
    cli.authenticated_navigate('/system/archdata')
    cli.wait_for_stable(2500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/full2_step1.png')

    # Step 2: 选择产品
    print('\n=== Step 2: 选产品 ===')
    cli.evaluate('''() => {
        const selects = document.querySelectorAll('.el-select')
        // 第一个是产品
        const wrapper = selects[0].querySelector('.el-select__wrapper')
        if (wrapper) wrapper.click()
    }''')
    cli.wait_for_stable(1500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/full2_step2_product_dropdown.png')

    options = find_visible_dropdown_items(cli)
    print(f'  产品下拉选项: {options[:5]}')

    if options:
        cli.evaluate('''() => {
            const allDropdowns = document.querySelectorAll('.el-select-dropdown')
            for (const d of allDropdowns) {
                if (d.checkVisibility && d.checkVisibility()) {
                    const items = d.querySelectorAll('.el-select-dropdown__item')
                    if (items[0]) { items[0].click(); return }
                }
            }
        }''')
        cli.wait_for_stable(2500)
        print('  [OK] 选中第一个产品')
        cli.screenshot('d:/filework/excel-to-diagram/test_output/full2_step2_product_selected.png')

    # Step 3: 选版本
    print('\n=== Step 3: 选版本 ===')
    # 检查 el-select 状态
    state = cli.evaluate('''() => {
        return Array.from(document.querySelectorAll('.el-select')).map((s, i) => {
            const ph = s.querySelector('.el-select__placeholder')?.textContent?.trim() || ''
            const wrap = s.querySelector('.el-select__wrapper')?.textContent?.trim() || ''
            const isDisabled = s.classList.contains('is-disabled')
            return { idx: i, ph, wrap: wrap.substring(0, 30), isDisabled }
        })
    }''')
    print(f'  选完产品后 el-select 状态:')
    for s in state:
        print(f'    [{s["idx"]}] ph="{s["ph"]}" wrap="{s["wrap"]}" disabled={s["isDisabled"]}')

    # 点击版本下拉
    cli.evaluate('''() => {
        const selects = document.querySelectorAll('.el-select')
        for (const s of selects) {
            const wrapper = s.querySelector('.el-select__wrapper')
            if (wrapper && !s.classList.contains('is-disabled')) {
                wrapper.click()
                return
            }
        }
    }''')
    cli.wait_for_stable(1500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/full2_step3_version_dropdown.png')

    options = find_visible_dropdown_items(cli)
    print(f'  版本下拉选项: {options[:5]}')

    if options:
        cli.evaluate('''() => {
            const allDropdowns = document.querySelectorAll('.el-select-dropdown')
            for (const d of allDropdowns) {
                if (d.checkVisibility && d.checkVisibility()) {
                    const items = d.querySelectorAll('.el-select-dropdown__item')
                    if (items[0]) { items[0].click(); return }
                }
            }
        }''')
        cli.wait_for_stable(2500)
        print('  [OK] 选中第一个版本')
        cli.screenshot('d:/filework/excel-to-diagram/test_output/full2_step3_version_selected.png')

    # Step 4: 检查页面状态
    print('\n=== Step 4: 检查页面状态（应该出现 tabs）===')
    page_state = cli.evaluate('''() => {
        const state = {
            url: window.location.href,
            tabsList: [],
            buttons: []
        }
        document.querySelectorAll('.el-tabs__item, [role="tab"]').forEach(t => {
            state.tabsList.push(t.textContent.trim().substring(0, 30))
        })
        document.querySelectorAll('button').forEach(b => {
            const t = b.textContent.trim()
            if (t) state.buttons.push(t.substring(0, 30))
        })
        return state
    }''')
    print(f'  URL: {page_state["url"]}')
    print(f'  tabs: {page_state["tabsList"]}')
    print(f'  buttons: {page_state["buttons"]}')

    # Step 5: 切到领域 tab
    print('\n=== Step 5: 切到领域 tab ===')
    if page_state['tabsList']:
        cli.evaluate('''() => {
            const tabs = document.querySelectorAll('.el-tabs__item')
            for (const t of tabs) {
                if (t.textContent.includes('领域') || t.textContent.includes('domain') || t.textContent.includes('Domain')) {
                    t.click()
                    return t.textContent.trim()
                }
            }
            return 'not found'
        }''')
        cli.wait_for_stable(2000)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/full2_step5_domain_tab.png')

    # 找"新建"按钮
    print('\n=== Step 6: 找"新建"按钮 ===')
    new_btn = cli.evaluate('''() => {
        const buttons = document.querySelectorAll('button')
        for (const b of buttons) {
            const text = b.textContent.trim()
            if (text === '新建' || text === '新 建' || text.includes('新建')) {
                const rect = b.getBoundingClientRect()
                return {
                    text: text,
                    visible: rect.width > 0 && rect.height > 0,
                    class: b.className.substring(0, 100)
                }
            }
        }
        return null
    }''')
    print(f'  新建按钮: {new_btn}')

    if new_btn:
        cli.evaluate('''() => {
            const buttons = document.querySelectorAll('button')
            for (const b of buttons) {
                const text = b.textContent.trim()
                if (text === '新建' || text === '新 建' || text.includes('新建')) {
                    b.click()
                    return true
                }
            }
            return false
        }''')
        cli.wait_for_stable(3500)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/full2_step6_new_clicked.png')

        # Step 7: 检查表单
        print('\n=== Step 7: 检查新表单 ===')
        new_state = cli.evaluate('''() => {
            return {
                url: window.location.href,
                hasForm: !!document.querySelector('.el-form, [class*="detail-page"]'),
            }
        }''')
        print(f'  URL: {new_state["url"]}')
        print(f'  hasForm: {new_state["hasForm"]}')

        # 看 version 字段
        version_field = cli.evaluate('''() => {
            const items = document.querySelectorAll('.el-form-item')
            for (const item of items) {
                const label = item.querySelector('.el-form-item__label')?.textContent?.trim() || ''
                if (label.includes('版本') || label === 'version_id' || label === 'version') {
                    const input = item.querySelector('input')
                    const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
                    const placeholder = item.querySelector('.el-select__placeholder')?.textContent?.trim()
                    return {
                        label,
                        inputValue: input?.value,
                        selectValue: selectVal,
                        placeholder,
                        isDisabled: input?.disabled,
                    }
                }
            }
            return { found: false }
        }''')
        print(f'  version 字段: {version_field}')

        # 看所有字段
        all_fields = cli.evaluate('''() => {
            const items = document.querySelectorAll('.el-form-item')
            return Array.from(items).map(item => {
                const label = item.querySelector('.el-form-item__label')?.textContent?.trim() || ''
                const input = item.querySelector('input')
                const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
                return { label, value: input?.value || selectVal || '' }
            })
        }''')
        print(f'\n  所有表单字段:')
        for f in all_fields:
            print(f'    {f}')

        # 注入代码看 version context 状态
        print('\n=== Step 8: 看 Pinia store / version context ===')
        ctx = cli.evaluate('''() => {
            const root = document.getElementById('app')?.__vue_app__
            if (!root) return { error: 'no app' }
            const pinia = root.config.globalProperties.$pinia
            if (!pinia) return { error: 'no pinia' }
            const stores = {}
            pinia._s.forEach((store, key) => {
                stores[key] = Object.keys(store.$state || {})
            })
            return stores
        }''')
        print(f'  Pinia stores: {ctx}')

    print('\n=== Done ===')
