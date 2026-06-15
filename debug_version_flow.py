"""
复现 user 的流程：选 product+version -> 点击新建 -> 看 version_id 字段值
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    print('=== Step 1: 登录并打开架构数据管理 ===')
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-tabs')
    cli.wait_for_stable(3000)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/version_step1_archdata.png')

    # 2. 找到 product selector 和 version selector
    print('\n=== Step 2: 检查 GlobalToolbar 是否有 product/version selector ===')
    # 查所有 el-select 数量
    info = cli.evaluate('''() => {
        const selects = document.querySelectorAll('.el-select')
        const result = []
        selects.forEach((s, i) => {
            const rect = s.getBoundingClientRect()
            const wrap = s.closest('.global-toolbar, .toolbar, header, .arch-workspace-header, [class*="toolbar"], [class*="header"]')
            const placeholder = s.querySelector('.el-select__placeholder')?.textContent || ''
            const label = s.querySelector('.el-select__wrapper')?.textContent || ''
            result.push({
                index: i,
                placeholder: placeholder.trim(),
                label: label.trim().substring(0, 50),
                inToolbar: !!wrap,
                tag: wrap ? wrap.className.substring(0, 80) : 'no-toolbar',
                rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width)}
            })
        })
        return result
    }''')
    print(f'  找到 {len(info)} 个 el-select:')
    for s in info:
        print(f'    [{s["index"]}] placeholder="{s["placeholder"]}" in_toolbar={s["in_toolbar"]} tag={s["tag"]}')

    # 3. 选择第一个产品
    print('\n=== Step 3: 打开产品下拉 ===')
    # 找产品下拉 - placeholder 包含 产品
    product_select_idx = None
    for s in info:
        if '产品' in s['placeholder']:
            product_select_idx = s['index']
            break

    if product_select_idx is None:
        print('  [WARN] 没找到产品下拉，先看页面结构')
        # dump page structure
        struct = cli.evaluate('''() => {
            const items = []
            document.querySelectorAll('.el-select, .el-input, button').forEach(el => {
                const text = (el.textContent || '').trim().substring(0, 50)
                if (text) items.push({tag: el.tagName, class: el.className.substring(0, 60), text})
            })
            return items.slice(0, 30)
        }''')
        for s in struct:
            print('   ', s)
    else:
        print(f'  找到产品下拉 idx={product_select_idx}')
        cli.evaluate(f'''() => {{
            const selects = document.querySelectorAll('.el-select')
            const target = selects[{product_select_idx}]
            target.querySelector('.el-select__wrapper')?.click()
        }}''')
        cli.wait_for_stable(1500)

        # 查看下拉选项
        options = cli.evaluate('''() => {
            const opts = document.querySelectorAll('.el-select-dropdown:visible .el-select-dropdown__item')
            return Array.from(opts).map(o => o.textContent.trim())
        }''')
        print(f'  产品下拉选项 ({len(options)}): {options[:5]}')

        if options:
            # 选第一个
            cli.evaluate(f'''() => {{
                const opts = document.querySelectorAll('.el-select-dropdown:visible .el-select-dropdown__item')
                if (opts.length) opts[0].click()
            }}''')
            cli.wait_for_stable(2000)
            print('  [OK] 选中第一个产品')

    # 4. 打开版本下拉
    print('\n=== Step 4: 打开版本下拉 ===')
    info2 = cli.evaluate('''() => {
        const selects = document.querySelectorAll('.el-select')
        const result = []
        selects.forEach((s, i) => {
            const placeholder = s.querySelector('.el-select__placeholder')?.textContent || ''
            const label = s.querySelector('.el-select__wrapper')?.textContent || ''
            result.push({
                index: i,
                placeholder: placeholder.trim(),
                label: label.trim().substring(0, 50)
            })
        })
        return result
    }''')
    print(f'  选完产品后 el-select:')
    for s in info2:
        print(f'    [{s["index"]}] placeholder="{s["placeholder"]}" label="{s["label"]}"')

    version_select_idx = None
    for s in info2:
        if '版本' in s['placeholder']:
            version_select_idx = s['index']
            break

    if version_select_idx is not None:
        print(f'  找到版本下拉 idx={version_select_idx}')
        cli.evaluate(f'''() => {{
            const selects = document.querySelectorAll('.el-select')
            const target = selects[{version_select_idx}]
            target.querySelector('.el-select__wrapper')?.click()
        }}''')
        cli.wait_for_stable(1500)

        options = cli.evaluate('''() => {
            const opts = document.querySelectorAll('.el-select-dropdown:visible .el-select-dropdown__item')
            return Array.from(opts).map(o => o.textContent.trim())
        }''')
        print(f'  版本下拉选项 ({len(options)}): {options[:5]}')

        if options:
            cli.evaluate(f'''() => {{
                const opts = document.querySelectorAll('.el-select-dropdown:visible .el-select-dropdown__item')
                if (opts.length) opts[0].click()
            }}''')
            cli.wait_for_stable(2000)
            print('  [OK] 选中第一个版本')
    else:
        print('  [WARN] 没找到版本下拉')

    # 5. 验证 selectedVersionId 是否设置
    print('\n=== Step 5: 检查 version context ===')
    ctx = cli.evaluate('''() => {
        // 尝试从 Pinia store 读
        const pinia = window.__pinia?._s || window.$pinia?._s
        if (pinia) {
            const stores = {}
            pinia.forEach((store, key) => { stores[key] = key })
            return { stores, has_pinia: true }
        }
        return { has_pinia: false }
    }''')
    print(f'  Pinia stores: {ctx}')

    # 6. 切到领域 tab
    print('\n=== Step 6: 切到 domain tab ===')
    cli.evaluate('''() => {
        const tabs = document.querySelectorAll('.el-tabs__item')
        for (const t of tabs) {
            if (t.textContent.includes('领域')) {
                t.click()
                return
            }
        }
    }''')
    cli.wait_for_stable(1500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/version_step6_domain_tab.png')

    # 7. 点击新建
    print('\n=== Step 7: 点击"新建"按钮 ===')
    cli.evaluate('''() => {
        const buttons = document.querySelectorAll('button')
        for (const b of buttons) {
            if (b.textContent.trim() === '新建' || b.textContent.includes('新建')) {
                b.click()
                return true
            }
        }
        return false
    }''')
    cli.wait_for_stable(2500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/version_step7_new_clicked.png')

    # 8. 检查新页面/drawer 的 version_id 字段
    print('\n=== Step 8: 检查新表单的 version_id 字段 ===')
    form_info = cli.evaluate('''() => {
        const result = { url: window.location.href, fields: [] }
        // 找所有 form
        const forms = document.querySelectorAll('form, .el-form, .object-page, [class*="detail"]')
        result.formCount = forms.length

        // 找所有版本相关的 select / input
        document.querySelectorAll('.el-form-item, [class*="field"]').forEach((el, i) => {
            const label = el.querySelector('.el-form-item__label, label')?.textContent?.trim() || ''
            const input = el.querySelector('input, .el-select__wrapper')
            const inputVal = input?.value || input?.textContent?.trim() || ''
            if (label || inputVal) {
                result.fields.push({
                    index: i,
                    label: label.substring(0, 30),
                    value: inputVal.substring(0, 50)
                })
            }
        })
        return result
    }''')
    print(f'  URL: {form_info["url"]}')
    print(f'  找到 {len(form_info["fields"])} 个字段:')
    for f in form_info['fields'][:20]:
        print(f'    label="{f["label"]}" value="{f["value"]}"')

    # 9. 单独看 version_id 字段
    print('\n=== Step 9: 单独看 version 字段 ===')
    version_field = cli.evaluate('''() => {
        const items = document.querySelectorAll('.el-form-item')
        for (const item of items) {
            const label = item.querySelector('.el-form-item__label')?.textContent?.trim() || ''
            if (label === '版本' || label === 'version_id' || label.includes('版本')) {
                const input = item.querySelector('input')
                const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
                const placeholder = item.querySelector('.el-select__placeholder')?.textContent?.trim()
                return {
                    label,
                    inputValue: input?.value,
                    selectValue: selectVal,
                    placeholder,
                    isDisabled: input?.disabled,
                    isReadonly: input?.readOnly
                }
            }
        }
        return { found: false }
    }''')
    print(f'  version 字段: {version_field}')

    print('\n=== Done ===')
